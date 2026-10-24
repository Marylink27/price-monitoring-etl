import pandas as pd
import pytest

from src.transform.matching import SkuMatcher

CATALOG = pd.DataFrame([
    {"sku_id": "S1", "name": "Кола классическая Гранд 0,5 л", "brand": "Гранд", "volume_l": 0.5},
    {"sku_id": "S2", "name": "Кола без сахара Гранд 0,5 л", "brand": "Гранд", "volume_l": 0.5},
    {"sku_id": "S3", "name": "Кола классическая Гранд 1,5 л", "brand": "Гранд", "volume_l": 1.5},
    {"sku_id": "S4", "name": "Лимонад Тархун Цитрус Лайн 0,5 л", "brand": "Цитрус Лайн", "volume_l": 0.5},
    {"sku_id": "S5", "name": "Вода негазированная Горная вершина 0,5 л", "brand": "Горная вершина", "volume_l": 0.5},
    {"sku_id": "S6", "name": "Вода газированная Горная вершина 0,5 л", "brand": "Горная вершина", "volume_l": 0.5},
])


@pytest.fixture(scope="module")
def matcher():
    return SkuMatcher(CATALOG, threshold=0.82, threshold_no_brand=0.90, brand_aliases={"Grand": "Гранд"})


@pytest.mark.parametrize("name, brand, vol, expected", [
    ("Гранд кола классическая, 0,5 л", "Гранд", 0.5, "S1"),
    ("ГРАНД кола класс. 500 мл", "Гранд", 0.5, "S1"),
    ("ГРАНД кола б/сахара 500 мл", "Гранд", 0.5, "S2"),
    ("Кола классическая Гранд 1.5л ПЭТ", None, 1.5, "S3"),          # бренд найден в названии
    ("Кола классическая Grand 0.5л ПЭТ", None, 0.5, "S1"),          # бренд латиницей
    ("Вода газированная Горная вершина 0,5 л", None, 0.5, "S6"),    # газ. и негаз. не путаются
    ("Вода негазированная Горная вершина 0,5 л", None, 0.5, "S5"),
])
def test_matches_expected_sku(matcher, name, brand, vol, expected):
    sku, score, _ = matcher.match_one(name, brand, vol)
    assert sku == expected and score >= 0.82


@pytest.mark.parametrize("name, brand, vol, reason", [
    ("Стар кола классическая, 0,5 л", "Стар", 0.5, "бренд вне матрицы"),
    ("Гранд кола классическая, 2 л", "Гранд", 2.0, "нет кандидатов"),
    ("Гранд кола лайм, 0,5 л", "Гранд", 0.5, "ниже порога"),
    ("Лимонад Тархун Zero Цитрус Лайн 0,5 л", "Цитрус Лайн", 0.5, "ниже порога"),
    ("Кола классическая Стар 0.5л", None, 0.5, "ниже порога"),
])
def test_rejects_foreign_and_variants(matcher, name, brand, vol, reason):
    sku, _, method = matcher.match_one(name, brand, vol)
    assert sku is None and method == reason


def test_match_dataframe_adds_columns(matcher):
    offers = pd.DataFrame({"raw_name": ["Гранд кола классическая, 0,5 л"], "brand": ["Гранд"], "volume_l": [0.5]})
    out = matcher.match(offers)
    assert list(out[["sku_id", "match_method"]].iloc[0]) == ["S1", "бренд из поля"]
