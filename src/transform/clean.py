"""Проверки качества и дедупликация предложений."""
from __future__ import annotations

import pandas as pd


def validate(df: pd.DataFrame, min_price: float, max_price: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Делит предложения на валидные и отклонённые с указанием причины."""
    reason = pd.Series(pd.NA, index=df.index, dtype="object")
    reason[df["offer_id"].isna()] = "нет идентификатора"
    reason[reason.isna() & df["raw_name"].fillna("").str.strip().eq("")] = "нет названия"
    reason[reason.isna() & df["price"].isna()] = "нет цены"
    reason[reason.isna() & ~df["price"].between(min_price, max_price)] = "цена вне допустимого диапазона"
    reason[reason.isna() & df["volume_l"].isna()] = "не удалось определить объём"
    bad = reason.notna()
    rejects = df.loc[bad, ["source", "offer_id", "raw_name"]].assign(reason=reason[bad])
    return df.loc[~bad].copy(), rejects


def deduplicate(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Убирает повторы одного предложения (тот же источник и offer_id), оставляя первое."""
    before = len(df)
    df = df.drop_duplicates(subset=["source", "offer_id"], keep="first")
    return df, before - len(df)


def add_unit_prices(df: pd.DataFrame) -> pd.DataFrame:
    """Цена за единицу (для мультипака делится на число штук) и цена за литр."""
    df = df.copy()
    df["unit_price"] = (df["price"] / df["pack_qty"]).round(2)
    df["price_per_l"] = (df["unit_price"] / df["volume_l"]).round(2)
    return df
