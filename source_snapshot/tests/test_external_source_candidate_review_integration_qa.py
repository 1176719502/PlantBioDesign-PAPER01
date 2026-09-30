# -*- coding: utf-8 -*-
from __future__ import annotations

import socket
import sqlite3
import sys
from pathlib import Path
from urllib import request as urllib_request

import pytest

from services import external_source_candidate_normalizer as normalizer
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
    _term("valid", "ated"),
    _term("experimentally ", "confirmed"),
    _term("ready ", "for synthesis"),
    _term("ready ", "for wet lab"),
    _term("host ", "compatibility"),
)


def _load_spike() -> dict:
    return normalizer.load_external_source_candidate_snapshot(SPIKE_PATH)


def test_r54f_integration_chain_keeps_r54c_snapshot_as_trace_only_review_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _unexpected_seed_loader(*args: object, **kwargs: object) -> None:
        raise AssertionError("seed loader should not be called by the R54f integration chain")

    def _unexpected_sqlite_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("sqlite should not be called by the R54f integration chain")

    def _unexpected_socket_connect(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access should not be called by the R54f integration chain")

    def _unexpected_urlopen(*args: object, **kwargs: object) -> None:
        raise AssertionError("urlopen should not be called by the R54f integration chain")

    monkeypatch.setattr(
        "services.plant_promoter_catalog_seed_loader.load_seed_catalog",
        _unexpected_seed_loader,
        raising=False,
    )
    monkeypatch.setattr(sqlite3, "connect", _unexpected_sqlite_connect)
    monkeypatch.setattr(socket, "create_connection", _unexpected_socket_connect)
    monkeypatch.setattr(urllib_request, "urlopen", _unexpected_urlopen)
    monkeypatch.delitem(sys.modules, "streamlit", raising=False)

    snapshot = _load_spike()
    summary = normalizer.build_external_source_candidate_summary(snapshot)
    view = presenter.build_external_source_candidate_review_view(snapshot)

    assert snapshot["spike_id"] == "V2_6_R54C_NCBI_GENBANK_CANDIDATE_LOOKUP_SPIKE"
    assert summary["candidate_count"] == 2
    assert summary["source_candidate_identified_count"] == 2
    assert summary["not_runtime_seed_count"] == 2
    assert summary["runtime_seed_ready_count"] == 0
    assert summary["curated_for_runtime_seed_count"] == 0
    assert summary["seed_expansion_status"] == "blocked"

    cards = {card["label"]: card["value"] for card in view["summary_cards"]}
    assert cards["Candidate records"] == "2"
    assert cards["Source candidates identified"] == "2"
    assert cards["Review required"] == "2"
    assert cards["Runtime seed ready"] == "0"
    assert cards["Seed expansion status"] == "blocked"

    assert len(view["candidate_rows"]) == 2
    trace_only_rows = [
        row for row in view["candidate_rows"] if row["row_status"] == "trace_only_candidate"
    ]
    assert len(trace_only_rows) == 2
    assert {row["source_accession"] for row in trace_only_rows} == {"S51061.1", "JX947345.1"}
    assert all(row["not_runtime_seed"] is True for row in trace_only_rows)
    assert all("trace-only candidate source" in row["trace_label"].lower() for row in trace_only_rows)

    assert "documentation-only" in view["boundary_message"].lower()
    assert "not runtime seed" in view["boundary_message"].lower()
    assert any("seed expansion remains blocked" in message.lower() for message in view["blocked_messages"])
    assert any(
        "manually" in message.lower() and "review" in message.lower()
        for message in view["next_action_messages"]
    )
    assert all("seed integration" not in message.lower() for message in view["next_action_messages"])
    assert not any(
        row["warning_code"] == "presenter_runtime_seed_ready_present"
        for row in view["warning_rows"]
    )
    assert "streamlit" not in sys.modules


def test_r54f_integration_chain_surfaces_boundary_flags_without_promoting_seed_ready_state() -> None:
    snapshot = {
        "spike_id": "R54F-UNSAFE",
        "source_route": "test route",
        "retrieved_at": "2026-06-18",
        "not_runtime_seed": True,
        "seed_expansion_status": "blocked",
        "candidate_results": [
            {
                "query_target": "unsafe review candidate",
                "candidate_id": "R54F-UNSAFE-001",
                "source_review_status": "source_candidate_identified",
                "source_database": "NCBI Nucleotide / GenBank",
                "source_url": "https://example.test/unsafe",
                "source_accession": "UNSAFE.1",
                "curation_status": "not_curated_yet",
                "not_runtime_seed": True,
                "runtime_seed_ready": True,
                "curated_for_runtime_seed": True,
            }
        ],
    }

    summary = normalizer.build_external_source_candidate_summary(snapshot)
    view = presenter.build_external_source_candidate_review_view(snapshot)

    assert summary["runtime_seed_ready_count"] == 1
    assert summary["curated_for_runtime_seed_count"] == 1
    assert {
        row["warning_code"] for row in summary["warning_rows"]
    } >= {"runtime_seed_ready_present", "curated_for_runtime_seed_present"}

    assert len(view["candidate_rows"]) == 1
    assert view["candidate_rows"][0]["row_status"] == "boundary_warning"
    assert "must not appear" in view["candidate_rows"][0]["review_status_label"].lower()

    warning_codes = {row["warning_code"] for row in view["warning_rows"]}
    assert "presenter_runtime_seed_ready_present" in warning_codes
    assert "presenter_curated_for_runtime_seed_present" in warning_codes
    assert not any(
        "ready" == row["row_status"] or "runtime_seed_ready" == row["row_status"]
        for row in view["candidate_rows"]
    )


def test_r54f_qa_surfaces_avoid_forbidden_positive_wording() -> None:
    qa_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "qa"
        / "V2_6_R54F_EXTERNAL_SOURCE_CANDIDATE_REVIEW_INTEGRATION_QA.md"
    )
    test_path = Path(__file__).resolve()

    qa_text = qa_path.read_text(encoding="utf-8").lower()
    test_text = test_path.read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in qa_text
        assert forbidden not in test_text
