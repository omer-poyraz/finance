"""Average true range indicator."""

from __future__ import annotations

import pandas as pd

from indicators.common import require_columns


def atr(frame: pd.DataFrame, period: int = 14) -> pd.Series:
    """Return the average true range for OHLC data."""

    if period <= 0:
        raise ValueError("period must be greater than zero")

    require_columns(frame, ["high", "low", "close"])
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)
    close = frame["close"].astype(float)

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(window=period, min_periods=1).mean()
