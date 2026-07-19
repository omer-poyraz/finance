"""Trend scoring and duration estimation engine."""

from __future__ import annotations

from typing import Any


class TrendEngine:
    """Estimate trend strength and likely trend duration window."""

    def analyze(
        self,
        *,
        technical_score: float,
        market_intelligence_score: float,
        news_score: float,
        volatility_pct: float,
        relative_volume: float,
        trend_label: str,
    ) -> dict[str, Any]:
        score = (
            technical_score * 0.45
            + market_intelligence_score * 0.20
            + news_score * 0.20
            + min(100.0, max(0.0, relative_volume * 40.0)) * 0.10
            + max(0.0, 100.0 - (volatility_pct * 3.0)) * 0.05
        )

        if trend_label == "Bullish":
            score += 6.0
        elif trend_label == "Bearish":
            score -= 10.0

        trend_strength = int(round(max(0.0, min(100.0, score))))
        duration = self._estimate_duration(trend_strength=trend_strength, volatility_pct=volatility_pct)

        return {
            "trend_strength": trend_strength,
            "estimated_trend_duration": duration,
        }

    def _estimate_duration(self, *, trend_strength: int, volatility_pct: float) -> str:
        if trend_strength >= 88 and volatility_pct <= 2.5:
            return "5-10 islem gunu"
        if trend_strength >= 75:
            return "3-7 islem gunu"
        if trend_strength >= 60:
            return "2-5 islem gunu"
        return "1-2 islem gunu"
