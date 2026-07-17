
"""Moving average convergence divergence indicator."""

from __future__ import annotations

import pandas as pd

from indicators.common import as_series
from indicators.common import ensure_period
from indicators.ema import ema


def macd(
	values: pd.Series | list[float],
	fast_period: int = 12,
	slow_period: int = 26,
	signal_period: int = 9,
) -> pd.DataFrame:
	"""Return MACD line, signal line, and histogram as a dataframe."""

	ensure_period(fast_period)
	ensure_period(slow_period)
	ensure_period(signal_period)

	if fast_period >= slow_period:
		raise ValueError("fast_period must be lower than slow_period")

	series = as_series(values)
	macd_line = ema(series, fast_period) - ema(series, slow_period)
	signal_line = macd_line.ewm(span=signal_period, adjust=False).mean()
	histogram = macd_line - signal_line

	return pd.DataFrame(
		{
			"macd": macd_line,
			"signal": signal_line,
			"histogram": histogram,
		}
	)

