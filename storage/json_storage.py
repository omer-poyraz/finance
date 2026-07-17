"""JSON file-based persistence for local desktop execution."""

from __future__ import annotations

from pathlib import Path
import json
import logging
from typing import Any


logger = logging.getLogger(__name__)


class JsonStorage:
    """Persist and retrieve structured data from JSON files."""

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def exists(self, filename: str) -> bool:
        """Return whether a JSON file exists in storage."""

        return self._path(filename).exists()

    def load(self, filename: str, default: Any | None = None) -> Any:
        """Load JSON content; return default when file is missing."""

        path = self._path(filename)
        if not path.exists():
            if default is not None:
                return default
            raise FileNotFoundError(f"Storage file does not exist: {path}")

        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, filename: str, payload: Any) -> Any:
        """Write JSON content to a storage file."""

        path = self._path(filename)
        self._write(path, payload)
        return payload

    def append(self, filename: str, item: dict[str, Any]) -> list[dict[str, Any]]:
        """Append one record to a JSON list file."""

        content = self.load(filename, default=[])
        if not isinstance(content, list):
            raise ValueError(f"append requires list content in {filename}")

        content.append(item)
        self.save(filename, content)
        return content

    def update(self, filename: str, updater: callable) -> Any:
        """Update file content by applying a callable to the existing payload."""

        current = self.load(filename, default=[])
        updated = updater(current)
        self.save(filename, updated)
        return updated

    def ensure_default_files(self, filenames: list[str]) -> None:
        """Create required storage files when missing."""

        for filename in filenames:
            path = self._path(filename)
            if not path.exists():
                self._write(path, [])
                logger.info("Created storage file %s", path)

    def _path(self, filename: str) -> Path:
        if not filename.endswith(".json"):
            raise ValueError("Only .json files are supported")
        return self._base_dir / filename

    def _write(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
