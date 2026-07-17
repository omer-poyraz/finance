"""Collector item models."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class NewsItem:
    """Normalized news article item."""

    title: str
    url: str
    source: str
    published_at: datetime | None = None
    summary: str | None = None


@dataclass(frozen=True, slots=True)
class AnnouncementItem:
    """Normalized KAP announcement item."""

    title: str
    url: str
    source: str
    symbol: str | None = None
    published_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MarketQuote:
    """Normalized market snapshot item."""

    symbol: str
    name: str
    source: str
    last_price: float | None = None
    change_percent: float | None = None
    volume: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    previous_close: float | None = None
    market_cap: float | None = None
    timestamp: str | None = None
    ticker: str | None = None
    company_name: str | None = None
    current_price: float | None = None
    daily_change_percent: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
