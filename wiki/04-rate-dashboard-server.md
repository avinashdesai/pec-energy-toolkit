# Rate Dashboard Server

## Purpose

`rate_dashboard_server.py` runs a local Flask app that shows the current PEC rate state and keeps a local snapshot file fresh in the background.

## What the Dashboard Shows

- current local time
- current season
- current TOU period
- current base rate
- current all-in variable rate
- next TOU change
- today’s TOU schedule
- last JSON update
- last successful refresh
- next scheduled refresh
- source details and latest error

## UI Behavior

The page is designed as a live dashboard, not a historical bill report.

Current behavior:

- dark mode UI
- auto-refresh every 60 seconds
- live clock updates every second
- active TOU row is highlighted
- current period uses color coding:
  - red for peak
  - orange for mid-peak
  - green for off-peak

## Server Endpoints

### `GET /`

Returns the dashboard HTML page.

### `GET /api/status`

Returns the current dashboard payload as JSON.

The payload includes:

- `server_time`
- `timezone`
- `current_period`
- `next_change`
- `today_schedule`
- `rates`
- `snapshot`
- `source`

### `GET /healthz`

Returns a minimal health payload:

- `ok`
- `saved_at`
- `last_success_at`
- `last_error`
- `next_scheduled_refresh`

## Background Refresh Loop

The server starts a daemon thread that:

1. computes the next scheduled refresh time
2. sleeps until that time
3. tries a live PEC refresh
4. writes the result to `pec_rate_snapshot.json`
5. preserves the last good rate data if the live refresh fails

## Refresh Schedule

The refresh model is:

- two refreshes per day
- base times of `9:00 AM` and `9:00 PM`
- per-process random jitter of `±60 minutes`
- the chosen offset pair stays stable until the server restarts

This reduces repeated requests at the exact same wall-clock time.

## Running the Server

```bash
source .venv/bin/activate
python rate_dashboard_server.py
```

Optional flags:

- `--host`
- `--port`
- `--snapshot-file`

Example:

```bash
python rate_dashboard_server.py --host 127.0.0.1 --port 8001
```

## Failure Behavior

If PEC blocks or fails during a refresh attempt:

- the dashboard keeps serving the last good snapshot
- `last_error` is recorded
- the UI shows the error message
- the next scheduled refresh is still calculated

## Related Pages

- [Rate Snapshot and Refresh Model](./05-rate-snapshot-and-refresh.md)
- [Testing and Maintenance](./07-testing-and-maintenance.md)

