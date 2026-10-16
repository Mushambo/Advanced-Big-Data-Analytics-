-- 3.1.2  Copy the cleaned rows into both new hypertables, then refresh statistics.
-- Run each INSERT on its own and check it reports INSERT 0 10643735.
\timing on
INSERT INTO energy_readings_3h (meter_id,event_time,received_time,power_kw,voltage_v,current_a,frequency_hz,energy_kwh)
SELECT meter_id,event_time,received_time,power_kw,voltage_v,current_a,frequency_hz,energy_kwh FROM energy_readings;

INSERT INTO energy_readings_week (meter_id,event_time,received_time,power_kw,voltage_v,current_a,frequency_hz,energy_kwh)
SELECT meter_id,event_time,received_time,power_kw,voltage_v,current_a,frequency_hz,energy_kwh FROM energy_readings;

VACUUM (ANALYZE) energy_readings;
VACUUM (ANALYZE) energy_readings_3h;
VACUUM (ANALYZE) energy_readings_week;
