"""Transactional persistence for the component direct-use admission lifecycle.

This Impl-02 repository is deliberately not wired into application startup. A
caller must provide its SQLite path, which keeps the current unified database
schema and its approved fingerprint unchanged until a later migration is
explicitly authorized.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from services.component_direct_use_contracts import (
    AdmissionState,
    ApprovalBinding,
    ComponentAdmission,
    ComponentLifecycleEvent,
    ContractValidationError,
    ResolutionFailureCode,
    RightsDecision,
    RightsEvidence,
    RightsState,
    validate_admission_transition,
)


SCHEMA_NAME = "component_direct_use_admission_lifecycle"
SCHEMA_VERSION = "1"
SUBJECT_KIND = "component_admission"
TRANSACTION_STATUS = "COMMITTED"
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RIGHTS_DECISION_FIELDS = (
    "rights_for_bundling",
    "rights_for_runtime_resolution",
    "rights_for_local_materialization",
    "rights_for_reference_metadata",
)
_CREATE_WRITES = (
    "assignment_ledger",
    "lifecycle_event",
    "admission_snapshot",
    "commit_marker",
)
_TRANSITION_WRITES = (
    "lifecycle_event",
    "admission_snapshot",
    "commit_marker",
)
_TRANSITION_WITH_APPROVAL_WRITES = (
    "approval_binding",
    *_TRANSITION_WRITES,
)
_APPROVAL_REQUIRED_STATES = frozenset(
    {
        AdmissionState.ASSIGNMENT_APPROVED,
        AdmissionState.FORMALLY_ADMITTED,
        AdmissionState.REVOKED,
        AdmissionState.RETIRED,
    }
)
_EVENT_TYPE_BY_STATE = {
    AdmissionState.DRY_RUN_ASSIGNABLE: "ADMISSION_CREATED",
    AdmissionState.ASSIGNMENT_APPROVED: "ASSIGNMENT_APPROVED",
    AdmissionState.ASSIGNED_NOT_ADMITTED: "ASSIGNMENT_COMMITTED",
    AdmissionState.FORMALLY_ADMITTED: "FORMAL_ADMISSION",
    AdmissionState.ADMISSION_FAILED: "ADMISSION_FAILED",
    AdmissionState.REVOKED: "ADMISSION_REVOKED",
    AdmissionState.RETIRED: "ADMISSION_RETIRED",
}


class AdmissionPersistenceError(RuntimeError):
    """Base class for durable admission lifecycle failures."""


class PersistenceIntegrityError(AdmissionPersistenceError):
    """Persisted state is malformed, inconsistent, or unsupported."""


class AdmissionNotFound(AdmissionPersistenceError):
    pass


class DuplicatePersistenceIdentity(AdmissionPersistenceError):
    pass


class StaleAdmissionState(AdmissionPersistenceError):
    pass


class TransactionReplayConflict(AdmissionPersistenceError):
    pass


FaultHook = Callable[[str], None]


@dataclass(frozen=True, slots=True)
class AssignmentLedgerEntry:
    assignment_id: str
    admission_id: str
    admission_version: int
    component_id: str
    reference_id: str
    reference_version: int
    assignee_id: str
    workflow_scope: tuple[str, ...]
    role_scope: tuple[str, ...]
    authority_id: str
    source: str
    provenance: Mapping[str, Any]
    created_at: datetime
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "assignment_id",
            "admission_id",
            "component_id",
            "reference_id",
            "assignee_id",
            "authority_id",
        ):
            object.__setattr__(self, name, _identity(getattr(self, name), name))
        for name in ("admission_version", "reference_version"):
            object.__setattr__(self, name, _positive_int(getattr(self, name), name))
        for name in ("workflow_scope", "role_scope"):
            values = tuple(_identity(item, name) for item in getattr(self, name))
            if not values or len(values) != len(set(values)):
                raise ContractValidationError(f"{name} must contain unique identities.")
            object.__setattr__(self, name, values)
        object.__setattr__(self, "source", _text(self.source, "source"))
        provenance = _json_mapping(self.provenance, "provenance")
        if not provenance:
            raise ContractValidationError("provenance must not be empty.")
        object.__setattr__(self, "provenance", _freeze_json(provenance))
        object.__setattr__(self, "created_at", _timestamp(self.created_at, "created_at"))
        if self.schema_version != SCHEMA_VERSION:
            raise ContractValidationError("assignment schema_version is unsupported.")


@dataclass(frozen=True, slots=True)
class LifecycleEventRecord:
    event: ComponentLifecycleEvent
    sequence_no: int
    previous_event_id: str | None
    payload_sha256: str
    chain_sha256: str
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class AdmissionLifecycleRecord:
    assignment: AssignmentLedgerEntry
    current_admission: ComponentAdmission
    admission_history: tuple[ComponentAdmission, ...]
    events: tuple[ComponentLifecycleEvent, ...]
    event_records: tuple[LifecycleEventRecord, ...]
    approval_bindings: tuple[ApprovalBinding, ...]
    transaction_ids: tuple[str, ...]


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractValidationError(f"{field_name} must be a non-empty string.")
    result = value.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in result):
        raise ContractValidationError(f"{field_name} contains a control character.")
    return result


def _identity(value: Any, field_name: str) -> str:
    result = _text(value, field_name)
    if _IDENTITY_RE.fullmatch(result) is None:
        raise ContractValidationError(f"{field_name} is not a valid identity.")
    return result


def _positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ContractValidationError(f"{field_name} must be a positive integer.")
    return value


def _timestamp(value: Any, field_name: str) -> datetime:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        try:
            result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ContractValidationError(
                f"{field_name} must be an ISO-8601 timestamp."
            ) from exc
    else:
        raise ContractValidationError(f"{field_name} must be an ISO-8601 timestamp.")
    if result.tzinfo is None or result.utcoffset() is None:
        raise ContractValidationError(f"{field_name} must include timezone information.")
    return result.astimezone(timezone.utc)


def _timestamp_text(value: Any, field_name: str) -> str:
    return _timestamp(value, field_name).isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _json_value(value: Any, field_name: str = "value") -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return _timestamp_text(value, field_name)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractValidationError(f"{field_name} contains a non-finite number.")
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key in result:
                raise ContractValidationError(f"{field_name} requires unique string keys.")
            result[key] = _json_value(item, f"{field_name}.{key}")
        return result
    if isinstance(value, (tuple, list)):
        return [_json_value(item, field_name) for item in value]
    raise ContractValidationError(f"{field_name} must contain JSON-compatible data.")


def _json_mapping(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractValidationError(f"{field_name} must be a mapping.")
    return _json_value(value, field_name)


def _freeze_json(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_json(item) for item in value)
    return value


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            _json_value(value),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ContractValidationError("payload must be canonical JSON data.") from exc


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _payload_and_hash(value: Any) -> tuple[str, str]:
    payload = _canonical_json(value)
    return payload, _sha256_text(payload)


def _strict_object(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise PersistenceIntegrityError(f"{label} fields do not match schema {SCHEMA_VERSION}.")
    return value


def _parse_payload(payload_text: Any, payload_sha256: Any, label: str) -> dict[str, Any]:
    if not isinstance(payload_text, str) or not isinstance(payload_sha256, str):
        raise PersistenceIntegrityError(f"{label} payload is malformed.")
    if _SHA256_RE.fullmatch(payload_sha256) is None:
        raise PersistenceIntegrityError(f"{label} payload hash is malformed.")
    if _sha256_text(payload_text) != payload_sha256:
        raise PersistenceIntegrityError(f"{label} payload hash does not match.")
    try:
        value = json.loads(payload_text)
    except (TypeError, ValueError) as exc:
        raise PersistenceIntegrityError(f"{label} payload is not valid JSON.") from exc
    try:
        is_canonical = isinstance(value, dict) and _canonical_json(value) == payload_text
    except ContractValidationError as exc:
        raise PersistenceIntegrityError(f"{label} payload is malformed.") from exc
    if not is_canonical:
        raise PersistenceIntegrityError(f"{label} payload is not canonical JSON.")
    return value


def _approval_payload(value: ApprovalBinding) -> dict[str, Any]:
    try:
        rebuilt = ApprovalBinding(
            **{item.name: getattr(value, item.name) for item in fields(ApprovalBinding) if item.init}
        )
    except (AttributeError, TypeError, ContractValidationError) as exc:
        raise ContractValidationError("approval binding failed contract validation.") from exc
    return {
        item.name: _json_value(getattr(rebuilt, item.name), item.name)
        for item in fields(ApprovalBinding)
        if item.init
    }


def _approval_from_payload(value: Any) -> ApprovalBinding:
    expected = {item.name for item in fields(ApprovalBinding) if item.init}
    raw = _strict_object(value, expected, "approval binding")
    try:
        return ApprovalBinding(**raw)
    except (TypeError, ContractValidationError) as exc:
        raise PersistenceIntegrityError("approval binding failed contract validation.") from exc


def _rights_evidence_payload(value: RightsEvidence) -> dict[str, Any]:
    try:
        rebuilt = RightsEvidence(
            **{item.name: getattr(value, item.name) for item in fields(RightsEvidence) if item.init}
        )
    except (AttributeError, TypeError, ContractValidationError) as exc:
        raise ContractValidationError("rights evidence failed contract validation.") from exc
    return {
        item.name: _json_value(getattr(rebuilt, item.name), item.name)
        for item in fields(RightsEvidence)
        if item.init
    }


def _rights_evidence_from_payload(value: Any) -> RightsEvidence:
    expected = {item.name for item in fields(RightsEvidence) if item.init}
    raw = _strict_object(value, expected, "rights evidence")
    try:
        return RightsEvidence(**raw)
    except (TypeError, ContractValidationError) as exc:
        raise PersistenceIntegrityError("rights evidence failed contract validation.") from exc


def _rights_payload(value: RightsState) -> dict[str, Any]:
    if not isinstance(value, RightsState):
        raise ContractValidationError("rights_snapshot must use RightsState.")
    evidence: dict[str, Any] = {}
    for dimension, item in value.evidence.items():
        if not isinstance(dimension, str) or not isinstance(item, RightsEvidence):
            raise ContractValidationError("rights evidence must use structured evidence records.")
        evidence[dimension] = _rights_evidence_payload(item)
    return {
        **{name: getattr(value, name).value for name in _RIGHTS_DECISION_FIELDS},
        "evidence": evidence,
    }


def _rights_from_payload(value: Any) -> RightsState:
    expected = {*_RIGHTS_DECISION_FIELDS, "evidence"}
    raw = _strict_object(value, expected, "rights snapshot")
    evidence_raw = raw["evidence"]
    if not isinstance(evidence_raw, dict):
        raise PersistenceIntegrityError("rights evidence collection is malformed.")
    evidence = {
        dimension: _rights_evidence_from_payload(item)
        for dimension, item in evidence_raw.items()
    }
    try:
        return RightsState(
            **{name: RightsDecision(raw[name]) for name in _RIGHTS_DECISION_FIELDS},
            evidence=evidence,
        )
    except (TypeError, ValueError, ContractValidationError) as exc:
        raise PersistenceIntegrityError("rights snapshot failed contract validation.") from exc


def _admission_payload(value: ComponentAdmission, *, revalidate: bool = True) -> dict[str, Any]:
    if revalidate:
        try:
            raw = {
                "admission_id": value.admission_id,
                "admission_version": value.admission_version,
                "reference_id": value.reference_id,
                "reference_version": value.reference_version,
                "assignment_id": value.assignment_id,
                "state": value.state.value,
                "workflow_scope": list(value.workflow_scope),
                "role_scope": list(value.role_scope),
                "rights_snapshot": _rights_payload(value.rights_snapshot),
                "approval_binding": _approval_payload(value.approval_binding)
                if isinstance(value.approval_binding, ApprovalBinding)
                else {},
                "effective_at": None
                if value.effective_at is None
                else _timestamp_text(value.effective_at, "effective_at"),
                "expires_at": None
                if value.expires_at is None
                else _timestamp_text(value.expires_at, "expires_at"),
                "audit_provenance": _json_mapping(value.audit_provenance, "audit_provenance"),
            }
            rebuilt = _admission_from_payload(raw)
        except (AttributeError, PersistenceIntegrityError) as exc:
            raise ContractValidationError("admission failed contract validation.") from exc
        return _admission_payload(rebuilt, revalidate=False)
    return {
        "admission_id": value.admission_id,
        "admission_version": value.admission_version,
        "reference_id": value.reference_id,
        "reference_version": value.reference_version,
        "assignment_id": value.assignment_id,
        "state": value.state.value,
        "workflow_scope": list(value.workflow_scope),
        "role_scope": list(value.role_scope),
        "rights_snapshot": _rights_payload(value.rights_snapshot),
        "approval_binding": _approval_payload(value.approval_binding)
        if isinstance(value.approval_binding, ApprovalBinding)
        else {},
        "effective_at": None
        if value.effective_at is None
        else _timestamp_text(value.effective_at, "effective_at"),
        "expires_at": None
        if value.expires_at is None
        else _timestamp_text(value.expires_at, "expires_at"),
        "audit_provenance": _json_mapping(value.audit_provenance, "audit_provenance"),
    }


def _admission_from_payload(value: Any) -> ComponentAdmission:
    expected = {item.name for item in fields(ComponentAdmission) if item.init}
    raw = _strict_object(value, expected, "admission")
    try:
        admission = ComponentAdmission(
            **{
                **raw,
                "rights_snapshot": _rights_from_payload(raw["rights_snapshot"]),
                "approval_binding": _approval_from_payload(raw["approval_binding"])
                if raw["approval_binding"]
                else {},
            }
        )
    except (TypeError, ValueError, ContractValidationError) as exc:
        raise PersistenceIntegrityError("admission failed contract validation.") from exc
    _validate_rights_bindings(admission)
    return admission


def _validate_rights_bindings(admission: ComponentAdmission) -> None:
    for dimension, evidence in admission.rights_snapshot.evidence.items():
        try:
            rebuilt = RightsEvidence(
                **{
                    item.name: getattr(evidence, item.name)
                    for item in fields(RightsEvidence)
                    if item.init
                }
            )
        except (AttributeError, TypeError, ContractValidationError) as exc:
            raise PersistenceIntegrityError("rights evidence failed contract validation.") from exc
        if dimension != rebuilt.rights_dimension:
            raise PersistenceIntegrityError("rights evidence dimension key does not match.")
        if (
            rebuilt.reference_id,
            rebuilt.reference_version,
            rebuilt.admission_id,
            rebuilt.admission_version,
        ) != (
            admission.reference_id,
            admission.reference_version,
            admission.admission_id,
            admission.admission_version,
        ):
            raise PersistenceIntegrityError("rights evidence identity does not match admission.")
        if not set(admission.workflow_scope).issubset(rebuilt.workflow_scope):
            raise PersistenceIntegrityError("rights evidence scope does not cover admission.")


def _event_payload(
    value: ComponentLifecycleEvent, *, revalidate: bool = True
) -> dict[str, Any]:
    if revalidate:
        raw = {
            item.name: _json_value(getattr(value, item.name), item.name)
            for item in fields(ComponentLifecycleEvent)
            if item.init
        }
        try:
            rebuilt = _event_from_payload(raw)
        except (AttributeError, PersistenceIntegrityError) as exc:
            raise ContractValidationError("lifecycle event failed contract validation.") from exc
        return _event_payload(rebuilt, revalidate=False)
    return {
        item.name: _json_value(getattr(value, item.name), item.name)
        for item in fields(ComponentLifecycleEvent)
        if item.init
    }


def _event_from_payload(value: Any) -> ComponentLifecycleEvent:
    expected = {item.name for item in fields(ComponentLifecycleEvent) if item.init}
    raw = _strict_object(value, expected, "lifecycle event")
    if raw["occurred_at"] is None:
        raise PersistenceIntegrityError("lifecycle event occurred_at is required.")
    try:
        raw = {**raw, "occurred_at": _timestamp(raw["occurred_at"], "occurred_at")}
        event = ComponentLifecycleEvent(**raw)
        _identity(event.event_id, "event_id")
        _identity(event.subject_id, "subject_id")
        _identity(event.authority_id, "authority_id")
        _identity(event.actor_id, "actor_id")
        _identity(event.correlation_id, "correlation_id")
        if event.approval_binding_id is not None:
            _identity(event.approval_binding_id, "approval_binding_id")
    except (TypeError, ContractValidationError) as exc:
        raise PersistenceIntegrityError("lifecycle event failed contract validation.") from exc
    return event


def _assignment_payload(value: AssignmentLedgerEntry) -> dict[str, Any]:
    try:
        rebuilt = AssignmentLedgerEntry(
            **{item.name: getattr(value, item.name) for item in fields(AssignmentLedgerEntry)}
        )
    except (AttributeError, TypeError, ContractValidationError) as exc:
        raise ContractValidationError("assignment failed contract validation.") from exc
    return {
        item.name: _json_value(getattr(rebuilt, item.name), item.name)
        for item in fields(AssignmentLedgerEntry)
    }


def _assignment_from_payload(value: Any) -> AssignmentLedgerEntry:
    expected = {item.name for item in fields(AssignmentLedgerEntry)}
    raw = _strict_object(value, expected, "assignment")
    try:
        return AssignmentLedgerEntry(**raw)
    except (TypeError, ContractValidationError) as exc:
        raise PersistenceIntegrityError("assignment failed contract validation.") from exc


def _stable_admission_payload(value: ComponentAdmission) -> dict[str, Any]:
    payload = _admission_payload(value)
    payload.pop("state")
    payload.pop("approval_binding")
    return payload


def _validate_assignment_binding(
    assignment: AssignmentLedgerEntry, admission: ComponentAdmission
) -> None:
    if (
        assignment.assignment_id,
        assignment.admission_id,
        assignment.admission_version,
        assignment.reference_id,
        assignment.reference_version,
        assignment.workflow_scope,
        assignment.role_scope,
    ) != (
        admission.assignment_id,
        admission.admission_id,
        admission.admission_version,
        admission.reference_id,
        admission.reference_version,
        admission.workflow_scope,
        admission.role_scope,
    ):
        raise ContractValidationError("assignment identity or scope does not match admission.")


def _validate_initial_event(
    assignment: AssignmentLedgerEntry,
    admission: ComponentAdmission,
    event: ComponentLifecycleEvent,
    transaction_id: str,
    recorded_at: datetime,
) -> None:
    if admission.state is not AdmissionState.DRY_RUN_ASSIGNABLE:
        raise ContractValidationError("initial admission state must be DRY_RUN_ASSIGNABLE.")
    if event.subject_kind != SUBJECT_KIND or event.subject_id != admission.admission_id:
        raise ContractValidationError("lifecycle event subject does not match admission.")
    if event.prior_state is not None or event.next_state != admission.state.value:
        raise ContractValidationError("initial lifecycle event state is inconsistent.")
    if event.event_type != _EVENT_TYPE_BY_STATE[admission.state]:
        raise ContractValidationError("initial lifecycle event type is inconsistent.")
    if event.approval_binding_id is not None:
        raise ContractValidationError("initial lifecycle event cannot claim approval.")
    if event.correlation_id != transaction_id:
        raise ContractValidationError("event correlation_id must equal transaction_id.")
    if event.authority_id != assignment.authority_id:
        raise ContractValidationError("initial event authority does not match assignment.")
    if event.occurred_at > recorded_at or assignment.created_at > recorded_at:
        raise ContractValidationError("initial event timestamps are not ordered.")


def _transition_failure_arguments(
    event: ComponentLifecycleEvent, target_state: AdmissionState
) -> tuple[ResolutionFailureCode | None, str | None]:
    if target_state is AdmissionState.ADMISSION_FAILED:
        try:
            return ResolutionFailureCode(event.reason_code), None
        except (TypeError, ValueError) as exc:
            raise ContractValidationError(
                "admission failure event requires a supported failure code."
            ) from exc
    if target_state is AdmissionState.REVOKED:
        return None, _text(event.reason_code, "reason_code")
    return None, None


class ComponentAdmissionRepository:
    """Append-only SQLite repository for one admission lifecycle slice."""

    def __init__(
        self, database_path: str | Path, *, fault_hook: FaultHook | None = None
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve(strict=False)
        self.fault_hook = fault_hook

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            if not self.database_path.is_file():
                raise AdmissionNotFound("admission repository does not exist.")
            try:
                connection = sqlite3.connect(
                    f"file:{self.database_path.as_posix()}?mode=ro",
                    uri=True,
                    timeout=2.0,
                )
            except sqlite3.Error as exc:
                raise PersistenceIntegrityError(
                    "admission repository database could not be opened for reading."
                ) from exc
        else:
            try:
                self.database_path.parent.mkdir(parents=True, exist_ok=True)
                connection = sqlite3.connect(str(self.database_path), timeout=2.0)
            except (OSError, sqlite3.Error) as exc:
                raise AdmissionPersistenceError(
                    "admission repository database could not be opened for writing."
                ) from exc
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 2000")
        return connection

    def initialize(self) -> None:
        connection = self._connect()
        try:
            existing = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
                if row["name"] in _EXPECTED_COLUMNS
            }
            if existing and existing != set(_EXPECTED_COLUMNS):
                raise PersistenceIntegrityError("admission repository schema is incomplete.")
            if not existing:
                connection.executescript(_SCHEMA_SQL)
                connection.execute(
                    "INSERT INTO component_direct_use_schema (schema_name, schema_version) VALUES (?, ?)",
                    (SCHEMA_NAME, SCHEMA_VERSION),
                )
            self._require_schema(connection)
            connection.commit()
        except PersistenceIntegrityError:
            connection.rollback()
            raise
        except sqlite3.Error as exc:
            connection.rollback()
            raise AdmissionPersistenceError("admission repository schema could not be initialized.") from exc
        finally:
            connection.close()

    def create_admission(
        self,
        assignment: AssignmentLedgerEntry,
        admission: ComponentAdmission,
        event: ComponentLifecycleEvent,
        *,
        transaction_id: str,
        recorded_at: datetime | str,
    ) -> AdmissionLifecycleRecord:
        transaction_id = _identity(transaction_id, "transaction_id")
        recorded = _timestamp(recorded_at, "recorded_at")
        assignment_payload = _assignment_payload(assignment)
        admission_payload = _admission_payload(admission)
        event_payload = _event_payload(event)
        rebuilt_assignment = _assignment_from_payload(assignment_payload)
        rebuilt_admission = _admission_from_payload(admission_payload)
        rebuilt_event = _event_from_payload(event_payload)
        _validate_assignment_binding(rebuilt_assignment, rebuilt_admission)
        _validate_initial_event(
            rebuilt_assignment, rebuilt_admission, rebuilt_event, transaction_id, recorded
        )
        input_value = self._transaction_input(
            operation="CREATE",
            transaction_id=transaction_id,
            expected_state=None,
            recorded_at=recorded,
            assignment=assignment_payload,
            admission=admission_payload,
            event=event_payload,
            approval=None,
        )
        input_hash = _payload_and_hash(input_value)[1]
        self.initialize()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._replay_result(connection, transaction_id, input_hash)
            if replay is not None:
                connection.rollback()
                return replay
            if connection.execute(
                "SELECT 1 FROM direct_use_admission_snapshots WHERE admission_id = ? LIMIT 1",
                (rebuilt_admission.admission_id,),
            ).fetchone():
                raise DuplicatePersistenceIdentity("admission_id already exists.")
            for table, column, value, label in (
                ("direct_use_assignment_ledger", "assignment_id", rebuilt_assignment.assignment_id, "assignment_id"),
                ("direct_use_lifecycle_events", "event_id", rebuilt_event.event_id, "event_id"),
            ):
                if connection.execute(
                    f"SELECT 1 FROM {table} WHERE {column} = ?", (value,)
                ).fetchone():
                    raise DuplicatePersistenceIdentity(f"{label} already exists.")
            assignment_text, assignment_hash = _payload_and_hash(assignment_payload)
            connection.execute(
                """INSERT INTO direct_use_assignment_ledger (
                    assignment_id, admission_id, admission_version, component_id,
                    reference_id, reference_version, schema_version, created_transaction_id,
                    created_at, payload_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rebuilt_assignment.assignment_id,
                    rebuilt_assignment.admission_id,
                    rebuilt_assignment.admission_version,
                    rebuilt_assignment.component_id,
                    rebuilt_assignment.reference_id,
                    rebuilt_assignment.reference_version,
                    SCHEMA_VERSION,
                    transaction_id,
                    _timestamp_text(rebuilt_assignment.created_at, "created_at"),
                    assignment_text,
                    assignment_hash,
                ),
            )
            self._fault("after_assignment_write")
            self._insert_event(
                connection,
                assignment=rebuilt_assignment,
                event=rebuilt_event,
                sequence_no=1,
                previous_event_id=None,
                previous_chain_hash=None,
                transaction_id=transaction_id,
                recorded_at=recorded,
            )
            self._fault("after_event_write")
            self._insert_snapshot(
                connection,
                rebuilt_admission,
                sequence_no=1,
                transaction_id=transaction_id,
                recorded_at=recorded,
            )
            self._fault("after_current_state_write")
            self._insert_journal(
                connection,
                operation="CREATE",
                transaction_id=transaction_id,
                admission_id=rebuilt_admission.admission_id,
                sequence_no=1,
                expected_state=None,
                target_state=rebuilt_admission.state.value,
                input_sha256=input_hash,
                ordered_writes=_CREATE_WRITES,
                recorded_at=recorded,
            )
            self._fault("after_journal_write")
            connection.commit()
        except (
            AdmissionPersistenceError,
            ContractValidationError,
        ):
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise AdmissionPersistenceError(
                "admission creation transaction failed; no lifecycle state was committed."
            ) from exc
        finally:
            connection.close()
        return self.load(rebuilt_admission.admission_id)

    def transition_admission(
        self,
        admission: ComponentAdmission,
        event: ComponentLifecycleEvent,
        *,
        expected_state: AdmissionState | str,
        transaction_id: str,
        recorded_at: datetime | str,
        approval_binding: ApprovalBinding | None = None,
    ) -> AdmissionLifecycleRecord:
        transaction_id = _identity(transaction_id, "transaction_id")
        recorded = _timestamp(recorded_at, "recorded_at")
        try:
            expected = expected_state if isinstance(expected_state, AdmissionState) else AdmissionState(expected_state)
        except (TypeError, ValueError) as exc:
            raise ContractValidationError("expected_state is unsupported.") from exc
        admission_payload = _admission_payload(admission)
        event_payload = _event_payload(event)
        target = _admission_from_payload(admission_payload)
        rebuilt_event = _event_from_payload(event_payload)
        approval_payload = None if approval_binding is None else _approval_payload(approval_binding)
        rebuilt_approval = (
            None if approval_payload is None else _approval_from_payload(approval_payload)
        )
        input_value = self._transaction_input(
            operation="TRANSITION",
            transaction_id=transaction_id,
            expected_state=expected.value,
            recorded_at=recorded,
            assignment=None,
            admission=admission_payload,
            event=event_payload,
            approval=approval_payload,
        )
        input_hash = _payload_and_hash(input_value)[1]
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_schema(connection)
            replay = self._replay_result(connection, transaction_id, input_hash)
            if replay is not None:
                connection.rollback()
                return replay
            lifecycle = self._load_from_connection(connection, target.admission_id)
            current = lifecycle.current_admission
            if current.state is not expected:
                raise StaleAdmissionState(
                    f"expected {expected.value}, found {current.state.value}."
                )
            if _stable_admission_payload(current) != _stable_admission_payload(target):
                raise ContractValidationError(
                    "transition cannot change admission identity, scope, rights, interval, or provenance."
                )
            failure_code, revocation_reason = _transition_failure_arguments(
                rebuilt_event, target.state
            )
            formal_approval = (
                target.approval_binding
                if target.state is AdmissionState.FORMALLY_ADMITTED
                else None
            )
            validate_admission_transition(
                current.state,
                target.state,
                approval_binding=formal_approval,
                failure_code=failure_code,
                revocation_reason=revocation_reason,
            )
            self._validate_transition_event(
                lifecycle,
                current,
                target,
                rebuilt_event,
                transaction_id,
                recorded,
                rebuilt_approval,
            )
            sequence_no = len(lifecycle.events) + 1
            if rebuilt_approval is not None:
                self._insert_approval(
                    connection,
                    rebuilt_approval,
                    admission_id=target.admission_id,
                    sequence_no=sequence_no,
                    transaction_id=transaction_id,
                    recorded_at=recorded,
                )
                self._fault("after_approval_write")
            previous = lifecycle.event_records[-1]
            self._insert_event(
                connection,
                assignment=lifecycle.assignment,
                event=rebuilt_event,
                sequence_no=sequence_no,
                previous_event_id=previous.event.event_id,
                previous_chain_hash=previous.chain_sha256,
                transaction_id=transaction_id,
                recorded_at=recorded,
            )
            self._fault("after_event_write")
            self._insert_snapshot(
                connection,
                target,
                sequence_no=sequence_no,
                transaction_id=transaction_id,
                recorded_at=recorded,
            )
            self._fault("after_current_state_write")
            writes = (
                _TRANSITION_WITH_APPROVAL_WRITES
                if rebuilt_approval is not None
                else _TRANSITION_WRITES
            )
            self._insert_journal(
                connection,
                operation="TRANSITION",
                transaction_id=transaction_id,
                admission_id=target.admission_id,
                sequence_no=sequence_no,
                expected_state=expected.value,
                target_state=target.state.value,
                input_sha256=input_hash,
                ordered_writes=writes,
                recorded_at=recorded,
            )
            self._fault("after_journal_write")
            connection.commit()
        except (
            AdmissionPersistenceError,
            ContractValidationError,
        ):
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise AdmissionPersistenceError(
                "admission transition transaction failed; no lifecycle state was committed."
            ) from exc
        finally:
            connection.close()
        return self.load(target.admission_id)

    def load(self, admission_id: str) -> AdmissionLifecycleRecord:
        admission_id = _identity(admission_id, "admission_id")
        connection = self._connect(read_only=True)
        try:
            self._require_schema(connection)
            return self._load_from_connection(connection, admission_id)
        except (AdmissionPersistenceError, ContractValidationError):
            raise
        except sqlite3.Error as exc:
            raise PersistenceIntegrityError("admission repository could not be read.") from exc
        finally:
            connection.close()

    def _load_from_connection(
        self, connection: sqlite3.Connection, admission_id: str
    ) -> AdmissionLifecycleRecord:
        assignment_row = connection.execute(
            "SELECT * FROM direct_use_assignment_ledger WHERE admission_id = ?",
            (admission_id,),
        ).fetchone()
        if assignment_row is None:
            raise AdmissionNotFound(f"admission {admission_id!r} does not exist.")
        self._require_version(assignment_row, "assignment")
        assignment_payload = _parse_payload(
            assignment_row["payload_json"], assignment_row["payload_sha256"], "assignment"
        )
        assignment = _assignment_from_payload(assignment_payload)
        self._require_row_values(
            assignment_row,
            {
                "assignment_id": assignment.assignment_id,
                "admission_id": assignment.admission_id,
                "admission_version": assignment.admission_version,
                "component_id": assignment.component_id,
                "reference_id": assignment.reference_id,
                "reference_version": assignment.reference_version,
                "created_at": _timestamp_text(assignment.created_at, "created_at"),
            },
            "assignment",
        )
        snapshot_rows = connection.execute(
            "SELECT * FROM direct_use_admission_snapshots WHERE admission_id = ? ORDER BY sequence_no",
            (admission_id,),
        ).fetchall()
        event_rows = connection.execute(
            "SELECT * FROM direct_use_lifecycle_events WHERE admission_id = ? ORDER BY sequence_no",
            (admission_id,),
        ).fetchall()
        journal_rows = connection.execute(
            "SELECT * FROM direct_use_transaction_journal WHERE admission_id = ? ORDER BY sequence_no",
            (admission_id,),
        ).fetchall()
        approval_rows = connection.execute(
            "SELECT * FROM direct_use_approval_bindings WHERE admission_id = ? ORDER BY sequence_no",
            (admission_id,),
        ).fetchall()
        if not snapshot_rows or not (
            len(snapshot_rows) == len(event_rows) == len(journal_rows)
        ):
            raise PersistenceIntegrityError("admission transaction units are incomplete.")
        expected_sequence = list(range(1, len(snapshot_rows) + 1))
        for rows, label in (
            (snapshot_rows, "admission snapshot"),
            (event_rows, "lifecycle event"),
            (journal_rows, "transaction journal"),
        ):
            if [row["sequence_no"] for row in rows] != expected_sequence:
                raise PersistenceIntegrityError(f"{label} ordering is inconsistent.")
        approvals_by_sequence: dict[int, ApprovalBinding] = {}
        approval_rows_by_sequence: dict[int, sqlite3.Row] = {}
        approvals: list[ApprovalBinding] = []
        for row in approval_rows:
            self._require_version(row, "approval binding")
            value = _approval_from_payload(
                _parse_payload(row["payload_json"], row["payload_sha256"], "approval binding")
            )
            self._require_row_values(
                row,
                {
                    "approval_binding_id": value.decision_id,
                    "admission_id": value.admission_id,
                    "reference_id": value.reference_id,
                    "reference_version": value.reference_version,
                },
                "approval binding",
            )
            if row["sequence_no"] in approvals_by_sequence:
                raise PersistenceIntegrityError("approval binding sequence is duplicated.")
            approvals_by_sequence[row["sequence_no"]] = value
            approval_rows_by_sequence[row["sequence_no"]] = row
            approvals.append(value)
        history: list[ComponentAdmission] = []
        events: list[ComponentLifecycleEvent] = []
        event_records: list[LifecycleEventRecord] = []
        transaction_ids: list[str] = []
        previous_event_id: str | None = None
        previous_chain_hash: str | None = None
        previous_recorded_at: datetime | None = None
        previous_occurred_at: datetime | None = None
        for sequence_no, (snapshot_row, event_row, journal_row) in enumerate(
            zip(snapshot_rows, event_rows, journal_rows), start=1
        ):
            for row, label in (
                (snapshot_row, "admission snapshot"),
                (event_row, "lifecycle event"),
                (journal_row, "transaction journal"),
            ):
                self._require_version(row, label)
            admission_payload = _parse_payload(
                snapshot_row["payload_json"], snapshot_row["payload_sha256"], "admission snapshot"
            )
            event_payload = _parse_payload(
                event_row["payload_json"], event_row["payload_sha256"], "lifecycle event"
            )
            admission = _admission_from_payload(admission_payload)
            event = _event_from_payload(event_payload)
            recorded = _timestamp(journal_row["recorded_at"], "recorded_at")
            if (
                snapshot_row["recorded_at"] != journal_row["recorded_at"]
                or event_row["recorded_at"] != journal_row["recorded_at"]
            ):
                raise PersistenceIntegrityError("transaction recorded_at values disagree.")
            self._require_row_values(
                snapshot_row,
                {
                    "admission_id": admission.admission_id,
                    "sequence_no": sequence_no,
                    "state": admission.state.value,
                    "assignment_id": admission.assignment_id,
                    "reference_id": admission.reference_id,
                    "reference_version": admission.reference_version,
                    "transaction_id": journal_row["transaction_id"],
                },
                "admission snapshot",
            )
            self._require_row_values(
                event_row,
                {
                    "event_id": event.event_id,
                    "admission_id": admission.admission_id,
                    "component_id": assignment.component_id,
                    "sequence_no": sequence_no,
                    "prior_state": event.prior_state,
                    "next_state": event.next_state,
                    "previous_event_id": previous_event_id,
                    "transaction_id": journal_row["transaction_id"],
                },
                "lifecycle event",
            )
            expected_chain = _sha256_text(
                f"{previous_chain_hash or ''}:{event_row['payload_sha256']}"
            )
            if event_row["chain_sha256"] != expected_chain:
                raise PersistenceIntegrityError("lifecycle event chain hash does not match.")
            if event.subject_kind != SUBJECT_KIND or event.subject_id != admission_id:
                raise PersistenceIntegrityError("lifecycle event subject does not match admission.")
            if event.correlation_id != journal_row["transaction_id"]:
                raise PersistenceIntegrityError("event correlation does not match transaction.")
            if event.occurred_at > recorded:
                raise PersistenceIntegrityError("event occurred_at is later than recorded_at.")
            if previous_recorded_at is not None and recorded < previous_recorded_at:
                raise PersistenceIntegrityError("recorded_at ordering is inconsistent.")
            if previous_occurred_at is not None and event.occurred_at < previous_occurred_at:
                raise PersistenceIntegrityError("event occurred_at ordering is inconsistent.")
            approval = approvals_by_sequence.get(sequence_no)
            if approval is not None:
                approval_row = approval_rows_by_sequence[sequence_no]
                self._require_row_values(
                    approval_row,
                    {
                        "sequence_no": sequence_no,
                        "transaction_id": journal_row["transaction_id"],
                        "recorded_at": journal_row["recorded_at"],
                    },
                    "approval binding",
                )
                if (
                    event.approval_binding_id != approval.decision_id
                    or event.authority_id != approval.authority_id
                    or _timestamp(approval.decision_timestamp, "decision_timestamp") > recorded
                ):
                    raise PersistenceIntegrityError("approval binding does not match lifecycle event.")
            self._require_row_values(
                journal_row,
                {
                    "admission_id": admission.admission_id,
                    "sequence_no": sequence_no,
                    "target_state": admission.state.value,
                    "recorded_at": _timestamp_text(recorded, "recorded_at"),
                },
                "transaction journal",
            )
            _identity(journal_row["transaction_id"], "transaction_id")
            if _SHA256_RE.fullmatch(journal_row["input_sha256"]) is None:
                raise PersistenceIntegrityError("transaction input hash is malformed.")
            if sequence_no == 1 and assignment_row["created_transaction_id"] != journal_row["transaction_id"]:
                raise PersistenceIntegrityError("assignment transaction identity does not match journal.")
            self._validate_loaded_transition(
                assignment,
                history,
                admission,
                event,
                approval,
                tuple(
                    approvals_by_sequence[item]
                    for item in sorted(approvals_by_sequence)
                    if item < sequence_no
                ),
                journal_row,
                recorded,
            )
            operation = journal_row["operation"]
            expected_state = journal_row["expected_state"]
            ordered_writes = self._journal_writes(journal_row)
            transaction_input = self._transaction_input(
                operation=operation,
                transaction_id=journal_row["transaction_id"],
                expected_state=expected_state,
                recorded_at=recorded,
                assignment=assignment_payload if sequence_no == 1 else None,
                admission=admission_payload,
                event=event_payload,
                approval=None if approval is None else _approval_payload(approval),
            )
            expected_input_hash = _payload_and_hash(transaction_input)[1]
            if journal_row["input_sha256"] != expected_input_hash:
                raise PersistenceIntegrityError("transaction input hash does not match.")
            required_writes = (
                _CREATE_WRITES
                if sequence_no == 1
                else _TRANSITION_WITH_APPROVAL_WRITES
                if approval is not None
                else _TRANSITION_WRITES
            )
            if ordered_writes != required_writes or journal_row["status"] != TRANSACTION_STATUS:
                raise PersistenceIntegrityError("transaction journal is incomplete or inconsistent.")
            history.append(admission)
            events.append(event)
            event_records.append(
                LifecycleEventRecord(
                    event=event,
                    sequence_no=sequence_no,
                    previous_event_id=previous_event_id,
                    payload_sha256=event_row["payload_sha256"],
                    chain_sha256=event_row["chain_sha256"],
                    recorded_at=recorded,
                )
            )
            transaction_ids.append(journal_row["transaction_id"])
            previous_event_id = event.event_id
            previous_chain_hash = event_row["chain_sha256"]
            previous_recorded_at = recorded
            previous_occurred_at = event.occurred_at
        if set(approvals_by_sequence) - set(expected_sequence):
            raise PersistenceIntegrityError("approval binding references an unknown transition.")
        return AdmissionLifecycleRecord(
            assignment=assignment,
            current_admission=history[-1],
            admission_history=tuple(history),
            events=tuple(events),
            event_records=tuple(event_records),
            approval_bindings=tuple(approvals),
            transaction_ids=tuple(transaction_ids),
        )

    def _validate_loaded_transition(
        self,
        assignment: AssignmentLedgerEntry,
        history: list[ComponentAdmission],
        admission: ComponentAdmission,
        event: ComponentLifecycleEvent,
        approval: ApprovalBinding | None,
        prior_approvals: tuple[ApprovalBinding, ...],
        journal_row: sqlite3.Row,
        recorded_at: datetime,
    ) -> None:
        _validate_assignment_binding(assignment, admission)
        if not history:
            _validate_initial_event(
                assignment,
                admission,
                event,
                journal_row["transaction_id"],
                recorded_at,
            )
            if journal_row["operation"] != "CREATE" or journal_row["expected_state"] is not None:
                raise PersistenceIntegrityError("initial transaction journal is inconsistent.")
            return
        current = history[-1]
        if journal_row["operation"] != "TRANSITION":
            raise PersistenceIntegrityError("transition journal operation is inconsistent.")
        if journal_row["expected_state"] != current.state.value:
            raise PersistenceIntegrityError("transition expected_state is inconsistent.")
        if _stable_admission_payload(current) != _stable_admission_payload(admission):
            raise PersistenceIntegrityError("admission immutable fields changed across transition.")
        failure_code, revocation_reason = _transition_failure_arguments(event, admission.state)
        try:
            validate_admission_transition(
                current.state,
                admission.state,
                approval_binding=admission.approval_binding
                if admission.state is AdmissionState.FORMALLY_ADMITTED
                else None,
                failure_code=failure_code,
                revocation_reason=revocation_reason,
            )
            lifecycle = AdmissionLifecycleRecord(
                assignment,
                current,
                tuple(history),
                tuple(),
                tuple(),
                prior_approvals,
                tuple(),
            )
            self._validate_transition_event(
                lifecycle,
                current,
                admission,
                event,
                journal_row["transaction_id"],
                recorded_at,
                approval,
                loaded=True,
            )
        except ContractValidationError as exc:
            raise PersistenceIntegrityError("persisted admission transition is invalid.") from exc

    def _validate_transition_event(
        self,
        lifecycle: AdmissionLifecycleRecord,
        current: ComponentAdmission,
        target: ComponentAdmission,
        event: ComponentLifecycleEvent,
        transaction_id: str,
        recorded_at: datetime,
        approval: ApprovalBinding | None,
        *,
        loaded: bool = False,
    ) -> None:
        if event.subject_kind != SUBJECT_KIND or event.subject_id != target.admission_id:
            raise ContractValidationError("lifecycle event subject does not match admission.")
        if event.prior_state != current.state.value or event.next_state != target.state.value:
            raise ContractValidationError("lifecycle event states do not match transition.")
        if event.event_type != _EVENT_TYPE_BY_STATE[target.state]:
            raise ContractValidationError("lifecycle event type does not match transition.")
        if event.correlation_id != transaction_id:
            raise ContractValidationError("event correlation_id must equal transaction_id.")
        if event.occurred_at > recorded_at:
            raise ContractValidationError("event occurred_at cannot be later than recorded_at.")
        if lifecycle.event_records:
            previous = lifecycle.event_records[-1]
            if event.occurred_at < previous.event.occurred_at or recorded_at < previous.recorded_at:
                raise ContractValidationError("lifecycle event timestamps are out of order.")
        requires_approval = target.state in _APPROVAL_REQUIRED_STATES
        if requires_approval and approval is None:
            raise ContractValidationError(f"{target.state.value} requires approval binding.")
        if not requires_approval and approval is not None:
            raise ContractValidationError("transition does not accept a new approval binding.")
        if approval is not None:
            if (
                approval.admission_id,
                approval.reference_id,
                approval.reference_version,
            ) != (target.admission_id, target.reference_id, target.reference_version):
                raise ContractValidationError("approval binding identity does not match admission.")
            if event.approval_binding_id != approval.decision_id:
                raise ContractValidationError("event approval_binding_id does not match approval.")
            if event.authority_id != approval.authority_id:
                raise ContractValidationError("event authority does not match approval.")
            if _timestamp(approval.decision_timestamp, "decision_timestamp") > recorded_at:
                raise ContractValidationError("approval decision cannot be later than recorded_at.")
            if target.state is AdmissionState.FORMALLY_ADMITTED and (
                _approval_payload(target.approval_binding) != _approval_payload(approval)
            ):
                raise ContractValidationError("formal admission approval binding does not match.")
        elif target.state is AdmissionState.ASSIGNED_NOT_ADMITTED:
            prior_approval = (
                lifecycle.approval_bindings[-1] if lifecycle.approval_bindings else None
            )
            if prior_approval is None or event.approval_binding_id != prior_approval.decision_id:
                raise ContractValidationError(
                    "assignment commit must reference its persisted assignment approval."
                )
            if event.authority_id != prior_approval.authority_id:
                raise ContractValidationError("assignment event authority does not match approval.")
        elif event.approval_binding_id is not None:
            raise ContractValidationError("event cannot claim an unpersisted approval binding.")
        if target.state is AdmissionState.FORMALLY_ADMITTED:
            self._validate_formal_rights(target, event.occurred_at)
        if loaded and target.state is AdmissionState.ASSIGNED_NOT_ADMITTED:
            # A load-time caller supplies approval history separately below.
            return

    def _validate_formal_rights(
        self, admission: ComponentAdmission, evaluation_time: datetime
    ) -> None:
        for dimension, decision_field in (
            ("runtime_resolution", "rights_for_runtime_resolution"),
            ("local_materialization", "rights_for_local_materialization"),
        ):
            if getattr(admission.rights_snapshot, decision_field) is not RightsDecision.ELIGIBLE:
                raise ContractValidationError(
                    "formal admission requires runtime-resolution and local-materialization rights."
                )
            evidence = admission.rights_snapshot.evidence.get(dimension)
            if not isinstance(evidence, RightsEvidence):
                raise ContractValidationError("formal admission rights evidence is missing.")
            if evidence.evaluated_at > evaluation_time:
                raise ContractValidationError("rights evidence postdates the admission event.")
            if evidence.valid_until is not None and evidence.valid_until <= evaluation_time:
                raise ContractValidationError("rights evidence was expired at admission time.")

    def _insert_approval(
        self,
        connection: sqlite3.Connection,
        approval: ApprovalBinding,
        *,
        admission_id: str,
        sequence_no: int,
        transaction_id: str,
        recorded_at: datetime,
    ) -> None:
        payload, digest = _payload_and_hash(_approval_payload(approval))
        try:
            connection.execute(
                """INSERT INTO direct_use_approval_bindings (
                    approval_binding_id, admission_id, reference_id, reference_version,
                    sequence_no, schema_version, transaction_id, recorded_at,
                    payload_json, payload_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    approval.decision_id,
                    admission_id,
                    approval.reference_id,
                    approval.reference_version,
                    sequence_no,
                    SCHEMA_VERSION,
                    transaction_id,
                    _timestamp_text(recorded_at, "recorded_at"),
                    payload,
                    digest,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicatePersistenceIdentity("approval binding identity already exists.") from exc

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        *,
        assignment: AssignmentLedgerEntry,
        event: ComponentLifecycleEvent,
        sequence_no: int,
        previous_event_id: str | None,
        previous_chain_hash: str | None,
        transaction_id: str,
        recorded_at: datetime,
    ) -> None:
        payload, digest = _payload_and_hash(_event_payload(event))
        chain = _sha256_text(f"{previous_chain_hash or ''}:{digest}")
        try:
            connection.execute(
                """INSERT INTO direct_use_lifecycle_events (
                    event_id, admission_id, component_id, sequence_no, prior_state,
                    next_state, previous_event_id, schema_version, transaction_id,
                    recorded_at, payload_json, payload_sha256, chain_sha256
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event.event_id,
                    assignment.admission_id,
                    assignment.component_id,
                    sequence_no,
                    event.prior_state,
                    event.next_state,
                    previous_event_id,
                    SCHEMA_VERSION,
                    transaction_id,
                    _timestamp_text(recorded_at, "recorded_at"),
                    payload,
                    digest,
                    chain,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicatePersistenceIdentity("event identity or ordering already exists.") from exc

    def _insert_snapshot(
        self,
        connection: sqlite3.Connection,
        admission: ComponentAdmission,
        *,
        sequence_no: int,
        transaction_id: str,
        recorded_at: datetime,
    ) -> None:
        payload, digest = _payload_and_hash(_admission_payload(admission))
        connection.execute(
            """INSERT INTO direct_use_admission_snapshots (
                admission_id, sequence_no, state, assignment_id, reference_id,
                reference_version, schema_version, transaction_id, recorded_at,
                payload_json, payload_sha256
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                admission.admission_id,
                sequence_no,
                admission.state.value,
                admission.assignment_id,
                admission.reference_id,
                admission.reference_version,
                SCHEMA_VERSION,
                transaction_id,
                _timestamp_text(recorded_at, "recorded_at"),
                payload,
                digest,
            ),
        )

    def _insert_journal(
        self,
        connection: sqlite3.Connection,
        *,
        operation: str,
        transaction_id: str,
        admission_id: str,
        sequence_no: int,
        expected_state: str | None,
        target_state: str,
        input_sha256: str,
        ordered_writes: Sequence[str],
        recorded_at: datetime,
    ) -> None:
        connection.execute(
            """INSERT INTO direct_use_transaction_journal (
                transaction_id, admission_id, sequence_no, operation, expected_state,
                target_state, input_sha256, ordered_writes_json, status,
                recorded_at, schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                transaction_id,
                admission_id,
                sequence_no,
                operation,
                expected_state,
                target_state,
                input_sha256,
                _canonical_json(list(ordered_writes)),
                TRANSACTION_STATUS,
                _timestamp_text(recorded_at, "recorded_at"),
                SCHEMA_VERSION,
            ),
        )

    def _transaction_input(
        self,
        *,
        operation: str,
        transaction_id: str,
        expected_state: str | None,
        recorded_at: datetime,
        assignment: dict[str, Any] | None,
        admission: dict[str, Any],
        event: dict[str, Any],
        approval: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "operation": operation,
            "transaction_id": transaction_id,
            "expected_state": expected_state,
            "recorded_at": _timestamp_text(recorded_at, "recorded_at"),
            "assignment": assignment,
            "admission": admission,
            "event": event,
            "approval_binding": approval,
        }

    def _replay_result(
        self, connection: sqlite3.Connection, transaction_id: str, input_hash: str
    ) -> AdmissionLifecycleRecord | None:
        row = connection.execute(
            "SELECT admission_id, input_sha256, status FROM direct_use_transaction_journal WHERE transaction_id = ?",
            (transaction_id,),
        ).fetchone()
        if row is None:
            return None
        if row["input_sha256"] != input_hash or row["status"] != TRANSACTION_STATUS:
            raise TransactionReplayConflict(
                "transaction_id was already used for different or incomplete input."
            )
        return self._load_from_connection(connection, row["admission_id"])

    def _fault(self, stage: str) -> None:
        if self.fault_hook is not None:
            self.fault_hook(stage)

    def _require_version(self, row: sqlite3.Row, label: str) -> None:
        if row["schema_version"] != SCHEMA_VERSION:
            raise PersistenceIntegrityError(f"{label} schema version is unsupported.")

    def _require_row_values(
        self, row: sqlite3.Row, expected: Mapping[str, Any], label: str
    ) -> None:
        for column, value in expected.items():
            if row[column] != value:
                raise PersistenceIntegrityError(
                    f"{label} column {column} does not match its payload."
                )

    def _journal_writes(self, row: sqlite3.Row) -> tuple[str, ...]:
        try:
            value = json.loads(row["ordered_writes_json"])
        except (TypeError, ValueError) as exc:
            raise PersistenceIntegrityError("transaction ordered writes are malformed.") from exc
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise PersistenceIntegrityError("transaction ordered writes are malformed.")
        if _canonical_json(value) != row["ordered_writes_json"]:
            raise PersistenceIntegrityError("transaction ordered writes are not canonical.")
        return tuple(value)

    def _require_schema(self, connection: sqlite3.Connection) -> None:
        try:
            row = connection.execute(
                "SELECT schema_version FROM component_direct_use_schema WHERE schema_name = ?",
                (SCHEMA_NAME,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise PersistenceIntegrityError("admission repository schema is missing.") from exc
        if row is None or row["schema_version"] != SCHEMA_VERSION:
            raise PersistenceIntegrityError("admission repository schema version is unsupported.")
        for table, expected_columns in _EXPECTED_COLUMNS.items():
            actual = tuple(
                item["name"] for item in connection.execute(f"PRAGMA table_info({table})")
            )
            if actual != expected_columns:
                raise PersistenceIntegrityError(f"{table} schema does not match version {SCHEMA_VERSION}.")


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS component_direct_use_schema (
    schema_name TEXT PRIMARY KEY,
    schema_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS direct_use_assignment_ledger (
    assignment_id TEXT PRIMARY KEY,
    admission_id TEXT NOT NULL UNIQUE,
    admission_version INTEGER NOT NULL,
    component_id TEXT NOT NULL,
    reference_id TEXT NOT NULL,
    reference_version INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    created_transaction_id TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS direct_use_approval_bindings (
    approval_binding_id TEXT PRIMARY KEY,
    admission_id TEXT NOT NULL,
    reference_id TEXT NOT NULL,
    reference_version INTEGER NOT NULL,
    sequence_no INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    transaction_id TEXT NOT NULL UNIQUE,
    recorded_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    UNIQUE (admission_id, sequence_no),
    FOREIGN KEY (admission_id) REFERENCES direct_use_assignment_ledger(admission_id)
);
CREATE TABLE IF NOT EXISTS direct_use_admission_snapshots (
    admission_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    state TEXT NOT NULL,
    assignment_id TEXT NOT NULL,
    reference_id TEXT NOT NULL,
    reference_version INTEGER NOT NULL,
    schema_version TEXT NOT NULL,
    transaction_id TEXT NOT NULL UNIQUE,
    recorded_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    PRIMARY KEY (admission_id, sequence_no),
    FOREIGN KEY (assignment_id) REFERENCES direct_use_assignment_ledger(assignment_id)
);
CREATE TABLE IF NOT EXISTS direct_use_lifecycle_events (
    event_id TEXT PRIMARY KEY,
    admission_id TEXT NOT NULL,
    component_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    prior_state TEXT,
    next_state TEXT NOT NULL,
    previous_event_id TEXT,
    schema_version TEXT NOT NULL,
    transaction_id TEXT NOT NULL UNIQUE,
    recorded_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    chain_sha256 TEXT NOT NULL,
    UNIQUE (admission_id, sequence_no),
    FOREIGN KEY (admission_id) REFERENCES direct_use_assignment_ledger(admission_id),
    FOREIGN KEY (previous_event_id) REFERENCES direct_use_lifecycle_events(event_id)
);
CREATE TABLE IF NOT EXISTS direct_use_transaction_journal (
    transaction_id TEXT PRIMARY KEY,
    admission_id TEXT NOT NULL,
    sequence_no INTEGER NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('CREATE', 'TRANSITION')),
    expected_state TEXT,
    target_state TEXT NOT NULL,
    input_sha256 TEXT NOT NULL,
    ordered_writes_json TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status = 'COMMITTED'),
    recorded_at TEXT NOT NULL,
    schema_version TEXT NOT NULL,
    UNIQUE (admission_id, sequence_no),
    FOREIGN KEY (admission_id, sequence_no)
        REFERENCES direct_use_admission_snapshots(admission_id, sequence_no)
);
CREATE INDEX IF NOT EXISTS idx_direct_use_events_admission
    ON direct_use_lifecycle_events(admission_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_direct_use_approvals_admission
    ON direct_use_approval_bindings(admission_id, sequence_no);
"""


_EXPECTED_COLUMNS = {
    "component_direct_use_schema": ("schema_name", "schema_version"),
    "direct_use_assignment_ledger": (
        "assignment_id", "admission_id", "admission_version", "component_id",
        "reference_id", "reference_version", "schema_version",
        "created_transaction_id", "created_at", "payload_json", "payload_sha256",
    ),
    "direct_use_approval_bindings": (
        "approval_binding_id", "admission_id", "reference_id", "reference_version",
        "sequence_no", "schema_version", "transaction_id", "recorded_at",
        "payload_json", "payload_sha256",
    ),
    "direct_use_admission_snapshots": (
        "admission_id", "sequence_no", "state", "assignment_id", "reference_id",
        "reference_version", "schema_version", "transaction_id", "recorded_at",
        "payload_json", "payload_sha256",
    ),
    "direct_use_lifecycle_events": (
        "event_id", "admission_id", "component_id", "sequence_no", "prior_state",
        "next_state", "previous_event_id", "schema_version", "transaction_id",
        "recorded_at", "payload_json", "payload_sha256", "chain_sha256",
    ),
    "direct_use_transaction_journal": (
        "transaction_id", "admission_id", "sequence_no", "operation",
        "expected_state", "target_state", "input_sha256", "ordered_writes_json",
        "status", "recorded_at", "schema_version",
    ),
}


__all__ = [
    "AdmissionLifecycleRecord",
    "AdmissionNotFound",
    "AdmissionPersistenceError",
    "AssignmentLedgerEntry",
    "ComponentAdmissionRepository",
    "DuplicatePersistenceIdentity",
    "LifecycleEventRecord",
    "PersistenceIntegrityError",
    "SCHEMA_NAME",
    "SCHEMA_VERSION",
    "StaleAdmissionState",
    "TransactionReplayConflict",
]
