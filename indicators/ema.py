
"""Exponential moving average indicator."""

from __future__ import annotations

import pandas as pd

from indicators.common import as_series
from indicators.common import ensure_period


def ema(values: pd.Series | list[float], period: int) -> pd.Series:
	"""Return the exponential moving average for the given series."""

	ensure_period(period)
	series = as_series(values)
	return series.ewm(span=period, adjust=False).mean()

