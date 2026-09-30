from __future__ import annotations

from dataclasses import fields, replace
import hashlib
import json
import math
from pathlib import Path

import pytest

from services.cas_offinder_adapter import (
    BULGE_POLICY,
    CAS_OFFINDER_CPU_MODE,
    CAS_OFFINDER_ENGINE,
    CAS_OFFINDER_VERSION,
    OPENCL_RUNTIME_REQUIRED,
    SPCAS9_PATTERN,
    CasOffinderExecutableIdentity,
    CasOffinderRequest,
    CasOffinderRunResult,
    OffTargetComputationStatus,
    build_cas_offinder_input,
    parse_cas_offinder_v241_output,
)
from services.crispr_reference_contract import (
    InstalledReferenceIdentity,
    ReferenceFastaFile,
)
from services.crispr_v1_contract import (
    COORDINATE_SYSTEM_ID,
    CrisprTargetSequence,
    SpCas9CandidateGuide,
)
from services.crispr_workflow_contract import (
    CoordinateOrigin,
    CrisprCandidateRecord,
    CrisprExecutionIntent,
    CrisprWorkflowContractError,
    CrisprWorkflowInput,
    CrisprWorkflowResult,
    TargetCoordinateOrigin,
    WORKFLOW_SCHEMA_NAME,
    WORKFLOW_SCHEMA_VERSION,
    WorkflowState,
    compute_workflow,
    enumerate_off_targets,
    from_json,
    select_candidate,
    to_dict,
    to_json,
)


SEQUENCE = "AAA" + "ACGT" * 5 + "TGG" + "AAA"


def _reference(tmp_path: Path, *, version: str = "TAIR10.1") -> InstalledReferenceIdentity:
    fasta_bytes = f">chr1\n{SEQUENCE}\n".encode()
    return InstalledReferenceIdentity.build(
        organism_scientific_name="Arabidopsis thaliana",
        taxonomy_id="3702",
        provider="fixture-provider",
        assembly_accession="GCF_000001735.4",
        assembly_version=version,
        fasta_directory=tmp_path / version,
        fasta_files=(
            ReferenceFastaFile(
                relative_path="assembly.fa",
                sha256=hashlib.sha256(fasta_bytes).hexdigest(),
                contigs=("chr1",),
            ),
        ),
        installation_provenance="workflow contract fixture",
    )


def _input(
    tmp_path: Path,
    *,
    sequence: str = SEQUENCE,
    offset: int | None = 100,
    maximum_mismatches: int = 4,
    reference: InstalledReferenceIdentity | None = None,
    scan_requested: bool = True,
    off_target_requested: bool = True,
    executable_path: str | None = "C:/fixture/cas-offinder.exe",
    expected_executable_sha256: str | None = None,
) -> CrisprWorkflowInput:
    target = CrisprTargetSequence.from_raw(
        sequence,
        target_id="target-1",
        display_name="Target 1",
        reference_pack_id="tair10-reference-pack-v1",
        contig="chr1",
    )
    return CrisprWorkflowInput.create(
        target=target,
        reference=reference or _reference(tmp_path),
        coordinate_origin=TargetCoordinateOrigin(
            origin=(
                CoordinateOrigin.TARGET_LOCAL
                if offset is None
                else CoordinateOrigin.REFERENCE_CONTIG
            ),
            contig="chr1",
            offset=offset,
        ),
        execution_intent=CrisprExecutionIntent(
            scan_requested=scan_requested,
            off_target_requested=off_target_requested,
            maximum_mismatches=maximum_mismatches,
            executable_path=executable_path,
            expected_executable_sha256=expected_executable_sha256,
        ),
    )


def _computed_adapter_result(request, *, status=OffTargetComputationStatus.COMPUTED):
    input_text, input_sha256 = build_cas_offinder_input(request)
    if status is OffTargetComputationStatus.COMPUTED:
        return CasOffinderRunResult(
            request=request,
            status=status,
            hits=(),
            input_text=input_text,
            input_sha256=input_sha256,
            output_text="",
            output_sha256=hashlib.sha256(b"").hexdigest(),
            executable=CasOffinderExecutableIdentity(
                resolved_path="C:/fixture/cas-offinder.exe",
                sha256="1" * 64,
                observed_banner="Cas-OFFinder v2.4.1 (fixture)",
            ),
            invocation=("C:/fixture/cas-offinder.exe", "input", "C", "output"),
            exit_code=0,
            stdout="",
            stderr="",
            error_code=None,
            error_message=None,
            temporary_paths_cleaned=True,
        )
    return CasOffinderRunResult(
        request=request,
        status=status,
        hits=(),
        input_text=input_text,
        input_sha256=input_sha256,
        output_text=None,
        output_sha256=None,
        executable=None,
        invocation=None,
        exit_code=None,
        stdout="",
        stderr="dependency diagnostic",
        error_code=status.value.upper(),
        error_message="fixture non-computed result",
        temporary_paths_cleaned=True,
    )


def _fixture_executable_identity() -> CasOffinderExecutableIdentity:
    return CasOffinderExecutableIdentity(
        resolved_path="C:/fixture/cas-offinder.exe",
        sha256="1" * 64,
        observed_banner="Cas-OFFinder v2.4.1 (fixture)",
    )


def _selected_result(tmp_path: Path):
    result = compute_workflow(_input(tmp_path))
    return select_candidate(result, result.scan.candidates[0].candidate_id)


def _authority_bound_result(
    tmp_path: Path,
) -> tuple[CrisprWorkflowResult, CasOffinderExecutableIdentity]:
    trusted_executable = _fixture_executable_identity()
    scanned = compute_workflow(
        _input(
            tmp_path,
            executable_path=trusted_executable.resolved_path,
            expected_executable_sha256=trusted_executable.sha256,
        )
    )
    selected = select_candidate(scanned, scanned.scan.candidates[0].candidate_id)
    return (
        enumerate_off_targets(selected, runner=_computed_adapter_result),
        trusted_executable,
    )


def _canonical_payload(payload: dict) -> str:
    return json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _trusted_executable(result) -> CasOffinderExecutableIdentity | None:
    assert result.off_target is not None
    return result.off_target.executable or _fixture_executable_identity()


def _rebind_forged_intent_payload(payload: dict, result, **updates) -> None:
    forged_intent = replace(result.workflow_input.execution_intent, **updates)
    forged_input = replace(result.workflow_input, execution_intent=forged_intent)
    payload["workflow_input"]["execution_intent"].update(updates)
    payload["workflow_id"] = forged_input.workflow_id
    payload["scan"]["freshness_hash"] = forged_input.freshness_hash
    if payload["selection"] is not None:
        payload["selection"]["workflow_id"] = forged_input.workflow_id
    if payload["off_target"] is not None:
        payload["off_target"]["freshness_hash"] = forged_input.freshness_hash


def _remove_observed_executable_projections(payload: dict, result) -> None:
    _rebind_forged_intent_payload(
        payload,
        result,
        executable_path=payload["workflow_input"]["execution_intent"]["executable_path"],
        expected_executable_sha256=payload["workflow_input"]["execution_intent"][
            "expected_executable_sha256"
        ],
        observed_executable_path=None,
        observed_executable_sha256=None,
        observed_engine_banner=None,
        observed_engine=None,
        observed_engine_version=None,
        observed_runtime_mode=None,
    )
    payload["off_target"] = None
    payload["off_target_state"] = WorkflowState.NOT_RUN.value
    payload["selection"]["candidate"]["off_target_state"] = WorkflowState.NOT_RUN.value
    payload["scan"]["candidates"][0]["off_target_state"] = WorkflowState.NOT_RUN.value


def test_schema_workflow_and_candidate_ids_are_deterministic(tmp_path: Path) -> None:
    first = compute_workflow(_input(tmp_path))
    second = compute_workflow(_input(tmp_path))

    assert first.workflow_input.schema_name == WORKFLOW_SCHEMA_NAME
    assert first.workflow_input.schema_version == WORKFLOW_SCHEMA_VERSION
    assert first.workflow_id == second.workflow_id
    assert [item.candidate_id for item in first.scan.candidates] == [
        item.candidate_id for item in second.scan.candidates
    ]


def test_input_exposes_exact_spcas9_reference_and_coordinate_contract(tmp_path: Path) -> None:
    workflow_input = _input(tmp_path)
    result = compute_workflow(workflow_input)
    candidate = result.scan.candidates[0]

    assert workflow_input.reference_binding.assembly_accession == "GCF_000001735.4"
    assert workflow_input.reference_binding.assembly_version == "TAIR10.1"
    assert workflow_input.configuration.nuclease_profile_id == "spcas9_ngg_20nt_v1"
    assert workflow_input.configuration.pam_pattern == "NGG"
    assert workflow_input.configuration.spacer_length == 20
    assert candidate.coordinate_convention == COORDINATE_SYSTEM_ID
    assert candidate.interval_semantics == "zero_based_half_open"
    assert workflow_input.coordinate_origin.interval_for(3, 23) == (103, 123)
    assert candidate.provenance.reference_identity_sha256 == workflow_input.reference_hash


def test_target_local_coordinates_do_not_claim_reference_coordinates(tmp_path: Path) -> None:
    workflow_input = _input(tmp_path, offset=None)

    assert workflow_input.coordinate_origin.interval_for(3, 23) is None
    with pytest.raises(CrisprWorkflowContractError, match="requires an explicit"):
        TargetCoordinateOrigin(
            origin=CoordinateOrigin.REFERENCE_CONTIG,
            contig="chr1",
            offset=None,
        )


def test_valid_selection_references_exact_candidate(tmp_path: Path) -> None:
    result = compute_workflow(_input(tmp_path))
    selected = select_candidate(result, result.scan.candidates[0].candidate_id)

    assert selected.selection is not None
    assert selected.selection.candidate == selected.scan.candidates[0]


def test_forged_candidate_id_is_rejected(tmp_path: Path) -> None:
    result = compute_workflow(_input(tmp_path))

    with pytest.raises(CrisprWorkflowContractError, match="absent"):
        select_candidate(result, "spcas9-guide-forged")


@pytest.mark.parametrize(
    "coordinate_update",
    (
        {"spacer_start": 1, "spacer_end": 1},
        {"pam_start": 1, "pam_end": 1},
    ),
)
def test_forged_candidate_coordinate_projection_is_rejected(
    tmp_path: Path, coordinate_update: dict[str, int]
) -> None:
    result = compute_workflow(_input(tmp_path))
    candidate = result.scan.candidates[0]

    with pytest.raises(CrisprWorkflowContractError, match="projection"):
        replace(
            candidate,
            **{
                field_name: getattr(candidate, field_name) + delta
                for field_name, delta in coordinate_update.items()
            },
        )


def test_forged_serialized_candidate_coordinate_projection_is_rejected(tmp_path: Path) -> None:
    payload = to_dict(compute_workflow(_input(tmp_path)))
    payload["scan"]["candidates"][0]["spacer_start"] += 1

    with pytest.raises(CrisprWorkflowContractError, match="projection"):
        from_json(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def test_forged_serialized_selection_coordinate_projection_is_rejected(tmp_path: Path) -> None:
    result = select_candidate(
        compute_workflow(_input(tmp_path)),
        compute_workflow(_input(tmp_path)).scan.candidates[0].candidate_id,
    )
    payload = to_dict(result)
    assert payload["selection"] is not None
    payload["selection"]["candidate"]["pam_start"] += 1

    with pytest.raises(CrisprWorkflowContractError, match="selection candidate"):
        from_json(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def test_cross_result_selection_is_rejected(tmp_path: Path) -> None:
    first = _selected_result(tmp_path)
    changed = compute_workflow(_input(tmp_path, maximum_mismatches=5))

    assert changed.scan.candidates[0].candidate_id == first.selection.candidate_id

    with pytest.raises(CrisprWorkflowContractError, match="another workflow"):
        replace(changed, selection=first.selection)


@pytest.mark.parametrize(
    "change",
    [
        "sequence",
        "mismatch",
        "reference",
        "executable",
        "executable_hash",
        "timeout",
    ],
)
def test_relevant_input_changes_make_previous_result_stale(tmp_path: Path, change: str) -> None:
    original_input = _input(tmp_path)
    result = compute_workflow(original_input)
    if change == "sequence":
        changed = _input(tmp_path, sequence="A" + SEQUENCE)
    elif change == "mismatch":
        changed = _input(tmp_path, maximum_mismatches=5)
    elif change in {"executable", "executable_hash", "timeout"}:
        changed = replace(
            original_input,
            execution_intent=replace(
                original_input.execution_intent,
                **(
                    {"executable_path": "C:/different/cas-offinder.exe"}
                    if change == "executable"
                    else (
                        {"expected_executable_sha256": "2" * 64}
                        if change == "executable_hash"
                        else {"timeout_seconds": 60.0}
                    )
                ),
            ),
        )
    else:
        changed = _input(tmp_path, reference=_reference(tmp_path, version="TAIR10.2"))

    assert not result.is_fresh_against(changed)
    assert original_input.freshness_hash != changed.freshness_hash
    with pytest.raises(CrisprWorkflowContractError, match="stale"):
        select_candidate(result, result.scan.candidates[0].candidate_id, current_input=changed)


def test_zero_candidate_scan_is_computed_not_failed(tmp_path: Path) -> None:
    result = compute_workflow(_input(tmp_path, sequence="A" * 30))

    assert result.scan.state is WorkflowState.COMPUTED
    assert result.scan.candidates == ()
    assert result.scan.scanner_output_sha256 is not None


def test_scan_not_run_is_explicit(tmp_path: Path) -> None:
    result = compute_workflow(_input(tmp_path, scan_requested=False))

    assert result.scan.state is WorkflowState.NOT_RUN
    assert from_json(
        to_json(result), trusted_executable=_fixture_executable_identity()
    ) == result


def test_scanner_failure_is_an_explicit_failed_state(tmp_path: Path) -> None:
    def broken_scanner(target, configuration):
        raise ValueError("fixture scanner failure")

    result = compute_workflow(_input(tmp_path), scanner=broken_scanner)

    assert result.scan.state is WorkflowState.FAILED
    assert result.scan.error_message == "fixture scanner failure"
    assert from_json(
        to_json(result), trusted_executable=_fixture_executable_identity()
    ) == result


def test_zero_off_target_hits_are_computed(tmp_path: Path) -> None:
    result = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)

    assert result.off_target_state is WorkflowState.COMPUTED
    assert result.off_target is not None
    assert result.off_target.hit_count == 0
    assert result.selection is not None
    assert result.selection.candidate.off_target_state is WorkflowState.COMPUTED


@pytest.mark.parametrize(
    ("adapter_status", "workflow_state"),
    [
        (OffTargetComputationStatus.NOT_COMPUTED, WorkflowState.NOT_RUN),
        (OffTargetComputationStatus.COMPUTED, WorkflowState.COMPUTED),
        (OffTargetComputationStatus.UNAVAILABLE, WorkflowState.UNAVAILABLE),
        (OffTargetComputationStatus.EXECUTION_FAILED, WorkflowState.FAILED),
        (OffTargetComputationStatus.PARSE_FAILED, WorkflowState.FAILED),
    ],
)
def test_serialized_adapter_state_matrix_accepts_only_valid_pairs(
    tmp_path: Path,
    adapter_status: OffTargetComputationStatus,
    workflow_state: WorkflowState,
) -> None:
    result = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=lambda request: _computed_adapter_result(request, status=adapter_status),
    )

    assert result.off_target is not None
    assert result.off_target.state is workflow_state
    assert from_json(
        to_json(result), trusted_executable=_trusted_executable(result)
    ) == result


@pytest.mark.parametrize(
    ("adapter_status", "forged_state"),
    [
        (OffTargetComputationStatus.NOT_COMPUTED, WorkflowState.COMPUTED),
        (OffTargetComputationStatus.COMPUTED, WorkflowState.FAILED),
        (OffTargetComputationStatus.UNAVAILABLE, WorkflowState.NOT_RUN),
        (OffTargetComputationStatus.EXECUTION_FAILED, WorkflowState.UNAVAILABLE),
        (OffTargetComputationStatus.PARSE_FAILED, WorkflowState.COMPUTED),
    ],
)
def test_serialized_adapter_state_matrix_rejects_contradictions(
    tmp_path: Path,
    adapter_status: OffTargetComputationStatus,
    forged_state: WorkflowState,
) -> None:
    result = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=lambda request: _computed_adapter_result(request, status=adapter_status),
    )
    payload = to_dict(result)
    assert payload["off_target"] is not None
    payload["off_target"]["state"] = forged_state.value

    with pytest.raises(CrisprWorkflowContractError, match="incompatible"):
        from_json(
            json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            trusted_executable=_trusted_executable(result),
        )


def test_reselection_clears_prior_off_target_state(tmp_path: Path) -> None:
    computed = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=_computed_adapter_result,
    )
    assert computed.off_target_state is WorkflowState.COMPUTED

    reset = select_candidate(computed, computed.selection.candidate_id)

    assert reset.off_target is None
    assert reset.off_target_state is WorkflowState.NOT_RUN
    assert reset.selection is not None
    assert reset.selection.candidate.off_target_state is WorkflowState.NOT_RUN


@pytest.mark.parametrize(
    ("adapter_status", "workflow_state"),
    [
        (OffTargetComputationStatus.NOT_COMPUTED, WorkflowState.NOT_RUN),
        (OffTargetComputationStatus.UNAVAILABLE, WorkflowState.UNAVAILABLE),
        (OffTargetComputationStatus.EXECUTION_FAILED, WorkflowState.FAILED),
        (OffTargetComputationStatus.PARSE_FAILED, WorkflowState.FAILED),
    ],
)
def test_noncomputed_off_target_states_are_preserved(
    tmp_path: Path,
    adapter_status: OffTargetComputationStatus,
    workflow_state: WorkflowState,
) -> None:
    result = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=lambda request: _computed_adapter_result(request, status=adapter_status),
    )

    assert result.off_target_state is workflow_state
    assert result.off_target is not None
    assert result.off_target.adapter_status is adapter_status
    assert result.off_target.hit_count is None
    assert from_json(
        to_json(result), trusted_executable=_trusted_executable(result)
    ) == result


def test_adapter_filesystem_error_becomes_explicit_failed_state(tmp_path: Path) -> None:
    def blocked_runner(request):
        raise PermissionError("fixture temporary directory denied")

    result = enumerate_off_targets(_selected_result(tmp_path), runner=blocked_runner)

    assert result.off_target_state is WorkflowState.FAILED
    assert result.off_target is not None
    assert result.off_target.adapter_status is OffTargetComputationStatus.EXECUTION_FAILED
    assert result.off_target.error_code == "ORCHESTRATION_IO_FAILED"


def test_runner_cannot_return_cross_reference_request(tmp_path: Path) -> None:
    selected = _selected_result(tmp_path)

    def stale_runner(request):
        stale_request = replace(request, maximum_mismatches=request.maximum_mismatches + 1)
        return _computed_adapter_result(stale_request)

    with pytest.raises(CrisprWorkflowContractError, match="stale request"):
        enumerate_off_targets(selected, runner=stale_runner)


def test_runner_executable_identity_must_match_configured_freshness(tmp_path: Path) -> None:
    workflow_input = replace(
        _input(tmp_path),
        execution_intent=replace(
            _input(tmp_path).execution_intent,
            expected_executable_sha256="2" * 64,
        ),
    )
    computed = compute_workflow(workflow_input)
    selected = select_candidate(computed, computed.scan.candidates[0].candidate_id)

    with pytest.raises(CrisprWorkflowContractError, match="executable identity"):
        enumerate_off_targets(selected, runner=_computed_adapter_result)


def test_computed_result_dependency_freshness_checks_current_executable(tmp_path: Path) -> None:
    result = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=_computed_adapter_result,
    )

    assert result.is_off_target_fresh_against(
        result.workflow_input,
        executable_sha256="1" * 64,
    )
    assert not result.is_off_target_fresh_against(
        result.workflow_input,
        executable_sha256="2" * 64,
    )


@pytest.mark.parametrize("non_finite", (math.nan, math.inf, -math.inf))
def test_execution_timeout_rejects_non_finite_numbers(non_finite: float) -> None:
    with pytest.raises(CrisprWorkflowContractError, match="finite"):
        CrisprExecutionIntent(timeout_seconds=non_finite)


def test_canonical_json_disallows_non_finite_numbers(tmp_path: Path) -> None:
    result = compute_workflow(_input(tmp_path))
    forged = object.__new__(CrisprExecutionIntent)
    object.__setattr__(forged, "scan_requested", True)
    object.__setattr__(forged, "off_target_requested", True)
    object.__setattr__(forged, "maximum_mismatches", 4)
    object.__setattr__(forged, "timeout_seconds", math.nan)
    object.__setattr__(forged, "executable_path", None)
    object.__setattr__(forged, "expected_executable_sha256", None)
    object.__setattr__(forged, "observed_executable_path", None)
    object.__setattr__(forged, "observed_executable_sha256", None)
    object.__setattr__(forged, "observed_engine_banner", None)
    object.__setattr__(forged, "observed_engine", None)
    object.__setattr__(forged, "observed_engine_version", None)
    object.__setattr__(forged, "observed_runtime_mode", None)
    object.__setattr__(result.workflow_input, "execution_intent", forged)

    with pytest.raises(ValueError, match="Out of range"):
        to_json(result)


def test_observed_executable_identity_is_bound_to_freshness(tmp_path: Path) -> None:
    first = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)
    second = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)

    assert first.workflow_input.freshness_hash == second.workflow_input.freshness_hash
    assert first.workflow_input.execution_intent.observed_executable_sha256 == "1" * 64

    def changed_identity(request):
        result = _computed_adapter_result(request)
        return replace(
            result,
            executable=replace(result.executable, sha256="2" * 64),
        )

    changed = enumerate_off_targets(_selected_result(tmp_path), runner=changed_identity)
    assert changed.workflow_input.freshness_hash != first.workflow_input.freshness_hash
    assert not first.is_fresh_against(changed.workflow_input)


def test_runtime_executable_path_is_bound_without_invocation_noise(tmp_path: Path) -> None:
    selected = _selected_result(tmp_path)
    first = enumerate_off_targets(
        selected,
        runner=_computed_adapter_result,
        executable_path="C:/runtime/cas-offinder-a.exe",
    )
    second = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=_computed_adapter_result,
        executable_path="C:/runtime/cas-offinder-b.exe",
    )

    assert first.workflow_input.freshness_hash != second.workflow_input.freshness_hash
    assert first.workflow_input.execution_intent.observed_executable_sha256 == (
        second.workflow_input.execution_intent.observed_executable_sha256
    )


def test_canonical_json_ignores_temporary_invocation_paths_and_timing_stderr(
    tmp_path: Path,
) -> None:
    selected = _selected_result(tmp_path)

    def runner_with_diagnostics(request, input_path: str, output_path: str, stderr: str):
        base = _computed_adapter_result(request)
        return replace(
            base,
            invocation=(base.invocation[0], input_path, "C", output_path),
            stdout=f"run at {input_path}",
            stderr=stderr,
        )

    first = enumerate_off_targets(
        selected,
        runner=lambda request: runner_with_diagnostics(
            request,
            "C:/temp/run-a/input.txt",
            "C:/temp/run-a/output.txt",
            "elapsed=0.101s",
        ),
    )
    second = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=lambda request: runner_with_diagnostics(
            request,
            "D:/other/run-b/input.txt",
            "D:/other/run-b/output.txt",
            "elapsed=0.202s",
        ),
    )

    assert first.off_target.result_sha256 == second.off_target.result_sha256
    assert to_json(first) == to_json(second)
    payload = json.loads(to_json(first))
    assert payload["off_target"]["invocation"] == [
        "C:/fixture/cas-offinder.exe",
        "<temporary-path>",
        "C",
        "<temporary-path>",
    ]
    assert payload["off_target"]["stdout"] == ""
    assert payload["off_target"]["stderr"] == ""


def test_canonical_json_remains_sensitive_to_normalized_result_identity(
    tmp_path: Path,
) -> None:
    zero_hit = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=_computed_adapter_result,
    )

    def one_hit_runner(request):
        input_text, input_sha256 = build_cas_offinder_input(request)
        output_text = f"{request.query}\tchr1\t3\t{request.spacer}TGG\t+\t0\n"
        hits = parse_cas_offinder_v241_output(
            output_text,
            request,
            executable_sha256="1" * 64,
            input_sha256=input_sha256,
        )
        base = _computed_adapter_result(request)
        return replace(
            base,
            hits=hits,
            output_text=output_text,
            output_sha256=hashlib.sha256(output_text.encode()).hexdigest(),
        )

    one_hit = enumerate_off_targets(_selected_result(tmp_path), runner=one_hit_runner)

    assert zero_hit.off_target.result_sha256 != one_hit.off_target.result_sha256
    assert to_json(zero_hit) != to_json(one_hit)


def test_canonical_json_preserves_executable_reference_and_parameter_identity(
    tmp_path: Path,
) -> None:
    baseline = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=_computed_adapter_result,
    )

    def changed_executable(request):
        base = _computed_adapter_result(request)
        return replace(base, executable=replace(base.executable, sha256="2" * 64))

    executable_changed = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=changed_executable,
    )
    reference_input = _input(
        tmp_path,
        reference=_reference(tmp_path, version="TAIR10.2"),
    )
    reference_scan = compute_workflow(reference_input)
    reference_changed = enumerate_off_targets(
        select_candidate(reference_scan, reference_scan.scan.candidates[0].candidate_id),
        runner=_computed_adapter_result,
    )
    parameter_input = _input(tmp_path, maximum_mismatches=2)
    parameter_scan = compute_workflow(parameter_input)
    parameter_changed = enumerate_off_targets(
        select_candidate(parameter_scan, parameter_scan.scan.candidates[0].candidate_id),
        runner=_computed_adapter_result,
    )

    assert to_json(baseline) != to_json(executable_changed)
    assert to_json(baseline) != to_json(reference_changed)
    assert to_json(baseline) != to_json(parameter_changed)


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("maximum_mismatches", 9),
        ("guide_id", "spcas9-guide-forged"),
        ("spacer", "T" * 20),
        ("reference_identity_sha256", "2" * 64),
        ("engine", "forged-engine"),
        ("engine_version", "9.9.9"),
        ("cpu_mode", "G0"),
        ("opencl_runtime_required", False),
        ("pattern", "N" * 23),
        ("bulge_policy", "included"),
        ("timeout_seconds", 9.0),
    ],
)
def test_serialized_off_target_request_must_match_authoritative_workflow(
    tmp_path: Path,
    field_name: str,
    forged_value,
) -> None:
    result = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)
    payload = to_dict(result)
    request_payload = payload["off_target"]["request"]
    request_payload[field_name] = forged_value

    if field_name in {"maximum_mismatches", "guide_id", "spacer"}:
        forged_request = CasOffinderRequest(
            guide_id=request_payload["guide_id"],
            spacer=request_payload["spacer"],
            maximum_mismatches=request_payload["maximum_mismatches"],
            reference=result.workflow_input.reference_binding.reference,
        )
        request_payload["parameter_identity_sha256"] = (
            forged_request.parameter_identity_sha256
        )
        payload["off_target"]["input_sha256"] = build_cas_offinder_input(
            forged_request
        )[1]

    with pytest.raises(CrisprWorkflowContractError, match="authoritative workflow input"):
        from_json(
            _canonical_payload(payload),
            trusted_executable=_trusted_executable(result),
        )


def test_serialized_off_target_request_projection_is_complete_and_round_trips(
    tmp_path: Path,
) -> None:
    result = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)
    request_payload = to_dict(result)["off_target"]["request"]

    assert request_payload == {
        "guide_id": result.selection.candidate_id,
        "spacer": result.selection.candidate.guide_sequence,
        "maximum_mismatches": result.workflow_input.execution_intent.maximum_mismatches,
        "reference_identity_sha256": result.workflow_input.reference_hash,
        "parameter_identity_sha256": result.off_target.request.parameter_identity_sha256,
        "engine": CAS_OFFINDER_ENGINE,
        "engine_version": CAS_OFFINDER_VERSION,
        "cpu_mode": CAS_OFFINDER_CPU_MODE,
        "opencl_runtime_required": OPENCL_RUNTIME_REQUIRED,
        "pattern": SPCAS9_PATTERN,
        "bulge_policy": BULGE_POLICY,
        "timeout_seconds": result.workflow_input.execution_intent.timeout_seconds,
    }
    assert from_json(
        to_json(result), trusted_executable=_trusted_executable(result)
    ) == result


@pytest.mark.parametrize(
    ("field_name", "forged_value"),
    [
        ("observed_executable_path", "C:/forged/cas-offinder.exe"),
        ("observed_executable_sha256", "2" * 64),
        ("observed_engine_banner", "Cas-OFFinder v2.4.1 (forged)"),
        ("observed_engine", "forged-engine"),
        ("observed_engine_version", "9.9.9"),
        ("observed_runtime_mode", "G0"),
    ],
)
def test_serialized_observed_execution_identity_must_match_adapter_evidence(
    tmp_path: Path,
    field_name: str,
    forged_value: str,
) -> None:
    result = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)
    payload = to_dict(result)
    _rebind_forged_intent_payload(payload, result, **{field_name: forged_value})

    with pytest.raises(CrisprWorkflowContractError, match="adapter evidence"):
        from_json(
            _canonical_payload(payload),
            trusted_executable=_trusted_executable(result),
        )


def test_serialized_executable_evidence_identity_round_trips(tmp_path: Path) -> None:
    result = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)
    restored = from_json(
        to_json(result), trusted_executable=_trusted_executable(result)
    )

    assert restored.off_target.executable == result.off_target.executable
    assert restored.workflow_input.execution_intent.observed_engine == CAS_OFFINDER_ENGINE
    assert restored.workflow_input.execution_intent.observed_runtime_mode == CAS_OFFINDER_CPU_MODE


def test_expected_executable_sha256_is_checked_against_trusted_authority(
    tmp_path: Path,
) -> None:
    result, trusted_executable = _authority_bound_result(tmp_path)
    payload = to_dict(result)
    _rebind_forged_intent_payload(
        payload,
        result,
        expected_executable_sha256="2" * 64,
    )

    with pytest.raises(CrisprWorkflowContractError, match="expected executable SHA-256"):
        from_json(
            _canonical_payload(payload),
            trusted_executable=trusted_executable,
        )


def test_nullable_expected_sha_cannot_downgrade_executable_authority(
    tmp_path: Path,
) -> None:
    result, trusted_executable = _authority_bound_result(tmp_path)
    payload = to_dict(result)
    _rebind_forged_intent_payload(
        payload,
        result,
        expected_executable_sha256=None,
    )
    serialized = _canonical_payload(payload)

    restored = from_json(serialized, trusted_executable=trusted_executable)
    assert restored.workflow_input.execution_intent.expected_executable_sha256 is None
    with pytest.raises(CrisprWorkflowContractError, match="authority is required"):
        from_json(serialized)


@pytest.mark.parametrize("configured_path", (None, "C:/forged/cas-offinder.exe"))
def test_nullable_or_mutated_configured_path_cannot_downgrade_authority(
    tmp_path: Path,
    configured_path: str | None,
) -> None:
    result, trusted_executable = _authority_bound_result(tmp_path)
    payload = to_dict(result)
    _rebind_forged_intent_payload(
        payload,
        result,
        executable_path=configured_path,
    )
    serialized = _canonical_payload(payload)

    if configured_path is None:
        restored = from_json(
            serialized,
            trusted_executable=trusted_executable,
        )
        assert restored.workflow_input.execution_intent.executable_path is None
    else:
        with pytest.raises(CrisprWorkflowContractError, match="configured executable path"):
            from_json(serialized, trusted_executable=trusted_executable)
    with pytest.raises(CrisprWorkflowContractError, match="authority is required"):
        from_json(serialized)


def test_path_and_expected_sha_may_be_absent_when_observed_identity_remains(
    tmp_path: Path,
) -> None:
    result, trusted_executable = _authority_bound_result(tmp_path)
    payload = to_dict(result)
    _rebind_forged_intent_payload(
        payload,
        result,
        executable_path=None,
        expected_executable_sha256=None,
    )

    restored = from_json(
        _canonical_payload(payload),
        trusted_executable=trusted_executable,
    )

    assert restored.workflow_input.execution_intent.executable_path is None
    assert restored.workflow_input.execution_intent.expected_executable_sha256 is None
    assert restored.off_target is not None
    assert restored.off_target.executable == trusted_executable


@pytest.mark.parametrize(
    "removed_field",
    ("executable_path", "expected_executable_sha256"),
)
def test_no_observed_evidence_keeps_remaining_configured_identity_binding(
    tmp_path: Path,
    removed_field: str,
) -> None:
    result, trusted_executable = _authority_bound_result(tmp_path)
    payload = to_dict(result)
    _rebind_forged_intent_payload(
        payload,
        result,
        **{removed_field: None},
    )
    _remove_observed_executable_projections(payload, result)
    serialized = _canonical_payload(payload)

    restored = from_json(
        serialized,
        trusted_executable=trusted_executable,
    )

    assert restored.off_target is None
    assert getattr(restored.workflow_input.execution_intent, removed_field) is None
    with pytest.raises(CrisprWorkflowContractError, match="authority is required"):
        from_json(serialized)


def test_mutated_path_with_expected_sha_removed_is_rejected(
    tmp_path: Path,
) -> None:
    result, trusted_executable = _authority_bound_result(tmp_path)
    payload = to_dict(result)
    _rebind_forged_intent_payload(
        payload,
        result,
        executable_path="C:/forged/cas-offinder.exe",
        expected_executable_sha256=None,
    )

    with pytest.raises(CrisprWorkflowContractError, match="configured executable path"):
        from_json(
            _canonical_payload(payload),
            trusted_executable=trusted_executable,
        )


@pytest.mark.parametrize(
    "trusted_mode",
    ("absent", "matching", "mismatching"),
)
def test_removing_all_executable_projections_never_suppresses_semantic_gate(
    tmp_path: Path,
    trusted_mode: str,
) -> None:
    result, trusted_executable = _authority_bound_result(tmp_path)
    payload = to_dict(result)
    _rebind_forged_intent_payload(
        payload,
        result,
        executable_path=None,
        expected_executable_sha256=None,
    )
    _remove_observed_executable_projections(payload, result)
    authority = {
        "absent": None,
        "matching": trusted_executable,
        "mismatching": CasOffinderExecutableIdentity(
            resolved_path="C:/other/cas-offinder.exe",
            sha256="2" * 64,
            observed_banner="Cas-OFFinder v2.4.1 (other)",
        ),
    }[trusted_mode]
    expected_error = (
        "authority is required"
        if authority is None
        else "requires an executable identity binding"
    )

    with pytest.raises(CrisprWorkflowContractError, match=expected_error):
        from_json(
            _canonical_payload(payload),
            trusted_executable=authority,
        )


@pytest.mark.parametrize(
    "adapter_status",
    (
        OffTargetComputationStatus.NOT_COMPUTED,
        OffTargetComputationStatus.UNAVAILABLE,
        OffTargetComputationStatus.EXECUTION_FAILED,
        OffTargetComputationStatus.PARSE_FAILED,
    ),
)
def test_execution_configured_without_observed_evidence_still_requires_authority(
    tmp_path: Path,
    adapter_status: OffTargetComputationStatus,
) -> None:
    result = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=lambda request: _computed_adapter_result(request, status=adapter_status),
    )
    serialized = to_json(result)

    assert result.off_target is not None
    assert result.off_target.executable is None
    assert from_json(
        serialized,
        trusted_executable=_fixture_executable_identity(),
    ) == result
    with pytest.raises(CrisprWorkflowContractError, match="authority is required"):
        from_json(serialized)


def test_not_run_execution_configuration_still_requires_authority(tmp_path: Path) -> None:
    result = _selected_result(tmp_path)

    assert result.off_target is None
    assert result.off_target_state is WorkflowState.NOT_RUN
    with pytest.raises(CrisprWorkflowContractError, match="authority is required"):
        from_json(to_json(result))
    assert from_json(
        to_json(result),
        trusted_executable=_fixture_executable_identity(),
    ) == result


def test_genuinely_non_executable_workflow_does_not_require_authority(
    tmp_path: Path,
) -> None:
    scanned = compute_workflow(
        _input(
            tmp_path,
            off_target_requested=False,
            executable_path=None,
            expected_executable_sha256=None,
        )
    )
    result = select_candidate(scanned, scanned.scan.candidates[0].candidate_id)

    assert from_json(to_json(result)) == result


@pytest.mark.parametrize(
    "intent_updates",
    [
        {"executable_path": "C:/fixture/cas-offinder.exe"},
        {"expected_executable_sha256": "1" * 64},
        {
            "observed_executable_path": "C:/fixture/cas-offinder.exe",
            "observed_executable_sha256": "1" * 64,
            "observed_engine_banner": "Cas-OFFinder v2.4.1 (fixture)",
            "observed_engine": CAS_OFFINDER_ENGINE,
            "observed_engine_version": CAS_OFFINDER_VERSION,
            "observed_runtime_mode": CAS_OFFINDER_CPU_MODE,
        },
    ],
    ids=("configured-path", "expected-identity", "observed-identity"),
)
def test_false_off_target_semantic_consistency_rejects_executable_intent(
    tmp_path: Path,
    intent_updates: dict[str, str],
) -> None:
    result = compute_workflow(
        _input(
            tmp_path,
            off_target_requested=False,
            executable_path=None,
            expected_executable_sha256=None,
        )
    )
    payload = to_dict(result)
    _rebind_forged_intent_payload(payload, result, **intent_updates)

    with pytest.raises(CrisprWorkflowContractError, match="semantic consistency"):
        from_json(_canonical_payload(payload))


@pytest.mark.parametrize(
    "adapter_status",
    (
        OffTargetComputationStatus.NOT_COMPUTED,
        OffTargetComputationStatus.COMPUTED,
        OffTargetComputationStatus.UNAVAILABLE,
        OffTargetComputationStatus.EXECUTION_FAILED,
        OffTargetComputationStatus.PARSE_FAILED,
    ),
)
def test_false_off_target_semantic_consistency_rejects_adapter_state(
    tmp_path: Path,
    adapter_status: OffTargetComputationStatus,
) -> None:
    result = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=lambda request: _computed_adapter_result(request, status=adapter_status),
    )
    payload = to_dict(result)
    _rebind_forged_intent_payload(
        payload,
        result,
        off_target_requested=False,
        executable_path=None,
        expected_executable_sha256=None,
        observed_executable_path=None,
        observed_executable_sha256=None,
        observed_engine_banner=None,
        observed_engine=None,
        observed_engine_version=None,
        observed_runtime_mode=None,
    )

    with pytest.raises(CrisprWorkflowContractError, match="semantic consistency"):
        from_json(
            _canonical_payload(payload),
            trusted_executable=_fixture_executable_identity(),
        )


def test_false_off_target_semantic_consistency_rejects_retained_invocation(
    tmp_path: Path,
) -> None:
    result = enumerate_off_targets(
        _selected_result(tmp_path),
        runner=lambda request: _computed_adapter_result(
            request, status=OffTargetComputationStatus.NOT_COMPUTED
        ),
    )
    payload = to_dict(result)
    _rebind_forged_intent_payload(
        payload,
        result,
        off_target_requested=False,
        executable_path=None,
        expected_executable_sha256=None,
    )
    payload["off_target"]["invocation"] = [
        "C:/fixture/cas-offinder.exe",
        "input",
        "C",
        "output",
    ]

    with pytest.raises(CrisprWorkflowContractError, match="semantic consistency"):
        from_json(_canonical_payload(payload))


def test_false_off_target_semantic_consistency_rejects_candidate_state(
    tmp_path: Path,
) -> None:
    scanned = compute_workflow(
        _input(
            tmp_path,
            off_target_requested=False,
            executable_path=None,
            expected_executable_sha256=None,
        )
    )
    result = select_candidate(scanned, scanned.scan.candidates[0].candidate_id)
    payload = to_dict(result)
    payload["scan"]["candidates"][0]["off_target_state"] = WorkflowState.COMPUTED.value
    payload["selection"]["candidate"]["off_target_state"] = WorkflowState.COMPUTED.value

    with pytest.raises(CrisprWorkflowContractError, match="semantic consistency"):
        from_json(_canonical_payload(payload))


def test_false_off_target_semantic_consistency_rejects_executable_freshness(
    tmp_path: Path,
) -> None:
    result = _selected_result(tmp_path)
    payload = to_dict(result)
    forged_input = replace(
        result.workflow_input,
        execution_intent=replace(
            result.workflow_input.execution_intent,
            off_target_requested=False,
            executable_path=None,
            expected_executable_sha256=None,
        ),
    )
    payload["workflow_input"]["execution_intent"].update(
        {
            "off_target_requested": False,
            "executable_path": None,
            "expected_executable_sha256": None,
        }
    )
    payload["workflow_id"] = forged_input.workflow_id
    payload["selection"]["workflow_id"] = forged_input.workflow_id

    with pytest.raises(CrisprWorkflowContractError, match="scan freshness"):
        from_json(_canonical_payload(payload))


def test_false_off_target_semantic_consistency_accepts_fully_removed_projections(
    tmp_path: Path,
) -> None:
    result, _ = _authority_bound_result(tmp_path)
    payload = to_dict(result)
    _rebind_forged_intent_payload(
        payload,
        result,
        off_target_requested=False,
        executable_path=None,
        expected_executable_sha256=None,
        observed_executable_path=None,
        observed_executable_sha256=None,
        observed_engine_banner=None,
        observed_engine=None,
        observed_engine_version=None,
        observed_runtime_mode=None,
    )
    payload["off_target"] = None
    payload["off_target_state"] = WorkflowState.NOT_RUN.value
    for candidate in payload["scan"]["candidates"]:
        candidate["off_target_state"] = WorkflowState.NOT_RUN.value
    payload["selection"]["candidate"]["off_target_state"] = WorkflowState.NOT_RUN.value

    restored = from_json(_canonical_payload(payload))

    assert restored.workflow_input.execution_intent.off_target_requested is False
    assert restored.off_target is None
    assert restored.selection is not None


def test_non_executable_intent_cannot_carry_off_target_result(tmp_path: Path) -> None:
    result, _ = _authority_bound_result(tmp_path)
    forged_input = replace(
        result.workflow_input,
        execution_intent=replace(
            result.workflow_input.execution_intent,
            off_target_requested=False,
        ),
    )

    with pytest.raises(CrisprWorkflowContractError, match="semantic consistency"):
        replace(
            result,
            workflow_input=forged_input,
            workflow_id=forged_input.workflow_id,
            scan=replace(result.scan, freshness_hash=forged_input.freshness_hash),
            selection=replace(result.selection, workflow_id=forged_input.workflow_id),
            off_target=replace(result.off_target, freshness_hash=forged_input.freshness_hash),
        )


def test_executable_verification_fails_closed_without_trusted_authority(
    tmp_path: Path,
) -> None:
    result, _ = _authority_bound_result(tmp_path)

    with pytest.raises(CrisprWorkflowContractError, match="authority is required"):
        from_json(to_json(result))


def test_matching_trusted_executable_authority_allows_computed_zero_hit_round_trip(
    tmp_path: Path,
) -> None:
    result, trusted_executable = _authority_bound_result(tmp_path)

    restored = from_json(
        to_json(result),
        trusted_executable=trusted_executable,
    )

    assert restored == result
    assert restored.off_target is not None
    assert restored.off_target.state is WorkflowState.COMPUTED
    assert restored.off_target.hit_count == 0


def test_mismatching_trusted_authority_rejects_unchanged_payload(tmp_path: Path) -> None:
    result, _ = _authority_bound_result(tmp_path)
    mismatching_authority = CasOffinderExecutableIdentity(
        resolved_path="C:/other/cas-offinder.exe",
        sha256="2" * 64,
        observed_banner="Cas-OFFinder v2.4.1 (other)",
    )

    with pytest.raises(CrisprWorkflowContractError, match="trusted executable authority"):
        from_json(
            to_json(result),
            trusted_executable=mismatching_authority,
        )


def test_fully_colluding_serialized_forgery_cannot_replace_external_authority(
    tmp_path: Path,
) -> None:
    result, trusted_executable = _authority_bound_result(tmp_path)
    payload = to_dict(result)
    forged_executable = CasOffinderExecutableIdentity(
        resolved_path="C:/forged/cas-offinder.exe",
        sha256="2" * 64,
        observed_banner="Cas-OFFinder v2.4.1 (forged)",
    )
    _rebind_forged_intent_payload(
        payload,
        result,
        executable_path=forged_executable.resolved_path,
        expected_executable_sha256=forged_executable.sha256,
        observed_executable_path=forged_executable.resolved_path,
        observed_executable_sha256=forged_executable.sha256,
        observed_engine_banner=forged_executable.observed_banner,
        observed_engine=CAS_OFFINDER_ENGINE,
        observed_engine_version=CAS_OFFINDER_VERSION,
        observed_runtime_mode=CAS_OFFINDER_CPU_MODE,
    )
    payload["off_target"]["executable"] = {
        "resolved_path": forged_executable.resolved_path,
        "sha256": forged_executable.sha256,
        "observed_banner": forged_executable.observed_banner,
    }
    payload["off_target"]["invocation"][0] = forged_executable.resolved_path

    with pytest.raises(CrisprWorkflowContractError, match="trusted executable authority"):
        from_json(
            _canonical_payload(payload),
            trusted_executable=trusted_executable,
        )


@pytest.mark.parametrize("trusted_mode", ("absent", "unchanged", "mismatching"))
def test_all_replaced_executable_projections_remain_externally_authorized(
    tmp_path: Path,
    trusted_mode: str,
) -> None:
    result, trusted_executable = _authority_bound_result(tmp_path)
    forged_executable = CasOffinderExecutableIdentity(
        resolved_path="C:/forged/cas-offinder.exe",
        sha256="2" * 64,
        observed_banner="Cas-OFFinder v2.4.1 (forged)",
    )
    payload = to_dict(result)
    _rebind_forged_intent_payload(
        payload,
        result,
        executable_path=forged_executable.resolved_path,
        expected_executable_sha256=forged_executable.sha256,
        observed_executable_path=forged_executable.resolved_path,
        observed_executable_sha256=forged_executable.sha256,
        observed_engine_banner=forged_executable.observed_banner,
        observed_engine=CAS_OFFINDER_ENGINE,
        observed_engine_version=CAS_OFFINDER_VERSION,
        observed_runtime_mode=CAS_OFFINDER_CPU_MODE,
    )
    payload["off_target"]["executable"] = {
        "resolved_path": forged_executable.resolved_path,
        "sha256": forged_executable.sha256,
        "observed_banner": forged_executable.observed_banner,
    }
    payload["off_target"]["invocation"][0] = forged_executable.resolved_path
    authority = {
        "absent": None,
        "unchanged": trusted_executable,
        "mismatching": CasOffinderExecutableIdentity(
            resolved_path="C:/other/cas-offinder.exe",
            sha256="3" * 64,
            observed_banner="Cas-OFFinder v2.4.1 (other)",
        ),
    }[trusted_mode]
    expected_error = (
        "authority is required"
        if authority is None
        else "expected executable SHA-256"
    )

    with pytest.raises(CrisprWorkflowContractError, match=expected_error):
        from_json(
            _canonical_payload(payload),
            trusted_executable=authority,
        )


def test_forged_payload_with_mismatching_trusted_authority_is_rejected(
    tmp_path: Path,
) -> None:
    result, _ = _authority_bound_result(tmp_path)
    payload = to_dict(result)
    forged_path = "C:/forged/cas-offinder.exe"
    _rebind_forged_intent_payload(
        payload,
        result,
        executable_path=forged_path,
        observed_executable_path=forged_path,
    )
    payload["off_target"]["executable"]["resolved_path"] = forged_path
    payload["off_target"]["invocation"][0] = forged_path
    mismatching_authority = CasOffinderExecutableIdentity(
        resolved_path="C:/other/cas-offinder.exe",
        sha256="3" * 64,
        observed_banner="Cas-OFFinder v2.4.1 (other)",
    )

    with pytest.raises(CrisprWorkflowContractError, match="trusted executable authority"):
        from_json(
            _canonical_payload(payload),
            trusted_executable=mismatching_authority,
        )


def test_serialized_executable_path_must_match_invocation_evidence(tmp_path: Path) -> None:
    result = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)
    payload = to_dict(result)
    forged_path = "C:/forged/cas-offinder.exe"
    _rebind_forged_intent_payload(
        payload,
        result,
        observed_executable_path=forged_path,
    )
    payload["off_target"]["executable"]["resolved_path"] = forged_path

    with pytest.raises(CrisprWorkflowContractError, match="adapter evidence"):
        from_json(
            _canonical_payload(payload),
            trusted_executable=_trusted_executable(result),
        )


def test_serialized_invocation_executable_path_must_match_trusted_authority(
    tmp_path: Path,
) -> None:
    result, trusted_executable = _authority_bound_result(tmp_path)
    payload = to_dict(result)
    payload["off_target"]["invocation"][0] = "C:/forged/cas-offinder.exe"

    with pytest.raises(CrisprWorkflowContractError, match="adapter evidence"):
        from_json(
            _canonical_payload(payload),
            trusted_executable=trusted_executable,
        )


def test_serialized_runtime_mode_cannot_be_coforged_with_invocation(tmp_path: Path) -> None:
    result = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)
    payload = to_dict(result)
    _rebind_forged_intent_payload(payload, result, observed_runtime_mode="G0")
    payload["off_target"]["invocation"][2] = "G0"

    with pytest.raises(CrisprWorkflowContractError, match="adapter evidence"):
        from_json(
            _canonical_payload(payload),
            trusted_executable=_trusted_executable(result),
        )


def test_serialized_observed_identity_without_adapter_evidence_is_rejected(
    tmp_path: Path,
) -> None:
    result = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)
    payload = to_dict(result)
    payload["off_target"]["executable"] = None

    with pytest.raises(CrisprWorkflowContractError, match="executable or raw output evidence"):
        from_json(_canonical_payload(payload))


def test_serialization_round_trip_is_deterministic(tmp_path: Path) -> None:
    result = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)
    serialized = to_json(result)
    restored = from_json(
        serialized, trusted_executable=_trusted_executable(result)
    )

    assert restored == result
    assert to_json(restored) == serialized
    assert to_dict(restored)["off_target"]["hit_count"] == 0


def test_serialization_round_trip_preserves_normalized_hits(tmp_path: Path) -> None:
    selected = _selected_result(tmp_path)

    def one_hit_runner(request):
        input_text, input_sha256 = build_cas_offinder_input(request)
        output_text = (
            f"{request.query}\tchr1\t3\t{request.spacer}TGG\t+\t0\n"
        )
        hits = parse_cas_offinder_v241_output(
            output_text,
            request,
            executable_sha256="1" * 64,
            input_sha256=input_sha256,
        )
        return CasOffinderRunResult(
            request=request,
            status=OffTargetComputationStatus.COMPUTED,
            hits=hits,
            input_text=input_text,
            input_sha256=input_sha256,
            output_text=output_text,
            output_sha256=hashlib.sha256(output_text.encode()).hexdigest(),
            executable=CasOffinderExecutableIdentity(
                resolved_path="C:/fixture/cas-offinder.exe",
                sha256="1" * 64,
                observed_banner="Cas-OFFinder v2.4.1 (fixture)",
            ),
            invocation=("C:/fixture/cas-offinder.exe", "input", "C", "output"),
            exit_code=0,
            stdout="",
            stderr="",
            error_code=None,
            error_message=None,
            temporary_paths_cleaned=True,
        )

    result = enumerate_off_targets(selected, runner=one_hit_runner)
    restored = from_json(
        to_json(result), trusted_executable=_trusted_executable(result)
    )

    assert restored == result
    assert restored.off_target is not None
    assert restored.off_target.hit_count == 1
    assert restored.off_target.hits[0].contig == "chr1"


def test_legacy_native_order_result_hash_is_rejected_fail_closed(tmp_path: Path) -> None:
    result = enumerate_off_targets(_selected_result(tmp_path), runner=_computed_adapter_result)
    payload = to_dict(result)
    assert payload["off_target"] is not None
    raw_hash = payload["off_target"]["output_sha256"]
    payload["off_target"]["result_sha256"] = raw_hash
    for hit in payload["off_target"]["hits"]:
        hit["result_sha256"] = raw_hash

    with pytest.raises(CrisprWorkflowContractError, match="normalized result identity"):
        from_json(
            json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
            trusted_executable=_trusted_executable(result),
        )


def test_serialization_rejects_noncanonical_or_tampered_payload(tmp_path: Path) -> None:
    serialized = to_json(compute_workflow(_input(tmp_path)))

    with pytest.raises(CrisprWorkflowContractError):
        from_json(serialized.replace(WORKFLOW_SCHEMA_VERSION, "2.0.0", 1))

    payload = json.loads(serialized)
    payload["scan"]["scanner_output_sha256"] = "0" * 64
    payload["scan"]["candidates"][0]["provenance"]["scanner_output_sha256"] = "0" * 64
    tampered = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    with pytest.raises(CrisprWorkflowContractError, match="output identity"):
        from_json(tampered)


def test_aggregate_contract_introduces_no_predictive_or_ranking_fields() -> None:
    all_names = {
        field.name
        for record_type in (CrisprWorkflowInput, CrisprCandidateRecord)
        for field in fields(record_type)
    }
    forbidden = {
        "rank",
        "ranking",
        "recommended",
        "is_recommended",
        "efficiency_score",
        "cfd_score",
        "overall_score",
    }

    assert all_names.isdisjoint(forbidden)
    assert {field.name for field in fields(SpCas9CandidateGuide)}.isdisjoint(
        {"rank", "ranking", "recommended", "cfd_score"}
    )
