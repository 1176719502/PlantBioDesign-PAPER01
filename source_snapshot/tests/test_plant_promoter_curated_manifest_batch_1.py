# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_promoter_catalog_seed_loader as loader


BATCH_MANIFEST_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "data"
    / "plant_promoter_49_entry_manifest_batch_1_review.json"
)

REQUIRED_FIELDS = {
    "manifest_id",
    "source_review_status",
    "metadata_completeness_status",
    "curation_status",
    "promoter_label",
    "plant_clade",
    "species_scientific_name",
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
    "review_note",
    "source_trace_note",
}

def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_WORDING = (
    _term("successful ", "import"),
    _term("project ", "imported"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("valid", "ated ", "con", "struct"),
    _term("optimized ", "pathway"),
    _term("yield ", "pre", "diction"),
    _term("recom", "mended"),
    _term("rank", "ing"),
    _term("scor", "ing"),
    _term("optim", "ization"),
    _term("pre", "diction"),
    _term("vali", "dated"),
    _term("experimentally ", "confirmed"),
    _term("ready ", "for synthesis"),
    _term("ready ", "for wet lab"),
    _term("host ", "compatibility"),
)


def _load_batch_manifest() -> dict:
    return json.loads(BATCH_MANIFEST_PATH.read_text(encoding="utf-8"))


def _default_seed_record_count() -> int:
    return len(json.loads(loader.DEFAULT_SEED_PATH.read_text(encoding="utf-8"))["records"])


def test_batch_1_review_file_only_contains_pp_001_to_pp_005() -> None:
    payload = _load_batch_manifest()
    entries = payload["entries"]

    assert len(entries) <= 5
    assert [entry["manifest_id"] for entry in entries] == [
        "PP-001",
        "PP-002",
        "PP-003",
        "PP-004",
        "PP-005",
    ]
    assert payload["batch_manifest_ids"] == [entry["manifest_id"] for entry in entries]


def test_batch_1_entries_keep_required_review_fields() -> None:
    payload = _load_batch_manifest()

    for entry in payload["entries"]:
        assert REQUIRED_FIELDS.issubset(entry)
        assert entry["source_review_status"] == "source_review_required"
        assert entry["metadata_completeness_status"] == "not_curated_yet"
        assert entry["curation_status"] == "not_curated_yet"
        assert entry.get("runtime_seed_ready") is None
        assert "runtime_seed_ready" not in entry.values()


def test_batch_1_missing_sources_stay_explicitly_blocked() -> None:
    payload = _load_batch_manifest()

    for entry in payload["entries"]:
        assert entry["source_database"] == "source_required"
        assert entry["source_accession"] == "no_accession_assigned"
        assert entry["publication_reference"] == "no_publication_assigned"
        assert entry["promoter_label"] == "source_required"
        assert entry["plant_clade"] == "source_required"
        assert entry["species_scientific_name"] == "source_required"
        assert entry["native_gene_or_locus"] == "source_required"
        assert entry["promoter_type"] == "source_required"
        assert entry["tissue_context"] == "source_required"
        assert entry["evidence_type"] == "source_required"
        assert entry["motif_review_status"] == "source_review_required"
        assert entry["motif_name"] == "source_required"
        assert entry["motif_accession"] == "no_accession_assigned"
        assert "source_required" in entry["review_note"]
        assert "not_curated_yet" in entry["review_note"]
        assert "source_review_required" in entry["review_note"]


def test_batch_1_review_file_has_no_unsafe_wording() -> None:
    payload_text = BATCH_MANIFEST_PATH.read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in payload_text


def test_batch_1_review_file_is_not_used_as_seed_catalog() -> None:
    payload = _load_batch_manifest()

    assert payload["manifest_scope"] == "source intake review ledger only; not runtime seed data"
    assert "records" not in payload
    assert "plant_promoter_49_entry_manifest_batch_1_review.json" not in str(loader.DEFAULT_SEED_PATH)

    default_catalog = loader.load_seed_catalog()
    assert len(default_catalog["profiles"]) == _default_seed_record_count()

    try:
        loader.load_seed_catalog(BATCH_MANIFEST_PATH)
    except loader.PlantPromoterCatalogSeedError:
        pass
    else:
        raise AssertionError("Batch 1 review ledger should not be accepted as seed catalog")
