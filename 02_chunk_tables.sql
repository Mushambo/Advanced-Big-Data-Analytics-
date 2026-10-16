-- 3.1  Two extra hypertables with 3-hour and 1-week chunks.
CREATE TABLE energy_readings_3h (
  meter_id BIGINT, event_time TIMESTAMPTZ NOT NULL, received_time TIMESTAMPTZ,
  power_kw DOUBLE PRECISION, voltage_v DOUBLE PRECISION, current_a DOUBLE PRECISION,
  frequency_hz DOUBLE PRECISION, energy_kwh DOUBLE PRECISION);
SELECT create_hypertable('energy_readings_3h', 'event_time',
                         chunk_time_interval => INTERVAL '3 hours');

CREATE TABLE energy_readings_week (
  meter_id BIGINT, event_time TIMESTAMPTZ NOT NULL, received_time TIMESTAMPTZ,
  power_kw DOUBLE PRECISION, voltage_v DOUBLE PRECISION, current_a DOUBLE PRECISION,
  frequency_hz DOUBLE PRECISION, energy_kwh DOUBLE PRECISION);
SELECT create_hypertable('energy_readings_week', 'event_time',
                         chunk_time_interval => INTERVAL '1 week');
