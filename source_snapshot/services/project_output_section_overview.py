from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.generated_output_boundary import normalize_generated_output_claims
from services.project_output_boundary_copy import (
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    PROJECT_OUTPUT_NO_DATA_CHANGE_NOTE,
)

OVERVIEW_TITLE = "Output sections overview"
OVERVIEW_BOUNDARY_NOTE = (
    "Read-only section map for documentation review; it shows only section names, simple statuses, "
    "counts, and where to inspect next."
)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or [] if isinstance(row, Mapping)]


def _text(value: Any, fallback: str = "NOT_AVAILABLE") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _overview_row(
    *,
    section_name: str,
    status: str,
    count: int,
    inspect_next: str,
) -> dict[str, Any]:
    return {
        "section_name": section_name,
        "status": status,
        "count": count,
        "inspect_next": inspect_next,
        "boundary_note": "Read-only documentation review context only.",
    }


def build_project_output_sections_overview(
    *,
    report: Mapping[str, Any] | None = None,
    detailed_report_draft: Mapping[str, Any] | None = None,
    handoff_preview: Mapping[str, Any] | None = None,
    dashboard: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact read-only map of dense Project Outputs sections."""
    report_data = _mapping(report)
    draft = _mapping(detailed_report_draft or report_data.get("detailed_documentation_report_draft"))
    handoff = _mapping(handoff_preview or report_data.get("project_handoff_package_preview"))
    dashboard_data = _mapping(dashboard)

    report_markdown = _text(report_data.get("markdown"), "")
    draft_markdown = _text(draft.get("markdown"), "")
    handoff_markdown = _text(handoff.get("markdown_handoff_preview"), "")
    review_sheet_sections = _rows(handoff.get("review_sheet_sections"))
    traceability_rows = _rows(handoff.get("traceability_matrix_rows"))
    action_panel = _mapping(handoff.get("expression_construct_review_action_panel"))
    action_panel_summary = _mapping(action_panel.get("summary"))
    component_readback = _mapping(
        draft.get("component_library_followup_queue_report_readback")
        or report_data.get("component_library_followup_queue_report_readback")
    )
    component_summary = _mapping(component_readback.get("summary"))
    dashboard_metrics = _mapping(dashboard_data.get("metrics"))

    rows = [
        _overview_row(
            section_name="Project Review Report",
            status="Markdown available" if report_markdown else _text(report_data.get("status"), "AVAILABLE" if report_data else "NOT_AVAILABLE"),
            count=len(_rows(report_data.get("missing_fields"))),
            inspect_next="Report summary, missing fields, review notes, and boundary notes",
        ),
        _overview_row(
            section_name="Detailed Documentation Draft / markdown preview",
            status=_text(draft.get("status"), "Markdown available" if draft_markdown else "NOT_AVAILABLE"),
            count=len([line for line in draft_markdown.splitlines() if line.startswith("## ")]),
            inspect_next="Detailed documentation report draft Markdown",
        ),
        _overview_row(
            section_name="Handoff Review / package preview",
            status=_text(handoff.get("status"), "AVAILABLE" if handoff else "NOT_AVAILABLE"),
            count=len(review_sheet_sections) or len([line for line in handoff_markdown.splitlines() if line.startswith("### ")]),
            inspect_next="Project handoff review workspace, package preview, and review sheet",
        ),
        _overview_row(
            section_name="Quality Dashboard package preview",
            status=_text(dashboard_data.get("overall_documentation_status"), "AVAILABLE" if dashboard_data else "NOT_AVAILABLE"),
            count=_int(dashboard_metrics.get("review_gap_count")),
            inspect_next="Project Quality Dashboard summary metrics and package exchange review trail",
        ),
        _overview_row(
            section_name="Expression Construct Review summary/action panel",
            status=_text(action_panel.get("status"), "AVAILABLE" if action_panel else "NOT_AVAILABLE"),
            count=_int(action_panel_summary.get("row_count")),
            inspect_next="Expression construct review action panel and construct follow-up queue",
        ),
        _overview_row(
            section_name="Component Library follow-up queue report/readback",
            status=_text(component_readback.get("status"), "AVAILABLE" if component_readback else "NOT_AVAILABLE"),
            count=_int(component_summary.get("queue_item_count")),
            inspect_next="Component Library source/provenance follow-up queue report readback",
        ),
    ]
    rows.append(
        _overview_row(
            section_name="Project handoff traceability matrix",
            status="AVAILABLE" if traceability_rows else "NOT_AVAILABLE",
            count=len(traceability_rows),
            inspect_next="Traceability matrix source surface and review-next rows",
        )
    )

    available_count = sum(1 for row in rows if row["status"] != "NOT_AVAILABLE")
    overview = {
        "title": OVERVIEW_TITLE,
        "status": "AVAILABLE" if available_count else "NOT_AVAILABLE",
        "section_count": len(rows),
        "available_section_count": available_count,
        "rows": rows,
        "boundary_notes": [
            OVERVIEW_BOUNDARY_NOTE,
            PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
            PROJECT_OUTPUT_NO_DATA_CHANGE_NOTE,
        ],
    }
    return normalize_generated_output_claims(overview)


def format_project_output_sections_overview_markdown(overview: Mapping[str, Any] | None) -> str:
    overview_data = _mapping(overview)
    rows = _rows(overview_data.get("rows"))
    if not rows:
        return ""
    lines = [
        f"## {_text(overview_data.get('title'), OVERVIEW_TITLE)}",
        f"- Status: {_text(overview_data.get('status'))}",
        f"- Sections listed: {_int(overview_data.get('section_count'))}",
        f"- Available sections: {_int(overview_data.get('available_section_count'))}",
    ]
    for note in overview_data.get("boundary_notes") or []:
        lines.append(f"- {_text(note)}")
    lines += [
        "",
        "| Section | Status | Count | Inspect next |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _text(row.get("section_name")).replace("|", "\\|"),
                    _text(row.get("status")).replace("|", "\\|"),
                    str(_int(row.get("count"))),
                    _text(row.get("inspect_next")).replace("|", "\\|"),
                ]
            )
            + " |"
        )
    return "\n".join(lines)
