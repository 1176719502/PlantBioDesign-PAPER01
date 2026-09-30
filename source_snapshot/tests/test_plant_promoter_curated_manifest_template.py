# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_promoter_catalog_seed_loader as loader


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "docs" / "data" / "plant_promoter_49_entry_manifest_template.json"
REQUIRED_FIELDS = {
    "manifest_id",
    "promoter_label",
    "plant_clade",
    "species_scientific_name",
    "species_common_name",
    "taxonomy_id",
    "cultivar_or_ecotype",
    "native_gene_or_locus",
    "promoter_type",
    "tissue_context",
    "evidence_type",
    "source_database",
    "source_accession",
    "publication_reference",
    "motif_review_status",
    "motif_name",
    "motif_accession",
    "curation_status",
    "source_review_status",
    "metadata_completeness_status",
    "review_note",
}
ALLOWED_SOURCE_REVIEW_STATUS = {
    "source_required",
    "source_review_required",
    "source_review_in_progress",
    "source_review_complete",
    "deferred_incomplete",
    "curated",
}
ALLOWED_METADATA_COMPLETENESS_STATUS = {
    "not_curated_yet",
    "placeholder",
    "metadata_pending",
    "metadata_partial",
    "metadata_complete",
    "metadata_incomplete",
}
ALLOWED_MOTIF_REVIEW_STATUS = {
    "not_curated_yet",
    "not_reviewed",
    "motif_review_required",
    "motif_review_in_progress",
    "motif_review_complete",
    "motif_annotation_missing",
    "motif_curated",
}
ALLOWED_CURATION_STATUS = {
    "not_curated_yet",
    "not_curated",
    "curation_pending",
    "curation_in_progress",
    "curation_complete",
    "curated",
    "incomplete_retained",
}
FORBIDDEN_WORDS = (
    "recommended",
    "validated",
    "optimized",
    "ready for wet lab",
    "ready for synthesis",
    "seed loader",
)


def _default_seed_record_count() -> int:
    return len(json.loads(loader.DEFAULT_SEED_PATH.read_text(encoding="utf-8"))["records"])


def test_curated_manifest_template_is_49_entry_placeholder_scaffold() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = payload["entries"]

    assert len(entries) == 49
    manifest_ids = [entry["manifest_id"] for entry in entries]
    assert manifest_ids == [f"PP-{index:03d}" for index in range(1, 50)]
    assert len(set(manifest_ids)) == 49

    for entry in entries:
        assert REQUIRED_FIELDS.issubset(entry)
        assert entry["promoter_label"] == "source review required"
        assert entry["plant_clade"] == "source_required"
        assert entry["species_scientific_name"] == "source_required"
        assert entry["species_common_name"] == "source_required"
        assert entry["taxonomy_id"] == "no_accession_assigned"
        assert entry["cultivar_or_ecotype"] == "source_required"
        assert entry["native_gene_or_locus"] == "source_required"
        assert entry["promoter_type"] == "source_required"
        assert entry["tissue_context"] == "source_required"
        assert entry["evidence_type"] == "source_required"
        assert entry["source_database"] == "source_required"
        assert entry["source_accession"] == "no_accession_assigned"
        assert entry["publication_reference"] == "no_publication_assigned"
        assert entry["motif_review_status"] == "not_curated_yet"
        assert entry["motif_name"] == "no_motif_assigned"
        assert entry["motif_accession"] == "no_accession_assigned"
        assert entry["curation_status"] == "not_curated_yet"
        assert entry["source_review_status"] == "source_required"
        assert entry["metadata_completeness_status"] == "not_curated_yet"
        assert entry["review_note"] == (
            "source_required; not_curated_yet; no accession assigned; no publication assigned; "
            "no motif assigned; no experimental claim"
        )
        assert entry["source_review_status"] in ALLOWED_SOURCE_REVIEW_STATUS
        assert entry["metadata_completeness_status"] in ALLOWED_METADATA_COMPLETENESS_STATUS
        assert entry["motif_review_status"] in ALLOWED_MOTIF_REVIEW_STATUS
        assert entry["curation_status"] in ALLOWED_CURATION_STATUS
        entry_text = json.dumps(entry, sort_keys=True)
        assert "ready" not in entry_text.lower()
        assert "validated" not in entry_text.lower()
        assert "recommended" not in entry_text.lower()
        assert "optimized" not in entry_text.lower()
        assert "wet lab" not in entry_text.lower()


def test_manifest_template_is_not_runtime_seed_catalog() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert payload["manifest_scope"] == "source review scaffold only; not runtime seed data"
    assert "records" not in payload

    default_catalog = loader.load_seed_catalog()
    assert "plant_promoter_49_entry_manifest_template.json" not in str(loader.DEFAULT_SEED_PATH)
    assert len(default_catalog["profiles"]) == _default_seed_record_count()

    template_catalog_path = MANIFEST_PATH
    try:
        loader.load_seed_catalog(template_catalog_path)
    except loader.PlantPromoterCatalogSeedError:
        pass
    else:
        raise AssertionError("Template manifest should not be accepted as runtime seed catalog")


def test_manifest_template_retains_placeholder_review_only_statuses() -> None:
    payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    for entry in payload["entries"]:
        assert entry["source_review_status"] in ALLOWED_SOURCE_REVIEW_STATUS
        assert entry["metadata_completeness_status"] in ALLOWED_METADATA_COMPLETENESS_STATUS
        assert entry["motif_review_status"] in ALLOWED_MOTIF_REVIEW_STATUS
        assert entry["curation_status"] in ALLOWED_CURATION_STATUS
        assert entry["source_review_status"] != "curated"
        assert entry["metadata_completeness_status"] != "metadata_complete"
        assert entry["motif_review_status"] != "motif_curated"
        assert entry["curation_status"] != "curated"
        assert entry["review_note"].startswith("source_required; not_curated_yet")


def test_manifest_template_does_not_use_unsafe_runtime_seed_language() -> None:
    payload_text = MANIFEST_PATH.read_text(encoding="utf-8")
    lowered = payload_text.lower()
    for forbidden in FORBIDDEN_WORDS:
        assert forbidden not in lowered

    assert "runtime seed" in lowered
    assert "source review scaffold only" in lowered
