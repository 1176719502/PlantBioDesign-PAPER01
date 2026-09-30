from __future__ import annotations

import json
import os
import subprocess
import sys
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.design_session import DesignSession
from core.i18n import translate
from services.formal_project_persistence import WORKFLOW_GATE3_PATHWAY, save_formal_project_draft
from services.betalain_pbi121_canonical_construct import generate_betalain_pbi121_canonical_construct
from services.gate3_pathway_mapping import (
    SCENARIO_PATHWAY_MULTI_TU,
    SCENARIO_STANDARD,
    add_pathway_step,
    analyze_pathway_cds,
    apply_step_cds_to_unit,
    build_pathway_traceability_rows,
    delete_pathway_step,
    move_pathway_step,
    normalize_design_scenario,
    normalize_pathway_steps,
    new_pathway_step,
    test_only_three_step_fixture,
    update_pathway_step,
    validate_pathway_mapping,
)
from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design, save_mvp_multi_tu_design
from services.plant_project_draft_repository import PlantProjectDraftRepository
from tests.test_mvp9_multi_tu_runtime import DATA, _generate


ROOT = Path(__file__).resolve().parents[1]


class _SessionState(dict):
    pass


class _FakeStreamlit:
    def __init__(self, state: dict) -> None:
        self.session_state = _SessionState(state)


def _load_app_functions(*names: str, st: _FakeStreamlit) -> dict:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    required_names = {
        *names,
        "_plant_host_records",
        "_plant_host_storage_value",
        "_plant_host_record",
    }
    selected = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in required_names
    ]
    namespace = {
        "Any": object,
        "st": st,
        "_is_pathway_multi_tu_project": lambda: True,
        "GATE3_PATHWAY_DRAFT_KEY": "gate3_pathway_draft",
        "GATE3_PATHWAY_DRAFT_SCHEMA_VERSION": "v1",
        "PROJECT_TYPE_DUAL_TU": "dual_tu",
        "PAGE_DESIGN_WORKSPACE": "Six-Step Design Workspace",
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), "app.py", "exec"), namespace)
    return namespace


def _units() -> list[dict]:
    return [
        {"unit_id": "TU1", "display_name": "TU 1", "order": 1, "orientation": "forward", "cds": {}},
        {"unit_id": "TU2", "display_name": "TU 2", "order": 2, "orientation": "reverse", "cds": {}},
        {"unit_id": "TU3", "display_name": "TU 3", "order": 3, "orientation": "forward", "cds": {}},
    ]


def _applied_fixture() -> tuple[list[dict], list[dict]]:
    steps = test_only_three_step_fixture()
    units = _units()
    for step in list(steps):
        steps, units = apply_step_cds_to_unit(steps, units, step["step_id"])
    return steps, units


def test_selected_tu_survives_mapping_normalization_rerun() -> None:
    step = new_pathway_step(step_id="selector-normalization-step")
    selected = update_pathway_step(
        [step],
        step["step_id"],
        mapped_unit_id="TU1",
    )
    rerun_state = normalize_pathway_steps(selected)

    assert rerun_state[0]["mapped_unit_id"] == "TU1"
    assert rerun_state[0]["applied_to_unit"] is False
    assert rerun_state[0]["mapping_status"] == "mapped_pending_application"


def test_pending_mapping_status_copy_identifies_the_selected_tu_transition() -> None:
    assert translate("v1.expression.mapping_status_pending", language="zh-CN") == (
        "已选择 TU，待应用 CDS"
    )
    assert translate("v1.expression.mapping_status_pending", language="en") == (
        "TU selected, CDS pending application"
    )


def test_persisted_selection_can_advance_only_through_validated_cds_application() -> None:
    step = new_pathway_step(step_id="selector-apply-step")
    step.update(
        {
            "step_name": "Selector apply step",
            "enzyme_name": "Selector apply enzyme",
            "cds_source_type": "test_only_asset",
            "cds_source_reference": "TEST_ONLY selector fixture",
            "mapped_unit_id": "TU1",
        }
    )
    step.update(
        analyze_pathway_cds(
            "ATGGCTGCTTAA",
            source_type="test_only_asset",
            source_reference="TEST_ONLY selector fixture",
        )
    )
    pending = validate_pathway_mapping([step], _units())
    assert pending["mapping_complete"] is True
    assert pending["pathway_steps"][0]["mapping_status"] == "mapped_pending_application"

    applied_steps, applied_units = apply_step_cds_to_unit(
        pending["pathway_steps"],
        _units(),
        step["step_id"],
    )

    assert applied_steps[0]["applied_to_unit"] is True
    assert applied_steps[0]["mapping_status"] == "applied"
    assert applied_units[0]["cds"]["raw_text"] == "ATGGCTGCTTAA"


def test_selected_tu_does_not_bypass_incomplete_mapping() -> None:
    step = new_pathway_step(step_id="selector-invalid-step")
    step["mapped_unit_id"] = "TU1"
    validation = validate_pathway_mapping([step], _units())

    assert validation["mapping_complete"] is False
    assert validation["pathway_steps"][0]["mapping_status"] == "blocked"
    assert any(item["rule_id"] == "missing_cds" for item in validation["blocking_items"])


def test_semantic_mapping_change_invalidates_downstream_application_confirmation() -> None:
    steps, units = _applied_fixture()
    changed = update_pathway_step(
        steps,
        steps[0]["step_id"],
        mapped_unit_id="TU2",
    )

    assert changed[0]["applied_to_unit"] is False
    assert changed[0]["mapping_status"] == "mapped_pending_application"
    validation = validate_pathway_mapping(changed, units)
    assert validation["pathway_steps"][0]["mapping_status"] == "blocked"
    assert any(item["rule_id"] == "shared_transcription_unit" for item in validation["blocking_items"])
    assert validation["mapping_complete"] is False


def test_legacy_scenario_maps_to_standard_and_fixture_has_three_stable_distinct_steps() -> None:
    assert normalize_design_scenario(None) == SCENARIO_STANDARD
    assert normalize_design_scenario(SCENARIO_PATHWAY_MULTI_TU) == SCENARIO_PATHWAY_MULTI_TU
    steps = test_only_three_step_fixture()
    assert len(steps) == 3
    assert [step["display_order"] for step in steps] == [1, 2, 3]
    assert len({step["step_id"] for step in steps}) == 3
    assert len({step["cds_sequence"] for step in steps}) == 3
    assert all(step["cds_source_type"] == "test_only_asset" for step in steps)
    assert all(not step["cds_source_reference"].startswith("ACC") for step in steps)


def test_add_move_delete_keeps_step_identity_and_one_step_minimum() -> None:
    steps = test_only_three_step_fixture()
    step_ids = [step["step_id"] for step in steps]
    expanded = add_pathway_step(steps)
    assert len(expanded) == 4
    moved = move_pathway_step(expanded, step_ids[2], -2)
    assert moved[0]["step_id"] == step_ids[2]
    assert set(step_ids).issubset({step["step_id"] for step in moved})
    trimmed = delete_pathway_step(moved, moved[-1]["step_id"])
    assert [step["display_order"] for step in trimmed] == list(range(1, len(trimmed) + 1))
    with pytest.raises(ValueError, match="At least one"):
        delete_pathway_step([trimmed[0]], trimmed[0]["step_id"])


def test_cds_validation_reuses_existing_rules_and_manual_source_gap_is_review_item() -> None:
    steps = test_only_three_step_fixture()
    invalid = update_pathway_step(steps, steps[0]["step_id"], cds_sequence="ATGBCTAA")
    invalid_validation = validate_pathway_mapping(invalid, _units())
    assert any(item["rule_id"] == "invalid_cds" for item in invalid_validation["blocking_items"])

    missing_source = update_pathway_step(
        steps,
        steps[0]["step_id"],
        cds_source_reference="",
    )
    source_validation = validate_pathway_mapping(missing_source, _units())
    assert any(item["rule_id"] == "incomplete_cds_source" for item in source_validation["manual_review_items"])


def test_apply_to_distinct_tus_preserves_non_cds_roles_and_hashes_match() -> None:
    units = _units()
    units[0]["promoter"] = {"raw_text": "AAAA", "display_name": "Promoter"}
    units[0]["3_prime_regulatory_region"] = {"raw_text": "TTTT", "display_name": "3 prime"}
    steps = test_only_three_step_fixture()
    for step in list(steps):
        steps, units = apply_step_cds_to_unit(steps, units, step["step_id"])

    validation = validate_pathway_mapping(steps, units)
    assert validation["mapping_complete"] is True
    assert [step["mapping_status"] for step in validation["pathway_steps"]] == ["applied", "applied", "applied"]
    assert units[0]["promoter"]["raw_text"] == "AAAA"
    assert units[0]["3_prime_regulatory_region"]["raw_text"] == "TTTT"
    assert {unit["cds"]["raw_text"] for unit in units} == {step["cds_sequence"] for step in steps}


def test_cds_edit_after_apply_causes_pending_apply_then_hash_mismatch_if_marked_applied() -> None:
    steps, units = _applied_fixture()
    changed = update_pathway_step(steps, steps[1]["step_id"], cds_sequence="ATGCCCCCCTAA")
    validation = validate_pathway_mapping(changed, units)
    assert validation["pathway_steps"][1]["mapping_status"] == "mapped_pending_application"
    changed[1]["applied_to_unit"] = True
    mismatch = validate_pathway_mapping(changed, units)
    assert any(item["rule_id"] == "applied_cds_hash_mismatch" for item in mismatch["blocking_items"])


def test_dangling_duplicate_identity_and_shared_tu_are_respectively_blocking_or_review() -> None:
    steps, units = _applied_fixture()
    dangling = deepcopy(steps)
    dangling[1]["mapped_unit_id"] = "deleted-tu"
    dangling_validation = validate_pathway_mapping(dangling, units)
    assert any(item["rule_id"] == "dangling_mapped_unit" for item in dangling_validation["blocking_items"])

    duplicate = deepcopy(steps)
    duplicate[1]["step_id"] = duplicate[0]["step_id"]
    duplicate_validation = validate_pathway_mapping(duplicate, units)
    assert any(item["rule_id"] == "duplicate_step_id" for item in duplicate_validation["blocking_items"])

    shared = deepcopy(steps)
    shared[1]["mapped_unit_id"] = shared[0]["mapped_unit_id"]
    shared[1]["applied_to_unit"] = False
    shared_validation = validate_pathway_mapping(shared, units)
    assert any(item["rule_id"] == "shared_transcription_unit" for item in shared_validation["manual_review_items"])
    assert any(item["rule_id"] == "shared_transcription_unit" for item in shared_validation["blocking_items"])
    assert shared_validation["mapping_complete"] is False
    assert all(step["mapping_status"] == "blocked" for step in shared_validation["pathway_steps"][:2])

    with pytest.raises(ValueError, match="blocking mapping items"):
        apply_step_cds_to_unit(shared_validation["pathway_steps"], units, shared[0]["step_id"])

    one_to_many = deepcopy(steps)
    one_to_many[0]["mapped_unit_id"] = ["TU1", "TU2"]
    many_validation = validate_pathway_mapping(one_to_many, units)
    assert any(item["rule_id"] == "multiple_mapped_units" for item in many_validation["blocking_items"])


@pytest.mark.parametrize(
    "mapped_unit_id, expected_rule",
    [
        ("", "missing_mapped_unit"),
        ("deleted-tu", "dangling_mapped_unit"),
        ("unrelated-tu", "dangling_mapped_unit"),
    ],
)
def test_missing_or_unrelated_transcription_unit_selection_is_blocked(
    mapped_unit_id: str, expected_rule: str
) -> None:
    steps = test_only_three_step_fixture()
    steps[0]["mapped_unit_id"] = mapped_unit_id
    validation = validate_pathway_mapping(steps, _units())

    assert validation["mapping_complete"] is False
    assert any(item["rule_id"] == expected_rule for item in validation["blocking_items"])
    assert validation["pathway_steps"][0]["mapping_status"] == "blocked"


def test_nonblocking_manual_review_does_not_override_a_structurally_valid_mapping() -> None:
    steps = test_only_three_step_fixture()
    steps[0]["cds_source_reference"] = ""
    validation = validate_pathway_mapping(steps, _units())

    assert any(item["rule_id"] == "incomplete_cds_source" for item in validation["manual_review_items"])
    assert not any(item["rule_id"] == "incomplete_cds_source" for item in validation["blocking_items"])
    assert validation["mapping_complete"] is True


def test_valid_distinct_reviewed_mapping_remains_navigation_and_application_eligible() -> None:
    steps = test_only_three_step_fixture()
    validation = validate_pathway_mapping(steps, _units())

    assert validation["mapping_complete"] is True
    assert not validation["blocking_items"]
    assert all(step["mapping_status"] == "mapped_pending_application" for step in validation["pathway_steps"])
    applied_steps, applied_units = apply_step_cds_to_unit(validation["pathway_steps"], _units(), steps[0]["step_id"])
    assert applied_steps[0]["mapping_status"] == "applied"
    assert applied_units[0]["cds"]["raw_text"] == steps[0]["cds_sequence"]


def test_result_traceability_hides_ids_and_reports_tu_direction_and_review() -> None:
    steps, units = _applied_fixture()
    rows = build_pathway_traceability_rows(steps, units)
    assert len(rows) == 3
    assert rows[1]["transcription_unit_order"] == 2
    assert rows[1]["orientation"] == "reverse"
    assert "step_id" not in rows[0]
    assert "cds_sequence_sha256" not in rows[0]


def test_multi_tu_save_and_cold_reopen_preserve_optional_pathway_context(tmp_path: Path) -> None:
    result = _generate(DATA["cases"][0])
    result["project_type"] = "dual_tu"
    steps, units = _applied_fixture()
    result["formal_project_context"] = {
        "project_type": "dual_tu",
        "design_scenario": SCENARIO_PATHWAY_MULTI_TU,
        "pathway_steps": steps,
        "pathway_mapping": validate_pathway_mapping(steps, units),
        "current_step": 6,
    }
    repo = PlantProjectDraftRepository(tmp_path / "pathway-cold-start")
    saved = save_mvp_multi_tu_design(result, repository=repo)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repo)
    context = reopened["formal_project_context"]
    assert context["design_scenario"] == SCENARIO_PATHWAY_MULTI_TU
    assert [step["step_id"] for step in context["pathway_steps"]] == [step["step_id"] for step in steps]
    assert [step["cds_sequence"] for step in context["pathway_steps"]] == [step["cds_sequence"] for step in steps]

    command = (
        "from services.mvp_multi_tu_persistence import open_mvp_multi_tu_design; "
        f"r=open_mvp_multi_tu_design({saved.project_id!r}); "
        "import json; c=r['formal_project_context']; print(json.dumps({'scenario':c['design_scenario'],"
        "'ids':[s['step_id'] for s in c['pathway_steps']], 'units':[s['mapped_unit_id'] for s in c['pathway_steps']]}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", command],
        cwd=ROOT,
        env={**os.environ, "BIODESIGN_PLANT_PROJECT_DRAFT_DIR": str(repo.storage_dir)},
        check=True,
        capture_output=True,
        text=True,
    )
    cold = json.loads(completed.stdout.strip())
    assert cold["scenario"] == SCENARIO_PATHWAY_MULTI_TU
    assert cold["ids"] == [step["step_id"] for step in steps]
    assert cold["units"] == ["TU1", "TU2", "TU3"]


def test_blank_gate3_pathway_draft_uses_project_repository_and_restores_mapping(tmp_path: Path) -> None:
    steps, units = _applied_fixture()
    definition = {
        "project_name": "Gate 3 blank pathway draft",
        "plant_host": "Rice (O. sativa)",
        "material": "",
        "application_mode": "尚未确定",
        "transient_expression_system": "尚未确定",
        "tissue_specificity_requirement": "无特定组织或器官限制",
        "tissue_target": "",
        "inducibility_requirement": "无特定诱导要求",
        "induction_notes": "",
        "localization_target": "",
        "compatibility_review_required": "false",
        "legacy_application_mode": "",
        "legacy_expression_mode": "",
    }
    repository = PlantProjectDraftRepository(tmp_path / "blank-gate3-pathway")
    saving_streamlit = _FakeStreamlit(
        {
            "formal_project_name": definition["project_name"],
            "formal_pathway_steps": steps,
            "formal_transcription_units": units,
        }
    )
    save_functions = _load_app_functions("_save_gate3_pathway_draft", st=saving_streamlit)
    save_functions.update(
        {
            "_refresh_pathway_mapping_status": lambda: validate_pathway_mapping(steps, units),
            "_formal_project_definition": lambda: definition,
            "_project_definition_expression_target": lambda value: value["application_mode"],
            "_formal_design_scenario": lambda: SCENARIO_PATHWAY_MULTI_TU,
            "_transcription_units": lambda: units,
            "_save_current_formal_draft": lambda **kwargs: save_formal_project_draft(
                project_name=definition["project_name"],
                project_id="",
                workflow_type=WORKFLOW_GATE3_PATHWAY,
                current_step=kwargs["current_step"],
                design_session=DesignSession(step=2, host=definition["plant_host"]),
                formal_state={
                    "formal_project_name": definition["project_name"],
                    "formal_pathway_steps": steps,
                    "formal_transcription_units": units,
                },
                project_definition={
                    **definition,
                    "expression_target": definition["application_mode"],
                },
                manual_state_updates=kwargs["manual_state_updates"],
                repository=kwargs["repository"],
            ),
        }
    )

    saved = save_functions["_save_gate3_pathway_draft"](repository)
    cold_repository = PlantProjectDraftRepository(repository.storage_dir)
    persisted = cold_repository.load(saved.project_id)
    payload = persisted.manual_review_state["gate3_pathway_draft"]
    assert payload["project_type"] == "dual_tu"
    assert payload["design_scenario"] == SCENARIO_PATHWAY_MULTI_TU
    assert payload["project_definition"]["project_name"] == definition["project_name"]
    assert payload["project_definition"]["plant_host"] == definition["plant_host"]
    assert payload["pathway_steps"] == steps
    assert payload["transcription_units"] == units

    reopened_streamlit = _FakeStreamlit({})
    controller_state: list[object] = []
    page_state: list[str] = []
    restore_functions = _load_app_functions("_restore_gate3_pathway_draft", st=reopened_streamlit)
    restore_functions.update(
        {
            "_normalize_transcription_units": lambda value: value,
            "_invalidate_formal_snapshots": lambda: None,
            "_project_definition_expression_target": lambda value: value["application_mode"],
            "_controller": lambda: SimpleNamespace(save=controller_state.append),
            "_change_page": page_state.append,
        }
    )
    restore_functions["_restore_gate3_pathway_draft"](saved.project_id, cold_repository)

    state = reopened_streamlit.session_state
    assert state["formal_project_type"] == "dual_tu"
    assert state["formal_design_scenario"] == SCENARIO_PATHWAY_MULTI_TU
    assert state["formal_project_name"] == definition["project_name"]
    assert state["formal_project_host"] == definition["plant_host"]
    assert state["formal_pathway_steps"] == steps
    assert state["formal_transcription_units"] == units
    assert controller_state[0].step == 2
    assert page_state == ["Six-Step Design Workspace"]


def test_editing_pathway_mapping_invalidates_exports_then_regeneration_persists_new_mapping(
    tmp_path: Path,
) -> None:
    result = generate_betalain_pbi121_canonical_construct(
        project_id="gate3-edit-invalidation",
        project_name="Gate 3 edit invalidation",
        repeated_regulatory_confirmed=True,
    )
    steps = deepcopy(result["formal_project_context"]["pathway_steps"])
    original_enzyme = steps[0]["enzyme_name"]
    replacement_enzyme = f"{original_enzyme} (edited record)"
    exports = result["exports"]
    assert result["complete_plasmid"]["dna"]
    assert result["formal_project_context"]["pathway_mapping"]["mapping_complete"] is True
    assert result["complete_plasmid"]["validation_summary"]["blocking_count"] == 0
    assert exports["complete_plasmid_fasta"]["data"]
    assert exports["complete_plasmid_genbank"]["data"]

    fake_st = _FakeStreamlit(
        {
            "formal_pathway_steps": steps,
            "formal_dual_tu_combined_result": result,
            "formal_cassette_result": result,
            "formal_cassette_exports": result.get("cassette_exports", {}),
            "formal_cassette_input_signature": result["input_signature"],
            "mvp_vector_result": result,
            "mvp_current_input_signature": result["input_signature"],
            "mvp_inputs_stale": False,
        }
    )
    functions = _load_app_functions(
        "_store_pathway_steps",
        "_invalidate_dual_tu_outputs",
        st=fake_st,
    )
    edited = update_pathway_step(
        steps,
        steps[0]["step_id"],
        enzyme_name=replacement_enzyme,
    )
    functions["_store_pathway_steps"](edited)

    assert fake_st.session_state["mvp_inputs_stale"] is True
    assert "mvp_vector_result" not in fake_st.session_state
    assert "formal_dual_tu_combined_result" not in fake_st.session_state
    assert "formal_cassette_result" not in fake_st.session_state
    assert "formal_cassette_exports" not in fake_st.session_state
    assert "mvp_current_input_signature" not in fake_st.session_state

    regenerated = generate_betalain_pbi121_canonical_construct(
        project_id="gate3-edit-invalidation-regenerated",
        project_name="Gate 3 edit invalidation regenerated",
        repeated_regulatory_confirmed=True,
    )
    regenerated_context = dict(regenerated["formal_project_context"])
    regenerated_context["pathway_steps"] = edited
    regenerated_context["pathway_mapping"] = validate_pathway_mapping(
        edited,
        list((regenerated.get("original_input") or {}).get("expression_units") or []),
    )
    regenerated["formal_project_context"] = regenerated_context
    assert build_pathway_traceability_rows(
        regenerated_context["pathway_steps"],
        list((regenerated.get("original_input") or {}).get("expression_units") or []),
    )[0]["enzyme_name"] == replacement_enzyme

    repo = PlantProjectDraftRepository(tmp_path / "edited-pathway-cold-start")
    saved = save_mvp_multi_tu_design(regenerated, repository=repo)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repo)
    assert reopened["formal_project_context"]["pathway_steps"][0]["enzyme_name"] == replacement_enzyme
    assert reopened["exports"]["complete_plasmid_fasta"]["data"]
    assert reopened["exports"]["complete_plasmid_genbank"]["data"]


def test_formal_app_wires_pathway_scenario_into_step_two_save_restore_and_results_tracking() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert '"metabolic_pathway_multi_tu_vector"' in source
    assert "def _render_pathway_mapping_step_2" in source
    assert "v1.expression.step_2_pathway_step_cds_mapping" in source
    assert "v1.expression.applied_pathway_step_configuration" in source
    assert "def _restore_dual_tu_result" in source
    assert 'context.get("pathway_steps")' in source
    assert "v1.results_final_report.pathway_step_transcription_unit_tracing" in source
    assert '"pathway_steps": pathway_mapping["pathway_steps"]' in source
