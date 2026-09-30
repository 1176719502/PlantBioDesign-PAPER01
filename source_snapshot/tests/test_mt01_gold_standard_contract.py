from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.real_case_contracts.mt01_extract_and_verify import (
    DEFAULT_CONTRACT_DIR,
    load_contracts,
    verify_contract_consistency,
)
from tools.real_case_contracts.resource_tree_hash import hash_logical_resource_tree


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "data" / "real_case_contracts_v1" / "mt01_pgrdl_sp"


def _load(name: str) -> dict:
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


def test_all_mt01_documents_validate_against_the_versioned_schema() -> None:
    schema = _load("contracts.schema.json")
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    documents = sorted(CONTRACT_DIR.glob("*.json"))
    documents.remove(CONTRACT_DIR / "contracts.schema.json")

    assert {path.name for path in documents} == {
        "case_manifest.json",
        "source_contract.json",
        "extraction_contract.json",
        "component_contract.json",
        "feature_contract.json",
        "expected_hashes.json",
        "redistribution_contract.json",
    }
    for path in documents:
        validator.validate(json.loads(path.read_text(encoding="utf-8")))


def test_case_id_is_unique_and_product_contract_is_assembly_only() -> None:
    manifests = list((ROOT / "data" / "real_case_contracts_v1").glob("**/case_manifest.json"))
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in manifests]
    assert [item["case_id"] for item in payloads].count("MT-01") == 1

    manifest = _load("case_manifest.json")
    assert manifest["route"] == "generic_multi_tu"
    assert manifest["result_kind"] == "MULTI_TU_EXPRESSION_ASSEMBLY"
    assert manifest["construct_name"] == "pGrDL_SP"
    assert manifest["paper"] == {
        "doi": "10.3389/fpls.2017.01631",
        "pmid": "28979287",
    }
    assert manifest["product_result"] == {
        "topology": "linear",
        "contains_vector": False,
        "tu_count": 2,
        "tu_identities": ["Renilla luciferase TU", "firefly luciferase TU"],
        "orientations": ["reverse", "forward"],
    }
    assert manifest["status"] == "DATA_CONTRACT_READY_FOR_RUNTIME_INTEGRATION"


def test_source_identity_topology_length_and_hash_are_frozen() -> None:
    source = _load("source_contract.json")
    hashes = _load("expected_hashes.json")
    assert source["accession_version"] == source["record_id"] == "KX758647.1"
    assert source["parsed_record"]["topology"] == "circular"
    assert source["parsed_record"]["length_bp"] == 7086
    assert source["parsed_record"]["sequence_sha256"] == hashes["source_sequence_sha256"]
    assert hashes["source_sequence_sha256"] == "7baff645c3e75e31518a7bbc31b45ea321748fa37e5475fa821489ed8df06d15"
    assert source["retrieval"]["url"].endswith(
        "db=nuccore&id=KX758647.1&rettype=gbwithparts&retmode=text"
    )


def test_all_coordinate_systems_and_region_hash_are_frozen() -> None:
    extraction = _load("extraction_contract.json")
    region = extraction["extraction"]
    assert region["source_interval"] == {
        "external_1_based_inclusive": {"start": 571, "end": 4649},
        "internal_0_based_half_open": {"start": 570, "end": 4649},
        "length_bp": 4079,
    }
    assert region["local_interval"] == {
        "external_1_based_inclusive": {"start": 1, "end": 4079},
        "internal_0_based_half_open": {"start": 0, "end": 4079},
        "length_bp": 4079,
    }
    assert region["wraparound"] is False
    assert region["topology"] == "linear"
    assert region["sequence_sha256"] == "1847b411bd0592e0927db433bfc88f8eec3a9f8c30620af97aba5dae465c3104"


def test_tu_boundaries_are_contiguous_complete_and_uniquely_ordered() -> None:
    tus = _load("extraction_contract.json")["transcription_units"]
    assert [(item["tu_number"], item["orientation"], item["strand"]) for item in tus] == [
        (1, "reverse", -1),
        (2, "forward", 1),
    ]
    assert [item["source_interval"]["internal_0_based_half_open"] for item in tus] == [
        {"start": 570, "end": 2323},
        {"start": 2323, "end": 4649},
    ]
    assert [item["local_interval"]["internal_0_based_half_open"] for item in tus] == [
        {"start": 0, "end": 1753},
        {"start": 1753, "end": 4079},
    ]
    assert [item["source_interval"]["length_bp"] for item in tus] == [1753, 2326]
    assert 1753 + 2326 == 4079


def test_six_component_boundaries_transformations_and_hashes_are_frozen() -> None:
    rows = _load("component_contract.json")["components"]
    assert [(item["tu_number"], item["role"]) for item in rows] == [
        (1, "three_prime_regulatory_region"),
        (1, "cds"),
        (1, "promoter"),
        (2, "promoter"),
        (2, "cds"),
        (2, "three_prime_regulatory_region"),
    ]
    assert [item["source_physical_interval"]["length_bp"] for item in rows] == [
        283,
        936,
        534,
        398,
        1653,
        275,
    ]
    assert {item["ui_input_transformation"] for item in rows[:3]} == {
        "reverse_complement_source_physical_span"
    }
    assert {item["ui_input_transformation"] for item in rows[3:]} == {
        "identity_source_physical_span"
    }
    assert all(item["source_type"] == "REAL_CASE_ACCESSION_DERIVED" for item in rows)
    assert all(item["case_evidence_class"] == "DETERMINISTIC_ACCESSION_DERIVATION" for item in rows)
    assert all(len(item["expected_input_sequence_sha256"]) == 64 for item in rows)
    assert all(len(item["expected_physical_segment_sha256"]) == 64 for item in rows)


def test_unannotated_intervals_are_complete_conservative_and_hash_frozen() -> None:
    rows = _load("component_contract.json")["unannotated_intervals"]
    assert [item["source_interval"]["length_bp"] for item in rows] == [1, 15, 195, 6, 109]
    assert sum(item["source_interval"]["length_bp"] for item in rows) == 326
    assert [item["junction_id"] for item in rows] == [
        "MT-01-J01",
        "MT-01-J02",
        "MT-01-J03",
        "MT-01-J04",
        "MT-01-J05",
    ]
    assert all(item["category"] == "UNANNOTATED_SOURCE_SEQUENCE" for item in rows)
    assert all(item["source_annotated"] is False for item in rows)
    forbidden_names = {"assembly scar", "linker", "spacer", "insulator"}
    assert all(item["category"].lower() not in forbidden_names for item in rows)
    assert all(len(item["sequence_sha256"]) == 64 for item in rows)


def test_atomic_partition_and_cross_contract_invariants_pass() -> None:
    contracts = load_contracts(DEFAULT_CONTRACT_DIR)
    result = verify_contract_consistency(contracts)
    assert result == {
        "coordinate_conversions": "pass",
        "tu_partition": "pass",
        "component_partition": "pass",
        "atomic_partition": "pass",
        "unannotated_interval_count": 5,
        "unannotated_total_bp": 326,
    }


def test_feature_contract_uses_source_supported_and_conservative_identities() -> None:
    feature_contract = _load("feature_contract.json")
    expected = feature_contract["expected_features"]
    assert len({item["feature_id"] for item in expected}) == len(expected)
    assert {item["feature_type"] for item in expected} >= {
        "source",
        "transcription_unit",
        "CDS",
        "regulatory_region",
        "regulatory",
        "misc_feature",
    }
    assert {(item["label"], item["strand"]) for item in expected if item["feature_type"] == "CDS"} == {
        ("Renilla luciferase CDS", -1),
        ("firefly luciferase CDS", 1),
    }
    composite_labels = [item["label"] for item in expected if "physical span" in item["label"]]
    assert all("NOS terminator" not in label and "35S terminator" not in label for label in composite_labels)
    assert all(item["source_accession_version"] == "KX758647.1" for item in expected)
    assert not any(item["feature_type"] in {"vector", "backbone"} for item in expected)
    assert set(feature_contract["forbidden_feature_classes"]) >= {
        "vector",
        "backbone",
        "origin_of_replication",
        "T-DNA_border",
        "selectable_marker",
    }


def test_manifest_does_not_claim_complete_vector_or_experimental_performance() -> None:
    manifest = _load("case_manifest.json")
    combined = " ".join(manifest["formal_limitations"]).lower()
    assert "does not reproduce the complete pgrdl_sp vector" in combined
    assert "does not establish expression success" in combined
    assert manifest["product_result"]["contains_vector"] is False
    assert manifest["product_result"]["topology"] == "linear"


def test_redistribution_contract_blocks_source_and_region_bytes() -> None:
    contract = _load("redistribution_contract.json")
    assert contract["redistribution_status"] == "ACCESSION_AND_REPRODUCIBLE_EXTRACTION_ONLY"
    assert all(
        value is False
        for key, value in contract["repository_policy"].items()
        if key.endswith("_allowed") and key != "allowed_material"
    )
    assert contract["runtime_distribution"]["bundle_source_record"] is False
    assert contract["runtime_distribution"]["bundle_extracted_region"] is False


def test_contract_directory_contains_no_raw_sequence_asset() -> None:
    forbidden_suffixes = {".gb", ".gbk", ".genbank", ".fa", ".fasta", ".fna", ".gz", ".zip"}
    files = [path for path in CONTRACT_DIR.rglob("*") if path.is_file()]
    assert not [path for path in files if path.suffix.lower() in forbidden_suffixes]


def test_registry_and_vector_contract_trees_match_current_data_baseline() -> None:
    hashes = _load("expected_hashes.json")["protected_resource_tree_hashes"]
    assert hash_logical_resource_tree(
        repo_root=ROOT,
        resource_root=ROOT / "data/plant_component_registry_v1",
    ) == hashes[
        "data/plant_component_registry_v1"
    ]
    assert hash_logical_resource_tree(
        repo_root=ROOT,
        resource_root=ROOT / "data/vector_asset_contracts_v1",
    ) == hashes[
        "data/vector_asset_contracts_v1"
    ]
    registry = json.loads(
        (ROOT / "data" / "plant_component_registry_v1" / "registry.batch1.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(registry["records"]) == 34
    assert sum(item["evidence_level"] == "E1" for item in registry["records"]) == 24
    assert sum(item["evidence_level"] == "E2" for item in registry["records"]) == 10

