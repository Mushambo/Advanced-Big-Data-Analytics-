-- 1.1 / 1.2  Extension, session time zone, and the three base tables.
CREATE EXTENSION IF NOT EXISTS timescaledb;
ALTER DATABASE iot_assignment SET timezone TO 'Africa/Kigali';

-- Regular table for the MQTT pilot (duplicates allowed, no constraints).
CREATE TABLE energy_live (
  meter_id      BIGINT,
  event_time    TIMESTAMPTZ,
  received_time TIMESTAMPTZ,
  power_kw      DOUBLE PRECISION,
  voltage_v     DOUBLE PRECISION,
  current_a     DOUBLE PRECISION,
  frequency_hz  DOUBLE PRECISION,
  energy_kwh    DOUBLE PRECISION
);

-- Hypertable with one-day chunks (duplicates allowed at this stage).
CREATE TABLE energy_readings (
  meter_id      BIGINT,
  event_time    TIMESTAMPTZ NOT NULL,
  received_time TIMESTAMPTZ,
  power_kw      DOUBLE PRECISION,
  voltage_v     DOUBLE PRECISION,
  current_a     DOUBLE PRECISION,
  frequency_hz  DOUBLE PRECISION,
  energy_kwh    DOUBLE PRECISION
);
SELECT create_hypertable('energy_readings', 'event_time',
                         chunk_time_interval => INTERVAL '1 day');

CREATE TABLE meters (
  meter_id      BIGINT PRIMARY KEY,
  region        TEXT,
  customer_type TEXT,
  base_power_kw DOUBLE PRECISION,
  power_factor  DOUBLE PRECISION
);
