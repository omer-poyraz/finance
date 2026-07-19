"""Fundamental scoring engine."""

from __future__ import annotations

from typing import Any

import pandas as pd

from analyzers import FinancialAnalyzer


class FundamentalEngine:
    """Estimate fundamental quality score from available local market data."""

    def __init__(self) -> None:
        self._analyzer = FinancialAnalyzer()

    def analyze(self, frame: pd.DataFrame, *, market_cap: float | None = None) -> dict[str, Any]:
        close = frame["close"].astype(float)
        volume = frame["volume"].astype(float)

        returns = close.pct_change().dropna()
        avg_return_pct = float(returns.mean() * 100.0) if not returns.empty else 0.0
        volatility_pct = float(returns.std(ddof=0) * 100.0) if not returns.empty else 0.0
        liquidity_ratio = float(volume.iloc[-1] / volume.mean()) if float(volume.mean()) > 0 else 1.0

        metrics = {
            "revenue_growth": avg_return_pct,
            "net_margin": max(0.0, 18.0 - volatility_pct),
            "debt_to_equity": max(0.2, min(2.8, volatility_pct / 9.0)),
            "current_ratio": max(0.8, min(3.0, liquidity_ratio)),
            "roe": max(4.0, min(32.0, avg_return_pct + 11.0)),
        }

        if market_cap and market_cap > 0:
            scale_boost = min(6.0, max(0.0, market_cap / 1_000_000_000_000))
            metrics["roe"] = min(35.0, metrics["roe"] + scale_boost)

        score = self._analyzer.score(metrics)
        return {
            "fundamental_score": round(score, 2),
            "fundamental_metrics": {key: round(float(value), 4) for key, value in metrics.items()},
        }
