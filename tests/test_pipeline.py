from datetime import date

import pytest

from src.config import load_config
from src.extract.client import MarketplaceClient, TransientAPIError
from src.load import connect
from src.pipeline import run
from src.report import round_to_tens, shelf_price


class FlakyTransport:
    """Отдаёт 3 страницы по page-пагинации, первый запрос падает с временной ошибкой."""

    def __init__(self):
        self.calls = 0

    def get(self, url, params):
        self.calls += 1
        if self.calls == 1:
            raise TransientAPIError("HTTP 503")
        page = params["page"]
        return {"items": [{"id": f"{page}-{i}"} for i in range(2)], "pages": 3}


def test_client_paginates_and_retries():
    cfg = {"base_url": "https://x.example", "endpoint": "/o", "pagination": "page", "page_size": 2,
           "items_path": "items", "min_interval": 0, "backoff": 0, "max_retries": 2}
    client = MarketplaceClient("x", cfg, FlakyTransport())
    items = client.fetch_all()
    assert len(items) == 6
    assert client.stats["retries"] == 1


@pytest.fixture(scope="module")
def cfg(tmp_path_factory):
    c = load_config()
    c["paths"]["reports"] = str(tmp_path_factory.mktemp("reports"))
    return c


def _counts(db):
    con = connect(db, read_only=True)
    try:
        return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                for t in ["staging.offers", "core.offer_matches", "core.own_prices", "core.load_log"]}
    finally:
        con.close()


def test_load_is_idempotent(cfg, tmp_path):
    db = str(tmp_path / "test.duckdb")
    d = date(2026, 10, 20)
    run(d, cfg, mode="mock", make_report=False, db_path=db)
    first = _counts(db)
    run(d, cfg, mode="mock", make_report=False, db_path=db)
    assert _counts(db) == first
    run(date(2026, 10, 21), cfg, mode="mock", make_report=False, db_path=db)
    second = _counts(db)
    assert second["core.own_prices"] == 2 * first["core.own_prices"]


def test_marts_and_report(cfg, tmp_path):
    db = str(tmp_path / "test.duckdb")
    summary = run(date(2026, 10, 20), cfg, mode="mock", make_report=True, db_path=db)
    con = connect(db, read_only=True)
    try:
        idx = con.execute("SELECT * FROM mart.price_index").df()
        alerts = con.execute("SELECT * FROM mart.price_alerts").df()
    finally:
        con.close()
    assert len(idx) > 0 and idx["price_index"].between(50, 200).all()
    assert set(idx["positioning"]) <= {"дешевле рынка", "в рынке", "дороже рынка"}
    assert (alerts["deviation"].abs() > 0.10).all()
    assert summary["report"].endswith("price_monitoring_2026-10-20.xlsx")


@pytest.mark.parametrize("x, expected", [(164, 160), (165, 170), (169, 170), (151.2, 150)])
def test_round_to_tens(x, expected):
    assert round_to_tens(x) == expected


def test_shelf_price_keeps_min_margin_and_direction():
    # медиана 89, минимальная маржа требует 112.25: до десятков вверх -> 120
    assert shelf_price(112.25, 112.25, own_price=129) == 120
    # мы дороже рынка, но после округления цена выше текущей: оставляем текущую
    assert shelf_price(51.12, 51.12, own_price=59) == 59
    # мы дешевле рынка: поднимаем до медианы, округляя до десятков
    assert shelf_price(144.0, 100.0, own_price=119) == 140
    assert shelf_price(23.95, 15.0, own_price=21) == 21
