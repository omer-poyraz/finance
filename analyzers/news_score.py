
"""Rule-based news intelligence analyzer."""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
import unicodedata
import re
from typing import Any

from analyzers.base import BaseAnalyzer
from collectors.models import NewsItem
from shared.exceptions import AnalysisError
from shared.normalization import build_item_id
from shared.normalization import normalize_text


TICKER_PATTERN = re.compile(r"\b[A-ZÇĞİÖŞÜ]{4,5}\b")


DEFAULT_TICKER_ALIASES: dict[str, list[str]] = {
	"THYAO": ["türk hava yolları", "thy", "thyao", "turkish airlines"],
	"SISE": ["şişecam", "sisecam", "trakya cam", "anadolu cam", "paşabahçe"],
	"ASELS": ["aselsan", "asels", "aseisan"],
	"KCHOL": ["koç holding", "koc holding", "koç"],
	"FROTO": ["ford otosan", "ford otomotiv"],
	"EREGL": ["ereğli", "eregli", "erdemir"],
	"AKBNK": ["akbank", "ak bank"],
	"GARAN": ["garanti", "garanti bbva"],
	"TUPRS": ["tüpraş", "tupras"],
	"SAHOL": ["sabancı", "sabanci", "sabancı holding", "hacı ömer sabancı"],
	"BIMAS": ["bim", "bimas", "birleşik mağazalar"],
	"YKBNK": ["yapı kredi", "yapi kredi", "yapikredi"],
	"ISCTR": ["iş bankası", "is bankasi", "isbank"],
	"HALKB": ["halkbank", "halk bankası", "halk bankasi"],
	"VAKBN": ["vakıfbank", "vakifbank"],
	"PGSUS": ["pegasus", "pegasus hava"],
	"TCELL": ["turkcell", "türkcell"],
	"TTKOM": ["türk telekom", "turk telekom", "ttkom"],
	"ENKAI": ["enka", "enka inşaat", "enka insaat"],
	"ALARK": ["alarko"],
	"DOAS": ["doğuş otomotiv", "dogus otomotiv"],
	"TOASO": ["tofaş", "tofas"],
	"ARCLK": ["arçelik", "arcelik"],
	"KOZAL": ["koza altın", "koza altin"],
	"KOZAA": ["koza anadolu"],
	"PETKM": ["petkim"],
	"SASA": ["sasa polyester", "sasa"],
	"HEKTS": ["hektaş", "hektas"],
	"ODAS": ["odaş", "odas enerji"],
	"KRDMD": ["kardemir", "krdmd"],
	"MAVI": ["mavi giyim", "mavi"],
	"MGROS": ["migros", "mgros"],
	"ULKER": ["ülker", "ulker"],
	"CCOLA": ["coca cola içecek", "coca cola icecek", "ccola"],
	"EKGYO": ["emlak konut", "ekgyo"],
	"GUBRF": ["gübretaş", "gubretas"],
	"ISGYO": ["iş gyo", "is gyo"],
	"KONTR": ["kontrolmatik", "kontr"],
	"ASTOR": ["astor enerji", "astor"],
	"CIMSA": ["çimsa", "cimsa"],
	"OYAKC": ["oyak çimento", "oyak cimento"],
	"VESTL": ["vestel"],
	"ZOREN": ["zorlu enerji", "zoren"],
}


class NewsAnalyzer(BaseAnalyzer):
	"""Analyze news sentiment and impact using configurable keyword scores."""

	analyzer_name = "news"

	def __init__(self, keyword_config: Mapping[str, Mapping[str, int]] | None = None) -> None:
		super().__init__()
		self._keyword_config = keyword_config or {"positive": {}, "negative": {}}
		self._ticker_aliases = {
			ticker: sorted(set([ticker.lower(), *[alias.lower() for alias in aliases]]), key=len, reverse=True)
			for ticker, aliases in DEFAULT_TICKER_ALIASES.items()
		}

	def set_keyword_config(self, keyword_config: Mapping[str, Mapping[str, int]]) -> None:
		"""Update keyword scoring configuration at runtime."""

		self._keyword_config = keyword_config

	def set_ticker_alias_map(self, ticker_alias_map: Mapping[str, Sequence[str]]) -> None:
		"""Update ticker-alias mapping used for company name based ticker detection."""

		merged: dict[str, list[str]] = {
			ticker: list(aliases)
			for ticker, aliases in DEFAULT_TICKER_ALIASES.items()
		}

		for ticker, aliases in ticker_alias_map.items():
			normalized_ticker = str(ticker).strip().upper()
			if not normalized_ticker:
				continue
			merged.setdefault(normalized_ticker, [])
			for alias in aliases:
				alias_text = normalize_text(str(alias)).lower()
				if alias_text and alias_text not in merged[normalized_ticker]:
					merged[normalized_ticker].append(alias_text)

		self._ticker_aliases = {
			ticker: sorted(set([ticker.lower(), *aliases]), key=len, reverse=True)
			for ticker, aliases in merged.items()
		}

	def analyze(
		self,
		records: Sequence[dict[str, Any]],
		*,
		already_analyzed_ids: set[str] | None = None,
	) -> list[dict[str, Any]]:
		"""Analyze each news record and return enriched intelligence objects."""

		if not records:
			return []

		seen_ids = already_analyzed_ids or set()
		analyzed_items: list[dict[str, Any]] = []

		for record in records:
			title = normalize_text(str(record.get("title") or ""))
			url = normalize_text(str(record.get("url") or ""))
			summary = normalize_text(str(record.get("summary") or ""))
			if not title or not url:
				continue

			item_id = str(record.get("id") or build_item_id(title, url, str(record.get("source") or "news")))
			if item_id in seen_ids:
				continue

			text_full = normalize_text(f"{title} {summary}")
			text = text_full.lower()
			tickers = self._detect_tickers(text_full)

			positive_scores, positive_reasons = self._match_keywords(
				text,
				self._keyword_config.get("positive", {}),
				positive=True,
			)
			negative_scores, negative_reasons = self._match_keywords(
				text,
				self._keyword_config.get("negative", {}),
				positive=False,
			)

			matched_keywords = [*positive_scores.keys(), *negative_scores.keys()]
			net_score = 50 + sum(positive_scores.values()) + sum(negative_scores.values())
			sentiment_score = int(round(self._clamp_score(net_score)))
			confidence = self._confidence(sentiment_score, matched_keywords, tickers)
			importance_score = self._importance_score(matched_keywords, tickers)
			sentiment = self._sentiment(sentiment_score)

			reasons = [*positive_reasons, *negative_reasons]
			if tickers:
				reasons.append(f"Detected ticker(s): {', '.join(tickers)}")
			if not reasons:
				reasons.append("No matched keyword signal")

			analyzed_items.append(
				{
					"id": item_id,
					"ticker": tickers,
					"sentiment": sentiment,
					"score": sentiment_score,
					"confidence": confidence,
					"importance": self._importance_label(importance_score),
					"importance_score": importance_score,
					"matched_keywords": matched_keywords,
					"reasons": reasons,
				}
			)
			seen_ids.add(item_id)

		return analyzed_items

	def score(self, news_items: Sequence[NewsItem]) -> float:
		"""Return aggregate sentiment score (0-100) for compatibility."""

		if not news_items:
			raise AnalysisError("NewsAnalyzer requires at least one news item")

		records = [
			{
				"title": item.title,
				"url": item.url,
				"summary": item.summary or "",
				"source": item.source,
			}
			for item in news_items
		]
		analyzed = self.analyze(records)
		if not analyzed:
			raise AnalysisError("NewsAnalyzer could not analyze provided news items")

		total = sum(float(item["score"]) for item in analyzed)
		return self._clamp_score(total / len(analyzed))

	def _match_keywords(
		self,
		text: str,
		keywords: Mapping[str, int],
		*,
		positive: bool,
	) -> tuple[dict[str, int], list[str]]:
		matched: dict[str, int] = {}
		reasons: list[str] = []

		for keyword, value in keywords.items():
			normalized_keyword = normalize_text(str(keyword)).lower()
			if normalized_keyword and normalized_keyword in text:
				numeric_value = int(value)
				matched[normalized_keyword] = numeric_value
				prefix = "Positive" if positive else "Negative"
				reasons.append(f"{prefix} keyword: {normalized_keyword}")

		return matched, reasons

	def _sentiment(self, score: int) -> str:
		if score >= 55:
			return "Positive"
		if score <= 45:
			return "Negative"
		return "Neutral"

	def _confidence(self, score: int, keywords: list[str], tickers: list[str]) -> int:
		base = 55
		strength = abs(score - 50)
		confidence = base + strength + (len(keywords) * 4) + (len(tickers) * 3)
		return int(self._clamp_score(confidence))

	def _importance_score(self, keywords: list[str], tickers: list[str]) -> int:
		score = 25 + (len(keywords) * 10) + (len(tickers) * 8)
		return int(self._clamp_score(score))

	def _importance_label(self, score: int) -> str:
		if score >= 75:
			return "High"
		if score >= 45:
			return "Medium"
		return "Low"

	def _detect_tickers(self, text: str) -> list[str]:
		detected: set[str] = set()
		upper_text = text.upper()
		for token in TICKER_PATTERN.findall(upper_text):
			normalized = self._normalize_ascii(token)
			if normalized in {"KVKK", "BIST", "KAP", "SPK", "MKK", "VIOP"}:
				continue
			detected.add(normalized)

		ascii_text = self._normalize_ascii(text)
		for ticker, aliases in self._ticker_aliases.items():
			for alias in aliases:
				alias_ascii = self._normalize_ascii(alias)
				if not alias_ascii:
					continue
				if f" {alias_ascii} " in f" {ascii_text} ":
					detected.add(ticker)
					break

		return sorted(detected)

	def _normalize_ascii(self, value: str) -> str:
		decomposed = unicodedata.normalize("NFKD", value)
		ascii_only = decomposed.encode("ascii", "ignore").decode("ascii")
		return normalize_text(ascii_only).upper()

