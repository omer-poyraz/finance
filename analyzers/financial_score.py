
"""Financial scoring analyzer."""

from __future__ import annotations

from collections.abc import Mapping

from analyzers.base import BaseAnalyzer
from shared.exceptions import AnalysisError


class FinancialAnalyzer(BaseAnalyzer):
	"""Score fundamental quality from available financial metrics."""

	analyzer_name = "financial"

	def score(self, metrics: Mapping[str, float]) -> float:
		"""Return a financial quality score from normalized metrics."""

		if not metrics:
			raise AnalysisError("FinancialAnalyzer requires at least one metric")

		scores: list[float] = []

		for key, value in metrics.items():
			normalized_key = key.lower().strip()
			if value is None:
				continue

			if normalized_key in {"revenue_growth", "sales_growth", "earnings_growth"}:
				scores.append(self._clamp_score(50.0 + (float(value) * 2.0)))
			elif normalized_key in {"net_margin", "operating_margin", "gross_margin", "roe", "return_on_equity"}:
				scores.append(self._clamp_score(50.0 + float(value)))
			elif normalized_key in {"debt_to_equity", "debt_equity"}:
				scores.append(self._clamp_score(100.0 - min(100.0, float(value) * 20.0)))
			elif normalized_key in {"current_ratio", "quick_ratio"}:
				ratio = float(value)
				if 1.5 <= ratio <= 2.5:
					scores.append(95.0)
				elif 1.0 <= ratio < 1.5:
					scores.append(75.0)
				elif ratio > 2.5:
					scores.append(70.0)
				else:
					scores.append(40.0)
			elif normalized_key in {"eps_growth", "cash_flow_growth"}:
				scores.append(self._clamp_score(50.0 + (float(value) * 1.5)))

		if not scores:
			raise AnalysisError("FinancialAnalyzer did not receive recognized metrics")

		return self._clamp_score(sum(scores) / len(scores))

