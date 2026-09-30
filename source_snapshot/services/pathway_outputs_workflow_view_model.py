from __future__ import annotations

from copy import deepcopy
from typing import Any


def _dict_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in (items or []) if isinstance(item, dict)]


def _has_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _has_project_context(project: dict[str, Any] | None, steps: list[dict[str, Any]] | None) -> bool:
    if _dict_items(steps):
        return True
    if not isinstance(project, dict):
        return False
    return any(_has_text(project.get(field)) for field in ("name", "target_product", "host", "description", "status"))


def _missing_item_count(completeness_result: dict[str, Any] | None) -> int:
    if not isinstance(completeness_result, dict):
        return 0
    missing_items = completeness_result.get("missing_items")
    return len(missing_items) if isinstance(missing_items, list) else 0


def _row(label: str, status: str, detail: str, next_review_step: str, level: str) -> dict[str, str]:
    return {
        "label": label,
        "status": status,
        "detail": detail,
        "next_review_step": next_review_step,
        "level": level,
    }


def build_project_outputs_summary_card_items(
    workflow_rows: list[dict[str, Any]] | None,
    risk_rows: list[dict[str, Any]] | None,
) -> list[tuple[str, str, str]]:
    """Build read-only Project Outputs summary cards from presenter rows."""
    workflow_items = _dict_items(workflow_rows)
    risk_items = _dict_items(risk_rows)
    review_attention_count = sum(1 for row in workflow_items if row.get("level") == "review_attention")
    source_review_count = sum(
        1 for row in risk_items if str(row.get("status", "")).lower() not in {"ok", "complete"}
    )
    return [
        ("Output surfaces", str(len(workflow_items)), "Snapshots, reports, quality review, export, import preview"),
        ("Review attention", str(review_attention_count), "Workflow rows with documentation review prompts"),
        ("Source review needed", str(source_review_count), "Risk summary rows needing human review"),
        ("Report draft", "Available", "Markdown report draft and quality review tabs"),
    ]


def build_project_outputs_workflow_table_rows(workflow_rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Build Project Outputs workflow detail table rows for Streamlit rendering."""
    return [
        {
            "Output": row.get("label", ""),
            "Status": row.get("status", ""),
            "Detail": row.get("detail", ""),
            "Next review step": row.get("next_review_step", ""),
        }
        for row in _dict_items(workflow_rows)
    ]


def build_project_outputs_risk_table_rows(risk_rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """Build Project Outputs documentation-risk detail table rows for Streamlit rendering."""
    return [
        {
            "Area": row.get("label", ""),
            "Status": row.get("status", ""),
            "Detail": row.get("detail", ""),
            "Related count": row.get("related_count", 0),
            "Source area": row.get("source_area", ""),
        }
        for row in _dict_items(risk_rows)
    ]


def build_project_outputs_workflow_state(
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None,
    expression_links: list[dict[str, Any]] | None,
    test_records: list[dict[str, Any]] | None,
    completeness_result: dict[str, Any] | None,
    review_signals: list[dict[str, Any]] | None,
    snapshots: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Build read-only Project Outputs workflow state rows for documentation review."""
    step_rows = _dict_items(steps)
    link_rows = _dict_items(expression_links)
    test_rows = _dict_items(test_records)
    signal_rows = _dict_items(review_signals)
    snapshot_rows = _dict_items(snapshots)
    has_context = _has_project_context(project, step_rows)
    missing_count = _missing_item_count(completeness_result)
    evidence_detail = (
        f"{len(step_rows)} pathway step(s), {len(link_rows)} linked design record(s), "
        f"and {len(test_rows)} test record(s) are recorded for documentation review."
    )

    if snapshot_rows:
        snapshot_row = _row(
            "Documentation Snapshots",
            "Review record available",
            f"{len(snapshot_rows)} documentation snapshot(s) are saved for local traceability review.",
            "Compare saved documentation state with the current project context.",
            "review_available",
        )
    elif has_context:
        snapshot_row = _row(
            "Documentation Snapshots",
            "Needs saved documentation state",
            "No documentation snapshots are saved for this project yet.",
            "Save a documentation snapshot after the project context is organized.",
            "needs_context",
        )
    else:
        snapshot_row = _row(
            "Documentation Snapshots",
            "Not available",
            "Project context is not recorded yet, so snapshot review has no local documentation state.",
            "Record project context before snapshot review.",
            "not_available",
        )

    if has_context:
        reports_row = _row(
            "Reports",
            "Documentation report review available",
            evidence_detail,
            "Generate or review the Markdown report as a documentation-only project summary.",
            "review_available",
        )
        export_row = _row(
            "Export Package",
            "Package structure review available",
            "Recorded project context can be checked as a documentation-only export package and traceability bundle.",
            "Use the export package area for package structure check and traceability review.",
            "review_available",
        )
    else:
        reports_row = _row(
            "Reports",
            "Not available",
            "A documentation report needs recorded project context before it has content to review.",
            "Record pathway context before report review.",
            "not_available",
        )
        export_row = _row(
            "Export Package",
            "Not available",
            "Package structure review needs recorded project context before an export package summary is useful.",
            "Record project context before package structure review.",
            "not_available",
        )

    if signal_rows or missing_count:
        quality_row = _row(
            "Quality Review",
            "Documentation review attention",
            f"{missing_count} documentation gap(s) and {len(signal_rows)} review signal(s) are recorded.",
            "Review documentation gaps and review signals before sharing outputs.",
            "review_attention",
        )
    elif has_context:
        quality_row = _row(
            "Quality Review",
            "Documentation review available",
            "No documentation gaps or review signals are recorded in the current summary.",
            "Review context completeness before sharing outputs.",
            "review_available",
        )
    else:
        quality_row = _row(
            "Quality Review",
            "Not available",
            "Quality review needs recorded documentation context before gaps or review signals can be summarized.",
            "Record project context before quality review.",
            "not_available",
        )

    import_preview_row = _row(
        "Import Preview",
        "Package lifecycle structure preview",
        "Import Preview is a read-only package lifecycle structure preview for uploaded export packages.",
        "Use after an export package exists; it is not the primary design workflow next step.",
        "lifecycle_preview",
    )

    return [snapshot_row, reports_row, quality_row, export_row, import_preview_row]
