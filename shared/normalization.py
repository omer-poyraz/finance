"""Data normalization helpers for collected items."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
import hashlib
import re
from urllib.parse import parse_qsl
from urllib.parse import urlparse
from urllib.parse import urlunparse
from urllib.parse import urlencode
from typing import Any


_WHITESPACE_PATTERN = re.compile(r"\s+")
_PUNCT_PATTERN = re.compile(r"[^\w\s]")
_COMMON_NEWS_PREFIXES = (
    "son dakika",
    "flaş",
    "flas",
    "güncel",
    "guncel",
)


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


def canonicalize_url(value: str) -> str:
    """Normalize URL for stable deduplication across source variants."""

    text = normalize_text(value)
    if not text:
        return ""

    parsed = urlparse(text)
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/+", "/", parsed.path).rstrip("/")

    query_pairs = []
    for key, val in parse_qsl(parsed.query, keep_blank_values=False):
        lowered_key = key.lower()
        if lowered_key.startswith("utm_") or lowered_key in {"fbclid", "gclid", "ref", "source"}:
            continue
        query_pairs.append((key, val))
    query = urlencode(sorted(query_pairs))

    return urlunparse((scheme, netloc, path, "", query, ""))


def canonicalize_news_title(value: str) -> str:
    """Normalize news titles for cross-site duplicate collapsing."""

    text = normalize_text(value).lower()
    for prefix in _COMMON_NEWS_PREFIXES:
        if text.startswith(prefix + " "):
            text = text[len(prefix):].strip()
            break

    text = _PUNCT_PATTERN.sub(" ", text)
    text = normalize_text(text)
    return text


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

        if source == "news":
            normalized_title = canonicalize_news_title(str(transformed.get("title", "")))
            normalized_url = canonicalize_url(str(transformed.get("url", "")))
            if not normalized_title or not normalized_url:
                continue

        transformed["source"] = source
        transformed["collected_at"] = normalize_datetime(record.get("published_at"))

        if source == "news":
            time_bucket = str(transformed.get("collected_at", ""))[:10]
            key_basis = [
                normalized_title,
                normalized_url,
                time_bucket,
            ]
        else:
            key_basis = [str(transformed.get(key, "")) for key in required_keys]

        item_id = build_item_id(*key_basis, source)
        transformed["id"] = item_id

        if item_id in seen_ids:
            continue

        seen_ids.add(item_id)
        normalized.append(transformed)

    return normalized
