"""4.1.4 / 4.1.5  Record the cutoff (start - 48 h), copy the cleaned data into both
compressed hypertables one chunk at a time and compress each chunk whose end precedes
the cutoff.  Loading and compression are timed separately."""
import json
import time
from datetime import datetime, timedelta, timezone

import db

CAT = timezone(timedelta(hours=2), "CAT")
TABLES = ["energy_time_compressed", "energy_meter_compressed"]
COLS = "meter_id,event_time,received_time,power_kw,voltage_v,current_a,frequency_hz,energy_kwh"

conn = db.connect(autocommit=True)
cur = conn.cursor()

for t in TABLES:
    cur.execute(f"SELECT count(*) FROM {t}")
    assert cur.fetchone()[0] == 0, f"{t} must start empty"

start = datetime.now(CAT)
cutoff = start - timedelta(hours=48)            # recorded BEFORE loading
open("cutoff.txt", "w").write(cutoff.isoformat())
print("EXPERIMENT START:", start.isoformat(timespec="seconds"))
print("CUTOFF (start - 48h):", cutoff.isoformat(timespec="seconds"))

cur.execute("""SELECT range_start, range_end FROM timescaledb_information.chunks
               WHERE hypertable_name='energy_readings' ORDER BY range_start""")
ranges = cur.fetchall()

load_s = {t: 0.0 for t in TABLES}
comp_s = {t: 0.0 for t in TABLES}
comp_log = []
for a, b in ranges:
    for t in TABLES:
        t0 = time.perf_counter()
        cur.execute(f"INSERT INTO {t} ({COLS}) SELECT {COLS} FROM energy_readings "
                    "WHERE event_time >= %s AND event_time < %s", (a, b))
        load_s[t] += time.perf_counter() - t0
        if b <= cutoff:                          # chunk end precedes the cutoff
            cur.execute("""SELECT format('%%I.%%I', chunk_schema, chunk_name)
                           FROM timescaledb_information.chunks
                           WHERE hypertable_name=%s AND range_start=%s""", (t, a))
            chunk = cur.fetchone()[0]
            c0 = time.perf_counter()
            cur.execute("SELECT compress_chunk(%s::regclass)", (chunk,))
            dt = time.perf_counter() - c0
            comp_s[t] += dt
            comp_log.append([t, chunk, str(a), round(dt, 3)])
    print(f"chunk {a:%Y-%m-%d %H:%M} done", flush=True)

for t in TABLES:
    print(f"{t}: LOAD {load_s[t]:.1f}s | COMPRESSION {comp_s[t]:.1f}s")
json.dump({"cutoff": cutoff.isoformat(), "load_s": load_s, "compress_s": comp_s,
           "per_chunk": comp_log}, open("results/timing_compress.json", "w"), indent=1)

for t in TABLES:
    cur.execute(f"VACUUM (ANALYZE) {t}")
