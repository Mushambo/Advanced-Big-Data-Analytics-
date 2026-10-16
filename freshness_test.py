"""6.2  Freshness and delayed-arrival test on a separate hypertable and hourly aggregate.

Timeline (relative to the actual test time):
  H       = start of the most recent completed CAT hour
  OLD     = H - 48 hours
  insert  1 kWh at OLD+10min, refresh ONLY the old hour           -> old 1 kWh/1 row, H absent
  insert  0.5 kWh at OLD+25min and 2 kWh at H+10min (no refresh)  -> compare raw and aggregate
  enable real-time aggregation, query again                       -> H becomes visible
  refresh both hours, query again                                 -> 1.5 kWh/2 rows and 2 kWh/1 row
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import db

CAT = timezone(timedelta(hours=2), "CAT")
conn = db.connect(autocommit=True)
cur = conn.cursor()
cur.execute("SET timezone TO 'Africa/Kigali'")

# fresh objects every run
with open("sql/06c_freshness_test.sql") as f:
    cur.execute(f.read())

now = datetime.now(CAT)
H = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
OLD = H - timedelta(hours=48)
t_old1, t_old2, t_h = OLD + timedelta(minutes=10), OLD + timedelta(minutes=25), H + timedelta(minutes=10)
print(f"TEST TIME (CAT) : {now:%Y-%m-%d %H:%M:%S}")
print(f"H               : {H:%Y-%m-%d %H:%M}   (start of most recent completed CAT hour)")
print(f"H - 48 hours    : {OLD:%Y-%m-%d %H:%M}")
print(f"event_time chosen: 1 kWh -> {t_old1:%Y-%m-%d %H:%M}, 0.5 kWh -> {t_old2:%Y-%m-%d %H:%M}, "
      f"2 kWh -> {t_h:%Y-%m-%d %H:%M}")

stages = []


def hour_view(label, ts):
    cur.execute("SELECT sum_energy_kwh, reading_count FROM fresh_test_hourly WHERE bucket = %s", (ts,))
    r = cur.fetchone()
    return "no bucket returned" if r is None else f"{r[0]:g} kWh, {r[1]} row(s)"


def raw(ts):
    cur.execute("""SELECT sum(energy_kwh), count(*) FROM fresh_test
                   WHERE event_time >= %s AND event_time < %s""", (ts, ts + timedelta(hours=1)))
    s, n = cur.fetchone()
    return "no rows" if not n else f"{s:g} kWh, {n} row(s)"


def snapshot(stage):
    row = {"stage": stage, "older_raw": raw(OLD), "H_raw": raw(H),
           "older_agg": hour_view("old", OLD), "H_agg": hour_view("H", H)}
    stages.append(row)
    print(f"\n--- {stage}")
    print(f"  raw table     older: {row['older_raw']:<22} H: {row['H_raw']}")
    print(f"  aggregate     older: {row['older_agg']:<22} H: {row['H_agg']}")


cur.execute("""SELECT materialized_only FROM timescaledb_information.continuous_aggregates
               WHERE view_name='fresh_test_hourly'""")
print("\nreal-time aggregation (materialized_only) at start:", cur.fetchone()[0])

cur.execute("INSERT INTO fresh_test VALUES (%s, 1.0)", (t_old1,))
cur.execute("CALL refresh_continuous_aggregate('fresh_test_hourly', %s, %s)", (OLD, OLD + timedelta(hours=1)))
snapshot("1. Initial older-hour refresh, real-time off")

cur.execute("INSERT INTO fresh_test VALUES (%s, 0.5)", (t_old2,))
cur.execute("INSERT INTO fresh_test VALUES (%s, 2.0)", (t_h,))
snapshot("2. After both new inserts, before refresh, real-time off")

cur.execute("ALTER MATERIALIZED VIEW fresh_test_hourly SET (timescaledb.materialized_only = false)")
snapshot("3. Real-time on, still before refresh")

cur.execute("CALL refresh_continuous_aggregate('fresh_test_hourly', %s, %s)", (OLD, OLD + timedelta(hours=1)))
cur.execute("CALL refresh_continuous_aggregate('fresh_test_hourly', %s, %s)", (H, H + timedelta(hours=1)))
snapshot("4. After manual refresh of both hours")

# which hours could the 6.1 policy (start 3 days, end 1 hour) refresh at the test time?
win_lo, win_hi = now - timedelta(days=3), now - timedelta(hours=1)
for name, h in (("older hour", OLD), ("hour H", H)):
    inside = h >= win_lo and h + timedelta(hours=1) <= win_hi
    print(f"policy window [{win_lo:%m-%d %H:%M}, {win_hi:%m-%d %H:%M}) can refresh {name} "
          f"[{h:%m-%d %H:%M}, {(h+timedelta(hours=1)):%H:%M}): {'YES' if inside else 'NO'}")
json.dump({"test_time": now.isoformat(timespec="seconds"), "H": H.isoformat(), "older": OLD.isoformat(),
           "inserts": [t_old1.isoformat(), t_old2.isoformat(), t_h.isoformat()], "stages": stages,
           "policy_window": [win_lo.isoformat(timespec="seconds"), win_hi.isoformat(timespec="seconds")]},
          open("results/freshness.json", "w"), indent=1)
