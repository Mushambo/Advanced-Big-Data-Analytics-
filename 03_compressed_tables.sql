-- 4.1  Two empty hypertables (1-day chunks), same columns and indexes, two compression layouts.
CREATE TABLE energy_time_compressed (
  meter_id BIGINT, event_time TIMESTAMPTZ NOT NULL, received_time TIMESTAMPTZ,
  power_kw DOUBLE PRECISION, voltage_v DOUBLE PRECISION, current_a DOUBLE PRECISION,
  frequency_hz DOUBLE PRECISION, energy_kwh DOUBLE PRECISION);
SELECT create_hypertable('energy_time_compressed','event_time', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_etc_meter_time ON energy_time_compressed (meter_id, event_time);

CREATE TABLE energy_meter_compressed (
  meter_id BIGINT, event_time TIMESTAMPTZ NOT NULL, received_time TIMESTAMPTZ,
  power_kw DOUBLE PRECISION, voltage_v DOUBLE PRECISION, current_a DOUBLE PRECISION,
  frequency_hz DOUBLE PRECISION, energy_kwh DOUBLE PRECISION);
SELECT create_hypertable('energy_meter_compressed','event_time', chunk_time_interval => INTERVAL '1 day');
CREATE INDEX idx_emc_meter_time ON energy_meter_compressed (meter_id, event_time);

-- Time-ordered, no segmentation.
ALTER TABLE energy_time_compressed SET (
  timescaledb.enable_columnstore = true,
  timescaledb.orderby = 'event_time DESC',
  timescaledb.segmentby = '');
-- Same ordering, segmented by meter.
ALTER TABLE energy_meter_compressed SET (
  timescaledb.enable_columnstore = true,
  timescaledb.orderby = 'event_time DESC',
  timescaledb.segmentby = 'meter_id');

-- Policies: compress chunks whose end is more than 48 hours old. Pause them straight away
-- (job ids are printed by add_compression_policy; replace 1000 / 1001 with yours).
SELECT add_compression_policy('energy_time_compressed',  compress_after => INTERVAL '48 hours') AS job_time;
SELECT add_compression_policy('energy_meter_compressed', compress_after => INTERVAL '48 hours') AS job_meter;
