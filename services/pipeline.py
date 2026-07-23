"""End-to-end pipeline service for collection, analysis, recommendations, and storage."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import UTC
from datetime import datetime
import json
import logging
import math
import time
from typing import Any

import pandas as pd

from analyzers import FinancialAnalyzer
from analyzers import NewsAnalyzer
from analyzers import RiskAnalyzer
from analyzers import TechnicalAnalyzer
from collectors import CollectorManager
from collectors import KapCollector
from collectors import MarketCollector
from collectors import NewsCollector
from collectors import UsMarketCollector
from collectors.models import NewsItem
from config import settings
from decision import BistOpportunityEngine
from decision import DecisionEngine
from engines import CapitalAllocationEngine
from engines import FundamentalEngine
from engines import HalalFilterEngine
from engines import MarketIntelligenceEngine
from engines import PortfolioEngine
from engines import TechnicalEngine
from engines import TrendEngine
from indicators import atr
from indicators import bollinger_bands
from indicators import ema
from indicators import gap_detection
from indicators import macd
from indicators import rsi
from indicators import sma
from indicators import volume_analysis
from notifier import TelegramNotifier
from services.gemini_service import GeminiService
from shared.normalization import build_item_id
from shared.normalization import normalize_records
from shared.time_utils import format_istanbul_datetime
from storage import JsonStorage


logger = logging.getLogger(__name__)

MIN_EXPECTED_GAIN_PCT = 3.0
TARGET_EXPECTED_GAIN_PCT = 10.0


REQUIRED_STORAGE_FILES = [
    "news.json",
    "kap.json",
    "market.json",
    "analysis.json",
    "news_analysis.json",
    "ticker_news_summary.json",
    "market_analysis.json",
    "recommendations.json",
    "history.json",
    "performance.json",
    "portfolio.json",
    "portfolio_analysis.json",
    "bist_recommendations.json",
    "bist_scoring_log.json",
    "bist_opportunity_state.json",
    "bist_notification_history.json",
    "bist_live_summary.json",
    "us_recommendations.json",
]


DEFAULT_NEWS_KEYWORDS: dict[str, dict[str, int]] = {
    "positive": {
        "ihale": 35,
        "yatırım": 25,
        "kapasite artışı": 28,
        "geri alım": 25,
        "temettü": 24,
        "bedelsiz": 35,
        "yeni sözleşme": 30,
        "teşvik": 18,
        "kontrat": 26,
        "record kar": 28,
        "rekor kar": 28,
        "yeni fabrika": 24,
        "yabancı yatırım": 26,
        "new order": 22,
        "hükümet projesi": 24,
        "hukumet projesi": 24,
        "sipariş": 18,
        "siparis": 18,
    },
    "negative": {
        "sermaye azaltımı": -40,
        "konkordato": -100,
        "iflas": -100,
        "ceza": -70,
        "zarar": -30,
        "dava": -25,
        "kredi notu düşürüldü": -35,
        "soruşturma": -45,
        "sorusturma": -45,
        "deprem hasarı": -55,
        "deprem hasari": -55,
        "üretim duruşu": -60,
        "uretim durusu": -60,
        "yangın": -55,
        "yangin": -55,
        "zarar açıkladı": -38,
        "zarar acikladi": -38,
    },
}


DEFAULT_TECHNICAL_SCORING: dict[str, int] = {
    "ema_cross": 20,
    "macd_cross": 20,
    "gap": 20,
    "volume": 15,
    "rsi": 15,
    "trend": 10,
}


DEFAULT_HALAL_FILTER: dict[str, list[str]] = {
    "blocked_tickers": [
        "AKBNK",
        "GARAN",
        "ISCTR",
        "HALKB",
        "VAKBN",
        "YKBNK",
        "TSKB",
        "ALBRK",
        "QNBFB",
        "SKBNK",
        "JPM",
        "BAC",
        "WFC",
        "C",
        "GS",
        "MS",
    ],
    "blocked_keywords": [
        "bank",
        "finance",
        "financial",
        "alcohol",
        "beer",
        "casino",
        "gambling",
        "bet",
    ],
    "blocked_sectors": [
        "banking",
        "financial services",
        "alcoholic beverages",
        "gambling",
    ],
}


class FinancePipelineService:
    """Run the complete local data-to-recommendation pipeline."""

    def __init__(self) -> None:
        self.storage = JsonStorage(settings.storage_data_dir)
        self.storage.ensure_default_files(REQUIRED_STORAGE_FILES)
        self.config_storage = JsonStorage("storage/config")
        self._runtime_cache: dict[str, Any] = {}
        self._ensure_news_keyword_config()
        self._ensure_technical_scoring_config()
        self._ensure_halal_filter_config()
        self._ensure_bist_scoring_config()
        self._ensure_portfolio_file()

        self.collector_manager = CollectorManager()
        self.collector_manager.register(NewsCollector())
        self.collector_manager.register(KapCollector())
        self.collector_manager.register(MarketCollector())
        self.collector_manager.register(UsMarketCollector())

        self.news_analyzer = NewsAnalyzer(self._load_news_keyword_config())
        self.technical_analyzer = TechnicalAnalyzer()
        self.risk_analyzer = RiskAnalyzer()
        self.financial_analyzer = FinancialAnalyzer()
        self.decision_engine = DecisionEngine()
        self.gemini_service = GeminiService()

        self.bist_opportunity_engine = BistOpportunityEngine(self._load_bist_scoring_config())

        self.halal_filter_engine = HalalFilterEngine(self._load_halal_filter_config())
        self.technical_engine = TechnicalEngine()
        self.fundamental_engine = FundamentalEngine()
        self.market_intelligence_engine = MarketIntelligenceEngine()
        self.trend_engine = TrendEngine()
        self.capital_allocation_engine = CapitalAllocationEngine()
        self.portfolio_engine = PortfolioEngine()

        self.telegram_notifier = TelegramNotifier()

    def collect_news(self) -> list[dict[str, Any]]:
        """Collect and persist normalized news records."""

        try:
            result = self.collector_manager.collect_one("news")
            payload: list[dict[str, Any]] = []
            for item in result.items:
                row = asdict(item)
                summary_raw = str(row.get("summary") or "").strip()
                metadata: dict[str, Any] = {}
                if summary_raw:
                    try:
                        metadata = dict(json.loads(summary_raw))
                    except json.JSONDecodeError:
                        metadata = {}

                publish_date = str(metadata.get("publish_date") or row.get("published_at") or "")
                row.update(
                    {
                        "source": str(row.get("source") or metadata.get("source") or "news"),
                        "published_at": publish_date,
                        "publish_date": publish_date,
                        "company_names": list(metadata.get("company_names") or []),
                        "ticker_candidates": list(metadata.get("ticker_candidates") or []),
                        "detected_tickers": list(metadata.get("detected_tickers") or []),
                    }
                )
                payload.append(row)

            normalized = normalize_records(payload, required_keys=["title", "url"], source="news")
            self._save_if_changed("news.json", normalized)
            return normalized
        except Exception as exc:
            logger.exception("News collection failed: %s", exc)
            if settings.live_only_mode:
                return list(self._runtime_cache.get("news.json") or [])
            existing = self._load_cached("news.json", default=[])
            self._save_if_changed("news.json", existing)
            return existing

    def collect_kap(self) -> list[dict[str, Any]]:
        """Collect and persist normalized KAP records."""

        try:
            result = self.collector_manager.collect_one("kap")
            payload = [asdict(item) for item in result.items]
            normalized = normalize_records(payload, required_keys=["title", "url"], source="kap")
            self._save_if_changed("kap.json", normalized)
            return normalized
        except Exception as exc:
            logger.exception("KAP collection failed: %s", exc)
            if settings.live_only_mode:
                return list(self._runtime_cache.get("kap.json") or [])
            existing = self._load_cached("kap.json", default=[])
            self._save_if_changed("kap.json", existing)
            return existing

    def collect_market(self, *, markets: list[str] | None = None) -> list[dict[str, Any]]:
        """Collect and persist normalized market records."""

        try:
            selected_markets = {self._normalize_market_name(item) for item in (markets or settings.market_list)}
            payload: list[dict[str, Any]] = []

            if "BIST" in selected_markets:
                result = self.collector_manager.collect_one("market")
                payload.extend(asdict(item) for item in result.items)

            if "US" in selected_markets:
                us_result = self.collector_manager.collect_one("us_market")
                payload.extend(asdict(item) for item in us_result.items)

            for row in payload:
                metadata = dict(row.get("metadata") or {})
                if not metadata.get("market"):
                    metadata["market"] = "BIST"
                row["metadata"] = metadata

            normalized = normalize_records(payload, required_keys=["symbol", "name"], source="market")

            halal_result = self.halal_filter_engine.filter_market_items(normalized)
            allowed = halal_result.allowed_items

            raw_market_counts = self._count_items_by_market(normalized)
            halal_market_counts = self._count_items_by_market(allowed)
            market_scan_stats = self._runtime_cache.setdefault("market_scan_stats", {})
            for market_name in selected_markets:
                if not market_name:
                    continue
                market_scan_stats[market_name] = {
                    "analyzed_total": int(raw_market_counts.get(market_name, 0)),
                    "halal_passed": int(halal_market_counts.get(market_name, 0)),
                }

            configured_markets = {self._normalize_market_name(item) for item in settings.market_list}
            if selected_markets and selected_markets != configured_markets:
                existing_market = self._load_cached("market.json", default=[])
                preserved = [
                    item
                    for item in existing_market
                    if self._normalize_market_name((item.get("metadata") or {}).get("market") or item.get("source"))
                    not in selected_markets
                ]
                allowed = [*preserved, *allowed]

            self._save_if_changed("market.json", allowed)
            return allowed
        except Exception as exc:
            logger.exception("Market collection failed: %s", exc)
            if settings.live_only_mode:
                return list(self._runtime_cache.get("market.json") or [])
            existing = self._load_cached("market.json", default=[])
            self._save_if_changed("market.json", existing)
            return existing

    def collect_all(self) -> dict[str, int]:
        """Collect all sources and persist them to JSON files."""

        news = self.collect_news()
        kap = self.collect_kap()
        market = self.collect_market()
        return {
            "news": len(news),
            "kap": len(kap),
            "market": len(market),
        }

    def analyze(self) -> dict[str, Any]:
        """Compute analyzer scores and persist the analysis payload."""

        news_payload = self._load_cached("news.json", default=[])
        market_payload = self._load_cached("market.json", default=[])

        news_items = [
            NewsItem(
                title=item.get("title", ""),
                url=item.get("url", ""),
                source=item.get("source", "news"),
                summary=item.get("summary"),
            )
            for item in news_payload
            if item.get("title") and item.get("url")
        ]
        news_summary = self.analyze_news()
        news_analysis_items = self._load_cached("news_analysis.json", default=[])
        news_score = self._average_news_score(news_analysis_items)

        frame = self._market_frame(market_payload)

        analysis = {
            "timestamp": datetime.now(UTC).isoformat(),
            "scores": {
                "news": news_score if news_analysis_items else (self.news_analyzer.score(news_items) if news_items else 50.0),
                "technical": self.technical_analyzer.score(frame),
                "risk": self.risk_analyzer.score(frame),
                "financial": self.financial_analyzer.score(self._financial_metrics(frame)),
            },
            "news_intelligence": news_summary,
        }
        analysis["reasons"] = self._analysis_reasons(analysis["scores"])

        self._save_if_changed("analysis.json", analysis)
        return analysis

    def analyze_market(
        self,
        *,
        market: str | None = None,
        market_payload: list[dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        """Build technical intelligence profile for each collected market stock."""

        market_payload = list(market_payload or self.storage.load("market.json", default=[]))
        if not market_payload:
            market_payload = self.collect_market()

        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in market_payload:
            if market:
                item_market = self._normalize_market_name((item.get("metadata") or {}).get("market") or item.get("source"))
                if item_market != self._normalize_market_name(market):
                    continue
            ticker = str(item.get("symbol") or "").strip().upper()
            if not ticker:
                continue
            grouped.setdefault(ticker, []).append(item)

        ticker_news_summary = list(self._runtime_cache.get("ticker_news_summary_live") or [])
        if not ticker_news_summary:
            ticker_news_summary = self._load_cached("ticker_news_summary.json", default=[])
        news_lookup = {
            str(item.get("ticker") or "").strip().upper(): float(item.get("average_news_score") or 50.0)
            for item in ticker_news_summary
            if isinstance(item, dict)
        }
        analysis_items: list[dict[str, Any]] = []

        for ticker, rows in grouped.items():
            frame = self._market_history_frame(rows)
            technical = self.technical_engine.analyze(ticker, frame)
            market_name = str((rows[-1].get("metadata") or {}).get("market") or rows[-1].get("source") or "BIST")
            company_name = str(rows[-1].get("name") or rows[-1].get("company_name") or ticker)
            fundamental = self.fundamental_engine.analyze(
                frame,
                market_cap=float(rows[-1].get("market_cap") or 0.0) or None,
            )
            market_intel = self.market_intelligence_engine.analyze(frame, market_name=market_name)
            trend = self.trend_engine.analyze(
                technical_score=float(technical.get("technical_score") or 0.0),
                market_intelligence_score=float(market_intel.get("market_intelligence_score") or 0.0),
                news_score=float(news_lookup.get(ticker, 50.0)),
                volatility_pct=float(market_intel.get("volatility_pct") or 0.0),
                relative_volume=float(technical.get("relative_volume") or 1.0),
                trend_label=str(technical.get("trend") or "Neutral"),
            )

            merged = {
                **technical,
                **fundamental,
                **market_intel,
                **trend,
                **self._timeframe_snapshot(frame),
                "market": market_name,
                "company_name": company_name,
                "news_score": round(float(news_lookup.get(ticker, 50.0)), 2),
                "candles": self._candles_from_frame(frame, limit=260),
                "candles_hourly": self._candles_from_frame(frame.tail(120), limit=120),
                "candles_daily": self._candles_from_frame(frame.tail(260), limit=260),
            }
            analysis_items.append(merged)
        if market is None:
            self._save_if_changed("market_analysis.json", analysis_items)
            self._runtime_cache["market_analysis_live"] = list(analysis_items)
        else:
            normalized_market = self._normalize_market_name(market)
            existing_analysis = self._load_cached("market_analysis.json", default=[])
            merged_analysis = [
                item
                for item in existing_analysis
                if self._normalize_market_name(item.get("market") or "") != normalized_market
            ]
            merged_analysis.extend(analysis_items)
            self._save_if_changed("market_analysis.json", merged_analysis)
            self._runtime_cache.setdefault("market_analysis_live_by_market", {})[normalized_market] = list(analysis_items)
            if normalized_market == "BIST":
                self._save_if_changed("bist_market_analysis.json", analysis_items)
            elif normalized_market == "US":
                self._save_if_changed("us_market_analysis.json", analysis_items)

        bullish = sum(1 for item in analysis_items if item.get("trend") == "Bullish")
        bearish = sum(1 for item in analysis_items if item.get("trend") == "Bearish")
        neutral = sum(1 for item in analysis_items if item.get("trend") == "Neutral")
        return {
            "stocks": len(analysis_items),
            "bullish": bullish,
            "bearish": bearish,
            "neutral": neutral,
        }

    def analyze_news(
        self,
        *,
        news_payload: list[dict[str, Any]] | None = None,
        market_payload: list[dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        """Analyze collected news with configurable keyword intelligence rules."""

        keyword_config = self._load_news_keyword_config()
        self.news_analyzer.set_keyword_config(keyword_config)

        news_payload = list(news_payload or self._load_cached("news.json", default=[]))
        market_payload = list(market_payload or self._load_cached("market.json", default=[]))
        self.news_analyzer.set_ticker_alias_map(self._build_ticker_alias_map(market_payload))

        existing_analysis = self._load_cached("news_analysis.json", default=[])
        analyzed_ids = {
            str(item.get("id"))
            for item in existing_analysis
            if isinstance(item, dict) and item.get("id")
        }

        new_items = self.news_analyzer.analyze(news_payload, already_analyzed_ids=analyzed_ids)
        market_payload = list(market_payload or self._load_cached("market.json", default=[]))
        allowed_tickers = {
            str(item.get("symbol") or item.get("ticker") or "").strip().upper()
            for item in market_payload
            if isinstance(item, dict)
        }
        filtered_new_items: list[dict[str, Any]] = []
        for item in new_items:
            tickers = [
                str(value).strip().upper()
                for value in item.get("ticker", [])
                if str(value).strip().upper() in allowed_tickers
            ]
            if not tickers:
                continue
            item["ticker"] = tickers
            item["detected_tickers"] = tickers
            filtered_new_items.append(item)

        if new_items:
            combined = [*existing_analysis, *filtered_new_items]
            self._save_if_changed("news_analysis.json", combined)
        else:
            combined = existing_analysis

        self._runtime_cache["news_analysis_live"] = list(combined)
        self.analyze_tickers(
            news_analysis=combined,
            news_items=news_payload,
            market_payload=market_payload,
        )

        return self._news_summary(combined)

    def analyze_tickers(
        self,
        *,
        news_analysis: list[dict[str, Any]] | None = None,
        news_items: list[dict[str, Any]] | None = None,
        market_payload: list[dict[str, Any]] | None = None,
    ) -> dict[str, int]:
        """Aggregate analyzed news incrementally by ticker and persist ticker summaries."""

        news_analysis = list(news_analysis or self.storage.load("news_analysis.json", default=[]))
        news_items = list(news_items or self.storage.load("news.json", default=[]))
        market_payload = list(market_payload or self.storage.load("market.json", default=[]))
        allowed_tickers = {
            str(item.get("symbol") or item.get("ticker") or "").strip().upper()
            for item in market_payload
            if isinstance(item, dict)
        }
        published_at_by_id = {
            str(item.get("id")): str(item.get("published_at") or item.get("collected_at") or "")
            for item in news_items
            if isinstance(item, dict) and item.get("id")
        }

        existing_summary = self.storage.load("ticker_news_summary.json", default=[])
        summary_by_ticker: dict[str, dict[str, Any]] = {}

        for item in existing_summary:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            summary_by_ticker[ticker] = {
                "id": str(item.get("id") or build_item_id(ticker, "ticker_news_summary")),
                "ticker": ticker,
                "news_count": int(item.get("news_count") or 0),
                "positive_count": int(item.get("positive_count") or 0),
                "negative_count": int(item.get("negative_count") or 0),
                "neutral_count": int(item.get("neutral_count") or 0),
                "score_sum": float(item.get("average_news_score") or 0.0) * int(item.get("news_count") or 0),
                "highest_news_score": float(item.get("highest_news_score") or 0.0),
                "latest_news_date": str(item.get("latest_news_date") or ""),
                "confidence_sum": float(item.get("confidence") or 0.0) * int(item.get("news_count") or 0),
                "keyword_counts": {
                    str(key): int(value)
                    for key, value in dict(item.get("keyword_counts", {})).items()
                },
                "all_reasons": [str(reason) for reason in item.get("all_reasons", [])],
                "processed_news_ids": [
                    str(news_id)
                    for news_id in item.get("processed_news_ids", [])
                    if news_id
                ],
            }

        for item in news_analysis:
            if not isinstance(item, dict):
                continue

            news_id = str(item.get("id") or "")
            tickers = item.get("ticker", [])
            if not news_id or not isinstance(tickers, list) or not tickers:
                continue

            score = float(item.get("score", 50.0))
            sentiment = str(item.get("sentiment", "Neutral"))
            confidence = float(item.get("confidence", 50.0))
            matched_keywords = [str(keyword) for keyword in item.get("matched_keywords", [])]
            reasons = [str(reason) for reason in item.get("reasons", [])]
            latest_news_date = str(published_at_by_id.get(news_id, ""))

            for raw_ticker in tickers:
                ticker = str(raw_ticker or "").strip().upper()
                if not ticker:
                    continue
                if allowed_tickers and ticker not in allowed_tickers:
                    continue

                summary = summary_by_ticker.setdefault(
                    ticker,
                    {
                        "id": build_item_id(ticker, "ticker_news_summary"),
                        "ticker": ticker,
                        "news_count": 0,
                        "positive_count": 0,
                        "negative_count": 0,
                        "neutral_count": 0,
                        "score_sum": 0.0,
                        "highest_news_score": 0.0,
                        "latest_news_date": "",
                        "confidence_sum": 0.0,
                        "keyword_counts": {},
                        "all_reasons": [],
                        "processed_news_ids": [],
                    },
                )

                processed_ids = set(summary["processed_news_ids"])
                if news_id in processed_ids:
                    continue

                summary["processed_news_ids"].append(news_id)
                summary["news_count"] += 1
                summary["score_sum"] += score
                summary["confidence_sum"] += confidence
                summary["highest_news_score"] = max(float(summary["highest_news_score"]), score)

                if sentiment == "Positive":
                    summary["positive_count"] += 1
                elif sentiment == "Negative":
                    summary["negative_count"] += 1
                else:
                    summary["neutral_count"] += 1

                if latest_news_date and (
                    not summary["latest_news_date"] or latest_news_date > str(summary["latest_news_date"])
                ):
                    summary["latest_news_date"] = latest_news_date

                keyword_counts = summary["keyword_counts"]
                for keyword in matched_keywords:
                    normalized_keyword = str(keyword).strip().lower()
                    if not normalized_keyword:
                        continue
                    keyword_counts[normalized_keyword] = int(keyword_counts.get(normalized_keyword, 0)) + 1

                existing_reasons = set(summary["all_reasons"])
                for reason in reasons:
                    if reason and reason not in existing_reasons:
                        summary["all_reasons"].append(reason)
                        existing_reasons.add(reason)

        summaries: list[dict[str, Any]] = []
        for ticker in sorted(summary_by_ticker.keys()):
            item = summary_by_ticker[ticker]
            news_count = max(1, int(item["news_count"]))
            average_news_score = float(item["score_sum"]) / news_count
            average_confidence = float(item["confidence_sum"]) / news_count
            top_keywords = [
                keyword
                for keyword, _ in sorted(
                    item["keyword_counts"].items(),
                    key=lambda pair: (-pair[1], pair[0]),
                )[:3]
            ]

            summaries.append(
                {
                    "id": str(item["id"]),
                    "ticker": ticker,
                    "news_count": int(item["news_count"]),
                    "positive_count": int(item["positive_count"]),
                    "negative_count": int(item["negative_count"]),
                    "neutral_count": int(item["neutral_count"]),
                    "average_news_score": round(average_news_score, 2),
                    "highest_news_score": round(float(item["highest_news_score"]), 2),
                    "latest_news_date": str(item["latest_news_date"]),
                    "overall_news_sentiment": self._sentiment_from_score(average_news_score),
                    "confidence": int(round(max(0.0, min(100.0, average_confidence)))),
                    "top_keywords": top_keywords,
                    "all_reasons": list(item["all_reasons"]),
                    "keyword_counts": dict(item["keyword_counts"]),
                    "processed_news_ids": list(item["processed_news_ids"]),
                }
            )

        self._save_if_changed("ticker_news_summary.json", summaries)
        self._runtime_cache["ticker_news_summary_live"] = list(summaries)

        positive = sum(1 for item in summaries if item.get("overall_news_sentiment") == "Positive")
        negative = sum(1 for item in summaries if item.get("overall_news_sentiment") == "Negative")
        neutral = sum(1 for item in summaries if item.get("overall_news_sentiment") == "Neutral")

        return {
            "tickers": len(summaries),
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
        }

    def generate_recommendations(self, *, market: str | None = None) -> list[dict[str, Any]]:
        """Build recommendation list and persist to JSON storage."""

        started_at = time.perf_counter()
        normalized_market = self._normalize_market_name(market or "")
        if normalized_market == "BIST":
            return self._generate_bist_recommendations(started_at=started_at)

        self.analyze_news()
        self.analyze_market(market=market)
        self.analyze_tickers()

        market_analysis = self._load_cached("market_analysis.json", default=[])
        if market:
            market_analysis = [
                item
                for item in market_analysis
                if self._normalize_market_name(item.get("market") or "") == normalized_market
            ]
        ticker_news_summary = self._load_cached("ticker_news_summary.json", default=[])
        news_by_ticker, default_news_score, news_reasons_by_ticker, news_sentiment_by_ticker = self._news_lookup(
            ticker_news_summary
        )

        prequalified_candidates: list[dict[str, Any]] = []

        for market_item in market_analysis:
            ticker = str(market_item.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            current_price = float(market_item.get("current_price") or 0.0)
            support = float(market_item.get("support") or 0.0)
            resistance = float(market_item.get("resistance") or 0.0)
            ema20_value = float(market_item.get("ema20") or current_price)
            atr_value = float(market_item.get("atr") or 0.0)
            technical_score = float(market_item.get("technical_score") or 0.0)
            fundamental_score = float(market_item.get("fundamental_score") or 50.0)
            market_intelligence_score = float(market_item.get("market_intelligence_score") or 50.0)
            trend = str(market_item.get("trend") or "Neutral")
            trend_strength = int(market_item.get("trend_strength") or 0)
            estimated_trend_duration = str(market_item.get("estimated_trend_duration") or "1-2 islem gunu")
            relative_volume = float(market_item.get("relative_volume") or 0.0)
            gap_up = bool(market_item.get("gap_up", False))
            gap_down = bool(market_item.get("gap_down", False))
            rsi14 = float(market_item.get("rsi14") or 50.0)
            macd_state = str(market_item.get("macd") or "Neutral")
            ema50_value = float(market_item.get("ema50") or ema20_value)
            news_sentiment = str(news_sentiment_by_ticker.get(ticker, "Neutral") or "Neutral")

            if current_price <= 0 or support <= 0 or atr_value <= 0:
                continue

            news_score = float(news_by_ticker.get(ticker, default_news_score))
            if news_sentiment == "Negative":
                continue
            if technical_score < settings.min_technical_score:
                continue
            if trend_strength < settings.min_trend_strength:
                continue
            if relative_volume < settings.min_relative_volume:
                continue
            if fundamental_score < settings.min_fundamental_score:
                continue
            if market_intelligence_score < settings.min_market_intelligence_score:
                continue
            if news_score < settings.min_news_score:
                continue

            reasons = list(market_item.get("reasons", []))
            reasons.extend(news_reasons_by_ticker.get(ticker, []))
            prequalified_candidates.append(
                {
                    "market_item": market_item,
                    "ticker": ticker,
                    "current_price": current_price,
                    "support": support,
                    "resistance": resistance,
                    "ema20_value": ema20_value,
                    "atr_value": atr_value,
                    "technical_score": technical_score,
                    "fundamental_score": fundamental_score,
                    "market_intelligence_score": market_intelligence_score,
                    "trend": trend,
                    "trend_strength": trend_strength,
                    "estimated_trend_duration": estimated_trend_duration,
                    "relative_volume": relative_volume,
                    "gap_up": gap_up,
                    "gap_down": gap_down,
                    "rsi14": rsi14,
                    "macd_state": macd_state,
                    "ema50_value": ema50_value,
                    "news_score": news_score,
                    "reasons": reasons,
                }
            )

        ai_candidate_count = len(prequalified_candidates)
        allowed_decisions = set(settings.recommendation_decision_list or ["BUY", "HOLD"])
        recommendations: list[dict[str, Any]] = []

        for candidate in prequalified_candidates:
            market_item = dict(candidate["market_item"])

            decision = self.decision_engine.decide(
                ticker=str(candidate["ticker"]),
                current_price=float(candidate["current_price"]),
                support=float(candidate["support"]),
                resistance=float(candidate["resistance"]),
                ema20=float(candidate["ema20_value"]),
                atr_value=float(candidate["atr_value"]),
                technical_score=float(candidate["technical_score"]),
                news_score=float(candidate["news_score"]),
                fundamental_score=float(candidate["fundamental_score"]),
                market_intelligence_score=float(candidate["market_intelligence_score"]),
                trend=str(candidate["trend"]),
                trend_strength=int(candidate["trend_strength"]),
                estimated_trend_duration=str(candidate["estimated_trend_duration"]),
                relative_volume=float(candidate["relative_volume"]),
                gap_up=bool(candidate["gap_up"]),
                gap_down=bool(candidate["gap_down"]),
                rsi14=float(candidate["rsi14"]),
                macd_state=str(candidate["macd_state"]),
                ema50=float(candidate["ema50_value"]),
                reasons=list(candidate["reasons"]),
            )
            payload = asdict(decision)
            if payload.get("rejected"):
                continue

            decision_name = str(payload.get("decision") or "").upper()
            if decision_name not in allowed_decisions:
                continue
            if float(payload.get("confidence") or 0.0) < settings.min_confidence_score:
                continue
            if float(payload.get("risk_reward_ratio") or 0.0) < settings.min_risk_reward_ratio:
                continue

            payload["market"] = str(market_item.get("market") or "BIST")
            payload["company_name"] = str(market_item.get("company_name") or payload.get("ticker") or "")
            entry_price = float(payload.get("entry_price") or 0.0)
            current_price = float(payload.get("current_price") or payload.get("entry_price") or 0.0)
            target_price = float(payload.get("current_target") or 0.0)
            payload["expected_gain_pct"] = round(
                self._compute_gain_pct(base_price=entry_price, target_price=target_price),
                2,
            )
            payload["today_potential_pct"] = round(
                self._compute_gain_pct(base_price=current_price, target_price=target_price),
                2,
            )
            recommendations.append(payload)

        recommendations = [
            item
            for item in recommendations
            if float(item.get("expected_gain_pct") or 0.0) >= self._min_expected_gain_threshold(item)
        ]

        recommendations.sort(
            key=self._expected_gain_sort_key,
        )

        if not recommendations:
            recommendations = [
                {
                    "ticker": "CASH",
                    "company_name": "Cash Position",
                    "market": normalized_market or "BIST",
                    "decision": "WAIT IN CASH",
                    "entry_price": 0.0,
                    "entry_range_low": 0.0,
                    "entry_range_high": 0.0,
                    "stop_loss": 0.0,
                    "current_target": 0.0,
                    "risk_reward_ratio": 0.0,
                    "news_score": 50.0,
                    "technical_score": 0.0,
                    "fundamental_score": 0.0,
                    "market_intelligence_score": 0.0,
                    "overall_score": 45.0,
                    "confidence": 40.0,
                    "trend_strength": 0,
                    "estimated_trend_duration": "1-2 islem gunu",
                    "recommended_amount": round(settings.total_capital, 2),
                    "reasons": ["Yeterli kalite firsati bulunamadi, nakitte bekleme onerildi."],
                    "trend": "Neutral",
                    "relative_volume": 0.0,
                    "gap": False,
                    "rejected": False,
                    "reject_reasons": [],
                    "ai_summary": None,
                    "ai_reason": None,
                    "ai_risk": None,
                }
            ]

        allocation = self.capital_allocation_engine.allocate(recommendations, settings.total_capital)
        allocation_by_ticker = {
            str(item.get("ticker") or "").upper(): float(item.get("recommended_amount") or 0.0)
            for item in allocation.get("allocations", [])
        }
        for item in recommendations:
            ticker_key = str(item.get("ticker") or "").upper()
            if ticker_key == "CASH":
                item["recommended_amount"] = round(float(allocation.get("cash") or settings.total_capital), 2)
                continue
            item["recommended_amount"] = round(allocation_by_ticker.get(ticker_key, 0.0), 2)

        analysis_payload = dict(self._load_cached("analysis.json", default={}))
        analysis_payload["capital_allocation"] = allocation
        analysis_payload["timestamp"] = datetime.now(UTC).isoformat()
        self._save_if_changed("analysis.json", analysis_payload)

        storage_file = "recommendations.json"
        if normalized_market == "BIST":
            storage_file = "bist_recommendations.json"
        elif normalized_market == "US":
            storage_file = "us_recommendations.json"

        self._save_if_changed(storage_file, recommendations)
        gemini_before = self.gemini_service.diagnostics_snapshot()
        if len(recommendations) == 1 and str(recommendations[0].get("ticker") or "") == "CASH":
            enriched_recommendations = recommendations
        else:
            enriched_recommendations = self._enrich_recommendations_with_ai(recommendations)
        gemini_after = self.gemini_service.diagnostics_snapshot()
        gemini_calls = int(gemini_after.get("total_requests", 0)) - int(gemini_before.get("total_requests", 0))
        self._save_if_changed(storage_file, enriched_recommendations)

        recommendation_count = sum(1 for item in enriched_recommendations if str(item.get("ticker") or "") != "CASH")
        halal_passed = self._halal_passed_count_for_market(normalized_market, fallback=len(market_analysis))
        self._set_selection_stats(
            normalized_market,
            {
                "analyzed_total": len(market_analysis),
                "halal_passed": halal_passed,
                "ai_candidates": ai_candidate_count,
                "recommended": recommendation_count,
                "elapsed_seconds": round(time.perf_counter() - started_at, 3),
                "gemini_calls": max(0, gemini_calls),
                "gemini_last_key_label": str(gemini_after.get("last_key_label") or "N/A"),
            },
        )

        if market is None:
            self._save_if_changed("recommendations.json", enriched_recommendations)
        return enriched_recommendations

    def _generate_bist_recommendations(self, *, started_at: float) -> list[dict[str, Any]]:
        """Run the BIST-only scoring flow and persist ranked opportunities."""

        news_payload = self.collect_news()
        self.collect_kap()
        market_payload = self.collect_market(markets=["BIST"])
        self.analyze_news(news_payload=news_payload, market_payload=market_payload)
        self.analyze_market(market="BIST", market_payload=market_payload)

        market_analysis = list(
            self._runtime_cache.get("market_analysis_live_by_market", {}).get("BIST")
            or []
        )
        if not market_analysis:
            market_analysis = self._load_cached("market_analysis.json", default=[])
            market_analysis = [
                item
                for item in market_analysis
                if self._normalize_market_name(item.get("market") or "") == "BIST"
            ]

        ticker_news_summary = list(self._runtime_cache.get("ticker_news_summary_live") or [])
        if not ticker_news_summary:
            ticker_news_summary = self._load_cached("ticker_news_summary.json", default=[])

        news_by_ticker, default_news_score, news_reasons_by_ticker, news_sentiment_by_ticker = self._news_lookup(
            ticker_news_summary
        )
        news_confidence_by_ticker = {
            str(item.get("ticker") or "").strip().upper(): float(item.get("confidence") or 0.0)
            for item in ticker_news_summary
            if isinstance(item, dict)
        }

        scored_items: list[dict[str, Any]] = []
        for market_item in market_analysis:
            ticker = str(market_item.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            news_score = float(news_by_ticker.get(ticker, default_news_score))
            news_sentiment = str(news_sentiment_by_ticker.get(ticker, "Neutral") or "Neutral")
            news_confidence = float(news_confidence_by_ticker.get(ticker, 50.0))
            result = self.bist_opportunity_engine.score_candidate(
                market_item,
                news_score=news_score,
                news_sentiment=news_sentiment,
                news_confidence=news_confidence,
                news_reasons=list(news_reasons_by_ticker.get(ticker, [])),
            )
            payload = asdict(result)
            payload["rank"] = 0
            payload["market"] = "BIST"
            payload["company_name"] = str(market_item.get("company_name") or market_item.get("name") or ticker)
            payload["news_score"] = round(news_score, 2)
            payload["news_sentiment"] = news_sentiment
            payload["news_confidence"] = round(news_confidence, 2)
            payload["market_item"] = {
                "ticker": ticker,
                "name": payload["company_name"],
            }
            scored_items.append(payload)

        scored_items.sort(key=self._bist_score_sort_key, reverse=True)
        eligible_items = [item for item in scored_items if not bool(item.get("hard_filtered"))]
        top_n = int(self.bist_opportunity_engine.config.get("top_n") or 20)
        final_n = int(self.bist_opportunity_engine.config.get("final_n") or 10)

        for item in eligible_items:
            entry_price = float(item.get("entry_price") or 0.0)
            current_price = float(item.get("current_price") or entry_price or 0.0)
            target_price = float(item.get("current_target") or 0.0)
            item["expected_gain_pct"] = round(
                self._compute_gain_pct(base_price=entry_price, target_price=target_price),
                2,
            )
            item["today_potential_pct"] = round(
                self._compute_gain_pct(base_price=current_price, target_price=target_price),
                2,
            )

        eligible_items = [
            item
            for item in eligible_items
            if float(item.get("expected_gain_pct") or 0.0) >= self._min_expected_gain_threshold(item)
        ]
        rank_source = list(eligible_items)
        if not rank_source:
            rank_source = [item for item in scored_items if not bool(item.get("hard_filtered"))]

        bist100_priority_set = self._load_bist100_priority_set()
        regime_snapshot = self._bist_market_regime_snapshot(
            market_payload=market_payload,
            market_analysis=market_analysis,
        )
        scan_scope = "ALL_BIST"
        if (
            bool(regime_snapshot.get("is_bearish"))
            and settings.bist_bearish_only_bist100
            and bist100_priority_set
        ):
            restricted = [
                item
                for item in rank_source
                if str(item.get("ticker") or "").strip().upper() in bist100_priority_set
            ]
            if restricted:
                rank_source = restricted
                scan_scope = "BIST100_ONLY"
            else:
                scan_scope = "ALL_BIST_FALLBACK"

        ai_review_pool = self._enrich_recommendations_with_ai(rank_source)
        prefer_bist100 = bool(regime_snapshot.get("is_bearish"))
        if (
            not prefer_bist100
            and bist100_priority_set
            and settings.bist100_preference_enabled
        ):
            prefer_bist100 = self._has_good_bist100_candidate(ai_review_pool, bist100_priority_set)

        if prefer_bist100 and bist100_priority_set:
            ai_review_pool.sort(
                key=lambda item: self._rank_with_bist100_priority(item, bist100_priority_set)
            )
        else:
            ai_review_pool.sort(key=self._expected_gain_sort_key)

        ranked_pool = ai_review_pool[:top_n]
        for index, item in enumerate(ranked_pool, start=1):
            item["rank"] = index

        top_10 = ranked_pool[:10]
        top_final_candidates = ranked_pool[:final_n]

        final_recommendations = [
            self._finalize_bist_recommendation(item, rank=index + 1)
            for index, item in enumerate(top_final_candidates)
        ]
        gated_final: list[dict[str, Any]] = []
        for item in final_recommendations:
            gate_reasons = self._confidence_gate_reasons(item)
            if gate_reasons:
                item["rejected"] = True
                item["reject_reasons"] = gate_reasons
                continue
            gated_final.append(item)

        final_recommendations = list(gated_final)
        if prefer_bist100 and bist100_priority_set:
            final_recommendations.sort(
                key=lambda item: self._rank_with_bist100_priority(item, bist100_priority_set)
            )
        else:
            final_recommendations.sort(key=self._expected_gain_sort_key)
        final_recommendations = [
            self._finalize_bist_recommendation(item, rank=index + 1)
            for index, item in enumerate(final_recommendations[:final_n])
        ]

        if not final_recommendations:
            final_recommendations = [
                {
                    "ticker": "CASH",
                    "company_name": "Cash Position",
                    "market": "BIST",
                    "decision": "WAIT IN CASH",
                    "entry_price": 0.0,
                    "entry_range_low": 0.0,
                    "entry_range_high": 0.0,
                    "stop_loss": 0.0,
                    "current_target": 0.0,
                    "risk_reward_ratio": 0.0,
                    "news_score": 50.0,
                    "trend_strength": 0,
                    "confidence": 35.0,
                    "user_confidence": 35,
                    "overall_score": 40.0,
                    "expected_gain_pct": 0.0,
                    "today_potential_pct": 0.0,
                    "reasons": ["Celiski ve dusuk guven filtreleri nedeniyle bugun net firsat bulunamadi."],
                    "rejected": False,
                    "reject_reasons": [],
                }
            ]

        for item in final_recommendations:
            item["recommended_amount"] = 0.0

        allocation = self.capital_allocation_engine.allocate(final_recommendations, settings.total_capital)
        allocation_by_ticker = {
            str(item.get("ticker") or "").upper(): float(item.get("recommended_amount") or 0.0)
            for item in allocation.get("allocations", [])
        }
        for item in final_recommendations:
            ticker_key = str(item.get("ticker") or "").upper()
            item["recommended_amount"] = round(allocation_by_ticker.get(ticker_key, 0.0), 2)

        summary = self._build_bist_summary(
            started_at=started_at,
            analyzed_total=len(market_analysis),
            hard_filtered=sum(1 for item in scored_items if bool(item.get("hard_filtered"))),
            scored_total=len(scored_items),
            eligible_total=len(eligible_items),
            top_20=ranked_pool,
            top_10=top_10,
            top_5=final_recommendations,
            regime_snapshot=regime_snapshot,
            scan_scope=scan_scope,
            bist100_priority_enabled=bool(prefer_bist100 and bist100_priority_set),
        )

        analysis_payload = dict(self._load_cached("analysis.json", default={}))
        analysis_payload["capital_allocation"] = allocation
        analysis_payload["bist_summary"] = summary
        analysis_payload["timestamp"] = datetime.now(UTC).isoformat()
        self._save_if_changed("analysis.json", analysis_payload)
        self._save_if_changed("bist_scoring_log.json", scored_items)
        self._save_if_changed("bist_live_summary.json", summary)
        self._save_if_changed("bist_recommendations.json", final_recommendations)

        self._set_selection_stats(
            "BIST",
            {
                "analyzed_total": int(summary["analyzed_total"]),
                "filter_rejected": int(summary["hard_filtered"]),
                "scored_total": int(summary["scored_total"]),
                "top_20": int(len(ranked_pool)),
                "top_10": int(len(top_10)),
                "top_5": int(len(final_recommendations)),
                "top_final": int(len(final_recommendations)),
                "top_20_tickers": [str(item.get("ticker") or "") for item in ranked_pool],
                "top_10_tickers": [str(item.get("ticker") or "") for item in top_10],
                "top_5_tickers": [str(item.get("ticker") or "") for item in final_recommendations],
                "top_final_tickers": [str(item.get("ticker") or "") for item in final_recommendations],
                "best_opportunity": summary["best_opportunity"],
                "riskiest_opportunity": summary["riskiest_opportunity"],
                "strongest_news": summary["strongest_news"],
                "strongest_technical": summary["strongest_technical"],
                "highest_volume_growth": summary["highest_volume_growth"],
                "elapsed_seconds": summary["elapsed_seconds"],
            },
        )

        logger.info(
            "BIST scoring completed | analyzed=%s filtered=%s scored=%s top20=%s top10=%s top_final=%s elapsed=%.2fs",
            summary["analyzed_total"],
            summary["hard_filtered"],
            summary["scored_total"],
            len(ranked_pool),
            len(top_10),
            len(final_recommendations),
            float(summary["elapsed_seconds"]),
        )
        for item in final_recommendations:
            logger.info(self._format_bist_recommendation_log(item))

        return final_recommendations

    def _finalize_bist_recommendation(self, item: dict[str, Any], *, rank: int) -> dict[str, Any]:
        final_item = dict(item)
        final_item["rank"] = rank
        final_item["market"] = "BIST"
        final_item["decision"] = str(final_item.get("decision") or "WAIT")
        final_item["overall_score"] = round(float(final_item.get("total_score") or 0.0), 2)
        final_item["recommended_amount"] = round(float(final_item.get("recommended_amount") or 0.0), 2)
        final_item["rejected"] = False
        final_item["reject_reasons"] = []
        final_item["company_name"] = str(final_item.get("company_name") or final_item.get("ticker") or "UNKNOWN")
        final_item["ai_summary"] = final_item.get("ai_summary")
        final_item["ai_reason"] = final_item.get("ai_reason")
        final_item["ai_risk"] = final_item.get("ai_risk")
        entry_price = float(final_item.get("entry_price") or 0.0)
        current_price = float(final_item.get("current_price") or entry_price or 0.0)
        target_price = float(final_item.get("current_target") or 0.0)
        final_item["expected_gain_pct"] = round(
            self._compute_gain_pct(base_price=entry_price, target_price=target_price),
            2,
        )
        final_item["today_potential_pct"] = round(
            self._compute_gain_pct(base_price=current_price, target_price=target_price),
            2,
        )
        final_item["confidence"] = float(self._bist_confidence_score(final_item))
        final_item["user_confidence"] = int(round(float(final_item.get("confidence") or 0.0)))
        execution_plan = self._build_execution_plan(final_item)
        final_item["execution_plan"] = execution_plan
        final_item["trade_instruction"] = str(execution_plan.get("instruction") or "NO TRADE")
        return final_item

    def _build_execution_plan(self, item: dict[str, Any]) -> dict[str, Any]:
        ticker = str(item.get("ticker") or "UNKNOWN").strip().upper() or "UNKNOWN"
        decision = str(item.get("decision") or "WAIT").upper()
        entry_status = str(item.get("entry_status") or "WAIT").upper()
        current_price = float(item.get("current_price") or 0.0)
        entry_low = float(item.get("entry_range_low") or 0.0)
        entry_high = float(item.get("entry_range_high") or 0.0)
        limit_entry = float(item.get("limit_entry_price") or item.get("entry_price") or 0.0)
        stop_loss = float(item.get("stop_loss") or 0.0)
        risk_reward = float(item.get("risk_reward_ratio") or 0.0)

        tp_levels = [dict(level) for level in item.get("take_profit_levels") or [] if isinstance(level, dict)]
        if not tp_levels:
            tp_levels = [
                {"label": "TP1", "price": float(item.get("take_profit_1") or 0.0), "reason": "Teknik hedef"},
                {"label": "TP2", "price": float(item.get("take_profit_2") or 0.0), "reason": "Teknik hedef"},
                {"label": "TP3", "price": float(item.get("take_profit_3") or 0.0), "reason": "Teknik hedef"},
                {"label": "TP4", "price": float(item.get("take_profit_4") or 0.0), "reason": "Teknik hedef"},
            ]

        valid_tp = [level for level in tp_levels if float(level.get("price") or 0.0) > 0.0]
        valid_tp.sort(key=lambda value: float(value.get("price") or 0.0))

        sell_schedule: list[dict[str, Any]] = []
        default_weights = [35, 30, 20, 15]
        for idx, level in enumerate(valid_tp[:4]):
            sell_schedule.append(
                {
                    "label": str(level.get("label") or f"TP{idx + 1}"),
                    "price": round(float(level.get("price") or 0.0), 4),
                    "size_percent": default_weights[idx],
                    "order_type": "LIMIT_SELL",
                    "reason": str(level.get("reason") or "Teknik hedef"),
                }
            )

        actionable = decision in {"BUY", "BUY NOW", "LIMIT BUY"} and entry_status not in {"NO TRADE", "ENTRY MISSED"}
        if not actionable or limit_entry <= 0 or stop_loss <= 0 or stop_loss >= max(limit_entry, current_price, 0.01):
            return {
                "actionable": False,
                "instruction": f"{ticker}: NO TRADE",
                "entry_order": None,
                "stop_order": None,
                "sell_orders": [],
                "invalidation": "Yapisal risk yuksek veya giris kosulu uygun degil",
                "risk_reward": round(risk_reward, 2),
            }

        buy_price = round(limit_entry, 4)
        buy_range_low = round(entry_low if entry_low > 0 else limit_entry, 4)
        buy_range_high = round(entry_high if entry_high > 0 else limit_entry, 4)
        stop_price = round(stop_loss, 4)
        trigger_price = round(max(0.01, buy_price * 1.003), 4)

        entry_order_type = "LIMIT_BUY"
        if entry_status == "BUY" and bool(item.get("market_entry_allowed")):
            entry_order_type = "MARKET_BUY"
        elif str(item.get("entry_strategy") or "").strip().lower() == "breakout":
            entry_order_type = "STOP_LIMIT_BUY"

        entry_order: dict[str, Any] = {
            "type": entry_order_type,
            "price": buy_price,
            "range_low": buy_range_low,
            "range_high": buy_range_high,
            "trigger_price": trigger_price if entry_order_type == "STOP_LIMIT_BUY" else None,
            "time_in_force": "DAY",
        }

        stop_order = {
            "type": "STOP_MARKET_SELL",
            "price": stop_price,
            "trail_after_tp1": True,
            "trail_rule": "TP1 hit sonra stop entry fiyata cek",
        }

        primary_target = 0.0
        if sell_schedule:
            primary_target = float(sell_schedule[0].get("price") or 0.0)

        instruction = (
            f"{ticker}: ALIS {entry_order_type} {buy_price:.4f}"
            f" | STOP {stop_price:.4f}"
            f" | SATIS {primary_target:.4f} ve TP merdiveni"
        )

        return {
            "actionable": True,
            "instruction": instruction,
            "entry_order": entry_order,
            "stop_order": stop_order,
            "sell_orders": sell_schedule,
            "invalidation": "Fiyat stop seviyesinin altinda 15dk kapanirsa plan iptal",
            "risk_reward": round(risk_reward, 2),
        }

    def _format_bist_recommendation_log(self, item: dict[str, Any]) -> str:
        component_scores = dict(item.get("component_scores") or {})
        return (
            f"BIST RECOMMENDATION | {format_istanbul_datetime(pattern='%H:%M')} | {item.get('ticker')} | "
            f"Current={float(item.get('current_price') or 0.0):.4f} | "
            f"Entry={float(item.get('entry_price') or 0.0):.4f} | "
            f"Stop={float(item.get('stop_loss') or 0.0):.4f} | "
            f"TP1={float(item.get('take_profit_1') or 0.0):.4f} | "
            f"TP2={float(item.get('take_profit_2') or 0.0):.4f} | "
            f"TP3={float(item.get('take_profit_3') or 0.0):.4f} | "
            f"TP4={float(item.get('take_profit_4') or 0.0):.4f} | "
            f"RR={float(item.get('risk_reward_ratio') or 0.0):.2f} | "
            f"Score={float(item.get('overall_score') or 0.0):.2f} | "
            f"Confidence={self._format_confidence(item.get('confidence'))} | "
            f"Rules={'; '.join(str(line) for line in item.get('score_lines') or [])} | "
            f"PriceRule={'; '.join(str(note) for note in item.get('price_plan_notes') or [])} | "
            f"Components={component_scores}"
        )

    def _format_confidence(self, value: Any) -> str:
        if value is None:
            return "N/A"
        try:
            return str(int(round(float(value))))
        except (TypeError, ValueError):
            return "N/A"

    def _compute_gain_pct(self, *, base_price: float, target_price: float) -> float:
        if base_price <= 0 or target_price <= 0:
            return 0.0
        return ((target_price - base_price) / base_price) * 100.0

    def _min_expected_gain_threshold(self, item: dict[str, Any]) -> float:
        current_price = float(item.get("current_price") or item.get("entry_price") or 0.0)
        atr_value = float(item.get("atr") or 0.0)
        trend_strength = float(item.get("trend_strength") or 0.0)
        atr_ratio = (atr_value / max(current_price, 1e-9)) if current_price > 0 else 0.0
        volatility_floor = max(1.6, min(3.0, atr_ratio * 180.0))
        trend_discount = 0.0
        if trend_strength >= 75:
            trend_discount = 0.3
        elif trend_strength >= 65:
            trend_discount = 0.15
        threshold = max(1.5, min(3.0, volatility_floor - trend_discount))
        return threshold

    def _expected_gain_sort_key(self, item: dict[str, Any]) -> tuple[float, float, float, float, float, str]:
        expected_gain = float(item.get("expected_gain_pct") or 0.0)
        confidence = float(item.get("confidence") or item.get("overall_score") or item.get("total_score") or 0.0)
        trend_strength = float(item.get("trend_strength") or 0.0)
        risk_reward = float(item.get("risk_reward_ratio") or 0.0)
        total_score = float(item.get("total_score") or item.get("overall_score") or 0.0)
        quality_rank = (
            (total_score * 0.52)
            + (confidence * 0.22)
            + (min(100.0, expected_gain * 8.0) * 0.16)
            + (min(100.0, risk_reward * 25.0) * 0.10)
        )
        return (
            -quality_rank,
            -expected_gain,
            -confidence,
            -trend_strength,
            -total_score,
            str(item.get("ticker") or ""),
        )

    def _rank_with_bist100_priority(
        self,
        item: dict[str, Any],
        bist100_set: set[str],
    ) -> tuple[Any, ...]:
        ticker = str(item.get("ticker") or "").strip().upper()
        priority_flag = 0 if ticker and ticker in bist100_set else 1
        return (priority_flag, *self._expected_gain_sort_key(item))

    def _has_good_bist100_candidate(
        self,
        items: list[dict[str, Any]],
        bist100_set: set[str],
    ) -> bool:
        buy_like_decisions = {"BUY", "BUY NOW", "LIMIT BUY"}
        for item in items:
            ticker = str(item.get("ticker") or "").strip().upper()
            if ticker not in bist100_set:
                continue

            decision = str(item.get("decision") or "").strip().upper()
            if decision not in buy_like_decisions:
                continue

            total_score = float(item.get("total_score") or item.get("overall_score") or 0.0)
            if total_score < settings.bist100_good_min_total_score:
                continue

            confidence = float(item.get("confidence") or self._bist_confidence_score(item) or 0.0)
            if confidence < settings.bist100_good_min_confidence:
                continue

            expected_gain = float(item.get("expected_gain_pct") or 0.0)
            if expected_gain < self._min_expected_gain_threshold(item):
                continue

            risk_reward = float(item.get("risk_reward_ratio") or 0.0)
            if risk_reward < max(1.2, settings.min_risk_reward_ratio):
                continue

            return True
        return False

    def _bist_market_regime_snapshot(
        self,
        *,
        market_payload: list[dict[str, Any]],
        market_analysis: list[dict[str, Any]],
    ) -> dict[str, Any]:
        bist_rows = [
            row
            for row in market_payload
            if self._normalize_market_name((row.get("metadata") or {}).get("market") or row.get("source")) == "BIST"
        ]

        weighted_sum = 0.0
        total_weight = 0.0
        equal_changes: list[float] = []
        for row in bist_rows:
            try:
                change = float(row.get("daily_change_percent") or row.get("change_percent") or 0.0)
            except (TypeError, ValueError):
                continue
            equal_changes.append(change)

            try:
                market_cap = float(row.get("market_cap") or 0.0)
            except (TypeError, ValueError):
                market_cap = 0.0
            if market_cap > 0:
                weighted_sum += change * market_cap
                total_weight += market_cap

        weighted_change = (weighted_sum / total_weight) if total_weight > 0 else 0.0
        equal_change = (sum(equal_changes) / len(equal_changes)) if equal_changes else 0.0

        bearish_flags = 0
        trend_samples = 0
        for row in market_analysis:
            trend = str(row.get("trend") or "").strip().lower()
            if trend in {"bullish", "bearish", "neutral"}:
                trend_samples += 1
                if trend == "bearish":
                    bearish_flags += 1
        bearish_breadth = (bearish_flags / trend_samples) if trend_samples else 0.0

        change_reference = weighted_change if total_weight > 0 else equal_change
        down_by_change = change_reference <= settings.bist_bearish_change_threshold
        down_by_breadth = bearish_breadth >= settings.bist_bearish_breadth_threshold
        is_bearish = bool(settings.bist_regime_guard_enabled and (down_by_change or down_by_breadth))

        return {
            "is_bearish": is_bearish,
            "weighted_change_pct": round(weighted_change, 4),
            "equal_weight_change_pct": round(equal_change, 4),
            "bearish_breadth_ratio": round(bearish_breadth, 4),
            "sample_size": len(bist_rows),
            "trend_sample_size": trend_samples,
            "down_by_change": bool(down_by_change),
            "down_by_breadth": bool(down_by_breadth),
            "change_threshold": float(settings.bist_bearish_change_threshold),
            "breadth_threshold": float(settings.bist_bearish_breadth_threshold),
        }

    def _load_bist100_priority_set(self) -> set[str]:
        configured = self._load_bist100_benchmark_set()
        if configured:
            return configured

        market_rows = self._load_cached("market.json", default=[])
        if not isinstance(market_rows, list):
            return set()

        by_cap: list[tuple[str, float]] = []
        for row in market_rows:
            if not isinstance(row, dict):
                continue

            market_name = self._normalize_market_name(row.get("market") or "")
            if market_name and market_name != "BIST":
                continue

            ticker = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            try:
                market_cap = float(row.get("market_cap") or 0.0)
            except (TypeError, ValueError):
                market_cap = 0.0
            if market_cap <= 0:
                continue

            by_cap.append((ticker, market_cap))

        by_cap.sort(key=lambda item: item[1], reverse=True)
        return {ticker for ticker, _ in by_cap[:100]}

    def _load_bist100_benchmark_set(self) -> set[str]:
        filename = "index_benchmarks.json"
        if not self.config_storage.exists(filename):
            return set()

        raw = self.config_storage.load(filename, default={})
        if not isinstance(raw, dict):
            return set()

        values = raw.get("bist100", [])
        if not isinstance(values, list):
            return set()

        return {
            str(value).strip().upper()
            for value in values
            if str(value).strip()
        }

    def _user_confidence_score(self, item: dict[str, Any]) -> int:
        component_scores = dict(item.get("component_scores") or {})
        if component_scores:
            graph = float(component_scores.get("graph_structure") or 0.0)
            trend = float(component_scores.get("trend") or 0.0)
            volume = float(component_scores.get("volume") or 0.0)
            momentum = float(component_scores.get("momentum") or 0.0)
            news = float(component_scores.get("news") or 0.0)
            ai_conf = float(component_scores.get("ai_confidence") or 0.0)

            normalized = (
                (graph / 50.0) * 0.34
                + (trend / 22.0) * 0.28
                + (volume / 12.0) * 0.14
                + (momentum / 10.0) * 0.12
                + (news / 4.0) * 0.08
                + (ai_conf / 2.0) * 0.04
            )
            return int(max(0, min(100, round(normalized * 100.0))))

        raw_conf = float(item.get("confidence") or 0.0)
        if raw_conf > 0:
            return int(max(0, min(100, round(raw_conf))))

        overall = float(item.get("overall_score") or item.get("total_score") or 0.0)
        return int(max(0, min(100, round(overall))))

    def _bist_confidence_score(self, item: dict[str, Any]) -> float:
        component_scores = dict(item.get("component_scores") or {})

        def normalize_component(name: str, cap_value: float) -> float:
            value = float(component_scores.get(name) or 0.0)
            if cap_value <= 0:
                return 0.0
            return max(0.0, min(100.0, (value / cap_value) * 100.0))

        pattern_score = normalize_component("graph_structure", 50.0)
        trend_score = normalize_component("trend", 22.0)
        volume_score = normalize_component("volume", 12.0)
        momentum_score = normalize_component("momentum", 10.0)
        news_score = normalize_component("news", 4.0)
        ai_score = normalize_component("ai_confidence", 2.0)

        rr = float(item.get("risk_reward_ratio") or 0.0)
        if rr <= 0:
            risk_score = 0.0
        elif rr >= 3.0:
            risk_score = 100.0
        else:
            risk_score = (rr / 3.0) * 100.0

        macro_multiplier = float(item.get("macro_multiplier") or 1.0)
        market_score = max(0.0, min(100.0, ((macro_multiplier - 0.84) / 0.28) * 100.0))
        if market_score == 0.0:
            market_score = max(0.0, min(100.0, float(item.get("trend_strength") or 0.0)))

        decision = str(item.get("decision") or "WAIT").upper()
        decision_score = {
            "BUY NOW": 90.0,
            "LIMIT BUY": 84.0,
            "BUY": 82.0,
            "PULLBACK BEKLE": 64.0,
            "BREAKOUT BEKLE": 62.0,
            "WAIT": 50.0,
            "ENTRY MISSED": 42.0,
            "SELL": 30.0,
            "EXIT": 25.0,
            "NO TRADE": 20.0,
        }.get(decision, 48.0)

        confidence = (
            pattern_score * 0.20
            + trend_score * 0.14
            + momentum_score * 0.12
            + volume_score * 0.10
            + news_score * 0.10
            + ai_score * 0.08
            + risk_score * 0.14
            + market_score * 0.07
            + decision_score * 0.05
        )
        return round(max(0.0, min(100.0, confidence)), 2)

    def _confidence_gate_reasons(self, item: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        decision = str(item.get("decision") or "WAIT").upper()
        confidence = float(item.get("confidence") or 0.0)
        rr = float(item.get("risk_reward_ratio") or 0.0)
        trend = str(item.get("trend") or "Neutral").lower()
        news_sentiment = str(item.get("news_sentiment") or "Neutral").lower()
        macd_state = str(item.get("macd_state") or "Neutral").lower()

        if decision in {"WAIT", "SELL", "NO TRADE", "ENTRY MISSED", "EXIT"}:
            reasons.append("Karar tipi aksiyon icin uygun degil")
        if confidence < 62.0:
            reasons.append("Guven puani dusuk")
        if rr < max(1.2, settings.min_risk_reward_ratio):
            reasons.append("Risk-odul yetersiz")
        if trend == "bearish" and decision in {"BUY", "BUY NOW", "LIMIT BUY"}:
            reasons.append("Dusen trend ile alis karari celisiyor")
        if news_sentiment == "negative" and decision in {"BUY", "BUY NOW", "LIMIT BUY"}:
            reasons.append("Negatif haber tonu ile alis karari celisiyor")
        if macd_state == "bearish" and trend == "bullish" and decision in {"BUY", "BUY NOW", "LIMIT BUY"}:
            reasons.append("Trend/MACD uyumsuzlugu")

        indicator_text = " ".join(str(value) for value in item.get("indicator_confirmations") or []).lower()
        if ("rsi yuksek" in indicator_text or "overbought" in indicator_text) and decision in {"BUY", "BUY NOW", "LIMIT BUY"}:
            reasons.append("Asiri alim bolgesinde agresif giris")

        return reasons

    def _passes_confidence_gate(self, item: dict[str, Any]) -> bool:
        return len(self._confidence_gate_reasons(item)) == 0

    def _apply_ai_enrichment_to_scores(
        self,
        item: dict[str, Any],
        *,
        news_ai: dict[str, Any] | None,
        kap_ai: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = dict(item)
        component_scores = dict(payload.get("component_scores") or {})
        if not component_scores:
            return payload

        signals = [data for data in [news_ai, kap_ai] if isinstance(data, dict)]
        if not signals:
            return payload

        sentiment_map = {"POSITIVE": 1.0, "NEUTRAL": 0.0, "NEGATIVE": -1.0}

        def _default_factor(data: dict[str, Any], factor_name: str) -> float:
            sentiment = str(data.get("sentiment") or "NEUTRAL").upper()
            defaults_by_sentiment = {
                "POSITIVE": {
                    "positive_score": 72.0,
                    "negative_score": 28.0,
                    "uncertain_score": 30.0,
                    "risk_score": 34.0,
                    "opportunity_score": 72.0,
                },
                "NEGATIVE": {
                    "positive_score": 28.0,
                    "negative_score": 72.0,
                    "uncertain_score": 40.0,
                    "risk_score": 74.0,
                    "opportunity_score": 26.0,
                },
                "NEUTRAL": {
                    "positive_score": 50.0,
                    "negative_score": 50.0,
                    "uncertain_score": 50.0,
                    "risk_score": 50.0,
                    "opportunity_score": 50.0,
                },
            }
            return float(defaults_by_sentiment.get(sentiment, defaults_by_sentiment["NEUTRAL"]).get(factor_name, 50.0))

        def _factor(data: dict[str, Any], factor_name: str) -> float:
            raw = data.get(factor_name)
            if raw is None:
                return _default_factor(data, factor_name)
            try:
                return max(0.0, min(100.0, float(raw)))
            except (TypeError, ValueError):
                return _default_factor(data, factor_name)

        sentiments = [sentiment_map.get(str(data.get("sentiment") or "NEUTRAL").upper(), 0.0) for data in signals]
        confidences = [max(0.0, min(100.0, float(data.get("confidence") or 50.0))) for data in signals]
        positive_scores = [_factor(data, "positive_score") for data in signals]
        negative_scores = [_factor(data, "negative_score") for data in signals]
        uncertain_scores = [_factor(data, "uncertain_score") for data in signals]
        risk_scores = [_factor(data, "risk_score") for data in signals]
        opportunity_scores = [_factor(data, "opportunity_score") for data in signals]

        sentiment_bias = sum(sentiments) / max(1, len(sentiments))
        avg_confidence = sum(confidences) / max(1, len(confidences))
        avg_positive = sum(positive_scores) / max(1, len(positive_scores))
        avg_negative = sum(negative_scores) / max(1, len(negative_scores))
        avg_uncertain = sum(uncertain_scores) / max(1, len(uncertain_scores))
        avg_risk = sum(risk_scores) / max(1, len(risk_scores))
        avg_opportunity = sum(opportunity_scores) / max(1, len(opportunity_scores))

        conviction = max(0.0, min(100.0, avg_opportunity + avg_positive - avg_negative - (avg_uncertain * 0.6) - (avg_risk * 0.6)))
        base_ai_component = ((avg_confidence * 0.65) + (conviction * 0.35)) / 100.0 * 2.0
        ai_component = max(0.0, min(2.0, base_ai_component + (sentiment_bias * 0.22)))
        news_component = float(component_scores.get("news") or 0.0)
        news_adjustment = ((avg_positive - avg_negative) / 100.0) * 0.6
        news_adjustment -= (avg_uncertain / 100.0) * 0.25
        news_adjustment -= (avg_risk / 100.0) * 0.25
        news_component = max(0.0, min(4.0, news_component + news_adjustment))

        component_scores["ai_confidence"] = round(ai_component, 2)
        component_scores["news"] = round(news_component, 2)
        payload["component_scores"] = component_scores

        macro_multiplier = float(payload.get("macro_multiplier") or 1.0)
        total_score = round(sum(float(value or 0.0) for value in component_scores.values()) * macro_multiplier, 2)
        payload["total_score"] = total_score
        payload["overall_score"] = total_score
        payload["confidence"] = self._bist_confidence_score(payload)

        reasons = list(payload.get("reasons") or [])
        if sentiment_bias > 0.2:
            reasons.append("Gemini haber tonu olumlu")
        elif sentiment_bias < -0.2:
            reasons.append("Gemini haber tonu olumsuz")
        payload["reasons"] = reasons

        return payload

    def _plain_turkish_reason(self, reason: str) -> str:
        text = str(reason or "").strip()
        if not text:
            return ""

        lowered = text.lower()
        rules = [
            (["higher high", "higher low"], "Yukselis egilimi gucleniyor."),
            (["lower high", "lower low"], "Yukseliste zayiflama belirtileri var, dikkatli olunmali."),
            (["cup and handle"], "Fiyat yukari hareket icin guclu bir hazirlikta gorunuyor."),
            (["rsi"], "Kisa vadede alim-satim dengesi yukari yone donuyor."),
            (["atr"], "Fiyatta hareketlilik artti; ani dalgalanmalara karsi dikkatli olunmali."),
            (["ema", "moving average"], "Kisa ve orta vadede fiyatin yukari yonu destekleniyor."),
            (["macd"], "Alicilarin gucu satiya gore artiyor."),
            (["bollinger"], "Fiyat bant sinirlarinda hareket ediyor, devam ihtimali yukseliyor."),
            (["momentum"], "Hareket hizi yukari yone gucleniyor."),
            (["trend strength", "trend"], "Yukselis egilimi gucleniyor."),
            (["price action", "market structure"], "Fiyat hareketleri alicilarin daha guclu oldugunu gosteriyor."),
            (["volume above average", "relative volume", "hacim"], "Islem hacmi arttigi icin hareketin devam etme ihtimali yukseliyor."),
            (["support bounce", "destek", "pullback"], "Destekten guc alarak yukari donmeye basladi."),
            (["breakout"], "Direnc bolgesi asilmaya yaklasiyor, yukari hareket hizlanabilir."),
            (["positive", "olumlu", "news"], "Olumlu haber akisinin fiyati destekleme ihtimali var."),
            (["negative", "olumsuz"], "Olumsuz gelismeler nedeniyle kisa vadede temkinli olunmali."),
            (["overbought", "elevated"], "Yukseliste zayiflama belirtileri olusuyor, kar satisi gelebilir."),
            (["no strong", "weak", "zayif"], "Kisa vadede net bir guc sinyali yok; dikkatli olunmali."),
        ]

        for keywords, translated in rules:
            if any(keyword in lowered for keyword in keywords):
                return translated

        return "Kisa vadede fiyat hareketi olumlu; yine de risk yonetimi onemli."

    def _build_plain_reasons(self, item: dict[str, Any], *, limit: int = 3) -> list[str]:
        candidates: list[str] = []
        candidates.extend([str(value) for value in item.get("reasons") or [] if str(value).strip()])
        candidates.extend([str(value) for value in item.get("fresh_signals") or [] if str(value).strip()])
        candidates.extend([str(value) for value in item.get("indicator_confirmations") or [] if str(value).strip()])
        candidates.extend([str(value) for value in item.get("market_structure_signals") or [] if str(value).strip()])

        seen: set[str] = set()
        plain: list[str] = []
        for raw in candidates:
            simplified = self._plain_turkish_reason(raw)
            key = simplified.lower()
            if not simplified or key in seen:
                continue
            seen.add(key)
            plain.append(simplified)
            if len(plain) >= limit:
                break

        if not plain:
            plain = [
                "Yukselis egilimi gucleniyor.",
                "Islem hacmi hareketi destekliyor.",
                "Kisa vadede firsat devam edebilir.",
            ]
        return plain[:limit]

    def _sanitize_user_output(self, text: str) -> str:
        sanitized = str(text)
        replacements = {
            "Higher High": "Yukselis egilimi gucleniyor",
            "Higher Low": "Alicilarin gucu artiyor",
            "Lower High": "Yukseliste zayiflama olabilir",
            "Lower Low": "Satis baskisi artiyor olabilir",
            "Cup and Handle": "Yukari yonlu hazirlik formu",
            "RSI": "kisa vade denge gostergesi",
            "ATR": "hareketlilik seviyesi",
            "EMA": "fiyat ortalama yonu",
            "MACD": "alici-satici guc farki",
            "Bollinger": "fiyat bant araligi",
            "Momentum": "hareket hizi",
            "Trend Strength": "trend gucu",
            "Price Action": "fiyat davranisi",
        }
        for source, target in replacements.items():
            sanitized = sanitized.replace(source, target)
            sanitized = sanitized.replace(source.lower(), target)
            sanitized = sanitized.replace(source.upper(), target)
        return sanitized

    def _market_outlook_label(self, *, strong_count: int, medium_count: int, risky_count: int) -> tuple[str, str]:
        if strong_count >= max(2, medium_count) and risky_count <= (strong_count + medium_count):
            return "🟢", "Olumlu"
        if risky_count > (strong_count + medium_count):
            return "🔴", "Dikkatli olunmali"
        return "🟡", "Kararsiz"

    def _build_bist_summary(
        self,
        *,
        started_at: float,
        analyzed_total: int,
        hard_filtered: int,
        scored_total: int,
        eligible_total: int,
        top_20: list[dict[str, Any]],
        top_10: list[dict[str, Any]],
        top_5: list[dict[str, Any]],
        regime_snapshot: dict[str, Any],
        scan_scope: str,
        bist100_priority_enabled: bool,
    ) -> dict[str, Any]:
        def _pick_best(items: list[dict[str, Any]], key_fn) -> dict[str, Any] | None:
            if not items:
                return None
            return dict(max(items, key=key_fn))

        best_opportunity = _pick_best(top_20, lambda item: float(item.get("total_score") or 0.0))
        riskiest_opportunity = _pick_best(top_20, lambda item: -float(item.get("risk_reward_ratio") or 0.0))
        strongest_news = _pick_best(top_20, lambda item: float(item.get("news_score") or 0.0))
        strongest_technical = _pick_best(
            top_20,
            lambda item: float(item.get("component_scores", {}).get("graph_structure", 0.0)) + float(item.get("component_scores", {}).get("trend", 0.0)),
        )
        highest_volume_growth = _pick_best(top_20, lambda item: float(item.get("relative_volume") or 0.0))

        return {
            "market": "BIST",
            "analyzed_total": int(analyzed_total),
            "hard_filtered": int(hard_filtered),
            "scored_total": int(scored_total),
            "eligible_total": int(eligible_total),
            "top_20": [
                {
                    "rank": int(item.get("rank") or index + 1),
                    "ticker": str(item.get("ticker") or ""),
                    "company_name": str(item.get("company_name") or ""),
                    "total_score": round(float(item.get("total_score") or 0.0), 2),
                    "decision": str(item.get("decision") or "WATCH"),
                    "risk_reward_ratio": round(float(item.get("risk_reward_ratio") or 0.0), 2),
                    "component_scores": dict(item.get("component_scores") or {}),
                    "score_lines": list(item.get("score_lines") or []),
                    "reasons": list(item.get("reasons") or []),
                }
                for index, item in enumerate(top_20)
            ],
            "top_10": [str(item.get("ticker") or "") for item in top_10],
            "top_5": [str(item.get("ticker") or "") for item in top_5],
            "scan_scope": str(scan_scope),
            "bist100_priority_enabled": bool(bist100_priority_enabled),
            "market_regime": dict(regime_snapshot),
            "best_opportunity": best_opportunity,
            "riskiest_opportunity": riskiest_opportunity,
            "strongest_news": strongest_news,
            "strongest_technical": strongest_technical,
            "highest_volume_growth": highest_volume_growth,
            "elapsed_seconds": round(time.perf_counter() - started_at, 3),
            "generated_at": datetime.now(UTC).isoformat(),
        }

    def _bist_score_sort_key(self, item: dict[str, Any]) -> tuple[float, float, float, float, str]:
        component_scores = dict(item.get("component_scores") or {})
        graph_score = float(component_scores.get("graph_structure", 0.0))
        trend_score = float(component_scores.get("trend", 0.0))
        momentum_score = float(component_scores.get("momentum", 0.0))
        volume_score = float(component_scores.get("volume", 0.0))
        risk_reward = float(item.get("risk_reward_ratio") or 0.0)
        total_score = float(item.get("total_score") or 0.0)
        return (
            total_score,
            graph_score + trend_score,
            volume_score,
            momentum_score,
            risk_reward,
            str(item.get("ticker") or ""),
        )

    def run_bist_live_monitoring(self) -> dict[str, Any]:
        """Run the recurring BIST monitoring cycle and emit only new state changes."""

        if not self._bist_monitoring_window_open():
            logger.info("BIST live monitoring skipped outside configured market window")
            return {
                "market": "BIST",
                "skipped": True,
                "reason": "outside_market_window",
            }

        recommendations = self.generate_recommendations(market="BIST")
        summary = self._load_cached("bist_live_summary.json", default={})
        events = self._update_bist_opportunity_state(recommendations)

        telegram_result = None
        if events:
            telegram_result = self.telegram_notifier.send(self._format_bist_change_message(summary, events))

        return {
            "market": "BIST",
            "recommendations": len(recommendations),
            "events": len(events),
            "telegram": asdict(telegram_result) if telegram_result else None,
            "summary": summary,
        }

    def _update_bist_opportunity_state(self, recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        state = self._load_bist_state()
        active_by_ticker = self._ensure_state_mapping(state.get("active_opportunities"))
        sent_history = self._ensure_history_list(state.get("notification_history"))
        history_index = {str(entry.get("signature") or "") for entry in sent_history if isinstance(entry, dict)}

        current_tick = datetime.now(UTC).isoformat()
        current_by_ticker = {
            str(item.get("ticker") or "").strip().upper(): dict(item)
            for item in recommendations
            if str(item.get("ticker") or "").strip().upper()
        }

        events: list[dict[str, Any]] = []
        thresholds = dict(self.bist_opportunity_engine.config.get("thresholds") or {})
        strengthened_score_delta = float(thresholds.get("strengthened_score_delta", 5))
        strengthened_rr_delta = float(thresholds.get("strengthened_rr_delta", 0.2))
        weakened_score_delta = float(thresholds.get("weakened_score_delta", -5))
        exit_score = float(thresholds.get("exit_score", 35))

        for ticker, item in current_by_ticker.items():
            previous = dict(active_by_ticker.get(ticker) or {})
            current_score = float(item.get("total_score") or item.get("confidence") or 0.0)
            current_rr = float(item.get("risk_reward_ratio") or 0.0)
            current_stop = float(item.get("stop_loss") or 0.0)
            current_target = float(item.get("current_target") or 0.0)
            current_price = float(item.get("current_price") or 0.0)
            current_state = "ACTIVE"

            if previous:
                previous_score = float(previous.get("total_score") or previous.get("confidence") or 0.0)
                previous_rr = float(previous.get("risk_reward_ratio") or 0.0)
                previous_stop = float(previous.get("stop_loss") or 0.0)
                previous_target = float(previous.get("current_target") or 0.0)

                if current_price > 0 and current_stop > 0 and current_price <= current_stop:
                    current_state = "EXIT"
                elif current_price > 0 and current_target > 0 and current_price >= current_target:
                    current_state = "CLOSED"
                elif current_score - previous_score >= strengthened_score_delta or current_rr - previous_rr >= strengthened_rr_delta:
                    current_state = "STRENGTHENED"
                elif current_score - previous_score <= weakened_score_delta or (previous_stop > 0 and current_stop > 0 and current_stop < previous_stop):
                    current_state = "WEAKENED"
                elif current_score < exit_score:
                    current_state = "EXIT"
            else:
                current_state = "NEW"

            item["status"] = current_state
            item["updated_at"] = current_tick
            item["last_notified_state"] = current_state
            active_by_ticker[ticker] = item

            if current_state == "ACTIVE":
                continue

            signature = self._bist_event_signature(ticker, current_state, item)
            if signature in history_index:
                continue

            event = {
                "ticker": ticker,
                "state": current_state,
                "signature": signature,
                "score": round(current_score, 2),
                "risk_reward_ratio": round(current_rr, 2),
                "price": round(current_price, 4),
                "stop_loss": round(current_stop, 4),
                "current_target": round(current_target, 4),
                "company_name": str(item.get("company_name") or ticker),
                "summary": list(item.get("reasons") or [])[:4],
                "ai_summary": str(item.get("ai_summary") or "").strip(),
            }
            events.append(event)
            sent_history.append({
                "signature": signature,
                "ticker": ticker,
                "state": current_state,
                "notified_at": current_tick,
                "score": round(current_score, 2),
            })

        for ticker, previous in list(active_by_ticker.items()):
            if ticker in current_by_ticker:
                continue

            previous_score = float(previous.get("total_score") or previous.get("confidence") or 0.0)
            current_state = "EXIT" if previous_score >= exit_score else "WEAKENED"
            signature = self._bist_event_signature(ticker, current_state, previous)
            if signature in history_index:
                continue

            event = {
                "ticker": ticker,
                "state": current_state,
                "signature": signature,
                "score": round(previous_score, 2),
                "risk_reward_ratio": round(float(previous.get("risk_reward_ratio") or 0.0), 2),
                "price": round(float(previous.get("current_price") or 0.0), 4),
                "stop_loss": round(float(previous.get("stop_loss") or 0.0), 4),
                "current_target": round(float(previous.get("current_target") or 0.0), 4),
                "company_name": str(previous.get("company_name") or ticker),
                "summary": list(previous.get("reasons") or [])[:4],
                "ai_summary": str(previous.get("ai_summary") or "").strip(),
            }
            events.append(event)
            sent_history.append({
                "signature": signature,
                "ticker": ticker,
                "state": current_state,
                "notified_at": current_tick,
                "score": round(previous_score, 2),
            })

        state["active_opportunities"] = active_by_ticker
        state["notification_history"] = sent_history
        state["updated_at"] = current_tick
        self._save_if_changed("bist_opportunity_state.json", state)
        self._save_if_changed("bist_notification_history.json", sent_history)
        return events

    def _format_bist_change_message(self, summary: dict[str, Any], events: list[dict[str, Any]]) -> str:
        date_text = format_istanbul_datetime(pattern="%d.%m.%Y")
        time_text = format_istanbul_datetime(pattern="%H:%M")
        lines = ["📡 BIST Canli Firsatlar", "", f"📅 {date_text}", f"🕐 {time_text}", ""]

        if isinstance(summary, dict) and summary:
            lines.extend(
                [
                    f"Analiz edilen hisse: {int(summary.get('analyzed_total', 0))}",
                    f"Aktif firsat havuzu: {len(summary.get('top_20', []))}",
                    "",
                ]
            )

        for event in events[:6]:
            state = str(event.get("state") or "ACTIVE").upper()
            state_icon = "🟡"
            state_text = "Guncel"
            if state in {"NEW", "STRENGTHENED"}:
                state_icon = "🟢"
                state_text = "Gucleniyor"
            elif state in {"WEAKENED", "EXIT"}:
                state_icon = "🔴"
                state_text = "Temkinli"

            current_price = float(event.get("price") or 0.0)
            target_price = float(event.get("current_target") or 0.0)
            stop_price = float(event.get("stop_loss") or 0.0)
            expected_gain = self._compute_gain_pct(base_price=current_price, target_price=target_price)

            lines.extend(
                [
                    f"{state_icon} {event['ticker']} - {state_text}",
                    f"Alis: {current_price:.2f} TL",
                    f"Zarar Durdur: {stop_price:.2f} TL",
                    f"Bugunku Potansiyel: %{expected_gain:.1f}",
                ]
            )
            if event.get("summary"):
                plain_summary = [
                    self._plain_turkish_reason(str(item))
                    for item in list(event.get("summary") or [])
                ]
                plain_summary = [item for item in plain_summary if item]
                if plain_summary:
                    lines.append(f"Neden: {plain_summary[0]}")
            if event.get("ai_summary"):
                lines.append("Haber etkisi: Olumlu akis hareketi destekliyor.")
            lines.append("──────────────────")

        analyzed_total = int(summary.get("analyzed_total", 0)) if isinstance(summary, dict) else 0
        strong_count = sum(1 for event in events if str(event.get("state") or "").upper() in {"NEW", "STRENGTHENED"})
        medium_count = sum(1 for event in events if str(event.get("state") or "").upper() in {"ACTIVE", "CLOSED"})
        risky_count = max(0, analyzed_total - strong_count - medium_count)
        outlook_icon, outlook_text = self._market_outlook_label(
            strong_count=strong_count,
            medium_count=medium_count,
            risky_count=risky_count,
        )

        lines.extend(
            [
                "",
                "📊 Genel Durum",
                "",
                f"Bugun guclu yukselis beklenen hisse sayisi: {strong_count}",
                f"Orta seviyede firsat: {medium_count}",
                f"Riskli gorulen hisse: {risky_count}",
                "Piyasa gorunumu:",
                f"{outlook_icon} {outlook_text}",
            ]
        )

        return self._sanitize_user_output("\n".join(lines))

    def _bist_event_signature(self, ticker: str, state: str, item: dict[str, Any]) -> str:
        score_bucket = round(float(item.get("total_score") or item.get("confidence") or 0.0), 1)
        rr_bucket = round(float(item.get("risk_reward_ratio") or 0.0), 2)
        stop_bucket = round(float(item.get("stop_loss") or 0.0), 4)
        target_bucket = round(float(item.get("current_target") or 0.0), 4)
        return f"{ticker}:{state}:{score_bucket}:{rr_bucket}:{stop_bucket}:{target_bucket}"

    def _load_bist_state(self) -> dict[str, Any]:
        state = self._load_cached("bist_opportunity_state.json", default={})
        if not isinstance(state, dict):
            return {}
        return state

    def _ensure_state_mapping(self, value: Any) -> dict[str, dict[str, Any]]:
        if not isinstance(value, dict):
            return {}
        return {
            str(key).strip().upper(): dict(item)
            for key, item in value.items()
            if str(key).strip().upper() and isinstance(item, dict)
        }

    def _ensure_history_list(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, dict)]

    def _bist_monitoring_window_open(self) -> bool:
        try:
            from datetime import time as time_type
            from zoneinfo import ZoneInfo

            open_hour = int(settings.scheduler_bist_live_start_hour)
            open_minute = int(settings.scheduler_bist_live_start_minute)
            close_hour = int(settings.scheduler_bist_live_end_hour)
            close_minute = int(settings.scheduler_bist_live_end_minute)
            now_local = datetime.now(UTC).astimezone(ZoneInfo(settings.timezone))
            start = time_type(open_hour, open_minute)
            end = time_type(close_hour, close_minute)
            now_time = now_local.time()
            return start <= now_time <= end
        except Exception:
            return True

    def notify_recommendations(
        self,
        *,
        market: str | None = None,
        include_portfolio: bool = True,
        report_title: str | None = None,
        recommendations_override: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Send latest recommendations via configured notifiers."""

        storage_file = "recommendations.json"
        normalized_market = self._normalize_market_name(market or "")
        if normalized_market == "BIST":
            storage_file = "bist_recommendations.json"
        elif normalized_market == "US":
            storage_file = "us_recommendations.json"

        recommendations = list(recommendations_override or [])
        if not recommendations and not settings.live_only_mode:
            recommendations = self.storage.load(storage_file, default=[])
        if not recommendations:
            recommendations = self.generate_recommendations(market=market)
        portfolio_analysis = self.analyze_portfolio_positions() if include_portfolio else []
        selection_stats = self._get_selection_stats(normalized_market)

        ai_market_summary: str | None = None
        ai_recommendation_summary: str | None = None
        ai_news_summary: str | None = None
        try:
            ai_market_summary = self.gemini_service.summarize_market(recommendations)
            ai_recommendation_summary = self.gemini_service.summarize_recommendations(recommendations)
            news_analysis = self._load_cached("news_analysis.json", default=[])
            ai_news_summary = self.gemini_service.summarize_news(news_analysis)
        except Exception as exc:
            logger.warning("Gemini daily summary failed: %s", exc)
        telegram_summary = "\n\n".join(
            [
                value
                for value in [ai_market_summary, ai_recommendation_summary, ai_news_summary]
                if isinstance(value, str) and value.strip()
            ]
        )
        telegram_message = self._format_telegram_message(
            recommendations,
            report_title=report_title,
            portfolio_analysis=portfolio_analysis,
            ai_market_summary=telegram_summary or ai_market_summary,
            selection_stats=selection_stats,
        )

        telegram_result = self.telegram_notifier.send(telegram_message)

        return {
            "telegram": asdict(telegram_result),
        }

    def send_bist_daily_report(self) -> dict[str, Any]:
        """Run BIST-only daily flow and push Telegram report."""

        started_at = time.perf_counter()
        recommendations = self.generate_recommendations(market="BIST")
        notifications = self.notify_recommendations(
            market="BIST",
            include_portfolio=False,
            report_title="📈 BIST Daily Report",
            recommendations_override=recommendations,
        )
        stats = self._get_selection_stats("BIST")
        logger.info(
            "BIST | Toplam Hisse=%s | Elenen=%s | Skorlanan=%s | Top20=%s | Top10=%s | TopFinal=%s | Toplam Sure=%.2fs | Gemini Cagrisi=%s | API Key=%s",
            stats.get("analyzed_total", 0),
            stats.get("filter_rejected", 0),
            stats.get("scored_total", 0),
            stats.get("top_20", 0),
            stats.get("top_10", 0),
            stats.get("top_final", stats.get("top_5", 0)),
            float(time.perf_counter() - started_at),
            stats.get("gemini_calls", 0),
            stats.get("gemini_last_key_label", "N/A"),
        )
        return {
            "market": "BIST",
            "recommendations": len(recommendations),
            "items": recommendations,
            "notifications": notifications,
            "stats": stats,
            "live_only_mode": bool(settings.live_only_mode),
        }

    def send_us_daily_report(self) -> dict[str, Any]:
        """Run US-only daily flow and push Telegram report."""

        started_at = time.perf_counter()
        self.collect_market(markets=["US"])
        self.analyze_news()
        self.analyze_tickers()
        recommendations = self.generate_recommendations(market="US")
        notifications = self.notify_recommendations(
            market="US",
            include_portfolio=False,
            report_title="🇺🇸 US Market Report",
        )
        stats = self._get_selection_stats("US")
        logger.info(
            "US | Toplam Hisse=%s | Helal Filtre=%s | AI Analizi=%s | Onerilen=%s | Toplam Sure=%.2fs | Gemini Cagrisi=%s | API Key=%s",
            stats.get("analyzed_total", 0),
            stats.get("halal_passed", 0),
            stats.get("ai_candidates", 0),
            stats.get("recommended", 0),
            float(time.perf_counter() - started_at),
            stats.get("gemini_calls", 0),
            stats.get("gemini_last_key_label", "N/A"),
        )
        return {
            "market": "US",
            "recommendations": len(recommendations),
            "notifications": notifications,
            "stats": stats,
        }

    def send_portfolio_update(self) -> dict[str, Any]:
        """Analyze open positions and send portfolio-only update."""

        self.collect_market()
        self.analyze_market()
        portfolio_analysis = self.analyze_portfolio_positions()
        message = self._format_telegram_message(
            recommendations=[],
            report_title="📂 Portfolio Update",
            portfolio_analysis=portfolio_analysis,
            ai_market_summary=None,
        )
        telegram_result = self.telegram_notifier.send(message)
        return {
            "portfolio_positions": len(portfolio_analysis),
            "telegram": asdict(telegram_result),
        }

    def analyze_portfolio_positions(self) -> list[dict[str, Any]]:
        """Evaluate current holdings and generate management decisions."""

        positions = self._load_cached("portfolio.json", default=[])
        market_analysis = self._load_cached("market_analysis.json", default=[])
        analysis_by_ticker = {
            str(item.get("ticker") or "").strip().upper(): item
            for item in market_analysis
            if isinstance(item, dict)
        }

        evaluated = self.portfolio_engine.evaluate_positions(positions, analysis_by_ticker)
        self._save_if_changed("portfolio_analysis.json", evaluated)
        return evaluated

    def send_daily_recommendations(self) -> dict[str, Any]:
        """Run full weekday pipeline and send top recommendations."""

        collection = self.collect_all()
        news = self.analyze_news()
        market = self.analyze_market()
        tickers = self.analyze_tickers()
        recommendations = self.generate_recommendations()
        portfolio_analysis = self.analyze_portfolio_positions()
        notifications = self.notify_recommendations()
        history_entries = self.archive_today()
        performance = self.update_history_performance()

        return {
            "collection": collection,
            "news": news,
            "market": market,
            "tickers": tickers,
            "recommendations": len(recommendations),
            "portfolio_positions": len(portfolio_analysis),
            "history": len(history_entries),
            "performance": performance,
            "notifications": notifications,
        }

    def archive_today(self) -> list[dict[str, Any]]:
        """Archive current recommendations into history storage."""

        recommendations = self._load_cached("recommendations.json", default=[])
        if not recommendations:
            return self._load_cached("history.json", default=[])

        history = list(self._load_cached("history.json", default=[]))
        now_utc = datetime.now(UTC)
        date_text = now_utc.date().isoformat()

        existing_ids: set[str] = set()
        for day in history:
            for item in day.get("recommendations", []):
                value = str(item.get("id") or "")
                if value:
                    existing_ids.add(value)

        generated: list[dict[str, Any]] = []

        for item in recommendations:
            ticker = str(item.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            generated_time = now_utc.isoformat()
            entry_id = build_item_id(ticker, generated_time, "paper")
            if entry_id in existing_ids:
                continue

            entry = float(item.get("entry_price") or 0.0)
            stop = float(item.get("stop_loss") or 0.0)
            target = float(item.get("current_target") or 0.0)
            tp1 = float(item.get("take_profit_1") or target)
            tp2 = float(item.get("take_profit_2") or max(target, entry))
            tp3 = float(item.get("take_profit_3") or (tp2 + max(tp2 - entry, 0.0)))

            generated.append(
                {
                    "id": entry_id,
                    "ticker": ticker,
                    "company": str(item.get("company_name") or ticker),
                    "generated_time": generated_time,
                    "opened_at": generated_time,
                    "closed_at": "",
                    "entry": round(entry, 4),
                    "exit": 0.0,
                    "stop": round(stop, 4),
                    "tp1": round(tp1, 4),
                    "tp2": round(tp2, 4),
                    "tp3": round(tp3, 4),
                    "tp4": round(float(item.get("take_profit_4") or tp3), 4),
                    "take_profit_levels": list(item.get("take_profit_levels") or []),
                    "risk_reward": round(float(item.get("risk_reward_ratio") or 0.0), 4),
                    "current_target": round(target, 4),
                    "entry_range_low": round(float(item.get("entry_range_low") or entry), 4),
                    "entry_range_high": round(float(item.get("entry_range_high") or entry), 4),
                    "entry_strategy": str(item.get("entry_strategy") or "Unknown"),
                    "entry_status": str(item.get("entry_status") or "WAIT"),
                    "limit_entry_price": round(float(item.get("limit_entry_price") or entry), 4),
                    "trade_instruction": str(item.get("trade_instruction") or ""),
                    "confidence": round(float(item.get("confidence") or 0.0), 2),
                    "overall_score": round(float(item.get("overall_score") or 0.0), 2),
                    "technical_score": round(float(item.get("technical_score") or 0.0), 2),
                    "news_score": round(float(item.get("news_score") or 0.0), 2),
                    "current_price": round(float(item.get("current_price") or entry), 4),
                    "decision_reasons": list(item.get("reasons") or []),
                    "ai_summary": str(item.get("ai_summary") or ""),
                    "status": "OPEN",
                    "result": "PENDING",
                    "risk_reward_result": "PENDING",
                    "profit_percent": 0.0,
                    "profit_pct": 0.0,
                    "loss_percent": 0.0,
                    "holding_days": 0,
                    "holding_time_hours": 0.0,
                    "reached_tp": "NONE",
                    "stopped": False,
                    "max_gain": 0.0,
                    "max_drawdown": 0.0,
                }
            )
            existing_ids.add(entry_id)

        if generated:
            history.append(
                {
                    "date": date_text,
                    "recommendations": generated,
                }
            )

        self._save_if_changed("history.json", history)
        return history

    def get_history(self) -> list[dict[str, Any]]:
        """Return archived recommendation history."""

        return self.storage.load("history.json", default=[])

    def get_performance(self) -> dict[str, Any]:
        """Return current paper trading performance statistics."""

        return self.storage.load("performance.json", default={})

    def update_history_performance(self) -> dict[str, Any]:
        """Evaluate pending/open history entries and refresh performance statistics."""

        history = list(self._load_cached("history.json", default=[]))
        performance = self._calculate_performance(history)
        self._save_if_changed("history.json", history)
        self._save_if_changed("performance.json", performance)
        return performance

    def finalize_day_performance(self) -> dict[str, Any]:
        """Close active daily recommendations using the latest market snapshot and refresh performance."""

        history = deepcopy(self._load_cached("history.json", default=[]))
        market_lookup = self._market_snapshot_lookup()
        now_utc = datetime.now(UTC)

        for day in history:
            entries = day.get("recommendations", [])
            if not isinstance(entries, list):
                continue

            for entry in entries:
                status = str(entry.get("status") or "OPEN").upper()
                if status == "CLOSED":
                    continue

                ticker = str(entry.get("ticker") or "").upper()
                snapshot = market_lookup.get(ticker)
                if snapshot is None:
                    entry["status"] = "UNKNOWN"
                    continue

                opened_at = str(entry.get("opened_at") or entry.get("generated_time") or "")
                opened_dt = now_utc
                if opened_at:
                    try:
                        opened_dt = datetime.fromisoformat(opened_at.replace("Z", "+00:00")).astimezone(UTC)
                    except ValueError:
                        opened_dt = now_utc

                entry_price = float(entry.get("entry") or entry.get("entry_price") or 0.0)
                stop = float(entry.get("stop") or entry.get("stop_loss") or 0.0)
                tp1 = float(entry.get("tp1") or entry.get("take_profit_1") or 0.0)
                tp2 = float(entry.get("tp2") or entry.get("take_profit_2") or 0.0)
                current_price = float(snapshot.get("last_price") or 0.0)
                high = float(snapshot.get("high") or current_price)
                low = float(snapshot.get("low") or current_price)

                if current_price <= 0 or entry_price <= 0:
                    entry["status"] = "UNKNOWN"
                    continue

                exit_price = current_price
                risk_reward_result = "CLOSE"
                result = "FLAT"

                if stop > 0 and low <= stop:
                    exit_price = stop
                    risk_reward_result = "STOP"
                    result = "LOSE"
                elif tp2 > 0 and high >= tp2:
                    exit_price = tp2
                    risk_reward_result = "TP2"
                    result = "WIN"
                elif tp1 > 0 and high >= tp1:
                    exit_price = tp1
                    risk_reward_result = "TP1"
                    result = "WIN"
                elif exit_price > entry_price:
                    risk_reward_result = "CLOSE_ABOVE_ENTRY"
                    result = "WIN"
                elif exit_price < entry_price:
                    risk_reward_result = "CLOSE_BELOW_ENTRY"
                    result = "LOSE"

                profit_pct = ((exit_price - entry_price) / entry_price) * 100.0
                max_gain = ((high - entry_price) / entry_price) * 100.0
                max_drawdown = ((low - entry_price) / entry_price) * 100.0
                holding_days = max(0, (now_utc.date() - opened_dt.date()).days)

                entry["opened_at"] = opened_dt.isoformat()
                entry["closed_at"] = now_utc.isoformat()
                entry["exit"] = round(exit_price, 4)
                entry["current_price"] = round(current_price, 4)
                entry["status"] = "CLOSED"
                entry["result"] = result
                entry["risk_reward_result"] = risk_reward_result
                entry["holding_days"] = int(holding_days)
                entry["holding_time_hours"] = round(max(0.0, (now_utc - opened_dt).total_seconds() / 3600.0), 2)
                entry["profit_percent"] = round(max(profit_pct, 0.0), 4)
                entry["profit_pct"] = round(profit_pct, 4)
                entry["loss_percent"] = round(abs(min(profit_pct, 0.0)), 4)
                entry["max_gain"] = round(max(max_gain, 0.0), 4)
                entry["max_drawdown"] = round(abs(min(max_drawdown, 0.0)), 4)
                entry["reached_tp"] = risk_reward_result if risk_reward_result.startswith("TP") else "NONE"
                entry["stopped"] = bool(risk_reward_result == "STOP")

        performance = self._calculate_performance(history)
        self._save_if_changed("history.json", history)
        self._save_if_changed("performance.json", performance)
        return performance

    def gemini_health(self) -> dict[str, Any]:
        """Return Gemini feature health without interrupting the pipeline."""

        enabled = self.gemini_service.enabled
        healthy = self.gemini_service.health() if enabled else False
        diagnostics = self.gemini_service.diagnostics_snapshot()
        return {
            "enabled": self.gemini_service.enabled,
            "healthy": healthy,
            "diagnostics": diagnostics,
        }

    def _market_frame(self, market_payload: list[dict[str, Any]]) -> pd.DataFrame:
        rows: list[dict[str, float]] = []
        for item in market_payload:
            price = float(item.get("last_price") or item.get("price") or 0.0)
            if price <= 0:
                continue

            rows.append(
                {
                    "open": float(item.get("open") or price),
                    "high": float(item.get("high") or price * 1.01),
                    "low": float(item.get("low") or price * 0.99),
                    "close": float(item.get("close") or price),
                    "volume": float(item.get("volume") or 0.0),
                }
            )

        if not rows:
            rows = [
                {
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 1_000_000.0,
                }
            ]

        frame = pd.DataFrame(rows)
        return frame

    def _financial_metrics(self, frame: pd.DataFrame) -> dict[str, float]:
        returns = frame["close"].pct_change().dropna()
        avg_return_pct = float(returns.mean() * 100) if not returns.empty else 0.0
        volatility_pct = float(returns.std(ddof=0) * 100) if not returns.empty else 0.0
        liquidity_ratio = float((frame["volume"].iloc[-1] / frame["volume"].mean()) if frame["volume"].mean() else 1.0)

        return {
            "revenue_growth": avg_return_pct,
            "net_margin": max(0.0, 20.0 - volatility_pct),
            "debt_to_equity": max(0.1, min(3.0, volatility_pct / 10.0)),
            "current_ratio": max(0.8, min(3.0, liquidity_ratio)),
            "roe": max(5.0, min(30.0, avg_return_pct + 10.0)),
        }

    def _analysis_reasons(self, scores: dict[str, float]) -> dict[str, list[str]]:
        reasons: dict[str, list[str]] = {}
        for name, value in scores.items():
            if value >= 75:
                reasons[name] = [f"{name.capitalize()} score is strong ({value:.1f})"]
            elif value >= 55:
                reasons[name] = [f"{name.capitalize()} score is moderate ({value:.1f})"]
            else:
                reasons[name] = [f"{name.capitalize()} score is weak ({value:.1f})"]
        return reasons

    def _market_history_frame(self, rows: list[dict[str, Any]]) -> pd.DataFrame:
        prepared: list[dict[str, float]] = []
        for row in rows:
            price = float(row.get("last_price") or row.get("price") or row.get("close") or 0.0)
            if price <= 0:
                continue

            open_price = float(row.get("open") or price)
            inferred_base_high = max(price, open_price)
            inferred_base_low = min(price, open_price)
            high_price = float(row.get("high") or (inferred_base_high * 1.01))
            low_price = float(row.get("low") or (inferred_base_low * 0.99))
            volume = float(row.get("volume") or 0.0)
            change_percent = row.get("change_percent")
            if change_percent is None and open_price > 0:
                change_percent = ((price - open_price) / open_price) * 100

            prepared.append(
                {
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": price,
                    "volume": volume,
                    "daily_change_pct": float(change_percent or 0.0),
                }
            )

        if 1 <= len(prepared) < 260:
            latest = prepared[-1]
            close_now = float(latest["close"])
            change_pct = float(latest.get("daily_change_pct") or 0.0) / 100.0
            previous_close = close_now / (1.0 + change_pct) if abs(1.0 + change_pct) > 1e-9 else close_now

            points_needed = 260 - len(prepared)
            seed_close = max(0.01, previous_close)
            drift = (close_now - seed_close) / max(1, points_needed)
            base_volume = max(1.0, float(latest.get("volume") or 1.0))

            synthetic: list[dict[str, float]] = []
            for step in range(points_needed, 0, -1):
                synthetic_close = max(0.01, close_now - (drift * step))
                synthetic_open = synthetic_close * (1.0 - (change_pct * 0.25))
                synthetic_high = max(synthetic_open, synthetic_close) * 1.005
                synthetic_low = min(synthetic_open, synthetic_close) * 0.995
                synthetic_volume = max(1.0, base_volume * (0.9 + min(step / 120.0, 0.1)))

                synthetic.append(
                    {
                        "open": float(synthetic_open),
                        "high": float(synthetic_high),
                        "low": float(synthetic_low),
                        "close": float(synthetic_close),
                        "volume": float(synthetic_volume),
                        "daily_change_pct": float(change_pct * 100.0),
                    }
                )

            prepared = [*synthetic, *prepared]

        if not prepared:
            prepared.append(
                {
                    "open": 100.0,
                    "high": 101.0,
                    "low": 99.0,
                    "close": 100.0,
                    "volume": 0.0,
                    "daily_change_pct": 0.0,
                }
            )

        return pd.DataFrame(prepared)

    def _candles_from_frame(self, frame: pd.DataFrame, *, limit: int) -> list[dict[str, float]]:
        candles: list[dict[str, float]] = []
        if frame.empty:
            return candles

        for _, row in frame.tail(limit).iterrows():
            candles.append(
                {
                    "open": round(float(row.get("open") or 0.0), 6),
                    "high": round(float(row.get("high") or 0.0), 6),
                    "low": round(float(row.get("low") or 0.0), 6),
                    "close": round(float(row.get("close") or 0.0), 6),
                    "volume": round(float(row.get("volume") or 0.0), 6),
                }
            )
        return candles

    def _timeframe_snapshot(self, frame: pd.DataFrame) -> dict[str, Any]:
        if frame.empty:
            return {
                "trend_1h": "Neutral",
                "trend_1d": "Neutral",
                "trend_strength_1h": 0,
                "trend_strength_1d": 0,
            }

        daily_tail = frame.tail(60)
        hourly_tail = frame.tail(24)

        def _trend_from_tail(tail: pd.DataFrame) -> tuple[str, int]:
            close = tail["close"].astype(float)
            ema_fast = ema(close, 20)
            ema_slow = ema(close, 50)
            fast = float(ema_fast.iloc[-1])
            slow = float(ema_slow.iloc[-1])
            price = float(close.iloc[-1])
            spread_pct = ((fast - slow) / max(price, 1e-9)) * 100.0
            strength = int(max(0.0, min(100.0, abs(spread_pct) * 35.0)))
            if fast > slow:
                return "Bullish", strength
            if fast < slow:
                return "Bearish", strength
            return "Neutral", strength

        trend_1d, trend_strength_1d = _trend_from_tail(daily_tail)
        trend_1h, trend_strength_1h = _trend_from_tail(hourly_tail)
        return {
            "trend_1h": trend_1h,
            "trend_1d": trend_1d,
            "trend_strength_1h": trend_strength_1h,
            "trend_strength_1d": trend_strength_1d,
        }

    def _build_market_profile(
        self,
        ticker: str,
        frame: pd.DataFrame,
        scoring: dict[str, float],
    ) -> dict[str, Any]:
        close = frame["close"].astype(float)
        volume = frame["volume"].astype(float)

        ema20_series = ema(close, 20)
        ema50_series = ema(close, 50)
        ema200_series = ema(close, 200)
        sma20_series = sma(close, 20)
        rsi14_series = rsi(close, 14)
        macd_frame = macd(close)
        atr_series = atr(frame)
        boll = bollinger_bands(close)
        volume_frame = volume_analysis(volume)
        gap_frame = gap_detection(frame[["open", "close"]])

        price = float(close.iloc[-1])
        daily_change_pct = float(frame["daily_change_pct"].iloc[-1])
        current_volume = float(volume.iloc[-1])
        average_volume = float(volume_frame["volume_sma"].iloc[-1])
        relative_volume = float(volume_frame["volume_ratio"].iloc[-1])
        gap_up = bool(gap_frame["gap_up"].iloc[-1])
        gap_down = bool(gap_frame["gap_down"].iloc[-1])
        ema20_value = float(ema20_series.iloc[-1])
        ema50_value = float(ema50_series.iloc[-1])
        ema200_value = float(ema200_series.iloc[-1])
        sma20_value = float(sma20_series.iloc[-1])
        rsi14_value = float(rsi14_series.iloc[-1])
        macd_value = float(macd_frame["macd"].iloc[-1])
        macd_signal = float(macd_frame["signal"].iloc[-1])
        atr_value = float(atr_series.iloc[-1])
        boll_upper = float(boll["upper"].iloc[-1])
        boll_lower = float(boll["lower"].iloc[-1])
        support = float(frame["low"].rolling(window=50, min_periods=1).min().iloc[-1])
        resistance = float(frame["high"].rolling(window=50, min_periods=1).max().iloc[-1])

        trend = "Neutral"
        if ema20_value > ema50_value > ema200_value and price >= ema20_value:
            trend = "Bullish"
        elif ema20_value < ema50_value < ema200_value and price <= ema20_value:
            trend = "Bearish"

        macd_state = "Neutral"
        if macd_value > macd_signal:
            macd_state = "Bullish"
        elif macd_value < macd_signal:
            macd_state = "Bearish"

        reasons: list[str] = []
        weighted_points = 0.0
        total_weight = float(sum(scoring.values())) if scoring else 1.0

        if ema20_value > ema50_value:
            weighted_points += float(scoring.get("ema_cross", 0.0))
            reasons.append("EMA20 above EMA50")

        if ema50_value > ema200_value:
            weighted_points += float(scoring.get("trend", 0.0)) * 0.5
            reasons.append("EMA50 above EMA200")

        if macd_state == "Bullish":
            weighted_points += float(scoring.get("macd_cross", 0.0))
            reasons.append("MACD bullish crossover")

        if gap_up or gap_down:
            weighted_points += float(scoring.get("gap", 0.0))
            reasons.append("Gap detected")

        if relative_volume > 1.0:
            volume_weight = float(scoring.get("volume", 0.0))
            weighted_points += volume_weight * min(relative_volume / 2.0, 1.0)
            reasons.append("Volume above average")

        if 45.0 <= rsi14_value <= 62.0:
            weighted_points += float(scoring.get("rsi", 0.0))
            reasons.append("RSI in healthy zone")
        elif 30.0 <= rsi14_value < 40.0:
            weighted_points += float(scoring.get("rsi", 0.0)) * 0.5
            reasons.append("RSI recovery zone")
        elif 62.0 < rsi14_value <= 70.0:
            weighted_points += float(scoring.get("rsi", 0.0)) * 0.35
            reasons.append("RSI strong but elevated")

        if trend == "Bullish":
            weighted_points += float(scoring.get("trend", 0.0))
            reasons.append("Overall trend bullish")
        elif trend == "Neutral":
            weighted_points += float(scoring.get("trend", 0.0)) * 0.5

        if price <= support * 1.03:
            weighted_points += float(scoring.get("gap", 0.0)) * 0.35
            reasons.append("Support bounce zone")

        technical_score = int(round(max(0.0, min(100.0, (weighted_points / total_weight) * 100.0))))
        if not reasons:
            reasons.append("No strong technical signal")

        return {
            "ticker": ticker,
            "technical_score": technical_score,
            "trend": trend,
            "current_price": round(price, 4),
            "daily_change_pct": round(daily_change_pct, 4),
            "volume": round(current_volume, 4),
            "average_volume": round(average_volume, 4),
            "relative_volume": round(relative_volume, 4),
            "gap_up": gap_up,
            "gap_down": gap_down,
            "ema20": round(ema20_value, 4),
            "ema50": round(ema50_value, 4),
            "sma20": round(sma20_value, 4),
            "rsi14": round(rsi14_value, 4),
            "macd": macd_state,
            "macd_value": round(macd_value, 6),
            "macd_signal": round(macd_signal, 6),
            "atr": round(atr_value, 6),
            "bollinger_upper": round(boll_upper, 4),
            "bollinger_lower": round(boll_lower, 4),
            "support": round(support, 4),
            "resistance": round(resistance, 4),
            "reasons": reasons,
        }

    def _news_summary(self, analyzed_items: list[dict[str, Any]]) -> dict[str, int]:
        positive = sum(1 for item in analyzed_items if item.get("sentiment") == "Positive")
        negative = sum(1 for item in analyzed_items if item.get("sentiment") == "Negative")
        neutral = sum(1 for item in analyzed_items if item.get("sentiment") == "Neutral")
        return {
            "analyzed": len(analyzed_items),
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
        }

    def _average_news_score(self, analyzed_items: list[dict[str, Any]]) -> float:
        if not analyzed_items:
            return 50.0

        scores = [float(item.get("score", 50.0)) for item in analyzed_items]
        return sum(scores) / len(scores)

    def _ensure_news_keyword_config(self) -> None:
        filename = "news_keywords.json"
        if not self.config_storage.exists(filename):
            self.config_storage.save(filename, DEFAULT_NEWS_KEYWORDS)
            logger.info("Created default keyword config at storage/config/news_keywords.json")

    def _load_news_keyword_config(self) -> dict[str, dict[str, int]]:
        filename = "news_keywords.json"
        if not self.config_storage.exists(filename):
            self.config_storage.save(filename, DEFAULT_NEWS_KEYWORDS)

        config = self.config_storage.load(filename, default=DEFAULT_NEWS_KEYWORDS)
        positive = {
            str(key): int(value)
            for key, value in dict(config.get("positive", {})).items()
        }
        negative = {
            str(key): int(value)
            for key, value in dict(config.get("negative", {})).items()
        }
        return {"positive": positive, "negative": negative}

    def _ensure_technical_scoring_config(self) -> None:
        filename = "technical_scoring.json"
        if not self.config_storage.exists(filename):
            self.config_storage.save(filename, DEFAULT_TECHNICAL_SCORING)
            logger.info("Created technical scoring config at storage/config/technical_scoring.json")

    def _ensure_halal_filter_config(self) -> None:
        filename = "halal_filter.json"
        if not self.config_storage.exists(filename):
            self.config_storage.save(filename, DEFAULT_HALAL_FILTER)
            logger.info("Created halal filter config at storage/config/halal_filter.json")

    def _ensure_bist_scoring_config(self) -> None:
        filename = "bist_scoring.json"
        if not self.config_storage.exists(filename):
            self.config_storage.save(filename, {})
            logger.info("Created BIST scoring config at storage/config/bist_scoring.json")

    def _load_bist_scoring_config(self) -> dict[str, Any]:
        filename = "bist_scoring.json"
        if not self.config_storage.exists(filename):
            self.config_storage.save(filename, {})

        raw = self.config_storage.load(filename, default={})
        if not isinstance(raw, dict):
            return {}
        return raw

    def _load_technical_scoring_config(self) -> dict[str, float]:
        filename = "technical_scoring.json"
        if not self.config_storage.exists(filename):
            self.config_storage.save(filename, DEFAULT_TECHNICAL_SCORING)

        raw = self.config_storage.load(filename, default=DEFAULT_TECHNICAL_SCORING)
        return {str(key): float(value) for key, value in dict(raw).items()}

    def _load_halal_filter_config(self) -> dict[str, list[str]]:
        filename = "halal_filter.json"
        if not self.config_storage.exists(filename):
            self.config_storage.save(filename, DEFAULT_HALAL_FILTER)

        raw = self.config_storage.load(filename, default=DEFAULT_HALAL_FILTER)
        return {
            "blocked_tickers": [str(value).strip().upper() for value in raw.get("blocked_tickers", [])],
            "blocked_keywords": [str(value).strip().lower() for value in raw.get("blocked_keywords", [])],
            "blocked_sectors": [str(value).strip().lower() for value in raw.get("blocked_sectors", [])],
        }

    def _ensure_portfolio_file(self) -> None:
        if not self.storage.exists("portfolio.json"):
            self.storage.save("portfolio.json", [])

    def _format_recommendations_message(
        self,
        recommendations: list[dict[str, Any]],
        *,
        ai_market_summary: str | None = None,
    ) -> str:
        lines = ["📈 Gunun En Guclu Firsatlari", "", format_istanbul_datetime(pattern="%d.%m.%Y"), ""]
        for index, item in enumerate(recommendations, start=1):
            lines.extend(
                [
                    f"{index}) {str(item.get('ticker') or 'UNKNOWN')}",
                    f"Karar : {str(item.get('decision') or 'BUY')}",
                    f"Guven : {self._format_confidence(item.get('confidence'))}",
                    "---",
                ]
            )

        if ai_market_summary:
            lines.extend(["", "Today's AI Summary", str(ai_market_summary).strip()])

        return self._sanitize_user_output("\n".join(lines))

    def _format_telegram_message(
        self,
        recommendations: list[dict[str, Any]],
        *,
        report_title: str | None = None,
        portfolio_analysis: list[dict[str, Any]] | None = None,
        ai_market_summary: str | None = None,
        selection_stats: dict[str, Any] | None = None,
    ) -> str:
        date_text = format_istanbul_datetime(pattern="%d.%m.%Y")
        time_text = format_istanbul_datetime(pattern="%H:%M")
        lines = [
            str(report_title or "📡 BIST Canli Firsatlar"),
            "",
            f"📅 {date_text}",
            f"🕐 {time_text}",
        ]

        wait_only = (
            len(recommendations) == 1
            and str(recommendations[0].get("ticker") or "").upper() == "CASH"
            and str(recommendations[0].get("decision") or "").upper() == "WAIT IN CASH"
        )

        if wait_only:
            lines.extend(
                [
                    "",
                    "📌 Bugun minimum beklenen kazanc (%3) kriterine uyan uygun firsat bulunamadi.",
                    "Kisa vadede nakitte beklemek daha guvenli gorunuyor.",
                ]
            )
        else:
            ranked_recommendations = [
                dict(item)
                for item in recommendations
                if str(item.get("ticker") or "").upper() != "CASH"
            ]
            is_bist_report = any(
                self._normalize_market_name(item.get("market") or "") == "BIST"
                for item in ranked_recommendations
            )
            if is_bist_report:
                bist100_priority_set = self._load_bist100_priority_set()
            else:
                bist100_priority_set = set()

            if bist100_priority_set:
                ranked_recommendations.sort(
                    key=lambda item: self._rank_with_bist100_priority(item, bist100_priority_set)
                )
            else:
                ranked_recommendations.sort(key=self._expected_gain_sort_key)

            top_item = ranked_recommendations[0] if ranked_recommendations else {}
            if top_item:
                ticker = str(top_item.get("ticker") or "UNKNOWN")
                confidence = int(top_item.get("user_confidence") or self._user_confidence_score(top_item))
                entry_price = float(top_item.get("entry_price") or 0.0)
                target_price = float(top_item.get("current_target") or 0.0)
                stop_price = float(top_item.get("stop_loss") or 0.0)
                expected_gain = float(
                    top_item.get("expected_gain_pct")
                    or self._compute_gain_pct(base_price=entry_price, target_price=target_price)
                )
                today_potential = float(
                    top_item.get("today_potential_pct")
                    or self._compute_gain_pct(
                        base_price=float(top_item.get("current_price") or entry_price),
                        target_price=target_price,
                    )
                )
                reasons = self._build_plain_reasons(top_item, limit=3)

                lines.extend(
                    [
                        "",
                        "⭐ En Guclu Oneri",
                        "",
                        ticker,
                        "",
                        "🟢 Guven",
                        f"%{confidence}",
                        "",
                        "💰 Alis",
                        f"{entry_price:.2f} TL",
                        "",
                        "🛑 Zarar Durdur",
                        f"{stop_price:.2f} TL",
                        "",
                        "📈 Beklenen Kazanc",
                        f"%{expected_gain:.1f}",
                        "",
                        "🎯 Bugunku Potansiyel",
                        f"%{today_potential:.1f}",
                        "",
                        "Neden Oneriliyor?",
                        "",
                        f"✅ {reasons[0]}",
                        f"✅ {reasons[1] if len(reasons) > 1 else 'Alicilar satis yapanlardan daha guclu.'}",
                        f"✅ {reasons[2] if len(reasons) > 2 else 'Kisa vadede firsat devam edebilir.'}",
                        "",
                        "──────────────────",
                    ]
                )

            if len(ranked_recommendations) > 1:
                lines.append("Diger on plana cikan hisseler:")
                for extra in ranked_recommendations[1:5]:
                    extra_ticker = str(extra.get("ticker") or "UNKNOWN")
                    extra_gain = float(extra.get("expected_gain_pct") or 0.0)
                    extra_conf = int(extra.get("user_confidence") or self._user_confidence_score(extra))
                    lines.append(f"🟡 {extra_ticker} | Beklenen Kazanc: %{extra_gain:.1f} | Guven: %{extra_conf}")

        if portfolio_analysis:
            lines.extend(["", "📂 Acik Pozisyonlar"])
            for position in portfolio_analysis[:15]:
                lines.extend(
                    [
                        str(position.get("ticker") or "UNKNOWN"),
                        f"Kar : %{float(position.get('current_profit_pct') or 0.0):.2f}",
                        f"Karar : {str(position.get('decision') or 'HOLD')}",
                        f"Trend : {int(position.get('trend_strength') or 0)}",
                        f"Yeni Stop : {float(position.get('new_stop') or 0.0):.4f}",
                        "---",
                    ]
                )

        if ai_market_summary:
            lines.append("AI Piyasa Ozeti")
            lines.append(str(ai_market_summary).strip())

        analyzed_total = int(selection_stats.get("analyzed_total", 0)) if selection_stats else 0
        visible_recs = [
            item
            for item in recommendations
            if str(item.get("ticker") or "").upper() != "CASH"
        ]
        strong_count = sum(
            1
            for item in visible_recs
            if float(item.get("expected_gain_pct") or 0.0) >= 7.0
            and int(item.get("user_confidence") or self._user_confidence_score(item)) >= 70
        )
        medium_count = sum(
            1
            for item in visible_recs
            if 3.0 <= float(item.get("expected_gain_pct") or 0.0) < 7.0
        )
        risky_count = max(0, analyzed_total - strong_count - medium_count)
        outlook_icon, outlook_text = self._market_outlook_label(
            strong_count=strong_count,
            medium_count=medium_count,
            risky_count=risky_count,
        )

        lines.extend(
            [
                "",
                "📊 Genel Durum",
                "",
                f"Analiz edilen hisse: {analyzed_total}",
                f"Guclu firsat: {strong_count}",
                f"Orta firsat: {medium_count}",
                f"Riskli gorulen hisse: {risky_count}",
                "",
                "Bugun piyasa gorunumu:",
                f"{outlook_icon} {outlook_text}",
            ]
        )

        return self._sanitize_user_output("\n".join(lines))

    def _enrich_recommendations_with_ai(self, recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not recommendations:
            return recommendations

        news_payload = self._load_cached("news.json", default=[])
        kap_payload = self._load_cached("kap.json", default=[])
        enriched: list[dict[str, Any]] = []

        for item in recommendations:
            enriched_item = dict(item)
            ticker = str(item.get("ticker") or "").strip().upper()

            news_item = self._find_latest_item_for_ticker(news_payload, ticker)
            kap_item = self._find_latest_item_for_ticker(kap_payload, ticker)
            news_ai: dict[str, Any] | None = None
            kap_ai: dict[str, Any] | None = None

            try:
                news_ai = self.gemini_service.analyze_news(news_item)
            except Exception as exc:
                logger.warning("Gemini news analysis failed for %s: %s", ticker, exc)

            try:
                kap_ai = self.gemini_service.analyze_kap(kap_item)
            except Exception as exc:
                logger.warning("Gemini KAP analysis failed for %s: %s", ticker, exc)

            ai_summary = ""
            ai_reason_parts: list[str] = []

            if isinstance(news_ai, dict):
                news_explanation = str(news_ai.get("explanation") or "").strip()
                if news_explanation:
                    ai_summary = news_explanation
                    ai_reason_parts.append(f"News: {news_explanation}")

            if isinstance(kap_ai, dict):
                kap_explanation = str(kap_ai.get("explanation") or "").strip()
                if kap_explanation:
                    if not ai_summary:
                        ai_summary = kap_explanation
                    ai_reason_parts.append(f"KAP: {kap_explanation}")

            enriched_item["ai_summary"] = ai_summary or None
            enriched_item["ai_risk"] = self._ai_risk_label(news_ai, kap_ai)
            enriched_item["ai_reason"] = " | ".join(ai_reason_parts) if ai_reason_parts else None
            enriched_item = self._apply_ai_enrichment_to_scores(enriched_item, news_ai=news_ai, kap_ai=kap_ai)
            enriched.append(enriched_item)

        return enriched

    def _find_latest_item_for_ticker(self, items: list[dict[str, Any]], ticker: str) -> dict[str, Any] | None:
        if not ticker:
            return None

        ticker_upper = ticker.upper()
        for item in reversed(items):
            candidate_text = " ".join(
                [
                    str(item.get("ticker") or ""),
                    " ".join([str(value) for value in item.get("detected_tickers", [])]),
                    str(item.get("title") or ""),
                    str(item.get("summary") or ""),
                ]
            ).upper()
            if ticker_upper in candidate_text:
                return item

        return None

    def _ai_risk_label(self, news_ai: dict[str, Any] | None, kap_ai: dict[str, Any] | None) -> str | None:
        if not isinstance(news_ai, dict) and not isinstance(kap_ai, dict):
            return None

        sentiment_rank = {"NEGATIVE": 0, "NEUTRAL": 1, "POSITIVE": 2}
        impact_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}

        sentiment_values: list[int] = []
        impact_values: list[int] = []

        for payload in [news_ai, kap_ai]:
            if not isinstance(payload, dict):
                continue
            sentiment = str(payload.get("sentiment") or "NEUTRAL").upper()
            sentiment_values.append(sentiment_rank.get(sentiment, 1))

            impact = str(payload.get("impact") or "MEDIUM").upper()
            impact_values.append(impact_rank.get(impact, 1))

        if not sentiment_values:
            return None

        sentiment_avg = sum(sentiment_values) / len(sentiment_values)
        impact_avg = sum(impact_values) / len(impact_values) if impact_values else 1.0

        if sentiment_avg <= 0.6 or impact_avg >= 1.6:
            return "Yuksek"
        if sentiment_avg <= 1.2:
            return "Orta"
        return "Dusuk"

    def _news_lookup(
        self,
        ticker_news_summary: list[dict[str, Any]],
    ) -> tuple[dict[str, float], float, dict[str, list[str]], dict[str, str]]:
        ticker_scores: dict[str, float] = {}
        ticker_reasons: dict[str, list[str]] = {}
        ticker_sentiment: dict[str, str] = {}
        all_scores: list[float] = []

        for item in ticker_news_summary:
            ticker = str(item.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            score = float(item.get("average_news_score", 50.0))
            all_scores.append(score)
            ticker_scores[ticker] = score
            ticker_sentiment[ticker] = str(item.get("overall_news_sentiment") or self._sentiment_from_score(score))

            reasons = [str(reason) for reason in item.get("all_reasons", [])]
            if reasons:
                ticker_reasons[ticker] = reasons[:3]

        default_score = sum(all_scores) / len(all_scores) if all_scores else 50.0
        return ticker_scores, default_score, ticker_reasons, ticker_sentiment

    def _sentiment_from_score(self, score: float) -> str:
        if score >= 55.0:
            return "Positive"
        if score <= 45.0:
            return "Negative"
        return "Neutral"

    def _build_ticker_alias_map(self, market_payload: list[dict[str, Any]]) -> dict[str, list[str]]:
        alias_map: dict[str, list[str]] = {}
        for item in market_payload:
            ticker = str(item.get("symbol") or "").strip().upper()
            name = str(item.get("name") or item.get("company_name") or "").strip()
            if not ticker or not name:
                continue

            aliases = {
                name.lower(),
                name.replace("A.Ş.", "").replace("A.S.", "").strip().lower(),
                name.replace("SANAYİ", "").replace("SANAYI", "").strip().lower(),
                name.split(" ")[0].strip().lower(),
            }
            clean_aliases = [alias for alias in aliases if len(alias) >= 3]
            if clean_aliases:
                alias_map.setdefault(ticker, [])
                alias_map[ticker].extend(clean_aliases)

        deduped: dict[str, list[str]] = {}
        for ticker, aliases in alias_map.items():
            seen: set[str] = set()
            unique: list[str] = []
            for alias in aliases:
                if alias in seen:
                    continue
                seen.add(alias)
                unique.append(alias)
            deduped[ticker] = unique[:8]
        return deduped

    def _market_close_lookup(self) -> dict[str, float]:
        market_payload = self._load_cached("market.json", default=[])
        close_by_ticker: dict[str, float] = {}
        for item in market_payload:
            ticker = str(item.get("symbol") or "").strip().upper()
            price = float(item.get("last_price") or item.get("current_price") or 0.0)
            if ticker and price > 0:
                close_by_ticker[ticker] = price
        return close_by_ticker

    def _market_snapshot_lookup(self) -> dict[str, dict[str, float]]:
        market_payload = self._load_cached("market.json", default=[])
        snapshots: dict[str, dict[str, float]] = {}
        for item in market_payload:
            ticker = str(item.get("symbol") or item.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            snapshots[ticker] = {
                "last_price": float(item.get("last_price") or item.get("current_price") or 0.0),
                "high": float(item.get("high") or 0.0),
                "low": float(item.get("low") or 0.0),
            }
        return snapshots

    def _normalize_market_name(self, value: Any) -> str:
        text = str(value or "").strip().upper()
        if text in {"US", "USA", "NASDAQ", "NYSE"}:
            return "US"
        return "BIST" if text else ""

    def _count_items_by_market(self, items: list[dict[str, Any]]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for item in items:
            market_name = self._normalize_market_name((item.get("metadata") or {}).get("market") or item.get("source"))
            if not market_name:
                continue
            counts[market_name] = int(counts.get(market_name, 0)) + 1
        return counts

    def _halal_passed_count_for_market(self, market: str, *, fallback: int) -> int:
        normalized_market = self._normalize_market_name(market)
        if not normalized_market:
            return int(fallback)

        market_scan_stats = dict(self._runtime_cache.get("market_scan_stats") or {})
        market_stats = dict(market_scan_stats.get(normalized_market) or {})
        value = market_stats.get("halal_passed")
        if value is None:
            return int(fallback)
        return int(value)

    def _set_selection_stats(self, market: str, stats: dict[str, Any]) -> None:
        key = self._normalize_market_name(market) or "ALL"
        stats_by_market = self._runtime_cache.setdefault("selection_stats", {})
        stats_by_market[key] = dict(stats)

    def _get_selection_stats(self, market: str) -> dict[str, Any]:
        key = self._normalize_market_name(market) or "ALL"
        stats_by_market = dict(self._runtime_cache.get("selection_stats") or {})
        return dict(stats_by_market.get(key) or {})

    def _calculate_performance(self, history: list[dict[str, Any]]) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        for day in history:
            items = day.get("recommendations", [])
            if isinstance(items, list):
                entries.extend(items)

        total = len(entries)
        closed_entries = [entry for entry in entries if str(entry.get("status") or "").upper() == "CLOSED"]
        winning_entries = [entry for entry in closed_entries if str(entry.get("result") or "").upper() == "WIN"]
        losing_entries = [entry for entry in closed_entries if str(entry.get("result") or "").upper() == "LOSE"]
        open_entries = [entry for entry in entries if str(entry.get("status") or "").upper() != "CLOSED"]

        success_rate = (len(winning_entries) / len(closed_entries) * 100.0) if closed_entries else 0.0
        average_profit = sum(float(entry.get("profit_pct") or 0.0) for entry in winning_entries) / len(winning_entries) if winning_entries else 0.0
        average_loss = sum(float(entry.get("profit_pct") or 0.0) for entry in losing_entries) / len(losing_entries) if losing_entries else 0.0
        best_trade = max((float(entry.get("profit_pct") or 0.0) for entry in closed_entries), default=0.0)
        worst_trade = min((float(entry.get("profit_pct") or 0.0) for entry in closed_entries), default=0.0)
        average_holding = sum(float(entry.get("holding_days") or 0.0) for entry in entries) / len(entries) if entries else 0.0

        pending_signals = len(open_entries)
        tp_hits = sum(
            1
            for entry in closed_entries
            if str(entry.get("risk_reward_result") or "").upper().startswith("TP")
        )
        stop_hits = sum(1 for entry in closed_entries if str(entry.get("risk_reward_result") or "").upper() == "STOP")

        gross_profit = sum(max(0.0, float(entry.get("profit_pct") or 0.0)) for entry in closed_entries)
        gross_loss = abs(sum(min(0.0, float(entry.get("profit_pct") or 0.0)) for entry in closed_entries))
        if gross_loss <= 1e-9:
            profit_factor = float(gross_profit) if gross_profit > 0 else 0.0
        else:
            profit_factor = gross_profit / gross_loss

        win_rate_ratio = (len(winning_entries) / len(closed_entries)) if closed_entries else 0.0
        loss_rate_ratio = (len(losing_entries) / len(closed_entries)) if closed_entries else 0.0
        expectancy = (win_rate_ratio * average_profit) + (loss_rate_ratio * average_loss)

        returns = [float(entry.get("profit_pct") or 0.0) / 100.0 for entry in closed_entries]
        sharpe = 0.0
        if len(returns) >= 2:
            mean_return = sum(returns) / len(returns)
            variance = sum((value - mean_return) ** 2 for value in returns) / (len(returns) - 1)
            std_dev = math.sqrt(max(0.0, variance))
            if std_dev > 1e-9:
                sharpe = (mean_return / std_dev) * math.sqrt(len(returns))

        rr_values = [float(entry.get("risk_reward") or 0.0) for entry in entries if float(entry.get("risk_reward") or 0.0) > 0]
        average_rr = (sum(rr_values) / len(rr_values)) if rr_values else 0.0

        strategy_bucket: dict[str, dict[str, int]] = {}
        for entry in entries:
            strategy = str(entry.get("entry_strategy") or "Unknown").strip() or "Unknown"
            bucket = strategy_bucket.setdefault(strategy, {"total": 0, "closed": 0, "wins": 0, "losses": 0})
            bucket["total"] += 1
            status = str(entry.get("status") or "").upper()
            if status != "CLOSED":
                continue
            bucket["closed"] += 1
            result = str(entry.get("result") or "").upper()
            if result == "WIN":
                bucket["wins"] += 1
            elif result == "LOSE":
                bucket["losses"] += 1

        strategy_success: dict[str, dict[str, float | int]] = {}
        for strategy, data in strategy_bucket.items():
            closed = int(data["closed"])
            wins = int(data["wins"])
            losses = int(data["losses"])
            strategy_success[strategy] = {
                "total": int(data["total"]),
                "closed": closed,
                "wins": wins,
                "losses": losses,
                "pending": max(0, int(data["total"]) - closed),
                "win_rate": round((wins / closed * 100.0) if closed else 0.0, 2),
            }

        daily: dict[str, dict[str, Any]] = {}
        for entry in entries:
            timestamp = str(entry.get("generated_time") or entry.get("opened_at") or "")
            day_key = timestamp[:10] if len(timestamp) >= 10 else "UNKNOWN"
            row = daily.setdefault(
                day_key,
                {"signals": 0, "closed": 0, "wins": 0, "losses": 0, "pending": 0, "total_profit_pct": 0.0},
            )
            row["signals"] += 1
            status = str(entry.get("status") or "").upper()
            if status == "CLOSED":
                row["closed"] += 1
                row["total_profit_pct"] += float(entry.get("profit_pct") or 0.0)
                result = str(entry.get("result") or "").upper()
                if result == "WIN":
                    row["wins"] += 1
                elif result == "LOSE":
                    row["losses"] += 1
            else:
                row["pending"] += 1

        daily_report = {
            date_key: {
                "signals": int(payload["signals"]),
                "closed": int(payload["closed"]),
                "wins": int(payload["wins"]),
                "losses": int(payload["losses"]),
                "pending": int(payload["pending"]),
                "total_profit_pct": round(float(payload["total_profit_pct"]), 4),
                "win_rate": round((float(payload["wins"]) / float(payload["closed"]) * 100.0) if float(payload["closed"]) > 0 else 0.0, 2),
            }
            for date_key, payload in sorted(daily.items())
        }

        return {
            "total_signals": total,
            "winning_signals": len(winning_entries),
            "losing_signals": len(losing_entries),
            "pending_signals": pending_signals,
            "success_rate": round(success_rate, 2),
            "average_profit": round(average_profit, 4),
            "average_loss": round(average_loss, 4),
            "best_trade": round(best_trade, 4),
            "worst_trade": round(worst_trade, 4),
            "last_updated": datetime.now(UTC).isoformat(),
            "total_recommendations": total,
            "successful_recommendations": len(winning_entries),
            "failed_recommendations": len(losing_entries),
            "win_rate": round(success_rate, 2),
            "loss_rate": round((len(losing_entries) / len(closed_entries) * 100.0) if closed_entries else 0.0, 2),
            "average_holding_time": round(average_holding, 2),
            "tp1_hits": sum(1 for entry in closed_entries if str(entry.get("risk_reward_result") or "").upper() == "TP1"),
            "tp2_hits": sum(1 for entry in closed_entries if str(entry.get("risk_reward_result") or "").upper() == "TP2"),
            "tp3_hits": sum(1 for entry in closed_entries if str(entry.get("risk_reward_result") or "").upper() == "TP3"),
            "stop_hits": sum(1 for entry in closed_entries if str(entry.get("risk_reward_result") or "").upper() == "STOP"),
            "current_open_positions": len(open_entries),
            "reached_tp": tp_hits,
            "stopped": stop_hits,
            "profit_factor": round(profit_factor, 4),
            "expectancy": round(expectancy, 4),
            "sharpe": round(sharpe, 4),
            "average_risk_reward": round(average_rr, 4),
            "strategy_success": strategy_success,
            "daily_report": daily_report,
            "updated_at": datetime.now(UTC).isoformat(),
        }

    def _load_cached(self, filename: str, default: Any | None = None) -> Any:
        if filename in self._runtime_cache:
            return self._runtime_cache[filename]

        if settings.live_only_mode:
            payload = default
            self._runtime_cache[filename] = payload
            return payload

        payload = self.storage.load(filename, default=default)
        self._runtime_cache[filename] = payload
        return payload

    def _save_if_changed(self, filename: str, payload: Any) -> Any:
        current = self._runtime_cache.get(filename)
        if current is None and not settings.live_only_mode:
            current = self.storage.load(filename, default=None) if self.storage.exists(filename) else None

        if current == payload:
            self._runtime_cache[filename] = payload
            return payload

        if settings.live_only_mode:
            self._runtime_cache[filename] = payload
            return payload

        saved = self.storage.save(filename, payload)
        self._runtime_cache[filename] = saved
        return saved
