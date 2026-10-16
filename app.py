"""Dash dashboards.  Run one process per dashboard:

    python dashboard/app.py --mode raw       --port 8050   # dashboard "Raw"
    python dashboard/app.py --mode aggregate --port 8051   # dashboard "Aggregate"

Both use the same layout, filters (start day, end day, meter) and the same five panels.
No query-result caching is used: every refresh sends all five queries to PostgreSQL.
After each refresh every panel shows how long its query took, and the page text carries the same
numbers so that bench_dashboards.py can read them."""
import argparse
import os
import sys
import time

import pandas as pd
import plotly.express as px
from dash import Dash, Input, Output, State, dcc, html

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db            # noqa: E402
import queries as Q  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--mode", choices=["raw", "aggregate"], required=True)
ap.add_argument("--port", type=int, default=8050)
args = ap.parse_args()
MODE = args.mode
TITLE = "Raw" if MODE == "raw" else "Aggregate"

# one persistent connection per panel, reused for every refresh (same connection for all runs)
CONNS = {p: db.connect(autocommit=True) for p in Q.PANELS}
for c in CONNS.values():
    c.cursor().execute("SET timezone TO 'Africa/Kigali'")

app = Dash(__name__, title=f"{TITLE} dashboard")
app.index_string = app.index_string.replace(
    "</head>", "<style>body{font-family:Segoe UI,Arial,sans-serif;margin:12px;background:#f4f6f9}"
              ".card{background:#fff;border:1px solid #d6dbe3;border-radius:6px;padding:6px;margin:6px}"
              ".ms{font-size:12px;color:#44546a;margin:0 0 0 8px}</style></head>")


def card(pid, wide=False):
    return html.Div([
        html.Div(Q.PANELS[pid], style={"fontWeight": "600", "marginLeft": "8px"}),
        html.Div(id=f"ms-{pid}", className="ms"),
        dcc.Loading(dcc.Graph(id=f"g-{pid}", config={"displaylogo": False}), type="circle"),
    ], className="card", style={"width": "98%" if wide else "48%", "display": "inline-block",
                                "verticalAlign": "top"})


app.layout = html.Div([
    html.H2(f"{TITLE} dashboard  ({'queries energy_readings directly' if MODE == 'raw' else 'queries continuous aggregates'})"),
    html.Div([
        html.Label("Start day "), dcc.Input(id="start", value="2026-09-22", type="text", debounce=True, style={"width": 110}),
        html.Label("   End day (included) "), dcc.Input(id="end", value="2026-09-28", type="text", debounce=True, style={"width": 110}),
        html.Label("   Meter "), dcc.Input(id="meter", value="1000000000", type="text", debounce=True, style={"width": 120}),
        html.Button("Refresh", id="refresh", n_clicks=0, style={"marginLeft": 16}),
        html.Span(id="runinfo", className="ms"),
    ], className="card"),
    card(1, wide=True), card(2), card(3), card(4), card(5),
])


def make_callback(pid):
    @app.callback(Output(f"g-{pid}", "figure"), Output(f"ms-{pid}", "children"),
                  Input("refresh", "n_clicks"), Input("start", "value"), Input("end", "value"),
                  Input("meter", "value"))
    def cb(n, start, end, meter, pid=pid):
        t0 = time.perf_counter()
        rows = Q.run_panel(CONNS[pid].cursor(), MODE, pid, start, end, meter)
        ms = (time.perf_counter() - t0) * 1000
        df = pd.DataFrame(rows)
        if df.empty:
            fig = px.bar(title="no data")
        elif pid == 1:
            fig = px.line(df, x="bucket", y="energy_kwh", color="region", labels={"energy_kwh": "energy (kWh)", "bucket": "CAT hour"})
        elif pid == 2:
            fig = px.bar(df, x="bucket", y="energy_kwh", labels={"energy_kwh": "energy (kWh)", "bucket": "CAT day"})
        elif pid == 3:
            lab = [f"{pd.Timestamp(a):%d %b} - {pd.Timestamp(a) + pd.Timedelta(days=6):%d %b}" for a in df["period_start"]]
            fig = px.bar(df, x=lab, y="energy_kwh", labels={"x": "seven-day period", "energy_kwh": "energy (kWh)"})
            fig.update_xaxes(type="category")
        elif pid == 4:
            fig = px.bar(df, x="bucket", y="energy_kwh", labels={"energy_kwh": "energy (kWh)", "bucket": "CAT day"})
        else:
            fig = px.bar(df, x="region", y="completeness_pct", labels={"completeness_pct": "completeness (%)"})
            fig.update_yaxes(range=[95, 100.2])
        fig.update_layout(height=330 if pid != 1 else 360, margin=dict(l=45, r=10, t=10, b=40))
        return fig, f"query {ms:.1f} ms  |  {len(df)} rows  |  run {n}"
    return cb


for _pid in Q.PANELS:
    make_callback(_pid)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=args.port, debug=False)
