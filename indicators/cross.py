"""Moving average cross detection utilities."""

from __future__ import annotations

import pandas as pd


def moving_average_cross(
    fast_series: pd.Series,
    slow_series: pd.Series,
) -> pd.DataFrame:
    """Return bullish and bearish cross signals for two moving averages."""

    if len(fast_series) != len(slow_series):
        raise ValueError("fast_series and slow_series must have the same length")

    diff = fast_series.astype(float) - slow_series.astype(float)
    previous_diff = diff.shift(1)

    bullish_cross = (diff > 0) & (previous_diff <= 0)
    bearish_cross = (diff < 0) & (previous_diff >= 0)

    return pd.DataFrame(
        {
            "fast": fast_series,
            "slow": slow_series,
            "spread": diff,
            "bullish_cross": bullish_cross.fillna(False),
            "bearish_cross": bearish_cross.fillna(False),
            "signal": 0,
        }
    ).assign(
        signal=lambda frame: frame["signal"].mask(frame["bullish_cross"], 1).mask(
            frame["bearish_cross"], -1
        )
    )
