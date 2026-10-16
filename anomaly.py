"""Section 5.4  Abnormal consumption.

RULE (applied to cleaned readings BEFORE the labels are used)
  For every meter, the expected power for a reading is the MEDIAN power of that same meter
  at the same time of day on the same kind of day (weekday or weekend) over the 28 days.
  ratio = power_kw / expected.
  Flag a reading when ratio >= SPIKE (demand spike) or ratio <= DROP (unusual drop).

WHY THESE THRESHOLDS
  Normal readings vary by about +-15% (random noise) plus a +0.3 %/day trend, so the
  natural ratio stays roughly between 0.65 and 1.45.  SPIKE = 2.0 and DROP = 0.25 sit well
  outside that band.  The median is robust: a 3-hour event moves at most one value of the
  20 weekday (or 8 weekend) samples that define the expectation.

The labels from anomaly_events() are used only afterwards, for evaluation.
"""
import io
import json

import numpy as np
import pandas as pd

import db
import smart_meter_simulator as sim

SPIKE, DROP = 2.0, 0.25
START_EPOCH = 1788213600          # 2026-09-01 00:00 +02:00  (= 2026-08-31 22:00 UTC)

conn = db.connect(autocommit=True)
cur = conn.cursor()
buf = io.StringIO()
cur.copy_expert("""COPY (SELECT meter_id, extract(epoch FROM event_time)::bigint AS e, power_kw
                          FROM energy_readings) TO STDOUT WITH CSV""", buf)
buf.seek(0)
df = pd.read_csv(buf, names=["meter_id", "e", "power_kw"], dtype={"meter_id": "int64", "e": "int64",
                                                                 "power_kw": "float64"})
n_obs = len(df)
slot = (df["e"] - START_EPOCH) // 900
day = slot // 96
df["tod"] = (slot % 96).astype("int16")
df["weekend"] = (((day + 1) % 7) >= 5).astype("int8")    # 1 September 2026 is a Tuesday
df["meter_id"] = df["meter_id"].astype("int32")
print(f"{n_obs:,} cleaned readings loaded")

df["expected"] = df.groupby(["meter_id", "tod", "weekend"])["power_kw"].transform("median")
df["ratio"] = df["power_kw"] / df["expected"]
print("ratio percentiles  0.1%, 1%, 50%, 99%, 99.9%:",
      np.round(df["ratio"].quantile([0.001, 0.01, 0.5, 0.99, 0.999]).values, 3))


def evaluate(spike, drop, verbose=False):
    flagged = df[(df["ratio"] >= spike) | (df["ratio"] <= drop)][["meter_id", "e", "power_kw", "expected", "ratio"]]
    ev = pd.DataFrame(sim.anomaly_events())
    # epoch seconds, independent of the pandas datetime resolution (pandas 3 no longer defaults to ns)
    ev["s"] = ev["start_time"].map(lambda x: int(pd.Timestamp(x).timestamp()))
    ev["t"] = ev["end_time"].map(lambda x: int(pd.Timestamp(x).timestamp()))
    ev = ev.rename(columns={"meter_id": "mid"})
    detected = []
    merged = flagged.merge(ev[["mid", "s", "t", "event_type"]], left_on="meter_id", right_on="mid", how="left")
    inside = (merged["e"] >= merged["s"]) & (merged["e"] < merged["t"])
    hit = merged[inside]
    det_keys = set(zip(hit["mid"], hit["s"]))
    for r in ev.itertuples():
        detected.append((r.mid, r.s) in det_keys)
    ev["detected"] = detected
    # a flagged reading is "inside" when it falls in ANY interval of its meter
    in_any = merged.assign(inside=inside).groupby(["meter_id", "e"])["inside"].any().reset_index()
    false_flags = in_any[~in_any["inside"]]
    # observed readings outside every injected interval
    ev_by_meter = ev.groupby("mid")
    inside_count = 0
    for mid, g in ev_by_meter:
        m = (df["meter_id"] == mid)
        e = df.loc[m, "e"]
        msk = np.zeros(len(e), dtype=bool)
        for r in g.itertuples():
            msk |= ((e >= r.s) & (e < r.t)).values
        inside_count += int(msk.sum())
    outside = n_obs - inside_count
    res = {"spike": spike, "drop": drop, "flags": int(len(flagged)),
           "detected": int(ev["detected"].sum()), "missed": int((~ev["detected"]).sum()),
           "false_flags": int(len(false_flags)), "outside_readings": int(outside),
           "false_flag_pct": 100.0 * len(false_flags) / outside,
           "meters_with_false_flag": int(false_flags["meter_id"].nunique()),
           "pct_meters_affected": 100.0 * false_flags["meter_id"].nunique() / 4000}
    if verbose:
        return res, flagged, ev, false_flags
    return res


main, flagged, ev, false_flags = evaluate(SPIKE, DROP, verbose=True)
print("\nMAIN RESULT", json.dumps(main, indent=1))
print("\nEVENT TABLE (first 10)")
print(ev[["mid", "start_time", "end_time", "event_type", "detected"]].head(10).to_string(index=False))
missed = ev[~ev["detected"]]
print("\nMISSED EVENTS:", len(missed))
if len(missed):
    print(missed[["mid", "start_time", "end_time", "event_type"]].to_string(index=False))

sample = flagged.sort_values(["meter_id", "e"]).head(15).copy()
sample["event_time_cat"] = pd.to_datetime(sample["e"], unit="s", utc=True).dt.tz_convert("Africa/Kigali").astype(str)
print("\nSAMPLE OF FLAGGED READINGS (meter_id, event_time, power_kw, expected, ratio)")
print(sample[["meter_id", "event_time_cat", "power_kw", "expected", "ratio"]].round(3).to_string(index=False))

fp = false_flags.head(10).copy()
if len(fp):
    fp["event_time_cat"] = pd.to_datetime(fp["e"], unit="s", utc=True).dt.tz_convert("Africa/Kigali").astype(str)
    print("\nSAMPLE FALSE FLAGS\n", fp.to_string(index=False))

sens = []
for sp, dr in [(1.1, 0.9), (1.2, 0.8), (1.3, 0.75), (1.4, 0.7), (1.5, 0.5), (1.7, 0.4), (2.0, 0.25), (2.5, 0.1)]:
    r = evaluate(sp, dr)
    sens.append(r)
    print(f"thresholds spike>={sp} drop<={dr}: flags={r['flags']:,} detected={r['detected']}/40 "
          f"false={r['false_flags']:,} ({r['false_flag_pct']:.4f}%) meters_affected={r['pct_meters_affected']:.2f}%")

types = ev.groupby("event_type")["detected"].agg(["sum", "count"]).reset_index().to_dict("records")
json.dump({"main": main, "sensitivity": sens, "by_type": types,
           "sample_flags": sample[["meter_id", "event_time_cat", "power_kw", "expected", "ratio"]].round(3).to_dict("records"),
           "events": ev[["mid", "start_time", "end_time", "event_type", "detected"]].to_dict("records"),
           "ratio_quantiles": df["ratio"].quantile([0.001, 0.01, 0.5, 0.99, 0.999]).round(3).to_dict()},
          open("results/anomaly.json", "w"), indent=1, default=str)
