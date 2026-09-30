from __future__ import annotations

from collections import Counter
from typing import Any, Iterable


DOCUMENTATION_BOUNDARY_NOTE = (
    "Documentation-only Component Library component record. This record preserves source/provenance, "
    "review status, and traceability context for local project documentation. It does not recommend "
    "components, validate constructs, improve pathways, predict outcomes, verify source correctness, "
    "or judge downstream use."
)
REVIEW_FIELDS_BOUNDARY_NOTE = (
    "Review fields are documentation review state only; they are not biological proof or downstream-use status."
)
MISSING_METADATA_NOTE = (
    "Missing metadata indicates manual documentation follow-up, not automatic completion or component substitution."
)
DISPLAY_ONLY_NOTE = "Display-only in R353; no schema, persistence, package, or runtime UI behavior is changed."

PAGE_TITLE = "Component Library contract crosswalk"
PAGE_SUBTITLE = (
    "Read-only R352 contract view for existing Component Library and asset-like records."
)
EMPTY_STATE = (
    "No Component Library component or asset-like records are available for contract crosswalk readback. "
    "Add existing documentation records to review source/provenance, evidence/reference, and missing metadata context."
)

REQUIRED_FIELDS = (
    "component_id",
    "component_type",
    "component_label",
    "documentation_boundary_note",
)

OPTIONAL_FIELDS = (
    "component_version",
    "aliases",
    "short_description",
    "domain_or_source_context",
    "sequence_metadata_state",
    "sequence_hash",
    "sequence_hash_algorithm",
    "tags",
    "source_label",
    "source_type",
    "source_database",
    "source_accession",
    "source_reference",
    "source_record_family",
    "source_record_id",
    "provenance_status",
    "provenance_note",
    "documentation_status",
    "review_status",
    "human_review_required",
    "human_review_notes",
    "evidence_type",
    "evidence_summary",
    "missing_metadata_fields",
    "limitation_note",
)

DEFERRED_FIELDS = (
    "created_at",
    "updated_at",
    "normalized_source_provenance_tables",
    "normalized_evidence_reference_tables",
    "type_specific_detail_tables",
    "generic_asset_versioning_rules",
    "durable_construct_component_foreign_keys",
    "package_schema_component_asset_changes",
    "import_export_round_trip_behavior",
)

OUT_OF_SCOPE_ITEMS = (
    "automatic component, promoter, host, vector, cassette, or route choice",
    "component ranking, scoring, substitution, or fit inference",
    "claims about experiment success, source correctness, biological proof, pathway improvement, outcome forecasts, or downstream-use state",
    "database schema changes",
    "migrations",
    "import/export or package export changes",
    "Expression Wizard behavior changes",
    "Expression Construct Review runtime changes",
    "sequence generation or final sequence output",
)

FIELD_PRECEDENCE: dict[str, tuple[str, ...]] = {
    "component_id": ("component_id", "asset_id", "part_id", "profile_id", "record_identifier", "source_record_id"),
    "component_type": ("component_type", "asset_type", "part_type", "component_category", "Asset type"),
    "component_label": (
        "component_label",
        "asset_label",
        "asset_display_name",
        "display_name",
        "promoter_label",
        "part_label",
        "source_record_label",
        "Asset label",
    ),
    "component_version": ("component_version", "asset_version", "version_context", "seed_version", "snapshot_schema_version"),
    "aliases": ("aliases", "native_gene_or_locus", "alias"),
    "short_description": ("short_description", "description", "evidence_summary", "Type-specific notes", "documentation_note"),
    "domain_or_source_context": (
        "domain_or_source_context",
        "organism_or_source_context",
        "species_label",
        "species",
        "plant_clade",
        "clade",
        "host_context_note",
        "Domain/chassis context",
        "cassette_label",
    ),
    "sequence_metadata_state": ("sequence_metadata_state", "sequence_availability", "sequence_availability_status"),
    "sequence_hash": ("sequence_hash",),
    "sequence_hash_algorithm": ("sequence_hash_algorithm",),
    "tags": ("tags",),
    "documentation_boundary_note": ("documentation_boundary_note", "Documentation boundary note", "limitation_note"),
    "source_label": ("source_label", "source_labels", "source_notes", "source_database", "Source/provenance identity"),
    "source_type": ("source_type",),
    "source_database": ("source_database",),
    "source_accession": ("source_accession", "accession"),
    "source_reference": ("source_reference", "publication_reference", "source_notes"),
    "source_record_family": ("source_record_family", "source_catalog", "catalog", "catalog_label", "reference_origin"),
    "source_record_id": ("source_record_id", "record_identifier", "asset_id", "part_id", "profile_id"),
    "provenance_status": ("provenance_status", "curation_status", "source_review_metadata"),
    "provenance_note": ("provenance_note", "human_review_notes", "review_note"),
    "documentation_status": ("documentation_status", "documentation_status_label"),
    "review_status": ("review_status", "curation_status", "review_metadata_status", "Record review status"),
    "human_review_required": ("human_review_required",),
    "human_review_notes": ("human_review_notes", "review_note"),
    "evidence_type": ("evidence_type",),
    "evidence_summary": ("evidence_summary", "evidence_context_note"),
    "missing_metadata_fields": ("missing_metadata_fields", "metadata_gap", "metadata_gap_context"),
    "limitation_note": ("limitation_note", "documentation_boundary_note", "Documentation boundary note"),
}

DISPLAY_ONLY_FIELDS = {
    "component_type",
    "domain_or_source_context",
    "sequence_metadata_state",
    "source_label",
    "source_record_family",
    "source_record_id",
    "provenance_status",
    "documentation_status",
    "review_status",
    "human_review_required",
    "evidence_type",
    "evidence_summary",
    "missing_metadata_fields",
    "limitation_note",
}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = value.replace("|", ";").split(";")
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = []
    return sorted({_text(item) for item in raw_values if _text(item)}, key=str.casefold)


def _value(record: dict[str, Any], field: str) -> Any:
    for key in FIELD_PRECEDENCE.get(field, (field,)):
        if key in record:
            value = record.get(key)
            if isinstance(value, (list, tuple, set)):
                items = _text_list(value)
                if items:
                    return items
            elif isinstance(value, bool):
                return value
            elif _text(value):
                return _text(value)
    if field == "sequence_metadata_state" and "sequence_available" in record:
        return "sequence metadata recorded" if record.get("sequence_available") else "sequence metadata not recorded"
    if field == "documentation_boundary_note":
        return DOCUMENTATION_BOUNDARY_NOTE
    return ""


def _display(value: Any) -> str:
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return "; ".join(value)
    return _text(value, "Not recorded")


def _has_value(value: Any) -> bool:
    if isinstance(value, bool):
        return True
    if isinstance(value, list):
        return bool(value)
    return bool(_text(value))


def _field_requirement(field: str) -> str:
    if field in REQUIRED_FIELDS:
        return "required"
    if field in OPTIONAL_FIELDS:
        return "optional"
    if field in DEFERRED_FIELDS:
        return "deferred"
    return "out-of-scope"


def _source_status(record: dict[str, Any]) -> str:
    source_values = [
        _value(record, "source_label"),
        _value(record, "source_reference"),
        _value(record, "source_record_family"),
        _value(record, "source_record_id"),
        _value(record, "provenance_status"),
    ]
    return "Source/provenance context recorded" if any(_has_value(value) for value in source_values) else "Source/provenance context not recorded"


def _evidence_status(record: dict[str, Any]) -> str:
    evidence_values = [
        _value(record, "evidence_type"),
        _value(record, "evidence_summary"),
        _value(record, "source_reference"),
        _value(record, "documentation_status"),
        _value(record, "review_status"),
    ]
    return "Evidence/reference context recorded" if any(_has_value(value) for value in evidence_values) else "Evidence/reference context not recorded"


def _missing_fields(record: dict[str, Any]) -> list[str]:
    recorded_missing = _value(record, "missing_metadata_fields")
    missing = _text_list(recorded_missing)
    for field in REQUIRED_FIELDS:
        if not _has_value(_value(record, field)):
            missing.append(field)
    return sorted(set(missing), key=str.casefold)


def _follow_up_notes(record: dict[str, Any], missing_fields: list[str]) -> list[str]:
    notes: list[str] = []
    if missing_fields:
        notes.append(MISSING_METADATA_NOTE)
    if _source_status(record).endswith("not recorded"):
        notes.append("Record source/provenance context in an existing review surface before documentation reuse.")
    if _evidence_status(record).endswith("not recorded"):
        notes.append("Record evidence/reference context when available; absence remains a manual documentation follow-up.")
    human_note = _value(record, "human_review_notes") or _value(record, "provenance_note")
    if _has_value(human_note):
        notes.append(f"Manual review note: {_display(human_note)}")
    return notes


def _component_summary(record: dict[str, Any], missing_fields: list[str]) -> dict[str, Any]:
    return {
        "component_id": _display(_value(record, "component_id")),
        "component_type": _display(_value(record, "component_type")),
        "component_label": _display(_value(record, "component_label")),
        "source_provenance_display_status": _source_status(record),
        "evidence_reference_display_status": _evidence_status(record),
        "missing_fields": list(missing_fields),
        "follow_up_notes": _follow_up_notes(record, missing_fields),
        "boundary_notes": [DOCUMENTATION_BOUNDARY_NOTE, REVIEW_FIELDS_BOUNDARY_NOTE],
    }


def _field_row(record: dict[str, Any], field: str) -> dict[str, Any]:
    value = _value(record, field)
    return {
        "contract_field": field,
        "requirement": _field_requirement(field),
        "display_value": _display(value),
        "recorded": _has_value(value),
        "source_keys_checked": list(FIELD_PRECEDENCE.get(field, (field,))),
        "display_treatment": "display-only" if field in DISPLAY_ONLY_FIELDS else "contract field",
        "note": DISPLAY_ONLY_NOTE if field in DISPLAY_ONLY_FIELDS else "R352 contract field readback.",
    }


def _component_payload(record: dict[str, Any]) -> dict[str, Any]:
    source = dict(record)
    missing_fields = _missing_fields(source)
    contract_fields = [*REQUIRED_FIELDS, *OPTIONAL_FIELDS]
    return {
        "component_summary": _component_summary(source, missing_fields),
        "field_crosswalk_rows": [_field_row(source, field) for field in contract_fields],
        "required_fields": [_field_row(source, field) for field in REQUIRED_FIELDS],
        "optional_fields": [_field_row(source, field) for field in OPTIONAL_FIELDS],
        "deferred_fields": [
            {
                "contract_field": field,
                "requirement": "deferred",
                "display_value": "Deferred until a separate schema planning batch",
                "recorded": False,
                "source_keys_checked": [],
                "display_treatment": "not implemented in R353",
                "note": DISPLAY_ONLY_NOTE,
            }
            for field in DEFERRED_FIELDS
        ],
        "out_of_scope_items": list(OUT_OF_SCOPE_ITEMS),
        "source_provenance_display_status": _source_status(source),
        "evidence_reference_display_status": _evidence_status(source),
        "missing_fields": missing_fields,
        "follow_up_notes": _follow_up_notes(source, missing_fields),
        "boundary_notes": [DOCUMENTATION_BOUNDARY_NOTE, REVIEW_FIELDS_BOUNDARY_NOTE, MISSING_METADATA_NOTE],
    }


def _summarize_components(components: list[dict[str, Any]]) -> dict[str, Any]:
    type_counts = Counter(component["component_summary"]["component_type"] for component in components)
    return {
        "total_components": len(components),
        "component_type_counts": dict(sorted(type_counts.items(), key=lambda item: item[0].casefold())),
        "components_with_source_provenance_context": sum(
            1 for component in components if component["source_provenance_display_status"].endswith("recorded")
        ),
        "components_with_evidence_reference_context": sum(
            1 for component in components if component["evidence_reference_display_status"].endswith("recorded")
        ),
        "components_with_missing_fields": sum(1 for component in components if component["missing_fields"]),
        "documentation_boundary_note": DOCUMENTATION_BOUNDARY_NOTE,
    }


def build_component_library_contract_crosswalk_presenter(
    records: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a read-only R352 contract crosswalk from existing asset-like dict records."""
    components = [_component_payload(record) for record in records or []]
    return {
        "title": PAGE_TITLE,
        "subtitle": PAGE_SUBTITLE,
        "summary": _summarize_components(components),
        "components": components,
        "field_groups": {
            "required": list(REQUIRED_FIELDS),
            "optional": list(OPTIONAL_FIELDS),
            "deferred": list(DEFERRED_FIELDS),
            "out_of_scope": list(OUT_OF_SCOPE_ITEMS),
        },
        "boundary_notes": [DOCUMENTATION_BOUNDARY_NOTE, REVIEW_FIELDS_BOUNDARY_NOTE, MISSING_METADATA_NOTE],
        "empty_state": EMPTY_STATE,
    }
