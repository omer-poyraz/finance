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


settings = Settings()
