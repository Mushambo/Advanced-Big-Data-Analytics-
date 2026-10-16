"""2.3  Repeatable cleaning of energy_readings.
1. Check that duplicate pairs never carry conflicting values.
2. Delete the extra identical copies, one UTC-aligned day window at a time.
3. Verify the final row count equals expected_counts.unique_readings.
Running it twice is safe: the second run finds nothing to delete."""
from datetime import datetime, timedelta

import db

EXPECTED_UNIQUE = 10643735

conn = db.connect(autocommit=True)
cur = conn.cursor()


def stats(label):
    cur.execute("SELECT count(*), sum(energy_kwh) FROM energy_readings")
    n, s = cur.fetchone()
    print(f"{label}: rows={n:,}  sum_energy_kwh={s:.6f}")
    return n, s


before = stats("BEFORE")

cur.execute("""
  SELECT count(*) FROM (
    SELECT meter_id, event_time
    FROM energy_readings
    GROUP BY meter_id, event_time
    HAVING count(*) > 1 AND count(DISTINCT ROW(received_time, power_kw, voltage_v,
           current_a, frequency_hz, energy_kwh)) > 1) t""")
conflicts = cur.fetchone()[0]
print("CONFLICTING DUPLICATE PAIRS:", conflicts)
assert conflicts == 0, "Conflicts found - investigate before deleting"

start = datetime.fromisoformat("2026-08-31T22:00:00+00:00")   # before the first reading
removed = 0
for d in range(30):
    a = start + timedelta(days=d)
    b = a + timedelta(days=1)
    cur.execute("""
      DELETE FROM energy_readings x
      USING (SELECT tableoid AS t, ctid AS c,
                    row_number() OVER (PARTITION BY meter_id, event_time ORDER BY ctid) AS rn
             FROM energy_readings
             WHERE event_time >= %s AND event_time < %s) d
      WHERE x.tableoid = d.t AND x.ctid = d.c AND d.rn > 1
        AND x.event_time >= %s AND x.event_time < %s""", (a, b, a, b))
    removed += cur.rowcount
    print(f"day window {a:%Y-%m-%d %H:%M}Z removed {cur.rowcount}")
print("TOTAL REMOVED:", removed)

cur.execute("VACUUM (ANALYZE) energy_readings")
after = stats("AFTER ")

cur.execute("""SELECT count(*) FROM (SELECT 1 FROM energy_readings
               GROUP BY meter_id, event_time HAVING count(*) > 1) t""")
print("REMAINING DUPLICATE PAIRS:", cur.fetchone()[0])
print(f"MATCHES expected unique_readings ({EXPECTED_UNIQUE:,}):", after[0] == EXPECTED_UNIQUE)
print("Rows removed:", before[0] - after[0], " Energy removed (kWh):", before[1] - after[1])
