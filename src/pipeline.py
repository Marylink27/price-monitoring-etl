"""Оркестрация ETL: extract -> transform -> load -> витрины -> Excel-отчёт.

Примеры:
    python -m src.pipeline --date 2026-10-20
    python -m src.pipeline --start 2026-10-07 --end 2026-10-20
    python -m src.pipeline --date 2026-10-20 --mode live
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from .config import load_config
from .extract import HttpTransport, MarketplaceClient, MockMarketplaceAPI, MockTransport
from .load import build_marts, connect, init_schema, load_snapshot
from .report import build_report
from .transform import SkuMatcher, add_unit_prices, deduplicate, to_unified, validate

log = logging.getLogger("pipeline")

MATCH_COLUMNS = ["source", "offer_id", "sku_id", "pack_qty", "unit_price", "price_per_l",
                 "in_stock", "match_score", "match_method"]


def setup_logging(log_dir: str) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(Path(log_dir) / "pipeline.log", encoding="utf-8"),
                  logging.StreamHandler()],
        force=True,
    )


def _transports(cfg: dict, mode: str, catalog: pd.DataFrame, snapshot_date: date) -> dict:
    """Транспорт и параметры клиента для каждого источника в зависимости от режима."""
    result = {}
    if mode == "mock":
        api = MockMarketplaceAPI(catalog, snapshot_date)
        transport = MockTransport(api, cfg["sources"], fail_rate=cfg["mock"]["fail_rate"],
                                  seed=snapshot_date.toordinal())
        for name, src in cfg["sources"].items():
            src_cfg = src | {"min_interval": cfg["mock"]["min_interval"], "backoff": cfg["mock"]["backoff"]}
            result[name] = (src_cfg, transport)
    else:
        for name, src in cfg["sources"].items():
            result[name] = (src, HttpTransport(timeout=src["timeout"], token_env=src.get("token_env")))
    return result


def run(snapshot_date: date, cfg: dict, mode: str | None = None, make_report: bool = True,
        db_path: str | None = None) -> dict:
    """Полный прогон за одну дату. Возвращает сводку с числами и временем."""
    t0 = time.perf_counter()
    mode = mode or cfg["mode"]
    catalog = pd.read_csv(cfg["paths"]["catalog"])
    matcher = SkuMatcher(catalog, **cfg["matching"])

    all_offers, all_rejects, all_matches, log_rows = [], [], [], []
    for name, (src_cfg, transport) in _transports(cfg, mode, catalog, snapshot_date).items():
        ts = time.perf_counter()
        client = MarketplaceClient(name, src_cfg, transport)
        raw = to_unified(name, client.fetch_all())
        offers, n_dup = deduplicate(raw)
        valid, rejects = validate(offers, **cfg["validation"])
        valid = matcher.match(add_unit_prices(valid))
        matched = valid[valid["sku_id"].notna()]
        all_offers.append(offers)
        all_rejects.append(rejects)
        all_matches.append(matched[MATCH_COLUMNS])
        log_rows.append({"source": name, "n_raw": len(raw), "n_duplicates": n_dup,
                         "n_rejected": len(rejects), "n_valid": len(valid), "n_matched": len(matched),
                         "n_requests": client.stats["requests"], "n_retries": client.stats["retries"],
                         "seconds": round(time.perf_counter() - ts, 3)})
        log.info("%s %s: сырых %d, дублей %d, отклонено %d, сопоставлено %d из %d",
                 snapshot_date, name, len(raw), n_dup, len(rejects), len(matched), len(valid))

    con = connect(db_path or cfg["paths"]["db"])
    try:
        init_schema(con)
        load_snapshot(con, snapshot_date, catalog,
                      pd.concat(all_offers, ignore_index=True), pd.concat(all_rejects, ignore_index=True),
                      pd.concat(all_matches, ignore_index=True), pd.DataFrame(log_rows), cfg["pricing"])
        build_marts(con)
        report_path = None
        elapsed_etl = time.perf_counter() - t0
        if make_report:
            report_path = build_report(con, snapshot_date, cfg["paths"]["reports"], elapsed_etl)
    finally:
        con.close()

    elapsed = round(time.perf_counter() - t0, 2)
    summary = {"date": snapshot_date.isoformat(), "seconds": elapsed,
               "offers": int(sum(r["n_raw"] for r in log_rows)),
               "matched": int(sum(r["n_matched"] for r in log_rows)),
               "report": str(report_path) if report_path else None}
    log.info("Готово за %s: %d предложений, %d сопоставлено, %.2f с, отчёт: %s",
             summary["date"], summary["offers"], summary["matched"], elapsed, summary["report"])
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL мониторинга цен конкурентов")
    parser.add_argument("--date", help="дата снимка, ГГГГ-ММ-ДД (по умолчанию сегодня)")
    parser.add_argument("--start", help="начало периода для загрузки истории")
    parser.add_argument("--end", help="конец периода (включительно)")
    parser.add_argument("--mode", choices=["mock", "live"], help="переопределяет mode из config.yaml")
    parser.add_argument("--config", help="путь к config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    setup_logging(cfg["paths"]["logs"])
    if args.start:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else start
        days = [start + timedelta(d) for d in range((end - start).days + 1)]
    else:
        days = [date.fromisoformat(args.date) if args.date else date.today()]
    for i, d in enumerate(days):
        run(d, cfg, mode=args.mode, make_report=(i == len(days) - 1))


if __name__ == "__main__":
    main()
