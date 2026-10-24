"""Загрузка в хранилище (DuckDB) и пересборка витрин.

Загрузка инкрементальная по дате снимка: перед вставкой данные за эту дату удаляются
в той же транзакции, поэтому повторный запуск за день не создаёт дублей.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from ..config import ROOT

SQL_DIR = ROOT / "sql"
DATED_TABLES = ["staging.offers", "staging.rejects", "core.own_prices", "core.offer_matches", "core.load_log"]


def connect(db_path: str | Path, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path), read_only=read_only)


def init_schema(con: duckdb.DuckDBPyConnection) -> None:
    con.execute((SQL_DIR / "schema_duckdb.sql").read_text(encoding="utf-8"))


def build_marts(con: duckdb.DuckDBPyConnection) -> None:
    """Выполняет sql/marts/*.sql по порядку имён файлов."""
    for path in sorted((SQL_DIR / "marts").glob("*.sql")):
        con.execute(path.read_text(encoding="utf-8"))


def _insert(con: duckdb.DuckDBPyConnection, table: str, df: pd.DataFrame) -> None:
    if df.empty:
        return
    con.register("_df", df)
    cols = ", ".join(df.columns)
    con.execute(f"INSERT INTO {table} ({cols}) SELECT {cols} FROM _df")
    con.unregister("_df")


def load_snapshot(con: duckdb.DuckDBPyConnection, snapshot_date: date, catalog: pd.DataFrame,
                  offers: pd.DataFrame, rejects: pd.DataFrame, matches: pd.DataFrame,
                  load_log: pd.DataFrame, pricing: dict) -> None:
    """Перезаписывает все данные за дату одной транзакцией."""
    con.execute("BEGIN TRANSACTION")
    try:
        for table in DATED_TABLES:
            con.execute(f"DELETE FROM {table} WHERE snapshot_date = ?", [snapshot_date])
        con.execute("DELETE FROM core.own_catalog")
        _insert(con, "core.own_catalog", catalog)
        con.execute("DELETE FROM core.pricing_params")
        con.execute("INSERT INTO core.pricing_params VALUES (?, ?, ?)",
                    [pricing["in_market_band"], pricing["alert_threshold"], pricing["min_margin"]])
        own = catalog[["sku_id", "own_price", "purchase_price"]].assign(snapshot_date=snapshot_date)
        _insert(con, "core.own_prices", own)
        _insert(con, "staging.offers", offers.assign(snapshot_date=snapshot_date))
        _insert(con, "staging.rejects", rejects.assign(snapshot_date=snapshot_date))
        _insert(con, "core.offer_matches", matches.assign(snapshot_date=snapshot_date))
        _insert(con, "core.load_log", load_log.assign(snapshot_date=snapshot_date))
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
