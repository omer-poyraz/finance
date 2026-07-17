
"""Relative strength index indicator."""

from __future__ import annotations

import numpy as np
import pandas as pd

from indicators.common import as_series
from indicators.common import ensure_period


def rsi(values: pd.Series | list[float], period: int = 14) -> pd.Series:
	"""Return the relative strength index for the given series."""

	ensure_period(period)
	series = as_series(values)
	delta = series.diff()
	gains = delta.clip(lower=0.0)
	losses = -delta.clip(upper=0.0)

	average_gain = gains.ewm(alpha=1 / period, adjust=False).mean()
	average_loss = losses.ewm(alpha=1 / period, adjust=False).mean()
	relative_strength = average_gain / average_loss.replace(0, np.nan)
	values = 100 - (100 / (1 + relative_strength))
	return values.fillna(50.0)

