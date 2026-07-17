
"""Technical scoring analyzer."""

from __future__ import annotations

import pandas as pd

from analyzers.base import BaseAnalyzer
from indicators import bollinger_bands
from indicators import ema
from indicators import gap_detection
from indicators import macd
from indicators import moving_average_cross
from indicators import rsi
from indicators import volume_analysis
from shared.exceptions import AnalysisError


class TechnicalAnalyzer(BaseAnalyzer):
	"""Score a market snapshot using technical indicators."""

	analyzer_name = "technical"

	def score(self, frame: pd.DataFrame) -> float:
		"""Return a technical score for OHLCV market data."""

		required_columns = ["open", "high", "low", "close", "volume"]
		missing_columns = [column for column in required_columns if column not in frame.columns]
		if missing_columns:
			raise AnalysisError(
				f"TechnicalAnalyzer requires columns: {', '.join(required_columns)}"
			)

		if frame.empty:
			raise AnalysisError("TechnicalAnalyzer requires at least one market row")

		close = frame["close"].astype(float)
		volume = frame["volume"].astype(float)

		rsi_series = rsi(close)
		macd_frame = macd(close)
		fast_ema = ema(close, 12)
		slow_ema = ema(close, 26)
		cross_frame = moving_average_cross(fast_ema, slow_ema)
		bollinger_frame = bollinger_bands(close)
		volume_frame = volume_analysis(volume)
		gap_frame = gap_detection(frame[["open", "close"]].copy())

		score = 0.0

		last_rsi = float(rsi_series.iloc[-1])
		if 45.0 <= last_rsi <= 65.0:
			score += 22.0
		elif 30.0 <= last_rsi < 45.0:
			score += 12.0
		elif last_rsi > 70.0:
			score -= 10.0

		last_histogram = float(macd_frame["histogram"].iloc[-1])
		if last_histogram > 0:
			score += 20.0
		elif last_histogram < 0:
			score -= 12.0

		last_cross = int(cross_frame["signal"].iloc[-1])
		if last_cross > 0:
			score += 20.0
		elif last_cross < 0:
			score -= 15.0

		last_volume_ratio = float(volume_frame["volume_ratio"].iloc[-1])
		if last_volume_ratio >= 1.5:
			score += 15.0
		elif last_volume_ratio >= 1.1:
			score += 8.0

		last_percent_b = float(bollinger_frame["percent_b"].iloc[-1])
		if 0.35 <= last_percent_b <= 0.85:
			score += 10.0
		elif last_percent_b > 0.95:
			score -= 8.0

		last_gap_direction = int(gap_frame["gap_direction"].iloc[-1])
		if last_gap_direction > 0:
			score += 5.0
		elif last_gap_direction < 0:
			score -= 5.0

		trend_strength = float((fast_ema.iloc[-1] - slow_ema.iloc[-1]) / close.iloc[-1] * 100)
		if trend_strength > 0:
			score += min(10.0, trend_strength)
		else:
			score += max(-10.0, trend_strength)

		return self._clamp_score(score)

