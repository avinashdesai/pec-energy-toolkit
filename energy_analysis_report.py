#!/usr/bin/env python3
"""Generate an HTML energy analysis report from a Green Button XML export."""

from __future__ import annotations

import argparse
import statistics
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable
from xml.sax.saxutils import escape

import plotly.graph_objects as go
from plotly.io import to_html
from plotly.subplots import make_subplots

from pec_rates import (
    APP_TIMEZONE,
    DEFAULT_RATE_SNAPSHOT_FILE,
    RateConfig,
    apply_rate_overrides,
    build_daily_schedule,
    cents_per_kwh_label,
    resolve_rate_state,
    title_case_period,
)


ATOM_NS = "http://www.w3.org/2005/Atom"
ESPI_NS = "http://naesb.org/espi"
NS = {"a": ATOM_NS, "espi": ESPI_NS}
KWH_UOM = "72"


@dataclass(frozen=True)
class IntervalReading:
    start_utc: datetime
    duration_seconds: int
    value_kwh: float
    cost_dollars: float | None


@dataclass
class ReportData:
    total_kwh: float
    actual_cost: float | None
    actual_avg_rate: float | None
    actual_total_with_service: float | None
    tou_energy_cost: float
    tou_cost: float
    tou_avg_rate: float
    flat_energy_cost: float
    flat_cost: float
    flat_rate: float
    service_charge: float
    period_kwh: dict[str, float]
    season_kwh: dict[str, float]
    start_local: datetime
    end_local: datetime
    hourly_usage: dict[datetime, float]
    daily_usage: dict[date, float]
    daily_tou_cost: dict[date, float]
    daily_flat_cost: dict[date, float]
    hour_of_day_avg: dict[int, float]
    weekday_usage: dict[str, float]
    rate_config: RateConfig
    source_name: str
    snapshot_saved_at: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Plotly HTML report from a Green Button XML file."
    )
    parser.add_argument("xml_file", type=Path, help="Path to the Green Button XML file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Path for the HTML report. Defaults to <xml file stem>_report.html",
    )
    parser.add_argument(
        "--timezone",
        default=APP_TIMEZONE.key,
        help=f"Timezone used for time-of-use and chart labels. Default: {APP_TIMEZONE.key}",
    )
    parser.add_argument(
        "--rate-source",
        choices=("auto", "cached"),
        default="cached",
        help="Use the local snapshot or try a live PEC fetch first. Default: cached",
    )
    parser.add_argument(
        "--snapshot-file",
        type=Path,
        default=Path(DEFAULT_RATE_SNAPSHOT_FILE),
        help=f"Local PEC snapshot JSON. Default: {DEFAULT_RATE_SNAPSHOT_FILE}",
    )
    parser.add_argument("--service-charge", type=float, default=None)
    parser.add_argument("--delivery-charge", type=float, default=None)
    parser.add_argument("--transmission-charge", type=float, default=None)
    parser.add_argument("--flat-rate", type=float, default=None)
    return parser.parse_args()


def extract_kwh_interval_readings(xml_path: Path) -> list[IntervalReading]:
    root = ET.fromstring(xml_path.read_text(encoding="utf-8"))
    readings: list[IntervalReading] = []

    for entry in root.findall("a:entry", NS):
        content = entry.find("a:content", NS)
        if content is None:
            continue
        block = content.find("espi:IntervalBlock", NS)
        if block is None:
            continue
        interval_uom = block.findtext("espi:interval/espi:uom", namespaces=NS)
        if interval_uom != KWH_UOM:
            continue
        for reading in block.findall("espi:IntervalReading", NS):
            start_text = reading.findtext("espi:timePeriod/espi:start", namespaces=NS)
            duration_text = reading.findtext("espi:timePeriod/espi:duration", namespaces=NS)
            value_text = reading.findtext("espi:value", namespaces=NS)
            multiplier_text = reading.findtext("espi:powerOfTenMultiplier", namespaces=NS)
            cost_text = reading.findtext("espi:cost", namespaces=NS)
            if not start_text or not duration_text or not value_text:
                continue
            multiplier = int(multiplier_text) if multiplier_text else 0
            raw_value = float(value_text)
            value_kwh = raw_value / (10**multiplier) if multiplier > 0 else raw_value
            readings.append(
                IntervalReading(
                    start_utc=datetime.fromtimestamp(int(start_text), tz=timezone.utc),
                    duration_seconds=int(duration_text),
                    value_kwh=value_kwh,
                    cost_dollars=float(cost_text) if cost_text else None,
                )
            )

    if not readings:
        raise SystemExit("No kWh interval readings were found in the XML file.")

    readings.sort(key=lambda item: item.start_utc)
    return readings


def analyze_usage(
    readings: Iterable[IntervalReading],
    local_tz,
    rate_config: RateConfig,
    source_name: str,
    snapshot_saved_at: str | None,
) -> ReportData:
    hourly_usage: defaultdict[datetime, float] = defaultdict(float)
    daily_usage: defaultdict[date, float] = defaultdict(float)
    daily_tou_variable_cost: defaultdict[date, float] = defaultdict(float)
    daily_flat_variable_cost: defaultdict[date, float] = defaultdict(float)
    period_kwh: defaultdict[str, float] = defaultdict(float)
    season_kwh: defaultdict[str, float] = defaultdict(float)

    total_kwh = 0.0
    tou_energy_cost = 0.0
    actual_cost = 0.0
    actual_cost_available = False

    sorted_readings = list(readings)
    for interval in sorted_readings:
        total_kwh += interval.value_kwh
        if interval.cost_dollars is not None:
            actual_cost += interval.cost_dollars
            actual_cost_available = True

        local_start = interval.start_utc.astimezone(local_tz)
        total_minutes = max(1, interval.duration_seconds // 60)
        kwh_per_minute = interval.value_kwh / total_minutes

        for minute_index in range(total_minutes):
            minute_dt = local_start + timedelta(minutes=minute_index)
            schedule_rows = build_daily_schedule(minute_dt.date(), rate_config)
            entry = next(row for row in schedule_rows if row.start_local <= minute_dt < row.end_local)
            hour_bucket = minute_dt.replace(minute=0, second=0, microsecond=0)
            day_bucket = minute_dt.date()

            hourly_usage[hour_bucket] += kwh_per_minute
            daily_usage[day_bucket] += kwh_per_minute
            daily_tou_variable_cost[day_bucket] += kwh_per_minute * entry.total_rate
            daily_flat_variable_cost[day_bucket] += kwh_per_minute * rate_config.flat_variable_rate
            tou_energy_cost += kwh_per_minute * entry.total_rate
            period_kwh[entry.period_name] += kwh_per_minute
            season_kwh[entry.season_name] += kwh_per_minute

    ordered_hourly_usage = dict(sorted(hourly_usage.items()))
    ordered_daily_usage = dict(sorted(daily_usage.items()))
    day_count = max(1, len(ordered_daily_usage))
    daily_service_charge = rate_config.service_charge / day_count

    daily_tou_cost = {
        day_bucket: daily_tou_variable_cost[day_bucket] + daily_service_charge
        for day_bucket in ordered_daily_usage
    }
    daily_flat_cost = {
        day_bucket: daily_flat_variable_cost[day_bucket] + daily_service_charge
        for day_bucket in ordered_daily_usage
    }

    flat_energy_cost = total_kwh * rate_config.flat_variable_rate
    tou_cost = tou_energy_cost + rate_config.service_charge
    flat_cost = flat_energy_cost + rate_config.service_charge

    actual_avg_rate = actual_cost / total_kwh if actual_cost_available and total_kwh else None
    actual_total_with_service = (
        actual_cost + rate_config.service_charge if actual_cost_available else None
    )
    tou_avg_rate = tou_cost / total_kwh if total_kwh else 0.0

    start_local = sorted_readings[0].start_utc.astimezone(local_tz)
    end_local = (
        sorted_readings[-1].start_utc + timedelta(seconds=sorted_readings[-1].duration_seconds)
    ).astimezone(local_tz)

    hour_of_day_values: defaultdict[int, list[float]] = defaultdict(list)
    for hour_bucket, value in ordered_hourly_usage.items():
        hour_of_day_values[hour_bucket.hour].append(value)
    hour_of_day_avg = {
        hour: statistics.mean(values) if values else 0.0
        for hour, values in sorted(hour_of_day_values.items())
    }

    weekday_totals: defaultdict[str, float] = defaultdict(float)
    for day_bucket, value in ordered_daily_usage.items():
        weekday_totals[day_bucket.strftime("%A")] += value

    weekday_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    weekday_usage = {day_name: weekday_totals.get(day_name, 0.0) for day_name in weekday_order}

    return ReportData(
        total_kwh=total_kwh,
        actual_cost=actual_cost if actual_cost_available else None,
        actual_avg_rate=actual_avg_rate,
        actual_total_with_service=actual_total_with_service,
        tou_energy_cost=tou_energy_cost,
        tou_cost=tou_cost,
        tou_avg_rate=tou_avg_rate,
        flat_energy_cost=flat_energy_cost,
        flat_cost=flat_cost,
        flat_rate=rate_config.flat_variable_rate,
        service_charge=rate_config.service_charge,
        period_kwh={
            "off_peak": period_kwh.get("off_peak", 0.0),
            "mid_peak": period_kwh.get("mid_peak", 0.0),
            "peak": period_kwh.get("peak", 0.0),
        },
        season_kwh={
            "summer": season_kwh.get("summer", 0.0),
            "shoulder": season_kwh.get("shoulder", 0.0),
            "winter": season_kwh.get("winter", 0.0),
        },
        start_local=start_local,
        end_local=end_local,
        hourly_usage=ordered_hourly_usage,
        daily_usage=ordered_daily_usage,
        daily_tou_cost=daily_tou_cost,
        daily_flat_cost=daily_flat_cost,
        hour_of_day_avg=hour_of_day_avg,
        weekday_usage=weekday_usage,
        rate_config=rate_config,
        source_name=source_name,
        snapshot_saved_at=snapshot_saved_at,
    )


def money(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"${value:,.2f}"


def kwh(value: float) -> str:
    return f"{value:,.2f} kWh"


def pct(value: float) -> str:
    return f"{value:.1f}%"


def build_hourly_usage_chart(data: ReportData) -> str:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=list(data.hourly_usage.keys()),
            y=list(data.hourly_usage.values()),
            mode="lines",
            line={"color": "#2463eb", "width": 1.6},
            fill="tozeroy",
            fillcolor="rgba(36, 99, 235, 0.14)",
            name="Hourly kWh",
        )
    )
    fig.update_layout(
        title="Hourly Energy Usage",
        xaxis_title="Hour",
        yaxis_title="kWh",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d1822",
        height=420,
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
    )
    return to_html(fig, full_html=False, include_plotlyjs=True)


def build_daily_summary_chart(data: ReportData) -> str:
    dates = list(data.daily_usage.keys())
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=dates, y=list(data.daily_usage.values()), name="Daily usage (kWh)", marker_color="#0f766e"),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=list(data.daily_tou_cost.values()),
            mode="lines+markers",
            name="Daily TOU total",
            line={"color": "#f97316", "width": 2},
        ),
        secondary_y=True,
    )
    fig.add_trace(
        go.Scatter(
            x=dates,
            y=list(data.daily_flat_cost.values()),
            mode="lines",
            name="Daily flat total",
            line={"color": "#7c3aed", "width": 2, "dash": "dash"},
        ),
        secondary_y=True,
    )
    fig.update_layout(
        title="Daily Usage and Total Cost Comparison",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d1822",
        height=430,
        margin={"l": 40, "r": 40, "t": 60, "b": 40},
        legend={"orientation": "h", "y": 1.12},
    )
    fig.update_yaxes(title_text="Daily kWh", secondary_y=False)
    fig.update_yaxes(title_text="Daily total cost ($)", secondary_y=True)
    return to_html(fig, full_html=False, include_plotlyjs=False)


def build_cost_comparison_chart(data: ReportData) -> str:
    fig = go.Figure(
        data=[
            go.Bar(
                x=["TOU Total", "Flat Total"],
                y=[data.tou_cost, data.flat_cost],
                marker_color=["#ea580c", "#7c3aed"],
                text=[money(data.tou_cost), money(data.flat_cost)],
                textposition="outside",
            )
        ]
    )
    fig.update_layout(
        title="Total Bill Comparison",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d1822",
        height=380,
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
        yaxis_title="Cost ($)",
    )
    return to_html(fig, full_html=False, include_plotlyjs=False)


def build_period_mix_chart(data: ReportData) -> str:
    labels, values = [], []
    colors = {"off_peak": "#16a34a", "mid_peak": "#f97316", "peak": "#dc2626"}
    for period_name in ("off_peak", "mid_peak", "peak"):
        value = data.period_kwh.get(period_name, 0.0)
        if value > 0:
            labels.append(title_case_period(period_name))
            values.append(value)
    if not values:
        labels = ["No Usage"]
        values = [1.0]
    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.5,
                marker={"colors": [colors.get(label.lower().replace(" ", "_"), "#64748b") for label in labels]},
                textinfo="label+percent",
            )
        ]
    )
    fig.update_layout(
        title="Usage Split Under TOU Periods",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d1822",
        height=380,
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    return to_html(fig, full_html=False, include_plotlyjs=False)


def build_weekday_chart(data: ReportData) -> str:
    fig = go.Figure(
        data=[
            go.Bar(
                x=list(data.weekday_usage.keys()),
                y=list(data.weekday_usage.values()),
                marker_color="#2563eb",
                name="Total kWh",
            )
        ]
    )
    fig.update_layout(
        title="Usage by Day of Week",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#0d1822",
        height=380,
        margin={"l": 40, "r": 20, "t": 60, "b": 40},
        yaxis_title="kWh",
    )
    return to_html(fig, full_html=False, include_plotlyjs=False)


def build_rate_schedule_html(rate_config: RateConfig) -> str:
    rows: list[str] = []
    for season_name in ("summer", "shoulder", "winter"):
        sample_month = {"summer": 6, "shoulder": 4, "winter": 1}[season_name]
        schedule = build_daily_schedule(date(2026, sample_month, 15), rate_config)
        seen: set[str] = set()
        for entry in schedule:
            if entry.period_name in seen:
                continue
            seen.add(entry.period_name)
            rows.append(
                "<tr>"
                f"<th>{escape(season_name.title())} {escape(title_case_period(entry.period_name))}</th>"
                f"<td>{escape(entry.label)}</td>"
                f"<td>{escape(cents_per_kwh_label(entry.base_rate))}</td>"
                f"<td>{escape(cents_per_kwh_label(entry.total_rate))}</td>"
                "</tr>"
            )
    return f"""
    <section class="panel">
      <h2>Current PEC TOU Schedule</h2>
      <table>
        <tr><th>Season and Period</th><th>Window</th><th>Base Rate</th><th>All-In Rate</th></tr>
        {''.join(rows)}
      </table>
    </section>
    """


def build_summary_html(data: ReportData) -> str:
    tou_savings_vs_flat = data.flat_cost - data.tou_cost
    actual_vs_tou = (
        data.actual_total_with_service - data.tou_cost
        if data.actual_total_with_service is not None
        else None
    )
    tou_energy_avg_rate = data.tou_energy_cost / data.total_kwh if data.total_kwh else 0.0
    period_text = (
        f"{data.start_local.strftime('%Y-%m-%d %I:%M %p %Z')} to "
        f"{data.end_local.strftime('%Y-%m-%d %I:%M %p %Z')}"
    )
    usage_rows = "".join(
        f"<tr><th>{escape(title_case_period(period_name))} usage</th>"
        f"<td>{escape(kwh(value))} ({escape(pct(value / data.total_kwh * 100 if data.total_kwh else 0.0))})</td></tr>"
        for period_name, value in data.period_kwh.items()
        if value > 0
    )
    season_rows = "".join(
        f"<tr><th>{escape(season_name.title())} usage</th><td>{escape(kwh(value))}</td></tr>"
        for season_name, value in data.season_kwh.items()
        if value > 0
    )
    current_cost_rows = ""
    if data.actual_cost is not None:
        current_cost_rows = f"""
        <tr><th>Current XML energy charge</th><td>{escape(money(data.actual_cost))}</td></tr>
        <tr><th>Current XML average rate</th><td>{escape(cents_per_kwh_label(data.actual_avg_rate))}</td></tr>
        <tr><th>Current XML plus service charge</th><td>{escape(money(data.actual_total_with_service))}</td></tr>
        <tr><th>Current XML total minus TOU total</th><td>{escape(money(actual_vs_tou))}</td></tr>
        """
    source_links = " | ".join(
        f'<a href="{escape(url)}" target="_blank" rel="noreferrer">{escape(url)}</a>'
        for url in data.rate_config.source_urls
    )
    snapshot_row = ""
    if data.snapshot_saved_at:
        snapshot_row = f"<tr><th>Snapshot saved at</th><td>{escape(data.snapshot_saved_at)}</td></tr>"
    return f"""
    <section class="cards">
      <div class="card">
        <div class="eyebrow">Total Usage</div>
        <div class="value">{escape(kwh(data.total_kwh))}</div>
        <div class="note">Source file: {escape(data.source_name)}</div>
      </div>
      <div class="card">
        <div class="eyebrow">TOU Total</div>
        <div class="value">{escape(money(data.tou_cost))}</div>
        <div class="note">Effective energy rate: {escape(cents_per_kwh_label(tou_energy_avg_rate))}</div>
      </div>
      <div class="card">
        <div class="eyebrow">Flat Total</div>
        <div class="value">{escape(money(data.flat_cost))}</div>
        <div class="note">Variable flat rate: {escape(cents_per_kwh_label(data.flat_rate))}</div>
      </div>
      <div class="card">
        <div class="eyebrow">TOU vs Flat</div>
        <div class="value">{escape(money(tou_savings_vs_flat))}</div>
        <div class="note">Positive means TOU is cheaper</div>
      </div>
    </section>
    <section class="panel">
      <h2>Summary</h2>
      <table>
        <tr><th>Analysis period</th><td>{escape(period_text)}</td></tr>
        <tr><th>Rate source</th><td>{escape(data.rate_config.source_label)} ({escape(data.rate_config.source_status)})</td></tr>
        <tr><th>Rate source timestamp</th><td>{escape(data.rate_config.source_timestamp)}</td></tr>
        <tr><th>Rate source note</th><td>{escape(data.rate_config.source_note)}</td></tr>
        {snapshot_row}
        <tr><th>Rate source pages</th><td>{source_links}</td></tr>
        <tr><th>Service availability charge</th><td>{escape(money(data.rate_config.service_charge))}</td></tr>
        <tr><th>Delivery charge</th><td>{escape(cents_per_kwh_label(data.rate_config.delivery_charge_per_kwh))}</td></tr>
        <tr><th>Transmission charge</th><td>{escape(cents_per_kwh_label(data.rate_config.transmission_charge_per_kwh))}</td></tr>
        <tr><th>Flat base power charge</th><td>{escape(cents_per_kwh_label(data.rate_config.flat_base_rate_per_kwh))}</td></tr>
        <tr><th>Flat total variable rate</th><td>{escape(cents_per_kwh_label(data.rate_config.flat_variable_rate))}</td></tr>
        <tr><th>TOU energy charge only</th><td>{escape(money(data.tou_energy_cost))}</td></tr>
        <tr><th>TOU effective energy rate</th><td>{escape(cents_per_kwh_label(tou_energy_avg_rate))}</td></tr>
        <tr><th>TOU effective total rate incl. fixed charge</th><td>{escape(cents_per_kwh_label(data.tou_avg_rate))}</td></tr>
        <tr><th>Flat energy charge only</th><td>{escape(money(data.flat_energy_cost))}</td></tr>
        {usage_rows}
        {season_rows}
        {current_cost_rows}
      </table>
    </section>
    """


def render_report(data: ReportData, output_path: Path) -> None:
    charts = [
        build_hourly_usage_chart(data),
        build_daily_summary_chart(data),
        build_cost_comparison_chart(data),
        build_period_mix_chart(data),
        build_weekday_chart(data),
    ]
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Energy Analysis Report</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #07131b;
      --bg-deep: #0c1822;
      --surface: rgba(12, 25, 35, 0.9);
      --surface-strong: rgba(16, 35, 49, 0.96);
      --text: #e7eff6;
      --muted: #8ca2b4;
      --border: rgba(148, 163, 184, 0.16);
      --accent: #6cb5ff;
      --shadow: 0 18px 46px rgba(0, 0, 0, 0.34);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", Avenir, "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, rgba(108, 181, 255, 0.14), transparent 20%),
        radial-gradient(circle at top right, rgba(34, 197, 94, 0.12), transparent 24%),
        linear-gradient(180deg, var(--bg-deep) 0%, var(--bg) 100%);
      color: var(--text);
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .shell {{ max-width: 1380px; margin: 0 auto; padding: 28px; }}
    .hero {{
      background: linear-gradient(135deg, rgba(16, 35, 49, 0.96) 0%, rgba(10, 22, 31, 0.96) 100%);
      border: 1px solid var(--border);
      border-radius: 24px;
      padding: 28px;
      box-shadow: var(--shadow);
      margin-bottom: 22px;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 18px;
    }}
    .card, .panel, .chart {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 20px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }}
    .card {{ padding: 20px; }}
    .panel {{ padding: 22px; margin-bottom: 22px; }}
    .eyebrow {{
      color: var(--muted);
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 12px;
    }}
    .value {{
      font-size: clamp(1.9rem, 3vw, 2.8rem);
      line-height: 1;
      letter-spacing: -0.04em;
      margin-bottom: 10px;
    }}
    .note {{ color: var(--muted); font-size: 0.95rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{
      padding: 12px 0;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
    }}
    th {{ width: 280px; color: var(--muted); font-weight: 600; }}
    .chart-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 18px;
    }}
    .chart {{ padding: 10px; overflow: hidden; }}
    .chart.wide {{ grid-column: 1 / -1; }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <h1>Energy Analysis Report</h1>
      <p>This report applies the shared PEC rate snapshot and seasonal TOU schedule to your Green Button XML usage data.</p>
    </section>
    {build_summary_html(data)}
    {build_rate_schedule_html(data.rate_config)}
    <section class="chart-grid">
      <div class="chart wide">{charts[0]}</div>
      <div class="chart wide">{charts[1]}</div>
      <div class="chart">{charts[2]}</div>
      <div class="chart">{charts[3]}</div>
      <div class="chart">{charts[4]}</div>
    </section>
    <div class="note" style="padding: 18px 4px 6px;">
      Generated at {escape(generated_at)} from {escape(data.source_name)}.
    </div>
  </div>
</body>
</html>
"""
    output_path.write_text(html, encoding="utf-8")


def main() -> int:
    args = parse_args()
    if not args.xml_file.exists():
        raise SystemExit(f"XML file not found: {args.xml_file}")
    output_path = args.output or args.xml_file.with_name(f"{args.xml_file.stem}_report.html")
    local_tz = APP_TIMEZONE if args.timezone == APP_TIMEZONE.key else __import__("zoneinfo").ZoneInfo(args.timezone)
    snapshot_state = resolve_rate_state(args.rate_source, args.snapshot_file)
    rate_config = apply_rate_overrides(
        snapshot_state.rate_config,
        service_charge=args.service_charge,
        delivery_charge=args.delivery_charge,
        transmission_charge=args.transmission_charge,
        flat_rate=args.flat_rate,
    )
    report_data = analyze_usage(
        readings=extract_kwh_interval_readings(args.xml_file),
        local_tz=local_tz,
        rate_config=rate_config,
        source_name=args.xml_file.name,
        snapshot_saved_at=snapshot_state.metadata.saved_at,
    )
    render_report(report_data, output_path)
    print(f"Report written to: {output_path}")
    print(f"Rate source: {rate_config.source_label} ({rate_config.source_status})")
    print(f"Total energy: {report_data.total_kwh:.2f} kWh")
    print(f"TOU total: {report_data.tou_cost:.2f}")
    print(f"Flat total: {report_data.flat_cost:.2f}")
    if report_data.actual_cost is not None:
        print(f"Current XML energy charge: {report_data.actual_cost:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
