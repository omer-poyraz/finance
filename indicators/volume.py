
"""Volume analysis utilities."""

from __future__ import annotations

import pandas as pd

from indicators.common import as_series
from indicators.common import ensure_period


def volume_analysis(
	values: pd.Series | list[float],
	window: int = 20,
	spike_multiplier: float = 1.5,
) -> pd.DataFrame:
	"""Return rolling volume metrics and spike detection."""

	ensure_period(window)
	if spike_multiplier <= 0:
		raise ValueError("spike_multiplier must be positive")

	series = as_series(values)
	average_volume = series.rolling(window=window, min_periods=1).mean()
	volume_ratio = series / average_volume.replace(0, pd.NA)

	return pd.DataFrame(
		{
			"volume": series,
			"volume_sma": average_volume,
			"volume_ratio": volume_ratio.fillna(0.0),
			"volume_spike": (series > average_volume * spike_multiplier).fillna(False),
		}
	)

