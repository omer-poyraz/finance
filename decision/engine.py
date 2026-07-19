"""Decision engine for combining analyzer scores into actionable guidance."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from shared.exceptions import DecisionEngineError


@dataclass(frozen=True, slots=True)
class AnalyzerScore:
	"""One analyzer contribution to the final decision."""

	name: str
	score: float
	weight: float = 1.0


@dataclass(frozen=True, slots=True)
class DecisionResult:
	"""Final recommendation payload for downstream notification."""

	ticker: str
	decision: str
	entry_price: float
	entry_range_low: float
	entry_range_high: float
	stop_loss: float
	current_target: float
	risk_reward_ratio: float
	recommended_amount: float
	news_score: float
	technical_score: float
	fundamental_score: float
	market_intelligence_score: float
	overall_score: float
	confidence: float
	trend_strength: int
	estimated_trend_duration: str
	reasons: list[str] = field(default_factory=list)
	trend: str = "Neutral"
	relative_volume: float = 0.0
	gap: bool = False
	rejected: bool = False
	reject_reasons: list[str] = field(default_factory=list)


class DecisionEngine:
	"""Combine analyzer outputs into a price plan and rationale."""

	def __init__(
		self,
		*,
		stop_loss_atr_multiplier: float = 1.5,
	) -> None:
		if stop_loss_atr_multiplier <= 0:
			raise DecisionEngineError("stop_loss_atr_multiplier must be greater than zero")

		self._stop_loss_atr_multiplier = stop_loss_atr_multiplier

	def decide(
		self,
		*,
		ticker: str,
		current_price: float,
		support: float,
		resistance: float,
		ema20: float,
		atr_value: float,
		technical_score: float,
		news_score: float,
		fundamental_score: float,
		market_intelligence_score: float,
		trend: str,
		trend_strength: int,
		estimated_trend_duration: str,
		relative_volume: float,
		gap_up: bool,
		gap_down: bool,
		rsi14: float,
		macd_state: str,
		ema50: float,
		recommended_amount: float = 0.0,
		reasons: list[str] | None = None,
	) -> DecisionResult:
		"""Produce a deterministic recommendation from technical and news context."""

		if current_price <= 0:
			raise DecisionEngineError("current_price must be greater than zero")
		if support <= 0:
			raise DecisionEngineError("support must be greater than zero")
		if atr_value <= 0:
			raise DecisionEngineError("atr_value must be greater than zero")
		if ema50 <= 0:
			raise DecisionEngineError("ema50 must be greater than zero")

		clamped_news = self._clamp_score(news_score)
		clamped_technical = self._clamp_score(technical_score)
		clamped_fundamental = self._clamp_score(fundamental_score)
		clamped_market_intel = self._clamp_score(market_intelligence_score)
		reject_reasons = self._hard_filters(
			news_score=clamped_news,
			trend=trend,
			relative_volume=relative_volume,
			current_price=current_price,
			ema20=ema20,
			atr_value=atr_value,
		)

		confidence = self._calculate_confidence(
			news_score=clamped_news,
			technical_score=clamped_technical,
			fundamental_score=clamped_fundamental,
			market_intelligence_score=clamped_market_intel,
			trend=trend,
			relative_volume=relative_volume,
			has_gap=gap_up or gap_down,
			rsi14=rsi14,
			macd_state=macd_state,
			ema20=ema20,
			ema50=ema50,
		)
		overall_score = self._calculate_overall_score(
			news_score=clamped_news,
			technical_score=clamped_technical,
			fundamental_score=clamped_fundamental,
			market_intelligence_score=clamped_market_intel,
			confidence=confidence,
		)

		entry_price = self._calculate_entry_price(
			current_price,
			ema20=ema20,
			support=support,
			atr_value=atr_value,
		)
		stop_loss = self._calculate_stop_loss(
			entry_price=entry_price,
			support=support,
			atr_value=atr_value,
		)
		decision = self._determine_decision(
			overall_score=overall_score,
			trend=trend,
			trend_strength=trend_strength,
			rsi14=rsi14,
		)
		if decision in {"EXIT", "WAIT IN CASH"}:
			reject_reasons.append("Quality threshold not satisfied")

		current_target, risk_reward_ratio = self._calculate_target_and_rr(
			entry_price=entry_price,
			stop_loss=stop_loss,
			resistance=resistance,
			trend_strength=trend_strength,
		)

		entry_range_low = max(0.01, entry_price - max(atr_value * 0.25, entry_price * 0.002))
		entry_range_high = entry_price + max(atr_value * 0.25, entry_price * 0.002)

		merged_reasons = self._quality_reasons(
			base_reasons=reasons,
			trend=trend,
			relative_volume=relative_volume,
			rsi14=rsi14,
			macd_state=macd_state,
			ema20=ema20,
			ema50=ema50,
			gap_up=gap_up,
		)

		merged_reasons.extend(
			[
				f"Entry near pullback zone ({entry_price:.2f})",
				f"Stop below support ({support:.2f})",
				f"Trend strength {trend_strength}/100",
			]
		)

		return DecisionResult(
			ticker=ticker,
			decision=decision,
			entry_price=round(entry_price, 4),
			entry_range_low=round(entry_range_low, 4),
			entry_range_high=round(entry_range_high, 4),
			stop_loss=round(stop_loss, 4),
			current_target=round(current_target, 4),
			risk_reward_ratio=round(risk_reward_ratio, 4),
			recommended_amount=round(max(0.0, recommended_amount), 2),
			news_score=round(clamped_news, 2),
			technical_score=round(clamped_technical, 2),
			fundamental_score=round(clamped_fundamental, 2),
			market_intelligence_score=round(clamped_market_intel, 2),
			overall_score=round(overall_score, 2),
			confidence=round(confidence, 2),
			trend_strength=max(0, min(100, int(trend_strength))),
			estimated_trend_duration=str(estimated_trend_duration or "1-2 islem gunu"),
			reasons=merged_reasons,
			trend=trend,
			relative_volume=round(max(0.0, relative_volume), 4),
			gap=bool(gap_up or gap_down),
			rejected=bool(reject_reasons),
			reject_reasons=reject_reasons,
		)

	def _calculate_entry_price(
		self,
		current_price: float,
		*,
		ema20: float,
		support: float,
		atr_value: float,
	) -> float:
		pullback_floor = support + (atr_value * 0.2)
		pullback_anchor = min(current_price - (atr_value * 0.05), ema20)
		entry = max(pullback_floor, pullback_anchor)
		entry = min(entry, current_price - (atr_value * 0.02))

		if entry <= support:
			entry = support + (atr_value * 0.3)

		if entry >= current_price:
			entry = current_price - (atr_value * 0.02)

		if entry <= 0:
			raise DecisionEngineError("Calculated entry price is invalid")

		return entry

	def _calculate_stop_loss(
		self,
		entry_price: float,
		support: float,
		atr_value: float,
	) -> float:
		below_support = support - max((atr_value * 0.35), (entry_price * 0.003))
		atr_stop = entry_price - (atr_value * self._stop_loss_atr_multiplier)
		stop_loss = min(below_support, atr_stop)

		if stop_loss >= entry_price:
			raise DecisionEngineError("Stop loss must be below the entry price")
		if stop_loss >= support:
			stop_loss = support - max((atr_value * 0.2), (entry_price * 0.002))

		return stop_loss

	def _calculate_confidence(
		self,
		*,
		news_score: float,
		technical_score: float,
		fundamental_score: float,
		market_intelligence_score: float,
		trend: str,
		relative_volume: float,
		has_gap: bool,
		rsi14: float,
		macd_state: str,
		ema20: float,
		ema50: float,
	) -> float:
		trend_score = {"Bullish": 80.0, "Neutral": 55.0, "Bearish": 30.0}.get(trend, 50.0)
		volume_score = self._clamp_score(relative_volume * 50.0)
		gap_score = 65.0 if has_gap else 50.0
		rsi_score = 75.0 if 45.0 <= rsi14 <= 65.0 else (55.0 if 35.0 <= rsi14 <= 75.0 else 30.0)
		macd_score = {"Bullish": 75.0, "Neutral": 50.0, "Bearish": 30.0}.get(macd_state, 50.0)
		ema_score = 75.0 if ema20 > ema50 else 40.0

		confidence = (
			news_score * 0.18
			+ technical_score * 0.24
			+ fundamental_score * 0.16
			+ market_intelligence_score * 0.12
			+ trend_score * 0.15
			+ volume_score * 0.10
			+ gap_score * 0.08
			+ rsi_score * 0.04
			+ macd_score * 0.02
			+ ema_score * 0.01
		)
		return self._clamp_score(confidence)

	def _hard_filters(
		self,
		*,
		news_score: float,
		trend: str,
		relative_volume: float,
		current_price: float,
		ema20: float,
		atr_value: float,
	) -> list[str]:
		reasons: list[str] = []
		if news_score <= 35.0:
			reasons.append("Strongly negative news flow")
		if trend == "Bearish":
			reasons.append("Bearish trend")
		if relative_volume < 0.85:
			reasons.append("Relative volume too low")
		if current_price > (ema20 + (atr_value * 2.0)):
			reasons.append("Price is extremely overextended")
		return reasons

	def _quality_reasons(
		self,
		*,
		base_reasons: list[str] | None,
		trend: str,
		relative_volume: float,
		rsi14: float,
		macd_state: str,
		ema20: float,
		ema50: float,
		gap_up: bool,
	) -> list[str]:
		reasons = list(base_reasons or [])
		if trend == "Bullish":
			reasons.append("Bullish trend")
		if ema20 > ema50:
			reasons.append("EMA20 above EMA50")
		if macd_state == "Bullish":
			reasons.append("Bullish MACD")
		if relative_volume >= 1.1:
			reasons.append("High relative volume")
		if 45.0 <= rsi14 <= 65.0:
			reasons.append("Healthy RSI")
		if gap_up:
			reasons.append("Gap support confirmed")

		unique: list[str] = []
		seen: set[str] = set()
		for reason in reasons:
			if reason in seen:
				continue
			seen.add(reason)
			unique.append(reason)
		return unique

	def _calculate_overall_score(
		self,
		*,
		news_score: float,
		technical_score: float,
		fundamental_score: float,
		market_intelligence_score: float,
		confidence: float,
	) -> float:
		overall = (
			(news_score * 0.18)
			+ (technical_score * 0.34)
			+ (fundamental_score * 0.18)
			+ (market_intelligence_score * 0.12)
			+ (confidence * 0.18)
		)
		return self._clamp_score(overall)

	def _determine_decision(
		self,
		*,
		overall_score: float,
		trend: str,
		trend_strength: int,
		rsi14: float,
	) -> str:
		if trend == "Bearish" or overall_score < 40.0:
			return "EXIT"
		if overall_score < 52.0:
			return "WAIT IN CASH"
		if overall_score >= 72.0 and trend_strength >= 70 and 35.0 <= rsi14 <= 68.0:
			return "BUY"
		if overall_score >= 65.0 and trend_strength >= 72:
			return "RAISE STOP"
		if overall_score >= 58.0 and trend_strength < 70:
			return "PARTIAL TAKE PROFIT"
		return "HOLD"

	def _calculate_target_and_rr(
		self,
		*,
		entry_price: float,
		stop_loss: float,
		resistance: float,
		trend_strength: int,
	) -> tuple[float, float]:
		risk_amount = max(0.01, entry_price - stop_loss)
		strength_factor = 1.0 + max(0.0, min(1.0, trend_strength / 100.0))
		target = max(resistance, entry_price + (risk_amount * strength_factor))
		rr = (target - entry_price) / risk_amount if risk_amount > 0 else 0.0
		return target, max(0.0, rr)

	def _clamp_score(self, score: float) -> float:
		return max(0.0, min(100.0, float(score)))

