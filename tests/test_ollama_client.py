"""Tests for ollama_client.py — mock httpx; do not hit a real Ollama."""
from unittest.mock import MagicMock

import httpx
import pytest

from build_platform.ollama_client import (
    OllamaClient,
    OllamaError,
    OllamaUnreachableError,
    ModelNotPulledError,
)
from build_platform.schemas import OllamaConfig, OllamaModels, OllamaPreflight


def _config() -> OllamaConfig:
    return OllamaConfig(
        url="http://localhost:11434",
        timeout_seconds=10,
        models=OllamaModels(),
        preflight=OllamaPreflight(),
    )


def test_preflight_raises_when_server_unreachable(monkeypatch):
    def fake_get(*a, **kw):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    client = OllamaClient(_config())
    with pytest.raises(OllamaUnreachableError):
        client.preflight(required_models=["qwen2.5-coder:7b"])


def test_preflight_raises_when_model_missing(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
    fake_response.raise_for_status.return_value = None

    def fake_get(self, url, **kw):
        return fake_response

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    client = OllamaClient(_config())
    with pytest.raises(ModelNotPulledError) as ei:
        client.preflight(required_models=["qwen2.5-coder:7b"])
    assert "qwen2.5-coder:7b" in str(ei.value)


def test_preflight_passes_when_all_models_present(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = {"models": [
        {"name": "qwen2.5-coder:7b"},
        {"name": "llama3.2:3b"},
    ]}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(httpx.Client, "get", lambda self, url, **kw: fake_response)
    client = OllamaClient(_config())
    client.preflight(required_models=["qwen2.5-coder:7b", "llama3.2:3b"])


def test_chat_returns_content(monkeypatch):
    fake_response = MagicMock()
    fake_response.json.return_value = {"message": {"role": "assistant", "content": "hello"}}
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kw: fake_response)
    client = OllamaClient(_config())
    out = client.chat(model="qwen2.5-coder:7b", prompt="hi")
    assert out == "hello"


def test_chat_raises_ollama_error_on_http_error(monkeypatch):
    fake_response = MagicMock()

    def raise_(): raise httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())

    fake_response.raise_for_status.side_effect = raise_
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kw: fake_response)
    client = OllamaClient(_config())
    with pytest.raises(OllamaError):
        client.chat(model="qwen2.5-coder:7b", prompt="hi")
