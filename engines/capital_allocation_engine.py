"""Capital allocation engine based on confidence-weighted opportunities."""

from __future__ import annotations

from typing import Any


class CapitalAllocationEngine:
    """Allocate available capital to BUY opportunities."""

    def __init__(self, *, min_cash_ratio: float = 0.1, max_symbol_ratio: float = 0.4) -> None:
        self._min_cash_ratio = max(0.0, min(0.8, min_cash_ratio))
        self._max_symbol_ratio = max(0.05, min(1.0, max_symbol_ratio))

    def allocate(self, opportunities: list[dict[str, Any]], total_capital: float) -> dict[str, Any]:
        total_capital = max(0.0, float(total_capital))
        if total_capital <= 0:
            return {"allocations": [], "cash": 0.0}

        buy_decisions = {"BUY", "BUY NOW", "LIMIT BUY"}
        buy_items = [
            item
            for item in opportunities
            if str(item.get("decision") or "").strip().upper() in buy_decisions
        ]
        if not buy_items:
            return {"allocations": [], "cash": round(total_capital, 2)}

        reserve_cash = total_capital * self._min_cash_ratio
        investable = max(0.0, total_capital - reserve_cash)

        weights: list[float] = []
        for item in buy_items:
            confidence = max(1.0, float(item.get("confidence") or 0.0))
            weights.append(confidence * confidence)

        weight_sum = sum(weights) or 1.0
        max_symbol_amount = total_capital * self._max_symbol_ratio

        allocations: list[dict[str, Any]] = []
        allocated_total = 0.0

        for item, weight in zip(buy_items, weights, strict=False):
            amount = investable * (weight / weight_sum)
            amount = min(amount, max_symbol_amount)
            amount = round(amount, 2)
            allocated_total += amount

            allocations.append(
                {
                    "ticker": str(item.get("ticker") or "").upper(),
                    "recommended_amount": amount,
                }
            )

        cash = round(max(0.0, total_capital - allocated_total), 2)
        return {"allocations": allocations, "cash": cash}
