"""Runtime settings loaded from environment variables."""

from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    value = str(os.getenv(name, str(default))).strip().lower()
    return value in {"1", "true", "yes", "on"}


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
        "https://www.bloomberght.com/rss|https://www.ekonomim.com/rss|https://www.ntv.com.tr/ekonomi.rss|https://www.borsavegundem.com/rss|https://www.dunya.com/rss|https://www.haberturk.com/rss/ekonomi.xml|https://www.aa.com.tr/tr/rss/default?cat=ekonomi|https://www.trthaber.com/sondakika.rss|https://www.cnbce.com/rss|https://www.investing.com/rss/news_25.rss",
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
    gemini_required: bool = _env_bool("GEMINI_REQUIRED", True)
    storage_data_dir: str = os.getenv("STORAGE_DATA_DIR", "storage/data")
    markets: str = os.getenv("MARKETS", "BIST,US")
    us_market_tickers: str = os.getenv("US_MARKET_TICKERS", "GOOGL,AMZN,TSLA,META,NFLX")
    total_capital: float = float(os.getenv("TOTAL_CAPITAL", "10000"))
    min_confidence_score: float = float(os.getenv("MIN_CONFIDENCE_SCORE", "80"))
    min_risk_reward_ratio: float = float(os.getenv("MIN_RISK_REWARD_RATIO", "1.2"))
    min_trend_strength: int = int(os.getenv("MIN_TREND_STRENGTH", "60"))
    min_relative_volume: float = float(os.getenv("MIN_RELATIVE_VOLUME", "0.9"))
    min_fundamental_score: float = float(os.getenv("MIN_FUNDAMENTAL_SCORE", "50"))
    min_market_intelligence_score: float = float(os.getenv("MIN_MARKET_INTELLIGENCE_SCORE", "50"))
    min_news_score: float = float(os.getenv("MIN_NEWS_SCORE", "45"))
    min_technical_score: float = float(os.getenv("MIN_TECHNICAL_SCORE", "50"))
    recommendation_decisions: str = os.getenv("RECOMMENDATION_DECISIONS", "BUY,HOLD")
    bist100_preference_enabled: bool = _env_bool("BIST100_PREFERENCE_ENABLED", True)
    bist100_good_min_total_score: float = float(os.getenv("BIST100_GOOD_MIN_TOTAL_SCORE", "70"))
    bist100_good_min_confidence: float = float(os.getenv("BIST100_GOOD_MIN_CONFIDENCE", "62"))
    bist_regime_guard_enabled: bool = _env_bool("BIST_REGIME_GUARD_ENABLED", True)
    bist_bearish_only_bist100: bool = _env_bool("BIST_BEARISH_ONLY_BIST100", True)
    bist_bearish_change_threshold: float = float(os.getenv("BIST_BEARISH_CHANGE_THRESHOLD", "-0.35"))
    bist_bearish_breadth_threshold: float = float(os.getenv("BIST_BEARISH_BREADTH_THRESHOLD", "0.55"))
    scheduler_bist_enabled: bool = _env_bool("SCHEDULER_BIST_ENABLED", True)
    scheduler_bist_live_enabled: bool = _env_bool("SCHEDULER_BIST_LIVE_ENABLED", True)
    scheduler_us_enabled: bool = _env_bool("SCHEDULER_US_ENABLED", True)
    scheduler_portfolio_enabled: bool = _env_bool("SCHEDULER_PORTFOLIO_ENABLED", False)
    scheduler_bist_hour: int = int(os.getenv("SCHEDULER_BIST_HOUR", "9"))
    scheduler_bist_minute: int = int(os.getenv("SCHEDULER_BIST_MINUTE", "45"))
    scheduler_bist_live_interval_minutes: int = int(os.getenv("SCHEDULER_BIST_LIVE_INTERVAL_MINUTES", "3"))
    scheduler_bist_live_start_hour: int = int(os.getenv("SCHEDULER_BIST_LIVE_START_HOUR", "9"))
    scheduler_bist_live_start_minute: int = int(os.getenv("SCHEDULER_BIST_LIVE_START_MINUTE", "55"))
    scheduler_bist_live_end_hour: int = int(os.getenv("SCHEDULER_BIST_LIVE_END_HOUR", "18"))
    scheduler_bist_live_end_minute: int = int(os.getenv("SCHEDULER_BIST_LIVE_END_MINUTE", "10"))
    scheduler_us_hour: int = int(os.getenv("SCHEDULER_US_HOUR", "16"))
    scheduler_us_minute: int = int(os.getenv("SCHEDULER_US_MINUTE", "0"))
    scheduler_portfolio_hour: int = int(os.getenv("SCHEDULER_PORTFOLIO_HOUR", "22"))
    scheduler_portfolio_minute: int = int(os.getenv("SCHEDULER_PORTFOLIO_MINUTE", "30"))
    live_only_mode: bool = _env_bool("LIVE_ONLY_MODE", False)

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

    @property
    def market_list(self) -> list[str]:
        """Return enabled market identifiers."""

        values = [item.strip().upper() for item in self.markets.split(",")]
        return [item for item in values if item]

    @property
    def us_market_ticker_list(self) -> list[str]:
        """Return configured US symbols."""

        values = [item.strip().upper() for item in self.us_market_tickers.split(",")]
        return [item for item in values if item]

    @property
    def recommendation_decision_list(self) -> list[str]:
        """Return allowed recommendation decisions."""

        values = [item.strip().upper() for item in self.recommendation_decisions.split(",")]
        return [item for item in values if item]

    @property
    def gemini_api_keys(self) -> list[str]:
        """Return configured Gemini API keys from pool variables."""

        keys: list[str] = []

        primary = str(os.getenv("GEMINI_API_KEY", "")).strip()
        if primary:
            keys.append(primary)

        index = 1
        while True:
            env_name = f"GEMINI_API_KEY_{index}"
            value = str(os.getenv(env_name, "")).strip()
            if not value:
                break
            keys.append(value)
            index += 1

        deduped: list[str] = []
        seen: set[str] = set()
        for key in keys:
            if key in seen:
                continue
            seen.add(key)
            deduped.append(key)

        return deduped


settings = Settings()
