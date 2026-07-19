"""Market intelligence engine."""

from __future__ import annotations

from typing import Any

import pandas as pd


class MarketIntelligenceEngine:
    """Compute contextual market intelligence score."""

    def analyze(self, frame: pd.DataFrame, *, market_name: str) -> dict[str, Any]:
        close = frame["close"].astype(float)
        volume = frame["volume"].astype(float)

        momentum_5 = self._pct_change(close, 5)
        momentum_20 = self._pct_change(close, 20)
        volatility = float(close.pct_change().dropna().std(ddof=0) * 100.0) if len(close) > 1 else 0.0
        liquidity = float(volume.iloc[-1] / volume.mean()) if float(volume.mean()) > 0 else 1.0

        score = 50.0
        score += max(-12.0, min(12.0, momentum_5 * 0.9))
        score += max(-16.0, min(16.0, momentum_20 * 0.8))
        score += max(-10.0, min(10.0, (liquidity - 1.0) * 20.0))
        score -= max(0.0, min(15.0, volatility * 1.3))

        label = "Balanced"
        if score >= 70:
            label = "Strong"
        elif score <= 40:
            label = "Weak"

        return {
            "market_intelligence_score": round(max(0.0, min(100.0, score)), 2),
            "market_intelligence_label": label,
            "market_name": market_name,
            "momentum_5d": round(momentum_5, 4),
            "momentum_20d": round(momentum_20, 4),
            "volatility_pct": round(volatility, 4),
            "liquidity_ratio": round(liquidity, 4),
        }

    def _pct_change(self, series: pd.Series, lookback: int) -> float:
        if len(series) <= lookback:
            return 0.0
        start = float(series.iloc[-(lookback + 1)])
        end = float(series.iloc[-1])
        if start == 0:
            return 0.0
        return ((end - start) / start) * 100.0
