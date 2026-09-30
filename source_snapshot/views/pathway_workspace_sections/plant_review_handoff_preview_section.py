from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

import pandas as pd
import streamlit as st

from views.pathway_workspace_sections.responsive_review_tables import render_wrapped_summary_cards

from services.plant_evidence_review_worksheet_presenter import (
    ALL_FOLLOWUP_TYPES_FILTER,
    build_followup_queue_filter_view,
)
from services.rice_albumin_manual_provenance_verification import (
    EXPECTED_RICE_ALBUMIN_RECORD_COUNT,
    MANUAL_PROVENANCE_STATUS_FAIL_CLOSED,
    build_rice_albumin_manual_provenance_readback_rows,
    build_rice_albumin_manual_provenance_verification_payload,
)
from services.rice_albumin_manual_provenance_verification_queue import (
    MANUAL_PROVENANCE_QUEUE_STATUS_FAIL_CLOSED,
    build_rice_albumin_manual_provenance_verification_queue,
)
from services.rice_albumin_seed_review_workflow import build_rice_albumin_seed_review_visible_mount


HANDOFF_PREVIEW_BOUNDARY_COPY = (
    "Read-only handoff preview for documentation-only manual review. It shows review items, missing information, "
    "traceability, and blocked output boundaries without creating files, exporting packages, selecting components, "
    "or judging downstream use."
)

WORKSHEET_BOUNDARY_COPY = (
    "Read-only plant evidence review worksheet mounted from the R118 presenter payload. It shows evidence gaps, "
    "component-slot linkage, provenance placeholders, follow-up review items, and manual-review status as "
    "documentation-only review context."
)

ROUTE_CONSTRUCT_TRACEABILITY_BOUNDARY_COPY = (
    "Read-only route-to-construct traceability readback mounted from the R128 presenter payload. It shows "
    "relationships among intent, route/context, evidence rows, component slots, construct draft slots, and "
    "handoff review items as documentation-only review context."
)

FOLLOWUP_FILTER_LABEL = "Follow-up issue type"
FOLLOWUP_FILTER_ALL_LABEL = "All follow-up types"
FOLLOWUP_GROUP_LABEL = "Group follow-up rows by issue type"
R134_SEED_REVIEW_BOUNDARY_COPY = (
    "Local seed-data review, documentation-only, needs manual review. Provenance gaps remain visible."
)
R144_MANUAL_PROVENANCE_BOUNDARY_COPY = (
    "Rice albumin manual provenance verification readback: local seed data, documentation-only, "
    "needs manual review, source/accession gaps visible, not promoted."
)
R147_MANUAL_PROVENANCE_QUEUE_BOUNDARY_COPY = (
    "Rice albumin provenance verification queue: documentation-only, manual review required, "
    "source/accession gaps visible, no automatic identifier fill, not promoted."
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _status_label(value: Any) -> str:
    return _text(value).replace("_", " ") or "not recorded"


def _readback_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _yes_no(value: Any) -> str:
    return "yes" if value is True else "no"


def _metric_rows(handoff_payload: Mapping[str, Any]) -> list[tuple[str, str]]:
    summary = _mapping(handoff_payload.get("reviewer_summary"))
    return [
        ("Review items", str(summary.get("review_item_count", 0))),
        ("Blocked", "yes" if summary.get("blocked") else "no"),
    ]


def _handoff_status_cards(handoff_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    summary = _mapping(handoff_payload.get("reviewer_summary"))
    return [
        {
            "label": "Handoff status",
            "value": _status_label(handoff_payload.get("handoff_status")),
            "note": "Read-only handoff state from the presenter payload.",
        },
        {
            "label": "Manual review",
            "value": "yes" if handoff_payload.get("manual_review_required") else "no",
            "note": "Human review remains visible before any downstream interpretation.",
        },
        {
            "label": "Status label",
            "value": _status_label(summary.get("status_label")),
            "note": "Displayed as wrapped text so long status values are not clipped.",
        },
    ]


def _reviewer_summary_rows(handoff_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    summary = _mapping(handoff_payload.get("reviewer_summary"))
    categories = _mapping(summary.get("review_item_categories"))
    return [
        {"Field": "Chain status", "Readback": _status_label(summary.get("chain_status"))},
        {"Field": "Status label", "Readback": _status_label(summary.get("status_label"))},
        {"Field": "Manual review", "Readback": "yes" if summary.get("manual_review_required") else "no"},
        {"Field": "Review categories", "Readback": ", ".join(f"{key}: {value}" for key, value in categories.items())},
        {"Field": "Boundary note", "Readback": _text(summary.get("safe_boundary_note"))},
    ]


def _review_item_rows(items: Sequence[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "Item id": _text(item.get("item_id")),
                "Category": _text(item.get("category")),
                "Title": _text(item.get("title")),
                "Severity": _text(item.get("severity")),
                "Slot": _text(item.get("slot_id")),
                "Reason": _text(item.get("reason")),
                "Evidence ids": ", ".join(_text(value) for value in _list(item.get("evidence_ids")) if _text(value)),
                "Component ids": ", ".join(_text(value) for value in _list(item.get("component_ids")) if _text(value)),
            }
        )
    return rows


def _traceability_item_rows(items: Sequence[Any], id_key: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        rows.append(
            {
                "Traceability id": _text(item.get(id_key)),
                "Source": _text(item.get("traceability_source")),
            }
        )
    return rows


def _source_traceability_rows(handoff_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    traceability = _mapping(handoff_payload.get("source_traceability"))
    return [
        {"Field": "Source kind", "Readback": _text(traceability.get("source_kind"))},
        {"Field": "Source schema", "Readback": _text(traceability.get("source_schema_version"))},
        {"Field": "Route traceability items", "Readback": str(len(_list(traceability.get("route_traceability_items"))))},
        {"Field": "Handoff context", "Readback": str(_mapping(traceability.get("handoff_context")))},
    ]


def _blocked_boundary_rows(handoff_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {"Blocked output boundary": f"Blocked output boundary: {_text(item)}"}
        for item in _list(handoff_payload.get("blocked_output_boundaries"))
        if _text(item)
    ]


def _design_slot_completion_rows(handoff_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    readback = _mapping(handoff_payload.get("design_slot_completion_readback"))
    summary = _mapping(readback.get("summary"))
    rows = [
        {"Field": "Completed slots", "Readback": _readback_value(summary.get("completed_slot_count"))},
        {"Field": "Missing slots", "Readback": _readback_value(summary.get("missing_slot_count"))},
        {"Field": "Completion status", "Readback": _status_label(summary.get("completion_status"))},
        {
            "Field": "Manual review",
            "Readback": "yes" if summary.get("manual_review_required") else "not flagged",
        },
        {"Field": "Missing slot keys", "Readback": ", ".join(_text(value) for value in _list(summary.get("missing_slots")))},
    ]
    return [row for row in rows if row["Readback"]]


def _worksheet_section_rows(
    section_payload: Mapping[str, Any],
    display_columns: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    columns = [_text(column) for column in _list(section_payload.get("columns")) if _text(column)]
    if display_columns:
        preferred = [_text(column) for column in display_columns if _text(column)]
        columns = [column for column in preferred if column in columns] + [
            column for column in columns if column not in preferred
        ]
    rows: list[dict[str, Any]] = []
    for row in _list(section_payload.get("rows")):
        if not isinstance(row, Mapping):
            continue
        if columns:
            rows.append({column: row.get(column, "") for column in columns})
        else:
            rows.append(dict(row))
    return rows


def _worksheet_boundary_rows(worksheet: Mapping[str, Any]) -> list[dict[str, str]]:
    boundary = _mapping(worksheet.get("boundary_section"))
    return [
        {"Boundary category": f"Blocked output boundary: {_text(item)}"}
        for item in _list(boundary.get("blocked_output_categories"))
        if _text(item)
    ]


def _worksheet_summary_rows(worksheet: Mapping[str, Any]) -> list[dict[str, str]]:
    summary = _mapping(worksheet.get("summary"))
    fields = (
        ("Overall review state", "overall_review_state"),
        ("Total evidence rows", "total_evidence_rows"),
        ("Linked component slots", "linked_component_slot_count"),
        ("Missing source/provenance", "missing_source_or_provenance_count"),
        ("Weak or unreviewed evidence", "weak_or_unreviewed_evidence_count"),
        ("Manual review required", "manual_review_required_count"),
        ("Blocked boundary categories", "blocked_boundary_category_count"),
    )
    return [
        {"Summary field": label, "Readback": _text(summary.get(key))}
        for label, key in fields
        if key in summary
    ]


def _worksheet_handoff_readback_rows(readback_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    readback = _mapping(readback_payload)
    summary = _mapping(readback.get("summary"))
    followup = _mapping(readback.get("followup_queue_status"))
    type_counts = _mapping(summary.get("followup_queue_type_counts"))
    group_counts = _mapping(followup.get("group_counts"))
    return [
        {
            "Field": "Worksheet status",
            "Readback": _status_label(readback.get("worksheet_status") or "empty_manual_review_required"),
        },
        {
            "Field": "Overall evidence review state",
            "Readback": _status_label(summary.get("overall_review_state") or "evidence incomplete"),
        },
        {
            "Field": "Missing source/provenance",
            "Readback": _readback_value(summary.get("missing_source_or_provenance_count")),
        },
        {
            "Field": "Weak or unreviewed evidence",
            "Readback": _readback_value(summary.get("weak_or_unreviewed_evidence_count")),
        },
        {"Field": "Manual review required", "Readback": _readback_value(summary.get("manual_review_required_count"))},
        {"Field": "Follow-up queue items", "Readback": _readback_value(followup.get("total_count"))},
        {
            "Field": "Follow-up issue types",
            "Readback": ", ".join(f"{key}: {value}" for key, value in type_counts.items()),
        },
        {
            "Field": "R124 filter/group metadata",
            "Readback": (
                f"filter={_text(followup.get('filter_key'))}; "
                f"group_by_type={'yes' if followup.get('group_by_type') else 'no'}; "
                f"groups={group_counts}"
            ),
        },
        {
            "Field": "Blocked boundary categories",
            "Readback": ", ".join(_text(value) for value in _list(readback.get("blocked_output_boundary_categories"))),
        },
        {"Field": "Boundary note", "Readback": _text(readback.get("boundary_note"))},
    ]


def _route_construct_summary_rows(readback_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    readback = _mapping(readback_payload)
    summary = _mapping(readback.get("summary"))
    fields = (
        ("Trace rows", "trace_row_count"),
        ("Evidence links", "evidence_link_count"),
        ("Component-slot links", "component_slot_link_count"),
        ("Construct-slot links", "construct_slot_link_count"),
        ("Construct draft slots", "construct_slot_count"),
        ("Gap or follow-up rows", "gap_or_followup_count"),
        ("Manual review required", "manual_review_required"),
        ("Empty input", "empty_input"),
    )
    return [
        {"Summary field": label, "Readback": _readback_value(summary.get(key))}
        for label, key in fields
        if key in summary
    ]


def _route_construct_boundary_rows(readback_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    boundary = _mapping(_mapping(readback_payload).get("boundary_section"))
    return [
        {"Boundary category": f"Boundary category: {_text(item)}"}
        for item in _list(boundary.get("allowed_output_categories"))
        if _text(item)
    ]


def _manual_evidence_queue_summary_rows(readback_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    readback = _mapping(readback_payload)
    summary = _mapping(readback.get("summary"))
    return [
        {"Field": "Readback status", "Readback": _status_label(readback.get("section_status"))},
        {"Field": "Queue rows", "Readback": _readback_value(summary.get("row_count", 0))},
        {"Field": "Review-needed rows", "Readback": _readback_value(summary.get("review_needed_count", 0))},
        {"Field": "Blocked rows", "Readback": _readback_value(summary.get("blocked_count", 0))},
        {"Field": "Preview-only rows", "Readback": _readback_value(summary.get("preview_only_count", 0))},
        {"Field": "Malformed/empty rows", "Readback": _readback_value(summary.get("malformed_or_empty_count", 0))},
        {"Field": "Boundary note", "Readback": _text(readback.get("boundary_note"))},
    ]


def _manual_evidence_queue_detail_rows(readback_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    readback = _mapping(readback_payload)
    rows: list[dict[str, str]] = []
    for row in _list(readback.get("rows")):
        if not isinstance(row, Mapping):
            continue
        traceability = _mapping(row.get("traceability_readback") or row.get("traceability"))
        rows.append(
            {
                "Queue item": _text(row.get("queue_item_id")),
                "Evidence label": _text(row.get("evidence_label")),
                "Queue state": _status_label(row.get("queue_state")),
                "Primary reason": _text(row.get("primary_reason")),
                "Blocking reasons": "; ".join(_text(value) for value in _list(row.get("visible_blocking_reasons"))),
                "Warnings": "; ".join(_text(value) for value in _list(row.get("visible_warnings"))),
                "Traceability": (
                    f"record={_text(traceability.get('record_id'))}; "
                    f"type={_text(traceability.get('record_type'))}; "
                    f"scope={_text(traceability.get('route_scope'))}"
                ),
            }
        )
    return rows


def _manual_provenance_summary_rows(
    payload: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    summary = _mapping(payload.get("summary"))
    workflow_status = _text(payload.get("workflow_status")) or MANUAL_PROVENANCE_STATUS_FAIL_CLOSED
    represented_count = summary.get("total_records", len(rows))
    expected_count = summary.get("expected_record_count", EXPECTED_RICE_ALBUMIN_RECORD_COUNT)
    not_promoted = summary.get("all_records_do_not_promote")
    if not rows:
        workflow_status = MANUAL_PROVENANCE_STATUS_FAIL_CLOSED
        represented_count = 0
        not_promoted = True
    return [
        {"Field": "Workflow status", "Readback": _status_label(workflow_status)},
        {"Field": "Manual material status", "Readback": _status_label(summary.get("manual_material_status"))},
        {"Field": "Seed records represented", "Readback": _readback_value(represented_count)},
        {"Field": "Expected R131 seed records", "Readback": _readback_value(expected_count)},
        {"Field": "Missing source IDs", "Readback": _readback_value(summary.get("missing_source_id_count", 0))},
        {"Field": "Missing accessions", "Readback": _readback_value(summary.get("missing_accession_count", 0))},
        {"Field": "Manual lookup required", "Readback": _readback_value(summary.get("manual_lookup_required_count", 0))},
        {"Field": "do_not_promote_until_verified", "Readback": _readback_value(summary.get("do_not_promote_count", 0))},
        {"Field": "Records promoted", "Readback": _yes_no(summary.get("any_record_promoted"))},
        {
            "Field": "Source/accession auto-filled",
            "Readback": _yes_no(summary.get("any_source_or_accession_auto_filled")),
        },
        {"Field": "Not promoted", "Readback": _yes_no(not_promoted)},
    ]


def _manual_provenance_queue_payload(queue_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if queue_payload is None:
        return build_rice_albumin_manual_provenance_verification_queue()
    payload = _mapping(queue_payload)
    if isinstance(payload.get("tasks"), Sequence) and not isinstance(
        payload.get("tasks"), (bytes, bytearray, str)
    ):
        return payload
    return build_rice_albumin_manual_provenance_verification_queue(payload)


def _manual_provenance_queue_summary_rows(queue_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    summary = _mapping(queue_payload.get("summary"))
    return [
        {"Field": "Total tasks", "Readback": _readback_value(summary.get("total_tasks", 0))},
        {
            "Field": "Represented records",
            "Readback": _readback_value(summary.get("represented_record_count", 0)),
        },
        {
            "Field": "Records requiring manual lookup",
            "Readback": _readback_value(summary.get("records_requiring_manual_lookup", 0)),
        },
        {
            "Field": "Records blocked from promotion",
            "Readback": _readback_value(summary.get("records_blocked_from_promotion", 0)),
        },
        {
            "Field": "Missing source ID tasks",
            "Readback": _readback_value(summary.get("missing_source_id_count", 0)),
        },
        {
            "Field": "Missing accession tasks",
            "Readback": _readback_value(summary.get("missing_accession_count", 0)),
        },
        {
            "Field": "ready_to_promote_count",
            "Readback": _readback_value(summary.get("ready_to_promote_count", 0)),
        },
    ]


def _manual_provenance_queue_task_type_rows(queue_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    summary = _mapping(queue_payload.get("summary"))
    task_counts = _mapping(summary.get("task_type_counts"))
    tasks = [_mapping(task) for task in _list(queue_payload.get("tasks"))]
    if not task_counts:
        task_counts = Counter(_text(task.get("task_type")) for task in tasks if _text(task.get("task_type")))

    task_types = [_text(task_type) for task_type in _list(queue_payload.get("task_types")) if _text(task_type)]
    ordered_task_types = task_types + [
        _text(task_type)
        for task_type in task_counts
        if _text(task_type) and _text(task_type) not in set(task_types)
    ]
    return [
        {"Task type": task_type, "Task rows": _readback_value(task_counts.get(task_type, 0))}
        for task_type in ordered_task_types
    ]


def _render_table(title: str, rows: list[dict[str, Any]], empty_message: str) -> None:
    st.markdown(f"**{title}**")
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info(empty_message)


def _render_followup_queue_table(worksheet: Mapping[str, Any], *, widget_key_prefix: str) -> None:
    followup_section = _mapping(worksheet.get("followup_queue_section"))
    base_view = build_followup_queue_filter_view(followup_section)
    type_options = [ALL_FOLLOWUP_TYPES_FILTER, *base_view["followup_type_options"]]
    selected_type = st.selectbox(
        FOLLOWUP_FILTER_LABEL,
        type_options,
        format_func=lambda value: FOLLOWUP_FILTER_ALL_LABEL
        if value == ALL_FOLLOWUP_TYPES_FILTER
        else _status_label(value),
        key=f"{widget_key_prefix}_r124_followup_type_filter",
        help="Read-only filter by follow-up issue type.",
    )
    group_by_type = st.checkbox(
        FOLLOWUP_GROUP_LABEL,
        value=True,
        key=f"{widget_key_prefix}_r124_followup_group_by_type",
        help="Read-only grouping for inspection; it does not change the worksheet payload.",
    )
    view = build_followup_queue_filter_view(
        followup_section,
        followup_type=_text(selected_type) or ALL_FOLLOWUP_TYPES_FILTER,
        group_by_type=group_by_type,
    )
    st.caption(
        f"{view['filtered_count']} of {view['total_count']} worksheet follow-up rows shown. {view['boundary_note']}"
    )
    display_columns = (
        "followup_id",
        "followup_type",
        "linked_evidence_id",
        "linked_component",
        "linked_slot",
        "reason",
        "suggested_review_action",
        "review_status",
    )
    if group_by_type and view["grouped_rows"]:
        st.markdown("**Worksheet follow-up queue by issue type**")
        for followup_type, rows in view["grouped_rows"].items():
            st.markdown(f"**{_status_label(followup_type)} ({len(rows)})**")
            st.dataframe(
                pd.DataFrame(_worksheet_section_rows({"columns": display_columns, "rows": rows})),
                use_container_width=True,
                hide_index=True,
            )
        return
    _render_table(
        "Worksheet follow-up queue",
        _worksheet_section_rows({"columns": display_columns, "rows": view["rows"]}),
        _text(view.get("empty_state")) or "No worksheet follow-up queue items are available yet.",
    )


def _render_plant_evidence_review_worksheet(
    worksheet_payload: Mapping[str, Any] | None,
    *,
    widget_key_prefix: str,
) -> None:
    worksheet = _mapping(worksheet_payload)
    summary = _mapping(worksheet.get("summary"))
    st.markdown("**Plant evidence review worksheet**")
    st.caption(WORKSHEET_BOUNDARY_COPY)
    st.caption(_text(worksheet.get("documentation_only_boundary")))

    columns = st.columns(4, gap="small")
    metrics = [
        ("Read-only", "yes" if worksheet.get("read_only", True) else "no"),
        ("Evidence rows", str(summary.get("evidence_row_count", 0))),
        ("Component slots", str(summary.get("component_slot_row_count", 0))),
        ("Follow-up items", str(summary.get("followup_queue_count", 0))),
    ]
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, value)

    for warning in _list(worksheet.get("warnings")):
        if _text(warning):
            st.info(_text(warning))

    _render_table(
        "Worksheet summary rollup",
        _worksheet_summary_rows(worksheet),
        "No worksheet summary rollup is available yet.",
    )
    _render_table(
        "Worksheet route context",
        _worksheet_section_rows(_mapping(worksheet.get("route_context_section"))),
        "No worksheet route context is available yet.",
    )
    _render_table(
        "Worksheet evidence rows",
        _worksheet_section_rows(
            _mapping(worksheet.get("evidence_review_section")),
            (
                "evidence_item_id",
                "evidence_label",
                "linked_component_id",
                "linked_slot_id",
                "source_or_provenance_placeholder",
                "review_status",
                "gap_reason",
                "manual_review_note",
                "row_id",
            ),
        ),
        "No worksheet evidence rows are available yet; manual source/evidence review remains needed.",
    )
    _render_table(
        "Worksheet component-slot linkage",
        _worksheet_section_rows(
            _mapping(worksheet.get("component_slot_linkage_section")),
            (
                "linked_slot_id",
                "linked_component_id",
                "linked_component_label",
                "linked_evidence_ids",
                "source_or_provenance_placeholder",
                "review_status",
                "gap_reason",
                "manual_review_note",
                "row_id",
            ),
        ),
        "No worksheet component-slot linkage rows are available yet; manual component/source review remains needed.",
    )
    _render_table(
        "Worksheet manual-review items",
        _worksheet_section_rows(
            _mapping(worksheet.get("manual_review_section")),
            (
                "item_id",
                "category",
                "severity",
                "linked_slot_id",
                "linked_component_ids",
                "linked_evidence_ids",
                "gap_reason",
                "manual_review_note",
                "row_id",
            ),
        ),
        "No worksheet manual-review items are available yet; keep the handoff in manual review.",
    )
    _render_followup_queue_table(worksheet, widget_key_prefix=widget_key_prefix)
    _render_table(
        "Worksheet blocked-output boundary categories",
        _worksheet_boundary_rows(worksheet),
        "No worksheet blocked-output boundary categories are recorded.",
    )


def _render_route_construct_traceability_readback(readback_payload: Mapping[str, Any] | None) -> None:
    readback = _mapping(readback_payload)
    summary = _mapping(readback.get("summary"))
    boundary = _mapping(readback.get("boundary_section"))
    st.markdown("**Route-to-construct traceability readback**")
    st.caption(ROUTE_CONSTRUCT_TRACEABILITY_BOUNDARY_COPY)
    st.caption(_text(boundary.get("boundary_note")))

    columns = st.columns(4, gap="small")
    metrics = [
        ("Read-only", "yes" if readback.get("read_only", True) else "no"),
        ("Trace rows", str(summary.get("trace_row_count", 0))),
        ("Construct slots", str(summary.get("construct_slot_count", 0))),
        ("Follow-up rows", str(summary.get("gap_or_followup_count", 0))),
    ]
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, value)

    for warning in _list(readback.get("warnings")):
        if _text(warning):
            st.info(_text(warning))

    _render_table(
        "Route-to-construct summary",
        _route_construct_summary_rows(readback),
        "No route-to-construct summary is available yet.",
    )
    _render_table(
        "Route-to-construct intent",
        _worksheet_section_rows(_mapping(readback.get("intent_section"))),
        "No route-to-construct intent rows are available yet.",
    )
    _render_table(
        "Route/context readback",
        _worksheet_section_rows(_mapping(readback.get("route_context_section"))),
        "No route/context rows are available yet.",
    )
    _render_table(
        "Route-to-construct links",
        _worksheet_section_rows(_mapping(readback.get("traceability_section"))),
        "No route-to-construct traceability rows are available yet; keep manual review.",
    )
    _render_table(
        "Construct draft slots",
        _worksheet_section_rows(_mapping(readback.get("construct_slot_section"))),
        "No construct draft slot rows are available yet; keep manual review.",
    )
    _render_table(
        "Handoff review links",
        _worksheet_section_rows(_mapping(readback.get("handoff_review_section"))),
        "No handoff review link rows are available yet.",
    )
    _render_table(
        "Route-to-construct boundary categories",
        _route_construct_boundary_rows(readback),
        "No route-to-construct boundary categories are recorded.",
    )


def _render_r134_seed_summary(mount_payload: Mapping[str, Any]) -> None:
    rows = _list(mount_payload.get("seed_record_rows"))
    rejected_rows = _list(mount_payload.get("rejected_seed_rows"))
    columns = st.columns(4, gap="small")
    metrics = [
        ("Read-only", "yes" if mount_payload.get("read_only", True) else "no"),
        ("Seed rows", str(len(rows))),
        ("Rejected rows", str(len(rejected_rows))),
        ("Manual review", "yes" if mount_payload.get("manual_review_required", True) else "no"),
    ]
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, value)


def render_rice_albumin_seed_review_visible_mount(
    workflow_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    mount_payload = build_rice_albumin_seed_review_visible_mount(workflow_payload)
    st.markdown("**Rice albumin seed review visible mount**")
    st.caption(R134_SEED_REVIEW_BOUNDARY_COPY)
    st.caption(_text(mount_payload.get("documentation_only_boundary")))
    _render_r134_seed_summary(mount_payload)

    for warning in _list(mount_payload.get("warnings")):
        if _text(warning):
            st.info(_text(warning))

    _render_table(
        "Seed review summary",
        _worksheet_section_rows(
            {"columns": ["Field", "Readback"], "rows": _list(mount_payload.get("summary_rows"))}
        ),
        "No seed review summary is available yet.",
    )
    _render_table(
        "Seed record readback",
        _worksheet_section_rows(
            {
                "columns": [
                    "record_id",
                    "record_type",
                    "route_or_context_id",
                    "component_or_context_id",
                    "evidence_ids",
                    "review_status",
                    "provenance_status",
                    "gap_fields",
                    "manual_review_note",
                ],
                "rows": _list(mount_payload.get("seed_record_rows")),
            }
        ),
        _text(mount_payload.get("empty_state")) or "No seed record rows are available yet.",
    )
    _render_table(
        "Rejected seed rows",
        _worksheet_section_rows(
            {
                "columns": [
                    "record_id",
                    "record_type",
                    "source_file",
                    "row_index",
                    "rejection_reason",
                    "review_status",
                    "provenance_status",
                    "manual_review_note",
                ],
                "rows": _list(mount_payload.get("rejected_seed_rows")),
            }
        ),
        "No rejected seed rows are recorded for this local seed-data review.",
    )
    _render_table(
        "Seed handoff readback",
        _worksheet_handoff_readback_rows(
            _mapping(_mapping(mount_payload.get("handoff_readback")).get("evidence_worksheet_handoff_readback"))
        ),
        "No seed evidence worksheet handoff readback is available yet.",
    )
    _render_route_construct_traceability_readback(_mapping(mount_payload.get("route_construct_traceability")))
    _render_plant_evidence_review_worksheet(
        _mapping(mount_payload.get("evidence_worksheet")),
        widget_key_prefix="r134_seed_review",
    )
    st.caption("R134 local seed-data review mount: read-only and documentation-only; manual review remains required.")
    return mount_payload


def render_rice_albumin_manual_provenance_verification_readback(
    provenance_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_payload = (
        build_rice_albumin_manual_provenance_verification_payload()
        if provenance_payload is None
        else _mapping(provenance_payload)
    )
    rows = build_rice_albumin_manual_provenance_readback_rows(source_payload) if source_payload else []

    st.markdown("**Rice albumin manual provenance verification**")
    st.caption(R144_MANUAL_PROVENANCE_BOUNDARY_COPY)
    st.caption(_text(source_payload.get("documentation_only_boundary")))

    summary = _mapping(source_payload.get("summary"))
    columns = st.columns(4, gap="small")
    metrics = [
        ("Read-only", "yes"),
        ("Readback rows", str(len(rows))),
        ("Missing source IDs", str(summary.get("missing_source_id_count", 0))),
        ("Missing accessions", str(summary.get("missing_accession_count", 0))),
    ]
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, value)

    if not rows:
        st.info("No manual provenance rows are available; read-only fail-closed state shown.")
    for warning in _list(source_payload.get("warnings")):
        if _text(warning):
            st.info(_text(warning))

    _render_table(
        "Manual provenance review",
        _manual_provenance_summary_rows(source_payload, rows),
        "No manual provenance summary is available; read-only fail-closed state shown.",
    )
    _render_table(
        "Source/accession gaps",
        _worksheet_section_rows(
            {
                "columns": [
                    "record_id",
                    "record_type",
                    "review_status",
                    "provenance_status",
                    "source_type",
                    "source_id",
                    "missing_source_id",
                    "missing_accession",
                    "review_categories",
                    "manual_action",
                    "do_not_promote_status",
                    "manual_review_note",
                ],
                "rows": rows,
            }
        ),
        "No source/accession gap rows are available; local seed data remains documentation-only and needs manual review.",
    )
    st.caption("R144 manual provenance readback is read-only; no source IDs or accessions are filled here.")
    return {
        "manual_provenance_payload": source_payload,
        "manual_provenance_rows": rows,
        "read_only": True,
    }


def render_rice_albumin_manual_provenance_verification_queue(
    queue_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    source_payload = _manual_provenance_queue_payload(queue_payload)
    tasks = [_mapping(task) for task in _list(source_payload.get("tasks"))]
    summary = _mapping(source_payload.get("summary"))
    workflow_status = _text(source_payload.get("workflow_status")) or MANUAL_PROVENANCE_QUEUE_STATUS_FAIL_CLOSED

    st.markdown("**Rice albumin manual provenance verification queue**")
    st.caption(R147_MANUAL_PROVENANCE_QUEUE_BOUNDARY_COPY)
    st.caption(_text(source_payload.get("queue_boundary")))
    st.caption(_text(source_payload.get("source_policy")))

    columns = st.columns(4, gap="small")
    metrics = [
        ("Total tasks", str(summary.get("total_tasks", len(tasks)))),
        ("Represented records", str(summary.get("represented_record_count", 0))),
        ("Missing source ID tasks", str(summary.get("missing_source_id_count", 0))),
        ("ready_to_promote_count", str(summary.get("ready_to_promote_count", 0))),
    ]
    for column, (label, value) in zip(columns, metrics):
        column.metric(label, value)

    if not tasks or workflow_status == MANUAL_PROVENANCE_QUEUE_STATUS_FAIL_CLOSED:
        st.info("Manual provenance verification queue is in a read-only fail-closed state.")
    for warning in _list(source_payload.get("warnings")):
        if _text(warning):
            st.info(_text(warning))

    _render_table(
        "Manual provenance verification queue summary",
        _manual_provenance_queue_summary_rows(source_payload),
        "No queue summary is available; manual review remains required and records are not promoted.",
    )
    st.caption(
        "Manual verification task rows are summarized by task type first; open the detail table for row-level review."
    )
    _render_table(
        "Manual provenance verification task type summary",
        _manual_provenance_queue_task_type_rows(source_payload),
        "No manual provenance verification task type counts are available; row-level review remains required.",
    )
    with st.expander(f"Show all {len(tasks)} manual provenance task rows", expanded=False):
        _render_table(
            "Manual provenance verification tasks",
            _worksheet_section_rows(
                {
                    "columns": [
                        "task_id",
                        "record_id",
                        "record_type",
                        "task_type",
                        "missing_fields",
                        "verification_question",
                        "blocking_reason",
                        "required_manual_action",
                        "promotion_blocked",
                        "do_not_promote_until_verified",
                    ],
                    "rows": tasks,
                }
            ),
            "No manual provenance verification task rows are available; queue remains read-only and fail-closed.",
        )
    st.caption(
        "R147 queue mount is read-only; it does not fill source IDs, accessions, publication identifiers, "
        "or database IDs."
    )
    return {
        "manual_provenance_queue_payload": source_payload,
        "manual_provenance_queue_tasks": tasks,
        "read_only": True,
    }


def render_plant_review_handoff_preview_section(handoff_payload: Mapping[str, Any] | None) -> None:
    payload = _mapping(handoff_payload)
    st.markdown("**Handoff preview**")
    st.caption(HANDOFF_PREVIEW_BOUNDARY_COPY)
    render_wrapped_summary_cards(st, _handoff_status_cards(payload), class_suffix="bds-handoff-status")

    columns = st.columns(2, gap="small")
    for column, (label, value) in zip(columns, _metric_rows(payload)):
        column.metric(label, value)

    _render_table("Reviewer summary", _reviewer_summary_rows(payload), "No reviewer summary is available yet.")
    with st.expander("Handoff review item detail", expanded=False):
        _render_table(
            "Required review items",
            _review_item_rows(_list(payload.get("required_review_items"))),
            "No required review items are available yet.",
        )
        _render_table(
            "Missing information items",
            _review_item_rows(_list(payload.get("missing_information_items"))),
            "No missing information items are available yet.",
        )
    with st.expander("Design slot completion readback", expanded=False):
        readback = _mapping(payload.get("design_slot_completion_readback"))
        st.caption(
            _text(readback.get("boundary_note"))
            or "Design slot completion is documentation-only manual review readback."
        )
        _render_table(
            "Design slot completion summary",
            _design_slot_completion_rows(payload),
            "No design slot completion summary is available yet.",
        )
    with st.expander("Handoff traceability and boundary detail", expanded=False):
        _render_table(
            "Evidence traceability",
            _traceability_item_rows(_list(payload.get("evidence_traceability_items")), "evidence_id"),
            "No evidence traceability items are available yet.",
        )
        _render_table(
            "Component traceability",
            _traceability_item_rows(_list(payload.get("component_traceability_items")), "component_id"),
            "No component traceability items are available yet.",
        )
        _render_table(
            "Blocked output boundaries",
            _blocked_boundary_rows(payload),
            "No blocked output boundaries are recorded.",
        )
        _render_table("Source traceability", _source_traceability_rows(payload), "No source traceability is available yet.")
    with st.expander("Evidence worksheet and route-to-construct readbacks", expanded=False):
        _render_table(
            "Evidence worksheet handoff readback",
            _worksheet_handoff_readback_rows(_mapping(payload.get("evidence_worksheet_handoff_readback"))),
            "No evidence worksheet handoff readback is available yet.",
        )
        _render_route_construct_traceability_readback(_mapping(payload.get("route_construct_traceability_readback")))
        _render_plant_evidence_review_worksheet(
            _mapping(payload.get("plant_evidence_review_worksheet")),
            widget_key_prefix="handoff_preview",
        )
    with st.expander("Manual evidence queue package readback", expanded=False):
        readback = _mapping(payload.get("manual_evidence_review_queue_readback"))
        st.caption(
            _text(readback.get("boundary_note"))
            or "Manual evidence queue status is preflight/readback only."
        )
        _render_table(
            "Manual evidence queue readback summary",
            _manual_evidence_queue_summary_rows(readback),
            "No manual evidence queue readback summary is available yet.",
        )
        _render_table(
            "Manual evidence queue readback rows",
            _manual_evidence_queue_detail_rows(readback),
            "No manual evidence preflight payload is available for package readback.",
        )
    with st.expander("Rice albumin provenance verification detail", expanded=False):
        render_rice_albumin_manual_provenance_verification_readback()
        render_rice_albumin_manual_provenance_verification_queue()
    st.caption("Manual-review boundary note: this preview is read-only and does not create a handoff file or package.")
