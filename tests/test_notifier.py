from __future__ import annotations

from types import SimpleNamespace

from notifier import ConsoleNotifier
from notifier import TelegramNotifier
from notifier import WhatsAppNotifier


def test_console_notifier_returns_success() -> None:
    notifier = ConsoleNotifier()

    result = notifier.send("Hello world", title="Daily summary")

    assert result.success is True
    assert result.channel == "console"


def test_whatsapp_notifier_fails_gracefully_when_unconfigured(monkeypatch) -> None:
    from notifier import whatsapp as whatsapp_module

    monkeypatch.setattr(
        whatsapp_module,
        "settings",
        SimpleNamespace(
            whatsapp_configured=False,
            whatsapp_api_url="https://graph.facebook.com/v20.0",
            whatsapp_phone_number_id="",
            whatsapp_access_token="",
            whatsapp_recipient_phone="",
        ),
    )

    notifier = WhatsAppNotifier()
    result = notifier.send("Hello world")

    assert result.success is False
    assert result.channel == "whatsapp"


def test_telegram_notifier_fails_gracefully_when_unconfigured(monkeypatch) -> None:
    from notifier import telegram_notifier as telegram_module

    monkeypatch.setattr(
        telegram_module,
        "settings",
        SimpleNamespace(
            telegram_configured=False,
            telegram_bot_token="",
            telegram_chat_id="",
        ),
    )

    notifier = TelegramNotifier()
    result = notifier.send("Hello world")

    assert result.success is False
    assert result.channel == "telegram"
