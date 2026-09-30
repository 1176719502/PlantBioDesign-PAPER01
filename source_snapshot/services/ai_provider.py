"""Provider-neutral, optional AI transport for report drafts."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol
from urllib import error, request


DEFAULT_PROVIDER = "disabled"
DEFAULT_TIMEOUT_SECONDS = 8.0
MAX_REQUEST_BYTES = 64 * 1024


@dataclass(frozen=True)
class ProviderResponse:
    content: Any
    metadata: dict[str, Any]


class AIReportProvider(Protocol):
    def generate_report_draft(self, request_payload: dict[str, Any]) -> ProviderResponse: ...


class DisabledAIReportProvider:
    def generate_report_draft(self, request_payload: dict[str, Any]) -> ProviderResponse:
        del request_payload
        raise RuntimeError("AI report provider is disabled.")


class OllamaAIReportProvider:
    """Small stdlib-only Ollama adapter. It never sends credentials or DNA."""

    def __init__(self, *, endpoint: str | None = None, model: str | None = None, timeout_seconds: float | None = None) -> None:
        self.endpoint = endpoint or os.getenv("AI_REPORT_OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
        self.model = model or os.getenv("AI_REPORT_OLLAMA_MODEL", "")
        self.timeout_seconds = float(timeout_seconds or os.getenv("AI_REPORT_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS))
        if not self.model:
            raise ValueError("AI_REPORT_OLLAMA_MODEL is required for the Ollama provider.")
        if self.timeout_seconds <= 0:
            raise ValueError("AI report timeout must be positive.")

    def generate_report_draft(self, request_payload: dict[str, Any]) -> ProviderResponse:
        body = json.dumps(
            {"model": self.model, "prompt": json.dumps(request_payload, ensure_ascii=True), "format": "json", "stream": False},
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(body) > MAX_REQUEST_BYTES:
            raise ValueError("AI report request exceeds the bounded payload limit.")
        http_request = request.Request(self.endpoint, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with request.urlopen(http_request, timeout=self.timeout_seconds) as response:  # nosec B310: caller configures a local provider
                response_body = response.read(MAX_REQUEST_BYTES + 1)
        except (error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError("Ollama AI report provider is unavailable.") from exc
        if len(response_body) > MAX_REQUEST_BYTES:
            raise RuntimeError("Ollama AI report response exceeds the bounded payload limit.")
        try:
            envelope = json.loads(response_body.decode("utf-8"))
            content = envelope.get("response")
        except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
            raise RuntimeError("Ollama AI report response is malformed.") from exc
        return ProviderResponse(content=content, metadata={"provider": "ollama", "model": self.model})


def configured_ai_report_provider() -> AIReportProvider:
    """Return the configured V1 provider without probing a network endpoint."""
    configured = os.getenv("AI_REPORT_PROVIDER", DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
    if configured == "disabled":
        return DisabledAIReportProvider()
    if configured == "ollama":
        return OllamaAIReportProvider()
    raise ValueError(f"Unsupported AI_REPORT_PROVIDER: {configured!r}.")
