#!/usr/bin/env python3
"""Local PEC rate dashboard server with snapshot refresh scheduling."""

from __future__ import annotations

import argparse
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template_string

from pec_rates import (
    APP_TIMEZONE,
    APP_TIMEZONE_NAME,
    DEFAULT_RATE_SNAPSHOT_FILE,
    SnapshotMetadata,
    SnapshotState,
    build_daily_schedule,
    cents_per_kwh_label,
    create_refresh_schedule,
    current_rate_status,
    ensure_snapshot_state_for_server,
    fetch_live_rate_state,
    next_refresh_datetime,
    now_local,
    period_color,
    save_rate_snapshot,
    title_case_period,
)


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PEC Rate Dashboard</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #07131b;
      --bg-deep: #0c1b24;
      --surface: rgba(12, 25, 35, 0.9);
      --surface-strong: rgba(16, 35, 49, 0.96);
      --text: #e6eef5;
      --muted: #8da1b1;
      --border: rgba(148, 163, 184, 0.18);
      --shadow: 0 20px 48px rgba(0, 0, 0, 0.34);
      --peak: #ef4444;
      --mid: #f59e0b;
      --off: #22c55e;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Avenir Next", Avenir, "Segoe UI", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(34, 197, 94, 0.16), transparent 18%),
        radial-gradient(circle at top right, rgba(239, 68, 68, 0.12), transparent 22%),
        linear-gradient(180deg, var(--bg-deep) 0%, var(--bg) 100%);
    }
    .shell { max-width: 1240px; margin: 0 auto; padding: 24px; }
    .hero, .panel, .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 22px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(12px);
    }
    .hero {
      background: linear-gradient(135deg, rgba(16, 35, 49, 0.96) 0%, rgba(10, 22, 31, 0.96) 100%);
      padding: 28px;
      display: grid;
      grid-template-columns: 1.2fr 1fr;
      gap: 18px;
      margin-bottom: 18px;
    }
    .hero h1 {
      margin: 0 0 10px;
      font-size: clamp(2rem, 4vw, 3.4rem);
      line-height: 1;
      letter-spacing: -0.05em;
    }
    .hero p { margin: 0; color: var(--muted); max-width: 60ch; }
    .rate-focus {
      border-radius: 18px;
      padding: 20px;
      color: white;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      min-height: 180px;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 8px 14px;
      font-size: 0.85rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      background: rgba(255, 255, 255, 0.16);
      width: fit-content;
    }
    .rate-value {
      font-size: clamp(2.6rem, 5vw, 4.6rem);
      line-height: 1;
      letter-spacing: -0.06em;
    }
    .sub {
      font-size: 1rem;
      opacity: 0.92;
    }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }
    .card { padding: 18px; }
    .eyebrow {
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-size: 0.78rem;
      margin-bottom: 10px;
    }
    .value {
      font-size: clamp(1.4rem, 3vw, 2.1rem);
      line-height: 1.05;
      letter-spacing: -0.04em;
      margin-bottom: 8px;
    }
    .note { color: var(--muted); font-size: 0.93rem; }
    .grid {
      display: grid;
      grid-template-columns: 1.3fr 0.9fr;
      gap: 18px;
    }
    .panel { padding: 20px; }
    .panel h2 { margin: 0 0 14px; font-size: 1.15rem; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.96rem;
    }
    th, td {
      padding: 12px 0;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
    }
    th {
      color: var(--muted);
      font-weight: 600;
      width: 140px;
    }
    .schedule th { width: auto; }
    .period-pill {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 110px;
      padding: 7px 12px;
      border-radius: 999px;
      font-weight: 700;
      color: white;
    }
    .row-current {
      outline: 2px solid currentColor;
      outline-offset: -2px;
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.05);
    }
    .error {
      margin-bottom: 16px;
      padding: 14px 16px;
      border-radius: 16px;
      background: rgba(127, 29, 29, 0.28);
      color: #fecaca;
      border: 1px solid rgba(248, 113, 113, 0.34);
      display: none;
    }
    .footer {
      color: var(--muted);
      font-size: 0.9rem;
      padding: 16px 4px 4px;
    }
    @media (max-width: 920px) {
      .hero, .grid { grid-template-columns: 1fr; }
    }
    @media (max-width: 680px) {
      .shell { padding: 14px; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div id="error" class="error"></div>
    <section class="hero">
      <div>
        <h1>PEC Rate Dashboard</h1>
        <p>
          Live local dashboard for the current PEC rate snapshot. It shows the current
          TOU period, today’s schedule, next rate change, and the last time the local
          snapshot JSON was updated.
        </p>
      </div>
      <div id="rate-focus" class="rate-focus">
        <div id="period-badge" class="badge">Loading</div>
        <div>
          <div id="allin-rate" class="rate-value">--</div>
          <div id="base-rate" class="sub">--</div>
        </div>
        <div id="next-change-focus" class="sub">--</div>
      </div>
    </section>

    <section class="cards">
      <div class="card">
        <div class="eyebrow">Current Time</div>
        <div id="current-time" class="value">--</div>
        <div id="current-date" class="note">--</div>
      </div>
      <div class="card">
        <div class="eyebrow">Current Period</div>
        <div id="current-period" class="value">--</div>
        <div id="current-season" class="note">--</div>
      </div>
      <div class="card">
        <div class="eyebrow">Today's Rate</div>
        <div id="today-rate" class="value">--</div>
        <div class="note">All-in variable rate</div>
      </div>
      <div class="card">
        <div class="eyebrow">Next Change</div>
        <div id="next-change" class="value">--</div>
        <div id="next-period" class="note">--</div>
      </div>
      <div class="card">
        <div class="eyebrow">Last JSON Update</div>
        <div id="saved-at" class="value">--</div>
        <div id="last-success" class="note">--</div>
      </div>
      <div class="card">
        <div class="eyebrow">Next Snapshot Refresh</div>
        <div id="next-refresh" class="value">--</div>
        <div id="refresh-profile" class="note">--</div>
      </div>
    </section>

    <section class="grid">
      <section class="panel">
        <h2>Today's Schedule</h2>
        <table class="schedule">
          <thead>
            <tr>
              <th>Window</th>
              <th>Period</th>
              <th>Base Rate</th>
              <th>All-In Rate</th>
            </tr>
          </thead>
          <tbody id="schedule-body"></tbody>
        </table>
      </section>
      <section class="panel">
        <h2>Snapshot Details</h2>
        <table>
          <tbody id="meta-body"></tbody>
        </table>
      </section>
    </section>

    <div class="footer">
      Auto-refreshing every 60 seconds. Clock updates every second between refreshes.
    </div>
  </div>

  <script>
    let serverTimeMs = null;
    let clientTickBase = null;
    let latestStatus = null;

    function formatDateTime(isoValue) {
      if (!isoValue) return "N/A";
      const value = new Date(isoValue);
      return new Intl.DateTimeFormat("en-US", {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(value);
    }

    function formatClock(value) {
      return new Intl.DateTimeFormat("en-US", {
        timeStyle: "medium"
      }).format(value);
    }

    function formatLongDate(value) {
      return new Intl.DateTimeFormat("en-US", {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric"
      }).format(value);
    }

    function rateColor(periodName) {
      if (periodName === "peak") return "var(--peak)";
      if (periodName === "mid_peak") return "var(--mid)";
      return "var(--off)";
    }

    function periodLabel(periodName) {
      return periodName.replaceAll("_", " ").replace(/\\b\\w/g, char => char.toUpperCase());
    }

    function updateClock() {
      if (serverTimeMs === null || clientTickBase === null) return;
      const nowValue = new Date(serverTimeMs + (Date.now() - clientTickBase));
      document.getElementById("current-time").textContent = formatClock(nowValue);
      document.getElementById("current-date").textContent = formatLongDate(nowValue);
    }

    function renderSchedule(rows, currentPeriod) {
      const tbody = document.getElementById("schedule-body");
      tbody.innerHTML = "";
      for (const row of rows) {
        const tr = document.createElement("tr");
        if (row.is_current) {
          tr.classList.add("row-current");
          tr.style.color = rateColor(row.period_name);
        }
        tr.innerHTML = `
          <td>${row.start_label} - ${row.end_label}</td>
          <td><span class="period-pill" style="background:${rateColor(row.period_name)}">${periodLabel(row.period_name)}</span></td>
          <td>${row.base_rate_label}</td>
          <td>${row.total_rate_label}</td>
        `;
        tbody.appendChild(tr);
      }
    }

    function renderMeta(data) {
      const tbody = document.getElementById("meta-body");
      const rows = [
        ["Rate Source", `${data.source.label} (${data.source.status})`],
        ["Source Timestamp", data.source.timestamp || "N/A"],
        ["Snapshot Saved", data.snapshot.saved_at_label],
        ["Last Success", data.snapshot.last_success_at_label],
        ["Last Attempt", data.snapshot.last_attempt_at_label],
        ["Last Error", data.snapshot.last_error || "None"],
        ["Service Charge", data.rates.service_charge_label],
        ["Delivery Charge", data.rates.delivery_charge_label],
        ["Transmission Charge", data.rates.transmission_charge_label],
        ["Flat Variable", data.rates.flat_variable_rate_label]
      ];
      tbody.innerHTML = rows.map(([label, value]) => `<tr><th>${label}</th><td>${value}</td></tr>`).join("");
    }

    function applyStatus(data) {
      latestStatus = data;
      serverTimeMs = Date.parse(data.server_time);
      clientTickBase = Date.now();
      updateClock();

      const focus = document.getElementById("rate-focus");
      focus.style.background = `linear-gradient(135deg, ${data.current_period.color} 0%, rgba(15, 23, 42, 0.92) 100%)`;
      document.getElementById("period-badge").textContent = `${data.current_period.label} • ${data.current_period.season_label}`;
      document.getElementById("allin-rate").textContent = data.current_period.total_rate_label;
      document.getElementById("base-rate").textContent = `Base ${data.current_period.base_rate_label} • ${data.current_period.season_label}`;
      document.getElementById("next-change-focus").textContent = `Next change: ${data.next_change.time_label} → ${data.next_change.next_period_label}`;

      document.getElementById("current-period").textContent = data.current_period.label;
      document.getElementById("current-season").textContent = data.current_period.season_label;
      document.getElementById("today-rate").textContent = data.current_period.total_rate_label;
      document.getElementById("next-change").textContent = data.next_change.time_label;
      document.getElementById("next-period").textContent = data.next_change.next_period_label;
      document.getElementById("saved-at").textContent = data.snapshot.saved_at_label;
      document.getElementById("last-success").textContent = `Last success: ${data.snapshot.last_success_at_label}`;
      document.getElementById("next-refresh").textContent = data.snapshot.next_scheduled_refresh_label;
      document.getElementById("refresh-profile").textContent = data.snapshot.scheduler_summary;

      renderSchedule(data.today_schedule, data.current_period.period_name);
      renderMeta(data);

      const errorBox = document.getElementById("error");
      if (data.snapshot.last_error) {
        errorBox.style.display = "block";
        errorBox.textContent = `Last refresh error: ${data.snapshot.last_error}`;
      } else {
        errorBox.style.display = "none";
        errorBox.textContent = "";
      }
    }

    async function refreshStatus() {
      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        applyStatus(payload);
      } catch (error) {
        const errorBox = document.getElementById("error");
        errorBox.style.display = "block";
        errorBox.textContent = `Dashboard refresh failed: ${error.message}`;
      }
    }

    refreshStatus();
    setInterval(refreshStatus, 60000);
    setInterval(updateClock, 1000);
  </script>
</body>
</html>
"""


class SnapshotManager:
    def __init__(self, snapshot_file: Path) -> None:
        self.snapshot_file = snapshot_file
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.schedule = create_refresh_schedule()
        self.snapshot_state = ensure_snapshot_state_for_server(snapshot_file, self.schedule)
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self._run_loop, name="pec-rate-refresh", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=1)

    def _persist_state(self, snapshot_state: SnapshotState) -> SnapshotState:
        save_rate_snapshot(snapshot_state, self.snapshot_file)
        self.snapshot_state = snapshot_state
        return snapshot_state

    def _metadata_for(self, *, now_value: datetime, last_success_at: str | None, last_attempt_at: str | None, last_error: str | None) -> SnapshotMetadata:
        return SnapshotMetadata(
            saved_at=now_value.isoformat(),
            last_success_at=last_success_at,
            last_attempt_at=last_attempt_at,
            last_error=last_error,
            next_scheduled_refresh=next_refresh_datetime(now_value, self.schedule).isoformat(),
            scheduler_profile=self.schedule.to_dict(),
        )

    def refresh_once(self) -> None:
        with self.lock:
            now_value = now_local()
            try:
                live_state = fetch_live_rate_state()
                metadata = self._metadata_for(
                    now_value=now_value,
                    last_success_at=now_value.isoformat(),
                    last_attempt_at=now_value.isoformat(),
                    last_error=None,
                )
                self._persist_state(
                    SnapshotState(
                        rate_config=live_state.rate_config,
                        metadata=metadata,
                        source_payload=live_state.source_payload,
                    )
                )
            except Exception as exc:
                metadata = self._metadata_for(
                    now_value=now_value,
                    last_success_at=self.snapshot_state.metadata.last_success_at,
                    last_attempt_at=now_value.isoformat(),
                    last_error=str(exc),
                )
                self._persist_state(
                    SnapshotState(
                        rate_config=self.snapshot_state.rate_config,
                        metadata=metadata,
                        source_payload=self.snapshot_state.source_payload,
                    )
                )

    def _run_loop(self) -> None:
        while not self.stop_event.is_set():
            with self.lock:
                next_value = next_refresh_datetime(now_local(), self.schedule)
            wait_seconds = max(1, (next_value - now_local()).total_seconds())
            if self.stop_event.wait(wait_seconds):
                break
            self.refresh_once()

    def get_status_payload(self) -> dict[str, Any]:
        with self.lock:
            state = self.snapshot_state
        now_value = now_local()
        current = current_rate_status(now_value, state.rate_config)
        schedule_rows = []
        for row in build_daily_schedule(now_value.date(), state.rate_config):
            schedule_rows.append(
                {
                    "start": row.start_local.isoformat(),
                    "end": row.end_local.isoformat(),
                    "start_label": row.start_local.strftime("%I:%M %p"),
                    "end_label": row.end_local.strftime("%I:%M %p"),
                    "season_name": row.season_name,
                    "period_name": row.period_name,
                    "label": row.label,
                    "base_rate": row.base_rate,
                    "total_rate": row.total_rate,
                "base_rate_label": cents_per_kwh_label(row.base_rate),
                "total_rate_label": cents_per_kwh_label(row.total_rate),
                    "color": period_color(row.period_name),
                    "is_current": row.start_local <= now_value < row.end_local,
                }
            )

        scheduler_profile = state.metadata.scheduler_profile or self.schedule.to_dict()
        return {
            "server_time": now_value.isoformat(),
            "timezone": APP_TIMEZONE_NAME,
            "current_period": {
                "season_name": current.season_name,
                "season_label": current.season_name.title(),
                "period_name": current.period_name,
                "label": title_case_period(current.period_name),
                "color": period_color(current.period_name),
                "base_rate": current.base_rate,
                "base_rate_label": cents_per_kwh_label(current.base_rate),
                "total_rate": current.total_rate,
                "total_rate_label": cents_per_kwh_label(current.total_rate),
            },
            "next_change": {
                "time": current.next_change_local.isoformat(),
                "time_label": current.next_change_local.strftime("%I:%M %p %Z"),
                "next_period_name": current.next_period_name,
                "next_period_label": title_case_period(current.next_period_name),
            },
            "today_schedule": schedule_rows,
            "rates": {
                "service_charge": state.rate_config.service_charge,
                "service_charge_label": f"${state.rate_config.service_charge:,.2f}",
                "delivery_charge": state.rate_config.delivery_charge_per_kwh,
                "delivery_charge_label": cents_per_kwh_label(state.rate_config.delivery_charge_per_kwh),
                "transmission_charge": state.rate_config.transmission_charge_per_kwh,
                "transmission_charge_label": cents_per_kwh_label(state.rate_config.transmission_charge_per_kwh),
                "flat_variable_rate": state.rate_config.flat_variable_rate,
                "flat_variable_rate_label": cents_per_kwh_label(state.rate_config.flat_variable_rate),
            },
            "snapshot": {
                "saved_at": state.metadata.saved_at,
                "saved_at_label": format_snapshot_label(state.metadata.saved_at),
                "last_success_at": state.metadata.last_success_at,
                "last_success_at_label": format_snapshot_label(state.metadata.last_success_at),
                "last_attempt_at": state.metadata.last_attempt_at,
                "last_attempt_at_label": format_snapshot_label(state.metadata.last_attempt_at),
                "last_error": state.metadata.last_error,
                "next_scheduled_refresh": state.metadata.next_scheduled_refresh,
                "next_scheduled_refresh_label": format_snapshot_label(state.metadata.next_scheduled_refresh),
                "scheduler_profile": scheduler_profile,
                "scheduler_summary": scheduler_summary(scheduler_profile),
            },
            "source": {
                "label": state.rate_config.source_label,
                "status": state.rate_config.source_status,
                "note": state.rate_config.source_note,
                "timestamp": state.rate_config.source_timestamp,
                "urls": list(state.rate_config.source_urls),
            },
        }


def format_snapshot_label(value: str | None) -> str:
    if not value:
        return "N/A"
    try:
        return (
            datetime.fromisoformat(value)
            .astimezone(APP_TIMEZONE)
            .strftime("%Y-%m-%d %I:%M %p %Z")
        )
    except ValueError:
        return value


def scheduler_summary(profile: dict[str, Any]) -> str:
    scheduled_times = profile.get("scheduled_times", [])
    return f"{', '.join(scheduled_times)} {profile.get('timezone', APP_TIMEZONE_NAME)}"


def create_app(snapshot_file: Path, start_scheduler: bool = True) -> Flask:
    app = Flask(__name__)
    manager = SnapshotManager(snapshot_file)
    if start_scheduler:
        manager.start()
    app.config["snapshot_manager"] = manager

    @app.get("/")
    def index():
        return render_template_string(DASHBOARD_HTML)

    @app.get("/api/status")
    def api_status():
        return jsonify(manager.get_status_payload())

    @app.get("/healthz")
    def healthz():
        status = manager.get_status_payload()
        return jsonify(
            {
                "ok": True,
                "saved_at": status["snapshot"]["saved_at"],
                "last_success_at": status["snapshot"]["last_success_at"],
                "last_error": status["snapshot"]["last_error"],
                "next_scheduled_refresh": status["snapshot"]["next_scheduled_refresh"],
            }
        )

    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local PEC rate dashboard server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--snapshot-file",
        type=Path,
        default=Path(DEFAULT_RATE_SNAPSHOT_FILE),
        help=f"Path to the PEC snapshot JSON. Default: {DEFAULT_RATE_SNAPSHOT_FILE}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    app = create_app(args.snapshot_file, start_scheduler=True)
    app.run(host=args.host, port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
