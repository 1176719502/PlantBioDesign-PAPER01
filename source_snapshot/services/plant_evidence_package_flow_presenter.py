from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    normalize_generated_output_text,
)


PAGE_TITLE = "Plant Evidence Package Flow Readback"
SUBTITLE = "Documentation-only evidence, gap, package, and handoff summary for manual review."
BOUNDARY_NOTICE = (
    "Documentation-only plant evidence/package flow presenter for manual review. It formats "
    "existing readback data without resolving gaps, choosing components, creating construct "
    "outputs, changing package export data, or judging downstream use."
)
EMPTY_STATE_MESSAGE = (
    "No evidence/package flow rows are available. Build or provide a flow readback before "
    "using this presenter for manual documentation review."
)

PRESENTER_KEYS: tuple[str, ...] = (
    "page_title",
    "subtitle",
    "summary_card",
    "route_card",
    "evidence_rows",
    "gap_rows",
    "package_section_rows",
    "handoff_card",
    "boundary_notice",
    "markdown_snapshot",
    "empty_state",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _empty_presenter() -> dict[str, Any]:
    return {
        "page_title": PAGE_TITLE,
        "subtitle": SUBTITLE,
        "summary_card": {
            "flow_status": "",
            "evidence_record_count": 0,
            "gap_review_item_count": 0,
            "package_section_count": 0,
            "manual_review_required": True,
        },
        "route_card": {},
        "evidence_rows": [],
        "gap_rows": [],
        "package_section_rows": [],
        "handoff_card": {},
        "boundary_notice": BOUNDARY_NOTICE,
        "markdown_snapshot": "",
        "empty_state": {"is_empty": True, "message": EMPTY_STATE_MESSAGE},
    }


def _evidence_rows(flow: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(_mapping_list(flow.get("evidence_records")), start=1):
        rows.append(
            {
                "row_id": f"evidence-{index:02d}",
                "evidence_id": _text(row.get("evidence_id")),
                "linked_slot_id": _text(row.get("linked_slot_id")),
                "linked_module_id": _text(row.get("linked_module_id")),
                "source_label": _text(row.get("source_label")),
                "evidence_status": _text(row.get("evidence_status")),
                "manual_review_status": _text(row.get("manual_review_status")),
                "package_section": _text(row.get("package_section")),
            }
        )
    return rows


def _gap_rows(flow: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(_mapping_list(flow.get("gap_review_items")), start=1):
        rows.append(
            {
                "row_id": f"gap-{index:02d}",
                "item_id": _text(row.get("item_id")),
                "linked_slot_id": _text(row.get("linked_slot_id")),
                "gap_type": _text(row.get("gap_type")),
                "missing_field": _text(row.get("missing_field")),
                "review_question": _text(row.get("review_question")),
                "manual_review_status": _text(row.get("manual_review_status")),
                "handoff_section": _text(row.get("handoff_section")),
            }
        )
    return rows


def _package_section_rows(flow: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(_mapping_list(flow.get("package_sections")), start=1):
        rows.append(
            {
                "row_id": f"package-section-{index:02d}",
                "section_id": _text(row.get("section_id")),
                "section_label": _text(row.get("section_label")),
                "display_order": int(row.get("display_order") or index),
                "status": _text(row.get("status")) or "included",
            }
        )
    return rows


def _summary_card(
    flow: Mapping[str, Any],
    evidence_rows: Sequence[Mapping[str, Any]],
    gap_rows: Sequence[Mapping[str, Any]],
    package_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    handoff = _mapping(flow.get("handoff_summary"))
    return {
        "flow_status": _text(flow.get("flow_status")),
        "evidence_record_count": len(evidence_rows),
        "gap_review_item_count": len(gap_rows),
        "package_section_count": len(package_rows),
        "manual_review_required": bool(handoff.get("manual_review_required", True)),
    }


def _route_card(flow: Mapping[str, Any]) -> dict[str, Any]:
    route = _mapping(flow.get("route_summary"))
    return {
        "route_template_id": _text(route.get("route_template_id")),
        "canonical_route_template_id": _text(route.get("canonical_route_template_id")),
        "route_id": _text(route.get("route_id")),
        "route_name": _text(route.get("route_name")),
        "draft_status": _text(route.get("draft_status")),
        "package_status": _text(route.get("package_status")),
    }


def _handoff_card(flow: Mapping[str, Any]) -> dict[str, Any]:
    handoff = _mapping(flow.get("handoff_summary"))
    return {
        "package_id": _text(handoff.get("package_id")),
        "package_scope": _text(handoff.get("package_scope")),
        "identity_md5": _text(handoff.get("identity_md5")),
        "handoff_status": _text(handoff.get("handoff_status")) or "manual_review_required",
        "manual_review_required": bool(handoff.get("manual_review_required", True)),
    }


def format_evidence_package_flow_markdown(presenter: Mapping[str, Any]) -> str:
    summary = _mapping(presenter.get("summary_card"))
    route = _mapping(presenter.get("route_card"))
    handoff = _mapping(presenter.get("handoff_card"))
    evidence_rows = _mapping_list(presenter.get("evidence_rows"))
    gap_rows = _mapping_list(presenter.get("gap_rows"))
    package_rows = _mapping_list(presenter.get("package_section_rows"))
    lines = [
        "# Plant Evidence Package Flow Readback Snapshot",
        "",
        BOUNDARY_NOTICE,
        "This snapshot is review text only. It does not save records, export packages, or create construct outputs.",
        "",
        "## Summary",
        f"- flow status: {summary.get('flow_status') or 'NOT_AVAILABLE'}",
        f"- evidence records: {summary.get('evidence_record_count', 0)}",
        f"- gap review items: {summary.get('gap_review_item_count', 0)}",
        f"- package sections: {summary.get('package_section_count', 0)}",
        f"- manual review required: {summary.get('manual_review_required', True)}",
        "",
        "## Route",
        f"- route ID: {route.get('route_id') or 'NOT_AVAILABLE'}",
        f"- route template ID: {route.get('route_template_id') or 'NOT_AVAILABLE'}",
        f"- package status: {route.get('package_status') or 'NOT_AVAILABLE'}",
        "",
        "## Evidence records",
    ]
    if evidence_rows:
        for row in evidence_rows:
            lines.append(
                "- "
                f"{row.get('evidence_id') or 'evidence'} | "
                f"{row.get('linked_slot_id') or 'slot'} | "
                f"{row.get('evidence_status') or 'manual_review_required'}"
            )
    else:
        lines.append(f"- {EMPTY_STATE_MESSAGE}")

    lines.extend(["", "## Gap review items"])
    if gap_rows:
        for row in gap_rows:
            lines.append(
                "- "
                f"{row.get('item_id') or 'gap'} | "
                f"{row.get('linked_slot_id') or 'slot'} | "
                f"{row.get('manual_review_status') or 'manual_review_required'}"
            )
    else:
        lines.append("- No gap review items are currently available.")

    lines.extend(["", "## Package sections"])
    if package_rows:
        for row in package_rows:
            lines.append(
                "- "
                f"{row.get('display_order') or 0}. "
                f"{row.get('section_label') or row.get('section_id') or 'section'}: "
                f"{row.get('status') or 'included'}"
            )
    else:
        lines.append("- No package section rows are currently available.")

    lines.extend(
        [
            "",
            "## Handoff summary",
            f"- package ID: {handoff.get('package_id') or 'NOT_AVAILABLE'}",
            f"- handoff status: {handoff.get('handoff_status') or 'manual_review_required'}",
            "",
            "## Boundary note",
            f"- {BOUNDARY_NOTICE}",
            "",
        ]
    )
    markdown = normalize_generated_output_text("\n".join(lines))
    assert_no_misleading_generated_claims(markdown, context="plant evidence package flow presenter")
    return markdown


def present_evidence_package_flow_readback(flow_readback: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return deterministic plain readback sections for an existing evidence/package flow."""
    flow = flow_readback if isinstance(flow_readback, Mapping) else {}
    if not flow:
        return _empty_presenter()

    evidence_rows = _evidence_rows(flow)
    gap_rows = _gap_rows(flow)
    package_rows = _package_section_rows(flow)
    presented = _empty_presenter()
    presented.update(
        {
            "summary_card": _summary_card(flow, evidence_rows, gap_rows, package_rows),
            "route_card": _route_card(flow),
            "evidence_rows": evidence_rows,
            "gap_rows": gap_rows,
            "package_section_rows": package_rows,
            "handoff_card": _handoff_card(flow),
            "empty_state": {
                "is_empty": not bool(evidence_rows or gap_rows or package_rows),
                "message": "" if evidence_rows or gap_rows or package_rows else EMPTY_STATE_MESSAGE,
            },
        }
    )
    presented["markdown_snapshot"] = format_evidence_package_flow_markdown(presented)
    return {key: presented[key] for key in PRESENTER_KEYS}
