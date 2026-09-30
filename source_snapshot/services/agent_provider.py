"""Production Qwen provider boundary for the V1 Agent backend.

Only this module knows the OpenAI-compatible wire format. AgentService sees
provider-neutral contracts and never receives credentials or HTTP payloads.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import json
import math
import os
import time
from typing import Any, Protocol
from urllib.parse import urlparse

try:  # Optional at import time; FakeQwenTransport remains usable offline.
    import httpx
except ImportError:  # pragma: no cover - exercised only in minimal runtimes
    class _HttpxFallback:
        class TransportError(Exception): pass
        class TimeoutException(Exception): pass
        class ConnectError(Exception): pass
        class ReadError(Exception): pass
        class WriteError(Exception): pass
        class Client:
            def __init__(self, *args, **kwargs): raise RuntimeError("httpx is required for network provider transport")
    httpx = _HttpxFallback()

from services.agent_contracts import (
    AgentAlternative,
    AgentNeedInput,
    AgentRequest,
    ComponentTier,
    ContractError,
    NeedInputCode,
    ProviderCandidateDraft,
    request_digest,
)
from services.agent_contracts import safe_fingerprint


QWEN_RESPONSE_SCHEMA_VERSION = "qwen-agent-response-v1"
DEFAULT_QWEN_MODEL = "qwen-plus"
DEFAULT_QWEN_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_QWEN_TIMEOUT_SECONDS = DEFAULT_QWEN_REQUEST_TIMEOUT_SECONDS
DEFAULT_QWEN_CONNECT_TIMEOUT_SECONDS = 5.0
DEFAULT_QWEN_MAX_RESPONSE_BYTES = 1_000_000
_SUPPORTED_WORKFLOWS = frozenset({"single_gene", "multi_tu", "pathway"})
_PROHIBITED_DETAIL_KEYS = (
    "sequence", "nucleotide", "nucleotide_truth", "component_identity",
    "component_id", "component_tier", "tier", "evidence", "provenance",
    "license", "rights", "host_scope", "host", "validation",
    "deterministic_validation", "human_confirmation", "adoption",
    "formal_adoption", "lifecycle_state", "full_auto",
)
_SAFE_RETRY_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504})
_TRANSIENT_TRANSPORT_EXCEPTIONS = (
    httpx.TimeoutException,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
)


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ProviderFailureCode(_StringEnum):
    REQUEST_SCHEMA_MISMATCH = "request_schema_mismatch"
    CONFIGURATION_MISSING = "configuration_missing"
    API_KEY_MISSING = "api_key_missing"
    TRANSPORT_TIMEOUT = "transport_timeout"
    TRANSPORT_CONNECTION_FAILURE = "transport_connection_failure"
    HTTP_FAILURE = "http_failure"
    RATE_LIMIT = "rate_limit"
    MALFORMED_JSON = "malformed_json"
    SCHEMA_MISMATCH = "schema_mismatch"
    EMPTY_MODEL_RESPONSE = "empty_model_response"
    OVERSIZED_RESPONSE = "oversized_response"
    UNSUPPORTED_MODEL_RESPONSE = "unsupported_model_response"
    PROVIDER_METADATA_MISSING = "provider_metadata_missing"
    GOVERNANCE_VIOLATION = "governance_violation"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


class ProviderResponseStatus(_StringEnum):
    CANDIDATES = "CANDIDATES"
    NEEDS_INPUT = "NEEDS_INPUT"


class StructuredOutputMode(_StringEnum):
    JSON_SCHEMA = "json_schema"
    JSON_OBJECT = "json_object"


class ProviderError(RuntimeError):
    """Typed, secret-free provider failure surfaced to AgentService."""

    def __init__(
        self,
        code: ProviderFailureCode | str,
        message: str,
        *,
        response_id: str | None = None,
        retryable: bool = False,
        structured_output_validation: str | None = None,
    ) -> None:
        try:
            normalized = ProviderFailureCode(code)
        except (TypeError, ValueError):
            normalized = ProviderFailureCode.PROVIDER_UNAVAILABLE
        self.code = normalized.value
        # Provider-controlled text and identifiers are not public evidence.
        # Expose only the stable code/message and a one-way correlation value.
        self.message = _safe_provider_message(normalized)
        self.response_id = safe_fingerprint(_optional_string(response_id, "response_id"))
        self.retryable = bool(retryable)
        if structured_output_validation is None:
            parsing_failures = {
                ProviderFailureCode.MALFORMED_JSON,
                ProviderFailureCode.SCHEMA_MISMATCH,
                ProviderFailureCode.UNSUPPORTED_MODEL_RESPONSE,
                ProviderFailureCode.PROVIDER_METADATA_MISSING,
                ProviderFailureCode.GOVERNANCE_VIOLATION,
            }
            structured_output_validation = "FAIL" if normalized in parsing_failures else "NOT_RUN"
        if structured_output_validation not in {"NOT_RUN", "FAIL"}:
            raise ValueError("provider failure structured_output_validation is unsupported.")
        self.structured_output_validation = structured_output_validation
        super().__init__(self.message)


def _safe_provider_message(code: ProviderFailureCode | str) -> str:
    """Return a stable public message for failures crossing the transport boundary."""
    try:
        normalized = ProviderFailureCode(code)
    except (TypeError, ValueError):
        normalized = ProviderFailureCode.PROVIDER_UNAVAILABLE
    return {
        ProviderFailureCode.REQUEST_SCHEMA_MISMATCH: "Qwen provider request failed schema validation.",
        ProviderFailureCode.CONFIGURATION_MISSING: "Qwen production transport requires a configured base URL.",
        ProviderFailureCode.API_KEY_MISSING: "Qwen production transport requires its configured API key source.",
        ProviderFailureCode.TRANSPORT_TIMEOUT: "Qwen transport timed out after bounded retries.",
        ProviderFailureCode.TRANSPORT_CONNECTION_FAILURE: "Qwen transport failed safely.",
        ProviderFailureCode.HTTP_FAILURE: "Qwen transport returned an HTTP failure.",
        ProviderFailureCode.RATE_LIMIT: "Qwen transport was rate limited after bounded retries.",
        ProviderFailureCode.MALFORMED_JSON: "Qwen structured content was not valid JSON.",
        ProviderFailureCode.SCHEMA_MISMATCH: "Qwen structured content did not match the response schema.",
        ProviderFailureCode.EMPTY_MODEL_RESPONSE: "Qwen returned an empty model response.",
        ProviderFailureCode.OVERSIZED_RESPONSE: "Qwen response exceeded the configured size limit.",
        ProviderFailureCode.UNSUPPORTED_MODEL_RESPONSE: "Qwen returned an unsupported model response.",
        ProviderFailureCode.PROVIDER_METADATA_MISSING: "Qwen provider metadata was missing or inconsistent.",
        ProviderFailureCode.GOVERNANCE_VIOLATION: "Qwen response failed governance checks.",
        ProviderFailureCode.PROVIDER_UNAVAILABLE: "Qwen provider failed safely.",
    }[normalized]


@dataclass(frozen=True)
class _SafeTransportFailure:
    code: ProviderFailureCode | str
    message: str
    response_id: str | None = None
    retryable: bool = False


@dataclass(frozen=True)
class RetryPolicy:
    max_retries: int = 2
    backoff_seconds: float = 0.25
    retry_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)

    def __post_init__(self) -> None:
        if isinstance(self.max_retries, bool) or not isinstance(self.max_retries, int) or not 0 <= self.max_retries <= 3:
            raise ValueError("Qwen retry max_retries must be an integer from 0 to 3.")
        if isinstance(self.backoff_seconds, bool) or not isinstance(self.backoff_seconds, (int, float)) or self.backoff_seconds < 0:
            raise ValueError("Qwen retry backoff_seconds must be non-negative.")
        codes = tuple(self.retry_status_codes)
        if not codes or any(isinstance(code, bool) or not isinstance(code, int) or code not in _SAFE_RETRY_STATUS_CODES for code in codes):
            raise ValueError("Qwen retry status codes must be a bounded transient-status allowlist.")
        if len(set(codes)) != len(codes):
            raise ValueError("Qwen retry status codes must be unique.")
        object.__setattr__(self, "backoff_seconds", float(self.backoff_seconds))
        object.__setattr__(self, "retry_status_codes", codes)


@dataclass(frozen=True)
class QwenConfig:
    provider: str = "qwen"
    model: str = DEFAULT_QWEN_MODEL
    base_url: str = ""
    api_key_env: str = "DASHSCOPE_API_KEY"
    request_timeout_seconds: float = DEFAULT_QWEN_REQUEST_TIMEOUT_SECONDS
    connect_timeout_seconds: float = DEFAULT_QWEN_CONNECT_TIMEOUT_SECONDS
    max_response_bytes: int = DEFAULT_QWEN_MAX_RESPONSE_BYTES
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    structured_output_mode: StructuredOutputMode | str = StructuredOutputMode.JSON_OBJECT
    schema_version: str = QWEN_RESPONSE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        provider = _required_string(self.provider, "provider")
        model = _required_string(self.model, "model")
        base_url = _optional_string(self.base_url, "base_url") or ""
        api_key_env = _required_string(self.api_key_env, "api_key_env")
        if provider != "qwen":
            raise ValueError("QwenConfig provider must be 'qwen'.")
        if base_url:
            parsed = urlparse(base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError("Qwen base_url must be an absolute HTTP(S) URL.")
        for name, value in (
            ("request_timeout_seconds", self.request_timeout_seconds),
            ("connect_timeout_seconds", self.connect_timeout_seconds),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise ValueError(f"Qwen {name} must be positive.")
        if isinstance(self.max_response_bytes, bool) or not isinstance(self.max_response_bytes, int) or self.max_response_bytes <= 0:
            raise ValueError("Qwen max_response_bytes must be a positive integer.")
        if not isinstance(self.retry_policy, RetryPolicy):
            raise ValueError("Qwen retry_policy must be RetryPolicy.")
        try:
            mode = StructuredOutputMode(self.structured_output_mode)
        except (TypeError, ValueError) as exc:
            raise ValueError("Qwen structured_output_mode is unsupported.") from exc
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "model", model)
        object.__setattr__(self, "base_url", base_url.rstrip("/"))
        object.__setattr__(self, "api_key_env", api_key_env)
        object.__setattr__(self, "request_timeout_seconds", float(self.request_timeout_seconds))
        object.__setattr__(self, "connect_timeout_seconds", float(self.connect_timeout_seconds))
        object.__setattr__(self, "structured_output_mode", mode)
        object.__setattr__(self, "schema_version", _required_string(self.schema_version, "schema_version"))

    @property
    def base_endpoint(self) -> str:
        """Compatibility name for the original provider-neutral preparation."""
        return self.base_url

    @property
    def timeout_seconds(self) -> float:
        """Compatibility name for the original single-timeout contract."""
        return self.request_timeout_seconds

    @classmethod
    def from_env(cls) -> "QwenConfig":
        return cls(
            model=os.getenv("AGENT_QWEN_MODEL", DEFAULT_QWEN_MODEL),
            base_url=os.getenv("AGENT_QWEN_BASE_URL", os.getenv("AGENT_QWEN_BASE_ENDPOINT", "")),
            api_key_env=os.getenv("AGENT_QWEN_API_KEY_ENV", "DASHSCOPE_API_KEY"),
            request_timeout_seconds=(
                _env_float("AGENT_QWEN_REQUEST_TIMEOUT_SECONDS", DEFAULT_QWEN_REQUEST_TIMEOUT_SECONDS)
                if "AGENT_QWEN_REQUEST_TIMEOUT_SECONDS" in os.environ
                else _env_float("AGENT_QWEN_TIMEOUT_SECONDS", DEFAULT_QWEN_REQUEST_TIMEOUT_SECONDS)
            ),
            connect_timeout_seconds=_env_float("AGENT_QWEN_CONNECT_TIMEOUT_SECONDS", DEFAULT_QWEN_CONNECT_TIMEOUT_SECONDS),
            max_response_bytes=_env_int("AGENT_QWEN_MAX_RESPONSE_BYTES", DEFAULT_QWEN_MAX_RESPONSE_BYTES),
            retry_policy=RetryPolicy(
                max_retries=_env_int("AGENT_QWEN_MAX_RETRIES", 2),
                backoff_seconds=_env_float("AGENT_QWEN_RETRY_BACKOFF_SECONDS", 0.25),
            ),
            structured_output_mode=os.getenv("AGENT_QWEN_STRUCTURED_OUTPUT_MODE", StructuredOutputMode.JSON_OBJECT.value),
        )


@dataclass(frozen=True)
class ProviderExplanationMetadata:
    confidence: float | None = None
    basis: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
                raise ValueError("provider confidence must be numeric.")
            confidence = float(self.confidence)
            if not 0 <= confidence <= 1:
                raise ValueError("provider confidence must be between 0 and 1.")
            object.__setattr__(self, "confidence", confidence)
        object.__setattr__(self, "basis", _string_tuple(self.basis, "basis"))


@dataclass(frozen=True)
class ProviderMetadata:
    provider: str
    model: str
    request_id: str
    schema_version: str
    transport: str = "custom"
    response_id: str | None = None
    structured_output_validation: str = "NOT_RUN"

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _required_string(self.provider, "provider"))
        object.__setattr__(self, "model", _required_string(self.model, "model"))
        if self.request_id:
            object.__setattr__(self, "request_id", _required_string(self.request_id, "request_id"))
        object.__setattr__(self, "schema_version", _required_string(self.schema_version, "schema_version"))
        object.__setattr__(self, "transport", _required_string(self.transport, "transport"))
        object.__setattr__(self, "response_id", safe_fingerprint(_optional_string(self.response_id, "response_id")))
        if self.structured_output_validation not in {"NOT_RUN", "PASS", "FAIL"}:
            raise ValueError("structured_output_validation is unsupported.")

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
            "schema_version": self.schema_version,
            "transport": self.transport,
            "response_id": self.response_id,
            "structured_output_validation": self.structured_output_validation,
        }


@dataclass(frozen=True)
class ProviderGenerationResponse:
    status: ProviderResponseStatus
    interpretation: str
    missing_inputs: tuple[AgentNeedInput, ...]
    candidates: tuple[ProviderCandidateDraft, ...]
    alternatives: tuple[AgentAlternative, ...]
    explanation: str
    explanation_metadata: ProviderExplanationMetadata
    metadata: ProviderMetadata

    def __post_init__(self) -> None:
        if not isinstance(self.status, ProviderResponseStatus):
            raise ValueError("provider response status must be ProviderResponseStatus.")
        if any(not isinstance(item, AgentNeedInput) for item in self.missing_inputs):
            raise ValueError("provider missing_inputs must contain AgentNeedInput values.")
        if any(not isinstance(item, ProviderCandidateDraft) for item in self.candidates):
            raise ValueError("provider candidates must contain ProviderCandidateDraft values.")
        if any(not isinstance(item, AgentAlternative) for item in self.alternatives):
            raise ValueError("provider alternatives must contain AgentAlternative values.")
        if self.status is ProviderResponseStatus.CANDIDATES and (not self.candidates or self.missing_inputs):
            raise ValueError("candidate provider response has inconsistent fields.")
        if self.status is ProviderResponseStatus.NEEDS_INPUT and (not self.missing_inputs or self.candidates or self.alternatives):
            raise ValueError("needs-input provider response has inconsistent fields.")
        if not isinstance(self.explanation_metadata, ProviderExplanationMetadata):
            raise ValueError("provider explanation_metadata has an invalid type.")
        if not isinstance(self.metadata, ProviderMetadata):
            raise ValueError("provider metadata has an invalid type.")


class ModelProvider(Protocol):
    @property
    def metadata(self) -> ProviderMetadata: ...

    def generate(self, request: AgentRequest) -> ProviderGenerationResponse: ...


@dataclass(frozen=True)
class QwenProviderRequest:
    request_id: str
    model: str
    user_supplied_facts: Mapping[str, Any]
    deterministic_ubd_facts: Mapping[str, Any]
    component_governance: tuple[Mapping[str, Any], ...]
    model_task: tuple[str, ...]
    model_prohibitions: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "prompt_schema_version": "agent-v1-prompt",
            "request_id": self.request_id,
            "sections": {
                "USER-SUPPLIED FACTS": dict(self.user_supplied_facts),
                "DETERMINISTIC UBD FACTS": dict(self.deterministic_ubd_facts),
                "COMPONENT GOVERNANCE": [dict(item) for item in self.component_governance],
                "MODEL TASK": list(self.model_task),
                "MODEL PROHIBITIONS": list(self.model_prohibitions),
            },
        }


@dataclass(frozen=True)
class QwenTransportResponse:
    content: str
    response_id: str | None
    model: str

    def __post_init__(self) -> None:
        if not isinstance(self.content, str):
            raise ValueError("Qwen transport content must be text.")
        object.__setattr__(self, "response_id", _optional_string(self.response_id, "response_id"))
        object.__setattr__(self, "model", _required_string(self.model, "model"))


class QwenTransport(Protocol):
    name: str

    def generate(self, request: QwenProviderRequest, *, config: QwenConfig) -> QwenTransportResponse: ...


QWEN_RESPONSE_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "status", "interpretation", "missing_inputs", "candidates", "alternatives", "explanation"],
    "properties": {
        "schema_version": {"type": "string", "const": QWEN_RESPONSE_SCHEMA_VERSION},
        "status": {"type": "string", "enum": [item.value for item in ProviderResponseStatus]},
        "interpretation": {"type": "string", "minLength": 1},
        "missing_inputs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["code", "field", "message", "blocking", "details"],
                "properties": {
                    "code": {"type": "string", "enum": [item.value for item in NeedInputCode]},
                    "field": {"type": "string", "minLength": 1},
                    "message": {"type": "string", "minLength": 1},
                    "blocking": {"type": "boolean"},
                    "details": {"type": "object"},
                },
            },
        },
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["candidate_id", "evidence_references", "unresolved_requirements", "rationale"],
                "properties": {
                    "candidate_id": {"type": "string", "pattern": "^[A-Za-z0-9_.:-]+$"},
                    "evidence_references": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
                    "unresolved_requirements": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
                    "rationale": {"type": "string", "minLength": 1},
                },
            },
        },
        "alternatives": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["alternative_id", "candidate_id", "rationale", "differences"],
                "properties": {
                    "alternative_id": {"type": "string", "pattern": "^[A-Za-z0-9_.:-]+$"},
                    "candidate_id": {"type": "string", "pattern": "^[A-Za-z0-9_.:-]+$"},
                    "rationale": {"type": "string", "minLength": 1},
                    "differences": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
                },
            },
        },
        "explanation": {"type": "string", "minLength": 1},
        "explanation_metadata": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "basis": {"type": "array", "items": {"type": "string", "minLength": 1}, "uniqueItems": True},
            },
        },
    },
}


class FakeQwenTransport:
    name = "fake"

    def __init__(self, response: Any = None, *, response_id: str | None = "fake-response-1") -> None:
        self.response = response
        self.response_id = response_id
        self.calls: list[QwenProviderRequest] = []

    def generate(self, request: QwenProviderRequest, *, config: QwenConfig) -> QwenTransportResponse:
        self.calls.append(request)
        if isinstance(self.response, BaseException):
            raise self.response
        response = self.response if self.response is not None else _default_fake_response(request, config)
        content = response if isinstance(response, str) else json.dumps(response, sort_keys=True)
        return QwenTransportResponse(content, self.response_id, config.model)


class OpenAICompatibleQwenTransport:
    """Production HTTP transport requiring an explicitly configured base URL."""

    name = "openai-compatible-http"

    def __init__(self, *, client: httpx.Client | None = None, sleeper: Callable[[float], None] = time.sleep) -> None:
        self._client = client
        self._sleeper = sleeper

    def generate(self, request: QwenProviderRequest, *, config: QwenConfig) -> QwenTransportResponse:
        outcome = self._generate_safely(request, config)
        if isinstance(outcome, _SafeTransportFailure):
            code, message, response_id, retryable = outcome.code, outcome.message, outcome.response_id, outcome.retryable
            del self, request, config, outcome
            raise ProviderError(code, message, response_id=response_id, retryable=retryable)
        return outcome

    def _generate_safely(self, request: QwenProviderRequest, config: QwenConfig) -> QwenTransportResponse | _SafeTransportFailure:
        """Own credentials and HTTP objects only inside an exception firewall.

        No exception raised from this frame escapes.  In particular, the
        authenticated request and API key never become reachable from the
        public ProviderError traceback or its exception graph.
        """
        if not config.base_url:
            return _SafeTransportFailure(ProviderFailureCode.CONFIGURATION_MISSING, "Qwen production transport requires a configured base URL.")
        api_key = os.getenv(config.api_key_env)
        if not api_key:
            return _SafeTransportFailure(ProviderFailureCode.API_KEY_MISSING, "Qwen production transport requires its configured API key source.")
        timeout = httpx.Timeout(config.request_timeout_seconds, connect=config.connect_timeout_seconds)
        client = self._client or httpx.Client()
        try:
            response = self._post_with_retries(client, request, config, api_key, timeout)
            if isinstance(response, _SafeTransportFailure):
                return response
            try:
                return self._adapt_response(response, config)
            except ProviderError as exc:
                return _SafeTransportFailure(exc.code, _safe_provider_message(exc.code), exc.response_id, exc.retryable)
            except Exception:
                return _SafeTransportFailure(ProviderFailureCode.UNSUPPORTED_MODEL_RESPONSE, "Qwen HTTP response envelope could not be adapted safely.")
        except Exception:
            return _SafeTransportFailure(ProviderFailureCode.PROVIDER_UNAVAILABLE, "Qwen transport failed safely.")
        finally:
            if self._client is None:
                client.close()

    def _post_with_retries(
        self, client: httpx.Client, request: QwenProviderRequest,
        config: QwenConfig, api_key: str, timeout: httpx.Timeout,
    ) -> httpx.Response | _SafeTransportFailure:
        attempts = config.retry_policy.max_retries + 1
        for attempt in range(attempts):
            try:
                with client.stream(
                    "POST", f"{config.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=_openai_request_body(request, config), timeout=timeout,
                ) as response:
                    if response.status_code in config.retry_policy.retry_status_codes and attempt + 1 < attempts:
                        self._backoff(config, attempt)
                        continue
                    response_id = response.headers.get("x-request-id")
                    if response.status_code == 429:
                        return _SafeTransportFailure(ProviderFailureCode.RATE_LIMIT, "Qwen transport was rate limited after bounded retries.", response_id, True)
                    if response.status_code >= 400:
                        return _SafeTransportFailure(ProviderFailureCode.HTTP_FAILURE, f"Qwen transport returned HTTP status {response.status_code}.", response_id, response.status_code >= 500)
                    bounded_content = _read_bounded_response(response, config.max_response_bytes)
                    # iter_bytes() has decoded the body. Retaining wire encoding
                    # headers would make the detached response decode it again.
                    detached_headers = {
                        key: value
                        for key, value in response.headers.items()
                        if key.lower() not in {"content-encoding", "content-length", "transfer-encoding"}
                    }
                    # Never carry response.request into the returned object.
                    return httpx.Response(response.status_code, headers=detached_headers, content=bounded_content)
            except ProviderError as exc:
                return _SafeTransportFailure(exc.code, _safe_provider_message(exc.code), exc.response_id, exc.retryable)
            except _TRANSIENT_TRANSPORT_EXCEPTIONS as exc:
                if attempt + 1 < attempts:
                    self._backoff(config, attempt)
                    continue
                code = ProviderFailureCode.TRANSPORT_TIMEOUT if isinstance(exc, httpx.TimeoutException) else ProviderFailureCode.TRANSPORT_CONNECTION_FAILURE
                message = "Qwen transport timed out after bounded retries." if code is ProviderFailureCode.TRANSPORT_TIMEOUT else "Qwen transport could not connect after bounded retries."
                return _SafeTransportFailure(code, message, retryable=True)
            except httpx.TransportError:
                # Protocol/configuration errors are not transient and receive
                # exactly one attempt, even when max_retries is configured.
                return _SafeTransportFailure(ProviderFailureCode.TRANSPORT_CONNECTION_FAILURE, "Qwen transport failed with a non-transient connection error.")
            except Exception:
                return _SafeTransportFailure(ProviderFailureCode.PROVIDER_UNAVAILABLE, "Qwen transport failed safely.")
        return _SafeTransportFailure(ProviderFailureCode.PROVIDER_UNAVAILABLE, "Qwen transport exhausted its retry policy.")

    def _backoff(self, config: QwenConfig, attempt: int) -> None:
        delay = config.retry_policy.backoff_seconds * (2**attempt)
        if delay:
            self._sleeper(delay)

    @staticmethod
    def _adapt_response(response: httpx.Response, config: QwenConfig) -> QwenTransportResponse:
        try:
            declared_size = int(response.headers.get("content-length", "0"))
        except ValueError:
            declared_size = 0
        if declared_size > config.max_response_bytes or len(response.content) > config.max_response_bytes:
            raise ProviderError(ProviderFailureCode.OVERSIZED_RESPONSE, "Qwen response exceeded the configured size limit.")
        if not response.content.strip():
            raise ProviderError(ProviderFailureCode.EMPTY_MODEL_RESPONSE, "Qwen returned an empty HTTP response.")
        try:
            envelope = response.json()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            raise ProviderError(ProviderFailureCode.UNSUPPORTED_MODEL_RESPONSE, "Qwen returned an unreadable HTTP response envelope.") from None
        if not isinstance(envelope, Mapping):
            raise ProviderError(ProviderFailureCode.UNSUPPORTED_MODEL_RESPONSE, "Qwen HTTP response envelope must be an object.")
        response_id = _optional_string(envelope.get("id"), "response id")
        model = _optional_string(envelope.get("model"), "response model")
        if not model:
            raise ProviderError(ProviderFailureCode.PROVIDER_METADATA_MISSING, "Qwen HTTP response did not include model metadata.", response_id=response_id)
        choices = envelope.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], Mapping):
            raise ProviderError(ProviderFailureCode.UNSUPPORTED_MODEL_RESPONSE, "Qwen HTTP response must contain exactly one structured choice.", response_id=response_id)
        message = choices[0].get("message")
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str):
            raise ProviderError(ProviderFailureCode.UNSUPPORTED_MODEL_RESPONSE, "Qwen structured choice did not contain text JSON content.", response_id=response_id)
        if not content.strip():
            raise ProviderError(ProviderFailureCode.EMPTY_MODEL_RESPONSE, "Qwen returned empty structured content.", response_id=response_id)
        return QwenTransportResponse(content, response_id, model)


class QwenProvider:
    """Strict Qwen adapter with production HTTP transport by default."""

    def __init__(self, *, config: QwenConfig | None = None, transport: QwenTransport | None = None) -> None:
        self.config = config or QwenConfig.from_env()
        self.transport = transport or OpenAICompatibleQwenTransport()
        self._metadata = ProviderMetadata(
            self.config.provider, self.config.model, "", self.config.schema_version,
            self.transport.name,
        )

    @property
    def metadata(self) -> ProviderMetadata:
        return self._metadata

    def generate(self, request: AgentRequest) -> ProviderGenerationResponse:
        provider_request = _provider_request(request, self.config.model)
        _validate_json_structure(provider_request.as_dict())
        outcome = _safe_provider_response(self.transport, provider_request, request, self.config)
        if isinstance(outcome, _SafeTransportFailure):
            code, message, response_id, retryable = outcome.code, outcome.message, outcome.response_id, outcome.retryable
            del self, provider_request, request, outcome
            raise ProviderError(code, message, response_id=response_id, retryable=retryable)
        response = outcome
        self._metadata = response.metadata
        return response

    def generate_candidates(self, request: AgentRequest) -> ProviderGenerationResponse:
        return self.generate(request)


def _safe_provider_response(
    transport: QwenTransport,
    provider_request: QwenProviderRequest,
    request: AgentRequest,
    config: QwenConfig,
) -> ProviderGenerationResponse | _SafeTransportFailure:
    """Parse a transport response without exposing its raw object in errors."""
    try:
        raw = transport.generate(provider_request, config=config)
        if not isinstance(raw, QwenTransportResponse):
            return _SafeTransportFailure(ProviderFailureCode.UNSUPPORTED_MODEL_RESPONSE, "Qwen transport returned an unsupported response type.")
        if raw.model != config.model:
            return _SafeTransportFailure(
                ProviderFailureCode.PROVIDER_METADATA_MISSING,
                "Qwen transport model metadata did not match the configured model.",
                raw.response_id,
            )
        try:
            envelope = _decode_json(raw)
            return _parse_response(envelope, request, config, transport.name, raw.response_id)
        except ProviderError as exc:
            return _SafeTransportFailure(exc.code, _safe_provider_message(exc.code), exc.response_id, exc.retryable)
        except Exception:
            return _SafeTransportFailure(ProviderFailureCode.PROVIDER_UNAVAILABLE, "Qwen provider response failed safely.")
    except ProviderError as exc:
        return _SafeTransportFailure(exc.code, _safe_provider_message(exc.code), exc.response_id, exc.retryable)
    except Exception:
        return _SafeTransportFailure(ProviderFailureCode.PROVIDER_UNAVAILABLE, "Qwen provider transport failed safely.")


def _provider_request(request: AgentRequest, model: str) -> QwenProviderRequest:
    governance = tuple(
        {
            "component_id": ref.component_id,
            "role": ref.role,
            "tier": ref.tier.value,
            "sequence_reference": ref.sequence_reference,
            "evidence_references": list(ref.evidence_references),
            "provenance_references": list(ref.provenance_references),
            "direct_adoption_allowed": ref.tier is ComponentTier.DIRECT_USE,
        }
        for ref in request.component_references
    )
    return QwenProviderRequest(
        request.request_id,
        model,
        {
            "workflow_type": request.workflow_type,
            "host": request.host,
            "user_intent": request.user_intent,
            "cds_or_reference_input": request.cds_or_reference_input,
            "evidence_references": list(request.evidence_references),
            "context": dict(request.context),
        },
        {
            "supported_workflows": sorted(_SUPPORTED_WORKFLOWS),
            "verified_sequence_reference_ids": sorted(request.verified_sequence_references),
            "provider_authority": "advisory_only",
            "required_candidate_initial_state": "AUTO_GENERATED",
            "deterministic_validation_required": True,
            "human_confirmation_required": True,
            "formal_adoption_available": False,
        },
        governance,
        (
            "Interpret the user's design-record intent.",
            "Identify missing inputs or return structured candidate proposals.",
            "Provide alternatives and a concise explanation when useful.",
            "Return only JSON matching the supplied response schema.",
        ),
        (
            "Do not invent nucleotide sequences or component accessions.",
            "Do not invent references, licenses, provenance, or rights.",
            "Do not claim experimental validation or modify Product state.",
            "Do not change host scope or component governance tiers.",
            "Do not claim deterministic validation, human confirmation, or formal adoption.",
            "Do not create or infer catalog admission; preserve request-bound V2 modes.",
        ),
    )


def _openai_request_body(request: QwenProviderRequest, config: QwenConfig) -> dict[str, Any]:
    authority_instruction = (
        "You are an advisory_only BioDesign Studio model provider. Immutable request facts are "
        "supplied by UBD and are intentionally absent from the response schema: workflow_type, "
        "host, user_intent, cds_or_reference_input, and the complete ordered component_references "
        "snapshot. Do not regenerate or add those fields. UBD materializes them from the validated "
        "request, and model text cannot override them. Fill only model-authorized response fields. "
        "Candidate evidence_references may only select a subset of request-authorized evidence IDs. "
        "Do not invent components, evidence, provenance, authority, validation, confirmation, or "
        "adoption claims. Deterministic UBD validation remains authoritative."
    )
    if config.structured_output_mode is StructuredOutputMode.JSON_SCHEMA:
        response_format = {"type": "json_schema", "json_schema": {"name": "ubd_agent_response", "strict": True, "schema": QWEN_RESPONSE_JSON_SCHEMA}}
        system_instruction = (
            f"{authority_instruction} Return JSON only, with no Markdown or code fences, matching "
            "the exact supplied response schema with no extra properties."
        )
    else:
        response_format = {"type": "json_object"}
        required_fields = ", ".join(QWEN_RESPONSE_JSON_SCHEMA["required"])
        optional_fields = ", ".join(
            sorted(set(QWEN_RESPONSE_JSON_SCHEMA["properties"]) - set(QWEN_RESPONSE_JSON_SCHEMA["required"]))
        )
        schema_contract = json.dumps(
            QWEN_RESPONSE_JSON_SCHEMA, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        system_instruction = (
            f"{authority_instruction} Return one JSON object only, "
            "with no Markdown or code fences. The required top-level fields are exactly: "
            f"{required_fields}. The only optional top-level field is: {optional_fields}. "
            "Use the exact field names and no extra top-level fields. The authoritative response "
            f"contract, including required nested fields, types, and allowed enum values, is this JSON Schema: {schema_contract}. "
            "For status CANDIDATES, return at least one candidate and no missing_inputs. For status "
            "NEEDS_INPUT, return at least one missing_inputs item and empty candidates and alternatives. "
            "Do not add properties that are absent from that schema."
        )
    return {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": json.dumps(request.as_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False)},
        ],
        "response_format": response_format,
    }


def _decode_json(response: QwenTransportResponse) -> dict[str, Any]:
    if not response.content.strip():
        raise ProviderError(ProviderFailureCode.EMPTY_MODEL_RESPONSE, "Qwen returned empty structured content.", response_id=response.response_id)
    try:
        value = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise ProviderError(ProviderFailureCode.MALFORMED_JSON, "Qwen structured content was not valid JSON.", response_id=response.response_id) from exc
    if not isinstance(value, Mapping):
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, "Qwen structured content must be an object.", response_id=response.response_id)
    return dict(value)


def _parse_response(
    envelope: Mapping[str, Any], request: AgentRequest, config: QwenConfig,
    transport_name: str, response_id: str | None,
) -> ProviderGenerationResponse:
    required = {"schema_version", "status", "interpretation", "missing_inputs", "candidates", "alternatives", "explanation"}
    _keys(envelope, required, {"explanation_metadata", "metadata"}, "response", response_id)
    if "metadata" in envelope:
        _ignore_legacy_response_metadata(envelope["metadata"], response_id)
    if envelope["schema_version"] != QWEN_RESPONSE_SCHEMA_VERSION:
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, "Qwen response schema version is unsupported.", response_id=response_id)
    try:
        status = ProviderResponseStatus(_provider_string(envelope["status"], "status", response_id))
    except ValueError as exc:
        raise ProviderError(ProviderFailureCode.UNSUPPORTED_MODEL_RESPONSE, "Qwen response status is unsupported.", response_id=response_id) from exc
    interpretation = _provider_string(envelope["interpretation"], "interpretation", response_id)
    explanation = _provider_string(envelope["explanation"], "explanation", response_id)
    missing = tuple(_missing(item, response_id) for item in _list(envelope["missing_inputs"], "missing_inputs", response_id))
    candidates = tuple(_candidate(item, request, response_id) for item in _list(envelope["candidates"], "candidates", response_id))
    alternatives = tuple(_alternative(item, response_id) for item in _list(envelope["alternatives"], "alternatives", response_id))
    if status is ProviderResponseStatus.CANDIDATES and (not candidates or missing):
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, "Qwen candidate response has inconsistent required fields.", response_id=response_id)
    if status is ProviderResponseStatus.NEEDS_INPUT and (not missing or candidates or alternatives):
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, "Qwen needs-input response has inconsistent candidate fields.", response_id=response_id)
    candidate_ids = [item.candidate_id for item in candidates]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, "Qwen candidate identities must be unique.", response_id=response_id)
    alternative_ids = [item.alternative_id for item in alternatives]
    if len(alternative_ids) != len(set(alternative_ids)) or any(item.candidate_id not in set(candidate_ids) for item in alternatives):
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, "Qwen alternatives must be unique and reference returned candidates.", response_id=response_id)
    explanation_metadata = _explanation_metadata(envelope.get("explanation_metadata"), response_id)
    metadata = ProviderMetadata(
        config.provider, config.model, request.request_id,
        QWEN_RESPONSE_SCHEMA_VERSION, transport_name, response_id, "PASS",
    )
    return ProviderGenerationResponse(status, interpretation, missing, candidates, alternatives, explanation, explanation_metadata, metadata)


def _missing(value: Any, response_id: str | None) -> AgentNeedInput:
    raw = _mapping(value, "missing input", response_id)
    _keys(raw, {"code", "field", "message", "blocking", "details"}, set(), "missing input", response_id)
    if not isinstance(raw["blocking"], bool):
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, "Qwen missing-input blocking must be boolean.", response_id=response_id)
    details = _mapping(raw["details"], "missing-input details", response_id)
    if _contains_prohibited_detail_key(details):
        raise ProviderError(ProviderFailureCode.GOVERNANCE_VIOLATION, "Qwen missing-input details contained an unauthorized authority claim.", response_id=response_id)
    try:
        return AgentNeedInput(NeedInputCode(_required_string(raw["code"], "code")), _required_string(raw["field"], "field"), _required_string(raw["message"], "message"), raw["blocking"], details)
    except (ContractError, TypeError, ValueError) as exc:
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, "Qwen missing input failed contract validation.", response_id=response_id) from exc


def _candidate(value: Any, request: AgentRequest, response_id: str | None) -> ProviderCandidateDraft:
    raw = _mapping(value, "candidate", response_id)
    required = {"candidate_id", "evidence_references", "unresolved_requirements", "rationale"}
    _keys(raw, required, set(), "candidate", response_id)
    evidence = _provider_strings(raw["evidence_references"], "evidence_references", response_id)
    if not set(evidence).issubset(set(request.evidence_references)):
        raise ProviderError(ProviderFailureCode.GOVERNANCE_VIOLATION, "Qwen candidate invented evidence or provenance references.", response_id=response_id)
    try:
        return ProviderCandidateDraft(
            _provider_string(raw["candidate_id"], "candidate_id", response_id), request.workflow_type,
            request.host, request.user_intent, request.cds_or_reference_input, request.component_references,
            evidence, _provider_strings(raw["unresolved_requirements"], "unresolved_requirements", response_id),
            _provider_string(raw["rationale"], "rationale", response_id),
        )
    except (ContractError, TypeError, ValueError) as exc:
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, "Qwen candidate failed contract validation.", response_id=response_id) from exc


def _alternative(value: Any, response_id: str | None) -> AgentAlternative:
    raw = _mapping(value, "alternative", response_id)
    _keys(raw, {"alternative_id", "candidate_id", "rationale", "differences"}, set(), "alternative", response_id)
    try:
        return AgentAlternative(
            _required_string(raw["alternative_id"], "alternative_id"),
            _required_string(raw["candidate_id"], "candidate_id"),
            _required_string(raw["rationale"], "rationale"),
            _provider_strings(raw["differences"], "differences", response_id),
        )
    except (ContractError, TypeError, ValueError) as exc:
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, "Qwen alternative failed contract validation.", response_id=response_id) from exc


def _explanation_metadata(value: Any, response_id: str | None) -> ProviderExplanationMetadata:
    if value is None:
        return ProviderExplanationMetadata()
    raw = _mapping(value, "explanation metadata", response_id)
    _keys(raw, set(), {"confidence", "basis"}, "explanation metadata", response_id)
    try:
        return ProviderExplanationMetadata(raw.get("confidence"), _provider_strings(raw.get("basis", []), "explanation basis", response_id))
    except (TypeError, ValueError) as exc:
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, "Qwen explanation metadata failed validation.", response_id=response_id) from exc


def _ignore_legacy_response_metadata(value: Any, response_id: str | None) -> None:
    """Accept the old field shape without granting its model-authored values authority."""
    raw = _mapping(value, "legacy metadata", response_id)
    _keys(raw, {"provider", "model"}, {"response_id"}, "legacy metadata", response_id)


def _default_fake_response(request: QwenProviderRequest, config: QwenConfig) -> dict[str, Any]:
    user = request.user_supplied_facts
    return {
        "schema_version": QWEN_RESPONSE_SCHEMA_VERSION,
        "status": "CANDIDATES",
        "interpretation": "Prepare a reviewable design-record candidate from supplied facts.",
        "missing_inputs": [],
        "candidates": [{
            "candidate_id": f"candidate-{_request_digest(request)[:16]}",
            "evidence_references": user["evidence_references"], "unresolved_requirements": [],
            "rationale": "Fake provider candidate; deterministic checks remain authoritative.",
        }],
        "alternatives": [],
        "explanation": "The candidate records supplied facts and does not assert biological validation.",
        "explanation_metadata": {"confidence": 0.5, "basis": ["user_supplied_facts"]},
    }


def _request_digest(request: QwenProviderRequest) -> str:
    user = request.user_supplied_facts
    return request_digest(AgentRequest(
        request_id=request.request_id, workflow_type=str(user.get("workflow_type") or ""),
        host=user.get("host"), user_intent=str(user.get("user_intent") or ""),
        cds_or_reference_input=user.get("cds_or_reference_input"),
    ))


def _mapping(value: Any, context: str, response_id: str | None) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, f"Qwen {context} must be an object.", response_id=response_id)
    return dict(value)


def _contains_prohibited_detail_key(value: Any) -> bool:
    """Reject structured authority claims at any nesting depth."""
    if isinstance(value, Mapping):
        for key, nested in value.items():
            normalized = _normalize_authority_key(key)
            if normalized in _PROHIBITED_DETAIL_KEYS:
                return True
            if _contains_prohibited_detail_key(nested):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_prohibited_detail_key(item) for item in value)
    return False


def _normalize_authority_key(value: Any) -> str:
    """Normalize structured authority vocabulary without matching prose."""
    return "_".join(str(value).strip().lower().replace("-", " ").split())


def _read_bounded_response(response: httpx.Response, max_bytes: int) -> bytes:
    """Read response bytes incrementally and stop at the configured bound."""
    try:
        declared_size = int(response.headers.get("content-length", "0"))
    except ValueError:
        declared_size = 0
    if declared_size > max_bytes:
        raise ProviderError(ProviderFailureCode.OVERSIZED_RESPONSE, "Qwen response exceeded the configured size limit.")
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes(chunk_size=min(64 * 1024, max_bytes + 1)):
        total += len(chunk)
        if total > max_bytes:
            raise ProviderError(ProviderFailureCode.OVERSIZED_RESPONSE, "Qwen response exceeded the configured size limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def _list(value: Any, field_name: str, response_id: str | None) -> list[Any]:
    if not isinstance(value, list):
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, f"Qwen {field_name} must be a list.", response_id=response_id)
    return value


def _provider_string(value: Any, field_name: str, response_id: str | None) -> str:
    try:
        return _required_string(value, field_name)
    except (TypeError, ValueError) as exc:
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, f"Qwen {field_name} must be non-empty text.", response_id=response_id) from exc


def _provider_strings(value: Any, field_name: str, response_id: str | None) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, f"Qwen {field_name} must be a list of strings.", response_id=response_id)
    try:
        return _string_tuple(value, field_name)
    except (TypeError, ValueError) as exc:
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, f"Qwen {field_name} must contain unique non-empty strings.", response_id=response_id) from exc


def _keys(value: Mapping[str, Any], required: set[str], optional: set[str], context: str, response_id: str | None) -> None:
    keys = set(value)
    if required - keys:
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, f"Qwen {context} is missing required fields.", response_id=response_id)
    if keys - required - optional:
        raise ProviderError(ProviderFailureCode.SCHEMA_MISMATCH, f"Qwen {context} contains unsupported fields.", response_id=response_id)


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text.")
    return value.strip()


def _optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text or None.")
    return value.strip() or None


def _string_tuple(value: Sequence[str], field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise TypeError(f"{field_name} must be a sequence of strings.")
    items = tuple(_required_string(item, field_name) for item in value)
    if len(items) != len(set(items)):
        raise ValueError(f"{field_name} must contain unique strings.")
    return items


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be numeric.") from exc


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc


def _validate_json_structure(value: Any, *, path: str = "request") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProviderError(ProviderFailureCode.REQUEST_SCHEMA_MISMATCH, f"Qwen provider {path} contains a non-finite number.")
        return
    if isinstance(value, Mapping):
        for key, nested in value.items():
            if not isinstance(key, str):
                raise ProviderError(ProviderFailureCode.REQUEST_SCHEMA_MISMATCH, f"Qwen provider {path} contains a non-string object key.")
            _validate_json_structure(nested, path=f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, nested in enumerate(value):
            _validate_json_structure(nested, path=f"{path}[{index}]")
        return
    raise ProviderError(ProviderFailureCode.REQUEST_SCHEMA_MISMATCH, f"Qwen provider {path} contains a non-JSON value.")


__all__ = [
    "DEFAULT_QWEN_MODEL", "DEFAULT_QWEN_TIMEOUT_SECONDS", "FakeQwenTransport", "ModelProvider",
    "OpenAICompatibleQwenTransport", "ProviderError", "ProviderExplanationMetadata",
    "ProviderFailureCode", "ProviderGenerationResponse", "ProviderMetadata",
    "ProviderResponseStatus", "QWEN_RESPONSE_JSON_SCHEMA", "QWEN_RESPONSE_SCHEMA_VERSION",
    "QwenConfig", "QwenProvider", "QwenProviderRequest", "QwenTransport",
    "QwenTransportResponse", "RetryPolicy", "StructuredOutputMode",
]
