"""7.3 Verify matching results, 7.4 Measure dashboard performance.

  python bench_dashboards.py verify     # 7.3  numerical comparison of the five panels, Raw vs Aggregate
  python bench_dashboards.py time       # 7.4  1 warm-up + 10 measured refreshes per dashboard

Period used for both: 00:00 22 September through 00:00 29 September 2026 (exclusive), all regions,
meter 1000000000.

7.4 method
  * Both dashboards (dashboard/app.py --mode raw | aggregate) run as separate local processes.
  * A headless Chromium browser (Playwright) opens one dashboard at a time; the same browser, the same
    machine and one persistent PostgreSQL connection per panel are used for every refresh.
  * Dash does no result caching; the app sends all five queries to PostgreSQL on every refresh.
  * Per-panel query duration = time.perf_counter() around the panel query inside the app (shown on the page).
  * Whole-dashboard time = performance.now() in the page from the click on "Refresh" until the text of all
    five panels carries the new run number (all five responses applied) plus two animation frames.
  * Refresh policies, compression policies and other background jobs are paused during timing and resumed after.
"""
import csv
import json
import os
import re
import socket
import statistics
import subprocess
import sys
import time
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard"))
import db            # noqa: E402
import queries as Q  # noqa: E402

START, END, METER = "2026-09-22", "2026-09-28", "1000000000"
os.makedirs("results/dashboard_export", exist_ok=True)


# ------------------------------------------------------------------------------ 7.3
def fetch(mode, panel, cur):
    return Q.run_panel(cur, mode, panel, START, END, METER)


def key_of(panel, r):
    if panel == 1:
        return (str(r["bucket"]), r["region"])
    if panel in (2, 4):
        return (str(r["bucket"]),)
    if panel == 3:
        return (str(r["period_start"]),)
    return (r["region"],)


def verify():
    conn = db.connect(autocommit=True)
    cur = conn.cursor()
    cur.execute("SET timezone TO 'Africa/Kigali'")
    report = []
    for p, name in Q.PANELS.items():
        raw, agg = fetch("raw", p, cur), fetch("aggregate", p, cur)
        for mode, rows in (("raw", raw), ("aggregate", agg)):
            with open(f"results/dashboard_export/panel{p}_{mode}.csv", "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        kr = {key_of(p, r): r for r in raw}
        ka = {key_of(p, r): r for r in agg}
        same_keys = set(kr) == set(ka)
        max_e = max_c = max_pct = 0.0
        for k in set(kr) & set(ka):
            a, b = kr[k], ka[k]
            if "energy_kwh" in a:
                max_e = max(max_e, abs(float(a["energy_kwh"]) - float(b["energy_kwh"])))
            cnt = "observed" if p == 5 else "readings"
            max_c = max(max_c, abs(int(a[cnt]) - int(b[cnt])))
            if p == 5:
                max_pct = max(max_pct, abs(a["completeness_pct"] - b["completeness_pct"]))
        ok = same_keys and max_c == 0 and max_e <= 0.001 and max_pct <= 1e-6
        report.append({"panel": p, "name": name, "rows_compared": len(kr), "identical_keys": same_keys,
                       "max_abs_energy_diff_kwh": max_e, "max_abs_count_diff": max_c,
                       "max_abs_completeness_diff_pp": max_pct, "pass": ok})
    print(f"Period {START} 00:00 .. {END} 24:00 CAT, all regions, meter {METER}\n")
    print(f"{'Panel':<44}{'rows':>6}  {'keys':>5}  {'max |dE| kWh':>14}  {'max |dN|':>9}  {'max |dC| pp':>12}  result")
    for r in report:
        print(f"P{r['panel']} {r['name']:<41}{r['rows_compared']:>6}  {str(r['identical_keys']):>5}  "
              f"{r['max_abs_energy_diff_kwh']:>14.3e}  {r['max_abs_count_diff']:>9}  "
              f"{r['max_abs_completeness_diff_pp']:>12.3e}  {'PASS' if r['pass'] else 'FAIL'}")
    json.dump(report, open("results/dashboard_verify.json", "w"), indent=1)
    print("\nALL PANELS MATCH:", all(r["pass"] for r in report))
    return all(r["pass"] for r in report)


# ------------------------------------------------------------------------------ 7.4
def wait_http(port, timeout=60):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2)
            return
        except Exception:                    # noqa: BLE001
            time.sleep(0.5)
    raise RuntimeError(f"dashboard on port {port} did not start")


JS_REFRESH = """async (n) => {
  const t0 = performance.now();
  document.getElementById('refresh').click();
  await new Promise(res => {
    const check = () => {
      const ok = [1,2,3,4,5].every(p => {
        const el = document.getElementById('ms-' + p);
        return el && el.textContent.includes('run ' + n);
      });
      if (ok) res(); else requestAnimationFrame(check);
    };
    check();
  });
  await new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
  const out = {total: performance.now() - t0};
  for (const p of [1,2,3,4,5]) out['p' + p] = document.getElementById('ms-' + p).textContent;
  return out;
}"""


def timing():
    from playwright.sync_api import sync_playwright
    conn = db.connect(autocommit=True)
    cur = conn.cursor()
    cur.execute("""SELECT job_id FROM timescaledb_information.jobs
                   WHERE proc_name LIKE 'policy_%' AND scheduled""")
    paused = [r[0] for r in cur.fetchall()]
    for j in paused:
        cur.execute("SELECT alter_job(%s, scheduled => false)", (j,))
    print("paused background jobs:", paused)
    runs = []
    py = sys.executable
    try:
        for mode, port in (("raw", 8050), ("aggregate", 8051)):
            proc = subprocess.Popen([py, "dashboard/app.py", "--mode", mode, "--port", str(port)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                wait_http(port)
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    ctx = browser.new_context(viewport={"width": 1500, "height": 1400}, bypass_csp=False)
                    page = ctx.new_page()
                    page.goto(f"http://127.0.0.1:{port}/")
                    page.wait_for_function(
                        "[1,2,3,4,5].every(p => document.getElementById('ms-'+p) && "
                        "document.getElementById('ms-'+p).textContent.includes('query'))", timeout=60000)
                    for n in range(1, 12):                 # n = 1 is the warm-up
                        res = page.evaluate(JS_REFRESH, n)
                        panel_ms = [float(re.search(r"query ([\d.]+) ms", res[f"p{p}"]).group(1)) for p in range(1, 6)]
                        runs.append({"mode": mode, "run": n, "kind": "warmup" if n == 1 else "measured",
                                     "total_ms": res["total"], **{f"p{p}_ms": panel_ms[p - 1] for p in range(1, 6)}})
                        print(f"{mode:9s} run {n:2d} {'warm-up' if n == 1 else 'measured':8s} "
                              f"dashboard {res['total']:8.1f} ms   panels " + " ".join(f"{x:7.1f}" for x in panel_ms), flush=True)
                    if mode == "raw":
                        page.screenshot(path="results/dashboard_raw.png", full_page=True)
                    else:
                        page.screenshot(path="results/dashboard_aggregate.png", full_page=True)
                    browser.close()
            finally:
                proc.terminate()
                proc.wait(timeout=15)
    finally:
        for j in paused:
            cur.execute("SELECT alter_job(%s, scheduled => true)", (j,))
        print("resumed background jobs:", paused)

    with open("results/dashboard_timing_runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(runs[0].keys()))
        w.writeheader()
        w.writerows(runs)
    summary = {}
    for mode in ("raw", "aggregate"):
        m = [r for r in runs if r["mode"] == mode and r["kind"] == "measured"]
        summary[mode] = {}
        for col in ["p1_ms", "p2_ms", "p3_ms", "p4_ms", "p5_ms", "total_ms"]:
            v = [r[col] for r in m]
            summary[mode][col] = {"median": statistics.median(v), "min": min(v), "max": max(v)}
    json.dump(summary, open("results/dashboard_timing.json", "w"), indent=1)
    print("\nmedian / min / max (ms) over 10 measured refreshes")
    print(f"{'':<22}{'Raw':>30}{'Aggregate':>34}{'speed-up':>10}")
    labels = {"p1_ms": "P1 hourly regional", "p2_ms": "P2 daily network", "p3_ms": "P3 seven-day periods",
              "p4_ms": "P4 selected meter", "p5_ms": "P5 completeness", "total_ms": "WHOLE DASHBOARD"}
    for col, lab in labels.items():
        a, b = summary["raw"][col], summary["aggregate"][col]
        print(f"{lab:<22}{a['median']:>10.1f}{a['min']:>9.1f}{a['max']:>9.1f}"
              f"{b['median']:>12.1f}{b['min']:>9.1f}{b['max']:>9.1f}{a['median'] / b['median']:>9.1f}x")
    try:
        cg = json.load(open("results/cagg_refresh.json"))
        tot = sum(c["total_bytes"] for c in cg)
        print(f"\nAggregate storage (6.1): {tot / 1e6:.1f} MB in total; initial refresh "
              f"{sum(c['refresh_s'] for c in cg):.1f} s for the three views")
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("verify", "time"):
        sys.exit(__doc__)
    if sys.argv[1] == "verify":
        sys.exit(0 if verify() else 1)
    timing()
