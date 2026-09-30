from __future__ import annotations

from typing import Any, Iterable

from services.placeholder_review_value import has_recorded_review_value


SAFETY_BOUNDARY_NOTE = (
    "Documentation-only slot readback for recorded local project context and manual review gaps. "
    "It does not choose components, alter sequences, assemble vector output, provide procedure steps, "
    "forecast outcomes, or judge downstream use."
)

SLOT_COLUMNS = [
    "slot_key",
    "slot_label",
    "slot_group",
    "recorded_value",
    "source_or_provenance",
    "review_status",
    "gap_or_follow_up",
    "notes",
    "safety_boundary_note",
]

SLOT_DEFINITIONS = [
    {
        "slot_key": "target_gene_cds_protein",
        "slot_label": "Target Gene / CDS / Protein",
        "slot_group": "target",
        "optional": False,
        "missing_status": "missing",
    },
    {
        "slot_key": "sequence_source_provenance",
        "slot_label": "Sequence Source / Provenance",
        "slot_group": "source/provenance",
        "optional": False,
        "missing_status": "needs source",
    },
    {
        "slot_key": "expression_host",
        "slot_label": "Expression Host",
        "slot_group": "host/context",
        "optional": False,
        "missing_status": "missing",
    },
    {
        "slot_key": "promoter",
        "slot_label": "Promoter",
        "slot_group": "expression cassette",
        "optional": False,
        "missing_status": "missing",
    },
    {
        "slot_key": "rbs_kozak_5utr",
        "slot_label": "RBS / Kozak / 5' UTR",
        "slot_group": "expression cassette",
        "optional": True,
        "missing_status": "optional / not provided",
    },
    {
        "slot_key": "signal_peptide",
        "slot_label": "Signal Peptide / Secretion Leader",
        "slot_group": "expression cassette",
        "optional": True,
        "missing_status": "optional / not provided",
    },
    {
        "slot_key": "cds_insert",
        "slot_label": "CDS / Insert",
        "slot_group": "expression cassette",
        "optional": False,
        "missing_status": "missing",
    },
    {
        "slot_key": "fusion_tag",
        "slot_label": "Fusion Tag",
        "slot_group": "expression cassette",
        "optional": True,
        "missing_status": "optional / not provided",
    },
    {
        "slot_key": "linker",
        "slot_label": "Linker",
        "slot_group": "expression cassette",
        "optional": True,
        "missing_status": "optional / not provided",
    },
    {
        "slot_key": "terminator_polya",
        "slot_label": "Terminator / PolyA",
        "slot_group": "expression cassette",
        "optional": True,
        "missing_status": "optional / not provided",
    },
    {
        "slot_key": "selectable_marker_reporter",
        "slot_label": "Selectable Marker / Reporter",
        "slot_group": "vector/context",
        "optional": True,
        "missing_status": "optional / not provided",
    },
    {
        "slot_key": "vector_backbone",
        "slot_label": "Vector / Backbone",
        "slot_group": "vector/context",
        "optional": False,
        "missing_status": "missing",
    },
    {
        "slot_key": "component_source",
        "slot_label": "Component Source",
        "slot_group": "source/provenance",
        "optional": False,
        "missing_status": "needs source",
    },
    {
        "slot_key": "sequence_basic_checks",
        "slot_label": "Sequence Basic Checks",
        "slot_group": "read-only checks",
        "optional": False,
        "missing_status": "not assessed",
    },
    {
        "slot_key": "gap_follow_up_review",
        "slot_label": "Gap / Follow-up Review",
        "slot_group": "manual review",
        "optional": False,
        "missing_status": "needs review",
    },
]

SLOT_ORDER = [slot["slot_key"] for slot in SLOT_DEFINITIONS]

DIRECT_SLOT_ALIASES = {
    "target": "target_gene_cds_protein",
    "target_gene": "target_gene_cds_protein",
    "target_gene_cds_protein": "target_gene_cds_protein",
    "cds_target": "cds_insert",
    "coding_sequence": "cds_insert",
    "cds": "cds_insert",
    "gene": "cds_insert",
    "insert": "cds_insert",
    "sequence_source": "sequence_source_provenance",
    "sequence_source_provenance": "sequence_source_provenance",
    "literature_source_note": "sequence_source_provenance",
    "source_reference": "sequence_source_provenance",
    "host": "expression_host",
    "host_context": "expression_host",
    "host_chassis_context_note": "expression_host",
    "expression_host": "expression_host",
    "promoter": "promoter",
    "rbs": "rbs_kozak_5utr",
    "rbs_5utr": "rbs_kozak_5utr",
    "5utr": "rbs_kozak_5utr",
    "5' utr": "rbs_kozak_5utr",
    "kozak": "rbs_kozak_5utr",
    "translation_initiation_context": "rbs_kozak_5utr",
    "signal": "signal_peptide",
    "signal_peptide": "signal_peptide",
    "secretion_leader": "signal_peptide",
    "tag": "fusion_tag",
    "fusion_tag": "fusion_tag",
    "linker": "linker",
    "terminator": "terminator_polya",
    "polya": "terminator_polya",
    "poly_a": "terminator_polya",
    "marker": "selectable_marker_reporter",
    "selectable_marker": "selectable_marker_reporter",
    "reporter": "selectable_marker_reporter",
    "marker_metadata": "selectable_marker_reporter",
    "vector": "vector_backbone",
    "backbone": "vector_backbone",
    "vector_backbone": "vector_backbone",
    "plasmid_backbone": "vector_backbone",
    "component_source": "component_source",
    "sequence_basic_checks": "sequence_basic_checks",
    "gap_follow_up_review": "gap_follow_up_review",
}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _join(values: Iterable[Any], fallback: str = "") -> str:
    clean_values = [_text(value) for value in values if has_recorded_review_value(value)]
    return "; ".join(dict.fromkeys(clean_values)) if clean_values else fallback


def _list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [dict(value)]
    if isinstance(value, list):
        return [dict(item) for item in value if isinstance(item, dict)]
    if isinstance(value, tuple):
        return [dict(item) for item in value if isinstance(item, dict)]
    return []


def _slot_key(value: Any) -> str:
    raw = _text(value).casefold().replace("-", "_").replace("/", "_").replace(" ", "_")
    raw = raw.replace("__", "_").strip("_")
    return DIRECT_SLOT_ALIASES.get(raw, DIRECT_SLOT_ALIASES.get(_text(value).casefold(), ""))


def _record_slot(record: dict[str, Any]) -> str:
    for key in ("slot_key", "slot", "key", "part_role", "component_category", "asset_type", "category"):
        slot = _slot_key(record.get(key))
        if slot:
            return slot
    return ""


def _recorded_value(record: dict[str, Any], slot_key: str) -> str:
    if slot_key == "sequence_basic_checks":
        return _sequence_check_value(record)
    if slot_key == "gap_follow_up_review":
        return _gap_review_value(record)
    for key in (
        "recorded_value",
        "component_label",
        "asset_label",
        "display_name",
        "part_label",
        "target_label",
        "protein_label",
        "sequence_label",
        "value",
        "label",
    ):
        value = _text(record.get(key))
        if has_recorded_review_value(value):
            return value
    return _join(
        [
            record.get("gene_label"),
            record.get("step2_value"),
        ]
    )


def _source_or_provenance(record: dict[str, Any]) -> str:
    return _join(
        [
            record.get("source_or_provenance"),
            record.get("source_provenance"),
            record.get("source_provenance_review"),
            record.get("source_reference"),
            record.get("provenance_note"),
            record.get("source_catalog"),
            record.get("source_record_id"),
            record.get("source_record_label"),
            record.get("source_notes"),
            record.get("asset_id"),
            record.get("record_identifier"),
            record.get("provenance_status"),
            record.get("version_context"),
        ],
        fallback="Not recorded",
    )


def _review_status(record: dict[str, Any], *, recorded_value: str, source_or_provenance: str) -> str:
    recorded_status = _join(
        [
            record.get("review_status"),
            record.get("record_review_status"),
            record.get("review_metadata_status"),
            record.get("curation_status"),
            record.get("documentation_status"),
            record.get("context_state"),
        ]
    )
    if recorded_status:
        return recorded_status
    if recorded_value and source_or_provenance == "Not recorded":
        return "needs source"
    if recorded_value:
        return "documented"
    return ""


def _notes(record: dict[str, Any]) -> str:
    return _join(
        [
            record.get("notes"),
            record.get("manual_notes"),
            record.get("review_note"),
            record.get("human_review_notes"),
            record.get("recorded_context"),
            record.get("evidence_context_note"),
            record.get("documentation_context_note"),
            record.get("documentation_scope_note"),
            record.get("sequence_metadata"),
            record.get("gap_or_follow_up"),
            record.get("manual_follow_up"),
        ],
        fallback="No additional notes recorded.",
    )


def _sequence_check_value(record: dict[str, Any]) -> str:
    recorded = _text(record.get("recorded_value") or record.get("summary") or record.get("label"))
    if recorded:
        return recorded
    return _join(
        [
            f"length: {record.get('length')}" if has_recorded_review_value(record.get("length")) else "",
            f"GC: {record.get('gc_percent')}" if has_recorded_review_value(record.get("gc_percent")) else "",
            f"frame: {record.get('frame_status')}" if has_recorded_review_value(record.get("frame_status")) else "",
            f"start/stop: {record.get('start_stop_status')}" if has_recorded_review_value(record.get("start_stop_status")) else "",
            f"ambiguous bases: {record.get('ambiguous_bases')}" if has_recorded_review_value(record.get("ambiguous_bases")) else "",
        ]
    )


def _gap_review_value(record: dict[str, Any]) -> str:
    return _join(
        [
            record.get("recorded_value"),
            record.get("gap_type"),
            record.get("issue_type"),
            record.get("Gap type"),
            record.get("Issue type"),
            record.get("label"),
            record.get("Label"),
        ]
    )


def _build_row(slot: dict[str, Any], records: list[dict[str, Any]]) -> dict[str, str]:
    slot_key = str(slot["slot_key"])
    record = records[0] if records else {}
    recorded_value = _recorded_value(record, slot_key)
    source_or_provenance = _source_or_provenance(record) if record else "Not recorded"
    review_status = _review_status(
        record,
        recorded_value=recorded_value,
        source_or_provenance=source_or_provenance,
    )

    if recorded_value and source_or_provenance == "Not recorded":
        review_status = "needs source"
        gap_or_follow_up = "Manual follow-up: record source/provenance context in the existing review surface."
    elif recorded_value:
        review_status = review_status or "documented"
        gap_or_follow_up = _text(
            record.get("gap_or_follow_up") or record.get("manual_follow_up"),
            "No slot-specific follow-up generated by this presenter.",
        )
    elif slot.get("optional"):
        recorded_value = "Not provided"
        review_status = "optional / not provided"
        gap_or_follow_up = "Optional slot not provided in current documentation input."
    else:
        recorded_value = "Not recorded"
        review_status = str(slot["missing_status"])
        if review_status == "not assessed":
            gap_or_follow_up = "Manual follow-up: record read-only sequence check context when available."
        elif review_status == "needs source":
            gap_or_follow_up = "Manual follow-up: record source/provenance context in the existing review surface."
        else:
            gap_or_follow_up = f"Manual follow-up: record {slot['slot_label']} context in the existing review surface."

    return {
        "slot_key": slot_key,
        "slot_label": str(slot["slot_label"]),
        "slot_group": str(slot["slot_group"]),
        "recorded_value": recorded_value,
        "source_or_provenance": source_or_provenance,
        "review_status": review_status,
        "gap_or_follow_up": gap_or_follow_up,
        "notes": _notes(record) if record else "No additional notes recorded.",
        "safety_boundary_note": SAFETY_BOUNDARY_NOTE,
    }


def _add_record(bucket: dict[str, list[dict[str, Any]]], slot_key: str, record: dict[str, Any]) -> None:
    if slot_key in SLOT_ORDER:
        bucket.setdefault(slot_key, []).append(dict(record))


def _add_records(bucket: dict[str, list[dict[str, Any]]], records: Iterable[dict[str, Any]]) -> None:
    for record in records:
        slot = _record_slot(record)
        if slot:
            _add_record(bucket, slot, record)


def _component_source_record(bucket: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    source_rows = []
    for slot_key, records in bucket.items():
        if slot_key in {"component_source", "gap_follow_up_review"}:
            continue
        for record in records:
            source = _source_or_provenance(record)
            value = _recorded_value(record, slot_key)
            if value and source != "Not recorded":
                source_rows.append(f"{value}: {source}")
    return {
        "recorded_value": f"{len(source_rows)} component source/provenance row(s) recorded" if source_rows else "",
        "source_or_provenance": "; ".join(source_rows[:4]) if source_rows else "",
        "review_status": "documented" if source_rows else "",
        "notes": "Aggregated from supplied slot/component records; no new source assertions are created.",
    }


def _follow_up_record(rows: list[dict[str, str]]) -> dict[str, Any]:
    gaps = [
        f"{row['slot_label']}: {row['review_status']}"
        for row in rows
        if row["review_status"] in {"missing", "needs source", "needs review", "not assessed"}
    ]
    return {
        "recorded_value": f"{len(gaps)} manual follow-up item(s) visible" if gaps else "No required follow-up generated",
        "review_status": "needs review" if gaps else "documented",
        "notes": "; ".join(gaps[:6]) if gaps else "Recorded rows do not add required follow-up in this presenter output.",
    }


def build_expression_cassette_slot_rows(
    *,
    slot_records: dict[str, Any] | Iterable[dict[str, Any]] | None = None,
    target_record: dict[str, Any] | None = None,
    sequence_source_record: dict[str, Any] | None = None,
    host_record: dict[str, Any] | None = None,
    construct_profile: dict[str, Any] | None = None,
    cassette_rows: Iterable[dict[str, Any]] | None = None,
    cassette_part_rows: Iterable[dict[str, Any]] | None = None,
    component_rows: Iterable[dict[str, Any]] | None = None,
    component_library_rows: Iterable[dict[str, Any]] | None = None,
    step2_context_rows: Iterable[dict[str, Any]] | None = None,
    sequence_check_record: dict[str, Any] | None = None,
    gap_review_records: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    """Map existing read-only records into deterministic expression cassette slot rows."""
    bucket: dict[str, list[dict[str, Any]]] = {}

    if isinstance(slot_records, dict):
        for raw_slot, raw_records in slot_records.items():
            slot = _slot_key(raw_slot)
            for record in _list(raw_records):
                _add_record(bucket, slot, record)
    else:
        _add_records(bucket, _list(slot_records))

    if target_record:
        _add_record(bucket, "target_gene_cds_protein", target_record)
    if sequence_source_record:
        _add_record(bucket, "sequence_source_provenance", sequence_source_record)
    if host_record:
        _add_record(bucket, "expression_host", host_record)
    if sequence_check_record:
        _add_record(bucket, "sequence_basic_checks", sequence_check_record)

    if construct_profile:
        profile = dict(construct_profile)
        if has_recorded_review_value(profile.get("host_context_note")):
            _add_record(
                bucket,
                "expression_host",
                {
                    **profile,
                    "recorded_value": profile.get("host_context_note"),
                    "notes": "Expression construct profile host/context note.",
                },
            )
        if has_recorded_review_value(profile.get("plasmid_backbone")):
            _add_record(
                bucket,
                "vector_backbone",
                {
                    **profile,
                    "recorded_value": profile.get("plasmid_backbone"),
                    "notes": "Expression construct profile vector/backbone context.",
                },
            )

    for cassette in _list(cassette_rows):
        if has_recorded_review_value(cassette.get("promoter_label")):
            _add_record(bucket, "promoter", {**cassette, "recorded_value": cassette.get("promoter_label")})
        if has_recorded_review_value(cassette.get("gene_label")):
            _add_record(bucket, "cds_insert", {**cassette, "recorded_value": cassette.get("gene_label")})
        if has_recorded_review_value(cassette.get("terminator_label")):
            _add_record(bucket, "terminator_polya", {**cassette, "recorded_value": cassette.get("terminator_label")})

    _add_records(bucket, _list(cassette_part_rows))
    _add_records(bucket, _list(component_rows))
    _add_records(bucket, _list(component_library_rows))
    _add_records(bucket, _list(step2_context_rows))

    for gap_record in _list(gap_review_records):
        _add_record(bucket, "gap_follow_up_review", gap_record)

    if "component_source" not in bucket:
        source_record = _component_source_record(bucket)
        if _recorded_value(source_record, "component_source"):
            _add_record(bucket, "component_source", source_record)

    rows = [_build_row(slot, bucket.get(str(slot["slot_key"]), [])) for slot in SLOT_DEFINITIONS]

    if "gap_follow_up_review" not in bucket:
        rows_without_gap = [row for row in rows if row["slot_key"] != "gap_follow_up_review"]
        follow_up_row = _build_row(
            next(slot for slot in SLOT_DEFINITIONS if slot["slot_key"] == "gap_follow_up_review"),
            [_follow_up_record(rows_without_gap)],
        )
        rows = [row if row["slot_key"] != "gap_follow_up_review" else follow_up_row for row in rows]

    return rows


def build_expression_cassette_slot_rows_presenter(**kwargs: Any) -> dict[str, Any]:
    rows = build_expression_cassette_slot_rows(**kwargs)
    return {
        "title": "Expression cassette slot rows",
        "columns": list(SLOT_COLUMNS),
        "rows": rows,
        "slot_order": list(SLOT_ORDER),
        "documentation_boundary_note": SAFETY_BOUNDARY_NOTE,
        "summary": {
            "total_slot_rows": len(rows),
            "documented_rows": sum(1 for row in rows if row["review_status"] == "documented"),
            "manual_follow_up_rows": sum(
                1
                for row in rows
                if row["review_status"] in {"missing", "needs source", "needs review", "not assessed"}
            ),
            "optional_not_provided_rows": sum(
                1 for row in rows if row["review_status"] == "optional / not provided"
            ),
        },
    }
