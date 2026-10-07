"""Next-fire computation for interval, daily-at-time and cron schedules with explicit timezones."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter

from app.core.enums import ScheduleKind
from app.core.errors import ValidationFailed


def zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValidationFailed(
            f"Unknown timezone {name!r}",
            details={"fields": [{"field": "timezone", "message": "Use an IANA name such as Europe/Berlin"}]},
        ) from exc


def validate_schedule(
    kind: ScheduleKind, *, cron: str | None, interval_seconds: int | None, daily_time: str | None, timezone: str
) -> None:
    zone(timezone)
    if kind == ScheduleKind.cron:
        if not cron or not croniter.is_valid(cron):
            raise ValidationFailed(
                "Invalid cron expression",
                details={"fields": [{"field": "cron", "message": "Five fields: minute hour day month weekday"}]},
            )
    elif kind == ScheduleKind.interval:
        if not interval_seconds or interval_seconds < 60:
            raise ValidationFailed(
                "Interval must be at least 60 seconds",
                details={"fields": [{"field": "interval_seconds", "message": "Minimum 60"}]},
            )
    elif kind == ScheduleKind.daily:
        try:
            time.fromisoformat(daily_time or "")
        except ValueError as exc:
            raise ValidationFailed(
                "Daily time must be HH:MM", details={"fields": [{"field": "daily_time", "message": "Use 24h HH:MM"}]}
            ) from exc


def next_fire(
    kind: ScheduleKind,
    *,
    after: datetime,
    cron: str | None,
    interval_seconds: int | None,
    daily_time: str | None,
    timezone: str,
    anchor: datetime | None = None,
) -> datetime:
    """Next occurrence strictly after `after` (UTC-aware in, UTC-aware out)."""
    tz = zone(timezone)
    local_after = after.astimezone(tz)
    if kind == ScheduleKind.cron:
        return croniter(cron or "* * * * *", local_after).get_next(datetime).astimezone(after.tzinfo)
    if kind == ScheduleKind.interval:
        step = timedelta(seconds=interval_seconds or 3600)
        base = anchor or after
        if base > after:
            return base
        periods = int((after - base) / step) + 1
        return base + periods * step
    at = time.fromisoformat(daily_time or "09:00")
    candidate = datetime.combine(local_after.date(), at, tzinfo=tz)
    if candidate <= local_after:
        candidate = datetime.combine(local_after.date() + timedelta(days=1), at, tzinfo=tz)
    return candidate.astimezone(after.tzinfo)
