#!/usr/bin/env python3
"""Shared PEC rate, snapshot, and scheduling utilities."""

from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from zoneinfo import ZoneInfo
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Python 3.9+ with zoneinfo support is required.") from exc


PEC_TOU_URL = "https://mypec.com/residential-rates/time-of-use-rate/"
PEC_RESIDENTIAL_URL = "https://mypec.com/residential-rates/"
DEFAULT_RATE_SNAPSHOT_FILE = "pec_rate_snapshot.json"
APP_TIMEZONE_NAME = "America/Chicago"
APP_TIMEZONE = ZoneInfo(APP_TIMEZONE_NAME)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class PeriodWindow:
    start_minute: int
    end_minute: int
    period_name: str
    label: str


@dataclass(frozen=True)
class SeasonDefinition:
    season_name: str
    months: tuple[int, ...]
    windows: tuple[PeriodWindow, ...]


@dataclass(frozen=True)
class RateConfig:
    service_charge: float = 32.50
    delivery_charge_per_kwh: float = 0.022546
    transmission_charge_per_kwh: float = 0.019930
    flat_base_rate_per_kwh: float = 0.065900
    summer_off_peak_base: float = 0.043481
    summer_mid_peak_base: float = 0.093169
    summer_peak_base: float = 0.161843
    shoulder_off_peak_base: float = 0.043481
    shoulder_mid_peak_base: float = 0.086442
    winter_off_peak_base: float = 0.043481
    winter_mid_peak_base: float = 0.086442
    source_label: str = "PEC official snapshot"
    source_status: str = "cached"
    source_note: str = "Built-in fallback values from the official PEC rate pages."
    source_timestamp: str = "2026-04-15"
    source_urls: tuple[str, ...] = (PEC_TOU_URL, PEC_RESIDENTIAL_URL)

    @property
    def additional_variable_charge_per_kwh(self) -> float:
        return self.delivery_charge_per_kwh + self.transmission_charge_per_kwh

    @property
    def flat_variable_rate(self) -> float:
        return self.flat_base_rate_per_kwh + self.additional_variable_charge_per_kwh

    def tou_base_rate(self, season_name: str, period_name: str) -> float:
        if season_name == "summer":
            if period_name == "off_peak":
                return self.summer_off_peak_base
            if period_name == "mid_peak":
                return self.summer_mid_peak_base
            if period_name == "peak":
                return self.summer_peak_base
        if season_name == "winter":
            if period_name == "off_peak":
                return self.winter_off_peak_base
            if period_name == "mid_peak":
                return self.winter_mid_peak_base
        if period_name == "off_peak":
            return self.shoulder_off_peak_base
        if period_name == "mid_peak":
            return self.shoulder_mid_peak_base
        raise ValueError(f"Unsupported TOU period '{period_name}' for season '{season_name}'")

    def tou_total_rate(self, season_name: str, period_name: str) -> float:
        return self.tou_base_rate(season_name, period_name) + self.additional_variable_charge_per_kwh


@dataclass(frozen=True)
class SnapshotMetadata:
    saved_at: str | None = None
    last_success_at: str | None = None
    last_attempt_at: str | None = None
    last_error: str | None = None
    next_scheduled_refresh: str | None = None
    scheduler_profile: dict[str, Any] | None = None


@dataclass(frozen=True)
class SnapshotState:
    rate_config: RateConfig
    metadata: SnapshotMetadata
    source_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class ScheduleEntry:
    season_name: str
    period_name: str
    start_local: datetime
    end_local: datetime
    label: str
    base_rate: float
    total_rate: float


@dataclass(frozen=True)
class CurrentRateStatus:
    now_local: datetime
    season_name: str
    period_name: str
    base_rate: float
    total_rate: float
    next_change_local: datetime
    next_period_name: str


@dataclass(frozen=True)
class RefreshSchedule:
    timezone_name: str
    base_times: tuple[str, str]
    offsets_minutes: tuple[int, int]
    daily_minutes: tuple[int, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "timezone": self.timezone_name,
            "base_times": list(self.base_times),
            "offsets_minutes": list(self.offsets_minutes),
            "scheduled_times": [minutes_to_time_label(value) for value in self.daily_minutes],
        }


SUMMER_WINDOWS = (
    PeriodWindow(0, 14 * 60, "off_peak", "12:01 a.m. to 2:00 p.m.; 9:01 p.m. to 12:00 a.m."),
    PeriodWindow(14 * 60 + 1, 16 * 60, "mid_peak", "2:01 p.m. to 4:00 p.m.; 8:01 p.m. to 9:00 p.m."),
    PeriodWindow(16 * 60 + 1, 20 * 60, "peak", "4:01 p.m. to 8:00 p.m."),
    PeriodWindow(20 * 60 + 1, 21 * 60, "mid_peak", "2:01 p.m. to 4:00 p.m.; 8:01 p.m. to 9:00 p.m."),
    PeriodWindow(21 * 60 + 1, 23 * 60 + 59, "off_peak", "12:01 a.m. to 2:00 p.m.; 9:01 p.m. to 12:00 a.m."),
)
SHOULDER_WINDOWS = (
    PeriodWindow(0, 17 * 60, "off_peak", "12:01 a.m. to 5:00 p.m.; 9:01 p.m. to 12:00 a.m."),
    PeriodWindow(17 * 60 + 1, 21 * 60, "mid_peak", "5:01 p.m. to 9:00 p.m."),
    PeriodWindow(21 * 60 + 1, 23 * 60 + 59, "off_peak", "12:01 a.m. to 5:00 p.m.; 9:01 p.m. to 12:00 a.m."),
)
WINTER_WINDOWS = (
    PeriodWindow(0, 5 * 60, "off_peak", "12:01 a.m. to 5:00 a.m.; 9:01 a.m. to 5:00 p.m.; 9:01 p.m. to 12:00 a.m."),
    PeriodWindow(5 * 60 + 1, 9 * 60, "mid_peak", "5:01 a.m. to 9:00 a.m.; 5:01 p.m. to 9:00 p.m."),
    PeriodWindow(9 * 60 + 1, 17 * 60, "off_peak", "12:01 a.m. to 5:00 a.m.; 9:01 a.m. to 5:00 p.m.; 9:01 p.m. to 12:00 a.m."),
    PeriodWindow(17 * 60 + 1, 21 * 60, "mid_peak", "5:01 a.m. to 9:00 a.m.; 5:01 p.m. to 9:00 p.m."),
    PeriodWindow(21 * 60 + 1, 23 * 60 + 59, "off_peak", "12:01 a.m. to 5:00 a.m.; 9:01 a.m. to 5:00 p.m.; 9:01 p.m. to 12:00 a.m."),
)

SEASONS = (
    SeasonDefinition("summer", (6, 7, 8, 9), SUMMER_WINDOWS),
    SeasonDefinition("shoulder", (3, 4, 5, 10, 11), SHOULDER_WINDOWS),
    SeasonDefinition("winter", (12, 1, 2), WINTER_WINDOWS),
)


def now_local() -> datetime:
    return datetime.now(APP_TIMEZONE)


def time_label(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %I:%M %p %Z")


def minutes_to_time_label(total_minutes: int) -> str:
    hour = total_minutes // 60
    minute = total_minutes % 60
    value = datetime.combine(date.today(), time(hour=hour, minute=minute))
    return value.strftime("%I:%M %p")


def title_case_period(period_name: str) -> str:
    return period_name.replace("_", " ").title()


def cents_per_kwh_label(value: float) -> str:
    return f"{value * 100:.1f}¢/kWh"


def period_color(period_name: str) -> str:
    return {
        "off_peak": "#16a34a",
        "mid_peak": "#f97316",
        "peak": "#dc2626",
    }.get(period_name, "#64748b")


def season_definition_for_month(month: int) -> SeasonDefinition:
    for season in SEASONS:
        if month in season.months:
            return season
    raise ValueError(f"Unsupported month: {month}")


def tou_period_for_local_dt(local_dt: datetime) -> tuple[str, str]:
    season = season_definition_for_month(local_dt.month)
    minute = local_dt.hour * 60 + local_dt.minute
    for window in season.windows:
        if window.start_minute <= minute <= window.end_minute:
            return season.season_name, window.period_name
    raise ValueError(f"No TOU period found for local time {local_dt.isoformat()}")


def build_daily_schedule(local_day: date, rate_config: RateConfig) -> list[ScheduleEntry]:
    season = season_definition_for_month(local_day.month)
    midnight = datetime.combine(local_day, time.min, tzinfo=APP_TIMEZONE)
    entries: list[ScheduleEntry] = []
    for window in season.windows:
        start_local = midnight + timedelta(minutes=window.start_minute)
        end_exclusive = midnight + timedelta(minutes=window.end_minute + 1)
        entries.append(
            ScheduleEntry(
                season_name=season.season_name,
                period_name=window.period_name,
                start_local=start_local,
                end_local=end_exclusive,
                label=window.label,
                base_rate=rate_config.tou_base_rate(season.season_name, window.period_name),
                total_rate=rate_config.tou_total_rate(season.season_name, window.period_name),
            )
        )
    return entries


def current_rate_status(reference_local: datetime, rate_config: RateConfig) -> CurrentRateStatus:
    season_name, period_name = tou_period_for_local_dt(reference_local)
    base_rate = rate_config.tou_base_rate(season_name, period_name)
    total_rate = rate_config.tou_total_rate(season_name, period_name)

    today_schedule = build_daily_schedule(reference_local.date(), rate_config)
    tomorrow_schedule = build_daily_schedule(reference_local.date() + timedelta(days=1), rate_config)
    combined = today_schedule + tomorrow_schedule

    next_change_local = combined[-1].end_local
    next_period_name = combined[0].period_name
    for index, entry in enumerate(combined):
        if entry.start_local <= reference_local < entry.end_local:
            if index + 1 < len(combined):
                next_change_local = entry.end_local
                next_period_name = combined[index + 1].period_name
            break

    return CurrentRateStatus(
        now_local=reference_local,
        season_name=season_name,
        period_name=period_name,
        base_rate=base_rate,
        total_rate=total_rate,
        next_change_local=next_change_local,
        next_period_name=next_period_name,
    )


def create_refresh_schedule(rng: random.Random | None = None) -> RefreshSchedule:
    generator = rng or random.SystemRandom()
    base_minutes = (9 * 60, 21 * 60)
    offsets = (
        generator.randint(-60, 60),
        generator.randint(-60, 60),
    )
    scheduled = tuple(
        max(0, min(23 * 60 + 59, base + offset))
        for base, offset in zip(base_minutes, offsets)
    )
    return RefreshSchedule(
        timezone_name=APP_TIMEZONE_NAME,
        base_times=("09:00", "21:00"),
        offsets_minutes=offsets,
        daily_minutes=scheduled,
    )


def next_refresh_datetime(reference_local: datetime, schedule: RefreshSchedule) -> datetime:
    candidates: list[datetime] = []
    for day_offset in range(2):
        local_day = reference_local.date() + timedelta(days=day_offset)
        midnight = datetime.combine(local_day, time.min, tzinfo=APP_TIMEZONE)
        for scheduled_minute in schedule.daily_minutes:
            candidates.append(midnight + timedelta(minutes=scheduled_minute))
    for candidate in sorted(candidates):
        if candidate > reference_local:
            return candidate
    return candidates[-1]


def normalize_web_text(html_text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\\1>", " ", html_text)
    text = re.sub(r"(?i)<br\\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|tr|td|th|h1|h2|h3|h4|h5|h6)>", "\n", text)
    text = re.sub(r"(?i)<[^>]+>", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n+", "\n", text)
    return text.strip()


def fetch_url_text(url: str, timeout_seconds: int = 8) -> str:
    errors: list[str] = []
    try:
        request = Request(url, headers={"User-Agent": USER_AGENT})
        with urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
        return body.decode("utf-8", errors="ignore")
    except HTTPError as exc:  # pragma: no cover
        errors.append(f"urllib returned HTTP {exc.code} for {url}")
    except URLError as exc:  # pragma: no cover
        errors.append(f"urllib failed for {url}: {exc.reason}")
    except Exception as exc:  # pragma: no cover
        errors.append(f"urllib failed for {url}: {exc}")
    raise RuntimeError("; ".join(errors))


def extract_block(text: str, start_marker: str, end_marker: str | None) -> str:
    start_index = text.find(start_marker)
    if start_index == -1:
        raise ValueError(f"Could not find marker '{start_marker}' in live rate page.")
    if end_marker is None:
        return text[start_index:]
    end_index = text.find(end_marker, start_index)
    if end_index == -1:
        return text[start_index:]
    return text[start_index:end_index]


def parse_money(text: str, pattern: str, label: str) -> float:
    match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
    if not match:
        raise ValueError(f"Could not parse '{label}' from live rate page.")
    return float(match.group(1))


def parse_live_pec_rates(tou_html: str, residential_html: str) -> RateConfig:
    tou_text = normalize_web_text(tou_html)
    residential_text = normalize_web_text(residential_html)

    summer_block = extract_block(
        tou_text,
        "Summer (June-September)",
        "Shoulder (March, April, May, October, November)",
    )
    shoulder_block = extract_block(
        tou_text,
        "Shoulder (March, April, May, October, November)",
        "Winter (December-February)",
    )
    winter_block = extract_block(
        tou_text,
        "Winter (December-February)",
        "For additional information about PEC rates",
    )

    return RateConfig(
        service_charge=parse_money(
            residential_text,
            r"Service Availability Charge .*? \$([0-9]+\.[0-9]+)",
            "service availability charge",
        ),
        delivery_charge_per_kwh=parse_money(
            residential_text,
            r"Delivery Charge per kWh .*? \$([0-9]+\.[0-9]+)",
            "delivery charge",
        ),
        transmission_charge_per_kwh=parse_money(
            residential_text,
            r"Transmission Cost of Service per kWh .*? \$([0-9]+\.[0-9]+)",
            "transmission cost of service charge",
        ),
        flat_base_rate_per_kwh=parse_money(
            residential_text,
            r"Flat Base Power Charge(?: per kWh)? .*? \$([0-9]+\.[0-9]+)",
            "flat base power charge",
        ),
        summer_off_peak_base=parse_money(
            summer_block,
            r"Off-Peak .*? \$([0-9]+\.[0-9]+)",
            "summer off-peak base rate",
        ),
        summer_mid_peak_base=parse_money(
            summer_block,
            r"Mid-Peak .*? \$([0-9]+\.[0-9]+)",
            "summer mid-peak base rate",
        ),
        summer_peak_base=parse_money(
            summer_block,
            r"Peak .*? \$([0-9]+\.[0-9]+)",
            "summer peak base rate",
        ),
        shoulder_off_peak_base=parse_money(
            shoulder_block,
            r"Off-Peak .*? \$([0-9]+\.[0-9]+)",
            "shoulder off-peak base rate",
        ),
        shoulder_mid_peak_base=parse_money(
            shoulder_block,
            r"Mid-Peak .*? \$([0-9]+\.[0-9]+)",
            "shoulder mid-peak base rate",
        ),
        winter_off_peak_base=parse_money(
            winter_block,
            r"Off-Peak .*? \$([0-9]+\.[0-9]+)",
            "winter off-peak base rate",
        ),
        winter_mid_peak_base=parse_money(
            winter_block,
            r"Mid-Peak .*? \$([0-9]+\.[0-9]+)",
            "winter mid-peak base rate",
        ),
        source_label="PEC official website",
        source_status="live",
        source_note="Live rates fetched from the PEC rate pages at refresh time.",
        source_timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


def fetch_live_rate_state() -> SnapshotState:
    tou_html = fetch_url_text(PEC_TOU_URL)
    residential_html = fetch_url_text(PEC_RESIDENTIAL_URL)
    rate_config = parse_live_pec_rates(tou_html, residential_html)
    return SnapshotState(
        rate_config=rate_config,
        metadata=SnapshotMetadata(),
        source_payload=None,
    )


def default_rate_state() -> SnapshotState:
    return SnapshotState(
        rate_config=RateConfig(),
        metadata=SnapshotMetadata(),
        source_payload=None,
    )


def apply_rate_overrides(
    rate_config: RateConfig,
    *,
    service_charge: float | None = None,
    delivery_charge: float | None = None,
    transmission_charge: float | None = None,
    flat_rate: float | None = None,
) -> RateConfig:
    return replace(
        rate_config,
        service_charge=service_charge if service_charge is not None else rate_config.service_charge,
        delivery_charge_per_kwh=(
            delivery_charge if delivery_charge is not None else rate_config.delivery_charge_per_kwh
        ),
        transmission_charge_per_kwh=(
            transmission_charge
            if transmission_charge is not None
            else rate_config.transmission_charge_per_kwh
        ),
        flat_base_rate_per_kwh=(
            flat_rate if flat_rate is not None else rate_config.flat_base_rate_per_kwh
        ),
    )


def snapshot_state_with_rate_config(snapshot_state: SnapshotState, rate_config: RateConfig) -> SnapshotState:
    return SnapshotState(
        rate_config=rate_config,
        metadata=snapshot_state.metadata,
        source_payload=snapshot_state.source_payload,
    )


def update_snapshot_metadata(
    snapshot_state: SnapshotState,
    *,
    saved_at: str | None = None,
    last_success_at: str | None = None,
    last_attempt_at: str | None = None,
    last_error: str | None = None,
    next_scheduled_refresh: str | None = None,
    scheduler_profile: dict[str, Any] | None = None,
) -> SnapshotState:
    metadata = snapshot_state.metadata
    return SnapshotState(
        rate_config=snapshot_state.rate_config,
        metadata=SnapshotMetadata(
            saved_at=saved_at if saved_at is not None else metadata.saved_at,
            last_success_at=(
                last_success_at if last_success_at is not None else metadata.last_success_at
            ),
            last_attempt_at=(
                last_attempt_at if last_attempt_at is not None else metadata.last_attempt_at
            ),
            last_error=last_error,
            next_scheduled_refresh=(
                next_scheduled_refresh
                if next_scheduled_refresh is not None
                else metadata.next_scheduled_refresh
            ),
            scheduler_profile=(
                scheduler_profile if scheduler_profile is not None else metadata.scheduler_profile
            ),
        ),
        source_payload=snapshot_state.source_payload,
    )


def rate_config_to_snapshot_payload(rate_config: RateConfig) -> dict[str, Any]:
    return {
        "label": rate_config.source_label,
        "status": rate_config.source_status,
        "note": rate_config.source_note,
        "timestamp": rate_config.source_timestamp,
        "urls": list(rate_config.source_urls),
    }


def snapshot_state_to_payload(snapshot_state: SnapshotState) -> dict[str, Any]:
    metadata = snapshot_state.metadata
    source = snapshot_state.source_payload or rate_config_to_snapshot_payload(snapshot_state.rate_config)
    return {
        "saved_at": metadata.saved_at,
        "last_success_at": metadata.last_success_at,
        "last_attempt_at": metadata.last_attempt_at,
        "last_error": metadata.last_error,
        "next_scheduled_refresh": metadata.next_scheduled_refresh,
        "scheduler_profile": metadata.scheduler_profile,
        "rates": {
            "service_charge": snapshot_state.rate_config.service_charge,
            "delivery_charge_per_kwh": snapshot_state.rate_config.delivery_charge_per_kwh,
            "transmission_charge_per_kwh": snapshot_state.rate_config.transmission_charge_per_kwh,
            "flat_base_rate_per_kwh": snapshot_state.rate_config.flat_base_rate_per_kwh,
            "summer_off_peak_base": snapshot_state.rate_config.summer_off_peak_base,
            "summer_mid_peak_base": snapshot_state.rate_config.summer_mid_peak_base,
            "summer_peak_base": snapshot_state.rate_config.summer_peak_base,
            "shoulder_off_peak_base": snapshot_state.rate_config.shoulder_off_peak_base,
            "shoulder_mid_peak_base": snapshot_state.rate_config.shoulder_mid_peak_base,
            "winter_off_peak_base": snapshot_state.rate_config.winter_off_peak_base,
            "winter_mid_peak_base": snapshot_state.rate_config.winter_mid_peak_base,
        },
        "source": source,
    }


def save_rate_snapshot(snapshot_state: SnapshotState, snapshot_file: Path) -> Path:
    payload = snapshot_state_to_payload(snapshot_state)
    snapshot_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return snapshot_file


def load_rate_snapshot(snapshot_file: Path) -> SnapshotState | None:
    if not snapshot_file.exists():
        return None

    payload = json.loads(snapshot_file.read_text(encoding="utf-8"))
    rates = payload.get("rates", {})
    source = payload.get("source", {})
    saved_at = payload.get("saved_at")
    rate_config = RateConfig(
        service_charge=float(rates["service_charge"]),
        delivery_charge_per_kwh=float(rates["delivery_charge_per_kwh"]),
        transmission_charge_per_kwh=float(rates["transmission_charge_per_kwh"]),
        flat_base_rate_per_kwh=float(rates["flat_base_rate_per_kwh"]),
        summer_off_peak_base=float(rates["summer_off_peak_base"]),
        summer_mid_peak_base=float(rates["summer_mid_peak_base"]),
        summer_peak_base=float(rates["summer_peak_base"]),
        shoulder_off_peak_base=float(rates["shoulder_off_peak_base"]),
        shoulder_mid_peak_base=float(rates["shoulder_mid_peak_base"]),
        winter_off_peak_base=float(rates["winter_off_peak_base"]),
        winter_mid_peak_base=float(rates["winter_mid_peak_base"]),
        source_label=str(source.get("label", "PEC official snapshot")),
        source_status=str(source.get("status", "cached")),
        source_note=str(source.get("note", "Loaded from local snapshot.")),
        source_timestamp=str(source.get("timestamp", saved_at or "unknown")),
        source_urls=tuple(source.get("urls", [PEC_TOU_URL, PEC_RESIDENTIAL_URL])),
    )
    metadata = SnapshotMetadata(
        saved_at=saved_at,
        last_success_at=payload.get("last_success_at") or saved_at,
        last_attempt_at=payload.get("last_attempt_at"),
        last_error=payload.get("last_error"),
        next_scheduled_refresh=payload.get("next_scheduled_refresh"),
        scheduler_profile=payload.get("scheduler_profile"),
    )
    return SnapshotState(
        rate_config=rate_config,
        metadata=metadata,
        source_payload=dict(source) if source else None,
    )


def resolve_rate_state(rate_source: str, snapshot_file: Path) -> SnapshotState:
    if rate_source == "cached":
        snapshot_state = load_rate_snapshot(snapshot_file)
        return snapshot_state if snapshot_state is not None else default_rate_state()

    try:
        return fetch_live_rate_state()
    except Exception:
        snapshot_state = load_rate_snapshot(snapshot_file)
        return snapshot_state if snapshot_state is not None else default_rate_state()


def ensure_snapshot_state_for_server(snapshot_file: Path, schedule: RefreshSchedule) -> SnapshotState:
    timestamp = now_local().isoformat()
    snapshot_state = load_rate_snapshot(snapshot_file) or default_rate_state()
    if snapshot_state.metadata.last_success_at is None:
        snapshot_state = update_snapshot_metadata(
            snapshot_state,
            last_success_at=timestamp,
        )
    next_refresh = next_refresh_datetime(now_local(), schedule).isoformat()
    snapshot_state = update_snapshot_metadata(
        snapshot_state,
        saved_at=timestamp,
        next_scheduled_refresh=next_refresh,
        scheduler_profile=schedule.to_dict(),
        last_error=snapshot_state.metadata.last_error,
    )
    save_rate_snapshot(snapshot_state, snapshot_file)
    return snapshot_state
