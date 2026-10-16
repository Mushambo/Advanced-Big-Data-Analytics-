-- 6.1.3  Refresh policies: 3-day lookback, 1-hour end offset, 15-minute schedule.
-- Run ONLY after the manual full refresh and its measurements (caggs_refresh.py).
-- The offsets are relative to the database clock, so these policies do not touch the
-- September 2026 data that was refreshed manually.
SELECT add_continuous_aggregate_policy('cagg_15min_region',
       start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour',
       schedule_interval => INTERVAL '15 minutes', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('cagg_hour_region',
       start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour',
       schedule_interval => INTERVAL '15 minutes', if_not_exists => TRUE);
SELECT add_continuous_aggregate_policy('cagg_day_meter',
       start_offset => INTERVAL '3 days', end_offset => INTERVAL '1 hour',
       schedule_interval => INTERVAL '15 minutes', if_not_exists => TRUE);

-- evidence: policy settings and background-job status
SELECT j.job_id, j.hypertable_name, j.schedule_interval, j.scheduled, j.config
FROM timescaledb_information.jobs j
WHERE j.proc_name = 'policy_refresh_continuous_aggregate' ORDER BY j.job_id;
SELECT job_id, hypertable_name, last_run_status, next_start, total_runs, total_successes, total_failures
FROM timescaledb_information.job_stats
WHERE job_id IN (SELECT job_id FROM timescaledb_information.jobs
                 WHERE proc_name = 'policy_refresh_continuous_aggregate') ORDER BY job_id;
