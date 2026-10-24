-- Схема хранилища для локального запуска (DuckDB).
-- Структура совпадает с sql/schema_postgres.sql, отличаются только типы и служебные поля.

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS mart;

-- Предложения площадок после разбора, до матчинга
CREATE TABLE IF NOT EXISTS staging.offers (
    snapshot_date DATE NOT NULL,
    source        VARCHAR NOT NULL,
    offer_id      VARCHAR NOT NULL,
    raw_name      VARCHAR,
    brand         VARCHAR,
    price         DOUBLE,
    old_price     DOUBLE,
    volume_l      DOUBLE,
    pack_qty      INTEGER,
    in_stock      BOOLEAN,
    loaded_at     TIMESTAMP DEFAULT current_timestamp
);

-- Отклонённые позиции с причиной
CREATE TABLE IF NOT EXISTS staging.rejects (
    snapshot_date DATE NOT NULL,
    source        VARCHAR NOT NULL,
    offer_id      VARCHAR,
    raw_name      VARCHAR,
    reason        VARCHAR NOT NULL,
    loaded_at     TIMESTAMP DEFAULT current_timestamp
);

-- Собственная матрица (выгрузка из 1С), перезаписывается при каждой загрузке
CREATE TABLE IF NOT EXISTS core.own_catalog (
    sku_id         VARCHAR PRIMARY KEY,
    name           VARCHAR NOT NULL,
    brand          VARCHAR NOT NULL,
    category       VARCHAR NOT NULL,
    volume_l       DOUBLE NOT NULL,
    purchase_price DOUBLE NOT NULL,
    own_price      DOUBLE NOT NULL
);

-- Наши цены на дату снимка
CREATE TABLE IF NOT EXISTS core.own_prices (
    snapshot_date  DATE NOT NULL,
    sku_id         VARCHAR NOT NULL,
    own_price      DOUBLE NOT NULL,
    purchase_price DOUBLE NOT NULL,
    PRIMARY KEY (snapshot_date, sku_id)
);

-- Сопоставленные предложения конкурентов
CREATE TABLE IF NOT EXISTS core.offer_matches (
    snapshot_date DATE NOT NULL,
    source        VARCHAR NOT NULL,
    offer_id      VARCHAR NOT NULL,
    sku_id        VARCHAR NOT NULL,
    pack_qty      INTEGER NOT NULL,
    unit_price    DOUBLE NOT NULL,
    price_per_l   DOUBLE NOT NULL,
    in_stock      BOOLEAN NOT NULL,
    match_score   DOUBLE NOT NULL,
    match_method  VARCHAR NOT NULL,
    PRIMARY KEY (snapshot_date, source, offer_id)
);

-- Параметры ценовой политики (из config.yaml), одна строка
CREATE TABLE IF NOT EXISTS core.pricing_params (
    in_market_band  DOUBLE NOT NULL,
    alert_threshold DOUBLE NOT NULL,
    min_margin      DOUBLE NOT NULL
);

-- Журнал загрузок: объёмы и время выполнения
CREATE TABLE IF NOT EXISTS core.load_log (
    snapshot_date DATE NOT NULL,
    source        VARCHAR NOT NULL,
    n_raw         INTEGER,
    n_duplicates  INTEGER,
    n_rejected    INTEGER,
    n_valid       INTEGER,
    n_matched     INTEGER,
    n_requests    INTEGER,
    n_retries     INTEGER,
    seconds       DOUBLE,
    loaded_at     TIMESTAMP DEFAULT current_timestamp
);
