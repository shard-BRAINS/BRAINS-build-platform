"""Token-saving pre-digest helper using a small local model."""
from pathlib import Path

from build_platform.ollama_client import OllamaClient

DIGEST_PROMPT = """\
You are a fact-preserving summarizer. Read the input and produce a bulleted summary
under {target_tokens} tokens that preserves every concrete fact, number, identifier,
file path, and decision. Drop prose, rhetorical flourishes, and repeated content.

INPUT:
{content}

OUTPUT (markdown bullets only, no preamble):
"""


def digest_text(client: OllamaClient, content: str, *, target_tokens: int = 1500) -> str:
    """Return a digest of `content` produced by the summarizer model."""
    prompt = DIGEST_PROMPT.format(target_tokens=target_tokens, content=content)
    return client.chat(model=client.config.models.summarizer, prompt=prompt)


def digest_file(
    client: OllamaClient,
    source: Path,
    destination: Path,
    *,
    target_tokens: int = 1500,
) -> Path:
    """Read `source`, digest it, write to `destination`. Returns the destination path."""
    content = source.read_text(encoding="utf-8")
    digest = digest_text(client, content, target_tokens=target_tokens)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(digest, encoding="utf-8")
    return destination
