-- Рыночная цена SKU на дату.
-- Берём лучшее (минимальное) предложение каждой площадки, только штучные позиции в наличии:
-- мультипаки дешевле за штуку и исказили бы сравнение с полочной ценой.
CREATE OR REPLACE VIEW mart.market_prices AS
WITH best_offer AS (
    SELECT snapshot_date, sku_id, source, MIN(unit_price) AS price
    FROM core.offer_matches
    WHERE in_stock AND pack_qty = 1
    GROUP BY snapshot_date, sku_id, source
)
SELECT
    snapshot_date,
    sku_id,
    COUNT(*)                                            AS n_sources,
    MIN(price)                                          AS market_min,
    percentile_cont(0.5) WITHIN GROUP (ORDER BY price)  AS market_median,
    MAX(price)                                          AS market_max
FROM best_offer
GROUP BY snapshot_date, sku_id;
