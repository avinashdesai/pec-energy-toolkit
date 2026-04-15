from __future__ import annotations

import random
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from pec_rates import (
    APP_TIMEZONE,
    SnapshotMetadata,
    SnapshotState,
    build_daily_schedule,
    create_refresh_schedule,
    current_rate_status,
    default_rate_state,
    next_refresh_datetime,
    period_color,
    save_rate_snapshot,
    load_rate_snapshot,
)


class PecRatesTests(unittest.TestCase):
    def test_current_rate_status_shoulder(self) -> None:
        reference = datetime(2026, 4, 15, 18, 30, tzinfo=APP_TIMEZONE)
        status = current_rate_status(reference, default_rate_state().rate_config)
        self.assertEqual(status.season_name, "shoulder")
        self.assertEqual(status.period_name, "mid_peak")
        self.assertEqual(status.next_period_name, "off_peak")
        self.assertEqual(status.next_change_local.hour, 21)
        self.assertEqual(status.next_change_local.minute, 1)

    def test_current_rate_status_summer_peak(self) -> None:
        reference = datetime(2026, 7, 10, 17, 0, tzinfo=APP_TIMEZONE)
        status = current_rate_status(reference, default_rate_state().rate_config)
        self.assertEqual(status.season_name, "summer")
        self.assertEqual(status.period_name, "peak")
        self.assertEqual(status.next_period_name, "mid_peak")

    def test_current_rate_status_winter_rollover(self) -> None:
        reference = datetime(2026, 1, 10, 23, 30, tzinfo=APP_TIMEZONE)
        status = current_rate_status(reference, default_rate_state().rate_config)
        self.assertEqual(status.season_name, "winter")
        self.assertEqual(status.period_name, "off_peak")
        self.assertEqual(status.next_change_local.date(), date(2026, 1, 11))

    def test_schedule_colors(self) -> None:
        self.assertEqual(period_color("peak"), "#dc2626")
        self.assertEqual(period_color("mid_peak"), "#f97316")
        self.assertEqual(period_color("off_peak"), "#16a34a")

    def test_schedule_builds_rows(self) -> None:
        schedule = build_daily_schedule(date(2026, 4, 15), default_rate_state().rate_config)
        self.assertGreaterEqual(len(schedule), 3)
        self.assertEqual(schedule[0].period_name, "off_peak")

    def test_refresh_schedule_is_stable(self) -> None:
        schedule = create_refresh_schedule(random.Random(4))
        self.assertEqual(schedule.daily_minutes, create_refresh_schedule(random.Random(4)).daily_minutes)
        reference = datetime(2026, 4, 15, 8, 0, tzinfo=APP_TIMEZONE)
        next_value = next_refresh_datetime(reference, schedule)
        self.assertEqual(next_value.date(), reference.date())

    def test_snapshot_round_trip_preserves_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            snapshot_file = Path(temp_dir) / "snapshot.json"
            state = SnapshotState(
                rate_config=default_rate_state().rate_config,
                metadata=SnapshotMetadata(
                    saved_at="2026-04-15T09:00:00-05:00",
                    last_success_at="2026-04-15T09:00:00-05:00",
                    last_attempt_at="2026-04-15T09:00:00-05:00",
                    last_error=None,
                    next_scheduled_refresh="2026-04-15T21:00:00-05:00",
                    scheduler_profile={"scheduled_times": ["09:15 AM", "09:40 PM"]},
                ),
            )
            save_rate_snapshot(state, snapshot_file)
            loaded = load_rate_snapshot(snapshot_file)
            assert loaded is not None
            self.assertEqual(loaded.metadata.next_scheduled_refresh, state.metadata.next_scheduled_refresh)
            self.assertEqual(
                loaded.metadata.scheduler_profile,
                state.metadata.scheduler_profile,
            )


if __name__ == "__main__":
    unittest.main()
