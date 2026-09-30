from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from Bio import SeqIO

from services.betalain_three_enzyme_gate3_case import (
    CASE_ROOT,
    BetalainThreeEnzymeCaseError,
    MANIFEST_PATH,
    PROJECT_NAME,
    apply_betalain_case_to_units,
    evaluate_real_component_asset_gate,
    load_betalain_three_enzyme_case,
    open_betalain_gate3_mapping,
    save_betalain_gate3_mapping,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.project_lifecycle import ProjectLifecycleService


ROOT = Path(__file__).resolve().parents[1]


def _units() -> list[dict]:
    return [
        {"unit_id": "TU1", "display_name": "TU1", "order": 1, "orientation": "forward", "promoter": {}, "cds": {}, "3_prime_regulatory_region": {}},
        {"unit_id": "TU2", "display_name": "TU2", "order": 2, "orientation": "forward", "promoter": {}, "cds": {}, "3_prime_regulatory_region": {}},
        {"unit_id": "TU3", "display_name": "TU3", "order": 3, "orientation": "forward", "promoter": {}, "cds": {}, "3_prime_regulatory_region": {}},
    ]


def test_official_records_are_feature_extracted_and_manifested_exactly() -> None:
    case = load_betalain_three_enzyme_case()
    assert [record["version"] for record in case["cds_records"]] == ["HQ656023.1", "HQ656027.1", "AB182643.1"]
    assert [(record["cds_length"], record["protein_length"]) for record in case["cds_records"]] == [(1494, 497), (828, 275), (1503, 500)]
    assert all(record["contains_start_codon"] and record["contains_terminal_stop_codon"] for record in case["cds_records"])
    assert all(record["length_multiple_of_three"] and not record["internal_stop_codon_positions"] for record in case["cds_records"])
    assert all(record["translation_matches_record"] and record["verification_status"] == "passed" for record in case["cds_records"])
    assert all(set(record["cds_sequence"]) <= set("ATCG") for record in case["cds_records"])
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert all(
        {"accession", "version", "organism", "record_title", "gene", "product", "cds_coordinates", "cds_length", "protein_length", "cds_sha256", "source_record_sha256", "fetched_from", "fetched_date", "extraction_method", "verification_status", "manual_review_notes"} <= set(record)
        for record in manifest["cds_records"]
    )
    for source in case["cds_records"]:
        fasta = SeqIO.read(CASE_ROOT / source["extracted_fasta_path"], "fasta")
        assert str(fasta.seq).upper() == source["cds_sequence"]


def test_exact_public_cds_apply_to_tu1_tu2_tu3_without_rewrite() -> None:
    case = load_betalain_three_enzyme_case()
    steps, units, mapping = apply_betalain_case_to_units(_units())
    assert mapping["mapping_complete"] is True
    assert [step["mapped_unit_id"] for step in steps] == ["TU1", "TU2", "TU3"]
    assert [step["cds_source_reference"] for step in steps] == ["HQ656023.1", "HQ656027.1", "AB182643.1"]
    assert [unit["cds"]["raw_text"] for unit in units] == [record["cds_sequence"] for record in case["cds_records"]]
    assert [step["cds_sequence_sha256"] for step in steps] == [record["cds_sha256"] for record in case["cds_records"]]
    assert all(step["cds_analysis"]["normalized_cds"] == step["cds_sequence"] for step in steps)
    assert all(not step["cds_analysis"]["blocking"] for step in steps)


def test_real_asset_gate_stops_before_complete_vector_generation() -> None:
    gate = evaluate_real_component_asset_gate()
    assert gate["complete_vector_allowed"] is False
    assert {item["asset_type"] for item in gate["missing_assets"]} == {"promoter", "terminator", "plasmid_backbone", "LB/RB/T-DNA record"}
    assert not gate["usable_assets"]


def test_saved_mapping_survives_cold_start_without_complete_plasmid(tmp_path: Path) -> None:
    steps, units, _mapping = apply_betalain_case_to_units(_units())
    repo = PlantProjectDraftRepository(tmp_path / "betalain-gate3")
    saved = save_betalain_gate3_mapping(pathway_steps=steps, transcription_units=units, repository=repo)
    assert saved.project_name == PROJECT_NAME
    reopened = open_betalain_gate3_mapping(saved.project_id, repository=repo)
    assert reopened["complete_vector_generated"] is False
    assert [step["cds_source_reference"] for step in reopened["pathway_steps"]] == ["HQ656023.1", "HQ656027.1", "AB182643.1"]
    assert [unit["cds"]["raw_text"] for unit in reopened["transcription_units"]] == [step["cds_sequence"] for step in steps]

    command = (
        "from services.betalain_three_enzyme_gate3_case import open_betalain_gate3_mapping; "
        f"r=open_betalain_gate3_mapping({saved.project_id!r}); "
        "import json; print(json.dumps({'accessions':[s['cds_source_reference'] for s in r['pathway_steps']],"
        "'units':[s['mapped_unit_id'] for s in r['pathway_steps']], 'complete':r['complete_vector_generated']}))"
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
    assert cold == {"accessions": ["HQ656023.1", "HQ656027.1", "AB182643.1"], "units": ["TU1", "TU2", "TU3"], "complete": False}


@pytest.mark.parametrize("status", ["archived", "invalid"])
def test_gate3_case_open_rejects_non_active_records(tmp_path: Path, status: str) -> None:
    steps, units, _mapping = apply_betalain_case_to_units(_units())
    repository = PlantProjectDraftRepository(tmp_path / "betalain-gate3")
    saved = save_betalain_gate3_mapping(
        pathway_steps=steps,
        transcription_units=units,
        repository=repository,
    )
    if status == "archived":
        ProjectLifecycleService(json_repository=repository).archive_project(saved.project_id, backend="json")
    else:
        path = repository.storage_dir / f"{saved.project_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["lifecycle_status"] = "invalid"
        path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BetalainThreeEnzymeCaseError, match="does not allow editing or saving"):
        open_betalain_gate3_mapping(saved.project_id, repository=repository)


@pytest.mark.parametrize("status", ["archived", "invalid"])
def test_gate3_restore_rejection_leaves_session_state_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    steps, units, _mapping = apply_betalain_case_to_units(_units())
    repository = PlantProjectDraftRepository(tmp_path / "betalain-gate3")
    saved = save_betalain_gate3_mapping(
        pathway_steps=steps,
        transcription_units=units,
        repository=repository,
    )
    if status == "archived":
        ProjectLifecycleService(json_repository=repository).archive_project(saved.project_id, backend="json")
    else:
        path = repository.storage_dir / f"{saved.project_id}.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["lifecycle_status"] = "invalid"
        path.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("BIODESIGN_PLANT_PROJECT_DRAFT_DIR", str(repository.storage_dir))
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    restore = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_restore_betalain_three_enzyme_gate3_case"
    )
    session_state = {"formal_source_input_records": {"retain": True}, "unrelated": "retain"}
    namespace = {
        "st": SimpleNamespace(session_state=session_state),
        "_invalidate_formal_snapshots": lambda: pytest.fail("must not run before lifecycle rejection"),
    }
    exec(compile(ast.Module(body=[restore], type_ignores=[]), "app.py", "exec"), namespace)

    with pytest.raises(BetalainThreeEnzymeCaseError, match="does not allow editing or saving"):
        namespace["_restore_betalain_three_enzyme_gate3_case"](saved.project_id)
    assert session_state == {"formal_source_input_records": {"retain": True}, "unrelated": "retain"}


def test_formal_app_keeps_real_case_loader_without_public_homepage_shortcut() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    loader = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_load_betalain_three_enzyme_gate3_case"
    )
    loader_source = ast.get_source_segment(source, loader) or ""
    single_restore = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_restore_mvp_result"
    )
    single_restore_source = ast.get_source_segment(source, single_restore) or ""
    homepage = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_project_home"
    )
    homepage_source = ast.get_source_segment(source, homepage) or ""
    step3 = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_dual_tu_step_3"
    )
    step3_source = ast.get_source_segment(source, step3) or ""
    navigation = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_step_navigation"
    )
    navigation_source = ast.get_source_segment(source, navigation) or ""
    assert "def _load_betalain_three_enzyme_gate3_case" in source
    assert "加载甜菜红素三酶真实来源案例" not in homepage_source
    assert "_save_gate3_pathway_draft()" in navigation_source
    assert 'key=f"formal_step_{current_step}_save_draft"' in navigation_source
    assert "No TEST_ONLY component or placeholder backbone is used." in source
    assert "Pathway step to transcription-unit mapping" in source
    assert 'key="formal_betalain_record_regulatory"' in step3_source
    assert 'st.session_state["formal_betalain_regulatory_components_recorded"] = True' in step3_source
    assert "Generate computational canonical construct" in source
    assert "_invalidate_formal_snapshots()" in loader_source
    assert 'st.session_state.pop("formal_source_input_records", None)' in loader_source
    assert 'st.session_state.pop("formal_expression_cassette", None)' in loader_source
    assert 'st.session_state.pop("formal_betalain_gate3_case", None)' in single_restore_source
