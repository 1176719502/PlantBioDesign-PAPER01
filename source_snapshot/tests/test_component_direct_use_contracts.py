from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

import services.component_direct_use_contracts as direct_use_contracts
from services.component_direct_use_contracts import (
    AdmissionState,
    ApprovalBinding,
    BackboneLifecycle,
    BackboneState,
    ComponentAdmission,
    ComponentReference,
    ComponentResolvedSequence,
    ComponentResolutionRequest,
    ComponentSelectionSnapshot,
    ComponentType,
    ContractValidationError,
    ResolutionFailureCode,
    ResolutionStatus,
    RightsDecision,
    RightsOutcome,
    RightsState,
    SelectionSource,
    is_component_selectable,
    is_backbone_selectable,
    BackboneResolutionEvidence, BackboneBoundaryEvidence, BackboneApprovalBinding, BackboneRightsEvidence,
    RightsEvidence,
    is_admission_current,
    sequence_sha256,
    validate_admission_transition,
    validate_backbone_transition,
)


DNA = "ACGT"
HASH = sequence_sha256(DNA)
NOW = datetime.now(timezone.utc)

def _evidence(dimension, ref="ref-1"):
    return RightsEvidence(evidence_id=f"ev-{dimension}", rights_dimension=dimension,
            operation=dimension, workflow_scope=("single_gene",), reference_id=ref,
            reference_version=1, admission_id="adm-1", admission_version=1,
            authority_id="authority", source_id="review-1", policy_version="p1",
            decision_id=f"decision-{dimension}", decision_hash="a" * 64,
            provenance={"record": "review-1"}, evaluated_at=NOW)


def _rights(**overrides):
    values = {
        "rights_for_bundling": RightsDecision.UNKNOWN,
        "rights_for_runtime_resolution": RightsDecision.ELIGIBLE,
        "rights_for_local_materialization": RightsDecision.ELIGIBLE,
        "rights_for_reference_metadata": RightsDecision.UNKNOWN,
    }
    values.update(overrides)
    values["evidence"] = {d: _evidence(d) for d, k in (("runtime_resolution", "rights_for_runtime_resolution"), ("local_materialization", "rights_for_local_materialization"), ("bundling", "rights_for_bundling"), ("reference_metadata", "rights_for_reference_metadata")) if values[k] is RightsDecision.ELIGIBLE}
    return RightsState(**values)


def _reference(**overrides):
    values = dict(
        reference_id="ref-1",
        reference_version=1,
        component_id="cmp-1",
        component_type=ComponentType.CDS,
        display_name="Example CDS",
        source_provenance={"source": "review-record", "accession": "NM_000000.1", "source_version": "1"},
    )
    values.update(overrides)
    return ComponentReference(**values)


def _admission(state=AdmissionState.FORMALLY_ADMITTED, **overrides):
    values = dict(
        admission_id="adm-1",
        admission_version=1,
        reference_id="ref-1",
        reference_version=1,
        assignment_id="assign-1",
        state=state,
        workflow_scope=("single_gene",),
        role_scope=("cds",),
        rights_snapshot=_rights(),
        approval_binding=ApprovalBinding("authority-1", "policy-v1", "decision-1", "a" * 64, "approver-1", NOW, "sig-1", "adm-1", "ref-1", 1),
    )
    values.update(overrides)
    return ComponentAdmission(**values)


def _request(**overrides):
    values = dict(
        request_id="req-1",
        request_version=1,
        component_id="cmp-1",
        admission_id="adm-1",
        admission_version=1,
        provider="NCBI",
        accession="NM_000000.1",
        source_version="NM_000000.1",
        feature_identity="CDS",
        start=0,
        end=4,
        strand=1,
        coordinate_system="0-based-half-open",
        expected_length=4,
        expected_sha256=HASH,
        requested_mechanism="pinned_provider_api",
        requested_at=NOW,
    )
    values.update(overrides)
    return ComponentResolutionRequest(**values)


def _resolved_sequence(**overrides):
    values = dict(
        resolution_id="res-1",
        resolution_version=1,
        request_id="req-1",
        request_version=1,
        provider="NCBI",
        accession="NM_000000.1",
        version="1",
        feature_identity="cmp-1",
        start=0,
        end=4,
        strand="+",
        coordinate_system="0-based-half-open",
        expected_length=4,
        expected_sha256=HASH,
        retrieved_length=4,
        retrieved_sha256=HASH,
        resolution_mechanism="local",
        resolved_at=NOW,
        provider_provenance={},
        rights_evaluation_id="rights-1",
        status=ResolutionStatus.RESOLVED,
        sequence=DNA,
        component_id="cmp-1",
        admission_id="adm-1",
        admission_version=1,
    )
    values.update(overrides)
    return ComponentResolvedSequence(**values)


def test_domain_objects_are_explicit_and_immutable():
    ref = _reference(sequence_length=4, sequence_sha256=HASH, sequence=DNA)
    assert ref.component_type is ComponentType.CDS
    with pytest.raises((FrozenInstanceError, AttributeError, TypeError)):
        ref.component_id = "other"


def test_invalid_required_fields_and_hashes_fail_closed():
    with pytest.raises(ContractValidationError):
        _reference(reference_id="")
    with pytest.raises(ContractValidationError):
        _reference(sequence_length=4, sequence_sha256="not-a-hash")
    with pytest.raises(ContractValidationError):
        _request(expected_sha256="0" * 63)
    with pytest.raises(ContractValidationError):
        _request(start=8, end=4)


def test_legal_admission_transitions_and_required_evidence():
    binding = ApprovalBinding("a", "v1", "d", "a" * 64, "p", NOW, "s", "adm-1", "ref-1", 1)
    validate_admission_transition(AdmissionState.DRY_RUN_ASSIGNABLE, AdmissionState.ASSIGNMENT_APPROVED)
    validate_admission_transition(AdmissionState.ASSIGNMENT_APPROVED, AdmissionState.ASSIGNED_NOT_ADMITTED)
    validate_admission_transition(AdmissionState.ASSIGNED_NOT_ADMITTED, AdmissionState.FORMALLY_ADMITTED, approval_binding=binding)
    validate_admission_transition(AdmissionState.FORMALLY_ADMITTED, AdmissionState.ADMISSION_FAILED, failure_code=ResolutionFailureCode.BOUNDARY_MISMATCH)
    validate_admission_transition(AdmissionState.FORMALLY_ADMITTED, AdmissionState.REVOKED, revocation_reason="rights withdrawn")
    validate_admission_transition(AdmissionState.FORMALLY_ADMITTED, AdmissionState.RETIRED)


def test_illegal_admission_transitions_fail_closed():
    with pytest.raises(ContractValidationError):
        validate_admission_transition(AdmissionState.DRY_RUN_ASSIGNABLE, AdmissionState.FORMALLY_ADMITTED, approval_binding={"authority_id": "a"})
    with pytest.raises(ContractValidationError):
        validate_admission_transition(AdmissionState.REVOKED, AdmissionState.FORMALLY_ADMITTED, approval_binding={"authority_id": "a"})
    with pytest.raises(ContractValidationError):
        validate_admission_transition(AdmissionState.FORMALLY_ADMITTED, AdmissionState.ADMISSION_FAILED)


def test_rights_states_are_independent():
    rights = RightsState(
        rights_for_bundling=RightsDecision.DENIED,
        rights_for_runtime_resolution=RightsDecision.ELIGIBLE,
        rights_for_local_materialization=RightsDecision.UNKNOWN,
        rights_for_reference_metadata=RightsDecision.ELIGIBLE,
        evidence={"reference_metadata": _evidence("reference_metadata"), "runtime_resolution": _evidence("runtime_resolution")},
    )
    assert rights.operation_outcome("bundling").value == "RIGHTS_FOR_BUNDLING_DENIED"
    assert rights.operation_outcome("metadata").value == "RIGHTS_ELIGIBLE"
    assert not rights.is_runtime_eligible()
    assert RightsDecision.UNPROVEN.value == "UNPROVEN"


def test_resolution_failure_enums_and_hash_length_contract():
    for code in ResolutionFailureCode:
        result = ComponentResolvedSequence(
            resolution_id="res-1", resolution_version=1, request_id="req-1", request_version=1,
            provider="NCBI", accession="NM_000000.1", version="NM_000000.1",
            feature_identity="CDS", start=0, end=4, strand="+", coordinate_system="0-based-half-open",
            expected_length=4, expected_sha256=HASH, retrieved_length=None, retrieved_sha256=None,
            resolution_mechanism="pinned_provider_api", resolved_at=NOW,
            provider_provenance={"uri": "https://example.invalid"}, rights_evaluation_id="rights-1",
            status=ResolutionStatus(code.value),
        )
        assert result.sequence is None
    with pytest.raises(ContractValidationError):
        ComponentResolvedSequence(
            resolution_id="res-1", resolution_version=1, request_id="req-1", request_version=1,
            provider="NCBI", accession="A", version="1", feature_identity="CDS", start=0, end=4,
            strand="+", coordinate_system="0-based-half-open", expected_length=4, expected_sha256=HASH,
            retrieved_length=3, retrieved_sha256=HASH, resolution_mechanism="local", resolved_at=NOW,
            provider_provenance={}, rights_evaluation_id="rights-1", status=ResolutionStatus.RESOLVED,
            sequence=None,
        )


def test_selection_snapshot_library_and_custom_contracts():
    snapshot = ComponentSelectionSnapshot(
        snapshot_id="snap-1", snapshot_version=1, component_id="cmp-1", reference_id="ref-1",
        admission_id="adm-1", admission_version=1, accession="NM_000000.1", source_version="1",
        exact_selected_sequence=DNA, exact_sha256=HASH, exact_length=4, start=0, end=4, strand="+",
        coordinate_system="0-based-half-open", workflow_role="cds", workflow_kind="single_gene",
        host_scope="rice", evidence_scope="reviewed", rights_state_at_selection=_rights(),
        resolution_id="res-1", resolution_provenance={"provider": "NCBI"},
        selection_source=SelectionSource.LIBRARY_SELECTED, selected_at=NOW,
    )
    assert snapshot.exact_sha256 == HASH
    custom = ComponentSelectionSnapshot(
        snapshot_id="snap-custom", snapshot_version=1, component_id=None, reference_id=None,
        admission_id=None, admission_version=None, accession=None, source_version=None,
        exact_selected_sequence=DNA, exact_sha256=HASH, exact_length=4, start=None, end=None,
        strand=None, coordinate_system=None, workflow_role="cds", workflow_kind="single_gene",
        host_scope="user", evidence_scope="user-provided", rights_state_at_selection=RightsState(),
        resolution_id=None, resolution_provenance={"source": "user"},
        selection_source=SelectionSource.USER_CUSTOM, selected_at=NOW,
    )
    assert custom.selection_source is SelectionSource.USER_CUSTOM
    with pytest.raises(ContractValidationError):
        ComponentSelectionSnapshot(
            snapshot_id="snap-2", snapshot_version=1, component_id=None, reference_id="ref-claimed",
            admission_id=None, admission_version=None, accession=None, source_version=None,
            exact_selected_sequence=DNA, exact_sha256=HASH, exact_length=4, start=None, end=None,
            strand=None, coordinate_system=None, workflow_role="cds", workflow_kind="single_gene",
            host_scope="user", evidence_scope="user", rights_state_at_selection=RightsState(),
            resolution_id=None, resolution_provenance={}, selection_source=SelectionSource.USER_CUSTOM,
        )


def test_backbone_lifecycle_and_resolution_never_implies_admission():
    for prior, nxt in zip(tuple(BackboneState)[:-1], tuple(BackboneState)[1:]):
        evidence = {
            "resolution_evidence": BackboneResolutionEvidence("r", "bb", 1, "p", "acc", "v", "res", 4, HASH, 4, HASH, "a", "1"),
            "boundary_evidence": BackboneBoundaryEvidence("b", "bb", 1, "insertion", 0, 4, "+", {"left": "A"}, 4, HASH, "a", "1"),
            "approval_binding": BackboneApprovalBinding("a", "bb", 1, "adm-bb", "direct_use", ("single_gene",), "auth", "p1", "d", "a"*64, NOW, "sig", "1"),
            "rights_evidence": BackboneRightsEvidence("rights", "runtime_resolution", "runtime_resolution", ("single_gene",), "bb-ref", 1, "adm-bb", 1, "auth", "src", "p1", "d", "a"*64, NOW, None, {"record": "r"}, backbone_id="bb", backbone_version=1),
        }
        if nxt is BackboneState.BACKBONE_RESOLUTION_ELIGIBLE:
            validate_backbone_transition(prior, nxt, resolution_evidence=evidence["resolution_evidence"], rights_evidence=evidence["rights_evidence"])
        elif nxt is BackboneState.BACKBONE_BOUNDARY_VERIFIED:
            validate_backbone_transition(
                prior, nxt, resolution_evidence=evidence["resolution_evidence"],
                boundary_evidence=evidence["boundary_evidence"], rights_evidence=evidence["rights_evidence"],
            )
        elif nxt is BackboneState.FORMALLY_ADMITTED_BACKBONE:
            validate_backbone_transition(prior, nxt, **evidence)
        else:
            validate_backbone_transition(prior, nxt, **evidence)
    with pytest.raises(ContractValidationError):
        validate_backbone_transition(BackboneState.REFERENCE_BACKBONE, BackboneState.SELECTABLE_BACKBONE)
    backbone = BackboneLifecycle("bb-1", 1)
    assert backbone.state is BackboneState.REFERENCE_BACKBONE
    resolved = ComponentResolvedSequence(
        resolution_id="res-2", resolution_version=1, request_id="req-1", request_version=1,
        provider="NCBI", accession="A", version="1", feature_identity="CDS", start=0, end=4,
        strand="+", coordinate_system="0-based-half-open", expected_length=4, expected_sha256=HASH,
        retrieved_length=4, retrieved_sha256=HASH, resolution_mechanism="local", resolved_at=NOW,
        provider_provenance={}, rights_evaluation_id="rights-1", status=ResolutionStatus.RESOLVED, sequence=DNA,
        component_id="cmp-1", admission_id="adm-1", admission_version=1,
    )
    not_admitted = _admission(AdmissionState.ASSIGNED_NOT_ADMITTED, approval_binding={})
    assert not is_component_selectable(not_admitted, _rights())


def test_formal_admission_requires_complete_bound_approval():
    with pytest.raises(ContractValidationError):
        _admission(approval_binding={})
    with pytest.raises(ContractValidationError):
        _admission(approval_binding={"authority_id": "a"})
    with pytest.raises(ContractValidationError):
        _admission(approval_binding=ApprovalBinding("a", "v1", "d", "bad", "p", NOW, "s", "adm-1", "ref-1", 1))
    with pytest.raises(ContractValidationError):
        _admission(approval_binding={"authority_id": "a", "policy_version": "v1", "decision_id": "d", "decision_hash": "a"*64, "approver_id": "p", "decision_timestamp": "2024-01-01", "signature": "s", "admission_id": "wrong", "reference_id": "ref-1", "reference_version": 1})


def test_rights_eligible_requires_dimension_bound_evidence():
    with pytest.raises(ContractValidationError):
        RightsState(rights_for_runtime_resolution=RightsDecision.ELIGIBLE)
    with pytest.raises(ContractValidationError):
        RightsState(rights_for_runtime_resolution=RightsDecision.ELIGIBLE, evidence={"runtime_resolution": {"rights_dimension": "bundling"}})


def test_recursive_immutability_copies_nested_inputs():
    original = {"nested": {"x": 1}, "items": [1, 2]}
    ref = _reference(source_provenance=original)
    original["nested"]["x"] = 9
    original["items"].append(3)
    assert ref.source_provenance["nested"]["x"] == 1
    with pytest.raises(TypeError):
        ref.source_provenance["nested"]["x"] = 2


def test_backbone_advanced_states_cannot_be_forged():
    with pytest.raises(ContractValidationError):
        BackboneLifecycle("bb", 1, BackboneState.SELECTABLE_BACKBONE)
    with pytest.raises(ContractValidationError):
        validate_backbone_transition(BackboneState.REFERENCE_BACKBONE, BackboneState.BACKBONE_RESOLUTION_ELIGIBLE)
    with pytest.raises(ContractValidationError):
        BackboneLifecycle("bb", 1, BackboneState.BACKBONE_RESOLUTION_ELIGIBLE, resolution_evidence={"x": 1})


def test_r3_resolution_without_bytes_and_rights_scope_fail_closed():
    ref = _reference()
    admission = _admission()
    resolution = ComponentResolvedSequence(
        resolution_id="res-r3", resolution_version=1, request_id="req-1", request_version=1,
        provider="NCBI", accession="NM_000000.1", version="1", feature_identity="cmp-1",
        start=0, end=4, strand="+", coordinate_system="0-based-half-open", expected_length=4,
        expected_sha256=HASH, retrieved_length=4, retrieved_sha256=HASH,
        resolution_mechanism="local", resolved_at=NOW, provider_provenance={},
        rights_evaluation_id="rights-1", status=ResolutionStatus.RESOLVED,
        sequence=None, component_id="cmp-1", admission_id="adm-1", admission_version=1,
    )
    assert not is_component_selectable(ref, admission, _rights(), resolution,
                                       workflow_role="cds", workflow_scope="single_gene")
    wrong_scope = RightsEvidence(
        evidence_id="wrong", rights_dimension="runtime_resolution", operation="runtime_resolution",
        workflow_scope=("multi_tu",), reference_id="ref-1", reference_version=1,
        admission_id="adm-1", admission_version=1, authority_id="a", source_id="s",
        policy_version="p", decision_id="d", decision_hash="a"*64, evaluated_at=NOW,
        provenance={"record": "r"},
    )
    scoped_rights = RightsState(
        rights_for_runtime_resolution=RightsDecision.ELIGIBLE,
        rights_for_local_materialization=RightsDecision.ELIGIBLE,
        evidence={"runtime_resolution": wrong_scope, "local_materialization": _evidence("local_materialization")},
    )
    assert not is_component_selectable(ref, admission, scoped_rights, resolution,
                                       workflow_role="cds", workflow_scope="single_gene")


def test_backbone_structured_evidence_and_selection_gate():
    resolution = BackboneResolutionEvidence("r", "bb", 1, "p", "acc", "v", "res", 4, HASH, 4, HASH, "a", "1")
    boundary = BackboneBoundaryEvidence("b", "bb", 1, "insertion", 0, 4, "+", {"left": "A", "right": "T"}, 4, HASH, "a", "1")
    approval = BackboneApprovalBinding("a", "bb", 1, "adm-bb", "direct_use", ("single_gene",), "auth", "p1", "d", "a"*64, NOW, "sig", "1")
    rights = BackboneRightsEvidence("rights", "runtime_resolution", "runtime_resolution", ("single_gene",), "bb-ref", 1, "adm-bb", 1, "auth", "src", "p1", "d", "a"*64, NOW, None, {"record": "r"}, backbone_id="bb", backbone_version=1)
    backbone = BackboneLifecycle("bb", 1, BackboneState.SELECTABLE_BACKBONE, boundary, resolution, approval, rights)
    assert is_backbone_selectable(backbone, workflow_scope="single_gene")
    assert not is_backbone_selectable(backbone, workflow_scope="multi_tu")
    with pytest.raises(ContractValidationError):
        BackboneLifecycle("bb", 1, BackboneState.FORMALLY_ADMITTED_BACKBONE, approval_binding={"x": 1})


@pytest.mark.parametrize(
    ("start", "end", "expected_length"),
    ((4, 4, 4), (0, 3, 4), (0, 5, 4)),
)
def test_backbone_boundary_span_must_match_expected_length(start, end, expected_length):
    with pytest.raises(ContractValidationError):
        BackboneBoundaryEvidence(
            "b", "bb", 1, "insertion", start, end, "+", {"left": "A"},
            expected_length, HASH, "authority", "1",
        )


def test_backbone_boundary_accepts_exact_half_open_span():
    boundary = BackboneBoundaryEvidence(
        "b", "bb", 1, "replacement", 99, 103, "reverse", {"left": "A", "right": "T"},
        4, HASH, "authority", "1",
    )
    assert (boundary.start, boundary.end, boundary.end - boundary.start) == (99, 103, 4)


def test_formal_admission_interval_is_deterministic_and_expiry_is_exclusive():
    effective = datetime(2030, 1, 1, tzinfo=timezone.utc)
    expires = datetime(2030, 2, 1, tzinfo=timezone.utc)
    admission = _admission(effective_at=effective, expires_at=expires)
    assert not is_admission_current(admission, evaluation_time=datetime(2029, 12, 31, 23, 59, tzinfo=timezone.utc))
    assert is_admission_current(admission, evaluation_time=effective)
    assert is_admission_current(admission, evaluation_time=datetime(2030, 1, 15, tzinfo=timezone.utc))
    assert not is_admission_current(admission, evaluation_time=expires)
    assert not is_admission_current(admission, evaluation_time=datetime(2030, 2, 2, tzinfo=timezone.utc))
    assert not is_admission_current(admission)


@pytest.mark.parametrize("value", ("2030-01-01", "not-a-timestamp"))
def test_admission_timestamps_require_timezone_and_valid_iso(value):
    with pytest.raises(ContractValidationError):
        _admission(effective_at=value)


def test_admission_rejects_inverted_interval_and_open_ended_interval_is_supported():
    with pytest.raises(ContractValidationError):
        _admission(effective_at="2030-02-01T00:00:00Z", expires_at="2030-01-01T00:00:00Z")
    open_ended = _admission(effective_at="2030-01-01T00:00:00Z")
    assert is_admission_current(open_ended, evaluation_time="2099-01-01T00:00:00Z")


@pytest.mark.parametrize(
    "evaluation_time",
    ("not-a-timestamp", datetime(2030, 1, 1)),
)
def test_unbounded_admission_rejects_explicit_invalid_evaluation_time(evaluation_time):
    open_ended = _admission()
    assert not is_admission_current(open_ended, evaluation_time=evaluation_time)
    assert not is_admission_current(open_ended, now_utc=evaluation_time)


@pytest.mark.parametrize(
    "evaluation_time",
    (
        datetime(2030, 1, 1, tzinfo=timezone.utc),
        datetime(2030, 1, 1, tzinfo=timezone(timedelta(hours=8))),
    ),
)
def test_unbounded_admission_accepts_valid_aware_evaluation_time(evaluation_time):
    assert is_admission_current(_admission(), evaluation_time=evaluation_time)


def test_bounded_admission_rejects_malformed_or_conflicting_evaluation_time():
    admission = _admission(
        effective_at="2030-01-01T00:00:00Z",
        expires_at="2030-02-01T00:00:00Z",
    )
    assert not is_admission_current(admission, evaluation_time="not-a-timestamp")
    assert not is_admission_current(admission, evaluation_time=datetime(2030, 1, 1))
    assert not is_admission_current(admission, evaluation_time=NOW, now_utc=NOW)


def _backbone_evidence():
    return {
        "resolution_evidence": BackboneResolutionEvidence(
            "r", "bb", 1, "p", "acc", "v", "res", 4, HASH, 4, HASH, "a", "1"
        ),
        "boundary_evidence": BackboneBoundaryEvidence(
            "b", "bb", 1, "insertion", 0, 4, "+", {"left": "A"}, 4, HASH, "a", "1"
        ),
        "approval_binding": BackboneApprovalBinding(
            "a", "bb", 1, "adm-bb", "direct_use", ("single_gene",), "auth", "p1",
            "d", "a" * 64, NOW, "sig", "1"
        ),
        "rights_evidence": BackboneRightsEvidence(
            "rights", "runtime_resolution", "runtime_resolution", ("single_gene",),
            "bb-ref", 1, "adm-bb", 1, "auth", "src", "p1", "d", "a" * 64, NOW,
            None, {"record": "r"}, backbone_id="bb", backbone_version=1
        ),
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (("start", 1), ("end", 5), ("expected_length", 3), ("boundary_type", "bad"),
     ("orientation", "bad"), ("expected_sha256", "b" * 64), ("backbone_id", "other"),
     ("backbone_version", 2)),
)
def test_backbone_transition_revalidates_corrupted_boundary(field, value):
    evidence = _backbone_evidence()
    boundary = evidence["boundary_evidence"]
    object.__setattr__(boundary, field, value)
    with pytest.raises(ContractValidationError):
        validate_backbone_transition(
            BackboneState.BACKBONE_RESOLUTION_ELIGIBLE,
            BackboneState.BACKBONE_BOUNDARY_VERIFIED,
            boundary_evidence=boundary,
            resolution_evidence=evidence["resolution_evidence"],
            rights_evidence=evidence["rights_evidence"],
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (("backbone_id", "other"), ("backbone_version", 2), ("accession", ""),
     ("source_version", ""), ("expected_sha256", "b" * 64)),
)
def test_backbone_transition_revalidates_corrupted_resolution(field, value):
    evidence = _backbone_evidence()
    resolution = evidence["resolution_evidence"]
    object.__setattr__(resolution, field, value)
    with pytest.raises(ContractValidationError):
        validate_backbone_transition(
            BackboneState.REFERENCE_BACKBONE,
            BackboneState.BACKBONE_RESOLUTION_ELIGIBLE,
            resolution_evidence=resolution,
            rights_evidence=evidence["rights_evidence"],
        )


def test_backbone_transition_revalidates_corrupted_approval_and_rights():
    evidence = _backbone_evidence()
    object.__setattr__(evidence["approval_binding"], "decision_hash", "bad")
    with pytest.raises(ContractValidationError):
        validate_backbone_transition(
            BackboneState.BACKBONE_BOUNDARY_VERIFIED,
            BackboneState.FORMALLY_ADMITTED_BACKBONE,
            **evidence,
        )

    evidence = _backbone_evidence()
    object.__setattr__(evidence["rights_evidence"], "reference_version", 0)
    with pytest.raises(ContractValidationError):
        validate_backbone_transition(
            BackboneState.REFERENCE_BACKBONE,
            BackboneState.BACKBONE_RESOLUTION_ELIGIBLE,
            resolution_evidence=evidence["resolution_evidence"],
            rights_evidence=evidence["rights_evidence"],
        )


@pytest.mark.parametrize(
    ("evidence_name", "field", "value"),
    (
        ("resolution_evidence", "accession", ""),
        ("boundary_evidence", "provenance_version", ""),
        ("approval_binding", "admission_id", "other-admission"),
        ("rights_evidence", "source_id", ""),
    ),
)
def test_selectable_transition_revalidates_every_evidence_contract(evidence_name, field, value):
    evidence = _backbone_evidence()
    object.__setattr__(evidence[evidence_name], field, value)
    with pytest.raises(ContractValidationError):
        validate_backbone_transition(
            BackboneState.FORMALLY_ADMITTED_BACKBONE,
            BackboneState.SELECTABLE_BACKBONE,
            **evidence,
        )

def test_backbone_selectability_remains_fail_closed_for_forged_boundary():
    evidence = _backbone_evidence()
    boundary = evidence["boundary_evidence"]
    backbone = BackboneLifecycle(
        "bb", 1, BackboneState.SELECTABLE_BACKBONE, boundary,
        evidence["resolution_evidence"], evidence["approval_binding"], evidence["rights_evidence"],
    )
    object.__setattr__(boundary, "end", 5)
    assert not is_backbone_selectable(backbone, workflow_scope="single_gene", evaluation_time=NOW)


@pytest.mark.parametrize("evaluation_time", ("not-a-timestamp", datetime(2030, 1, 1)))
def test_backbone_selectability_rejects_explicit_invalid_time_when_rights_are_unbounded(evaluation_time):
    evidence = _backbone_evidence()
    backbone = BackboneLifecycle(
        "bb", 1, BackboneState.SELECTABLE_BACKBONE, evidence["boundary_evidence"],
        evidence["resolution_evidence"], evidence["approval_binding"], evidence["rights_evidence"],
    )
    assert not is_backbone_selectable(
        backbone, workflow_scope="single_gene", evaluation_time=evaluation_time
    )
    assert not is_backbone_selectable(
        backbone, workflow_scope="single_gene", now_utc=evaluation_time
    )


def test_selectability_gates_reject_conflicting_explicit_time_aliases():
    evidence = _backbone_evidence()
    backbone = BackboneLifecycle(
        "bb", 1, BackboneState.SELECTABLE_BACKBONE, evidence["boundary_evidence"],
        evidence["resolution_evidence"], evidence["approval_binding"], evidence["rights_evidence"],
    )
    assert not is_backbone_selectable(
        backbone, workflow_scope="single_gene", evaluation_time=NOW, now_utc=NOW
    )

    reference = _reference(sequence_length=4, sequence_sha256=HASH, sequence=DNA)
    resolution = ComponentResolvedSequence(
        resolution_id="res-conflict", resolution_version=1, request_id="req-1", request_version=1,
        provider="NCBI", accession="NM_000000.1", version="1", feature_identity="cmp-1",
        start=0, end=4, strand="+", coordinate_system="0-based-half-open", expected_length=4,
        expected_sha256=HASH, retrieved_length=4, retrieved_sha256=HASH,
        resolution_mechanism="local", resolved_at=NOW, provider_provenance={},
        rights_evaluation_id="rights-1", status=ResolutionStatus.RESOLVED, sequence=DNA,
        component_id="cmp-1", admission_id="adm-1", admission_version=1,
    )
    assert not is_component_selectable(
        reference, _admission(), _rights(), resolution,
        workflow_role="cds", workflow_scope="single_gene",
        evaluation_time=NOW, now_utc=NOW,
    )


def test_component_selectability_applies_admission_interval_gate():
    reference = _reference(sequence_length=4, sequence_sha256=HASH, sequence=DNA)
    admission = _admission(
        effective_at="2030-01-01T00:00:00Z",
        expires_at="2030-02-01T00:00:00Z",
    )
    resolution = ComponentResolvedSequence(
        resolution_id="res-interval", resolution_version=1, request_id="req-1", request_version=1,
        provider="NCBI", accession="NM_000000.1", version="1", feature_identity="cmp-1",
        start=0, end=4, strand="+", coordinate_system="0-based-half-open", expected_length=4,
        expected_sha256=HASH, retrieved_length=4, retrieved_sha256=HASH,
        resolution_mechanism="local", resolved_at=NOW, provider_provenance={},
        rights_evaluation_id="rights-1", status=ResolutionStatus.RESOLVED, sequence=DNA,
        component_id="cmp-1", admission_id="adm-1", admission_version=1,
    )
    assert not is_component_selectable(reference, admission, _rights(), resolution,
                                       workflow_role="cds", workflow_scope="single_gene",
                                       evaluation_time="2029-12-31T23:59:59Z")
    assert is_component_selectable(reference, admission, _rights(), resolution,
                                   workflow_role="cds", workflow_scope="single_gene",
                                   evaluation_time="2030-01-01T00:00:00Z")
    assert not is_component_selectable(reference, admission, _rights(), resolution,
                                       workflow_role="cds", workflow_scope="single_gene",
                                       evaluation_time="2030-02-01T00:00:00Z")
    assert not is_component_selectable(
        reference, _admission(), _rights(), resolution,
        workflow_role="cds", workflow_scope="single_gene",
        evaluation_time="not-a-timestamp",
    )
    assert not is_component_selectable(
        reference, _admission(), _rights(), resolution,
        workflow_role="cds", workflow_scope="single_gene",
        evaluation_time=datetime(2030, 1, 1),
    )
    assert not is_component_selectable(
        reference, _admission(), _rights(), resolution,
        workflow_role="cds", workflow_scope="single_gene",
        now_utc="not-a-timestamp",
    )


@pytest.mark.parametrize(
    ("field", "forged_value"),
    (
        ("reference_id", "forged-reference"),
        ("admission_id", "forged-admission"),
        ("reference_version", 2),
        ("policy_version", "forged-policy"),
        ("decision_id", "forged-decision"),
        ("decision_hash", "not-a-sha256"),
        ("decision_hash", "b" * 64),
        ("authority_id", "forged-authority"),
        ("approver_id", "forged-approver"),
        ("signature", "forged-signature"),
        ("decision_timestamp", NOW + timedelta(days=1)),
    ),
)
def test_forged_approval_binding_fails_every_component_trust_boundary(field, forged_value):
    forged = ApprovalBinding(
        "authority-1", "policy-v1", "decision-1", "a" * 64, "approver-1",
        NOW, "sig-1", "adm-1", "ref-1", 1,
    )
    object.__setattr__(forged, field, forged_value)

    with pytest.raises(ContractValidationError):
        validate_admission_transition(
            AdmissionState.ASSIGNED_NOT_ADMITTED,
            AdmissionState.FORMALLY_ADMITTED,
            approval_binding=forged,
        )
    with pytest.raises(ContractValidationError):
        _admission(approval_binding=forged)

    admission = _admission()
    object.__setattr__(admission.approval_binding, field, forged_value)
    assert not is_component_selectable(
        _reference(sequence_length=4, sequence_sha256=HASH, sequence=DNA),
        admission,
        _rights(),
        _resolved_sequence(),
        workflow_role="cds",
        workflow_scope="single_gene",
        evaluation_time=NOW,
    )


@pytest.mark.parametrize(
    ("dimension", "field", "forged_value"),
    (
        ("runtime_resolution", "rights_dimension", "bundling"),
        ("runtime_resolution", "operation", "bundling"),
        ("runtime_resolution", "workflow_scope", ("multi_tu",)),
        ("runtime_resolution", "reference_id", "forged-reference"),
        ("runtime_resolution", "reference_version", 2),
        ("runtime_resolution", "admission_id", "forged-admission"),
        ("runtime_resolution", "admission_version", 2),
        ("runtime_resolution", "evidence_id", "forged-evidence"),
        ("runtime_resolution", "evidence_version", "2"),
        ("runtime_resolution", "authority_id", "forged-authority"),
        ("runtime_resolution", "source_id", "forged-source"),
        ("runtime_resolution", "policy_version", "forged-policy"),
        ("runtime_resolution", "decision_id", "forged-decision"),
        ("runtime_resolution", "decision_hash", "not-a-sha256"),
        ("runtime_resolution", "decision_hash", "b" * 64),
        ("runtime_resolution", "evaluated_at", NOW - timedelta(days=1)),
        ("runtime_resolution", "provenance", {"record": "forged-record"}),
        ("local_materialization", "valid_until", NOW + timedelta(days=30)),
    ),
)
def test_forged_rights_evidence_fails_construction_runtime_and_component_gates(
    dimension, field, forged_value
):
    forged = _evidence(dimension)
    object.__setattr__(forged, field, forged_value)
    decisions = {
        "rights_for_runtime_resolution": RightsDecision.ELIGIBLE,
        "rights_for_local_materialization": RightsDecision.ELIGIBLE,
    }
    evidence = {
        "runtime_resolution": forged if dimension == "runtime_resolution" else _evidence("runtime_resolution"),
        "local_materialization": forged if dimension == "local_materialization" else _evidence("local_materialization"),
    }
    with pytest.raises(ContractValidationError):
        RightsState(evidence=evidence, **decisions)

    rights = _rights()
    object.__setattr__(rights.evidence[dimension], field, forged_value)
    assert not rights.is_runtime_eligible(evaluation_time=NOW)
    assert not is_component_selectable(
        _reference(sequence_length=4, sequence_sha256=HASH, sequence=DNA),
        _admission(),
        rights,
        _resolved_sequence(),
        workflow_role="cds",
        workflow_scope="single_gene",
        evaluation_time=NOW,
    )


def _rights_with_expiry(valid_until):
    evidence = {}
    for dimension in ("runtime_resolution", "local_materialization"):
        base = _evidence(dimension)
        evidence[dimension] = RightsEvidence(
            **{
                key: getattr(base, key)
                for key, contract_field in RightsEvidence.__dataclass_fields__.items()
                if contract_field.init and key != "valid_until"
            },
            valid_until=valid_until,
        )
    return RightsState(
        rights_for_runtime_resolution=RightsDecision.ELIGIBLE,
        rights_for_local_materialization=RightsDecision.ELIGIBLE,
        evidence=evidence,
    )


def _clock_at(wall_time, calls=None):
    real_datetime = datetime

    class _ClockMeta(type):
        def __instancecheck__(cls, value):
            return isinstance(value, real_datetime)

    class _Clock(real_datetime, metaclass=_ClockMeta):
        @classmethod
        def now(cls, tz=None):
            if calls is not None:
                calls.append(wall_time)
            return wall_time if tz is None else wall_time.astimezone(tz)

    return _Clock


def test_rights_snapshot_reconstruction_does_not_re_evaluate_historical_expiry(monkeypatch):
    expires = datetime(2030, 2, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(
        direct_use_contracts,
        "datetime",
        _clock_at(datetime(2040, 1, 1, tzinfo=timezone.utc)),
    )

    rights = _rights_with_expiry(expires)

    assert rights.is_runtime_eligible(evaluation_time="2030-01-15T00:00:00Z")
    assert not rights.is_runtime_eligible(evaluation_time="2030-02-01T00:00:00Z")


@pytest.mark.parametrize("bounded_admission", (False, True))
def test_explicit_component_evaluation_time_is_independent_of_wall_clock(
    monkeypatch, bounded_admission
):
    evaluation_time = "2030-01-15T08:00:00+08:00"
    admission_bounds = (
        {"effective_at": "2030-01-01T00:00:00Z", "expires_at": "2030-02-01T00:00:00Z"}
        if bounded_admission
        else {}
    )
    monkeypatch.setattr(
        direct_use_contracts,
        "datetime",
        _clock_at(datetime(2029, 12, 1, tzinfo=timezone.utc)),
    )
    inputs = (
        _reference(sequence_length=4, sequence_sha256=HASH, sequence=DNA),
        _admission(**admission_bounds),
        _rights_with_expiry(datetime(2030, 2, 1, tzinfo=timezone.utc)),
        _resolved_sequence(),
    )

    results = []
    for wall_time in (
        datetime(2029, 12, 1, tzinfo=timezone.utc),
        datetime(2030, 3, 1, tzinfo=timezone.utc),
    ):
        monkeypatch.setattr(direct_use_contracts, "datetime", _clock_at(wall_time))
        results.append(is_component_selectable(
            *inputs,
            workflow_role="cds",
            workflow_scope="single_gene",
            evaluation_time=evaluation_time,
        ))

    assert results == [True, True]


def test_explicit_backbone_evaluation_time_is_independent_of_wall_clock(monkeypatch):
    evidence = _backbone_evidence()
    base_rights = evidence["rights_evidence"]
    evidence["rights_evidence"] = BackboneRightsEvidence(
        **{
            key: getattr(base_rights, key)
            for key, contract_field in BackboneRightsEvidence.__dataclass_fields__.items()
            if contract_field.init and key != "valid_until"
        },
        valid_until=datetime(2030, 2, 1, tzinfo=timezone.utc),
    )
    backbone = BackboneLifecycle(
        "bb", 1, BackboneState.SELECTABLE_BACKBONE, evidence["boundary_evidence"],
        evidence["resolution_evidence"], evidence["approval_binding"], evidence["rights_evidence"],
    )

    results = []
    for wall_time in (
        datetime(2029, 12, 1, tzinfo=timezone.utc),
        datetime(2030, 3, 1, tzinfo=timezone.utc),
    ):
        monkeypatch.setattr(direct_use_contracts, "datetime", _clock_at(wall_time))
        results.append(is_backbone_selectable(
            backbone,
            workflow_scope="single_gene",
            evaluation_time="2030-01-15T00:00:00Z",
        ))

    assert results == [True, True]


def test_component_default_evaluation_reads_wall_clock_only_once(monkeypatch):
    inputs = (
        _reference(sequence_length=4, sequence_sha256=HASH, sequence=DNA),
        _admission(),
        _rights(),
        _resolved_sequence(),
    )
    calls = []
    monkeypatch.setattr(
        direct_use_contracts,
        "datetime",
        _clock_at(datetime(2030, 1, 15, tzinfo=timezone.utc), calls),
    )

    assert is_component_selectable(
        *inputs, workflow_role="cds", workflow_scope="single_gene"
    )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "evaluation_kwargs",
    (
        {"evaluation_time": "not-a-timestamp"},
        {"evaluation_time": datetime(2030, 1, 15)},
        {"now_utc": "not-a-timestamp"},
        {"now_utc": datetime(2030, 1, 15)},
        {"evaluation_time": NOW, "now_utc": NOW},
    ),
)
def test_rights_runtime_evaluation_rejects_invalid_explicit_time(evaluation_kwargs):
    rights = _rights()
    assert not rights.is_runtime_eligible(**evaluation_kwargs)
    assert rights.operation_outcome(
        "runtime_resolution", **evaluation_kwargs
    ) is not RightsOutcome.RIGHTS_ELIGIBLE
