"""End-to-end pipeline service for collection, analysis, recommendations, and storage."""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC
from datetime import datetime
import logging
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
from collectors.models import NewsItem
from config import settings
from decision import DecisionEngine
from indicators import atr
from indicators import bollinger_bands
from indicators import ema
from indicators import gap_detection
from indicators import macd
from indicators import rsi
from indicators import sma
from indicators import volume_analysis
from notifier import ConsoleNotifier
from notifier import WhatsAppNotifier
from shared.normalization import build_item_id
from shared.normalization import normalize_records
from storage import JsonStorage


logger = logging.getLogger(__name__)


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
]


DEFAULT_NEWS_KEYWORDS: dict[str, dict[str, int]] = {
    "positive": {
        "ihale": 40,
        "yatırım": 20,
        "kapasite artışı": 30,
        "geri alım": 25,
        "temettü": 15,
        "bedelsiz": 35,
        "yeni sözleşme": 30,
        "teşvik": 20,
    },
    "negative": {
        "sermaye azaltımı": -40,
        "konkordato": -100,
        "iflas": -100,
        "ceza": -70,
        "zarar": -30,
        "dava": -25,
        "kredi notu düşürüldü": -35,
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


class FinancePipelineService:
    """Run the complete local data-to-recommendation pipeline."""

    def __init__(self) -> None:
        self.storage = JsonStorage(settings.storage_data_dir)
        self.storage.ensure_default_files(REQUIRED_STORAGE_FILES)
        self.config_storage = JsonStorage("storage/config")
        self._ensure_news_keyword_config()
        self._ensure_technical_scoring_config()

        self.collector_manager = CollectorManager()
        self.collector_manager.register(NewsCollector())
        self.collector_manager.register(KapCollector())
        self.collector_manager.register(MarketCollector())

        self.news_analyzer = NewsAnalyzer(self._load_news_keyword_config())
        self.technical_analyzer = TechnicalAnalyzer()
        self.risk_analyzer = RiskAnalyzer()
        self.financial_analyzer = FinancialAnalyzer()
        self.decision_engine = DecisionEngine()

        self.console_notifier = ConsoleNotifier()
        self.whatsapp_notifier = WhatsAppNotifier()

    def collect_news(self) -> list[dict[str, Any]]:
        """Collect and persist normalized news records."""

        try:
            result = self.collector_manager.collect_one("news")
            payload = [asdict(item) for item in result.items]
            normalized = normalize_records(payload, required_keys=["title", "url"], source="news")
            self.storage.save("news.json", normalized)
            return normalized
        except Exception as exc:
            logger.exception("News collection failed: %s", exc)
            existing = self.storage.load("news.json", default=[])
            self.storage.save("news.json", existing)
            return existing

    def collect_kap(self) -> list[dict[str, Any]]:
        """Collect and persist normalized KAP records."""

        try:
            result = self.collector_manager.collect_one("kap")
            payload = [asdict(item) for item in result.items]
            normalized = normalize_records(payload, required_keys=["title", "url"], source="kap")
            self.storage.save("kap.json", normalized)
            return normalized
        except Exception as exc:
            logger.exception("KAP collection failed: %s", exc)
            existing = self.storage.load("kap.json", default=[])
            self.storage.save("kap.json", existing)
            return existing

    def collect_market(self) -> list[dict[str, Any]]:
        """Collect and persist normalized market records."""

        try:
            result = self.collector_manager.collect_one("market")
            payload = [asdict(item) for item in result.items]
            normalized = normalize_records(payload, required_keys=["symbol", "name"], source="market")
            self.storage.save("market.json", normalized)
            return normalized
        except Exception as exc:
            logger.exception("Market collection failed: %s", exc)
            existing = self.storage.load("market.json", default=[])
            self.storage.save("market.json", existing)
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

        news_payload = self.storage.load("news.json", default=[])
        market_payload = self.storage.load("market.json", default=[])

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
        news_analysis_items = self.storage.load("news_analysis.json", default=[])
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

        self.storage.save("analysis.json", analysis)
        return analysis

    def analyze_market(self) -> dict[str, int]:
        """Build technical intelligence profile for each collected market stock."""

        market_payload = self.storage.load("market.json", default=[])
        if not market_payload:
            market_payload = self.collect_market()

        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in market_payload:
            ticker = str(item.get("symbol") or "").strip().upper()
            if not ticker:
                continue
            grouped.setdefault(ticker, []).append(item)

        scoring = self._load_technical_scoring_config()
        analysis_items: list[dict[str, Any]] = []

        for ticker, rows in grouped.items():
            frame = self._market_history_frame(rows)
            analysis_items.append(self._build_market_profile(ticker, frame, scoring))

        self.storage.save("market_analysis.json", analysis_items)

        bullish = sum(1 for item in analysis_items if item.get("trend") == "Bullish")
        bearish = sum(1 for item in analysis_items if item.get("trend") == "Bearish")
        neutral = sum(1 for item in analysis_items if item.get("trend") == "Neutral")
        return {
            "stocks": len(analysis_items),
            "bullish": bullish,
            "bearish": bearish,
            "neutral": neutral,
        }

    def analyze_news(self) -> dict[str, int]:
        """Analyze collected news with configurable keyword intelligence rules."""

        keyword_config = self._load_news_keyword_config()
        self.news_analyzer.set_keyword_config(keyword_config)

        news_payload = self.storage.load("news.json", default=[])
        existing_analysis = self.storage.load("news_analysis.json", default=[])
        analyzed_ids = {
            str(item.get("id"))
            for item in existing_analysis
            if isinstance(item, dict) and item.get("id")
        }

        new_items = self.news_analyzer.analyze(news_payload, already_analyzed_ids=analyzed_ids)
        if new_items:
            combined = [*existing_analysis, *new_items]
            self.storage.save("news_analysis.json", combined)
        else:
            combined = existing_analysis

        self.analyze_tickers()

        return self._news_summary(combined)

    def analyze_tickers(self) -> dict[str, int]:
        """Aggregate analyzed news incrementally by ticker and persist ticker summaries."""

        news_analysis = self.storage.load("news_analysis.json", default=[])
        news_items = self.storage.load("news.json", default=[])
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

        self.storage.save("ticker_news_summary.json", summaries)

        positive = sum(1 for item in summaries if item.get("overall_news_sentiment") == "Positive")
        negative = sum(1 for item in summaries if item.get("overall_news_sentiment") == "Negative")
        neutral = sum(1 for item in summaries if item.get("overall_news_sentiment") == "Neutral")

        return {
            "tickers": len(summaries),
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
        }

    def generate_recommendations(self) -> list[dict[str, Any]]:
        """Build recommendation list and persist to JSON storage."""

        self.analyze_news()
        self.analyze_market()
        self.analyze_tickers()

        market_analysis = self.storage.load("market_analysis.json", default=[])
        ticker_news_summary = self.storage.load("ticker_news_summary.json", default=[])
        news_by_ticker, default_news_score, news_reasons_by_ticker = self._news_lookup(ticker_news_summary)

        recommendations: list[dict[str, Any]] = []

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
            trend = str(market_item.get("trend") or "Neutral")
            relative_volume = float(market_item.get("relative_volume") or 0.0)
            gap_up = bool(market_item.get("gap_up", False))
            gap_down = bool(market_item.get("gap_down", False))
            rsi14 = float(market_item.get("rsi14") or 50.0)
            macd_state = str(market_item.get("macd") or "Neutral")
            ema50_value = float(market_item.get("ema50") or ema20_value)

            if current_price <= 0 or support <= 0 or atr_value <= 0:
                continue

            news_score = float(news_by_ticker.get(ticker, default_news_score))
            reasons = list(market_item.get("reasons", []))
            reasons.extend(news_reasons_by_ticker.get(ticker, []))

            decision = self.decision_engine.decide(
                ticker=ticker,
                current_price=current_price,
                support=support,
                resistance=resistance,
                ema20=ema20_value,
                atr_value=atr_value,
                technical_score=technical_score,
                news_score=news_score,
                trend=trend,
                relative_volume=relative_volume,
                gap_up=gap_up,
                gap_down=gap_down,
                rsi14=rsi14,
                macd_state=macd_state,
                ema50=ema50_value,
                reasons=reasons,
            )
            payload = asdict(decision)
            if payload.get("rejected"):
                continue

            if float(payload["risk_reward_ratio"]) < 2.0:
                continue

            if float(payload["overall_score"]) >= 70.0:
                recommendations.append(payload)

        recommendations.sort(
            key=lambda item: (
                float(item.get("confidence", 0.0)),
                float(item.get("overall_score", 0.0)),
                float(item.get("risk_reward_ratio", 0.0)),
            ),
            reverse=True,
        )
        self.storage.save("recommendations.json", recommendations)
        return recommendations

    def notify_recommendations(self) -> dict[str, Any]:
        """Send latest recommendations via configured notifiers."""

        recommendations = self.storage.load("recommendations.json", default=[])
        if not recommendations:
            recommendations = self.generate_recommendations()

        message = self._format_recommendations_message(recommendations)
        console_result = self.console_notifier.send(message, title="Daily Analysis")
        whatsapp_result = self.whatsapp_notifier.send(message, title="Daily Analysis")

        return {
            "console": asdict(console_result),
            "whatsapp": asdict(whatsapp_result),
        }

    def send_daily_recommendations(self) -> dict[str, Any]:
        """Run full weekday pipeline and send top recommendations."""

        collection = self.collect_all()
        news = self.analyze_news()
        market = self.analyze_market()
        tickers = self.analyze_tickers()
        recommendations = self.generate_recommendations()
        notifications = self.notify_recommendations()

        return {
            "collection": collection,
            "news": news,
            "market": market,
            "tickers": tickers,
            "recommendations": len(recommendations),
            "notifications": notifications,
        }

    def archive_today(self) -> list[dict[str, Any]]:
        """Archive current recommendations into history storage."""

        recommendations = self.storage.load("recommendations.json", default=[])
        if not recommendations:
            return self.storage.load("history.json", default=[])

        history = self.storage.load("history.json", default=[])
        history.append(
            {
                "date": datetime.now(UTC).date().isoformat(),
                "recommendations": recommendations,
            }
        )
        self.storage.save("history.json", history)
        return history

    def get_history(self) -> list[dict[str, Any]]:
        """Return archived recommendation history."""

        return self.storage.load("history.json", default=[])

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
        sma20_value = float(sma20_series.iloc[-1])
        rsi14_value = float(rsi14_series.iloc[-1])
        macd_value = float(macd_frame["macd"].iloc[-1])
        macd_signal = float(macd_frame["signal"].iloc[-1])
        atr_value = float(atr_series.iloc[-1])
        boll_upper = float(boll["upper"].iloc[-1])
        boll_lower = float(boll["lower"].iloc[-1])
        support = float(frame["low"].rolling(window=20, min_periods=1).min().iloc[-1])
        resistance = float(frame["high"].rolling(window=20, min_periods=1).max().iloc[-1])

        trend = "Neutral"
        if ema20_value > ema50_value:
            trend = "Bullish"
        elif ema20_value < ema50_value:
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

        if 40.0 <= rsi14_value <= 60.0:
            weighted_points += float(scoring.get("rsi", 0.0))
            reasons.append("RSI in balanced bullish zone")
        elif 30.0 <= rsi14_value < 40.0:
            weighted_points += float(scoring.get("rsi", 0.0)) * 0.5
            reasons.append("RSI recovery zone")

        if trend == "Bullish":
            weighted_points += float(scoring.get("trend", 0.0))
            reasons.append("Overall trend bullish")
        elif trend == "Neutral":
            weighted_points += float(scoring.get("trend", 0.0)) * 0.5

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

    def _load_technical_scoring_config(self) -> dict[str, float]:
        filename = "technical_scoring.json"
        if not self.config_storage.exists(filename):
            self.config_storage.save(filename, DEFAULT_TECHNICAL_SCORING)

        raw = self.config_storage.load(filename, default=DEFAULT_TECHNICAL_SCORING)
        return {str(key): float(value) for key, value in dict(raw).items()}

    def _format_recommendations_message(self, recommendations: list[dict[str, Any]]) -> str:
        lines = ["📈 Finance Robot", "", datetime.now(UTC).date().strftime("%d.%m.%Y"), "", "Top Opportunities"]
        for index, item in enumerate(recommendations, start=1):
            lines.extend(
                [
                    "",
                    f"{index})",
                    str(item.get("ticker", "UNKNOWN")),
                    f"Entry : {item.get('entry_price', 0):.2f}",
                    f"Stop : {item.get('stop_loss', 0):.2f}",
                    f"TP1 : {item.get('take_profit_1', item.get('target_price_1', 0)):.2f}",
                    f"TP2 : {item.get('take_profit_2', item.get('target_price_2', 0)):.2f}",
                    f"Confidence : {item.get('confidence', 0):.0f}%",
                    f"Risk/Reward : {item.get('risk_reward_ratio', 0):.2f}",
                    "Reason",
                ]
            )

            for reason in item.get("reasons", [])[:6]:
                lines.append(str(reason))

            lines.append("--------------------------------")

        return "\n".join(lines)

    def _news_lookup(
        self,
        ticker_news_summary: list[dict[str, Any]],
    ) -> tuple[dict[str, float], float, dict[str, list[str]]]:
        ticker_scores: dict[str, float] = {}
        ticker_reasons: dict[str, list[str]] = {}
        all_scores: list[float] = []

        for item in ticker_news_summary:
            ticker = str(item.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            score = float(item.get("average_news_score", 50.0))
            all_scores.append(score)
            ticker_scores[ticker] = score

            reasons = [str(reason) for reason in item.get("all_reasons", [])]
            if reasons:
                ticker_reasons[ticker] = reasons[:3]

        default_score = sum(all_scores) / len(all_scores) if all_scores else 50.0
        return ticker_scores, default_score, ticker_reasons

    def _sentiment_from_score(self, score: float) -> str:
        if score >= 55.0:
            return "Positive"
        if score <= 45.0:
            return "Negative"
        return "Neutral"
