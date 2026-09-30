# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import pytest

from services import external_source_candidate_review_presenter as presenter


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
)


def test_presenter_builds_review_view_from_r54c_json_path() -> None:
    view = presenter.build_external_source_candidate_review_view_from_path(SPIKE_PATH)

    assert view["title"] == "External Source Candidate Review"
    assert view["source_route"] == "NCBI / GenBank / RefSeq candidate lookup spike"
    assert view["retrieved_at"] == "2026-06-18"
    assert view["seed_expansion_status"] == "blocked"
    assert view["empty_state_message"] == ""


def test_presenter_summary_cards_and_candidate_rows_match_r54c_trace_only_snapshot() -> None:
    view = presenter.build_external_source_candidate_review_view_from_path(SPIKE_PATH)

    cards = {card["label"]: card["value"] for card in view["summary_cards"]}
    assert cards["Candidate records"] == "2"
    assert cards["Source candidates identified"] == "2"
    assert cards["Review required"] == "2"
    assert cards["Seed expansion status"] == "blocked"

    rows = view["candidate_rows"]
    assert len(rows) == 2
    assert {row["source_accession"] for row in rows} == {"S51061.1", "JX947345.1"}
    assert all(row["row_status"] == "trace_only_candidate" for row in rows)
    assert all(row["not_runtime_seed"] is True for row in rows)
    assert all("trace-only candidate source" in row["trace_label"].lower() for row in rows)
    assert all("runtime" not in row["review_status_label"].lower() or "must not appear" not in row["review_status_label"].lower() for row in rows)


def test_presenter_boundary_message_and_blocked_messages_keep_documentation_only_scope() -> None:
    view = presenter.build_external_source_candidate_review_view_from_path(SPIKE_PATH)

    assert "documentation-only" in view["boundary_message"].lower()
    assert "not runtime seed" in view["boundary_message"].lower()
    assert any("runtime seed" in message.lower() for message in view["blocked_messages"])
    assert any("curated manifest" in message.lower() for message in view["blocked_messages"])


def test_presenter_surfaces_existing_normalizer_warning_rows() -> None:
    view = presenter.build_external_source_candidate_review_view(
        {
            "spike_id": "WARNINGS",
            "source_route": "test route",
            "retrieved_at": "2026-06-18",
            "not_runtime_seed": True,
            "seed_expansion_status": "blocked",
            "candidate_results": [
                {
                    "query_target": "test promoter",
                    "candidate_id": "WARN-001",
                    "source_review_status": "source_candidate_identified",
                    "source_database": "NCBI",
                    "source_url": "",
                    "source_accession": "",
                    "curation_status": "not_curated_yet",
                    "not_runtime_seed": True,
                }
            ],
        }
    )

    warning_codes = {row["warning_code"] for row in view["warning_rows"]}
    assert "identified_candidate_missing_source_url" in warning_codes
    assert "identified_candidate_missing_stable_identifier" in warning_codes
    assert "presenter_missing_trace_records" in warning_codes


def test_presenter_provides_empty_state_when_candidate_results_are_missing() -> None:
    view = presenter.build_external_source_candidate_review_view(
        {
            "spike_id": "EMPTY",
            "source_route": "test route",
            "retrieved_at": "2026-06-18",
            "not_runtime_seed": True,
            "seed_expansion_status": "blocked",
        }
    )

    assert view["candidate_rows"] == []
    assert view["empty_state_message"]
    assert "documentation-only" in view["empty_state_message"].lower()


def test_presenter_adds_boundary_warnings_for_runtime_seed_positive_flags() -> None:
    view = presenter.build_external_source_candidate_review_view(
        {
            "spike_id": "UNSAFE",
            "source_route": "test route",
            "retrieved_at": "2026-06-18",
            "not_runtime_seed": True,
            "seed_expansion_status": "open",
            "candidate_results": [
                {
                    "query_target": "unsafe candidate",
                    "candidate_id": "UNSAFE-001",
                    "source_review_status": "source_candidate_identified",
                    "source_database": "NCBI",
                    "source_url": "https://example.test/unsafe",
                    "source_accession": "UNSAFE.1",
                    "curation_status": "not_curated_yet",
                    "not_runtime_seed": True,
                    "runtime_seed_ready": True,
                    "curated_for_runtime_seed": True,
                }
            ],
        }
    )

    warning_codes = {row["warning_code"] for row in view["warning_rows"]}
    assert "presenter_seed_expansion_not_blocked" in warning_codes
    assert "presenter_runtime_seed_ready_present" in warning_codes
    assert "presenter_curated_for_runtime_seed_present" in warning_codes
    assert view["candidate_rows"][0]["row_status"] == "boundary_warning"


def test_presenter_defends_against_partial_candidate_rows_without_crashing() -> None:
    rows = presenter.build_candidate_review_rows(
        [
            {
                "query_target": "partial candidate",
                "candidate_id": "",
            },
            None,
        ]
    )

    assert len(rows) == 2
    assert rows[0]["candidate_id"] == "candidate-row-1"
    assert rows[0]["source_accession"] == "missing-accession"
    assert rows[1]["candidate_id"] == "candidate-row-2"


def test_presenter_does_not_call_seed_loader_db_or_ui(monkeypatch: pytest.MonkeyPatch) -> None:
    def _unexpected_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("presenter should not call external runtime dependencies")

    monkeypatch.setattr(
        "services.plant_promoter_catalog_seed_loader.load_seed_catalog",
        _unexpected_call,
        raising=False,
    )
    monkeypatch.setattr(
        "sqlite3.connect",
        _unexpected_call,
        raising=False,
    )

    view = presenter.build_external_source_candidate_review_view_from_path(SPIKE_PATH)

    assert len(view["candidate_rows"]) == 2


def test_presenter_qa_doc_avoids_forbidden_wording() -> None:
    qa_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "qa"
        / "V2_6_R54E_EXTERNAL_SOURCE_CANDIDATE_REVIEW_PRESENTER_QA.md"
    )
    text = qa_path.read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in text
