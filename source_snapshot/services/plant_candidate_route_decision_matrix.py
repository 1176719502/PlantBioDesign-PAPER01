from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    normalize_generated_output_text,
)
from services.placeholder_review_value import clean_review_value, has_recorded_review_value


DOCUMENTATION_ONLY_BOUNDARY_NOTE = (
    "Documentation-only candidate route review. Rows preserve user-entered route context, "
    "evidence notes, gaps, and manual follow-up for human review; they do not choose a "
    "biological route or judge downstream use state."
)
EMPTY_STATE_MESSAGE = (
    "No candidate route rows are currently recorded. Add at least one route row to compare "
    "documentation context, evidence notes, gaps, and manual follow-up for review."
)
MISSING_FIELD_ACTION = (
    "Record missing route context, source/provenance notes, or manual follow-up before adding "
    "the route row to a review package draft."
)
RECORDED_FIELD_ACTION = (
    "Continue manual documentation review with the recorded route context and rationale."
)

DECISION_STATUS_OPTIONS: tuple[str, ...] = (
    "Under review",
    "Needs more evidence",
    "Paused",
    "Rejected by reviewer",
    "Selected for documentation follow-up",
)
DEFAULT_DECISION_STATUS = DECISION_STATUS_OPTIONS[0]

ROUTE_DECISION_FIELD_SPECS: tuple[dict[str, str], ...] = (
    {
        "key": "route_label",
        "label": "Route label",
        "gap": "Record a human-readable label for this candidate route row.",
    },
    {
        "key": "route_type",
        "label": "Route type",
        "gap": "Record the user-entered route class or review route type.",
    },
    {
        "key": "plant_host_context",
        "label": "Plant host context",
        "gap": "Record plant host or species context for documentation review.",
    },
    {
        "key": "tissue_or_compartment_context",
        "label": "Tissue / compartment context",
        "gap": "Record tissue, organ, compartment, or localization context when relevant.",
    },
    {
        "key": "expression_mode_context",
        "label": "Expression mode context",
        "gap": "Record expression-mode context as documentation only.",
    },
    {
        "key": "component_context_summary",
        "label": "Component context summary",
        "gap": "Record component context or note which component records still need review.",
    },
    {
        "key": "linked_evidence_notes",
        "label": "Linked evidence notes",
        "gap": "Record source/provenance or evidence notes linked to this route row.",
    },
    {
        "key": "route_risk_notes",
        "label": "Route risk / uncertainty notes",
        "gap": "Record uncertainty, limitation, or route-risk notes for manual review.",
    },
    {
        "key": "missing_information",
        "label": "Missing information",
        "gap": "Record missing information that should remain visible in the review queue.",
    },
    {
        "key": "manual_follow_up",
        "label": "Manual follow-up",
        "gap": "Record the next human/company/expert review action.",
    },
    {
        "key": "decision_status",
        "label": "Manual review status",
        "gap": "Record a documentation review status for this route row.",
    },
    {
        "key": "decision_rationale",
        "label": "Decision rationale",
        "gap": "Record the human rationale for keeping this route in review.",
    },
    {
        "key": "rejection_rationale",
        "label": "Rejection rationale",
        "gap": "Record rationale when a reviewer excludes this row from follow-up.",
    },
)

REQUIRED_ROUTE_FIELDS: tuple[str, ...] = (
    "route_label",
    "route_type",
    "plant_host_context",
    "linked_evidence_notes",
    "manual_follow_up",
    "decision_status",
)

_RECORD_LIST_KEYS = (
    "route_rows",
    "candidate_route_rows",
    "candidate_routes",
    "rows",
)

WORKSPACE_BOUNDARY_NOTE = (
    "Documentation-only plant route review workspace. It links candidate route rows, "
    "evidence cards, component traceability notes, gaps, and manual follow-up for human "
    "review without changing project storage or package export data."
)


def _text(value: Any, fallback: str = "") -> str:
    return clean_review_value(value, fallback)


def _record_value(record: Any, key: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(key, "")
    return getattr(record, key, "")


def _as_record(record: Any) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    data = getattr(record, "__dict__", None)
    if isinstance(data, Mapping):
        return dict(data)
    return {}


def _extract_records(rows_or_view_model: Any) -> list[Any]:
    if rows_or_view_model is None:
        return []
    if isinstance(rows_or_view_model, Mapping):
        for key in _RECORD_LIST_KEYS:
            rows = rows_or_view_model.get(key)
            if isinstance(rows, list | tuple):
                return list(rows)
        return [rows_or_view_model]
    if isinstance(rows_or_view_model, (str, bytes)):
        return []
    if isinstance(rows_or_view_model, Iterable):
        return list(rows_or_view_model)
    return []


def _status(value: Any) -> str:
    clean = str(value or "").strip()
    return clean if clean in DECISION_STATUS_OPTIONS else DEFAULT_DECISION_STATUS


def _missing_required_fields(row: Mapping[str, Any]) -> list[str]:
    return [
        field
        for field in REQUIRED_ROUTE_FIELDS
        if not has_recorded_review_value(row.get(field))
    ]


def _field_label(key: str) -> str:
    for spec in ROUTE_DECISION_FIELD_SPECS:
        if spec["key"] == key:
            return spec["label"]
    return key.replace("_", " ").title()


def normalize_route_decision_rows(rows_or_view_model: Any) -> list[dict[str, str]]:
    """Normalize user-entered candidate route rows without inventing biological values."""
    normalized_rows: list[dict[str, str]] = []
    for index, raw_record in enumerate(_extract_records(rows_or_view_model), start=1):
        record = _as_record(raw_record)
        row: dict[str, str] = {}
        for spec in ROUTE_DECISION_FIELD_SPECS:
            key = spec["key"]
            if key == "decision_status":
                row[key] = _status(_record_value(record, key))
            else:
                row[key] = _text(_record_value(record, key))
        has_route_content = any(
            has_recorded_review_value(value)
            for key, value in row.items()
            if key != "decision_status"
        )
        if not has_route_content:
            continue
        if not row["route_label"]:
            row["route_label"] = f"candidate route {index}"
        normalized_rows.append(row)
    return normalized_rows


def _row_review_focus(missing_fields: list[str]) -> str:
    if not missing_fields:
        return "manual documentation review"
    if "linked_evidence_notes" in missing_fields:
        return "source/provenance review"
    if "manual_follow_up" in missing_fields:
        return "manual follow-up review"
    return "route context review"


def _row_gap_label(missing_fields: list[str]) -> str:
    if not missing_fields:
        return "No required documentation fields missing"
    return _row_review_focus(missing_fields)


def _manual_action(missing_fields: list[str]) -> str:
    return MISSING_FIELD_ACTION if missing_fields else RECORDED_FIELD_ACTION


def _sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    return (
        str(row.get("route_label") or "").casefold(),
        str(row.get("route_type") or "").casefold(),
    )


def build_route_decision_matrix(rows_or_view_model: Any) -> dict[str, Any]:
    """Build a documentation-only candidate route decision matrix payload."""
    rows: list[dict[str, Any]] = []
    for row in normalize_route_decision_rows(rows_or_view_model):
        missing_fields = _missing_required_fields(row)
        rows.append(
            {
                **row,
                "missing_fields": missing_fields,
                "documentation_status": (
                    "documentation fields recorded"
                    if not missing_fields
                    else "documentation gaps recorded"
                ),
                "review_focus": _row_review_focus(missing_fields),
                "gap_label": _row_gap_label(missing_fields),
                "next_manual_action": _manual_action(missing_fields),
                "boundary_note": DOCUMENTATION_ONLY_BOUNDARY_NOTE,
            }
        )

    rows = sorted(rows, key=_sort_key)
    status_counts = Counter(row["decision_status"] for row in rows)
    focus_counts = Counter(row["review_focus"] for row in rows)
    rows_with_gaps = [row for row in rows if row["missing_fields"]]
    selected_for_follow_up_count = status_counts.get("Selected for documentation follow-up", 0)
    rejected_by_reviewer_count = status_counts.get("Rejected by reviewer", 0)

    return {
        "title": "Plant Candidate Route Decision Matrix",
        "subtitle": "Session-only candidate route review for documentation follow-up.",
        "rows": rows,
        "summary": {
            "route_count": len(rows),
            "documentation_complete_count": len(rows) - len(rows_with_gaps),
            "documentation_gap_count": len(rows_with_gaps),
            "manual_follow_up_count": sum(
                1 for row in rows if has_recorded_review_value(row.get("manual_follow_up"))
            ),
            "selected_for_documentation_follow_up_count": selected_for_follow_up_count,
            "rejected_by_reviewer_count": rejected_by_reviewer_count,
            "decision_status_counts": dict(sorted(status_counts.items())),
            "review_focus_counts": dict(sorted(focus_counts.items())),
        },
        "gap_rows": [
            {
                "route_label": row["route_label"],
                "route_type": row["route_type"],
                "missing_fields": row["missing_fields"],
                "gap_label": row["gap_label"],
                "next_manual_action": row["next_manual_action"],
            }
            for row in rows_with_gaps
        ],
        "manual_follow_up_queue": [
            {
                "route_label": row["route_label"],
                "decision_status": row["decision_status"],
                "manual_follow_up": row["manual_follow_up"] or row["next_manual_action"],
                "review_focus": row["review_focus"],
            }
            for row in rows
            if row["decision_status"] != "Rejected by reviewer" or has_recorded_review_value(row.get("rejection_rationale"))
        ],
        "empty_state_message": EMPTY_STATE_MESSAGE if not rows else "",
        "boundary_note": DOCUMENTATION_ONLY_BOUNDARY_NOTE,
    }


def build_route_decision_rows(rows_or_view_model: Any) -> list[dict[str, Any]]:
    return build_route_decision_matrix(rows_or_view_model)["rows"]


def _matrix_payload(rows_or_matrix: Any) -> dict[str, Any]:
    if isinstance(rows_or_matrix, Mapping) and isinstance(rows_or_matrix.get("rows"), list):
        return dict(rows_or_matrix)
    return build_route_decision_matrix(rows_or_matrix)


def _recorded_status(value: Any, *, recorded: str, missing: str) -> str:
    return recorded if has_recorded_review_value(value) else missing


def build_route_evidence_cards(rows_or_matrix: Any) -> dict[str, Any]:
    """Build route-linked evidence cards from the candidate route matrix payload."""
    matrix = _matrix_payload(rows_or_matrix)
    rows = [row for row in matrix.get("rows") or [] if isinstance(row, Mapping)]
    cards: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        cards.append(
            {
                "card_id": f"route-evidence-{index:02d}",
                "route_label": _text(row.get("route_label"), f"candidate route {index}"),
                "route_type": _text(row.get("route_type")),
                "evidence_notes": _text(row.get("linked_evidence_notes")),
                "evidence_context_status": _recorded_status(
                    row.get("linked_evidence_notes"),
                    recorded="evidence note recorded",
                    missing="evidence note needed",
                ),
                "source_provenance_status": _recorded_status(
                    row.get("linked_evidence_notes"),
                    recorded="source/provenance note recorded",
                    missing="source/provenance note needed",
                ),
                "uncertainty_notes": _text(row.get("route_risk_notes") or row.get("missing_information")),
                "uncertainty_status": _recorded_status(
                    row.get("route_risk_notes") or row.get("missing_information"),
                    recorded="uncertainty or missing-info note recorded",
                    missing="uncertainty note not recorded",
                ),
                "manual_follow_up": _text(row.get("manual_follow_up") or row.get("next_manual_action")),
                "manual_review_status": _status(row.get("decision_status")),
                "boundary_note": WORKSPACE_BOUNDARY_NOTE,
            }
        )

    cards_with_evidence = sum(
        1 for card in cards if card["evidence_context_status"] == "evidence note recorded"
    )
    cards_with_uncertainty = sum(
        1 for card in cards if card["uncertainty_status"] == "uncertainty or missing-info note recorded"
    )
    return {
        "title": "Plant Route Evidence Cards",
        "cards": cards,
        "summary": {
            "evidence_card_count": len(cards),
            "cards_with_evidence_notes": cards_with_evidence,
            "cards_needing_evidence_notes": len(cards) - cards_with_evidence,
            "cards_with_uncertainty_notes": cards_with_uncertainty,
            "cards_with_manual_follow_up": sum(
                1 for card in cards if has_recorded_review_value(card.get("manual_follow_up"))
            ),
        },
        "empty_state_message": (
            "No route-linked evidence cards are available until at least one candidate route row is recorded."
            if not cards
            else ""
        ),
        "boundary_note": WORKSPACE_BOUNDARY_NOTE,
    }


def build_route_component_traceability(rows_or_matrix: Any) -> dict[str, Any]:
    """Build route-to-component traceability rows without parsing or selecting components."""
    matrix = _matrix_payload(rows_or_matrix)
    rows = [row for row in matrix.get("rows") or [] if isinstance(row, Mapping)]
    traceability_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        component_context = _text(row.get("component_context_summary"))
        evidence_notes = _text(row.get("linked_evidence_notes"))
        traceability_rows.append(
            {
                "traceability_row_id": f"route-component-{index:02d}",
                "route_label": _text(row.get("route_label"), f"candidate route {index}"),
                "route_type": _text(row.get("route_type")),
                "component_context_summary": component_context,
                "component_trace_status": _recorded_status(
                    component_context,
                    recorded="component context recorded",
                    missing="component context needed",
                ),
                "linked_evidence_notes": evidence_notes,
                "source_trace_status": _recorded_status(
                    evidence_notes,
                    recorded="source trace note recorded",
                    missing="source trace note needed",
                ),
                "manual_follow_up": _text(row.get("manual_follow_up") or row.get("next_manual_action")),
                "manual_review_status": _status(row.get("decision_status")),
                "boundary_note": WORKSPACE_BOUNDARY_NOTE,
            }
        )

    rows_with_component_context = sum(
        1
        for row in traceability_rows
        if row["component_trace_status"] == "component context recorded"
    )
    rows_with_source_trace = sum(
        1 for row in traceability_rows if row["source_trace_status"] == "source trace note recorded"
    )
    return {
        "title": "Plant Route Component Traceability Matrix",
        "rows": traceability_rows,
        "summary": {
            "traceability_row_count": len(traceability_rows),
            "rows_with_component_context": rows_with_component_context,
            "rows_needing_component_context": len(traceability_rows) - rows_with_component_context,
            "rows_with_source_trace_notes": rows_with_source_trace,
            "rows_needing_source_trace_notes": len(traceability_rows) - rows_with_source_trace,
        },
        "empty_state_message": (
            "No component traceability rows are available until at least one candidate route row is recorded."
            if not traceability_rows
            else ""
        ),
        "boundary_note": WORKSPACE_BOUNDARY_NOTE,
    }


def build_route_review_workspace(rows_or_view_model: Any) -> dict[str, Any]:
    """Build the combined route, evidence, component, and follow-up workspace payload."""
    matrix = build_route_decision_matrix(rows_or_view_model)
    evidence_cards = build_route_evidence_cards(matrix)
    component_traceability = build_route_component_traceability(matrix)
    matrix_summary = matrix.get("summary") or {}
    evidence_summary = evidence_cards.get("summary") or {}
    trace_summary = component_traceability.get("summary") or {}
    return {
        "title": "Plant Route Review Workspace",
        "matrix": matrix,
        "evidence_cards": evidence_cards,
        "component_traceability": component_traceability,
        "summary": {
            "route_count": matrix_summary.get("route_count", 0),
            "documentation_gap_count": matrix_summary.get("documentation_gap_count", 0),
            "manual_follow_up_count": matrix_summary.get("manual_follow_up_count", 0),
            "evidence_card_count": evidence_summary.get("evidence_card_count", 0),
            "cards_needing_evidence_notes": evidence_summary.get("cards_needing_evidence_notes", 0),
            "traceability_row_count": trace_summary.get("traceability_row_count", 0),
            "rows_needing_component_context": trace_summary.get("rows_needing_component_context", 0),
        },
        "empty_state_message": matrix.get("empty_state_message") or "",
        "boundary_note": WORKSPACE_BOUNDARY_NOTE,
    }


def _summary_lines(summary: Mapping[str, Any]) -> list[str]:
    return [
        f"- route rows: {summary.get('route_count', 0)}",
        f"- rows with required documentation fields recorded: {summary.get('documentation_complete_count', 0)}",
        f"- rows with documentation gaps: {summary.get('documentation_gap_count', 0)}",
        f"- rows with manual follow-up notes: {summary.get('manual_follow_up_count', 0)}",
        "- rows marked for documentation follow-up: "
        f"{summary.get('selected_for_documentation_follow_up_count', 0)}",
        f"- rows rejected by reviewer: {summary.get('rejected_by_reviewer_count', 0)}",
    ]


def format_route_decision_matrix_markdown(rows_or_matrix: Any) -> str:
    """Format a deterministic Markdown snapshot for manual route review."""
    matrix = rows_or_matrix if isinstance(rows_or_matrix, Mapping) and "rows" in rows_or_matrix else build_route_decision_matrix(rows_or_matrix)
    rows = [row for row in matrix.get("rows") or [] if isinstance(row, Mapping)]
    summary = dict(matrix.get("summary") or {})
    lines = [
        "# Plant Candidate Route Decision Matrix Snapshot",
        "",
        DOCUMENTATION_ONLY_BOUNDARY_NOTE,
        "This snapshot is session-only review text. It does not save structured project records or modify package export data.",
        "",
        "## Summary",
    ]
    lines.extend(_summary_lines(summary))

    lines.extend(["", "## Candidate route rows"])
    if rows:
        for row in rows:
            lines.extend(
                [
                    f"- Route label: {row.get('route_label') or 'NOT_AVAILABLE'}",
                    f"  - Route type: {row.get('route_type') or 'NOT_AVAILABLE'}",
                    f"  - Plant host context: {row.get('plant_host_context') or 'NOT_AVAILABLE'}",
                    f"  - Tissue / compartment context: {row.get('tissue_or_compartment_context') or 'NOT_AVAILABLE'}",
                    f"  - Expression mode context: {row.get('expression_mode_context') or 'NOT_AVAILABLE'}",
                    f"  - Component context summary: {row.get('component_context_summary') or 'NOT_AVAILABLE'}",
                    f"  - Linked evidence notes: {row.get('linked_evidence_notes') or 'NOT_AVAILABLE'}",
                    f"  - Route risk / uncertainty notes: {row.get('route_risk_notes') or 'NOT_AVAILABLE'}",
                    f"  - Missing information: {row.get('missing_information') or 'NOT_AVAILABLE'}",
                    f"  - Manual follow-up: {row.get('manual_follow_up') or row.get('next_manual_action') or 'NOT_AVAILABLE'}",
                    f"  - Manual review status: {row.get('decision_status') or DEFAULT_DECISION_STATUS}",
                    f"  - Decision rationale: {row.get('decision_rationale') or 'NOT_AVAILABLE'}",
                    f"  - Rejection rationale: {row.get('rejection_rationale') or 'NOT_AVAILABLE'}",
                ]
            )
    else:
        lines.append(f"- {matrix.get('empty_state_message') or EMPTY_STATE_MESSAGE}")

    lines.extend(["", "## Documentation gap rows"])
    gap_rows = [row for row in matrix.get("gap_rows") or [] if isinstance(row, Mapping)]
    if gap_rows:
        for row in gap_rows:
            fields = ", ".join(row.get("missing_fields") or [])
            lines.append(
                f"- {row.get('route_label') or 'candidate route'}: {row.get('gap_label')} "
                f"({fields or 'no required fields missing'}). {row.get('next_manual_action')}"
            )
    else:
        lines.append("- No required documentation gaps were detected in the current route rows.")

    lines.extend(["", "## Manual follow-up queue"])
    queue_rows = [row for row in matrix.get("manual_follow_up_queue") or [] if isinstance(row, Mapping)]
    if queue_rows:
        for row in queue_rows:
            lines.append(
                f"- {row.get('route_label') or 'candidate route'}: "
                f"{row.get('manual_follow_up') or 'Manual documentation review needed.'}"
            )
    else:
        lines.append("- No manual follow-up rows are currently available.")

    lines.extend(["", "## Boundary note", f"- {DOCUMENTATION_ONLY_BOUNDARY_NOTE}", ""])
    markdown = normalize_generated_output_text("\n".join(lines))
    assert_no_misleading_generated_claims(markdown, context="candidate route decision matrix")
    return markdown


def format_route_review_workspace_markdown(rows_or_workspace: Any) -> str:
    """Format a compact combined Markdown snapshot for manual route review."""
    workspace = (
        dict(rows_or_workspace)
        if isinstance(rows_or_workspace, Mapping) and "matrix" in rows_or_workspace
        else build_route_review_workspace(rows_or_workspace)
    )
    summary = dict(workspace.get("summary") or {})
    matrix = _matrix_payload(workspace.get("matrix") or {})
    evidence_cards = workspace.get("evidence_cards") or {}
    component_traceability = workspace.get("component_traceability") or {}
    cards = [card for card in evidence_cards.get("cards") or [] if isinstance(card, Mapping)]
    trace_rows = [row for row in component_traceability.get("rows") or [] if isinstance(row, Mapping)]

    lines = [
        "# Plant Route Review Workspace Snapshot",
        "",
        WORKSPACE_BOUNDARY_NOTE,
        "This snapshot is runtime-only review text. It does not save structured project records or modify package export data.",
        "",
        "## Workspace summary",
        f"- candidate route rows: {summary.get('route_count', 0)}",
        f"- documentation gap rows: {summary.get('documentation_gap_count', 0)}",
        f"- manual follow-up rows: {summary.get('manual_follow_up_count', 0)}",
        f"- evidence cards: {summary.get('evidence_card_count', 0)}",
        f"- evidence cards needing notes: {summary.get('cards_needing_evidence_notes', 0)}",
        f"- component traceability rows: {summary.get('traceability_row_count', 0)}",
        f"- component context rows needing notes: {summary.get('rows_needing_component_context', 0)}",
        "",
        "## Route rows",
    ]
    rows = [row for row in matrix.get("rows") or [] if isinstance(row, Mapping)]
    if rows:
        for row in rows:
            lines.append(
                "- "
                f"{row.get('route_label') or 'candidate route'} | "
                f"{row.get('route_type') or 'NOT_AVAILABLE'} | "
                f"{row.get('decision_status') or DEFAULT_DECISION_STATUS} | "
                f"{row.get('review_focus') or 'manual documentation review'}"
            )
    else:
        lines.append(f"- {workspace.get('empty_state_message') or EMPTY_STATE_MESSAGE}")

    lines.extend(["", "## Evidence cards"])
    if cards:
        for card in cards:
            lines.append(
                "- "
                f"{card.get('card_id')}: {card.get('route_label') or 'candidate route'}; "
                f"{card.get('evidence_context_status')}; "
                f"{card.get('source_provenance_status')}; "
                f"follow-up: {card.get('manual_follow_up') or 'manual documentation review needed'}"
            )
    else:
        lines.append("- No route-linked evidence cards are currently available.")

    lines.extend(["", "## Component traceability"])
    if trace_rows:
        for row in trace_rows:
            lines.append(
                "- "
                f"{row.get('traceability_row_id')}: {row.get('route_label') or 'candidate route'}; "
                f"{row.get('component_trace_status')}; {row.get('source_trace_status')}; "
                f"manual review status: {row.get('manual_review_status') or DEFAULT_DECISION_STATUS}"
            )
    else:
        lines.append("- No component traceability rows are currently available.")

    lines.extend(["", "## Boundary note", f"- {WORKSPACE_BOUNDARY_NOTE}", ""])
    markdown = normalize_generated_output_text("\n".join(lines))
    assert_no_misleading_generated_claims(markdown, context="plant route review workspace")
    return markdown
