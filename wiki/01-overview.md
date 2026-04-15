# Overview

## Purpose

This toolkit analyzes household electricity usage from Green Button XML exports and combines that usage with PEC pricing data.

It supports two main workflows:

- Offline bill analysis from an XML file
- Live local viewing of current PEC time-of-use rates

## Architecture

The code is split into a shared rate layer plus small entrypoint scripts.

### Shared Core

- `pec_rates.py`

This module is the system of record for:

- PEC seasonal TOU schedules
- base and all-in variable rate calculations
- rate snapshot JSON read/write
- live PEC page parsing
- refresh scheduling
- current-period and next-change calculations

### User-Facing Scripts

- `energy_analysis_report.py`
  - Builds a standalone HTML report from a Green Button XML file.
- `rate_dashboard_server.py`
  - Runs a Flask server with a live rates dashboard and background snapshot refresh loop.
- `refresh_pec_rate_snapshot.py`
  - Manually refreshes the local rate snapshot JSON.
- `hourly_usage_chart.py`
  - Creates a simpler hourly usage chart from XML.
- `parse_energy.py`
  - A lightweight inspection script for raw XML totals.

## Data Flow

### Report Flow

1. Read Green Button XML.
2. Extract interval kWh readings.
3. Resolve PEC rate state from the local snapshot or live fetch path.
4. Apply TOU and flat-rate calculations across the interval data.
5. Generate a standalone HTML report with summary tables and Plotly charts.

### Dashboard Flow

1. Start Flask app.
2. Load `pec_rate_snapshot.json`, or create it from cached defaults if missing.
3. Start a background thread.
4. The thread refreshes the snapshot twice per day using a jittered schedule.
5. The webpage polls `/api/status` every 60 seconds and updates the visible rate cards and tables.

## Timezone Model

The toolkit treats `America/Chicago` as the application timezone for:

- PEC TOU period resolution
- dashboard display
- refresh scheduling

The report script can still accept a timezone override for chart labels.

## Current UI Features

- Dark mode on the live dashboard
- Dark mode on generated HTML reports
- Current rate cards and next-change display
- Color-coded TOU periods:
  - red for peak
  - orange for mid-peak
  - green for off-peak
- Rate display in cents per kWh with one decimal place

## Related Pages

- [Setup and Quick Start](./02-setup-and-quick-start.md)
- [Energy Analysis Report](./03-energy-analysis-report.md)
- [Rate Dashboard Server](./04-rate-dashboard-server.md)

