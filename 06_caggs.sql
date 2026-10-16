-- 6.1  Three continuous aggregates over energy_readings, created WITHOUT data and with
-- real-time aggregation disabled (materialized_only = TRUE).  The two regional views use an
-- inner join with meters on meter_id.
-- Buckets: 15 minutes, CAT hour and CAT day (time zone argument Africa/Kigali).

CREATE MATERIALIZED VIEW cagg_15min_region
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket('15 minutes', r.event_time)  AS bucket,
       m.region                                 AS region,
       sum(r.energy_kwh)                        AS sum_energy_kwh,
       sum(r.power_kw)                          AS sum_power_kw,
       count(*)                                 AS reading_count
FROM energy_readings r
JOIN meters m ON m.meter_id = r.meter_id
GROUP BY 1, 2
WITH NO DATA;

CREATE MATERIALIZED VIEW cagg_hour_region
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket('1 hour', r.event_time, 'Africa/Kigali') AS bucket,
       m.region                                 AS region,
       sum(r.energy_kwh)                        AS sum_energy_kwh,
       sum(r.power_kw)                          AS sum_power_kw,
       count(*)                                 AS reading_count
FROM energy_readings r
JOIN meters m ON m.meter_id = r.meter_id
GROUP BY 1, 2
WITH NO DATA;

CREATE MATERIALIZED VIEW cagg_day_meter
WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
SELECT time_bucket('1 day', event_time, 'Africa/Kigali') AS bucket,
       meter_id                                 AS meter_id,
       sum(energy_kwh)                          AS sum_energy_kwh,
       sum(power_kw)                            AS sum_power_kw,
       count(*)                                 AS reading_count
FROM energy_readings
GROUP BY 1, 2
WITH NO DATA;

-- make sure real-time aggregation is off on all three (explicit, in case of defaults)
ALTER MATERIALIZED VIEW cagg_15min_region SET (timescaledb.materialized_only = true);
ALTER MATERIALIZED VIEW cagg_hour_region  SET (timescaledb.materialized_only = true);
ALTER MATERIALIZED VIEW cagg_day_meter    SET (timescaledb.materialized_only = true);
