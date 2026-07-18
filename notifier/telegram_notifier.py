"""Telegram notifier implementation using Bot API."""

from __future__ import annotations

import logging
import time

import requests

from config import settings
from notifier.base import Notifier
from notifier.base import NotificationResult


class TelegramNotifier(Notifier):
    """Send Telegram notifications with chunking and retry support."""

    _max_chunk_size = 3800

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)

    def send(self, message: str, *, title: str | None = None) -> NotificationResult:
        payload_text = f"{title}\n\n{message}" if title else message

        if not settings.telegram_configured:
            error = "Telegram Bot API is not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID."
            self._logger.warning(error)
            return self._result(
                channel="telegram",
                success=False,
                message=payload_text,
                error=error,
            )

        chunks = self._chunk_message(payload_text)
        for index, chunk in enumerate(chunks, start=1):
            sent = self._send_with_retry(chunk)
            if not sent:
                error = f"Telegram notification failed at chunk {index}/{len(chunks)}"
                return self._result(
                    channel="telegram",
                    success=False,
                    message=payload_text,
                    error=error,
                )

        return self._result(channel="telegram", success=True, message=payload_text)

    def _send_with_retry(self, chunk: str) -> bool:
        endpoint = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": settings.telegram_chat_id,
            "text": chunk,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        delays = [0.5, 1.0, 1.8]
        for attempt, delay in enumerate(delays, start=1):
            try:
                response = requests.post(endpoint, json=payload, timeout=20)
                if response.status_code == 400 and payload.get("parse_mode"):
                    payload.pop("parse_mode", None)
                    response = requests.post(endpoint, json=payload, timeout=20)
                if response.status_code in {429, 500, 502, 503, 504}:
                    raise requests.RequestException(f"retryable_status:{response.status_code}")
                response.raise_for_status()
                return True
            except requests.RequestException as exc:
                self._logger.warning("Telegram send failed (attempt %s/%s): %s", attempt, len(delays), exc)
                if attempt == len(delays):
                    break
                time.sleep(delay)

        return False

    def _chunk_message(self, message: str) -> list[str]:
        text = message.strip()
        if not text:
            return ["No content"]

        if len(text) <= self._max_chunk_size:
            return [text]

        lines = text.splitlines()
        chunks: list[str] = []
        current = ""

        for line in lines:
            candidate = f"{current}\n{line}".strip() if current else line
            if len(candidate) <= self._max_chunk_size:
                current = candidate
                continue

            if current:
                chunks.append(current)
                current = ""

            if len(line) <= self._max_chunk_size:
                current = line
                continue

            start = 0
            while start < len(line):
                end = min(start + self._max_chunk_size, len(line))
                chunks.append(line[start:end])
                start = end

        if current:
            chunks.append(current)

        return chunks
