from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import Any

from services.expression_cassette_slot_rows_presenter import (
    SAFETY_BOUNDARY_NOTE as CASSETTE_SLOT_BOUNDARY_NOTE,
    build_expression_cassette_slot_rows_presenter,
)
from services.placeholder_review_value import has_recorded_review_value


PACKAGE_TYPE = "Expression Vector Design Package Preview"
DEFAULT_PACKAGE_TITLE = "Expression Vector Design Package preview"
DEFAULT_PACKAGE_STATUS = "draft / needs review"
CHECKSUM_ALGORITHM = "MD5"
NOT_RECORDED = "Not recorded"
DOCUMENTATION_ONLY_SEQUENCE_AVAILABILITY = "Documentation-only record; no final vector sequence is generated."

PACKAGE_LIMITATIONS = [
    "Documentation-only preview assembled from supplied local records for human review.",
    "Does not generate a final vector sequence or complete construct sequence.",
    "Does not output codon-rewritten sequences or perform sequence improvement.",
    "Does not recommend promoters, hosts, backbones, markers, or cloning choices.",
    "Does not provide protocol steps or procedure instructions.",
    "Does not forecast expression, yield, or experimental outcomes.",
    "Does not claim experimental validation, downstream use, or wet-lab use.",
]

IDENTITY_BOUNDARY_NOTE = (
    "The identity payload and MD5 are for matching the same read-only package preview during human review. "
    "They are not a security signature, certification, biological recommendation, or downstream-use judgment."
)

FOLLOW_UP_STATUSES = {
    "missing",
    "needs source",
    "needs review",
    "not assessed",
    "draft / needs review",
}

SOURCE_KEYS = (
    "source_or_provenance",
    "source_provenance",
    "source_provenance_review",
    "source_reference",
    "provenance_note",
    "source_catalog",
    "source_record_id",
    "source_record_label",
    "source_notes",
    "asset_id",
    "record_identifier",
    "provenance_status",
    "version_context",
)

VALUE_KEYS = (
    "recorded_value",
    "target_name",
    "target_label",
    "protein_label",
    "sequence_label",
    "host",
    "host_system",
    "host_label",
    "vector_backbone",
    "backbone",
    "backbone_name",
    "display_name",
    "component_label",
    "asset_label",
    "part_label",
    "value",
    "label",
)

NOTE_KEYS = (
    "notes",
    "manual_notes",
    "review_note",
    "human_review_notes",
    "recorded_context",
    "documentation_context_note",
    "documentation_scope_note",
    "gap_or_follow_up",
    "manual_follow_up",
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _first_recorded(record: Mapping[str, Any], keys: Iterable[str], fallback: str = "") -> str:
    for key in keys:
        value = _text(record.get(key))
        if has_recorded_review_value(value):
            return value
    return fallback


def _join_recorded(record: Mapping[str, Any], keys: Iterable[str], fallback: str = NOT_RECORDED) -> str:
    values = []
    for key in keys:
        value = _text(record.get(key))
        if has_recorded_review_value(value):
            values.append(value)
    return "; ".join(dict.fromkeys(values)) if values else fallback


def _review_status(record: Mapping[str, Any], fallback: str = "needs review") -> str:
    return _first_recorded(
        record,
        (
            "review_status",
            "record_review_status",
            "review_metadata_status",
            "documentation_status",
            "curation_status",
            "context_state",
        ),
        fallback,
    )


def _safe_notes(record: Mapping[str, Any]) -> str:
    return _join_recorded(record, NOTE_KEYS, fallback="No additional notes recorded.")


def _row_by_key(rows: list[dict[str, Any]], slot_key: str) -> dict[str, Any]:
    return next((row for row in rows if row.get("slot_key") == slot_key), {})


def _summary_from_record_or_slot(
    *,
    section: str,
    record: Mapping[str, Any],
    slot_row: Mapping[str, Any] | None = None,
    value_keys: Iterable[str] = VALUE_KEYS,
    value_label: str = "recorded_value",
) -> dict[str, str]:
    slot = dict(slot_row or {})
    value = _first_recorded(record, value_keys) or _text(slot.get("recorded_value"), NOT_RECORDED)
    source = _join_recorded(record, SOURCE_KEYS, fallback=_text(slot.get("source_or_provenance"), NOT_RECORDED))
    status = _review_status(record, fallback=_text(slot.get("review_status"), "needs review"))
    follow_up = _first_recorded(
        record,
        ("gap_or_follow_up", "manual_follow_up"),
        _text(slot.get("gap_or_follow_up"), f"Manual follow-up: review {section} documentation context."),
    )
    notes = _safe_notes(record) if record else _text(slot.get("notes"), "No additional notes recorded.")

    if value == NOT_RECORDED and status == "documented":
        status = "needs review"
    if source == NOT_RECORDED and value != NOT_RECORDED:
        status = "needs source"
        follow_up = "Manual follow-up: record source/provenance context in the existing review surface."

    return {
        "section": section,
        value_label: value,
        "source_or_provenance": source,
        "review_status": status,
        "gap_or_follow_up": follow_up,
        "notes": notes,
    }


def _target_summary(
    record: Mapping[str, Any],
    sequence_source_record: Mapping[str, Any],
    target_slot: Mapping[str, Any],
    source_slot: Mapping[str, Any],
) -> dict[str, str]:
    summary = _summary_from_record_or_slot(
        section="target",
        record=record,
        slot_row=target_slot,
        value_keys=("target_name", "target_label", "protein_label", "sequence_label", "recorded_value", "label"),
        value_label="target_name",
    )
    summary["cds_or_protein_value"] = _first_recorded(
        record,
        ("cds_or_protein_value", "cds_value", "protein_value", "sequence_value", "recorded_value", "value"),
        summary["target_name"],
    )
    sequence_source = _join_recorded(sequence_source_record, SOURCE_KEYS, fallback=_text(source_slot.get("source_or_provenance"), NOT_RECORDED))
    if sequence_source != NOT_RECORDED:
        summary["source_or_provenance"] = sequence_source
    summary["review_status"] = _review_status(
        record,
        fallback=_text(target_slot.get("review_status"), DEFAULT_PACKAGE_STATUS),
    )
    if summary["source_or_provenance"] == NOT_RECORDED and summary["target_name"] != NOT_RECORDED:
        summary["review_status"] = "needs source"
        summary["gap_or_follow_up"] = "Manual follow-up: record target sequence source/provenance context."
    return summary


def _host_summary(record: Mapping[str, Any], host_slot: Mapping[str, Any]) -> dict[str, str]:
    return _summary_from_record_or_slot(
        section="host",
        record=record,
        slot_row=host_slot,
        value_keys=("host", "host_system", "host_label", "recorded_value", "value", "label"),
        value_label="host_or_system",
    )


def _vector_backbone_summary(record: Mapping[str, Any], construct_profile: Mapping[str, Any], vector_slot: Mapping[str, Any]) -> dict[str, str]:
    merged = {**dict(construct_profile), **dict(record)}
    summary = _summary_from_record_or_slot(
        section="vector/backbone",
        record=merged,
        slot_row=vector_slot,
        value_keys=("vector_backbone", "plasmid_backbone", "backbone", "backbone_name", "recorded_value", "value", "label"),
        value_label="vector_or_backbone_name",
    )
    summary["sequence_availability"] = DOCUMENTATION_ONLY_SEQUENCE_AVAILABILITY
    return summary


def _sequence_basic_checks(sequence_basic_checks: Any, sequence_slot: Mapping[str, Any]) -> list[dict[str, str]]:
    rows = _list_of_mappings(sequence_basic_checks)
    if not rows and sequence_slot:
        rows = [
            {
                "check_name": "Sequence Basic Checks",
                "recorded_value": _text(sequence_slot.get("recorded_value"), NOT_RECORDED),
                "review_status": _text(sequence_slot.get("review_status"), "not assessed"),
                "gap_or_follow_up": _text(
                    sequence_slot.get("gap_or_follow_up"),
                    "Manual follow-up: record read-only sequence check context when available.",
                ),
                "notes": _text(sequence_slot.get("notes"), "No additional notes recorded."),
            }
        ]
    if not rows:
        rows = [
            {
                "check_name": "Sequence Basic Checks",
                "recorded_value": NOT_RECORDED,
                "review_status": "not assessed",
                "gap_or_follow_up": "Manual follow-up: record read-only sequence check context when available.",
                "notes": "No sequence checks were supplied to this read-only adapter.",
            }
        ]

    normalized = []
    for index, row in enumerate(rows, start=1):
        normalized.append(
            {
                "check_name": _first_recorded(row, ("check_name", "metric", "label"), f"Sequence check {index}"),
                "recorded_value": _first_recorded(row, ("recorded_value", "value", "summary"), NOT_RECORDED),
                "review_status": _review_status(row, fallback="not assessed"),
                "gap_or_follow_up": _first_recorded(
                    row,
                    ("gap_or_follow_up", "manual_follow_up"),
                    "Manual follow-up: review read-only sequence check context.",
                ),
                "notes": _safe_notes(row),
            }
        )
    return normalized


def _provenance_summary(sections: Iterable[Mapping[str, str]], cassette_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for section in sections:
        rows.append(
            {
                "section": _text(section.get("section"), "package section"),
                "source_or_provenance": _text(section.get("source_or_provenance"), NOT_RECORDED),
                "review_status": _text(section.get("review_status"), "needs review"),
                "gap_or_follow_up": _text(section.get("gap_or_follow_up"), "Manual follow-up: review source/provenance context."),
            }
        )
    for cassette_row in cassette_rows:
        if _text(cassette_row.get("source_or_provenance")) == NOT_RECORDED or _text(cassette_row.get("review_status")) in FOLLOW_UP_STATUSES:
            rows.append(
                {
                    "section": f"cassette slot: {_text(cassette_row.get('slot_label'), _text(cassette_row.get('slot_key'), 'slot'))}",
                    "source_or_provenance": _text(cassette_row.get("source_or_provenance"), NOT_RECORDED),
                    "review_status": _text(cassette_row.get("review_status"), "needs review"),
                    "gap_or_follow_up": _text(cassette_row.get("gap_or_follow_up"), "Manual follow-up: review slot source/provenance context."),
                }
            )
    return rows


def _gap_row(section: str, status: str, recorded_value: str, follow_up: str, notes: str = "") -> dict[str, str]:
    return {
        "section": section,
        "review_status": status,
        "recorded_value": recorded_value,
        "manual_follow_up": follow_up,
        "notes": notes or "Documentation review follow-up generated from supplied package preview inputs.",
    }


def _gap_follow_up_summary(
    sections: Iterable[Mapping[str, str]],
    cassette_rows: Iterable[Mapping[str, Any]],
    sequence_rows: Iterable[Mapping[str, str]],
    supplied_gap_records: Any,
) -> list[dict[str, str]]:
    gaps = []
    for section in sections:
        status = _text(section.get("review_status"))
        source = _text(section.get("source_or_provenance"), NOT_RECORDED)
        value = _text(section.get("recorded_value") or section.get("target_name") or section.get("host_or_system") or section.get("vector_or_backbone_name"), NOT_RECORDED)
        if status in FOLLOW_UP_STATUSES or source == NOT_RECORDED:
            gaps.append(
                _gap_row(
                    _text(section.get("section"), "package section"),
                    status or "needs review",
                    value,
                    _text(section.get("gap_or_follow_up"), "Manual follow-up: review missing package context."),
                    _text(section.get("notes")),
                )
            )
    for row in cassette_rows:
        status = _text(row.get("review_status"))
        if status in FOLLOW_UP_STATUSES:
            gaps.append(
                _gap_row(
                    f"cassette slot: {_text(row.get('slot_label'), _text(row.get('slot_key'), 'slot'))}",
                    status,
                    _text(row.get("recorded_value"), NOT_RECORDED),
                    _text(row.get("gap_or_follow_up"), "Manual follow-up: review cassette slot context."),
                    _text(row.get("notes")),
                )
            )
    for row in sequence_rows:
        status = _text(row.get("review_status"))
        if status in FOLLOW_UP_STATUSES:
            gaps.append(
                _gap_row(
                    f"sequence check: {_text(row.get('check_name'), 'Sequence Basic Checks')}",
                    status,
                    _text(row.get("recorded_value"), NOT_RECORDED),
                    _text(row.get("gap_or_follow_up"), "Manual follow-up: review sequence check context."),
                    _text(row.get("notes")),
                )
            )
    for record in _list_of_mappings(supplied_gap_records):
        gaps.append(
            _gap_row(
                _first_recorded(record, ("section", "affected_section", "workspace_area", "label"), "manual follow-up"),
                _review_status(record, fallback="needs review"),
                _first_recorded(record, ("recorded_value", "current_value", "value"), NOT_RECORDED),
                _first_recorded(record, ("manual_follow_up", "gap_or_follow_up", "notes"), "Manual follow-up recorded by caller."),
                _safe_notes(record),
            )
        )
    return gaps


def _canonical_json(data: Mapping[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _md5(data: Mapping[str, Any]) -> str:
    return hashlib.md5(_canonical_json(data).encode("utf-8")).hexdigest()


def _package_identity(
    *,
    package_title: str,
    package_status: str,
    source_commit_or_version: str,
    target_summary: Mapping[str, str],
    host_summary: Mapping[str, str],
    vector_backbone_summary: Mapping[str, str],
    cassette_slot_rows: list[dict[str, Any]],
    sequence_basic_checks: list[dict[str, str]],
    gap_follow_up_summary: list[dict[str, str]],
) -> dict[str, Any]:
    identity_payload = {
        "package_type": PACKAGE_TYPE,
        "package_title": package_title,
        "package_status": package_status,
        "source_commit_or_version": source_commit_or_version or NOT_RECORDED,
        "target_name": _text(target_summary.get("target_name"), NOT_RECORDED),
        "host_or_system": _text(host_summary.get("host_or_system"), NOT_RECORDED),
        "vector_or_backbone_name": _text(vector_backbone_summary.get("vector_or_backbone_name"), NOT_RECORDED),
        "cassette_slot_row_count": len(cassette_slot_rows),
        "sequence_basic_check_count": len(sequence_basic_checks),
        "manual_follow_up_count": len(gap_follow_up_summary),
        "boundary": "documentation-only read-only preview",
    }
    checksum = _md5(identity_payload)
    return {
        "package_type": PACKAGE_TYPE,
        "package_title": package_title,
        "source_commit_or_version": source_commit_or_version or NOT_RECORDED,
        "package_status": package_status,
        "identity_payload": identity_payload,
        "checksum_algorithm": CHECKSUM_ALGORITHM,
        "md5": checksum,
        "package_id": f"md5:{checksum}",
        "identity_boundary_note": IDENTITY_BOUNDARY_NOTE,
    }


def build_expression_vector_design_package_preview(
    *,
    package_title: str = DEFAULT_PACKAGE_TITLE,
    source_commit_or_version: str = "",
    package_status: str = DEFAULT_PACKAGE_STATUS,
    target_record: Mapping[str, Any] | None = None,
    sequence_source_record: Mapping[str, Any] | None = None,
    host_record: Mapping[str, Any] | None = None,
    vector_backbone_record: Mapping[str, Any] | None = None,
    sequence_basic_checks: Any = None,
    sequence_check_record: Mapping[str, Any] | None = None,
    gap_follow_up_records: Any = None,
    slot_records: Any = None,
    construct_profile: Mapping[str, Any] | None = None,
    cassette_rows: Any = None,
    cassette_part_rows: Any = None,
    component_rows: Any = None,
    component_library_rows: Any = None,
    step2_context_rows: Any = None,
) -> dict[str, Any]:
    """Build a deterministic read-only Expression Vector Design Package preview.

    The adapter composes existing readback records into a package-shaped preview only.
    It does not persist data, change schemas, export packages, or generate vector sequences.
    """
    target = _mapping(target_record)
    sequence_source = _mapping(sequence_source_record)
    host = _mapping(host_record)
    vector = _mapping(vector_backbone_record)
    profile = _mapping(construct_profile)

    presenter_slot_records = slot_records
    if vector:
        if isinstance(presenter_slot_records, Mapping):
            presenter_slot_records = {**dict(presenter_slot_records), "vector_backbone": [vector]}
        elif presenter_slot_records:
            presenter_slot_records = [*_list_of_mappings(presenter_slot_records), {"slot_key": "vector_backbone", **vector}]
        else:
            presenter_slot_records = {"vector_backbone": [vector]}

    slot_presenter = build_expression_cassette_slot_rows_presenter(
        slot_records=presenter_slot_records,
        target_record=target or None,
        sequence_source_record=sequence_source or None,
        host_record=host or None,
        construct_profile=profile or None,
        cassette_rows=cassette_rows,
        cassette_part_rows=cassette_part_rows,
        component_rows=component_rows,
        component_library_rows=component_library_rows,
        step2_context_rows=step2_context_rows,
        sequence_check_record=dict(sequence_check_record) if sequence_check_record else None,
        gap_review_records=gap_follow_up_records,
    )
    cassette_slot_rows = [dict(row) for row in slot_presenter["rows"]]

    target_summary = _target_summary(
        target,
        sequence_source,
        _row_by_key(cassette_slot_rows, "target_gene_cds_protein"),
        _row_by_key(cassette_slot_rows, "sequence_source_provenance"),
    )
    host_summary = _host_summary(host, _row_by_key(cassette_slot_rows, "expression_host"))
    vector_summary = _vector_backbone_summary(vector, profile, _row_by_key(cassette_slot_rows, "vector_backbone"))
    sequence_rows = _sequence_basic_checks(sequence_basic_checks, _row_by_key(cassette_slot_rows, "sequence_basic_checks"))
    section_summaries = [target_summary, host_summary, vector_summary]
    provenance_rows = _provenance_summary(section_summaries, cassette_slot_rows)
    gap_rows = _gap_follow_up_summary(section_summaries, cassette_slot_rows, sequence_rows, gap_follow_up_records)
    identity = _package_identity(
        package_title=_text(package_title, DEFAULT_PACKAGE_TITLE),
        package_status=_text(package_status, DEFAULT_PACKAGE_STATUS),
        source_commit_or_version=_text(source_commit_or_version),
        target_summary=target_summary,
        host_summary=host_summary,
        vector_backbone_summary=vector_summary,
        cassette_slot_rows=cassette_slot_rows,
        sequence_basic_checks=sequence_rows,
        gap_follow_up_summary=gap_rows,
    )

    return {
        "package_identity": identity,
        "target_summary": target_summary,
        "host_summary": host_summary,
        "cassette_slot_rows": cassette_slot_rows,
        "cassette_slot_rows_presenter": {
            "title": slot_presenter["title"],
            "columns": list(slot_presenter["columns"]),
            "slot_order": list(slot_presenter["slot_order"]),
            "summary": dict(slot_presenter["summary"]),
            "documentation_boundary_note": _text(
                slot_presenter.get("documentation_boundary_note"),
                CASSETTE_SLOT_BOUNDARY_NOTE,
            ),
        },
        "vector_backbone_summary": vector_summary,
        "sequence_basic_checks": sequence_rows,
        "provenance_summary": provenance_rows,
        "gap_follow_up_summary": gap_rows,
        "package_limitations": list(PACKAGE_LIMITATIONS),
    }
