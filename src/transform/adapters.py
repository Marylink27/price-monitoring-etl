"""Приведение ответов разных площадок к единой схеме предложения."""
from __future__ import annotations

import pandas as pd

from .parsing import parse_price, parse_volume

UNIFIED_COLUMNS = ["source", "offer_id", "raw_name", "brand", "price", "old_price",
                   "volume_l", "pack_qty", "in_stock"]


def _market_a(it: dict) -> dict:
    return {"offer_id": it.get("id"), "raw_name": it.get("title"), "brand": it.get("brand"),
            "price": parse_price(it.get("price")), "old_price": parse_price(it.get("old_price")),
            "in_stock": bool(it.get("available"))}


def _market_b(it: dict) -> dict:
    price_info = it.get("priceInfo") or {}
    return {"offer_id": it.get("sku"), "raw_name": it.get("name"), "brand": it.get("vendor"),
            "price": parse_price(price_info.get("current"), unit="kopecks"), "old_price": None,
            "in_stock": (it.get("stock") or 0) > 0}


def _market_c(it: dict) -> dict:
    return {"offer_id": it.get("offer_id"), "raw_name": it.get("nm"), "brand": it.get("brand"),
            "price": parse_price(it.get("price")), "old_price": None,
            "in_stock": bool(it.get("in_stock"))}


ADAPTERS = {"market_a": _market_a, "market_b": _market_b, "market_c": _market_c}


def to_unified(source: str, items: list[dict]) -> pd.DataFrame:
    """Список позиций площадки в DataFrame единого формата."""
    rows = []
    for it in items:
        rec = ADAPTERS[source](it)
        rec["volume_l"], rec["pack_qty"] = parse_volume(rec["raw_name"] or "")
        rec["source"] = source
        rows.append(rec)
    return pd.DataFrame(rows, columns=UNIFIED_COLUMNS)
