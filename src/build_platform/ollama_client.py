"""HTTP client for a locally-running Ollama instance."""
import time

import httpx

from build_platform.schemas import OllamaConfig

# Transient errors worth retrying. HTTP status errors are NOT retried — a 4xx
# won't be fixed by waiting, and a 5xx from Ollama usually indicates a real
# server-side problem the user needs to see.
_TRANSIENT_ERRORS = (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)


class OllamaError(RuntimeError):
    """Base class for Ollama errors."""


class OllamaUnreachableError(OllamaError):
    """Raised when Ollama HTTP server is not reachable."""


class ModelNotPulledError(OllamaError):
    """Raised when a required model is not pulled."""


class OllamaClient:
    def __init__(self, config: OllamaConfig):
        self.config = config
        self._client = httpx.Client(
            base_url=config.url, timeout=config.timeout_seconds,
        )

    def preflight(self, required_models: list[str]) -> None:
        """Verify Ollama is reachable and required models are pulled."""
        try:
            r = self._client.get("/api/tags")
            r.raise_for_status()
        except httpx.ConnectError as e:
            raise OllamaUnreachableError(
                f"Ollama not reachable at {self.config.url}. "
                f"Start it with `ollama serve` and try again."
            ) from e
        except httpx.HTTPError as e:
            raise OllamaUnreachableError(f"Ollama returned HTTP error: {e}") from e

        present = {m["name"] for m in r.json().get("models", [])}
        missing = [m for m in required_models if m not in present]
        if missing:
            cmds = "\n".join(f"  ollama pull {m}" for m in missing)
            raise ModelNotPulledError(
                f"Required Ollama models not pulled: {missing}.\n"
                f"Run:\n{cmds}"
            )

    def chat_with_metrics(
        self, model: str, prompt: str, *, system: str | None = None
    ) -> tuple[str, dict]:
        """Send a one-shot chat request; return (assistant_content, metrics_dict).

        metrics_dict keys: tokens_in (int), tokens_out (int), cost_usd (float).
        cost_usd is always 0.0 for local Ollama models.
        Retries on transient network errors with exponential backoff.
        HTTP status errors are not retried.
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": model, "messages": messages, "stream": False}

        last_transient: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                r = self._client.post("/api/chat", json=payload)
                r.raise_for_status()
                data = r.json()
                content = data["message"]["content"]
                metrics = {
                    "tokens_in": data.get("prompt_eval_count", 0),
                    "tokens_out": data.get("eval_count", 0),
                    "cost_usd": 0.0,
                }
                return content, metrics
            except _TRANSIENT_ERRORS as e:
                last_transient = e
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.retry_backoff_base_seconds * (2 ** attempt))
                    continue
                raise OllamaError(
                    f"Ollama chat failed after {self.config.max_retries} attempts: {e}"
                ) from e
            except httpx.HTTPError as e:
                raise OllamaError(f"Ollama chat failed: {e}") from e
        # Unreachable, but mypy/safety: surface the last transient if loop exits
        raise OllamaError(f"Ollama chat exhausted retries: {last_transient}")

    def chat(self, model: str, prompt: str, *, system: str | None = None) -> str:
        """Send a one-shot chat request; return assistant content.

        Thin wrapper around chat_with_metrics that discards the metrics dict.
        Kept for backward compatibility — existing callers that expect a plain
        string are unaffected.
        """
        text, _ = self.chat_with_metrics(model=model, prompt=prompt, system=system)
        return text
