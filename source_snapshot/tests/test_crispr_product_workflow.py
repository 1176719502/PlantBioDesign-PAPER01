from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import json
from io import StringIO
from pathlib import Path

import pytest
from services.cas_offinder_adapter import (
    CasOffinderExecutableIdentity,
    CasOffinderRunResult,
    OffTargetComputationStatus,
    build_cas_offinder_input,
    parse_cas_offinder_v241_output,
)
from services.crispr_product_workflow import (
    CRISPR_PRODUCT_STATE_KEY,
    OFF_TARGET_TSV_COLUMNS,
    CrisprProductWorkflowError,
    build_product_workflow_input,
    candidate_projection,
    compute_product_workflow,
    enumerate_product_off_targets,
    installed_reference_from_fasta,
    invalidate_stale_product_result,
    off_target_hit_projection,
    off_target_hits_tsv,
    open_crispr_product_workflow,
    save_crispr_product_workflow,
    saved_crispr_product_metadata,
    select_product_candidate,
)
from services.crispr_workflow_contract import (
    CrisprWorkflowContractError,
    WorkflowState,
    to_json,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from views.CrisprWorkspace import _current_input, _hydration_values


SEQUENCE = "AAA" + "ACGT" * 5 + "TGG" + "AAA"
EXECUTABLE = CasOffinderExecutableIdentity(
    resolved_path="C:/fixture/cas-offinder.exe",
    sha256="1" * 64,
    observed_banner="Cas-OFFinder v2.4.1 (fixture)",
)
ROOT = Path(__file__).resolve().parents[1]


def _reference(tmp_path: Path, *, version: str = "TAIR10.1"):
    path = tmp_path / version / "assembly.fa"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f">chr1\n{SEQUENCE}\n", encoding="utf-8")
    return installed_reference_from_fasta(
        path,
        organism_scientific_name="Arabidopsis thaliana",
        taxonomy_id="3702",
        provider="fixture-provider",
        assembly_accession="GCF_000001735.4",
        assembly_version=version,
        installation_provenance="product integration fixture",
    )


def _input(
    tmp_path: Path,
    *,
    sequence: str = SEQUENCE,
    reference=None,
    maximum_mismatches: int = 4,
    off_target_requested: bool = True,
):
    return build_product_workflow_input(
        target_sequence=sequence,
        target_id="target-1",
        target_display_name="Target 1",
        reference_pack_id="tair10-reference-pack-v1",
        contig="chr1",
        reference=reference or _reference(tmp_path),
        reference_offset=100,
        maximum_mismatches=maximum_mismatches,
        off_target_requested=off_target_requested,
        executable_path=EXECUTABLE.resolved_path if off_target_requested else None,
        expected_executable_sha256=EXECUTABLE.sha256 if off_target_requested else None,
    )


def _selected(tmp_path: Path):
    workflow_input = _input(tmp_path)
    computed = compute_product_workflow(workflow_input)
    return select_product_candidate(
        computed,
        computed.scan.candidates[0].candidate_id,
        current_input=workflow_input,
    )


def _refresh_from_widget_intent(result, *, off_target_requested: bool):
    state = _hydration_values(result)
    state["formal_crispr_off_target_requested"] = off_target_requested
    current_input = _current_input(state)
    return current_input, invalidate_stale_product_result(result, current_input)


def _runner(*, rows: int = 0, status=OffTargetComputationStatus.COMPUTED):
    def run(request):
        input_text, input_sha256 = build_cas_offinder_input(request)
        if status is OffTargetComputationStatus.COMPUTED:
            output_text = "".join(
                f"{request.query}\tchr1\t{3 + index}\t{request.spacer}TGG\t+\t{index}\n"
                for index in range(rows)
            )
            hits = parse_cas_offinder_v241_output(
                output_text,
                request,
                executable_sha256=EXECUTABLE.sha256,
                input_sha256=input_sha256,
            )
            return CasOffinderRunResult(
                request=request,
                status=status,
                hits=hits,
                input_text=input_text,
                input_sha256=input_sha256,
                output_text=output_text,
                output_sha256=hashlib.sha256(output_text.encode()).hexdigest(),
                executable=EXECUTABLE,
                invocation=(EXECUTABLE.resolved_path, "input", "C", "output"),
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
            stderr="fixture diagnostic",
            error_code=status.value.upper(),
            error_message="fixture non-computed state",
            temporary_paths_cleaned=True,
        )

    return run


def _repository_with_project(tmp_path: Path):
    repo = PlantProjectDraftRepository(tmp_path / "projects")
    project = repo.create_blank("CRISPR product project")
    return repo, repo.save(project)


def _all_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _all_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _all_keys(nested)


def test_formal_product_entry_uses_aggregate_and_stable_candidate_projection(tmp_path: Path) -> None:
    workflow_input = _input(tmp_path)
    first = compute_product_workflow(workflow_input)
    second = compute_product_workflow(workflow_input)

    assert first.workflow_id.startswith("crispr-workflow-")
    assert first.scan.state is WorkflowState.COMPUTED
    assert candidate_projection(first) == candidate_projection(second)
    first_row = candidate_projection(first)[0]
    assert first_row["candidate_id"] == first.scan.candidates[0].candidate_id
    assert first_row["gc_fraction"] == first.scan.candidates[0]._guide.gc_fraction
    assert first_row["warning_codes"] == tuple(
        warning.code.value for warning in first.scan.candidates[0]._guide.warnings
    )
    assert (
        first_row["scanner_algorithm_id"]
        == first.scan.candidates[0]._guide.scanner.algorithm_id
    )
    assert first_row["scanner_output_sha256"] == first.scan.scanner_output_sha256


def test_off_target_not_requested_does_not_invent_string_none_executable_identity(
    tmp_path: Path,
) -> None:
    workflow_input = build_product_workflow_input(
        target_sequence=SEQUENCE,
        target_id="target-1",
        target_display_name="Target 1",
        reference_pack_id="tair10-reference-pack-v1",
        contig="chr1",
        reference=_reference(tmp_path),
        reference_offset=100,
        maximum_mismatches=4,
        off_target_requested=False,
        executable_path=EXECUTABLE.resolved_path,
        expected_executable_sha256=EXECUTABLE.sha256,
    )
    result = compute_product_workflow(workflow_input)

    assert workflow_input.execution_intent.executable_path is None
    assert workflow_input.execution_intent.expected_executable_sha256 is None
    assert result.off_target_state is WorkflowState.NOT_RUN


def test_explicit_selection_is_bound_and_invalid_candidate_is_rejected(tmp_path: Path) -> None:
    workflow_input = _input(tmp_path)
    result = compute_product_workflow(workflow_input)
    selected = select_product_candidate(
        result,
        result.scan.candidates[0].candidate_id,
        current_input=workflow_input,
    )

    assert selected.selection is not None
    assert selected.selection.workflow_id == result.workflow_id
    assert selected.selection.candidate == selected.scan.candidates[0]
    with pytest.raises(CrisprWorkflowContractError, match="absent"):
        select_product_candidate(result, "candidate-from-another-workflow")


@pytest.mark.parametrize("rows", [0, 1, 3])
def test_zero_exact_and_multi_hit_results_remain_computed(tmp_path: Path, rows: int) -> None:
    selected = _selected(tmp_path)
    result = enumerate_product_off_targets(selected, runner=_runner(rows=rows))

    assert result.off_target_state is WorkflowState.COMPUTED
    assert result.off_target is not None
    assert result.off_target.hit_count == rows
    assert len(result.off_target.hits) == rows


@pytest.mark.parametrize(
    ("status", "expected_state"),
    [
        (OffTargetComputationStatus.UNAVAILABLE, WorkflowState.UNAVAILABLE),
        (OffTargetComputationStatus.EXECUTION_FAILED, WorkflowState.FAILED),
    ],
)
def test_unavailable_and_failed_execution_are_explicit(
    tmp_path: Path, status, expected_state
) -> None:
    result = enumerate_product_off_targets(_selected(tmp_path), runner=_runner(status=status))

    assert result.off_target_state is expected_state
    assert result.off_target is not None
    assert result.off_target.hit_count is None
    assert result.off_target.hits == ()
    assert result.off_target.error_message == "fixture non-computed state"


def test_changed_target_invalidates_selection_and_off_target_state(tmp_path: Path) -> None:
    original = _input(tmp_path)
    completed = enumerate_product_off_targets(_selected(tmp_path), runner=_runner(rows=0))
    changed = _input(tmp_path, sequence="T" + SEQUENCE[1:])

    reset = invalidate_stale_product_result(completed, changed)

    assert original.freshness_hash != changed.freshness_hash
    assert reset.workflow_id == changed.workflow_id
    assert reset.selection is None
    assert reset.off_target is None
    assert reset.off_target_state is WorkflowState.NOT_RUN


def test_changed_reference_invalidates_downstream_state(tmp_path: Path) -> None:
    completed = enumerate_product_off_targets(_selected(tmp_path), runner=_runner(rows=1))
    changed_reference = _input(
        tmp_path,
        reference=_reference(tmp_path, version="TAIR10.2"),
    )

    reset = invalidate_stale_product_result(completed, changed_reference)

    assert reset.workflow_id != completed.workflow_id
    assert reset.selection is None
    assert reset.off_target is None


def test_false_to_true_execution_intent_preserves_the_same_selected_candidate(
    tmp_path: Path,
) -> None:
    initial_input = _input(tmp_path, off_target_requested=False)
    computed = compute_product_workflow(initial_input)
    completed = select_product_candidate(
        computed,
        computed.scan.candidates[0].candidate_id,
        current_input=initial_input,
    )
    changed = replace(
        completed.workflow_input,
        execution_intent=replace(
            completed.workflow_input.execution_intent,
            off_target_requested=True,
            timeout_seconds=60.0,
            executable_path=EXECUTABLE.resolved_path,
            expected_executable_sha256=EXECUTABLE.sha256,
        ),
    )

    refreshed = invalidate_stale_product_result(completed, changed)

    assert refreshed.workflow_id == changed.workflow_id
    assert refreshed.workflow_input.execution_intent.off_target_requested is True
    assert refreshed.selection is not None
    assert refreshed.selection.candidate_id == completed.selection.candidate_id
    assert refreshed.selection.candidate.off_target_state is WorkflowState.NOT_RUN
    assert refreshed.off_target is None
    assert refreshed.off_target_state is WorkflowState.NOT_RUN


def test_true_to_true_rerun_preserves_complete_valid_intent(tmp_path: Path) -> None:
    selected = _selected(tmp_path)
    current_input, refreshed = _refresh_from_widget_intent(
        selected,
        off_target_requested=True,
    )

    assert current_input == selected.workflow_input
    assert refreshed is selected
    assert refreshed.workflow_input.execution_intent.off_target_requested is True
    assert (
        refreshed.workflow_input.execution_intent.executable_path
        == EXECUTABLE.resolved_path
    )
    assert (
        refreshed.workflow_input.execution_intent.expected_executable_sha256
        == EXECUTABLE.sha256
    )


def test_true_to_false_with_configured_executable_does_not_raise(tmp_path: Path) -> None:
    selected = _selected(tmp_path)

    current_input, refreshed = _refresh_from_widget_intent(
        selected,
        off_target_requested=False,
    )

    assert current_input.execution_intent.off_target_requested is False
    assert current_input.execution_intent.executable_path is None
    assert current_input.execution_intent.expected_executable_sha256 is None
    assert refreshed.workflow_input == current_input


def test_true_to_false_after_computed_result_removes_stale_result(tmp_path: Path) -> None:
    completed = enumerate_product_off_targets(
        _selected(tmp_path),
        runner=_runner(rows=1),
    )

    _, refreshed = _refresh_from_widget_intent(
        completed,
        off_target_requested=False,
    )

    assert refreshed.off_target is None
    assert refreshed.off_target_state is WorkflowState.NOT_RUN
    assert off_target_hit_projection(refreshed) == ()
    with pytest.raises(CrisprProductWorkflowError, match="only for a computed"):
        off_target_hits_tsv(refreshed)


def test_true_to_false_preserves_selected_guide(tmp_path: Path) -> None:
    selected = _selected(tmp_path)

    _, refreshed = _refresh_from_widget_intent(
        selected,
        off_target_requested=False,
    )

    assert refreshed.selection is not None
    assert refreshed.selection.candidate_id == selected.selection.candidate_id
    assert (
        refreshed.selection.candidate.guide_sequence
        == selected.selection.candidate.guide_sequence
    )


def test_true_to_false_removes_all_incompatible_execution_state(tmp_path: Path) -> None:
    completed = enumerate_product_off_targets(
        _selected(tmp_path),
        runner=_runner(rows=1),
    )

    _, refreshed = _refresh_from_widget_intent(
        completed,
        off_target_requested=False,
    )

    intent = refreshed.workflow_input.execution_intent
    assert intent.executable_path is None
    assert intent.expected_executable_sha256 is None
    assert intent.observed_executable_path is None
    assert intent.observed_executable_sha256 is None
    assert intent.observed_engine_banner is None
    assert intent.observed_engine is None
    assert intent.observed_engine_version is None
    assert intent.observed_runtime_mode is None
    assert refreshed.off_target is None
    assert all(
        candidate.off_target_state is WorkflowState.NOT_RUN
        for candidate in refreshed.scan.candidates
    )


def test_true_false_true_transition_restores_valid_executable_intent(tmp_path: Path) -> None:
    selected = _selected(tmp_path)
    state = _hydration_values(selected)
    state["formal_crispr_off_target_requested"] = False
    disabled_input = _current_input(state)
    disabled = invalidate_stale_product_result(selected, disabled_input)

    state["formal_crispr_off_target_requested"] = True
    enabled_input = _current_input(state)
    reenabled = invalidate_stale_product_result(disabled, enabled_input)

    assert reenabled.workflow_input.execution_intent.off_target_requested is True
    assert (
        reenabled.workflow_input.execution_intent.executable_path
        == EXECUTABLE.resolved_path
    )
    assert (
        reenabled.workflow_input.execution_intent.expected_executable_sha256
        == EXECUTABLE.sha256
    )
    assert reenabled.selection is not None
    assert reenabled.selection.candidate_id == selected.selection.candidate_id
    assert reenabled.off_target is None
    assert reenabled.off_target_state is WorkflowState.NOT_RUN


def test_mismatch_configuration_change_invalidates_downstream_state(
    tmp_path: Path,
) -> None:
    completed = enumerate_product_off_targets(
        _selected(tmp_path),
        runner=_runner(rows=1),
    )
    changed = replace(
        completed.workflow_input,
        execution_intent=replace(
            completed.workflow_input.execution_intent,
            maximum_mismatches=2,
        ),
    )

    reset = invalidate_stale_product_result(completed, changed)

    assert reset.workflow_id == changed.workflow_id
    assert reset.selection is None
    assert reset.off_target is None
    assert reset.off_target_state is WorkflowState.NOT_RUN


def test_unchanged_input_preserves_the_complete_result(tmp_path: Path) -> None:
    completed = enumerate_product_off_targets(
        _selected(tmp_path),
        runner=_runner(rows=1),
    )

    assert invalidate_stale_product_result(completed, completed.workflow_input) is completed


def test_real_candidate_change_clears_incompatible_off_target_result(
    tmp_path: Path,
) -> None:
    sequence = SEQUENCE + "ACGT" * 5 + "AGGAAA"
    workflow_input = _input(tmp_path, sequence=sequence)
    computed = compute_product_workflow(workflow_input)
    assert len(computed.scan.candidates) >= 2
    selected = select_product_candidate(
        computed,
        computed.scan.candidates[0].candidate_id,
        current_input=workflow_input,
    )
    completed = enumerate_product_off_targets(selected, runner=_runner(rows=1))

    changed = select_product_candidate(
        completed,
        completed.scan.candidates[1].candidate_id,
        current_input=workflow_input,
    )

    assert changed.selection is not None
    assert changed.selection.candidate_id == completed.scan.candidates[1].candidate_id
    assert changed.off_target is None
    assert changed.off_target_state is WorkflowState.NOT_RUN


def test_save_reopen_and_independent_cold_reopen_preserve_exact_aggregate(tmp_path: Path) -> None:
    repo, project = _repository_with_project(tmp_path)
    result = enumerate_product_off_targets(_selected(tmp_path), runner=_runner(rows=1))

    save_crispr_product_workflow(project.project_id, result, repository=repo)
    reopened = open_crispr_product_workflow(
        project.project_id,
        trusted_executable=EXECUTABLE,
        repository=repo,
    )
    cold_repo = PlantProjectDraftRepository(repo.storage_dir)
    cold_reopened = open_crispr_product_workflow(
        project.project_id,
        trusted_executable=EXECUTABLE,
        repository=cold_repo,
    )

    assert to_json(reopened) == to_json(result)
    assert to_json(cold_reopened) == to_json(result)
    assert reopened.workflow_input.target == result.workflow_input.target
    assert reopened.workflow_input.configuration == result.workflow_input.configuration
    assert reopened.workflow_input.reference_hash == result.workflow_input.reference_hash
    assert reopened.selection == result.selection
    assert reopened.off_target == result.off_target
    metadata = saved_crispr_product_metadata(project.project_id, repository=cold_repo)
    assert metadata["workflow_id"] == result.workflow_id
    assert metadata["expected_executable_sha256"] == EXECUTABLE.sha256
    assert metadata["off_target_state"] == "computed"
    assert metadata["selected_candidate_id"] == result.selection.candidate_id
    assert metadata["hit_count"] == 1


def test_reopen_hydration_executes_with_the_saved_reference_path(tmp_path: Path) -> None:
    result = _selected(tmp_path)
    hydration_values = _hydration_values(result)

    fasta_file = result.workflow_input.reference_binding.reference.fasta_files[0]
    assert hydration_values["formal_crispr_reference_fasta"] == str(
        Path(result.workflow_input.reference_binding.reference.fasta_directory)
        / fasta_file.relative_path
    )
    assert hydration_values["formal_crispr_target_sequence"] == SEQUENCE
    assert hydration_values["formal_crispr_mismatches"] == 4


def test_persisted_aggregate_requires_external_executable_authority(tmp_path: Path) -> None:
    repo, project = _repository_with_project(tmp_path)
    result = enumerate_product_off_targets(_selected(tmp_path), runner=_runner(rows=0))
    save_crispr_product_workflow(project.project_id, result, repository=repo)

    with pytest.raises(CrisprWorkflowContractError, match="authority is required"):
        open_crispr_product_workflow(project.project_id, repository=repo)
    stored = repo.load(project.project_id).manual_review_state[CRISPR_PRODUCT_STATE_KEY]
    assert stored["aggregate_json"] == to_json(result)


def test_aggregate_serialization_is_deterministic_and_has_no_ranking_fields(tmp_path: Path) -> None:
    result = enumerate_product_off_targets(_selected(tmp_path), runner=_runner(rows=0))
    first = to_json(result)
    second = to_json(result)
    payload = json.loads(first)
    forbidden = {
        "rank",
        "ranking",
        "score",
        "activity_prediction",
        "cfd_score",
        "deepcrispr",
        "best_grna",
        "recommendation",
        "recommended",
    }

    assert first == second
    assert forbidden.isdisjoint({key.casefold() for key in _all_keys(payload)})
    assert forbidden.isdisjoint(
        {key.casefold() for row in candidate_projection(result) for key in row}
    )


def test_off_target_projection_and_tsv_use_exact_deterministic_contract(tmp_path: Path) -> None:
    result = enumerate_product_off_targets(_selected(tmp_path), runner=_runner(rows=3))

    rows = off_target_hit_projection(result)
    tsv = off_target_hits_tsv(result)
    parsed = list(csv.DictReader(StringIO(tsv), delimiter="\t"))

    assert tuple(parsed[0]) == OFF_TARGET_TSV_COLUMNS
    assert len(rows) == len(parsed) == 3
    assert [row["start_0_based"] for row in rows] == [3, 4, 5]
    assert [int(row["start_0_based"]) for row in parsed] == [3, 4, 5]
    assert tsv.endswith("\n")
    assert "\r" not in tsv
    assert all("path" not in key for key in OFF_TARGET_TSV_COLUMNS)


def test_tsv_bytes_ignore_run_specific_invocation_and_diagnostics(tmp_path: Path) -> None:
    base_runner = _runner(rows=1)

    def diagnostic_runner(request, input_path: str, output_path: str, stderr: str):
        return replace(
            base_runner(request),
            invocation=(EXECUTABLE.resolved_path, input_path, "C", output_path),
            stdout=f"run at {input_path}",
            stderr=stderr,
        )

    first = enumerate_product_off_targets(
        _selected(tmp_path),
        runner=lambda request: diagnostic_runner(
            request,
            "C:/temp/run-a/input.txt",
            "C:/temp/run-a/output.txt",
            "elapsed=0.101s",
        ),
    )
    second = enumerate_product_off_targets(
        _selected(tmp_path),
        runner=lambda request: diagnostic_runner(
            request,
            "D:/other/run-b/input.txt",
            "D:/other/run-b/output.txt",
            "elapsed=0.202s",
        ),
    )

    assert off_target_hits_tsv(first) == off_target_hits_tsv(second)


def test_zero_hit_tsv_is_header_only_and_noncomputed_states_are_disabled(
    tmp_path: Path,
) -> None:
    zero = enumerate_product_off_targets(_selected(tmp_path), runner=_runner(rows=0))
    unavailable = enumerate_product_off_targets(
        _selected(tmp_path),
        runner=_runner(status=OffTargetComputationStatus.UNAVAILABLE),
    )

    assert off_target_hits_tsv(zero) == "\t".join(OFF_TARGET_TSV_COLUMNS) + "\n"
    with pytest.raises(CrisprProductWorkflowError, match="only for a computed"):
        off_target_hits_tsv(_selected(tmp_path))
    with pytest.raises(CrisprProductWorkflowError, match="only for a computed"):
        off_target_hits_tsv(unavailable)


def test_formal_app_registers_primary_extracted_crispr_product_route() -> None:
    source = Path("app.py").read_text(encoding="utf-8")
    view_source = (ROOT / "views" / "CrisprWorkspace.py").read_text(encoding="utf-8")

    assert 'PAGE_CRISPR_WORKFLOW = "CRISPR V1 Workflow"' in source
    assert "_render_crispr_product_workflow()" in source
    assert "from views.CrisprWorkspace import render" in source
    assert "compute_product_workflow" not in source
    assert "enumerate_product_off_targets" not in source
    assert "compute_product_workflow" in view_source
    assert "enumerate_product_off_targets" in view_source
