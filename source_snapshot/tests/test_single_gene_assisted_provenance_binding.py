"""R2: editable assisted provenance must agree before save and cold reopen."""
from __future__ import annotations

import json
from copy import deepcopy
import subprocess
import sys

import pytest

from services.mvp_single_gene_persistence import (
    MVP_SINGLE_GENE_PERSISTENCE_KEY,
    MvpSingleGenePersistenceError,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.formal_editor_state_contract import (
    FORMAL_EDITOR_STATE_CONTRACT_VERSION, RECORD_KIND_FORMAL_EDITOR_COMPLETED,
)
from services.single_gene_assisted_components import single_gene_assisted_input
from tests.test_single_gene_assisted_routing import HOST, ROOT, full_result, project


def _editor_result(project, *, ui_projection=False):
    result = full_result(project)
    if ui_projection:
        from services.formal_expression_cassette import assess_expression_cassette, generate_expression_cassette
        from services.formal_single_gene_runtime import generate_complete_vector

        components = deepcopy(result["formal_expression_cassette"]["components"])
        components[0]["source_file"] = ""
        components[1]["source_kind"] = "paste"
        assessment = assess_expression_cassette(
            components, cds_sequence=result["cds_input"]["normalized_cds"],
            cds_signature="test-only-cds", order_confirmed=True,
        )
        generated = generate_expression_cassette(assessment, project_id=project[1])
        context = result["formal_project_context"]
        result = generate_complete_vector(
            cds_input=result["cds_input"], input_records=result["input_records"],
            insertion_settings=result["insertion_settings"], project_id=project[1],
            project_name=result["project_name"], cassette_runtime=generated["runtime"],
            cassette_signature=generated["input_signature"],
        )
        result["formal_expression_cassette"] = generated
        result["formal_project_context"] = context
    cassette = result["formal_expression_cassette"]
    utr = next(c for c in cassette["components"] if c["biological_role"] == "five_prime_utr")
    utr_input = single_gene_assisted_input(
        {"role": "five_prime_region", "raw_text": utr["sequence"],
         "display_name": utr["display_name"], "component_reference": utr["component_reference"]},
        project_id=project[1], host=HOST, repository=project[0],
    )
    if ui_projection:
        utr_input = {key: deepcopy(utr[key]) for key in (
            "biological_role", "display_name", "sequence", "source_kind",
            "source_reference", "source_file", "component_reference", "assisted_project_host",
        )}
    definition = {"project_name": result["project_name"], "plant_host": HOST}
    result["formal_project_context"].update(
        record_kind=RECORD_KIND_FORMAL_EDITOR_COMPLETED,
        formal_editor_state_contract_version=FORMAL_EDITOR_STATE_CONTRACT_VERSION,
        project_definition=definition,
        formal_state={
            "formal_project_definition": deepcopy(definition),
            "formal_cds_input": deepcopy(result["cds_input"]),
            "formal_expression_cassette": deepcopy(cassette),
            "formal_backbone_record": deepcopy(result["input_records"]["backbone"]),
            "formal_insertion_settings": deepcopy(result["insertion_settings"]),
            "formal_cassette_result": {
                "cassette_input_signature": cassette["input_signature"],
                "input_records": deepcopy(result["input_records"]),
                "runtime": deepcopy(cassette["runtime"]),
            },
            "formal_element_source_records": {
                "promoter": deepcopy(result["input_records"]["promoter"]), "five_prime": utr_input,
            },
            "formal_step3_order_confirmation_recorded": True,
            "formal_step4_strategy_confirmed": True,
            "formal_step5_strategy_confirmed": True,
            "formal_construct_review_status": "current",
            "formal_cds_source_review_status": "current",
        },
    )
    return result


def _snapshot(result, location):
    if location == "promoter_input":
        return result["input_records"]["promoter"]
    role = "promoter" if location == "promoter_cassette" else "five_prime_utr"
    return next(
        c for c in result["formal_expression_cassette"]["components"]
        if c["biological_role"] == role
    )


def _stored_bytes(repository):
    return {p.name: p.read_bytes() for p in repository.storage_dir.glob("*.json")}


@pytest.mark.parametrize("location", ["promoter_input", "promoter_cassette", "utr_cassette"])
@pytest.mark.parametrize("field,value", [
    ("assisted_project_host", "Oryza sativa"),
    ("source_reference", "TEST ONLY contradictory source marker"),
])
def test_save_rejects_tampered_editable_binding_without_writing(project, location, field, value):
    result = _editor_result(project)
    _snapshot(result, location)[field] = value
    before = _stored_bytes(project[0])
    with pytest.raises(MvpSingleGenePersistenceError, match=field):
        save_mvp_single_gene_design(result, repository=project[0])
    assert _stored_bytes(project[0]) == before


@pytest.mark.parametrize("location", ["promoter_input", "promoter_cassette", "utr_cassette"])
@pytest.mark.parametrize("field,value", [
    ("assisted_project_host", "Oryza sativa"),
    ("source_reference", "TEST ONLY contradictory source marker"),
])
def test_cold_reopen_rejects_tampered_persisted_binding(project, location, field, value):
    saved = save_mvp_single_gene_design(_editor_result(project), repository=project[0])
    assert open_mvp_single_gene_design(saved.project_id, repository=project[0])["formal_editor_restore_reason"] == ""
    path = project[0].storage_dir / f"{saved.project_id}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    _snapshot(payload["manual_review_state"][MVP_SINGLE_GENE_PERSISTENCE_KEY], location)[field] = value
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    before = _stored_bytes(project[0])
    script = '''
import json, sys
from services.mvp_single_gene_persistence import (
    open_mvp_single_gene_design, list_mvp_single_gene_designs, MvpSingleGenePersistenceError,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
repo = PlantProjectDraftRepository(sys.argv[1])
try:
    result = open_mvp_single_gene_design(sys.argv[2], repository=repo)
except MvpSingleGenePersistenceError as exc:
    print(json.dumps({"blocked": True, "reason": str(exc),
                      "listed": sys.argv[2] in [d.project_id for d in list_mvp_single_gene_designs(repository=repo)]}))
else:
    print(json.dumps({"blocked": False, "restore_reason": result.get("formal_editor_restore_reason")}))
'''
    cold = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script, str(project[0].storage_dir), saved.project_id],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert cold.returncode == 0, cold.stderr
    outcome = json.loads(cold.stdout.strip().splitlines()[-1])
    assert outcome["blocked"]
    assert field in outcome["reason"]
    assert not outcome["listed"]
    assert _stored_bytes(project[0]) == before


@pytest.mark.parametrize("location,field,value", [
    ("promoter_input", "project_id", "another-project"),
    ("promoter_input", "role", "five_prime_utr"),
    ("promoter_input", "biological_role", "five_prime_utr"),
    ("promoter_input", "source_kind", "library"),
    ("promoter_input", "source_name", "TEST ONLY another source"),
    ("promoter_input", "normalized_sequence", "ACGT"),
    ("promoter_cassette", "source_kind", "library"),
    ("promoter_cassette", "source_file", "TEST ONLY another source"),
    ("utr_cassette", "biological_role", "promoter"),
    ("utr_cassette", "sequence", "ACGT"),
    ("utr_cassette", "project_id", "another-project"),
    ("utr_cassette", "component_type", "cds"),
    ("utr_cassette", "length", 1),
    ("promoter_cassette", "normalized_sequence", "ACGT"),
])
def test_save_binds_other_authoritative_snapshot_fields(project, location, field, value):
    result = _editor_result(project)
    _snapshot(result, location)[field] = value
    before = _stored_bytes(project[0])
    with pytest.raises(MvpSingleGenePersistenceError, match="binding|traceability"):
        save_mvp_single_gene_design(result, repository=project[0])
    assert _stored_bytes(project[0]) == before


@pytest.mark.parametrize("location", ["promoter_input", "promoter_cassette", "utr_cassette"])
@pytest.mark.parametrize("field", ["assisted_project_host", "source_reference"])
def test_missing_binding_cannot_bypass_comparison(project, location, field):
    result = _editor_result(project)
    _snapshot(result, location).pop(field)
    with pytest.raises(MvpSingleGenePersistenceError, match=field):
        save_mvp_single_gene_design(result, repository=project[0])


@pytest.mark.parametrize("location", ["promoter", "five_prime", "cassette_input", "cassette_component"])
@pytest.mark.parametrize("field,value", [
    ("assisted_project_host", "Oryza sativa"),
    ("source_reference", "TEST ONLY contradictory source marker"),
])
def test_formal_state_copies_cannot_bypass_binding(project, location, field, value):
    result = _editor_result(project)
    state = result["formal_project_context"]["formal_state"]
    if location == "cassette_input":
        snapshot = state["formal_cassette_result"]["input_records"]["promoter"]
    elif location == "cassette_component":
        snapshot = state["formal_expression_cassette"]["components"][1]
    else:
        snapshot = state["formal_element_source_records"][location]
    snapshot[field] = value
    with pytest.raises(MvpSingleGenePersistenceError, match=field):
        save_mvp_single_gene_design(result, repository=project[0])


@pytest.mark.parametrize("target", ["component", "asset"])
def test_canonical_source_must_still_match_resolution(project, target):
    result = _editor_result(project)
    component = next(c for c in result["runtime"]["components"] if c.get("component_reference"))
    snapshot = component if target == "component" else next(
        a for a in result["runtime"]["sequence_assets"] if a["asset_id"] == component["sequence_asset_id"]
    )
    snapshot["provenance_reference"] = "TEST ONLY contradictory source marker"
    with pytest.raises(MvpSingleGenePersistenceError, match="canonical provenance binding"):
        save_mvp_single_gene_design(result, repository=project[0])


@pytest.mark.parametrize("ui_projection", [False, True])
def test_valid_assisted_editor_saves_and_cold_reopens_without_promotion(project, ui_projection):
    result = _editor_result(project, ui_projection=ui_projection)
    saved = save_mvp_single_gene_design(result, repository=project[0])
    script = '''
import json, sys
from services.mvp_single_gene_persistence import open_mvp_single_gene_design
from services.plant_project_draft_repository import PlantProjectDraftRepository
r = open_mvp_single_gene_design(sys.argv[2], repository=PlantProjectDraftRepository(sys.argv[1]))
print(json.dumps({k:r[k] for k in ("runtime", "exports", "input_records", "formal_project_context", "formal_editor_restore_reason")}))
'''
    cold = subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script, str(project[0].storage_dir), saved.project_id],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    assert cold.returncode == 0, cold.stderr
    reopened = json.loads(cold.stdout.strip().splitlines()[-1])
    assert reopened["formal_editor_restore_reason"] == ""
    for key in ("runtime", "exports", "input_records"):
        assert reopened[key] == result[key]
    assert reopened["formal_project_context"]["formal_state"] == result["formal_project_context"]["formal_state"]
    refs = [c["component_reference"] for c in reopened["runtime"]["components"] if c.get("component_reference")]
    assert {r["catalog_component_id"] for r in refs} == {"V2-CMP-004", "V2-EXT-R2-013"}
    for ref in refs:
        assert ref["source_type"] == "USER_PROVIDED"
        assert ref["governance_status"] == "USER_SEQUENCE_ASSISTED"
        assert ref["registry_component_id"] == ref["accession_version"] == ""
        flags = ref["assisted_resolution"]["confirmation_contract"]
        assert flags["accession_verified"] is flags["boundary_verified_by_software"] is False
    before = _stored_bytes(project[0])
    result["input_records"]["promoter"]["source_reference"] = "TEST ONLY overwrite attempt"
    with pytest.raises(MvpSingleGenePersistenceError, match="source_reference"):
        save_mvp_single_gene_design(result, repository=project[0])
    assert _stored_bytes(project[0]) == before


@pytest.mark.parametrize("location", ["generated", "editor_cassette", "editor_result"])
@pytest.mark.parametrize("field,value", [
    ("assisted_project_host", "Oryza sativa"),
    ("provenance_reference", "TEST ONLY contradictory source marker"),
])
def test_restored_runtime_copies_remain_bound_to_canonical(project, location, field, value):
    result = _editor_result(project)
    state = result["formal_project_context"]["formal_state"]
    snapshot = {
        "generated": result["formal_expression_cassette"],
        "editor_cassette": state["formal_expression_cassette"],
        "editor_result": state["formal_cassette_result"],
    }[location]
    snapshot["runtime"]["components"][0][field] = value
    with pytest.raises(MvpSingleGenePersistenceError, match="runtime copy binding"):
        save_mvp_single_gene_design(result, repository=project[0])


def test_host_alias_cannot_disagree_with_definition_and_canonical(project):
    result = _editor_result(project)
    result["formal_project_context"]["host_key"] = "Oryza sativa"
    with pytest.raises(MvpSingleGenePersistenceError, match="host"):
        save_mvp_single_gene_design(result, repository=project[0])
