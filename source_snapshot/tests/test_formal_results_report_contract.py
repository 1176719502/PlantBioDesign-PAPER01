from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

import services.formal_results_report_contract as contract
from services.formal_results_report_contract import (
    FormalResultsReportContractError,
    build_formal_results_report_contract,
    validate_report_artifact_manifest,
)


CANONICAL = "ATGCGTACGTAGCTAGCTAG"
CANONICAL_HASH = hashlib.sha256(CANONICAL.encode("ascii")).hexdigest()
INPUT_SIGNATURE = "1" * 64
FASTA = f">canonical\n{CANONICAL}\n"
GENBANK = "LOCUS       canonical 20 bp DNA linear\nORIGIN\n        1 atgcgtacgtagctagctag\n//\n"


def _state() -> dict:
    runtime = {
        "schema_version": "runtime-v1",
        "project_id": "p1",
        "active_transcription_unit_id": "tu1",
        "active_complete_plasmid_id": "plasmid1",
        "transcription_units": [{"tu_id": "tu1", "input_signature": INPUT_SIGNATURE}],
        "complete_plasmid_constructs": [{"plasmid_id": "plasmid1", "input_signature": INPUT_SIGNATURE}],
        "components": [
            {"component_id": "c1", "display_name": "Promoter", "component_type": "promoter", "sequence_asset_id": "a1"},
            {"component_id": "c2", "display_name": "CDS", "component_type": "cds", "sequence_asset_id": "a2"},
        ],
        "sequence_assets": [
            {"asset_id": "a1", "display_name": "Promoter", "length": 5, "source_type": "paste", "sequence_checksum": "a" * 64},
            {"asset_id": "a2", "display_name": "CDS", "length": 5, "source_type": "registry", "original_record_identifier": "ACC.1", "sequence_checksum": "b" * 64},
        ],
    }
    cassette = {
        "runtime": runtime,
        "construct_id": "construct1",
        "construct_status": "current",
        "revision_id": "rev1",
        "sequence": CANONICAL,
        "sequence_length": len(CANONICAL),
        "sequence_checksum": CANONICAL_HASH,
        "feature_rows": [
            {"name": "Promoter", "component_type": "promoter", "start": 1, "end": 5, "strand": 1, "component_id": "c1"},
            {"name": "CDS", "component_type": "cds", "start": 6, "end": 15, "strand": 1, "component_id": "c2"},
        ],
        "validation_findings": [],
        "validation_summary": {"blocking_count": 0, "warning_count": 0, "info_count": 0},
        "ordered_component_ids": ["c1", "c2"],
        "topology": "linear",
    }
    plasmid = dict(cassette)
    plasmid.update({"plasmid_id": "plasmid1", "topology": "circular"})
    return runtime, cassette, plasmid


def _record() -> dict:
    runtime, _cassette, _plasmid = _state()
    return {
        "project_id": "p1",
        "project_name": "Persisted project",
        "project_type": "single_gene",
        "runtime": runtime,
        "contains_vector": False,
        "formal_project_context": {"host_key": "Arabidopsis thaliana", "expression_target": "recorded target", "current_step": 6},
        "source_inputs": {"cds": "recorded source"},
        "source_input_sha256": {"cds": hashlib.sha256(b"recorded source").hexdigest()},
        "input_records": {"cds": {"source_kind": "paste", "source_reference": "local-cds", "sequence_length": 10}},
        "insertion_settings": {},
        "exports": {
            "combined_construct_fasta": {"data": FASTA, "file_name": "construct.fasta", "mime": "text/plain"},
            "combined_construct_genbank": {"data": GENBANK, "file_name": "construct.gb", "mime": "text/plain"},
        },
        "_transient": {"project_name": "forged", "canonical_hash": "f" * 64},
    }


def _artifact(manifest: dict, artifact_id: str) -> dict:
    return next(
        item for item in manifest["artifacts"] if item["artifact_id"] == artifact_id
    )


def _resign_manifest(manifest: dict) -> None:
    payload = {key: value for key, value in manifest.items() if key != "manifest_id"}
    manifest["manifest_id"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()


@pytest.fixture(autouse=True)
def _canonical_reader(monkeypatch: pytest.MonkeyPatch):
    def _cassette(runtime):
        value = copy.deepcopy(_state()[1])
        signature = runtime["transcription_units"][0]["input_signature"]
        value["runtime"] = copy.deepcopy(runtime)
        value["runtime"]["transcription_units"][0]["input_signature"] = signature
        return value

    def _plasmid(runtime):
        value = copy.deepcopy(_state()[2])
        signature = runtime["complete_plasmid_constructs"][0]["input_signature"]
        value["runtime"] = copy.deepcopy(runtime)
        value["runtime"]["complete_plasmid_constructs"][0]["input_signature"] = signature
        return value

    monkeypatch.setattr(
        contract,
        "_read_canonical_runtime",
        lambda runtime: (
            _cassette(runtime),
            _plasmid(runtime) if bool(runtime.get("has_complete_plasmid")) else {},
        ),
    )


def test_deterministic_regeneration_and_transient_state_is_non_authoritative() -> None:
    record = _record()
    first = build_formal_results_report_contract(record)
    second = build_formal_results_report_contract(copy.deepcopy(record))
    assert first == second
    assert first["report_snapshot"]["project"]["name"] == "Persisted project"
    assert first["report_snapshot"]["construct_summary"]["canonical_hash"] == CANONICAL_HASH
    assert first["artifact_manifest"]["report_snapshot_identity"]["snapshot_id"] == first["report_snapshot"]["snapshot_id"]


def test_missing_mandatory_canonical_fields_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _record()
    cassette = _state()[1]
    cassette["sequence_checksum"] = ""
    monkeypatch.setattr(contract, "_read_canonical_runtime", lambda runtime: (cassette, {}))
    with pytest.raises(FormalResultsReportContractError, match="canonical sequence identity"):
        build_formal_results_report_contract(record)


def test_missing_canonical_component_reference_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    record = _record()
    cassette = _state()[1]
    cassette["ordered_component_ids"] = ["missing"]
    monkeypatch.setattr(contract, "_read_canonical_runtime", lambda runtime: (cassette, {}))
    with pytest.raises(FormalResultsReportContractError, match="incomplete component"):
        build_formal_results_report_contract(record)


def test_persistence_compatible_json_round_trip_regenerates_same_identities() -> None:
    record = _record()
    before = build_formal_results_report_contract(record)
    reopened_shape = json.loads(json.dumps(record, ensure_ascii=False))
    after = build_formal_results_report_contract(reopened_shape)
    assert before["report_snapshot"]["snapshot_id"] == after["report_snapshot"]["snapshot_id"]
    assert before["artifact_manifest"]["manifest_id"] == after["artifact_manifest"]["manifest_id"]
    assert before["report_snapshot"]["component_summary"]["authority"] == after["report_snapshot"]["component_summary"]["authority"]
    assert before["report_snapshot"]["delivery_artifacts"] == after["report_snapshot"]["delivery_artifacts"]


def test_persistence_navigation_metadata_does_not_change_report_identity() -> None:
    record = _record()
    record["formal_project_context"].pop("current_step")
    before = build_formal_results_report_contract(record)
    record["formal_project_context"]["current_step"] = 6
    after = build_formal_results_report_contract(record)
    assert before == after


def test_persisted_source_hash_uses_exact_input_text_bytes() -> None:
    record = _record()
    source = ">source\nATGC\n"
    record["source_inputs"] = {"cds": source}
    record["source_input_sha256"] = {"cds": hashlib.sha256(source.encode("utf-8")).hexdigest()}
    built = build_formal_results_report_contract(record)
    assert built["report_snapshot"]["biological_inputs"]["source_hashes"] == [
        {"source_id": "cds", "sha256": f"sha256:{record['source_input_sha256']['cds']}"}
    ]


def test_source_hash_contract_preserves_exact_utf8_persistence_semantics() -> None:
    first = _record()
    first["source_inputs"] = {"cds": ">source\r\nATGC\r\n"}
    first["source_input_sha256"] = {
        "cds": hashlib.sha256(first["source_inputs"]["cds"].encode("utf-8")).hexdigest()
    }
    reopened = json.loads(json.dumps(first, ensure_ascii=False))
    assert build_formal_results_report_contract(first) == build_formal_results_report_contract(reopened)

    normalized = copy.deepcopy(first)
    normalized["source_inputs"]["cds"] = normalized["source_inputs"]["cds"].replace("\r\n", "\n")
    with pytest.raises(FormalResultsReportContractError, match="source hash mismatch"):
        build_formal_results_report_contract(normalized)


def test_persisted_provenance_reference_uses_recorded_asset_identity() -> None:
    record = _record()
    record["input_records"]["cds"] = {
        "source_kind": "genbank",
        "asset": {"original_record_identifier": "ACC.7", "length": 10},
    }
    built = build_formal_results_report_contract(record)
    assert built["report_snapshot"]["provenance_summary"]["records"] == [
        {
            "role": "cds",
            "source_kind": "genbank",
            "source_reference": "ACC.7",
            "length_bp": 10,
        }
    ]


def test_forged_top_level_multi_tu_type_cannot_override_canonical_runtime() -> None:
    record = _record()
    record["project_type"] = "multi_tu"
    record["expression_units"] = [{"unit_id": "forged", "orientation": "reverse"}]
    record["unit_order"] = ["forged"]
    with pytest.raises(FormalResultsReportContractError, match="workflow type"):
        build_formal_results_report_contract(record)


def test_forged_contains_vector_flag_cannot_downgrade_canonical_plasmid() -> None:
    record = _record()
    record["runtime"]["has_complete_plasmid"] = True
    record["contains_vector"] = False
    first = build_formal_results_report_contract(record)
    record["contains_vector"] = True
    second = build_formal_results_report_contract(record)
    assert first == second
    assert first["artifact_manifest"]["canonical_sequence_identity"]["topology"] == "circular"


def test_project_identity_mismatch_with_runtime_fails_closed() -> None:
    record = _record()
    record["project_id"] = "forged-project"
    with pytest.raises(FormalResultsReportContractError, match="project identity"):
        build_formal_results_report_contract(record)


def test_stale_upstream_input_signature_changes_snapshot_and_manifest_identity() -> None:
    first = build_formal_results_report_contract(_record())
    record = _record()
    record["runtime"]["transcription_units"][0]["input_signature"] = "2" * 64
    record["runtime"]["complete_plasmid_constructs"][0]["input_signature"] = "2" * 64
    second = build_formal_results_report_contract(record)
    assert first["report_snapshot"]["snapshot_id"] != second["report_snapshot"]["snapshot_id"]
    assert first["artifact_manifest"]["manifest_id"] != second["artifact_manifest"]["manifest_id"]


def test_component_asset_identity_mutations_change_or_invalidate_report() -> None:
    first_record = _record()
    first = build_formal_results_report_contract(first_record)

    checksum_mutation = copy.deepcopy(first_record)
    checksum_mutation["runtime"]["sequence_assets"][0]["sequence_checksum"] = "c" * 64
    changed = build_formal_results_report_contract(checksum_mutation)
    assert changed["report_snapshot"]["snapshot_id"] != first["report_snapshot"]["snapshot_id"]
    assert changed["artifact_manifest"]["component_identity"] != first["artifact_manifest"]["component_identity"]

    contradictory = copy.deepcopy(first_record)
    contradictory["runtime"]["sequence_assets"][0].update(
        nucleotide_sequence="AAAAA",
        sequence_checksum="c" * 64,
    )
    with pytest.raises(FormalResultsReportContractError, match="contradicts its authoritative sequence"):
        build_formal_results_report_contract(contradictory)

    source_mutation = copy.deepcopy(first_record)
    source_mutation["runtime"]["sequence_assets"][1]["original_record_identifier"] = "ACC.2"
    changed_source = build_formal_results_report_contract(source_mutation)
    assert changed_source["report_snapshot"]["snapshot_id"] != first["report_snapshot"]["snapshot_id"]


def test_resigned_component_authority_contradiction_is_rejected() -> None:
    built = build_formal_results_report_contract(_record())
    snapshot = copy.deepcopy(built["report_snapshot"])
    snapshot["component_summary"]["authority"]["records"][0]["asset_sha256"] = "sha256:" + "0" * 64
    snapshot_payload = {key: value for key, value in snapshot.items() if key != "snapshot_id"}
    snapshot["snapshot_id"] = hashlib.sha256(
        json.dumps(snapshot_payload, sort_keys=True, separators=(",", ":")).encode("ascii")
    ).hexdigest()
    manifest = copy.deepcopy(built["artifact_manifest"])
    manifest["report_snapshot_identity"]["snapshot_id"] = snapshot["snapshot_id"]
    _resign_manifest(manifest)
    with pytest.raises(FormalResultsReportContractError, match="component identity"):
        validate_report_artifact_manifest(manifest, snapshot)


def test_artifact_hash_mismatch_is_rejected() -> None:
    record = _record()
    record["exports"]["combined_construct_fasta"]["sha256"] = "0" * 64
    with pytest.raises(FormalResultsReportContractError, match="FASTA artifact hash"):
        build_formal_results_report_contract(record)


def test_manifest_tampering_and_snapshot_mismatch_are_rejected() -> None:
    built = build_formal_results_report_contract(_record())
    manifest = copy.deepcopy(built["artifact_manifest"])
    manifest["freshness"]["state"] = "stale"
    with pytest.raises(FormalResultsReportContractError, match="Manifest ID"):
        validate_report_artifact_manifest(manifest, built["report_snapshot"])
    resigned = copy.deepcopy(built["artifact_manifest"])
    _resign_manifest(resigned)
    snapshot = copy.deepcopy(built["report_snapshot"])
    snapshot["snapshot_id"] = "f" * 64
    with pytest.raises(Exception, match="Snapshot ID"):
        validate_report_artifact_manifest(resigned, snapshot)


def test_resigned_manifest_cannot_change_canonical_snapshot_binding() -> None:
    built = build_formal_results_report_contract(_record())
    manifest = copy.deepcopy(built["artifact_manifest"])
    manifest["canonical_sequence_identity"]["sha256"] = "0" * 64
    for artifact in manifest["artifacts"]:
        if artifact.get("status") == "available":
            artifact["canonical_sha256"] = "0" * 64
    _resign_manifest(manifest)
    with pytest.raises(FormalResultsReportContractError, match="ReportSnapshot facts"):
        validate_report_artifact_manifest(manifest, built["report_snapshot"])


@pytest.mark.parametrize(
    ("artifact_id", "field", "value"),
    [
        ("fasta", "sha256", "0" * 64),
        ("fasta", "size_bytes", 999),
        ("fasta", "file_name", "forged.fasta"),
        ("fasta", "canonical_sha256", "0" * 64),
        ("genbank", "sha256", "0" * 64),
        ("genbank", "canonical_sha256", "0" * 64),
        ("plasmid_map", "source_feature_sha256", "0" * 64),
        ("plasmid_map", "renderer_version", "forged-renderer"),
    ],
)
def test_resigned_artifact_claim_forgery_is_rejected(
    artifact_id: str, field: str, value: object
) -> None:
    built = build_formal_results_report_contract(_record())
    manifest = copy.deepcopy(built["artifact_manifest"])
    _artifact(manifest, artifact_id)[field] = value
    _resign_manifest(manifest)
    with pytest.raises(FormalResultsReportContractError, match="artifact claims"):
        validate_report_artifact_manifest(manifest, built["report_snapshot"])


def test_assembly_only_multi_tu_uses_explicit_complete_plasmid_availability() -> None:
    record = _record()
    record["project_type"] = "multi_tu"
    record["runtime"].update(
        project_type="multi_tu",
        expression_units=[
            {"unit_id": "tu1", "orientation": "forward", "length": len(CANONICAL), "input_signature": INPUT_SIGNATURE},
            {"unit_id": "tu2", "orientation": "reverse", "length": len(CANONICAL), "input_signature": INPUT_SIGNATURE},
        ],
        unit_order=["tu1", "tu2"],
    )
    first = build_formal_results_report_contract(record)
    second = build_formal_results_report_contract(json.loads(json.dumps(record)))
    complete = first["report_snapshot"]["construct_summary"]["complete_plasmid"]
    assert first == second
    assert first["report_snapshot"]["workflow_type"] == "multi_tu"
    assert complete == {
        "status": "unavailable",
        "reason": "not_generated_for_assembly_only_design",
    }
    assert _artifact(first["artifact_manifest"], "plasmid_map")["reason"] == "not_applicable_without_complete_plasmid"


def test_complete_plasmid_availability_remains_explicit_for_single_and_multi_tu() -> None:
    for project_type in ("single_gene", "multi_tu"):
        record = _record()
        record["runtime"]["has_complete_plasmid"] = True
        record["project_type"] = project_type
        if project_type == "multi_tu":
            record["runtime"]["project_type"] = "multi_tu"
        built = build_formal_results_report_contract(record)
        complete = built["report_snapshot"]["construct_summary"]["complete_plasmid"]
        assert complete["status"] == "available"
        assert complete["facts"]["topology"] == "circular"


def _assert_report_identity_preserved(before_record: dict, after_record: dict) -> None:
    before = build_formal_results_report_contract(before_record)
    after = build_formal_results_report_contract(after_record)
    assert before["report_snapshot"]["snapshot_id"] == after["report_snapshot"]["snapshot_id"]
    assert before["artifact_manifest"]["manifest_id"] == after["artifact_manifest"]["manifest_id"]
    assert before["artifact_manifest"]["component_identity"] == after["artifact_manifest"]["component_identity"]
    assert before["report_snapshot"]["delivery_artifacts"] == after["report_snapshot"]["delivery_artifacts"]


def test_real_single_gene_save_reopen_preserves_report_identities(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()
    from mvp_app import generate_complete_vector, load_real_case
    from services.mvp_single_gene_persistence import (
        open_mvp_single_gene_design,
        save_mvp_single_gene_design,
    )
    from services.plant_project_draft_repository import PlantProjectDraftRepository

    repository = PlantProjectDraftRepository(tmp_path / "single-gene")
    before = generate_complete_vector(load_real_case())
    saved = save_mvp_single_gene_design(before, repository=repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repository)
    _assert_report_identity_preserved(before, reopened)


@pytest.mark.parametrize("assembly_only", [False, True])
def test_real_multi_tu_save_reopen_preserves_report_identities(
    tmp_path: Path, assembly_only: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.undo()
    from services.mvp_multi_tu_persistence import (
        open_mvp_multi_tu_design,
        save_mvp_multi_tu_design,
    )
    from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct
    from services.plant_project_draft_repository import PlantProjectDraftRepository
    from tests.test_mvp9_multi_tu_runtime import DATA, _generate, _units_for_case

    repository = PlantProjectDraftRepository(tmp_path / ("assembly" if assembly_only else "complete"))
    if assembly_only:
        before = generate_multi_tu_combined_construct(
            project_id="report-r2-assembly",
            project_name="Report R2 assembly",
            expression_units=_units_for_case(DATA["cases"][1]),
        )
        before["project_type"] = "dual_tu"
        before["formal_project_context"] = {
            "current_step": 6,
            "design_scenario": "standard_plant_expression_vector",
        }
    else:
        before = _generate(DATA["cases"][1])
    saved = save_mvp_multi_tu_design(before, repository=repository)
    reopened = open_mvp_multi_tu_design(saved.project_id, repository=repository)
    _assert_report_identity_preserved(before, reopened)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda manifest: manifest["project_identity"].update(project_id="other"), "project identity"),
        (
            lambda manifest: manifest["report_snapshot_identity"].update(schema_version="other"),
            "ReportSnapshot identity",
        ),
        (lambda manifest: manifest["artifacts"].pop(), "artifact inventory"),
        (
            lambda manifest: manifest["canonical_sequence_identity"].update(
                input_signature="9" * 64
            ),
            "input signatures",
        ),
    ],
)
def test_resigned_manifest_cannot_replace_bound_contract_facts(mutate, message: str) -> None:
    built = build_formal_results_report_contract(_record())
    manifest = copy.deepcopy(built["artifact_manifest"])
    mutate(manifest)
    _resign_manifest(manifest)
    with pytest.raises(FormalResultsReportContractError, match=message):
        validate_report_artifact_manifest(manifest, built["report_snapshot"])
