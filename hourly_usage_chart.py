#!/usr/bin/env python3
"""Generate an hourly usage chart from a Green Button XML export."""

from __future__ import annotations

import argparse
import math
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape
from typing import Iterable

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore[assignment]

try:  # pragma: no cover
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
except ImportError:  # pragma: no cover
    plt = None
    mdates = None


ATOM_NS = "http://www.w3.org/2005/Atom"
ESPI_NS = "http://naesb.org/espi"
NS = {"a": ATOM_NS, "espi": ESPI_NS}
KWH_UOM = "72"


@dataclass
class IntervalReading:
    start_utc: datetime
    duration_seconds: int
    value_kwh: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate an hourly usage chart from Green Button XML."
    )
    parser.add_argument("xml_file", type=Path, help="Path to the Green Button XML file.")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("hourly_usage_chart.svg"),
        help="Path to save the chart image. Default: hourly_usage_chart.svg",
    )
    parser.add_argument(
        "--timezone",
        default=None,
        help=(
            "IANA timezone name for chart labels, for example America/Chicago. "
            "Defaults to the system local timezone."
        ),
    )
    parser.add_argument(
        "--title",
        default="Hourly Energy Usage",
        help="Chart title. Default: Hourly Energy Usage",
    )
    return parser.parse_args()


def determine_timezone(name: str | None) -> timezone:
    if name:
        if ZoneInfo is None:
            raise SystemExit("Timezone names require Python 3.9+ with zoneinfo support.")
        try:
            return ZoneInfo(name)
        except Exception as exc:
            raise SystemExit(f"Invalid timezone: {name}") from exc
    return datetime.now().astimezone().tzinfo or timezone.utc


def extract_kwh_interval_readings(xml_path: Path) -> list[IntervalReading]:
    root = ET.fromstring(xml_path.read_text(encoding="utf-8"))
    readings: list[IntervalReading] = []

    for entry in root.findall("a:entry", NS):
        content = entry.find("a:content", NS)
        if content is None:
            continue

        interval_block = content.find("espi:IntervalBlock", NS)
        if interval_block is None:
            continue

        interval_uom = interval_block.findtext("espi:interval/espi:uom", namespaces=NS)
        if interval_uom != KWH_UOM:
            continue

        for reading in interval_block.findall("espi:IntervalReading", NS):
            duration_text = reading.findtext(
                "espi:timePeriod/espi:duration", namespaces=NS
            )
            start_text = reading.findtext("espi:timePeriod/espi:start", namespaces=NS)
            value_text = reading.findtext("espi:value", namespaces=NS)
            multiplier_text = reading.findtext(
                "espi:powerOfTenMultiplier", namespaces=NS
            )

            if not duration_text or not start_text or not value_text:
                continue

            duration_seconds = int(duration_text)
            start_utc = datetime.fromtimestamp(int(start_text), tz=timezone.utc)

            raw_value = float(value_text)
            multiplier = int(multiplier_text) if multiplier_text else 0

            # In these Green Button exports, interval energy values are typically
            # watt-hours stored with multiplier 3, so 1830 means 1.830 kWh.
            value_kwh = raw_value / (10**multiplier) if multiplier > 0 else raw_value

            readings.append(
                IntervalReading(
                    start_utc=start_utc,
                    duration_seconds=duration_seconds,
                    value_kwh=value_kwh,
                )
            )

    if not readings:
        raise SystemExit("No kWh interval readings were found in the XML file.")

    readings.sort(key=lambda item: item.start_utc)
    return readings


def hourly_totals(
    readings: Iterable[IntervalReading], local_tz: timezone
) -> tuple[list[datetime], list[float]]:
    totals: defaultdict[datetime, float] = defaultdict(float)

    for reading in readings:
        local_start = reading.start_utc.astimezone(local_tz)
        bucket = local_start.replace(minute=0, second=0, microsecond=0)
        totals[bucket] += reading.value_kwh

    ordered_hours = sorted(totals)
    return ordered_hours, [totals[hour] for hour in ordered_hours]


def plot_hourly_usage(
    hours: list[datetime], usage_kwh: list[float], output_path: Path, title: str
) -> None:
    if plt is None or mdates is None:
        raise RuntimeError("matplotlib is unavailable")

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(hours, usage_kwh, color="#1f77b4", linewidth=1.4)
    ax.fill_between(hours, usage_kwh, color="#1f77b4", alpha=0.15)

    ax.set_title(title)
    ax.set_xlabel("Hour")
    ax.set_ylabel("Energy Usage (kWh)")
    ax.grid(True, axis="y", alpha=0.3)
    ax.margins(x=0.01)

    if len(hours) <= 72:
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d\n%H:%M"))
    else:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(ax.xaxis.get_major_locator()))

    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def write_svg_chart(
    hours: list[datetime], usage_kwh: list[float], output_path: Path, title: str
) -> None:
    width = 1400
    height = 700
    left = 90
    right = 30
    top = 60
    bottom = 90
    plot_width = width - left - right
    plot_height = height - top - bottom

    min_y = 0.0
    max_y = max(usage_kwh) if usage_kwh else 1.0
    if math.isclose(max_y, min_y):
        max_y = min_y + 1.0

    count = len(usage_kwh)
    if count == 1:
        x_positions = [left + plot_width / 2]
    else:
        step = plot_width / (count - 1)
        x_positions = [left + idx * step for idx in range(count)]

    def y_to_px(value: float) -> float:
        return top + plot_height - ((value - min_y) / (max_y - min_y) * plot_height)

    line_points = " ".join(
        f"{x:.2f},{y_to_px(y):.2f}" for x, y in zip(x_positions, usage_kwh)
    )
    area_points = (
        f"{left:.2f},{top + plot_height:.2f} "
        + line_points
        + f" {left + plot_width:.2f},{top + plot_height:.2f}"
    )

    y_ticks = 6
    y_tick_values = [min_y + (max_y - min_y) * i / y_ticks for i in range(y_ticks + 1)]
    y_grid = []
    for value in y_tick_values:
        y = y_to_px(value)
        y_grid.append(
            f'<line x1="{left}" y1="{y:.2f}" x2="{left + plot_width}" y2="{y:.2f}" '
            'stroke="#d7dde5" stroke-width="1"/>'
        )
        y_grid.append(
            f'<text x="{left - 10}" y="{y + 5:.2f}" text-anchor="end" '
            'font-size="12" fill="#425466">{:.2f}</text>'.format(value)
        )

    label_count = min(10, count)
    x_labels = []
    if label_count > 1:
        used = sorted({round(i * (count - 1) / (label_count - 1)) for i in range(label_count)})
    else:
        used = [0]
    for idx in used:
        x = x_positions[idx]
        label = hours[idx].strftime("%m-%d %H:%M")
        x_labels.append(
            f'<line x1="{x:.2f}" y1="{top + plot_height}" x2="{x:.2f}" y2="{top + plot_height + 6}" '
            'stroke="#425466" stroke-width="1"/>'
        )
        x_labels.append(
            f'<text x="{x:.2f}" y="{top + plot_height + 24}" text-anchor="end" '
            'transform="rotate(-35 {0:.2f},{1})" font-size="12" fill="#425466">{2}</text>'.format(
                x, top + plot_height + 24, escape(label)
            )
        )

    total_kwh = sum(usage_kwh)
    subtitle = (
        f"{hours[0].strftime('%Y-%m-%d %H:%M')} to "
        f"{(hours[-1] + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M')} | "
        f"Total: {total_kwh:.2f} kWh"
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
  <rect width="100%" height="100%" fill="#ffffff"/>
  <text x="{left}" y="30" font-size="26" font-family="Arial, sans-serif" font-weight="700" fill="#16202a">{escape(title)}</text>
  <text x="{left}" y="52" font-size="13" font-family="Arial, sans-serif" fill="#425466">{escape(subtitle)}</text>
  <line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#425466" stroke-width="1.5"/>
  <line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#425466" stroke-width="1.5"/>
  {''.join(y_grid)}
  {''.join(x_labels)}
  <polygon points="{area_points}" fill="#4c78a8" opacity="0.18"/>
  <polyline points="{line_points}" fill="none" stroke="#2c5d8a" stroke-width="2"/>
  <text x="24" y="{top + plot_height / 2:.2f}" transform="rotate(-90 24,{top + plot_height / 2:.2f})" font-size="14" font-family="Arial, sans-serif" fill="#16202a">Energy Usage (kWh)</text>
  <text x="{left + plot_width / 2:.2f}" y="{height - 15}" text-anchor="middle" font-size="14" font-family="Arial, sans-serif" fill="#16202a">Hour</text>
</svg>
"""
    output_path.write_text(svg, encoding="utf-8")


def main() -> int:
    args = parse_args()
    local_tz = determine_timezone(args.timezone)
    readings = extract_kwh_interval_readings(args.xml_file)
    hours, usage_kwh = hourly_totals(readings, local_tz)

    if not hours:
        raise SystemExit("No hourly totals could be calculated.")

    output_suffix = args.output.suffix.lower()
    if output_suffix == ".svg":
        write_svg_chart(hours, usage_kwh, args.output, args.title)
    else:
        if plt is None or mdates is None:
            raise SystemExit(
                "Non-SVG output requires matplotlib. Install it with: "
                "python3 -m pip install matplotlib"
            )
        plot_hourly_usage(hours, usage_kwh, args.output, args.title)

    total_kwh = sum(usage_kwh)
    print(f"Chart written to: {args.output}")
    print(f"Hourly points: {len(hours)}")
    print(f"Total energy: {total_kwh:.2f} kWh")
    print(f"Time range: {hours[0].isoformat()} to {(hours[-1] + timedelta(hours=1)).isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
