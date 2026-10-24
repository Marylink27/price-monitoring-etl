"""Имитатор API трёх площадок для демо-режима.

Отдаёт ответы в тех же форматах, что ждёт клиент: три разные JSON-структуры,
три типа пагинации и характерный «грязный» контент: цены строками с пробелами
и "руб", цены в копейках, пропуски, дубли, объём в литрах и миллилитрах,
мультипаки, товары не из нашей матрицы. Всё детерминировано датой: повторный
запуск за тот же день даёт те же данные.
"""
from __future__ import annotations

import math
import zlib
from datetime import date
from urllib.parse import urlparse

import numpy as np
import pandas as pd

from .client import TransientAPIError

EPOCH = date(2026, 10, 1)

# Ассортимент демо-сети: бренд, категория, товары, объёмы (л), закупочная цена за литр (руб)
ASSORTMENT = [
    ("Гранд", "Газированные напитки", ["Кола классическая", "Кола без сахара", "Кола ваниль"], [0.33, 0.5, 1.0, 1.5], 62),
    ("Цитрус Лайн", "Газированные напитки", ["Лимонад Тархун", "Лимонад Дюшес", "Лимонад Груша"], [0.5, 1.5], 55),
    ("Лимонадная артель", "Газированные напитки", ["Лимонад Крем-сода", "Лимонад Барбарис", "Лимонад Колокольчик"], [0.5, 1.0], 70),
    ("Бриз", "Газированные напитки", ["Тоник классический", "Тоник грейпфрут"], [0.33, 1.0], 80),
    ("Горная вершина", "Вода", ["Вода негазированная", "Вода газированная"], [0.5, 1.5, 5.0], 22),
    ("Ледяной ключ", "Вода", ["Вода минеральная", "Вода детская"], [0.5, 1.5], 30),
    ("Солнечный сад", "Соки и нектары", ["Сок яблочный", "Сок апельсиновый", "Нектар вишневый", "Нектар персиковый"], [0.2, 1.0], 95),
    ("Фруктовый край", "Соки и нектары", ["Сок томатный", "Сок мультифрукт"], [1.0, 2.0], 85),
    ("Морс Север", "Соки и нектары", ["Морс клюквенный", "Морс брусничный"], [0.5, 1.0], 110),
    ("Чайная долина", "Холодный чай", ["Чай черный лимон", "Чай зеленый", "Чай персик", "Чай малина"], [0.5, 1.0], 60),
    ("Хлебный двор", "Квас", ["Квас хлебный", "Квас окрошечный"], [1.0, 1.5, 2.0], 45),
    ("Энерджи Макс", "Энергетики", ["Энергетик оригинальный", "Энергетик без сахара", "Энергетик манго"], [0.25, 0.45], 230),
    ("Бодрость", "Энергетики", ["Энергетик классический", "Энергетик ягодный"], [0.45], 200),
]

# Товары на площадках, которых нет в нашей матрице: должны остаться без сопоставления
FOREIGN = [
    ("Стар", "Кола классическая", 0.5), ("Стар", "Кола классическая", 1.5), ("Аква Чистая", "Вода негазированная", 0.5),
    ("Аква Чистая", "Вода негазированная", 1.5), ("Дачный", "Сок яблочный", 1.0), ("Дачный", "Сок томатный", 1.0),
    ("Гранд", "Кола лайм", 0.5), ("Цитрус Лайн", "Лимонад Лайм-мята", 0.5), ("Горная вершина", "Вода с лимоном", 0.5),
    ("Чайная долина", "Чай каркаде", 0.5), ("Энерджи Макс", "Энергетик кокос", 0.45), ("Квасной", "Квас хлебный", 1.5),
    ("Гранд", "Кола классическая", 2.0), ("Бодрость", "Энергетик классический", 0.25),
    # почти совпадающие названия: проверка матчинга на ложные срабатывания
    ("Гранд", "Кола классическая лайт", 0.5), ("Цитрус Лайн", "Лимонад Тархун Zero", 0.5),
    ("Солнечный сад", "Сок яблочный прямого отжима", 1.0),
]
LATIN_BRANDS = {"Гранд": "Grand", "Бриз": "Breeze", "Энерджи Макс": "Energy Max", "Бодрость": "Bodrost"}


def _typo(word: str, rng: np.random.Generator) -> str:
    """Опечатка: две соседние буквы меняются местами."""
    if len(word) < 5:
        return word
    i = int(rng.integers(1, len(word) - 2))
    return word[:i] + word[i + 1] + word[i] + word[i + 2:]

SOURCES = ("market_a", "market_b", "market_c")
COVERAGE = {"market_a": 0.88, "market_b": 0.78, "market_c": 0.72}
ABBREV_B = {"классическая": "класс.", "негазированная": "негаз.", "газированная": "газ.",
            "без сахара": "б/сахара", "оригинальный": "ориг.", "минеральная": "минер."}
NBSP = " "


def _rng(*parts) -> np.random.Generator:
    """Детерминированный генератор по набору ключей (источник, SKU, дата...)."""
    return np.random.default_rng(zlib.crc32("|".join(map(str, parts)).encode()))


def _vol_text(v: float, comma: bool = True) -> str:
    s = f"{v:g}"
    return s.replace(".", ",") if comma else s


def _to_shelf_price(p: float) -> int:
    """Цена «как на полке»: оканчивается на 9."""
    return max(9, int(p // 10) * 10 + 9)


def build_demo_catalog(seed: int = 42) -> pd.DataFrame:
    """Собственная матрица сети в формате выгрузки из 1С."""
    rng = np.random.default_rng(seed)
    rows = []
    for brand, category, products, volumes, per_l in ASSORTMENT:
        for product in products:
            for v in volumes:
                purchase = per_l * v ** 0.85 * rng.uniform(0.9, 1.15)
                own = _to_shelf_price(purchase * rng.uniform(1.38, 1.62))
                rows.append({
                    "name": f"{product} {brand} {_vol_text(v)} л",
                    "brand": brand, "category": category, "volume_l": v,
                    "purchase_price": round(purchase, 2), "own_price": float(own),
                })
    df = pd.DataFrame(rows)
    df.insert(0, "sku_id", [f"SKU-{i:04d}" for i in range(1, len(df) + 1)])
    return df


class MockMarketplaceAPI:
    """Генерирует снимок предложений трёх площадок на дату и отдаёт его постранично."""

    def __init__(self, catalog: pd.DataFrame, snapshot_date: date):
        self.catalog = catalog
        self.snapshot_date = snapshot_date
        self.day = (snapshot_date - EPOCH).days
        self.truth: dict[str, dict[str, str | None]] = {}
        self._offers = {s: self._build(s) for s in SOURCES}

    # ---------- генерация цены ----------
    def _market_price(self, source: str, sku: str, own_price: float) -> float:
        r = _rng("sku-factor", sku)
        u = r.random()
        if u < 0.12:          # у нас заметно дороже рынка
            factor = r.uniform(0.76, 0.86)
        elif u < 0.22:        # у нас заметно дешевле рынка
            factor = r.uniform(1.12, 1.25)
        else:
            factor = float(np.clip(r.normal(1.0, 0.035), 0.92, 1.08))
        rs = _rng("src-factor", source, sku)
        src_factor = rs.normal(1.0, 0.04)
        phase = rs.uniform(0, 11)
        trend = 1 + 0.025 * math.sin(2 * math.pi * (self.day + phase) / 11)
        rd = _rng("daily", source, sku, self.snapshot_date)
        price = own_price * factor * src_factor * trend * (1 + rd.normal(0, 0.012))
        if rd.random() < 0.06:  # промо на площадке
            price *= rd.uniform(0.72, 0.85)
        return price

    # ---------- представление позиции в формате площадки ----------
    def _item(self, source: str, offer_id: str, brand: str, product: str, v: float,
              price: float, rng: np.random.Generator, pack: int = 1) -> dict:
        p = _to_shelf_price(price)
        in_stock = bool(rng.random() > 0.05)
        if source == "market_a":
            fmt = rng.integers(0, 3)
            price_s = (f"{p:,}".replace(",", NBSP) + " руб") if fmt == 0 else (f"{p - 1},90 руб" if fmt == 1 else f"{p} руб")
            old = f"{_to_shelf_price(p * 1.2)} руб" if rng.random() < 0.3 else None
            prefix = "Напиток газированный " if rng.random() < 0.08 else ""  # лишние слова в карточке
            return {"id": offer_id, "title": f"{prefix}{brand} {product.lower()}, {_vol_text(v)} л",
                    "brand": brand, "price": price_s, "old_price": old, "available": in_stock}
        if source == "market_b":
            name = product.lower()
            for full, short in ABBREV_B.items():
                name = name.replace(full, short)
            if rng.random() < 0.06:  # опечатка в названии
                words = name.split()
                k = int(rng.integers(0, len(words)))
                words[k] = _typo(words[k], rng)
                name = " ".join(words)
            cur = None if rng.random() < 0.02 else int(round((p - rng.choice([0, 0.01, 0.1])) * 100))
            return {"sku": offer_id, "name": f"{brand.upper()} {name} {int(round(v * 1000))} мл",
                    "vendor": brand, "priceInfo": {"current": cur, "currency": "RUB"},
                    "stock": int(rng.integers(1, 60)) if in_stock else 0}
        # market_c
        tara = "ж/б" if v <= 0.5 and "Энергетик" in product else ("ПЭТ" if v >= 0.5 else "стекло")
        brand_field = brand if rng.random() > 0.25 else None
        if brand_field is None and brand in LATIN_BRANDS and rng.random() < 0.5:
            brand = LATIN_BRANDS[brand]  # бренд латиницей и без поля бренда
        if pack > 1:
            nm = f"{product} {brand} {pack}х{_vol_text(v)}л"
        else:
            nm = f"{product} {brand} {_vol_text(v, comma=False)}л {tara}"
        pv = p if rng.random() > 0.015 else ""
        price_v = pv if (pv == "" or rng.random() < 0.5) else f"{pv},0"
        return {"offer_id": offer_id, "nm": nm, "brand": brand_field,
                "price": price_v, "in_stock": int(in_stock)}

    def _build(self, source: str) -> list[dict]:
        truth: dict[str, str | None] = {}
        items: list[dict] = []
        prefix = {"market_a": "A", "market_b": "b_", "market_c": "C-"}[source]
        rng_day = _rng("items", source, self.snapshot_date)
        for row in self.catalog.itertuples():
            if _rng("coverage", source, row.sku_id).random() > COVERAGE[source]:
                continue
            product = row.name.split(f" {row.brand} ")[0]
            num = int(row.sku_id.split("-")[1])
            price = self._market_price(source, row.sku_id, row.own_price)
            oid = f"{prefix}{num * 7 + 1000}"
            items.append(self._item(source, oid, row.brand, product, row.volume_l, price, rng_day))
            truth[oid] = row.sku_id
            if source == "market_a" and _rng("2nd-seller", row.sku_id).random() < 0.15:
                oid2 = f"{prefix}{num * 7 + 5000}"
                items.append(self._item(source, oid2, row.brand, product, row.volume_l, price * 1.05, rng_day))
                truth[oid2] = row.sku_id
            if source == "market_c" and row.volume_l <= 0.5 and _rng("multipack", row.sku_id).random() < 0.3:
                oid3 = f"{prefix}{num * 7 + 9000}"
                items.append(self._item(source, oid3, row.brand, product, row.volume_l,
                                        price * 6 * 0.92, rng_day, pack=6))
                truth[oid3] = row.sku_id
        for i, (brand, product, v) in enumerate(FOREIGN):
            if _rng("foreign", source, i).random() > 0.8:
                continue
            base = 40 + 60 * v
            oid = f"{prefix}{90000 + i}"
            items.append(self._item(source, oid, brand, product, v, base * rng_day.uniform(0.9, 1.1), rng_day))
            truth[oid] = None
        order = rng_day.permutation(len(items))
        items = [items[i] for i in order]
        if source == "market_c":  # дубли: часть позиций повторяется на соседних страницах
            dup_idx = rng_day.choice(len(items), size=4, replace=False)
            for j, k in enumerate(sorted(dup_idx)):
                items.insert(min(len(items), k + 35 + j), dict(items[k]))
        self.truth[source] = truth
        return items

    # ---------- ответы API ----------
    def respond(self, source: str, params: dict) -> dict:
        items = self._offers[source]
        if source == "market_a":
            size, page = int(params["page_size"]), int(params["page"])
            pages = max(1, math.ceil(len(items) / size))
            chunk = items[(page - 1) * size: page * size]
            return {"items": chunk, "page": page, "pages": pages, "total": len(items)}
        if source == "market_b":
            size = int(params["limit"])
            offset = int(str(params.get("cursor", "c0"))[1:])
            chunk = items[offset: offset + size]
            nxt = f"c{offset + size}" if offset + size < len(items) else None
            return {"data": {"products": chunk}, "meta": {"next_cursor": nxt}}
        size, offset = int(params["limit"]), int(params["offset"])
        return {"offers": items[offset: offset + size], "count": len(items)}


class MockTransport:
    """Транспорт для демо-режима: вместо HTTP отвечает имитатор, иногда с ошибкой 503."""

    def __init__(self, api: MockMarketplaceAPI, sources_cfg: dict, fail_rate: float = 0.0, seed: int = 7):
        self.api = api
        self.hosts = {urlparse(c["base_url"]).netloc: name for name, c in sources_cfg.items()}
        self.fail_rate = fail_rate
        self.rng = np.random.default_rng(seed)

    def get(self, url: str, params: dict) -> dict:
        if self.rng.random() < self.fail_rate:
            raise TransientAPIError("HTTP 503 (имитация)")
        return self.api.respond(self.hosts[urlparse(url).netloc], params)
