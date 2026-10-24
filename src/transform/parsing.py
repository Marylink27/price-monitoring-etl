"""Разбор «грязных» полей: цена, объём, упаковка, название."""
from __future__ import annotations

import re

_NUM = r"\d+(?:[.,]\d+)?"
_UNIT = r"(мл|ml|л|l)(?![a-zа-яё])"
MULTIPACK_RE = re.compile(rf"(\d+)\s*[xх×*]\s*({_NUM})\s*{_UNIT}", re.IGNORECASE)
VOLUME_RE = re.compile(rf"({_NUM})\s*{_UNIT}", re.IGNORECASE)
CURRENCY_RE = re.compile(r"(руб\.?|р\.|rub|\u20bd)", re.IGNORECASE)

# Сокращения, которые встречаются в названиях на площадках
ABBREVIATIONS = {
    "класс.": "классическая", "негаз.": "негазированная", "газ.": "газированная",
    "б/сахара": "без сахара", "б/с": "без сахара", "ориг.": "оригинальный", "минер.": "минеральная",
}
# Слова, которые не помогают отличить товар: тара, общие слова
STOPWORDS = {"напиток", "газированный", "безалкогольный", "пэт", "ж/б", "стекло", "тетрапак",
             "бут", "бутылка", "банка", "уп", "шт"}


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))


def parse_price(value, unit: str = "rub") -> float | None:
    """Цена из строки или числа. unit='kopecks' для площадок, отдающих цену в копейках.

    >>> parse_price("1 299 руб")
    1299.0
    >>> parse_price("89,90 руб")
    89.9
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, (int, float)):
        price = float(value)
    else:
        s = CURRENCY_RE.sub("", str(value))
        s = s.replace(" ", "").replace(" ", "").strip()
        if not re.fullmatch(_NUM, s):
            return None
        price = _to_float(s)
    if unit == "kopecks":
        price /= 100
    return round(price, 2)


def parse_volume(text: str) -> tuple[float | None, int]:
    """Объём одной единицы в литрах и количество в упаковке.

    >>> parse_volume("Кола 6х0,5л")
    (0.5, 6)
    >>> parse_volume("КОЛА 500 мл")
    (0.5, 1)
    """
    if not text:
        return None, 1
    m = MULTIPACK_RE.search(text)
    if m:
        qty, num, unit = int(m.group(1)), _to_float(m.group(2)), m.group(3).lower()
    else:
        m = VOLUME_RE.search(text)
        if not m:
            return None, 1
        qty, num, unit = 1, _to_float(m.group(1)), m.group(2).lower()
    liters = num / 1000 if unit in ("мл", "ml") else num
    return round(liters, 3), qty


def normalize_name(text: str) -> str:
    """Название к сравнимому виду: регистр, ё, сокращения, без объёма, тары и пунктуации."""
    s = (text or "").lower().replace("ё", "е")
    for short, full in ABBREVIATIONS.items():
        s = s.replace(short, full)
    s = MULTIPACK_RE.sub(" ", s)
    s = VOLUME_RE.sub(" ", s)
    tokens = re.sub(r"[^\w/\-]+", " ", s).split()
    return " ".join(t for t in tokens if t not in STOPWORDS and not t.isdigit())
