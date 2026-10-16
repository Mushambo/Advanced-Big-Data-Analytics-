"""Panel queries for the Raw (7.1) and Aggregate (7.2) dashboards.

Filters: whole CAT days (start day .. end day, both included) and a selected meter.
Both dashboards use the same five panels, layout, filters and date range.

  P1 hourly regional energy       kWh
  P2 daily network energy         kWh
  P3 network energy per seven-day period beginning 1, 8, 15, 22 September   kWh
  P4 daily energy of the selected meter   kWh
  P5 completeness by region       percent  (observed / planned, planned = registered meters x days x 96)

RAW mode reads energy_readings directly (joining meters where needed).
AGGREGATE mode reads only the continuous aggregates (cagg_hour_region, cagg_15min_region,
cagg_day_meter); meters is used only for registered meter counts.
"""
from datetime import datetime, timedelta, timezone

CAT = timezone(timedelta(hours=2), "CAT")
TZ = "Africa/Kigali"
ORIGIN = "DATE '2026-09-01'"
PANELS = {
    1: "Hourly regional energy (kWh)",
    2: "Daily network energy (kWh)",
    3: "Network energy per seven-day period (kWh)",
    4: "Daily energy of selected meter (kWh)",
    5: "Completeness by region (%)",
}


def window(start_day: str, end_day: str):
    """Whole CAT days: [start 00:00, end+1 day 00:00)."""
    a = datetime.fromisoformat(start_day).replace(tzinfo=CAT)
    b = datetime.fromisoformat(end_day).replace(tzinfo=CAT) + timedelta(days=1)
    return a, b, (b - a).days


RAW = {
    1: """SELECT time_bucket('1 hour', r.event_time, 'Africa/Kigali') AS bucket, m.region AS region,
                 sum(r.energy_kwh) AS energy_kwh, count(*) AS readings
          FROM energy_readings r JOIN meters m ON m.meter_id = r.meter_id
          WHERE r.event_time >= %(t0)s AND r.event_time < %(t1)s
          GROUP BY 1, 2 ORDER BY 1, 2""",
    2: """SELECT time_bucket('1 day', event_time, 'Africa/Kigali') AS bucket, sum(energy_kwh) AS energy_kwh,
                 count(*) AS readings
          FROM energy_readings
          WHERE event_time >= %(t0)s AND event_time < %(t1)s
          GROUP BY 1 ORDER BY 1""",
    3: f"""SELECT {ORIGIN} + 7 * ((time_bucket('1 day', event_time, 'Africa/Kigali')::date - {ORIGIN}) / 7) AS period_start,
                  sum(energy_kwh) AS energy_kwh, count(*) AS readings
           FROM energy_readings
           WHERE event_time >= %(t0)s AND event_time < %(t1)s
           GROUP BY 1 ORDER BY 1""",
    4: """SELECT time_bucket('1 day', event_time, 'Africa/Kigali') AS bucket, sum(energy_kwh) AS energy_kwh,
                 count(*) AS readings
          FROM energy_readings
          WHERE meter_id = %(meter)s AND event_time >= %(t0)s AND event_time < %(t1)s
          GROUP BY 1 ORDER BY 1""",
    5: """SELECT m.region AS region, count(*) AS observed
          FROM energy_readings r JOIN meters m ON m.meter_id = r.meter_id
          WHERE r.event_time >= %(t0)s AND r.event_time < %(t1)s
          GROUP BY 1 ORDER BY 1""",
}

AGG = {
    1: """SELECT bucket, region, sum(sum_energy_kwh) AS energy_kwh, sum(reading_count) AS readings
          FROM cagg_hour_region
          WHERE bucket >= %(t0)s AND bucket < %(t1)s
          GROUP BY 1, 2 ORDER BY 1, 2""",
    2: """SELECT time_bucket('1 day', bucket, 'Africa/Kigali') AS bucket, sum(sum_energy_kwh) AS energy_kwh,
                 sum(reading_count) AS readings
          FROM cagg_15min_region
          WHERE bucket >= %(t0)s AND bucket < %(t1)s
          GROUP BY 1 ORDER BY 1""",
    3: f"""SELECT {ORIGIN} + 7 * ((time_bucket('1 day', bucket, 'Africa/Kigali')::date - {ORIGIN}) / 7) AS period_start,
                  sum(sum_energy_kwh) AS energy_kwh, sum(reading_count) AS readings
           FROM cagg_15min_region
           WHERE bucket >= %(t0)s AND bucket < %(t1)s
           GROUP BY 1 ORDER BY 1""",
    4: """SELECT bucket, sum_energy_kwh AS energy_kwh, reading_count AS readings
          FROM cagg_day_meter
          WHERE meter_id = %(meter)s AND bucket >= %(t0)s AND bucket < %(t1)s
          ORDER BY 1""",
    5: """SELECT region, sum(reading_count) AS observed
          FROM cagg_15min_region
          WHERE bucket >= %(t0)s AND bucket < %(t1)s
          GROUP BY 1 ORDER BY 1""",
}

METERS_PER_REGION = "SELECT region, count(*) AS meters FROM meters GROUP BY 1 ORDER BY 1"


def region_key(r):
    return int(r.split()[-1])


def run_panel(cur, mode, panel, start_day, end_day, meter):
    """Execute one panel query. Returns a list of dict rows (and for P5 adds completeness)."""
    t0, t1, days = window(start_day, end_day)
    sql = (RAW if mode == "raw" else AGG)[panel]
    cur.execute(sql, {"t0": t0, "t1": t1, "meter": int(meter)})
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    if panel == 5:
        cur.execute(METERS_PER_REGION)
        mcount = dict(cur.fetchall())
        for r in rows:
            planned = mcount[r["region"]] * days * 96
            r["observed"] = int(r["observed"])
            r["planned"] = planned
            r["completeness_pct"] = 100.0 * r["observed"] / planned
        rows.sort(key=lambda r: region_key(r["region"]))
    return rows
