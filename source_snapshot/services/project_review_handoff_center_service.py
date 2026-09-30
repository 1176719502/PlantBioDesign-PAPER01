from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    normalize_generated_output_claims,
)
from services.component_library_slot_browse_presenter import (
    SLOT_COLUMNS,
    build_component_library_slot_browse_presenter,
)
from services.documentation_review_label_helper import format_review_next_label
from services.placeholder_review_value import clean_review_value, is_placeholder_review_value
from services.project_review_follow_up_index import build_project_review_follow_up_index
from services.project_output_boundary_copy import (
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE,
    PROJECT_OUTPUT_SCOPE_NOTE,
)


HANDOFF_TITLE = "Project review handoff center"
HANDOFF_SUBTITLE = (
    "Read-only project-level handoff summary for construct, source, provenance, "
    "evidence, promoter, host/context, and report review follow-up."
)
HANDOFF_EMPTY_STATE = (
    "No project review handoff follow-up items are currently visible from available documentation queues. "
    "Review next: open the Project Review Follow-up Index or the handoff review sheet for source/provenance "
    "context."
)
HANDOFF_BOUNDARY_NOTES = [
    PROJECT_OUTPUT_SCOPE_NOTE,
    "This handoff center is documentation-only and read-only.",
    "It aggregates existing review queues and documentation gaps without changing project data.",
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE,
]
STEP2_COMPONENT_CONTEXT_APPENDIX_TITLE = "Step 2 recorded Component Library context appendix"
STEP2_COMPONENT_CONTEXT_APPENDIX_EMPTY_STATE = (
    "No current Step 2 Component Library context is available for this review appendix."
)
COMPONENT_LIBRARY_HANDOFF_READBACK_TITLE = "Component Library source/provenance readback"
COMPONENT_LIBRARY_HANDOFF_READBACK_INTRO = (
    "Review Component Library records and missing source/provenance before handoff. "
    "This section does not choose components or validate the design."
)
COMPONENT_LIBRARY_HANDOFF_READBACK_EMPTY_STATE = (
    "No Component Library records are available for Handoff Review yet. "
    "Open or add Component Library records before using this read-only source/provenance readback."
)
COMPONENT_LIBRARY_HANDOFF_READBACK_BOUNDARY_NOTE = (
    "Read-only documentation review only. Existing Component Library records are reused for source/provenance "
    "and manual follow-up readback; no biology-use recommendation, validation claim, sequence generation, "
    "package export, saved state, optimization claim, or wet-lab use judgment is created here."
)
COMPONENT_LIBRARY_HANDOFF_READBACK_COLUMNS = [
    "Slot",
    "Record count",
    "Records",
    "Source/provenance status",
    "Manual follow-up",
]

_SOURCE_TITLES = {
    "expression_constructs": "Expression Construct documentation",
    "candidate_evidence": "Candidate Evidence Human Review Queue",
    "plant_promoter_catalog": "Component Library Promoter Asset Evidence Gap Review",
    "host_context": "Host / chassis documentation context",
    "report_markdown": "Project Review Report Markdown",
}
_REVIEW_NEXT = {
    "expression_constructs": "Expression Constructs",
    "candidate_evidence": "Candidate Evidence Review Matrix",
    "plant_promoter_catalog": "Component Library promoter asset reference summary",
    "host_context": "Host / Chassis Context Summary",
    "report_markdown": "Project Review Report",
}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _review_text(value: Any, fallback: str = "") -> str:
    return clean_review_value(value, fallback)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _rows(value: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in value or [] if isinstance(row, Mapping)]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _queue_item_count(queue: Mapping[str, Any], summary_key: str = "summary") -> int:
    summary = _mapping(queue.get(summary_key))
    for key in ("queue_item_count", "rows_needing_manual_follow_up"):
        value = summary.get(key)
        if isinstance(value, int):
            return value
    total_rows = queue.get("total_rows_available")
    if isinstance(total_rows, int):
        return total_rows
    return len(_rows(queue.get("rows") or queue.get("queue_item_rows")))


def _expression_follow_up_count(queue: Mapping[str, Any]) -> int:
    summary = _mapping(queue.get("summary"))
    value = summary.get("rows_needing_manual_follow_up")
    if isinstance(value, int):
        return value
    return _queue_item_count(queue)


def _candidate_follow_up_count(
    candidate_queue: Mapping[str, Any],
    follow_up_index: Mapping[str, Any],
) -> int:
    source_counts = _mapping(_mapping(follow_up_index.get("summary")).get("source_section_counts"))
    if isinstance(source_counts.get("candidate_evidence"), int):
        return int(source_counts["candidate_evidence"])
    return _queue_item_count(candidate_queue)


def _promoter_follow_up_count(
    promoter_queue: Mapping[str, Any],
    follow_up_index: Mapping[str, Any],
) -> int:
    source_counts = _mapping(_mapping(follow_up_index.get("summary")).get("source_section_counts"))
    if isinstance(source_counts.get("plant_promoter_catalog"), int):
        return int(source_counts["plant_promoter_catalog"])
    return _queue_item_count(promoter_queue, summary_key="summary_counts")


def _host_context_follow_up_rows(host_context: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    context_rows = _rows(host_context.get("rows"))
    if not context_rows:
        rows.append(
            {
                "source_surface": _SOURCE_TITLES["host_context"],
                "item_label": "Host / chassis context",
                "issue_type": "No host/context readback rows",
                "manual_follow_up_note": "Review next: decide whether host or chassis documentation context should be recorded for this project.",
                "where_to_review_next": format_review_next_label(_REVIEW_NEXT["host_context"]),
            }
        )
        return rows

    for row in context_rows:
        source_value = _text(row.get("source_value"))
        if is_placeholder_review_value(source_value):
            rows.append(
                {
                    "source_surface": _SOURCE_TITLES["host_context"],
                    "item_label": _text(row.get("asset_display_name"), "Host / chassis context"),
                    "issue_type": "Host/context documentation not recorded",
                    "manual_follow_up_note": "Review next: add or confirm host/context documentation notes when they are needed for handoff review.",
                    "where_to_review_next": format_review_next_label(_REVIEW_NEXT["host_context"]),
                }
            )
    return rows


def _normalize_expression_rows(queue: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _rows(queue.get("rows")):
        rows.append(
            {
                "source_surface": _SOURCE_TITLES["expression_constructs"],
                "item_label": _text(
                    row.get("Component label") or row.get("Cassette label") or row.get("Construct label"),
                    "Construct component row",
                ),
                "issue_type": _text(row.get("Issue type"), "Construct documentation follow-up"),
                "manual_follow_up_note": _text(
                    row.get("Manual follow-up note"),
                    "Review next: inspect construct/component documentation context manually.",
                ),
                "where_to_review_next": format_review_next_label(_REVIEW_NEXT["expression_constructs"]),
            }
        )
    return rows


def _normalize_follow_up_index_rows(follow_up_index: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _rows(follow_up_index.get("rows")):
        source_section = _text(row.get("source_section"))
        rows.append(
            {
                "source_surface": _text(row.get("source_title"), _SOURCE_TITLES.get(source_section, source_section)),
                "item_label": _text(row.get("item_label"), "Documentation review item"),
                "issue_type": _text(row.get("category") or row.get("issue"), "Documentation follow-up"),
                "manual_follow_up_note": _text(
                    _review_text(row.get("human_follow_up")),
                    "Review next: inspect the documentation context manually.",
                ),
                "where_to_review_next": format_review_next_label(
                    _REVIEW_NEXT.get(source_section, "Project Review Follow-up Index")
                ),
            }
        )
    return rows


def _status_from_count(count: int, available: bool) -> str:
    if count:
        return "Needs documentation follow-up"
    return "No visible follow-up" if available else "No records available"


def _checklist_item(key: str, label: str, complete: bool, note: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": "Review available" if complete else "Follow-up visible",
        "complete": complete,
        "note": note,
    }


def _build_checklist(
    *,
    expression_count: int,
    expression_queue: Mapping[str, Any],
    candidate_count: int,
    promoter_count: int,
    host_count: int,
    host_context: Mapping[str, Any],
    report_markdown_available: bool,
) -> list[dict[str, Any]]:
    expression_summary = _mapping(expression_queue.get("summary"))
    component_rows = _int(expression_summary.get("total_component_rows"))
    host_rows = len(_rows(host_context.get("rows")))
    return [
        _checklist_item(
            "construct_component_source_context_reviewed",
            "construct/component source context reviewed",
            bool(component_rows) and expression_count == 0,
            _status_from_count(expression_count, bool(component_rows)),
        ),
        _checklist_item(
            "provenance_review_context_reviewed",
            "provenance/review context reviewed",
            expression_count == 0 and candidate_count == 0 and promoter_count == 0,
            _status_from_count(expression_count + candidate_count + promoter_count, True),
        ),
        _checklist_item(
            "evidence_follow_up_reviewed",
            "evidence follow-up reviewed",
            candidate_count == 0,
            _status_from_count(candidate_count, bool(candidate_count == 0)),
        ),
        _checklist_item(
            "promoter_source_metadata_reviewed",
            "Component Library promoter asset source/provenance and record review status reviewed",
            promoter_count == 0,
            _status_from_count(promoter_count, bool(promoter_count == 0)),
        ),
        _checklist_item(
            "host_context_documentation_reviewed",
            "host/context documentation reviewed",
            bool(host_rows) and host_count == 0,
            _status_from_count(host_count, bool(host_rows)),
        ),
        _checklist_item(
            "report_markdown_available_for_human_review",
            "report markdown available for human review",
            report_markdown_available,
            "Markdown summary available for copy/review only."
            if report_markdown_available
            else "Report markdown was not supplied to the handoff center.",
        ),
    ]


def build_component_library_handoff_readback(
    records: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build compact read-only Component Library slot readback for Handoff Review."""
    presenter = build_component_library_slot_browse_presenter(records or [])
    rows = [
        {column: _text(row.get(column)) for column in COMPONENT_LIBRARY_HANDOFF_READBACK_COLUMNS}
        for row in _rows(presenter.get("rows"))
    ]
    summary = _mapping(presenter.get("summary"))
    return {
        "title": COMPONENT_LIBRARY_HANDOFF_READBACK_TITLE,
        "intro": COMPONENT_LIBRARY_HANDOFF_READBACK_INTRO,
        "boundary_note": COMPONENT_LIBRARY_HANDOFF_READBACK_BOUNDARY_NOTE,
        "empty_state": COMPONENT_LIBRARY_HANDOFF_READBACK_EMPTY_STATE,
        "columns": list(COMPONENT_LIBRARY_HANDOFF_READBACK_COLUMNS),
        "source_presenter_columns": list(SLOT_COLUMNS),
        "rows": rows,
        "status": "AVAILABLE" if rows else "NOT_AVAILABLE",
        "summary": {
            "slot_row_count": _int(summary.get("slot_row_count")),
            "slot_rows_with_records": _int(summary.get("slot_rows_with_records")),
            "source_follow_up_slot_count": _int(summary.get("source_follow_up_slot_count")),
            "manual_follow_up_slot_count": _int(summary.get("manual_follow_up_slot_count")),
        },
        "reused_presenter": "services.component_library_slot_browse_presenter.build_component_library_slot_browse_presenter",
    }


def format_project_review_handoff_markdown(handoff: Mapping[str, Any]) -> str:
    summary = _mapping(handoff.get("summary"))
    appendix = _mapping(handoff.get("step2_component_context_appendix"))
    readback = _mapping(handoff.get("component_library_source_provenance_readback"))
    lines: list[str] = [
        "## Project review handoff center",
        "- Documentation-only handoff summary for human review.",
        f"- Total follow-up items: {_int(summary.get('total_follow_up_items'))}",
        f"- Expression construct documentation follow-up: {_int(summary.get('expression_construct_documentation_follow_up_count'))}",
        f"- Candidate evidence follow-up: {_int(summary.get('candidate_evidence_follow_up_count'))}",
        "- Component Library promoter asset source/review follow-up: "
        f"{_int(summary.get('promoter_source_review_follow_up_count'))}",
        f"- Host/context documentation follow-up: {_int(summary.get('host_context_documentation_follow_up_count'))}",
        "",
        "### Handoff checklist",
    ]
    for item in _rows(handoff.get("checklist")):
        lines.append(
            f"- {item.get('label')}: {_text(item.get('status'), 'Follow-up visible')} - "
            f"{_text(item.get('note'), 'Review documentation context manually.')}"
        )

    lines += ["", "### Follow-up queue overview"]
    overview_rows = _rows(handoff.get("follow_up_rows"))
    if overview_rows:
        lines += [
            "| Source surface | Item label | Issue type | Manual follow-up note | Review next |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in overview_rows:
            lines.append(
                "| "
                + " | ".join(
                    _text(row.get(key), "NOT_AVAILABLE").replace("|", "\\|").replace("\n", "<br>")
                    for key in (
                        "source_surface",
                        "item_label",
                        "issue_type",
                        "manual_follow_up_note",
                        "where_to_review_next",
                    )
                )
                + " |"
            )
    else:
        lines.append(f"- {_text(handoff.get('empty_state_message'), HANDOFF_EMPTY_STATE)}")

    lines += ["", f"### {STEP2_COMPONENT_CONTEXT_APPENDIX_TITLE}"]
    lines.append("- Read-only review appendix for recorded Component Library context.")
    lines.append(f"- Status: {_text(appendix.get('status'), 'NOT_AVAILABLE')}")
    lines.append(f"- Rows available: {_int(appendix.get('total_rows_available'))}")
    lines.append(f"- Rows shown: {len(_rows(appendix.get('rows')))}")
    lines.append(
        f"- Manual follow-up rows: {_int(_mapping(appendix.get('summary')).get('manual_follow_up_rows'))}"
    )
    lines.append(
        f"- Boundary: {_text(appendix.get('documentation_boundary_note'), 'Documentation-only review context.')}"
    )
    if _rows(appendix.get("rows")):
        lines += [
            "| Step 2 context category | Step 2 recorded value | Component Library asset | Source/provenance review | Record review status | Sequence metadata | Manual follow-up |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in _rows(appendix.get("rows")):
            lines.append(
                "| "
                + " | ".join(
                    _text(row.get(key), "NOT_AVAILABLE").replace("|", "\\|").replace("\n", "<br>")
                    for key in (
                        "Step 2 context category",
                        "Step 2 recorded value",
                        "Component Library asset",
                        "Source/provenance review",
                        "Record review status",
                        "Sequence metadata",
                        "Manual follow-up",
                    )
                )
                + " |"
            )
    else:
        lines.append(
            f"- {_text(appendix.get('empty_state_message'), STEP2_COMPONENT_CONTEXT_APPENDIX_EMPTY_STATE)}"
        )

    lines += ["", f"### {_text(readback.get('title'), COMPONENT_LIBRARY_HANDOFF_READBACK_TITLE)}"]
    lines.append(f"- {_text(readback.get('intro'), COMPONENT_LIBRARY_HANDOFF_READBACK_INTRO)}")
    lines.append(
        f"- Boundary: {_text(readback.get('boundary_note'), COMPONENT_LIBRARY_HANDOFF_READBACK_BOUNDARY_NOTE)}"
    )
    readback_summary = _mapping(readback.get("summary"))
    lines.append(f"- Slot rows with records: {_int(readback_summary.get('slot_rows_with_records'))}")
    lines.append(f"- Source/provenance follow-up slots: {_int(readback_summary.get('source_follow_up_slot_count'))}")
    lines.append(f"- Manual follow-up slots: {_int(readback_summary.get('manual_follow_up_slot_count'))}")
    readback_rows = _rows(readback.get("rows"))
    if readback_rows:
        lines += [
            "| Slot | Record count | Records | Source/provenance status | Manual follow-up |",
            "| --- | --- | --- | --- | --- |",
        ]
        for row in readback_rows:
            lines.append(
                "| "
                + " | ".join(
                    _text(row.get(key), "NOT_AVAILABLE").replace("|", "\\|").replace("\n", "<br>")
                    for key in COMPONENT_LIBRARY_HANDOFF_READBACK_COLUMNS
                )
                + " |"
            )
    else:
        lines.append(f"- {_text(readback.get('empty_state'), COMPONENT_LIBRARY_HANDOFF_READBACK_EMPTY_STATE)}")

    lines += ["", "### Boundary notes"]
    for note in handoff.get("boundary_notes") or []:
        lines.append(f"- {_text(note)}")
    return "\n".join(lines)


def build_project_review_handoff_center(
    *,
    expression_construct_queue: Mapping[str, Any] | None = None,
    candidate_queue: Mapping[str, Any] | None = None,
    promoter_queue: Mapping[str, Any] | None = None,
    follow_up_index: Mapping[str, Any] | None = None,
    host_chassis_context: Mapping[str, Any] | None = None,
    step2_component_context_appendix: Mapping[str, Any] | None = None,
    component_library_records: list[dict[str, Any]] | None = None,
    report_markdown_available: bool = False,
) -> dict[str, Any]:
    """Build a read-only project handoff center from existing review outputs."""
    expression_construct_queue = _mapping(expression_construct_queue)
    candidate_queue = _mapping(candidate_queue)
    promoter_queue = _mapping(promoter_queue)
    host_chassis_context = _mapping(host_chassis_context)
    step2_component_context_appendix = _mapping(step2_component_context_appendix)
    component_library_source_provenance_readback = build_component_library_handoff_readback(
        component_library_records or []
    )
    follow_up_index = (
        _mapping(follow_up_index)
        if isinstance(follow_up_index, Mapping)
        else build_project_review_follow_up_index(candidate_queue, promoter_queue)
    )

    expression_count = _expression_follow_up_count(expression_construct_queue)
    candidate_count = _candidate_follow_up_count(candidate_queue, follow_up_index)
    promoter_count = _promoter_follow_up_count(promoter_queue, follow_up_index)
    host_rows = _host_context_follow_up_rows(host_chassis_context)
    host_count = len(host_rows)
    total_count = expression_count + candidate_count + promoter_count + host_count

    follow_up_rows = sorted(
        [
            *_normalize_expression_rows(expression_construct_queue),
            *_normalize_follow_up_index_rows(follow_up_index),
            *host_rows,
        ],
        key=lambda row: (
            _text(row.get("source_surface")).casefold(),
            _text(row.get("item_label")).casefold(),
            _text(row.get("issue_type")).casefold(),
        ),
    )

    handoff = {
        "title": HANDOFF_TITLE,
        "subtitle": HANDOFF_SUBTITLE,
        "status": "AVAILABLE" if total_count or report_markdown_available else "NOT_AVAILABLE",
        "summary": {
            "total_follow_up_items": total_count,
            "expression_construct_documentation_follow_up_count": expression_count,
            "candidate_evidence_follow_up_count": candidate_count,
            "promoter_source_review_follow_up_count": promoter_count,
            "host_context_documentation_follow_up_count": host_count,
            "report_markdown_available": bool(report_markdown_available),
            "component_library_readback_slot_count": _int(
                _mapping(component_library_source_provenance_readback.get("summary")).get("slot_rows_with_records")
            ),
            "component_library_source_follow_up_slot_count": _int(
                _mapping(component_library_source_provenance_readback.get("summary")).get("source_follow_up_slot_count")
            ),
            "component_library_manual_follow_up_slot_count": _int(
                _mapping(component_library_source_provenance_readback.get("summary")).get("manual_follow_up_slot_count")
            ),
        },
        "expression_construct_queue": expression_construct_queue,
        "step2_component_context_appendix": step2_component_context_appendix,
        "component_library_source_provenance_readback": component_library_source_provenance_readback,
        "checklist": _build_checklist(
            expression_count=expression_count,
            expression_queue=expression_construct_queue,
            candidate_count=candidate_count,
            promoter_count=promoter_count,
            host_count=host_count,
            host_context=host_chassis_context,
            report_markdown_available=report_markdown_available,
        ),
        "follow_up_rows": follow_up_rows,
        "total_rows_available": len(follow_up_rows),
        "empty_state_message": "" if follow_up_rows else HANDOFF_EMPTY_STATE,
        "boundary_notes": HANDOFF_BOUNDARY_NOTES[:],
    }
    handoff = normalize_generated_output_claims(handoff)
    handoff["markdown"] = format_project_review_handoff_markdown(handoff)
    assert_no_misleading_generated_claims(handoff, context="handoff center")
    return handoff
