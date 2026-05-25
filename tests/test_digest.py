"""Tests for digest.py."""
from pathlib import Path
from unittest.mock import MagicMock

from build_platform.digest import digest_text, digest_file
from build_platform.ollama_client import OllamaClient
from build_platform.schemas import OllamaConfig, OllamaModels, OllamaPreflight


def _client_returning(content: str) -> OllamaClient:
    config = OllamaConfig(models=OllamaModels(), preflight=OllamaPreflight())
    client = OllamaClient(config)
    client.chat = MagicMock(return_value=content)  # type: ignore
    return client


def test_digest_text_calls_summarizer_model():
    client = _client_returning("- key fact A\n- key fact B")
    out = digest_text(client, "lots of words about A and B", target_tokens=200)
    assert "key fact A" in out
    client.chat.assert_called_once()
    _, kwargs = client.chat.call_args
    assert client.chat.call_args.kwargs["model"] == "llama3.2:3b"


def test_digest_file_writes_output(tmp_path: Path):
    src = tmp_path / "big.log"
    src.write_text("line1\nline2\nline3\n" * 200, encoding="utf-8")
    client = _client_returning("- summary")
    out_path = tmp_path / "digest.md"

    digest_file(client, src, out_path, target_tokens=300)
    assert out_path.read_text(encoding="utf-8").strip() == "- summary"
