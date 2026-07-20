from __future__ import annotations

from decision import BistOpportunityEngine


def test_bist_engine_scores_viable_candidate() -> None:
    engine = BistOpportunityEngine()

    result = engine.score_candidate(
        {
            "ticker": "ASELS",
            "company_name": "Aselsan",
            "market": "BIST",
            "current_price": 100.0,
            "support": 96.0,
            "resistance": 112.0,
            "atr": 2.5,
            "volume": 2200000,
            "average_volume": 1500000,
            "relative_volume": 1.35,
            "technical_score": 78.0,
            "trend": "Bullish",
            "trend_strength": 84,
            "estimated_trend_duration": "3-7 islem gunu",
            "rsi14": 58.0,
            "macd": "Bullish",
            "daily_change_pct": 4.2,
            "gap_up": True,
        },
        news_score=72.0,
        news_sentiment="Positive",
        news_confidence=68.0,
        news_reasons=["Yeni sozlesme", "Hacim destegi"],
    )

    assert result.hard_filtered is False
    assert result.total_score > 0
    assert result.component_scores["graph_structure"] > 0
    assert result.component_scores["trend"] > 0
    assert result.component_scores["volume"] > 0
    assert result.component_scores["momentum"] > 0
    assert result.decision in {"BUY", "WATCH"}
    assert result.entry_price > result.stop_loss
    assert result.current_target >= result.entry_price
    assert isinstance(result.chart_formations, list)
    assert isinstance(result.market_structure_signals, list)
    assert isinstance(result.indicator_confirmations, list)


def test_bist_engine_hard_filters_invalid_data() -> None:
    engine = BistOpportunityEngine()

    result = engine.score_candidate(
        {
            "ticker": "XXX",
            "company_name": "Broken",
            "market": "BIST",
            "current_price": 0.0,
            "support": 0.0,
            "resistance": 0.0,
            "atr": 0.0,
            "volume": 0.0,
            "average_volume": 0.0,
            "relative_volume": 0.0,
            "technical_score": 0.0,
            "trend": "Neutral",
        },
        news_score=0.0,
        news_sentiment="Neutral",
        news_confidence=0.0,
    )

    assert result.hard_filtered is True
    assert result.status == "FILTERED"
    assert result.total_score == 0.0
    assert result.hard_filter_reasons
