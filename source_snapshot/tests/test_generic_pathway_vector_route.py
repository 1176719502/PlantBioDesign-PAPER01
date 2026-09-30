from __future__ import annotations

import ast
import copy
import json
from io import StringIO
from pathlib import Path

from Bio import SeqIO
import pytest

from core.pbi121_replacement_contract import (
    Pbi121ReplacementContractError,
    prepare_pbi121_backbone_record_for_replacement,
    replacement_contract,
)
from core.vector_asset_contracts_v1 import vector_asset_contract
from services.mvp_multi_tu_persistence import (
    open_mvp_multi_tu_design,
    save_mvp_multi_tu_design,
)
from services.mvp_multi_tu_runtime import (
    generate_admitted_multi_tu_complete_plasmid,
    generate_multi_tu_combined_construct,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.vector_asset_admission import (
    assess_vector_workflow,
    normalize_workflow_id,
    validate_vector_operation,
)
from services.vector_backbone_catalog import catalog_backbone_record, catalog_entries
ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
FIXTURE_PATH = ROOT / "tests" / "data" / "generic_pathway_vector_route_r3.json"
FIXTURE = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
PBI121_ASSET_ID = "pbi121_af485783_1"
PATHWAY_WORKFLOW = "gate3_pathway"
PATHWAY_SCENARIO = "metabolic_pathway_multi_tu_vector"


def _record(asset_id: str) -> dict:
    return catalog_backbone_record(asset_id, project_id=f"generic-pathway-{asset_id}")


def _genbank_text(record: object) -> str:
    output = StringIO()
    SeqIO.write(record, output, "genbank")
    return output.getvalue()


def _malformed_pbi121_record(*, forged_marker: bool) -> dict:
    malformed = copy.deepcopy(_record(PBI121_ASSET_ID))
    parsed = SeqIO.read(StringIO(malformed["original_text"]), "genbank")
    parsed.features = [
        feature
        for feature in parsed.features
        if "nptii"
        not in " ".join(
            str(value).lower()
            for values in feature.qualifiers.values()
            for value in values
        )
    ]
    malformed["original_text"] = _genbank_text(parsed)
    if forged_marker:
        malformed["pbi121_replacement_feature_projection"] = {
            "contract_version": "pbi121-exact-replacement-v1",
            "sequence_unchanged": True,
            "removed_feature_count": 4,
            "replacement_start": 4974,
            "replacement_end": 7979,
        }
    return malformed


def _pathway_result() -> tuple[dict, dict, dict]:
    combined = generate_multi_tu_combined_construct(
        project_id="generic-pathway-vector-route",
        project_name="Generic pathway vector route",
        expression_units=copy.deepcopy(FIXTURE["expression_units"]),
    )
    backbone = prepare_pbi121_backbone_record_for_replacement(_record(PBI121_ASSET_ID))
    assessment = assess_vector_workflow(backbone, workflow_id=PATHWAY_WORKFLOW)
    settings = {
        **assessment["canonical_settings"],
        "workflow_id": PATHWAY_WORKFLOW,
        "user_confirmation": True,
        "topology_confirmation": True,
    }
    result = generate_admitted_multi_tu_complete_plasmid(
        combined,
        backbone=backbone,
        insertion_settings=settings,
        workflow_id=PATHWAY_WORKFLOW,
    )
    result["project_type"] = "dual_tu"
    result["workflow_kind"] = PATHWAY_WORKFLOW
    result["topology"] = str(backbone.get("topology") or "")
    result["formal_project_context"] = {
        "project_type": "dual_tu",
        "design_scenario": PATHWAY_SCENARIO,
        "current_step": 6,
        "pathway_steps": copy.deepcopy(FIXTURE["pathway_steps"]),
        "pathway_mapping": {
            "mapping_complete": True,
            "mapped_unit_ids": ["TU1", "TU2"],
        },
        "source_backbone_length": 14758,
    }
    return result, combined, backbone


def _function_source(name: str) -> str:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


def test_workflow_identities_are_independent_and_legacy_gate3_stays_betalain_only() -> None:
    assert normalize_workflow_id(PATHWAY_WORKFLOW) == PATHWAY_WORKFLOW
    assert normalize_workflow_id("betalain_gate3") == "betalain_gate3"
    assert normalize_workflow_id("gate3") == "betalain_gate3"
    assert normalize_workflow_id("generic_multi_tu") == "generic_multi_tu"


@pytest.mark.parametrize(
    ("asset_id", "workflow_id", "allowed"),
    [
        (PBI121_ASSET_ID, PATHWAY_WORKFLOW, True),
        (PBI121_ASSET_ID, "betalain_gate3", True),
        (PBI121_ASSET_ID, "gate3", True),
        (PBI121_ASSET_ID, "generic_multi_tu", False),
        (PBI121_ASSET_ID, "single_gene", False),
        ("pcambia1300_af234296_1", PATHWAY_WORKFLOW, False),
        ("pbin19_u09365_1", PATHWAY_WORKFLOW, False),
        ("r229_local_example", PATHWAY_WORKFLOW, False),
    ],
)
def test_generic_pathway_admission_matrix_fails_closed(
    asset_id: str,
    workflow_id: str,
    allowed: bool,
) -> None:
    assert assess_vector_workflow(_record(asset_id), workflow_id=workflow_id)["allowed"] is allowed


def test_unknown_and_unsafe_uploaded_vectors_remain_blocked_for_generic_pathway() -> None:
    for record in (
        {"normalized_sequence": "ACGT", "topology": "circular"},
        {
            "normalized_sequence": "ACGT" * 40,
            "topology": "circular",
            "source_kind": "upload",
            "source_name": "unsafe.gb",
        },
    ):
        assert assess_vector_workflow(record, workflow_id=PATHWAY_WORKFLOW)["allowed"] is False


def test_pbi121_scientific_operation_contract_is_unchanged_and_coordinates_are_immutable() -> None:
    contract = vector_asset_contract(PBI121_ASSET_ID)
    legacy_contract = replacement_contract()
    assert contract["accession_version"] == legacy_contract["accession_version"] == "AF485783.1"
    assert contract["full_sequence_length"] == legacy_contract["full_sequence_length"] == 14758
    assert contract["full_sequence_sha256"] == legacy_contract["full_sequence_sha256"]
    assert contract["operation_region_sha256"] == legacy_contract["replacement_sha256"]
    assert contract["external_coordinate_contract"] == {
        "coordinate_system": "1-based inclusive",
        "start": 4974,
        "end": 7979,
    }
    assert contract["internal_coordinate_contract"] == {
        "coordinate_system": "0-based half-open",
        "start": 4973,
        "end": 7979,
    }
    assert contract["retained_features"] == [
        "nptII plant selection cassette",
        "T-DNA right border",
        "T-DNA left border",
        "bacterial replication regions",
    ]
    assert contract["protected_features"] == [
        "nptII plant selection cassette",
        "T-DNA right border",
        "T-DNA left border",
    ]
    backbone = _record(PBI121_ASSET_ID)
    exact = validate_vector_operation(
        backbone,
        workflow_id=PATHWAY_WORKFLOW,
        insertion_settings={
            "mode": "replacement",
            "start_coordinate": 4974,
            "end_coordinate": 7979,
            "insertion_orientation": "forward",
        },
    )
    tampered = validate_vector_operation(
        backbone,
        workflow_id=PATHWAY_WORKFLOW,
        insertion_settings={
            "mode": "replacement",
            "start_coordinate": 4973,
            "end_coordinate": 7979,
            "insertion_orientation": "forward",
        },
    )
    assert exact["allowed"] is True
    assert exact["canonical_settings"] == {
        "mode": "replacement",
        "start_coordinate": 4974,
        "end_coordinate": 7979,
        "insertion_orientation": "forward",
    }
    assert tampered["allowed"] is False


def test_pbi121_runtime_projection_removes_only_the_reviewed_replaced_features() -> None:
    original = _record(PBI121_ASSET_ID)
    prepared = prepare_pbi121_backbone_record_for_replacement(original)
    original_record = SeqIO.read(StringIO(original["original_text"]), "genbank")
    prepared_record = SeqIO.read(StringIO(prepared["original_text"]), "genbank")
    prepared_again = prepare_pbi121_backbone_record_for_replacement(prepared)
    assert str(prepared_record.seq).upper() == str(original_record.seq).upper()
    assert prepared_record.id == original_record.id == "AF485783.1"
    assert prepared_record.annotations["topology"] == original_record.annotations["topology"] == "circular"
    assert len(original_record.features) - len(prepared_record.features) == 4
    assert prepared["pbi121_replacement_feature_projection"] == {
        "contract_version": "pbi121-exact-replacement-v1",
        "sequence_unchanged": True,
        "removed_feature_count": 4,
        "replacement_start": 4974,
        "replacement_end": 7979,
    }
    assert prepared_again == prepared
    retained_qualifiers = " ".join(
        str(value)
        for feature in prepared_record.features
        for values in feature.qualifiers.values()
        for value in values
    )
    assert "nptII" in retained_qualifiers
    assert "T-DNA right border" in retained_qualifiers
    assert "T-DNA left border" in retained_qualifiers


@pytest.mark.parametrize("forged_marker", [False, True])
def test_malformed_retained_annotations_fail_closed_at_projection_and_admission(
    forged_marker: bool,
) -> None:
    malformed = _malformed_pbi121_record(forged_marker=forged_marker)
    with pytest.raises(Pbi121ReplacementContractError, match="retained and protected"):
        prepare_pbi121_backbone_record_for_replacement(malformed)
    assessment = validate_vector_operation(
        malformed,
        workflow_id=PATHWAY_WORKFLOW,
        insertion_settings={
            "mode": "replacement",
            "start_coordinate": 4974,
            "end_coordinate": 7979,
            "insertion_orientation": "forward",
        },
    )
    assert assessment["allowed"] is False
    assert "retained and protected" in assessment["reason"]


def test_pbi121_source_and_operation_region_sequence_drift_fail_closed() -> None:
    original = _record(PBI121_ASSET_ID)
    for index in (100, 5000):
        malformed = copy.deepcopy(original)
        sequence = list(malformed["normalized_sequence"])
        sequence[index] = "A" if sequence[index] != "A" else "C"
        malformed["normalized_sequence"] = "".join(sequence)
        with pytest.raises(Pbi121ReplacementContractError, match="SHA-256"):
            prepare_pbi121_backbone_record_for_replacement(malformed)


def test_generic_pathway_catalog_exposes_only_pbi121_as_selectable() -> None:
    entries = {row["asset_id"]: row for row in catalog_entries(PATHWAY_WORKFLOW)}
    assert entries[PBI121_ASSET_ID]["selectable"] is True
    assert entries[PBI121_ASSET_ID]["operation_label"] == "精确替换"
    assert {
        asset_id for asset_id, row in entries.items() if row["selectable"]
    } == {PBI121_ASSET_ID}


def test_generic_pathway_reuses_existing_builder_for_one_circular_canonical_plasmid() -> None:
    result, combined, backbone = _pathway_result()
    source = str(backbone["normalized_sequence"]).upper()
    insert = str(combined["combined_construct"]["dna"]).upper()
    canonical = str(result["complete_plasmid"]["dna"]).upper()
    assert canonical == source[:4973] + insert + source[7979:]
    assert len(canonical) == 14758 - 3006 + len(insert)
    assert result["topology"] == "circular"
    assert result["runtime"]["complete_plasmid_constructs"][0]["topology"] == "circular"
    assert source[2453:2478] in canonical  # RB
    assert source[2837:3632] in canonical  # nptII
    assert source[8620:8646] in canonical  # LB

    fasta = next(
        SeqIO.parse(StringIO(result["exports"]["complete_plasmid_fasta"]["data"]), "fasta")
    )
    genbank = next(
        SeqIO.parse(StringIO(result["exports"]["complete_plasmid_genbank"]["data"]), "genbank")
    )
    assert str(fasta.seq).upper() == str(genbank.seq).upper() == canonical
    assert genbank.annotations["topology"] == "circular"


def test_committed_acceptance_fixture_matches_independent_canonical_oracle() -> None:
    result, combined, backbone = _pathway_result()
    expected = FIXTURE["expected"]
    canonical = str(result["complete_plasmid"]["dna"]).upper()
    source = str(backbone["normalized_sequence"]).upper()
    insert = str(combined["combined_construct"]["dna"]).upper()
    assert FIXTURE["fixture_id"] == "generic-pathway-pbi121-r3"
    assert FIXTURE["workflow"] == PATHWAY_WORKFLOW
    assert len(FIXTURE["pathway_steps"]) == expected["tu_count"] == 2
    assert [step["mapped_unit_id"] for step in FIXTURE["pathway_steps"]] == ["TU1", "TU2"]
    assert len(insert) == expected["multi_tu_length"] == 67
    assert combined["combined_construct"]["sequence_sha256"] == expected["multi_tu_sha256"]
    assert canonical == source[:4973] + insert + source[7979:]
    assert len(canonical) == expected["final_plasmid_length"] == 11819
    assert result["complete_plasmid"]["sequence_sha256"] == expected["final_plasmid_sha256"]
    fasta = next(
        SeqIO.parse(StringIO(result["exports"]["complete_plasmid_fasta"]["data"]), "fasta")
    )
    genbank = next(
        SeqIO.parse(StringIO(result["exports"]["complete_plasmid_genbank"]["data"]), "genbank")
    )
    assert str(fasta.seq).upper() == canonical
    assert str(genbank.seq).upper() == canonical


def test_generic_pathway_save_and_fresh_repository_reopen_do_not_drift(tmp_path: Path) -> None:
    result, _combined, _backbone = _pathway_result()
    repository = PlantProjectDraftRepository(tmp_path / "generic-pathway-projects")
    saved = save_mvp_multi_tu_design(result, repository=repository)
    reopened = open_mvp_multi_tu_design(
        saved.project_id,
        repository=PlantProjectDraftRepository(repository.storage_dir),
    )

    assert reopened["workflow_kind"] == PATHWAY_WORKFLOW
    assert reopened["formal_project_context"] == result["formal_project_context"]
    assert reopened["formal_project_context"].get("replacement_strategy_id") in {None, ""}
    assert reopened["vector_asset_admission"]["allowed"] is True
    assert reopened["vector_asset_admission"]["workflow_id"] == PATHWAY_WORKFLOW
    assert reopened["original_input"]["backbone"] == result["original_input"]["backbone"]
    assert reopened["original_input"]["insertion_settings"] == result["original_input"]["insertion_settings"]
    assert reopened["runtime"] == result["runtime"]
    assert reopened["complete_plasmid"]["dna"] == result["complete_plasmid"]["dna"]
    assert reopened["complete_plasmid"]["sequence_sha256"] == result["complete_plasmid"]["sequence_sha256"]
    assert reopened["exports"] == result["exports"]


def test_formal_app_routes_generic_pathway_without_borrowing_betalain_identity() -> None:
    action_key_source = _function_source("_is_formal_action_widget_key")
    scenario_source = _function_source("_formal_design_scenario")
    active_workflow_source = _function_source("_active_backbone_workflow_id")
    status_source = _function_source("_formal_step_statuses")
    step4_source = _function_source("_render_step_4_backbone")
    step5_source = _function_source("_render_step_5_complete")
    generator_source = _function_source("_generate_dual_tu_complete_plasmid")
    assert 'r"catalog_select_.+|"' in action_key_source
    assert "formal_design_scenario_recorded" in scenario_source
    assert "formal_dual_tu_combined_result" in scenario_source
    assert 'return "gate3_pathway"' in active_workflow_source
    assert 'return "gate3"' in active_workflow_source
    assert "uses_multi_tu_assembly_gate" in status_source
    assert "_is_pathway_multi_tu_project()" in status_source
    assert 'state.get("formal_betalain_gate3_case")' in status_source
    assert 'workflow_id == "gate3_pathway"' in step4_source
    assert "confirm_pathway_backbone" in step4_source
    assert "replacement_strategy_id" not in step4_source
    assert "_is_pathway_multi_tu_project()" in step5_source
    assert "_generate_dual_tu_complete_plasmid(ds)" in step5_source
    assert 'result["workflow_kind"] = _active_backbone_workflow_id()' in generator_source
    assert "generate_admitted_multi_tu_complete_plasmid" in generator_source
