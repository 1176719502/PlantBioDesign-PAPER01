from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.pathway_outputs_workflow_view_model import (
    build_project_outputs_risk_table_rows,
    build_project_outputs_summary_card_items,
    build_project_outputs_workflow_table_rows,
    build_project_outputs_workflow_state,
)


def _state_text(rows: list[dict[str, str]]) -> str:
    return " ".join(str(value) for row in rows for value in row.values()).lower()


def _row(rows: list[dict[str, str]], label: str) -> dict[str, str]:
    return next(row for row in rows if row["label"] == label)


def test_empty_project_context_marks_outputs_as_needing_context_or_not_available():
    rows = build_project_outputs_workflow_state({}, [], [], [], {}, [], snapshots=[])

    assert [row["label"] for row in rows] == [
        "Documentation Snapshots",
        "Reports",
        "Quality Review",
        "Export Package",
        "Import Preview",
    ]
    assert _row(rows, "Documentation Snapshots")["level"] == "not_available"
    assert _row(rows, "Reports")["level"] == "not_available"
    assert _row(rows, "Quality Review")["level"] == "not_available"
    assert _row(rows, "Export Package")["level"] == "not_available"
    assert _row(rows, "Import Preview")["level"] == "lifecycle_preview"


def test_steps_without_linked_designs_remain_documentation_review_not_readiness():
    rows = build_project_outputs_workflow_state(
        {"id": 1, "name": "Pathway documentation project"},
        [{"id": 10, "step_order": 1, "step_name": "Recorded step"}],
        [],
        [],
        {"missing_items": []},
        [],
        snapshots=[],
    )

    text = _state_text(rows)
    assert _row(rows, "Reports")["level"] == "review_available"
    assert _row(rows, "Quality Review")["status"] == "Documentation review available"
    assert "documentation review" in text
    assert "readiness" not in text
    assert "validation" not in text


def test_linked_designs_test_records_and_review_signals_make_outputs_reviewable():
    rows = build_project_outputs_workflow_state(
        {"id": 1, "name": "Pathway documentation project"},
        [{"id": 10, "step_order": 1, "step_name": "Recorded step"}],
        [{"id": 20, "step_id": 10, "design_name": "Linked design"}],
        [{"id": 30, "step_id": 10, "sample_name": "Recorded observation"}],
        {"missing_items": ["gene sequence"]},
        [{"signal_type": "documentation_gap"}],
        snapshots=[{"id": 40, "title": "Snapshot"}],
    )

    assert _row(rows, "Documentation Snapshots")["level"] == "review_available"
    assert _row(rows, "Reports")["level"] == "review_available"
    assert _row(rows, "Quality Review")["level"] == "review_attention"
    assert _row(rows, "Export Package")["level"] == "review_available"
    assert "linked design record(s)" in _row(rows, "Reports")["detail"]


def test_export_package_copy_avoids_unsafe_readiness_terms():
    rows = build_project_outputs_workflow_state(
        {"name": "Project"},
        [{"id": 1, "step_name": "Step"}],
        [],
        [],
        {},
        [],
    )
    export_text = " ".join(_row(rows, "Export Package").values()).lower()

    forbidden = ["ready", "validated", "recommended", "wet-lab", "execution", "deploy"]
    assert [term for term in forbidden if term in export_text] == []
    assert "package structure review" in export_text
    assert "traceability" in export_text


def test_import_preview_is_package_lifecycle_structure_preview_not_design_next_step():
    rows = build_project_outputs_workflow_state({"name": "Project"}, [], [], [], {}, [])
    import_preview = _row(rows, "Import Preview")
    text = " ".join(import_preview.values()).lower()

    assert import_preview["level"] == "lifecycle_preview"
    assert "package lifecycle" in text
    assert "structure preview" in text
    assert "not the primary design workflow next step" in text


def test_inputs_are_not_mutated():
    project = {"id": 1, "name": "Project"}
    steps = [{"id": 10, "metadata": {"nested": "value"}}]
    expression_links = [{"id": 20, "step_id": 10}]
    test_records = [{"id": 30, "step_id": 10}]
    completeness_result = {"missing_items": ["gene"]}
    review_signals = [{"signal_type": "gap", "evidence": {"step_id": 10}}]
    snapshots = [{"id": 40, "payload": {"pathway_steps": []}}]
    before = copy.deepcopy((project, steps, expression_links, test_records, completeness_result, review_signals, snapshots))

    rows = build_project_outputs_workflow_state(
        project,
        steps,
        expression_links,
        test_records,
        completeness_result,
        review_signals,
        snapshots=snapshots,
    )
    rows[0]["detail"] = "Changed row"

    assert (project, steps, expression_links, test_records, completeness_result, review_signals, snapshots) == before


def test_missing_optional_fields_do_not_raise():
    rows = build_project_outputs_workflow_state(
        {"id": None},
        [None, "bad", {"id": None}],
        [None, {"step_id": None}],
        [None, {"step_id": None}],
        {"missing_items": "not-a-list"},
        [None, {"signal_type": None}],
        snapshots=[None, {"id": None}],
    )

    assert len(rows) == 5
    assert _row(rows, "Reports")["level"] == "review_available"


def test_project_outputs_summary_cards_pin_read_only_counts():
    cards = build_project_outputs_summary_card_items(
        [
            {"label": "Documentation Snapshots", "level": "review_available"},
            {"label": "Reports", "level": "review_available"},
            {"label": "Quality Review", "level": "review_attention"},
            {"label": "Export Package", "level": "review_available"},
            {"label": "Import Preview", "level": "lifecycle_preview"},
        ],
        [
            {"label": "Project metadata", "status": "ok"},
            {"label": "Traceability", "status": "human_review_needed"},
            {"label": "Provenance", "status": "complete"},
            {"label": "Source review", "status": "REVIEW_NEEDED"},
        ],
    )

    assert cards == [
        ("Output surfaces", "5", "Snapshots, reports, quality review, export, import preview"),
        ("Review attention", "1", "Workflow rows with documentation review prompts"),
        ("Source review needed", "2", "Risk summary rows needing human review"),
        ("Report draft", "Available", "Markdown report draft and quality review tabs"),
    ]


def test_project_outputs_summary_cards_handle_empty_and_malformed_rows():
    cards = build_project_outputs_summary_card_items(
        [None, "bad", {"label": "Quality Review", "level": "review_attention"}],
        [None, {"label": "Metadata", "status": "OK"}, {"label": "Traceability"}],
    )

    assert cards[0] == ("Output surfaces", "1", "Snapshots, reports, quality review, export, import preview")
    assert cards[1] == ("Review attention", "1", "Workflow rows with documentation review prompts")
    assert cards[2] == ("Source review needed", "1", "Risk summary rows needing human review")


def test_project_outputs_summary_cards_do_not_mutate_inputs_or_add_claims():
    workflow_rows = [{"label": "Quality Review", "level": "review_attention", "nested": {"status": "kept"}}]
    risk_rows = [{"label": "Traceability", "status": "human_review_needed", "nested": {"status": "kept"}}]
    before = copy.deepcopy((workflow_rows, risk_rows))

    cards = build_project_outputs_summary_card_items(workflow_rows, risk_rows)
    cards_text = " ".join(" ".join(card).lower() for card in cards)

    assert (workflow_rows, risk_rows) == before
    forbidden = [
        "successful" + " import",
        "project" + " imported",
        "ready" + " for execution",
        "experiment" + "-ready",
        "production" + "-ready",
        "validated" + " construct",
        "optimized" + " pathway",
        "yield" + " prediction",
    ]
    assert [phrase for phrase in forbidden if phrase in cards_text] == []


def test_project_outputs_workflow_table_rows_pin_columns_and_defaults():
    rows = build_project_outputs_workflow_table_rows(
        [
            {
                "label": "Reports",
                "status": "Documentation report review available",
                "detail": "Recorded project context is available.",
                "next_review_step": "Review the Markdown report as a documentation-only project summary.",
                "extra": "ignored",
            },
            {"label": "Import Preview"},
            None,
            "bad row",
        ]
    )

    assert rows == [
        {
            "Output": "Reports",
            "Status": "Documentation report review available",
            "Detail": "Recorded project context is available.",
            "Next review step": "Review the Markdown report as a documentation-only project summary.",
        },
        {"Output": "Import Preview", "Status": "", "Detail": "", "Next review step": ""},
    ]


def test_project_outputs_risk_table_rows_pin_columns_and_defaults():
    rows = build_project_outputs_risk_table_rows(
        [
            {
                "label": "Traceability",
                "status": "human_review_needed",
                "detail": "Review linked records for local documentation traceability.",
                "related_count": 2,
                "source_area": "Project Outputs",
                "extra": "ignored",
            },
            {"label": "Project metadata"},
            None,
            "bad row",
        ]
    )

    assert rows == [
        {
            "Area": "Traceability",
            "Status": "human_review_needed",
            "Detail": "Review linked records for local documentation traceability.",
            "Related count": 2,
            "Source area": "Project Outputs",
        },
        {"Area": "Project metadata", "Status": "", "Detail": "", "Related count": 0, "Source area": ""},
    ]


def test_project_outputs_detail_table_rows_do_not_mutate_inputs_or_add_claims():
    workflow_rows = [{"label": "Reports", "nested": {"status": "kept"}}]
    risk_rows = [{"label": "Traceability", "nested": {"status": "kept"}}]
    before = copy.deepcopy((workflow_rows, risk_rows))

    workflow_table = build_project_outputs_workflow_table_rows(workflow_rows)
    risk_table = build_project_outputs_risk_table_rows(risk_rows)
    workflow_table[0]["Output"] = "Changed"
    risk_table[0]["Area"] = "Changed"
    text = " ".join(str(value).lower() for row in workflow_table + risk_table for value in row.values())

    assert (workflow_rows, risk_rows) == before
    forbidden = [
        "successful" + " import",
        "project" + " imported",
        "ready" + " for execution",
        "experiment" + "-ready",
        "production" + "-ready",
        "validated" + " construct",
        "optimized" + " pathway",
        "yield" + " prediction",
    ]
    assert [phrase for phrase in forbidden if phrase in text] == []
