from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.component_library_asset_readback_presenter import (
    DOCUMENTATION_BOUNDARY_NOTE,
    NO_SOURCE_PROVENANCE_IDENTITY,
    NO_SOURCE_REFERENCE_CONTEXT,
    build_component_library_asset_readback_presenter,
    build_component_library_asset_readback_rows,
    normalize_asset_type_label,
    summarize_asset_readback,
)


def test_normalize_asset_type_labels_cover_generic_component_library_taxonomy() -> None:
    assert normalize_asset_type_label("promoter") == "promoter"
    assert normalize_asset_type_label("plant_promoter_profile") == "promoter"
    assert normalize_asset_type_label("cds_target") == "CDS / gene"
    assert normalize_asset_type_label("marker_metadata") == "marker / reporter"
    assert normalize_asset_type_label("plasmid_backbone") == "vector backbone"
    assert normalize_asset_type_label("rbs_5utr") == "UTR / RBS / Kozak"
    assert normalize_asset_type_label("literature_source_note") == "source / reference"
    assert normalize_asset_type_label("construct_component_reference") == "construct component reference"


def test_local_design_asset_rows_expose_generic_documentation_only_readback() -> None:
    rows = build_component_library_asset_readback_rows(
        local_design_assets=[
            {
                "asset_id": "lda-promoter-001",
                "asset_type": "promoter",
                "display_name": "Plant promoter note",
                "aliases": ["Promoter alias"],
                "short_description": "Metadata-only promoter source context.",
                "organism_or_source_context": "Plant source context",
                "sequence_available": False,
                "source_notes": "Local source note.",
                "provenance_status": "source review needed",
                "version_context": "seed v2.6",
                "review_status": "human review needed",
                "human_review_notes": "Review source metadata before citing.",
                "tags": ["promoter"],
                "documentation_boundary_note": "Documentation-only metadata record for review and traceability.",
            }
        ]
    )

    assert rows == [
        {
            "Asset label": "Plant promoter note",
            "Asset type": "promoter",
            "Domain/chassis context": "Plant source context",
            "Source/provenance identity": "Local Design Asset Catalog; lda-promoter-001; source review needed; seed v2.6",
            "Record review status": "human review needed; Review source metadata before citing.",
            "Next documentation review action": "Review next: record source/provenance identity and record review status in the existing review surface.",
            "Documentation context note": "Linked catalog documentation context is not recorded for this Local Design Asset Catalog row.",
            "documentation_context_note": "Linked catalog documentation context is not recorded for this Local Design Asset Catalog row.",
            "Type-specific notes": "Metadata-only promoter source context.; aliases: Promoter alias; tags: promoter; sequence metadata not recorded",
            "Documentation boundary note": "Documentation-only metadata record for review and traceability.",
        }
    ]


def test_linked_catalog_asset_row_preserves_plant_promoter_catalog_source_identity() -> None:
    presenter = build_component_library_asset_readback_presenter(
        linked_catalog_assets=[
            {
                "asset_type": "plant_promoter_profile",
                "asset_id": "ppc-001",
                "asset_label": "Plant promoter profile",
                "source_label": "curated sample source",
                "documentation_status": "source review needed",
                "linkage_role": "project reference",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "ppc-001",
                    "reference_origin": "Pathway Workspace linked catalog assets",
                    "project_documentation_context": "Pathway Workspace linked catalog assets",
                },
                "asset_snapshot": {
                    "asset_type": "plant_promoter_profile",
                    "asset_id": "ppc-001",
                    "asset_label": "Plant promoter profile",
                    "source_label": "curated sample source",
                    "documentation_status": "source review needed",
                    "species": "Nicotiana benthamiana",
                    "clade": "Solanaceae",
                    "tissue_contexts": ["leaf"],
                    "motif_labels": ["motif note"],
                    "limitation_note": "Pinned documentation snapshot for reference context only.",
                },
                "review_status_snapshot": {"review_status": "human review needed"},
                "human_review_required": True,
            }
        ]
    )

    row = presenter["rows"][0]
    assert row["Asset type"] == "promoter"
    assert row["Source/provenance identity"].startswith("Plant Promoter Catalog; ppc-001")
    assert row["Documentation context note"] == (
        "Documentation context: Pathway Workspace linked catalog assets; "
        "origin: Pathway Workspace linked catalog assets; role: project reference; "
        "link state: Linked catalog reference. "
        "Source/provenance identity remains Plant Promoter Catalog / ppc-001."
    )
    assert row["documentation_context_note"] == row["Documentation context note"]
    assert "Plant Promoter Catalog source identity preserved" in row["Type-specific notes"]
    assert presenter["source_identity_note"].startswith("Stored route, source, provenance")
    assert "Review next column" in presenter["source_identity_note"]
    assert presenter["documentation_boundary_note"] == DOCUMENTATION_BOUNDARY_NOTE


def test_documentation_context_note_preserves_source_identity_and_safe_boundaries() -> None:
    presenter = build_component_library_asset_readback_presenter(
        linked_catalog_assets=[
            {
                "asset_type": "source_reference",
                "asset_id": "source-note-208",
                "asset_label": "Source note row",
                "source_context_snapshot": {
                    "catalog": "Local Design Asset Catalog",
                    "profile_id": "source-note-208",
                    "reference_origin": "Expression Wizard catalog context",
                    "project_documentation_context": "Project review documentation context",
                },
                "linked_persisted_status": "Persisted linked catalog reference",
                "linkage_role": "report_context",
            }
        ]
    )

    note = presenter["rows"][0]["documentation_context_note"]

    assert note == (
        "Documentation context: Project review documentation context; "
        "origin: Expression Wizard catalog context; role: report_context; "
        "link state: Persisted linked catalog reference. "
        "Source/provenance identity remains Local Design Asset Catalog / source-note-208."
    )
    assert "Local Design Asset Catalog" in note
    assert "source-note-208" in note
    lower_note = note.casefold()
    forbidden = [
        "recommendation",
        "recommended",
        "validation",
        "validated",
        "optimization",
        "optimized",
        "compatibility proof",
        "yield prediction",
        "wet-lab readiness",
        "ready for execution",
        "experiment-ready",
        "production-ready",
    ]
    for phrase in forbidden:
        assert phrase not in lower_note


def test_construct_component_rows_remain_readback_references_not_catalog_model() -> None:
    presenter = build_component_library_asset_readback_presenter(
        construct_component_rows=[
            {
                "component_label": "Cassette promoter row",
                "component_category": "promoter",
                "cassette_label": "Cassette A",
                "component_reference_label": "Plant promoter profile",
                "sequence_availability_status": "Sequence availability recorded through linked source/reference context",
                "review_metadata_status": "Source/reference metadata recorded for documentation review",
                "review_note": "Manual review note recorded.",
            }
        ]
    )

    row = presenter["rows"][0]
    assert row["Asset type"] == "construct component reference"
    assert row["Domain/chassis context"] == "Cassette A"
    assert row["Documentation context note"] == "Linked catalog documentation context is not recorded for this construct component row."
    assert row["Next documentation review action"] == (
        "Review next: review recorded source/provenance and record review status in the existing review surface before documentation reuse."
    )
    assert "component category: promoter" in row["Type-specific notes"]
    assert "Documentation-only Component Library asset readback" in row["Documentation boundary note"]


def test_summary_counts_group_rows_without_schema_or_package_assumptions() -> None:
    rows = [
        {"Asset type": "promoter", "Source/provenance identity": "Plant Promoter Catalog", "Record review status": "review", "Documentation boundary note": DOCUMENTATION_BOUNDARY_NOTE},
        {"Asset type": "CDS / gene", "Source/provenance identity": "Local Design Asset Catalog", "Record review status": "review", "Documentation boundary note": DOCUMENTATION_BOUNDARY_NOTE},
    ]
    summary = summarize_asset_readback(rows)

    assert summary["total_asset_rows"] == 2
    assert summary["asset_type_counts"] == {"CDS / gene": 1, "promoter": 1}
    assert summary["asset_type_count"] == 2
    assert summary["rows_with_source_provenance_identity"] == 2
    assert summary["rows_with_evidence_review_metadata"] == 2
    assert summary["rows_with_next_documentation_review_action"] == 0
    assert summary["rows_with_documentation_boundary_note"] == 2


def test_component_library_readback_next_action_flags_missing_source_or_review_context() -> None:
    presenter = build_component_library_asset_readback_presenter(
        construct_component_rows=[
            {
                "component_label": "Component needing source review",
                "component_category": "terminator",
                "component_reference_label": "",
                "sequence_availability_status": "Sequence availability not recorded",
                "review_metadata_status": "Review metadata gap",
                "review_note": "",
                "cassette_label": "Cassette review row",
            }
        ]
    )

    row = presenter["rows"][0]
    assert row["Source/provenance identity"] == NO_SOURCE_REFERENCE_CONTEXT
    assert row["Next documentation review action"] == (
        "Review next: record source/provenance identity and record review status in the existing review surface."
    )
    assert presenter["summary"]["rows_with_next_documentation_review_action"] == 1
    assert "Review next: clear active filters or use existing review surfaces for saved component asset rows" in presenter["empty_state"]


def test_component_library_readback_does_not_count_recorded_review_action_as_gap() -> None:
    rows = build_component_library_asset_readback_rows(
        construct_component_rows=[
            {
                "component_label": "Component with recorded source context",
                "component_category": "promoter",
                "component_reference_label": "Recorded source row",
                "sequence_availability_status": "Sequence availability recorded through linked source/reference context",
                "review_metadata_status": "Source/reference metadata recorded for documentation review",
                "review_note": "Manual review note recorded.",
                "cassette_label": "Cassette A",
            }
        ]
    )
    summary = summarize_asset_readback(rows)

    assert rows[0]["Next documentation review action"] == (
        "Review next: review recorded source/provenance and record review status in the existing review surface before documentation reuse."
    )
    assert summary["rows_with_next_documentation_review_action"] == 0
    assert summary["rows_with_source_provenance_identity"] == 1


def test_component_library_readback_flags_missing_local_asset_source_identity() -> None:
    rows = build_component_library_asset_readback_rows(
        local_design_assets=[
            {
                "asset_type": "source_reference",
                "display_name": "Unidentified source note",
                "review_status": "human review needed",
            }
        ]
    )

    row = rows[0]
    assert row["Source/provenance identity"] == NO_SOURCE_PROVENANCE_IDENTITY
    assert row["Next documentation review action"] == (
        "Review next: record source/provenance identity and record review status in the existing review surface."
    )


def test_component_library_readback_treats_placeholder_metadata_as_missing() -> None:
    rows = build_component_library_asset_readback_rows(
        construct_component_rows=[
            {
                "component_label": "Placeholder component",
                "component_category": "promoter",
                "component_reference_label": "Unknown",
                "sequence_availability_status": "Not specified",
                "review_metadata_status": "N/A",
                "review_note": "TBD",
                "cassette_label": "Cassette placeholder",
            }
        ]
    )
    summary = summarize_asset_readback(rows)

    assert rows[0]["Source/provenance identity"] == NO_SOURCE_REFERENCE_CONTEXT
    assert rows[0]["Record review status"] == "Not recorded"
    assert rows[0]["Next documentation review action"] == (
        "Review next: record source/provenance identity and record review status in the existing review surface."
    )
    assert summary["rows_with_source_provenance_identity"] == 0
    assert summary["rows_with_evidence_review_metadata"] == 0
    assert summary["rows_with_next_documentation_review_action"] == 1
