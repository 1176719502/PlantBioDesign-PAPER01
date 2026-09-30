# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_promoter_catalog_seed_loader as loader


SPIKE_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "data"
    / "plant_promoter_ncbi_candidate_lookup_spike.json"
)

REQUIRED_TOP_LEVEL_FIELDS = {
    "spike_id",
    "source_route",
    "retrieved_at",
    "not_runtime_seed",
    "seed_expansion_status",
    "query_targets",
    "candidate_results",
}

REQUIRED_RESULT_FIELDS = {
    "query_target",
    "candidate_id",
    "source_review_status",
    "source_database",
    "source_record_type",
    "source_url",
    "source_accession",
    "record_title",
    "candidate_label",
    "species_scientific_name",
    "native_gene_or_locus",
    "promoter_type",
    "publication_reference",
    "motif_context",
    "metadata_completeness_status",
    "curation_status",
    "not_runtime_seed",
    "review_note",
    "source_trace_note",
    "license_or_usage_note",
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
    _term("runtime", "_seed", "_ready"),
    _term("curated", "_for", "_runtime", "_seed"),
)


def _load_spike() -> dict:
    return json.loads(SPIKE_PATH.read_text(encoding="utf-8"))


def _default_seed_record_count() -> int:
    return len(json.loads(loader.DEFAULT_SEED_PATH.read_text(encoding="utf-8"))["records"])


def test_ncbi_candidate_lookup_spike_file_exists_and_is_json() -> None:
    assert SPIKE_PATH.exists()
    payload = _load_spike()

    assert isinstance(payload, dict)
    assert REQUIRED_TOP_LEVEL_FIELDS.issubset(payload)


def test_ncbi_candidate_lookup_spike_blocks_runtime_seed_expansion() -> None:
    payload = _load_spike()

    assert payload["not_runtime_seed"] is True
    assert payload["seed_expansion_status"] == "blocked"


def test_ncbi_candidate_lookup_spike_keeps_narrow_target_and_result_count() -> None:
    payload = _load_spike()

    assert len(payload["query_targets"]) <= 2
    assert len(payload["candidate_results"]) <= 2


def test_ncbi_candidate_lookup_spike_results_have_required_review_status() -> None:
    payload = _load_spike()

    for result in payload["candidate_results"]:
        assert REQUIRED_RESULT_FIELDS.issubset(result)
        assert result["source_review_status"] in {
            "source_candidate_identified",
            "no_acceptable_candidate_selected",
        }
        assert result["not_runtime_seed"] is True


def test_identified_candidates_have_source_url_and_accession_or_stable_identifier() -> None:
    payload = _load_spike()

    for result in payload["candidate_results"]:
        if result["source_review_status"] != "source_candidate_identified":
            continue

        assert result["source_url"].startswith("https://www.ncbi.nlm.nih.gov/nuccore/")
        assert result["source_accession"] not in {
            "",
            "no_accession_assigned",
            "source_review_required",
        }
        assert result["record_title"]
        assert result["species_scientific_name"]


def test_unassigned_accession_or_publication_is_not_marked_curated() -> None:
    payload = _load_spike()

    for result in payload["candidate_results"]:
        has_unassigned_trace = (
            result["source_accession"] == "no_accession_assigned"
            or result["publication_reference"] == "no_publication_assigned"
        )
        if has_unassigned_trace:
            assert result["curation_status"] != "curated"
            assert result["curation_status"] == "not_curated_yet"


def test_ncbi_candidate_lookup_spike_has_no_runtime_or_unsafe_wording() -> None:
    payload_text = SPIKE_PATH.read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in payload_text


def test_ncbi_candidate_lookup_spike_is_not_accepted_as_runtime_seed_catalog() -> None:
    payload = _load_spike()

    assert payload["not_runtime_seed"] is True
    assert "records" not in payload
    assert "profiles" not in payload
    assert "plant_promoter_ncbi_candidate_lookup_spike.json" not in str(loader.DEFAULT_SEED_PATH)

    default_catalog = loader.load_seed_catalog()
    assert len(default_catalog["profiles"]) == _default_seed_record_count()

    try:
        loader.load_seed_catalog(SPIKE_PATH)
    except loader.PlantPromoterCatalogSeedError:
        pass
    else:
        raise AssertionError("NCBI candidate lookup spike should not be accepted as seed catalog")
