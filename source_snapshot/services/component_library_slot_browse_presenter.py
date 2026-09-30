from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from services.component_library_asset_readback_presenter import (
    DOCUMENTATION_BOUNDARY_NOTE,
    NO_SOURCE_PROVENANCE_IDENTITY,
    build_component_library_asset_readback_rows,
)
from services.placeholder_review_value import has_recorded_review_value, is_placeholder_review_value


SLOT_BROWSE_TITLE = "Component records by plant expression construct context"
SLOT_BROWSE_INTRO = (
    "Browse existing Component Library records by plant-expression-construct context, with source/provenance "
    "and manual follow-up readback shown for documentation-only review."
)
SLOT_BROWSE_BOUNDARY_NOTE = (
    "Slot browse is documentation-only readback. It groups existing records for review; it does not choose "
    "components, rank biological fit, assemble vectors, rewrite sequences, provide procedure steps, predict "
    "outcomes, validate plant lines, certify construct readiness, or judge wet-lab use."
)
SLOT_BROWSE_EMPTY_STATE = (
    "No component records are available yet. Add or open component records before using Component Library "
    "for plant expression construct review."
)
SOURCE_PROVENANCE_MISSING_STATUS = "Source/provenance missing - manual follow-up needed."
SOURCE_PROVENANCE_PRESENT_STATUS = "Source/provenance present for documentation review."
MANUAL_FOLLOW_UP_NEEDED = "Manual follow-up needed."
NO_SLOT_RECORDS_STATUS = "No usable records in this slot yet."
NO_SLOT_RECORDS_ACTION = "Manual follow-up needed before this slot can be cited in documentation."
NO_SLOT_RECORDS_NOTE = "No existing Component Library records mapped to this slot in the current readback."


SLOT_COLUMNS = [
    "Slot",
    "Record count",
    "Records",
    "Source/provenance status",
    "Manual follow-up",
    "Readback note",
    "Documentation boundary",
]

SLOT_DEFINITIONS = [
    {
        "slot_key": "promoter",
        "slot_label": "Plant promoter context",
        "asset_types": ("promoter", "plant_promoter_profile"),
    },
    {
        "slot_key": "rbs_kozak_utr",
        "slot_label": "RBS / Kozak / UTR",
        "asset_types": ("rbs_5utr", "rbs", "kozak", "5' utr", "5utr"),
    },
    {
        "slot_key": "cds_insert",
        "slot_label": "CDS / Insert",
        "asset_types": ("cds_target", "cds_gene", "cds", "coding sequence", "gene", "insert"),
    },
    {
        "slot_key": "signal_peptide",
        "slot_label": "Signal peptide",
        "asset_types": ("signal_peptide", "signal", "secretion_leader"),
    },
    {
        "slot_key": "transit_peptide",
        "slot_label": "Transit peptide",
        "asset_types": ("transit_peptide", "transit", "chloroplast_transit_peptide", "mitochondrial_transit_peptide"),
    },
    {
        "slot_key": "subcellular_targeting",
        "slot_label": "Subcellular targeting",
        "asset_types": ("subcellular_targeting", "targeting_signal", "organelle_targeting", "compartment_targeting"),
    },
    {
        "slot_key": "fusion_tag_linker",
        "slot_label": "Fusion Tag / Linker",
        "asset_types": ("tag", "fusion_tag", "linker", "tag_linker"),
    },
    {
        "slot_key": "terminator_polya",
        "slot_label": "Terminator context",
        "asset_types": ("terminator", "polya", "poly_a"),
    },
    {
        "slot_key": "selectable_marker_reporter",
        "slot_label": "Selectable Marker / Reporter",
        "asset_types": ("marker_metadata", "marker", "selectable_marker", "reporter"),
    },
    {
        "slot_key": "vector_backbone",
        "slot_label": "Vector / backbone context",
        "asset_types": ("plasmid_backbone", "vector_backbone", "backbone", "vector", "origin_metadata"),
    },
    {
        "slot_key": "host_expression_context",
        "slot_label": "Plant species / host context",
        "asset_types": ("host_chassis_context_note", "host", "host_context", "expression_host"),
    },
    {
        "slot_key": "tissue_organ_expression_compartment",
        "slot_label": "Tissue / organ / expression compartment",
        "asset_types": ("tissue_context", "organ_context", "expression_compartment", "expression_tissue", "plant_tissue"),
    },
    {
        "slot_key": "expression_mode",
        "slot_label": "Expression mode",
        "asset_types": ("expression_mode", "transient_expression", "stable_expression", "inducible_expression"),
    },
    {
        "slot_key": "source_provenance",
        "slot_label": "Source / Provenance",
        "asset_types": ("literature_source_note", "source_reference", "origin_metadata", "component_source"),
    },
    {
        "slot_key": "manual_follow_up",
        "slot_label": "Manual Follow-up",
        "asset_types": (),
        "manual_follow_up": True,
    },
]

SLOT_LABELS = [str(slot["slot_label"]) for slot in SLOT_DEFINITIONS]
_TYPE_TO_SLOT_KEY = {
    str(asset_type).casefold(): str(slot["slot_key"])
    for slot in SLOT_DEFINITIONS
    for asset_type in slot.get("asset_types", ())
}
_SLOT_BY_KEY = {str(slot["slot_key"]): slot for slot in SLOT_DEFINITIONS}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _record_asset_type(record: dict[str, Any]) -> str:
    return _text(record.get("asset_type") or record.get("Asset type")).casefold()


def _record_label(record: dict[str, Any]) -> str:
    return _text(
        record.get("display_name")
        or record.get("asset_display_name")
        or record.get("asset_label")
        or record.get("Asset label")
        or record.get("asset_id")
        or record.get("record_id"),
        "Unnamed component record",
    )


def _slot_key_for_record(record: dict[str, Any]) -> str:
    explicit = _text(record.get("slot_key") or record.get("slot")).casefold()
    if explicit in _SLOT_BY_KEY:
        return explicit
    return _TYPE_TO_SLOT_KEY.get(_record_asset_type(record), "")


def _source_identity_from_record(record: dict[str, Any]) -> str:
    readback_rows = build_component_library_asset_readback_rows(local_design_assets=[record])
    if readback_rows:
        return _text(readback_rows[0].get("Source/provenance identity"), NO_SOURCE_PROVENANCE_IDENTITY)
    return NO_SOURCE_PROVENANCE_IDENTITY


def _review_status_from_record(record: dict[str, Any]) -> str:
    readback_rows = build_component_library_asset_readback_rows(local_design_assets=[record])
    if readback_rows:
        return _text(readback_rows[0].get("Record review status"), "Not recorded")
    return "Not recorded"


def _source_missing(source_identity: Any) -> bool:
    text = _text(source_identity).casefold()
    return (
        not has_recorded_review_value(source_identity)
        or is_placeholder_review_value(text)
        or "missing" in text
        or "no source" in text
        or "not recorded" in text
        or text == NO_SOURCE_PROVENANCE_IDENTITY.casefold()
    )


def _record_source_missing(record: dict[str, Any]) -> bool:
    provenance_status = _text(record.get("provenance_status") or record.get("source_provenance_status"))
    provenance_status_text = provenance_status.casefold()
    source_note = _text(
        record.get("source_notes")
        or record.get("source_reference")
        or record.get("source_record_label")
        or record.get("Source/provenance identity")
    )
    return (
        not has_recorded_review_value(provenance_status)
        or is_placeholder_review_value(provenance_status)
        or "source review needed" in provenance_status_text
        or "source status not recorded" in provenance_status_text
        or "source not recorded" in provenance_status_text
        or "missing source" in provenance_status_text
        or _source_missing(_source_identity_from_record(record))
        or (not has_recorded_review_value(source_note) and not _text(record.get("asset_id") or record.get("record_id")))
    )


def _review_needs_follow_up(review_status: Any) -> bool:
    text = _text(review_status).casefold()
    return (
        not has_recorded_review_value(review_status)
        or is_placeholder_review_value(text)
        or "human review needed" in text
        or "review needed" in text
        or "source review needed" in text
        or "not recorded" in text
        or "missing" in text
    )


def _record_follow_up_needed(record: dict[str, Any]) -> bool:
    return _record_source_missing(record) or _review_needs_follow_up(_review_status_from_record(record))


def _record_source_status(records: list[dict[str, Any]]) -> str:
    if not records:
        return NO_SLOT_RECORDS_STATUS
    missing_count = sum(1 for record in records if _record_source_missing(record))
    if missing_count:
        return f"{SOURCE_PROVENANCE_MISSING_STATUS} Missing in {missing_count} of {len(records)} record(s)."
    return SOURCE_PROVENANCE_PRESENT_STATUS


def _record_manual_follow_up(records: list[dict[str, Any]]) -> str:
    if not records:
        return NO_SLOT_RECORDS_ACTION
    follow_up_count = sum(1 for record in records if _record_follow_up_needed(record))
    if follow_up_count:
        return f"{MANUAL_FOLLOW_UP_NEEDED} {follow_up_count} of {len(records)} record(s) need source/provenance or review-status follow-up."
    return "No manual follow-up flagged by this readback."


def _record_summary(records: list[dict[str, Any]], *, limit: int = 4) -> str:
    if not records:
        return "No records shown for this slot."
    labels = [_record_label(record) for record in records[:limit]]
    overflow = len(records) - len(labels)
    summary = "; ".join(labels)
    if overflow > 0:
        summary += f"; +{overflow} more"
    return summary


def _slot_note(records: list[dict[str, Any]]) -> str:
    if not records:
        return NO_SLOT_RECORDS_NOTE
    source_needed = sum(1 for record in records if _record_source_missing(record))
    review_needed = sum(1 for record in records if _review_needs_follow_up(_review_status_from_record(record)))
    return (
        f"Read-only slot group with {len(records)} existing record(s); "
        f"source/provenance follow-up: {source_needed}; review follow-up: {review_needed}."
    )


def _manual_follow_up_records(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(record) for record in records if _record_follow_up_needed(dict(record))]


def build_component_library_slot_browse_rows(
    records: Iterable[dict[str, Any]] | None,
    *,
    selected_slot_label: str = "",
) -> list[dict[str, str]]:
    record_list = [dict(record) for record in records or []]
    if not record_list:
        return []

    grouped: dict[str, list[dict[str, Any]]] = {str(slot["slot_key"]): [] for slot in SLOT_DEFINITIONS}
    for record in record_list:
        slot_key = _slot_key_for_record(record)
        if slot_key in grouped:
            grouped[slot_key].append(record)
        if _record_follow_up_needed(record):
            grouped["manual_follow_up"].append(record)

    rows: list[dict[str, str]] = []
    selected = _text(selected_slot_label)
    for slot in SLOT_DEFINITIONS:
        slot_label = str(slot["slot_label"])
        if selected and selected not in {
            "All expression vector slots",
            "All plant expression construct contexts",
        } and selected != slot_label:
            continue
        slot_records = sorted(grouped[str(slot["slot_key"])], key=lambda item: _record_label(item).casefold())
        rows.append(
            {
                "Slot": slot_label,
                "Record count": str(len(slot_records)),
                "Records": _record_summary(slot_records),
                "Source/provenance status": _record_source_status(slot_records),
                "Manual follow-up": _record_manual_follow_up(slot_records),
                "Readback note": _slot_note(slot_records),
                "Documentation boundary": DOCUMENTATION_BOUNDARY_NOTE,
            }
        )
    return rows


def summarize_component_library_slot_browse(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    row_list = [dict(row) for row in rows]
    counts = Counter(_text(row.get("Slot"), "Unmapped") for row in row_list)
    slot_rows_with_records = sum(1 for row in row_list if int(_text(row.get("Record count"), "0") or 0) > 0)
    source_follow_up_rows = sum(
        1
        for row in row_list
        if SOURCE_PROVENANCE_MISSING_STATUS.casefold() in _text(row.get("Source/provenance status")).casefold()
    )
    manual_follow_up_rows = sum(
        1
        for row in row_list
        if MANUAL_FOLLOW_UP_NEEDED.casefold() in _text(row.get("Manual follow-up")).casefold()
    )
    return {
        "slot_row_count": len(row_list),
        "slot_rows_with_records": slot_rows_with_records,
        "slot_counts": dict(sorted(counts.items(), key=lambda item: item[0].casefold())),
        "source_follow_up_slot_count": source_follow_up_rows,
        "manual_follow_up_slot_count": manual_follow_up_rows,
    }


def build_component_library_slot_browse_presenter(
    records: Iterable[dict[str, Any]] | None,
    *,
    selected_slot_label: str = "",
) -> dict[str, Any]:
    rows = build_component_library_slot_browse_rows(records, selected_slot_label=selected_slot_label)
    return {
        "title": SLOT_BROWSE_TITLE,
        "intro": SLOT_BROWSE_INTRO,
        "boundary_note": SLOT_BROWSE_BOUNDARY_NOTE,
        "empty_state": SLOT_BROWSE_EMPTY_STATE,
        "slot_labels": list(SLOT_LABELS),
        "columns": list(SLOT_COLUMNS),
        "rows": rows,
        "summary": summarize_component_library_slot_browse(rows),
    }
