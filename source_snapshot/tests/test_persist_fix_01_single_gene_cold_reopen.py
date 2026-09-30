from __future__ import annotations

import ast
import hashlib
import json
import re
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from core.design_session import DesignSession
from services.formal_project_definition_lifecycle import (
    active_project_definition_summary,
    normalize_project_definition,
)
from services.formal_project_persistence import save_formal_project_draft
from services.plant_project_draft_repository import PlantProjectDraftRepository


ROOT = Path(__file__).resolve().parents[1]


def _app_runtime(state: dict[str, Any], controller: Any) -> dict[str, Any]:
    names = {
        "_formal_ui_signature",
        "_formal_step4_strategy_signature",
        "_formal_step_statuses",
        "_normalize_formal_current_step",
        "_is_formal_action_widget_key",
        "_restore_formal_workflow_draft",
    }
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    assert {node.name for node in nodes} == names
    namespace: dict[str, Any] = {
        "Any": Any,
        "Mapping": Mapping,
        "hashlib": hashlib,
        "json": json,
        "re": re,
        "st": SimpleNamespace(session_state=state),
        "PROJECT_TYPE_SINGLE_GENE": "single_gene",
        "PROJECT_TYPE_DUAL_TU": "dual_tu",
        "PAGE_DESIGN_WORKSPACE": "Six-Step Design Workspace",
        "_controller": lambda: controller,
        "_change_page": lambda _page: None,
        "_restore_formal_step3_generated_result": lambda: None,
        "_establish_workflow_baseline": lambda **_kwargs: None,
        "_host_supports_project_type": lambda _host, project_type: (
            project_type == "single_gene"
        ),
        "_formal_project_type": lambda: "single_gene",
        "_is_pathway_multi_tu_project": lambda: False,
        "_is_generic_multi_tu_workflow": lambda: False,
        "_is_multi_tu_expression_assembly": lambda _value: False,
    }
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / "app.py"), "exec"),
        namespace,
    )
    return namespace


def _definition() -> dict[str, str]:
    return normalize_project_definition(
        {
            "project_name": "PERSIST-FIX-01 SG USERSEQ",
            "plant_host": "Rice / Oryza sativa",
            "material": "seedling",
            "application_mode": "稳定遗传转化",
            "transient_expression_system": "尚未确定",
            "tissue_specificity_requirement": "无特定组织或器官限制",
            "tissue_target": "",
            "inducibility_requirement": "无特定诱导要求",
            "induction_notes": "",
            "localization_target": "",
        }
    )


def _step5_state(definition: dict[str, str]) -> dict[str, Any]:
    state: dict[str, Any] = {
        "formal_project_definition": deepcopy(definition),
        "formal_project_name": definition["project_name"],
        "formal_project_type": "single_gene",
        "formal_design_scenario": "standard_plant_expression_vector",
        "formal_cds_input": {"normalized_cds": "ATGAAATAA"},
        "formal_expression_cassette": {"findings": []},
        "formal_cassette_result": {
            "input_signature": "cassette-signature",
            "runtime": {"record_kind": "canonical_construct_runtime"},
        },
        "formal_cassette_input_signature": "cassette-signature",
        "formal_step3_order_confirmation_recorded": True,
        "formal_backbone_record": {
            "normalized_sequence": "ACGTACGT",
            "normalized_sequence_sha256": "backbone-signature",
        },
        "formal_insertion_settings": {
            "mode": "insertion",
            "start_coordinate": 4,
            "end_coordinate": 5,
            "t_dna_confirmation": {"status": "confirmed"},
            "t_dna_operation_validation": {
                "status": "pcambia1300_exact_insertion_applied",
                "allowed": True,
            },
        },
        "mvp_inputs_stale": False,
    }
    controller = SimpleNamespace(save=lambda _value: None)
    runtime = _app_runtime(state, controller)
    signature = runtime["_formal_step4_strategy_signature"]()
    state["formal_step4_strategy_confirmed"] = True
    state["formal_step4_strategy_signature"] = signature
    return state


def test_user_sequence_step4_confirmation_survives_equivalent_cold_hydration(
    tmp_path: Path,
) -> None:
    definition = _definition()
    saved_state = _step5_state(definition)
    repository = PlantProjectDraftRepository(tmp_path / "projects")
    persisted_definition = {
        **definition,
        "expression_target": "；".join(active_project_definition_summary(definition)),
    }
    saved = save_formal_project_draft(
        project_name=definition["project_name"],
        project_id="persist-fix-01-sg-userseq",
        workflow_type="single_gene",
        current_step=5,
        design_session=DesignSession(
            step=5,
            gene_name="USER_SEQUENCE_ASSISTED_CDS",
            original_seq="ATGAAATAA",
            host=definition["plant_host"],
            tag="No tag",
        ),
        formal_state=saved_state,
        project_definition=persisted_definition,
        repository=repository,
    )

    before_controller = SimpleNamespace(save=lambda _value: None)
    before_runtime = _app_runtime(saved_state, before_controller)
    before_statuses = before_runtime["_formal_step_statuses"]()
    saved_signature = saved_state["formal_step4_strategy_signature"]
    assert [row["done"] for row in before_statuses] == [True, True, True, True, False, False]
    assert before_runtime["_normalize_formal_current_step"](
        5, statuses=before_statuses
    ) == 5

    reopened_state: dict[str, Any] = {}
    reopened_controller = SimpleNamespace(saved=None)
    reopened_controller.save = lambda value: setattr(reopened_controller, "saved", value)
    reopened_runtime = _app_runtime(reopened_state, reopened_controller)
    reopened_runtime["_restore_formal_workflow_draft"](
        saved.project_id, repository=repository
    )

    reopened_statuses = reopened_runtime["_formal_step_statuses"]()
    assert reopened_state["formal_project_definition"] == definition
    assert "expression_target" not in reopened_state["formal_project_definition"]
    assert reopened_runtime["_formal_step4_strategy_signature"]() == saved_signature
    assert reopened_state["formal_step4_strategy_confirmed"] is True
    assert [row["done"] for row in reopened_statuses] == [
        True,
        True,
        True,
        True,
        False,
        False,
    ]
    assert reopened_controller.saved is not None
    assert reopened_runtime["_normalize_formal_current_step"](
        reopened_controller.saved.step, statuses=reopened_statuses
    ) == 5

    reopened_state["formal_project_definition"] = {
        **definition,
        "localization_target": "chloroplast",
    }
    changed_statuses = reopened_runtime["_formal_step_statuses"]()
    assert reopened_runtime["_formal_step4_strategy_signature"]() != saved_signature
    assert changed_statuses[3]["done"] is False
    assert reopened_runtime["_normalize_formal_current_step"](
        reopened_controller.saved.step, statuses=changed_statuses
    ) == 4


def test_single_gene_acceptance_requires_completed_step6_save_and_cold_reopen() -> None:
    source = (
        ROOT / "scripts" / "acceptance" / "run_formal_single_gene_blank_acceptance.py"
    ).read_text(encoding="utf-8")
    build = source.split("def _build_blank_single_gene", 1)[1].split(
        "def _download", 1
    )[0]

    assert build.index('"第六步：项目保存、结果审查与交付"') < build.index(
        '"保存项目"'
    )
    assert '"项目已保存，可从项目中心重新打开。"' in build
    assert '"确认 CDS 并继续"' in build
    assert '"保存 CDS 并继续"' not in build
    assert 'persisted.draft_status != "completed"' in source
    assert 'formal_context.get("record_kind") != "formal_editor_completed"' in source
    assert 'formal_state.get("formal_step4_strategy_confirmed")' in source
    assert 'formal_state.get("formal_step5_strategy_confirmed")' in source
    assert 'result["steps"]["complete_stop_before_cold_start"] = "passed"' in source
