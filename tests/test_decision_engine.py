from __future__ import annotations

from decision import DecisionEngine


def test_decision_engine_builds_price_levels() -> None:
    engine = DecisionEngine()

    result = engine.decide(
        ticker="THYAO",
        current_price=100.0,
        support=96.0,
        resistance=110.0,
        ema20=99.0,
        atr_value=2.5,
        technical_score=84.0,
        news_score=78.0,
        trend="Bullish",
        relative_volume=1.2,
        gap_up=False,
        gap_down=False,
        rsi14=55.0,
        macd_state="Bullish",
        ema50=97.0,
        reasons=["Test input"],
    )

    assert result.entry_price > 0
    assert result.stop_loss < result.entry_price
    assert result.take_profit_1 > result.entry_price
    assert result.take_profit_2 >= result.take_profit_1
    assert result.confidence > 0
    assert result.reasons
