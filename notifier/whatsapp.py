
"""WhatsApp notifier implementation using the Cloud API."""

from __future__ import annotations

import logging

import requests

from config import settings
from notifier.base import Notifier
from notifier.base import NotificationResult


class WhatsAppNotifier(Notifier):
	"""Send WhatsApp messages through Meta's Cloud API when configured."""

	def __init__(self) -> None:
		self._logger = logging.getLogger(__name__)

	def send(self, message: str, *, title: str | None = None) -> NotificationResult:
		payload_text = f"{title}\n\n{message}" if title else message

		if not settings.whatsapp_configured:
			error = (
				"WhatsApp Cloud API is not configured. Set the required environment variables."
			)
			self._logger.warning(error)
			return self._result(
				channel="whatsapp",
				success=False,
				message=payload_text,
				error=error,
			)

		url = f"{settings.whatsapp_api_url}/{settings.whatsapp_phone_number_id}/messages"
		headers = {
			"Authorization": f"Bearer {settings.whatsapp_access_token}",
			"Content-Type": "application/json",
		}
		payload = {
			"messaging_product": "whatsapp",
			"to": settings.whatsapp_recipient_phone,
			"type": "text",
			"text": {
				"preview_url": False,
				"body": payload_text,
			},
		}

		try:
			response = requests.post(url, json=payload, headers=headers, timeout=20)
			response.raise_for_status()
		except requests.RequestException as exc:
			error = f"WhatsApp notification failed: {exc}"
			self._logger.exception(error)
			return self._result(
				channel="whatsapp",
				success=False,
				message=payload_text,
				error=error,
			)

		return self._result(channel="whatsapp", success=True, message=payload_text)

