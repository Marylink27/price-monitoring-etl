"""Клиент REST API площадки: пагинация, повторы с экспоненциальной паузой, ограничение частоты.

Транспорт вынесен отдельно: HttpTransport делает реальные запросы через requests,
MockTransport отдаёт ответы имитатора. Логика пагинации и повторов одна и та же.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Iterator, Protocol

import requests

log = logging.getLogger(__name__)


class TransientAPIError(Exception):
    """Временная ошибка площадки (429, 5xx, обрыв соединения): запрос стоит повторить."""


class Transport(Protocol):
    def get(self, url: str, params: dict) -> dict: ...


class HttpTransport:
    """Реальные HTTP-запросы с таймаутом и токеном из переменной окружения."""

    RETRY_STATUSES = {429, 500, 502, 503, 504}

    def __init__(self, timeout: float = 10, token_env: str | None = None):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "price-monitoring-etl/1.0"
        token = os.getenv(token_env) if token_env else None
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def get(self, url: str, params: dict) -> dict:
        try:
            resp = self.session.get(url, params=params, timeout=self.timeout)
        except (requests.ConnectionError, requests.Timeout) as exc:
            raise TransientAPIError(str(exc)) from exc
        if resp.status_code in self.RETRY_STATUSES:
            raise TransientAPIError(f"HTTP {resp.status_code}")
        resp.raise_for_status()
        return resp.json()


def _dig(obj: dict, path: str) -> Any:
    """Достаёт значение по пути вида 'data.products'."""
    for key in path.split("."):
        obj = obj.get(key, {}) if isinstance(obj, dict) else {}
    return obj


class MarketplaceClient:
    """Выгружает все предложения площадки постранично."""

    def __init__(self, name: str, cfg: dict, transport: Transport):
        self.name = name
        self.cfg = cfg
        self.transport = transport
        self.url = cfg["base_url"].rstrip("/") + cfg["endpoint"]
        self._last_call = 0.0
        self.stats = {"requests": 0, "retries": 0, "pages": 0}

    def _throttle(self) -> None:
        wait = self.cfg.get("min_interval", 0) - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _get(self, params: dict) -> dict:
        retries = self.cfg.get("max_retries", 3)
        for attempt in range(retries + 1):
            self._throttle()
            self.stats["requests"] += 1
            try:
                return self.transport.get(self.url, params)
            except TransientAPIError as exc:
                if attempt == retries:
                    raise
                pause = self.cfg.get("backoff", 1.0) * 2 ** attempt
                self.stats["retries"] += 1
                log.warning("%s: %s, повтор %d через %.2f с", self.name, exc, attempt + 1, pause)
                time.sleep(pause)
        raise RuntimeError("недостижимо")

    def iter_pages(self) -> Iterator[list[dict]]:
        mode, size = self.cfg["pagination"], self.cfg["page_size"]
        if mode == "page":
            page, pages = 1, 1
            while page <= pages:
                data = self._get({"page": page, "page_size": size})
                pages = int(data.get("pages", 1))
                yield _dig(data, self.cfg["items_path"]) or []
                page += 1
        elif mode == "cursor":
            cursor = None
            while True:
                params = {"limit": size} | ({"cursor": cursor} if cursor else {})
                data = self._get(params)
                yield _dig(data, self.cfg["items_path"]) or []
                cursor = _dig(data, "meta.next_cursor")
                if not cursor:
                    break
        elif mode == "offset":
            offset = 0
            while True:
                data = self._get({"offset": offset, "limit": size})
                items = _dig(data, self.cfg["items_path"]) or []
                yield items
                if len(items) < size:
                    break
                offset += size
        else:
            raise ValueError(f"Неизвестный тип пагинации: {mode}")

    def fetch_all(self) -> list[dict]:
        items: list[dict] = []
        for page in self.iter_pages():
            self.stats["pages"] += 1
            items.extend(page)
        log.info("%s: %d позиций, %d страниц, %d запросов, %d повторов",
                 self.name, len(items), self.stats["pages"], self.stats["requests"], self.stats["retries"])
        return items
