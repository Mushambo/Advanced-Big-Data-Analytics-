"""2.1  Capture the full generator stream to readings.csv (no database access).
Records are consumed progressively; nothing is accumulated in memory."""
import csv
import json
import time
from datetime import datetime

import smart_meter_simulator as sim

info = sim.dataset_info()
expected = info["expected_counts"]["emitted_readings"]
print("planned_readings :", info["planned_readings"])
print("expected counts  :", info["expected_counts"])

FIELDS = info["reading_fields"]
t0 = time.time()
start_cat = datetime.now()
n = 0
with open("readings.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(FIELDS)
    for rec in sim.iter_readings():          # fresh iterator, consumed progressively
        w.writerow([rec[k] for k in FIELDS])
        n += 1
        if n % 500000 == 0:
            print(f"{n:,} dictionaries consumed  ({time.time()-t0:.0f}s)", flush=True)
gen_seconds = time.time() - t0

print("DICTIONARIES CONSUMED:", n)
print("expected emitted     :", expected, "->", "MATCH" if n == expected else "MISMATCH")
print(f"GENERATION SECONDS   : {gen_seconds:.1f}")
json.dump({"consumed": n, "gen_seconds": gen_seconds, "gen_start": start_cat.isoformat()},
          open("timing_gen.json", "w"))
