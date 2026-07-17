"""Base analyzer abstraction."""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
import logging
from typing import ClassVar


class BaseAnalyzer(ABC):
    """Shared base class for scoring analyzers."""

    analyzer_name: ClassVar[str] = "analyzer"

    def __init__(self) -> None:
        self._logger = logging.getLogger(f"analyzers.{self.analyzer_name}")

    @abstractmethod
    def score(self, *args, **kwargs) -> float:
        """Return a score between 0 and 100."""

    def _clamp_score(self, score: float) -> float:
        """Clamp the score to the valid 0-100 range."""

        return max(0.0, min(100.0, float(score)))
