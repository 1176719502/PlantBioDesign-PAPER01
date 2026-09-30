from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from services.component_library_asset_readback_presenter import (
    NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL,
    build_component_library_asset_readback_rows,
)
from services.component_library_contract_crosswalk_presenter import (
    DEFERRED_FIELDS,
    DOCUMENTATION_BOUNDARY_NOTE,
    build_component_library_contract_crosswalk_presenter,
)
from services.project_output_boundary_copy import PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE


FOLLOWUP_QUEUE_TITLE = "Component Library source/provenance follow-up queue"
FOLLOWUP_QUEUE_INTRO = (
    "Read-only source/provenance follow-up rows for existing Component Library and asset-like records."
)
FOLLOWUP_QUEUE_EMPTY_STATE = (
    "No Component Library source/provenance follow-up rows are currently flagged. Existing records may still "
    "need ordinary human review before reuse in project documentation."
)
FOLLOWUP_QUEUE_BOUNDARY_NOTE = (
    "Documentation-only follow-up queue. It surfaces missing source/provenance, evidence/reference, deferred-field, "
    f"and boundary notes for manual review. {PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE} "
    "It does not recommend or select components, forecast outcomes, generate sequences, or judge downstream use."
)

FOLLOWUP_QUEUE_COLUMNS = [
    "Component label",
    "Component ID",
    "Component type",
    "Follow-up type",
    "Follow-up detail",
    "Manual review",
    "Boundary note",
]

RECORDED_REVIEW_ACTION_MARKER = "review recorded source/provenance and record review status"
FOLLOWUP_FILTER_EMPTY_STATE = (
    "No follow-up rows match the current read-only filters. Adjust the filters to review other existing rows."
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _summary_from_component(component: dict[str, Any]) -> dict[str, Any]:
    summary = component.get("component_summary")
    return dict(summary) if isinstance(summary, dict) else {}


def _component_label(component: dict[str, Any]) -> str:
    return _text(_summary_from_component(component).get("component_label"), "Unnamed component record")


def _component_id(component: dict[str, Any]) -> str:
    return _text(_summary_from_component(component).get("component_id"), "Not recorded")


def _component_type(component: dict[str, Any]) -> str:
    return _text(_summary_from_component(component).get("component_type"), "component asset")


def _queue_row(component: dict[str, Any], followup_type: str, detail: str) -> dict[str, str]:
    return {
        "Component label": _component_label(component),
        "Component ID": _component_id(component),
        "Component type": _component_type(component),
        "Follow-up type": followup_type,
        "Follow-up detail": detail,
        "Manual review": "Needs manual review",
        "Boundary note": FOLLOWUP_QUEUE_BOUNDARY_NOTE,
    }


def _source_provenance_missing(component: dict[str, Any]) -> bool:
    missing_fields = _missing_fields(component)
    return "not recorded" in _text(component.get("source_provenance_display_status")).casefold() or any(
        field.casefold().startswith(("source", "provenance")) for field in missing_fields
    )


def _evidence_reference_missing(component: dict[str, Any]) -> bool:
    return "not recorded" in _text(component.get("evidence_reference_display_status")).casefold()


def _missing_fields(component: dict[str, Any]) -> list[str]:
    value = component.get("missing_fields")
    if isinstance(value, (list, tuple, set)):
        return sorted({_text(item) for item in value if _text(item)}, key=str.casefold)
    return []


def _followup_notes(component: dict[str, Any]) -> list[str]:
    value = component.get("follow_up_notes")
    if isinstance(value, (list, tuple, set)):
        return sorted({_text(item) for item in value if _text(item)}, key=str.casefold)
    return []


def _manual_review_note_flagged(note: str) -> bool:
    text = note.casefold()
    return bool(text) and RECORDED_REVIEW_ACTION_MARKER not in text


def _component_rows(component: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if _source_provenance_missing(component):
        rows.append(
            _queue_row(
                component,
                "Missing source/provenance",
                "Source/provenance context is not recorded in the existing readback payload.",
            )
        )
    if _evidence_reference_missing(component):
        rows.append(
            _queue_row(
                component,
                "Missing evidence/reference",
                "Evidence/reference context is not recorded in the existing readback payload.",
            )
        )

    missing_fields = _missing_fields(component)
    if missing_fields:
        rows.append(
            _queue_row(
                component,
                "Needs manual review",
                f"Missing metadata fields: {'; '.join(missing_fields)}.",
            )
        )

    for note in _followup_notes(component):
        if _manual_review_note_flagged(note):
            rows.append(_queue_row(component, "Needs manual review", note))

    if not rows:
        return []

    rows.append(
        _queue_row(
            component,
            "Deferred field",
            f"Deferred contract fields remain display-only in this batch: {'; '.join(DEFERRED_FIELDS)}.",
        )
    )
    rows.append(_queue_row(component, "Boundary note", DOCUMENTATION_BOUNDARY_NOTE))
    return rows


def _asset_readback_rows(
    *,
    local_design_assets: Iterable[dict[str, Any]] | None,
    linked_catalog_assets: Iterable[dict[str, Any]] | None,
    construct_component_rows: Iterable[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    rows = build_component_library_asset_readback_rows(
        local_design_assets=local_design_assets,
        linked_catalog_assets=linked_catalog_assets,
        construct_component_rows=construct_component_rows,
    )
    output: list[dict[str, str]] = []
    for row in rows:
        action = _text(row.get(NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL))
        if not action or RECORDED_REVIEW_ACTION_MARKER in action.casefold():
            continue
        component = {
            "component_summary": {
                "component_label": row.get("Asset label"),
                "component_id": row.get("Source/provenance identity"),
                "component_type": row.get("Asset type"),
            }
        }
        output.append(_queue_row(component, "Needs manual review", action))
    return output


def _summarize(rows: list[dict[str, str]]) -> dict[str, Any]:
    followup_type_counts = Counter(row["Follow-up type"] for row in rows)
    component_type_counts = Counter(row["Component type"] for row in rows)
    component_keys = {
        (
            _text(row.get("Component label")),
            _text(row.get("Component ID")),
            _text(row.get("Component type")),
        )
        for row in rows
        if any(
            _text(row.get(field))
            for field in ("Component label", "Component ID", "Component type")
        )
    }
    summary_rows = [
        {
            "Summary group": "Follow-up type",
            "Group value": label,
            "Rows": count,
        }
        for label, count in sorted(followup_type_counts.items(), key=lambda item: item[0].casefold())
    ]
    summary_rows.extend(
        {
            "Summary group": "Component type",
            "Group value": label,
            "Rows": count,
        }
        for label, count in sorted(component_type_counts.items(), key=lambda item: item[0].casefold())
    )
    return {
        "total_followup_rows": len(rows),
        "components_with_followup": len(component_keys),
        "records_with_followup": len(component_keys),
        "followup_type_counts": dict(sorted(followup_type_counts.items(), key=lambda item: item[0].casefold())),
        "component_type_counts": dict(sorted(component_type_counts.items(), key=lambda item: item[0].casefold())),
        "missing_source_provenance_count": followup_type_counts.get("Missing source/provenance", 0),
        "missing_evidence_reference_count": followup_type_counts.get("Missing evidence/reference", 0),
        "needs_manual_review_count": followup_type_counts.get("Needs manual review", 0),
        "deferred_field_count": followup_type_counts.get("Deferred field", 0),
        "boundary_note_count": followup_type_counts.get("Boundary note", 0),
        "summary_rows": summary_rows,
        "documentation_boundary_note": FOLLOWUP_QUEUE_BOUNDARY_NOTE,
    }


def followup_queue_filter_options(rows: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    row_list = [dict(row) for row in rows or []]
    return {
        "followup_types": sorted(
            {_text(row.get("Follow-up type")) for row in row_list if _text(row.get("Follow-up type"))},
            key=str.casefold,
        ),
        "component_types": sorted(
            {_text(row.get("Component type")) for row in row_list if _text(row.get("Component type"))},
            key=str.casefold,
        ),
    }


def filter_followup_queue_rows(
    rows: Iterable[dict[str, Any]],
    *,
    followup_types: Iterable[str] | None = None,
    component_types: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    selected_followup_types = {_text(value) for value in followup_types or [] if _text(value)}
    selected_component_types = {_text(value) for value in component_types or [] if _text(value)}
    filtered: list[dict[str, Any]] = []
    for row in rows or []:
        row_copy = dict(row)
        if selected_followup_types and _text(row_copy.get("Follow-up type")) not in selected_followup_types:
            continue
        if selected_component_types and _text(row_copy.get("Component type")) not in selected_component_types:
            continue
        filtered.append(row_copy)
    return filtered


def build_component_library_followup_queue_presenter(
    records: Iterable[dict[str, Any]] | None = None,
    *,
    local_design_assets: Iterable[dict[str, Any]] | None = None,
    linked_catalog_assets: Iterable[dict[str, Any]] | None = None,
    construct_component_rows: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build read-only source/provenance follow-up rows from existing Component Library readback payloads."""
    record_list = [dict(record) for record in records or []]
    local_asset_list = [dict(record) for record in local_design_assets or []]
    linked_asset_list = [dict(record) for record in linked_catalog_assets or []]
    construct_row_list = [dict(record) for record in construct_component_rows or []]

    crosswalk = build_component_library_contract_crosswalk_presenter(record_list)
    rows: list[dict[str, str]] = []
    for component in crosswalk["components"]:
        rows.extend(_component_rows(component))
    rows.extend(
        _asset_readback_rows(
            local_design_assets=local_asset_list,
            linked_catalog_assets=linked_asset_list,
            construct_component_rows=construct_row_list,
        )
    )

    return {
        "title": FOLLOWUP_QUEUE_TITLE,
        "intro": FOLLOWUP_QUEUE_INTRO,
        "columns": list(FOLLOWUP_QUEUE_COLUMNS),
        "rows": rows,
        "filter_options": followup_queue_filter_options(rows),
        "filter_empty_state": FOLLOWUP_FILTER_EMPTY_STATE,
        "summary": _summarize(rows),
        "empty_state": FOLLOWUP_QUEUE_EMPTY_STATE,
        "boundary_note": FOLLOWUP_QUEUE_BOUNDARY_NOTE,
    }
