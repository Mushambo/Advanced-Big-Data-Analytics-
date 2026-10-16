"""1.3.2  Subscriber: energy/meters/# at QoS 1 -> JSON parse -> energy_live.
Start this BEFORE the publisher, with energy_live empty."""
import os
import json
import queue
import time

import paho.mqtt.client as mqtt
from psycopg2.extras import execute_values

import db

TOPIC = "energy/meters/#"
IDLE_SECONDS = 10          # stop after this long with no new messages
q = queue.Queue()
stats = {"received": 0, "dup_flag": 0, "parse_errors": 0, "inserted": 0, "insert_errors": 0}


def on_connect(client, userdata, flags, reason_code, properties):
    print("connected:", reason_code)
    client.subscribe(TOPIC, qos=1)


def on_message(client, userdata, msg):
    stats["received"] += 1
    if msg.dup:
        stats["dup_flag"] += 1          # broker redelivery
    try:
        d = json.loads(msg.payload)
        q.put((d["meter_id"], d["event_time"], d["received_time"], d["power_kw"],
               d["voltage_v"], d["current_a"], d["frequency_hz"], d["energy_kwh"]))
    except Exception as e:                # noqa: BLE001
        stats["parse_errors"] += 1
        print("PARSE ERROR:", e, msg.payload[:80])


SQL = ("INSERT INTO energy_live (meter_id, event_time, received_time, power_kw, "
       "voltage_v, current_a, frequency_hz, energy_kwh) VALUES %s")
conn = db.connect()
cur = conn.cursor()


def flush(batch):
    if not batch:
        return
    try:
        execute_values(cur, SQL, batch)
        conn.commit()
        stats["inserted"] += len(batch)
    except Exception as e:                # noqa: BLE001
        conn.rollback()
        stats["insert_errors"] += len(batch)
        print("INSERT FAILED:", e)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pilot-subscriber")
client.on_connect = on_connect
client.on_message = on_message
client.connect(os.getenv("MQTT_HOST", "localhost"), int(os.getenv("MQTT_PORT", "1883")))
client.loop_start()

batch, last = [], time.time()
print("waiting for messages...")
while True:
    try:
        batch.append(q.get(timeout=1))
        last = time.time()
    except queue.Empty:
        pass
    if len(batch) >= 200 or (batch and q.empty()):
        flush(batch)
        batch = []
    if stats["received"] > 0 and q.empty() and not batch and time.time() - last > IDLE_SECONDS:
        break

client.loop_stop()
client.disconnect()
print("SUBSCRIBER DONE:", stats)
