from __future__ import annotations

from types import SimpleNamespace

from services.gemini_service import GeminiService


class _FailingModel:
    def generate_content(self, *args, **kwargs):
        raise RuntimeError("429 quota exceeded")


class _SuccessModel:
    def generate_content(self, *args, **kwargs):
        return SimpleNamespace(text="ok")


class _AuthFailingModel:
    def generate_content(self, *args, **kwargs):
        raise RuntimeError("401 invalid authentication credentials")


def test_gemini_service_rotates_keys_on_failure(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("GEMINI_API_KEY_1", "key-one")
    monkeypatch.setenv("GEMINI_API_KEY_2", "key-two")

    service = GeminiService(model_name="gemini-2.5-flash", max_retries=0)

    def _fake_model_for_key(api_key: str):
        if api_key == "key-one":
            return _FailingModel()
        return _SuccessModel()

    monkeypatch.setattr(service, "_model_for_key", _fake_model_for_key)

    result = service._request_text(prompt="hello", cache_key="unit-test")

    assert result == "ok"


def test_gemini_service_health_false_without_keys(monkeypatch) -> None:
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY_1", raising=False)

    service = GeminiService(model_name="gemini-2.5-flash")

    assert service.enabled is False
    assert service.health_check(force=True) is False


def test_gemini_service_disables_invalid_auth_keys(monkeypatch) -> None:
    service = GeminiService(api_key="bad-key", model_name="gemini-2.5-flash", max_retries=0)
    monkeypatch.setattr(service, "_model_for_key", lambda _api_key: _AuthFailingModel())

    result = service._request_text(prompt="hello", cache_key="auth-fail-test")

    assert result is None
    assert service.enabled is False
    diagnostics = service.diagnostics_snapshot()
    assert diagnostics["disabled_key_count"] == 1
    assert "auth_failed" in str(diagnostics["disabled_reason"])
