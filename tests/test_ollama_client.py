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


def test_chat_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr("build_platform.ollama_client.time.sleep", lambda s: None)
    call_count = {"n": 0}
    fake_response = MagicMock()
    fake_response.json.return_value = {"message": {"role": "assistant", "content": "ok"}}
    fake_response.raise_for_status.return_value = None

    def flaky_post(self, url, **kw):
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise httpx.ConnectError("transient")
        return fake_response

    monkeypatch.setattr(httpx.Client, "post", flaky_post)
    client = OllamaClient(_config())
    assert client.chat(model="qwen2.5-coder:7b", prompt="hi") == "ok"
    assert call_count["n"] == 3


def test_chat_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("build_platform.ollama_client.time.sleep", lambda s: None)
    call_count = {"n": 0}

    def always_fails(self, url, **kw):
        call_count["n"] += 1
        raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx.Client, "post", always_fails)
    client = OllamaClient(_config())
    with pytest.raises(OllamaError) as ei:
        client.chat(model="qwen2.5-coder:7b", prompt="hi")
    assert call_count["n"] == 3  # default max_retries
    assert "after 3 attempts" in str(ei.value)


def test_chat_does_not_retry_on_http_status_error(monkeypatch):
    monkeypatch.setattr("build_platform.ollama_client.time.sleep", lambda s: None)
    call_count = {"n": 0}
    fake_response = MagicMock()

    def raise_status():
        raise httpx.HTTPStatusError("500", request=MagicMock(), response=MagicMock())

    fake_response.raise_for_status.side_effect = raise_status

    def post(self, url, **kw):
        call_count["n"] += 1
        return fake_response

    monkeypatch.setattr(httpx.Client, "post", post)
    client = OllamaClient(_config())
    with pytest.raises(OllamaError):
        client.chat(model="qwen2.5-coder:7b", prompt="hi")
    assert call_count["n"] == 1  # no retries on HTTP status errors


# ---------------------------------------------------------------------------
# WP-0015: chat_with_metrics
# ---------------------------------------------------------------------------

def test_chat_with_metrics_parses_prompt_eval_count_and_eval_count(monkeypatch):
    """chat_with_metrics must return (text, dict) with token counts from Ollama response."""
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "message": {"role": "assistant", "content": "hello metrics"},
        "prompt_eval_count": 42,
        "eval_count": 17,
    }
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kw: fake_response)
    client = OllamaClient(_config())
    text, metrics = client.chat_with_metrics(model="qwen2.5-coder:7b", prompt="hi")
    assert text == "hello metrics"
    assert metrics["tokens_in"] == 42
    assert metrics["tokens_out"] == 17


def test_chat_with_metrics_cost_usd_zero_for_ollama(monkeypatch):
    """cost_usd is always 0.0 for local Ollama models."""
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "message": {"role": "assistant", "content": "x"},
        "prompt_eval_count": 10,
        "eval_count": 5,
    }
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kw: fake_response)
    client = OllamaClient(_config())
    _, metrics = client.chat_with_metrics(model="qwen2.5-coder:7b", prompt="hi")
    assert metrics["cost_usd"] == 0.0


def test_chat_with_metrics_falls_back_to_zero_when_counts_absent(monkeypatch):
    """If Ollama omits eval counts (e.g. streaming stub), default to 0 rather than error."""
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "message": {"role": "assistant", "content": "y"},
    }
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kw: fake_response)
    client = OllamaClient(_config())
    text, metrics = client.chat_with_metrics(model="qwen2.5-coder:7b", prompt="hi")
    assert text == "y"
    assert metrics["tokens_in"] == 0
    assert metrics["tokens_out"] == 0


def test_chat_is_backward_compatible_with_new_implementation(monkeypatch):
    """chat() still returns just the text string (thin wrapper around chat_with_metrics)."""
    fake_response = MagicMock()
    fake_response.json.return_value = {
        "message": {"role": "assistant", "content": "compat"},
        "prompt_eval_count": 8,
        "eval_count": 3,
    }
    fake_response.raise_for_status.return_value = None
    monkeypatch.setattr(httpx.Client, "post", lambda self, url, **kw: fake_response)
    client = OllamaClient(_config())
    out = client.chat(model="qwen2.5-coder:7b", prompt="hi")
    assert out == "compat"  # not a tuple
