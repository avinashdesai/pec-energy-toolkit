# Energy Usage Toolkit Wiki

This wiki documents the Green Button energy-analysis tooling in this folder.

## Reading Order

1. [Overview](./01-overview.md)
2. [Setup and Quick Start](./02-setup-and-quick-start.md)
3. [Energy Analysis Report](./03-energy-analysis-report.md)
4. [Rate Dashboard Server](./04-rate-dashboard-server.md)
5. [Rate Snapshot and Refresh Model](./05-rate-snapshot-and-refresh.md)
6. [XML Utilities](./06-xml-utilities.md)
7. [Testing and Maintenance](./07-testing-and-maintenance.md)

## What This Toolkit Does

- Parses Green Button XML interval data.
- Computes usage totals and cost comparisons.
- Applies PEC seasonal time-of-use rates and a flat-rate comparison.
- Saves a local JSON rate snapshot.
- Serves a local dashboard that shows the current rate and refresh status.
- Generates standalone HTML reports with Plotly charts.

## Main Entry Points

- `energy_analysis_report.py`
- `rate_dashboard_server.py`
- `refresh_pec_rate_snapshot.py`
- `hourly_usage_chart.py`
- `pec_rates.py`

## Output Files You Will Commonly See

- `*_report.html`: standalone usage analysis reports
- `pec_rate_snapshot.json`: local PEC rate snapshot with metadata
- `hourly_usage_chart.svg`: static hourly chart output

## Recommended Flow

If you are new to the project:

1. Read [Overview](./01-overview.md) to understand the moving parts.
2. Read [Setup and Quick Start](./02-setup-and-quick-start.md) to run the tools.
3. Use either:
   - [Energy Analysis Report](./03-energy-analysis-report.md) for bill analysis from XML
   - [Rate Dashboard Server](./04-rate-dashboard-server.md) for a live local rate page
4. Read [Rate Snapshot and Refresh Model](./05-rate-snapshot-and-refresh.md) if you need to change rate sourcing or snapshot behavior.

