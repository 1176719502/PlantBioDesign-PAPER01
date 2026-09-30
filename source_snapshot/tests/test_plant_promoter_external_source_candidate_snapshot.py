# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_promoter_catalog_seed_loader as loader


SNAPSHOT_TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "data"
    / "plant_promoter_external_source_candidate_snapshot_template.json"
)

REQUIRED_TOP_LEVEL_FIELDS = {
    "snapshot_name",
    "snapshot_scope",
    "snapshot_version",
    "documentation_boundary_note",
    "supported_source_route_types",
    "required_placeholder_values",
    "candidate_entries",
}

REQUIRED_ENTRY_FIELDS = {
    "candidate_id",
    "source_database",
    "source_record_type",
    "source_route_type",
    "source_url",
    "source_accession",
    "publication_reference",
    "candidate_label",
    "species_scientific_name",
    "native_gene_or_locus",
    "promoter_type",
    "tissue_context",
    "motif_context",
    "retrieved_at",
    "retrieval_method",
    "source_review_status",
    "metadata_completeness_status",
    "curation_status",
    "not_runtime_seed",
    "blocked_reason",
    "review_note",
    "source_trace_note",
    "license_or_usage_note",
}

REQUIRED_PLACEHOLDERS = {
    "source_required",
    "no_accession_assigned",
    "no_publication_assigned",
    "not_curated_yet",
    "candidate_snapshot_only",
    "not_runtime_seed",
    "no_experimental_claim",
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
    _term("runtime_seed_ready"),
)


def _load_snapshot_template() -> dict:
    return json.loads(SNAPSHOT_TEMPLATE_PATH.read_text(encoding="utf-8"))


def _default_seed_record_count() -> int:
    return len(json.loads(loader.DEFAULT_SEED_PATH.read_text(encoding="utf-8"))["records"])


def test_snapshot_template_file_exists_and_is_json() -> None:
    assert SNAPSHOT_TEMPLATE_PATH.exists()
    payload = _load_snapshot_template()

    assert isinstance(payload, dict)
    assert REQUIRED_TOP_LEVEL_FIELDS.issubset(payload)


def test_snapshot_template_contains_placeholder_candidate_example() -> None:
    payload = _load_snapshot_template()
    entries = payload["candidate_entries"]

    assert isinstance(entries, list)
    assert len(entries) >= 1
    assert REQUIRED_PLACEHOLDERS.issubset(set(payload["required_placeholder_values"]))


def test_snapshot_candidate_entries_keep_required_fields_and_block_runtime_seed_use() -> None:
    payload = _load_snapshot_template()

    for entry in payload["candidate_entries"]:
        assert REQUIRED_ENTRY_FIELDS.issubset(entry)
        assert entry["not_runtime_seed"] is True
        assert entry["source_accession"] == "no_accession_assigned"
        assert entry["publication_reference"] == "no_publication_assigned"
        assert entry["curation_status"] == "candidate_snapshot_only"
        assert entry["source_review_status"] == "source_review_required"
        assert entry["metadata_completeness_status"] == "not_curated_yet"
        assert "curated" not in str(entry.get("curation_status", "")).replace("not_curated_yet", "")
        assert "runtime_seed_ready" not in entry
        assert "not_runtime_seed" in entry["blocked_reason"]
        assert "candidate_snapshot_only" in entry["review_note"]
        assert "candidate_snapshot_only" in entry["source_trace_note"]


def test_snapshot_template_does_not_fabricate_real_accessions_or_publications() -> None:
    payload = _load_snapshot_template()

    for entry in payload["candidate_entries"]:
        assert entry["source_accession"] == "no_accession_assigned"
        assert entry["publication_reference"] == "no_publication_assigned"
        assert entry["species_scientific_name"] == "source_required"
        assert entry["motif_context"] == "source_required"


def test_snapshot_template_has_no_unsafe_wording() -> None:
    payload_text = SNAPSHOT_TEMPLATE_PATH.read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in payload_text


def test_snapshot_template_is_not_accepted_as_runtime_seed_catalog() -> None:
    payload = _load_snapshot_template()

    assert payload["snapshot_scope"] == (
        "documentation-only external source candidate snapshot; "
        "not curated manifest; not runtime seed data"
    )
    assert "records" not in payload
    assert "candidate_entries" in payload
    assert "plant_promoter_external_source_candidate_snapshot_template.json" not in str(
        loader.DEFAULT_SEED_PATH
    )

    default_catalog = loader.load_seed_catalog()
    assert len(default_catalog["profiles"]) == _default_seed_record_count()

    try:
        loader.load_seed_catalog(SNAPSHOT_TEMPLATE_PATH)
    except loader.PlantPromoterCatalogSeedError:
        pass
    else:
        raise AssertionError("Candidate snapshot template should not be accepted as seed catalog")
