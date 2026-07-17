"""Shared helpers for manual indicator calculations."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from shared.exceptions import IndicatorError


def as_series(values: pd.Series | Iterable[float], *, name: str | None = None) -> pd.Series:
    """Normalize a sequence into a floating-point pandas Series."""

    if isinstance(values, pd.Series):
        series = values.copy()
    else:
        series = pd.Series(list(values), name=name)

    if series.empty:
        raise IndicatorError("Indicator input cannot be empty")

    return series.astype(float)


def ensure_period(period: int) -> None:
    """Validate rolling window periods."""

    if period <= 0:
        raise IndicatorError("Indicator period must be greater than zero")


def require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    """Ensure the dataframe contains the expected columns."""

    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise IndicatorError(f"Missing required columns: {', '.join(missing)}")
