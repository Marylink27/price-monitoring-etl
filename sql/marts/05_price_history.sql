-- История цен: наша цена и рынок по дням, для графиков динамики.
CREATE OR REPLACE VIEW mart.price_history AS
SELECT
    i.snapshot_date,
    i.sku_id,
    i.name,
    i.category,
    i.own_price,
    i.market_min,
    i.market_median,
    i.price_index
FROM mart.price_index i;
