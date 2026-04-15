#!/usr/bin/env python3
"""Refresh the local PEC rate snapshot JSON used by the report and dashboard."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pec_rates import (
    DEFAULT_RATE_SNAPSHOT_FILE,
    SnapshotState,
    SnapshotMetadata,
    apply_rate_overrides,
    default_rate_state,
    now_local,
    resolve_rate_state,
    save_rate_snapshot,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh the local PEC rate snapshot JSON."
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(DEFAULT_RATE_SNAPSHOT_FILE),
        help=f"Snapshot JSON path. Default: {DEFAULT_RATE_SNAPSHOT_FILE}",
    )
    parser.add_argument(
        "--rate-source",
        choices=("auto", "cached"),
        default="auto",
        help="Try a live PEC fetch first or write the built-in cached snapshot. Default: auto",
    )
    parser.add_argument(
        "--service-charge",
        type=float,
        default=None,
        help="Override the fixed service availability charge in dollars.",
    )
    parser.add_argument(
        "--delivery-charge",
        type=float,
        default=None,
        help="Override the delivery charge in $/kWh.",
    )
    parser.add_argument(
        "--transmission-charge",
        type=float,
        default=None,
        help="Override the transmission cost of service charge in $/kWh.",
    )
    parser.add_argument(
        "--flat-rate",
        type=float,
        default=None,
        help="Override the flat base power charge in $/kWh.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot_state = (
        default_rate_state()
        if args.rate_source == "cached"
        else resolve_rate_state(args.rate_source, args.output)
    )
    overridden = apply_rate_overrides(
        snapshot_state.rate_config,
        service_charge=args.service_charge,
        delivery_charge=args.delivery_charge,
        transmission_charge=args.transmission_charge,
        flat_rate=args.flat_rate,
    )
    timestamp = now_local().isoformat()
    snapshot_state = SnapshotState(
        rate_config=overridden,
        metadata=SnapshotMetadata(
            saved_at=timestamp,
            last_success_at=timestamp,
            last_attempt_at=timestamp if args.rate_source == "auto" else snapshot_state.metadata.last_attempt_at,
            last_error=None,
            next_scheduled_refresh=snapshot_state.metadata.next_scheduled_refresh,
            scheduler_profile=snapshot_state.metadata.scheduler_profile,
        ),
        source_payload=snapshot_state.source_payload,
    )
    save_rate_snapshot(snapshot_state, args.output)

    print(f"Snapshot written to: {args.output}")
    print(
        f"Rate source: {snapshot_state.rate_config.source_label} "
        f"({snapshot_state.rate_config.source_status})"
    )
    print(f"Service charge: ${snapshot_state.rate_config.service_charge:.2f}")
    print(
        f"Flat variable rate: "
        f"${snapshot_state.rate_config.flat_variable_rate:.6f}/kWh"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
