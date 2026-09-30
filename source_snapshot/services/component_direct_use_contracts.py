"""Immutable domain and value contracts for the future direct-use component path.

Impl-01 deliberately contains no persistence, provider calls, or workflow/UI
integration.  These objects only describe identity, authority, rights, and
exact sequence evidence.  All validation is deterministic and fail-closed.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class ContractValidationError(ValueError):
    """Raised when a direct-use contract is malformed or unsafe."""


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ComponentType(_StringEnum):
    PROMOTER = "promoter"
    FIVE_PRIME_UTR = "five_prime_utr"
    CDS = "cds"
    THREE_PRIME_REGULATORY_REGION = "three_prime_regulatory_region"
    TERMINATOR = "terminator"
    VECTOR_BACKBONE = "vector_backbone"


class ReferenceLifecycleStatus(_StringEnum):
    ACTIVE = "active"
    RETIRED = "retired"
    REVOKED = "revoked"


class AdmissionState(_StringEnum):
    DRY_RUN_ASSIGNABLE = "DRY_RUN_ASSIGNABLE"
    ASSIGNMENT_APPROVED = "ASSIGNMENT_APPROVED"
    ASSIGNED_NOT_ADMITTED = "ASSIGNED_NOT_ADMITTED"
    FORMALLY_ADMITTED = "FORMALLY_ADMITTED"
    ADMISSION_FAILED = "ADMISSION_FAILED"
    REVOKED = "REVOKED"
    RETIRED = "RETIRED"


class RightsDecision(_StringEnum):
    ELIGIBLE = "ELIGIBLE"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"
    UNPROVEN = "UNPROVEN"


class RightsOutcome(_StringEnum):
    RIGHTS_ELIGIBLE = "RIGHTS_ELIGIBLE"
    RIGHTS_NOT_ELIGIBLE = "RIGHTS_NOT_ELIGIBLE"
    RIGHTS_FOR_BUNDLING_DENIED = "RIGHTS_FOR_BUNDLING_DENIED"
    RIGHTS_FOR_RUNTIME_RESOLUTION_DENIED = "RIGHTS_FOR_RUNTIME_RESOLUTION_DENIED"
    RIGHTS_FOR_LOCAL_MATERIALIZATION_DENIED = "RIGHTS_FOR_LOCAL_MATERIALIZATION_DENIED"
    RIGHTS_FOR_REFERENCE_METADATA_DENIED = "RIGHTS_FOR_REFERENCE_METADATA_DENIED"
    RIGHTS_EVIDENCE_MISSING = "RIGHTS_EVIDENCE_MISSING"
    RIGHTS_EVIDENCE_EXPIRED = "RIGHTS_EVIDENCE_EXPIRED"
    RIGHTS_SCOPE_MISMATCH = "RIGHTS_SCOPE_MISMATCH"


class ResolutionFailureCode(_StringEnum):
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_VERSION_MISMATCH = "SOURCE_VERSION_MISMATCH"
    FEATURE_NOT_FOUND = "FEATURE_NOT_FOUND"
    BOUNDARY_MISMATCH = "BOUNDARY_MISMATCH"
    SEQUENCE_HASH_MISMATCH = "SEQUENCE_HASH_MISMATCH"
    RIGHTS_NOT_ELIGIBLE = "RIGHTS_NOT_ELIGIBLE"
    NOT_FORMALLY_ADMITTED = "NOT_FORMALLY_ADMITTED"


class ResolutionStatus(_StringEnum):
    RESOLVED = "RESOLVED"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    SOURCE_VERSION_MISMATCH = "SOURCE_VERSION_MISMATCH"
    FEATURE_NOT_FOUND = "FEATURE_NOT_FOUND"
    BOUNDARY_MISMATCH = "BOUNDARY_MISMATCH"
    SEQUENCE_HASH_MISMATCH = "SEQUENCE_HASH_MISMATCH"
    RIGHTS_NOT_ELIGIBLE = "RIGHTS_NOT_ELIGIBLE"
    NOT_FORMALLY_ADMITTED = "NOT_FORMALLY_ADMITTED"


class SelectionSource(_StringEnum):
    LIBRARY_SELECTED = "LIBRARY_SELECTED"
    USER_CUSTOM = "USER_CUSTOM"


class BackboneState(_StringEnum):
    REFERENCE_BACKBONE = "REFERENCE_BACKBONE"
    BACKBONE_RESOLUTION_ELIGIBLE = "BACKBONE_RESOLUTION_ELIGIBLE"
    BACKBONE_BOUNDARY_VERIFIED = "BACKBONE_BOUNDARY_VERIFIED"
    FORMALLY_ADMITTED_BACKBONE = "FORMALLY_ADMITTED_BACKBONE"
    SELECTABLE_BACKBONE = "SELECTABLE_BACKBONE"


_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_DNA_RE = re.compile(r"^[ACGTN]*$", re.IGNORECASE)
_ACTIVE_ADMISSION_STATES = frozenset(
    {
        AdmissionState.DRY_RUN_ASSIGNABLE,
        AdmissionState.ASSIGNMENT_APPROVED,
        AdmissionState.ASSIGNED_NOT_ADMITTED,
        AdmissionState.FORMALLY_ADMITTED,
    }
)
_FAILURE_CODES = frozenset(ResolutionFailureCode)


def _nonempty(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractValidationError(f"{field_name} must be a positive integer.")
    return value


def _optional_positive_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, field_name)


def validate_sha256(value: Any, field_name: str = "sha256") -> str:
    value = _nonempty(value, field_name).lower()
    if _SHA256_RE.fullmatch(value) is None:
        raise ContractValidationError(f"{field_name} must be a 64-character hexadecimal SHA-256.")
    return value


def normalize_sequence(value: Any) -> str:
    if not isinstance(value, str):
        raise ContractValidationError("sequence must be a string.")
    normalized = "".join(value.split()).upper()
    if not normalized or _DNA_RE.fullmatch(normalized) is None:
        raise ContractValidationError("sequence must contain only DNA bases (A/C/G/T/N).")
    return normalized


def sequence_sha256(sequence: str) -> str:
    normalized = normalize_sequence(sequence)
    return hashlib.sha256(normalized.encode("ascii")).hexdigest()


def _freeze(value: Any, field_name: str = "value") -> Any:
    """Copy and recursively freeze contract-owned containers."""
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v, field_name) for k, v in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(v, field_name) for v in value)
    if isinstance(value, tuple):
        return tuple(_freeze(v, field_name) for v in value)
    if isinstance(value, set):
        return frozenset(_freeze(v, field_name) for v in value)
    if isinstance(value, frozenset):
        return frozenset(_freeze(v, field_name) for v in value)
    return value


def _freeze_mapping(value: Mapping[str, Any] | None, field_name: str) -> Mapping[str, Any]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field_name} must be a mapping.")
    return _freeze(value, field_name)


def _timestamp(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractValidationError(f"{field_name} must be an ISO-8601 timestamp.") from exc
    else:
        raise ContractValidationError(f"{field_name} must be an ISO-8601 timestamp.")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must include timezone information.")
    return result.astimezone(timezone.utc)


def _evaluation_time(value: Any, field_name: str = "evaluation_time") -> datetime | None:
    """Normalize an explicit evaluation instant; never consult local wall time."""
    if value is None:
        return None
    return _timestamp(value, field_name)


def _direct_use_evaluation_time(
    evaluation_time: datetime | str | None,
    now_utc: datetime | str | None,
    *,
    default_to_current: bool = False,
) -> datetime | None:
    if evaluation_time is not None and now_utc is not None:
        raise ContractValidationError("Provide only one explicit evaluation time.")
    explicit = evaluation_time if evaluation_time is not None else now_utc
    if explicit is not None:
        return _evaluation_time(explicit)
    return datetime.now(timezone.utc) if default_to_current else None


@dataclass(frozen=True, slots=True)
class ApprovalBinding:
    """Structured, auditable proof for a formal admission decision."""
    authority_id: str
    policy_version: str
    decision_id: str
    decision_hash: str
    approver_id: str
    decision_timestamp: datetime
    signature: str
    admission_id: str
    reference_id: str
    reference_version: int
    _validated_contract: tuple[Any, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in ("authority_id", "policy_version", "decision_id", "approver_id", "signature", "admission_id", "reference_id"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        object.__setattr__(self, "decision_hash", validate_sha256(self.decision_hash, "decision_hash"))
        object.__setattr__(self, "decision_timestamp", _timestamp(self.decision_timestamp, "decision_timestamp"))
        object.__setattr__(self, "reference_version", _positive_int(self.reference_version, "reference_version"))
        object.__setattr__(self, "_validated_contract", _approval_binding_fields(self))


def _approval_binding_fields(value: ApprovalBinding) -> tuple[Any, ...]:
    return tuple(
        getattr(value, name)
        for name, contract_field in ApprovalBinding.__dataclass_fields__.items()
        if contract_field.init
    )


def _approval_binding(value: Any, *, admission_id: str | None = None, reference_id: str | None = None, reference_version: int | None = None) -> ApprovalBinding:
    if isinstance(value, ApprovalBinding):
        try:
            if value._validated_contract != _approval_binding_fields(value):
                raise ContractValidationError("approval_binding fields changed after validation.")
            binding = ApprovalBinding(**{
                key: getattr(value, key)
                for key, contract_field in ApprovalBinding.__dataclass_fields__.items()
                if contract_field.init
            })
        except (AttributeError, TypeError, ContractValidationError) as exc:
            raise ContractValidationError("approval_binding must satisfy the structured approval contract.") from exc
    elif isinstance(value, Mapping):
        try:
            raw = dict(value)
            aliases = {
                "approval_authority_id": "authority_id",
                "policy_contract_version": "policy_version",
                "decision_identity": "decision_id",
                "approver_identity": "approver_id",
                "decision_signature": "signature",
            }
            for source, target in aliases.items():
                if target not in raw and source in raw:
                    raw[target] = raw[source]
            binding = ApprovalBinding(**{
                key: raw[key]
                for key, contract_field in ApprovalBinding.__dataclass_fields__.items()
                if contract_field.init
            })
        except (TypeError, KeyError, ContractValidationError) as exc:
            raise ContractValidationError("approval_binding must satisfy the structured approval contract.") from exc
    else:
        raise ContractValidationError("approval_binding must be an ApprovalBinding.")
    if admission_id is not None and (binding.admission_id, binding.reference_id, binding.reference_version) != (admission_id, reference_id, reference_version):
        raise ContractValidationError("approval_binding identity does not match the admission.")
    return binding


_RIGHTS_FIELDS = {
    "bundling": "rights_for_bundling",
    "runtime_resolution": "rights_for_runtime_resolution",
    "local_materialization": "rights_for_local_materialization",
    "reference_metadata": "rights_for_reference_metadata",
}


@dataclass(frozen=True, slots=True)
class RightsEvidence:
    """Evidence for one exact rights dimension, operation, and workflow scope."""
    evidence_id: str
    rights_dimension: str
    operation: str
    workflow_scope: tuple[str, ...]
    reference_id: str
    reference_version: int
    admission_id: str | None
    admission_version: int | None
    authority_id: str
    source_id: str
    policy_version: str
    decision_id: str
    decision_hash: str
    evaluated_at: datetime
    valid_until: datetime | None = None
    provenance: Mapping[str, Any] = field(default_factory=dict)
    evidence_version: str = "1"
    _validated_contract: tuple[Any, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        for name in ("evidence_id", "rights_dimension", "operation", "reference_id", "authority_id", "source_id", "policy_version", "decision_id", "evidence_version"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        if self.rights_dimension not in _RIGHTS_FIELDS:
            raise ContractValidationError("rights_dimension is unsupported.")
        if self.operation not in _RIGHTS_FIELDS:
            raise ContractValidationError("operation is unsupported.")
        if self.operation != self.rights_dimension:
            raise ContractValidationError("rights evidence dimension and operation must match exactly.")
        scopes = tuple(_nonempty(item, "workflow_scope") for item in (self.workflow_scope or ()))
        if not scopes:
            raise ContractValidationError("workflow_scope must contain at least one exact scope.")
        object.__setattr__(self, "workflow_scope", scopes)
        object.__setattr__(self, "reference_version", _positive_int(self.reference_version, "reference_version"))
        if self.admission_id is not None:
            object.__setattr__(self, "admission_id", _nonempty(self.admission_id, "admission_id"))
            object.__setattr__(self, "admission_version", _positive_int(self.admission_version, "admission_version"))
        elif self.admission_version is not None:
            raise ContractValidationError("admission_version requires admission_id.")
        object.__setattr__(self, "decision_hash", validate_sha256(self.decision_hash, "decision_hash"))
        object.__setattr__(self, "evaluated_at", _timestamp(self.evaluated_at, "evaluated_at"))
        if self.valid_until is not None:
            object.__setattr__(self, "valid_until", _timestamp(self.valid_until, "valid_until"))
            if self.valid_until <= self.evaluated_at:
                raise ContractValidationError("valid_until must be later than evaluated_at.")
        object.__setattr__(self, "provenance", _freeze_mapping(self.provenance, "provenance"))
        if not self.provenance:
            raise ContractValidationError("provenance must not be empty.")
        object.__setattr__(self, "_validated_contract", _rights_evidence_fields(self))


def _rights_evidence_fields(value: RightsEvidence) -> tuple[Any, ...]:
    return tuple(
        getattr(value, name)
        for name, contract_field in RightsEvidence.__dataclass_fields__.items()
        if contract_field.init
    )


def _revalidate_rights_evidence(value: Any) -> RightsEvidence:
    if not isinstance(value, RightsEvidence):
        raise ContractValidationError("rights evidence must use its structured evidence contract.")
    try:
        if value._validated_contract != _rights_evidence_fields(value):
            raise ContractValidationError("rights evidence fields changed after validation.")
        return RightsEvidence(**{
            key: getattr(value, key)
            for key, contract_field in RightsEvidence.__dataclass_fields__.items()
            if contract_field.init
        })
    except (AttributeError, TypeError, ContractValidationError) as exc:
        raise ContractValidationError("rights evidence must satisfy the structured evidence contract.") from exc


def _valid_rights_evidence(evidence: Any, dimension: str, *, reference_id: str | None = None,
                           reference_version: int | None = None, admission_id: str | None = None,
                           admission_version: int | None = None, workflow_scope: str | None = None,
                           operation: str | None = None,
                           evaluation_time: datetime | None = None) -> bool:
    if evaluation_time is not None and (
        not isinstance(evaluation_time, datetime)
        or evaluation_time.tzinfo is None
        or evaluation_time.utcoffset() is None
    ):
        return False
    try:
        item = _revalidate_rights_evidence(evidence)
    except ContractValidationError:
        return False
    if item.rights_dimension != dimension or item.operation != (operation or dimension):
        return False
    if reference_id is not None and item.reference_id != reference_id:
        return False
    if reference_version is not None and item.reference_version != reference_version:
        return False
    if admission_id is not None and item.admission_id != admission_id:
        return False
    if admission_version is not None and item.admission_version != admission_version:
        return False
    if workflow_scope is not None and workflow_scope not in item.workflow_scope:
        return False
    if item.valid_until is not None and evaluation_time is not None and item.valid_until <= evaluation_time:
        return False
    return True


def _enum(value: Any, enum_type: type[Enum], field_name: str):
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ContractValidationError(f"{field_name} has an unsupported value.") from exc


def _coordinate(start: Any, end: Any) -> tuple[int, int]:
    if isinstance(start, bool) or not isinstance(start, int) or start < 0:
        raise ContractValidationError("start must be a non-negative integer.")
    if isinstance(end, bool) or not isinstance(end, int) or end < 0:
        raise ContractValidationError("end must be a non-negative integer.")
    if end <= start:
        raise ContractValidationError("end must be greater than start for a half-open interval.")
    return start, end


def _strand(value: Any) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    value = _nonempty(value, "strand")
    if value not in {"+", "-", "1", "-1", "forward", "reverse"}:
        raise ContractValidationError("strand must be '+', '-', '1', '-1', 'forward', or 'reverse'.")
    return value


@dataclass(frozen=True, slots=True)
class RightsState:
    rights_for_bundling: RightsDecision = RightsDecision.UNKNOWN
    rights_for_runtime_resolution: RightsDecision = RightsDecision.UNKNOWN
    rights_for_local_materialization: RightsDecision = RightsDecision.UNKNOWN
    rights_for_reference_metadata: RightsDecision = RightsDecision.UNKNOWN
    evidence: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for name in (
            "rights_for_bundling",
            "rights_for_runtime_resolution",
            "rights_for_local_materialization",
            "rights_for_reference_metadata",
        ):
            object.__setattr__(self, name, _enum(getattr(self, name), RightsDecision, name))
        evidence_by_dimension = dict(_freeze_mapping(self.evidence, "evidence"))
        for dimension, field_name in _RIGHTS_FIELDS.items():
            decision = getattr(self, field_name)
            evidence = evidence_by_dimension.get(dimension)
            if decision is RightsDecision.ELIGIBLE and not _valid_rights_evidence(evidence, dimension):
                raise ContractValidationError(f"Eligible {dimension} rights require bound evidence.")
            if decision is RightsDecision.ELIGIBLE:
                validated = _revalidate_rights_evidence(evidence)
                evidence_by_dimension[dimension] = validated
        object.__setattr__(self, "evidence", _freeze_mapping(evidence_by_dimension, "evidence"))

    def operation_outcome(
        self,
        operation: str,
        *,
        evaluation_time: datetime | str | None = None,
        now_utc: datetime | str | None = None,
    ) -> RightsOutcome:
        try:
            instant = _direct_use_evaluation_time(
                evaluation_time, now_utc, default_to_current=True
            )
        except ContractValidationError:
            required = {
                "metadata": RightsOutcome.RIGHTS_FOR_REFERENCE_METADATA_DENIED,
                "runtime_resolution": RightsOutcome.RIGHTS_FOR_RUNTIME_RESOLUTION_DENIED,
                "local_materialization": RightsOutcome.RIGHTS_FOR_LOCAL_MATERIALIZATION_DENIED,
                "bundling": RightsOutcome.RIGHTS_FOR_BUNDLING_DENIED,
            }
            if operation not in required:
                raise ContractValidationError(f"Unknown rights operation: {operation}.")
            return required[operation]
        return self._operation_outcome_at(operation, instant)

    def _operation_outcome_at(self, operation: str, instant: datetime | None) -> RightsOutcome:
        required = {
            "metadata": ("rights_for_reference_metadata", RightsOutcome.RIGHTS_FOR_REFERENCE_METADATA_DENIED),
            "runtime_resolution": (
                "rights_for_runtime_resolution",
                RightsOutcome.RIGHTS_FOR_RUNTIME_RESOLUTION_DENIED,
            ),
            "local_materialization": (
                "rights_for_local_materialization",
                RightsOutcome.RIGHTS_FOR_LOCAL_MATERIALIZATION_DENIED,
            ),
            "bundling": ("rights_for_bundling", RightsOutcome.RIGHTS_FOR_BUNDLING_DENIED),
        }
        if operation not in required:
            raise ContractValidationError(f"Unknown rights operation: {operation}.")
        field_name, denied = required[operation]
        decision = getattr(self, field_name)
        evidence_dimension = "reference_metadata" if operation == "metadata" else operation
        return RightsOutcome.RIGHTS_ELIGIBLE if decision is RightsDecision.ELIGIBLE and _valid_rights_evidence(
            self.evidence.get(evidence_dimension),
            evidence_dimension,
            evaluation_time=instant,
        ) else denied

    def is_runtime_eligible(
        self,
        *,
        evaluation_time: datetime | str | None = None,
        now_utc: datetime | str | None = None,
    ) -> bool:
        try:
            instant = _direct_use_evaluation_time(
                evaluation_time, now_utc, default_to_current=True
            )
        except ContractValidationError:
            return False
        return self._is_runtime_eligible_at(instant)

    def _is_runtime_eligible_at(self, instant: datetime | None) -> bool:
        return (
            self._operation_outcome_at("runtime_resolution", instant) is RightsOutcome.RIGHTS_ELIGIBLE
            and self._operation_outcome_at("local_materialization", instant) is RightsOutcome.RIGHTS_ELIGIBLE
        )


@dataclass(frozen=True, slots=True)
class ComponentReference:
    reference_id: str
    reference_version: int
    component_id: str
    component_type: ComponentType
    display_name: str
    source_provenance: Mapping[str, Any]
    sequence_length: int | None = None
    sequence_sha256: str | None = None
    boundary_descriptor: Mapping[str, Any] = field(default_factory=dict)
    host_scope: str = "NOT_PROVEN"
    evidence_scope: str = "NOT_PROVEN"
    lifecycle_status: ReferenceLifecycleStatus = ReferenceLifecycleStatus.ACTIVE
    sequence: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference_id", _nonempty(self.reference_id, "reference_id"))
        object.__setattr__(self, "reference_version", _positive_int(self.reference_version, "reference_version"))
        object.__setattr__(self, "component_id", _nonempty(self.component_id, "component_id"))
        object.__setattr__(self, "component_type", _enum(self.component_type, ComponentType, "component_type"))
        object.__setattr__(self, "display_name", _nonempty(self.display_name, "display_name"))
        object.__setattr__(self, "source_provenance", _freeze_mapping(self.source_provenance, "source_provenance"))
        if not self.source_provenance:
            raise ContractValidationError("source_provenance must not be empty.")
        length = _optional_positive_int(self.sequence_length, "sequence_length")
        digest = None if self.sequence_sha256 is None else validate_sha256(self.sequence_sha256, "sequence_sha256")
        sequence = None if self.sequence is None else normalize_sequence(self.sequence)
        if (length is None) != (digest is None):
            raise ContractValidationError("sequence_length and sequence_sha256 must be supplied together.")
        if sequence is not None:
            if length is None or len(sequence) != length or sequence_sha256(sequence) != digest:
                raise ContractValidationError("Reference sequence does not match its length/hash.")
        object.__setattr__(self, "sequence_length", length)
        object.__setattr__(self, "sequence_sha256", digest)
        object.__setattr__(self, "boundary_descriptor", _freeze_mapping(self.boundary_descriptor, "boundary_descriptor"))
        object.__setattr__(self, "host_scope", _nonempty(self.host_scope, "host_scope"))
        object.__setattr__(self, "evidence_scope", _nonempty(self.evidence_scope, "evidence_scope"))
        object.__setattr__(self, "lifecycle_status", _enum(self.lifecycle_status, ReferenceLifecycleStatus, "lifecycle_status"))
        object.__setattr__(self, "sequence", sequence)


@dataclass(frozen=True, slots=True)
class ComponentAdmission:
    admission_id: str
    admission_version: int
    reference_id: str
    reference_version: int
    assignment_id: str
    state: AdmissionState
    workflow_scope: tuple[str, ...]
    role_scope: tuple[str, ...]
    rights_snapshot: RightsState
    approval_binding: ApprovalBinding | Mapping[str, Any]
    effective_at: datetime | None = None
    expires_at: datetime | None = None
    audit_provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("admission_id", "reference_id", "assignment_id"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        for name in ("admission_version", "reference_version"):
            object.__setattr__(self, name, _positive_int(getattr(self, name), name))
        object.__setattr__(self, "state", _enum(self.state, AdmissionState, "state"))
        for name in ("workflow_scope", "role_scope"):
            values = tuple(_nonempty(item, name) for item in (getattr(self, name) or ()))
            if not values:
                raise ContractValidationError(f"{name} must contain at least one scope.")
            object.__setattr__(self, name, values)
        if not isinstance(self.rights_snapshot, RightsState):
            raise ContractValidationError("rights_snapshot must be a RightsState.")
        if self.state is AdmissionState.FORMALLY_ADMITTED:
            binding = _approval_binding(self.approval_binding, admission_id=self.admission_id, reference_id=self.reference_id, reference_version=self.reference_version)
        else:
            if self.approval_binding not in (None, {}, MappingProxyType({})):
                raise ContractValidationError("Only formal admissions may carry approval binding.")
            binding = MappingProxyType({})
        object.__setattr__(self, "approval_binding", binding)
        effective_at = _evaluation_time(self.effective_at, "effective_at")
        expires_at = _evaluation_time(self.expires_at, "expires_at")
        if effective_at is not None and expires_at is not None and effective_at > expires_at:
            raise ContractValidationError("effective_at must be earlier than or equal to expires_at.")
        object.__setattr__(self, "effective_at", effective_at)
        object.__setattr__(self, "expires_at", expires_at)
        object.__setattr__(self, "audit_provenance", _freeze_mapping(self.audit_provenance, "audit_provenance"))


def is_admission_current(admission: ComponentAdmission | None, *, evaluation_time: datetime | str | None = None,
                         now_utc: datetime | str | None = None) -> bool:
    """Return whether a formal admission is effective at one explicit UTC instant.

    Unbounded intervals are supported by the frozen contract: a missing
    ``effective_at`` means effective from the beginning of the record, and a
    missing ``expires_at`` is open-ended (it is not an automatic renewal).
    When either bound exists, callers must provide ``evaluation_time`` so
    historical qualification remains deterministic and never depends on a
    hidden local clock.
    """
    if not isinstance(admission, ComponentAdmission) or admission.state is not AdmissionState.FORMALLY_ADMITTED:
        return False
    try:
        instant = _direct_use_evaluation_time(evaluation_time, now_utc)
    except ContractValidationError:
        return False
    return _is_admission_current_at(
        admission,
        instant,
        evaluation_was_explicit=evaluation_time is not None or now_utc is not None,
    )


def _is_admission_current_at(
    admission: ComponentAdmission,
    instant: datetime | None,
    *,
    evaluation_was_explicit: bool,
) -> bool:
    if admission.state is not AdmissionState.FORMALLY_ADMITTED:
        return False
    if admission.effective_at is None and admission.expires_at is None:
        return True
    if not evaluation_was_explicit or instant is None:
        return False
    if admission.effective_at is not None and instant < admission.effective_at:
        return False
    if admission.expires_at is not None and instant >= admission.expires_at:
        return False
    return True


def validate_admission_transition(
    prior_state: AdmissionState | str,
    next_state: AdmissionState | str,
    *,
    approval_binding: Mapping[str, Any] | None = None,
    failure_code: ResolutionFailureCode | str | None = None,
    revocation_reason: str | None = None,
) -> None:
    """Validate one append-only admission transition; invalid paths fail closed."""
    prior = _enum(prior_state, AdmissionState, "prior_state")
    next_value = _enum(next_state, AdmissionState, "next_state")
    legal = {
        (AdmissionState.DRY_RUN_ASSIGNABLE, AdmissionState.ASSIGNMENT_APPROVED),
        (AdmissionState.ASSIGNMENT_APPROVED, AdmissionState.ASSIGNED_NOT_ADMITTED),
        (AdmissionState.ASSIGNED_NOT_ADMITTED, AdmissionState.FORMALLY_ADMITTED),
        *((state, AdmissionState.ADMISSION_FAILED) for state in _ACTIVE_ADMISSION_STATES),
        *((state, AdmissionState.REVOKED) for state in {
            AdmissionState.ASSIGNMENT_APPROVED,
            AdmissionState.ASSIGNED_NOT_ADMITTED,
            AdmissionState.FORMALLY_ADMITTED,
        }),
        (AdmissionState.FORMALLY_ADMITTED, AdmissionState.RETIRED),
    }
    if (prior, next_value) not in legal:
        raise ContractValidationError(f"Illegal admission transition: {prior.value} -> {next_value.value}.")
    if next_value is AdmissionState.FORMALLY_ADMITTED:
        if not isinstance(approval_binding, (Mapping, ApprovalBinding)):
            raise ContractValidationError("Formal admission requires an approval binding.")
        _approval_binding(approval_binding)
    if next_value is AdmissionState.ADMISSION_FAILED:
        if failure_code is None:
            raise ContractValidationError("Admission failure requires a deterministic failure code.")
        _enum(failure_code, ResolutionFailureCode, "failure_code")
    if next_value is AdmissionState.REVOKED and not _nonempty(revocation_reason, "revocation_reason"):
        raise ContractValidationError("Revocation requires an accountable reason.")


@dataclass(frozen=True, slots=True)
class ComponentResolutionRequest:
    request_id: str
    request_version: int
    component_id: str
    admission_id: str
    admission_version: int
    provider: str
    accession: str
    source_version: str
    feature_identity: str
    start: int
    end: int
    strand: str
    coordinate_system: str
    expected_length: int
    expected_sha256: str
    requested_mechanism: str
    requested_at: datetime | None = None
    requester_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("request_id", "component_id", "admission_id", "provider", "accession", "source_version", "feature_identity", "coordinate_system", "requested_mechanism"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        for name in ("request_version", "admission_version", "expected_length"):
            object.__setattr__(self, name, _positive_int(getattr(self, name), name))
        start, end = _coordinate(self.start, self.end)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "strand", _strand(self.strand))
        object.__setattr__(self, "expected_sha256", validate_sha256(self.expected_sha256, "expected_sha256"))
        object.__setattr__(self, "requester_context", _freeze_mapping(self.requester_context, "requester_context"))


@dataclass(frozen=True, slots=True)
class ComponentResolvedSequence:
    resolution_id: str
    resolution_version: int
    request_id: str
    request_version: int
    provider: str
    accession: str
    version: str
    feature_identity: str
    start: int
    end: int
    strand: str
    coordinate_system: str
    expected_length: int
    expected_sha256: str
    retrieved_length: int | None
    retrieved_sha256: str | None
    resolution_mechanism: str
    resolved_at: datetime | None
    provider_provenance: Mapping[str, Any]
    rights_evaluation_id: str
    status: ResolutionStatus
    sequence: str | None = None
    component_id: str | None = None
    admission_id: str | None = None
    admission_version: int | None = None

    def __post_init__(self) -> None:
        for name in ("resolution_id", "request_id", "provider", "accession", "version", "feature_identity", "coordinate_system", "resolution_mechanism", "rights_evaluation_id"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        for name in ("resolution_version", "request_version", "expected_length"):
            object.__setattr__(self, name, _positive_int(getattr(self, name), name))
        start, end = _coordinate(self.start, self.end)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "strand", _strand(self.strand))
        object.__setattr__(self, "expected_sha256", validate_sha256(self.expected_sha256, "expected_sha256"))
        object.__setattr__(self, "status", _enum(self.status, ResolutionStatus, "status"))
        length = _optional_positive_int(self.retrieved_length, "retrieved_length")
        digest = None if self.retrieved_sha256 is None else validate_sha256(self.retrieved_sha256, "retrieved_sha256")
        sequence = None if self.sequence is None else normalize_sequence(self.sequence)
        if self.status is ResolutionStatus.RESOLVED:
            if length is None or digest is None:
                raise ContractValidationError("A resolved sequence requires retrieved length and SHA-256.")
            if length != self.expected_length or digest != self.expected_sha256:
                raise ContractValidationError("Resolved sequence does not match the expected length/hash.")
            if sequence is not None and (len(sequence) != length or sequence_sha256(sequence) != digest):
                raise ContractValidationError("Resolved sequence bytes do not match retrieved length/hash.")
        elif sequence is not None:
            raise ContractValidationError("Fail-closed resolution results must not expose sequence bytes.")
        object.__setattr__(self, "retrieved_length", length)
        object.__setattr__(self, "retrieved_sha256", digest)
        object.__setattr__(self, "sequence", sequence)
        object.__setattr__(self, "provider_provenance", _freeze_mapping(self.provider_provenance, "provider_provenance"))
        if self.component_id is not None:
            object.__setattr__(self, "component_id", _nonempty(self.component_id, "component_id"))
        if self.admission_id is not None:
            object.__setattr__(self, "admission_id", _nonempty(self.admission_id, "admission_id"))
            object.__setattr__(self, "admission_version", _positive_int(self.admission_version, "admission_version"))
        elif self.admission_version is not None:
            raise ContractValidationError("admission_version requires admission_id.")


@dataclass(frozen=True, slots=True)
class ComponentSelectionSnapshot:
    snapshot_id: str
    snapshot_version: int
    component_id: str | None
    reference_id: str | None
    admission_id: str | None
    admission_version: int | None
    accession: str | None
    source_version: str | None
    exact_selected_sequence: str
    exact_sha256: str
    exact_length: int
    start: int | None
    end: int | None
    strand: str | None
    coordinate_system: str | None
    workflow_role: str
    workflow_kind: str
    host_scope: str
    evidence_scope: str
    rights_state_at_selection: RightsState
    resolution_id: str | None
    resolution_provenance: Mapping[str, Any]
    selection_source: SelectionSource
    selected_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "snapshot_id", _nonempty(self.snapshot_id, "snapshot_id"))
        object.__setattr__(self, "snapshot_version", _positive_int(self.snapshot_version, "snapshot_version"))
        sequence = normalize_sequence(self.exact_selected_sequence)
        digest = validate_sha256(self.exact_sha256, "exact_sha256")
        length = _positive_int(self.exact_length, "exact_length")
        if len(sequence) != length or sequence_sha256(sequence) != digest:
            raise ContractValidationError("Selection snapshot sequence, length, and hash must agree.")
        object.__setattr__(self, "exact_selected_sequence", sequence)
        object.__setattr__(self, "exact_sha256", digest)
        object.__setattr__(self, "exact_length", length)
        for name in ("workflow_role", "workflow_kind", "host_scope", "evidence_scope"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        source = _enum(self.selection_source, SelectionSource, "selection_source")
        object.__setattr__(self, "selection_source", source)
        if not isinstance(self.rights_state_at_selection, RightsState):
            raise ContractValidationError("rights_state_at_selection must be a RightsState.")
        object.__setattr__(self, "resolution_provenance", _freeze_mapping(self.resolution_provenance, "resolution_provenance"))
        if source is SelectionSource.LIBRARY_SELECTED:
            for name in ("component_id", "reference_id", "admission_id", "accession", "source_version", "resolution_id"):
                _nonempty(getattr(self, name), name)
            _positive_int(self.admission_version, "admission_version")
            if self.start is None or self.end is None or self.strand is None or self.coordinate_system is None:
                raise ContractValidationError("Library selections require exact coordinates and strand.")
            _coordinate(self.start, self.end)
            _strand(self.strand)
            if not self.rights_state_at_selection.is_runtime_eligible():
                raise ContractValidationError("Library selections require runtime and local-materialization rights.")
        else:
            if any(value not in (None, "NOT_APPLICABLE") for value in (self.component_id, self.reference_id, self.admission_id, self.accession, self.source_version, self.resolution_id)):
                raise ContractValidationError("USER_CUSTOM snapshots cannot claim Registry/admission/resolution identity.")
        if (self.start is None) != (self.end is None):
            raise ContractValidationError("start and end must be supplied together when coordinates are present.")
        if self.start is not None and self.end is not None:
            _coordinate(self.start, self.end)
        if self.strand is not None:
            _strand(self.strand)


@dataclass(frozen=True, slots=True)
class ComponentRevocation:
    revocation_id: str
    revocation_version: int
    target_kind: str
    target_id: str
    target_version: int
    reason_code: str
    scope: str
    effective_at: datetime | None
    authority_id: str
    approval_binding_id: str
    replacement_admission_id: str | None = None
    evidence_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("revocation_id", "target_kind", "target_id", "reason_code", "scope", "authority_id", "approval_binding_id"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        for name in ("revocation_version", "target_version"):
            object.__setattr__(self, name, _positive_int(getattr(self, name), name))
        refs = tuple(_nonempty(item, "evidence_refs") for item in (self.evidence_refs or ()))
        object.__setattr__(self, "evidence_refs", refs)


@dataclass(frozen=True, slots=True)
class ComponentLifecycleEvent:
    event_id: str
    event_version: int
    event_type: str
    subject_kind: str
    subject_id: str
    prior_state: str | None
    next_state: str
    authority_id: str
    approval_binding_id: str | None
    reason_code: str | None
    evidence_refs: tuple[str, ...]
    occurred_at: datetime | None
    actor_id: str
    correlation_id: str

    def __post_init__(self) -> None:
        for name in ("event_id", "event_type", "subject_kind", "subject_id", "next_state", "authority_id", "actor_id", "correlation_id"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        object.__setattr__(self, "event_version", _positive_int(self.event_version, "event_version"))
        for name in ("approval_binding_id", "reason_code", "prior_state"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _nonempty(value, name))
        object.__setattr__(self, "evidence_refs", tuple(_nonempty(item, "evidence_refs") for item in (self.evidence_refs or ())))


@dataclass(frozen=True, slots=True)
class BackboneResolutionEvidence:
    evidence_id: str
    backbone_id: str
    backbone_version: int
    provider: str
    accession: str
    source_version: str
    resolution_id: str
    expected_length: int
    expected_sha256: str
    retrieved_length: int
    retrieved_sha256: str
    authority_id: str
    provenance_version: str

    def __post_init__(self) -> None:
        for name in ("evidence_id", "backbone_id", "provider", "accession", "source_version", "resolution_id", "authority_id", "provenance_version"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        for name in ("backbone_version", "expected_length", "retrieved_length"):
            object.__setattr__(self, name, _positive_int(getattr(self, name), name))
        object.__setattr__(self, "expected_sha256", validate_sha256(self.expected_sha256, "expected_sha256"))
        object.__setattr__(self, "retrieved_sha256", validate_sha256(self.retrieved_sha256, "retrieved_sha256"))
        if self.expected_length != self.retrieved_length or self.expected_sha256 != self.retrieved_sha256:
            raise ContractValidationError("Backbone resolution evidence bytes do not match expected identity.")


@dataclass(frozen=True, slots=True)
class BackboneBoundaryEvidence:
    evidence_id: str
    backbone_id: str
    backbone_version: int
    boundary_type: str
    start: int
    end: int
    orientation: str
    preserved_flanks: Mapping[str, Any]
    expected_length: int
    expected_sha256: str
    authority_id: str
    provenance_version: str

    def __post_init__(self) -> None:
        for name in ("evidence_id", "backbone_id", "boundary_type", "authority_id", "provenance_version"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        if self.boundary_type not in {"insertion", "replacement"}:
            raise ContractValidationError("boundary_type must be insertion or replacement.")
        start, end = _coordinate(self.start, self.end)
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)
        object.__setattr__(self, "orientation", _strand(self.orientation))
        object.__setattr__(self, "preserved_flanks", _freeze_mapping(self.preserved_flanks, "preserved_flanks"))
        if not self.preserved_flanks:
            raise ContractValidationError("preserved_flanks must not be empty.")
        object.__setattr__(self, "backbone_version", _positive_int(self.backbone_version, "backbone_version"))
        object.__setattr__(self, "expected_length", _positive_int(self.expected_length, "expected_length"))
        object.__setattr__(self, "expected_sha256", validate_sha256(self.expected_sha256, "expected_sha256"))
        if self.end - self.start != self.expected_length:
            raise ContractValidationError("Backbone boundary span must equal expected_length.")


@dataclass(frozen=True, slots=True)
class BackboneApprovalBinding:
    evidence_id: str
    backbone_id: str
    backbone_version: int
    admission_id: str
    operation: str
    workflow_scope: tuple[str, ...]
    authority_id: str
    policy_version: str
    decision_id: str
    decision_hash: str
    decision_timestamp: datetime
    signature: str
    provenance_version: str

    def __post_init__(self) -> None:
        for name in ("evidence_id", "backbone_id", "admission_id", "operation", "authority_id", "policy_version", "decision_id", "signature", "provenance_version"):
            object.__setattr__(self, name, _nonempty(getattr(self, name), name))
        scopes = tuple(_nonempty(item, "workflow_scope") for item in (self.workflow_scope or ()))
        if not scopes:
            raise ContractValidationError("workflow_scope must not be empty.")
        object.__setattr__(self, "workflow_scope", scopes)
        object.__setattr__(self, "backbone_version", _positive_int(self.backbone_version, "backbone_version"))
        object.__setattr__(self, "decision_hash", validate_sha256(self.decision_hash, "decision_hash"))
        object.__setattr__(self, "decision_timestamp", _timestamp(self.decision_timestamp, "decision_timestamp"))


@dataclass(frozen=True, slots=True)
class BackboneRightsEvidence(RightsEvidence):
    backbone_id: str = ""
    backbone_version: int = 0

    def __post_init__(self) -> None:
        RightsEvidence.__post_init__(self)
        object.__setattr__(self, "backbone_id", _nonempty(self.backbone_id, "backbone_id"))
        object.__setattr__(self, "backbone_version", _positive_int(self.backbone_version, "backbone_version"))


def _revalidate_backbone_resolution(value: Any) -> BackboneResolutionEvidence:
    if not isinstance(value, BackboneResolutionEvidence):
        raise ContractValidationError("Backbone resolution evidence must use its structured contract.")
    return BackboneResolutionEvidence(
        value.evidence_id, value.backbone_id, value.backbone_version, value.provider,
        value.accession, value.source_version, value.resolution_id, value.expected_length,
        value.expected_sha256, value.retrieved_length, value.retrieved_sha256,
        value.authority_id, value.provenance_version,
    )


def _revalidate_backbone_boundary(value: Any) -> BackboneBoundaryEvidence:
    if not isinstance(value, BackboneBoundaryEvidence):
        raise ContractValidationError("Backbone boundary evidence must use its structured contract.")
    return BackboneBoundaryEvidence(
        value.evidence_id, value.backbone_id, value.backbone_version, value.boundary_type,
        value.start, value.end, value.orientation, value.preserved_flanks, value.expected_length,
        value.expected_sha256, value.authority_id, value.provenance_version,
    )


def _revalidate_backbone_approval(value: Any) -> BackboneApprovalBinding:
    if not isinstance(value, BackboneApprovalBinding):
        raise ContractValidationError("Backbone approval binding must use its structured contract.")
    return BackboneApprovalBinding(
        value.evidence_id, value.backbone_id, value.backbone_version, value.admission_id,
        value.operation, value.workflow_scope, value.authority_id, value.policy_version,
        value.decision_id, value.decision_hash, value.decision_timestamp, value.signature,
        value.provenance_version,
    )


def _revalidate_backbone_rights(value: Any) -> BackboneRightsEvidence:
    if not isinstance(value, BackboneRightsEvidence):
        raise ContractValidationError("Backbone rights evidence must use its structured contract.")
    return BackboneRightsEvidence(
        value.evidence_id, value.rights_dimension, value.operation, value.workflow_scope,
        value.reference_id, value.reference_version, value.admission_id, value.admission_version,
        value.authority_id, value.source_id, value.policy_version, value.decision_id,
        value.decision_hash, value.evaluated_at, value.valid_until, value.provenance,
        value.evidence_version, value.backbone_id, value.backbone_version,
    )


def validate_backbone_transition(prior_state: BackboneState | str, next_state: BackboneState | str, **evidence: Any) -> None:
    prior = _enum(prior_state, BackboneState, "prior_state")
    next_value = _enum(next_state, BackboneState, "next_state")
    order = tuple(BackboneState)
    if order.index(next_value) != order.index(prior) + 1:
        raise ContractValidationError(f"Illegal backbone transition: {prior.value} -> {next_value.value}.")
    required = {
        BackboneState.BACKBONE_RESOLUTION_ELIGIBLE: ("resolution_evidence", "rights_evidence"),
        BackboneState.BACKBONE_BOUNDARY_VERIFIED: ("resolution_evidence", "boundary_evidence", "rights_evidence"),
        BackboneState.FORMALLY_ADMITTED_BACKBONE: ("resolution_evidence", "boundary_evidence", "approval_binding", "rights_evidence"),
        BackboneState.SELECTABLE_BACKBONE: ("resolution_evidence", "boundary_evidence", "approval_binding", "rights_evidence"),
    }
    validators = {
        "resolution_evidence": _revalidate_backbone_resolution,
        "boundary_evidence": _revalidate_backbone_boundary,
        "approval_binding": _revalidate_backbone_approval,
        "rights_evidence": _revalidate_backbone_rights,
    }
    revalidated = {}
    for name, validator in validators.items():
        if name not in required.get(next_value, ()) and name not in evidence:
            continue
        try:
            revalidated[name] = validator(evidence.get(name))
        except ContractValidationError as exc:
            qualifier = "requires" if name in required.get(next_value, ()) else "contains"
            raise ContractValidationError(f"{next_value.value} {qualifier} valid {name}.") from exc
    typed = list(revalidated.values())
    identities = {(value.backbone_id, value.backbone_version) for value in typed}
    if len(identities) > 1:
        raise ContractValidationError("Backbone evidence must share one exact backbone identity/version.")
    boundary = revalidated.get("boundary_evidence")
    resolution = revalidated.get("resolution_evidence")
    if boundary is not None and resolution is not None and (
        boundary.expected_length,
        boundary.expected_sha256,
    ) != (
        resolution.expected_length,
        resolution.expected_sha256,
    ):
        raise ContractValidationError("Backbone boundary and resolution identities must match.")
    approval = revalidated.get("approval_binding")
    rights = revalidated.get("rights_evidence")
    if approval is not None and rights is not None and approval.admission_id != rights.admission_id:
        raise ContractValidationError("Backbone approval and rights admission identities must match.")
    if next_value is BackboneState.SELECTABLE_BACKBONE:
        boundary = revalidated["boundary_evidence"]
        resolution = revalidated["resolution_evidence"]
        if boundary.end - boundary.start != boundary.expected_length:
            raise ContractValidationError("Selectable backbone requires an exact boundary span.")
        if (boundary.expected_length, boundary.expected_sha256) != (resolution.expected_length, resolution.expected_sha256):
            raise ContractValidationError("Selectable backbone boundary and resolution identities must match.")


@dataclass(frozen=True, slots=True)
class BackboneLifecycle:
    backbone_id: str
    backbone_version: int
    state: BackboneState = BackboneState.REFERENCE_BACKBONE
    boundary_evidence: BackboneBoundaryEvidence | None = None
    resolution_evidence: BackboneResolutionEvidence | None = None
    approval_binding: BackboneApprovalBinding | None = None
    rights_evidence: BackboneRightsEvidence | None = None
    lifecycle_status: ReferenceLifecycleStatus = ReferenceLifecycleStatus.ACTIVE

    def __post_init__(self) -> None:
        object.__setattr__(self, "backbone_id", _nonempty(self.backbone_id, "backbone_id"))
        object.__setattr__(self, "backbone_version", _positive_int(self.backbone_version, "backbone_version"))
        object.__setattr__(self, "state", _enum(self.state, BackboneState, "state"))
        for name, cls in (("boundary_evidence", BackboneBoundaryEvidence), ("resolution_evidence", BackboneResolutionEvidence), ("approval_binding", BackboneApprovalBinding), ("rights_evidence", BackboneRightsEvidence)):
            value = getattr(self, name)
            if value is not None and not isinstance(value, cls):
                raise ContractValidationError(f"{name} must use its structured evidence contract.")
        object.__setattr__(self, "lifecycle_status", _enum(self.lifecycle_status, ReferenceLifecycleStatus, "lifecycle_status"))
        index = tuple(BackboneState).index(self.state)
        if index >= 1 and (not isinstance(self.resolution_evidence, BackboneResolutionEvidence) or not isinstance(self.rights_evidence, BackboneRightsEvidence)):
            raise ContractValidationError("Backbone resolution eligibility requires structured resolution and rights evidence.")
        if index >= 2 and not isinstance(self.boundary_evidence, BackboneBoundaryEvidence):
            raise ContractValidationError("Backbone boundary verification requires evidence.")
        if index >= 3 and not isinstance(self.approval_binding, BackboneApprovalBinding):
            raise ContractValidationError("Formal backbone admission requires approval binding.")
        if index >= 4 and not isinstance(self.rights_evidence, BackboneRightsEvidence):
            raise ContractValidationError("Selectable backbone requires rights evidence.")
        if self.state is BackboneState.SELECTABLE_BACKBONE and self.lifecycle_status is not ReferenceLifecycleStatus.ACTIVE:
            raise ContractValidationError("Retired or revoked backbones cannot be selectable.")
        for name in ("resolution_evidence", "boundary_evidence", "approval_binding", "rights_evidence"):
            value = getattr(self, name)
            if value is not None and (value.backbone_id != self.backbone_id or value.backbone_version != self.backbone_version):
                raise ContractValidationError(f"{name} identity does not match the backbone.")
        if self.boundary_evidence is not None and self.resolution_evidence is not None:
            if (self.boundary_evidence.expected_length, self.boundary_evidence.expected_sha256) != (self.resolution_evidence.expected_length, self.resolution_evidence.expected_sha256):
                raise ContractValidationError("Backbone boundary and resolution identities must match.")
            if self.boundary_evidence.end - self.boundary_evidence.start != self.boundary_evidence.expected_length:
                raise ContractValidationError("Backbone boundary span must equal expected_length.")


def is_component_selectable(
    reference: ComponentReference | None = None,
    admission: ComponentAdmission | None = None,
    rights: RightsState | None = None,
    resolution: ComponentResolvedSequence | None = None,
    *,
    workflow_role: str | None = None,
    workflow_scope: str | None = None,
    evaluation_time: datetime | str | None = None,
    now_utc: datetime | str | None = None,
) -> bool:
    """Return true only when every identity, resolution, rights, and scope gate is explicit."""
    if not all(isinstance(value, expected) for value, expected in ((reference, ComponentReference), (admission, ComponentAdmission), (rights, RightsState), (resolution, ComponentResolvedSequence))):
        return False
    assert reference is not None and admission is not None and rights is not None and resolution is not None
    evaluation_was_explicit = evaluation_time is not None or now_utc is not None
    try:
        instant = _direct_use_evaluation_time(
            evaluation_time, now_utc, default_to_current=True
        )
        _approval_binding(
            admission.approval_binding,
            admission_id=admission.admission_id,
            reference_id=admission.reference_id,
            reference_version=admission.reference_version,
        )
    except ContractValidationError:
        return False
    if not _is_admission_current_at(
        admission, instant, evaluation_was_explicit=evaluation_was_explicit
    ) or reference.lifecycle_status is not ReferenceLifecycleStatus.ACTIVE:
        return False
    if resolution.status is not ResolutionStatus.RESOLVED or not resolution.sequence:
        return False
    if (admission.reference_id, admission.reference_version) != (reference.reference_id, reference.reference_version):
        return False
    if resolution.expected_length != resolution.retrieved_length or resolution.expected_sha256 != resolution.retrieved_sha256:
        return False
    if len(resolution.sequence) != resolution.retrieved_length or sequence_sha256(resolution.sequence) != resolution.retrieved_sha256:
        return False
    if resolution.component_id is not None and resolution.component_id != reference.component_id:
        return False
    if resolution.admission_id != admission.admission_id or resolution.admission_version != admission.admission_version:
        return False
    source = reference.source_provenance
    if source.get("accession") != resolution.accession or source.get("source_version") != resolution.version:
        return False
    if resolution.feature_identity != reference.component_id:
        return False
    if resolution.end - resolution.start != resolution.expected_length:
        return False
    boundary = reference.boundary_descriptor
    for key, actual in (("start", resolution.start), ("end", resolution.end), ("strand", resolution.strand), ("coordinate_system", resolution.coordinate_system)):
        if key in boundary and boundary[key] != actual:
            return False
    if workflow_role is None or workflow_scope is None or workflow_role not in admission.role_scope or workflow_scope not in admission.workflow_scope:
        return False
    for dimension in ("runtime_resolution", "local_materialization"):
        if getattr(rights, _RIGHTS_FIELDS[dimension]) is not RightsDecision.ELIGIBLE:
            return False
        evidence = rights.evidence.get(dimension)
        if not _valid_rights_evidence(evidence, dimension, reference_id=reference.reference_id, reference_version=reference.reference_version, admission_id=admission.admission_id, admission_version=admission.admission_version, workflow_scope=workflow_scope, evaluation_time=instant):
            return False
    return True


def is_backbone_selectable(backbone: BackboneLifecycle | None, *, workflow_scope: str | None = None,
                           operation: str = "direct_use",
                           evaluation_time: datetime | str | None = None,
                           now_utc: datetime | str | None = None) -> bool:
    """Evaluate the complete, identity-bound backbone selection gate."""
    if not isinstance(backbone, BackboneLifecycle) or backbone.state is not BackboneState.SELECTABLE_BACKBONE:
        return False
    if backbone.lifecycle_status is not ReferenceLifecycleStatus.ACTIVE:
        return False
    try:
        instant = _direct_use_evaluation_time(evaluation_time, now_utc)
        resolution = _revalidate_backbone_resolution(backbone.resolution_evidence)
        boundary = _revalidate_backbone_boundary(backbone.boundary_evidence)
        approval = _revalidate_backbone_approval(backbone.approval_binding)
        rights = _revalidate_backbone_rights(backbone.rights_evidence)
    except ContractValidationError:
        return False
    if workflow_scope is None or workflow_scope not in approval.workflow_scope or approval.operation != operation:
        return False
    if any(value.backbone_id != backbone.backbone_id or value.backbone_version != backbone.backbone_version for value in (resolution, boundary, approval, rights)):
        return False
    if (boundary.expected_length, boundary.expected_sha256) != (resolution.expected_length, resolution.expected_sha256):
        return False
    if approval.admission_id != rights.admission_id:
        return False
    if workflow_scope not in rights.workflow_scope or rights.operation != "runtime_resolution":
        return False
    if rights.valid_until is not None:
        if instant is None or rights.valid_until <= instant:
            return False
    if boundary.boundary_type not in {"insertion", "replacement"} or not boundary.preserved_flanks:
        return False
    return True


__all__ = [
    "AdmissionState", "ApprovalBinding", "BackboneLifecycle", "BackboneState", "ComponentAdmission",
    "ComponentLifecycleEvent", "ComponentReference", "ComponentResolvedSequence",
    "ComponentResolutionRequest", "ComponentRevocation", "ComponentSelectionSnapshot",
    "ComponentType", "ContractValidationError", "ReferenceLifecycleStatus", "ResolutionFailureCode",
    "ResolutionStatus", "RightsDecision", "RightsOutcome", "RightsState", "SelectionSource",
    "BackboneApprovalBinding", "BackboneBoundaryEvidence", "BackboneResolutionEvidence", "BackboneRightsEvidence", "RightsEvidence",
    "is_admission_current", "is_backbone_selectable", "is_component_selectable", "normalize_sequence", "sequence_sha256", "validate_admission_transition",
    "validate_backbone_transition", "validate_sha256",
]
