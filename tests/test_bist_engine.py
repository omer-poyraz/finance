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
            "candles": list(range(260)),
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
    assert result.decision in {"BUY", "WAIT", "PULLBACK BEKLE", "BREAKOUT BEKLE", "ENTRY MISSED"}
    assert result.entry_price > result.stop_loss
    assert result.current_target >= result.entry_price
    assert isinstance(result.chart_formations, list)
    assert isinstance(result.market_structure_signals, list)
    assert isinstance(result.indicator_confirmations, list)
    assert isinstance(result.take_profit_levels, list)
    assert isinstance(result.risk_reward_by_tp, list)


def test_bist_engine_builds_tp_ladder_with_probabilities() -> None:
    engine = BistOpportunityEngine()

    result = engine.score_candidate(
        {
            "ticker": "THYAO",
            "company_name": "Turkish Airlines",
            "market": "BIST",
            "current_price": 101.0,
            "support": 96.0,
            "resistance": 100.0,
            "atr": 2.1,
            "volume": 4800000,
            "average_volume": 2500000,
            "relative_volume": 1.92,
            "technical_score": 81.0,
            "trend": "Bullish",
            "trend_strength": 82,
            "estimated_trend_duration": "3-10 islem gunu",
            "rsi14": 57.0,
            "macd": "Bullish",
            "macd_value": 0.62,
            "macd_signal": 0.51,
            "adx": 29.0,
            "ema20": 99.5,
            "ema50": 98.7,
            "ema200": 96.4,
            "bollinger_upper": 101.7,
            "bollinger_lower": 98.8,
            "momentum_5d": 0.24,
            "momentum_20d": 0.61,
            "daily_change_pct": 3.1,
            "volatility_pct": 0.011,
            "fibonacci": {
                "0.236": 102.7,
                "0.382": 103.6,
                "0.618": 105.1,
            },
            "candles": list(range(280)),
            "high": 101.3,
        },
        news_score=74.0,
        news_sentiment="Positive",
        news_confidence=72.0,
        news_reasons=["KAP yeni sozlesme", "Sektor haberi"],
    )

    assert result.hard_filtered is False
    assert result.take_profit_1 > result.entry_price
    assert result.take_profit_2 >= result.take_profit_1
    assert result.take_profit_3 >= result.take_profit_2
    assert result.take_profit_4 >= result.take_profit_3
    assert len(result.take_profit_levels) >= 3
    assert len(result.risk_reward_by_tp) >= 3
    assert all(float(item.get("probability") or 0.0) > 0 for item in result.risk_reward_by_tp)
    assert all("ATR" not in str(level.get("reason") or "") for level in result.take_profit_levels)


def test_bist_engine_marks_entry_missed_when_price_far_above_zone() -> None:
    engine = BistOpportunityEngine()

    result = engine.score_candidate(
        {
            "ticker": "GARAN",
            "company_name": "Garanti",
            "market": "BIST",
            "current_price": 120.0,
            "support": 100.0,
            "resistance": 110.0,
            "atr": 1.2,
            "volume": 3500000,
            "average_volume": 1800000,
            "relative_volume": 1.7,
            "technical_score": 76.0,
            "trend": "Bullish",
            "trend_strength": 78,
            "estimated_trend_duration": "3-10 islem gunu",
            "rsi14": 59.0,
            "macd": "Bullish",
            "macd_value": 0.41,
            "macd_signal": 0.32,
            "adx": 26.0,
            "ema20": 113.0,
            "ema50": 108.0,
            "ema200": 99.0,
            "bollinger_upper": 121.0,
            "bollinger_lower": 112.0,
            "momentum_5d": 0.31,
            "momentum_20d": 0.52,
            "daily_change_pct": 2.5,
            "volatility_pct": 0.018,
            "candles": list(range(280)),
        },
        news_score=66.0,
        news_sentiment="Neutral",
        news_confidence=64.0,
        news_reasons=["Momentum devam"],
    )

    assert result.entry_status == "ENTRY MISSED"
    assert result.decision == "ENTRY MISSED"
    assert result.market_entry_allowed is False


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
