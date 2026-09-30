"""Provider-neutral V1 Agent contracts.

The Agent layer is intentionally a review and orchestration boundary.  It
does not own nucleotide sequence truth, Component Registry authority, or
Product persistence.  Those remain deterministic services outside this
module.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets


class IntegrityKeyError(RuntimeError):
    pass


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def safe_fingerprint(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    return "sha256:" + hashlib.sha256(str(value).encode("utf-8")).hexdigest()


class AgentIntegrityKey:
    """Resolve service-owned key material outside mutable candidate records."""

    def __init__(self, storage_dir: str | os.PathLike[str]) -> None:
        self.storage_dir = Path(storage_dir)
        self.path = self.storage_dir / ".agent_integrity_secret"

    def read(self) -> bytes:
        configured = os.getenv("UBD_AGENT_INTEGRITY_KEY")
        if configured:
            key = configured.encode("utf-8")
            if len(key) < 32:
                raise IntegrityKeyError("configured Agent integrity key is too short")
            return key
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.exists():
                key = base64.b64decode(self.path.read_bytes(), validate=True)
                if len(key) < 32:
                    raise IntegrityKeyError("stored Agent integrity key is too short")
                return key
            key = secrets.token_bytes(32)
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                key = base64.b64decode(self.path.read_bytes(), validate=True)
                if len(key) < 32:
                    raise IntegrityKeyError("stored Agent integrity key is too short")
                return key
            try:
                os.write(fd, base64.b64encode(key))
            finally:
                os.close(fd)
            return key
        except IntegrityKeyError:
            raise
        except OSError as exc:
            raise IntegrityKeyError("Agent integrity key could not be resolved") from exc


def signed_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): value for key, value in payload.items() if key not in {"integrity", "created_at", "updated_at"}}


def sign_payload(payload: Mapping[str, Any], key: bytes) -> dict[str, Any]:
    digest = hmac.new(key, canonical_json(signed_payload(payload)), hashlib.sha256).hexdigest()
    return {"version": 1, "algorithm": "HMAC-SHA256", "signature": digest}


def verify_payload(payload: Mapping[str, Any], key: bytes) -> bool:
    envelope = payload.get("integrity")
    if not isinstance(envelope, Mapping) or envelope.get("version") != 1 or envelope.get("algorithm") != "HMAC-SHA256":
        return False
    actual = str(envelope.get("signature") or "")
    expected = sign_payload(payload, key)["signature"]
    return bool(actual) and hmac.compare_digest(actual, expected)


SCHEMA_VERSION = "agent-v1-contracts"
PROMPT_SCHEMA_VERSION = "agent-v1-prompt"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_WORKFLOW_TYPES = frozenset({"single_gene", "multi_tu", "pathway"})


class ContractError(ValueError):
    """Raised when a provider-neutral Agent contract is malformed."""


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class AgentRunState(_StringEnum):
    NEW = "NEW"
    NEEDS_INPUT = "NEEDS_INPUT"
    RESULT = "RESULT"
    ALTERNATIVES = "ALTERNATIVES"
    ADOPTION_PREVIEW = "ADOPTION_PREVIEW"
    HUMAN_CONFIRMATION_REQUIRED = "HUMAN_CONFIRMATION_REQUIRED"
    FAILED = "FAILED"


class CandidateState(_StringEnum):
    AUTO_GENERATED = "AUTO_GENERATED"
    VALIDATED_CANDIDATE = "VALIDATED_CANDIDATE"
    USER_ADOPTED = "USER_ADOPTED"
    # Historical names remain readable for old traces, but serialize to the
    # current V1 lifecycle vocabulary.
    MODEL_GENERATED = "AUTO_GENERATED"
    DETERMINISTICALLY_VALIDATED = "VALIDATED_CANDIDATE"
    HUMAN_CONFIRMED = "VALIDATED_CANDIDATE"
    FORMALLY_ADOPTED = "USER_ADOPTED"


class DeterministicValidationStatus(_StringEnum):
    NOT_RUN = "NOT_RUN"
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"


class ComponentTier(_StringEnum):
    DIRECT_USE = "DIRECT_USE"
    USER_SEQUENCE_ASSISTED = "USER_SEQUENCE_ASSISTED"
    REFERENCE_ONLY = "REFERENCE_ONLY"


class ProductLibraryTier(_StringEnum):
    CORE = "CORE"
    REFERENCE = "REFERENCE"
    RETIRED = "RETIRED"


class NeedInputCode(_StringEnum):
    MISSING_CDS_OR_REFERENCE = "MISSING_CDS_OR_REFERENCE"
    MISSING_VERIFIED_SEQUENCE = "MISSING_VERIFIED_SEQUENCE"
    HOST_NOT_SELECTED = "HOST_NOT_SELECTED"
    ASSISTED_COMPONENT_SEQUENCE_REQUIRED = "ASSISTED_COMPONENT_SEQUENCE_REQUIRED"
    COMPONENT_RIGHTS_UNRESOLVED = "COMPONENT_RIGHTS_UNRESOLVED"
    UNSUPPORTED_WORKFLOW = "UNSUPPORTED_WORKFLOW"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"


class AdoptionStatus(_StringEnum):
    PREVIEW_ONLY = "PREVIEW_ONLY"
    HUMAN_CONFIRMATION_REQUIRED = "HUMAN_CONFIRMATION_REQUIRED"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    FORMALLY_ADOPTED = "FORMALLY_ADOPTED"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _tuple_strings(value: Sequence[str] | None, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        raise ContractError(f"{field_name} must be a sequence of strings.")
    items = tuple(_text(item) for item in value)
    if any(not item for item in items):
        raise ContractError(f"{field_name} cannot contain blank values.")
    if len(set(items)) != len(items):
        raise ContractError(f"{field_name} must contain unique values.")
    return items


def _safe_id(value: str, *, field_name: str) -> str:
    normalized = _text(value)
    if not normalized or not _IDENTIFIER_RE.fullmatch(normalized):
        raise ContractError(f"{field_name} must be a non-empty machine-readable identifier.")
    return normalized


def _normalize_trace_key(value: Any) -> str:
    return re.sub(r"[_\s-]+", "_", str(value).strip().lower())


def _assert_trace_secret_free(value: Any, *, field_name: str) -> None:
    """Reject credential-shaped trace data while preserving ordinary prose.

    Trace records are an explicitly JSON-shaped surface.  Arbitrary objects,
    including exception instances, are rejected instead of being inspected by
    ``repr`` because their reachable graph may contain authenticated requests.
    """

    forbidden_keys = {
        "api_key", "apikey", "authorization", "auth_token", "access_token",
        "client_secret", "secret", "password",
    }
    secret_value_patterns = (
        # Require a token-shaped value after Bearer so prose such as
        # ``seed bearer phenotype`` remains valid.
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9][A-Za-z0-9._~+/=-]{11,}"),
        re.compile(r"(?i)\b(?:api[_\s-]?key|access[_\s-]?token|client[_\s-]?secret)\s*[:=]\s*[^\s,;]+"),
        re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9][A-Za-z0-9._~+/=-]{11,}"),
    )

    def visit(item: Any) -> None:
        if item is None or isinstance(item, (str, bool, int, float)):
            if isinstance(item, str) and any(pattern.search(item) for pattern in secret_value_patterns):
                raise ContractError(f"{field_name} cannot contain credential-like values.")
            return
        if isinstance(item, Mapping):
            for key, nested in item.items():
                if not isinstance(key, str):
                    raise ContractError(f"{field_name} must contain string keys only.")
                if _normalize_trace_key(key) in forbidden_keys:
                    raise ContractError(f"{field_name} cannot contain secret-bearing fields.")
                visit(nested)
            return
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for nested in item:
                visit(nested)
            return
        raise ContractError(f"{field_name} must contain only JSON-safe trace values.")

    visit(value)


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ComponentReference:
    """A candidate's reference to a component, never a component authority."""

    component_id: str
    role: str = ""
    tier: ComponentTier | str = ComponentTier.REFERENCE_ONLY
    sequence_reference: str | None = None
    evidence_references: tuple[str, ...] = ()
    provenance_references: tuple[str, ...] = ()
    library_tier: str = "CORE"
    canonical_v2_component_id: str = ""
    sequence_sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _safe_id(self.component_id, field_name="component_id"))
        object.__setattr__(self, "role", _text(self.role))
        try:
            object.__setattr__(self, "tier", ComponentTier(self.tier))
        except (TypeError, ValueError) as exc:
            raise ContractError("component tier is unsupported.") from exc
        object.__setattr__(self, "sequence_reference", _text(self.sequence_reference) or None)
        object.__setattr__(self, "evidence_references", _tuple_strings(self.evidence_references, field_name="evidence_references"))
        object.__setattr__(self, "provenance_references", _tuple_strings(self.provenance_references, field_name="provenance_references"))
        object.__setattr__(self, "library_tier", _text(self.library_tier) or "CORE")
        object.__setattr__(self, "canonical_v2_component_id", _text(self.canonical_v2_component_id) or self.component_id)
        object.__setattr__(self, "sequence_sha256", _text(self.sequence_sha256))


@dataclass(frozen=True)
class ComponentRecord:
    """Minimal adapter record supplied by the reconciled Component repository."""

    component_id: str
    tier: ComponentTier | str
    roles: tuple[str, ...] = ()
    host_scope: tuple[str, ...] = ()
    sequence_available: bool = False
    sequence_verified: bool = False
    rights_status: str = "unresolved"
    admission_status: str = "unresolved"
    evidence_references: tuple[str, ...] = ()
    provenance_references: tuple[str, ...] = ()
    library_tier: str = "CORE"
    canonical_v2_component_id: str = ""
    sequence_sha256: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "component_id", _safe_id(self.component_id, field_name="component_id"))
        try:
            object.__setattr__(self, "tier", ComponentTier(self.tier))
        except (TypeError, ValueError) as exc:
            raise ContractError("component record tier is unsupported.") from exc
        object.__setattr__(self, "roles", _tuple_strings(self.roles, field_name="roles"))
        object.__setattr__(self, "host_scope", _tuple_strings(self.host_scope, field_name="host_scope"))
        if not isinstance(self.sequence_available, bool) or not isinstance(self.sequence_verified, bool):
            raise ContractError("component sequence flags must be boolean.")
        object.__setattr__(self, "rights_status", _text(self.rights_status) or "unresolved")
        object.__setattr__(self, "admission_status", _text(self.admission_status) or "unresolved")
        object.__setattr__(self, "evidence_references", _tuple_strings(self.evidence_references, field_name="evidence_references"))
        object.__setattr__(self, "provenance_references", _tuple_strings(self.provenance_references, field_name="provenance_references"))
        object.__setattr__(self, "library_tier", _text(self.library_tier) or "CORE")
        object.__setattr__(self, "canonical_v2_component_id", _text(self.canonical_v2_component_id) or self.component_id)
        object.__setattr__(self, "sequence_sha256", _text(self.sequence_sha256))


class ComponentRepository(Protocol):
    """Read-only future Component repository adapter; it must not be a writer."""

    def resolve(self, component_id: str) -> ComponentRecord | None: ...


@dataclass(frozen=True)
class AgentRequest:
    request_id: str = field(default_factory=lambda: f"req-{secrets.token_urlsafe(12)}")
    workflow_type: str = ""
    host: str | None = None
    user_intent: str = ""
    cds_or_reference_input: str | Mapping[str, Any] | None = None
    component_references: tuple[ComponentReference, ...] = ()
    evidence_references: tuple[str, ...] = ()
    verified_sequence_references: Mapping[str, str] = field(default_factory=dict)
    project_id: str = ""
    context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _safe_id(self.request_id, field_name="request_id"))
        object.__setattr__(self, "workflow_type", _text(self.workflow_type))
        object.__setattr__(self, "host", _text(self.host) or None)
        object.__setattr__(self, "user_intent", _text(self.user_intent))
        if self.cds_or_reference_input is not None and not isinstance(self.cds_or_reference_input, (str, Mapping)):
            raise ContractError("cds_or_reference_input must be text, an object, or None.")
        refs = tuple(self.component_references or ())
        if any(not isinstance(item, ComponentReference) for item in refs):
            raise ContractError("component_references must contain ComponentReference values.")
        if len({item.component_id for item in refs}) != len(refs):
            raise ContractError("component_references must contain unique component identities.")
        object.__setattr__(self, "component_references", refs)
        object.__setattr__(self, "evidence_references", _tuple_strings(self.evidence_references, field_name="evidence_references"))
        verified = dict(self.verified_sequence_references or {})
        if any(not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip() for key, value in verified.items()):
            raise ContractError("verified_sequence_references must map IDs to non-empty strings.")
        object.__setattr__(self, "verified_sequence_references", verified)
        object.__setattr__(self, "project_id", _text(self.project_id))
        object.__setattr__(self, "context", dict(self.context or {}))


@dataclass(frozen=True)
class AgentNeedInput:
    code: NeedInputCode | str
    field: str
    message: str
    blocking: bool = True
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "code", NeedInputCode(self.code))
        except (TypeError, ValueError) as exc:
            raise ContractError("need-input code is unsupported.") from exc
        object.__setattr__(self, "field", _safe_id(self.field, field_name="field"))
        object.__setattr__(self, "message", _text(self.message))
        if not self.message:
            raise ContractError("need-input message cannot be blank.")
        if not isinstance(self.blocking, bool):
            raise ContractError("need-input blocking must be boolean.")
        object.__setattr__(self, "details", dict(self.details or {}))


@dataclass(frozen=True)
class AgentValidationSummary:
    status: DeterministicValidationStatus | str = DeterministicValidationStatus.NOT_RUN
    checks: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()
    warning_codes: tuple[str, ...] = ()
    authority: str = "deterministic"
    checked_at: str | None = None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "status", DeterministicValidationStatus(self.status))
        except (TypeError, ValueError) as exc:
            raise ContractError("deterministic validation status is unsupported.") from exc
        object.__setattr__(self, "checks", _tuple_strings(self.checks, field_name="checks"))
        object.__setattr__(self, "blocking_reasons", _tuple_strings(self.blocking_reasons, field_name="blocking_reasons"))
        object.__setattr__(self, "warning_codes", _tuple_strings(self.warning_codes, field_name="warning_codes"))
        object.__setattr__(self, "authority", _text(self.authority) or "deterministic")
        object.__setattr__(self, "checked_at", _text(self.checked_at) or None)
        if self.status is DeterministicValidationStatus.PASS and self.blocking_reasons:
            raise ContractError("a passing validation cannot contain blocking reasons.")
        if self.status in {DeterministicValidationStatus.BLOCKED, DeterministicValidationStatus.FAIL} and not self.blocking_reasons:
            raise ContractError("blocked or failed validation requires a blocking reason.")


@dataclass(frozen=True)
class ProviderCandidateDraft:
    """Provider-neutral candidate draft produced by a ModelProvider adapter."""

    candidate_id: str
    workflow_type: str
    host: str | None
    user_intent: str
    cds_or_reference_input: str | Mapping[str, Any] | None
    component_references: tuple[ComponentReference, ...] = ()
    evidence_references: tuple[str, ...] = ()
    unresolved_requirements: tuple[str, ...] = ()
    rationale: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _safe_id(self.candidate_id, field_name="candidate_id"))
        object.__setattr__(self, "workflow_type", _text(self.workflow_type))
        object.__setattr__(self, "host", _text(self.host) or None)
        object.__setattr__(self, "user_intent", _text(self.user_intent))
        refs = tuple(self.component_references or ())
        if any(not isinstance(item, ComponentReference) for item in refs):
            raise ContractError("candidate component_references must contain ComponentReference values.")
        object.__setattr__(self, "component_references", refs)
        object.__setattr__(self, "evidence_references", _tuple_strings(self.evidence_references, field_name="evidence_references"))
        object.__setattr__(self, "unresolved_requirements", _tuple_strings(self.unresolved_requirements, field_name="unresolved_requirements"))
        object.__setattr__(self, "rationale", _text(self.rationale))


@dataclass(frozen=True)
class AgentCandidate:
    candidate_id: str
    workflow_type: str
    host: str | None
    user_intent: str
    cds_or_reference_input: str | Mapping[str, Any] | None
    component_references: tuple[ComponentReference, ...] = ()
    component_tiers: tuple[ComponentTier, ...] = ()
    evidence_references: tuple[str, ...] = ()
    provenance_references: tuple[str, ...] = ()
    unresolved_requirements: tuple[str, ...] = ()
    deterministic_validation: AgentValidationSummary = field(default_factory=AgentValidationSummary)
    provider_metadata: Mapping[str, Any] = field(default_factory=dict)
    human_confirmation_state: str = "NOT_CONFIRMED"
    state: CandidateState = CandidateState.MODEL_GENERATED
    rationale: str = ""
    request_id: str = ""
    content_digest: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _safe_id(self.candidate_id, field_name="candidate_id"))
        object.__setattr__(self, "workflow_type", _text(self.workflow_type))
        object.__setattr__(self, "host", _text(self.host) or None)
        object.__setattr__(self, "user_intent", _text(self.user_intent))
        refs = tuple(self.component_references or ())
        if any(not isinstance(item, ComponentReference) for item in refs):
            raise ContractError("candidate component_references must contain ComponentReference values.")
        object.__setattr__(self, "component_references", refs)
        tiers = tuple(ComponentTier(item) for item in (self.component_tiers or tuple(ref.tier for ref in refs)))
        if len(tiers) != len(refs):
            raise ContractError("component_tiers must align with component_references.")
        object.__setattr__(self, "component_tiers", tiers)
        object.__setattr__(self, "evidence_references", _tuple_strings(self.evidence_references, field_name="evidence_references"))
        object.__setattr__(self, "provenance_references", _tuple_strings(self.provenance_references, field_name="provenance_references"))
        object.__setattr__(self, "unresolved_requirements", _tuple_strings(self.unresolved_requirements, field_name="unresolved_requirements"))
        if not isinstance(self.deterministic_validation, AgentValidationSummary):
            raise ContractError("deterministic_validation must be AgentValidationSummary.")
        object.__setattr__(self, "provider_metadata", dict(self.provider_metadata or {}))
        object.__setattr__(self, "human_confirmation_state", _text(self.human_confirmation_state) or "NOT_CONFIRMED")
        try:
            object.__setattr__(self, "state", CandidateState(self.state))
        except (TypeError, ValueError) as exc:
            raise ContractError("candidate state is unsupported.") from exc
        object.__setattr__(self, "rationale", _text(self.rationale))
        object.__setattr__(self, "request_id", _text(self.request_id))
        if self.request_id:
            object.__setattr__(self, "request_id", _safe_id(self.request_id, field_name="request_id"))
        object.__setattr__(self, "content_digest", _text(self.content_digest))


@dataclass(frozen=True)
class AgentAlternative:
    alternative_id: str
    candidate_id: str
    rationale: str = ""
    differences: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "alternative_id", _safe_id(self.alternative_id, field_name="alternative_id"))
        object.__setattr__(self, "candidate_id", _safe_id(self.candidate_id, field_name="candidate_id"))
        object.__setattr__(self, "rationale", _text(self.rationale))
        object.__setattr__(self, "differences", _tuple_strings(self.differences, field_name="differences"))


@dataclass(frozen=True)
class AgentTraceRecord:
    candidate_id: str | None
    request_id: str
    provider: str
    model: str
    generated_at: str
    provider_response_id: str | None = None
    structured_output_validation: str = "NOT_RUN"
    deterministic_validation_result: str = DeterministicValidationStatus.NOT_RUN.value
    human_confirmation_state: str = "NOT_CONFIRMED"
    prompt_schema_version: str = PROMPT_SCHEMA_VERSION
    component_references: tuple[str, ...] = ()
    evidence_references: tuple[str, ...] = ()
    deterministic_checks: tuple[str, ...] = ()
    human_confirmation: Mapping[str, Any] = field(default_factory=dict)
    adoption_result: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.candidate_id is not None:
            object.__setattr__(self, "candidate_id", _safe_id(self.candidate_id, field_name="candidate_id"))
        object.__setattr__(self, "request_id", _safe_id(self.request_id, field_name="request_id"))
        object.__setattr__(self, "provider", _text(self.provider) or "unknown")
        object.__setattr__(self, "model", _text(self.model) or "unknown")
        object.__setattr__(self, "generated_at", _text(self.generated_at) or utc_timestamp())
        object.__setattr__(self, "provider_response_id", safe_fingerprint(_text(self.provider_response_id) or None))
        structured_validation = _text(self.structured_output_validation) or "NOT_RUN"
        if structured_validation not in {"NOT_RUN", "PASS", "FAIL"}:
            raise ContractError("structured output validation result is unsupported.")
        object.__setattr__(self, "structured_output_validation", structured_validation)
        try:
            deterministic_result = DeterministicValidationStatus(self.deterministic_validation_result)
        except (TypeError, ValueError) as exc:
            raise ContractError("trace deterministic validation result is unsupported.") from exc
        object.__setattr__(self, "deterministic_validation_result", deterministic_result.value)
        object.__setattr__(self, "human_confirmation_state", _text(self.human_confirmation_state) or "NOT_CONFIRMED")
        object.__setattr__(self, "prompt_schema_version", _text(self.prompt_schema_version) or PROMPT_SCHEMA_VERSION)
        object.__setattr__(self, "component_references", _tuple_strings(self.component_references, field_name="component_references"))
        object.__setattr__(self, "evidence_references", _tuple_strings(self.evidence_references, field_name="evidence_references"))
        object.__setattr__(self, "deterministic_checks", _tuple_strings(self.deterministic_checks, field_name="deterministic_checks"))
        human_confirmation = dict(self.human_confirmation or {})
        adoption_result = dict(self.adoption_result or {})
        trace_payload = {
            "candidate_id": self.candidate_id,
            "request_id": self.request_id,
            "provider": self.provider,
            "model": self.model,
            "generated_at": self.generated_at,
            "provider_response_id": self.provider_response_id,
            "structured_output_validation": structured_validation,
            "deterministic_validation_result": deterministic_result.value,
            "human_confirmation_state": self.human_confirmation_state,
            "prompt_schema_version": self.prompt_schema_version,
            "component_references": self.component_references,
            "evidence_references": self.evidence_references,
            "deterministic_checks": self.deterministic_checks,
            "human_confirmation": human_confirmation,
            "adoption_result": adoption_result,
        }
        _assert_trace_secret_free(trace_payload, field_name="trace")
        object.__setattr__(self, "human_confirmation", human_confirmation)
        object.__setattr__(self, "adoption_result", adoption_result)

    def as_dict(self) -> dict[str, Any]:
        """Return the stable, secret-free trace serialization surface."""
        return {
            "candidate_id": self.candidate_id,
            "request_id": self.request_id,
            "provider": self.provider,
            "model": self.model,
            "generated_at": self.generated_at,
            "provider_response_id": self.provider_response_id,
            "structured_output_validation": self.structured_output_validation,
            "deterministic_validation_result": self.deterministic_validation_result,
            "human_confirmation_state": self.human_confirmation_state,
            "prompt_schema_version": self.prompt_schema_version,
            "component_references": list(self.component_references),
            "evidence_references": list(self.evidence_references),
            "deterministic_checks": list(self.deterministic_checks),
            "human_confirmation": dict(self.human_confirmation),
            "adoption_result": dict(self.adoption_result),
        }


@dataclass(frozen=True)
class AgentAdoptionPreview:
    preview_id: str
    candidate_id: str
    intended_project_changes: tuple[str, ...]
    deterministic_preconditions: tuple[str, ...]
    provenance_references: tuple[str, ...] = ()
    rollback_concept: str = "No Product write is performed by this preview. A future boundary must provide atomic write and rollback semantics."
    requires_human_confirmation: bool = True
    request_id: str = ""
    candidate_digest: str = ""
    service_id: str = ""
    issuance_nonce: str = ""
    lifecycle_state: str = "ISSUED"

    def __post_init__(self) -> None:
        object.__setattr__(self, "preview_id", _safe_id(self.preview_id, field_name="preview_id"))
        object.__setattr__(self, "candidate_id", _safe_id(self.candidate_id, field_name="candidate_id"))
        object.__setattr__(self, "intended_project_changes", _tuple_strings(self.intended_project_changes, field_name="intended_project_changes"))
        object.__setattr__(self, "deterministic_preconditions", _tuple_strings(self.deterministic_preconditions, field_name="deterministic_preconditions"))
        object.__setattr__(self, "provenance_references", _tuple_strings(self.provenance_references, field_name="provenance_references"))
        object.__setattr__(self, "rollback_concept", _text(self.rollback_concept))
        object.__setattr__(self, "request_id", _text(self.request_id))
        if self.request_id:
            object.__setattr__(self, "request_id", _safe_id(self.request_id, field_name="request_id"))
        object.__setattr__(self, "candidate_digest", _text(self.candidate_digest))
        object.__setattr__(self, "service_id", _text(self.service_id))
        object.__setattr__(self, "issuance_nonce", _text(self.issuance_nonce))
        lifecycle = _text(self.lifecycle_state) or "ISSUED"
        if lifecycle not in {"ISSUED", "CONFIRMED", "REVOKED"}:
            raise ContractError("adoption preview lifecycle state is unsupported.")
        object.__setattr__(self, "lifecycle_state", lifecycle)
        if self.requires_human_confirmation is not True:
            raise ContractError("adoption previews always require human confirmation.")


@dataclass(frozen=True)
class AgentAdoptionResult:
    candidate_id: str
    status: AdoptionStatus | str
    message: str
    transaction_id: str | None = None
    rollback_token: str | None = None
    trace: AgentTraceRecord | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _safe_id(self.candidate_id, field_name="candidate_id"))
        try:
            object.__setattr__(self, "status", AdoptionStatus(self.status))
        except (TypeError, ValueError) as exc:
            raise ContractError("adoption status is unsupported.") from exc
        object.__setattr__(self, "message", _text(self.message))
        object.__setattr__(self, "transaction_id", _text(self.transaction_id) or None)
        object.__setattr__(self, "rollback_token", _text(self.rollback_token) or None)
        if self.status is AdoptionStatus.FORMALLY_ADOPTED and (not self.transaction_id or not self.rollback_token):
            raise ContractError("formal adoption requires transaction and rollback identities.")


class DeterministicAdoptionBoundary(Protocol):
    """Future write boundary; this V1 preparation supplies no implementation."""

    def adopt(self, preview: AgentAdoptionPreview, *, confirmation_id: str) -> AgentAdoptionResult: ...


@dataclass(frozen=True)
class ToolCallRequest:
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _safe_id(self.name, field_name="tool_name"))
        object.__setattr__(self, "arguments", dict(self.arguments or {}))


@dataclass(frozen=True)
class ToolCallResult:
    ok: bool
    data: Mapping[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", dict(self.data or {}))
        object.__setattr__(self, "error_code", _text(self.error_code) or None)
        object.__setattr__(self, "error_message", _text(self.error_message) or None)
        if self.ok and (self.error_code or self.error_message):
            raise ContractError("successful tool results cannot contain errors")


@dataclass(frozen=True)
class CandidateArtifactState:
    input_signature: str
    artifacts: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    fresh: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "input_signature", _safe_id(self.input_signature, field_name="input_signature"))
        object.__setattr__(self, "artifacts", {str(k): dict(v) for k, v in dict(self.artifacts or {}).items()})
        if not isinstance(self.fresh, bool):
            raise ContractError("artifact freshness must be boolean")


@dataclass(frozen=True)
class AdoptionRequest:
    candidate_id: str
    project_id: str
    candidate_digest: str
    confirmation_token: str

    def __post_init__(self) -> None:
        for name in ("candidate_id", "project_id", "candidate_digest", "confirmation_token"):
            object.__setattr__(self, name, _safe_id(getattr(self, name), field_name=name))


@dataclass(frozen=True)
class AdoptionReceipt:
    receipt_id: str
    transaction_id: str
    candidate_id: str
    project_id: str
    candidate_digest: str
    candidate_revision: int
    adopted_at: str
    validation_version: str
    adoption_status: str = "COMMITTED"
    component_identities: tuple[str, ...] = ()
    sequence_provenance: Mapping[str, Any] = field(default_factory=dict)
    artifact_identities: Mapping[str, Any] = field(default_factory=dict)
    provider: str = ""
    model: str = ""

    def __post_init__(self) -> None:
        for name in ("receipt_id", "transaction_id", "candidate_id", "project_id", "candidate_digest", "validation_version"):
            object.__setattr__(self, name, _safe_id(getattr(self, name), field_name=name))
        if not isinstance(self.candidate_revision, int) or isinstance(self.candidate_revision, bool) or self.candidate_revision < 1:
            raise ContractError("receipt candidate_revision must be a positive integer.")
        if self.adoption_status != "COMMITTED":
            raise ContractError("receipt adoption_status must be COMMITTED.")
        object.__setattr__(self, "component_identities", _tuple_strings(self.component_identities, field_name="component_identities"))
        object.__setattr__(self, "sequence_provenance", dict(self.sequence_provenance or {}))
        object.__setattr__(self, "artifact_identities", dict(self.artifact_identities or {}))
        object.__setattr__(self, "provider", _text(self.provider))
        object.__setattr__(self, "model", _text(self.model))
        _assert_trace_secret_free(self.__dict__, field_name="adoption_receipt")


@dataclass(frozen=True)
class FailureEnvelope:
    code: str
    message: str
    retryable: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", _safe_id(self.code, field_name="failure_code"))
        object.__setattr__(self, "message", _text(self.message) or "Agent operation failed safely.")
        object.__setattr__(self, "retryable", bool(self.retryable))


@dataclass(frozen=True)
class AgentResultEnvelope:
    request_id: str
    ok: bool
    candidates: tuple[AgentCandidate, ...] = ()
    failure: FailureEnvelope | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_id", _safe_id(self.request_id, field_name="request_id"))
        object.__setattr__(self, "candidates", tuple(self.candidates or ()))
        if self.ok and self.failure is not None:
            raise ContractError("successful Agent result cannot contain failure")


def candidate_state_transition(current: CandidateState | str, target: CandidateState | str) -> None:
    """Fail closed for any lifecycle transition not explicitly approved."""
    try:
        source = CandidateState(current)
        destination = CandidateState(target)
    except (TypeError, ValueError) as exc:
        raise ContractError("candidate lifecycle state is unsupported.") from exc
    allowed = {
        CandidateState.AUTO_GENERATED: {CandidateState.VALIDATED_CANDIDATE},
        CandidateState.VALIDATED_CANDIDATE: {CandidateState.USER_ADOPTED},
        CandidateState.USER_ADOPTED: set(),
    }
    if destination not in allowed[source]:
        raise ContractError(f"invalid candidate lifecycle transition: {source.value} -> {destination.value}.")


def request_digest(request: AgentRequest) -> str:
    """Return an order-sensitive digest for the request binding.

    Component order is authoritative in the V1 request contract.  Providers
    must preserve the exact ordered component identity sequence; the digest,
    preview, and confirmation bindings therefore remain order-sensitive.
    """
    payload = {
        "request_id": request.request_id,
        "project_id": request.project_id,
        "workflow_type": request.workflow_type,
        "host": request.host,
        "user_intent": request.user_intent,
        "cds_or_reference_input": request.cds_or_reference_input,
        "component_references": [
            {
                "component_id": item.component_id,
                "role": item.role,
                "tier": item.tier.value,
                "sequence_reference": item.sequence_reference,
                "library_tier": item.library_tier,
                "canonical_v2_component_id": item.canonical_v2_component_id,
                "sequence_sha256": item.sequence_sha256,
            }
            for item in request.component_references
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def candidate_digest(candidate: AgentCandidate) -> str:
    """Digest immutable candidate content for preview/confirmation binding."""
    payload = {
        "candidate_id": candidate.candidate_id,
        "request_id": candidate.request_id,
        "workflow_type": candidate.workflow_type,
        "host": candidate.host,
        "user_intent": candidate.user_intent,
        "cds_or_reference_input": candidate.cds_or_reference_input,
        "component_references": [
            {
                "component_id": item.component_id,
                "role": item.role,
                "tier": item.tier.value,
                "sequence_reference": item.sequence_reference,
                "evidence_references": list(item.evidence_references),
                "provenance_references": list(item.provenance_references),
                "library_tier": item.library_tier,
                "canonical_v2_component_id": item.canonical_v2_component_id,
                "sequence_sha256": item.sequence_sha256,
            }
            for item in candidate.component_references
        ],
        "component_tiers": [item.value for item in candidate.component_tiers],
        "evidence_references": list(candidate.evidence_references),
        "provenance_references": list(candidate.provenance_references),
        "unresolved_requirements": list(candidate.unresolved_requirements),
        "rationale": candidate.rationale,
        "provider_metadata": dict(candidate.provider_metadata),
        "deterministic_validation": {
            "status": candidate.deterministic_validation.status.value,
            "checks": list(candidate.deterministic_validation.checks),
            "blocking_reasons": list(candidate.deterministic_validation.blocking_reasons),
            "warning_codes": list(candidate.deterministic_validation.warning_codes),
            "authority": candidate.deterministic_validation.authority,
            "checked_at": candidate.deterministic_validation.checked_at,
        },
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


__all__ = [
    "AgentAdoptionPreview",
    "AgentAdoptionResult",
    "AgentAlternative",
    "AgentCandidate",
    "AgentNeedInput",
    "AgentRequest",
    "AgentRunState",
    "AgentTraceRecord",
    "AgentValidationSummary",
    "AgentResultEnvelope",
    "AdoptionRequest",
    "AdoptionReceipt",
    "CandidateArtifactState",
    "AdoptionStatus",
    "CandidateState",
    "ComponentRecord",
    "ComponentReference",
    "ComponentRepository",
    "ComponentTier",
    "ProductLibraryTier",
    "ContractError",
    "CandidateState",
    "DeterministicAdoptionBoundary",
    "DeterministicValidationStatus",
    "FailureEnvelope",
    "NeedInputCode",
    "ToolCallRequest",
    "ToolCallResult",
    "PROMPT_SCHEMA_VERSION",
    "ProviderCandidateDraft",
    "SCHEMA_VERSION",
    "candidate_state_transition",
    "candidate_digest",
    "request_digest",
    "utc_timestamp",
]
