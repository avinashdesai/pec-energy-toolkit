# Setup and Quick Start

## Requirements

- Python 3.9 or newer
- A Green Button XML export for report generation
- Internet access only if you want live PEC rate refreshes

## Virtual Environment

Create and activate the virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Installed Dependencies

Current package requirements:

- `Flask`
- `plotly`

The hourly chart script can also use `matplotlib` when you want raster image output such as PNG.

## Quick Start: Generate an HTML Report

```bash
source .venv/bin/activate
python energy_analysis_report.py april_bill_data.xml
```

This writes:

- `april_bill_data_report.html`

## Quick Start: Run the Local Rate Dashboard

```bash
source .venv/bin/activate
python rate_dashboard_server.py
```

Then open:

- `http://127.0.0.1:8000`

## Quick Start: Refresh the PEC Snapshot Manually

```bash
source .venv/bin/activate
python refresh_pec_rate_snapshot.py --rate-source auto
```

If PEC blocks the live request, write the cached official snapshot instead:

```bash
python refresh_pec_rate_snapshot.py --rate-source cached
```

## Common Commands

Generate a report with a specific output path:

```bash
python energy_analysis_report.py april_current_bill.xml -o april_current_bill_report.html
```

Run the dashboard on a different port:

```bash
python rate_dashboard_server.py --port 8010
```

Use a different snapshot file:

```bash
python rate_dashboard_server.py --snapshot-file my_snapshot.json
```

## Suggested First Run

1. Refresh the snapshot once.
2. Start the dashboard.
3. Generate a report from one XML file.
4. Compare the dashboard’s current rate with the report’s historical bill analysis.

## Related Pages

- [Overview](./01-overview.md)
- [Energy Analysis Report](./03-energy-analysis-report.md)
- [Rate Dashboard Server](./04-rate-dashboard-server.md)

