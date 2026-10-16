-- Section 5  SQL used by analysis_section5.py (cleaned energy_readings + meters).
-- All day/hour buckets are CAT (Africa/Kigali).

-- 5.1  total network energy per CAT day
SELECT time_bucket('1 day', event_time, 'Africa/Kigali')::date AS day, sum(energy_kwh) AS energy_kwh
FROM energy_readings GROUP BY 1 ORDER BY 1;

-- 5.1  seven-day periods beginning 1, 8, 15 and 22 September
SELECT DATE '2026-09-01' + 7 * ((time_bucket('1 day', event_time, 'Africa/Kigali')::date - DATE '2026-09-01') / 7) AS period_start,
       sum(energy_kwh) AS energy_kwh
FROM energy_readings GROUP BY 1 ORDER BY 1;

-- 5.1  three highest 15-minute network demand intervals
SELECT event_time, sum(power_kw) AS network_kw
FROM energy_readings GROUP BY event_time ORDER BY network_kw DESC, event_time LIMIT 3;

-- 5.2  by region and by customer type (energy per registered meter)
SELECT m.region, count(DISTINCT m.meter_id) AS meters, sum(r.energy_kwh) AS energy_kwh,
       sum(r.energy_kwh) / count(DISTINCT m.meter_id) AS kwh_per_meter
FROM energy_readings r JOIN meters m USING (meter_id) GROUP BY 1 ORDER BY 1;

-- registered meter counts must come from meters, not from readings
SELECT region, count(*) AS registered_meters FROM meters GROUP BY 1 ORDER BY 1;
SELECT customer_type, count(*) AS registered_meters FROM meters GROUP BY 1 ORDER BY 1;

SELECT m.customer_type, sum(r.energy_kwh) AS energy_kwh
FROM energy_readings r JOIN meters m USING (meter_id) GROUP BY 1 ORDER BY 1;

-- 5.3  completeness per region (planned = registered meters * 28 * 96)
SELECT m.region,
       count(*) AS observed_unique_pairs,
       (SELECT count(*) FROM meters mm WHERE mm.region = m.region) * 28 * 96 AS planned,
       100.0 * count(*) / ((SELECT count(*) FROM meters mm WHERE mm.region = m.region) * 28 * 96) AS completeness_pct
FROM (SELECT DISTINCT meter_id, event_time FROM energy_readings) r JOIN meters m USING (meter_id)
GROUP BY m.region ORDER BY 1;

-- 5.3  21 September: as known at 00:00 on 22 September versus all arrivals
SELECT sum(energy_kwh) FILTER (WHERE received_time <= TIMESTAMPTZ '2026-09-22 00:00:00+02') AS known_at_midnight,
       sum(energy_kwh) AS final_total
FROM energy_readings
WHERE event_time >= TIMESTAMPTZ '2026-09-21 00:00:00+02' AND event_time < TIMESTAMPTZ '2026-09-22 00:00:00+02';
