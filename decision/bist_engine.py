"""BIST graph-first scoring and opportunity selection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any


DEFAULT_BIST_SCORING_CONFIG: dict[str, Any] = {
    "top_n": 20,
    "final_n": 5,
    "weights": {
        "graph_structure": 45,
        "trend": 20,
        "volume": 15,
        "momentum": 10,
        "news": 5,
        "ai_confidence": 5,
    },
    "hard_filters": {
        "min_price": 0.1,
        "min_volume": 1,
        "min_average_volume": 1,
    },
    "thresholds": {
        "buy_score": 60,
        "strengthened_score_delta": 5,
        "strengthened_rr_delta": 0.2,
        "weakened_score_delta": -5,
        "exit_score": 35,
    },
}


@dataclass(frozen=True, slots=True)
class BistOpportunityResult:
    """Structured BIST opportunity output used by the pipeline."""

    ticker: str
    company_name: str
    market: str
    total_score: float
    decision: str
    component_scores: dict[str, float] = field(default_factory=dict)
    score_lines: list[str] = field(default_factory=list)
    chart_formations: list[dict[str, Any]] = field(default_factory=list)
    market_structure_signals: list[str] = field(default_factory=list)
    indicator_confirmations: list[str] = field(default_factory=list)
    hard_filter_reasons: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    price_plan_notes: list[str] = field(default_factory=list)
    entry_price: float = 0.0
    entry_range_low: float = 0.0
    entry_range_high: float = 0.0
    stop_loss: float = 0.0
    current_target: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    take_profit_3: float = 0.0
    risk_reward_ratio: float = 0.0
    trend: str = "Neutral"
    trend_strength: int = 0
    estimated_trend_duration: str = "1-2 islem gunu"
    current_price: float = 0.0
    support: float = 0.0
    resistance: float = 0.0
    atr: float = 0.0
    volume: float = 0.0
    average_volume: float = 0.0
    relative_volume: float = 0.0
    rsi14: float = 0.0
    macd_state: str = "Neutral"
    news_score: float = 0.0
    news_sentiment: str = "Neutral"
    ai_confidence: float | None = None
    ai_summary: str | None = None
    ai_reason: str | None = None
    ai_risk: str | None = None
    hard_filtered: bool = False
    score_label: str = "Watch"
    status: str = "ELIGIBLE"
    rank: int = 0


class BistOpportunityEngine:
    """Score BIST candidates without hard-filtering weak but valid opportunities."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config = self._merge_config(config)

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    def score_candidate(
        self,
        market_item: dict[str, Any],
        *,
        news_score: float,
        news_sentiment: str,
        news_confidence: float,
        news_reasons: list[str] | None = None,
        ai_summary: str | None = None,
        ai_reason: str | None = None,
        ai_risk: str | None = None,
    ) -> BistOpportunityResult:
        ticker = str(market_item.get("ticker") or market_item.get("symbol") or "").strip().upper()
        company_name = str(market_item.get("company_name") or market_item.get("name") or ticker or "UNKNOWN")
        market = str(market_item.get("market") or "BIST").strip().upper() or "BIST"

        current_price = self._float(market_item.get("current_price") or market_item.get("last_price"))
        support = self._float(market_item.get("support"))
        resistance = self._float(market_item.get("resistance"))
        atr_value = self._float(market_item.get("atr"))
        volume = self._float(market_item.get("volume"))
        average_volume = self._float(market_item.get("average_volume"))
        relative_volume = self._float(market_item.get("relative_volume"))
        technical_score = self._float(market_item.get("technical_score"))
        trend = str(market_item.get("trend") or "Neutral")
        trend_strength = self._int(market_item.get("trend_strength"))
        estimated_trend_duration = str(market_item.get("estimated_trend_duration") or "1-2 islem gunu")
        rsi14 = self._float(market_item.get("rsi14"))
        macd_state = str(market_item.get("macd") or market_item.get("macd_state") or "Neutral")

        hard_filter_reasons = self._hard_filters(
            current_price=current_price,
            support=support,
            resistance=resistance,
            atr_value=atr_value,
            volume=volume,
            average_volume=average_volume,
            technical_score=technical_score,
            trend=trend,
        )
        if hard_filter_reasons:
            return BistOpportunityResult(
                ticker=ticker,
                company_name=company_name,
                market=market,
                total_score=0.0,
                decision="FILTERED",
                hard_filter_reasons=hard_filter_reasons,
                reasons=list(news_reasons or []),
                price_plan_notes=["Hard filter nedeniyle fiyat planı üretilmedi"],
                entry_price=0.0,
                entry_range_low=0.0,
                entry_range_high=0.0,
                stop_loss=0.0,
                current_target=0.0,
                take_profit_1=0.0,
                take_profit_2=0.0,
                take_profit_3=0.0,
                risk_reward_ratio=0.0,
                trend=trend,
                trend_strength=trend_strength,
                estimated_trend_duration=estimated_trend_duration,
                current_price=current_price,
                support=support,
                resistance=resistance,
                atr=atr_value,
                volume=volume,
                average_volume=average_volume,
                relative_volume=relative_volume,
                rsi14=rsi14,
                macd_state=macd_state,
                news_score=max(0.0, min(100.0, float(news_score))),
                news_sentiment=news_sentiment,
                ai_confidence=max(0.0, min(100.0, float(news_confidence))),
                ai_summary=ai_summary,
                ai_reason=ai_reason,
                ai_risk=ai_risk,
                hard_filtered=True,
                score_label="Filtered",
                status="FILTERED",
            )

        graph_analysis = self._graph_structure_score(
            market_item=market_item,
            trend=trend,
            trend_strength=trend_strength,
            current_price=current_price,
            support=support,
            resistance=resistance,
            atr_value=atr_value,
            volume=volume,
            average_volume=average_volume,
            relative_volume=relative_volume,
            rsi14=rsi14,
            macd_state=macd_state,
        )
        raw_components = {
            "graph_structure": graph_analysis["score"],
            "trend": self._trend_score(trend=trend, trend_strength=trend_strength, market_item=market_item),
            "volume": self._volume_score(
                volume=volume,
                average_volume=average_volume,
                relative_volume=relative_volume,
                chart_score=graph_analysis["score"],
            ),
            "momentum": self._momentum_score(
                technical_score=technical_score,
                rsi14=rsi14,
                macd_state=macd_state,
                market_item=market_item,
                graph_score=graph_analysis["score"],
            ),
            "news": self._news_score(news_score=news_score, news_sentiment=news_sentiment),
            "ai_confidence": self._ai_confidence_score(news_confidence=news_confidence),
        }
        component_scores = self._weighted_component_scores(raw_components)

        total_score = round(sum(component_scores.values()), 2)
        entry_price, stop_loss, current_target, rr_ratio, price_plan_notes = self._price_plan(
            current_price=current_price,
            support=support,
            resistance=resistance,
            atr_value=atr_value,
            trend_strength=trend_strength,
        )

        entry_range_low = max(0.01, entry_price - max(atr_value * 0.25, entry_price * 0.002))
        entry_range_high = entry_price + max(atr_value * 0.25, entry_price * 0.002)
        take_profit_1 = round(entry_price + ((entry_price - stop_loss) * 1.0), 4)
        take_profit_2 = round(entry_price + ((entry_price - stop_loss) * 1.6), 4)
        take_profit_3 = round(entry_price + ((entry_price - stop_loss) * 2.4), 4)

        score_lines = [
            f"Grafik +{component_scores['graph_structure']:.0f}",
            f"Trend +{component_scores['trend']:.0f}",
            f"Hacim +{component_scores['volume']:.0f}",
            f"Momentum +{component_scores['momentum']:.0f}",
            f"News +{component_scores['news']:.0f}",
            f"AI +{component_scores['ai_confidence']:.0f}",
        ]
        reasons = self._reasons(
            market_item=market_item,
            trend=trend,
            trend_strength=trend_strength,
            relative_volume=relative_volume,
            rsi14=rsi14,
            macd_state=macd_state,
            news_sentiment=news_sentiment,
            news_reasons=news_reasons or [],
            graph_analysis=graph_analysis,
        )

        score_label = self._label(total_score)
        decision = "BUY" if total_score >= float(self._thresholds().get("buy_score", 60)) else "WATCH"

        return BistOpportunityResult(
            ticker=ticker,
            company_name=company_name,
            market=market,
            total_score=total_score,
            decision=decision,
            component_scores={name: round(value, 2) for name, value in component_scores.items()},
            score_lines=score_lines,
            chart_formations=list(graph_analysis["formations"]),
            market_structure_signals=list(graph_analysis["market_structure"]),
            indicator_confirmations=list(graph_analysis["indicator_confirmations"]),
            hard_filter_reasons=hard_filter_reasons,
            reasons=reasons,
            price_plan_notes=price_plan_notes,
            entry_price=round(entry_price, 4),
            entry_range_low=round(entry_range_low, 4),
            entry_range_high=round(entry_range_high, 4),
            stop_loss=round(stop_loss, 4),
            current_target=round(current_target, 4),
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            take_profit_3=take_profit_3,
            risk_reward_ratio=round(rr_ratio, 4),
            trend=trend,
            trend_strength=trend_strength,
            estimated_trend_duration=estimated_trend_duration,
            current_price=round(current_price, 4),
            support=round(support, 4),
            resistance=round(resistance, 4),
            atr=round(atr_value, 6),
            volume=round(volume, 4),
            average_volume=round(average_volume, 4),
            relative_volume=round(relative_volume, 4),
            rsi14=round(rsi14, 4),
            macd_state=macd_state,
            news_score=round(max(0.0, min(100.0, float(news_score))), 2),
            news_sentiment=news_sentiment,
            ai_confidence=None,
            ai_summary=ai_summary,
            ai_reason=ai_reason,
            ai_risk=ai_risk,
            hard_filtered=False,
            score_label=score_label,
            status="ELIGIBLE",
        )

    def _hard_filters(
        self,
        *,
        current_price: float,
        support: float,
        resistance: float,
        atr_value: float,
        volume: float,
        average_volume: float,
        technical_score: float,
        trend: str,
    ) -> list[str]:
        hard_filters = self._hard_filter_config()
        reasons: list[str] = []

        if current_price <= float(hard_filters.get("min_price", 0.1)):
            reasons.append("Teknik veri bozuk veya fiyat gecersiz")
        if support <= 0 or resistance <= 0 or atr_value <= 0:
            reasons.append("Analiz yapilamiyor")
        if volume <= float(hard_filters.get("min_volume", 1)):
            reasons.append("Islem hacmi yok denecek kadar dusuk")
        if average_volume <= float(hard_filters.get("min_average_volume", 1)):
            reasons.append("Ortalama hacim yetersiz")
        if technical_score < 5 and trend not in {"Bullish", "Neutral", "Bearish"}:
            reasons.append("Teknik durum yorumlanamiyor")

        seen: set[str] = set()
        unique: list[str] = []
        for reason in reasons:
            if reason in seen:
                continue
            seen.add(reason)
            unique.append(reason)
        return unique

    def _weighted_component_scores(self, raw_components: dict[str, float]) -> dict[str, float]:
        weights = dict(self._config.get("weights") or {})
        weighted: dict[str, float] = {}
        for name in ["graph_structure", "trend", "volume", "momentum", "news", "ai_confidence"]:
            weight_pct = float(weights.get(name, 0.0))
            raw_score = max(0.0, min(100.0, float(raw_components.get(name, 0.0))))
            weighted[name] = self._cap((raw_score * weight_pct) / 100.0, name)
        return weighted

    def _graph_structure_score(
        self,
        *,
        market_item: dict[str, Any],
        trend: str,
        trend_strength: int,
        current_price: float,
        support: float,
        resistance: float,
        atr_value: float,
        volume: float,
        average_volume: float,
        relative_volume: float,
        rsi14: float,
        macd_state: str,
    ) -> dict[str, Any]:
        feature = self._chart_features(
            market_item=market_item,
            trend=trend,
            trend_strength=trend_strength,
            current_price=current_price,
            support=support,
            resistance=resistance,
            atr_value=atr_value,
            volume=volume,
            average_volume=average_volume,
            relative_volume=relative_volume,
            rsi14=rsi14,
            macd_state=macd_state,
        )
        formations = self._detect_chart_formations(feature)
        market_structure = self._detect_market_structure(feature)
        indicator_confirmations = self._indicator_confirmations(feature)

        base_score = 28.0
        if formations:
            base_score += min(52.0, sum(float(item["confidence"]) for item in formations[:4]) * 0.22)
        if market_structure:
            base_score += min(15.0, len(market_structure) * 2.5)
        if indicator_confirmations:
            base_score += min(12.0, len(indicator_confirmations) * 2.0)
        if feature["volume_expansion"]:
            base_score += 6.0
        if feature["breakout_up"]:
            base_score += 4.0
        if feature["breakout_down"]:
            base_score -= 8.0

        score = max(0.0, min(100.0, base_score))
        return {
            "score": score,
            "formations": formations,
            "market_structure": market_structure,
            "indicator_confirmations": indicator_confirmations,
        }

    def _trend_score(self, *, trend: str, trend_strength: int, market_item: dict[str, Any]) -> float:
        score = 0.0
        ema20 = self._float(market_item.get("ema20"))
        ema50 = self._float(market_item.get("ema50"))
        ema200 = self._float(market_item.get("ema200"))
        current_price = self._float(market_item.get("current_price") or market_item.get("last_price"))

        if trend == "Bullish":
            score += 11.0
        elif trend == "Neutral":
            score += 6.0
        else:
            score += 2.0

        if ema20 > ema50:
            score += 4.0
        if ema50 > ema200:
            score += 3.0
        if current_price >= ema20 and ema20 > 0:
            score += 2.0

        score += min(6.0, max(0.0, trend_strength / 20.0))
        return max(0.0, min(100.0, score * 3.2))

    def _momentum_score(
        self,
        *,
        technical_score: float,
        rsi14: float,
        macd_state: str,
        market_item: dict[str, Any],
        graph_score: float,
    ) -> float:
        score = min(8.0, max(0.0, technical_score / 10.0))
        daily_change_pct = self._float(market_item.get("daily_change_pct"))
        gap_up = bool(market_item.get("gap_up"))
        if macd_state == "Bullish":
            score += 5.0
        elif macd_state == "Neutral":
            score += 2.5
        if 45.0 <= rsi14 <= 68.0:
            score += 4.5
        elif 35.0 <= rsi14 < 45.0:
            score += 2.5
        elif rsi14 > 70.0:
            score += 1.0
        if daily_change_pct > 0:
            score += min(2.5, daily_change_pct * 0.3)
        if gap_up:
            score += 1.5
        if graph_score >= 70:
            score += 1.5
        return max(0.0, min(100.0, score * 4.8))

    def _volume_score(
        self,
        *,
        volume: float,
        average_volume: float,
        relative_volume: float,
        chart_score: float,
    ) -> float:
        score = 0.0
        if average_volume > 0 and volume > 0:
            volume_ratio = volume / max(average_volume, 1e-9)
            score += min(7.0, max(0.0, volume_ratio * 3.5))
        score += min(5.0, max(0.0, relative_volume * 4.0))
        if relative_volume >= 1.25:
            score += 3.0
        elif relative_volume >= 1.05:
            score += 1.5
        if chart_score >= 70 and relative_volume >= 1.05:
            score += 2.0
        return max(0.0, min(100.0, score * 6.0))

    def _news_score(self, *, news_score: float, news_sentiment: str) -> float:
        base = max(0.0, min(100.0, float(news_score)))
        if news_sentiment == "Positive":
            base += 4.0
        elif news_sentiment == "Negative":
            base -= 12.0
        return max(0.0, min(100.0, base))

    def _ai_confidence_score(self, *, news_confidence: float) -> float:
        return max(0.0, min(100.0, float(news_confidence)))

    def _chart_features(
        self,
        *,
        market_item: dict[str, Any],
        trend: str,
        trend_strength: int,
        current_price: float,
        support: float,
        resistance: float,
        atr_value: float,
        volume: float,
        average_volume: float,
        relative_volume: float,
        rsi14: float,
        macd_state: str,
    ) -> dict[str, Any]:
        daily_change = self._float(market_item.get("daily_change_pct"))
        momentum_5d = self._float(market_item.get("momentum_5d"))
        momentum_20d = self._float(market_item.get("momentum_20d"))
        volatility_pct = self._float(market_item.get("volatility_pct"))
        boll_upper = self._float(market_item.get("bollinger_upper"))
        boll_lower = self._float(market_item.get("bollinger_lower"))
        ema20 = self._float(market_item.get("ema20"))
        ema50 = self._float(market_item.get("ema50"))
        ema200 = self._float(market_item.get("ema200"))
        fibonacci = market_item.get("fibonacci") if isinstance(market_item.get("fibonacci"), dict) else {}
        fib_618 = self._float(fibonacci.get("0.618"))

        support_distance = abs(current_price - support) / max(current_price, 1e-9) if support > 0 else 1.0
        resistance_distance = abs(resistance - current_price) / max(current_price, 1e-9) if resistance > 0 else 1.0
        width_ratio = (resistance - support) / max(current_price, 1e-9) if resistance > support > 0 else 0.0
        atr_ratio = atr_value / max(current_price, 1e-9)
        volume_ratio = volume / max(average_volume, 1e-9) if average_volume > 0 else 0.0
        bb_width_ratio = ((boll_upper - boll_lower) / max(current_price, 1e-9)) if boll_upper > boll_lower > 0 else 0.0

        breakout_up = bool(current_price > resistance and resistance > 0) or bool(daily_change >= 2.2 and resistance_distance <= 0.02)
        breakout_down = bool(current_price < support and support > 0) or bool(daily_change <= -2.2 and support_distance <= 0.02)
        squeeze = (bb_width_ratio > 0 and bb_width_ratio <= 0.03) or (atr_ratio <= 0.015) or (volatility_pct > 0 and volatility_pct <= 0.15)
        volume_expansion = relative_volume >= 1.15 or volume_ratio >= 1.2

        return {
            "trend": trend,
            "trend_strength": trend_strength,
            "current_price": current_price,
            "support": support,
            "resistance": resistance,
            "atr_ratio": atr_ratio,
            "support_distance": support_distance,
            "resistance_distance": resistance_distance,
            "width_ratio": width_ratio,
            "daily_change": daily_change,
            "momentum_5d": momentum_5d,
            "momentum_20d": momentum_20d,
            "volume_ratio": volume_ratio,
            "relative_volume": relative_volume,
            "volume_expansion": volume_expansion,
            "breakout_up": breakout_up,
            "breakout_down": breakout_down,
            "squeeze": squeeze,
            "bb_width_ratio": bb_width_ratio,
            "ema20": ema20,
            "ema50": ema50,
            "ema200": ema200,
            "ema_bull": ema20 > ema50 > ema200 > 0,
            "ema_bear": ema20 < ema50 < ema200 and ema20 > 0,
            "rsi14": rsi14,
            "macd_state": macd_state,
            "fib_618": fib_618,
        }

    def _detect_chart_formations(self, feature: dict[str, Any]) -> list[dict[str, Any]]:
        formations: list[dict[str, Any]] = []

        def add(name: str, confidence: float, reason: str) -> None:
            if confidence <= 0:
                return
            formations.append(
                {
                    "name": name,
                    "confidence": round(max(0.0, min(100.0, confidence)), 1),
                    "reason": reason,
                }
            )

        up = bool(feature["breakout_up"])
        down = bool(feature["breakout_down"])
        squeeze = bool(feature["squeeze"])
        ema_bull = bool(feature["ema_bull"])
        ema_bear = bool(feature["ema_bear"])
        vol_up = bool(feature["volume_expansion"])
        near_support = feature["support_distance"] <= 0.02
        near_resistance = feature["resistance_distance"] <= 0.02
        narrow = 0 < feature["width_ratio"] <= 0.06

        if up and ema_bull:
            add("Resistance Break", 82 + (8 if vol_up else 0), "Direnc kirildi")
        if down and ema_bear:
            add("Support Break", 82 + (8 if vol_up else 0), "Destek kirildi")
        if up and vol_up and squeeze:
            add("Bollinger Squeeze Breakout", 86, "Sikisma sonrasi hacimli kirilim")
            add("Volatility Squeeze", 78, "Daralan bant cikisla sonlandi")
        if squeeze and feature["bb_width_ratio"] > 0:
            add("Pennant", 64 + (8 if vol_up else 0), "Daralan fiyat salinimi")

        if ema_bull and near_support and feature["momentum_20d"] >= 0:
            add("Cup and Handle", 73 + (7 if vol_up else 0), "Destekten kulp benzeri toparlanma")
            add("Double Bottom (W)", 70 + (6 if vol_up else 0), "W benzeri dipten donus")
            add("Inverse Head and Shoulders", 66 + (8 if vol_up else 0), "Boyun cizgisi ustunde tutunma")
            add("Falling Wedge", 69 + (7 if up else 0), "Dusen takoz yukari kirilim adayi")

        if ema_bear and near_resistance and feature["momentum_20d"] <= 0:
            add("Double Top (M)", 70 + (6 if vol_up else 0), "M benzeri tepe yorulmasi")
            add("Head and Shoulders", 66 + (8 if vol_up else 0), "Boyun cizgisi asagi kirilim adayi")
            add("Rising Wedge", 69 + (7 if down else 0), "Yukselen takoz asagi kirilim adayi")

        if narrow and ema_bull:
            add("Ascending Triangle", 68 + (8 if up else 0), "Yukselen dipler ve yatay direnc")
            add("Bull Flag", 67 + (6 if vol_up else 0), "Trend icinde bayrak konsolidasyonu")
            add("Rectangle", 62 + (6 if vol_up else 0), "Yatay bant birikimi")
            add("Channel Breakout", 70 + (7 if up else 0), "Kanal ustu kirilim")
        if narrow and ema_bear:
            add("Descending Triangle", 68 + (8 if down else 0), "Dusen tepeler ve yatay destek")
            add("Bear Flag", 67 + (6 if vol_up else 0), "Trend icinde ayi bayragi")
            add("Rectangle", 62 + (6 if vol_up else 0), "Yatay bant dagilimi")
            add("Channel Breakout", 70 + (7 if down else 0), "Kanal alti kirilim")

        if narrow and not ema_bull and not ema_bear:
            add("Symmetrical Triangle", 64 + (8 if vol_up else 0), "Simetrik daralma")
        if up and feature["daily_change"] >= 1.5:
            add("Gap Breakout", 62 + (10 if vol_up else 0), "Bosluk sonrası hizli devam")
            add("Pivot Breakout", 65 + (8 if vol_up else 0), "Pivot seviyesi asildi")
            add("Trendline Break", 68, "Trend cizgisi yukari kirildi")
        if down and feature["daily_change"] <= -1.5:
            add("Trendline Break", 68, "Trend cizgisi asagi kirildi")

        formations.sort(key=lambda item: float(item["confidence"]), reverse=True)
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in formations:
            name = str(item.get("name") or "")
            if not name or name in seen:
                continue
            seen.add(name)
            unique.append(item)
        return unique[:8]

    def _detect_market_structure(self, feature: dict[str, Any]) -> list[str]:
        signals: list[str] = []
        if feature["trend"] == "Bullish":
            signals.extend(["Higher High", "Higher Low"])
            if feature["breakout_up"]:
                signals.append("Break of Structure")
                signals.append("Resistance Kirilimi")
        elif feature["trend"] == "Bearish":
            signals.extend(["Lower High", "Lower Low"])
            if feature["breakout_down"]:
                signals.append("Break of Structure")
                signals.append("Support Break")
        else:
            signals.append("Trend Channel")

        if feature["support_distance"] <= 0.02:
            signals.append("Destekten Tepki")
            signals.append("Swing Low")
            signals.append("Retest")
        if feature["resistance_distance"] <= 0.02:
            signals.append("Swing High")

        if feature["breakout_up"] and feature["volume_expansion"]:
            signals.append("Market Structure Shift")
        if feature["breakout_down"] and feature["volume_expansion"]:
            signals.append("Liquidity Sweep")
            signals.append("False Breakout")

        unique: list[str] = []
        seen: set[str] = set()
        for item in signals:
            if item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return unique[:8]

    def _indicator_confirmations(self, feature: dict[str, Any]) -> list[str]:
        confirmations: list[str] = []
        if feature["ema_bull"]:
            confirmations.append("EMA20 EMA50 uzerinde")
        elif feature["ema_bear"]:
            confirmations.append("EMA20 EMA50 altinda")
        if feature["macd_state"] == "Bullish":
            confirmations.append("MACD pozitif kesisim")
        elif feature["macd_state"] == "Bearish":
            confirmations.append("MACD negatif kesisim")
        if 45.0 <= float(feature["rsi14"]) <= 68.0:
            confirmations.append("RSI dengeli")
        if feature["volume_expansion"]:
            confirmations.append("Hacim artisi teyidi")
        return confirmations[:5]

    def _price_plan(self, *, current_price: float, support: float, resistance: float, atr_value: float, trend_strength: int) -> tuple[float, float, float, float, list[str]]:
        price_buffer = max(current_price * 0.0015, atr_value * 0.05, 0.01)
        pullback_buffer = max(current_price * 0.003, atr_value * 0.08)
        breakout_anchor = current_price - price_buffer
        pullback_anchor = min(current_price - pullback_buffer, support + max(atr_value * 0.12, current_price * 0.002))

        entry_price = min(breakout_anchor, pullback_anchor)
        if entry_price <= 0:
            entry_price = max(0.01, current_price - price_buffer)
        if entry_price > current_price:
            entry_price = current_price - price_buffer
        if support > 0 and entry_price < support:
            entry_price = min(current_price - price_buffer, support + max(atr_value * 0.08, current_price * 0.0015))
        if entry_price <= 0 or entry_price >= current_price:
            entry_price = max(0.01, current_price - price_buffer)

        stop_loss = min(support - max((atr_value * 0.35), (entry_price * 0.003)), entry_price - (atr_value * 1.35))
        if stop_loss >= entry_price:
            stop_loss = entry_price - max(atr_value * 0.5, entry_price * 0.01)

        risk_amount = max(0.01, entry_price - stop_loss)
        strength_factor = 1.0 + max(0.0, min(1.0, trend_strength / 100.0))
        current_target = max(resistance, entry_price + (risk_amount * strength_factor))
        rr_ratio = (current_target - entry_price) / risk_amount if risk_amount > 0 else 0.0
        notes = [
            f"Entry current_price - buffer={price_buffer:.4f}",
            f"Pullback cap={pullback_anchor:.4f}",
            f"Entry finalized at {entry_price:.4f}",
            f"Stop placed below support and ATR={stop_loss:.4f}",
        ]
        return entry_price, stop_loss, current_target, max(0.0, rr_ratio), notes

    def _reasons(
        self,
        *,
        market_item: dict[str, Any],
        trend: str,
        trend_strength: int,
        relative_volume: float,
        rsi14: float,
        macd_state: str,
        news_sentiment: str,
        news_reasons: list[str],
        graph_analysis: dict[str, Any],
    ) -> list[str]:
        reasons = [str(reason) for reason in market_item.get("reasons", []) if str(reason).strip()]
        formations = list(graph_analysis.get("formations") or [])
        if formations:
            top = formations[0]
            reasons.append(f"Formasyon: {top.get('name')} ({int(round(float(top.get('confidence') or 0.0)))}%)")
            reasons.append(str(top.get("reason") or "Grafik yapisi olumlu"))
        for structure_signal in list(graph_analysis.get("market_structure") or [])[:3]:
            reasons.append(f"Price Action: {structure_signal}")
        for confirmation in list(graph_analysis.get("indicator_confirmations") or [])[:2]:
            reasons.append(confirmation)

        if trend == "Bullish":
            reasons.append("Trend guclu")
        elif trend == "Neutral":
            reasons.append("Trend dengeli")
        else:
            reasons.append("Trend zayif")
        if trend_strength >= 70:
            reasons.append(f"Trend gucu {trend_strength}/100")
        if relative_volume >= 1.2:
            reasons.append("Hacim patlamasi destekliyor")
        elif relative_volume >= 1.0:
            reasons.append("Hacim normal ustu")
        if 45.0 <= rsi14 <= 68.0:
            reasons.append("Momentum dengeli")
        if macd_state == "Bullish":
            reasons.append("MACD pozitif")
        if news_sentiment == "Positive":
            reasons.append("Haber akisi olumlu")
        elif news_sentiment == "Negative":
            reasons.append("Haber akisi baski yaratiyor")
        reasons.extend(news_reasons[:3])

        unique: list[str] = []
        seen: set[str] = set()
        for reason in reasons:
            cleaned = str(reason).strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            unique.append(cleaned)
        return unique

    def _label(self, total_score: float) -> str:
        if total_score >= 80:
            return "Elite"
        if total_score >= 65:
            return "Strong"
        if total_score >= 50:
            return "Watch"
        return "Speculative"

    def _merge_config(self, config: dict[str, Any] | None) -> dict[str, Any]:
        merged = self._deep_copy(DEFAULT_BIST_SCORING_CONFIG)
        if isinstance(config, dict):
            for key, value in config.items():
                if isinstance(value, dict) and isinstance(merged.get(key), dict):
                    merged[key].update(value)
                else:
                    merged[key] = value
        return merged

    def _thresholds(self) -> dict[str, Any]:
        return dict(self._config.get("thresholds") or {})

    def _hard_filter_config(self) -> dict[str, Any]:
        return dict(self._config.get("hard_filters") or {})

    def _cap(self, score: float, component: str) -> float:
        weights = dict(self._config.get("weights") or {})
        caps = {
            "graph_structure": float(weights.get("graph_structure", 45.0)),
            "trend": float(weights.get("trend", 20.0)),
            "volume": float(weights.get("volume", 15.0)),
            "momentum": float(weights.get("momentum", 10.0)),
            "news": float(weights.get("news", 5.0)),
            "ai_confidence": float(weights.get("ai_confidence", 5.0)),
        }
        return max(0.0, min(caps.get(component, 100.0), float(score)))

    def _deep_copy(self, payload: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, dict):
                result[key] = self._deep_copy(value)
            elif isinstance(value, list):
                result[key] = list(value)
            else:
                result[key] = value
        return result

    def _float(self, value: Any) -> float:
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    def _int(self, value: Any) -> int:
        try:
            return int(float(value or 0.0))
        except (TypeError, ValueError):
            return 0
