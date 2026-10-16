"""Section 8  Forecast hourly regional consumption (kWh) for the next day.

8.1  analysis dataset (one row per region and CAT hour), chronological split, lag features
8.2  previous-day baseline
8.3  one regression model (Ridge), several configurations, validation, frozen model, test predictions
8.4  baseline versus model: overall and per region, peak hours, plot

Forecast origin = 00:00 CAT at the start of the target day.  Every predictor is observed
before that origin.  Prediction error = predicted - actual (kWh).
Run:  python s8_forecast.py
"""
import json
import os

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

import db

TZ = "Africa/Kigali"
os.makedirs("results/charts", exist_ok=True)
pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)

# ------------------------------------------------------------------ 8.1 dataset
conn = db.connect(autocommit=True)
cur = conn.cursor()
cur.execute("SET timezone TO 'Africa/Kigali'")
cur.execute("""SELECT m.region, time_bucket('1 hour', r.event_time, 'Africa/Kigali') AS hour,
                      sum(r.energy_kwh), count(*)
               FROM energy_readings r JOIN meters m ON m.meter_id = r.meter_id
               GROUP BY 1, 2""")
obs = pd.DataFrame(cur.fetchall(), columns=["region", "hour", "kwh", "n_readings"])
obs["hour"] = pd.to_datetime(obs["hour"], utc=True).dt.tz_convert(TZ)
cur.execute("SELECT region, count(*) FROM meters GROUP BY 1")
registered = dict(cur.fetchall())

regions = sorted(registered, key=lambda r: int(r.split()[-1]))
grid = pd.MultiIndex.from_product(
    [regions, pd.date_range("2026-09-01 00:00", "2026-09-28 23:00", freq="h", tz=TZ)],
    names=["region", "hour"])
df = obs.set_index(["region", "hour"]).reindex(grid).reset_index()
absent = int(df["kwh"].isna().sum())
planned_per_hour = {r: registered[r] * 4 for r in regions}
df["planned_readings"] = df["region"].map(planned_per_hour)
df["n_readings"] = df["n_readings"].fillna(0).astype(int)
print("=== 8.1 DATASET")
print(f"rows (region x CAT hour): {len(df):,}  = {len(regions)} regions x {len(df)//len(regions)} hours")
print(f"absent region-hours (no readings at all): {absent}")
print("reading count per region-hour: min {} / median {:.0f} / max {}   (planned 1,600 = 400 meters x 4)".format(
    df.n_readings.min(), df.n_readings.median(), df.n_readings.max()))
print(f"observed share of planned readings: {100 * df.n_readings.sum() / df.planned_readings.sum():.3f}%")
print("Targets are the OBSERVED hourly totals; missing readings are NOT filled or zeroed.")

# lag features (hours): previous day, two days back, same hour last week, mean of previous full day
df = df.sort_values(["region", "hour"]).reset_index(drop=True)
g = df.groupby("region")["kwh"]
df["lag_24h"] = g.shift(24)
df["lag_48h"] = g.shift(48)
df["lag_168h"] = g.shift(168)
# mean of the 24 hours of the previous CAT day (all observed before the 00:00 origin)
df["date"] = df["hour"].dt.normalize()
daily_mean = df.groupby(["region", "date"])["kwh"].mean().rename("day_mean").reset_index()
daily_mean["date"] = daily_mean["date"] + pd.Timedelta(days=1)          # available the NEXT day
df = df.merge(daily_mean, on=["region", "date"], how="left").rename(columns={"day_mean": "prev_day_mean_24h"})
df["hour_of_day"] = df["hour"].dt.hour
df["is_weekend"] = (df["hour"].dt.dayofweek >= 5).astype(int)
df["origin"] = df["date"]                                               # 00:00 CAT of the target day
# source timestamps (for the leakage check)
df["src_lag_24h"] = df["hour"] - pd.Timedelta(hours=24)
df["src_lag_48h"] = df["hour"] - pd.Timedelta(hours=48)
df["src_lag_168h"] = df["hour"] - pd.Timedelta(hours=168)
df["src_prev_day_last"] = df["origin"] - pd.Timedelta(hours=1)          # last hour of the window

SPLITS = {"train": ("2026-09-01", "2026-09-15"), "validation": ("2026-09-15", "2026-09-22"),
          "test": ("2026-09-22", "2026-09-29")}
df["split"] = None
for name, (a, b) in SPLITS.items():
    m = (df["hour"] >= pd.Timestamp(a, tz=TZ)) & (df["hour"] < pd.Timestamp(b, tz=TZ))
    df.loc[m, "split"] = name
print("\n=== 8.1 SPLITS (by target timestamp)")
for name in SPLITS:
    s = df[df.split == name]
    print(f"{name:11s} rows={len(s):5d}  first target={s.hour.min():%Y-%m-%d %H:%M}  last target={s.hour.max():%Y-%m-%d %H:%M}")

FEATURES = [
    ("lag_24h", 24, "2026-09-02 00:00"),
    ("lag_48h", 48, "2026-09-03 00:00"),
    ("lag_168h", 168, "2026-09-08 00:00"),
    ("prev_day_mean_24h", 24, "2026-09-02 00:00"),
    ("hour_of_day", 0, "2026-09-01 00:00"),
    ("is_weekend", 0, "2026-09-01 00:00"),
    ("region", 0, "2026-09-01 00:00"),
]
LOOKBACK = 168
earliest = pd.Timestamp("2026-09-01", tz=TZ) + pd.Timedelta(hours=LOOKBACK)
print("\n=== 8.1 FEATURES (name, lag/window length in hours, earliest usable target)")
for n, w, e in FEATURES:
    print(f"  {n:20s} {w:4d} h   {e}")
print(f"  chosen initial lookback = {LOOKBACK} h  ->  earliest usable target = {earliest:%Y-%m-%d %H:%M}")

train_all = df[df.split == "train"]
train_use = train_all[train_all["hour"] >= earliest]
print(f"\ntraining rows before lookback exclusions: {len(train_all):,}")
print(f"excluded (lack the {LOOKBACK} h lookback): {len(train_all) - len(train_use):,}")
print(f"retained training rows: {len(train_use):,}   (same rows for every model configuration)")
val = df[df.split == "validation"]
test = df[df.split == "test"]
print(f"validation rows {len(val):,}  test rows {len(test):,}")

NUM = ["lag_24h", "lag_48h", "lag_168h", "prev_day_mean_24h", "is_weekend"]
CAT_ = ["region", "hour_of_day"]
X_COLS = NUM + CAT_

# ---- leakage check: every lag source precedes its forecast origin
chk = df[df["hour"] >= earliest]
for c in ["src_lag_24h", "src_lag_48h", "src_lag_168h", "src_prev_day_last"]:
    assert (chk[c] < chk["origin"]).all(), f"{c} is not before the forecast origin"
print("\nLEAKAGE CHECK: for all {:,} usable rows lag_24h, lag_48h, lag_168h and the previous-day window "
      "end strictly before the 00:00 forecast origin -> PASSED".format(len(chk)))
ex = chk[chk.region == "Region 1"].iloc[[0, 30, 400]]
print("example rows (Region 1): target / origin / source of lag_24h / source of lag_168h")
for r in ex.itertuples():
    print(f"  {r.hour:%m-%d %H:%M} | origin {r.origin:%m-%d %H:%M} | lag_24h from {r.src_lag_24h:%m-%d %H:%M} "
          f"| lag_168h from {r.src_lag_168h:%m-%d %H:%M}")
print("missing predictor values in usable rows:", int(chk[NUM].isna().sum().sum()))
print("\nfeature sample (Region 1, first usable rows)")
print(chk[chk.region == "Region 1"][["hour", "kwh"] + X_COLS].head(5).to_string(index=False, float_format=lambda v: f"{v:.2f}"))

# ------------------------------------------------------------------ 8.2 baseline
def metrics(y, p):
    e = np.asarray(p) - np.asarray(y)                         # predicted - actual
    return float(np.mean(np.abs(e))), float(np.sqrt(np.mean(e ** 2)))


test = test.copy()
test["baseline"] = test["lag_24h"]
assert test["baseline"].notna().all()
b_mae, b_rmse = metrics(test.kwh, test.baseline)
print("\n=== 8.2 BASELINE (previous day's corresponding hour)")
print(f"predictions: {len(test):,}  (10 regions x 7 days x 24 hours)")
print(f"MAE = {b_mae:.3f} kWh   RMSE = {b_rmse:.3f} kWh   (mean actual = {test.kwh.mean():.1f} kWh)")
print(test[["region", "hour", "kwh", "baseline"]].head(5).to_string(index=False, float_format=lambda v: f"{v:.2f}"))

# ------------------------------------------------------------------ 8.3 model
def make_pipe(alpha):
    pre = ColumnTransformer([
        ("num", Pipeline([("imp", SimpleImputer(strategy="median")), ("sc", StandardScaler())]), NUM),
        ("cat", OneHotEncoder(categories=[regions, list(range(24))], handle_unknown="ignore"), CAT_),
    ])
    return Pipeline([("pre", pre), ("reg", Ridge(alpha=alpha))])


CONFIGS = {"R1": 0.01, "R2": 0.1, "R3": 1.0, "R4": 10.0, "R5": 100.0}
rows = []
fitted = {}
for cid, alpha in CONFIGS.items():
    pipe = make_pipe(alpha).fit(train_use[X_COLS], train_use["kwh"])
    pv = pipe.predict(val[X_COLS])
    mae, rmse = metrics(val.kwh, pv)
    fitted[cid] = pipe
    rows.append({"config": cid, "model": "Ridge", "alpha": alpha, "scaling": "StandardScaler (train only)",
                 "train_rows": len(train_use), "val_rows": len(val), "val_MAE": mae, "val_RMSE": rmse})
vt = pd.DataFrame(rows)
vb_mae, vb_rmse = metrics(val.kwh, val.lag_24h)
print("\n=== 8.3 VALIDATION (shared predictors: " + ", ".join(X_COLS) + ")")
print(vt.round(3).to_string(index=False))
print(f"(previous-day baseline on validation: MAE {vb_mae:.3f}  RMSE {vb_rmse:.3f})")
best = vt.sort_values("val_MAE").iloc[0]
cid = best["config"]
frozen = fitted[cid]
joblib.dump(frozen, "results/frozen_model.joblib")
print(f"\nSELECTED {cid}: Ridge alpha={best['alpha']}  validation MAE={best['val_MAE']:.3f} kWh "
      f"-> model and preprocessing frozen (results/frozen_model.joblib); never refitted on test days")

test["model"] = frozen.predict(test[X_COLS])
assert len(test) == 1680 and test["model"].notna().all()
m_mae, m_rmse = metrics(test.kwh, test.model)
print(f"\ntest predictions: {len(test):,}")
print(test[["region", "hour", "kwh", "baseline", "model"]].head(8).to_string(index=False, float_format=lambda v: f"{v:.2f}"))

# ------------------------------------------------------------------ 8.4 judge
print("\n=== 8.4 OVERALL (1,680 test observations)")
print(f"baseline  MAE {b_mae:8.3f} kWh   RMSE {b_rmse:8.3f} kWh")
print(f"model     MAE {m_mae:8.3f} kWh   RMSE {m_rmse:8.3f} kWh")
print(f"MAE change {100 * (b_mae - m_mae) / b_mae:+.1f}%   RMSE change {100 * (b_rmse - m_rmse) / b_rmse:+.1f}%")
per = []
for r in regions:
    s = test[test.region == r]
    bm, br = metrics(s.kwh, s.baseline)
    mm, mr = metrics(s.kwh, s.model)
    per.append({"region": r, "mean_actual_kwh": s.kwh.mean(), "baseline_MAE": bm, "model_MAE": mm,
                "baseline_RMSE": br, "model_RMSE": mr})
per = pd.DataFrame(per)
print("\nPER REGION (kWh)")
print(per.round(2).to_string(index=False))

peaks = []
for r in regions:
    s = test[test.region == r].sort_values(["kwh", "hour"], ascending=[False, True]).iloc[0]
    peaks.append({"region": r, "peak_hour": f"{s.hour:%Y-%m-%d %H:%M}", "actual": s.kwh,
                  "baseline_pred": s.baseline, "baseline_abs_err": abs(s.baseline - s.kwh),
                  "model_pred": s.model, "model_abs_err": abs(s.model - s.kwh)})
peaks = pd.DataFrame(peaks)
print("\nPEAK ACTUAL TEST HOUR PER REGION")
print(peaks.round(2).to_string(index=False))
print(f"mean abs error at peak hours: baseline {peaks.baseline_abs_err.mean():.2f}  model {peaks.model_abs_err.mean():.2f} kWh")

daily_err = test.assign(day=test.hour.dt.date, be=(test.baseline - test.kwh).abs(),
                        me=(test.model - test.kwh).abs()).groupby("day")[["be", "me"]].mean()
print("\nMAE BY TEST DAY (kWh)")
print(daily_err.round(2).to_string())

PLOT_REGION = "Region 1"
s = test[test.region == PLOT_REGION]
fig, ax = plt.subplots(figsize=(13, 4.2))
ax.plot(s.hour, s.kwh, color="black", lw=2, label="Actual")
ax.plot(s.hour, s.baseline, color="#c0504d", lw=1.2, ls="--", label="Baseline (previous day)")
ax.plot(s.hour, s.model, color="#2f5f98", lw=1.5, label=f"Model (Ridge {cid})")
ax.set_ylabel("Energy per hour (kWh)")
ax.set_title(f"{PLOT_REGION}: hourly consumption, 22-28 September 2026 (test week)")
ax.legend(ncol=3)
fig.autofmt_xdate()
fig.tight_layout()
fig.savefig("results/charts/8_4_forecast_region1.png", dpi=150)
plt.close(fig)

fig, ax = plt.subplots(figsize=(8, 3.8))
xx = np.arange(len(regions))
ax.bar(xx - 0.2, per.baseline_MAE, 0.4, label="Baseline", color="#c0504d")
ax.bar(xx + 0.2, per.model_MAE, 0.4, label="Model", color="#2f5f98")
ax.set_xticks(xx)
ax.set_xticklabels([r.replace("Region ", "R") for r in regions])
ax.set_ylabel("MAE (kWh)")
ax.set_title("Test MAE by region")
ax.legend()
fig.tight_layout()
fig.savefig("results/charts/8_4_mae_by_region.png", dpi=150)
plt.close(fig)

test[["region", "hour", "kwh", "baseline", "model"]].to_csv("results/forecast_predictions.csv", index=False)
json.dump({
    "dataset": {"rows": len(df), "absent_region_hours": absent,
                "reading_count": {"min": int(df.n_readings.min()), "median": float(df.n_readings.median()),
                                  "max": int(df.n_readings.max())},
                "observed_share_pct": float(100 * df.n_readings.sum() / df.planned_readings.sum())},
    "splits": {k: {"rows": int((df.split == k).sum()),
                   "first": str(df[df.split == k].hour.min()), "last": str(df[df.split == k].hour.max())}
               for k in SPLITS},
    "training": {"before": len(train_all), "excluded": len(train_all) - len(train_use), "retained": len(train_use),
                 "lookback_h": LOOKBACK, "earliest_target": str(earliest)},
    "features": [{"name": n, "lag_or_window_h": w, "earliest_target": e} for n, w, e in FEATURES],
    "validation": vt.to_dict("records"), "validation_baseline": {"MAE": vb_mae, "RMSE": vb_rmse},
    "selected": {"config": cid, "alpha": float(best["alpha"]), "val_MAE": float(best["val_MAE"])},
    "test": {"n": len(test), "baseline": {"MAE": b_mae, "RMSE": b_rmse}, "model": {"MAE": m_mae, "RMSE": m_rmse},
             "mean_actual": float(test.kwh.mean())},
    "per_region": per.to_dict("records"), "peaks": peaks.to_dict("records"),
    "by_day": [{"day": str(k), "baseline": float(v.be), "model": float(v.me)} for k, v in daily_err.iterrows()],
}, open("results/forecast.json", "w"), indent=1, default=str)
print("\nsaved results/forecast.json, results/forecast_predictions.csv, results/charts/8_4_*.png")
