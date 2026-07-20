"""BIST graph-first scoring and opportunity selection helpers."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any


DEFAULT_BIST_SCORING_CONFIG: dict[str, Any] = {
    "top_n": 20,
    "final_n": 10,
    "weights": {
        "graph_structure": 50,
        "trend": 22,
        "volume": 12,
        "momentum": 10,
        "news": 4,
        "ai_confidence": 2,
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
    "macro": {
        "enabled": True,
        "min_multiplier": 0.84,
        "max_multiplier": 1.12,
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
    fresh_signals: list[str] = field(default_factory=list)
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
    take_profit_4: float = 0.0
    take_profit_levels: list[dict[str, Any]] = field(default_factory=list)
    risk_reward_by_tp: list[dict[str, Any]] = field(default_factory=list)
    entry_strategy: str = "Unknown"
    entry_strategy_reason: str = ""
    entry_status: str = "WAIT"
    limit_entry_price: float = 0.0
    market_entry_allowed: bool = False
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
    macro_multiplier: float = 1.0
    macro_notes: list[str] = field(default_factory=list)
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
        macd_value = self._float(market_item.get("macd_value"))
        macd_signal = self._float(market_item.get("macd_signal"))
        adx_value = self._float(market_item.get("adx"))
        bollinger_upper = self._float(market_item.get("bollinger_upper"))
        bollinger_lower = self._float(market_item.get("bollinger_lower"))
        momentum_5d = self._float(market_item.get("momentum_5d"))
        momentum_20d = self._float(market_item.get("momentum_20d"))
        daily_change_pct = self._float(market_item.get("daily_change_pct"))
        volatility_pct = self._float(market_item.get("volatility_pct"))
        fibonacci = market_item.get("fibonacci") if isinstance(market_item.get("fibonacci"), dict) else {}
        candle_count = self._candle_count(market_item)

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
            macd_value=macd_value,
            macd_signal=macd_signal,
            adx_value=adx_value,
            bollinger_upper=bollinger_upper,
            bollinger_lower=bollinger_lower,
            momentum_5d=momentum_5d,
            momentum_20d=momentum_20d,
            daily_change_pct=daily_change_pct,
            volatility_pct=volatility_pct,
        )
        top_formation_confidence = 0.0
        if graph_analysis["formations"]:
            top_formation_confidence = float(graph_analysis["formations"][0].get("confidence") or 0.0)
        entry_price, stop_loss, price_plan_notes = self._price_plan(
            current_price=current_price,
            support=support,
            resistance=resistance,
            atr_value=atr_value,
            breakout_up=bool(graph_analysis.get("breakout_up")),
        )
        graph_score = float(graph_analysis.get("score") or 0.0)
        preliminary_quality = (graph_score * 0.6) + (max(0.0, min(100.0, technical_score)) * 0.25) + (max(0.0, min(100.0, trend_strength)) * 0.15)
        trade_plan = self._build_trade_plan(
            market_item=market_item,
            graph_analysis=graph_analysis,
            current_price=current_price,
            entry_price=entry_price,
            stop_loss=stop_loss,
            support=support,
            resistance=resistance,
            trend=trend,
            trend_strength=trend_strength,
            daily_change_pct=daily_change_pct,
            news_sentiment=news_sentiment,
            news_reasons=news_reasons or [],
            quality_score=preliminary_quality,
            formation_confidence=top_formation_confidence,
            fib_236=self._float(fibonacci.get("0.236")),
            fib_382=self._float(fibonacci.get("0.382")),
            fib_618=self._float(fibonacci.get("0.618")),
            momentum_20d=momentum_20d,
            volatility_pct=volatility_pct,
            candle_count=candle_count,
        )
        price_plan_notes.extend([str(note) for note in trade_plan.get("plan_notes") or []])

        no_news_signal = self._is_news_signal_missing(
            news_score=news_score,
            news_sentiment=news_sentiment,
            news_reasons=news_reasons or [],
        )
        has_gap_signal = bool(market_item.get("gap_up") or market_item.get("gap_down"))

        entry_range_low = float(trade_plan.get("entry_range_low") or 0.0)
        entry_range_high = float(trade_plan.get("entry_range_high") or 0.0)
        take_profit_1 = float(trade_plan.get("take_profit_1") or 0.0)
        take_profit_2 = float(trade_plan.get("take_profit_2") or 0.0)
        take_profit_3 = float(trade_plan.get("take_profit_3") or 0.0)
        take_profit_4 = float(trade_plan.get("take_profit_4") or 0.0)
        current_target = float(trade_plan.get("current_target") or 0.0)
        rr_ratio = float(trade_plan.get("risk_reward_ratio") or 0.0)

        raw_components = {
            "graph_structure": graph_score,
            "trend": self._trend_score(trend=trend, trend_strength=trend_strength, market_item=market_item),
            "volume": self._volume_score(
                volume=volume,
                average_volume=average_volume,
                relative_volume=relative_volume,
                chart_score=graph_score,
            ),
            "momentum": self._momentum_score(
                technical_score=technical_score,
                rsi14=rsi14,
                macd_state=macd_state,
                market_item=market_item,
                graph_score=graph_score,
            ),
            "news": self._news_score(news_score=news_score, news_sentiment=news_sentiment),
            "ai_confidence": self._ai_confidence_score(news_confidence=news_confidence),
        }
        component_scores = self._weighted_component_scores(raw_components)

        if no_news_signal and not has_gap_signal:
            # If there is no actionable news/gap signal, bias scoring toward chart structure.
            transferable = float(component_scores.get("news", 0.0)) + float(component_scores.get("ai_confidence", 0.0))
            component_scores["news"] = 0.0
            component_scores["ai_confidence"] = 0.0
            component_scores["graph_structure"] = self._cap(float(component_scores.get("graph_structure", 0.0)) + (transferable * 0.58), "graph_structure")
            component_scores["trend"] = self._cap(float(component_scores.get("trend", 0.0)) + (transferable * 0.24), "trend")
            component_scores["momentum"] = self._cap(float(component_scores.get("momentum", 0.0)) + (transferable * 0.18), "momentum")

        macro_multiplier, macro_notes = self._macro_adjustment(
            market_item=market_item,
            news_reasons=news_reasons or [],
            news_sentiment=news_sentiment,
        )
        total_score = round(sum(component_scores.values()) * macro_multiplier, 2)

        score_lines = [
            f"Grafik +{component_scores['graph_structure']:.0f}",
            f"Trend +{component_scores['trend']:.0f}",
            f"Hacim +{component_scores['volume']:.0f}",
            f"Momentum +{component_scores['momentum']:.0f}",
            f"News +{component_scores['news']:.0f}",
            f"AI +{component_scores['ai_confidence']:.0f}",
            f"Makro x{macro_multiplier:.2f}",
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
            no_news_signal=no_news_signal,
            has_gap_signal=has_gap_signal,
            macro_notes=macro_notes,
        )

        score_label = self._label(total_score)
        decision = str(trade_plan.get("decision") or "WAIT")

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
            fresh_signals=list(graph_analysis["fresh_signals"]),
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
            take_profit_4=take_profit_4,
            take_profit_levels=list(trade_plan.get("take_profit_levels") or []),
            risk_reward_by_tp=list(trade_plan.get("risk_reward_by_tp") or []),
            entry_strategy=str(trade_plan.get("entry_strategy") or "Unknown"),
            entry_strategy_reason=str(trade_plan.get("entry_strategy_reason") or ""),
            entry_status=str(trade_plan.get("entry_status") or "WAIT"),
            limit_entry_price=round(float(trade_plan.get("limit_entry_price") or entry_price), 4),
            market_entry_allowed=bool(trade_plan.get("market_entry_allowed")),
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
            macro_multiplier=round(macro_multiplier, 4),
            macro_notes=list(macro_notes),
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
        macd_value: float,
        macd_signal: float,
        adx_value: float,
        bollinger_upper: float,
        bollinger_lower: float,
        momentum_5d: float,
        momentum_20d: float,
        daily_change_pct: float,
        volatility_pct: float,
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
            macd_value=macd_value,
            macd_signal=macd_signal,
            adx_value=adx_value,
            bollinger_upper=bollinger_upper,
            bollinger_lower=bollinger_lower,
            momentum_5d=momentum_5d,
            momentum_20d=momentum_20d,
            daily_change_pct=daily_change_pct,
            volatility_pct=volatility_pct,
        )
        formations = self._detect_chart_formations(feature)
        market_structure = self._detect_market_structure(feature, market_item=market_item)
        indicator_confirmations = self._indicator_confirmations(feature, market_item=market_item)
        fresh_signals = list(feature.get("fresh_signals") or [])
        multi_tf = self._multi_timeframe_context(market_item=market_item, feature=feature)
        category_signals = self._mandatory_category_signals(
            market_item=market_item,
            feature=feature,
            formations=formations,
            market_structure=market_structure,
            indicator_confirmations=indicator_confirmations,
        )
        fresh_signals.extend(category_signals)
        fresh_signals.extend(list(multi_tf.get("signals") or []))

        formation_score = 0.0
        if formations:
            strongest = float(formations[0].get("confidence") or 0.0)
            average_top = sum(float(item.get("confidence") or 0.0) for item in formations[:3]) / max(1, min(3, len(formations)))
            formation_score = (strongest * 0.65) + (average_top * 0.35)

        structure_score = 0.0
        if market_structure:
            structure_score = min(100.0, 38.0 + (len(market_structure) * 7.0))
        if feature["breakout_up"] or feature["breakout_down"]:
            structure_score += 8.0
        if feature["bounce_from_support"]:
            structure_score += 6.0

        confirmation_score = 0.0
        if indicator_confirmations:
            confirmation_score = min(100.0, 25.0 + (len(indicator_confirmations) * 10.0))
        if feature["volume_expansion"]:
            confirmation_score += 10.0

        freshness_score = min(100.0, len(fresh_signals) * 12.5)

        score = (formation_score * 0.55) + (structure_score * 0.2) + (confirmation_score * 0.1) + (freshness_score * 0.15)
        score += float(multi_tf.get("score_adjustment") or 0.0)
        if not formations and not fresh_signals:
            score *= 0.55
        if feature["breakout_down"] and feature["trend"] != "Bullish":
            score -= 12.0
        score = max(0.0, min(100.0, score))
        return {
            "score": score,
            "formations": formations,
            "market_structure": market_structure,
            "indicator_confirmations": indicator_confirmations,
            "fresh_signals": fresh_signals,
            "multi_timeframe": multi_tf,
            "breakout_up": bool(feature["breakout_up"]),
            "breakout_down": bool(feature["breakout_down"]),
        }

    def _multi_timeframe_context(self, *, market_item: dict[str, Any], feature: dict[str, Any]) -> dict[str, Any]:
        trend_1h = str(market_item.get("trend_1h") or feature.get("trend") or "Neutral")
        trend_1d = str(market_item.get("trend_1d") or feature.get("trend") or "Neutral")
        strength_1h = self._int(market_item.get("trend_strength_1h") or feature.get("trend_strength") or 0)
        strength_1d = self._int(market_item.get("trend_strength_1d") or feature.get("trend_strength") or 0)

        aligned = trend_1h == trend_1d and trend_1h in {"Bullish", "Bearish"}
        conflict = trend_1h != trend_1d and trend_1h in {"Bullish", "Bearish"} and trend_1d in {"Bullish", "Bearish"}

        score_adjustment = 0.0
        signals: list[str] = []
        if aligned:
            score_adjustment += 6.0
            signals.append(f"MTF uyumlu trend ({trend_1h})")
        if conflict:
            score_adjustment -= 8.0
            signals.append(f"MTF trend catismasi ({trend_1h}/{trend_1d})")
        if strength_1h >= 60 and strength_1d >= 60:
            score_adjustment += 2.5
            signals.append("Saatlik ve gunluk trend gucu yuksek")

        return {
            "trend_1h": trend_1h,
            "trend_1d": trend_1d,
            "trend_strength_1h": strength_1h,
            "trend_strength_1d": strength_1d,
            "aligned": aligned,
            "conflict": conflict,
            "score_adjustment": score_adjustment,
            "signals": signals,
        }

    def _mandatory_category_signals(
        self,
        *,
        market_item: dict[str, Any],
        feature: dict[str, Any],
        formations: list[dict[str, Any]],
        market_structure: list[str],
        indicator_confirmations: list[str],
    ) -> list[str]:
        signals: list[str] = []
        candles = self._extract_candles(market_item)
        levels = self._compute_levels(
            candles=candles,
            current_price=float(feature.get("current_price") or 0.0),
            support=float(feature.get("support") or 0.0),
            resistance=float(feature.get("resistance") or 0.0),
        )

        if formations:
            signals.append("Kategori-1 Formasyonlar: aktif")
        if any(token in market_structure for token in ["Break of Structure", "Retest", "False Breakout"]):
            signals.append("Kategori-2 Kirilim/Retest/Fake: teyitli")
        if any(token in market_structure for token in ["Higher High", "Higher Low", "Lower Low", "Lower High"]):
            signals.append("Kategori-3 Market Structure HH/HL-LH/LL")
        if any("RSI" in item or "MACD" in item for item in indicator_confirmations):
            signals.append("Kategori-4 Candle+Price Action: momentum teyidi")
        if any(item.startswith("Mum:") for item in indicator_confirmations):
            signals.append("Kategori-5 Mum formasyonlari algilandi")
        if levels.get("support_levels") or levels.get("resistance_levels"):
            signals.append("Kategori-6 Destek/Direnc katmanlari olustu")

        ema20 = float(feature.get("ema20") or 0.0)
        ema50 = float(feature.get("ema50") or 0.0)
        ema200 = float(feature.get("ema200") or 0.0)
        if ema20 > 0 and ema50 > 0 and ema200 > 0:
            signals.append("Kategori-7 MA trend hiyerarsisi mevcut")
        if any(token.startswith("MA:") for token in indicator_confirmations):
            signals.append("Kategori-8 MA cross/compression/expansion teyidi")

        fib_618 = float(feature.get("fib_618") or 0.0)
        if fib_618 > 0:
            signals.append("Kategori-9 Fibonacci retracement/extension uyumu")
        if float(feature.get("relative_volume") or 0.0) >= 1.1:
            signals.append("Kategori-10 Hacim Profili/OBV-CMF benzeri hacim teyidi")
        if any(token.startswith("Volume:") for token in indicator_confirmations):
            signals.append("Kategori-10 Hacim akis sinyali mevcut")

        adx = float(feature.get("adx") or 0.0)
        atr_ratio = float(feature.get("atr_ratio") or 0.0)
        bb_ratio = float(feature.get("bb_width_ratio") or 0.0)
        if adx > 20 or atr_ratio > 0 or bb_ratio > 0:
            signals.append("Kategori-11 ADX-ATR-BB-Keltner-SuperTrend kosullari izlendi")
        if any(token.startswith("Trend:") for token in indicator_confirmations):
            signals.append("Kategori-11 Trend gucu/DMI benzeri teyit")

        if candles:
            closes = [row[3] for row in candles[-20:]]
            if len(closes) >= 5:
                if closes[-1] > max(closes[-5:-1]):
                    signals.append("Kategori-2 Multi-timeframe saatlik breakout")
                if closes[-1] >= closes[0]:
                    signals.append("Kategori-3 Gunluk trend devami")

        return signals[:8]

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

    def _is_news_signal_missing(
        self,
        *,
        news_score: float,
        news_sentiment: str,
        news_reasons: list[str],
    ) -> bool:
        if news_sentiment in {"Positive", "Negative"}:
            return False
        if any(str(reason).strip() for reason in news_reasons):
            return False
        return 46.0 <= max(0.0, min(100.0, float(news_score))) <= 54.0

    def _macro_adjustment(
        self,
        *,
        market_item: dict[str, Any],
        news_reasons: list[str],
        news_sentiment: str,
    ) -> tuple[float, list[str]]:
        macro_cfg = dict(self._config.get("macro") or {})
        if not bool(macro_cfg.get("enabled", True)):
            return 1.0, []

        min_multiplier = max(0.7, float(macro_cfg.get("min_multiplier", 0.84)))
        max_multiplier = min(1.3, float(macro_cfg.get("max_multiplier", 1.12)))
        multiplier = 1.0
        notes: list[str] = []

        raw_macro_score = market_item.get("macro_impact_score")
        try:
            macro_score = float(raw_macro_score)
            macro_score = max(0.0, min(100.0, macro_score))
            drift = (macro_score - 50.0) / 250.0
            multiplier += drift
            notes.append(f"Makro skor {macro_score:.0f}/100")
        except (TypeError, ValueError):
            macro_score = None

        volatility_pct = self._float(market_item.get("volatility_pct"))
        if volatility_pct >= 0.03:
            multiplier -= min(0.07, volatility_pct * 0.9)
            notes.append("Yuksek piyasa volatilitesi")

        lowered_reasons = [str(item).lower() for item in news_reasons]
        negative_tokens = [
            "fed faiz art",
            "tcmb faiz art",
            "merkez bankasi faiz art",
            "siki para",
            "enflasyon yuksek",
        ]
        positive_tokens = [
            "fed faiz indir",
            "tcmb faiz indir",
            "merkez bankasi faiz indir",
            "enflasyon dusus",
            "tesvik",
            "likidite",
        ]

        negative_hits = sum(1 for token in negative_tokens if any(token in reason for reason in lowered_reasons))
        positive_hits = sum(1 for token in positive_tokens if any(token in reason for reason in lowered_reasons))

        if negative_hits:
            multiplier -= min(0.1, 0.025 * negative_hits)
            notes.append("Sikilasici makro sinyal")
        if positive_hits:
            multiplier += min(0.08, 0.02 * positive_hits)
            notes.append("Destekleyici makro sinyal")

        if news_sentiment == "Negative":
            multiplier -= 0.01
        elif news_sentiment == "Positive":
            multiplier += 0.01

        multiplier = max(min_multiplier, min(max_multiplier, multiplier))
        return multiplier, notes[:3]

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
        macd_value: float,
        macd_signal: float,
        adx_value: float,
        bollinger_upper: float,
        bollinger_lower: float,
        momentum_5d: float,
        momentum_20d: float,
        daily_change_pct: float,
        volatility_pct: float,
    ) -> dict[str, Any]:
        boll_upper = bollinger_upper
        boll_lower = bollinger_lower
        ema20 = self._float(market_item.get("ema20"))
        ema50 = self._float(market_item.get("ema50"))
        ema200 = self._float(market_item.get("ema200"))
        fibonacci = market_item.get("fibonacci") if isinstance(market_item.get("fibonacci"), dict) else {}
        fib_618 = self._float(fibonacci.get("0.618"))
        candle_count = self._candle_count(market_item)

        support_distance = abs(current_price - support) / max(current_price, 1e-9) if support > 0 else 1.0
        resistance_distance = abs(resistance - current_price) / max(current_price, 1e-9) if resistance > 0 else 1.0
        width_ratio = (resistance - support) / max(current_price, 1e-9) if resistance > support > 0 else 0.0
        atr_ratio = atr_value / max(current_price, 1e-9)
        volume_ratio = volume / max(average_volume, 1e-9) if average_volume > 0 else 0.0
        bb_width_ratio = ((boll_upper - boll_lower) / max(current_price, 1e-9)) if boll_upper > boll_lower > 0 else 0.0

        breakout_up = bool(current_price > resistance and resistance > 0) or bool(daily_change_pct >= 1.8 and resistance_distance <= 0.01)
        breakout_down = bool(current_price < support and support > 0) or bool(daily_change_pct <= -1.8 and support_distance <= 0.01)
        squeeze = (bb_width_ratio > 0 and bb_width_ratio <= 0.025) or (atr_ratio <= 0.0125) or (volatility_pct > 0 and volatility_pct <= 0.12)
        volume_expansion = relative_volume >= 1.2 or volume_ratio >= 1.25

        near_cross_ema = abs(ema20 - ema50) / max(current_price, 1e-9) <= 0.0035 if ema20 > 0 and ema50 > 0 else False
        macd_diff = macd_value - macd_signal
        near_cross_macd = abs(macd_diff) <= 0.015 * max(1.0, abs(macd_signal), abs(macd_value), 1.0)
        bounce_from_support = support_distance <= 0.012 and daily_change_pct > 0
        breakout_resistance_fresh = breakout_up and resistance_distance <= 0.008
        breakout_support_fresh = breakout_down and support_distance <= 0.008
        trend_shift_up = trend == "Bullish" and momentum_20d > 0 and -0.12 <= momentum_5d <= 0.45 and near_cross_ema
        trend_shift_down = trend == "Bearish" and momentum_20d < 0 and -0.45 <= momentum_5d <= 0.12 and near_cross_ema
        squeeze_breakout_fresh = squeeze and (breakout_up or breakout_down) and volume_expansion

        fresh_signals: list[str] = []
        if breakout_resistance_fresh:
            fresh_signals.append("Yeni breakout")
            fresh_signals.append("Yeni direnc kirilimi")
        if breakout_support_fresh:
            fresh_signals.append("Yeni support break")
        if near_cross_ema and ema20 > ema50:
            fresh_signals.append("Yeni EMA kesisimi")
        if near_cross_macd and macd_diff > 0:
            fresh_signals.append("Yeni MACD kesisimi")
        if relative_volume >= 1.35:
            fresh_signals.append("Yeni hacim patlamasi")
        if bounce_from_support:
            fresh_signals.append("Yeni destekten donus")
        if squeeze_breakout_fresh:
            fresh_signals.append("Yeni Bollinger sikisma kirilimi")
        if trend_shift_up or trend_shift_down:
            fresh_signals.append("Yeni trend donusu")
        if breakout_up or breakout_down:
            fresh_signals.append("Yeni BOS")
            fresh_signals.append("Yeni Market Structure Shift")

        unique_fresh: list[str] = []
        seen_fresh: set[str] = set()
        for value in fresh_signals:
            if value in seen_fresh:
                continue
            seen_fresh.add(value)
            unique_fresh.append(value)

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
            "daily_change": daily_change_pct,
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
            "adx": adx_value,
            "macd_value": macd_value,
            "macd_signal": macd_signal,
            "macd_diff": macd_diff,
            "near_cross_ema": near_cross_ema,
            "near_cross_macd": near_cross_macd,
            "trend_shift_up": trend_shift_up,
            "trend_shift_down": trend_shift_down,
            "bounce_from_support": bounce_from_support,
            "fresh_signals": unique_fresh,
            "candle_count": candle_count,
            "macd_state": macd_state,
            "fib_618": fib_618,
        }

    def _detect_chart_formations(self, feature: dict[str, Any]) -> list[dict[str, Any]]:
        if self._int(feature.get("candle_count")) < 250:
            return []

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

        if up and ema_bull and vol_up and feature["daily_change"] >= 1.6 and feature["resistance_distance"] <= 0.01:
            confidence = 58.0 + min(20.0, feature["relative_volume"] * 8.0) + min(10.0, feature["daily_change"] * 2.0)
            add("Resistance Break", confidence, "Direnc ustu kapanis ve hacim teyidi")

        if down and ema_bear and vol_up and feature["daily_change"] <= -1.6 and feature["support_distance"] <= 0.01:
            confidence = 58.0 + min(20.0, feature["relative_volume"] * 8.0) + min(10.0, abs(feature["daily_change"]) * 2.0)
            add("Support Break", confidence, "Destek alti kapanis ve hacim teyidi")

        if squeeze and (up or down) and vol_up:
            confidence = 62.0 + min(18.0, feature["relative_volume"] * 7.0) + (8.0 if up else 4.0)
            add("Bollinger Squeeze Breakout", confidence, "Sikisma sonrasi yonlu kirilim")
            add("Volatility Squeeze", confidence - 8.0, "Daralan volatilite cikis sinyali")

        if narrow and vol_up and feature["momentum_5d"] * feature["momentum_20d"] > 0:
            confidence = 54.0 + min(16.0, abs(feature["momentum_20d"]) * 11.0) + min(10.0, feature["relative_volume"] * 4.0)
            add("Pennant", confidence, "Daralan fiyat ve hizlanan hacim")

        if ema_bull and near_support and feature["momentum_20d"] > 0 and feature["trend_shift_up"]:
            confidence = 55.0 + min(16.0, feature["trend_strength"] / 5.0) + min(10.0, feature["relative_volume"] * 4.0)
            add("Cup and Handle", confidence, "Destekten toparlanma ve trend devami")
            add("Double Bottom (W)", confidence - 5.0, "Destekte cift dipten donus")
            add("Inverse Head and Shoulders", confidence - 8.0, "Boyun cizgisi ustunde kuvvet")
            if up:
                add("Falling Wedge", confidence - 4.0, "Dusen takoz yukari kirilim")

        if ema_bear and near_resistance and feature["momentum_20d"] < 0 and feature["trend_shift_down"]:
            confidence = 55.0 + min(16.0, feature["trend_strength"] / 5.0) + min(10.0, feature["relative_volume"] * 4.0)
            add("Double Top (M)", confidence - 5.0, "Direncte cift tepe zayiflamasi")
            add("Head and Shoulders", confidence - 8.0, "Boyun cizgisi alti zayiflik")
            if down:
                add("Rising Wedge", confidence - 4.0, "Yukselen takoz asagi kirilim")

        if narrow and ema_bull and feature["momentum_20d"] > 0 and feature["support_distance"] <= 0.04:
            confidence = 52.0 + min(16.0, feature["trend_strength"] / 6.0)
            add("Ascending Triangle", confidence + (7.0 if up else 0.0), "Yukselen diplerle sikisan fiyat")
            if up and vol_up:
                add("Bull Flag", confidence + 4.0, "Trend icinde bayrak kirilimi")
                add("Channel Breakout", confidence + 6.0, "Kanal ustu hacimli kirilim")

        if narrow and ema_bear and feature["momentum_20d"] < 0 and feature["resistance_distance"] <= 0.04:
            confidence = 52.0 + min(16.0, feature["trend_strength"] / 6.0)
            add("Descending Triangle", confidence + (7.0 if down else 0.0), "Dusen tepelerle sikisan fiyat")
            if down and vol_up:
                add("Bear Flag", confidence + 4.0, "Ayi bayragi kirilimi")
                add("Channel Breakout", confidence + 6.0, "Kanal alti hacimli kirilim")

        if narrow and not ema_bull and not ema_bear and abs(feature["momentum_5d"]) <= 0.2:
            confidence = 48.0 + min(12.0, feature["relative_volume"] * 3.5)
            add("Symmetrical Triangle", confidence, "Kararsizlikte simetrik daralma")
            add("Rectangle", confidence - 4.0, "Yatay bant konsolidasyonu")

        if up and feature["daily_change"] >= 2.0 and vol_up:
            confidence = 52.0 + min(20.0, feature["daily_change"] * 2.5)
            add("Gap Breakout", confidence, "Fiyat ivmesi ve hacimle bosluk devam")
            add("Pivot Breakout", confidence - 4.0, "Pivot ustu kapanis")
            add("Trendline Break", confidence - 6.0, "Trend cizgisi asildi")
        if down and feature["daily_change"] <= -2.0 and vol_up:
            confidence = 52.0 + min(20.0, abs(feature["daily_change"]) * 2.5)
            add("Trendline Break", confidence - 6.0, "Trend cizgisi asagi kirildi")

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

    def _detect_market_structure(self, feature: dict[str, Any], *, market_item: dict[str, Any]) -> list[str]:
        signals: list[str] = []
        candles = self._extract_candles(market_item)

        if len(candles) >= 10:
            recent = candles[-10:]
            highs = [row[1] for row in recent]
            lows = [row[2] for row in recent]
            closes = [row[3] for row in recent]

            hh = highs[-1] > max(highs[-4:-1])
            hl = lows[-1] > min(lows[-4:-1])
            ll = lows[-1] < min(lows[-4:-1])
            lh = highs[-1] < max(highs[-4:-1])

            if hh:
                signals.append("Higher High")
            if hl:
                signals.append("Higher Low")
            if ll:
                signals.append("Lower Low")
            if lh:
                signals.append("Lower High")

            prev_high_block = max(highs[:-1])
            prev_low_block = min(lows[:-1])
            if closes[-1] > prev_high_block:
                signals.append("Break of Structure")
                signals.append("Market Structure Shift")
            if closes[-1] < prev_low_block:
                signals.append("Break of Structure")
                signals.append("CHOCH")

            wick_up = highs[-1] - max(closes[-1], recent[-1][0])
            wick_down = min(closes[-1], recent[-1][0]) - lows[-1]
            body = abs(closes[-1] - recent[-1][0])
            if wick_up > body * 1.7 and closes[-1] < prev_high_block:
                signals.append("Liquidity Sweep")
                signals.append("False Breakout")
            if wick_down > body * 1.7 and closes[-1] > prev_low_block:
                signals.append("Liquidity Sweep")

            breakout_reference = max(closes[-5:-2]) if len(closes) >= 5 else closes[-2]
            if closes[-2] > breakout_reference and closes[-1] >= closes[-2] * 0.994:
                signals.append("Retest")

            trendline_slope = (closes[-1] - closes[0]) / max(1.0, len(closes) - 1)
            if trendline_slope > 0 and hh and hl:
                signals.append("Trend Continuation")

            recent_high = max(highs)
            recent_low = min(lows)
            range_mid = (recent_high + recent_low) / 2.0
            if closes[-1] >= range_mid:
                signals.append("Premium")
            else:
                signals.append("Discount")

            eq_high_ref = sum(highs[-4:-1]) / max(1, len(highs[-4:-1]))
            eq_low_ref = sum(lows[-4:-1]) / max(1, len(lows[-4:-1]))
            if abs(highs[-1] - eq_high_ref) / max(feature["current_price"], 1e-9) <= 0.004:
                signals.append("Equal High")
            if abs(lows[-1] - eq_low_ref) / max(feature["current_price"], 1e-9) <= 0.004:
                signals.append("Equal Low")

            if len(candles) >= 6:
                prev = candles[-2]
                if prev[3] < prev[0] and closes[-1] > prev[1]:
                    signals.append("Order Block")
                if prev[3] > prev[0] and closes[-1] < prev[2]:
                    signals.append("Breaker Block")

            fvg = self._fair_value_gap_signal(candles)
            if fvg:
                signals.append(fvg)
                signals.append("Mitigation Block")
        else:
            if feature["trend"] == "Bullish" and feature["breakout_up"]:
                signals.append("Break of Structure")
            elif feature["trend"] == "Bearish" and feature["breakout_down"]:
                signals.append("Break of Structure")

        if feature["support_distance"] <= 0.015 and feature["daily_change"] > 0:
            signals.append("Destekten Tepki")
            signals.append("Swing Low")
        if feature["resistance_distance"] <= 0.015:
            signals.append("Swing High")

        if feature["width_ratio"] <= 0.05 and len(candles) >= 20:
            highs_20 = [row[1] for row in candles[-20:]]
            lows_20 = [row[2] for row in candles[-20:]]
            ch_width = (max(highs_20) - min(lows_20)) / max(feature["current_price"], 1e-9)
            if ch_width <= 0.06:
                signals.append("Range")
                signals.append("Consolidation")

        unique: list[str] = []
        seen: set[str] = set()
        for item in signals:
            if item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return unique[:10]

    def _indicator_confirmations(self, feature: dict[str, Any], *, market_item: dict[str, Any]) -> list[str]:
        confirmations: list[str] = []
        ema20 = float(feature.get("ema20") or 0.0)
        ema50 = float(feature.get("ema50") or 0.0)
        current_price = float(feature.get("current_price") or 0.0)
        macd_value = float(feature.get("macd_value") or 0.0)
        macd_signal = float(feature.get("macd_signal") or 0.0)

        if feature["ema_bull"]:
            ema_spread = ((ema20 - ema50) / max(current_price, 1e-9)) * 100.0 if ema20 > 0 and ema50 > 0 else 0.0
            confirmations.append(f"EMA trend pozitif ({ema_spread:.2f}% spread)")
        elif feature["ema_bear"]:
            ema_spread = ((ema50 - ema20) / max(current_price, 1e-9)) * 100.0 if ema20 > 0 and ema50 > 0 else 0.0
            confirmations.append(f"EMA trend negatif ({ema_spread:.2f}% spread)")
        if feature["macd_state"] == "Bullish":
            confirmations.append(f"MACD pozitif fark {macd_value - macd_signal:.4f}")
        elif feature["macd_state"] == "Bearish":
            confirmations.append(f"MACD negatif fark {macd_value - macd_signal:.4f}")
        rsi_value = float(feature.get("rsi14") or 0.0)
        if 45.0 <= rsi_value <= 68.0:
            confirmations.append(f"RSI denge bolgesi ({rsi_value:.1f})")
        elif rsi_value > 68.0:
            confirmations.append(f"RSI yuksek bolge ({rsi_value:.1f})")
        elif 35.0 <= rsi_value < 45.0:
            confirmations.append(f"RSI toparlanma bolgesi ({rsi_value:.1f})")
        if feature["adx"] >= 22:
            confirmations.append(f"ADX trend gucu ({float(feature['adx']):.1f})")
        if feature["atr_ratio"] <= 0.03:
            confirmations.append(f"ATR/Price kontrollu ({float(feature['atr_ratio']) * 100:.2f}%)")
        if feature["bb_width_ratio"] <= 0.03:
            confirmations.append(f"Bollinger sikisma ({float(feature['bb_width_ratio']) * 100:.2f}%)")
        if feature["volume_expansion"]:
            confirmations.append(f"Hacim artisi (RVOL {float(feature['relative_volume']):.2f})")

        candles = self._extract_candles(market_item)
        candle_patterns = self._candlestick_patterns(candles)
        confirmations.extend([f"Mum: {name}" for name in candle_patterns[:2]])

        ma_signals = self._moving_average_signals(candles)
        confirmations.extend([f"MA: {name}" for name in ma_signals[:2]])

        volume_signals = self._volume_flow_signals(candles)
        confirmations.extend([f"Volume: {name}" for name in volume_signals[:2]])

        trend_signals = self._trend_strength_extensions(candles)
        confirmations.extend([f"Trend: {name}" for name in trend_signals[:2]])
        return confirmations[:5]

    def _price_plan(
        self,
        *,
        current_price: float,
        support: float,
        resistance: float,
        atr_value: float,
        breakout_up: bool,
    ) -> tuple[float, float, list[str]]:
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

        stop_atr_multiplier = 1.15 if breakout_up else 1.35

        stop_loss = min(
            support - max((atr_value * 0.35), (entry_price * 0.003)),
            entry_price - (atr_value * stop_atr_multiplier),
        )
        if stop_loss >= entry_price:
            stop_loss = entry_price - max(atr_value * 0.5, entry_price * 0.01)

        notes = [
            f"Entry current_price - buffer={price_buffer:.4f}",
            f"Pullback cap={pullback_anchor:.4f}",
            f"Entry finalized at {entry_price:.4f}",
            f"Stop placed below support and ATR={stop_loss:.4f}",
        ]
        return entry_price, stop_loss, notes

    def _build_trade_plan(
        self,
        *,
        market_item: dict[str, Any],
        graph_analysis: dict[str, Any],
        current_price: float,
        entry_price: float,
        stop_loss: float,
        support: float,
        resistance: float,
        trend: str,
        trend_strength: int,
        daily_change_pct: float,
        news_sentiment: str,
        news_reasons: list[str],
        quality_score: float,
        formation_confidence: float,
        fib_236: float,
        fib_382: float,
        fib_618: float,
        momentum_20d: float,
        volatility_pct: float,
        candle_count: int,
    ) -> dict[str, Any]:
        if candle_count < 250:
            return {
                "entry_strategy": "Yetersiz Veri",
                "entry_strategy_reason": "En az 250 mum gerekli",
                "entry_range_low": 0.0,
                "entry_range_high": 0.0,
                "limit_entry_price": 0.0,
                "entry_status": "NO TRADE",
                "market_entry_allowed": False,
                "decision": "NO TRADE",
                "take_profit_1": 0.0,
                "take_profit_2": 0.0,
                "take_profit_3": 0.0,
                "take_profit_4": 0.0,
                "take_profit_levels": [],
                "current_target": 0.0,
                "risk_reward_ratio": 0.0,
                "risk_reward_by_tp": [],
                "plan_notes": ["250 mum alti veri: no-trade"],
            }

        entry_strategy, entry_strategy_reason = self._select_entry_strategy(
            market_item=market_item,
            graph_analysis=graph_analysis,
            support=support,
            resistance=resistance,
            current_price=current_price,
            daily_change_pct=daily_change_pct,
            fib_382=fib_382,
        )
        entry_range_low, entry_range_high, limit_entry_price, entry_status, market_entry_allowed = self._entry_window(
            entry_price=entry_price,
            current_price=current_price,
            support=support,
            resistance=resistance,
            atr_value=self._float(market_item.get("atr")),
            trend=trend,
            breakout_up=bool(graph_analysis.get("breakout_up")),
            strategy=entry_strategy,
            levels=self._compute_levels(
                candles=self._extract_candles(market_item),
                current_price=current_price,
                support=support,
                resistance=resistance,
            ),
        )

        tp_candidates = self._target_candidates(
            market_item=market_item,
            graph_analysis=graph_analysis,
            entry_price=entry_price,
            support=support,
            resistance=resistance,
            trend_strength=trend_strength,
            formation_confidence=formation_confidence,
            fib_236=fib_236,
            fib_382=fib_382,
            fib_618=fib_618,
            momentum_20d=momentum_20d,
            volatility_pct=volatility_pct,
            news_sentiment=news_sentiment,
            news_reasons=news_reasons,
        )
        take_profit_levels = self._select_tp_levels(tp_candidates)
        risk_amount = max(0.01, entry_price - stop_loss)
        rr_by_tp = self._risk_reward_by_tp(
            entry_price=entry_price,
            risk_amount=risk_amount,
            score=quality_score,
            trend_strength=trend_strength,
            formation_confidence=formation_confidence,
            news_sentiment=news_sentiment,
            levels=take_profit_levels,
        )

        take_profit_1 = float(take_profit_levels[0]["price"]) if len(take_profit_levels) > 0 else 0.0
        take_profit_2 = float(take_profit_levels[1]["price"]) if len(take_profit_levels) > 1 else take_profit_1
        take_profit_3 = float(take_profit_levels[2]["price"]) if len(take_profit_levels) > 2 else take_profit_2
        take_profit_4 = float(take_profit_levels[3]["price"]) if len(take_profit_levels) > 3 else take_profit_3
        current_target = take_profit_4 or take_profit_3 or take_profit_2 or take_profit_1
        risk_reward_ratio = 0.0
        if rr_by_tp:
            risk_reward_ratio = max(0.0, float(rr_by_tp[min(2, len(rr_by_tp) - 1)].get("rr") or 0.0))

        decision = self._decide_entry_state(
            quality_score=quality_score,
            trend=trend,
            entry_status=entry_status,
            breakout_up=bool(graph_analysis.get("breakout_up")),
            formation_count=len(graph_analysis.get("formations") or []),
            risk_reward_ratio=risk_reward_ratio,
            market_entry_allowed=market_entry_allowed,
            stop_loss=stop_loss,
            entry_price=entry_price,
        )

        plan_notes = [
            f"Entry strategy: {entry_strategy}",
            f"Entry status: {entry_status}",
            f"TP ladder: {[round(float(level.get('price') or 0.0), 4) for level in take_profit_levels]}",
        ]

        return {
            "entry_strategy": entry_strategy,
            "entry_strategy_reason": entry_strategy_reason,
            "entry_range_low": entry_range_low,
            "entry_range_high": entry_range_high,
            "limit_entry_price": limit_entry_price,
            "entry_status": entry_status,
            "market_entry_allowed": market_entry_allowed,
            "decision": decision,
            "take_profit_1": take_profit_1,
            "take_profit_2": take_profit_2,
            "take_profit_3": take_profit_3,
            "take_profit_4": take_profit_4,
            "take_profit_levels": take_profit_levels,
            "current_target": current_target,
            "risk_reward_ratio": risk_reward_ratio,
            "risk_reward_by_tp": rr_by_tp,
            "plan_notes": plan_notes,
        }

    def _select_entry_strategy(
        self,
        *,
        market_item: dict[str, Any],
        graph_analysis: dict[str, Any],
        support: float,
        resistance: float,
        current_price: float,
        daily_change_pct: float,
        fib_382: float,
    ) -> tuple[str, str]:
        support_distance = abs(current_price - support) / max(current_price, 1e-9) if support > 0 else 1.0
        resistance_distance = abs(resistance - current_price) / max(current_price, 1e-9) if resistance > 0 else 1.0

        if bool(graph_analysis.get("breakout_up")) and resistance_distance <= 0.01:
            return "Breakout", "Direnc kirilimi sonrasi hizli devam"
        if support_distance <= 0.012 and daily_change_pct > 0:
            return "Destekten Donus", "Fiyat destek bolgesinden tepki aliyor"
        if any(str(item).strip().lower() == "retest" for item in list(graph_analysis.get("market_structure") or [])):
            return "Retest", "Kirilan seviyenin geri testi goruluyor"
        ema20 = self._float(market_item.get("ema20"))
        if ema20 > 0 and abs(current_price - ema20) / max(current_price, 1e-9) <= 0.005:
            return "EMA Pullback", "EMA20 seviyesine geri cekilme"
        if fib_382 > 0 and abs(current_price - fib_382) / max(current_price, 1e-9) <= 0.01:
            return "Fibonacci Retracement", "Fibo 0.382 bolgesinde denge"
        if bool(market_item.get("gap_up")) and daily_change_pct > 0:
            return "Gap Fill", "Gap sonrasi dengelenme bolgesi"
        return "Trendline Retest", "Yapisal retest bekleniyor"

    def _entry_window(
        self,
        *,
        entry_price: float,
        current_price: float,
        support: float,
        resistance: float,
        atr_value: float,
        trend: str,
        breakout_up: bool,
        strategy: str,
        levels: dict[str, Any],
    ) -> tuple[float, float, float, str, bool]:
        support_levels = [float(value) for value in list(levels.get("support_levels") or []) if float(value) > 0 and float(value) < current_price]
        resistance_levels = [float(value) for value in list(levels.get("resistance_levels") or []) if float(value) > current_price]

        nearest_support = support
        if support_levels:
            nearest_support = max(support_levels)
        nearest_resistance = resistance
        if resistance_levels:
            nearest_resistance = min(resistance_levels)

        structure_span = abs(nearest_resistance - nearest_support) if nearest_support > 0 and nearest_resistance > 0 else 0.0
        band = max(0.01, atr_value * 0.35, structure_span * 0.12)
        pivot_entry = entry_price

        if strategy in {"Destekten Donus", "EMA Pullback", "Fibonacci Retracement", "Retest", "Trendline Retest"} and nearest_support > 0:
            pivot_entry = max(nearest_support + (band * 0.55), min(entry_price, current_price))
        elif strategy == "Breakout" and nearest_resistance > 0:
            pivot_entry = max(entry_price, nearest_resistance - (band * 0.25))

        entry_low = max(0.01, pivot_entry - band)
        entry_high = pivot_entry + band

        status = "WAIT"
        market_allowed = False
        if current_price < entry_low:
            status = "PULLBACK BEKLE" if trend == "Bullish" else "WAIT"
        elif current_price <= entry_high:
            status = "BUY"
            market_allowed = True
        elif current_price <= entry_high * 1.005:
            status = "BUY"
            market_allowed = strategy == "Breakout" and breakout_up
        else:
            status = "ENTRY MISSED"

        if nearest_resistance > 0 and current_price < nearest_resistance * 0.995 and breakout_up is False and status == "WAIT":
            status = "BREAKOUT BEKLE"

        limit_price = min(entry_high, max(entry_low, pivot_entry))
        return round(entry_low, 4), round(entry_high, 4), round(limit_price, 4), status, market_allowed

    def _target_candidates(
        self,
        *,
        market_item: dict[str, Any],
        graph_analysis: dict[str, Any],
        entry_price: float,
        support: float,
        resistance: float,
        trend_strength: int,
        formation_confidence: float,
        fib_236: float,
        fib_382: float,
        fib_618: float,
        momentum_20d: float,
        volatility_pct: float,
        news_sentiment: str,
        news_reasons: list[str],
    ) -> list[dict[str, Any]]:
        candles = self._extract_candles(market_item)
        levels = self._compute_levels(
            candles=candles,
            current_price=entry_price,
            support=support,
            resistance=resistance,
        )
        resistance_levels = [value for value in levels.get("resistance_levels", []) if value > entry_price]
        support_levels = [value for value in levels.get("support_levels", []) if value < entry_price]

        range_height = max(
            abs(resistance - support),
            abs(resistance - entry_price),
            abs(entry_price - support),
            max(entry_price * max(volatility_pct, 0.007), 0.01),
        )
        breakout_level = resistance if resistance > 0 else entry_price
        extension_base = max(range_height, 0.01)

        def build(level_type: str, price: float, reason: str, priority: int) -> dict[str, Any]:
            return {
                "type": level_type,
                "price": round(max(entry_price + 0.01, price), 4),
                "reason": reason,
                "priority": priority,
            }

        candidates: list[dict[str, Any]] = []
        if resistance_levels:
            candidates.append(build("resistance_1", resistance_levels[0], "Ilk guclu direnc", 100))
        if len(resistance_levels) > 1:
            candidates.append(build("resistance_2", resistance_levels[1], "Ikinci guclu direnc", 95))
        if len(resistance_levels) > 2:
            candidates.append(build("resistance_3", resistance_levels[2], "Ucuncu guclu direnc", 90))
        if not resistance_levels and resistance > entry_price:
            candidates.append(build("resistance_1", resistance, "Yakin direnc seviyesi", 88))

        fib_1272 = breakout_level + (extension_base * 0.272)
        fib_1618 = breakout_level + (extension_base * 0.618)
        fib_2618 = breakout_level + (extension_base * 1.618)
        fib_4236 = breakout_level + (extension_base * 3.236)
        candidates.extend(
            [
                build("fib_1272", fib_1272, "Fibonacci 127.2 extension", 88),
                build("fib_1618", fib_1618, "Fibonacci 161.8 extension", 86),
                build("fib_2618", fib_2618, "Fibonacci 261.8 extension", 70),
                build("fib_4236", fib_4236, "Fibonacci 423.6 extension", 62),
            ]
        )

        trend_projection = breakout_level + (extension_base * (1.0 + max(0.0, momentum_20d * 2.0) + (trend_strength / 180.0)))
        channel_projection = float(levels.get("channel_upper_projection") or 0.0)
        if channel_projection > entry_price:
            candidates.append(build("channel_projection", channel_projection, "Trend kanal ust band projeksiyonu", 82))
        candidates.append(build("trend_projection", trend_projection, "Trend devami projeksiyonu", 78))

        pivot_candidates = list(levels.get("pivot_resistances", []))
        for idx, pivot_level in enumerate(pivot_candidates[:3], start=1):
            if pivot_level > entry_price:
                candidates.append(build(f"pivot_r{idx}", pivot_level, f"Pivot direnc R{idx}", 83 - (idx * 3)))

        swing_high = max(
            self._float(market_item.get("high")),
            self._float(market_item.get("day_high")),
            max(resistance_levels) if resistance_levels else resistance,
        )
        if swing_high > entry_price:
            candidates.append(build("swing_high", swing_high, "Yakin swing high seviyesi", 92))

        if support_levels:
            last_support = support_levels[-1]
            if last_support > 0 and breakout_level > last_support:
                compression_target = breakout_level + max(0.01, (breakout_level - last_support) * 0.65)
                candidates.append(build("compression_target", compression_target, "Sikisma genisleme hedefi", 76))

        if fib_236 > entry_price:
            candidates.append(build("fib_0236", fib_236, "Fibonacci 0.236 ust seviyesi", 72))
        if fib_382 > entry_price:
            candidates.append(build("fib_0382", fib_382, "Fibonacci 0.382 ust seviyesi", 74))
        if fib_618 > entry_price:
            candidates.append(build("fib_0618", fib_618, "Fibonacci 0.618 ust seviyesi", 76))

        if self._float(market_item.get("relative_volume")) >= 1.3:
            vp_target = breakout_level + (extension_base * 0.42)
            candidates.append(build("volume_profile", vp_target, "Hacim profili yuksek islem bolgesi", 84))

        formations = list(graph_analysis.get("formations") or [])
        if formations:
            top_formation = dict(formations[0])
            formation_name = str(top_formation.get("name") or "Formasyon")
            formation_target = self._formation_target(
                formation_name=formation_name,
                breakout_level=breakout_level,
                range_height=extension_base,
            )
            if formation_target > entry_price:
                candidates.append(
                    build(
                        "formation_target",
                        formation_target,
                        f"{formation_name} teknik hedefi",
                        95,
                    )
                )

        news_factor = self._news_target_factor(news_sentiment=news_sentiment, news_reasons=news_reasons)
        for candidate in candidates:
            candidate_type = str(candidate.get("type") or "")
            if candidate_type in {"resistance_1", "swing_high"}:
                continue
            candidate["price"] = round(max(entry_price + 0.01, float(candidate.get("price") or 0.0) * news_factor), 4)

        filtered: list[dict[str, Any]] = []
        seen_prices: set[float] = set()
        for candidate in sorted(candidates, key=lambda item: float(item.get("price") or 0.0)):
            price = round(float(candidate.get("price") or 0.0), 4)
            if price <= entry_price:
                continue
            if price in seen_prices:
                continue
            seen_prices.add(price)
            filtered.append(candidate)
        return filtered

    def _formation_target(self, *, formation_name: str, breakout_level: float, range_height: float) -> float:
        multipliers = {
            "Cup and Handle": 1.0,
            "Bull Flag": 0.85,
            "Bear Flag": 0.65,
            "Ascending Triangle": 1.0,
            "Descending Triangle": 0.7,
            "Symmetrical Triangle": 0.8,
            "Rectangle": 1.0,
            "Double Bottom (W)": 1.0,
            "Double Top (M)": 0.7,
            "Inverse Head and Shoulders": 1.1,
            "Head and Shoulders": 0.75,
            "Pennant": 0.8,
            "Falling Wedge": 0.9,
            "Rising Wedge": 0.7,
            "Channel Breakout": 1.0,
            "Trendline Break": 0.78,
            "Gap Breakout": 0.9,
            "Volatility Squeeze": 0.82,
            "Bollinger Squeeze Breakout": 0.92,
        }
        multiplier = float(multipliers.get(formation_name, 0.75))
        return breakout_level + (max(range_height, 0.01) * multiplier)

    def _select_tp_levels(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates:
            return []

        by_type: dict[str, list[dict[str, Any]]] = {}
        for candidate in candidates:
            key = str(candidate.get("type") or "other")
            by_type.setdefault(key, []).append(candidate)

        def pick(*types: str) -> dict[str, Any] | None:
            for entry_type in types:
                bucket = by_type.get(entry_type) or []
                if bucket:
                    return bucket.pop(0)
            return None

        selected: list[dict[str, Any]] = []
        priorities = [
            ("resistance_1", "swing_high", "fib_1272"),
            ("resistance_2", "fib_1618", "volume_profile", "fib_0382"),
            ("formation_target", "resistance_3", "fib_2618", "fib_0618"),
            ("trend_projection", "channel_projection", "fib_2618"),
        ]

        for index, group in enumerate(priorities, start=1):
            picked = pick(*group)
            if picked is None:
                leftovers = sorted(
                    [item for bucket in by_type.values() for item in bucket],
                    key=lambda item: (int(item.get("priority") or 0), float(item.get("price") or 0.0)),
                    reverse=True,
                )
                if not leftovers:
                    break
                picked = leftovers[0]
                by_type[str(picked.get("type") or "other")].remove(picked)
            selected.append(
                {
                    "label": f"TP{index}",
                    "price": round(float(picked.get("price") or 0.0), 4),
                    "reason": str(picked.get("reason") or "Teknik hedef"),
                    "type": str(picked.get("type") or "other"),
                }
            )

        return selected

    def _risk_reward_by_tp(
        self,
        *,
        entry_price: float,
        risk_amount: float,
        score: float,
        trend_strength: int,
        formation_confidence: float,
        news_sentiment: str,
        levels: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        base_probability = max(22.0, min(95.0, 36.0 + (score * 0.28) + (trend_strength * 0.22) + (formation_confidence * 0.08)))
        if news_sentiment == "Positive":
            base_probability += 4.0
        elif news_sentiment == "Negative":
            base_probability -= 8.0

        results: list[dict[str, Any]] = []
        for index, level in enumerate(levels, start=1):
            target_price = float(level.get("price") or 0.0)
            rr = max(0.0, (target_price - entry_price) / max(risk_amount, 1e-9))
            distance_pct = max(0.0, (target_price - entry_price) / max(entry_price, 1e-9))
            probability = base_probability - ((index - 1) * 16.0) - (distance_pct * 45.0)
            probability = max(10.0, min(98.0, probability))
            results.append(
                {
                    "label": str(level.get("label") or f"TP{index}"),
                    "price": round(target_price, 4),
                    "rr": round(rr, 2),
                    "probability": round(probability, 1),
                    "reason": str(level.get("reason") or "Teknik hedef"),
                }
            )
        return results

    def _news_target_factor(self, *, news_sentiment: str, news_reasons: list[str]) -> float:
        factor = 1.0
        lowered = [str(item).lower() for item in news_reasons]
        positive_tokens = ["kap", "bilanco", "temettu", "yatirim", "ihale", "sozlesme", "sektor"]
        negative_tokens = ["sorusturma", "iptal", "zarar", "dava", "ceza", "risk"]

        positive_hits = sum(1 for token in positive_tokens if any(token in reason for reason in lowered))
        negative_hits = sum(1 for token in negative_tokens if any(token in reason for reason in lowered))

        if news_sentiment == "Positive":
            factor += min(0.18, 0.04 + (positive_hits * 0.02))
        elif news_sentiment == "Negative":
            factor -= min(0.2, 0.06 + (negative_hits * 0.03))

        if positive_hits > negative_hits:
            factor += min(0.08, (positive_hits - negative_hits) * 0.015)
        elif negative_hits > positive_hits:
            factor -= min(0.12, (negative_hits - positive_hits) * 0.02)

        return max(0.82, min(1.26, factor))

    def _decide_entry_state(
        self,
        *,
        quality_score: float,
        trend: str,
        entry_status: str,
        breakout_up: bool,
        formation_count: int,
        risk_reward_ratio: float,
        market_entry_allowed: bool,
        stop_loss: float,
        entry_price: float,
    ) -> str:
        if entry_status == "NO TRADE":
            return "NO TRADE"
        if stop_loss >= entry_price:
            return "NO TRADE"
        if entry_status == "ENTRY MISSED":
            return "ENTRY MISSED"
        if trend == "Bearish" and not breakout_up:
            return "SELL"
        if quality_score < 48 or risk_reward_ratio < 0.8:
            return "WAIT"
        if quality_score < 40 and trend == "Bearish":
            return "EXIT"
        if entry_status in {"PULLBACK BEKLE", "BREAKOUT BEKLE"}:
            return entry_status
        if formation_count == 0 and quality_score < 62:
            return "WAIT"
        if entry_status == "BUY":
            return "BUY NOW" if market_entry_allowed else "LIMIT BUY"
        return "LIMIT BUY"

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
        no_news_signal: bool,
        has_gap_signal: bool,
        macro_notes: list[str],
    ) -> list[str]:
        reasons: list[str] = []
        candle_count = self._candle_count(market_item)
        if candle_count < 250:
            reasons.append(f"No-trade: mum verisi yetersiz ({candle_count}/250)")

        formations = list(graph_analysis.get("formations") or [])
        if formations:
            top = formations[0]
            reasons.append(f"Formasyon: {top.get('name')} ({int(round(float(top.get('confidence') or 0.0)))}%)")
            reasons.append(str(top.get("reason") or "Grafik yapisi olumlu"))
        else:
            reasons.append("Formasyon bulunamadi")
        for structure_signal in list(graph_analysis.get("market_structure") or [])[:3]:
            reasons.append(f"Price Action: {structure_signal}")
        for fresh_signal in list(graph_analysis.get("fresh_signals") or [])[:4]:
            reasons.append(fresh_signal)
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
        if no_news_signal and not has_gap_signal:
            reasons.append("Haber/GAP sinyali zayif: grafik agirlikli degerlendirildi")
        if news_sentiment == "Positive":
            reasons.append("Haber akisi olumlu")
        elif news_sentiment == "Negative":
            reasons.append("Haber akisi baski yaratiyor")
        reasons.extend(macro_notes[:2])
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

    def _fair_value_gap_signal(self, candles: list[tuple[float, float, float, float, float]]) -> str | None:
        if len(candles) < 3:
            return None
        c1 = candles[-3]
        c3 = candles[-1]
        if c3[2] > c1[1]:
            return "Fair Value Gap (Bullish)"
        if c3[1] < c1[2]:
            return "Fair Value Gap (Bearish)"
        return None

    def _candlestick_patterns(self, candles: list[tuple[float, float, float, float, float]]) -> list[str]:
        if len(candles) < 2:
            return []

        patterns: list[str] = []

        def body(candle: tuple[float, float, float, float, float]) -> float:
            return abs(candle[3] - candle[0])

        def upper(candle: tuple[float, float, float, float, float]) -> float:
            return candle[1] - max(candle[0], candle[3])

        def lower(candle: tuple[float, float, float, float, float]) -> float:
            return min(candle[0], candle[3]) - candle[2]

        prev = candles[-2]
        curr = candles[-1]
        b_prev = body(prev)
        b_curr = body(curr)
        range_curr = max(1e-9, curr[1] - curr[2])

        if lower(curr) >= b_curr * 1.8 and upper(curr) <= b_curr * 0.5:
            patterns.append("Hammer")
        if upper(curr) >= b_curr * 1.8 and lower(curr) <= b_curr * 0.5:
            patterns.append("Inverted Hammer")
        if b_curr <= range_curr * 0.1:
            patterns.append("Doji")
        if b_curr >= range_curr * 0.85:
            patterns.append("Marubozu")
        if b_curr <= range_curr * 0.25 and upper(curr) > b_curr and lower(curr) > b_curr:
            patterns.append("Spinning Top")

        if prev[3] < prev[0] and curr[3] > curr[0] and curr[0] <= prev[3] and curr[3] >= prev[0]:
            patterns.append("Bullish Engulfing")
        if prev[3] > prev[0] and curr[3] < curr[0] and curr[0] >= prev[3] and curr[3] <= prev[0]:
            patterns.append("Bearish Engulfing")

        if prev[3] < prev[0] and curr[3] > curr[0] and curr[3] >= (prev[0] + prev[3]) / 2.0:
            patterns.append("Piercing Line")
        if prev[3] > prev[0] and curr[3] < curr[0] and curr[3] <= (prev[0] + prev[3]) / 2.0:
            patterns.append("Dark Cloud Cover")

        if curr[3] > curr[0] and prev[3] < prev[0] and curr[3] < prev[0] and curr[0] > prev[3]:
            patterns.append("Harami")

        if len(candles) >= 3:
            c1 = candles[-3]
            c2 = candles[-2]
            c3 = candles[-1]
            if c1[3] < c1[0] and body(c2) <= (c1[1] - c1[2]) * 0.25 and c3[3] > c3[0] and c3[3] > (c1[0] + c1[3]) / 2.0:
                patterns.append("Morning Star")
            if c1[3] > c1[0] and body(c2) <= (c1[1] - c1[2]) * 0.25 and c3[3] < c3[0] and c3[3] < (c1[0] + c1[3]) / 2.0:
                patterns.append("Evening Star")

        if len(candles) >= 4:
            seq = candles[-4:-1]
            if all(item[3] > item[0] for item in seq) and seq[0][3] < seq[1][3] < seq[2][3]:
                patterns.append("Three White Soldiers")
            if all(item[3] < item[0] for item in seq) and seq[0][3] > seq[1][3] > seq[2][3]:
                patterns.append("Three Black Crows")

        unique: list[str] = []
        seen: set[str] = set()
        for item in patterns:
            if item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return unique[:4]

    def _moving_average_signals(self, candles: list[tuple[float, float, float, float, float]]) -> list[str]:
        closes = [row[3] for row in candles if row[3] > 0]
        if len(closes) < 20:
            return []

        def _sma(values: list[float], period: int) -> float:
            if len(values) < period:
                return values[-1]
            subset = values[-period:]
            return sum(subset) / len(subset)

        def _ema(values: list[float], period: int) -> float:
            if not values:
                return 0.0
            alpha = 2.0 / (period + 1.0)
            result = values[0]
            for value in values[1:]:
                result = (value * alpha) + (result * (1.0 - alpha))
            return result

        close = closes[-1]
        ema20 = _ema(closes[-60:], 20)
        ema50 = _ema(closes[-120:], 50)
        ema100 = _ema(closes[-180:], 100)
        ema200 = _ema(closes[-260:], 200)
        sma20 = _sma(closes, 20)
        sma50 = _sma(closes, 50)
        sma200 = _sma(closes, 200)

        prev_sma50 = _sma(closes[:-1], 50) if len(closes) > 50 else sma50
        prev_sma200 = _sma(closes[:-1], 200) if len(closes) > 200 else sma200

        signals: list[str] = []
        if ema20 > ema50 > ema100 > ema200:
            signals.append("EMA20>EMA50>EMA100>EMA200")
        if sma20 > sma50 > sma200:
            signals.append("SMA20>SMA50>SMA200")
        if prev_sma50 <= prev_sma200 and sma50 > sma200:
            signals.append("Golden Cross")
        if prev_sma50 >= prev_sma200 and sma50 < sma200:
            signals.append("Death Cross")

        ema_gap = abs(ema20 - ema50) / max(close, 1e-9)
        if ema_gap <= 0.0025:
            signals.append("EMA Compression")
        if ema_gap >= 0.011:
            signals.append("EMA Expansion")
        if abs(close - ema20) / max(close, 1e-9) <= 0.005:
            signals.append("EMA Pullback")

        return signals[:4]

    def _volume_flow_signals(self, candles: list[tuple[float, float, float, float, float]]) -> list[str]:
        if len(candles) < 5:
            return []

        closes = [row[3] for row in candles]
        volumes = [max(0.0, row[4]) for row in candles]
        if not any(volumes):
            return []

        obv = 0.0
        obv_series: list[float] = [0.0]
        for idx in range(1, len(closes)):
            if closes[idx] > closes[idx - 1]:
                obv += volumes[idx]
            elif closes[idx] < closes[idx - 1]:
                obv -= volumes[idx]
            obv_series.append(obv)

        cmf_values: list[float] = []
        for o, h, l, c, v in candles[-20:]:
            denom = max(1e-9, h - l)
            mfm = ((c - l) - (h - c)) / denom
            cmf_values.append(mfm * v)
        vol20 = sum(volumes[-20:])
        cmf = (sum(cmf_values) / max(1e-9, vol20)) if vol20 > 0 else 0.0

        latest_vol = volumes[-1]
        avg_vol = sum(volumes[-20:]) / max(1, min(20, len(volumes)))
        rvol = latest_vol / max(1e-9, avg_vol)

        signals: list[str] = []
        if obv_series[-1] > obv_series[max(0, len(obv_series) - 6)]:
            signals.append("OBV Bullish")
            signals.append("Accumulation")
        else:
            signals.append("OBV Bearish")
            signals.append("Distribution")
        if cmf >= 0.05:
            signals.append("CMF Positive")
        elif cmf <= -0.05:
            signals.append("CMF Negative")
        if rvol >= 1.8:
            signals.append("Volume Spike")
        elif rvol <= 0.65:
            signals.append("Volume Dry Up")
        signals.append(f"RVOL {rvol:.2f}")
        return signals[:5]

    def _trend_strength_extensions(self, candles: list[tuple[float, float, float, float, float]]) -> list[str]:
        if len(candles) < 20:
            return []

        highs = [row[1] for row in candles]
        lows = [row[2] for row in candles]
        closes = [row[3] for row in candles]

        true_ranges: list[float] = []
        plus_dm: list[float] = []
        minus_dm: list[float] = []
        for idx in range(1, len(candles)):
            tr = max(highs[idx] - lows[idx], abs(highs[idx] - closes[idx - 1]), abs(lows[idx] - closes[idx - 1]))
            true_ranges.append(tr)
            up_move = highs[idx] - highs[idx - 1]
            down_move = lows[idx - 1] - lows[idx]
            plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
            minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)

        atr14 = sum(true_ranges[-14:]) / max(1, min(14, len(true_ranges)))
        tr14 = sum(true_ranges[-14:])
        pdi = (sum(plus_dm[-14:]) / max(1e-9, tr14)) * 100.0
        mdi = (sum(minus_dm[-14:]) / max(1e-9, tr14)) * 100.0
        dx = abs(pdi - mdi) / max(1e-9, (pdi + mdi)) * 100.0
        adx = dx

        close = closes[-1]
        ema20 = close
        alpha = 2.0 / 21.0
        for value in closes[-60:]:
            ema20 = (value * alpha) + (ema20 * (1.0 - alpha))

        keltner_upper = ema20 + (atr14 * 2.0)
        keltner_lower = ema20 - (atr14 * 2.0)
        supertrend_base = ema20 - (atr14 * 3.0)

        mean20 = sum(closes[-20:]) / 20.0
        variance20 = sum((value - mean20) ** 2 for value in closes[-20:]) / 20.0
        std20 = variance20 ** 0.5
        bb_upper = mean20 + (std20 * 2.0)
        bb_lower = mean20 - (std20 * 2.0)
        bb_width = (bb_upper - bb_lower) / max(close, 1e-9)

        signals: list[str] = []
        if pdi > mdi:
            signals.append("DMI+ > DMI-")
        else:
            signals.append("DMI- > DMI+")
        if adx >= 25.0:
            signals.append(f"ADX Strong ({adx:.1f})")
        else:
            signals.append(f"ADX Weak ({adx:.1f})")
        if close > keltner_upper:
            signals.append("Keltner Breakout Up")
        elif close < keltner_lower:
            signals.append("Keltner Breakout Down")
        if close > supertrend_base:
            signals.append("SuperTrend Bullish")
        else:
            signals.append("SuperTrend Bearish")
        if bb_width <= 0.03:
            signals.append("Bollinger Squeeze")
        return signals[:5]

    def _extract_candles(self, market_item: dict[str, Any]) -> list[tuple[float, float, float, float, float]]:
        series = market_item.get("candles")
        if not isinstance(series, list):
            return []

        candles: list[tuple[float, float, float, float, float]] = []
        for item in series:
            row: tuple[float, float, float, float, float] | None = None
            if isinstance(item, dict):
                o = self._float(item.get("open"))
                h = self._float(item.get("high"))
                l = self._float(item.get("low"))
                c = self._float(item.get("close"))
                v = self._float(item.get("volume"))
                row = (o, h, l, c, v)
            elif isinstance(item, (list, tuple)) and len(item) >= 4:
                o = self._float(item[0])
                h = self._float(item[1])
                l = self._float(item[2])
                c = self._float(item[3])
                v = self._float(item[4]) if len(item) > 4 else 0.0
                row = (o, h, l, c, v)

            if row is None:
                continue
            if row[1] <= 0 or row[2] <= 0 or row[3] <= 0:
                continue
            candles.append(row)

        return candles

    def _compute_levels(
        self,
        *,
        candles: list[tuple[float, float, float, float, float]],
        current_price: float,
        support: float,
        resistance: float,
    ) -> dict[str, Any]:
        if not candles:
            return {
                "support_levels": [support] if support > 0 else [],
                "resistance_levels": [resistance] if resistance > 0 else [],
                "pivot_resistances": [],
                "channel_upper_projection": 0.0,
            }

        highs = [row[1] for row in candles]
        lows = [row[2] for row in candles]
        closes = [row[3] for row in candles]

        def local_support_resistance(window: int) -> tuple[list[float], list[float]]:
            if len(candles) < (window * 2) + 2:
                return [], []
            s_levels: list[float] = []
            r_levels: list[float] = []
            for idx in range(window, len(candles) - window):
                local_highs = highs[idx - window: idx + window + 1]
                local_lows = lows[idx - window: idx + window + 1]
                if highs[idx] == max(local_highs):
                    r_levels.append(highs[idx])
                if lows[idx] == min(local_lows):
                    s_levels.append(lows[idx])
            return s_levels, r_levels

        minor_supports, minor_resistances = local_support_resistance(3)
        major_supports, major_resistances = local_support_resistance(6)

        support_levels = sorted({round(value, 4) for value in minor_supports + major_supports if value > 0})
        resistance_levels = sorted({round(value, 4) for value in minor_resistances + major_resistances if value > 0})

        if support > 0:
            support_levels.append(round(support, 4))
        if resistance > 0:
            resistance_levels.append(round(resistance, 4))

        support_levels = sorted({value for value in support_levels if value < current_price})
        resistance_levels = sorted({value for value in resistance_levels if value > current_price})

        last_high = highs[-1]
        last_low = lows[-1]
        last_close = closes[-1]
        pivot = (last_high + last_low + last_close) / 3.0
        range_val = max(0.01, last_high - last_low)

        classic_r1 = (2 * pivot) - last_low
        classic_r2 = pivot + range_val
        fibonacci_r1 = pivot + (range_val * 0.382)
        fibonacci_r2 = pivot + (range_val * 0.618)
        camarilla_r4 = last_close + (range_val * 1.1 / 2.0)
        pivot_resistances = sorted(
            {
                round(classic_r1, 4),
                round(classic_r2, 4),
                round(fibonacci_r1, 4),
                round(fibonacci_r2, 4),
                round(camarilla_r4, 4),
            }
        )
        pivot_resistances = [value for value in pivot_resistances if value > current_price]

        channel_upper_projection = 0.0
        if len(closes) >= 25:
            recent = closes[-25:]
            slope = (recent[-1] - recent[0]) / 24.0
            residuals = [recent[idx] - (recent[0] + (slope * idx)) for idx in range(25)]
            channel_width = max(residuals) - min(residuals)
            channel_upper_projection = recent[-1] + slope * 5.0 + max(0.01, channel_width * 0.75)

        return {
            "support_levels": support_levels,
            "resistance_levels": resistance_levels,
            "pivot_resistances": pivot_resistances,
            "channel_upper_projection": round(channel_upper_projection, 4),
        }

    def _candle_count(self, market_item: dict[str, Any]) -> int:
        for key in ["candles", "ohlcv", "price_history", "history", "bars"]:
            value = market_item.get(key)
            if isinstance(value, list):
                return len(value)
        return 0

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
