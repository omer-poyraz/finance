"""Rule-based halal filtering for equities."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class HalalFilterResult:
    """Output of halal filtering."""

    allowed_items: list[dict[str, Any]]
    rejected_items: list[dict[str, Any]]


class HalalFilterEngine:
    """Filter out equities that do not pass halal constraints."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    def filter_market_items(self, items: list[dict[str, Any]]) -> HalalFilterResult:
        allowed: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []

        for item in items:
            if self._is_halal(item):
                allowed.append(item)
            else:
                rejected.append(item)

        return HalalFilterResult(allowed_items=allowed, rejected_items=rejected)

    def _is_halal(self, item: dict[str, Any]) -> bool:
        ticker = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
        name = str(item.get("name") or item.get("company_name") or "").strip().lower()
        sector = str(item.get("sector") or item.get("industry") or "").strip().lower()

        blocked_tickers = {str(value).strip().upper() for value in self._config.get("blocked_tickers", [])}
        if ticker and ticker in blocked_tickers:
            return False

        blocked_keywords = [str(value).strip().lower() for value in self._config.get("blocked_keywords", [])]
        for keyword in blocked_keywords:
            if keyword and (keyword in name or keyword in sector):
                return False

        blocked_sectors = [str(value).strip().lower() for value in self._config.get("blocked_sectors", [])]
        for keyword in blocked_sectors:
            if keyword and keyword in sector:
                return False

        return True
