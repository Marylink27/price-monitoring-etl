"""Создаёт демо-матрицу data/own_catalog.csv (аналог выгрузки номенклатуры и цен из 1С).

Запуск: python scripts/make_catalog.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.extract.mock import build_demo_catalog  # noqa: E402

if __name__ == "__main__":
    out = ROOT / "data" / "own_catalog.csv"
    catalog = build_demo_catalog()
    catalog.to_csv(out, index=False, encoding="utf-8")
    print(f"{len(catalog)} SKU -> {out}")
