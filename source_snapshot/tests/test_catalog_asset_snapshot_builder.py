from __future__ import annotations

from services.catalog_asset_snapshot_builder import (
    SNAPSHOT_MISSING_METADATA_NOTE,
    build_catalog_asset_snapshot,
)


def test_snapshot_builder_output_is_deterministic_and_compact():
    record = {
        "part_id": "plant-promoter-seed-001",
        "display_name": "Maize ubiquitin promoter source context",
        "plant_clade": "monocot",
        "species_scientific_name": "Zea mays",
        "species_common_name": "maize",
        "seed_source": "local curated sample records",
        "documentation_status": "source review needed",
        "native_gene_or_locus": "Ubi-1",
        "limitation_notes": ["Documentation context only."],
    }
    evidence_rows = [
        {"tissue_context": "root", "source_database": "Fixture", "source_accession": "ROOT-101"},
        {"tissue_context": "leaf", "source_database": "Fixture", "source_accession": "LEAF-102"},
    ]
    motif_rows = [{"motif_name": "TATA-box note"}, {"motif_name": "CAAT-box note"}]

    first = build_catalog_asset_snapshot(
        record,
        asset_type="plant_promoter_profile",
        evidence_rows=evidence_rows,
        motif_rows=motif_rows,
    )
    second = build_catalog_asset_snapshot(
        record,
        asset_type="plant_promoter_profile",
        evidence_rows=list(reversed(evidence_rows)),
        motif_rows=list(reversed(motif_rows)),
    )

    assert first == second
    assert first == {
        "asset_type": "plant_promoter_profile",
        "asset_id": "plant-promoter-seed-001",
        "asset_label": "Maize ubiquitin promoter source context",
        "asset_version": "",
        "source_label": "local curated sample records",
        "documentation_status": "source review needed",
        "species": "Zea mays (maize)",
        "clade": "monocot",
        "aliases": ["Ubi-1"],
        "tissue_contexts": ["leaf", "root"],
        "motif_labels": ["CAAT-box note", "TATA-box note"],
        "limitation_note": "Documentation context only.",
    }


def test_snapshot_builder_handles_missing_optional_metadata_safely():
    snapshot = build_catalog_asset_snapshot(
        {},
        fallback={"asset_id": "asset-1", "asset_label": "Local asset"},
    )

    assert snapshot["asset_id"] == "asset-1"
    assert snapshot["asset_label"] == "Local asset"
    assert snapshot["aliases"] == []
    assert snapshot["tissue_contexts"] == []
    assert snapshot["motif_labels"] == []
    assert snapshot["missing_metadata_note"] == SNAPSHOT_MISSING_METADATA_NOTE
    assert snapshot["missing_metadata_fields"] == [
        "asset_type",
        "source_label",
        "documentation_status",
    ]
