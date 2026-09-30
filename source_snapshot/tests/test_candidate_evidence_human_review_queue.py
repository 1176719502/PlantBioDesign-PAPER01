# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib
from pathlib import Path

from services import candidate_evidence_human_review_queue as queue_service
from services import candidate_evidence_review_matrix as matrix_service


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
    _term("best"),
    _term("rank", "ing"),
    _term("scor", "ing"),
    _term("ready ", "for synthesis"),
    _term("host ", "compatibility"),
)


def _complete_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "candidate_label": "Maize promoter source context",
        "source_category": "Plant Promoter Catalog",
        "source_identifier": "PP-TRACE-001",
        "source_hash": "sha256:abc123",
        "review_status": "source review recorded",
    }
    record.update(overrides)
    return record


def test_empty_input_returns_safe_empty_queue() -> None:
    queue = queue_service.build_candidate_evidence_human_review_queue([])

    assert queue["rows"] == []
    assert queue["summary"]["queue_item_count"] == 0
    assert queue["summary"]["candidate_count"] == 0
    assert queue["empty_state_message"]
    assert "manual review only" in queue["boundary_notes"][0].lower()


def test_complete_rows_return_low_priority_confirmation_only() -> None:
    queue = queue_service.build_candidate_evidence_human_review_queue([_complete_record()])

    assert queue["summary"]["queue_item_count"] == 1
    assert queue["summary"]["documentation_gap_count"] == 1
    assert queue["summary"]["low_priority_count"] == 1
    row = queue["rows"][0]
    assert row["category"] == "documentation_gap"
    assert row["severity"] == "low"
    assert row["issue"] == queue_service.QUEUE_CONFIRMATION_ISSUE


def test_missing_provenance_fields_produce_provenance_gap_queue_items() -> None:
    queue = queue_service.build_candidate_evidence_human_review_queue(
        [
            {
                "candidate_label": "Partial candidate",
                "review_status": "source review recorded",
            }
        ]
    )

    issues = {(row["category"], row["issue"]) for row in queue["rows"]}
    assert ("provenance_gap", "Missing source/provenance details") in issues
    assert queue["summary"]["provenance_gap_count"] == 3
    assert queue["summary"]["high_priority_count"] >= 2


def test_missing_review_status_produces_review_follow_up_queue_items() -> None:
    queue = queue_service.build_candidate_evidence_human_review_queue(
        [
            {
                "candidate_label": "Review needed candidate",
                "source_category": "Plant Promoter Catalog",
                "source_identifier": "PP-TRACE-002",
                "source_hash": "sha256:def456",
            }
        ]
    )

    issues = [row["issue"] for row in queue["rows"] if row["category"] == "review_follow_up"]
    assert "Missing review status" in issues
    assert "Records needing manual follow-up" in issues
    assert queue["summary"]["review_follow_up_count"] == 2


def test_placeholder_values_keep_source_and_review_follow_up_visible() -> None:
    queue = queue_service.build_candidate_evidence_human_review_queue(
        [
            {
                "candidate_label": "Placeholder candidate",
                "source_category": "Not specified",
                "source_identifier": "Unknown",
                "source_hash": "TBD",
                "review_status": "N/A",
            }
        ]
    )

    assert queue["summary"]["queue_item_count"] == 5
    assert queue["summary"]["provenance_gap_count"] == 3
    assert queue["summary"]["review_follow_up_count"] == 2
    assert {row["source_context"] for row in queue["rows"]} == {
        "source not recorded / identifier not recorded"
    }


def test_output_order_is_deterministic() -> None:
    queue = queue_service.build_candidate_evidence_human_review_queue(
        [
            _complete_record(candidate_label="Zulu", source_identifier="Z-002"),
            {
                "candidate_label": "Alpha",
                "source_category": "Catalog A",
            },
            {
                "candidate_label": "Alpha",
                "source_category": "Catalog Z",
            },
        ]
    )

    assert [(row["candidate_label"], row["category"], row["issue"]) for row in queue["rows"]] == [
        ("Alpha", "provenance_gap", "Missing source/provenance details"),
        ("Alpha", "provenance_gap", "Missing source/provenance details"),
        ("Alpha", "provenance_gap", "Missing source/provenance details"),
        ("Alpha", "provenance_gap", "Missing source/provenance details"),
        ("Alpha", "review_follow_up", "Missing review status"),
        ("Alpha", "review_follow_up", "Missing review status"),
        ("Alpha", "review_follow_up", "Records needing manual follow-up"),
        ("Alpha", "review_follow_up", "Records needing manual follow-up"),
        ("Zulu", "documentation_gap", "Documentation review remains available for confirmation."),
    ]


def test_service_accepts_existing_matrix_output() -> None:
    matrix = matrix_service.build_candidate_evidence_review_matrix(
        [
            _complete_record(candidate_label="Matrix-backed candidate"),
            {"candidate_label": "Partial matrix-backed candidate"},
        ]
    )

    queue = queue_service.build_candidate_evidence_human_review_queue(matrix)

    assert queue["summary"]["candidate_count"] == 2
    assert any(row["candidate_label"] == "Matrix-backed candidate" for row in queue["rows"])
    assert any(row["candidate_label"] == "Partial matrix-backed candidate" for row in queue["rows"])


def test_queue_copy_avoids_unsafe_wording() -> None:
    queue_text = str(
        queue_service.build_candidate_evidence_human_review_queue(
            [_complete_record(), {"candidate_label": "Partial candidate"}]
        )
    ).lower()
    service_text = (
        Path(__file__).resolve().parents[1]
        / "services"
        / "candidate_evidence_human_review_queue.py"
    ).read_text(encoding="utf-8").lower()

    for forbidden in FORBIDDEN_WORDING:
        assert forbidden not in queue_text
        assert forbidden not in service_text


def test_queue_service_does_not_import_streamlit(monkeypatch) -> None:
    original_import = builtins.__import__

    def _block_streamlit_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "streamlit" or name.startswith("streamlit."):
            raise AssertionError("candidate evidence human review queue must not import Streamlit")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_streamlit_import)

    queue = queue_service.build_candidate_evidence_human_review_queue([_complete_record()])

    assert queue["summary"]["queue_item_count"] == 1
    importlib.reload(queue_service)
