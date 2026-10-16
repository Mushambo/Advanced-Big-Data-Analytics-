-- 6.2  Definitions for the freshness / delayed-arrival test (separate test objects).
-- freshness_test.py drives the inserts, refreshes and comparisons.
DROP MATERIALIZED VIEW IF EXISTS fresh_test_hourly;
DROP TABLE IF EXISTS fresh_test;

CREATE TABLE fresh_test (
  event_time TIMESTAMPTZ NOT NULL,
  energy_kwh DOUBLE PRECISION
);
SELECT create_hypertable('fresh_test', 'event_time', chunk_time_interval => INTERVAL '1 day');

CREATE MATERIALIZED VIEW fresh_test_hourly
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket('1 hour', event_time, 'Africa/Kigali') AS bucket,
       sum(energy_kwh) AS sum_energy_kwh,
       count(*)        AS reading_count
FROM fresh_test
GROUP BY 1
WITH NO DATA;
-- no refresh policy is added: automatic refresh stays off during the test
