"""Technical analysis engine for multi-market scoring."""

from __future__ import annotations

from typing import Any

import pandas as pd

from indicators import atr
from indicators import bollinger_bands
from indicators import ema
from indicators import macd
from indicators import rsi
from indicators import sma
from indicators import volume_analysis


class TechnicalEngine:
    """Compute technical metrics and a normalized technical score."""

    def analyze(self, ticker: str, frame: pd.DataFrame) -> dict[str, Any]:
        close = frame["close"].astype(float)
        high = frame["high"].astype(float)
        low = frame["low"].astype(float)
        volume = frame["volume"].astype(float)

        ema20 = ema(close, 20)
        ema50 = ema(close, 50)
        ema200 = ema(close, 200)
        sma20 = sma(close, 20)
        sma50 = sma(close, 50)
        rsi14 = rsi(close, 14)
        macd_frame = macd(close)
        atr14 = atr(frame)
        bollinger = bollinger_bands(close)
        volume_frame = volume_analysis(volume)

        current_price = float(close.iloc[-1])
        ema20_value = float(ema20.iloc[-1])
        ema50_value = float(ema50.iloc[-1])
        ema200_value = float(ema200.iloc[-1])
        sma20_value = float(sma20.iloc[-1])
        sma50_value = float(sma50.iloc[-1])
        rsi14_value = float(rsi14.iloc[-1])
        macd_value = float(macd_frame["macd"].iloc[-1])
        macd_signal = float(macd_frame["signal"].iloc[-1])
        atr14_value = float(atr14.iloc[-1])
        relative_volume = float(volume_frame["volume_ratio"].iloc[-1])

        support = float(low.rolling(window=50, min_periods=1).min().iloc[-1])
        resistance = float(high.rolling(window=50, min_periods=1).max().iloc[-1])

        adx_value = self._estimate_adx(close, high, low)
        supertrend_signal = self._supertrend_signal(current_price, ema20_value, atr14_value)
        fib_levels = self._fibonacci_levels(high, low)

        reasons: list[str] = []
        score = 0.0

        if ema20_value > ema50_value:
            score += 14.0
            reasons.append("EMA20 EMA50 ustunde")
        if ema50_value > ema200_value:
            score += 10.0
            reasons.append("EMA50 EMA200 ustunde")
        if 45.0 <= rsi14_value <= 65.0:
            score += 12.0
            reasons.append("RSI dengeli")
        if macd_value > macd_signal:
            score += 12.0
            reasons.append("MACD pozitif")
        if relative_volume >= 1.1:
            score += min(12.0, relative_volume * 6.0)
            reasons.append("Hacim ortalamanin uzerinde")
        if adx_value >= 25.0:
            score += 12.0
            reasons.append("ADX trend gucunu destekliyor")
        if supertrend_signal == "Bullish":
            score += 12.0
            reasons.append("SuperTrend yukari")
        if support > 0 and current_price <= support * 1.05:
            score += 8.0
            reasons.append("Destek bolgesine yakin")
        if resistance > 0 and current_price >= resistance * 0.98:
            score += 5.0
            reasons.append("Direnc testi")

        if not reasons:
            reasons.append("Guclu teknik kanit sinirli")

        trend = "Neutral"
        if ema20_value > ema50_value > ema200_value:
            trend = "Bullish"
        elif ema20_value < ema50_value < ema200_value:
            trend = "Bearish"

        return {
            "ticker": ticker,
            "technical_score": round(max(0.0, min(100.0, score)), 2),
            "trend": trend,
            "current_price": round(current_price, 4),
            "ema20": round(ema20_value, 4),
            "ema50": round(ema50_value, 4),
            "ema200": round(ema200_value, 4),
            "sma20": round(sma20_value, 4),
            "sma50": round(sma50_value, 4),
            "rsi14": round(rsi14_value, 4),
            "macd_value": round(macd_value, 6),
            "macd_signal": round(macd_signal, 6),
            "macd": "Bullish" if macd_value > macd_signal else "Bearish" if macd_value < macd_signal else "Neutral",
            "bollinger_upper": round(float(bollinger["upper"].iloc[-1]), 4),
            "bollinger_lower": round(float(bollinger["lower"].iloc[-1]), 4),
            "atr": round(atr14_value, 6),
            "adx": round(adx_value, 4),
            "supertrend": supertrend_signal,
            "fibonacci": fib_levels,
            "support": round(support, 4),
            "resistance": round(resistance, 4),
            "relative_volume": round(relative_volume, 4),
            "volume": round(float(volume.iloc[-1]), 4),
            "average_volume": round(float(volume_frame["volume_sma"].iloc[-1]), 4),
            "reasons": reasons,
        }

    def _estimate_adx(self, close: pd.Series, high: pd.Series, low: pd.Series) -> float:
        lookback = min(14, len(close) - 1)
        if lookback < 2:
            return 20.0

        up_moves = high.diff().fillna(0.0)
        down_moves = (-low.diff()).fillna(0.0)
        plus_dm = up_moves.where((up_moves > down_moves) & (up_moves > 0), 0.0)
        minus_dm = down_moves.where((down_moves > up_moves) & (down_moves > 0), 0.0)
        tr = pd.concat(
            [
                (high - low),
                (high - close.shift(1)).abs(),
                (low - close.shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)

        atr_roll = tr.rolling(lookback, min_periods=1).mean().replace(0, 1e-9)
        plus_di = 100.0 * (plus_dm.rolling(lookback, min_periods=1).mean() / atr_roll)
        minus_di = 100.0 * (minus_dm.rolling(lookback, min_periods=1).mean() / atr_roll)
        dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-9)) * 100.0
        adx_value = float(dx.rolling(lookback, min_periods=1).mean().iloc[-1])
        return max(0.0, min(100.0, adx_value))

    def _supertrend_signal(self, price: float, ema20_value: float, atr_value: float) -> str:
        buffer = max(atr_value * 0.4, price * 0.004)
        if price > ema20_value + buffer:
            return "Bullish"
        if price < ema20_value - buffer:
            return "Bearish"
        return "Neutral"

    def _fibonacci_levels(self, high: pd.Series, low: pd.Series) -> dict[str, float]:
        highest = float(high.rolling(window=60, min_periods=1).max().iloc[-1])
        lowest = float(low.rolling(window=60, min_periods=1).min().iloc[-1])
        distance = max(highest - lowest, 1e-9)
        return {
            "0.236": round(highest - distance * 0.236, 4),
            "0.382": round(highest - distance * 0.382, 4),
            "0.5": round(highest - distance * 0.5, 4),
            "0.618": round(highest - distance * 0.618, 4),
            "0.786": round(highest - distance * 0.786, 4),
        }
