"""Data normalization helpers for collected items."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
import hashlib
import re
from typing import Any


_WHITESPACE_PATTERN = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    """Normalize whitespace and trim text values."""

    return _WHITESPACE_PATTERN.sub(" ", value).strip()


def normalize_datetime(value: datetime | str | None) -> str:
    """Normalize date values to ISO-8601 UTC strings."""

    if value is None:
        return datetime.now(UTC).isoformat()

    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()

    text = normalize_text(value)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.astimezone(UTC).isoformat()
    except ValueError:
        return datetime.now(UTC).isoformat()


def build_item_id(*parts: str) -> str:
    """Create SHA256 ID from normalized string parts."""

    normalized_parts = [normalize_text(part).lower() for part in parts if part]
    payload = "|".join(normalized_parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def normalize_records(
    records: list[dict[str, Any]],
    *,
    required_keys: list[str],
    source: str,
) -> list[dict[str, Any]]:
    """Normalize records, reject invalid rows, and deduplicate by SHA256 id."""

    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for record in records:
        if not all(record.get(key) for key in required_keys):
            continue

        transformed: dict[str, Any] = {}
        for key, value in record.items():
            if isinstance(value, str):
                transformed[key] = normalize_text(value)
            else:
                transformed[key] = value

        transformed["source"] = source
        transformed["collected_at"] = normalize_datetime(record.get("published_at"))

        key_basis = [str(transformed.get(key, "")) for key in required_keys]
        item_id = build_item_id(*key_basis, source)
        transformed["id"] = item_id

        if item_id in seen_ids:
            continue

        seen_ids.add(item_id)
        normalized.append(transformed)

    return normalized
