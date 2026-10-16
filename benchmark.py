"""3.2 / 4.3  Time the five workloads on a set of hypertables.

Client: Python + psycopg2.  Timer: time.perf_counter().  One warm-up followed by five
measured runs per query and table.  A run lasts from statement submission until the last
result row has been fetched.  Results are compared with the first table (tolerance 0.001).

  python benchmark.py                       # 3.2: the 1-day, 3-hour and 1-week tables
  python benchmark.py --compressed          # 4.3: baseline + the two compressed tables
"""
import argparse
import csv
import json
import socket
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import psycopg2

import db

CAT = timezone(timedelta(hours=2), "CAT")
HOST = socket.gethostname()
D0, D1 = "'2026-09-22 00:00:00+02'", "'2026-09-29 00:00:00+02'"

QUERIES = {
    "Q1": """SELECT time_bucket('1 hour', event_time, 'Africa/Kigali') AS hour_cat,
                    avg(power_kw) AS avg_kw
             FROM {t}
             WHERE event_time >= '2026-09-21 00:00:00+02' AND event_time < '2026-09-22 00:00:00+02'
             GROUP BY 1 ORDER BY 1""",
    "Q2": f"""SELECT event_time, sum(power_kw) AS total_kw
             FROM {{t}}
             WHERE event_time >= {D0} AND event_time < {D1}
             GROUP BY event_time
             ORDER BY total_kw DESC, event_time ASC
             LIMIT 10""",
    "Q3": """SELECT meter_id, sum(energy_kwh) AS total_kwh
             FROM {t} GROUP BY meter_id ORDER BY meter_id""",
    "Q4": f"""SELECT sum(energy_kwh) AS total_kwh, avg(power_kw) AS avg_kw, max(power_kw) AS peak_kw
             FROM {{t}}
             WHERE meter_id = 1000000000 AND event_time >= {D0} AND event_time < {D1}""",
    "Q5": """SELECT count(*) AS n, sum(energy_kwh) AS total_kwh, avg(power_kw) AS avg_kw,
                    min(power_kw) AS min_kw, max(power_kw) AS max_kw FROM {t}""",
}


def num(v):
    return float(v) if isinstance(v, (float, Decimal)) else v


def same(a, b, tol=0.001):
    if len(a) != len(b):
        return False
    for ra, rb in zip(a, b):
        for x, y in zip(ra, rb):
            x, y = num(x), num(y)
            if isinstance(x, float) or isinstance(y, float):
                if abs(x - y) > tol:
                    return False
            elif x != y:
                return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--compressed", action="store_true")
    ap.add_argument("--tables", default=None, help="comma-separated; first is the baseline")
    ap.add_argument("--tag", default=None)
    args = ap.parse_args()
    if args.tables:
        tables = args.tables.split(",")
    elif args.compressed:
        tables = ["energy_readings", "energy_time_compressed", "energy_meter_compressed"]
    else:
        tables = ["energy_readings", "energy_readings_3h", "energy_readings_week"]
    tag = args.tag or ("benchmark4" if args.compressed else "benchmark")

    conn = db.connect(autocommit=True)
    cur = conn.cursor()
    runs, summary, last_rows = [], [], {}
    session_t0 = time.perf_counter()
    session_start = datetime.now(CAT)

    for q, template in QUERIES.items():
        for t in tables:
            sql = template.replace("{t}", t)
            block_t0 = time.perf_counter()
            measured = []
            for i in range(6):                      # i = 0 is the warm-up
                s_cat = datetime.now(CAT)
                p0 = time.perf_counter()
                cur.execute(sql)
                rows = cur.fetchall()               # until the last row is received
                ms = (time.perf_counter() - p0) * 1000
                e_cat = datetime.now(CAT)
                runs.append([q, t, i, "warmup" if i == 0 else "measured",
                             s_cat.isoformat(timespec="milliseconds"),
                             e_cat.isoformat(timespec="milliseconds"), round(ms, 3), HOST])
                if i > 0:
                    measured.append(ms)
            block_s = time.perf_counter() - block_t0
            last_rows[(q, t)] = rows
            match = same(last_rows[(q, tables[0])], rows)
            summary.append({"query": q, "table": t,
                            "median_ms": round(statistics.median(measured), 3),
                            "min_ms": round(min(measured), 3), "max_ms": round(max(measured), 3),
                            "session_s": round(block_s, 2), "matches_baseline": match})
            print(f"{q} {t:26s} median={statistics.median(measured):9.2f} ms  "
                  f"min={min(measured):9.2f}  max={max(measured):9.2f}  "
                  f"session={block_s:6.1f}s  results_match={match}", flush=True)

    total_s = time.perf_counter() - session_t0
    print(f"\nTOTAL SESSION SECONDS: {total_s:.1f}  (start {session_start:%H:%M:%S} CAT)")
    print("Client: Python", sys.version.split()[0], "+ psycopg2", psycopg2.__version__,
          "| timer: time.perf_counter | machine:", HOST)

    with open(f"results/{tag}_runs.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["query", "table", "run", "kind", "start_cat", "end_cat", "ms", "machine"])
        w.writerows(runs)
    json.dump({"tables": tables, "summary": summary, "total_session_s": round(total_s, 1),
               "client": f"Python {sys.version.split()[0]} + psycopg2 {psycopg2.__version__}",
               "timer": "time.perf_counter", "machine": HOST,
               "start_cat": session_start.isoformat(timespec="seconds")},
              open(f"results/{tag}_summary.json", "w"), indent=1)


if __name__ == "__main__":
    main()
