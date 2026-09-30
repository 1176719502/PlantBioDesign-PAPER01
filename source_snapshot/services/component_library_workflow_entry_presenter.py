from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from services.component_library_slot_browse_presenter import SLOT_DEFINITIONS
from services.local_design_asset_catalog_service import asset_type_short_label
from services.placeholder_review_value import has_recorded_review_value, is_placeholder_review_value


WORKFLOW_ENTRY_TITLE = "Find components by workflow slot"
WORKFLOW_ENTRY_INTRO = (
    "Start with plant expression construct slots, source/provenance status, and manual follow-up state. "
    "Full record detail remains available below the first-screen summary."
)
WORKFLOW_ENTRY_BOUNDARY_NOTE = (
    "Documentation-only Component Library entry view. It organizes recorded information for manual review; "
    "it is not a biological recommendation, experiment validation claim, optimization claim, or lab-use decision."
)
WORKFLOW_ENTRY_EMPTY_STATE = (
    "No component records are available for the workflow entry view. Full Component Library sections remain below."
)

ALL_SLOT_FILTER = "All workflow slots"
ALL_TYPE_FILTER = "All component types"
ALL_SOURCE_FILTER = "All source/provenance states"
ALL_FOLLOWUP_FILTER = "All follow-up states"
SOURCE_RECORDED = "Source/provenance recorded"
SOURCE_NEEDS_REVIEW = "Needs source/provenance review"
FOLLOWUP_NEEDED = "Needs manual review"
FOLLOWUP_NOT_FLAGGED = "No follow-up flagged"
UNMAPPED_SLOT = "Unmapped component context"

WORKFLOW_ENTRY_COLUMNS = [
    "Slot",
    "Component label",
    "Component type",
    "Record ID",
    "Source/provenance status",
    "Follow-up status",
    "Review status",
    "Source/provenance detail",
    "Short description",
    "Documentation boundary",
]

_TYPE_TO_SLOT_LABEL = {
    str(asset_type).casefold(): str(slot["slot_label"])
    for slot in SLOT_DEFINITIONS
    for asset_type in slot.get("asset_types", ())
}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _display_name(record: dict[str, Any]) -> str:
    return _text(
        record.get("display_name")
        or record.get("asset_display_name")
        or record.get("asset_label")
        or record.get("name")
        or record.get("asset_id")
        or record.get("record_id"),
        "Unnamed component record",
    )


def _record_id(record: dict[str, Any]) -> str:
    return _text(record.get("asset_id") or record.get("record_id") or record.get("id"), "Not recorded")


def _asset_type(record: dict[str, Any]) -> str:
    raw_type = _text(record.get("asset_type") or record.get("component_type") or record.get("type"))
    return asset_type_short_label(raw_type) if raw_type else "component record"


def _slot_label(record: dict[str, Any]) -> str:
    explicit = _text(record.get("slot_label") or record.get("slot"))
    if explicit:
        return explicit
    raw_type = _text(record.get("asset_type") or record.get("component_type") or record.get("type")).casefold()
    return _TYPE_TO_SLOT_LABEL.get(raw_type, UNMAPPED_SLOT)


def _source_detail(record: dict[str, Any]) -> str:
    return _text(
        record.get("source_notes")
        or record.get("source_reference")
        or record.get("source_label")
        or record.get("source_context")
        or record.get("provenance_status"),
        "Source/provenance detail not recorded",
    )


def _source_needs_review(record: dict[str, Any]) -> bool:
    provenance_status = _text(record.get("provenance_status") or record.get("source_provenance_status"))
    detail = _source_detail(record)
    combined = f"{provenance_status} {detail}".casefold()
    return (
        not has_recorded_review_value(detail)
        or is_placeholder_review_value(detail)
        or "source review needed" in combined
        or "source/provenance detail not recorded" in combined
        or "source not recorded" in combined
        or "missing source" in combined
    )


def _source_status(record: dict[str, Any]) -> str:
    return SOURCE_NEEDS_REVIEW if _source_needs_review(record) else SOURCE_RECORDED


def _followup_needed(record: dict[str, Any]) -> bool:
    review_status = _text(record.get("review_status") or record.get("record_review_status"))
    review_note = _text(record.get("human_review_notes") or record.get("review_note"))
    combined = f"{review_status} {review_note}".casefold()
    return (
        _source_needs_review(record)
        or not has_recorded_review_value(review_status)
        or is_placeholder_review_value(review_status)
        or "human review needed" in combined
        or "manual review" in combined
        or "review required" in combined
        or "source_review_required" in combined
        or "construct_review_required" in combined
    )


def _followup_status(record: dict[str, Any]) -> str:
    return FOLLOWUP_NEEDED if _followup_needed(record) else FOLLOWUP_NOT_FLAGGED


def _review_status(record: dict[str, Any]) -> str:
    return _text(record.get("review_status") or record.get("record_review_status"), "Not recorded")


def _short_description(record: dict[str, Any]) -> str:
    return _text(record.get("short_description") or record.get("description"), "No description recorded")


def _boundary_note(record: dict[str, Any]) -> str:
    return _text(record.get("documentation_boundary_note"), WORKFLOW_ENTRY_BOUNDARY_NOTE)


def build_component_library_workflow_entry_rows(
    records: Iterable[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in records or []:
        record_copy = dict(record)
        rows.append(
            {
                "Slot": _slot_label(record_copy),
                "Component label": _display_name(record_copy),
                "Component type": _asset_type(record_copy),
                "Record ID": _record_id(record_copy),
                "Source/provenance status": _source_status(record_copy),
                "Follow-up status": _followup_status(record_copy),
                "Review status": _review_status(record_copy),
                "Source/provenance detail": _source_detail(record_copy),
                "Short description": _short_description(record_copy),
                "Documentation boundary": _boundary_note(record_copy),
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["Follow-up status"] != FOLLOWUP_NEEDED,
            row["Slot"].casefold(),
            row["Component label"].casefold(),
        ),
    )


def filter_component_library_workflow_entry_rows(
    rows: Iterable[dict[str, Any]],
    *,
    slot: str = ALL_SLOT_FILTER,
    component_type: str = ALL_TYPE_FILTER,
    source_status: str = ALL_SOURCE_FILTER,
    followup_status: str = ALL_FOLLOWUP_FILTER,
) -> list[dict[str, str]]:
    filtered: list[dict[str, str]] = []
    for row in rows or []:
        row_copy = {str(key): _text(value) for key, value in dict(row).items()}
        if slot != ALL_SLOT_FILTER and row_copy.get("Slot") != slot:
            continue
        if component_type != ALL_TYPE_FILTER and row_copy.get("Component type") != component_type:
            continue
        if source_status != ALL_SOURCE_FILTER and row_copy.get("Source/provenance status") != source_status:
            continue
        if followup_status != ALL_FOLLOWUP_FILTER and row_copy.get("Follow-up status") != followup_status:
            continue
        filtered.append(row_copy)
    return filtered


def _filter_options(rows: list[dict[str, str]]) -> dict[str, list[str]]:
    return {
        "slots": sorted({row["Slot"] for row in rows if row["Slot"]}, key=str.casefold),
        "component_types": sorted({row["Component type"] for row in rows if row["Component type"]}, key=str.casefold),
        "source_statuses": [SOURCE_NEEDS_REVIEW, SOURCE_RECORDED],
        "followup_statuses": [FOLLOWUP_NEEDED, FOLLOWUP_NOT_FLAGGED],
    }


def _slot_groups(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    slot_counts = Counter(row["Slot"] for row in rows)
    source_counts = Counter(row["Slot"] for row in rows if row["Source/provenance status"] == SOURCE_NEEDS_REVIEW)
    followup_counts = Counter(row["Slot"] for row in rows if row["Follow-up status"] == FOLLOWUP_NEEDED)
    return [
        {
            "Slot": slot,
            "Record count": str(count),
            "Source/provenance review": str(source_counts.get(slot, 0)),
            "Manual review": str(followup_counts.get(slot, 0)),
        }
        for slot, count in sorted(slot_counts.items(), key=lambda item: item[0].casefold())
    ]


def summarize_component_library_workflow_entry_rows(
    rows: Iterable[dict[str, Any]],
    *,
    saved_registry_record_count: int = 0,
) -> dict[str, int]:
    row_list = [dict(row) for row in rows or []]
    source_review_count = sum(1 for row in row_list if row.get("Source/provenance status") == SOURCE_NEEDS_REVIEW)
    followup_count = sum(1 for row in row_list if row.get("Follow-up status") == FOLLOWUP_NEEDED)
    return {
        "total_records": len(row_list) + max(int(saved_registry_record_count), 0),
        "workflow_records": len(row_list),
        "saved_registry_records": max(int(saved_registry_record_count), 0),
        "records_with_source_provenance": len(row_list) - source_review_count,
        "records_needing_source_provenance_review": source_review_count,
        "records_needing_manual_review": followup_count,
        "slot_group_count": len({str(row.get("Slot") or "") for row in row_list if str(row.get("Slot") or "")}),
    }


def build_component_library_workflow_entry_presenter(
    records: Iterable[dict[str, Any]] | None,
    *,
    saved_registry_record_count: int = 0,
    slot: str = ALL_SLOT_FILTER,
    component_type: str = ALL_TYPE_FILTER,
    source_status: str = ALL_SOURCE_FILTER,
    followup_status: str = ALL_FOLLOWUP_FILTER,
    card_limit: int = 8,
) -> dict[str, Any]:
    rows = build_component_library_workflow_entry_rows(records)
    filtered_rows = filter_component_library_workflow_entry_rows(
        rows,
        slot=slot,
        component_type=component_type,
        source_status=source_status,
        followup_status=followup_status,
    )
    summary = summarize_component_library_workflow_entry_rows(
        rows,
        saved_registry_record_count=saved_registry_record_count,
    )
    summary["filtered_records"] = len(filtered_rows)
    return {
        "title": WORKFLOW_ENTRY_TITLE,
        "intro": WORKFLOW_ENTRY_INTRO,
        "boundary_note": WORKFLOW_ENTRY_BOUNDARY_NOTE,
        "empty_state": WORKFLOW_ENTRY_EMPTY_STATE,
        "columns": list(WORKFLOW_ENTRY_COLUMNS),
        "rows": rows,
        "filtered_rows": filtered_rows,
        "cards": filtered_rows[: max(int(card_limit), 1)],
        "slot_groups": _slot_groups(rows),
        "filter_options": _filter_options(rows),
        "summary": summary,
        "selected_filters": {
            "slot": slot,
            "component_type": component_type,
            "source_status": source_status,
            "followup_status": followup_status,
        },
    }
