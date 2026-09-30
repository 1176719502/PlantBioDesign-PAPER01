from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import services.component_direct_use_contracts as direct_use_contracts
from services.component_direct_use_contracts import (
    AdmissionState,
    ApprovalBinding,
    ComponentAdmission,
    ComponentLifecycleEvent,
    ContractValidationError,
    RightsDecision,
    RightsEvidence,
    RightsState,
    is_admission_current,
)
from services.component_direct_use_persistence import (
    AdmissionPersistenceError,
    AssignmentLedgerEntry,
    ComponentAdmissionRepository,
    DuplicatePersistenceIdentity,
    PersistenceIntegrityError,
    StaleAdmissionState,
    TransactionReplayConflict,
)
from services.plant_component_workflow_registry import catalog_library_view_records


BASE = datetime(2030, 1, 1, 12, tzinfo=timezone.utc)
EXPIRES = datetime(2035, 1, 1, tzinfo=timezone.utc)


def _clock_at(wall_time: datetime):
    real_datetime = datetime

    class _ClockMeta(type):
        def __instancecheck__(cls, value):
            return isinstance(value, real_datetime)

    class _Clock(real_datetime, metaclass=_ClockMeta):
        @classmethod
        def now(cls, tz=None):
            return wall_time if tz is None else wall_time.astimezone(tz)

    return _Clock


def _evidence(
    dimension: str,
    *,
    admission_id: str = "admission-1",
    valid_until: datetime | None = EXPIRES,
) -> RightsEvidence:
    return RightsEvidence(
        evidence_id=f"evidence-{dimension}",
        rights_dimension=dimension,
        operation=dimension,
        workflow_scope=("single_gene",),
        reference_id="reference-1",
        reference_version=1,
        admission_id=admission_id,
        admission_version=1,
        authority_id="authority-rights",
        source_id="source-review-1",
        policy_version="rights-policy-1",
        decision_id=f"rights-decision-{dimension}",
        decision_hash="a" * 64,
        evaluated_at=BASE - timedelta(days=1),
        valid_until=valid_until,
        provenance={"record": "synthetic-review-fixture"},
    )


def _rights(
    *,
    admission_id: str = "admission-1",
    valid_until: datetime | None = EXPIRES,
) -> RightsState:
    return RightsState(
        rights_for_runtime_resolution=RightsDecision.ELIGIBLE,
        rights_for_local_materialization=RightsDecision.ELIGIBLE,
        evidence={
            "runtime_resolution": _evidence(
                "runtime_resolution",
                admission_id=admission_id,
                valid_until=valid_until,
            ),
            "local_materialization": _evidence(
                "local_materialization",
                admission_id=admission_id,
                valid_until=valid_until,
            ),
        },
    )


def _approval(
    decision_id: str,
    *,
    admission_id: str = "admission-1",
    reference_id: str = "reference-1",
    decision_at: datetime = BASE,
) -> ApprovalBinding:
    return ApprovalBinding(
        authority_id="authority-admission",
        policy_version="admission-policy-1",
        decision_id=decision_id,
        decision_hash="b" * 64,
        approver_id="approver-1",
        decision_timestamp=decision_at,
        signature=f"signature-{decision_id}",
        admission_id=admission_id,
        reference_id=reference_id,
        reference_version=1,
    )


def _assignment(
    *,
    assignment_id: str = "assignment-1",
    admission_id: str = "admission-1",
    component_id: str = "component-1",
) -> AssignmentLedgerEntry:
    return AssignmentLedgerEntry(
        assignment_id=assignment_id,
        admission_id=admission_id,
        admission_version=1,
        component_id=component_id,
        reference_id="reference-1",
        reference_version=1,
        assignee_id="component-identity-service",
        workflow_scope=("single_gene",),
        role_scope=("cds",),
        authority_id="authority-ledger",
        source="synthetic-test-fixture",
        provenance={"source_record": "fixture-1", "reviewed": True},
        created_at=BASE,
    )


def _admission(
    state: AdmissionState,
    *,
    admission_id: str = "admission-1",
    assignment_id: str = "assignment-1",
    approval: ApprovalBinding | None = None,
    valid_until: datetime | None = EXPIRES,
    rights_snapshot: RightsState | None = None,
) -> ComponentAdmission:
    return ComponentAdmission(
        admission_id=admission_id,
        admission_version=1,
        reference_id="reference-1",
        reference_version=1,
        assignment_id=assignment_id,
        state=state,
        workflow_scope=("single_gene",),
        role_scope=("cds",),
        rights_snapshot=rights_snapshot
        if rights_snapshot is not None
        else _rights(admission_id=admission_id, valid_until=valid_until),
        approval_binding=approval or {},
        effective_at=BASE,
        expires_at=datetime(2034, 1, 1, tzinfo=timezone.utc),
        audit_provenance={"review": "synthetic-only"},
    )


def _event(
    event_id: str,
    transaction_id: str,
    prior_state: AdmissionState | None,
    next_state: AdmissionState,
    *,
    minute: int,
    approval: ApprovalBinding | None = None,
    approval_id: str | None = None,
    reason_code: str | None = None,
    admission_id: str = "admission-1",
) -> ComponentLifecycleEvent:
    event_types = {
        AdmissionState.DRY_RUN_ASSIGNABLE: "ADMISSION_CREATED",
        AdmissionState.ASSIGNMENT_APPROVED: "ASSIGNMENT_APPROVED",
        AdmissionState.ASSIGNED_NOT_ADMITTED: "ASSIGNMENT_COMMITTED",
        AdmissionState.FORMALLY_ADMITTED: "FORMAL_ADMISSION",
        AdmissionState.ADMISSION_FAILED: "ADMISSION_FAILED",
        AdmissionState.REVOKED: "ADMISSION_REVOKED",
        AdmissionState.RETIRED: "ADMISSION_RETIRED",
    }
    return ComponentLifecycleEvent(
        event_id=event_id,
        event_version=1,
        event_type=event_types[next_state],
        subject_kind="component_admission",
        subject_id=admission_id,
        prior_state=None if prior_state is None else prior_state.value,
        next_state=next_state.value,
        authority_id=approval.authority_id if approval else "authority-ledger",
        approval_binding_id=approval.decision_id if approval else approval_id,
        reason_code=reason_code,
        evidence_refs=("synthetic-evidence-1",),
        occurred_at=BASE + timedelta(minutes=minute),
        actor_id="actor-1",
        correlation_id=transaction_id,
    )


def _new_repository(tmp_path: Path, **kwargs) -> ComponentAdmissionRepository:
    return ComponentAdmissionRepository(tmp_path / "admission.db", **kwargs)


def _create(repo: ComponentAdmissionRepository):
    return repo.create_admission(
        _assignment(),
        _admission(AdmissionState.DRY_RUN_ASSIGNABLE),
        _event(
            "event-create",
            "transaction-create",
            None,
            AdmissionState.DRY_RUN_ASSIGNABLE,
            minute=0,
        ),
        transaction_id="transaction-create",
        recorded_at=BASE + timedelta(seconds=1),
    )


def _approve_assignment(
    repo: ComponentAdmissionRepository, *, rights_snapshot: RightsState | None = None
):
    approval = _approval(
        "approval-assignment", decision_at=BASE + timedelta(seconds=30)
    )
    return repo.transition_admission(
        _admission(
            AdmissionState.ASSIGNMENT_APPROVED, rights_snapshot=rights_snapshot
        ),
        _event(
            "event-assignment-approved",
            "transaction-assignment-approved",
            AdmissionState.DRY_RUN_ASSIGNABLE,
            AdmissionState.ASSIGNMENT_APPROVED,
            minute=1,
            approval=approval,
        ),
        expected_state=AdmissionState.DRY_RUN_ASSIGNABLE,
        transaction_id="transaction-assignment-approved",
        recorded_at=BASE + timedelta(minutes=1, seconds=1),
        approval_binding=approval,
    )


def _commit_assignment(
    repo: ComponentAdmissionRepository, *, rights_snapshot: RightsState | None = None
):
    assignment_approval = _approval(
        "approval-assignment", decision_at=BASE + timedelta(seconds=30)
    )
    return repo.transition_admission(
        _admission(
            AdmissionState.ASSIGNED_NOT_ADMITTED, rights_snapshot=rights_snapshot
        ),
        _event(
            "event-assignment-committed",
            "transaction-assignment-committed",
            AdmissionState.ASSIGNMENT_APPROVED,
            AdmissionState.ASSIGNED_NOT_ADMITTED,
            minute=2,
            approval=assignment_approval,
        ),
        expected_state=AdmissionState.ASSIGNMENT_APPROVED,
        transaction_id="transaction-assignment-committed",
        recorded_at=BASE + timedelta(minutes=2, seconds=1),
    )


def _formally_admit(repo: ComponentAdmissionRepository):
    approval = _approval(
        "approval-formal", decision_at=BASE + timedelta(minutes=2, seconds=30)
    )
    return repo.transition_admission(
        _admission(AdmissionState.FORMALLY_ADMITTED, approval=approval),
        _event(
            "event-formally-admitted",
            "transaction-formally-admitted",
            AdmissionState.ASSIGNED_NOT_ADMITTED,
            AdmissionState.FORMALLY_ADMITTED,
            minute=3,
            approval=approval,
        ),
        expected_state=AdmissionState.ASSIGNED_NOT_ADMITTED,
        transaction_id="transaction-formally-admitted",
        recorded_at=BASE + timedelta(minutes=3, seconds=1),
        approval_binding=approval,
    )


def _through_formal(repo: ComponentAdmissionRepository):
    _create(repo)
    _approve_assignment(repo)
    _commit_assignment(repo)
    return _formally_admit(repo)


def _rewrite_payload(
    database_path: Path,
    table: str,
    where_column: str,
    where_value: str,
    mutate,
) -> None:
    connection = sqlite3.connect(database_path)
    try:
        row = connection.execute(
            f"SELECT payload_json FROM {table} WHERE {where_column} = ?", (where_value,)
        ).fetchone()
        payload = json.loads(row[0])
        mutate(payload)
        encoded = json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        connection.execute(
            f"UPDATE {table} SET payload_json = ?, payload_sha256 = ? WHERE {where_column} = ?",
            (encoded, digest, where_value),
        )
        connection.commit()
    finally:
        connection.close()


def test_full_lifecycle_persists_and_cold_repository_reload_is_equivalent(tmp_path):
    repository = _new_repository(tmp_path)
    written = _through_formal(repository)

    reloaded = ComponentAdmissionRepository(repository.database_path).load("admission-1")

    assert reloaded == written
    assert reloaded.assignment.component_id == "component-1"
    assert reloaded.current_admission.state is AdmissionState.FORMALLY_ADMITTED
    assert [item.state for item in reloaded.admission_history] == [
        AdmissionState.DRY_RUN_ASSIGNABLE,
        AdmissionState.ASSIGNMENT_APPROVED,
        AdmissionState.ASSIGNED_NOT_ADMITTED,
        AdmissionState.FORMALLY_ADMITTED,
    ]
    assert [item.event_id for item in reloaded.events] == [
        "event-create",
        "event-assignment-approved",
        "event-assignment-committed",
        "event-formally-admitted",
    ]
    assert [item.previous_event_id for item in reloaded.event_records] == [
        None,
        "event-create",
        "event-assignment-approved",
        "event-assignment-committed",
    ]
    assert [item.decision_id for item in reloaded.approval_bindings] == [
        "approval-assignment",
        "approval-formal",
    ]
    assert reloaded.transaction_ids == (
        "transaction-create",
        "transaction-assignment-approved",
        "transaction-assignment-committed",
        "transaction-formally-admitted",
    )
    assert is_admission_current(
        reloaded.current_admission, evaluation_time="2031-01-01T00:00:00Z"
    )
    assert not is_admission_current(
        reloaded.current_admission, evaluation_time="2034-01-01T00:00:00Z"
    )


def test_reload_of_historical_rights_does_not_depend_on_current_wall_clock(
    tmp_path, monkeypatch
):
    repository = _new_repository(tmp_path)
    _through_formal(repository)
    monkeypatch.setattr(
        direct_use_contracts,
        "datetime",
        _clock_at(datetime(2040, 1, 1, tzinfo=timezone.utc)),
    )

    reloaded = ComponentAdmissionRepository(repository.database_path).load("admission-1")

    rights = reloaded.current_admission.rights_snapshot
    assert rights.is_runtime_eligible(evaluation_time="2031-01-01T00:00:00Z")
    assert not rights.is_runtime_eligible(evaluation_time="2035-01-01T00:00:00Z")


def test_fresh_python_process_reconstructs_same_identity_state_and_event_order(tmp_path):
    repository = _new_repository(tmp_path)
    _through_formal(repository)
    script = (
        "import json,sys; "
        "from services.component_direct_use_persistence import ComponentAdmissionRepository; "
        "r=ComponentAdmissionRepository(sys.argv[1]).load('admission-1'); "
        "print(json.dumps({'admission_id':r.current_admission.admission_id,"
        "'state':r.current_admission.state.value,"
        "'approval_ids':[a.decision_id for a in r.approval_bindings],"
        "'event_ids':[e.event_id for e in r.events]}))"
    )

    result = subprocess.run(
        [sys.executable, "-c", script, str(repository.database_path)],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "admission_id": "admission-1",
        "state": "FORMALLY_ADMITTED",
        "approval_ids": ["approval-assignment", "approval-formal"],
        "event_ids": [
            "event-create",
            "event-assignment-approved",
            "event-assignment-committed",
            "event-formally-admitted",
        ],
    }


def test_duplicate_transition_retry_is_idempotent_and_input_conflict_is_rejected(tmp_path):
    repository = _new_repository(tmp_path)
    _create(repository)
    approval = _approval("approval-assignment", decision_at=BASE + timedelta(seconds=30))
    target = _admission(AdmissionState.ASSIGNMENT_APPROVED)
    event = _event(
        "event-assignment-approved",
        "transaction-assignment-approved",
        AdmissionState.DRY_RUN_ASSIGNABLE,
        AdmissionState.ASSIGNMENT_APPROVED,
        minute=1,
        approval=approval,
    )
    kwargs = dict(
        expected_state=AdmissionState.DRY_RUN_ASSIGNABLE,
        transaction_id="transaction-assignment-approved",
        recorded_at=BASE + timedelta(minutes=1, seconds=1),
        approval_binding=approval,
    )

    first = repository.transition_admission(target, event, **kwargs)
    replay = repository.transition_admission(target, event, **kwargs)

    assert replay == first
    conflicting = _event(
        "event-different",
        "transaction-assignment-approved",
        AdmissionState.DRY_RUN_ASSIGNABLE,
        AdmissionState.ASSIGNMENT_APPROVED,
        minute=1,
        approval=approval,
    )
    with pytest.raises(TransactionReplayConflict):
        repository.transition_admission(target, conflicting, **kwargs)


def test_skipped_and_stale_transitions_fail_closed(tmp_path):
    repository = _new_repository(tmp_path)
    _create(repository)
    formal = _approval("approval-formal")
    with pytest.raises(ContractValidationError, match="Illegal admission transition"):
        repository.transition_admission(
            _admission(AdmissionState.FORMALLY_ADMITTED, approval=formal),
            _event(
                "event-skip",
                "transaction-skip",
                AdmissionState.DRY_RUN_ASSIGNABLE,
                AdmissionState.FORMALLY_ADMITTED,
                minute=1,
                approval=formal,
            ),
            expected_state=AdmissionState.DRY_RUN_ASSIGNABLE,
            transaction_id="transaction-skip",
            recorded_at=BASE + timedelta(minutes=1, seconds=1),
            approval_binding=formal,
        )
    _approve_assignment(repository)
    with pytest.raises(StaleAdmissionState):
        repository.transition_admission(
            _admission(AdmissionState.ASSIGNED_NOT_ADMITTED),
            _event(
                "event-stale",
                "transaction-stale",
                AdmissionState.DRY_RUN_ASSIGNABLE,
                AdmissionState.ASSIGNED_NOT_ADMITTED,
                minute=2,
                approval_id="approval-assignment",
            ),
            expected_state=AdmissionState.DRY_RUN_ASSIGNABLE,
            transaction_id="transaction-stale",
            recorded_at=BASE + timedelta(minutes=2, seconds=1),
        )


def test_approval_and_rights_identity_mismatches_fail_before_write(tmp_path):
    repository = _new_repository(tmp_path)
    _create(repository)
    wrong = _approval(
        "approval-wrong", admission_id="other-admission", decision_at=BASE
    )
    with pytest.raises(ContractValidationError, match="identity"):
        repository.transition_admission(
            _admission(AdmissionState.ASSIGNMENT_APPROVED),
            _event(
                "event-wrong-approval",
                "transaction-wrong-approval",
                AdmissionState.DRY_RUN_ASSIGNABLE,
                AdmissionState.ASSIGNMENT_APPROVED,
                minute=1,
                approval=wrong,
            ),
            expected_state=AdmissionState.DRY_RUN_ASSIGNABLE,
            transaction_id="transaction-wrong-approval",
            recorded_at=BASE + timedelta(minutes=1, seconds=1),
            approval_binding=wrong,
        )
    forged = _admission(AdmissionState.ASSIGNMENT_APPROVED)
    object.__setattr__(
        forged.rights_snapshot.evidence["runtime_resolution"],
        "reference_id",
        "forged-reference",
    )
    with pytest.raises(ContractValidationError):
        repository.transition_admission(
            forged,
            _event(
                "event-forged-rights",
                "transaction-forged-rights",
                AdmissionState.DRY_RUN_ASSIGNABLE,
                AdmissionState.ASSIGNMENT_APPROVED,
                minute=1,
                approval=_approval("approval-forged"),
            ),
            expected_state=AdmissionState.DRY_RUN_ASSIGNABLE,
            transaction_id="transaction-forged-rights",
            recorded_at=BASE + timedelta(minutes=1, seconds=1),
            approval_binding=_approval("approval-forged"),
        )


@pytest.mark.parametrize(
    "target_state,reason_code",
    ((AdmissionState.REVOKED, "RIGHTS_WITHDRAWN"), (AdmissionState.RETIRED, None)),
)
def test_terminal_lifecycle_transition_is_persisted(tmp_path, target_state, reason_code):
    repository = _new_repository(tmp_path)
    _through_formal(repository)
    approval = _approval(
        f"approval-{target_state.value.lower()}",
        decision_at=BASE + timedelta(minutes=3, seconds=30),
    )

    record = repository.transition_admission(
        _admission(target_state),
        _event(
            f"event-{target_state.value.lower()}",
            f"transaction-{target_state.value.lower()}",
            AdmissionState.FORMALLY_ADMITTED,
            target_state,
            minute=4,
            approval=approval,
            reason_code=reason_code,
        ),
        expected_state=AdmissionState.FORMALLY_ADMITTED,
        transaction_id=f"transaction-{target_state.value.lower()}",
        recorded_at=BASE + timedelta(minutes=4, seconds=1),
        approval_binding=approval,
    )

    assert record.current_admission.state is target_state
    assert record.events[-1].next_state == target_state.value
    assert record.approval_bindings[-1] == approval


def test_admission_failure_transition_requires_supported_reason_and_persists(tmp_path):
    repository = _new_repository(tmp_path)
    _create(repository)
    record = repository.transition_admission(
        _admission(AdmissionState.ADMISSION_FAILED),
        _event(
            "event-failed",
            "transaction-failed",
            AdmissionState.DRY_RUN_ASSIGNABLE,
            AdmissionState.ADMISSION_FAILED,
            minute=1,
            reason_code="BOUNDARY_MISMATCH",
        ),
        expected_state=AdmissionState.DRY_RUN_ASSIGNABLE,
        transaction_id="transaction-failed",
        recorded_at=BASE + timedelta(minutes=1, seconds=1),
    )
    assert record.current_admission.state is AdmissionState.ADMISSION_FAILED
    assert record.events[-1].reason_code == "BOUNDARY_MISMATCH"


def test_duplicate_admission_assignment_event_and_approval_ids_fail_closed(tmp_path):
    repository = _new_repository(tmp_path)
    _create(repository)
    with pytest.raises(DuplicatePersistenceIdentity, match="admission_id"):
        repository.create_admission(
            _assignment(assignment_id="assignment-other"),
            _admission(
                AdmissionState.DRY_RUN_ASSIGNABLE, assignment_id="assignment-other"
            ),
            _event(
                "event-other",
                "transaction-other",
                None,
                AdmissionState.DRY_RUN_ASSIGNABLE,
                minute=0,
            ),
            transaction_id="transaction-other",
            recorded_at=BASE + timedelta(seconds=2),
        )
    with pytest.raises(DuplicatePersistenceIdentity, match="assignment_id"):
        repository.create_admission(
            _assignment(admission_id="admission-2"),
            _admission(
                AdmissionState.DRY_RUN_ASSIGNABLE,
                admission_id="admission-2",
            ),
            _event(
                "event-admission-2",
                "transaction-admission-2",
                None,
                AdmissionState.DRY_RUN_ASSIGNABLE,
                minute=0,
                admission_id="admission-2",
            ),
            transaction_id="transaction-admission-2",
            recorded_at=BASE + timedelta(seconds=2),
        )
    with pytest.raises(DuplicatePersistenceIdentity, match="event_id"):
        repository.create_admission(
            _assignment(
                assignment_id="assignment-3", admission_id="admission-3"
            ),
            _admission(
                AdmissionState.DRY_RUN_ASSIGNABLE,
                admission_id="admission-3",
                assignment_id="assignment-3",
            ),
            _event(
                "event-create",
                "transaction-admission-3",
                None,
                AdmissionState.DRY_RUN_ASSIGNABLE,
                minute=0,
                admission_id="admission-3",
            ),
            transaction_id="transaction-admission-3",
            recorded_at=BASE + timedelta(seconds=2),
        )


@pytest.mark.parametrize(
    "stage",
    (
        "after_assignment_write",
        "after_event_write",
        "after_current_state_write",
        "after_journal_write",
    ),
)
def test_create_failure_injection_rolls_back_every_durable_unit(tmp_path, stage):
    def fail(selected):
        if selected == stage:
            raise OSError("simulated storage failure")

    repository = _new_repository(tmp_path, fault_hook=fail)
    with pytest.raises(AdmissionPersistenceError, match="no lifecycle state"):
        _create(repository)

    connection = sqlite3.connect(repository.database_path)
    try:
        for table in (
            "direct_use_assignment_ledger",
            "direct_use_lifecycle_events",
            "direct_use_admission_snapshots",
            "direct_use_transaction_journal",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        connection.close()


@pytest.mark.parametrize(
    "stage",
    (
        "after_approval_write",
        "after_event_write",
        "after_current_state_write",
        "after_journal_write",
    ),
)
def test_transition_failure_injection_preserves_previous_state(tmp_path, stage):
    repository = _new_repository(tmp_path)
    _create(repository)

    def fail(selected):
        if selected == stage:
            raise OSError("simulated storage failure")

    failing = ComponentAdmissionRepository(repository.database_path, fault_hook=fail)
    with pytest.raises(AdmissionPersistenceError, match="no lifecycle state"):
        _approve_assignment(failing)

    reloaded = ComponentAdmissionRepository(repository.database_path).load("admission-1")
    assert reloaded.current_admission.state is AdmissionState.DRY_RUN_ASSIGNABLE
    assert len(reloaded.events) == 1
    assert not reloaded.approval_bindings


def test_optimistic_state_check_rejects_stale_repository_instance(tmp_path):
    first = _new_repository(tmp_path)
    second = ComponentAdmissionRepository(first.database_path)
    _create(first)
    _approve_assignment(first)

    with pytest.raises(StaleAdmissionState):
        second.transition_admission(
            _admission(AdmissionState.ASSIGNED_NOT_ADMITTED),
            _event(
                "event-concurrent-stale",
                "transaction-concurrent-stale",
                AdmissionState.DRY_RUN_ASSIGNABLE,
                AdmissionState.ASSIGNED_NOT_ADMITTED,
                minute=2,
                approval_id="approval-assignment",
            ),
            expected_state=AdmissionState.DRY_RUN_ASSIGNABLE,
            transaction_id="transaction-concurrent-stale",
            recorded_at=BASE + timedelta(minutes=2, seconds=1),
        )


@pytest.mark.parametrize(
    "table,column,value",
    (
        ("direct_use_assignment_ledger", "schema_version", "999"),
        ("direct_use_admission_snapshots", "schema_version", "999"),
        ("direct_use_lifecycle_events", "schema_version", "999"),
        ("direct_use_transaction_journal", "schema_version", "999"),
    ),
)
def test_unknown_record_schema_versions_fail_closed(tmp_path, table, column, value):
    repository = _new_repository(tmp_path)
    _create(repository)
    connection = sqlite3.connect(repository.database_path)
    try:
        connection.execute(f"UPDATE {table} SET {column} = ?", (value,))
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PersistenceIntegrityError, match="schema version"):
        ComponentAdmissionRepository(repository.database_path).load("admission-1")


def test_unknown_repository_schema_version_fails_closed(tmp_path):
    repository = _new_repository(tmp_path)
    _create(repository)
    connection = sqlite3.connect(repository.database_path)
    try:
        connection.execute(
            "UPDATE component_direct_use_schema SET schema_version = '999'"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PersistenceIntegrityError, match="schema version"):
        ComponentAdmissionRepository(repository.database_path).load("admission-1")


def test_malformed_payload_and_missing_required_field_fail_closed(tmp_path):
    malformed = _new_repository(tmp_path / "malformed")
    _create(malformed)
    connection = sqlite3.connect(malformed.database_path)
    try:
        raw = "{"
        connection.execute(
            "UPDATE direct_use_admission_snapshots SET payload_json = ?, payload_sha256 = ?",
            (raw, hashlib.sha256(raw.encode()).hexdigest()),
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PersistenceIntegrityError, match="valid JSON"):
        malformed.load("admission-1")

    missing = _new_repository(tmp_path / "missing")
    _create(missing)
    _rewrite_payload(
        missing.database_path,
        "direct_use_admission_snapshots",
        "admission_id",
        "admission-1",
        lambda payload: payload.pop("reference_id"),
    )
    with pytest.raises(PersistenceIntegrityError, match="fields do not match"):
        missing.load("admission-1")


def test_tampered_approval_rights_and_admission_identity_fail_closed(tmp_path):
    approval_repo = _new_repository(tmp_path / "approval")
    _create(approval_repo)
    _approve_assignment(approval_repo)
    _rewrite_payload(
        approval_repo.database_path,
        "direct_use_approval_bindings",
        "approval_binding_id",
        "approval-assignment",
        lambda payload: payload.__setitem__("decision_hash", "bad"),
    )
    with pytest.raises(PersistenceIntegrityError):
        approval_repo.load("admission-1")

    rights_repo = _new_repository(tmp_path / "rights")
    _create(rights_repo)
    _rewrite_payload(
        rights_repo.database_path,
        "direct_use_admission_snapshots",
        "admission_id",
        "admission-1",
        lambda payload: payload["rights_snapshot"]["evidence"][
            "runtime_resolution"
        ].__setitem__("reference_id", "forged-reference"),
    )
    with pytest.raises(PersistenceIntegrityError, match="rights evidence identity"):
        rights_repo.load("admission-1")

    identity_repo = _new_repository(tmp_path / "identity")
    _create(identity_repo)
    _rewrite_payload(
        identity_repo.database_path,
        "direct_use_admission_snapshots",
        "admission_id",
        "admission-1",
        lambda payload: payload.__setitem__("assignment_id", "forged-assignment"),
    )
    with pytest.raises(PersistenceIntegrityError, match="column assignment_id"):
        identity_repo.load("admission-1")


def test_approval_binding_mismatch_and_component_identity_mismatch_fail_closed(tmp_path):
    approval_repo = _new_repository(tmp_path / "approval-id")
    _create(approval_repo)
    _approve_assignment(approval_repo)
    _rewrite_payload(
        approval_repo.database_path,
        "direct_use_lifecycle_events",
        "event_id",
        "event-assignment-approved",
        lambda payload: payload.__setitem__(
            "approval_binding_id", "forged-approval"
        ),
    )
    with pytest.raises(PersistenceIntegrityError):
        approval_repo.load("admission-1")

    component_repo = _new_repository(tmp_path / "component")
    _create(component_repo)
    connection = sqlite3.connect(component_repo.database_path)
    try:
        connection.execute(
            "UPDATE direct_use_lifecycle_events SET component_id = 'forged-component'"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PersistenceIntegrityError, match="component_id"):
        component_repo.load("admission-1")


def test_invalid_and_naive_timestamps_fail_closed(tmp_path):
    with pytest.raises(ContractValidationError, match="timezone"):
        _new_repository(tmp_path).create_admission(
            _assignment(),
            _admission(AdmissionState.DRY_RUN_ASSIGNABLE),
            _event(
                "event-create",
                "transaction-create",
                None,
                AdmissionState.DRY_RUN_ASSIGNABLE,
                minute=0,
            ),
            transaction_id="transaction-create",
            recorded_at=datetime(2030, 1, 1),
        )
    invalid_repo = _new_repository(tmp_path / "invalid")
    _create(invalid_repo)
    _rewrite_payload(
        invalid_repo.database_path,
        "direct_use_lifecycle_events",
        "event_id",
        "event-create",
        lambda payload: payload.__setitem__("occurred_at", "not-a-time"),
    )
    with pytest.raises(PersistenceIntegrityError, match="lifecycle event"):
        invalid_repo.load("admission-1")


def test_event_ordering_chain_and_incomplete_transaction_fail_closed(tmp_path):
    order_repo = _new_repository(tmp_path / "order")
    _create(order_repo)
    _approve_assignment(order_repo)
    connection = sqlite3.connect(order_repo.database_path)
    try:
        connection.execute(
            "UPDATE direct_use_lifecycle_events SET previous_event_id = NULL WHERE sequence_no = 2"
        )
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PersistenceIntegrityError, match="previous_event_id"):
        order_repo.load("admission-1")

    incomplete_repo = _new_repository(tmp_path / "incomplete")
    _create(incomplete_repo)
    connection = sqlite3.connect(incomplete_repo.database_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("DELETE FROM direct_use_lifecycle_events")
        connection.commit()
    finally:
        connection.close()
    with pytest.raises(PersistenceIntegrityError, match="incomplete"):
        incomplete_repo.load("admission-1")


def test_tampered_event_timestamp_order_fails_even_with_recomputed_chain_hash(tmp_path):
    repository = _new_repository(tmp_path)
    _create(repository)
    _approve_assignment(repository)
    connection = sqlite3.connect(repository.database_path)
    try:
        first_chain = connection.execute(
            "SELECT chain_sha256 FROM direct_use_lifecycle_events WHERE sequence_no = 1"
        ).fetchone()[0]
        payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM direct_use_lifecycle_events WHERE sequence_no = 2"
            ).fetchone()[0]
        )
        payload["occurred_at"] = "2029-12-31T00:00:00.000000Z"
        encoded = json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        chain = hashlib.sha256(f"{first_chain}:{digest}".encode("utf-8")).hexdigest()
        connection.execute(
            """UPDATE direct_use_lifecycle_events
               SET payload_json = ?, payload_sha256 = ?, chain_sha256 = ?
               WHERE sequence_no = 2""",
            (encoded, digest, chain),
        )
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PersistenceIntegrityError, match="occurred_at ordering"):
        repository.load("admission-1")


def test_event_type_and_formal_rights_gate_fail_closed(tmp_path):
    repository = _new_repository(tmp_path / "event-type")
    _create(repository)
    approval = _approval("approval-event-type")
    event = _event(
        "event-wrong-type",
        "transaction-wrong-type",
        AdmissionState.DRY_RUN_ASSIGNABLE,
        AdmissionState.ASSIGNMENT_APPROVED,
        minute=1,
        approval=approval,
    )
    object.__setattr__(event, "event_type", "FORMAL_ADMISSION")
    with pytest.raises(ContractValidationError, match="event type"):
        repository.transition_admission(
            _admission(AdmissionState.ASSIGNMENT_APPROVED),
            event,
            expected_state=AdmissionState.DRY_RUN_ASSIGNABLE,
            transaction_id="transaction-wrong-type",
            recorded_at=BASE + timedelta(minutes=1, seconds=1),
            approval_binding=approval,
        )

    rights_repository = _new_repository(tmp_path / "rights-gate")
    unresolved_rights = RightsState()
    rights_repository.create_admission(
        _assignment(),
        _admission(
            AdmissionState.DRY_RUN_ASSIGNABLE,
            rights_snapshot=unresolved_rights,
        ),
        _event(
            "event-create",
            "transaction-create",
            None,
            AdmissionState.DRY_RUN_ASSIGNABLE,
            minute=0,
        ),
        transaction_id="transaction-create",
        recorded_at=BASE + timedelta(seconds=1),
    )
    _approve_assignment(rights_repository, rights_snapshot=unresolved_rights)
    _commit_assignment(rights_repository, rights_snapshot=unresolved_rights)
    formal = _approval(
        "approval-formal", decision_at=BASE + timedelta(minutes=2, seconds=30)
    )
    with pytest.raises(ContractValidationError, match="requires runtime-resolution"):
        rights_repository.transition_admission(
            _admission(
                AdmissionState.FORMALLY_ADMITTED,
                approval=formal,
                rights_snapshot=unresolved_rights,
            ),
            _event(
                "event-formal-without-rights",
                "transaction-formal-without-rights",
                AdmissionState.ASSIGNED_NOT_ADMITTED,
                AdmissionState.FORMALLY_ADMITTED,
                minute=3,
                approval=formal,
            ),
            expected_state=AdmissionState.ASSIGNED_NOT_ADMITTED,
            transaction_id="transaction-formal-without-rights",
            recorded_at=BASE + timedelta(minutes=3, seconds=1),
            approval_binding=formal,
        )


@pytest.mark.parametrize(
    "invalid_identity",
    ("", "contains spaces", "contains\\newline", "x" * 129),
)
def test_invalid_assignment_identities_fail_closed(invalid_identity):
    with pytest.raises(ContractValidationError):
        _assignment(component_id=invalid_identity)


def test_duplicate_approval_identity_is_rejected_across_admissions(tmp_path):
    repository = _new_repository(tmp_path)
    _create(repository)
    _approve_assignment(repository)
    repository.create_admission(
        _assignment(assignment_id="assignment-2", admission_id="admission-2"),
        _admission(
            AdmissionState.DRY_RUN_ASSIGNABLE,
            admission_id="admission-2",
            assignment_id="assignment-2",
        ),
        _event(
            "event-create-2",
            "transaction-create-2",
            None,
            AdmissionState.DRY_RUN_ASSIGNABLE,
            minute=0,
            admission_id="admission-2",
        ),
        transaction_id="transaction-create-2",
        recorded_at=BASE + timedelta(seconds=1),
    )
    duplicate = _approval(
        "approval-assignment",
        admission_id="admission-2",
        decision_at=BASE + timedelta(seconds=30),
    )
    with pytest.raises(DuplicatePersistenceIdentity, match="approval binding"):
        repository.transition_admission(
            _admission(
                AdmissionState.ASSIGNMENT_APPROVED,
                admission_id="admission-2",
                assignment_id="assignment-2",
            ),
            _event(
                "event-approve-2",
                "transaction-approve-2",
                AdmissionState.DRY_RUN_ASSIGNABLE,
                AdmissionState.ASSIGNMENT_APPROVED,
                minute=1,
                approval=duplicate,
                admission_id="admission-2",
            ),
            expected_state=AdmissionState.DRY_RUN_ASSIGNABLE,
            transaction_id="transaction-approve-2",
            recorded_at=BASE + timedelta(minutes=1, seconds=1),
            approval_binding=duplicate,
        )
    assert repository.load("admission-2").current_admission.state is AdmissionState.DRY_RUN_ASSIGNABLE


def test_incomplete_schema_is_not_silently_repaired(tmp_path):
    repository = _new_repository(tmp_path)
    repository.initialize()
    connection = sqlite3.connect(repository.database_path)
    try:
        connection.execute("DROP TABLE direct_use_transaction_journal")
        connection.commit()
    finally:
        connection.close()

    with pytest.raises(PersistenceIntegrityError, match="schema is incomplete"):
        repository.initialize()

    connection = sqlite3.connect(repository.database_path)
    try:
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'direct_use_transaction_journal'"
        ).fetchone() is None
    finally:
        connection.close()


def test_repository_open_write_failure_is_wrapped(tmp_path):
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("block", encoding="utf-8")
    repository = ComponentAdmissionRepository(blocking_file / "admission.db")

    with pytest.raises(AdmissionPersistenceError, match="opened for writing"):
        _create(repository)


def test_catalog_and_selectability_invariants_remain_unchanged(tmp_path):
    repository = _new_repository(tmp_path)
    _through_formal(repository)

    rows = catalog_library_view_records()

    assert len(rows) == 156
    assert {
        row["registry_component_id"]
        for row in rows
        if row["formal_selectable"]
    } == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}
