"""1.3.1  Publisher: first 2,000 generator dictionaries -> JSON -> energy/meters/{meter_id},
MQTT QoS 1, retain=False.  The pilot replays history; it does not wait 15 minutes."""
import os
import itertools
import json
import time

import paho.mqtt.client as mqtt

import smart_meter_simulator as sim

N = 2000
acked = 0


def on_publish(client, userdata, mid, reason_code, properties):
    global acked
    acked += 1                      # PUBACK received from the broker


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pilot-publisher")
client.on_publish = on_publish
client.connect(os.getenv("MQTT_HOST", "localhost"), int(os.getenv("MQTT_PORT", "1883")))
client.loop_start()

taken, infos = 0, []
for rec in itertools.islice(sim.iter_readings(), N):
    taken += 1
    infos.append(client.publish(f"energy/meters/{rec['meter_id']}",
                                json.dumps(rec), qos=1, retain=False))
for info in infos:
    info.wait_for_publish(timeout=30)
time.sleep(1)

client.loop_stop()
client.disconnect()
print(f"PUBLISHER DONE: taken from generator={taken}, acknowledged by broker={acked}")
