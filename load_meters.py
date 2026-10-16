"""1.2.4  Insert the 4,000 meter metadata dictionaries into meters."""
from psycopg2.extras import execute_values
import smart_meter_simulator as sim
import db

meters = sim.meter_metadata()
rows = [(m["meter_id"], m["region"], m["customer_type"],
         m["base_power_kw"], m["power_factor"]) for m in meters]

conn = db.connect()
cur = conn.cursor()
execute_values(
    cur,
    "INSERT INTO meters (meter_id, region, customer_type, base_power_kw, power_factor) "
    "VALUES %s ON CONFLICT (meter_id) DO NOTHING", rows)
conn.commit()
cur.execute("SELECT count(*) FROM meters")
print("meters rows:", cur.fetchone()[0])
