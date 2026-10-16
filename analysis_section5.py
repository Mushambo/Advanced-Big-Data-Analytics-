"""Section 5.1 - 5.3  Demand patterns, regions / customer types and reporting quality.
Reads cleaned energy_readings + meters, prints every result, saves charts and
results/section5.json."""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import db

os.makedirs("results/charts", exist_ok=True)
conn = db.connect(autocommit=True)
cur = conn.cursor()
conn.cursor().execute("SET timezone TO 'Africa/Kigali'")


def q(sql, cols):
    cur.execute(sql)
    return pd.DataFrame(cur.fetchall(), columns=cols)


out = {}

# ---------------------------------------------------------------- 5.1
daily = q("""SELECT time_bucket('1 day', event_time, 'Africa/Kigali')::date, sum(energy_kwh)
             FROM energy_readings GROUP BY 1 ORDER BY 1""", ["day", "kwh"])
weekly = q("""SELECT DATE '2026-09-01' + 7 * ((time_bucket('1 day', event_time, 'Africa/Kigali')::date
                                             - DATE '2026-09-01') / 7), sum(energy_kwh)
              FROM energy_readings GROUP BY 1 ORDER BY 1""", ["period_start", "kwh"])
weekly["period_end"] = pd.to_datetime(weekly["period_start"]) + pd.Timedelta(days=6)
top3 = q("""SELECT event_time, sum(power_kw) FROM energy_readings
            GROUP BY event_time ORDER BY 2 DESC, 1 LIMIT 3""", ["event_time", "kw"])
top3["event_time"] = top3["event_time"].astype(str)

# network demand profile (average kW per time of day, weekday vs weekend) for the discussion
prof = q("""SELECT extract(hour from event_time)::int AS h,
                   (extract(isodow from event_time) >= 6) AS weekend,
                   avg(net_kw) FROM (SELECT event_time, sum(power_kw) AS net_kw FROM energy_readings
                                     GROUP BY event_time) t GROUP BY 1, 2 ORDER BY 2, 1""",
         ["hour", "weekend", "kw"])

print("DAILY ENERGY (kWh)\n", daily.to_string(index=False))
print("\nSEVEN-DAY PERIODS\n", weekly.to_string(index=False))
print("\nTOP 3 15-MINUTE NETWORK DEMAND INTERVALS\n", top3.to_string(index=False))

fig, ax = plt.subplots(1, 2, figsize=(13, 4.2), gridspec_kw={"width_ratios": [2.4, 1]})
cols = ["#c0504d" if pd.Timestamp(d).weekday() >= 5 else "#2f5f98" for d in daily["day"]]
ax[0].bar(pd.to_datetime(daily["day"]).dt.strftime("%d %b"), daily["kwh"] / 1000, color=cols)
ax[0].set_ylabel("Network energy (MWh)")
ax[0].set_title("Total network energy per CAT day (red = weekend)")
ax[0].tick_params(axis="x", rotation=90, labelsize=8)
ax[1].bar([f"{a:%d %b}-{b:%d %b}" for a, b in zip(pd.to_datetime(weekly["period_start"]), weekly["period_end"])],
          weekly["kwh"] / 1000, color="#2f5f98")
ax[1].set_ylabel("Network energy (MWh)")
ax[1].set_title("Four seven-day periods")
ax[1].tick_params(axis="x", rotation=30, labelsize=8)
fig.tight_layout()
fig.savefig("results/charts/5_1_energy.png", dpi=150)
plt.close(fig)

fig, ax = plt.subplots(figsize=(7, 3.8))
for wk, lab, c in [(False, "Weekday", "#2f5f98"), (True, "Weekend", "#c0504d")]:
    d = prof[prof["weekend"] == wk]
    ax.plot(d["hour"], d["kw"], label=lab, color=c, lw=2)
ax.set_xlabel("Hour of day (CAT)")
ax.set_ylabel("Average network demand (kW)")
ax.set_title("Average 15-minute network demand by hour")
ax.legend()
fig.tight_layout()
fig.savefig("results/charts/5_1_profile.png", dpi=150)
plt.close(fig)

out["daily"] = [{"day": str(d), "kwh": float(k)} for d, k in zip(daily["day"], daily["kwh"])]
out["weekly"] = [{"start": str(a.date()), "end": str(b.date()), "kwh": float(k)}
                 for a, b, k in zip(pd.to_datetime(weekly["period_start"]), weekly["period_end"], weekly["kwh"])]
out["top3"] = top3.to_dict("records")
out["profile"] = prof.to_dict("records")

# ---------------------------------------------------------------- 5.2
counts_region = q("SELECT region, count(*) FROM meters GROUP BY 1 ORDER BY 1", ["region", "meters"])
counts_type = q("SELECT customer_type, count(*) FROM meters GROUP BY 1 ORDER BY 1", ["customer_type", "meters"])
by_region = q("""SELECT m.region, sum(r.energy_kwh) FROM energy_readings r
                 JOIN meters m USING (meter_id) GROUP BY 1 ORDER BY 1""", ["region", "kwh"])
by_type = q("""SELECT m.customer_type, sum(r.energy_kwh) FROM energy_readings r
               JOIN meters m USING (meter_id) GROUP BY 1 ORDER BY 1""", ["customer_type", "kwh"])
by_region = by_region.merge(counts_region, on="region")
by_type = by_type.merge(counts_type, on="customer_type")
for d in (by_region, by_type):
    d["kwh_per_meter"] = d["kwh"] / d["meters"]
by_region["order"] = by_region["region"].str.extract(r"(\d+)").astype(int)
by_region = by_region.sort_values("order").drop(columns="order")
print("\nBY REGION\n", by_region.to_string(index=False))
print("\nBY CUSTOMER TYPE\n", by_type.to_string(index=False))

fig, ax = plt.subplots(1, 2, figsize=(13, 4))
ax[0].bar(by_region["region"].str.replace("Region ", "R"), by_region["kwh_per_meter"], color="#2f5f98")
ax[0].set_title("Energy per meter by region (kWh, 28 days)")
ax[0].set_ylabel("kWh per meter")
ax[0].set_ylim(by_region["kwh_per_meter"].min() * 0.9, by_region["kwh_per_meter"].max() * 1.05)
ax[1].bar(by_type["customer_type"], by_type["kwh_per_meter"], color=["#2f5f98", "#6a9fd6", "#c0504d"])
ax[1].set_title("Energy per meter by customer type (kWh, 28 days)")
ax[1].set_ylabel("kWh per meter")
fig.tight_layout()
fig.savefig("results/charts/5_2_groups.png", dpi=150)
plt.close(fig)
out["by_region"] = by_region.to_dict("records")
out["by_type"] = by_type.to_dict("records")

# ---------------------------------------------------------------- 5.3
# DISTINCT over 10.6 M rows sorts on disk with the default 4 MB work_mem; give THIS analysis session more
# memory (session-only; no benchmark is timed in this program).
cur.execute("SET work_mem = '512MB'")
comp_net = q("SELECT count(*) FROM (SELECT DISTINCT meter_id, event_time FROM energy_readings) t", ["n"])["n"][0]
planned_net = 4000 * 28 * 96
comp_reg = q("""SELECT m.region, count(*) FROM (SELECT DISTINCT meter_id, event_time FROM energy_readings) r
                JOIN meters m USING (meter_id) GROUP BY 1""", ["region", "observed"])
comp_reg = comp_reg.merge(counts_region, on="region")
comp_reg["planned"] = comp_reg["meters"] * 28 * 96
comp_reg["completeness_pct"] = 100.0 * comp_reg["observed"] / comp_reg["planned"]
comp_reg["order"] = comp_reg["region"].str.extract(r"(\d+)").astype(int)
comp_reg = comp_reg.sort_values("order").drop(columns="order")
print(f"\nNETWORK completeness: {comp_net:,} / {planned_net:,} = {100*comp_net/planned_net:.4f}%")
print(comp_reg.to_string(index=False))
out["completeness_network"] = {"observed": int(comp_net), "planned": planned_net,
                               "pct": 100.0 * comp_net / planned_net}
out["completeness_region"] = comp_reg.to_dict("records")

cur.execute("""SELECT sum(energy_kwh) FILTER (WHERE received_time <= TIMESTAMPTZ '2026-09-22 00:00:00+02'),
                      sum(energy_kwh), count(*),
                      count(*) FILTER (WHERE received_time <= TIMESTAMPTZ '2026-09-22 00:00:00+02')
               FROM energy_readings
               WHERE event_time >= TIMESTAMPTZ '2026-09-21 00:00:00+02'
                 AND event_time <  TIMESTAMPTZ '2026-09-22 00:00:00+02'""")
known, final, n_all, n_known = cur.fetchone()
print(f"\n21 SEPTEMBER: known at 00:00 on 22 Sep = {known:.3f} kWh ({n_known:,} rows); "
      f"all arrivals = {final:.3f} kWh ({n_all:,} rows); "
      f"difference = {final-known:.3f} kWh = {100*(final-known)/final:.4f}% of final")
out["day21"] = {"known": known, "final": final, "diff": final - known,
                "pct": 100 * (final - known) / final, "rows_known": n_known, "rows_all": n_all}
json.dump(out, open("results/section5.json", "w"), indent=1, default=str)
