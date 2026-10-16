"""6.1.3  Manually refresh the whole generated period of each (empty) continuous aggregate,
time it and report the materialized data + index size and row count.
Policies are added afterwards with sql/06b_cagg_policies.sql."""
import json

import time

import db

VIEWS = ["cagg_15min_region", "cagg_hour_region", "cagg_day_meter"]
W0, W1 = "2026-09-01 00:00:00+02", "2026-09-29 00:00:00+02"

conn = db.connect(autocommit=True)         # refresh_continuous_aggregate cannot run in a transaction
cur = conn.cursor()
cur.execute("SET timezone TO 'Africa/Kigali'")
res = []
for v in VIEWS:
    cur.execute(f"SELECT count(*) FROM {v}")
    assert cur.fetchone()[0] == 0, f"{v} must be empty before the first refresh"
    t0 = time.perf_counter()
    cur.execute(f"CALL refresh_continuous_aggregate('{v}', %s, %s)", (W0, W1))
    secs = time.perf_counter() - t0
    cur.execute("""SELECT materialization_hypertable_schema || '.' || materialization_hypertable_name
                   FROM timescaledb_information.continuous_aggregates WHERE view_name = %s""", (v,))
    mat = cur.fetchone()[0]
    cur.execute("""SELECT table_bytes, index_bytes, COALESCE(toast_bytes,0), total_bytes
                   FROM hypertable_detailed_size(%s::regclass)""", (mat,))
    tb, ib, tob, tot = cur.fetchone()
    cur.execute(f"SELECT count(*), sum(reading_count), min(bucket), max(bucket) FROM {v}")
    n, readings, lo, hi = cur.fetchone()
    cur.execute("VACUUM (ANALYZE) " + mat)
    r = {"view": v, "refresh_s": round(secs, 2), "materialization": mat, "rows": n,
         "readings_covered": int(readings), "table_bytes": tb, "index_bytes": ib,
         "total_bytes": tot, "first_bucket": str(lo), "last_bucket": str(hi)}
    res.append(r)
    print(f"{v}: refresh {secs:.1f}s  rows={n:,}  readings={int(readings):,}  "
          f"data={tb/1e6:.1f} MB  index={ib/1e6:.1f} MB  total={tot/1e6:.1f} MB")
json.dump(res, open("results/cagg_refresh.json", "w"), indent=1)
