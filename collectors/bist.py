
"""Market collector for BIST snapshots and table-based market views."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from io import StringIO
import re
from typing import Any

import pandas as pd
from bs4 import BeautifulSoup
import requests

from collectors.base_collector import BaseCollector
from collectors.base_collector import CollectorResult
from collectors.models import MarketQuote
from config import settings
from shared.exceptions import DataCollectionError


class MarketCollector(BaseCollector[MarketQuote]):
	"""Collect market table data from a public BIST page."""

	collector_name = "market"
	source_name = "BIST"
	_tradingview_scan_url = "https://scanner.tradingview.com/turkey/scan"
	_ticker_pattern = re.compile(r"^[A-Z0-9]{3,6}$")

	def collect(self) -> CollectorResult[MarketQuote]:
		errors: list[str] = []

		for strategy in (self._collect_from_tradingview, self._collect_from_table_source):
			try:
				quotes, metadata = strategy()
				if quotes:
					deduped, skipped_duplicates = self._dedupe_quotes(quotes)
					metadata["count"] = len(deduped)
					metadata["skipped_duplicates"] = skipped_duplicates
					self._record_success()
					return self._build_result(items=deduped, metadata=metadata)
			except DataCollectionError as exc:
				errors.append(str(exc))

		fallback = self._fallback_quotes("")
		metadata = {
			"selected_source": "fallback",
			"count": len(fallback),
			"skipped_duplicates": 0,
			"errors": errors,
		}
		self._record_failure("All market sources failed. Fallback quote used.")
		return self._build_result(items=fallback, metadata=metadata)

	def _collect_from_tradingview(self) -> tuple[list[MarketQuote], dict[str, Any]]:
		payload = {
			"filter": [
				{"left": "exchange", "operation": "equal", "right": "BIST"},
				{"left": "type", "operation": "equal", "right": "stock"},
			],
			"options": {"lang": "tr"},
			"symbols": {"query": {"types": []}, "tickers": []},
			"columns": [
				"name",
				"description",
				"close",
				"open",
				"high",
				"low",
				"prev_close",
				"volume",
				"change",
				"market_cap_basic",
			],
		}

		try:
			response = self._session.post(
				self._tradingview_scan_url,
				json=payload,
				timeout=self._timeout_seconds,
				headers={"User-Agent": "Mozilla/5.0"},
			)
			response.raise_for_status()
			raw_payload = response.json()
		except requests.RequestException as exc:
			raise DataCollectionError(f"tradingview scanner request failed: {exc}") from exc
		except ValueError as exc:
			raise DataCollectionError(f"tradingview scanner json parse failed: {exc}") from exc

		rows = raw_payload.get("data", [])
		if not isinstance(rows, list) or not rows:
			raise DataCollectionError("tradingview scanner returned no BIST stock rows")

		timestamp = datetime.now(UTC).isoformat()
		quotes: list[MarketQuote] = []
		skipped_invalid = 0

		for row in rows:
			if not isinstance(row, dict):
				skipped_invalid += 1
				continue

			symbol_ref = row.get("s")
			data = row.get("d", [])
			if not isinstance(data, list):
				skipped_invalid += 1
				continue

			ticker = self._normalize_ticker(data[0] if len(data) > 0 else symbol_ref)
			if not ticker:
				skipped_invalid += 1
				continue

			company_name = str(data[1]).strip() if len(data) > 1 and data[1] else ticker
			current_price = self._to_float(data[2] if len(data) > 2 else None)
			open_price = self._to_float(data[3] if len(data) > 3 else None)
			high_price = self._to_float(data[4] if len(data) > 4 else None)
			low_price = self._to_float(data[5] if len(data) > 5 else None)
			previous_close = self._to_float(data[6] if len(data) > 6 else None)
			volume = self._to_float(data[7] if len(data) > 7 else None)
			daily_change_percent = self._to_float(data[8] if len(data) > 8 else None)
			market_cap = self._to_float(data[9] if len(data) > 9 else None)

			if current_price is None:
				skipped_invalid += 1
				continue

			quotes.append(
				MarketQuote(
					symbol=ticker,
					name=company_name,
					source=self.source_name,
					last_price=current_price,
					change_percent=daily_change_percent,
					volume=volume,
					open=open_price,
					high=high_price,
					low=low_price,
					previous_close=previous_close,
					market_cap=market_cap,
					timestamp=timestamp,
					ticker=ticker,
					company_name=company_name,
					current_price=current_price,
					daily_change_percent=daily_change_percent,
					metadata={
						"provider": "tradingview",
						"raw_symbol": str(symbol_ref or ""),
					},
				)
			)

		if not quotes:
			raise DataCollectionError("tradingview scanner yielded no valid market quotes")

		metadata = {
			"selected_source": "tradingview_scanner",
			"source_url": self._tradingview_scan_url,
			"raw_rows": len(rows),
			"skipped_records": skipped_invalid,
		}
		return quotes, metadata

	def _collect_from_table_source(self) -> tuple[list[MarketQuote], dict[str, Any]]:
		response = self._request(settings.market_source_url)
		quotes = self._parse_quotes(response.text)
		if not quotes:
			raise DataCollectionError("table source returned no market quotes")

		metadata = {
			"selected_source": "table_parser",
			"source_url": settings.market_source_url,
			"raw_rows": len(quotes),
			"skipped_records": 0,
		}
		return quotes, metadata

	def _parse_quotes(self, html: str) -> list[MarketQuote]:
		tables = self._read_tables(html)
		if tables:
			parsed = self._parse_table_rows(tables)
			if parsed:
				return parsed
		return self._fallback_quotes(html)

	def _read_tables(self, html: str) -> list[pd.DataFrame]:
		try:
			return pd.read_html(StringIO(html))
		except ValueError:
			return []

	def _parse_table_rows(self, tables: list[pd.DataFrame]) -> list[MarketQuote]:
		quotes: list[MarketQuote] = []

		for table in tables:
			normalized = table.copy()
			normalized.columns = [str(column).strip() for column in normalized.columns]
			for _, row in normalized.head(25).iterrows():
				row_data = {str(key): self._normalize_value(value) for key, value in row.items()}
				quote = self._build_quote_from_row(row_data)
				if quote is not None:
					quotes.append(quote)

			if quotes:
				break

		return quotes

	def _build_quote_from_row(self, row_data: dict[str, Any]) -> MarketQuote | None:
		values = [str(value).strip() for value in row_data.values() if str(value).strip()]
		if not values:
			return None

		symbol = self._normalize_ticker(self._find_symbol(row_data) or values[0])
		if not symbol:
			return None

		name = self._find_name(row_data) or symbol
		last_price = self._find_float(row_data, ["last", "price", "close", "son", "fiyat"])
		change_percent = self._find_float(row_data, ["change", "%", "değiş", "degis"])
		volume = self._find_float(row_data, ["volume", "hacim", "lot"])
		open_price = self._find_float(row_data, ["open", "açılış", "acilis"])
		high_price = self._find_float(row_data, ["high", "yüksek", "yuksek"])
		low_price = self._find_float(row_data, ["low", "düşük", "dusuk"])
		previous_close = self._find_float(row_data, ["prev", "önceki", "onceki", "kapanış", "kapanis"])
		market_cap = self._find_float(row_data, ["market cap", "piyasa değeri", "piyasa degeri"])
		timestamp = datetime.now(UTC).isoformat()

		if last_price is None:
			return None

		return MarketQuote(
			symbol=symbol,
			name=name,
			source=self.source_name,
			last_price=last_price,
			change_percent=change_percent,
			volume=volume,
			open=open_price,
			high=high_price,
			low=low_price,
			previous_close=previous_close,
			market_cap=market_cap,
			timestamp=timestamp,
			ticker=symbol,
			company_name=name,
			current_price=last_price,
			daily_change_percent=change_percent,
			metadata=row_data,
		)

	def _find_symbol(self, row_data: dict[str, Any]) -> str | None:
		for key, value in row_data.items():
			if any(token in key.lower() for token in ["symbol", "kod", "hisse", "sembol"]):
				text = str(value).strip()
				if text:
					return text
		return None

	def _find_name(self, row_data: dict[str, Any]) -> str | None:
		for key, value in row_data.items():
			if any(token in key.lower() for token in ["name", "ad", "şirket", "sirket"]):
				text = str(value).strip()
				if text:
					return text
		return None

	def _find_float(self, row_data: dict[str, Any], keywords: list[str]) -> float | None:
		for key, value in row_data.items():
			if any(keyword in key.lower() for keyword in keywords):
				normalized = self._to_float(value)
				if normalized is not None:
					return normalized
		return None

	def _normalize_value(self, value: Any) -> Any:
		if pd.isna(value):
			return None
		return value

	def _to_float(self, value: Any) -> float | None:
		if value is None:
			return None

		text = str(value).replace("\u00a0", " ").replace("%", "").strip()
		if not text or text in {"-", "--", "nan", "None"}:
			return None

		text = text.replace(" ", "")
		if "," in text and "." in text:
			if text.rfind(",") > text.rfind("."):
				text = text.replace(".", "").replace(",", ".")
			else:
				text = text.replace(",", "")
		elif "," in text:
			left, right = text.split(",", 1)
			if len(right) <= 2:
				text = left.replace(".", "") + "." + right
			else:
				text = text.replace(",", "")

		try:
			return float(text)
		except ValueError:
			return None

	def _normalize_ticker(self, value: Any) -> str | None:
		if value is None:
			return None

		candidate = str(value).strip().upper()
		if not candidate:
			return None

		if ":" in candidate:
			candidate = candidate.split(":")[-1]
		if "." in candidate:
			candidate = candidate.split(".")[0]

		candidate = candidate.replace("BIST", "")
		candidate = re.sub(r"[^A-Z0-9]", "", candidate)
		if not candidate:
			return None

		if not self._ticker_pattern.match(candidate):
			return None

		return candidate

	def _dedupe_quotes(self, quotes: list[MarketQuote]) -> tuple[list[MarketQuote], int]:
		unique: list[MarketQuote] = []
		seen: set[str] = set()
		skipped = 0

		for quote in quotes:
			normalized = self._normalize_ticker(quote.symbol)
			if not normalized or normalized in seen:
				skipped += 1
				continue
			seen.add(normalized)
			unique.append(quote)

		return unique, skipped

	def _fallback_quotes(self, html: str) -> list[MarketQuote]:
		soup = BeautifulSoup(html, "html.parser")
		title = soup.title.get_text(" ", strip=True) if soup.title else "BIST 100"
		timestamp = datetime.now(UTC).isoformat()

		return [
			MarketQuote(
				symbol="XU100",
				name=title,
				source=self.source_name,
				last_price=100.0,
				change_percent=0.0,
				volume=0.0,
				open=100.0,
				high=101.0,
				low=99.0,
				previous_close=100.0,
				market_cap=None,
				timestamp=timestamp,
				ticker="XU100",
				company_name=title,
				current_price=100.0,
				daily_change_percent=0.0,
				metadata={"mode": "fallback", "source_url": settings.market_source_url},
			)
		]


BistCollector = MarketCollector

