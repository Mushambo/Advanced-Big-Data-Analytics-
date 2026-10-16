"""2.1  Bulk-load readings.csv into energy_readings with COPY, in 500,000-row batches,
inside one transaction (all-or-nothing)."""
import io
import itertools
import json
import time

import db

gen = json.load(open("timing_gen.json"))
COLS = "meter_id,event_time,received_time,power_kw,voltage_v,current_a,frequency_hz,energy_kwh"
CHUNK = 500_000
EXPECTED = 10696848

conn = db.connect()
cur = conn.cursor()
cur.execute("SELECT count(*) FROM energy_readings")
assert cur.fetchone()[0] == 0, "energy_readings must start empty"

t0 = time.time()                          # first database write
loaded = 0
with open("readings.csv", "r", newline="") as f:
    next(f)                               # skip header
    while True:
        lines = list(itertools.islice(f, CHUNK))
        if not lines:
            break
        cur.copy_expert(f"COPY energy_readings ({COLS}) FROM STDIN WITH (FORMAT csv)",
                        io.StringIO("".join(lines)))
        loaded += len(lines)
        print(f"{loaded:,} rows copied ({time.time()-t0:.0f}s)", flush=True)
conn.commit()                             # final commit
load_seconds = time.time() - t0

cur.execute("SELECT count(*) FROM energy_readings")
db_rows = cur.fetchone()[0]
print("COMMITTED ROWS      :", db_rows)
print("EXPECTED EMITTED    :", EXPECTED)
print("ALL THREE AGREE     :", gen["consumed"] == loaded == db_rows == EXPECTED)
print(f"LOAD SECONDS        : {load_seconds:.1f}")
print(f"GENERATION SECONDS  : {gen['gen_seconds']:.1f}")
print(f"TOTAL ELAPSED       : {gen['gen_seconds'] + load_seconds:.1f} s (generation start to final commit)")
