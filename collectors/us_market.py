"""US market collector using Yahoo Finance chart endpoint."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from typing import Any

import requests

from collectors.base_collector import BaseCollector
from collectors.base_collector import CollectorResult
from collectors.models import MarketQuote
from config import settings
from shared.exceptions import DataCollectionError


class UsMarketCollector(BaseCollector[MarketQuote]):
    """Collect selected US stock quotes for multi-market analysis."""

    collector_name = "us_market"
    source_name = "US"
    _yahoo_chart_url = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

    def collect(self) -> CollectorResult[MarketQuote]:
        symbols = settings.us_market_ticker_list
        if not symbols:
            self._record_success()
            return self._build_result(items=[], metadata={"count": 0, "reason": "no_symbols"})

        quotes: list[MarketQuote] = []
        errors: list[str] = []

        for symbol in symbols:
            try:
                quote = self._fetch_symbol(symbol)
                if quote is not None:
                    quotes.append(quote)
            except DataCollectionError as exc:
                errors.append(str(exc))

        if quotes:
            self._record_success()
            return self._build_result(
                items=quotes,
                metadata={"count": len(quotes), "errors": errors},
            )

        self._record_failure("US market data collection failed")
        return self._build_result(
            items=[],
            metadata={"count": 0, "errors": errors},
            success=False,
            error="US market data collection failed",
        )

    def _fetch_symbol(self, symbol: str) -> MarketQuote | None:
        url = self._yahoo_chart_url.format(symbol=symbol.upper())
        try:
            response = self._session.get(url, timeout=self._timeout_seconds, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise DataCollectionError(f"US quote request failed for {symbol}: {exc}") from exc
        except ValueError as exc:
            raise DataCollectionError(f"US quote parse failed for {symbol}: {exc}") from exc

        result = (((payload.get("chart") or {}).get("result") or [None])[0]) or {}
        meta = dict(result.get("meta") or {})
        indicators = dict(result.get("indicators") or {})
        quote_rows = (indicators.get("quote") or [{}])[0]

        def _last_float(values: list[Any]) -> float | None:
            for value in reversed(values or []):
                try:
                    if value is None:
                        continue
                    return float(value)
                except (TypeError, ValueError):
                    continue
            return None

        close_price = _last_float(quote_rows.get("close", []))
        if close_price is None:
            close_price = self._safe_float(meta.get("regularMarketPrice"))
        if close_price is None:
            return None

        open_price = _last_float(quote_rows.get("open", []))
        high_price = _last_float(quote_rows.get("high", []))
        low_price = _last_float(quote_rows.get("low", []))
        volume = _last_float(quote_rows.get("volume", []))
        previous_close = self._safe_float(meta.get("previousClose"))

        if open_price is None:
            open_price = close_price
        if high_price is None:
            high_price = max(open_price, close_price)
        if low_price is None:
            low_price = min(open_price, close_price)
        if volume is None:
            volume = 0.0

        change_percent = None
        if previous_close and previous_close > 0:
            change_percent = ((close_price - previous_close) / previous_close) * 100.0

        company_name = str(meta.get("longName") or meta.get("shortName") or symbol.upper())
        timestamp = datetime.now(UTC).isoformat()

        return MarketQuote(
            symbol=symbol.upper(),
            name=company_name,
            source=self.source_name,
            last_price=close_price,
            change_percent=change_percent,
            volume=volume,
            open=open_price,
            high=high_price,
            low=low_price,
            previous_close=previous_close,
            market_cap=self._safe_float(meta.get("marketCap")),
            timestamp=timestamp,
            ticker=symbol.upper(),
            company_name=company_name,
            current_price=close_price,
            daily_change_percent=change_percent,
            metadata={"market": "US", "provider": "yahoo"},
        )

    def _safe_float(self, value: Any) -> float | None:
        try:
            if value is None:
                return None
            return float(value)
        except (TypeError, ValueError):
            return None
