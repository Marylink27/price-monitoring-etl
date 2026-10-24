"""Проверка качества матчинга на разметке имитатора.

Имитатор знает, какому SKU соответствует каждое предложение (или что товара нет в матрице).
Пайплайн эту разметку не видит; здесь она используется только для оценки точности и полноты.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from .extract import MarketplaceClient, MockMarketplaceAPI, MockTransport
from .transform import SkuMatcher, add_unit_prices, deduplicate, to_unified, validate


def evaluate_matching(cfg: dict, snapshot_date: date) -> pd.DataFrame:
    """Таблица предложений с предсказанным и истинным SKU."""
    catalog = pd.read_csv(cfg["paths"]["catalog"])
    api = MockMarketplaceAPI(catalog, snapshot_date)
    transport = MockTransport(api, cfg["sources"], fail_rate=0.0)
    matcher = SkuMatcher(catalog, **cfg["matching"])
    frames = []
    for name, src in cfg["sources"].items():
        client = MarketplaceClient(name, src | {"min_interval": 0, "backoff": 0}, transport)
        offers, _ = deduplicate(to_unified(name, client.fetch_all()))
        valid, _ = validate(offers, **cfg["validation"])
        res = matcher.match(add_unit_prices(valid))
        res["true_sku"] = res["offer_id"].map(api.truth[name])
        frames.append(res)
    return pd.concat(frames, ignore_index=True)


def matching_metrics(df: pd.DataFrame) -> dict:
    """Точность: доля верных среди сопоставленных. Полнота: доля найденных среди наших товаров."""
    predicted = df["sku_id"].notna()
    ours = df["true_sku"].notna()
    correct = predicted & (df["sku_id"] == df["true_sku"])
    return {
        "offers": int(len(df)),
        "precision": round(correct.sum() / max(predicted.sum(), 1), 4),
        "recall": round(correct.sum() / max(ours.sum(), 1), 4),
        "false_matches": int((predicted & ~correct).sum()),
        "missed": int((ours & ~predicted).sum()),
        "foreign_rejected": int((~ours & ~predicted).sum()),
    }
