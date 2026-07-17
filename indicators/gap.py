
"""Gap detection utilities."""

from __future__ import annotations

import pandas as pd

from indicators.common import require_columns


def gap_detection(
	frame: pd.DataFrame,
	*,
	threshold: float = 0.003,
) -> pd.DataFrame:
	"""Detect upside and downside gaps using open/close relationships."""

	require_columns(frame, ["open", "close"])
	if threshold < 0:
		raise ValueError("threshold must be non-negative")

	result = frame.copy()
	previous_close = result["close"].shift(1)
	open_price = result["open"].astype(float)

	gap_up = open_price > previous_close * (1 + threshold)
	gap_down = open_price < previous_close * (1 - threshold)

	result["gap_up"] = gap_up.fillna(False)
	result["gap_down"] = gap_down.fillna(False)
	result["gap_size"] = ((open_price - previous_close).abs() / previous_close).fillna(0.0)
	result["gap_direction"] = 0
	result.loc[result["gap_up"], "gap_direction"] = 1
	result.loc[result["gap_down"], "gap_direction"] = -1
	return result

