# Smart Energy Grid Analytics — Assignment I (Advanced Big Data Analytics, October 2026)

4,000 smart meters, 28 days (1–28 September 2026, 15-minute readings), EMQX + PostgreSQL/TimescaleDB,
Python analysis. All times are CAT (Africa/Kigali, UTC+02:00, no daylight saving).

* `smart_meter_simulator.py` is the supplied generator, **unchanged** (byte for byte).
* Passwords and secrets are placeholders. Copy `.env.example` to `.env`, choose a password, and set the
  same value in every PowerShell window: `$env:PGPASSWORD="choose-a-password"`.
* The full generated dataset (`readings.csv`, about 1.2 GB) stays local and is not committed. It can be
  regenerated at any time with `python capture_csv.py`.

## 0. Requirements

* Windows 10/11 with Docker Desktop (PostgreSQL + TimescaleDB 2.30 on PG16 and EMQX run as containers)
* Python 3.12 — `pip install -r requirements.txt`
* About 10 GB free disk space
* For the dashboard timing only: `playwright install chromium`

## 1. Start the services (1.1)

```powershell
copy .env.example .env          # then edit PGPASSWORD
docker compose up -d
docker compose ps
docker exec emqx emqx ctl status
$env:PGPASSWORD="choose-a-password"
docker exec -it timescaledb psql -U postgres -d iot_assignment -f /sql/01_schema.sql
```

`01_schema.sql` enables TimescaleDB, sets the database time zone to `Africa/Kigali`, and creates
`energy_live`, `energy_readings` (hypertable, 1-day chunks) and `meters`. Daily buckets are aligned to
CAT midnight with `time_bucket('1 day', event_time, 'Africa/Kigali')`.

## 2. Meters and the 2,000-message pilot (1.2, 1.3)  — verify the four counts

```powershell
python load_meters.py        # 4,000 rows in meters
python run_pilot.py          # truncates energy_live, starts subscriber, runs publisher, prints the four counts
```

Expected: generator 2000 · acknowledged 2000 · received 2000 · rows in `energy_live` 2000.
(`pilot_subscriber.py` and `pilot_publisher.py` can also be run by hand: subscriber first, then publisher.)

## 3. Full dataset (2.1 – 2.3)

```powershell
python capture_csv.py        # generator -> readings.csv   (10,696,848 rows, timed)
python load_csv.py           # COPY in 500,000-row batches into energy_readings (timed, one transaction)
docker exec -it timescaledb psql -U postgres -d iot_assignment -f /sql/04_quality.sql    # 2.2 diagnostics
python clean.py              # 2.3 removes 53,113 identical copies; verifies 10,643,735 rows
```

## 4. Chunk intervals (3.1 – 3.3)

```powershell
docker exec -it timescaledb psql -U postgres -d iot_assignment -f /sql/02_chunk_tables.sql
docker exec -it timescaledb psql -U postgres -d iot_assignment -f /sql/02b_copy_chunk_tables.sql
docker exec -it timescaledb psql -U postgres -d iot_assignment -f /sql/02d_indexes.sql
docker exec -it timescaledb psql -U postgres -d iot_assignment -f /sql/02c_verify_chunk_tables.sql
python benchmark.py          # 1 warm-up + 5 measured runs of Q1–Q5 on the three tables
```

## 5. Compression (4.1 – 4.4)

```powershell
docker exec -it timescaledb psql -U postgres -d iot_assignment -f /sql/03_compressed_tables.sql
# pause both policies (use the two job ids printed by the script)
docker exec -it timescaledb psql -U postgres -d iot_assignment -c "SELECT alter_job(1000, scheduled => false);" -c "SELECT alter_job(1001, scheduled => false);"
python load_compressed.py    # records cutoff = start - 48 h, loads chunk by chunk, compresses chunks, times both
python benchmark.py --compressed
# after the measurements, resume the policies
docker exec -it timescaledb psql -U postgres -d iot_assignment -c "SELECT alter_job(1000, scheduled => true);" -c "SELECT alter_job(1001, scheduled => true);"
```

## 6. Analysis (Sections 5 and 8)

```powershell
python analysis_section5.py  # 5.1 demand, 5.2 regions/customer types, 5.3 completeness and late arrivals
python anomaly.py            # 5.4 anomaly rule and evaluation against anomaly_events()
python s8_forecast.py        # 8.1–8.4 dataset, baseline, Ridge model, evaluation, charts
```

## 7. Continuous aggregates (6.1, 6.2)

```powershell
docker exec -it timescaledb psql -U postgres -d iot_assignment -f /sql/06_caggs.sql      # three views, WITH NO DATA, real-time off
python caggs_refresh.py      # manual full refresh, refresh seconds and size per view
docker exec -it timescaledb psql -U postgres -d iot_assignment -f /sql/06b_cagg_policies.sql   # 3 days / 1 hour / 15 minutes
python freshness_test.py     # 6.2 (uses sql/06c_freshness_test.sql); run it at any time of day
```

## 8. Dashboards (7.1 – 7.4)

```powershell
python dashboard/app.py --mode raw       --port 8050     # dashboard "Raw"       http://127.0.0.1:8050
python dashboard/app.py --mode aggregate --port 8051     # dashboard "Aggregate" http://127.0.0.1:8051
python bench_dashboards.py verify        # 7.3 compares every panel (keys, counts, energy, completeness)
python bench_dashboards.py time          # 7.4 1 warm-up + 10 measured refreshes per dashboard
```

Panel queries for both dashboards: `dashboard/queries.py`.

## File map

| File | Purpose |
|---|---|
| `docker-compose.yml`, `.env.example` | EMQX + TimescaleDB containers, secret placeholders |
| `sql/*.sql` | schema, chunk tables, compression, quality checks, analysis, aggregates, freshness test |
| `db.py` | connection helper (environment variables) |
| `load_meters.py`, `pilot_publisher.py`, `pilot_subscriber.py`, `run_pilot.py` | 1.2, 1.3 |
| `capture_csv.py`, `load_csv.py`, `clean.py` | 2.1, 2.3 |
| `benchmark.py`, `load_compressed.py` | 3.2, 4.1–4.3 |
| `analysis_section5.py`, `anomaly.py` | 5.1–5.4 |
| `caggs_refresh.py`, `freshness_test.py` | 6.1, 6.2 |
| `dashboard/app.py`, `dashboard/queries.py`, `bench_dashboards.py` | 7.1–7.4 |
| `s8_forecast.py` | 8.1–8.4 |
| `results/` | recorded timings and outputs (see `results/README.md`) |
| `docs/` | the final report and environment notes |

## Recorded environment

See `docs/environment.md` (CPU, RAM, OS, storage, versions, PostgreSQL settings; PostgreSQL runs in a
Docker container with no CPU or memory limits set).
