from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import streamlit as st

from services import plant_construct_draft_preview_presenter as presenter_service
from views.tool_typography import (
    inject_tool_typography_css,
    render_boundary_note,
    render_compact_summary_cards,
    render_help_text,
    render_section_heading,
    render_tool_header,
)


SECTION_STATUS_AVAILABLE = "plant_construct_draft_preview_section_available"
SECTION_STATUS_EMPTY = "plant_construct_draft_preview_section_empty"
EMPTY_STATE_COPY = "No readable construct draft preview is available for this read-only section."
SECTION_HELP_COPY = (
    "Read-only preview from the R333 presenter. Slot state, source IDs, evidence IDs, "
    "missing reasons, review items, and warnings are displayed as supplied."
)

SUMMARY_KEYS = (
    "draft_id",
    "draft_status",
    "manual_review_required",
    "slot_count",
    "missing_slot_count",
    "needs_source_count",
    "needs_confirmation_count",
)

SLOT_TABLE_COLUMNS = [
    "Draft slot",
    "Slot key",
    "Role",
    "Status",
    "Source status",
    "Recorded value",
    "Missing reason",
    "Source IDs",
    "Evidence IDs",
    "Manual review",
]

MISSING_FIELD_COLUMNS = ["Draft slot", "Slot key", "Status", "Missing reason", "Manual review"]
EVIDENCE_SUMMARY_COLUMNS = ["Identifier type", "Count", "Identifiers", "Note"]
REVIEW_ITEM_COLUMNS = ["Review item"]
WARNING_COLUMNS = ["Warning"]


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return [_text(item) for item in _sequence(value) if _text(item)]


def _yes_no(value: Any) -> str:
    return "yes" if value is True else "no" if value is False else "not provided"


def _join_ids(value: Any) -> str:
    return ", ".join(_string_list(value)) or "not provided"


def _summary_rows(summary_card: Mapping[str, Any]) -> dict[str, str]:
    review_counts = _mapping(summary_card.get("review_counts"))
    return {
        "draft_id": _text(summary_card.get("draft_id"), "not provided"),
        "draft_status": _text(summary_card.get("draft_status"), "not provided"),
        "manual_review_required": _yes_no(summary_card.get("manual_review_required")),
        "slot_count": _text(review_counts.get("slot_count"), "0"),
        "missing_slot_count": _text(review_counts.get("missing_slot_count"), "0"),
        "needs_source_count": _text(review_counts.get("needs_source_count"), "0"),
        "needs_confirmation_count": _text(review_counts.get("needs_confirmation_count"), "0"),
    }


def _status_badges(raw_badges: Any) -> list[dict[str, str]]:
    badges: list[dict[str, str]] = []
    for raw_badge in _sequence(raw_badges):
        badge = _mapping(raw_badge)
        if not badge:
            continue
        badges.append(
            {
                "label": _text(badge.get("label"), "Status"),
                "value": _text(badge.get("value"), "not provided"),
                "tone": _text(badge.get("tone"), "neutral"),
            }
        )
    return badges


def _slot_frame(rows: Any) -> pd.DataFrame:
    display_rows: list[dict[str, str]] = []
    for raw_row in _sequence(rows):
        row = _mapping(raw_row)
        if not row:
            continue
        display_rows.append(
            {
                "Draft slot": _text(row.get("display_label"), "Draft slot"),
                "Slot key": _text(row.get("slot_name"), "not provided"),
                "Role": _text(row.get("role"), "draft slot"),
                "Status": _text(row.get("status"), "not provided"),
                "Source status": _text(row.get("safe_status_text"), "manual review required"),
                "Recorded value": _text(row.get("value"), "not provided"),
                "Missing reason": _text(row.get("missing_reason"), "not provided"),
                "Source IDs": _join_ids(row.get("source_ids")),
                "Evidence IDs": _join_ids(row.get("evidence_ids")),
                "Manual review": _yes_no(row.get("manual_review_required")),
            }
        )
    return pd.DataFrame(display_rows, columns=SLOT_TABLE_COLUMNS)


def _missing_fields_frame(rows: Any) -> pd.DataFrame:
    display_rows: list[dict[str, str]] = []
    for raw_row in _sequence(rows):
        row = _mapping(raw_row)
        if not row:
            continue
        display_rows.append(
            {
                "Draft slot": _text(row.get("display_label"), "Draft slot"),
                "Slot key": _text(row.get("slot_name"), "not provided"),
                "Status": _text(row.get("status"), "not provided"),
                "Missing reason": _text(row.get("missing_reason"), "not provided"),
                "Manual review": _yes_no(row.get("manual_review_required")),
            }
        )
    return pd.DataFrame(display_rows, columns=MISSING_FIELD_COLUMNS)


def _evidence_summary_frame(evidence_summary: Mapping[str, Any]) -> pd.DataFrame:
    note = _text(evidence_summary.get("note"), "Identifiers are displayed as supplied.")
    rows = [
        {
            "Identifier type": "Source IDs",
            "Count": _text(evidence_summary.get("source_count"), "0"),
            "Identifiers": _join_ids(evidence_summary.get("source_ids")),
            "Note": note,
        },
        {
            "Identifier type": "Evidence IDs",
            "Count": _text(evidence_summary.get("evidence_count"), "0"),
            "Identifiers": _join_ids(evidence_summary.get("evidence_ids")),
            "Note": note,
        },
    ]
    return pd.DataFrame(rows, columns=EVIDENCE_SUMMARY_COLUMNS)


def _single_column_frame(values: Any, column: str) -> pd.DataFrame:
    rows = [{column: value} for value in _string_list(values)]
    return pd.DataFrame(rows, columns=[column])


def build_plant_construct_draft_preview_section(presenter_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Prepare a deterministic read-only section model from an R333 presenter payload."""
    presenter = _mapping(presenter_payload)
    empty_state = _mapping(presenter.get("empty_state"))
    if not presenter or empty_state.get("is_empty") is True:
        empty = presenter if presenter else presenter_service.build_plant_construct_draft_preview_presenter(None)
        reason = _text(_mapping(empty.get("empty_state")).get("reason"), EMPTY_STATE_COPY)
        return {
            "status": SECTION_STATUS_EMPTY,
            "title": _text(empty.get("page_title"), presenter_service.PAGE_TITLE),
            "subtitle": _text(empty.get("subtitle"), presenter_service.SUBTITLE),
            "help_copy": SECTION_HELP_COPY,
            "summary": _summary_rows(_mapping(empty.get("draft_summary_card"))),
            "status_badges": _status_badges(empty.get("status_badges")),
            "slot_table": _slot_frame([]),
            "evidence_summary": _evidence_summary_frame(_mapping(empty.get("evidence_summary"))),
            "missing_fields": _missing_fields_frame([]),
            "review_items": _single_column_frame([], "Review item"),
            "warnings": _single_column_frame(_mapping(empty.get("warnings_section")).get("warnings") or [reason], "Warning"),
            "boundary_note": _text(_mapping(empty.get("draft_summary_card")).get("safety_boundary"), presenter_service.DEFAULT_BOUNDARY),
            "empty_state": {"is_empty": True, "reason": reason, "manual_review_required": True},
            "read_only": True,
        }

    summary_card = _mapping(presenter.get("draft_summary_card"))
    slot_table = _mapping(presenter.get("slot_table"))
    missing_fields = _mapping(presenter.get("missing_fields_section"))
    review_items = _mapping(presenter.get("review_items_section"))
    warnings = _mapping(presenter.get("warnings_section"))
    empty_state = _mapping(presenter.get("empty_state"))

    return {
        "status": SECTION_STATUS_AVAILABLE,
        "title": _text(presenter.get("page_title"), presenter_service.PAGE_TITLE),
        "subtitle": _text(presenter.get("subtitle"), presenter_service.SUBTITLE),
        "help_copy": SECTION_HELP_COPY,
        "summary": _summary_rows(summary_card),
        "status_badges": _status_badges(presenter.get("status_badges")),
        "slot_table": _slot_frame(slot_table.get("rows")),
        "evidence_summary": _evidence_summary_frame(_mapping(presenter.get("evidence_summary"))),
        "missing_fields": _missing_fields_frame(missing_fields.get("rows")),
        "review_items": _single_column_frame(review_items.get("items"), "Review item"),
        "warnings": _single_column_frame(warnings.get("warnings"), "Warning"),
        "boundary_note": _text(summary_card.get("safety_boundary"), presenter_service.DEFAULT_BOUNDARY),
        "empty_state": {
            "is_empty": bool(empty_state.get("is_empty", False)),
            "reason": _text(empty_state.get("reason")),
            "manual_review_required": empty_state.get("manual_review_required") is not False,
        },
        "read_only": True,
    }


def _render_frame_or_caption(frame: pd.DataFrame, empty_copy: str) -> None:
    if frame.empty:
        st.caption(empty_copy)
        return
    st.dataframe(frame, hide_index=True)


def render_plant_construct_draft_preview_section(presenter_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Render the R334 read-only Streamlit section and return the prepared model for tests."""
    section = build_plant_construct_draft_preview_section(presenter_payload)
    inject_tool_typography_css()
    render_tool_header(section["title"], section["subtitle"])
    render_help_text(section["help_copy"])
    render_boundary_note(section["boundary_note"])

    summary = section["summary"]
    render_compact_summary_cards(
        [
            ("Draft ID", summary["draft_id"], None),
            ("Draft status", summary["draft_status"], None),
            ("Manual review", summary["manual_review_required"], None),
            ("Draft slots", summary["slot_count"], None),
            ("Missing fields", summary["missing_slot_count"], None),
            ("Missing sources", summary["needs_source_count"], None),
            ("Needs confirmation", summary["needs_confirmation_count"], None),
        ]
    )

    if section["empty_state"]["is_empty"]:
        st.info(section["empty_state"]["reason"])

    render_section_heading("Status badges")
    if section["status_badges"]:
        render_compact_summary_cards((badge["label"], badge["value"], badge["tone"]) for badge in section["status_badges"])
    else:
        st.caption("No status badges supplied.")

    render_section_heading("Draft slot table")
    _render_frame_or_caption(section["slot_table"], "No draft slot rows supplied.")

    render_section_heading("Evidence summary")
    _render_frame_or_caption(section["evidence_summary"], "No source or evidence identifiers supplied.")

    render_section_heading("Missing fields")
    _render_frame_or_caption(section["missing_fields"], "No missing fields supplied.")

    render_section_heading("Review items")
    _render_frame_or_caption(section["review_items"], "No review items supplied.")

    render_section_heading("Warnings")
    _render_frame_or_caption(section["warnings"], "No warnings supplied.")

    return section
