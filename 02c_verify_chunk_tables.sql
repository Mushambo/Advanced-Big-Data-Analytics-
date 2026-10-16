-- 3.1.3 / 3.1.4  Data checks, chunk intervals, chunk counts, date ranges and indexes.
SELECT 'energy_readings' AS tbl, count(*) AS rows, count(DISTINCT meter_id) AS meters,
       min(event_time) AS first_event, max(event_time) AS last_event,
       sum(power_kw) AS sum_power, sum(energy_kwh) AS sum_energy FROM energy_readings
UNION ALL SELECT 'energy_readings_3h', count(*), count(DISTINCT meter_id), min(event_time), max(event_time),
       sum(power_kw), sum(energy_kwh) FROM energy_readings_3h
UNION ALL SELECT 'energy_readings_week', count(*), count(DISTINCT meter_id), min(event_time), max(event_time),
       sum(power_kw), sum(energy_kwh) FROM energy_readings_week;

WITH s AS (
  SELECT 'energy_readings' AS tbl, sum(power_kw) p, sum(energy_kwh) e FROM energy_readings
  UNION ALL SELECT 'energy_readings_3h',   sum(power_kw), sum(energy_kwh) FROM energy_readings_3h
  UNION ALL SELECT 'energy_readings_week', sum(power_kw), sum(energy_kwh) FROM energy_readings_week)
SELECT tbl,
       abs(p - max(p) FILTER (WHERE tbl = 'energy_readings') OVER ()) AS power_diff,
       abs(e - max(e) FILTER (WHERE tbl = 'energy_readings') OVER ()) AS energy_diff,
       (abs(p - max(p) FILTER (WHERE tbl = 'energy_readings') OVER ()) <= 0.001
        AND abs(e - max(e) FILTER (WHERE tbl = 'energy_readings') OVER ()) <= 0.001) AS within_tolerance
FROM s ORDER BY tbl;

SELECT hypertable_name, column_name, time_interval
FROM timescaledb_information.dimensions
WHERE hypertable_name LIKE 'energy_readings%' ORDER BY 1;

SELECT hypertable_name, count(*) AS chunks,
       min(range_start) AS first_range_start, max(range_end) AS last_range_end
FROM timescaledb_information.chunks
WHERE hypertable_name LIKE 'energy_readings%'
GROUP BY 1 ORDER BY 1;

SELECT tablename, indexname, indexdef FROM pg_indexes
WHERE tablename LIKE 'energy_readings%' ORDER BY 1, 2;
