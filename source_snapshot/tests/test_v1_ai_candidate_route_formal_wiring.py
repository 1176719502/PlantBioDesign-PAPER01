from __future__ import annotations

import ast
import csv
import json
import re
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
GOAL = "Express human serum albumin protein in rice"
HOST = "rice"
CDS = "ATG" + ("GCT" * 12) + "TAA"
ROUTE_ID = "plant_protein_expression_review"
SOURCE_METADATA = {
    "gene_name": "HSA",
    "source_species": "Homo sapiens",
    "source_reference": "USER-SUPPLIED-REFERENCE",
}


def _source() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    source = _source()
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


def _app_functions(names: set[str], namespace: dict[str, Any]) -> dict[str, Any]:
    tree = ast.parse(_source())
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"),
        namespace,
    )
    return namespace


def _logic_namespace(state: dict[str, Any] | None = None) -> dict[str, Any]:
    namespace: dict[str, Any] = {
        "Any": Any,
        "Mapping": Mapping,
        "PROJECT_TYPE_SINGLE_GENE": "single_gene",
        "st": SimpleNamespace(session_state=state if state is not None else {}),
    }
    return _app_functions(
        {
            "_formal_ai_route_current_signature",
            "_build_formal_ai_route_candidate_set",
            "_formal_ai_route_fail_closed",
            "_build_formal_ai_route_handoff",
            "_apply_formal_ai_route_prefill",
            "_hydrate_formal_ai_route_step2_prefill",
            "_synchronize_formal_ai_route_freshness",
        },
        namespace,
    )


def _persistence_namespace(state: dict[str, Any]) -> dict[str, Any]:
    namespace: dict[str, Any] = {
        "Any": Any,
        "Mapping": Mapping,
        "json": json,
        "re": re,
        "st": SimpleNamespace(session_state=state),
    }
    return _app_functions(
        {
            "_is_formal_action_widget_key",
            "_formal_state_snapshot",
            "_restore_completed_formal_state",
        },
        namespace,
    )


def _candidate_set(namespace: dict[str, Any]) -> dict[str, Any]:
    return namespace["_build_formal_ai_route_candidate_set"](
        goal_text=GOAL,
        plant_host=HOST,
        user_provided_cds=CDS,
        source_metadata=SOURCE_METADATA,
    )


def _handoff(
    namespace: dict[str, Any],
    candidate_set: Mapping[str, Any],
    **overrides: Any,
) -> dict[str, Any]:
    values = {
        "goal_text": GOAL,
        "plant_host": HOST,
        "user_provided_cds": CDS,
        "source_metadata": SOURCE_METADATA,
        "candidate_set": candidate_set,
        "user_selected_route_id": ROUTE_ID,
        "human_confirmed": True,
    }
    values.update(overrides)
    return namespace["_build_formal_ai_route_handoff"](**values)


def test_candidate_set_reuses_adopted_l6_contract_and_preserves_advisory_flags() -> None:
    namespace = _logic_namespace()
    candidate_set = _candidate_set(namespace)
    intent = candidate_set["intent_payload"]
    candidates = intent["route_candidates"]

    assert candidate_set["advisory_only"] is True
    assert candidate_set["formal_authority"] is False
    assert candidate_set["persist"] is False
    assert intent["decision_state"] == "ready_for_user_confirmation"
    assert ROUTE_ID in {candidate["route_id"] for candidate in candidates}
    selected = next(candidate for candidate in candidates if candidate["route_id"] == ROUTE_ID)
    assert selected["match_reasons_zh"]
    assert "uncertainties_zh" in selected


def test_handoff_requires_current_candidate_selection_and_strict_confirmation() -> None:
    namespace = _logic_namespace()
    candidate_set = _candidate_set(namespace)

    missing_selection = _handoff(
        namespace,
        candidate_set,
        user_selected_route_id=None,
    )
    unconfirmed = _handoff(
        namespace,
        candidate_set,
        human_confirmed=False,
    )
    absent_candidate = _handoff(
        namespace,
        candidate_set,
        user_selected_route_id="plant_regulatory_module_review",
    )

    assert missing_selection["fail_closed_reason"] == "explicit_user_route_selection_required"
    assert unconfirmed["fail_closed_reason"] == "human_confirmation_required"
    assert absent_candidate["fail_closed_reason"] == "selected_route_not_in_current_candidates"
    for result in (missing_selection, unconfirmed, absent_candidate):
        assert result["fail_closed"] is True
        assert result["advisory_only"] is True
        assert result["formal_authority"] is False
        assert result["persist"] is False


def test_goal_host_cds_and_source_metadata_changes_make_candidate_set_stale() -> None:
    namespace = _logic_namespace()
    candidate_set = _candidate_set(namespace)
    changed_inputs = (
        {"goal_text": GOAL + " in seed"},
        {"plant_host": "Rice (O. sativa)", "source_metadata": {**SOURCE_METADATA, "note": "changed"}},
        {"user_provided_cds": "ATG" + ("GCC" * 12) + "TAA"},
        {"source_metadata": {**SOURCE_METADATA, "source_reference": "CHANGED"}},
    )

    # Host aliases normalize to one host identity, but any supplied metadata change still binds freshness.
    for overrides in changed_inputs:
        result = _handoff(namespace, candidate_set, **overrides)
        assert result["fail_closed"] is True
        assert result["fail_closed_reason"] == "candidate_set_stale"


def test_confirmed_handoff_prefills_only_existing_step1_step2_widget_drafts() -> None:
    state: dict[str, Any] = {}
    namespace = _logic_namespace(state)
    candidate_set = _candidate_set(namespace)
    result = _handoff(namespace, candidate_set)

    assert result["fail_closed"] is False
    assert result["advisory_only"] is True
    assert result["formal_authority"] is False
    assert result["persist"] is False
    fields = namespace["_apply_formal_ai_route_prefill"](result)

    assert fields["formal_step1_project_name"] == GOAL
    assert fields["formal_step1_host"] == "Rice (O. sativa)"
    assert fields["formal_step2_gene_name"] == "HSA"
    assert fields["formal_step2_cds_text"] == CDS
    assert fields["formal_step2_source_reference"] == "USER-SUPPLIED-REFERENCE"
    assert fields["formal_step2_modification_status"] == "尚未确定"
    assert "formal_step1_project_type" not in fields
    assert "formal_step1_design_scenario" not in fields
    assert "formal_step2_gene_name" not in state
    assert "formal_step2_cds_text" not in state
    assert namespace["_hydrate_formal_ai_route_step2_prefill"]() is True
    assert state["formal_step2_gene_name"] == "HSA"
    assert state["formal_step2_cds_text"] == CDS
    assert state["formal_step2_source_type"] == "用户自有序列"
    for authoritative_key in (
        "formal_project_definition",
        "formal_cds_input",
        "formal_ui_completed_actions",
        "mvp_project_id",
        "mvp_vector_result",
        "formal_cassette_result",
        "formal_backbone_record",
    ):
        assert authoritative_key not in state


def test_real_rice_egfp_candidate_handoff_populates_step1_step2_without_identity_invention() -> None:
    inventory_path = ROOT / "data" / "plant_component_registry_v1" / "intake_20260827" / "candidate_inventory.csv"
    with inventory_path.open(encoding="utf-8-sig", newline="") as handle:
        egfp_record = next(
            row
            for row in csv.DictReader(handle)
            if row.get("accession_record_identifier") == "U55763.1"
        )

    goal = "在水稻中表达 GFP 荧光报告蛋白，用于植物组织中的表达观察。"
    cds = str(egfp_record["sequence"])
    state: dict[str, Any] = {}
    namespace = _logic_namespace(state)
    candidate_set = namespace["_build_formal_ai_route_candidate_set"](
        goal_text=goal,
        plant_host=HOST,
        user_provided_cds=cds,
        source_metadata={},
    )
    result = namespace["_build_formal_ai_route_handoff"](
        goal_text=goal,
        plant_host=HOST,
        user_provided_cds=cds,
        source_metadata={},
        candidate_set=candidate_set,
        user_selected_route_id=ROUTE_ID,
        human_confirmed=True,
    )

    assert len(cds) == 798
    assert result["fail_closed"] is False
    assert result["advisory_only"] is True
    assert result["formal_authority"] is False
    assert result["persist"] is False
    assert result["prefill"]["supplied_source_metadata"] == {}
    assert result["prefill"]["gene_cds_display_name"] == "用户提供的 CDS"
    assert result["prefill"]["raw_cds"] == cds
    assert "U55763.1" not in str(result)
    assert "EGFP" not in result["prefill"]["gene_cds_display_name"]

    fields = namespace["_apply_formal_ai_route_prefill"](result)
    assert fields["formal_step1_project_name"] == goal
    assert fields["formal_step1_host"] == "Rice (O. sativa)"
    assert fields["formal_step2_gene_name"] == "用户提供的 CDS"
    assert fields["formal_step2_cds_text"] == cds
    assert fields["formal_step2_source_type"] == "用户自有序列"
    assert fields["formal_step2_source_species"] == ""
    assert fields["formal_step2_source_reference"] == ""
    assert fields["formal_step2_modification_status"] == "尚未确定"
    assert "formal_step2_gene_name" not in state
    assert namespace["_hydrate_formal_ai_route_step2_prefill"]() is True
    assert state["formal_step2_gene_name"] == "用户提供的 CDS"
    assert state["formal_step2_cds_text"] == cds


def test_handoff_errors_use_user_copy_and_keep_reason_codes_in_session_state() -> None:
    state: dict[str, Any] = {}
    namespace = _logic_namespace(state)
    namespace.update(
        {
            "_FORMAL_AI_ROUTE_ERROR_MESSAGES_ZH": {
                "unsupported_formal_plant_host": "请选择支持的植物宿主。",
                "missing_step2_draft_fields": "目标 CDS 草稿不完整。",
            },
            "_FORMAL_AI_ROUTE_GENERIC_ERROR_MESSAGE_ZH": "候选路线暂时无法处理，请检查输入后重试。",
        }
    )
    namespace = _app_functions(
        {"_formal_ai_route_reason_code", "_formal_ai_route_user_error"},
        namespace,
    )

    host_message = namespace["_formal_ai_route_user_error"](
        ValueError("plant_host is not supported by the single-gene formal workflow")
    )
    step2_message = namespace["_formal_ai_route_user_error"](
        ValueError("missing_step2_draft_fields")
    )

    assert host_message == "请选择支持的植物宿主。"
    assert step2_message == "目标 CDS 草稿不完整。"
    assert state["formal_ai_route_last_error_reason"] == "missing_step2_draft_fields"
    assert "plant_host" not in host_message
    assert "missing_step2" not in step2_message


def test_freshness_invalidation_clears_untouched_prefill_but_preserves_user_edits() -> None:
    state: dict[str, Any] = {}
    namespace = _logic_namespace(state)
    candidate_set = _candidate_set(namespace)
    result = _handoff(namespace, candidate_set)
    applied_fields = namespace["_apply_formal_ai_route_prefill"](result)
    state["formal_ai_route_candidate_set"] = candidate_set
    state["formal_ai_route_selected_route"] = ROUTE_ID
    state["formal_ai_route_human_confirmed"] = True
    namespace["_hydrate_formal_ai_route_step2_prefill"]()
    state["formal_step2_gene_name"] = "USER_EDITED_NAME"
    changed_signature = namespace["_formal_ai_route_current_signature"](
        goal_text=GOAL,
        plant_host=HOST,
        user_provided_cds=CDS,
        source_metadata={**SOURCE_METADATA, "source_reference": "CHANGED"},
    )

    stale = namespace["_synchronize_formal_ai_route_freshness"](changed_signature)

    assert stale is True
    assert state["formal_step2_gene_name"] == "USER_EDITED_NAME"
    assert state["formal_step1_project_name"] == ""
    assert state["formal_step1_host"] is None
    for key in applied_fields:
        if key not in {
            "formal_step1_project_name",
            "formal_step1_host",
            "formal_step2_gene_name",
        }:
            assert key not in state
    assert "formal_ai_route_candidate_set" not in state
    assert "formal_ai_route_selected_route" not in state
    assert "formal_ai_route_human_confirmed" not in state
    assert "formal_ai_route_applied_prefill" not in state
    assert state["formal_ai_route_stale_notice"] is True


@pytest.mark.parametrize(
    ("stage", "ai_state"),
    (
        (
            "generated",
            {
                "formal_ai_route_candidate_set": {
                    "input_signature": "generated-signature",
                    "persist": False,
                },
            },
        ),
        (
            "selected",
            {
                "formal_ai_route_candidate_set": {"input_signature": "selected-signature"},
                "formal_ai_route_selected_route": ROUTE_ID,
            },
        ),
        (
            "confirmed",
            {
                "formal_ai_route_candidate_set": {"input_signature": "confirmed-signature"},
                "formal_ai_route_selected_route": ROUTE_ID,
                "formal_ai_route_human_confirmed": True,
            },
        ),
        (
            "prefilled",
            {
                "formal_ai_route_candidate_set": {"input_signature": "prefilled-signature"},
                "formal_ai_route_selected_route": ROUTE_ID,
                "formal_ai_route_human_confirmed": True,
                "formal_ai_route_applied_prefill": {
                    "input_signature": "prefilled-signature",
                    "field_values": {"formal_step2_gene_name": "HSA"},
                },
                "formal_ai_route_step2_hydrated_signature": "prefilled-signature",
                "formal_ai_route_future_control": "must-also-be-session-only",
            },
        ),
    ),
)
def test_ai_route_lifecycle_save_excludes_entire_session_namespace_and_keeps_drafts(
    tmp_path: Path,
    stage: str,
    ai_state: dict[str, Any],
) -> None:
    from core.design_session import DesignSession
    from services.formal_project_persistence import (
        formal_draft_snapshot,
        save_formal_project_draft,
    )
    from services.plant_project_draft_repository import PlantProjectDraftRepository

    legitimate_state = {
        "formal_step1_host": "Rice (O. sativa)",
        "formal_step2_gene_name": "HSA",
        "formal_step2_cds_text": CDS,
        "formal_project_definition": {
            "project_name": GOAL,
            "plant_host": "Rice (O. sativa)",
        },
        "formal_cds_input": {
            "normalized_cds": CDS,
            "gene_information": {"gene_name": "HSA"},
        },
    }
    state = {**legitimate_state, **ai_state}
    snapshot = _persistence_namespace(state)["_formal_state_snapshot"]()
    repository = PlantProjectDraftRepository(tmp_path / stage)
    saved = save_formal_project_draft(
        project_name=GOAL,
        project_id=f"ai-route-{stage}",
        workflow_type="single_gene",
        current_step=2,
        design_session=DesignSession(
            step=2,
            gene_name="HSA",
            original_seq=CDS,
            host="Rice (O. sativa)",
        ),
        formal_state=snapshot,
        project_definition=legitimate_state["formal_project_definition"],
        repository=repository,
    )
    persisted_state = formal_draft_snapshot(repository.load(saved.project_id))["formal_state"]

    assert not any(key.startswith("formal_ai_route_") for key in snapshot)
    assert not any(key.startswith("formal_ai_route_") for key in persisted_state)
    for key, value in legitimate_state.items():
        assert persisted_state[key] == value


def test_adversarial_completed_snapshot_does_not_restore_ai_route_session_state() -> None:
    state: dict[str, Any] = {}
    functions = _persistence_namespace(state)
    functions["_restore_completed_formal_state"](
        {
            "formal_state": {
                "formal_step1_host": "Rice (O. sativa)",
                "formal_step2_gene_name": "HSA",
                "formal_step2_cds_text": CDS,
                "formal_ai_route_candidate_set": {"input_signature": "legacy"},
                "formal_ai_route_selected_route": ROUTE_ID,
                "formal_ai_route_human_confirmed": True,
                "formal_ai_route_applied_prefill": {"input_signature": "legacy"},
                "formal_ai_route_step2_hydrated_signature": "legacy",
            }
        }
    )

    assert state["formal_step1_host"] == "Rice (O. sativa)"
    assert state["formal_step2_gene_name"] == "HSA"
    assert state["formal_step2_cds_text"] == CDS
    assert not any(key.startswith("formal_ai_route_") for key in state)


def test_adversarial_draft_cold_reopen_filters_ai_state_preserves_drafts_and_requires_fresh_route(
    tmp_path: Path,
) -> None:
    from core.design_session import DesignSession
    from services.formal_project_persistence import save_formal_project_draft
    from services.plant_project_draft_repository import PlantProjectDraftRepository

    repository = PlantProjectDraftRepository(tmp_path / "adversarial")
    saved = save_formal_project_draft(
        project_name=GOAL,
        project_id="legacy-ai-route-state",
        workflow_type="single_gene",
        current_step=2,
        design_session=DesignSession(
            step=2,
            gene_name="HSA",
            original_seq=CDS,
            host="Rice (O. sativa)",
        ),
        formal_state={
            "formal_step1_host": "Rice (O. sativa)",
            "formal_step2_gene_name": "HSA",
            "formal_step2_cds_text": CDS,
            "formal_cds_input": {
                "normalized_cds": CDS,
                "gene_information": {"gene_name": "HSA"},
            },
            "formal_ai_route_candidate_set": {"input_signature": "legacy"},
            "formal_ai_route_selected_route": ROUTE_ID,
            "formal_ai_route_human_confirmed": True,
            "formal_ai_route_applied_prefill": {"input_signature": "legacy"},
            "formal_ai_route_step2_hydrated_signature": "legacy",
        },
        project_definition={
            "project_name": GOAL,
            "plant_host": "Rice (O. sativa)",
        },
        repository=repository,
    )
    state: dict[str, Any] = {"formal_ai_route_existing_session_value": "clear-on-open"}
    route: list[str] = []

    class Controller:
        restored: Any = None

        def save(self, value: Any) -> None:
            self.restored = value

    controller = Controller()
    namespace: dict[str, Any] = {
        "Any": Any,
        "Mapping": Mapping,
        "re": re,
        "st": SimpleNamespace(session_state=state),
        "PROJECT_TYPE_SINGLE_GENE": "single_gene",
        "PROJECT_TYPE_DUAL_TU": "dual_tu",
        "PAGE_DESIGN_WORKSPACE": "design_workspace",
        "_restore_formal_step3_generated_result": lambda: None,
        "_controller": lambda: controller,
        "_change_page": route.append,
    }
    functions = _app_functions(
        {
            "_is_formal_action_widget_key",
            "_restore_formal_workflow_draft",
        },
        namespace,
    )
    functions["_restore_formal_workflow_draft"](saved.project_id, repository)

    assert route == ["design_workspace"]
    assert controller.restored is not None
    assert state["formal_step1_host"] == "Rice (O. sativa)"
    assert state["formal_step2_gene_name"] == "HSA"
    assert state["formal_step2_cds_text"] == CDS
    assert state["formal_cds_input"]["normalized_cds"] == CDS
    assert not any(key.startswith("formal_ai_route_") for key in state)
    for premature_key in (
        "mvp_vector_result",
        "formal_cassette_result",
        "formal_expression_cassette",
        "formal_backbone_record",
    ):
        assert premature_key not in state

    ai_namespace = _logic_namespace(state)
    stale_handoff = _handoff(ai_namespace, state.get("formal_ai_route_candidate_set"))
    assert stale_handoff["fail_closed_reason"] == "candidate_set_stale"
    fresh_candidate_set = _candidate_set(ai_namespace)
    fresh_handoff = _handoff(ai_namespace, fresh_candidate_set)
    assert fresh_handoff["fail_closed"] is False


def test_legacy_ai_prefill_ui_is_retired_without_changing_bounded_helpers() -> None:
    workspace = _function_source("_render_design_workspace")
    renderer = _function_source("_render_formal_ai_route_entry")
    apply_prefill = _function_source("_apply_formal_ai_route_prefill")

    assert '_formal_ai_route_prefill_eligible' not in workspace
    assert '_render_formal_ai_route_entry' not in workspace
    assert 'st.title("表达设计")' in workspace
    assert "_render_step_1_project" in workspace
    assert "_render_step_2_cds" in workspace
    assert "v1.expression.generate_candidate_routes" in renderer
    assert "v1.expression.matching_basis" in renderer
    assert "v1.expression.input_basis" in renderer
    assert "v1.expression.information_gap" in renderer
    assert 'index=None' in renderer
    assert 'disabled=not bool(selected_route_id and human_confirmed)' in renderer
    assert "v1.expression.step_1_step_2_draft_fields_pre" in renderer
    forbidden_calls = (
        "generate_complete_vector",
        "generate_expression_cassette",
        "_apply_formal_project_definition",
        "_apply_formal_cds_analysis",
        "_save_current_formal_draft",
        "save_formal_project",
        "initialize_database",
        "export_active_construct",
    )
    combined = renderer + apply_prefill
    assert all(call not in combined for call in forbidden_calls)
