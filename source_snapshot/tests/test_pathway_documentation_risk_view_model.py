from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.pathway_documentation_risk_view_model import build_documentation_risk_summary


def _row(rows: list[dict], label: str) -> dict:
    return next(row for row in rows if row["label"] == label)


def _summary_text(rows: list[dict]) -> str:
    return " ".join(str(value) for row in rows for value in row.values()).lower()


def test_empty_project_context_returns_no_records_summary():
    rows = build_documentation_risk_summary({}, [], [], [], [], snapshots=[])

    assert [row["label"] for row in rows] == [
        "Pathway steps documentation",
        "Linked expression designs",
        "Test records / observations",
        "Review signals",
        "Documentation snapshots",
        "Project outputs traceability",
    ]
    assert {row["status"] for row in rows} == {"no_records"}


def test_steps_without_linked_designs_mark_traceability_review_gap():
    rows = build_documentation_risk_summary(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10, "step_order": 1, "step_name": "Recorded step"}],
        [],
        [],
        [],
        snapshots=[],
    )

    assert _row(rows, "Pathway steps documentation")["status"] == "available_for_review"
    assert _row(rows, "Linked expression designs")["status"] == "needs_review"
    assert _row(rows, "Test records / observations")["status"] == "needs_documentation"
    assert _row(rows, "Project outputs traceability")["status"] == "needs_review"


def test_linked_designs_present_are_available_for_traceability_review():
    rows = build_documentation_risk_summary(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10, "step_name": "Recorded step"}],
        [{"id": 20, "step_id": 10, "design_name": "Linked design"}],
        [],
        [],
    )

    links = _row(rows, "Linked expression designs")
    assert links["status"] == "available_for_review"
    assert links["related_count"] == 1
    assert "traceability review" in links["detail"]


def test_review_signals_present_require_human_review():
    rows = build_documentation_risk_summary(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10}],
        [],
        [],
        [{"signal_type": "missing_documentation", "message": "Review field."}],
    )

    signals = _row(rows, "Review signals")
    assert signals["status"] == "needs_review"
    assert signals["related_count"] == 1
    assert "human review" in signals["detail"]


def test_snapshots_present_are_available_for_review_history():
    rows = build_documentation_risk_summary(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10}],
        [],
        [],
        [],
        snapshots=[{"id": 30, "title": "Snapshot"}],
    )

    snapshots = _row(rows, "Documentation snapshots")
    assert snapshots["status"] == "available_for_review"
    assert snapshots["related_count"] == 1
    assert "local review history" in snapshots["detail"]


def test_missing_optional_fields_do_not_raise():
    rows = build_documentation_risk_summary(
        {"id": None},
        [None, "bad", {"id": None}],
        [None, {"step_id": None}],
        [None, {"step_id": None}],
        [None, {"signal_type": None}],
        snapshots=[None, {"id": None}],
    )

    assert len(rows) == 6
    assert _row(rows, "Pathway steps documentation")["related_count"] == 1
    assert _row(rows, "Project outputs traceability")["status"] == "available_for_review"


def test_inputs_are_not_mutated():
    project = {"id": 1, "name": "Documentation project", "metadata": {"nested": "value"}}
    steps = [{"id": 10, "metadata": {"nested": "step"}}]
    expression_links = [{"id": 20, "step_id": 10}]
    test_records = [{"id": 30, "step_id": 10}]
    review_signals = [{"signal_type": "gap", "evidence": {"step_id": 10}}]
    snapshots = [{"id": 40, "payload": {"pathway_steps": []}}]
    before = copy.deepcopy((project, steps, expression_links, test_records, review_signals, snapshots))

    rows = build_documentation_risk_summary(
        project,
        steps,
        expression_links,
        test_records,
        review_signals,
        snapshots=snapshots,
    )
    rows[0]["detail"] = "Changed row"

    assert (project, steps, expression_links, test_records, review_signals, snapshots) == before


def test_output_copy_does_not_include_forbidden_wording():
    rows = build_documentation_risk_summary(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10, "step_name": "Recorded step"}],
        [{"id": 20, "step_id": 10}],
        [{"id": 30, "step_id": 10}],
        [{"signal_type": "gap"}],
        snapshots=[{"id": 40}],
    )
    text = _summary_text(rows)

    forbidden = [
        "ready",
        "readiness",
        "validated",
        "validation",
        "recommended",
        "optimized",
        "optimization",
        "prediction",
        "wet-lab",
        "experimental guidance",
    ]
    assert [term for term in forbidden if term in text] == []
