# Rate Snapshot and Refresh Model

## Purpose

The rate snapshot system keeps local pricing data separate from the XML report logic.

This gives the project:

- a persistent local source of PEC rate data
- a fallback when live fetches fail
- a consistent rate model shared by the report and dashboard

## Shared Module

All rate logic lives in:

- `pec_rates.py`

## Rate Model

The main configuration object is `RateConfig`.

It holds:

- service availability charge
- delivery charge per kWh
- transmission charge per kWh
- flat base rate per kWh
- seasonal TOU base rates
- source label, status, note, timestamp, and URLs

Computed properties include:

- `additional_variable_charge_per_kwh`
- `flat_variable_rate`
- `tou_base_rate(season_name, period_name)`
- `tou_total_rate(season_name, period_name)`

## Seasons and TOU Periods

The code defines three seasons:

- summer
- shoulder
- winter

TOU periods are:

- `off_peak`
- `mid_peak`
- `peak`

Not every season uses every period. Winter and shoulder currently use off-peak and mid-peak. Summer uses all three.

## Snapshot File

The default snapshot file is:

- `pec_rate_snapshot.json`

The snapshot contains:

- `rates`
- `source`
- `saved_at`
- `last_success_at`
- `last_attempt_at`
- `last_error`
- `next_scheduled_refresh`
- `scheduler_profile`

## Snapshot Lifecycle

### Load

`load_rate_snapshot()` reads the JSON file and reconstructs the snapshot state.

### Save

`save_rate_snapshot()` writes the current rate config and metadata back to JSON.

### Resolve

`resolve_rate_state()` chooses the rate source:

- `cached`
  - built-in official snapshot values
- `auto`
  - try live fetch first, then fall back to local snapshot or cached values

### Ensure for Server

`ensure_snapshot_state_for_server()` guarantees the dashboard can start with a usable snapshot and scheduler metadata.

## Manual Refresh Script

`refresh_pec_rate_snapshot.py` is the operator-facing entrypoint for writing the snapshot file.

It supports:

- live refresh via `--rate-source auto`
- cached snapshot write via `--rate-source cached`
- rate overrides for service, delivery, transmission, and flat base rate

## Live PEC Parsing

The live fetch path:

1. downloads the PEC TOU page
2. downloads the PEC residential rates page
3. normalizes the HTML text
4. extracts the rate blocks
5. parses dollar values into the shared `RateConfig`

## Important Constraint

PEC may block automated requests.

The implementation already accounts for that by preserving the last working local snapshot and exposing errors through the dashboard metadata.

## Related Pages

- [Rate Dashboard Server](./04-rate-dashboard-server.md)
- [Testing and Maintenance](./07-testing-and-maintenance.md)

