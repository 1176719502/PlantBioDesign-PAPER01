"""Shared production-path helpers for MVP7 tests; not an assembly oracle."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from mvp_app import generate_complete_vector, load_real_case
from scripts.validation.validate_single_gene_accuracy import (
    REPO_ROOT,
    assert_sequences_equal,
    build_fixture_genbank,
    load_case_data,
    sha256_sequence,
)
from services.canonical_construct_runtime import (
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
)
from services.mvp_cds_input import analyze_cds_input
from services.mvp_sequence_input import (
    analyze_dna_component_input,
    analyze_genbank_backbone_input,
)


CASE_DATA = load_case_data()
CASES = list(CASE_DATA["cases"])


def case_by_id(case_id: str) -> dict[str, Any]:
    return next(case for case in CASES if case["case_id"] == case_id)


def backbone_text_for_case(case: dict[str, Any]) -> str:
    if case.get("backbone_input_path"):
        return (REPO_ROOT / str(case["backbone_input_path"])).read_text(encoding="utf-8")
    return build_fixture_genbank(case)


def _component_record(
    case: dict[str, Any], role: str, *, project_id: str
) -> dict[str, Any]:
    return analyze_dna_component_input(
        str(case[f"{role}_sequence"]),
        project_id=project_id,
        component_type=role,
        display_name=str(case["component_names"][role]),
        source_kind="mvp7-fixed-case",
        source_name=f"{case['case_id']}_{role}.txt",
    )


def build_production_result(case: dict[str, Any]) -> dict[str, Any]:
    """Call the existing public MVP production path for one fixed case."""
    if case["case_id"] == "case_01_stable_example":
        return generate_complete_vector(load_real_case())

    project_id = f"mvp7-{case['case_id'].replace('_', '-')}"
    cds_input = analyze_cds_input(
        str(case["cds_sequence"]),
        source_kind="mvp7-fixed-case",
        source_name=f"{case['case_id']}_cds.txt",
    )
    assert not cds_input["blocking"], cds_input["findings"]
    records = {
        "promoter": _component_record(case, "promoter", project_id=project_id),
        "cds": {
            "role": "cds",
            "source_kind": "mvp7-fixed-case",
            "source_name": f"{case['case_id']}_cds.txt",
            "source_format": "plain",
            "display_name": str(case["component_names"]["cds"]),
            "original_text": str(case["cds_sequence"]),
            "normalized_sequence": str(cds_input["normalized_cds"]),
            "length": int(cds_input["normalized_length"]),
        },
        "terminator": _component_record(case, "terminator", project_id=project_id),
        "backbone": analyze_genbank_backbone_input(
            backbone_text_for_case(case),
            project_id=project_id,
            display_name=f"BACKBONE_{case['case_id']}",
            source_kind="mvp7-fixed-case",
            source_name=f"{case['case_id']}.gb",
        ),
    }
    coordinates = case["insertion_coordinates"]
    settings = {
        "mode": str(case["insertion_mode"]),
        "start_coordinate": int(coordinates["start"]),
        "end_coordinate": int(coordinates["end"]),
        "expected_removed_sequence": str(case["expected_removed_sequence"]),
        "topology_confirmation": False,
    }
    return generate_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id=project_id,
        project_name=str(case["project_name"]),
    )


def _normalized_parts_from_row(row: dict[str, Any]) -> list[dict[str, int]]:
    raw_parts = list(row.get("location_parts") or [])
    if raw_parts:
        parts = [
            {
                "start": int(part["start"]) - 1,
                "end": int(part["end"]),
                "strand": int(part.get("strand", row.get("strand", 1))),
            }
            for part in raw_parts
        ]
    else:
        parts = [
            {
                "start": int(row["start"]) - 1,
                "end": int(row["end"]),
                "strand": int(row.get("strand", 1)),
            }
        ]
    return sorted(parts, key=lambda part: (part["start"], part["end"], part["strand"]))


def normalize_runtime_features(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = [
        {
            "name": str(row["name"]),
            "feature_type": str(row.get("feature_type") or row.get("component_type") or ""),
            "source": str(row.get("source") or ("transcription_unit" if row.get("component_type") else "")),
            "strand": int(row.get("strand", 1)),
            "parts_0_based_half_open": _normalized_parts_from_row(row),
        }
        for row in rows
    ]
    return sorted(
        normalized,
        key=lambda item: (
            min(part["start"] for part in item["parts_0_based_half_open"]),
            max(part["end"] for part in item["parts_0_based_half_open"]),
            item["name"],
        ),
    )


def normalize_expected_features(case: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "name": str(feature["name"]),
            "feature_type": str(feature["feature_type"]),
            "source": str(feature["source"]),
            "strand": int(feature["strand"]),
            "parts_0_based_half_open": sorted(
                [dict(part) for part in feature["parts_0_based_half_open"]],
                key=lambda part: (part["start"], part["end"], part["strand"]),
            ),
        }
        for feature in case["expected"]["feature_locations"]
    ]


def compare_case_to_reference(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    cassette = active_construct_snapshot(result["runtime"])
    plasmid = active_complete_plasmid_snapshot(result["runtime"])
    assert_sequences_equal(expected["cassette_sequence"], cassette["sequence"], label=f"{case['case_id']} cassette")
    assert_sequences_equal(expected["plasmid_sequence"], plasmid["sequence"], label=f"{case['case_id']} plasmid")
    assert cassette["sequence_length"] == expected["cassette_length"]
    assert plasmid["sequence_length"] == expected["plasmid_length"]
    assert sha256_sequence(cassette["sequence"]) == expected["cassette_sha256"]
    assert sha256_sequence(plasmid["sequence"]) == expected["plasmid_sha256"]
    assert plasmid["cassette_coordinates"] == expected["cassette_span_1_based_inclusive"]
    actual_features = normalize_runtime_features(plasmid["feature_rows"])
    expected_features = normalize_expected_features(case)
    assert actual_features == expected_features
    assert plasmid["sequence"].count(cassette["sequence"]) == 1
    removed = str(expected["removed_sequence"])
    if removed:
        assert removed not in plasmid["sequence"]
    return {
        "case_id": case["case_id"],
        "cassette_length": cassette["sequence_length"],
        "plasmid_length": plasmid["sequence_length"],
        "cassette_sha256": sha256_sequence(cassette["sequence"]),
        "plasmid_sha256": sha256_sequence(plasmid["sequence"]),
        "feature_count": len(actual_features),
        "status": "passed",
    }


def sha256_bytes(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
