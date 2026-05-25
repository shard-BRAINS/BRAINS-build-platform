"""HTTP client for a locally-running Ollama instance."""
import httpx

from build_platform.schemas import OllamaConfig


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

    def chat(self, model: str, prompt: str, *, system: str | None = None) -> str:
        """Send a one-shot chat request; return assistant content."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {"model": model, "messages": messages, "stream": False}
        try:
            r = self._client.post("/api/chat", json=payload)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise OllamaError(f"Ollama chat failed: {e}") from e
        return r.json()["message"]["content"]
