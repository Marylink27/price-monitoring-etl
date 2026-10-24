-- Ценовой индекс SKU: наша цена к медиане рынка, 100 = в рынке.
-- Позиционирование по коридору in_market_band из core.pricing_params.
CREATE OR REPLACE VIEW mart.price_index AS
SELECT
    p.snapshot_date,
    p.sku_id,
    c.name,
    c.brand,
    c.category,
    p.own_price,
    p.purchase_price,
    m.n_sources,
    m.market_min,
    m.market_median,
    m.market_max,
    CAST(100.0 * p.own_price / m.market_median AS NUMERIC(8, 1)) AS price_index,
    CASE
        WHEN p.own_price < m.market_median * (1 - prm.in_market_band) THEN 'дешевле рынка'
        WHEN p.own_price > m.market_median * (1 + prm.in_market_band) THEN 'дороже рынка'
        ELSE 'в рынке'
    END AS positioning
FROM core.own_prices p
JOIN core.own_catalog c ON c.sku_id = p.sku_id
JOIN mart.market_prices m ON m.snapshot_date = p.snapshot_date AND m.sku_id = p.sku_id
CROSS JOIN core.pricing_params prm;
