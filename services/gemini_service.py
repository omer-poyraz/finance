"""Optional Gemini integration with strict fallback behavior."""

from __future__ import annotations

from copy import deepcopy
import importlib
import hashlib
import json
import logging
import time
from typing import Any

from config import settings


logger = logging.getLogger(__name__)


class GeminiService:
    """Provide resilient Gemini access for analysis-only enrichment."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: int = 12,
        max_retries: int = 2,
    ) -> None:
        key_pool = list(settings.gemini_api_keys)
        if api_key is not None:
            chosen = api_key.strip()
            key_pool = [chosen] if chosen else []

        self._api_keys = [key for key in key_pool if key]
        self._model_name = (model_name if model_name is not None else settings.gemini_model).strip()
        self._timeout_seconds = max(3, int(timeout_seconds))
        self._max_retries = max(0, int(max_retries))

        self._models_by_key: dict[str, Any] = {}
        self._sdk: Any | None = None
        self._active_key_index = 0
        self._last_used_key_index = 0
        self._request_count = 0
        self._health_cache: bool | None = None
        self._cache: dict[str, Any] = {}

    @property
    def enabled(self) -> bool:
        if not self._api_keys:
            return False
        if not self._model_name or self._model_name.upper() == "XXXX":
            return False
        return True

    def health(self, *, force: bool = False) -> bool:
        """Compatibility health method required by production contract."""

        return self.health_check(force=force)

    def health_check(self, *, force: bool = False) -> bool:
        """Validate basic Gemini availability without raising errors."""

        if not self.enabled:
            return False

        if self._health_cache is not None and not force:
            return self._health_cache

        if not self._api_keys:
            self._health_cache = False
            return False

        healthy_model_found = False
        for api_key in self._api_keys:
            if self._model_for_key(api_key) is not None:
                healthy_model_found = True
                break
        if not healthy_model_found:
            self._health_cache = False
            return False

        prompt = "Only return this exact JSON: {\"status\":\"ok\"}"
        result = self._request_json(prompt=prompt, cache_key="health", retries=0)
        self._health_cache = bool(isinstance(result, dict) and str(result.get("status")).lower() == "ok")
        return bool(self._health_cache)

    def analyze_news(self, news_item: dict[str, Any] | None) -> dict[str, Any] | None:
        """Analyze one normalized news item and return structured sentiment JSON."""

        if not isinstance(news_item, dict) or not news_item:
            return None

        compact = {
            "title": str(news_item.get("title") or "").strip(),
            "summary": str(news_item.get("summary") or "").strip(),
            "source": str(news_item.get("source") or "").strip(),
            "ticker": news_item.get("ticker"),
            "published_at": str(news_item.get("published_at") or news_item.get("collected_at") or "").strip(),
            "url": str(news_item.get("url") or "").strip(),
        }
        if not compact["title"]:
            return None

        prompt = (
            "Analyze this BIST news item for qualitative context only. "
            "Do not calculate entry, stop, take profit, indicators, risk model, trend, signals, or confidence score of the trading engine. "
            "Return only JSON with keys: sentiment, impact, confidence, explanation. "
            "sentiment must be one of Positive, Neutral, Negative. "
            "impact must be one of Low, Medium, High. "
            "confidence must be an integer between 0 and 100. "
            "explanation must be short, professional, and in Turkish.\n"
            f"Input: {json.dumps(compact, ensure_ascii=False)}"
        )

        cache_key = self._cache_key("news", compact)
        payload = self._request_json(prompt=prompt, cache_key=cache_key)
        if not isinstance(payload, dict):
            return None

        sentiment = str(payload.get("sentiment") or "Neutral").strip().title()
        if sentiment not in {"Positive", "Neutral", "Negative"}:
            sentiment = "Neutral"

        impact = str(payload.get("impact") or "Medium").strip().title()
        if impact not in {"Low", "Medium", "High"}:
            impact = "Medium"

        confidence = self._safe_int(payload.get("confidence"), default=55, minimum=0, maximum=100)
        explanation = str(payload.get("explanation") or "").strip()
        if not explanation:
            return None

        return {
            "sentiment": sentiment,
            "impact": impact,
            "confidence": confidence,
            "explanation": explanation,
        }

    def summarize_market(self, recommendations: list[dict[str, Any]]) -> str | None:
        """Summarize overall market tone from final recommendation context."""

        if not recommendations:
            return None

        compact = {
            "total": len(recommendations),
            "top": [
                {
                    "ticker": str(item.get("ticker") or "").strip().upper(),
                    "overall_score": float(item.get("overall_score") or 0.0),
                    "confidence": float(item.get("confidence") or 0.0),
                    "ai_reason": str(item.get("ai_reason") or "").strip(),
                }
                for item in recommendations
            ],
        }

        prompt = (
            "BIST gunu icin kisa piyasa ozeti yaz. "
            "Sadece niteliksel yorum yap ve profesyonel Turkce kullan. "
            "Al/sat sinyali, giris-stop-hedef, teknik indikatorden uretilmis islem onerisi veya skor degisikligi yapma.\n"
            f"Input: {json.dumps(compact, ensure_ascii=False)}"
        )

        return self._request_text(prompt=prompt, cache_key=self._cache_key("market_summary", compact))

    def summarize_recommendations(self, recommendations: list[dict[str, Any]]) -> str | None:
        """Summarize recommendation rationale in natural Turkish."""

        return self.generate_daily_summary(recommendations)

    def summarize_news(self, analyzed_news: list[dict[str, Any]]) -> str | None:
        """Summarize daily important news in Turkish for optional notifier context."""

        if not analyzed_news:
            return None

        compact = [
            {
                "ticker": item.get("ticker"),
                "sentiment": item.get("sentiment"),
                "importance": item.get("importance"),
                "reasons": list(item.get("reasons") or [])[:2],
            }
            for item in analyzed_news[:12]
        ]

        prompt = (
            "BIST gununun onemli haberlerini 3-5 satirda Turkce ozetle. "
            "Sadece niteliksel yorum yap, fiyat seviyesi veya al-sat sinyali verme.\n"
            f"Input: {json.dumps(compact, ensure_ascii=False)}"
        )
        return self._request_text(prompt=prompt, cache_key=self._cache_key("news_summary", compact))

    def analyze_kap(self, kap_item: dict[str, Any] | None) -> dict[str, Any] | None:
        """Analyze one KAP item and return structured sentiment JSON."""

        if not isinstance(kap_item, dict) or not kap_item:
            return None

        compact = {
            "title": str(kap_item.get("title") or "").strip(),
            "summary": str(kap_item.get("summary") or "").strip(),
            "source": str(kap_item.get("source") or "kap").strip(),
            "ticker": kap_item.get("ticker"),
            "published_at": str(kap_item.get("published_at") or kap_item.get("collected_at") or "").strip(),
            "url": str(kap_item.get("url") or "").strip(),
        }
        if not compact["title"]:
            return None

        prompt = (
            "Analyze this KAP disclosure for qualitative market tone only. "
            "Do not calculate any trading levels, technical indicators, trend signals, risk model, or decision confidence. "
            "Return only JSON with keys: sentiment, confidence, explanation. "
            "sentiment must be one of Positive, Neutral, Negative. "
            "confidence must be an integer between 0 and 100. "
            "explanation must be short, professional, and in Turkish.\n"
            f"Input: {json.dumps(compact, ensure_ascii=False)}"
        )

        cache_key = self._cache_key("kap", compact)
        payload = self._request_json(prompt=prompt, cache_key=cache_key)
        if not isinstance(payload, dict):
            return None

        sentiment = str(payload.get("sentiment") or "Neutral").strip().title()
        if sentiment not in {"Positive", "Neutral", "Negative"}:
            sentiment = "Neutral"

        confidence = self._safe_int(payload.get("confidence"), default=55, minimum=0, maximum=100)
        explanation = str(payload.get("explanation") or "").strip()
        if not explanation:
            return None

        return {
            "sentiment": sentiment,
            "confidence": confidence,
            "explanation": explanation,
        }

    def generate_daily_summary(self, recommendations: list[dict[str, Any]]) -> str | None:
        """Generate a professional Turkish market summary from final recommendations."""

        if not recommendations:
            return None

        compact: list[dict[str, Any]] = []
        for item in recommendations:
            compact.append(
                {
                    "ticker": str(item.get("ticker") or "").strip().upper(),
                    "overall_score": float(item.get("overall_score") or 0.0),
                    "confidence": float(item.get("confidence") or 0.0),
                    "reasons": [str(reason) for reason in item.get("reasons", [])[:4]],
                    "ai_summary": str(item.get("ai_summary") or "").strip(),
                }
            )

        prompt = (
            "BIST icin profesyonel bir gunluk piyasa ozeti yaz. "
            "Maksimum 8 paragraf olsun. "
            "Yalnizca niteliksel yorum yap. "
            "Giris, stop, hedef, indikator, trend sinyali, risk hesaplamasi veya engine confidence hesaplama yapma.\n"
            f"Input: {json.dumps(compact, ensure_ascii=False)}"
        )

        cache_key = self._cache_key("daily_summary", compact)
        text = self._request_text(prompt=prompt, cache_key=cache_key)
        if not text:
            return None

        return text.strip()

    def _ensure_sdk(self) -> bool:
        if self._sdk is not None:
            return True

        try:
            self._sdk = importlib.import_module("google.generativeai")
            return True
        except ModuleNotFoundError:
            logger.warning("Gemini SDK is not installed; AI enrichment disabled")
            return False

    def _model_for_key(self, api_key: str) -> Any | None:
        model = self._models_by_key.get(api_key)
        if model is not None:
            return model

        if not self._ensure_sdk():
            return None

        assert self._sdk is not None
        configure = getattr(self._sdk, "configure", None)
        model_cls = getattr(self._sdk, "GenerativeModel", None)
        if not callable(configure) or model_cls is None:
            logger.warning("Gemini SDK exports are unavailable; AI enrichment disabled")
            return None

        try:
            configure(api_key=api_key)
            model = model_cls(self._model_name)
            self._models_by_key[api_key] = model
            return model
        except Exception as exc:  # pragma: no cover - SDK-specific initialization failure
            logger.warning("Gemini client initialization failed for key index %s: %s", self._safe_key_index(api_key), exc)
            return None

    def _request_json(self, *, prompt: str, cache_key: str, retries: int | None = None) -> dict[str, Any] | None:
        cached = self._cache.get(cache_key)
        if isinstance(cached, dict):
            return deepcopy(cached)

        text = self._request_text(prompt=prompt, cache_key=f"{cache_key}:text", retries=retries)
        if not text:
            return None

        parsed = self._extract_json(text)
        if not isinstance(parsed, dict):
            logger.warning("Gemini returned non-JSON output for key=%s", cache_key)
            return None

        self._cache[cache_key] = parsed
        return deepcopy(parsed)

    def _request_text(self, *, prompt: str, cache_key: str, retries: int | None = None) -> str | None:
        cached = self._cache.get(cache_key)
        if isinstance(cached, str):
            return cached

        if not self.enabled:
            return None

        max_retry = self._max_retries if retries is None else max(0, int(retries))
        attempts_per_key = max_retry + 1
        key_count = len(self._api_keys)
        total_attempts = max(1, key_count * attempts_per_key)

        for global_attempt in range(total_attempts):
            key_offset = global_attempt % key_count
            key_index = (self._active_key_index + key_offset) % key_count
            api_key = self._api_keys[key_index]
            model = self._model_for_key(api_key)
            if model is None:
                continue

            try:
                response = model.generate_content(
                    prompt,
                    generation_config={"temperature": 0.1, "max_output_tokens": 700},
                    request_options={"timeout": self._timeout_seconds},
                )
                text = str(getattr(response, "text", "") or "").strip()
                if not text:
                    raise ValueError("empty response text")

                self._active_key_index = key_index
                self._last_used_key_index = key_index + 1
                self._request_count += 1
                logger.info("Gemini request succeeded with key index %s", self._safe_key_index(api_key))
                self._cache[cache_key] = text
                return text
            except Exception as exc:  # pragma: no cover - external SDK errors vary by runtime
                retryable = self._is_retryable_error(exc)
                logger.warning(
                    "Gemini request failed with key index %s (attempt %s/%s, retryable=%s): %s",
                    self._safe_key_index(api_key),
                    global_attempt + 1,
                    total_attempts,
                    retryable,
                    exc,
                )
                if not retryable:
                    continue
                time.sleep(min(1.5, 0.35 * ((global_attempt % attempts_per_key) + 1)))

        return None

    def _safe_key_index(self, api_key: str) -> int:
        for idx, value in enumerate(self._api_keys, start=1):
            if value == api_key:
                return idx
        return -1

    def diagnostics_snapshot(self) -> dict[str, Any]:
        """Return lightweight runtime diagnostics for logging/reporting."""

        key_label = "N/A"
        if self._last_used_key_index > 0:
            if self._last_used_key_index == 1:
                key_label = "GEMINI_API_KEY"
            else:
                key_label = f"GEMINI_API_KEY_{self._last_used_key_index - 1}"

        return {
            "total_requests": int(self._request_count),
            "last_key_label": key_label,
        }

    def _cache_key(self, prefix: str, payload: Any) -> str:
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return f"{prefix}:{digest}"

    def _extract_json(self, text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json", "", 1).strip()

        if cleaned.startswith("{") and cleaned.endswith("}"):
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return None

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return None

    def _is_retryable_error(self, exc: Exception) -> bool:
        text = str(exc).lower()
        error_type = type(exc).__name__.lower()

        if "timeout" in text or "deadline" in text or "timed out" in text:
            return True
        if "resourceexhausted" in error_type or "quota" in text or "429" in text:
            return True
        if "unavailable" in text or "connection" in text or "network" in text:
            return True
        if "500" in text or "502" in text or "503" in text or "504" in text:
            return True

        return False

    def _safe_int(self, value: Any, *, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(float(value))
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, parsed))
