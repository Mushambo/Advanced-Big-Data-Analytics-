-- 2.2  Data-quality diagnostics on energy_readings BEFORE cleaning.
SELECT count(*) AS emitted_rows FROM energy_readings;
SELECT count(*) AS unique_pairs FROM (SELECT 1 FROM energy_readings GROUP BY meter_id, event_time) t;

SELECT count(*) AS delayed_unique
FROM (SELECT meter_id, event_time, min(received_time) AS r
      FROM energy_readings GROUP BY meter_id, event_time) t
WHERE r > event_time + interval '15 minutes';

WITH u AS (
  SELECT meter_id, event_time, min(received_time) AS r, count(*) AS copies
  FROM energy_readings GROUP BY meter_id, event_time)
SELECT 10752000 AS planned, sum(copies) AS emitted, count(*) AS unique_pairs,
       sum(copies) - count(*) AS extra_copies, 10752000 - count(*) AS missing_pairs,
       count(*) FILTER (WHERE r > event_time + interval '15 minutes') AS delayed_unique,
       round(100.0 * (10752000 - count(*)) / 10752000, 4) AS missing_pct,
       round(100.0 * (sum(copies) - count(*)) / count(*), 4) AS duplicate_pct,
       round(100.0 * count(*) FILTER (WHERE r > event_time + interval '15 minutes') / count(*), 4) AS delayed_pct,
       round(100.0 * count(*) / 10752000, 4) AS completeness_pct
FROM u;

SELECT meter_id, 2688 - count(DISTINCT event_time) AS missing
FROM energy_readings GROUP BY meter_id ORDER BY missing DESC, meter_id LIMIT 5;
