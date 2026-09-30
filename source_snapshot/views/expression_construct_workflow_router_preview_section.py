from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import streamlit as st

from services import expression_construct_workflow_router_presenter as presenter_service
from views.tool_typography import (
    inject_tool_typography_css,
    render_boundary_note,
    render_compact_summary_cards,
    render_help_text,
    render_section_heading,
    render_tool_header,
)


SECTION_STATUS_AVAILABLE = "expression_construct_workflow_router_preview_section_available"
SECTION_STATUS_EMPTY = "expression_construct_workflow_router_preview_section_empty"

SECTION_HELP_COPY = (
    "Read-only route readback from the R342 presenter payload. Intent text, route status, "
    "review stages, required slots, missing information, warnings, and boundary notes are displayed as supplied."
)
EMPTY_STATE_COPY = "No readable expression construct workflow router presenter payload is available."

ROUTE_STATUS_KEYS = (
    "route_category",
    "status_label",
    "active_mainline",
    "future_candidate",
    "fallback",
    "confidence_category",
    "manual_review_required",
)

SUMMARY_KEYS = (
    "matched_workflow_route",
    "route_status_label",
    "confidence_category",
    "manual_review_required",
    "required_slot_count",
    "missing_or_unknown_slot_count",
)

REVIEW_STAGE_COLUMNS = ["Review stage", "Review status"]
REQUIRED_SLOT_COLUMNS = ["Required information slot", "Review status"]
MISSING_SLOT_COLUMNS = ["Missing or unknown slot"]
BOUNDARY_NOTE_COLUMNS = ["Boundary note"]
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


def _summary_rows(summary_card: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: _yes_no(summary_card.get(key))
        if key == "manual_review_required"
        else _text(summary_card.get(key), "not provided")
        for key in SUMMARY_KEYS
    }


def _route_status_rows(route_status: Mapping[str, Any]) -> dict[str, str]:
    return {
        key: _yes_no(route_status.get(key))
        if key in {"active_mainline", "future_candidate", "fallback", "manual_review_required"}
        else _text(route_status.get(key), "not provided")
        for key in ROUTE_STATUS_KEYS
    }


def _review_stage_frame(rows: Any, stages: Any) -> pd.DataFrame:
    display_rows: list[dict[str, str]] = []
    for raw_row in _sequence(rows):
        row = _mapping(raw_row)
        if row:
            display_rows.append(
                {
                    "Review stage": _text(row.get("stage"), "not provided"),
                    "Review status": _text(row.get("review_status"), "manual review required"),
                }
            )
    if not display_rows:
        display_rows = [
            {"Review stage": stage, "Review status": "manual review required"}
            for stage in _string_list(stages)
        ]
    return pd.DataFrame(display_rows, columns=REVIEW_STAGE_COLUMNS)


def _required_slot_frame(rows: Any, slots: Any, missing_slots: Any) -> pd.DataFrame:
    display_rows: list[dict[str, str]] = []
    for raw_row in _sequence(rows):
        row = _mapping(raw_row)
        if row:
            display_rows.append(
                {
                    "Required information slot": _text(row.get("slot_key"), "not provided"),
                    "Review status": _text(row.get("review_status"), "manual review required"),
                }
            )
    if not display_rows:
        missing = {slot.casefold() for slot in _string_list(missing_slots)}
        display_rows = [
            {
                "Required information slot": slot,
                "Review status": "missing or unknown" if slot.casefold() in missing else "present in router result",
            }
            for slot in _string_list(slots)
        ]
    return pd.DataFrame(display_rows, columns=REQUIRED_SLOT_COLUMNS)


def _single_column_frame(values: Any, column: str) -> pd.DataFrame:
    rows = [{column: value} for value in _string_list(values)]
    return pd.DataFrame(rows, columns=[column])


def _empty_section(presenter_payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    supplied = _mapping(presenter_payload)
    empty_payload = supplied if supplied else presenter_service.build_expression_construct_workflow_router_presenter(None)
    empty_state = _mapping(empty_payload.get("empty_state"))
    message = _text(empty_state.get("message"), EMPTY_STATE_COPY)
    warnings = _string_list(empty_payload.get("warnings")) or [message]
    summary = _summary_rows(_mapping(empty_payload.get("route_summary_card")))
    status_rows = _route_status_rows(_mapping(empty_payload.get("route_status")))
    boundary_notes = _string_list(empty_payload.get("documentation_only_boundary_notes"))

    return {
        "status": SECTION_STATUS_EMPTY,
        "title": _text(empty_payload.get("page_title"), presenter_service.PAGE_TITLE),
        "subtitle": _text(empty_payload.get("subtitle"), presenter_service.SUBTITLE),
        "help_copy": SECTION_HELP_COPY,
        "summary": summary,
        "route_status": status_rows,
        "matched_intent_text": _text(empty_payload.get("matched_intent_text"), "Intent text was not supplied."),
        "review_stages": _review_stage_frame([], []),
        "required_information_slots": _required_slot_frame([], [], []),
        "missing_or_unknown_slots": _single_column_frame([], "Missing or unknown slot"),
        "safe_next_review_action": _text(
            empty_payload.get("safe_next_review_action"),
            "Collect a readable presenter payload before showing route readback.",
        ),
        "boundary_notes": _single_column_frame(boundary_notes, "Boundary note"),
        "boundary_note": _text(summary.get("boundary_summary"), presenter_service.BASE_BOUNDARY_NOTES[0]),
        "warnings": _single_column_frame(warnings, "Warning"),
        "empty_state": {"is_empty": True, "message": message, "manual_review_required": True},
        "read_only": True,
    }


def build_expression_construct_workflow_router_preview_section(
    presenter_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Prepare a deterministic read-only section model from an R342 presenter payload."""
    payload = _mapping(presenter_payload)
    empty_state = _mapping(payload.get("empty_state"))
    if (
        not payload
        or payload.get("status") != presenter_service.PRESENTER_STATUS_AVAILABLE
        or empty_state.get("is_empty") is True
    ):
        return _empty_section(payload)

    summary_card = _mapping(payload.get("route_summary_card"))
    missing_slots = payload.get("missing_or_unknown_slots")
    summary = _summary_rows(summary_card)

    return {
        "status": SECTION_STATUS_AVAILABLE,
        "title": _text(payload.get("page_title"), presenter_service.PAGE_TITLE),
        "subtitle": _text(payload.get("subtitle"), presenter_service.SUBTITLE),
        "help_copy": SECTION_HELP_COPY,
        "summary": summary,
        "route_status": _route_status_rows(_mapping(payload.get("route_status"))),
        "matched_intent_text": _text(payload.get("matched_intent_text"), "Intent text was not supplied."),
        "review_stages": _review_stage_frame(
            payload.get("suggested_review_stage_rows"),
            payload.get("suggested_review_stages"),
        ),
        "required_information_slots": _required_slot_frame(
            payload.get("required_information_slot_rows"),
            payload.get("required_information_slots"),
            missing_slots,
        ),
        "missing_or_unknown_slots": _single_column_frame(missing_slots, "Missing or unknown slot"),
        "safe_next_review_action": _text(
            payload.get("safe_next_review_action"),
            "Review the route result and record missing information before downstream interpretation.",
        ),
        "boundary_notes": _single_column_frame(payload.get("documentation_only_boundary_notes"), "Boundary note"),
        "boundary_note": _text(summary_card.get("boundary_summary"), presenter_service.BASE_BOUNDARY_NOTES[0]),
        "warnings": _single_column_frame(payload.get("warnings"), "Warning"),
        "empty_state": {
            "is_empty": bool(empty_state.get("is_empty", False)),
            "message": _text(empty_state.get("message")),
            "manual_review_required": empty_state.get("manual_review_required") is not False,
        },
        "read_only": True,
    }


def _render_frame_or_caption(frame: pd.DataFrame, empty_copy: str) -> None:
    if frame.empty:
        st.caption(empty_copy)
        return
    st.dataframe(frame, hide_index=True)


def render_expression_construct_workflow_router_preview_section(
    presenter_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Render the R343 read-only Streamlit section and return the prepared model for tests."""
    section = build_expression_construct_workflow_router_preview_section(presenter_payload)
    inject_tool_typography_css()
    render_tool_header(section["title"], section["subtitle"])
    render_help_text(section["help_copy"])
    render_boundary_note(section["boundary_note"])

    summary = section["summary"]
    render_compact_summary_cards(
        [
            ("Matched route", summary["matched_workflow_route"], None),
            ("Route status", summary["route_status_label"], None),
            ("Confidence", summary["confidence_category"], None),
            ("Manual review", summary["manual_review_required"], None),
            ("Required slots", summary["required_slot_count"], None),
            ("Missing slots", summary["missing_or_unknown_slot_count"], None),
        ]
    )

    if section["empty_state"]["is_empty"]:
        st.info(section["empty_state"]["message"])

    render_section_heading("Route status")
    status = section["route_status"]
    render_compact_summary_cards(
        [
            ("Category", status["route_category"], None),
            ("Status label", status["status_label"], None),
            ("Active mainline", status["active_mainline"], None),
            ("Future candidate", status["future_candidate"], None),
            ("Fallback", status["fallback"], None),
            ("Manual review", status["manual_review_required"], None),
        ]
    )

    render_section_heading("Matched intent")
    st.caption(section["matched_intent_text"])

    render_section_heading("Suggested review stages")
    _render_frame_or_caption(section["review_stages"], "No suggested review stages supplied.")

    render_section_heading("Required information slots")
    _render_frame_or_caption(section["required_information_slots"], "No required information slots supplied.")

    render_section_heading("Missing or unknown slots")
    _render_frame_or_caption(section["missing_or_unknown_slots"], "No missing or unknown slots supplied.")

    render_section_heading("Safe next review action")
    st.info(section["safe_next_review_action"])

    render_section_heading("Documentation-only boundary notes")
    _render_frame_or_caption(section["boundary_notes"], "No boundary notes supplied.")

    render_section_heading("Warnings")
    _render_frame_or_caption(section["warnings"], "No warnings supplied.")

    return section
