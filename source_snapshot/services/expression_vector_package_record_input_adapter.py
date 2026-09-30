from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from services.expression_vector_design_package_adapter import build_expression_vector_design_package_preview
from services.generated_output_boundary import normalize_generated_output_claims
from services.placeholder_review_value import has_recorded_review_value


CURRENT_RECORD_SOURCE = "current_record"
EMPTY_RECORD_SOURCE = "empty_state"
LEARNING_SAMPLE_SOURCE = "sample_learning_aid"
SOURCE_READBACK_COLUMNS = [
    "Preview field",
    "Current value",
    "Source/readback origin",
    "Source/provenance status",
    "Follow-up",
]

EMPTY_STATE_MESSAGE = (
    "No current expression vector record is available yet. Start from Expression Wizard or open a saved design."
)
EMPTY_STATE_NEXT_STEP = (
    "Start from Expression Wizard or open a saved design, then record one target gene / CDS / protein, "
    "sequence source/provenance, expression host, cassette element, and vector/backbone context before using "
    "the current-record preview."
)
CURRENT_RECORD_COPY = (
    "Current record preview assembled from existing local project, construct, and component documentation rows."
)
SOURCE_READBACK_COPY = (
    "Current-record source readback table: shows where each preview field came from before the Markdown preview. "
    "It is read-only and does not validate, design, or choose biological parts."
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _first_text(*values: Any) -> str:
    for value in values:
        clean = _text(value)
        if has_recorded_review_value(clean):
            return clean
    return ""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, Mapping):
        return [dict(value)]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _project_value(project: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _first_text(project.get(key))
        if value:
            return value
    return ""


def _nested_mapping(source: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return dict(value) if isinstance(value, Mapping) else {}


def _first_construct_view(expression_construct_views: Any) -> dict[str, Any]:
    for view in _list_of_mappings(expression_construct_views):
        if _list_of_mappings(view.get("construct_profile_rows")) or _list_of_mappings(view.get("cassette_part_rows")):
            return view
    return {}


def _first_row(rows: Any) -> dict[str, Any]:
    normalized = _list_of_mappings(rows)
    return normalized[0] if normalized else {}


def _linked_catalog_asset_slot_records(linked_catalog_assets: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    role_to_slot = {
        "promoter": "promoter",
        "coding_sequence": "coding_sequence",
        "cds": "coding_sequence",
        "gene": "coding_sequence",
        "tag": "tag",
        "terminator": "terminator",
        "selection_marker": "selection_marker",
        "marker": "selection_marker",
        "origin": "origin",
        "ori": "origin",
        "vector_backbone": "vector_backbone",
        "backbone": "vector_backbone",
    }
    for asset in _list_of_mappings(linked_catalog_assets):
        asset_snapshot = _nested_mapping(asset, "asset_snapshot")
        source_context = _nested_mapping(asset, "source_context_snapshot")
        review_context = _nested_mapping(asset, "review_status_snapshot")
        role_text = " ".join(
            [
                _text(asset.get("linkage_role")),
                _text(asset.get("asset_type")),
                _text(asset_snapshot.get("asset_type")),
                _text(asset_snapshot.get("component_category")),
                _text(asset_snapshot.get("part_role")),
            ]
        ).casefold()
        slot_key = ""
        for role, candidate_slot in role_to_slot.items():
            if role in role_text:
                slot_key = candidate_slot
                break
        if not slot_key:
            continue
        records.append(
            {
                "slot_key": slot_key,
                "recorded_value": _first_text(
                    asset.get("asset_display_name"),
                    asset_snapshot.get("asset_label"),
                    asset_snapshot.get("display_name"),
                    asset.get("asset_id"),
                ),
                "source_reference": _first_text(
                    source_context.get("stable_source_identifier"),
                    source_context.get("profile_id"),
                    source_context.get("source_accession"),
                    source_context.get("catalog"),
                    asset.get("asset_id"),
                ),
                "review_status": _first_text(
                    review_context.get("review_status"),
                    review_context.get("curation_statuses"),
                    source_context.get("source_review_status"),
                    "needs review",
                ),
                "manual_follow_up": _first_text(
                    asset.get("manual_follow_up"),
                    asset.get("documentation_note"),
                    "Manual follow-up: review linked Component Library source/provenance context.",
                ),
            }
        )
    return records


def _cassette_part_slot_records(cassette_part_rows: Any) -> list[dict[str, Any]]:
    role_to_slot = {
        "promoter": "promoter",
        "5'utr": "five_prime_utr",
        "5' utr": "five_prime_utr",
        "rbs": "rbs",
        "signal": "signal_peptide",
        "signal peptide": "signal_peptide",
        "signal_peptide": "signal_peptide",
        "cds": "coding_sequence",
        "coding sequence": "coding_sequence",
        "terminator": "terminator",
        "selection marker": "selection_marker",
        "selection_marker": "selection_marker",
        "origin": "origin",
        "ori": "origin",
    }
    records: list[dict[str, Any]] = []
    for part in _list_of_mappings(cassette_part_rows):
        role = _text(part.get("part_role")).casefold()
        slot_key = role_to_slot.get(role, "")
        if not slot_key:
            continue
        source = _first_text(part.get("source_reference"), part.get("source_record_label"), part.get("part_reference"))
        records.append(
            {
                "slot_key": slot_key,
                "recorded_value": _first_text(part.get("part_label"), part.get("source_record_label")),
                "source_reference": source or "Not recorded",
                "review_status": "documented" if source else "needs source",
                "manual_follow_up": (
                    "Manual follow-up: review component source/provenance context."
                    if source
                    else "Manual follow-up: record component source/provenance context."
                ),
                "notes": _first_text(part.get("provenance_note"), part.get("evidence_context_note")),
            }
        )
    return records


def _sequence_basic_checks(project: Mapping[str, Any]) -> list[dict[str, str]]:
    sequence_label = _project_value(
        project,
        "sequence_label",
        "cds_label",
        "target_sequence_label",
        "target_gene",
        "target_product",
        "name",
    )
    return [
        {
            "check_name": "Sequence Basic Checks",
            "recorded_value": sequence_label or "Not recorded",
            "review_status": "needs review" if sequence_label else "not assessed",
            "gap_or_follow_up": "Manual follow-up: review read-only sequence check context in the existing project records.",
            "notes": "Documentation review preview only; no sequence rewriting or final complete vector sequence is produced.",
        }
    ]


def _step_context(steps: Any) -> str:
    return "; ".join(
        _first_text(step.get("name"), step.get("title"), step.get("step_name"))
        for step in _list_of_mappings(steps)
        if _first_text(step.get("name"), step.get("title"), step.get("step_name"))
    )


def _source_version(handoff_preview: Mapping[str, Any] | None) -> str:
    handoff = _mapping(handoff_preview)
    identity = _mapping(handoff.get("snapshot_review_card"))
    return _first_text(
        identity.get("snapshot_id"),
        identity.get("snapshot_checksum"),
        "Project Quality Dashboard read-only preview",
    )


def _row_by_slot_key(rows: Any, slot_key: str) -> dict[str, Any]:
    return next((row for row in _list_of_mappings(rows) if row.get("slot_key") == slot_key), {})


def _preview_mapping(preview: Mapping[str, Any] | None, key: str) -> dict[str, Any]:
    return _mapping(_mapping(preview).get(key))


def _has_source_readback_value(value: Any) -> bool:
    text = _text(value)
    return bool(text) and text.casefold() != "missing" and has_recorded_review_value(text)


def _source_status(source: Any, review_status: Any, current_value: Any) -> str:
    source_text = _text(source)
    status_text = _text(review_status, "needs manual review")
    value_text = _text(current_value)
    if not _has_source_readback_value(value_text):
        return "missing"
    if not _has_source_readback_value(source_text):
        return "needs source/provenance"
    return status_text or "needs manual review"


def _origin_from_value(current_value: Any, *, record_source: str, source_label: str) -> str:
    if record_source == EMPTY_RECORD_SOURCE:
        return "missing"
    if record_source == LEARNING_SAMPLE_SOURCE:
        return "sample helper"
    if not _has_source_readback_value(current_value):
        return "not provided"
    return source_label or "current record"


def _source_readback_row(
    *,
    preview_field: str,
    current_value: Any,
    source: Any,
    review_status: Any,
    follow_up: Any,
    record_source: str = CURRENT_RECORD_SOURCE,
    source_label: str = "current record",
) -> dict[str, str]:
    value_text = _text(current_value, "Missing")
    if not _has_source_readback_value(value_text):
        value_text = "Missing"
    follow_up_text = _text(follow_up, "Manual follow-up: review this preview field in the existing records.")
    return {
        "Preview field": preview_field,
        "Current value": value_text,
        "Source/readback origin": _origin_from_value(
            value_text,
            record_source=record_source,
            source_label=source_label,
        ),
        "Source/provenance status": _source_status(source, review_status, value_text),
        "Follow-up": follow_up_text,
    }


def _manual_follow_up_readback_row(gap_rows: Any, *, record_source: str, fallback_follow_up: str) -> dict[str, str]:
    gaps = _list_of_mappings(gap_rows)
    if record_source == EMPTY_RECORD_SOURCE:
        return {
            "Preview field": "Manual Follow-up",
            "Current value": "Missing",
            "Source/readback origin": "missing",
            "Source/provenance status": "needs manual review",
            "Follow-up": fallback_follow_up,
        }
    return {
        "Preview field": "Manual Follow-up",
        "Current value": f"{len(gaps)} follow-up row(s)",
        "Source/readback origin": "current record gap summary",
        "Source/provenance status": "needs manual review" if gaps else "not provided",
        "Follow-up": (
            _first_text(*(row.get("manual_follow_up") or row.get("gap_or_follow_up") for row in gaps))
            or "Manual follow-up: review package limitations before handoff."
        ),
    }


def _empty_source_readback_rows(next_step: str) -> list[dict[str, str]]:
    rows = []
    for field in (
        "Target Gene / CDS / Protein",
        "Expression Host",
        "Promoter",
        "CDS / Insert",
        "Vector / Backbone",
        "Sequence Basic Checks",
    ):
        rows.append(
            _source_readback_row(
                preview_field=field,
                current_value="Missing",
                source="",
                review_status="missing",
                follow_up=next_step,
                record_source=EMPTY_RECORD_SOURCE,
                source_label="",
            )
        )
    rows.append(
        _manual_follow_up_readback_row(
            [],
            record_source=EMPTY_RECORD_SOURCE,
            fallback_follow_up=next_step,
        )
    )
    return rows


def build_expression_vector_package_source_readback_rows(
    record_input: Mapping[str, Any] | None,
) -> list[dict[str, str]]:
    """Build compact source/readback rows for the Handoff Review preview UI.

    The rows explain existing preview inputs only. They do not validate records,
    create package data, choose parts, generate sequences, or change state.
    """
    result = _mapping(record_input)
    record_source = _text(result.get("record_source"), CURRENT_RECORD_SOURCE)
    next_step = _text(result.get("next_step"), EMPTY_STATE_NEXT_STEP)
    preview = result.get("preview") if isinstance(result.get("preview"), Mapping) else None
    if record_source == EMPTY_RECORD_SOURCE or not preview:
        return _empty_source_readback_rows(next_step)

    preview_data = _mapping(preview)
    target = _preview_mapping(preview_data, "target_summary")
    host = _preview_mapping(preview_data, "host_summary")
    vector = _preview_mapping(preview_data, "vector_backbone_summary")
    sequence_rows = _list_of_mappings(preview_data.get("sequence_basic_checks"))
    sequence = sequence_rows[0] if sequence_rows else {}
    cassette_rows = _list_of_mappings(preview_data.get("cassette_slot_rows"))
    promoter = _row_by_slot_key(cassette_rows, "promoter")
    insert = _row_by_slot_key(cassette_rows, "cds_insert")

    rows = [
        _source_readback_row(
            preview_field="Target Gene / CDS / Protein",
            current_value=_first_text(target.get("target_name"), target.get("cds_or_protein_value")),
            source=target.get("source_or_provenance"),
            review_status=target.get("review_status"),
            follow_up=target.get("gap_or_follow_up"),
        ),
        _source_readback_row(
            preview_field="Expression Host",
            current_value=host.get("host_or_system"),
            source=host.get("source_or_provenance"),
            review_status=host.get("review_status"),
            follow_up=host.get("gap_or_follow_up"),
        ),
        _source_readback_row(
            preview_field="Promoter",
            current_value=promoter.get("recorded_value"),
            source=promoter.get("source_or_provenance"),
            review_status=promoter.get("review_status"),
            follow_up=promoter.get("gap_or_follow_up"),
            source_label="current record cassette slot",
        ),
        _source_readback_row(
            preview_field="CDS / Insert",
            current_value=insert.get("recorded_value"),
            source=insert.get("source_or_provenance"),
            review_status=insert.get("review_status"),
            follow_up=insert.get("gap_or_follow_up"),
            source_label="current record cassette slot",
        ),
        _source_readback_row(
            preview_field="Vector / Backbone",
            current_value=vector.get("vector_or_backbone_name"),
            source=vector.get("source_or_provenance"),
            review_status=vector.get("review_status"),
            follow_up=vector.get("gap_or_follow_up"),
        ),
        _source_readback_row(
            preview_field="Sequence Basic Checks",
            current_value=sequence.get("recorded_value"),
            source=sequence.get("source_or_provenance"),
            review_status=sequence.get("review_status"),
            follow_up=sequence.get("gap_or_follow_up"),
            source_label="current record sequence check",
        ),
        _manual_follow_up_readback_row(
            preview_data.get("gap_follow_up_summary"),
            record_source=record_source,
            fallback_follow_up=next_step,
        ),
    ]
    return rows


def _has_current_record(input_payload: Mapping[str, Any], expression_construct_view: Mapping[str, Any]) -> bool:
    project_fields = [
        input_payload.get("target_record", {}).get("target_name"),
        input_payload.get("host_record", {}).get("host_system"),
        input_payload.get("vector_backbone_record", {}).get("backbone_name"),
        input_payload.get("sequence_source_record", {}).get("source_reference"),
    ]
    if any(has_recorded_review_value(value) for value in project_fields):
        return True
    return bool(
        _list_of_mappings(expression_construct_view.get("construct_profile_rows"))
        or _list_of_mappings(expression_construct_view.get("cassette_rows"))
        or _list_of_mappings(expression_construct_view.get("cassette_part_rows"))
    )


def build_expression_vector_package_record_input(
    *,
    project: Mapping[str, Any] | None = None,
    steps: Any = None,
    linked_catalog_assets: Any = None,
    handoff_preview: Mapping[str, Any] | None = None,
    expression_construct_views: Any = None,
) -> dict[str, Any]:
    """Map existing local records into R269 Expression Vector Design Package preview input.

    This adapter is read-only. It does not persist data, export packages, generate sequences,
    choose components, or alter Expression Wizard logic.
    """
    project_data = _mapping(normalize_generated_output_claims(dict(project or {})))
    linked_assets = normalize_generated_output_claims(linked_catalog_assets or [])
    construct_view = _first_construct_view(expression_construct_views)
    construct_profile = _first_row(construct_view.get("construct_profile_rows"))
    cassette_rows = _list_of_mappings(construct_view.get("cassette_rows"))
    cassette_part_rows = _list_of_mappings(construct_view.get("cassette_part_rows"))

    project_label = _project_value(project_data, "name", "project_name", "target_product") or "Active pathway documentation project"
    target_label = _project_value(
        project_data,
        "target_gene",
        "target_gene_name",
        "gene_name",
        "target_cds",
        "target_product",
    )
    host_label = _first_text(
        _project_value(project_data, "host", "host_system", "expression_host", "chassis"),
        construct_profile.get("host_context_note"),
    )
    vector_label = _first_text(
        _project_value(project_data, "vector_backbone", "backbone", "plasmid_backbone", "vector"),
        construct_profile.get("plasmid_backbone"),
    )
    source_label = _project_value(
        project_data,
        "sequence_source",
        "source_reference",
        "source_provenance",
        "documentation_source",
    )
    step_notes = _step_context(steps)

    slot_records = [
        *_linked_catalog_asset_slot_records(linked_assets),
        *_cassette_part_slot_records(cassette_part_rows),
    ]
    input_payload = {
        "package_title": f"{project_label} Expression Vector Design Package preview",
        "source_commit_or_version": _source_version(handoff_preview),
        "package_status": "draft / needs review",
        "target_record": {
            "target_name": target_label or "Not recorded",
            "cds_or_protein_value": target_label or "Not recorded",
            "source_reference": source_label or "Not recorded",
            "review_status": "needs review",
            "manual_follow_up": "Manual follow-up: confirm target gene / CDS / protein source and provenance.",
            "notes": step_notes or "No pathway step context is recorded for this preview.",
        },
        "sequence_source_record": {
            "source_reference": source_label or "Not recorded",
            "review_status": "needs review",
            "manual_follow_up": "Manual follow-up: confirm sequence source/provenance in the existing review surface.",
        },
        "host_record": {
            "host_system": host_label or "Not recorded",
            "source_reference": _project_value(project_data, "host_source", "host_reference") or "Not recorded",
            "review_status": "needs review",
            "manual_follow_up": "Manual follow-up: review expression host documentation context.",
        },
        "vector_backbone_record": {
            "backbone_name": vector_label or "Not recorded",
            "source_reference": _project_value(project_data, "vector_source", "backbone_source", "vector_reference") or "Not recorded",
            "review_status": "needs review",
            "manual_follow_up": "Manual follow-up: review vector/backbone source and limitations.",
        },
        "sequence_basic_checks": _sequence_basic_checks(project_data),
        "gap_follow_up_records": [
            {
                "section": "Expression Vector Design Package preview",
                "recorded_value": "Draft / needs review",
                "review_status": "needs review",
                "manual_follow_up": "Manual follow-up: review package limitations before handoff.",
            }
        ],
        "slot_records": slot_records,
        "construct_profile": construct_profile or {"backbone_name": vector_label or "Not recorded"},
        "cassette_rows": cassette_rows,
        "cassette_part_rows": cassette_part_rows,
        "component_rows": _list_of_mappings(construct_view.get("construct_component_rows")),
    }
    record_source = CURRENT_RECORD_SOURCE if _has_current_record(input_payload, construct_view) else EMPTY_RECORD_SOURCE
    result = {
        "record_source": record_source,
        "has_current_record": record_source == CURRENT_RECORD_SOURCE,
        "input": input_payload,
        "preview": build_expression_vector_design_package_preview(**input_payload)
        if record_source == CURRENT_RECORD_SOURCE
        else None,
        "empty_state": EMPTY_STATE_MESSAGE,
        "next_step": EMPTY_STATE_NEXT_STEP,
        "current_record_copy": CURRENT_RECORD_COPY,
        "learning_sample_source": LEARNING_SAMPLE_SOURCE,
        "source_summary": {
            "project_fields_checked": [
                "target_gene",
                "sequence_source/source_reference",
                "host/expression_host",
                "vector_backbone/plasmid_backbone",
            ],
            "construct_profile_rows": len(_list_of_mappings(construct_view.get("construct_profile_rows"))),
            "cassette_rows": len(cassette_rows),
            "cassette_part_rows": len(cassette_part_rows),
            "linked_slot_rows": len(slot_records),
        },
    }
    result["source_readback_columns"] = list(SOURCE_READBACK_COLUMNS)
    result["source_readback_copy"] = SOURCE_READBACK_COPY
    result["source_readback_rows"] = build_expression_vector_package_source_readback_rows(result)
    return result
