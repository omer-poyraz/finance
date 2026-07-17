"""Simple moving average indicator."""

from __future__ import annotations

import pandas as pd

from indicators.common import as_series
from indicators.common import ensure_period


def sma(values: pd.Series | list[float], period: int) -> pd.Series:
    """Return the simple moving average for the given series."""

    ensure_period(period)
    series = as_series(values)
    return series.rolling(window=period, min_periods=1).mean()
