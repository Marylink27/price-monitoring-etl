-- Алерты: наша цена отклоняется от медианы рынка больше порога alert_threshold.
-- Рекомендованная цена: медиана рынка, но не ниже цены, дающей минимальную маржу min_margin.
CREATE OR REPLACE VIEW mart.price_alerts AS
SELECT
    i.snapshot_date,
    i.sku_id,
    i.name,
    i.category,
    i.n_sources,
    i.purchase_price,
    i.own_price,
    i.market_median,
    i.market_min,
    i.price_index,
    CAST(i.own_price / i.market_median - 1 AS NUMERIC(6, 3)) AS deviation,
    CASE WHEN i.own_price > i.market_median THEN 'дороже рынка' ELSE 'дешевле рынка' END AS alert_type,
    i.purchase_price / (1 - prm.min_margin) AS min_price_for_margin,
    GREATEST(i.market_median, i.purchase_price / (1 - prm.min_margin)) AS recommended_price,
    CAST(1 - i.purchase_price / i.own_price AS NUMERIC(5, 3)) AS margin_now,
    CAST(1 - i.purchase_price / GREATEST(i.market_median, i.purchase_price / (1 - prm.min_margin)) AS NUMERIC(5, 3)) AS margin_recommended,
    CASE WHEN i.purchase_price / (1 - prm.min_margin) > i.market_median
         THEN 'ограничено минимальной маржой' ELSE '' END AS note
FROM mart.price_index i
CROSS JOIN core.pricing_params prm
WHERE ABS(i.own_price / i.market_median - 1) > prm.alert_threshold;
