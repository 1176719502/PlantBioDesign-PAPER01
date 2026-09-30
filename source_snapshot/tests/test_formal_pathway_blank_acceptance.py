from __future__ import annotations

import ast
import copy
from pathlib import Path

from scripts.acceptance.run_formal_pathway_blank_acceptance import (
    BROWSER_FIXTURE_CANONICAL_LENGTH,
    BROWSER_FIXTURE_CANONICAL_SHA256,
    GATE3_CDS_LENGTHS,
    GATE3_DISPLAY_ORDER,
    GATE3_ENZYMES,
    GATE3_ORIENTATIONS,
    GATE3_REPLACEMENT_STRATEGY,
    HOST_KEY,
    PROJECT_NAME,
    _pathway_export_evidence,
    FIXTURE_IDENTITY,
    LOCATOR_INVENTORY,
)
from services.betalain_pbi121_canonical_construct import (
    generate_betalain_pbi121_canonical_construct,
)
from services.gate3_pathway_mapping import (
    analyze_pathway_cds,
    apply_step_cds_to_unit,
    new_pathway_step,
    update_pathway_step,
)
from services.formal_editor_state_contract import (
    FORMAL_EDITOR_STATE_CONTRACT_VERSION,
    RECORD_KIND_FORMAL_EDITOR_COMPLETED,
)
from services.mvp_multi_tu_persistence import save_mvp_multi_tu_design
from services.plant_project_draft_repository import PlantProjectDraftRepository


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "acceptance"
    / "run_formal_pathway_blank_acceptance.py"
)


def _cds_sequence(unit: dict[str, object]) -> str:
    cds = dict(unit.get("cds") or {})
    analysis = dict(cds.get("cds_analysis") or {})
    return str(
        analysis.get("normalized_cds")
        or cds.get("raw_text")
        or cds.get("sequence")
        or ""
    )


def test_pathway_acceptance_evidence_covers_mapping_persistence_coordinates_and_exports(
    tmp_path: Path,
) -> None:
    result = generate_betalain_pbi121_canonical_construct(
        project_id="baseline01a-gate3-evidence",
        project_name=PROJECT_NAME,
        repeated_regulatory_confirmed=True,
    )
    result["workflow_kind"] = "gate3_pathway"
    context = dict(result["formal_project_context"])
    definition = {
        "project_name": result["project_name"],
        "plant_host": HOST_KEY,
    }
    context.update(
        {
            "record_kind": RECORD_KIND_FORMAL_EDITOR_COMPLETED,
            "formal_editor_state_contract_version": FORMAL_EDITOR_STATE_CONTRACT_VERSION,
            "project_type": "dual_tu",
            "current_step": 6,
            "project_definition": definition,
            "formal_state": {
                "formal_project_type": "dual_tu",
                "formal_design_scenario": "metabolic_pathway_multi_tu_vector",
                "formal_project_definition": copy.deepcopy(definition),
                "formal_pathway_steps": copy.deepcopy(context["pathway_steps"]),
                "formal_transcription_units": copy.deepcopy(
                    result["original_input"]["expression_units"]
                ),
                "formal_backbone_record": copy.deepcopy(
                    result["original_input"]["backbone"]
                ),
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

    storage = tmp_path / "drafts"
    repository = PlantProjectDraftRepository(storage)
    save_mvp_multi_tu_design(result, repository=repository)
    fasta_path = tmp_path / "complete.fasta"
    genbank_path = tmp_path / "complete.gb"
    fasta_path.write_text(result["exports"]["complete_plasmid_fasta"]["data"], encoding="utf-8")
    genbank_path.write_text(result["exports"]["complete_plasmid_genbank"]["data"], encoding="utf-8")

    evidence = _pathway_export_evidence(
        storage,
        fasta_path,
        genbank_path,
    )

    assert evidence["project_name"] == PROJECT_NAME
    assert evidence["host_key"] == HOST_KEY
    assert evidence["replacement_strategy_id"] == GATE3_REPLACEMENT_STRATEGY
    assert evidence["enzymes"] == GATE3_ENZYMES
    assert evidence["cds_lengths"] == GATE3_CDS_LENGTHS
    assert evidence["display_order"] == GATE3_DISPLAY_ORDER
    assert evidence["orientations"] == GATE3_ORIENTATIONS
    assert evidence["pathway_mapping_blocking_count"] == 0
    assert evidence["mapping_statuses"] == ["applied", "applied", "applied"]
    assert evidence["mapped_tu_orders"] == [1, 2, 3]
    assert evidence["validation_blocking_count"] == 0
    assert evidence["canonical_length"] == 18_841
    assert evidence["canonical_sha256"] == (
        "cdeb4ea329322b942472b38c44fcad9c11216cd1e3fd4b9540e28a37826e2dc7"
    )
    assert evidence["fasta_matches_canonical"] is True
    assert evidence["genbank_matches_canonical"] is True
    assert evidence["workflow_type"] == "gate3_pathway"
    assert evidence["workflow_kind"] == "betalain_gate3"
    assert evidence["completed_editor_record"] is True
    assert evidence["restored_step"] == 6
    assert len(set(evidence["unit_ids"])) == 3


def test_pathway_acceptance_script_uses_ui_without_test_only_or_direct_generator_helpers() -> None:
    tree = ast.parse(SCRIPT_PATH.read_text(encoding="utf-8"))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    imported_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert "test_only_three_step_fixture" not in called_names | imported_names
    assert "generate_betalain_pbi121_canonical_construct" not in called_names | imported_names


def test_current_generic_pathway_runner_inventory_and_sync_contract_are_explicit() -> None:
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert FIXTURE_IDENTITY == "GENERIC_USER_ENTERED_GATE3_PATHWAY"
    assert LOCATOR_INVENTORY["headings"]["home"] == "项目中心"
    assert LOCATOR_INVENTORY["step4_controls"]["pbi121_identity"] == "pBI121 / AF485783.1"
    assert "def _add_tu_and_prove_tu3" in source
    assert "expect(tu3).to_be_visible" in source
    assert "wait_for_timeout" not in source
    assert '"project_center_to_step6_gate3_completed_save"' in source
    assert "_reopen_from_home(page)" in source
    assert 'result["fasta_bytes_identical"]' in source
    assert 'result["genbank_bytes_identical"]' in source
    assert LOCATOR_INVENTORY["step6_controls"]["save_entry"] == "Step 6 保存项目"
    assert BROWSER_FIXTURE_CANONICAL_LENGTH == 11_849
    assert BROWSER_FIXTURE_CANONICAL_SHA256 == (
        "43f5c937a9298a85d1960b21d762b15a19876111c031950f6d3395efe649574f"
    )
    assert "_select_localized_streamlit_option" in source
    assert "_fill_project_name" in source


def test_historical_gate3_entrypoint_only_delegates_to_current_runner() -> None:
    alias_source = (SCRIPT_PATH.parent / "run_gate3_pathway_acceptance.py").read_text(
        encoding="utf-8"
    )
    assert "test_only_three_step_fixture" not in alias_source
    assert "植物表达载体设计" not in alias_source
    assert "确认并保存" not in alias_source
    assert "run_formal_pathway_blank_acceptance" in alias_source


def test_applied_pathway_step_can_be_remapped_and_reapplied_to_a_different_tu() -> None:
    units = [
        {
            "unit_id": "focused-tu-1",
            "display_name": "Focused TU 1",
            "order": 1,
            "orientation": "forward",
            "cds": {},
        },
        {
            "unit_id": "focused-tu-2",
            "display_name": "Focused TU 2",
            "order": 2,
            "orientation": "reverse",
            "cds": {
                "sequence": "ATGAAACCCGGGTAG",
            },
        },
    ]
    step = new_pathway_step(step_id="focused-remap-step")
    step.update(
        {
            "step_name": "Focused remap step",
            "enzyme_name": "Focused remap enzyme",
            "cds_source_type": "test_only_asset",
            "cds_source_reference": "existing focused repository fixture",
            "mapped_unit_id": "focused-tu-1",
        }
    )
    step.update(
        analyze_pathway_cds(
            "ATGGCTGCTTAA",
            source_type="test_only_asset",
            source_reference="existing focused repository fixture",
        )
    )
    applied_steps, applied_units = apply_step_cds_to_unit([step], units, step["step_id"])
    assert applied_steps[0]["applied_to_unit"] is True

    remapped_steps = update_pathway_step(
        applied_steps,
        step["step_id"],
        mapped_unit_id="focused-tu-2",
    )
    assert remapped_steps[0]["applied_to_unit"] is False
    assert remapped_steps[0]["mapping_status"] == "mapped_pending_application"

    reapplied_steps, reapplied_units = apply_step_cds_to_unit(
        remapped_steps,
        applied_units,
        step["step_id"],
    )
    assert reapplied_steps[0]["applied_to_unit"] is True
    assert reapplied_steps[0]["mapped_unit_id"] == "focused-tu-2"
    assert _cds_sequence(reapplied_units[1]) == "ATGGCTGCTTAA"
