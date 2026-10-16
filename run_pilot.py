"""1.3 / 9.2.4  One-command pilot check.

Empties energy_live, starts the subscriber, waits until it is subscribed, runs the publisher,
waits for the subscriber to finish and prints the four counts in one table:

    generator dictionaries | broker acknowledgements | subscriber received | rows in energy_live

Run:  python run_pilot.py
Needs: broker on MQTT_HOST:MQTT_PORT (default localhost:1883) and the schema from sql/01_schema.sql.
"""
import os
import re
import subprocess
import sys
import time

import db

PY = sys.executable
env = dict(os.environ, PYTHONUNBUFFERED="1")

conn = db.connect(autocommit=True)
cur = conn.cursor()
cur.execute("TRUNCATE energy_live")
cur.execute("SELECT count(*) FROM energy_live")
print("energy_live rows before the pilot:", cur.fetchone()[0])

sub = subprocess.Popen([PY, "pilot_subscriber.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, env=env)
lines = []
t0 = time.time()
while time.time() - t0 < 30:                       # wait for "waiting for messages..." and "connected"
    line = sub.stdout.readline()
    if not line:
        break
    lines.append(line.rstrip())
    print("[subscriber]", line.rstrip())
    if "connected" in line:
        break
time.sleep(1.0)                                     # let the SUBSCRIBE (QoS 1) be acknowledged

pub = subprocess.run([PY, "pilot_publisher.py"], capture_output=True, text=True, env=env)
print("[publisher] ", pub.stdout.strip())
pm = re.search(r"taken from generator=(\d+), acknowledged by broker=(\d+)", pub.stdout)

rest, _ = sub.communicate(timeout=120)              # subscriber ends after IDLE_SECONDS without messages
for l in rest.splitlines():
    print("[subscriber]", l)
sm = re.search(r"'received': (\d+)", rest)

cur.execute("SELECT count(*) FROM energy_live")
rows = cur.fetchone()[0]
taken, acked = (int(pm.group(1)), int(pm.group(2))) if pm else (None, None)
received = int(sm.group(1)) if sm else None

print("\n+-----------------------------------------+-------+")
print("| Stage                                   | Count |")
print("+-----------------------------------------+-------+")
for name, val in [("Dictionaries taken from generator", taken), ("Messages acknowledged by broker", acked),
                  ("Messages received by subscriber", received), ("Rows in energy_live", rows)]:
    print(f"| {name:<39} | {val!s:>5} |")
print("+-----------------------------------------+-------+")
ok = taken == acked == received == rows == 2000
print("ALL FOUR COUNTS EQUAL 2000:", ok)
sys.exit(0 if ok else 1)
