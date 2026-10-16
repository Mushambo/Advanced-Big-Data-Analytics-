-- 3.1.2  Matching non-unique indexes on all three reading tables.
-- create_hypertable already created the default btree (event_time DESC) on each table.
CREATE INDEX IF NOT EXISTS idx_er_meter_time   ON energy_readings      (meter_id, event_time);
CREATE INDEX IF NOT EXISTS idx_er3h_meter_time ON energy_readings_3h   (meter_id, event_time);
CREATE INDEX IF NOT EXISTS idx_erw_meter_time  ON energy_readings_week (meter_id, event_time);
