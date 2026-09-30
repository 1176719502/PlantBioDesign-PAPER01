from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

import mvp_app
from scripts.acceptance.ui04a_acceptance_seed import (
    COMPLETE_PROJECT_ID,
    COMPLETE_PROJECT_NAME,
    HISTORICAL_PROJECT_ID,
    build_formal_editor_completed,
    migrate_ui04a_complete_project,
    seed_ui04a_acceptance_environment,
)
from services.mvp_single_gene_persistence import (
    MvpSingleGenePersistenceError,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.formal_project_definition_lifecycle import requires_construct_review
from services.plant_project_draft_repository import PlantProjectDraftRepository


ROOT = Path(__file__).resolve().parents[1]


class _Streamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}


class _Controller:
    def save(self, _session: Any) -> None:
        pass


def _app_functions(*names: str, namespace: dict[str, Any]) -> dict[str, Any]:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    nodes = [
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return {name: namespace[name] for name in names}


def _restored_statuses(
    result: dict[str, Any], *, explicit_historical_open: bool = False
) -> tuple[list[dict[str, bool]], bool, dict[str, Any]]:
    streamlit = _Streamlit()
    route: list[str] = []
    functions = _app_functions(
        "_formal_ui_signature",
        "_formal_step4_strategy_signature",
        "_is_formal_action_widget_key",
        "_restore_completed_formal_state",
        "_restored_formal_project_context",
        "_formal_step3_custom_input_label",
        "_restore_mvp_result",
        "_formal_step_statuses",
        "_is_result_preview_mode",
        "_project_definition_expression_target",
        "_verified_formal_saved_project_id",
        namespace={
            "Any": Any,
            "Mapping": Mapping,
            "hashlib": hashlib,
            "json": json,
            "re": __import__("re"),
            "st": streamlit,
            "_FORMAL_STEP3_CUSTOM_INPUT_LABELS": {
                "paste": "粘贴 DNA/FASTA",
                "upload": "上传 FASTA",
            },
            "_FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL": "需要核对输入来源",
            "PROJECT_TYPE_SINGLE_GENE": "single_gene",
            "PROJECT_TYPE_DUAL_TU": "dual_tu",
            "PAGE_RESULTS_EXPORT": "results",
            "_controller": lambda: _Controller(),
            "_change_page": route.append,
            "_formal_project_type": lambda: "single_gene",
            "_host_supports_project_type": lambda *_args: True,
            "_is_pathway_multi_tu_project": lambda: False,
            "_is_generic_multi_tu_workflow": lambda: False,
            "_is_multi_tu_expression_assembly": lambda _result: False,
        },
    )
    functions["_restore_mvp_result"](result, "Rice / Oryza sativa")
    if explicit_historical_open:
        streamlit.session_state["formal_explicit_historical_open"] = True
    streamlit.session_state["formal_last_saved_mvp_project_id"] = result["project_id"]
    return (
        functions["_formal_step_statuses"](),
        functions["_is_result_preview_mode"](),
        streamlit.session_state,
    )


def test_formal_editor_completed_round_trip_restores_all_six_steps(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "records")
    saved = save_mvp_single_gene_design(build_formal_editor_completed(), repository=repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repository)

    statuses, preview, state = _restored_statuses(reopened)

    assert reopened["record_kind"] == "formal_editor_completed"
    assert reopened["formal_editor_restore_reason"] == ""
    assert len(reopened["formal_expression_cassette"]["components"]) == 3
    assert state["formal_expression_cassette"]["components"] == reopened["formal_expression_cassette"]["components"]
    assert statuses == [{"done": True, "review": False}] * 6
    assert preview is False


@pytest.mark.parametrize(
    ("mutation", "expected_reason"),
    [
        ("missing_contract_version", "unsupported_version"),
        ("missing_formal_state", "missing_formal_state"),
        ("missing_step3_components", "missing_step3_components"),
        ("missing_review_status", "missing_formal_state"),
    ],
)
def test_formal_editor_completed_rejects_an_incomplete_contract(
    tmp_path: Path, mutation: str, expected_reason: str
) -> None:
    broken = build_formal_editor_completed()
    context = broken["formal_project_context"]
    if mutation == "missing_contract_version":
        context.pop("formal_editor_state_contract_version")
    elif mutation == "missing_formal_state":
        context.pop("formal_state")
    elif mutation == "missing_review_status":
        context["formal_state"].pop("formal_construct_review_status")
    else:
        context["formal_state"]["formal_expression_cassette"]["components"] = []
    with pytest.raises(MvpSingleGenePersistenceError, match=expected_reason):
        save_mvp_single_gene_design(broken, repository=PlantProjectDraftRepository(tmp_path / "records"))


def test_seeded_environment_keeps_result_only_history_in_preview(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "records")
    seed_ui04a_acceptance_environment(repository.storage_dir)

    complete = open_mvp_single_gene_design(COMPLETE_PROJECT_ID, repository=repository)
    historical = open_mvp_single_gene_design(HISTORICAL_PROJECT_ID, repository=repository)
    complete_statuses, complete_preview, _complete_state = _restored_statuses(complete)
    historical_statuses, historical_preview, _historical_state = _restored_statuses(
        historical,
        explicit_historical_open=True,
    )

    assert [item["done"] for item in complete_statuses] == [True] * 6
    assert complete_preview is False
    assert not requires_construct_review(
        complete["formal_project_context"]["project_definition"],
        complete["formal_project_context"]["construct_review_basis"],
    )
    assert historical["record_kind"] == "result_only_completed"
    assert historical["formal_editor_restore_reason"] == "result_only_completed"
    assert historical_preview is True
    assert historical_statuses[2]["done"] is False


def test_migration_mismatch_preserves_the_original_json(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "records")
    incompatible = mvp_app.generate_complete_vector(
        mvp_app.load_real_case(),
        project_id=COMPLETE_PROJECT_ID,
        project_name=COMPLETE_PROJECT_NAME,
    )
    save_mvp_single_gene_design(incompatible, repository=repository)
    target = repository._path_for(COMPLETE_PROJECT_ID)
    before = target.read_bytes()

    with pytest.raises(RuntimeError, match="canonical or Step 3 component verification failed"):
        migrate_ui04a_complete_project(repository.storage_dir)

    assert target.read_bytes() == before
    assert target.with_suffix(".json.ui04a-pre-migration.bak").read_bytes() == before


def test_seeded_project_ids_are_distinct_and_stable(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "records")
    seed_ui04a_acceptance_environment(repository.storage_dir)
    summaries = repository.list_summaries()
    names_by_id = {summary.project_id: summary.project_name for summary in summaries}

    assert names_by_id == {
        COMPLETE_PROJECT_ID: COMPLETE_PROJECT_NAME,
        HISTORICAL_PROJECT_ID: "UI-04A Historical Preview",
    }
