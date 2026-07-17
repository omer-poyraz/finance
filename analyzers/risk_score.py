
"""Risk scoring analyzer."""

from __future__ import annotations

import pandas as pd

from analyzers.base import BaseAnalyzer
from indicators import atr
from indicators import gap_detection
from shared.exceptions import AnalysisError


class RiskAnalyzer(BaseAnalyzer):
	"""Score downside risk and stability characteristics."""

	analyzer_name = "risk"

	def score(self, frame: pd.DataFrame) -> float:
		"""Return a risk-adjusted quality score."""

		required_columns = ["open", "high", "low", "close"]
		missing_columns = [column for column in required_columns if column not in frame.columns]
		if missing_columns:
			raise AnalysisError(
				f"RiskAnalyzer requires columns: {', '.join(required_columns)}"
			)

		if frame.empty:
			raise AnalysisError("RiskAnalyzer requires at least one market row")

		close = frame["close"].astype(float)
		returns = close.pct_change().dropna()
		atr_series = atr(frame)
		gap_frame = gap_detection(frame[["open", "close"]].copy())

		volatility = float(returns.std(ddof=0) * 100) if not returns.empty else 0.0
		atr_percent = float(atr_series.iloc[-1] / close.iloc[-1] * 100)
		max_drawdown = float(((close.cummax() - close) / close.cummax()).max() * 100)
		recent_gap_pressure = float(gap_frame["gap_size"].tail(5).mean() * 100)

		score = 100.0
		score -= min(35.0, volatility * 3.0)
		score -= min(25.0, atr_percent * 4.0)
		score -= min(20.0, max_drawdown * 2.0)
		score -= min(10.0, recent_gap_pressure * 5.0)

		return self._clamp_score(score)

