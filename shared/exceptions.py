"""Shared exception hierarchy for the project."""

from __future__ import annotations


class FinanceEngineError(Exception):
    """Base exception for finance engine failures."""


class ConfigurationError(FinanceEngineError):
    """Raised when required configuration is missing or invalid."""


class DataCollectionError(FinanceEngineError):
    """Raised when a data source cannot be collected successfully."""


class IndicatorError(FinanceEngineError):
    """Raised when an indicator computation cannot be completed."""


class AnalysisError(FinanceEngineError):
    """Raised when a score cannot be computed reliably."""


class DecisionEngineError(FinanceEngineError):
    """Raised when a decision cannot be produced."""


class NotificationError(FinanceEngineError):
    """Raised when a notification cannot be delivered."""


class RepositoryError(FinanceEngineError):
    """Raised when repository access fails."""


class SchedulerError(FinanceEngineError):
    """Raised when scheduler setup or execution fails."""
