from __future__ import annotations

from dataclasses import asdict

from decision import BistOpportunityEngine
from engines import CapitalAllocationEngine
from services.pipeline import FinancePipelineService


def test_finalize_bist_recommendation_sets_numeric_confidence() -> None:
    service = FinancePipelineService()

    result = service._finalize_bist_recommendation(
        {
            "ticker": "ASELS",
            "company_name": "Aselsan",
            "decision": "LIMIT BUY",
            "total_score": 71.4,
            "component_scores": {
                "graph_structure": 35.0,
                "trend": 14.2,
                "volume": 8.0,
                "momentum": 6.8,
                "news": 2.6,
                "ai_confidence": 1.2,
            },
            "macro_multiplier": 1.0,
            "risk_reward_ratio": 1.9,
            "trend_strength": 78,
            "entry_price": 102.0,
            "current_price": 103.0,
            "entry_range_low": 101.0,
            "entry_range_high": 103.0,
            "limit_entry_price": 102.1,
            "stop_loss": 98.4,
            "current_target": 110.5,
            "take_profit_1": 105.0,
            "take_profit_2": 107.0,
            "take_profit_3": 109.0,
            "take_profit_4": 111.0,
            "take_profit_levels": [
                {"label": "TP1", "price": 105.0, "reason": "Direnc"},
                {"label": "TP2", "price": 107.0, "reason": "Direnc"},
                {"label": "TP3", "price": 109.0, "reason": "Trend"},
                {"label": "TP4", "price": 111.0, "reason": "Trend"},
            ],
            "entry_status": "BUY",
            "market_entry_allowed": True,
            "reasons": ["Trend guclu"],
        },
        rank=1,
    )

    assert isinstance(result["confidence"], float)
    assert 0.0 <= float(result["confidence"]) <= 100.0
    assert int(result["user_confidence"]) == int(round(float(result["confidence"])))


def test_news_ai_decision_pipeline_e2e_influences_score(monkeypatch) -> None:
    service = FinancePipelineService()
    engine = BistOpportunityEngine()

    news_payload = [
        {
            "title": "ASELS yeni sozlesme imzaladi ve kapasite artisi acikladi",
            "url": "https://example.com/news/asels",
            "summary": "Savunma kontrati ve yeni yatirim",
            "source": "unit",
            "ticker_candidates": ["ASELS"],
            "detected_tickers": ["ASELS"],
        }
    ]
    analyzed_news = service.news_analyzer.analyze(news_payload)
    assert analyzed_news
    news_score = float(analyzed_news[0]["score"])
    news_sentiment = str(analyzed_news[0]["sentiment"])
    news_confidence = float(analyzed_news[0]["confidence"])

    scored = engine.score_candidate(
        {
            "ticker": "ASELS",
            "company_name": "Aselsan",
            "market": "BIST",
            "current_price": 100.0,
            "support": 95.0,
            "resistance": 108.0,
            "atr": 2.1,
            "volume": 3200000,
            "average_volume": 1800000,
            "relative_volume": 1.45,
            "technical_score": 80.0,
            "trend": "Bullish",
            "trend_strength": 82,
            "estimated_trend_duration": "3-7 islem gunu",
            "rsi14": 57.0,
            "macd": "Bullish",
            "daily_change_pct": 2.4,
            "gap_up": True,
            "candles": list(range(280)),
        },
        news_score=news_score,
        news_sentiment=news_sentiment,
        news_confidence=news_confidence,
        news_reasons=["Yeni sozlesme"],
    )

    assert scored.hard_filtered is False
    before = asdict(scored)
    base_total = float(before["total_score"])

    monkeypatch.setattr(service, "_load_cached", lambda name, default=None: news_payload if name == "news.json" else news_payload if name == "kap.json" else (default if default is not None else []))
    monkeypatch.setattr(
        service.gemini_service,
        "analyze_news",
        lambda _item: {
            "sentiment": "Positive",
            "impact": "High",
            "confidence": 88,
            "explanation": "Yeni sozlesme gelir beklentisini guclendiriyor.",
        },
    )
    monkeypatch.setattr(
        service.gemini_service,
        "analyze_kap",
        lambda _item: {
            "sentiment": "Positive",
            "confidence": 84,
            "explanation": "KAP bildirimi operasyonel ivmenin surdugunu gosteriyor.",
        },
    )

    after = service._enrich_recommendations_with_ai([before])[0]

    assert str(after.get("ai_summary") or "")
    assert float(after.get("total_score") or 0.0) >= base_total
    assert float((after.get("component_scores") or {}).get("ai_confidence") or 0.0) > 0.0


def test_calculate_performance_includes_advanced_metrics() -> None:
    service = FinancePipelineService()

    history = [
        {
            "date": "2026-07-21",
            "recommendations": [
                {
                    "ticker": "AAA",
                    "status": "CLOSED",
                    "result": "WIN",
                    "profit_pct": 6.0,
                    "risk_reward": 2.1,
                    "risk_reward_result": "TP1",
                    "entry_strategy": "EMA Pullback",
                    "generated_time": "2026-07-21T09:00:00+00:00",
                },
                {
                    "ticker": "BBB",
                    "status": "CLOSED",
                    "result": "LOSE",
                    "profit_pct": -2.5,
                    "risk_reward": 1.3,
                    "risk_reward_result": "STOP",
                    "entry_strategy": "Retest",
                    "generated_time": "2026-07-21T09:05:00+00:00",
                },
                {
                    "ticker": "CCC",
                    "status": "OPEN",
                    "result": "PENDING",
                    "profit_pct": 0.0,
                    "risk_reward": 1.8,
                    "entry_strategy": "Breakout",
                    "generated_time": "2026-07-21T09:10:00+00:00",
                },
            ],
        }
    ]

    performance = service._calculate_performance(history)

    assert int(performance["total_signals"]) == 3
    assert int(performance["pending_signals"]) == 1
    assert float(performance["profit_factor"]) > 0
    assert "strategy_success" in performance
    assert "EMA Pullback" in performance["strategy_success"]
    assert "Retest" in performance["strategy_success"]
    assert "daily_report" in performance


def test_capital_allocation_accepts_buy_variants() -> None:
    engine = CapitalAllocationEngine(min_cash_ratio=0.1, max_symbol_ratio=0.6)

    result = engine.allocate(
        [
            {"ticker": "AAA", "decision": "BUY NOW", "confidence": 70},
            {"ticker": "BBB", "decision": "LIMIT BUY", "confidence": 80},
        ],
        10000,
    )

    allocations = list(result.get("allocations") or [])
    assert len(allocations) == 2
    assert sum(float(item.get("recommended_amount") or 0.0) for item in allocations) > 0
