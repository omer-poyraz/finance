"""Collector registration and orchestration."""

from __future__ import annotations

import logging
from typing import Any

from collectors.base_collector import BaseCollector
from collectors.base_collector import CollectorHealth
from collectors.base_collector import CollectorResult
from shared.exceptions import DataCollectionError


class CollectorManager:
    """Register collectors, execute them, and expose health snapshots."""

    def __init__(self) -> None:
        self._collectors: dict[str, BaseCollector[Any]] = {}
        self._logger = logging.getLogger(__name__)

    def register(self, collector: BaseCollector[Any]) -> None:
        """Register a collector instance under its declared name."""

        self._collectors[collector.collector_name] = collector

    def names(self) -> list[str]:
        """Return registered collector names in insertion order."""

        return list(self._collectors.keys())

    def collect_all(self) -> dict[str, CollectorResult[Any]]:
        """Execute all registered collectors and isolate failures."""

        results: dict[str, CollectorResult[Any]] = {}
        for name, collector in self._collectors.items():
            try:
                results[name] = collector.collect()
            except DataCollectionError as exc:
                self._logger.exception("Collector %s failed", name)
                results[name] = collector._build_result(
                    items=[],
                    metadata={"collector": name},
                    error=str(exc),
                    success=False,
                )
            except Exception as exc:  # pragma: no cover - defensive guard
                self._logger.exception("Unexpected collector error for %s", name)
                results[name] = collector._build_result(
                    items=[],
                    metadata={"collector": name},
                    error=f"Unexpected collector error: {exc}",
                    success=False,
                )
        return results

    def collect_one(self, name: str) -> CollectorResult[Any]:
        """Run a single collector by name."""

        try:
            collector = self._collectors[name]
        except KeyError as exc:
            raise KeyError(f"Collector not registered: {name}") from exc

        return collector.collect()

    def health_report(self) -> dict[str, CollectorHealth]:
        """Return health snapshots for all registered collectors."""

        return {name: collector.health() for name, collector in self._collectors.items()}
