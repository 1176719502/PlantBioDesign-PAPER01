from __future__ import annotations

import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.real_case_contracts.mt02_extract_and_verify import (
    DEFAULT_CONTRACT_DIR,
    derive_atomic_partition,
    load_contracts,
    verify_contract_consistency,
)
from tools.real_case_contracts.resource_tree_hash import hash_logical_resource_tree


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "data" / "real_case_contracts_v1" / "mt02_pdoe13"


def _load(name: str) -> dict:
    return json.loads((CONTRACT_DIR / name).read_text(encoding="utf-8"))


def test_all_mt02_documents_validate_against_versioned_schema() -> None:
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


def test_case_id_is_unique_and_product_contract_is_expression_only() -> None:
    manifests = list((ROOT / "data" / "real_case_contracts_v1").glob("**/case_manifest.json"))
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in manifests]
    assert [item["case_id"] for item in payloads].count("MT-02") == 1
    manifest = _load("case_manifest.json")
    assert manifest["construct_name"] == "pDOE-13"
    assert manifest["result_kind"] == "MULTI_TU_EXPRESSION_ASSEMBLY"
    assert manifest["paper"] == {
        "doi": "10.1111/tpj.12639",
        "pmid": "25187041",
        "accession_relationship": "PAPER_ACCESSION_VERSION_MATCH_WITH_EXPLANATION",
    }
    assert manifest["product_result"]["contains_vector"] is False
    assert manifest["product_result"]["topology"] == "linear"
    assert manifest["status"] == "MT02_DATA_CONTRACT_PENDING_FULL_PYTEST_GATE"


def test_source_identity_version_topology_length_and_hash_are_frozen() -> None:
    source = _load("source_contract.json")
    hashes = _load("expected_hashes.json")
    assert source["accession_version"] == source["record_id"] == "KM507054.1"
    assert source["parsed_record"] == {
        "id": "KM507054.1",
        "locus_name": "KM507054",
        "description": "Binary vector pDOE-13, complete sequence",
        "topology": "circular",
        "length_bp": 13268,
        "sequence_sha256": "92e57f49a0986ad749dd2ccdca3051f6101be1bf917bff6e8492135e3ea2d6cc",
        "feature_count": 43,
        "sequence_version": 1,
        "parser": "Biopython SeqIO GenBank",
        "verified_parser_version": "1.87",
    }
    assert hashes["source_sequence_sha256"] == source["parsed_record"]["sequence_sha256"]
    assert source["retrieval"]["request_accession_must_equal"] == "KM507054.1"
    assert source["retrieval"]["unversioned_accession_allowed"] is False


def test_extraction_and_canonical_contract_are_frozen() -> None:
    extraction = _load("extraction_contract.json")["extraction"]
    assert extraction["source_interval"] == {
        "external_1_based_inclusive": {"start": 111, "end": 6719},
        "internal_0_based_half_open": {"start": 110, "end": 6719},
        "length_bp": 6609,
    }
    assert extraction["canonical_interval"]["internal_0_based_half_open"] == {
        "start": 0,
        "end": 6609,
    }
    assert extraction["wraparound"] is False
    assert extraction["topology"] == "linear"
    assert extraction["contains_vector"] is False
    assert extraction["sequence_sha256"] == (
        "ec86af6644082317a79dd938d6e70a0011b5d0f784f21da61fac55df4f43f8d2"
    )


def test_three_tu_roles_orientations_boundaries_and_algorithmic_coordinates() -> None:
    tus = _load("extraction_contract.json")["transcription_units"]
    assert [(item["tu_number"], item["role"], item["orientation"], item["strand"]) for item in tus] == [
        (1, "accessory", "reverse", -1),
        (2, "target/reporter", "forward", 1),
        (3, "target/reporter", "forward", 1),
    ]
    assert [item["source_interval"]["internal_0_based_half_open"] for item in tus] == [
        {"start": 110, "end": 1327},
        {"start": 1327, "end": 4263},
        {"start": 4263, "end": 6719},
    ]
    for item in tus:
        source = item["source_interval"]["internal_0_based_half_open"]
        canonical = item["canonical_interval"]["internal_0_based_half_open"]
        assert canonical == {"start": source["start"] - 110, "end": source["end"] - 110}
    assert [item["source_interval"]["length_bp"] for item in tus] == [1217, 2936, 2456]
    assert sum(item["source_interval"]["length_bp"] for item in tus) == 6609


def test_nine_components_are_contiguous_with_fixed_cores_and_transformations() -> None:
    rows = _load("component_contract.json")["components"]
    assert len(rows) == 9
    assert [(item["tu_number"], item["role"]) for item in rows] == [
        (1, "three_prime_regulatory_region"), (1, "cds"), (1, "promoter"),
        (2, "promoter"), (2, "cds"), (2, "three_prime_regulatory_region"),
        (3, "promoter"), (3, "cds"), (3, "three_prime_regulatory_region"),
    ]
    assert [item["source_physical_interval"]["length_bp"] for item in rows] == [
        302, 519, 396, 1414, 768, 754, 1416, 768, 272,
    ]
    assert [item["core_source_interval"]["external_1_based_inclusive"] for item in rows] == [
        {"start": 111, "end": 362}, {"start": 413, "end": 931}, {"start": 935, "end": 1315},
        {"start": 1328, "end": 2657}, {"start": 2742, "end": 3509}, {"start": 3532, "end": 4257},
        {"start": 4264, "end": 5597}, {"start": 5680, "end": 6447}, {"start": 6467, "end": 6719},
    ]
    assert {item["ui_input_transformation"] for item in rows[:3]} == {
        "reverse_complement_source_physical_span"
    }
    assert {item["ui_input_transformation"] for item in rows[3:]} == {
        "identity_source_physical_span"
    }


def test_unannotated_intervals_are_exactly_four_and_total_24_bp() -> None:
    rows = _load("component_contract.json")["unannotated_intervals"]
    assert [item["source_interval"]["external_1_based_inclusive"] for item in rows] == [
        {"start": 363, "end": 372},
        {"start": 1316, "end": 1327},
        {"start": 2658, "end": 2658},
        {"start": 6466, "end": 6466},
    ]
    assert [item["source_interval"]["length_bp"] for item in rows] == [10, 12, 1, 1]
    assert sum(item["source_interval"]["length_bp"] for item in rows) == 24
    assert all(item["category"] == "UNANNOTATED_SOURCE_SEQUENCE" for item in rows)
    assert all(item["source_annotated_as_component"] is False for item in rows)


def test_source_features_expected_features_and_overlap_count_are_derived() -> None:
    contract = _load("feature_contract.json")
    source_features = contract["source_feature_assertions"]
    assert len(source_features) == 33
    assert len(contract["derived_expected_features"]) == 17
    assert contract["expected_feature_count"] == 50
    overlap_count = sum(
        max(left["source_interval"]["start"], right["source_interval"]["start"])
        < min(left["source_interval"]["end"], right["source_interval"]["end"])
        for index, left in enumerate(source_features)
        for right in source_features[index + 1 :]
    )
    assert overlap_count == contract["expected_pairwise_source_feature_overlap_count"] == 30
    assert all(item["evidence_classification"] == "FACT_FROM_PRIMARY_SOURCE" for item in source_features)


def test_atomic_partition_is_algorithmic_complete_and_non_overlapping() -> None:
    components = _load("component_contract.json")
    features = _load("feature_contract.json")["source_feature_assertions"]
    derived = derive_atomic_partition(features, components["unannotated_intervals"])
    stored = components["atomic_partition"]
    assert len(derived) == len(stored) == 40
    for expected, actual in zip(derived, stored):
        for key, value in expected.items():
            assert actual[key] == value
    assert stored[0]["source_interval"] == {"start": 110, "end": 362}
    assert stored[-1]["source_interval"] == {"start": 6466, "end": 6719}
    assert all(left["source_interval"]["end"] == right["source_interval"]["start"] for left, right in zip(stored, stored[1:]))
    assert sum(item["length_bp"] for item in stored) == 6609
    assert {item["unannotated_interval_id"] for item in stored if item["unannotated_interval_id"]} == {
        "MT-02-U01", "MT-02-U02", "MT-02-U03", "MT-02-U04"
    }


def test_junctions_cover_all_component_and_inter_tu_boundaries() -> None:
    contract = _load("extraction_contract.json")
    junctions = contract["junctions"]
    assert len(junctions) == 8
    assert [item["scope"] for item in junctions] == [
        "within_TU1", "within_TU1", "between_TU1_TU2", "within_TU2",
        "within_TU2", "between_TU2_TU3", "within_TU3", "within_TU3",
    ]
    assert all(item["left_source_end"] == item["right_source_start"] for item in junctions)
    assert all(item["canonical_boundary"] == item["left_source_end"] - 110 for item in junctions)


def test_cross_contract_invariants_return_exact_summary() -> None:
    assert verify_contract_consistency(load_contracts(DEFAULT_CONTRACT_DIR)) == {
        "coordinate_conversions": "pass",
        "tu_partition": "pass",
        "component_partition": "pass",
        "atomic_partition": "pass",
        "atomic_interval_count": 40,
        "expected_feature_count": 50,
        "source_feature_overlap_count": 30,
        "junction_count": 8,
        "unannotated_interval_count": 4,
        "unannotated_total_bp": 24,
    }


def test_redistribution_contract_blocks_source_region_and_equivalent_bytes() -> None:
    contract = _load("redistribution_contract.json")
    assert contract["redistribution_status"] == "ACCESSION_AND_REPRODUCIBLE_EXTRACTION_ONLY"
    blocked = [value for key, value in contract["repository_policy"].items() if key.endswith("_allowed")]
    assert blocked and all(value is False for value in blocked)
    assert contract["runtime_distribution"]["bundle_source_record"] is False
    assert contract["runtime_distribution"]["bundle_extracted_region"] is False


def test_contract_directory_contains_no_raw_or_reconstructable_sequence_asset() -> None:
    forbidden_suffixes = {".gb", ".gbk", ".genbank", ".fa", ".fasta", ".fna", ".gz", ".zip", ".b64"}
    task_roots = [
        CONTRACT_DIR,
        ROOT / "docs" / "architecture_v2" / "mt02_gold_standard_contract",
        ROOT / "audit_reports" / "mt02_gold_standard_contract",
    ]
    files = [path for task_root in task_roots for path in task_root.rglob("*") if path.is_file()]
    files.extend(
        [
            ROOT / "tools" / "real_case_contracts" / "mt02_extract_and_verify.py",
            ROOT / "tests" / "test_mt02_extract_and_verify.py",
            ROOT / "tests" / "test_mt02_gold_standard_contract.py",
        ]
    )
    assert not [path for path in files if path.suffix.lower() in forbidden_suffixes]
    for path in files:
        if path.suffix.lower() in {".json", ".md", ".py", ".csv"}:
            assert not re.search(r"[ACGT]{100,}", path.read_text(encoding="utf-8"))


def test_registry_vector_and_mt01_trees_match_starting_head() -> None:
    hashes = _load("expected_hashes.json")["protected_resource_tree_hashes"]
    for relative_dir, expected in hashes.items():
        assert hash_logical_resource_tree(
            repo_root=ROOT,
            resource_root=ROOT / relative_dir,
        ) == expected


def test_contract_does_not_claim_runtime_ui_persistence_or_wet_lab_acceptance() -> None:
    manifest = _load("case_manifest.json")
    text = " ".join(manifest["formal_limitations"] + manifest["inferences"]).lower()
    assert "does not integrate app.py" in text
    assert "runtime integration" in text
    assert "cold-reopen are expected in principle" in text
    assert "neither behavior is accepted by this task" in text
    assert "does not establish expression success" in text
    assert manifest["next_stage_status"] == "BLOCKED_PENDING_CLEAN_TREE_GUARD_RESOLUTION"
