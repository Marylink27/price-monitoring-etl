import pytest

from src.transform.parsing import normalize_name, parse_price, parse_volume


@pytest.mark.parametrize("raw, unit, expected", [
    ("89 руб", "rub", 89.0),
    ("1 299 руб", "rub", 1299.0),
    ("89,90 руб", "rub", 89.9),
    ("  149,00 руб.", "rub", 149.0),
    (8900, "kopecks", 89.0),
    (89.0, "rub", 89.0),
    ("89,0", "rub", 89.0),
    ("", "rub", None),
    (None, "rub", None),
    ("по запросу", "rub", None),
])
def test_parse_price(raw, unit, expected):
    assert parse_price(raw, unit=unit) == expected


@pytest.mark.parametrize("text, expected", [
    ("Гранд кола классическая, 0,5 л", (0.5, 1)),
    ("ГРАНД кола класс. 500 мл", (0.5, 1)),
    ("Кола классическая Гранд 1.5л ПЭТ", (1.5, 1)),
    ("Энергетик манго 6х0,45л", (0.45, 6)),
    ("Тоник 4 x 330 мл", (0.33, 4)),
    ("Вода 5 л", (5.0, 1)),
    ("Лимонад без объёма", (None, 1)),
])
def test_parse_volume(text, expected):
    assert parse_volume(text) == expected


def test_volume_unit_not_part_of_word():
    # "л" в начале слова "лимонад" не должна читаться как литры
    assert parse_volume("Лимонад 2 лимона") == (None, 1)


def test_normalize_name_expands_abbreviations_and_drops_noise():
    assert normalize_name("ГРАНД Кола класс. 500 мл ПЭТ") == "гранд кола классическая"
    assert normalize_name("Напиток газированный Гранд кола ваниль, 1,5 л") == "гранд кола ваниль"
    assert normalize_name("Морс клюквенный 6х0,5л") == "морс клюквенный"
