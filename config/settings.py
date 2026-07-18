"""Runtime settings loaded from environment variables."""

from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True, slots=True)
class Settings:
    """Container for application-wide settings."""

    db_host: str = os.getenv("DB_HOST", "localhost")
    db_port: int = int(os.getenv("DB_PORT", "5432"))
    db_name: str = os.getenv("DB_NAME", "finance")
    db_user: str = os.getenv("DB_USER", "postgres")
    db_password: str = os.getenv("DB_PASSWORD", "")
    timezone: str = os.getenv("TIMEZONE", "Europe/Istanbul")
    news_source_url: str = os.getenv(
        "NEWS_SOURCE_URL",
        "https://www.getmidas.com/",
    )
    news_sources: str = os.getenv(
        "NEWS_SOURCES",
        "https://www.getmidas.com/|https://www.getmidas.com/borsa-haberleri/|https://www.kap.org.tr/tr/rss|https://www.borsaistanbul.com/tr/rss|https://feeds.finance.yahoo.com/rss/2.0/headline?s=THYAO.IS,SISE.IS,ASELS.IS&region=TR&lang=tr-TR|https://www.bloomberght.com/rss",
    )
    kap_source_url: str = os.getenv(
        "KAP_SOURCE_URL",
        "https://www.kap.org.tr/tr/bildirim-sorgu",
    )
    market_source_url: str = os.getenv(
        "MARKET_SOURCE_URL",
        "https://www.borsaistanbul.com/tr",
    )
    whatsapp_api_url: str = os.getenv(
        "WHATSAPP_API_URL",
        "https://graph.facebook.com/v20.0",
    )
    whatsapp_phone_number_id: str = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    whatsapp_access_token: str = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
    whatsapp_recipient_phone: str = os.getenv("WHATSAPP_RECIPIENT_PHONE", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    storage_data_dir: str = os.getenv("STORAGE_DATA_DIR", "storage/data")

    @property
    def database_url(self) -> str:
        """Return the SQLAlchemy database URL."""

        return (
            f"postgresql+psycopg2://"
            f"{self.db_user}:"
            f"{self.db_password}@"
            f"{self.db_host}:"
            f"{self.db_port}/"
            f"{self.db_name}"
        )

    @property
    def whatsapp_configured(self) -> bool:
        """Return whether WhatsApp Cloud API credentials are present."""

        return all(
            [
                self.whatsapp_phone_number_id,
                self.whatsapp_access_token,
                self.whatsapp_recipient_phone,
            ]
        )

    @property
    def telegram_configured(self) -> bool:
        """Return whether Telegram Bot API credentials are present."""

        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def news_source_list(self) -> list[str]:
        """Return configured multi-source news URLs from environment."""

        values = [item.strip() for item in self.news_sources.split("|")]
        return [item for item in values if item]


settings = Settings()
