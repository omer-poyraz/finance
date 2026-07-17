"""Base collector abstractions and collection result models."""

from __future__ import annotations

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from dataclasses import field
from datetime import UTC
from datetime import datetime
import logging
from typing import Any
from typing import ClassVar
from typing import Generic
from typing import TypeVar

import requests

from shared.exceptions import DataCollectionError


TItem = TypeVar("TItem")


@dataclass(frozen=True, slots=True)
class CollectorHealth:
    """Health snapshot for a collector."""

    name: str
    healthy: bool
    checked_at: datetime
    last_success_at: datetime | None
    consecutive_failures: int
    last_error: str | None


@dataclass(frozen=True, slots=True)
class CollectorResult(Generic[TItem]):
    """Result of a collector run."""

    collector_name: str
    source_name: str
    collected_at: datetime
    success: bool
    items: list[TItem] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BaseCollector(ABC, Generic[TItem]):
    """Shared base class for all collectors."""

    collector_name: ClassVar[str] = "collector"
    source_name: ClassVar[str] = "source"

    def __init__(
        self,
        *,
        timeout_seconds: int = 20,
        session: requests.Session | None = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()
        self._logger = logging.getLogger(f"collectors.{self.collector_name}")
        self._last_success_at: datetime | None = None
        self._last_error: str | None = None
        self._consecutive_failures = 0

    @abstractmethod
    def collect(self) -> CollectorResult[TItem]:
        """Collect data from the source and return a normalized result."""

    def health(self) -> CollectorHealth:
        """Return the current health snapshot for the collector."""

        return CollectorHealth(
            name=self.collector_name,
            healthy=self._consecutive_failures == 0,
            checked_at=datetime.now(UTC),
            last_success_at=self._last_success_at,
            consecutive_failures=self._consecutive_failures,
            last_error=self._last_error,
        )

    def _request(self, url: str) -> requests.Response:
        try:
            response = self._session.get(
                url,
                timeout=self._timeout_seconds,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            self._record_failure(str(exc))
            raise DataCollectionError(
                f"{self.collector_name} collector could not fetch {url}: {exc}"
            ) from exc

    def _record_success(self) -> None:
        self._last_success_at = datetime.now(UTC)
        self._last_error = None
        self._consecutive_failures = 0

    def _record_failure(self, error_message: str) -> None:
        self._last_error = error_message
        self._consecutive_failures += 1

    def _build_result(
        self,
        *,
        items: list[TItem],
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
        success: bool = True,
    ) -> CollectorResult[TItem]:
        return CollectorResult(
            collector_name=self.collector_name,
            source_name=self.source_name,
            collected_at=datetime.now(UTC),
            success=success,
            items=items,
            metadata=metadata or {},
            error=error,
        )
