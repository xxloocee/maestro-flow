import pytest

from maestro_flow.providers import resolve_provider


def test_resolve_provider_uses_provider_specific_key(monkeypatch):
    monkeypatch.delenv("MAESTRO_API_KEY", raising=False)
    monkeypatch.setenv("MAESTRO_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")

    profile, api_key, base_url, headers = resolve_provider()

    assert profile.name == "deepseek"
    assert api_key == "test-deepseek-key"
    assert base_url == "https://api.deepseek.com/v1"
    assert headers == {}


def test_resolve_provider_prefers_maestro_key(monkeypatch):
    monkeypatch.setenv("MAESTRO_PROVIDER", "openai")
    monkeypatch.setenv("MAESTRO_API_KEY", "global-key")
    monkeypatch.setenv("OPENAI_API_KEY", "provider-key")

    profile, api_key, _, _ = resolve_provider()

    assert profile.name == "openai"
    assert api_key == "global-key"


def test_resolve_provider_unknown(monkeypatch):
    monkeypatch.setenv("MAESTRO_PROVIDER", "not-real")
    with pytest.raises(RuntimeError):
        resolve_provider()
