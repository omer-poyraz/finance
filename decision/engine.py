"""Decision engine for combining analyzer scores into actionable guidance."""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Any

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
	entry_price: float
	stop_loss: float
	take_profit_1: float
	take_profit_2: float
	risk_reward_ratio: float
	news_score: float
	technical_score: float
	overall_score: float
	confidence: float
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
		risk_reward_ratio: float = 2.0,
		stop_loss_atr_multiplier: float = 1.5,
	) -> None:
		if risk_reward_ratio <= 0:
			raise DecisionEngineError("risk_reward_ratio must be greater than zero")
		if stop_loss_atr_multiplier <= 0:
			raise DecisionEngineError("stop_loss_atr_multiplier must be greater than zero")

		self._risk_reward_ratio = risk_reward_ratio
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
		trend: str,
		relative_volume: float,
		gap_up: bool,
		gap_down: bool,
		rsi14: float,
		macd_state: str,
		ema50: float,
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
		take_profit_1, take_profit_2, risk_reward_ratio = self._calculate_targets(
			entry_price=entry_price,
			stop_loss=stop_loss,
			resistance=resistance,
		)

		if risk_reward_ratio < 2.0:
			reject_reasons.append("Risk/Reward below 1:2 requirement")

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
				f"Risk/Reward {risk_reward_ratio:.2f}",
			]
		)

		return DecisionResult(
			ticker=ticker,
			entry_price=round(entry_price, 4),
			stop_loss=round(stop_loss, 4),
			take_profit_1=round(take_profit_1, 4),
			take_profit_2=round(take_profit_2, 4),
			risk_reward_ratio=round(risk_reward_ratio, 4),
			news_score=round(clamped_news, 2),
			technical_score=round(clamped_technical, 2),
			overall_score=round(overall_score, 2),
			confidence=round(confidence, 2),
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

	def _calculate_targets(
		self,
		entry_price: float,
		stop_loss: float,
		resistance: float | None,
	) -> tuple[float, float, float]:
		risk_amount = entry_price - stop_loss
		if risk_amount <= 0:
			raise DecisionEngineError("Risk amount must be positive")

		target_1 = resistance if resistance > entry_price else entry_price + risk_amount
		target_2 = entry_price + (risk_amount * max(2.0, self._risk_reward_ratio))

		if target_1 <= entry_price:
			target_1 = entry_price + risk_amount
		if target_2 <= target_1:
			target_2 = target_1 + risk_amount

		risk_reward_ratio = (target_2 - entry_price) / risk_amount
		if risk_reward_ratio < 2.0:
			target_2 = entry_price + (risk_amount * 2.0)
			risk_reward_ratio = 2.0

		return target_1, target_2, risk_reward_ratio

	def _calculate_confidence(
		self,
		*,
		news_score: float,
		technical_score: float,
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
			news_score * 0.20
			+ technical_score * 0.25
			+ trend_score * 0.15
			+ volume_score * 0.10
			+ gap_score * 0.08
			+ rsi_score * 0.08
			+ macd_score * 0.07
			+ ema_score * 0.07
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
		confidence: float,
	) -> float:
		overall = (news_score * 0.35) + (technical_score * 0.45) + (confidence * 0.20)
		return self._clamp_score(overall)

	def _clamp_score(self, score: float) -> float:
		return max(0.0, min(100.0, float(score)))

