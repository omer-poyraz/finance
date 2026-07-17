from __future__ import annotations

import pandas as pd

from indicators import atr
from indicators import bollinger_bands
from indicators import ema
from indicators import gap_detection
from indicators import macd
from indicators import moving_average_cross
from indicators import rsi
from indicators import sma
from indicators import volume_analysis


def test_indicator_outputs_have_expected_shapes() -> None:
    series = pd.Series([1, 2, 3, 4, 5, 6], dtype=float)
    frame = pd.DataFrame(
        {
            "open": [1, 2, 3, 4, 5, 6],
            "high": [2, 3, 4, 5, 6, 7],
            "low": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5],
            "close": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
            "volume": [10, 20, 30, 40, 50, 60],
        }
    )

    assert len(ema(series, 3)) == len(series)
    assert len(sma(series, 3)) == len(series)
    assert len(rsi(series)) == len(series)
    assert list(macd(series).columns) == ["macd", "signal", "histogram"]
    assert len(atr(frame)) == len(frame)
    assert list(bollinger_bands(series).columns) == ["middle", "upper", "lower", "bandwidth", "percent_b"]
    assert list(volume_analysis(frame["volume"]).columns) == [
        "volume",
        "volume_sma",
        "volume_ratio",
        "volume_spike",
    ]
    assert list(gap_detection(frame[["open", "close"]]).columns) == [
        "open",
        "close",
        "gap_up",
        "gap_down",
        "gap_size",
        "gap_direction",
    ]
    assert list(moving_average_cross(ema(series, 2), sma(series, 3)).columns) == [
        "fast",
        "slow",
        "spread",
        "bullish_cross",
        "bearish_cross",
        "signal",
    ]
