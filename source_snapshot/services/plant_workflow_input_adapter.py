from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


ADAPTER_SCHEMA_VERSION = "plant_workflow_input_adapter.v2.7.r81"
ADAPTER_BATCH = "v2.7-r81"

STATUS_READY_FOR_CHAIN = "ready_for_chain"
STATUS_MANUAL_REVIEW_REQUIRED = "manual_review_required"
STATUS_EMPTY_OR_INVALID_INPUT = "empty_or_invalid_input"
STATUS_UNSUPPORTED_OR_MANUAL_REVIEW = "unsupported_or_manual_review"

CORE_INPUT_FIELDS = (
    "design_goal",
    "host_plant_or_plant_context",
    "target_gene_or_target_product",
    "evidence_records",
    "component_records",
)

PLANT_SCOPE_TERMS = (
    "plant",
    "rice",
    "oryza",
    "nicotiana",
    "benthamiana",
    "arabidopsis",
    "maize",
    "corn",
    "wheat",
    "soybean",
    "tobacco",
    "chloroplast",
    "plastid",
)

NON_PLANT_SCOPE_TERMS = (
    "bacterial",
    "bacteria",
    "e. coli",
    "ecoli",
    "escherichia",
    "yeast",
    "saccharomyces",
    "pichia",
    "mammalian",
    "human cell",
    "cho cell",
    "hek293",
    "mouse",
)

ID_FIELD_CANDIDATES = ("id", "record_id", "source_id", "evidence_id")
COMPONENT_ID_FIELD_CANDIDATES = ("component_id", "asset_id", "id", "record_id")
PROVENANCE_FIELD_CANDIDATES = (
    "source_label",
    "source_reference",
    "source_references",
    "provenance_note",
    "provenance_status",
    "matched_evidence_ids",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return any(_has_value(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return any(_has_value(item) for item in value)
    return True


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _searchable(value: Any) -> str:
    if isinstance(value, Mapping):
        return " ".join(_searchable(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return " ".join(_searchable(item) for item in value)
    return " ".join(_text(value).casefold().replace("-", " ").replace("_", " ").split())


def _has_any_term(blob: str, terms: Sequence[str]) -> bool:
    searchable_blob = _searchable(blob)
    return any(_searchable(term) in searchable_blob for term in terms)


def _unique_texts(values: Sequence[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            unique.append(clean)
            seen.add(key)
    return unique


def _sequence_records(
    value: Any,
    *,
    record_label: str,
    collection_keys: Sequence[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    if value is None:
        return [], warnings

    payload: Any = value
    if isinstance(value, Mapping):
        for key in collection_keys:
            nested = value.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (bytes, bytearray, str)):
                payload = nested
                break
        else:
            payload = [value]

    if isinstance(payload, Sequence) and not isinstance(payload, (bytes, bytearray, str)):
        records: list[dict[str, Any]] = []
        malformed = 0
        for item in payload:
            if isinstance(item, Mapping):
                records.append(_plain_value(dict(item)))
            else:
                malformed += 1
        if malformed:
            warnings.append(f"{record_label} warning: malformed records were preserved as warnings and omitted")
        return records, warnings

    warnings.append(f"{record_label} warning: record collection is missing or malformed")
    return [], warnings


def _id_from_record(record: Mapping[str, Any], field_candidates: Sequence[str]) -> str:
    for field in field_candidates:
        value = _text(record.get(field))
        if value:
            return value
    return ""


def _record_ids(records: Sequence[Mapping[str, Any]], field_candidates: Sequence[str]) -> list[str]:
    return _unique_texts([_id_from_record(record, field_candidates) for record in records])


def _source_fields_used(payload: Mapping[str, Any], fields: Sequence[str]) -> list[str]:
    return [field for field in fields if _has_value(payload.get(field))]


def _plant_context_text(payload: Mapping[str, Any]) -> str:
    return " ".join(
        part
        for part in (
            _text(payload.get("host_plant")),
            _text(payload.get("expression_context")),
            _text(payload.get("plant_context")),
            _searchable(_mapping(payload.get("user_context")).get("plant_context")),
        )
        if part
    )


def _scope_status(payload: Mapping[str, Any]) -> tuple[str, list[str]]:
    host = _text(payload.get("host_plant"))
    context_blob = _searchable(_plant_context_text(payload))
    warnings: list[str] = []
    has_plant = _has_any_term(context_blob, PLANT_SCOPE_TERMS)
    has_non_plant = _has_any_term(context_blob, NON_PLANT_SCOPE_TERMS)

    if has_non_plant and not has_plant:
        warnings.append("scope warning: host/context is outside the plant-only adapter scope")
        return "unsupported_non_plant_scope", warnings
    if has_non_plant and has_plant:
        warnings.append("scope warning: host/context mixes plant and non-plant terms")
        return "ambiguous_or_mixed_scope", warnings
    if host and not has_plant:
        warnings.append("scope warning: host/context needs plant-scope manual review")
        return "ambiguous_host_context", warnings
    if has_plant:
        return "plant_scope_review", warnings
    return "missing_plant_context", warnings


def _construct_slot_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return _plain_value(dict(value))
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray, str)):
        return {}

    slots: dict[str, Any] = {}
    for item in value:
        if not isinstance(item, Mapping):
            continue
        key = (
            _text(item.get("slot_id"))
            or _text(item.get("slot_name"))
            or _text(item.get("component_type"))
        )
        slot_value = (
            _text(item.get("component_id"))
            or _text(item.get("component_name"))
            or _text(item.get("source_label"))
            or _text(item.get("value"))
        )
        if key and slot_value and key not in slots:
            slots[key] = slot_value
    return slots


def _evidence_sources(records: Sequence[Mapping[str, Any]]) -> list[str]:
    sources: list[str] = []
    for record in records:
        sources.append(_id_from_record(record, ID_FIELD_CANDIDATES))
        sources.append(_text(record.get("paper_title")))
        sources.append(_text(record.get("title")))
        sources.append(_text(record.get("source_label")))
    return _unique_texts(sources)


def _normalize_user_intent(
    payload: Mapping[str, Any],
    evidence_records: Sequence[Mapping[str, Any]],
    *,
    scope_status: str,
) -> dict[str, Any]:
    design_goal = _text(payload.get("design_goal"))
    target_product = _text(payload.get("target_product"))
    target_gene = _text(payload.get("target_gene"))
    expression_context = _text(payload.get("expression_context"))
    host_plant = _text(payload.get("host_plant"))
    target_name = target_product or target_gene
    construct_slots = _construct_slot_mapping(payload.get("construct_slots"))

    return _plain_value(
        {
            "intent_text": design_goal,
            "user_intent_text": design_goal,
            "target_name": target_name,
            "target": target_name,
            "product": target_product,
            "target_gene": target_gene,
            "target_type": "plant_expression_review_target" if target_name else "",
            "plant_host": host_plant,
            "host_plant": host_plant,
            "plant_context": " ".join(part for part in (host_plant, expression_context) if part),
            "expression_context": expression_context,
            "route_candidate": _text(payload.get("route_hint")),
            "expression_purpose": design_goal or "documentation review",
            "known_cds_source": _text(payload.get("cds_source")),
            "known_component_ids": construct_slots,
            "known_vector_or_backbone": _text(construct_slots.get("vector_backbone") or construct_slots.get("backbone")),
            "evidence_sources": _evidence_sources(evidence_records),
            "notes": _text(payload.get("notes")),
            "adapter_scope_status": scope_status,
            "active_plant_design_claim": scope_status == "plant_scope_review",
        }
    )


def _missing_input_fields(
    payload: Mapping[str, Any],
    evidence_records: Sequence[Mapping[str, Any]],
    component_records: Sequence[Mapping[str, Any]],
    *,
    scope_status: str,
) -> list[str]:
    missing: list[str] = []
    if not _has_value(payload.get("design_goal")):
        missing.append("design_goal")
    if scope_status == "missing_plant_context":
        missing.append("host_plant_or_plant_context")
    if not (_has_value(payload.get("target_gene")) or _has_value(payload.get("target_product"))):
        missing.append("target_gene_or_target_product")
    if not evidence_records:
        missing.append("evidence_records")
    if not component_records:
        missing.append("component_records")
    return missing


def _provenance_warnings(component_records: Sequence[Mapping[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for record in component_records:
        if not any(_has_value(record.get(field)) for field in PROVENANCE_FIELD_CANDIDATES):
            component_id = _id_from_record(record, COMPONENT_ID_FIELD_CANDIDATES) or "unidentified_component_record"
            warnings.append(f"component warning: {component_id} needs source/provenance review")
    return warnings


def _adapter_status(
    *,
    input_valid: bool,
    scope_status: str,
    missing_input_fields: Sequence[str],
    warnings: Sequence[str],
) -> str:
    if not input_valid:
        return STATUS_EMPTY_OR_INVALID_INPUT
    if scope_status in {"unsupported_non_plant_scope", "ambiguous_or_mixed_scope", "ambiguous_host_context"}:
        return STATUS_UNSUPPORTED_OR_MANUAL_REVIEW
    if missing_input_fields or warnings:
        return STATUS_MANUAL_REVIEW_REQUIRED
    return STATUS_READY_FOR_CHAIN


def _chain_options(
    payload: Mapping[str, Any],
    options: Mapping[str, Any],
    *,
    scope_status: str,
) -> dict[str, Any]:
    user_context = payload.get("user_context")
    context = {
        "project_id": _text(payload.get("project_id")),
        "project_name": _text(payload.get("project_name")),
        "design_goal": _text(payload.get("design_goal")),
        "host_plant": _text(payload.get("host_plant")),
        "expression_context": _text(payload.get("expression_context")),
        "route_hint": _text(payload.get("route_hint")),
        "notes": _text(payload.get("notes")),
        "construct_slots": _plain_value(payload.get("construct_slots")),
        "user_context": _plain_value(user_context),
        "adapter_context": {
            "adapter_batch": ADAPTER_BATCH,
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
            "scope_status": scope_status,
            "documentation_only": True,
        },
    }
    chain_options = _plain_value(dict(options))
    package_metadata = _mapping(chain_options.get("package_metadata"))
    package_metadata.setdefault("review_batch", ADAPTER_BATCH)
    package_metadata.setdefault("adapter_schema_version", ADAPTER_SCHEMA_VERSION)
    chain_options["package_metadata"] = package_metadata
    return {"context": _plain_value(context), "options": _plain_value(chain_options)}


def prepare_plant_review_workflow_input(
    project_payload: Mapping[str, Any] | None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare plain R76-compatible input from local project-style data without running R76."""
    warnings: list[str] = []
    input_valid = isinstance(project_payload, Mapping) and _has_value(project_payload)
    payload = dict(project_payload) if isinstance(project_payload, Mapping) else {}
    if not isinstance(project_payload, Mapping):
        warnings.append("adapter warning: project payload is missing or malformed")

    evidence_records, evidence_warnings = _sequence_records(
        payload.get("evidence_records"),
        record_label="evidence",
        collection_keys=("evidence_records", "records", "items"),
    )
    component_records, component_warnings = _sequence_records(
        payload.get("component_records"),
        record_label="component",
        collection_keys=("component_records", "records", "items"),
    )
    warnings.extend(evidence_warnings)
    warnings.extend(component_warnings)

    scope_status, scope_warnings = _scope_status(payload)
    warnings.extend(scope_warnings)
    warnings.extend(_provenance_warnings(component_records))
    missing_fields = _missing_input_fields(
        payload,
        evidence_records,
        component_records,
        scope_status=scope_status,
    )
    user_intent = _normalize_user_intent(payload, evidence_records, scope_status=scope_status)
    status = _adapter_status(
        input_valid=input_valid,
        scope_status=scope_status,
        missing_input_fields=missing_fields,
        warnings=warnings,
    )
    manual_review_required = status != STATUS_READY_FOR_CHAIN

    source_fields = (
        "project_id",
        "project_name",
        "design_goal",
        "target_product",
        "target_gene",
        "cds_source",
        "host_plant",
        "expression_context",
        "route_hint",
        "construct_slots",
        "component_records",
        "evidence_records",
        "notes",
        "user_context",
    )

    return _plain_value(
        {
            "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
            "adapter_status": status,
            "user_intent": user_intent,
            "evidence_records": evidence_records,
            "component_records": component_records,
            "chain_options": _chain_options(payload, _mapping(options), scope_status=scope_status),
            "missing_input_fields": missing_fields,
            "warnings": _unique_texts(warnings),
            "manual_review_required": manual_review_required,
            "traceability": {
                "project_id": _text(payload.get("project_id")),
                "project_name": _text(payload.get("project_name")),
                "source_field_names_used": _source_fields_used(payload, source_fields),
                "evidence_record_ids": _record_ids(evidence_records, ID_FIELD_CANDIDATES),
                "component_record_ids": _record_ids(component_records, COMPONENT_ID_FIELD_CANDIDATES),
                "scope_status": scope_status,
                "adapter_batch": ADAPTER_BATCH,
            },
        }
    )
