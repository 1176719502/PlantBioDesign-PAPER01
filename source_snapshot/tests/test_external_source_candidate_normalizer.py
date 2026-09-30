# -*- coding: utf-8 -*-
from __future__ import annotations
from pathlib import Path

import pytest

from services import external_source_candidate_normalizer as normalizer


SPIKE_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "data"
    / "plant_promoter_ncbi_candidate_lookup_spike.json"
)


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
    _term("curated_for_runtime_seed"),
)


def _load_spike() -> dict:
    return normalizer.load_external_source_candidate_snapshot(SPIKE_PATH)


def test_load_external_source_candidate_snapshot_reads_r54c_json() -> None:
    payload = _load_spike()

    assert payload["spike_id"] == "V2_6_R54C_NCBI_GENBANK_CANDIDATE_LOOKUP_SPIKE"
    assert len(payload["candidate_results"]) == 2


def test_build_external_source_candidate_summary_counts_r54c_candidates() -> None:
    summary = normalizer.build_external_source_candidate_summary(_load_spike())

    assert summary["candidate_count"] == 2
    assert summary["query_target_count"] == 2
    assert summary["source_candidate_identified_count"] == 2
    assert summary["no_acceptable_candidate_selected_count"] == 0
    assert summary["not_runtime_seed_count"] == 2
    assert summary["runtime_seed_ready_count"] == 0
    assert summary["curated_for_runtime_seed_count"] == 0
    assert summary["records_missing_trace_count"] == 0
    assert summary["seed_expansion_status"] == "blocked"
    assert summary["review_required_count"] == 2
    assert summary["warning_rows"] == []


def test_list_external_source_candidate_rows_keeps_trace_fields_without_runtime_promotion() -> None:
    rows = normalizer.list_external_source_candidate_rows(_load_spike())

    assert len(rows) == 2
    assert {row["source_accession"] for row in rows} == {"S51061.1", "JX947345.1"}
    for row in rows:
        assert set(
            [
                "query_target",
                "source_database",
                "source_accession",
                "source_url",
                "source_review_status",
                "curation_status",
                "not_runtime_seed",
            ]
        ).issubset(row)
        assert row["source_review_status"] == "source_candidate_identified"
        assert row["curation_status"] == "not_curated_yet"
        assert row["not_runtime_seed"] is True


def test_normalize_external_source_candidate_snapshot_keeps_candidate_trace_only() -> None:
    summary = normalizer.normalize_external_source_candidate_snapshot(_load_spike())

    assert summary["runtime_seed_ready_count"] == 0
    assert summary["curated_for_runtime_seed_count"] == 0
    assert all(
        row["source_accession"] in {"S51061.1", "JX947345.1"}
        for row in summary["candidate_rows"]
    )


def test_normalizer_defends_missing_file() -> None:
    missing_path = SPIKE_PATH.parent / "missing_external_source_candidate_snapshot.json"

    with pytest.raises(normalizer.ExternalSourceCandidateNormalizerError):
        normalizer.load_external_source_candidate_snapshot(missing_path)


def test_normalizer_defends_invalid_json(tmp_path: Path) -> None:
    invalid_path = tmp_path / "invalid_snapshot.json"
    invalid_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(normalizer.ExternalSourceCandidateNormalizerError):
        normalizer.load_external_source_candidate_snapshot(invalid_path)


def test_normalizer_reports_missing_candidate_results_and_required_fields() -> None:
    summary = normalizer.build_external_source_candidate_summary(
        {
            "spike_id": "BROKEN",
            "source_route": "test route",
            "retrieved_at": "2026-06-18",
            "not_runtime_seed": True,
            "seed_expansion_status": "blocked",
        }
    )

    assert summary["candidate_count"] == 0
    assert summary["review_required_count"] == 0
    assert any(
        row["warning_code"] == "missing_candidate_results"
        for row in summary["warning_rows"]
    )


def test_normalizer_reports_unsafe_candidate_flags_and_missing_trace() -> None:
    summary = normalizer.build_external_source_candidate_summary(
        {
            "spike_id": "UNSAFE",
            "source_route": "test route",
            "retrieved_at": "2026-06-18",
            "not_runtime_seed": False,
            "seed_expansion_status": "open",
            "candidate_results": [
                {
                    "query_target": "unsafe candidate",
                    "candidate_id": "UNSAFE-001",
                    "source_review_status": "source_candidate_identified",
                    "source_database": "NCBI",
                    "source_url": "",
                    "source_accession": "",
                    "curation_status": "not_curated_yet",
                    "not_runtime_seed": False,
                    "runtime_seed_ready": True,
                    "curated_for_runtime_seed": True,
                }
            ],
        }
    )

    assert summary["candidate_count"] == 1
    assert summary["records_missing_trace_count"] == 1
    assert summary["runtime_seed_ready_count"] == 1
    assert summary["curated_for_runtime_seed_count"] == 1
    assert summary["review_required_count"] == 1
    assert {row["warning_code"] for row in summary["warning_rows"]} >= {
        "top_level_not_runtime_seed_not_true",
        "seed_expansion_status_not_blocked",
        "identified_candidate_missing_source_url",
        "identified_candidate_missing_stable_identifier",
        "candidate_not_runtime_seed_not_true",
        "runtime_seed_ready_present",
        "curated_for_runtime_seed_present",
    }


def test_normalizer_does_not_promote_candidate_snapshot_to_seed_loader_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unexpected_loader_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("seed loader should not be called by external source candidate normalizer")

    monkeypatch.setattr(
        "services.plant_promoter_catalog_seed_loader.load_seed_catalog",
        _unexpected_loader_call,
        raising=False,
    )

    summary = normalizer.build_external_source_candidate_summary(_load_spike())

    assert summary["candidate_count"] == 2
    assert all("part_id" not in row for row in summary["candidate_rows"])


def test_normalizer_surfaces_no_unsafe_wording_in_service_doc_and_qa_surfaces() -> None:
    qa_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "qa"
        / "V2_6_R54D_EXTERNAL_SOURCE_CANDIDATE_NORMALIZER_QA.md"
    )
    text = qa_path.read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in text
