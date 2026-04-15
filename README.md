# pec-energy-toolkit

Local Python toolkit for analyzing Green Button home energy XML data, comparing PEC time-of-use and flat-rate costs, maintaining a local rate snapshot, and serving a live rate dashboard with standalone HTML reports.

## Features

- Parse Green Button XML interval usage data
- Compute total energy usage and interval-derived costs
- Apply PEC seasonal TOU pricing
- Compare TOU against a flat-rate model
- Save a local PEC rate snapshot in JSON
- Refresh the snapshot manually or through the local dashboard server
- Generate standalone HTML reports with Plotly charts
- Serve a live local dashboard for current PEC rates and refresh status

## Main Scripts

- `energy_analysis_report.py`
  - Generates a full HTML usage and billing report from a Green Button XML file.
- `rate_dashboard_server.py`
  - Runs a local Flask server with a live PEC rates dashboard and background snapshot refresh.
- `refresh_pec_rate_snapshot.py`
  - Refreshes or rewrites the local PEC rate snapshot JSON.
- `hourly_usage_chart.py`
  - Generates a simpler hourly usage chart from XML.
- `pec_rates.py`
  - Shared PEC rate, schedule, snapshot, and refresh logic used by the other scripts.

## Requirements

- Python 3.9+
- `Flask`
- `plotly`

Optional:

- `matplotlib` if you want raster chart output from `hourly_usage_chart.py`

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick Start

Refresh the PEC snapshot:

```bash
python refresh_pec_rate_snapshot.py --rate-source auto
```

Generate an energy report from XML:

```bash
python energy_analysis_report.py april_bill_data.xml
```

Run the live local dashboard:

```bash
python rate_dashboard_server.py
```

Then open:

```text
http://127.0.0.1:8000
```

## Typical Outputs

- `*_report.html`
- `pec_rate_snapshot.json`
- `hourly_usage_chart.svg`

## Examples

Generate a report with a custom output path:

```bash
python energy_analysis_report.py april_current_bill.xml -o april_current_bill_report.html
```

Run the dashboard on a different port:

```bash
python rate_dashboard_server.py --port 8010
```

Write a cached snapshot without attempting a live fetch:

```bash
python refresh_pec_rate_snapshot.py --rate-source cached
```

## Notes

- The dashboard uses `America/Chicago` for TOU schedule resolution and refresh scheduling.
- The report and dashboard use the shared local snapshot model in `pec_rates.py`.
- If the PEC site blocks automated requests, the last good local snapshot is preserved.
- Current rate displays use cents per kWh with one decimal place. Totals remain in dollars.

## Documentation

Detailed documentation is in the wiki:

- [Wiki Index](./wiki/index.md)
- [Overview](./wiki/01-overview.md)
- [Setup and Quick Start](./wiki/02-setup-and-quick-start.md)
- [Energy Analysis Report](./wiki/03-energy-analysis-report.md)
- [Rate Dashboard Server](./wiki/04-rate-dashboard-server.md)
- [Rate Snapshot and Refresh Model](./wiki/05-rate-snapshot-and-refresh.md)
- [XML Utilities](./wiki/06-xml-utilities.md)
- [Testing and Maintenance](./wiki/07-testing-and-maintenance.md)

## Testing

```bash
source .venv/bin/activate
python -m unittest test_pec_rates.py test_rate_dashboard_server.py
```
