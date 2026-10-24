"""Сопоставление предложений конкурентов с нашей матрицей SKU.

Правила:
1. Бренд берётся из поля площадки, а если его нет, ищется в названии по словарю наших брендов.
   Латинские написания приводятся к нашим через словарь синонимов (config.yaml).
2. Бренд известен, но его нет в нашей матрице: предложение не сопоставляется.
3. Кандидаты: SKU того же бренда (или все SKU, если бренд не найден) с тем же объёмом.
4. Сходство названий без бренда и объёма: rapidfuzz token_sort_ratio, итог 0..1.
5. Маркер варианта (zero, лайт...), которого нет у кандидата, снижает сходство:
   «Тархун Zero» не должен склеиться с обычным «Тархуном».
6. Принимаем лучшего кандидата, если сходство не ниже порога (без бренда порог строже).
"""
from __future__ import annotations

import pandas as pd
from rapidfuzz import fuzz

from .parsing import normalize_name

VOLUME_TOL = 0.005
VARIANT_MARKERS = {"zero", "лайт", "light", "диет", "диетическая", "прямого", "отжима", "детская"}
VARIANT_PENALTY = 0.8


class SkuMatcher:
    def __init__(self, catalog: pd.DataFrame, threshold: float = 0.82, threshold_no_brand: float = 0.90,
                 brand_aliases: dict[str, str] | None = None, variant_penalty: float = VARIANT_PENALTY):
        self.threshold = threshold
        self.variant_penalty = variant_penalty
        self.threshold_no_brand = threshold_no_brand
        self.aliases = {normalize_name(k): normalize_name(v) for k, v in (brand_aliases or {}).items()}
        cat = catalog.copy()
        cat["brand_norm"] = cat["brand"].map(normalize_name)
        cat["product_norm"] = [self._strip_brand(normalize_name(n), b) for n, b in zip(cat["name"], cat["brand_norm"])]
        self.catalog = cat
        # длинные бренды проверяем первыми, чтобы "лимонадная артель" не путалась с короткими
        self.brands = sorted(cat["brand_norm"].unique(), key=len, reverse=True)

    @staticmethod
    def _strip_brand(name_norm: str, brand_norm: str) -> str:
        if not brand_norm:
            return name_norm
        return " ".join(name_norm.replace(brand_norm, " ").split())

    def _apply_aliases(self, name_norm: str) -> str:
        padded = f" {name_norm} "
        for alias, canonical in self.aliases.items():
            padded = padded.replace(f" {alias} ", f" {canonical} ")
        return padded.strip()

    def _detect_brand(self, name_norm: str) -> str | None:
        padded = f" {name_norm} "
        return next((b for b in self.brands if f" {b} " in padded), None)

    def match_one(self, raw_name: str, brand: str | None, volume_l: float | None) -> tuple[str | None, float, str]:
        """Возвращает (sku_id или None, уверенность, способ сопоставления)."""
        if volume_l is None:
            return None, 0.0, "нет объёма"
        name_norm = self._apply_aliases(normalize_name(raw_name))
        brand_norm = normalize_name(brand) if brand else None
        brand_norm = self.aliases.get(brand_norm, brand_norm)
        if brand_norm and brand_norm not in self.brands:
            return None, 0.0, "бренд вне матрицы"
        method = "бренд из поля"
        if not brand_norm:
            brand_norm = self._detect_brand(name_norm)
            method = "бренд из названия" if brand_norm else "без бренда"
        cand = self.catalog[(self.catalog["volume_l"] - volume_l).abs() < VOLUME_TOL]
        if brand_norm:
            cand = cand[cand["brand_norm"] == brand_norm]
        if cand.empty:
            return None, 0.0, "нет кандидатов"
        product = self._strip_brand(name_norm, brand_norm) if brand_norm else name_norm
        target = cand["product_norm"] if brand_norm else (cand["product_norm"] + " " + cand["brand_norm"])
        markers = set(product.split()) & VARIANT_MARKERS
        scores = []
        for t in target:
            s = fuzz.token_sort_ratio(product, t) / 100
            if markers - set(t.split()):
                s *= self.variant_penalty
            scores.append(s)
        best = max(range(len(scores)), key=scores.__getitem__)
        score = round(scores[best], 3)
        threshold = self.threshold if brand_norm else self.threshold_no_brand
        if score < threshold:
            return None, score, "ниже порога"
        return cand.iloc[best]["sku_id"], score, method

    def match(self, offers: pd.DataFrame) -> pd.DataFrame:
        res = [self.match_one(n, b if isinstance(b, str) else None, v if pd.notna(v) else None)
               for n, b, v in zip(offers["raw_name"], offers["brand"], offers["volume_l"])]
        out = offers.copy()
        out["sku_id"] = [r[0] for r in res]
        out["match_score"] = [r[1] for r in res]
        out["match_method"] = [r[2] for r in res]
        return out
