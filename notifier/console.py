"""Console notifier implementation."""

from __future__ import annotations

import logging

from notifier.base import Notifier
from notifier.base import NotificationResult


class ConsoleNotifier(Notifier):
    """Send notifications to the application log stream."""

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def send(self, message: str, *, title: str | None = None) -> NotificationResult:
        payload = f"{title}\n\n{message}" if title else message
        self._logger.info("Notification: %s", payload)
        return self._result(channel="console", success=True, message=payload)
