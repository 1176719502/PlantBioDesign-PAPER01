from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.pathway_traceability_view_model import (
    build_project_outputs_traceability_summary_state,
    build_traceability_graph_lite,
    build_traceability_graph_lite_display_state,
    build_traceability_graph_lite_summary_state,
    build_traceability_graph_lite_table_state,
    traceability_summary_counts,
)


def _rows_text(rows: list[dict]) -> str:
    return " ".join(str(value) for row in rows for value in row.values()).lower()


def _row(rows: list[dict], relationship: str, target: str | None = None) -> dict:
    for row in rows:
        if row["Relationship"] != relationship:
            continue
        if target is None or row["Target"] == target:
            return row
    raise AssertionError(f"Missing row for {relationship} -> {target}")


def _all_output_text(graph: dict) -> str:
    parts: list[str] = []
    for section in ("nodes", "edges", "rows"):
        for item in graph[section]:
            parts.extend(str(value) for value in item.values())
    return " ".join(parts).lower()


def test_empty_project_context_returns_no_records_state():
    graph = build_traceability_graph_lite({}, [], [], [], [], snapshots=[])

    assert graph["nodes"] == []
    assert graph["edges"] == []
    assert graph["rows"] == [
        {
            "Source": "Project",
            "Relationship": "no_records",
            "Target": "Traceability Graph Lite",
            "Status": "no_records",
            "Review note": "No project documentation records are available for lineage review.",
        }
    ]


def test_project_contains_steps_relationship_rows_and_edges():
    graph = build_traceability_graph_lite(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10, "step_order": 1, "step_name": "Record substrate"}],
        [],
        [],
        [],
    )

    assert [node["type"] for node in graph["nodes"]] == ["project", "pathway_step"]
    row = _row(graph["rows"], "project_contains_step", "Record substrate")
    assert row["Source"] == "Documentation project"
    assert row["Status"] == "linked"
    assert graph["edges"][0]["source"] == "project:1"
    assert graph["edges"][0]["target"] == "step:10"


def test_step_links_expression_design_relationship():
    graph = build_traceability_graph_lite(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10, "step_name": "Recorded step"}],
        [{"id": 20, "step_id": 10, "design_name": "Linked design"}],
        [],
        [],
    )

    row = _row(graph["rows"], "step_links_expression_design", "Linked design")
    assert row["Source"] == "Recorded step"
    assert row["Status"] == "linked"
    assert "documentation lineage" in row["Review note"]
    assert any(edge["relationship"] == "step_links_expression_design" for edge in graph["edges"])


def test_project_has_test_records_relationship():
    graph = build_traceability_graph_lite(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10, "step_name": "Recorded step"}],
        [],
        [{"id": 30, "step_id": 10, "sample_name": "Observation note"}],
        [],
    )

    row = _row(graph["rows"], "project_has_test_record", "Observation note")
    assert row["Source"] == "Documentation project"
    assert row["Status"] == "linked"
    assert "project documentation lineage" in row["Review note"]


def test_project_has_review_signals_relationship():
    graph = build_traceability_graph_lite(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10, "step_name": "Recorded step"}],
        [],
        [],
        [{"id": 40, "related_step_id": 10, "signal_type": "missing_documentation"}],
    )

    row = _row(graph["rows"], "project_has_review_signal", "missing_documentation")
    assert row["Status"] == "review_note_present"
    assert "documentation review" in row["Review note"]


def test_project_has_snapshots_relationship():
    graph = build_traceability_graph_lite(
        {"id": 1, "name": "Documentation project"},
        [],
        [],
        [],
        [],
        snapshots=[{"id": 50, "snapshot_title": "Local documentation snapshot"}],
    )

    row = _row(graph["rows"], "project_has_snapshot", "Local documentation snapshot")
    assert row["Status"] == "snapshot_captured"
    assert "local lineage review" in row["Review note"]


def test_mixed_project_output_traceability_counts_are_stable():
    graph = build_traceability_graph_lite(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10, "step_name": "Recorded step"}],
        [
            {"id": 20, "step_id": 10, "design_name": "Linked design"},
            {"id": 21, "step_id": 999, "design_name": "Stale linked design"},
        ],
        [
            {"id": 30, "step_id": 10, "sample_name": "Linked observation"},
            {"id": 31, "step_id": 999, "sample_name": "Stale observation"},
        ],
        [
            {"id": 40, "related_step_id": 10, "signal_type": "recorded_review"},
            {"id": 41, "related_step_id": 999, "signal_type": "stale_review"},
        ],
        snapshots=[{"id": 50, "snapshot_title": "Local documentation snapshot"}],
    )
    rows = graph["rows"]

    assert len(graph["nodes"]) == 9
    assert len(graph["edges"]) == 8
    assert len(rows) == 8
    assert sum(1 for row in rows if row["Status"] == "missing_reference") == 2
    assert sum(1 for row in rows if row["Status"] == "needs_review") == 1
    assert sum(1 for row in rows if row["Status"] == "no_records") == 0


def test_traceability_summary_counts_handles_mixed_statuses_and_no_records():
    summary = traceability_summary_counts(
        {
            "rows": [
                {"Status": "linked"},
                {"Status": "missing_reference"},
                {"Status": "needs_review"},
                {"Status": "no_records"},
                None,
                "bad row",
            ]
        }
    )

    assert summary == {
        "traceability_rows": 4,
        "rows_needing_review": 1,
        "missing_references": 1,
        "lineage_records_exist": True,
    }


def test_traceability_summary_counts_no_records_only_has_no_lineage():
    summary = traceability_summary_counts({"rows": [{"Status": "no_records"}]})

    assert summary == {
        "traceability_rows": 1,
        "rows_needing_review": 0,
        "missing_references": 0,
        "lineage_records_exist": False,
    }


def test_project_outputs_traceability_summary_state_pins_display_metrics_and_boundary_copy():
    state = build_project_outputs_traceability_summary_state(
        {
            "rows": [
                {"Status": "linked"},
                {"Status": "missing_reference"},
                {"Status": "needs_review"},
            ]
        }
    )

    assert state["summary"] == {
        "traceability_rows": 3,
        "rows_needing_review": 1,
        "missing_references": 1,
        "lineage_records_exist": True,
    }
    assert state["metric_items"] == [
        ("Traceability rows", "3"),
        ("Rows needing review", "1"),
        ("Missing references", "1"),
        ("Local documentation lineage records exist", "Yes"),
    ]
    assert "documentation review only" in state["boundary_caption"]
    assert "not experimental validation" in state["boundary_caption"]
    assert "not prediction" in state["boundary_caption"]
    assert "not a recommendation" in state["boundary_caption"]


def test_traceability_graph_lite_summary_state_pins_graph_metric_labels():
    state = build_traceability_graph_lite_summary_state(
        {
            "nodes": [{"id": "project:1"}, {"id": "step:10"}, None],
            "edges": [{"source": "project:1", "target": "step:10"}, "bad"],
            "rows": [
                {"Status": "linked"},
                {"Status": "missing_reference"},
                {"Status": "needs_review"},
            ],
        }
    )

    assert state["summary"] == {
        "traceability_rows": 3,
        "rows_needing_review": 1,
        "missing_references": 1,
        "lineage_records_exist": True,
    }
    assert state["metric_items"] == [
        ("Traceability nodes", "2"),
        ("Traceability edges", "1"),
        ("Rows needing review", "1"),
        ("Missing references", "1"),
    ]


def test_traceability_graph_lite_table_state_copies_display_rows_and_ignores_malformed_items():
    graph = {
        "rows": [
            {"Source": "Project", "Relationship": "project_contains_step", "Target": "Step", "Status": "linked"},
            None,
            "bad row",
        ]
    }

    state = build_traceability_graph_lite_table_state(graph)
    state["rows"][0]["Status"] = "changed"

    assert state["has_rows"] is True
    assert state["rows"] == [
        {"Source": "Project", "Relationship": "project_contains_step", "Target": "Step", "Status": "changed"}
    ]
    assert graph["rows"][0]["Status"] == "linked"


def test_traceability_graph_lite_table_state_empty_for_missing_or_malformed_graph():
    assert build_traceability_graph_lite_table_state(None) == {"rows": [], "has_rows": False}
    assert build_traceability_graph_lite_table_state({"rows": [None, "bad row"]}) == {"rows": [], "has_rows": False}


def test_traceability_graph_lite_display_state_combines_summary_and_table_contracts():
    graph = {
        "nodes": [{"id": "project:1"}],
        "edges": [{"source": "project:1", "target": "step:10"}],
        "rows": [
            {"Source": "Project", "Relationship": "project_contains_step", "Target": "Step", "Status": "linked"},
            {"Status": "needs_review"},
            None,
        ],
    }

    state = build_traceability_graph_lite_display_state(graph)
    state["table"]["rows"][0]["Status"] = "changed"

    assert state["summary"]["metric_items"] == [
        ("Traceability nodes", "1"),
        ("Traceability edges", "1"),
        ("Rows needing review", "1"),
        ("Missing references", "0"),
    ]
    assert state["table"]["has_rows"] is True
    assert len(state["table"]["rows"]) == 2
    assert graph["rows"][0]["Status"] == "linked"


def test_missing_stale_step_reference_uses_review_status_without_experiment_risk_copy():
    graph = build_traceability_graph_lite(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10, "step_name": "Recorded step"}],
        [{"id": 20, "step_id": 999, "design_name": "Stale linked design"}],
        [{"id": 30, "step_id": 999, "sample_name": "Stale observation note"}],
        [{"id": 40, "related_step_id": 999, "signal_type": "stale_step_reference"}],
    )

    stale_rows = [row for row in graph["rows"] if "999" in row["Review note"] or "999" in row["Source"]]
    assert {row["Status"] for row in stale_rows} <= {"missing_reference", "needs_review"}
    assert "risk" not in _rows_text(stale_rows)
    assert "experimental" not in _rows_text(stale_rows)


def test_bad_none_and_string_numeric_step_ids_do_not_raise():
    graph = build_traceability_graph_lite(
        {"id": "1", "name": "Documentation project"},
        [
            {"id": None, "step_order": 1},
            {"id": "2", "step_name": "String id step"},
            {"id": "bad", "step_name": "Bad id step"},
        ],
        [
            {"id": 20, "step_id": "2", "design_name": "String linked design"},
            {"id": 21, "step_id": None, "design_name": "Missing step id design"},
            {"id": 22, "step_id": "bad", "design_name": "Bad step id design"},
        ],
        [{"id": 30, "pathway_step_id": "2"}],
        [{"id": 40, "evidence": {"step_id": "2"}}],
    )

    assert _row(graph["rows"], "step_links_expression_design", "String linked design")["Status"] == "linked"
    assert _row(graph["rows"], "step_links_expression_design", "Missing step id design")["Status"] == "missing_reference"
    assert _row(graph["rows"], "step_links_expression_design", "Bad step id design")["Status"] == "missing_reference"
    assert len(graph["nodes"]) == 9


def test_input_dicts_and_lists_are_not_mutated():
    project = {"id": 1, "name": "Documentation project", "metadata": {"nested": "value"}}
    steps = [{"id": 10, "step_name": "Recorded step", "metadata": {"nested": "step"}}]
    expression_links = [{"id": 20, "step_id": 10, "design_name": "Linked design"}]
    test_records = [{"id": 30, "step_id": 10, "sample_name": "Observation note"}]
    review_signals = [{"id": 40, "related_step_id": 10, "signal_type": "review_note"}]
    snapshots = [{"id": 50, "snapshot_title": "Snapshot", "payload": {"steps": []}}]
    before = copy.deepcopy((project, steps, expression_links, test_records, review_signals, snapshots))

    graph = build_traceability_graph_lite(project, steps, expression_links, test_records, review_signals, snapshots=snapshots)
    graph["nodes"][0]["record"]["metadata"]["nested"] = "changed"
    graph["rows"][0]["Review note"] = "Changed row"

    assert (project, steps, expression_links, test_records, review_signals, snapshots) == before


def test_output_copy_does_not_include_forbidden_wording():
    graph = build_traceability_graph_lite(
        {"id": 1, "name": "Documentation project"},
        [{"id": 10, "step_name": "Recorded step"}],
        [{"id": 20, "step_id": 10, "design_name": "Linked design"}],
        [{"id": 30, "step_id": 10, "sample_name": "Observation note"}],
        [{"id": 40, "related_step_id": 10, "signal_type": "review_note"}],
        snapshots=[{"id": 50, "snapshot_title": "Documentation snapshot"}],
    )
    text = _all_output_text(graph)

    forbidden = [
        "ready",
        "readiness",
        "validated",
        "validation",
        "optimized",
        "optimization",
        "prediction",
        "wet-lab",
        "biological recommendation",
        "experimental guidance",
    ]
    assert [term for term in forbidden if term in text] == []
