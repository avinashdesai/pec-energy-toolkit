# Testing and Maintenance

## Current Test Coverage

Two unit test files are present:

- `test_pec_rates.py`
- `test_rate_dashboard_server.py`

## What Is Covered

### `test_pec_rates.py`

This test module covers:

- current period resolution for shoulder season
- current period resolution for summer peak
- winter rollover into the next day
- period color mapping
- daily schedule construction
- refresh schedule stability with a seeded RNG
- snapshot JSON round-trip for metadata

### `test_rate_dashboard_server.py`

This test module covers:

- `GET /api/status`
- `GET /`
- `GET /healthz`

## Run Tests

```bash
source .venv/bin/activate
python -m unittest test_pec_rates.py test_rate_dashboard_server.py
```

## Compile Check

For a fast syntax sanity pass:

```bash
source .venv/bin/activate
python -m py_compile pec_rates.py energy_analysis_report.py rate_dashboard_server.py refresh_pec_rate_snapshot.py
```

## Operational Checks

### Dashboard

Start the server and confirm:

- the page loads
- the current rate card is populated
- the current schedule row is highlighted
- the current time updates every second
- the page refreshes data every 60 seconds

### Report

Generate a report and confirm:

- the HTML file is created
- summary totals render correctly
- charts appear without broken Plotly output
- snapshot/source details render

### Snapshot

Run a manual refresh and confirm:

- `pec_rate_snapshot.json` is written
- metadata fields are updated
- source labels and timestamps look correct

## Maintenance Notes

- Keep `pec_rates.py` as the single shared rate/snapshot implementation.
- Avoid duplicating TOU schedule logic in user-facing scripts.
- Treat `pec_rate_snapshot.json` as runtime data, not hand-maintained source.
- If PEC changes its page structure, the parsing logic in `pec_rates.py` is the first place to inspect.
- If the dashboard UI changes, keep the API payload backward-compatible unless you are updating both sides together.

## Common Failure Modes

### Live PEC Fetch Fails

Possible causes:

- anti-bot protection
- layout changes on the PEC site
- network errors

Current behavior:

- last good snapshot is retained
- dashboard still serves data
- refresh error is recorded in metadata

### XML Parsing Finds No kWh Readings

Possible causes:

- unexpected XML format
- missing `uom` value `72`
- non-energy interval series only

### Charts Do Not Render as Expected

Possible causes:

- broken HTML output
- incomplete file write
- browser caching older report files

## Suggested Extension Points

- add richer tests for live parser edge cases
- add snapshot schema versioning if the JSON format evolves
- add more report options if new billing models need comparison

## Related Pages

- [Rate Dashboard Server](./04-rate-dashboard-server.md)
- [Rate Snapshot and Refresh Model](./05-rate-snapshot-and-refresh.md)
