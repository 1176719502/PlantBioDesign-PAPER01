from __future__ import annotations

from copy import deepcopy
from typing import Any


ALLOWED_RELATIONSHIPS = {
    "project_contains_step",
    "step_links_expression_design",
    "project_has_test_record",
    "project_has_review_signal",
    "project_has_snapshot",
    "no_records",
}

ALLOWED_STATUSES = {
    "linked",
    "missing_reference",
    "snapshot_captured",
    "review_note_present",
    "needs_review",
    "no_records",
}


def _dict_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in (items or []) if isinstance(item, dict)]


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _has_text(value: Any) -> bool:
    return bool(_clean_text(value))


def _safe_positive_int(value: Any) -> int | None:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _record_id(record: dict[str, Any], fallback: str) -> str:
    for field in ("id", "record_id", "uuid"):
        value = _clean_text(record.get(field))
        if value:
            return value
    return fallback


def _project_node_id(project: dict[str, Any] | None) -> str:
    if isinstance(project, dict):
        project_id = _clean_text(project.get("id") or project.get("project_id"))
        if project_id:
            return f"project:{project_id}"
    return "project:local"


def _project_label(project: dict[str, Any] | None) -> str:
    if isinstance(project, dict):
        for field in ("name", "project_name", "title"):
            value = _clean_text(project.get(field))
            if value:
                return value
    return "Project"


def _step_label(step: dict[str, Any]) -> str:
    for field in ("step_name", "name", "step_title"):
        value = _clean_text(step.get(field))
        if value:
            return value
    order = _clean_text(step.get("step_order"))
    step_id = _clean_text(step.get("id"))
    if order:
        return f"Step {order}"
    return f"Step {step_id}" if step_id else "Step"


def _link_label(link: dict[str, Any]) -> str:
    for field in ("design_name", "design_title", "snapshot_title", "name", "title"):
        value = _clean_text(link.get(field))
        if value:
            return value
    design_id = _clean_text(link.get("design_id") or link.get("id"))
    return f"Expression design {design_id}" if design_id else "Expression design"


def _test_record_label(record: dict[str, Any]) -> str:
    for field in ("record_name", "test_name", "sample_name", "name", "title"):
        value = _clean_text(record.get(field))
        if value:
            return value
    record_id = _clean_text(record.get("id") or record.get("record_id"))
    return f"Test record {record_id}" if record_id else "Test record"


def _review_signal_label(signal: dict[str, Any]) -> str:
    for field in ("signal_type", "type", "title", "message"):
        value = _clean_text(signal.get(field))
        if value:
            return value
    return "Review signal"


def _snapshot_label(snapshot: dict[str, Any]) -> str:
    for field in ("snapshot_title", "title", "name"):
        value = _clean_text(snapshot.get(field))
        if value:
            return value
    snapshot_id = _clean_text(snapshot.get("id") or snapshot.get("snapshot_id"))
    return f"Documentation snapshot {snapshot_id}" if snapshot_id else "Documentation snapshot"


def _related_step_id(record: dict[str, Any]) -> int | None:
    for field in ("step_id", "pathway_step_id", "related_step_id", "step_order"):
        step_id = _safe_positive_int(record.get(field))
        if step_id is not None:
            return step_id
    evidence = record.get("evidence")
    if isinstance(evidence, dict):
        return _related_step_id(evidence)
    return None


def _related_step_value(record: dict[str, Any]) -> str:
    for field in ("step_id", "pathway_step_id", "related_step_id", "step_order"):
        value = _clean_text(record.get(field))
        if value:
            return value
    evidence = record.get("evidence")
    if isinstance(evidence, dict):
        return _related_step_value(evidence)
    return "unrecorded"


def _node(node_id: str, label: str, node_type: str, record: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"id": node_id, "label": label, "type": node_type}
    if record is not None:
        payload["record"] = deepcopy(record)
    return payload


def _edge(source: str, relationship: str, target: str, status: str, review_note: str) -> dict[str, str]:
    return {
        "source": source,
        "relationship": relationship,
        "target": target,
        "status": status,
        "review_note": review_note,
    }


def _row(source: str, relationship: str, target: str, status: str, review_note: str) -> dict[str, str]:
    return {
        "Source": source,
        "Relationship": relationship,
        "Target": target,
        "Status": status,
        "Review note": review_note,
    }


def _append_relation(
    edges: list[dict[str, str]],
    rows: list[dict[str, str]],
    source_id: str,
    source_label: str,
    relationship: str,
    target_id: str,
    target_label: str,
    status: str,
    review_note: str,
) -> None:
    edges.append(_edge(source_id, relationship, target_id, status, review_note))
    rows.append(_row(source_label, relationship, target_label, status, review_note))


def _has_project_context(project: dict[str, Any] | None, rows: list[list[dict[str, Any]]]) -> bool:
    if any(rows):
        return True
    if not isinstance(project, dict):
        return False
    return any(_has_text(project.get(field)) for field in ("id", "name", "project_name", "title", "description", "status"))


def traceability_summary_counts(graph: dict[str, Any] | None) -> dict[str, Any]:
    """Summarize documentation lineage rows without Streamlit rendering dependencies."""
    rows = graph.get("rows") if isinstance(graph, dict) else []
    row_items = [row for row in (rows or []) if isinstance(row, dict)]
    lineage_rows = [row for row in row_items if row.get("Status") != "no_records"]
    return {
        "traceability_rows": len(row_items),
        "rows_needing_review": sum(1 for row in row_items if row.get("Status") == "needs_review"),
        "missing_references": sum(1 for row in row_items if row.get("Status") == "missing_reference"),
        "lineage_records_exist": bool(lineage_rows),
    }


def build_traceability_graph_lite_summary_state(graph: dict[str, Any] | None) -> dict[str, Any]:
    """Build Traceability Graph Lite summary display state from a graph model."""
    nodes = graph.get("nodes") if isinstance(graph, dict) else []
    edges = graph.get("edges") if isinstance(graph, dict) else []
    node_items = [node for node in (nodes or []) if isinstance(node, dict)]
    edge_items = [edge for edge in (edges or []) if isinstance(edge, dict)]
    summary = traceability_summary_counts(graph)
    return {
        "summary": summary,
        "metric_items": [
            ("Traceability nodes", str(len(node_items))),
            ("Traceability edges", str(len(edge_items))),
            ("Rows needing review", str(summary["rows_needing_review"])),
            ("Missing references", str(summary["missing_references"])),
        ],
    }


def build_traceability_graph_lite_table_state(graph: dict[str, Any] | None) -> dict[str, Any]:
    """Build Traceability Graph Lite table display state from graph rows."""
    rows = graph.get("rows") if isinstance(graph, dict) else []
    row_items = [deepcopy(row) for row in (rows or []) if isinstance(row, dict)]
    return {
        "rows": row_items,
        "has_rows": bool(row_items),
    }


def build_traceability_graph_lite_display_state(graph: dict[str, Any] | None) -> dict[str, Any]:
    """Build combined Traceability Graph Lite display state for Streamlit rendering."""
    return {
        "summary": build_traceability_graph_lite_summary_state(graph),
        "table": build_traceability_graph_lite_table_state(graph),
    }


def build_project_outputs_traceability_summary_state(graph: dict[str, Any] | None) -> dict[str, Any]:
    """Build Project Outputs traceability summary display state from a graph model."""
    summary = traceability_summary_counts(graph)
    return {
        "boundary_caption": (
            "Traceability Summary for documentation review only: a local documentation lineage snapshot from current "
            "project records. It is not experimental validation, not prediction, not a recommendation, and does not "
            "determine readiness."
        ),
        "summary": summary,
        "metric_items": [
            ("Traceability rows", str(summary["traceability_rows"])),
            ("Rows needing review", str(summary["rows_needing_review"])),
            ("Missing references", str(summary["missing_references"])),
            (
                "Local documentation lineage records exist",
                "Yes" if summary["lineage_records_exist"] else "No",
            ),
        ],
    }


def build_traceability_graph_lite(
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None,
    expression_links: list[dict[str, Any]] | None,
    test_records: list[dict[str, Any]] | None,
    review_signals: list[dict[str, Any]] | None,
    snapshots: list[dict[str, Any]] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build a read-only documentation lineage graph model for existing project records."""
    step_rows = _dict_items(steps)
    link_rows = _dict_items(expression_links)
    test_rows = _dict_items(test_records)
    signal_rows = _dict_items(review_signals)
    snapshot_rows = _dict_items(snapshots)

    if not _has_project_context(project, [step_rows, link_rows, test_rows, signal_rows, snapshot_rows]):
        return {
            "nodes": [],
            "edges": [],
            "rows": [
                _row(
                    "Project",
                    "no_records",
                    "Traceability Graph Lite",
                    "no_records",
                    "No project documentation records are available for lineage review.",
                )
            ],
        }

    project_record = deepcopy(project) if isinstance(project, dict) else {}
    project_id = _project_node_id(project_record)
    project_label = _project_label(project_record)
    nodes: list[dict[str, Any]] = [_node(project_id, project_label, "project", project_record)]
    edges: list[dict[str, str]] = []
    rows: list[dict[str, str]] = []

    steps_by_id: dict[int, tuple[str, str]] = {}
    for index, step in enumerate(step_rows, start=1):
        step_int_id = _safe_positive_int(step.get("id"))
        node_suffix = str(step_int_id) if step_int_id is not None else f"local-{index}"
        step_id = f"step:{node_suffix}"
        label = _step_label(step)
        if step_int_id is not None:
            steps_by_id[step_int_id] = (step_id, label)
        nodes.append(_node(step_id, label, "pathway_step", step))
        _append_relation(
            edges,
            rows,
            project_id,
            project_label,
            "project_contains_step",
            step_id,
            label,
            "linked",
            "Pathway step is part of the project documentation lineage.",
        )

    for index, link in enumerate(link_rows, start=1):
        link_id = f"expression_design:{_record_id(link, str(index))}"
        link_label = _link_label(link)
        nodes.append(_node(link_id, link_label, "expression_design_link", link))
        step_int_id = _related_step_id(link)
        if step_int_id is not None and step_int_id in steps_by_id:
            source_id, source_label = steps_by_id[step_int_id]
            status = "linked"
            note = "Linked expression design record is connected for documentation lineage."
        else:
            source_id = f"missing_step:{_related_step_value(link)}"
            source_label = f"Missing step reference {_related_step_value(link)}"
            status = "missing_reference"
            note = "Referenced step is not present in the provided step records; human review is needed."
        _append_relation(
            edges,
            rows,
            source_id,
            source_label,
            "step_links_expression_design",
            link_id,
            link_label,
            status,
            note,
        )

    for index, record in enumerate(test_rows, start=1):
        record_id = f"test_record:{_record_id(record, str(index))}"
        label = _test_record_label(record)
        nodes.append(_node(record_id, label, "test_record", record))
        step_int_id = _related_step_id(record)
        status = "linked" if step_int_id is None or step_int_id in steps_by_id else "missing_reference"
        note = (
            "Test record is connected to the project documentation lineage."
            if status == "linked"
            else "Test record references a step that is not present in the provided step records; human review is needed."
        )
        _append_relation(edges, rows, project_id, project_label, "project_has_test_record", record_id, label, status, note)

    for index, signal in enumerate(signal_rows, start=1):
        signal_id = f"review_signal:{_record_id(signal, str(index))}"
        label = _review_signal_label(signal)
        nodes.append(_node(signal_id, label, "review_signal", signal))
        step_int_id = _related_step_id(signal)
        status = "review_note_present" if step_int_id is None or step_int_id in steps_by_id else "needs_review"
        note = (
            "Review signal is recorded for documentation review."
            if status == "review_note_present"
            else "Review signal references a step that is not present in the provided step records."
        )
        _append_relation(edges, rows, project_id, project_label, "project_has_review_signal", signal_id, label, status, note)

    for index, snapshot in enumerate(snapshot_rows, start=1):
        snapshot_id = f"snapshot:{_record_id(snapshot, str(index))}"
        label = _snapshot_label(snapshot)
        nodes.append(_node(snapshot_id, label, "documentation_snapshot", snapshot))
        _append_relation(
            edges,
            rows,
            project_id,
            project_label,
            "project_has_snapshot",
            snapshot_id,
            label,
            "snapshot_captured",
            "Documentation snapshot is captured for local lineage review.",
        )

    return {"nodes": nodes, "edges": edges, "rows": rows}
