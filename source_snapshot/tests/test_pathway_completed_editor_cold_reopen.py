from __future__ import annotations

import ast
import copy
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from services.formal_editor_state_contract import (
    FORMAL_EDITOR_STATE_CONTRACT_VERSION,
    RECORD_KIND_FORMAL_EDITOR_COMPLETED,
)
from services.mvp_multi_tu_persistence import (
    multi_tu_formal_editor_restore_reason,
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.mvp_multi_tu_runtime import GENERIC_MULTI_TU_WORKFLOW
from services.plant_project_draft_repository import PlantProjectDraftRepository


ROOT = Path(__file__).resolve().parents[1]
PATHWAY_SCENARIO = "metabolic_pathway_multi_tu_vector"
PATHWAY_WORKFLOW = "gate3_pathway"


def _completed_editor_result() -> dict[str, Any]:
    units = [{"unit_id": "TU1"}, {"unit_id": "TU2"}]
    backbone = {"asset_id": "pbi121_af485783_1", "normalized_sequence": "ACGT"}
    insertion = {
        "mode": "replacement",
        "start_coordinate": 4974,
        "end_coordinate": 7979,
        "insertion_orientation": "forward",
        "workflow_id": PATHWAY_WORKFLOW,
    }
    result = {
        "project_id": "generic-pathway-vector-route",
        "project_name": "Generic pathway vector route",
        "project_type": "dual_tu",
        "workflow_kind": PATHWAY_WORKFLOW,
        "input_signature": "final-plasmid-signature",
        "original_input": {
            "expression_units": units,
            "backbone": backbone,
            "insertion_settings": insertion,
        },
    }
    definition = {
        "project_name": result["project_name"],
        "plant_host": "Rice (O. sativa)",
    }
    pathway_steps = [{"step_id": "pathway-step-1"}, {"step_id": "pathway-step-2"}]
    result["formal_project_context"] = {
        "record_kind": RECORD_KIND_FORMAL_EDITOR_COMPLETED,
        "formal_editor_state_contract_version": FORMAL_EDITOR_STATE_CONTRACT_VERSION,
        "project_type": "dual_tu",
        "design_scenario": PATHWAY_SCENARIO,
        "current_step": 6,
        "pathway_steps": pathway_steps,
        "project_definition": definition,
        "formal_state": {
            "formal_project_type": "dual_tu",
            "formal_design_scenario": PATHWAY_SCENARIO,
            "formal_project_definition": dict(definition),
            "formal_pathway_steps": [dict(step) for step in pathway_steps],
            "formal_transcription_units": [dict(unit) for unit in units],
            "formal_backbone_record": dict(backbone),
            "formal_insertion_settings": dict(insertion),
            "formal_dual_tu_combined_result": {
                "project_id": result["project_id"],
                "input_signature": "combined-region-signature",
            },
            "mvp_project_id": result["project_id"],
            "mvp_current_input_signature": result["input_signature"],
        },
    }
    return result


def _prepare_open(state: dict[str, Any], result: Mapping[str, Any]) -> bool:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name == "_prepare_saved_multi_tu_open"
    )
    namespace = {"Any": Any, "Mapping": Mapping, "st": SimpleNamespace(session_state=state)}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace["_prepare_saved_multi_tu_open"](result)


def test_completed_gate3_pathway_record_opens_as_editor_and_clears_stale_state() -> None:
    reopened = _completed_editor_result()
    assert multi_tu_formal_editor_restore_reason(reopened) == ""
    reopened["formal_editor_restore_reason"] = ""
    reopened["formal_editor_restoration_eligible"] = True

    state = {
        "formal_explicit_historical_open": True,
        "formal_stale_from_previous_project": "remove",
        "mvp_project_id": "stale-project",
        "unrelated_state": "preserve",
    }
    assert _prepare_open(state, reopened) is True
    assert "formal_explicit_historical_open" not in state
    assert "formal_stale_from_previous_project" not in state
    assert "mvp_project_id" not in state
    assert state["unrelated_state"] == "preserve"


def test_legacy_multi_tu_result_remains_historical_read_only() -> None:
    result = _completed_editor_result()
    result["formal_project_context"].pop("record_kind")

    assert multi_tu_formal_editor_restore_reason(result) == "legacy_record"
    result["formal_editor_restoration_eligible"] = False
    state = {"formal_editor_widget": "stale"}
    assert _prepare_open(state, result) is False
    assert state == {"formal_explicit_historical_open": True}


def test_malformed_completed_editor_record_fails_closed() -> None:
    result = _completed_editor_result()
    del result["formal_project_context"]["formal_state"]["formal_backbone_record"]

    assert multi_tu_formal_editor_restore_reason(result) == "missing_formal_state"


def test_browser_shaped_record_uses_persisted_state_not_transient_confirmation_flags() -> None:
    result = _completed_editor_result()
    state = result["formal_project_context"]["formal_state"]

    assert "formal_step3_order_confirmation_recorded" not in state
    assert "formal_step4_strategy_confirmed" not in state
    assert "formal_step5_strategy_confirmed" not in state
    assert multi_tu_formal_editor_restore_reason(result) == ""

    state["formal_insertion_settings"]["start_coordinate"] = 4975
    assert multi_tu_formal_editor_restore_reason(result) == "state_canonical_mismatch"


def test_unrelated_supported_multi_tu_identity_is_not_broadened() -> None:
    result = _completed_editor_result()
    result["formal_project_context"]["design_scenario"] = "standard_plant_expression_vector"
    result["formal_project_context"]["formal_state"][
        "formal_design_scenario"
    ] = "standard_plant_expression_vector"
    result["workflow_kind"] = GENERIC_MULTI_TU_WORKFLOW

    assert multi_tu_formal_editor_restore_reason(result) == ""
    result["workflow_kind"] = PATHWAY_WORKFLOW
    assert multi_tu_formal_editor_restore_reason(result) == "state_canonical_mismatch"


def test_real_gate3_pathway_save_and_fresh_repository_reopen_is_editor_eligible(
    tmp_path: Path,
) -> None:
    from tests.test_generic_pathway_vector_route import _pathway_result

    result, _combined, _backbone = _pathway_result()
    context = dict(result["formal_project_context"])
    definition = {
        "project_name": result["project_name"],
        "plant_host": "Rice (O. sativa)",
    }
    context.update(
        {
            "record_kind": RECORD_KIND_FORMAL_EDITOR_COMPLETED,
            "formal_editor_state_contract_version": FORMAL_EDITOR_STATE_CONTRACT_VERSION,
            "project_definition": definition,
            "formal_state": {
                "formal_project_type": "dual_tu",
                "formal_design_scenario": PATHWAY_SCENARIO,
                "formal_project_definition": copy.deepcopy(definition),
                "formal_pathway_steps": copy.deepcopy(context["pathway_steps"]),
                "formal_transcription_units": copy.deepcopy(
                    result["original_input"]["expression_units"]
                ),
                "formal_backbone_record": copy.deepcopy(result["original_input"]["backbone"]),
                "formal_insertion_settings": copy.deepcopy(
                    result["original_input"]["insertion_settings"]
                ),
                "formal_dual_tu_combined_result": {
                    "project_id": result["project_id"],
                    "input_signature": result["combined_construct"]["input_signature"],
                },
                "mvp_project_id": result["project_id"],
                "mvp_current_input_signature": result["input_signature"],
            },
        }
    )
    result["formal_project_context"] = context
    repository = PlantProjectDraftRepository(tmp_path / "real-gate3-editor")

    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)

    assert reopened["formal_editor_restore_reason"] == ""
    assert reopened["formal_editor_restoration_eligible"] is True
    assert reopened["workflow_kind"] == PATHWAY_WORKFLOW
    assert reopened["complete_plasmid"]["total_length"] == 11819
    assert reopened["complete_plasmid"]["sequence_sha256"] == (
        "f6321f529bfbfb45de661476c62cf5a7a46446631e59954c5c97c70dd12f2e61"
    )
