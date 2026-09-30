from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from Bio import SeqIO

from core.vector_asset_contracts_v1 import (
    CONTRACTS_PATH,
    VectorAssetContractError,
    classify_vector_asset,
    load_vector_asset_contracts,
    sequence_sha256,
)
from services.vector_asset_admission import (
    assess_vector_workflow,
    validate_vector_operation,
)


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "pcambia1300_af234296_1": ("exact_insertion_source", "exact_insertion", 8958),
    "pbi121_af485783_1": ("tDNA_replacement_source", "exact_replacement", 14758),
    "pbin19_u09365_1": ("reference_vector", "none", 11777),
    "r229_local_example": ("hold_unverified_asset", "none", 4200),
}


def _source_record(contract: dict) -> dict:
    path = ROOT / contract["source_evidence"][0]["local_record_path"]
    parsed = SeqIO.read(path, "genbank")
    return {
        "normalized_sequence": str(parsed.seq).upper(),
        "source_accession_version": contract.get("accession_version") or contract.get("record_id"),
        "original_record_identifier": str(parsed.id),
        "topology": str(parsed.annotations.get("topology") or ""),
        "source_name": path.name,
    }


def _by_id() -> dict[str, dict]:
    return {row["asset_id"]: row for row in load_vector_asset_contracts()}


def test_four_contracts_load_with_unique_formal_classifications() -> None:
    rows = load_vector_asset_contracts()
    assert len(rows) == 4
    assert set(_by_id()) == set(EXPECTED)
    for asset_id, (asset_kind, operation_kind, length) in EXPECTED.items():
        row = _by_id()[asset_id]
        assert (row["asset_kind"], row["operation_kind"], row["full_sequence_length"]) == (
            asset_kind,
            operation_kind,
            length,
        )
        assert row["arbitrary_coordinate_allowed"] is False


def test_schema_declares_closed_asset_and_operation_enums() -> None:
    schema = json.loads((CONTRACTS_PATH.parent / "contracts.schema.json").read_text(encoding="utf-8"))
    properties = schema["$defs"]["contract"]["properties"]
    assert set(properties["asset_kind"]["enum"]) == {
        "exact_insertion_source",
        "tDNA_replacement_source",
        "reference_vector",
        "hold_unverified_asset",
    }
    assert set(properties["operation_kind"]["enum"]) == {"exact_insertion", "exact_replacement", "none"}
    assert properties["arbitrary_coordinate_allowed"] == {"const": False}


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda payload: payload["contracts"][0].update(asset_kind="unknown"), "unknown asset_kind"),
        (lambda payload: payload["contracts"][0].update(arbitrary_coordinate_allowed=True), "block arbitrary coordinates"),
        (lambda payload: payload["contracts"][1].update(operation_kind="none"), "requires an operation_kind"),
        (lambda payload: payload["contracts"][1].update(asset_id=payload["contracts"][0]["asset_id"]), "Duplicate"),
        (lambda payload: payload["contracts"][1]["aliases"].append("pCAMBIA1300"), "Duplicate vector identity token"),
    ],
)
def test_loader_rejects_invalid_schema_semantics(tmp_path: Path, mutation, message: str) -> None:
    payload = json.loads(CONTRACTS_PATH.read_text(encoding="utf-8"))
    mutation(payload)
    path = tmp_path / "contracts.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(VectorAssetContractError, match=message):
        load_vector_asset_contracts(path)


@pytest.mark.parametrize("asset_id", list(EXPECTED))
def test_each_reviewed_source_has_exact_identity(asset_id: str) -> None:
    contract = _by_id()[asset_id]
    record = _source_record(contract)
    identity = classify_vector_asset(record)
    assert identity["identity_status"] == "EXACT_KNOWN_ASSET"
    assert identity["asset_id"] == asset_id
    assert identity["asset_kind"] == contract["asset_kind"]
    assert identity["operation_kind"] == contract["operation_kind"]
    assert sequence_sha256(record["normalized_sequence"]) == contract["full_sequence_sha256"]


def test_known_accession_with_wrong_sequence_is_not_a_known_asset() -> None:
    contract = _by_id()["pbin19_u09365_1"]
    record = _source_record(contract)
    sequence = record["normalized_sequence"]
    record["normalized_sequence"] = ("A" if sequence[0] != "A" else "C") + sequence[1:]
    identity = classify_vector_asset(record)
    assert identity["identity_status"] == "KNOWN_ACCESSION_SEQUENCE_MISMATCH"
    assert identity["asset_id"] is None
    assert identity["read_only"] is True


def test_record_identifier_alias_participates_in_identity_mismatch_detection() -> None:
    contract = _by_id()["pbin19_u09365_1"]
    record = _source_record(contract)
    record["source_accession_version"] = ""
    record["original_record_identifier"] = "pBIN19"
    sequence = record["normalized_sequence"]
    record["normalized_sequence"] = ("A" if sequence[0] != "A" else "C") + sequence[1:]
    identity = classify_vector_asset(record)
    assert identity["identity_status"] == "KNOWN_ACCESSION_SEQUENCE_MISMATCH"
    assert identity["matched_asset_id"] == "pbin19_u09365_1"


def test_known_sequence_with_wrong_topology_is_metadata_mismatch() -> None:
    record = _source_record(_by_id()["pcambia1300_af234296_1"])
    record["topology"] = "linear"
    identity = classify_vector_asset(record)
    assert identity["identity_status"] == "KNOWN_SEQUENCE_METADATA_MISMATCH"
    assert identity["asset_id"] is None


def test_circular_rotation_is_identified_but_not_used_with_unremapped_coordinates() -> None:
    record = _source_record(_by_id()["pcambia1300_af234296_1"])
    sequence = record["normalized_sequence"]
    record["normalized_sequence"] = sequence[731:] + sequence[:731]
    identity = classify_vector_asset(record)
    assert identity["identity_status"] == "EXACT_KNOWN_ASSET"
    assert identity["rotation_equivalent"] is True
    admission = assess_vector_workflow(record, workflow_id="single_gene_rice_alb")
    assert admission["allowed"] is False
    assert "coordinate origin" in admission["reason"]


@pytest.mark.parametrize(
    ("asset_id", "workflow", "allowed"),
    [
        ("pcambia1300_af234296_1", "single_gene_rice_alb", True),
        ("pcambia1300_af234296_1", "single_gene", False),
        ("pcambia1300_af234296_1", "generic_multi_tu", False),
        ("pcambia1300_af234296_1", "betalain_gate3", False),
        ("pbi121_af485783_1", "single_gene", False),
        ("pbi121_af485783_1", "generic_multi_tu", False),
        ("pbi121_af485783_1", "betalain_gate3", True),
        ("pbin19_u09365_1", "single_gene", False),
        ("pbin19_u09365_1", "generic_multi_tu", False),
        ("pbin19_u09365_1", "betalain_gate3", False),
        ("r229_local_example", "single_gene", False),
        ("r229_local_example", "generic_multi_tu", False),
        ("r229_local_example", "betalain_gate3", False),
    ],
)
def test_workflow_admission_matrix(asset_id: str, workflow: str, allowed: bool) -> None:
    assessment = assess_vector_workflow(_source_record(_by_id()[asset_id]), workflow_id=workflow)
    assert assessment["allowed"] is allowed


def test_exact_operations_are_fixed_and_arbitrary_coordinates_are_rejected() -> None:
    rows = _by_id()
    pcambia = _source_record(rows["pcambia1300_af234296_1"])
    assert validate_vector_operation(
        pcambia,
        workflow_id="single_gene_rice_alb",
        insertion_settings={
            "mode": "insertion",
            "start_coordinate": 27,
            "end_coordinate": 28,
            "insertion_orientation": "forward",
        },
    )["allowed"]
    assert not validate_vector_operation(
        pcambia,
        workflow_id="single_gene_rice_alb",
        insertion_settings={
            "mode": "insertion",
            "start_coordinate": 219,
            "end_coordinate": 220,
            "insertion_orientation": "forward",
        },
    )["allowed"]
    pbi121 = _source_record(rows["pbi121_af485783_1"])
    assert validate_vector_operation(
        pbi121,
        workflow_id="betalain_gate3",
        insertion_settings={
            "mode": "replacement",
            "start_coordinate": 4974,
            "end_coordinate": 7979,
            "insertion_orientation": "forward",
        },
    )["allowed"]
    assert not validate_vector_operation(
        pbi121,
        workflow_id="betalain_gate3",
        insertion_settings={
            "mode": "replacement",
            "start_coordinate": 4973,
            "end_coordinate": 7979,
            "insertion_orientation": "forward",
        },
    )["allowed"]


def test_cached_identity_fields_cannot_override_recomputed_contract() -> None:
    record = _source_record(_by_id()["r229_local_example"])
    tampered = copy.deepcopy(record)
    tampered.update(
        asset_id="pcambia1300_af234296_1",
        asset_kind="exact_insertion_source",
        operation_kind="exact_insertion",
        vector_asset_identity={"identity_status": "EXACT_KNOWN_ASSET", "asset_id": "pcambia1300_af234296_1"},
    )
    assessment = validate_vector_operation(
        tampered,
        workflow_id="single_gene_rice_alb",
        insertion_settings={
            "mode": "insertion",
            "start_coordinate": 27,
            "end_coordinate": 28,
            "insertion_orientation": "forward",
        },
    )
    assert assessment["allowed"] is False
    assert assessment["identity"]["asset_id"] == "r229_local_example"
