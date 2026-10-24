"""Загрузка конфигурации и путей проекта."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config(path: str | Path | None = None) -> dict:
    """Читает config.yaml и превращает относительные пути в абсолютные от корня репозитория."""
    path = Path(path) if path else ROOT / "config.yaml"
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    cfg["paths"] = {k: str((ROOT / v).resolve()) if not Path(v).is_absolute() else v
                    for k, v in cfg["paths"].items()}
    return cfg
