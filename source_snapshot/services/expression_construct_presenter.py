from __future__ import annotations

from collections import Counter
from typing import Any

from services import expression_construct_repository as repo
from services.expression_wizard_step2_component_context_presenter import (
    build_step2_component_library_context,
)
from services.placeholder_review_value import has_recorded_review_value, is_placeholder_review_value


BOUNDARY_COPY = "Documentation-only construct workspace context for review and traceability."
WORKFLOW_COPY = (
    "This page manages construct/plasmid documentation records made of expression cassettes, cassette parts, "
    "linked genes, pathway links, and source-record references."
)
NO_SOURCE_LABEL = "No source reference recorded"
NO_PROVENANCE_LABEL = "No provenance note recorded"
NO_PART_LABEL = "No part label recorded"
NO_GENE_LABEL = "No linked gene label recorded"
NO_PATHWAY_STEP_LABEL = "No linked pathway step label recorded"
NO_PROJECT_LINK_LABEL = "No project link label recorded"
NO_PROJECT_LINK_NOTE_LABEL = "No project link note recorded"
DEFAULT_CONSTRUCT_LABEL = "Untitled construct draft"
DEFAULT_CONSTRUCT_TYPE = "documentation-only construct draft"
DEFAULT_CASSETTE_LABEL = "Untitled cassette draft"
DEFAULT_CASSETTE_TYPE = "documentation-only cassette draft"
NO_REVIEW_STATUS_LABEL = "No curation status recorded"
NO_REVIEW_NOTE_LABEL = "No review note recorded"
NO_SOURCE_CATALOG_LABEL = "No source catalog recorded"
NO_SOURCE_RECORD_LABEL = "No source record linked"
PROMOTER_SOURCE_LINK_EMPTY_COPY = (
    "Manual promoter rows can be documented without Component Library promoter asset references."
)
NO_EVIDENCE_CONTEXT_LABEL = "No promoter evidence context recorded"
PLANT_PROMOTER_CATALOG_LABEL = "Plant Promoter Catalog"
NO_COMPONENT_CATEGORY_LABEL = "other documented component"
NO_COMPONENT_REFERENCE_LABEL = "No component reference recorded"
SEQUENCE_STATUS_LINKED_REFERENCE = "Sequence availability recorded through linked source/reference context"
SEQUENCE_STATUS_NOT_RECORDED = "Sequence availability not recorded in this documentation view"
SEQUENCE_STATUS_NOT_DISPLAYED = "Sequence not displayed in this documentation review surface"
COMPONENT_METADATA_GAP_STATUS = "Review gap remains visible for documentation review"
COMPONENT_METADATA_RECORDED_STATUS = "Source/reference and record review status recorded for documentation review"
NO_CONSERVATION_EVIDENCE_LABEL = "No conservation review evidence recorded"
CONSERVATION_REVIEW_CONTEXT_RECORDED_STATUS = (
    "Conservation-related source/evidence context recorded for manual documentation review"
)
CONSERVATION_REVIEW_NEEDED_STATUS = "Needs conservation check"
CONSERVATION_REVIEW_ISSUE_TYPE = "Needs conservation check"
CONSERVATION_REVIEW_FOLLOW_UP_NOTE = (
    "Manual documentation follow-up: record source organism/source context, sequence source, literature or database "
    "evidence, conservation note, or reviewer note for conservation review."
)
CONSERVATION_REVIEW_BOUNDARY_NOTE = (
    "Manual conservation review only; records source/evidence context and review gaps without BLAST, MSA, "
    "conserved-domain analysis, conservation classification, component selection, expression outcome estimates, "
    "guarantees of success, or wet-lab use judgment."
)
COMPONENT_ROLE_REVIEW_ISSUE_TYPE = "Review component role documentation"
DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE = "Review duplicate component label"
SUPPORTED_COMPONENT_VOCABULARY = (
    "promoter",
    "5' UTR",
    "RBS",
    "signal peptide",
    "coding sequence",
    "terminator",
    "other documented component",
)
TABLE_COLUMNS = [
    "Construct label",
    "Construct type",
    "Organism / species context",
    "Curation status",
    "Source / provenance",
    "Review note",
]
CASSETTE_COLUMNS = [
    "Cassette label",
    "Construct label / construct id",
    "Cassette order",
    "Cassette type",
    "Curation status",
    "Review note",
]
PART_COLUMNS = [
    "Cassette label / cassette id",
    "Part order",
    "Part role",
    "Part label",
    "Promoter asset source record",
    "Promoter evidence context",
    "Source / provenance",
    "Review note",
]
GENE_COLUMNS = [
    "Gene label",
    "Gene reference",
    "Construct label / construct id",
    "Source / provenance",
    "Review note",
]
PATHWAY_COLUMNS = [
    "Pathway project / step reference",
    "Step label",
    "Construct label / construct id",
    "Link note",
    "Review note",
]
PROJECT_LINK_COLUMNS = [
    "Project id",
    "Construct label / construct id",
    "Link label",
    "Link note",
    "Source context",
    "Curation status",
    "Review note",
]
COMPONENT_COLUMNS = [
    "Component label",
    "Component category",
    "Cassette label",
    "Source/reference context",
    "Sequence availability note",
    "Conservation review evidence",
    "Conservation follow-up cue",
    "Record review status",
    "Review note",
]
COMPONENT_GAP_QUEUE_COLUMNS = [
    "Construct label",
    "Cassette label",
    "Component label",
    "Component category",
    "Issue type",
    "Issue detail",
    "Manual follow-up note",
]
STEP2_COMPONENT_CONTEXT_COLUMNS = [
    "Step 2 context category",
    "Step 2 recorded value",
    "Component Library asset",
    "Recorded Component Library context",
    "Source/provenance review",
    "Record review status",
    "Sequence metadata",
    "Manual follow-up",
]
COMPONENT_REVIEW_SUMMARY_LABELS = {
    "total_component_rows": "Component rows reviewed",
    "rows_with_source_reference_context": "Source/reference context",
    "rows_missing_source_reference_context": "Missing source/reference context",
    "rows_with_sequence_availability_note": "Sequence availability note",
    "rows_with_conservation_review_context": "Conservation review context",
    "rows_needing_conservation_follow_up": "Conservation follow-up",
    "rows_with_review_metadata_status": "Record review status",
    "rows_with_review_note": "Review note context",
    "rows_needing_manual_follow_up": "Documentation follow-up",
}
GAP_COLUMNS = ["Gap type", "Label", "Review gap note"]
PROJECT_REVIEW_QUEUE_BOUNDARY_NOTES = [
    "Expression construct documentation follow-up is read-only project review context.",
    "It summarizes documented component rows and manual documentation gaps only.",
    "It does not rank, recommend, validate, optimize, or judge downstream-use state.",
]
STEP2_CONTEXT_READBACK_TITLE = "Step 2 recorded Component Library context"
STEP2_CONTEXT_READBACK_COPY = (
    "Read-only review context bridged from the current Expression Wizard Step 2 Component Library presenter. "
    "It supports source/provenance review, record review status, sequence metadata review, and manual follow-up only."
)
STEP2_CONTEXT_EMPTY_STATE = "No Step 2 Component Library context is available for this construct yet."
STEP2_CONTEXT_BOUNDARY_NOTE = (
    "Step 2 Component Library context is read-only review context. It is not saved as construct source of truth, "
    "not a biological recommendation, not validation, not outcome-improvement guidance, and not a wet-lab readiness judgment."
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _row_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _review_gap_row(kind: str, label: str, note: str) -> dict[str, str]:
    return {
        "Gap type": kind,
        "Label": label,
        "Review gap note": note,
    }


def _has_missing_provenance(row: dict[str, Any]) -> bool:
    return (
        not has_recorded_review_value(row.get("source_reference"))
        or not has_recorded_review_value(row.get("provenance_note"))
    )


def _component_category_label(part_role: Any) -> str:
    role = _text(part_role).lower()
    return {
        "promoter": "promoter",
        "5'utr": "5' UTR",
        "rbs": "RBS",
        "signal": "signal peptide",
        "signal peptide": "signal peptide",
        "signal_peptide": "signal peptide",
        "cds": "coding sequence",
        "terminator": "terminator",
        "other": NO_COMPONENT_CATEGORY_LABEL,
    }.get(role, NO_COMPONENT_CATEGORY_LABEL)


def _component_sequence_status(row: dict[str, Any]) -> str:
    if has_recorded_review_value(row.get("sequence_availability_status")):
        return _text(row.get("sequence_availability_status"))
    if has_recorded_review_value(row.get("source_record_id")) or (
        has_recorded_review_value(row.get("part_reference"))
        and _text(row.get("part_reference")) != NO_COMPONENT_REFERENCE_LABEL
    ):
        return SEQUENCE_STATUS_LINKED_REFERENCE
    if has_recorded_review_value(row.get("source_reference")) and _text(row.get("source_reference")) != NO_SOURCE_LABEL:
        return SEQUENCE_STATUS_NOT_DISPLAYED
    return SEQUENCE_STATUS_NOT_RECORDED


def _component_review_status(row: dict[str, Any]) -> str:
    source_reference = _text(row.get("source_reference"))
    provenance_note = _text(row.get("provenance_note"))
    if (
        is_placeholder_review_value(source_reference)
        or source_reference == NO_SOURCE_LABEL
        or is_placeholder_review_value(provenance_note)
        or provenance_note == NO_PROVENANCE_LABEL
    ):
        return COMPONENT_METADATA_GAP_STATUS
    return COMPONENT_METADATA_RECORDED_STATUS


def _component_conservation_review_evidence(row: dict[str, Any]) -> str:
    context_items = []
    source_record_label = _text(row.get("source_record_label"))
    source_catalog = _text(row.get("source_catalog"))
    evidence_note = _text(row.get("evidence_context_note"))
    source_reference = _text(row.get("source_reference"))
    part_reference = _text(row.get("part_reference"))
    provenance_note = _text(row.get("provenance_note"))

    if source_catalog and source_catalog != NO_SOURCE_CATALOG_LABEL:
        context_items.append(f"source catalog: {source_catalog}")
    if source_record_label and source_record_label != NO_SOURCE_RECORD_LABEL:
        context_items.append(f"sequence/source record: {source_record_label}")
    if source_reference and source_reference != NO_SOURCE_LABEL:
        context_items.append(f"source context: {source_reference}")
    if part_reference and part_reference != NO_COMPONENT_REFERENCE_LABEL:
        context_items.append(f"component reference: {part_reference}")
    if evidence_note and evidence_note != NO_EVIDENCE_CONTEXT_LABEL:
        context_items.append(f"literature/database or conservation note: {evidence_note}")
    if provenance_note and provenance_note != NO_PROVENANCE_LABEL:
        context_items.append(f"manual reviewer note: {provenance_note}")

    return "; ".join(context_items) if context_items else NO_CONSERVATION_EVIDENCE_LABEL


def _component_conservation_follow_up_cue(row: dict[str, Any]) -> str:
    evidence = _component_conservation_review_evidence(row)
    if evidence == NO_CONSERVATION_EVIDENCE_LABEL:
        return CONSERVATION_REVIEW_NEEDED_STATUS
    return CONSERVATION_REVIEW_CONTEXT_RECORDED_STATUS


def _build_construct_component_rows(cassette_part_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    component_rows: list[dict[str, str]] = []
    for row in cassette_part_rows:
        component_rows.append(
            {
                "construct_id": _text(row.get("construct_id")),
                "construct_label": _text(row.get("construct_label"), DEFAULT_CONSTRUCT_LABEL),
                "component_label": _text(row.get("part_label"), NO_PART_LABEL),
                "component_category": _component_category_label(row.get("part_role")),
                "component_reference_label": _text(row.get("source_record_label"))
                if _text(row.get("source_record_label")) not in ("", NO_SOURCE_RECORD_LABEL)
                else _text(row.get("part_reference"), NO_COMPONENT_REFERENCE_LABEL),
                "sequence_availability_status": _component_sequence_status(row),
                "conservation_review_evidence": _component_conservation_review_evidence(row),
                "conservation_follow_up_cue": _component_conservation_follow_up_cue(row),
                "review_metadata_status": _component_review_status(row),
                "review_note": _text(row.get("provenance_note"), NO_PROVENANCE_LABEL),
                "cassette_label": _text(row.get("cassette_label"), DEFAULT_CASSETTE_LABEL),
            }
        )
    return component_rows


def _component_has_source_reference_context(row: dict[str, Any]) -> bool:
    return any(
        has_recorded_review_value(row.get(key))
        and _text(row.get(key)) not in (NO_SOURCE_LABEL, NO_SOURCE_RECORD_LABEL, NO_COMPONENT_REFERENCE_LABEL)
        for key in ("source_record_id", "source_record_label", "part_reference", "source_reference")
    )


def _component_gap_queue_key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        _text(row.get("construct_label"), DEFAULT_CONSTRUCT_LABEL),
        _text(row.get("cassette_label"), DEFAULT_CASSETTE_LABEL),
        _text(row.get("part_label"), NO_PART_LABEL),
        _component_category_label(row.get("part_role")),
    )


def _component_gap_queue_row(row: dict[str, Any], issue_type: str, issue_detail: str, follow_up_note: str) -> dict[str, str]:
    construct_label, cassette_label, component_label, component_category = _component_gap_queue_key(row)
    return {
        "Construct label": construct_label,
        "Cassette label": cassette_label,
        "Component label": component_label,
        "Component category": component_category,
        "Issue type": issue_type,
        "Issue detail": issue_detail,
        "Manual follow-up note": follow_up_note,
    }


def _component_role_needs_documentation_review(row: dict[str, Any]) -> bool:
    role = _text(row.get("part_role")).lower()
    return role in ("", "other") or _component_category_label(row.get("part_role")) == NO_COMPONENT_CATEGORY_LABEL


def _duplicate_component_label_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _text(row.get("construct_id")),
        _text(row.get("cassette_id")),
        _text(row.get("part_label"), NO_PART_LABEL).casefold(),
    )


def _duplicate_component_label_queue_rows(cassette_part_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    grouped_rows: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in cassette_part_rows:
        grouped_rows.setdefault(_duplicate_component_label_key(row), []).append(row)

    duplicate_rows: list[dict[str, str]] = []
    for rows in grouped_rows.values():
        if len(rows) < 2:
            continue
        first = rows[0]
        construct_label = _text(first.get("construct_label"), DEFAULT_CONSTRUCT_LABEL)
        cassette_label = _text(first.get("cassette_label"), DEFAULT_CASSETTE_LABEL)
        component_label = _text(first.get("part_label"), NO_PART_LABEL)
        categories = sorted({_component_category_label(row.get("part_role")) for row in rows}, key=str.casefold)
        component_category = categories[0] if len(categories) == 1 else "multiple documented component categories"
        duplicate_rows.append(
            {
                "Construct label": construct_label,
                "Cassette label": cassette_label,
                "Component label": component_label,
                "Component category": component_category,
                "Issue type": DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE,
                "Issue detail": (
                    "The same visible component label appears more than once in this construct/cassette "
                    "documentation context."
                ),
                "Manual follow-up note": (
                    "Manual documentation follow-up: review duplicate component labels for traceability clarity."
                ),
            }
        )
    return sorted(
        duplicate_rows,
        key=lambda row: (
            _text(row.get("Construct label")).casefold(),
            _text(row.get("Cassette label")).casefold(),
            _text(row.get("Component label")).casefold(),
            _text(row.get("Component category")).casefold(),
        ),
    )


def _build_construct_component_gap_queue(cassette_part_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    gap_rows: list[dict[str, str]] = []
    for row in cassette_part_rows:
        if not _component_has_source_reference_context(row):
            gap_rows.append(
                _component_gap_queue_row(
                    row,
                    "Missing source/reference context",
                    "No source record, component reference, or source note is recorded for this component row.",
                    "Add documentation source or reference context before using this row in project review documentation.",
                )
            )
        if (
            not has_recorded_review_value(row.get("provenance_note"))
            or _text(row.get("provenance_note")) == NO_PROVENANCE_LABEL
        ):
            gap_rows.append(
                _component_gap_queue_row(
                    row,
                    "Missing provenance context",
                    "No provenance or review note is recorded for this component row.",
                    "Add a manual provenance or review note for documentation traceability.",
                )
            )
        if _component_sequence_status(row) == SEQUENCE_STATUS_NOT_RECORDED:
            gap_rows.append(
                _component_gap_queue_row(
                    row,
                    "Missing sequence availability note",
                    "No sequence availability note is recorded in this documentation view.",
                    "Record whether sequence availability context is documented, if that information is known.",
                )
            )
        if _component_conservation_review_evidence(row) == NO_CONSERVATION_EVIDENCE_LABEL:
            gap_rows.append(
                _component_gap_queue_row(
                    row,
                    CONSERVATION_REVIEW_ISSUE_TYPE,
                    (
                        "No source organism/source context, sequence source, literature or database evidence, "
                        "conservation note, or reviewer note is recorded for conservation review."
                    ),
                    CONSERVATION_REVIEW_FOLLOW_UP_NOTE,
                )
            )
        if _component_role_needs_documentation_review(row):
            gap_rows.append(
                _component_gap_queue_row(
                    row,
                    COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
                    "Component role is missing or recorded as other documented component in this documentation view.",
                    "Manual documentation follow-up: review the component role label for traceability clarity.",
                )
            )
    gap_rows.extend(_duplicate_component_label_queue_rows(cassette_part_rows))
    return gap_rows


def build_construct_component_review_summary(
    component_rows: list[dict[str, Any]],
    gap_queue_rows: list[dict[str, Any]],
) -> dict[str, int]:
    """Summarize component review rows without adding persistence or biological judgments."""
    total_rows = len(component_rows)
    missing_source_keys = {
        (
            _text(row.get("Construct label"), DEFAULT_CONSTRUCT_LABEL),
            _text(row.get("Cassette label"), DEFAULT_CASSETTE_LABEL),
            _text(row.get("Component label"), NO_PART_LABEL),
            _text(row.get("Component category"), NO_COMPONENT_CATEGORY_LABEL),
        )
        for row in gap_queue_rows
        if _text(row.get("Issue type")) == "Missing source/reference context"
    }
    source_context_count = max(total_rows - len(missing_source_keys), 0)
    sequence_note_count = sum(
        1
        for row in component_rows
        if has_recorded_review_value(row.get("sequence_availability_status"))
        and _text(row.get("sequence_availability_status")) != SEQUENCE_STATUS_NOT_RECORDED
    )
    conservation_context_count = sum(
        1
        for row in component_rows
        if has_recorded_review_value(row.get("conservation_review_evidence"))
        and _text(row.get("conservation_review_evidence")) != NO_CONSERVATION_EVIDENCE_LABEL
    )
    conservation_follow_up_keys = {
        (
            _text(row.get("Construct label"), DEFAULT_CONSTRUCT_LABEL),
            _text(row.get("Cassette label"), DEFAULT_CASSETTE_LABEL),
            _text(row.get("Component label"), NO_PART_LABEL),
            _text(row.get("Component category"), NO_COMPONENT_CATEGORY_LABEL),
        )
        for row in gap_queue_rows
        if _text(row.get("Issue type")) == CONSERVATION_REVIEW_ISSUE_TYPE
    }
    metadata_status_count = sum(
        1 for row in component_rows if has_recorded_review_value(row.get("review_metadata_status"))
    )
    review_note_count = sum(
        1
        for row in component_rows
        if has_recorded_review_value(row.get("review_note"))
        and _text(row.get("review_note")) not in (NO_REVIEW_NOTE_LABEL, NO_PROVENANCE_LABEL)
    )
    follow_up_keys = {
        (
            _text(row.get("Construct label"), DEFAULT_CONSTRUCT_LABEL),
            _text(row.get("Cassette label"), DEFAULT_CASSETTE_LABEL),
            _text(row.get("Component label"), NO_PART_LABEL),
            _text(row.get("Component category"), NO_COMPONENT_CATEGORY_LABEL),
        )
        for row in gap_queue_rows
    }
    return {
        "total_component_rows": total_rows,
        "rows_with_source_reference_context": source_context_count,
        "rows_missing_source_reference_context": len(missing_source_keys),
        "rows_with_sequence_availability_note": sequence_note_count,
        "rows_with_conservation_review_context": conservation_context_count,
        "rows_needing_conservation_follow_up": len(conservation_follow_up_keys),
        "rows_with_review_metadata_status": metadata_status_count,
        "rows_with_review_note": review_note_count,
        "rows_needing_manual_follow_up": len(follow_up_keys),
    }


def construct_type_options(rows: list[dict[str, Any]]) -> list[str]:
    values = sorted({_text(row.get("construct_type")) for row in rows if _text(row.get("construct_type"))}, key=str.casefold)
    return ["all"] + values


def construct_status_options(rows: list[dict[str, Any]]) -> list[str]:
    values = sorted({_text(row.get("review_status")) for row in rows if _text(row.get("review_status"))}, key=str.casefold)
    return ["all"] + values


def cassette_label_options(rows: list[dict[str, Any]]) -> list[str]:
    values = sorted({_text(row.get("cassette_label"), DEFAULT_CASSETTE_LABEL) for row in rows}, key=str.casefold)
    return ["all"] + values


def pathway_reference_options(rows: list[dict[str, Any]]) -> list[str]:
    values = sorted({_text(row.get("pathway_step_id"), "No pathway step reference recorded") for row in rows}, key=str.casefold)
    return ["all"] + values


def filter_expression_construct_display_rows(
    profile_rows: list[dict[str, Any]],
    cassette_rows: list[dict[str, Any]],
    part_rows: list[dict[str, Any]],
    gene_rows: list[dict[str, Any]],
    pathway_rows: list[dict[str, Any]],
    review_gap_rows: list[dict[str, Any]],
    *,
    construct_type: str,
    construct_status: str,
    cassette_label: str,
    pathway_ref: str,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    if construct_type != "all":
        profile_rows = [row for row in profile_rows if _text(row.get("construct_type")) == construct_type]
    if construct_status != "all":
        profile_rows = [row for row in profile_rows if _text(row.get("review_status")) == construct_status]

    construct_ids = {_text(row.get("construct_id")) for row in profile_rows if _text(row.get("construct_id"))}
    if construct_ids:
        cassette_rows = [row for row in cassette_rows if _text(row.get("construct_id")) in construct_ids]
        gene_rows = [row for row in gene_rows if _text(row.get("construct_id")) in construct_ids]
        pathway_rows = [row for row in pathway_rows if _text(row.get("construct_id")) in construct_ids]
    else:
        cassette_rows = []
        gene_rows = []
        pathway_rows = []

    cassette_ids = {_text(row.get("cassette_id")) for row in cassette_rows if _text(row.get("cassette_id"))}
    if cassette_label != "all":
        cassette_rows = [row for row in cassette_rows if _text(row.get("cassette_label")) == cassette_label]
        cassette_ids = {_text(row.get("cassette_id")) for row in cassette_rows if _text(row.get("cassette_id"))}
    part_rows = [row for row in part_rows if _text(row.get("cassette_id")) in cassette_ids] if cassette_ids else []

    if pathway_ref != "all":
        pathway_rows = [row for row in pathway_rows if pathway_ref == _text(row.get("pathway_step_id"))]

    if construct_ids and not profile_rows:
        review_gap_rows = []

    return profile_rows, cassette_rows, part_rows, gene_rows, pathway_rows, review_gap_rows


def construct_profile_table_rows(profile_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Construct label": _text(row.get("construct_label"), DEFAULT_CONSTRUCT_LABEL),
            "Construct type": _text(row.get("construct_type"), DEFAULT_CONSTRUCT_TYPE),
            "Organism / species context": _text(row.get("host_context_note"), "No organism or species context recorded"),
            "Curation status": _text(row.get("review_status"), NO_REVIEW_STATUS_LABEL),
            "Source / provenance": " / ".join(
                [
                    _text(row.get("source_reference"), NO_SOURCE_LABEL),
                    _text(row.get("provenance_note"), NO_PROVENANCE_LABEL),
                ]
            ),
            "Review note": _text(row.get("documentation_scope_note"), NO_REVIEW_NOTE_LABEL),
        }
        for row in profile_rows
    ]


def cassette_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Cassette label": _text(row.get("cassette_label"), DEFAULT_CASSETTE_LABEL),
            "Construct label / construct id": _text(row.get("construct_id"), "Unknown construct id"),
            "Cassette order": str(row.get("cassette_order", 0)),
            "Cassette type": _text(row.get("cassette_role"), DEFAULT_CASSETTE_TYPE),
            "Curation status": _text(row.get("source_reference"), NO_REVIEW_STATUS_LABEL),
            "Review note": _text(row.get("provenance_note"), NO_REVIEW_NOTE_LABEL),
        }
        for row in rows
    ]


def cassette_part_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Cassette label / cassette id": " / ".join(
                [
                    _text(row.get("cassette_label"), DEFAULT_CASSETTE_LABEL),
                    _text(row.get("cassette_id"), "Unknown cassette id"),
                ]
            ),
            "Part order": str(row.get("part_order", 0)),
            "Part role": _text(row.get("part_role"), "other"),
            "Part label": _text(row.get("part_label"), NO_PART_LABEL),
            "Promoter source record": " / ".join(
                value
                for value in [
                    _text(row.get("source_catalog")),
                    _text(row.get("source_record_label")),
                    _text(row.get("source_record_id")),
                ]
                if value
            )
            or NO_SOURCE_RECORD_LABEL,
            "Promoter evidence context": _text(row.get("evidence_context_note"), NO_EVIDENCE_CONTEXT_LABEL),
            "Source / provenance": " / ".join(
                [
                    _text(row.get("source_reference"), NO_SOURCE_LABEL),
                    _text(row.get("provenance_note"), NO_PROVENANCE_LABEL),
                ]
            ),
            "Review note": _text(row.get("provenance_note"), NO_REVIEW_NOTE_LABEL),
        }
        for row in rows
    ]


def construct_component_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Component label": _text(row.get("component_label"), NO_PART_LABEL),
            "Component category": _text(row.get("component_category"), NO_COMPONENT_CATEGORY_LABEL),
            "Cassette label": _text(row.get("cassette_label"), DEFAULT_CASSETTE_LABEL),
            "Source/reference context": _text(row.get("component_reference_label"), NO_COMPONENT_REFERENCE_LABEL),
            "Sequence availability note": _text(
                row.get("sequence_availability_status"),
                SEQUENCE_STATUS_NOT_RECORDED,
            ),
            "Conservation review evidence": _text(
                row.get("conservation_review_evidence"),
                NO_CONSERVATION_EVIDENCE_LABEL,
            ),
            "Conservation follow-up cue": _text(
                row.get("conservation_follow_up_cue"),
                CONSERVATION_REVIEW_NEEDED_STATUS,
            ),
            "Record review status": _text(row.get("review_metadata_status"), COMPONENT_METADATA_GAP_STATUS),
            "Review note": _text(row.get("review_note"), NO_REVIEW_NOTE_LABEL),
        }
        for row in rows
    ]


def construct_component_gap_queue_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Construct label": _text(row.get("Construct label"), DEFAULT_CONSTRUCT_LABEL),
            "Cassette label": _text(row.get("Cassette label"), DEFAULT_CASSETTE_LABEL),
            "Component label": _text(row.get("Component label"), NO_PART_LABEL),
            "Component category": _text(row.get("Component category"), NO_COMPONENT_CATEGORY_LABEL),
            "Issue type": _text(row.get("Issue type"), "Documentation context needs review"),
            "Issue detail": _text(row.get("Issue detail"), "No issue detail recorded"),
            "Manual follow-up note": _text(row.get("Manual follow-up note"), "Manual documentation follow-up needed"),
        }
        for row in rows
    ]


def build_step2_component_context_readback(
    *,
    host: str = "",
    tag: str = "",
    rules: dict[str, Any] | None = None,
    elements: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Bridge Wizard Step 2 Component Library context into read-only construct readback."""
    if not _text(host):
        return {
            "title": STEP2_CONTEXT_READBACK_TITLE,
            "subtitle": STEP2_CONTEXT_READBACK_COPY,
            "rows": [],
            "summary": {
                "total_rows": 0,
                "rows_with_recorded_assets": 0,
                "manual_follow_up_rows": 0,
            },
            "empty_state": STEP2_CONTEXT_EMPTY_STATE,
            "documentation_boundary_note": STEP2_CONTEXT_BOUNDARY_NOTE,
        }

    context = build_step2_component_library_context(
        host=host,
        tag=tag,
        rules=_dict_or_empty(rules),
        elements=_dict_or_empty(elements),
        records=records,
    )
    rows = _row_list(context.get("rows"))
    rows_with_assets = [row for row in rows if _text(row.get("asset_id"))]
    if not rows_with_assets:
        rows = []

    return {
        "title": STEP2_CONTEXT_READBACK_TITLE,
        "subtitle": STEP2_CONTEXT_READBACK_COPY,
        "rows": rows,
        "summary": {
            "total_rows": len(rows),
            "rows_with_recorded_assets": len(rows_with_assets),
            "manual_follow_up_rows": sum(1 for row in rows if _text(row.get("context_state")) == "manual follow-up"),
        },
        "empty_state": STEP2_CONTEXT_EMPTY_STATE,
        "documentation_boundary_note": STEP2_CONTEXT_BOUNDARY_NOTE,
    }


def step2_component_context_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Step 2 context category": _text(row.get("category"), "Step 2 Component Library context"),
            "Step 2 recorded value": _text(row.get("step2_value"), "No Step 2 value recorded"),
            "Component Library asset": " / ".join(
                value
                for value in [
                    _text(row.get("asset_label"), "No recorded Component Library context"),
                    _text(row.get("asset_id")),
                ]
                if value
            ),
            "Recorded Component Library context": _text(
                row.get("recorded_context"),
                "recorded context not provided",
            ),
            "Source/provenance review": _text(row.get("source_provenance_review"), "manual follow-up"),
            "Record review status": _text(row.get("record_review_status"), "manual follow-up"),
            "Sequence metadata": _text(row.get("sequence_metadata"), "metadata not recorded"),
            "Manual follow-up": _text(
                row.get("manual_follow_up"),
                "Manual follow-up is required in the existing review surface.",
            ),
        }
        for row in rows
    ]


def build_project_construct_component_review_queue(project_id: str | int | None = None) -> dict[str, Any]:
    """Aggregate R173 component review output for project-level read-only dashboard use."""
    views = build_expression_construct_report_views(project_id=project_id)
    component_rows: list[dict[str, Any]] = []
    gap_queue_rows: list[dict[str, Any]] = []
    construct_count = 0
    for view in views:
        construct_count += len(_row_list(view.get("construct_profile_rows"))) or 1
        component_rows.extend(_row_list(view.get("construct_component_rows")))
        gap_queue_rows.extend(_row_list(view.get("construct_component_gap_queue")))

    summary = build_construct_component_review_summary(component_rows, gap_queue_rows)
    summary["construct_count"] = construct_count
    return {
        "status": "AVAILABLE" if component_rows or gap_queue_rows else "NOT_AVAILABLE",
        "section_title": "Expression construct documentation follow-up",
        "summary": summary,
        "rows": construct_component_gap_queue_table_rows(gap_queue_rows),
        "total_rows_available": len(gap_queue_rows),
        "boundary_notes": list(PROJECT_REVIEW_QUEUE_BOUNDARY_NOTES),
        "empty_state_message": (
            "No Expression Construct component documentation follow-up items are currently visible for this project."
        ),
        "caption": (
            "Review full construct, cassette, component, source/reference, provenance, and review-note readback "
            "in Expression Constructs."
        ),
    }


def linked_gene_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Gene label": _text(row.get("gene_label"), NO_GENE_LABEL),
            "Gene reference": _text(row.get("gene_reference"), "No gene reference recorded"),
            "Construct label / construct id": _text(row.get("construct_id"), "Unknown construct id"),
            "Source / provenance": " / ".join(
                [
                    _text(row.get("source_reference"), NO_SOURCE_LABEL),
                    _text(row.get("provenance_note"), NO_PROVENANCE_LABEL),
                ]
            ),
            "Review note": _text(row.get("provenance_note"), NO_REVIEW_NOTE_LABEL),
        }
        for row in rows
    ]


def linked_pathway_step_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Pathway project / step reference": _text(row.get("pathway_step_id"), "No pathway step reference recorded"),
            "Step label": _text(row.get("pathway_step_label"), NO_PATHWAY_STEP_LABEL),
            "Construct label / construct id": _text(row.get("construct_id"), "Unknown construct id"),
            "Link note": _text(row.get("source_reference"), NO_SOURCE_LABEL),
            "Review note": _text(row.get("provenance_note"), NO_REVIEW_NOTE_LABEL),
        }
        for row in rows
    ]


def project_link_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Project id": _text(row.get("project_id"), "No project id recorded"),
            "Construct label / construct id": " / ".join(
                [
                    _text(row.get("construct_label"), DEFAULT_CONSTRUCT_LABEL),
                    _text(row.get("construct_id"), "Unknown construct id"),
                ]
            ),
            "Link label": _text(row.get("link_label"), NO_PROJECT_LINK_LABEL),
            "Link note": _text(row.get("link_note"), NO_PROJECT_LINK_NOTE_LABEL),
            "Source context": _text(row.get("source_context"), NO_SOURCE_LABEL),
            "Curation status": _text(row.get("curation_status"), NO_REVIEW_STATUS_LABEL),
            "Review note": _text(row.get("review_note"), NO_REVIEW_NOTE_LABEL),
        }
        for row in rows
    ]


def review_gap_table_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "Gap type": _text(row.get("Gap type"), "Unknown gap"),
            "Label": _text(row.get("Label"), "Unknown label"),
            "Review gap note": _text(row.get("Review gap note"), "No review gap note recorded"),
        }
        for row in rows
    ]


def build_expression_construct_presenter(
    construct_id: str | None = None,
    project_id: str | int | None = None,
    step2_component_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    construct_id = _text(construct_id)
    project_id = _text(project_id)
    profiles = repo.list_construct_profiles_for_project(project_id) if project_id else repo.list_construct_profiles()
    profile = repo.get_construct_profile(construct_id) if construct_id else {}
    cassettes = repo.list_construct_cassettes(construct_id) if construct_id else []
    gene_links = repo.list_construct_gene_links(construct_id) if construct_id else []
    pathway_links = repo.list_construct_pathway_step_links(construct_id) if construct_id else []
    if construct_id and project_id:
        project_links = repo.list_construct_project_links(project_id=project_id, construct_id=construct_id)
    elif construct_id:
        project_links = repo.list_construct_project_links(construct_id=construct_id)
    elif project_id:
        project_links = repo.list_construct_project_links(project_id=project_id)
    else:
        project_links = []

    cassette_part_rows: list[dict[str, Any]] = []
    review_gap_rows: list[dict[str, str]] = []
    part_counter = Counter()
    profile_label = _text(profile.get("construct_label"), DEFAULT_CONSTRUCT_LABEL) if profile else (
        _text(construct_id) or DEFAULT_CONSTRUCT_LABEL
    )

    for cassette in cassettes:
        cassette_id = _text(cassette.get("cassette_id"))
        parts = repo.list_construct_cassette_parts(cassette_id)
        if not parts:
            review_gap_rows.append(
                _review_gap_row(
                    "cassette parts",
                    _text(cassette.get("cassette_label"), cassette_id),
                    "No ordered part rows recorded.",
                )
            )
        for part in parts:
            part_role = _text(part.get("part_role"), "other")
            part_counter[part_role] += 1
            if _has_missing_provenance(part):
                review_gap_rows.append(
                    _review_gap_row(
                        "part provenance",
                        _text(part.get("part_label"), NO_PART_LABEL),
                        "Part row is missing source reference or provenance note.",
                    )
                )
            if part_role == "promoter" and not _text(part.get("source_record_id")):
                review_gap_rows.append(
                    _review_gap_row(
                        "promoter source context",
                        _text(part.get("part_label"), NO_PART_LABEL),
                        "Promoter part row has no linked Component Library promoter asset source context.",
                    )
                )
            cassette_part_rows.append(
                {
                    "construct_id": _text(cassette.get("construct_id"), construct_id),
                    "construct_label": profile_label,
                    "cassette_id": cassette_id,
                    "cassette_label": _text(cassette.get("cassette_label"), cassette_id),
                    "part_order": part.get("part_order", 0),
                    "part_role": part_role,
                    "part_label": _text(part.get("part_label"), NO_PART_LABEL),
                    "part_reference": _text(part.get("part_reference")),
                    "source_reference": _text(part.get("source_reference"), NO_SOURCE_LABEL),
                    "source_catalog": _text(part.get("source_catalog"), NO_SOURCE_CATALOG_LABEL),
                    "source_record_id": _text(part.get("source_record_id")),
                    "source_record_label": _text(part.get("source_record_label"), NO_SOURCE_RECORD_LABEL),
                    "evidence_context_note": _text(part.get("evidence_context_note"), NO_EVIDENCE_CONTEXT_LABEL),
                    "provenance_note": _text(part.get("provenance_note"), NO_PROVENANCE_LABEL),
                }
            )

    if not profile and construct_id:
        review_gap_rows.append(
            _review_gap_row("construct profile", construct_id, "No construct profile row recorded.")
        )
    elif profile and _has_missing_provenance(profile):
        review_gap_rows.append(
            _review_gap_row(
                "construct provenance",
                _text(profile.get("construct_label"), construct_id),
                "Construct profile is missing source reference or provenance note.",
            )
        )
    if construct_id and not cassettes:
        review_gap_rows.append(
            _review_gap_row("cassettes", construct_id, "No cassette rows recorded.")
        )
    for cassette in cassettes:
        if _has_missing_provenance(cassette):
            review_gap_rows.append(
                _review_gap_row(
                    "cassette provenance",
                    _text(cassette.get("cassette_label"), _text(cassette.get("cassette_id"))),
                    "Cassette row is missing source reference or provenance note.",
                )
            )
    if construct_id and not gene_links:
        review_gap_rows.append(
            _review_gap_row("gene links", construct_id, "No linked gene rows recorded.")
        )
    for link in gene_links:
        if _has_missing_provenance(link):
            review_gap_rows.append(
                _review_gap_row(
                    "gene link provenance",
                    _text(link.get("gene_label"), NO_GENE_LABEL),
                    "Gene link row is missing source reference or provenance note.",
                )
            )
    if construct_id and not pathway_links:
        review_gap_rows.append(
            _review_gap_row("pathway step links", construct_id, "No linked pathway step rows recorded.")
        )
    for link in pathway_links:
        if _has_missing_provenance(link):
            review_gap_rows.append(
                _review_gap_row(
                    "pathway link provenance",
                    _text(link.get("pathway_step_label"), NO_PATHWAY_STEP_LABEL),
                    "Pathway step link row is missing source reference or provenance note.",
                )
            )
    if construct_id and project_id and not project_links:
        review_gap_rows.append(
            _review_gap_row("project links", construct_id, "No project-level construct link rows recorded.")
        )
    for link in project_links:
        if not _text(link.get("project_id")):
            review_gap_rows.append(
                _review_gap_row(
                    "project link project id",
                    _text(link.get("link_label"), _text(link.get("construct_id"), construct_id)),
                    "Project link row is missing a project id.",
                )
            )
        if not _text(link.get("link_note")) and not _text(link.get("review_note")):
            review_gap_rows.append(
                _review_gap_row(
                    "project link note",
                    _text(link.get("link_label"), _text(link.get("construct_id"), construct_id)),
                    "Project link row is missing link or review note context.",
                )
            )

    construct_component_rows = _build_construct_component_rows(cassette_part_rows)
    construct_component_gap_queue = _build_construct_component_gap_queue(cassette_part_rows)

    return {
        "summary_counts": {
            "construct_profile_count": len(profiles),
            "cassette_count": len(cassettes),
            "cassette_part_count": len(cassette_part_rows),
            "gene_link_count": len(gene_links),
            "pathway_step_link_count": len(pathway_links),
            "project_link_count": len(project_links),
            "review_gap_count": len(review_gap_rows),
        },
        "construct_profile_rows": [
            {
                "construct_id": _text(profile.get("construct_id")),
                "construct_label": _text(profile.get("construct_label"), DEFAULT_CONSTRUCT_LABEL),
                "construct_type": _text(profile.get("construct_type"), DEFAULT_CONSTRUCT_TYPE),
                "plasmid_backbone": _text(profile.get("plasmid_backbone")),
                "host_context_note": _text(profile.get("host_context_note")),
                "source_reference": _text(profile.get("source_reference"), NO_SOURCE_LABEL),
                "provenance_note": _text(profile.get("provenance_note"), NO_PROVENANCE_LABEL),
                "review_status": _text(profile.get("review_status"), NO_REVIEW_STATUS_LABEL),
                "documentation_scope_note": _text(profile.get("documentation_scope_note"), NO_REVIEW_NOTE_LABEL),
            }
        ] if profile else [],
        "cassette_rows": [
            {
                "cassette_id": _text(cassette.get("cassette_id")),
                "construct_id": _text(cassette.get("construct_id")),
                "cassette_label": _text(cassette.get("cassette_label"), DEFAULT_CASSETTE_LABEL),
                "cassette_role": _text(cassette.get("cassette_role"), DEFAULT_CASSETTE_TYPE),
                "cassette_order": cassette.get("cassette_order", 0),
                "promoter_label": _text(cassette.get("promoter_label")),
                "gene_label": _text(cassette.get("gene_label")),
                "terminator_label": _text(cassette.get("terminator_label")),
                "source_reference": _text(cassette.get("source_reference"), NO_SOURCE_LABEL),
                "provenance_note": _text(cassette.get("provenance_note"), NO_PROVENANCE_LABEL),
            }
            for cassette in cassettes
        ],
        "cassette_part_rows": cassette_part_rows,
        "construct_component_rows": construct_component_rows,
        "construct_component_review_summary": build_construct_component_review_summary(
            construct_component_rows,
            construct_component_gap_queue,
        ),
        "construct_component_gap_queue": construct_component_gap_queue,
        "step2_component_context_readback": _dict_or_empty(step2_component_context),
        "linked_gene_rows": [
            {
                "gene_label": _text(link.get("gene_label"), NO_GENE_LABEL),
                "gene_reference": _text(link.get("gene_reference")),
                "source_reference": _text(link.get("source_reference"), NO_SOURCE_LABEL),
                "provenance_note": _text(link.get("provenance_note"), NO_PROVENANCE_LABEL),
            }
            for link in gene_links
        ],
        "linked_pathway_step_rows": [
            {
                "construct_id": _text(link.get("construct_id"), construct_id),
                "pathway_step_id": _text(link.get("pathway_step_id")),
                "pathway_step_label": _text(link.get("pathway_step_label"), NO_PATHWAY_STEP_LABEL),
                "source_reference": _text(link.get("source_reference"), NO_SOURCE_LABEL),
                "provenance_note": _text(link.get("provenance_note"), NO_PROVENANCE_LABEL),
            }
            for link in pathway_links
        ],
        "project_link_rows": [
            {
                "id": link.get("id"),
                "project_id": _text(link.get("project_id")),
                "construct_id": _text(link.get("construct_id"), construct_id),
                "construct_label": _text(link.get("construct_label"), DEFAULT_CONSTRUCT_LABEL),
                "link_label": _text(link.get("link_label"), NO_PROJECT_LINK_LABEL),
                "link_note": _text(link.get("link_note"), NO_PROJECT_LINK_NOTE_LABEL),
                "source_context": _text(link.get("source_context"), NO_SOURCE_LABEL),
                "curation_status": _text(link.get("curation_status"), NO_REVIEW_STATUS_LABEL),
                "review_note": _text(link.get("review_note"), NO_REVIEW_NOTE_LABEL),
            }
            for link in project_links
        ],
        "review_gap_rows": review_gap_rows,
        "part_role_counts": dict(part_counter),
        "supported_component_vocabulary": list(SUPPORTED_COMPONENT_VOCABULARY),
        "boundary_copy": BOUNDARY_COPY,
        "draft_defaults": {
            "construct_label": DEFAULT_CONSTRUCT_LABEL,
            "construct_type": DEFAULT_CONSTRUCT_TYPE,
            "cassette_label": DEFAULT_CASSETTE_LABEL,
            "cassette_role": DEFAULT_CASSETTE_TYPE,
            "review_status": "draft documentation review",
        },
        "empty_states": {
            "constructs": "No construct drafts are present yet. Create a construct draft here or save a Wizard cassette into a construct.",
            "cassettes": "No cassette rows are recorded for the selected construct draft yet. Add cassette rows manually or save from Expression Wizard.",
            "parts": "No cassette part rows are recorded for the selected cassette yet. Add cassette part rows manually or save from Expression Wizard.",
            "project_links": "No project-level construct links are recorded yet. Add a documentation link to connect this construct with a pathway project.",
        },
    }


def build_expression_construct_report_views(project_id: str | int | None = None) -> list[dict[str, Any]]:
    """Return one presenter view per construct profile for read-only report consumers."""
    views: list[dict[str, Any]] = []
    project_id = _text(project_id)
    profiles = repo.list_construct_profiles_for_project(project_id) if project_id else repo.list_construct_profiles()
    seen_construct_ids: set[str] = set()
    for profile in profiles:
        construct_id = _text(profile.get("construct_id"))
        if construct_id and construct_id not in seen_construct_ids:
            seen_construct_ids.add(construct_id)
            views.append(build_expression_construct_presenter(construct_id, project_id=project_id or None))
    return views
