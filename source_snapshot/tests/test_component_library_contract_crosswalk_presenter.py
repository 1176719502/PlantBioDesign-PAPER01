from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.component_library_contract_crosswalk_presenter import (
    DOCUMENTATION_BOUNDARY_NOTE,
    build_component_library_contract_crosswalk_presenter,
)


def test_contract_crosswalk_builds_required_summary_and_field_groups() -> None:
    presenter = build_component_library_contract_crosswalk_presenter(
        [
            {
                "asset_id": "lda-promoter-001",
                "asset_type": "promoter",
                "display_name": "Plant promoter note",
                "version_context": "seed v2.6",
                "aliases": ["Promoter alias"],
                "short_description": "Metadata-only promoter source context.",
                "organism_or_source_context": "Plant source context",
                "sequence_available": False,
                "source_notes": "Local source note.",
                "provenance_status": "source review needed",
                "review_status": "human review needed",
                "human_review_notes": "Review source metadata before citing.",
                "tags": ["promoter"],
                "documentation_boundary_note": "Documentation-only metadata record for review and traceability.",
            }
        ]
    )

    assert presenter["title"] == "Component Library contract crosswalk"
    assert presenter["subtitle"].startswith("Read-only R352 contract view")
    assert presenter["field_groups"]["required"] == [
        "component_id",
        "component_type",
        "component_label",
        "documentation_boundary_note",
    ]
    assert "created_at" in presenter["field_groups"]["deferred"]
    assert "sequence generation or final sequence output" in presenter["field_groups"]["out_of_scope"]

    summary = presenter["summary"]
    assert summary["total_components"] == 1
    assert summary["component_type_counts"] == {"promoter": 1}
    assert summary["components_with_source_provenance_context"] == 1
    assert summary["components_with_evidence_reference_context"] == 1
    assert summary["components_with_missing_fields"] == 0

    component = presenter["components"][0]
    assert component["component_summary"]["component_id"] == "lda-promoter-001"
    assert component["component_summary"]["component_label"] == "Plant promoter note"
    assert component["source_provenance_display_status"] == "Source/provenance context recorded"
    assert component["evidence_reference_display_status"] == "Evidence/reference context recorded"
    assert component["missing_fields"] == []
    assert "Manual review note: Review source metadata before citing." in component["follow_up_notes"]


def test_contract_crosswalk_rows_map_existing_asset_like_keys_without_persistence() -> None:
    presenter = build_component_library_contract_crosswalk_presenter(
        [
            {
                "asset_snapshot": {"asset_id": "snapshot-only"},
                "record_identifier": "ppc-001",
                "asset_type": "plant_promoter_profile",
                "asset_label": "Plant promoter profile",
                "asset_version": "snapshot v1",
                "source_label": "Plant Promoter Catalog",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "ppc-001",
                },
                "documentation_status": "source review needed",
                "evidence_type": "literature context",
                "evidence_summary": "Recorded source/reference context for documentation review.",
                "missing_metadata_fields": ["source_accession"],
                "limitation_note": "Pinned documentation snapshot for reference context only.",
            }
        ]
    )

    component = presenter["components"][0]
    rows = {row["contract_field"]: row for row in component["field_crosswalk_rows"]}

    assert rows["component_id"]["display_value"] == "ppc-001"
    assert rows["component_type"]["display_value"] == "plant_promoter_profile"
    assert rows["component_type"]["display_treatment"] == "display-only"
    assert rows["component_label"]["display_value"] == "Plant promoter profile"
    assert rows["component_version"]["display_value"] == "snapshot v1"
    assert rows["source_label"]["display_value"] == "Plant Promoter Catalog"
    assert rows["evidence_summary"]["display_value"] == "Recorded source/reference context for documentation review."
    assert rows["missing_metadata_fields"]["display_value"] == "source_accession"
    assert component["missing_fields"] == ["source_accession"]
    assert any("manual documentation follow-up" in note for note in component["follow_up_notes"])


def test_contract_crosswalk_empty_state_and_missing_required_fields_are_review_only() -> None:
    empty = build_component_library_contract_crosswalk_presenter([])

    assert empty["summary"]["total_components"] == 0
    assert empty["components"] == []
    assert empty["empty_state"].startswith("No Component Library component or asset-like records")

    presenter = build_component_library_contract_crosswalk_presenter(
        [{"source_reference": "Project note", "review_status": "human review needed"}]
    )
    component = presenter["components"][0]

    assert component["missing_fields"] == ["component_id", "component_label", "component_type"]
    assert component["source_provenance_display_status"] == "Source/provenance context recorded"
    assert component["evidence_reference_display_status"] == "Evidence/reference context recorded"
    assert "Missing metadata indicates manual documentation follow-up" in component["follow_up_notes"][0]
    assert component["component_summary"]["boundary_notes"][0] == DOCUMENTATION_BOUNDARY_NOTE


def test_contract_crosswalk_boundary_copy_avoids_forbidden_user_visible_phrases() -> None:
    presenter = build_component_library_contract_crosswalk_presenter(
        [{"asset_id": "asset-1", "asset_type": "cds_target", "display_name": "CDS source note"}]
    )
    text = str(presenter).casefold()

    forbidden = [
        " ".join(("successful", "import")),
        " ".join(("project", "imported")),
        " ".join(("ready", "for", "execution")),
        "-".join(("experiment", "ready")),
        "-".join(("production", "ready")),
        " ".join(("validated", "construct")),
        " ".join(("optimized", "pathway")),
        " ".join(("yield", "prediction")),
        "-".join(("lab", "ready")),
        " ".join(("wet-lab", "ready")),
        " ".join(("proven", "construct")),
        " ".join(("validated", "pathway")),
    ]
    for phrase in forbidden:
        assert phrase not in text

    assert "documentation-only component library component record" in text
    assert "does not recommend components" in text
    assert "not biological proof" in text
