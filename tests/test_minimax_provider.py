"""Unit tests for MiniMax provider support."""

from app.core.config import settings
from app.core.llm import LLMProvider
from app.core.llm_router import MODEL_CATALOG, resolve_model_for_stage, _build_client


def test_minimax_is_registered_in_model_catalog():
    assert "minimax" in MODEL_CATALOG
    model_ids = {model["id"] for model in MODEL_CATALOG["minimax"]}
    assert "MiniMax-M2.7" in model_ids
    assert "MiniMax-M2.5-highspeed" in model_ids


def test_minimax_client_uses_dedicated_base_url(monkeypatch):
    monkeypatch.setattr(settings, "minimax_api_key", "minimax-test-key", raising=False)
    monkeypatch.setattr(settings, "minimax_model", "MiniMax-M2.7", raising=False)
    monkeypatch.setattr(settings, "minimax_base_url", "https://api.minimax.io/v1", raising=False)

    client, model = _build_client("minimax", settings.minimax_model)
    assert model == "MiniMax-M2.7"
    assert str(client.base_url).rstrip("/") == "https://api.minimax.io/v1"


def test_global_minimax_keeps_search_on_dedicated_provider(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "minimax", raising=False)
    monkeypatch.setattr(settings, "minimax_model", "MiniMax-M2.7", raising=False)
    monkeypatch.setattr(settings, "perplexity_model", "sonar-pro", raising=False)

    search_provider, search_model, _, _ = resolve_model_for_stage("discover")
    screen_provider, screen_model, _, _ = resolve_model_for_stage("screen")

    assert search_provider == "perplexity"
    assert search_model == "sonar-pro"
    assert screen_provider == "minimax"
    assert screen_model == "MiniMax-M2.7"


def test_llm_provider_initializes_minimax(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "minimax", raising=False)
    monkeypatch.setattr(settings, "minimax_api_key", "minimax-test-key", raising=False)
    monkeypatch.setattr(settings, "minimax_model", "MiniMax-M2.7", raising=False)
    monkeypatch.setattr(settings, "minimax_base_url", "https://api.minimax.io/v1", raising=False)

    provider = LLMProvider()
    assert provider._model == "MiniMax-M2.7"