"""Load: запись в хранилище и витрины."""
from .db import build_marts, connect, init_schema, load_snapshot

__all__ = ["build_marts", "connect", "init_schema", "load_snapshot"]
