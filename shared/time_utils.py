"""Shared timezone formatting helpers."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from zoneinfo import ZoneInfo


ISTANBUL_TZ = ZoneInfo("Europe/Istanbul")


def now_istanbul() -> datetime:
    """Return the current time in Europe/Istanbul."""

    return datetime.now(UTC).astimezone(ISTANBUL_TZ)


def to_istanbul_datetime(value: datetime | None = None) -> datetime:
    """Convert a datetime to Europe/Istanbul, defaulting to now."""

    if value is None:
        return now_istanbul()
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).astimezone(ISTANBUL_TZ)
    return value.astimezone(ISTANBUL_TZ)


def format_istanbul_datetime(value: datetime | None = None, *, pattern: str = "%d.%m.%Y %H:%M") -> str:
    """Format a datetime using Europe/Istanbul timezone."""

    return to_istanbul_datetime(value).strftime(pattern)
