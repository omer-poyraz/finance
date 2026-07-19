"""Portfolio engine for open-position re-evaluation."""

from __future__ import annotations

from typing import Any


class PortfolioEngine:
    """Evaluate existing positions with daily management decisions."""

    def evaluate_positions(
        self,
        positions: list[dict[str, Any]],
        analysis_by_ticker: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []

        for position in positions:
            ticker = str(position.get("ticker") or "").strip().upper()
            if not ticker:
                continue

            analysis = analysis_by_ticker.get(ticker)
            if not analysis:
                continue

            avg_price = float(position.get("average_price") or 0.0)
            qty = float(position.get("quantity") or 0.0)
            current_stop = float(position.get("current_stop") or 0.0)
            current_price = float(analysis.get("current_price") or 0.0)
            trend_strength = int(analysis.get("trend_strength") or 0)
            trend = str(analysis.get("trend") or "Neutral")
            confidence = float(analysis.get("confidence") or 0.0)
            atr_value = float(analysis.get("atr") or 0.0)

            if avg_price <= 0 or qty <= 0 or current_price <= 0:
                continue

            profit_pct = ((current_price - avg_price) / avg_price) * 100.0
            new_stop = current_stop
            decision = "HOLD"

            if trend == "Bearish" or confidence < 45:
                decision = "EXIT"
            elif profit_pct >= 15.0 and trend_strength < 75:
                decision = "PARTIAL TAKE PROFIT"
            elif profit_pct >= 5.0 and trend_strength >= 75:
                suggested_stop = max(current_stop, current_price - max(atr_value * 1.1, current_price * 0.02))
                new_stop = round(suggested_stop, 4)
                if new_stop > current_stop:
                    decision = "RAISE STOP"

            results.append(
                {
                    "ticker": ticker,
                    "average_price": round(avg_price, 4),
                    "quantity": round(qty, 4),
                    "current_price": round(current_price, 4),
                    "current_profit_pct": round(profit_pct, 2),
                    "trend": trend,
                    "trend_strength": trend_strength,
                    "new_stop": round(new_stop, 4),
                    "decision": decision,
                    "estimated_trend_duration": str(analysis.get("estimated_trend_duration") or "1-2 islem gunu"),
                }
            )

        return results
