"""Notifier abstractions and result model."""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NotificationResult:
    """Outcome of a notification attempt."""

    channel: str
    success: bool
    message: str
    delivered_at: datetime
    error: str | None = None


class Notifier(ABC):
    """Base interface for all notification channels."""

    @abstractmethod
    def send(self, message: str, *, title: str | None = None) -> NotificationResult:
        """Send a formatted notification payload."""

    def _result(
        self,
        *,
        channel: str,
        success: bool,
        message: str,
        error: str | None = None,
    ) -> NotificationResult:
        return NotificationResult(
            channel=channel,
            success=success,
            message=message,
            delivered_at=datetime.now(UTC),
            error=error,
        )
