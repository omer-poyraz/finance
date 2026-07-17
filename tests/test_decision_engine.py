from __future__ import annotations

from decision import AnalyzerScore
from decision import DecisionEngine


def test_decision_engine_builds_price_levels() -> None:
    engine = DecisionEngine()

    result = engine.decide(
        current_price=100.0,
        analyzer_scores={
            "news": 78.0,
            "technical": 84.0,
            "risk": 72.0,
            "financial": 68.0,
        },
        atr_value=2.5,
        support=96.0,
        resistance=110.0,
    )

    assert result.entry_price == 100.0
    assert result.stop_loss < result.entry_price
    assert result.take_profit > result.entry_price
    assert result.confidence_score > 0
    assert result.reason_list
    assert all(isinstance(item, AnalyzerScore) for item in result.analyzer_scores)
