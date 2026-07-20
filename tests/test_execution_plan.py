from __future__ import annotations

from services.pipeline import FinancePipelineService


def test_execution_plan_builds_actionable_orders() -> None:
    service = FinancePipelineService()

    plan = service._build_execution_plan(
        {
            "ticker": "ASELS",
            "decision": "BUY NOW",
            "entry_status": "BUY",
            "entry_strategy": "Breakout",
            "market_entry_allowed": True,
            "current_price": 100.0,
            "entry_range_low": 98.5,
            "entry_range_high": 100.2,
            "limit_entry_price": 99.8,
            "stop_loss": 96.7,
            "risk_reward_ratio": 2.1,
            "take_profit_levels": [
                {"label": "TP1", "price": 103.2, "reason": "Direnc"},
                {"label": "TP2", "price": 106.0, "reason": "Formasyon"},
                {"label": "TP3", "price": 109.5, "reason": "Extension"},
                {"label": "TP4", "price": 114.0, "reason": "Trend"},
            ],
        }
    )

    assert plan["actionable"] is True
    assert "ALIS" in str(plan["instruction"])
    assert "STOP" in str(plan["instruction"])
    assert isinstance(plan["entry_order"], dict)
    assert str(plan["entry_order"].get("type")) in {"MARKET_BUY", "LIMIT_BUY", "STOP_LIMIT_BUY"}
    assert float(plan["entry_order"].get("price") or 0.0) > 0
    assert isinstance(plan["stop_order"], dict)
    assert float(plan["stop_order"].get("price") or 0.0) > 0
    assert len(plan["sell_orders"]) >= 1


def test_execution_plan_returns_no_trade_for_invalid_setup() -> None:
    service = FinancePipelineService()

    plan = service._build_execution_plan(
        {
            "ticker": "XXX",
            "decision": "WAIT",
            "entry_status": "NO TRADE",
            "current_price": 10.0,
            "limit_entry_price": 0.0,
            "stop_loss": 0.0,
        }
    )

    assert plan["actionable"] is False
    assert str(plan["instruction"]).endswith("NO TRADE")
    assert plan["entry_order"] is None
    assert plan["stop_order"] is None
