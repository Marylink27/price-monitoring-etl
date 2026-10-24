"""Excel-отчёт для категорийного менеджера.

Формат: Calibri 10, строка итогов над шапкой (итоги через ПРОМЕЖУТОЧНЫЕ.ИТОГИ, поэтому
пересчитываются при фильтрации), автофильтр на шапке, без заливок и декора.
Рекомендованная цена округляется до десятков.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import duckdb
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

FONT = Font(name="Calibri", size=10)
FONT_BOLD = Font(name="Calibri", size=10, bold=True)
SUBTOTAL_CODE = {"count": 103, "sum": 109, "avg": 101}


def round_to_tens(x: float) -> int:
    """Округление до десятков по правилам арифметики: 164 -> 160, 165 -> 170."""
    return int(Decimal(str(x / 10)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) * 10


def shelf_price(recommended: float, floor: float, own_price: float) -> float:
    """Рекомендованная цена до десятков, не ниже цены минимальной маржи.

    Округление не должно разворачивать рекомендацию: если мы дороже рынка,
    новая цена не выше текущей, если дешевле, не ниже текущей.
    """
    price = round_to_tens(recommended)
    while price < floor:
        price += 10
    if own_price > recommended:
        return min(price, own_price)
    return max(price, own_price)


# Колонки листов: (поле в витрине, заголовок, формат, итог в верхней строке)
SHEETS = {
    "Алерты": [
        ("sku_id", "SKU", "@", "count"), ("name", "Наименование", "@", None),
        ("category", "Категория", "@", None), ("n_sources", "Площадок", "0", None),
        ("purchase_price", "Закупка, руб", "#,##0.00", None),
        ("own_price", "Наша цена, руб", "#,##0.00", None), ("market_median", "Медиана рынка, руб", "#,##0.00", None),
        ("market_min", "Минимум рынка, руб", "#,##0.00", None), ("price_index", "Индекс", "0.0", "avg"),
        ("deviation", "Отклонение", "0.0%", "avg"), ("alert_type", "Тип", "@", None),
        ("recommended_price", "Рекомендованная цена, руб", "#,##0", None),
        ("margin_now", "Маржа сейчас", "0.0%", "avg"), ("margin_recommended", "Маржа при рекомендованной", "0.0%", "avg"),
        ("note", "Примечание", "@", None),
    ],
    "Индекс по SKU": [
        ("sku_id", "SKU", "@", "count"), ("name", "Наименование", "@", None), ("brand", "Бренд", "@", None),
        ("category", "Категория", "@", None), ("n_sources", "Площадок", "0", None),
        ("own_price", "Наша цена, руб", "#,##0.00", None), ("market_min", "Минимум рынка, руб", "#,##0.00", None),
        ("market_median", "Медиана рынка, руб", "#,##0.00", None), ("market_max", "Максимум рынка, руб", "#,##0.00", None),
        ("price_index", "Индекс", "0.0", "avg"), ("positioning", "Позиционирование", "@", None),
    ],
    "Категории": [
        ("category", "Категория", "@", "count"), ("n_sku", "SKU", "0", "sum"),
        ("median_index", "Медианный индекс", "0.0", "avg"), ("share_cheaper", "Дешевле рынка", "0.0%", "avg"),
        ("share_in_market", "В рынке", "0.0%", "avg"), ("share_expensive", "Дороже рынка", "0.0%", "avg"),
    ],
    "Загрузка": [
        ("source", "Источник", "@", "count"), ("n_raw", "Получено", "0", "sum"), ("n_duplicates", "Дублей", "0", "sum"),
        ("n_rejected", "Отклонено", "0", "sum"), ("n_valid", "Валидных", "0", "sum"),
        ("n_matched", "Сопоставлено", "0", "sum"), ("n_requests", "Запросов", "0", "sum"),
        ("n_retries", "Повторов", "0", "sum"), ("seconds", "Время, с", "0.00", "sum"),
    ],
}

QUERIES = {
    "Алерты": "SELECT * FROM mart.price_alerts WHERE snapshot_date = ? ORDER BY ABS(deviation) DESC",
    "Индекс по SKU": "SELECT * FROM mart.price_index WHERE snapshot_date = ? ORDER BY category, price_index DESC",
    "Категории": "SELECT * FROM mart.category_index WHERE snapshot_date = ? ORDER BY median_index DESC",
    "Загрузка": "SELECT * FROM core.load_log WHERE snapshot_date = ? ORDER BY source",
}


def _write_sheet(ws, df: pd.DataFrame, columns: list[tuple], total_label: str) -> None:
    n = len(df)
    first, last = 3, max(3, n + 2)
    for j, (field, title, fmt, agg) in enumerate(columns, start=1):
        col = get_column_letter(j)
        head = ws.cell(row=2, column=j, value=title)
        head.font = FONT_BOLD
        if j == 1:
            total = ws.cell(row=1, column=1, value=total_label)
        elif agg:
            total = ws.cell(row=1, column=j, value=f"=SUBTOTAL({SUBTOTAL_CODE[agg]},{col}{first}:{col}{last})")
            total.number_format = fmt
        else:
            total = ws.cell(row=1, column=j)
        total.font = FONT_BOLD
        for i, value in enumerate(df[field].tolist() if n else [], start=first):
            if pd.isna(value):
                value = None
            cell = ws.cell(row=i, column=j, value=value)
            cell.font = FONT
            cell.number_format = fmt
        width = max([len(title)] + [len(str(v)) for v in (df[field].head(200).tolist() if n else [])])
        ws.column_dimensions[col].width = min(max(8, width + 2), 48)
    ws.auto_filter.ref = f"A2:{get_column_letter(len(columns))}{last}"
    ws.freeze_panes = "A3"


def build_report(con: duckdb.DuckDBPyConnection, snapshot_date: date, reports_dir: str,
                 elapsed_etl: float | None = None) -> Path:
    wb = Workbook()
    wb.remove(wb.active)
    for sheet, columns in SHEETS.items():
        df = con.execute(QUERIES[sheet], [snapshot_date]).df()
        if sheet == "Алерты" and not df.empty:
            df["recommended_price"] = [shelf_price(r, f, o) for r, f, o in
                                       zip(df["recommended_price"], df["min_price_for_margin"], df["own_price"])]
            df["margin_recommended"] = 1 - df["purchase_price"] / df["recommended_price"]
        for field, _, fmt, _ in columns:
            if fmt != "@":  # числа из DECIMAL приводим к float, текст не трогаем
                df[field] = pd.to_numeric(df[field], errors="coerce").astype(float)
        label = "Итого"
        if sheet == "Загрузка" and elapsed_etl is not None:
            label = f"Итого (прогон {elapsed_etl:.1f} с)"
        _write_sheet(wb.create_sheet(sheet), df, columns, label)
    out = Path(reports_dir) / f"price_monitoring_{snapshot_date.isoformat()}.xlsx"
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    return out
