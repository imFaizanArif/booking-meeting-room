"""Next-fire computation with explicit timezones (including DST changes)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.core.enums import ScheduleKind
from app.core.errors import ValidationFailed
from app.scheduler.timing import next_fire, validate_schedule


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def fire(kind: ScheduleKind, after: datetime, **kw: object) -> datetime:
    params: dict[str, object] = {"cron": None, "interval_seconds": None, "daily_time": None, "timezone": "UTC"}
    params.update(kw)
    return next_fire(kind, after=after, **params)  # type: ignore[arg-type]


def test_cron_in_local_time_across_dst() -> None:
    weekday_mornings = {"cron": "45 8 * * 1-5", "timezone": "Europe/London"}
    # Tue 6 Oct 2026, 09:00 BST -> Wed 08:45 BST = 07:45 UTC
    assert fire(ScheduleKind.cron, utc(2026, 10, 6, 8, 0), **weekday_mornings) == utc(2026, 10, 7, 7, 45)
    # Fri 30 Oct (after the clocks went back) -> Mon 2 Nov 08:45 GMT = 08:45 UTC
    assert fire(ScheduleKind.cron, utc(2026, 10, 30, 12, 0), **weekday_mornings) == utc(2026, 11, 2, 8, 45)
    result = fire(ScheduleKind.cron, utc(2026, 10, 6, 8, 0), **weekday_mornings)
    assert result.utcoffset() is not None and result.utcoffset().total_seconds() == 0  # type: ignore[union-attr]


def test_cron_is_strictly_after() -> None:
    assert fire(ScheduleKind.cron, utc(2026, 1, 1, 0, 0), cron="0 * * * *") == utc(2026, 1, 1, 1, 0)


def test_interval_anchored() -> None:
    anchor = utc(2026, 10, 6, 0, 0)
    assert fire(ScheduleKind.interval, utc(2026, 10, 6, 1, 30), interval_seconds=3600, anchor=anchor) == utc(
        2026, 10, 6, 2, 0
    )
    assert fire(ScheduleKind.interval, utc(2026, 10, 6, 2, 0), interval_seconds=3600, anchor=anchor) == utc(
        2026, 10, 6, 3, 0
    )
    future_anchor = utc(2026, 12, 1)
    assert fire(ScheduleKind.interval, utc(2026, 10, 6), interval_seconds=60, anchor=future_anchor) == future_anchor
    # Without an anchor the interval counts from `after`.
    assert fire(ScheduleKind.interval, utc(2026, 10, 6, 5, 0), interval_seconds=900) == utc(2026, 10, 6, 5, 15)


def test_daily_at_local_time_across_dst() -> None:
    ny = {"daily_time": "09:00", "timezone": "America/New_York"}
    assert fire(ScheduleKind.daily, utc(2026, 10, 6, 12, 0), **ny) == utc(2026, 10, 6, 13, 0)  # 08:00 EDT
    assert fire(ScheduleKind.daily, utc(2026, 10, 6, 13, 0), **ny) == utc(2026, 10, 7, 13, 0)  # exactly 09:00
    assert fire(ScheduleKind.daily, utc(2026, 10, 31, 14, 0), **ny) == utc(2026, 11, 1, 14, 0)  # EST after 1 Nov
    tokyo = {"daily_time": "07:30", "timezone": "Asia/Tokyo"}
    assert fire(ScheduleKind.daily, utc(2026, 10, 6, 23, 0), **tokyo) == utc(2026, 10, 7, 22, 30)


@pytest.mark.parametrize(
    ("kind", "kw", "field"),
    [
        (ScheduleKind.cron, {"cron": "61 * * * *"}, "cron"),
        (ScheduleKind.cron, {"cron": None}, "cron"),
        (ScheduleKind.interval, {"interval_seconds": 30}, "interval_seconds"),
        (ScheduleKind.daily, {"daily_time": "25:00"}, "daily_time"),
        (ScheduleKind.daily, {"daily_time": "09:00", "timezone": "Mars/Olympus"}, "timezone"),
    ],
)
def test_validation(kind: ScheduleKind, kw: dict[str, object], field: str) -> None:
    params: dict[str, object] = {"cron": None, "interval_seconds": None, "daily_time": None, "timezone": "UTC"}
    params.update(kw)
    with pytest.raises(ValidationFailed) as info:
        validate_schedule(kind, **params)  # type: ignore[arg-type]
    assert info.value.details["fields"][0]["field"] == field
