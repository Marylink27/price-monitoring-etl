-- Схема хранилища для PostgreSQL (боевой вариант).
-- Витрины из sql/marts/ написаны на общем подмножестве SQL и работают и здесь, и в DuckDB.

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

CREATE TABLE IF NOT EXISTS staging.offers (
    snapshot_date DATE NOT NULL,
    source        TEXT NOT NULL,
    offer_id      TEXT NOT NULL,
    raw_name      TEXT,
    brand         TEXT,
    price         NUMERIC(12, 2),
    old_price     NUMERIC(12, 2),
    volume_l      NUMERIC(8, 3),
    pack_qty      SMALLINT,
    in_stock      BOOLEAN,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_staging_offers_date ON staging.offers (snapshot_date, source);

CREATE TABLE IF NOT EXISTS staging.rejects (
    snapshot_date DATE NOT NULL,
    source        TEXT NOT NULL,
    offer_id      TEXT,
    raw_name      TEXT,
    reason        TEXT NOT NULL,
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS core.own_catalog (
    sku_id         TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    brand          TEXT NOT NULL,
    category       TEXT NOT NULL,
    volume_l       NUMERIC(8, 3) NOT NULL,
    purchase_price NUMERIC(12, 2) NOT NULL,
    own_price      NUMERIC(12, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS core.own_prices (
    snapshot_date  DATE NOT NULL,
    sku_id         TEXT NOT NULL REFERENCES core.own_catalog (sku_id),
    own_price      NUMERIC(12, 2) NOT NULL,
    purchase_price NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (snapshot_date, sku_id)
);

CREATE TABLE IF NOT EXISTS core.offer_matches (
    snapshot_date DATE NOT NULL,
    source        TEXT NOT NULL,
    offer_id      TEXT NOT NULL,
    sku_id        TEXT NOT NULL REFERENCES core.own_catalog (sku_id),
    pack_qty      SMALLINT NOT NULL,
    unit_price    NUMERIC(12, 2) NOT NULL,
    price_per_l   NUMERIC(12, 2) NOT NULL,
    in_stock      BOOLEAN NOT NULL,
    match_score   NUMERIC(4, 3) NOT NULL,
    match_method  TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, source, offer_id)
);
CREATE INDEX IF NOT EXISTS ix_offer_matches_sku ON core.offer_matches (sku_id, snapshot_date);

CREATE TABLE IF NOT EXISTS core.pricing_params (
    in_market_band  NUMERIC(5, 3) NOT NULL,
    alert_threshold NUMERIC(5, 3) NOT NULL,
    min_margin      NUMERIC(5, 3) NOT NULL
);

CREATE TABLE IF NOT EXISTS core.load_log (
    snapshot_date DATE NOT NULL,
    source        TEXT NOT NULL,
    n_raw         INTEGER,
    n_duplicates  INTEGER,
    n_rejected    INTEGER,
    n_valid       INTEGER,
    n_matched     INTEGER,
    n_requests    INTEGER,
    n_retries     INTEGER,
    seconds       NUMERIC(10, 3),
    loaded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE core.offer_matches IS 'Предложения конкурентов, сопоставленные с нашей матрицей SKU';
COMMENT ON TABLE core.load_log IS 'Журнал загрузок: объёмы, отбраковка, повторы запросов, время';
