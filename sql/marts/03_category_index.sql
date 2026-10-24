-- Сводка по категориям: медианный индекс и доли SKU по позиционированию.
CREATE OR REPLACE VIEW mart.category_index AS
SELECT
    snapshot_date,
    category,
    COUNT(*)                                                                    AS n_sku,
    CAST(percentile_cont(0.5) WITHIN GROUP (ORDER BY price_index) AS NUMERIC(8, 1)) AS median_index,
    CAST(AVG(CASE WHEN positioning = 'дешевле рынка' THEN 1.0 ELSE 0 END) AS NUMERIC(5, 3)) AS share_cheaper,
    CAST(AVG(CASE WHEN positioning = 'в рынке' THEN 1.0 ELSE 0 END) AS NUMERIC(5, 3))       AS share_in_market,
    CAST(AVG(CASE WHEN positioning = 'дороже рынка' THEN 1.0 ELSE 0 END) AS NUMERIC(5, 3))  AS share_expensive
FROM mart.price_index
GROUP BY snapshot_date, category;
