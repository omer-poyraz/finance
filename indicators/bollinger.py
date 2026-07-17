"""Bollinger bands indicator."""

from __future__ import annotations

import pandas as pd

from indicators.common import as_series
from indicators.common import ensure_period


def bollinger_bands(
    values: pd.Series | list[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> pd.DataFrame:
    """Return middle, upper, lower, bandwidth, and percent-b values."""

    ensure_period(period)
    if std_dev <= 0:
        raise ValueError("std_dev must be greater than zero")

    series = as_series(values)
    middle = series.rolling(window=period, min_periods=1).mean()
    deviation = series.rolling(window=period, min_periods=1).std(ddof=0).fillna(0.0)
    upper = middle + (deviation * std_dev)
    lower = middle - (deviation * std_dev)
    bandwidth = (upper - lower) / middle.replace(0, pd.NA)
    percent_b = (series - lower) / (upper - lower).replace(0, pd.NA)

    return pd.DataFrame(
        {
            "middle": middle,
            "upper": upper,
            "lower": lower,
            "bandwidth": bandwidth.fillna(0.0),
            "percent_b": percent_b.fillna(0.0),
        }
    )
