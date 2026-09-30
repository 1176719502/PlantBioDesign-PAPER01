# -*- coding: utf-8 -*-
"""Focused regression tests for the local design asset seed catalog."""
from __future__ import annotations

import importlib
import json
import os
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import local_design_asset_catalog_service as catalog_service

SEED_PATH = Path(ROOT) / "data" / "local_design_asset_seed.json"


def _load_seed_payload() -> dict:
    return json.loads(SEED_PATH.read_text(encoding="utf-8"))


def test_seed_file_loads():
    records = catalog_service.load_seed_records()
    catalog = catalog_service.load_seed_catalog()

    assert records
    assert catalog["metadata"]["seed_name"]
    assert catalog["records"]
    assert all(isinstance(record, dict) for record in records)


def test_required_fields_exist_and_validate():
    records = catalog_service.load_seed_records()
    errors = catalog_service.validate_seed_records(records)

    assert errors == []
    assert all(not catalog_service.validate_record(record) for record in records)
    assert all(record["sequence_available"] is False for record in records)
    assert all(record["sequence_hash"] == "" for record in records)
    assert all(record["sequence_hash_algorithm"] == "" for record in records)


def test_asset_types_are_recognized_and_covered():
    records = catalog_service.load_seed_records()
    expected_types = set(catalog_service.ASSET_TYPES)

    assert 50 <= len(records) <= 80
    assert {record["asset_type"] for record in records}.issubset(expected_types)
    assert expected_types.issubset({record["asset_type"] for record in records})


def test_list_filter_and_search_behavior():
    records = catalog_service.load_seed_records()

    listed = catalog_service.list_assets(records)
    assert [row["display_name"] for row in listed] == sorted(
        [row["display_name"] for row in records], key=str.lower
    )

    promoter_records = catalog_service.filter_by_asset_type(records, "promoter")
    assert promoter_records
    assert all(row["asset_type"] == "promoter" for row in promoter_records)

    alias_matches = catalog_service.search_assets(records, "5 utr")
    assert any(row["asset_type"] == "rbs_5utr" for row in alias_matches)

    tag_matches = catalog_service.search_assets(records, "documentation note")
    assert any(row["asset_type"] == "literature_source_note" for row in tag_matches)


def test_provenance_and_review_summary_reports_placeholder_records():
    records = catalog_service.load_seed_records()
    missing_review = catalog_service.report_records_missing_review(records)
    missing_review_summary = catalog_service.summarize_missing_review(records)
    inventory = catalog_service.summarize_catalog_inventory(records)

    assert missing_review
    assert all(
        row["provenance_status"] == "source review needed" or row["review_status"] == "human review needed"
        for row in missing_review
    )
    assert set(missing_review_summary["source_review_needed"]).issubset({row["asset_id"] for row in records})
    assert set(missing_review_summary["human_review_needed"]).issubset({row["asset_id"] for row in records})

    counts = catalog_service.summarize_counts_by_asset_type(records)
    assert counts["plasmid_backbone"] >= 3
    assert counts["promoter"] >= 8
    assert counts["rbs_5utr"] >= 3
    assert counts["terminator"] >= 2
    assert counts["signal_peptide"] >= 2
    assert counts["tag"] >= 2
    assert counts["cds_target"] >= 8
    assert counts["origin_metadata"] >= 2
    assert counts["marker_metadata"] >= 2
    assert counts["host_chassis_context_note"] >= 5
    assert counts["literature_source_note"] >= 2

    review_counts = catalog_service.summarize_review_status(records)
    assert review_counts["source_review_needed"] == len(records)
    assert review_counts["human_review_needed"] == len(records)
    assert inventory["record_source_label"] == "bundled seed records"
    assert inventory["documentation_status_label"] == "documentation-only reference records"
    assert inventory["total_record_count"] == len(records)
    assert inventory["represented_source_context_count"] >= 1


def test_empty_search_and_filter_behaviour_are_bounded():
    records = catalog_service.load_seed_records()
    assert catalog_service.search_assets(records, "no-such-local-design-asset") == []
    assert catalog_service.filter_by_asset_type(records, "not-a-real-type") == []


def test_asset_selector_label_and_preview_are_compact_and_documentation_only():
    records = catalog_service.load_seed_records()
    promoter_record = next(record for record in records if record["asset_type"] == "promoter")
    origin_record = next(record for record in records if record["asset_type"] == "origin_metadata")
    plant_record = next(record for record in records if record["asset_id"] == "lda-promoter-006")
    fallback_record = next(record for record in records if record["asset_id"] == "lda-origin-metadata-001")

    promoter_label = catalog_service.asset_selector_label(promoter_record)
    origin_label = catalog_service.asset_selector_label(origin_record)
    preview = catalog_service.asset_preview(origin_record)
    plant_preview = catalog_service.asset_preview(plant_record)
    fallback_preview = catalog_service.asset_preview(fallback_record)

    assert promoter_record["display_name"] in promoter_label
    assert promoter_label.endswith(" - promoter")
    assert origin_record["display_name"] in origin_label
    assert origin_label.endswith(" - origin / replication metadata")
    assert preview["display_name"] == origin_record["display_name"]
    assert preview["asset_type"] == "origin / replication metadata"
    assert preview["source_or_provenance_status"] == origin_record["provenance_status"]
    assert preview["review_status"] == origin_record["review_status"]
    assert preview["human_review_note"] == origin_record["human_review_notes"]
    assert plant_preview["host_chassis_context"] == plant_record["organism_or_source_context"]
    assert plant_preview["host_chassis_context_label"] == "Plant"
    assert "not compatibility evidence" in plant_preview["host_chassis_context_readback"].lower()
    assert fallback_preview["host_chassis_context_label"] == "Generic / unspecified"


def test_seed_has_no_sequence_payloads_or_external_requirements():
    payload = _load_seed_payload()
    records = payload["records"]

    assert all(not record["sequence_available"] for record in records)
    assert all(record["sequence_hash"] == "" for record in records)
    assert all(record["sequence_hash_algorithm"] == "" for record in records)
    assert all("http" not in json.dumps(record).lower() for record in records)
    assert "OPENAI_API_KEY" not in json.dumps(payload)


def test_no_schema_or_import_export_side_effects():
    before = set(sys.modules)
    importlib.reload(catalog_service)
    after = set(sys.modules)

    changed = after - before
    assert not any(name.startswith("services.project_export") for name in changed)
    assert not any(name.startswith("services.project_import") for name in changed)


def test_forbidden_user_visible_wording_not_present_in_seed_copy():
    payload = _load_seed_payload()
    forbidden = [
        "best",
        "optimal",
        "validated",
        "approved",
        "compatible",
        "suitable",
        "ready for synthesis",
        "ready for wet lab",
        "experimentally confirmed",
        "recommendation",
        "compatibility",
        "readiness",
        "score",
        "ranking",
        "optimized",
    ]
    boundary_allowlist = {"documentation_boundary_note"}

    searchable_text = []
    for record in payload["records"]:
        searchable_text.extend(str(value).lower() for key, value in record.items() if key not in boundary_allowlist)
    blob = "\n".join(searchable_text)

    assert not any(term in blob for term in forbidden)


def test_nicotiana_demo_candidate_records_are_present_with_review_only_wording():
    records = catalog_service.load_seed_records()
    ids = {record["asset_id"] for record in records}

    expected_ids = {
        "lda-cds-target-006",
        "lda-cds-target-007",
        "lda-cds-target-008",
        "lda-cds-target-009",
        "lda-cds-target-010",
        "lda-cds-target-011",
        "lda-cds-target-012",
        "lda-promoter-006",
        "lda-promoter-007",
        "lda-promoter-008",
        "lda-promoter-009",
        "lda-promoter-010",
    }
    assert expected_ids.issubset(ids)

    nicotiana_records = [record for record in records if "v2.6-r58 Nicotiana documentation case" in record["version_context"]]
    assert len(nicotiana_records) == 12
    assert all(record["sequence_available"] is False for record in nicotiana_records)
    assert all("source review needed" in record["provenance_status"].lower() for record in nicotiana_records)
    assert all("human review needed" in record["review_status"].lower() for record in nicotiana_records)
    assert all("documentation-only" in record["documentation_boundary_note"].lower() for record in nicotiana_records)
    assert all("recommend" not in record["short_description"].lower() for record in nicotiana_records)


def test_boundary_notes_keep_explicit_negation_and_block_positive_claims():
    payload = _load_seed_payload()
    boundary_notes = [record["documentation_boundary_note"].lower() for record in payload["records"]]
    boundary_blob = "\n".join(boundary_notes)

    allowed_negative_boundary_examples = [
        "not a recommendation",
        "not an optimization",
        "not experimental validation",
        "not a wet-lab readiness judgment",
    ]
    for phrase in allowed_negative_boundary_examples:
        assert phrase.startswith("not ")

    targeted_notes = {
        "lda-cds-target-007": "not a host-compatibility judgment or readiness claim",
        "lda-promoter-007": "not a validation claim",
        "lda-promoter-010": "not a validation or readiness claim",
    }
    indexed_notes = {
        record["asset_id"]: record["documentation_boundary_note"].lower()
        for record in payload["records"]
    }
    for asset_id, expected_phrase in targeted_notes.items():
        assert expected_phrase in indexed_notes[asset_id]

    boundary_risk_terms = [
        "recommendation",
        "optimization",
        "validation",
        "readiness",
        "judgment",
        "proof",
    ]
    for note in boundary_notes:
        if any(term in note for term in boundary_risk_terms):
            assert "not " in note

    forbidden_positive_claims = [
        "is recommended",
        "is optimized",
        "is validated",
        "ready for wet lab",
        "ready for synthesis",
        "best promoter",
        "host compatible",
    ]
    assert not any(term in boundary_blob for term in forbidden_positive_claims)


def test_host_chassis_seed_records_cover_chassis_neutral_context_examples() -> None:
    records = catalog_service.load_seed_records()
    host_records = [record for record in records if record["asset_type"] == "host_chassis_context_note"]
    combined = "\n".join(
        [
            str(record.get("display_name", ""))
            + " "
            + str(record.get("organism_or_source_context", ""))
            + " "
            + " ".join(str(tag) for tag in record.get("tags", []))
            for record in host_records
        ]
    ).lower()

    for phrase in ["bacterial", "yeast", "mammalian", "plant"]:
        assert phrase in combined
    assert "documentation-only" in "\n".join(record["documentation_boundary_note"] for record in host_records).lower()
    forbidden = ["recommended", "validated", "optimized", "compatible", "ready"]
    for term in forbidden:
        assert term not in combined


def test_local_asset_host_context_readback_falls_back_safely_when_not_recorded() -> None:
    preview = catalog_service.asset_preview(
        {
            "asset_id": "asset-unknown",
            "asset_type": "origin_metadata",
            "display_name": "Unknown origin note",
            "provenance_status": "source review needed",
            "review_status": "human review needed",
            "human_review_notes": "Documentation review needed.",
        }
    )

    assert preview["host_chassis_context"] == "Not recorded"
    assert preview["host_chassis_context_label"] == "Generic / unspecified"
