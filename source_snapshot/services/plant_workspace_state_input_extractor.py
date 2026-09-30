from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


EXTRACTOR_SCHEMA_VERSION = "plant_workspace_state_input_extractor.v2.7.r82"
EXTRACTOR_BATCH = "v2.7-r82"

PROJECT_FIELD_ALIASES = {
    "project_id": ("project_id", "id", "workspace_id", "record_id"),
    "project_name": ("project_name", "name", "workspace_name", "title"),
    "design_goal": ("design_goal", "goal", "plant_goal", "review_goal", "intent_text", "description"),
    "target_product": ("target_product", "product", "target_name", "target_protein", "expression_target"),
    "target_gene": ("target_gene", "gene", "gene_name", "cds_name", "target_cds"),
    "cds_source": ("cds_source", "sequence_source", "cds_reference", "source_note"),
    "host_plant": ("host_plant", "plant_host", "plant", "species", "host"),
    "expression_context": ("expression_context", "plant_context", "tissue_context", "context"),
    "route_hint": ("route_hint", "route_candidate", "review_route", "route"),
    "construct_slots": ("construct_slots", "slots", "cassette_slots", "construct_slot_records"),
    "notes": ("notes", "review_notes", "summary"),
    "user_context": ("user_context", "review_context", "context_payload"),
}

EVIDENCE_COLLECTION_KEYS = (
    "evidence_records",
    "evidence",
    "sources",
    "source_records",
    "literature_records",
    "references",
)

COMPONENT_COLLECTION_KEYS = (
    "component_records",
    "components",
    "component_library",
    "library_records",
    "candidate_components",
    "construct_components",
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


def _list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


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


def _source_value(state: Mapping[str, Any], aliases: Sequence[str]) -> tuple[Any, str]:
    for alias in aliases:
        if alias in state and _has_value(state.get(alias)):
            return state.get(alias), alias
    return None, ""


def _record_id(record: Mapping[str, Any], fallback_prefix: str, index: int) -> str:
    for key in ("component_id", "asset_id", "evidence_id", "source_id", "record_id", "id"):
        value = _text(record.get(key))
        if value:
            return value
    return f"{fallback_prefix}-{index:03d}"


def _normalize_evidence_record(record: Mapping[str, Any], source_key: str, index: int) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("id", _record_id(record, "workspace-evidence", index))
    if source_key:
        normalized.setdefault("workspace_source_key", source_key)
    return _plain_value(normalized)


def _normalize_component_record(record: Mapping[str, Any], source_key: str, index: int) -> dict[str, Any]:
    normalized = dict(record)
    normalized.setdefault("component_id", _record_id(record, "workspace-component", index))
    if source_key:
        normalized.setdefault("workspace_source_key", source_key)
    return _plain_value(normalized)


def _coerce_records(
    value: Any,
    *,
    source_key: str,
    fallback_prefix: str,
    normalizer: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    payload = [value] if isinstance(value, Mapping) else _list(value)
    records: list[dict[str, Any]] = []
    malformed = 0
    for index, item in enumerate(payload, start=1):
        if isinstance(item, Mapping):
            records.append(normalizer(item, source_key, index))
        elif _has_value(item):
            malformed += 1
    if malformed:
        warnings.append(f"{fallback_prefix} warning: malformed workspace records were omitted")
    return records, warnings


def _collect_records(
    state: Mapping[str, Any],
    keys: Sequence[str],
    *,
    fallback_prefix: str,
    normalizer: Any,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    source_keys: list[str] = []
    seen_ids: set[str] = set()
    for key in keys:
        if key not in state or not _has_value(state.get(key)):
            continue
        collected, record_warnings = _coerce_records(
            state.get(key),
            source_key=key,
            fallback_prefix=fallback_prefix,
            normalizer=normalizer,
        )
        warnings.extend(record_warnings)
        if collected:
            source_keys.append(key)
        for record in collected:
            record_id = _text(record.get("component_id") or record.get("id"))
            if record_id and record_id in seen_ids:
                continue
            if record_id:
                seen_ids.add(record_id)
            records.append(record)
    return records, warnings, source_keys


def _state_from_workspace(workspace_state: Any) -> tuple[dict[str, Any], list[str], str]:
    if isinstance(workspace_state, Mapping):
        return dict(workspace_state), [], "mapping"
    if isinstance(workspace_state, Sequence) and not isinstance(workspace_state, (bytes, bytearray, str)):
        records = [item for item in workspace_state if isinstance(item, Mapping)]
        warnings = []
        malformed = len([item for item in workspace_state if not isinstance(item, Mapping) and _has_value(item)])
        if malformed:
            warnings.append("extractor warning: malformed list entries were omitted")
        return {"component_records": records}, warnings, "list"
    return {}, ["extractor warning: workspace state is missing or malformed"], "malformed"


def _project_fields(state: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    payload: dict[str, Any] = {}
    source_keys: dict[str, str] = {}
    for field, aliases in PROJECT_FIELD_ALIASES.items():
        value, source_key = _source_value(state, aliases)
        if source_key:
            payload[field] = _plain_value(value)
            source_keys[field] = source_key
    return payload, source_keys


def _missing_fields(project_payload: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    if not _has_value(project_payload.get("design_goal")):
        missing.append("design_goal")
    if not _has_value(project_payload.get("host_plant")) and not _has_value(project_payload.get("expression_context")):
        missing.append("host_plant_or_plant_context")
    if not _has_value(project_payload.get("target_product")) and not _has_value(project_payload.get("target_gene")):
        missing.append("target_gene_or_target_product")
    if not _has_value(project_payload.get("evidence_records")):
        missing.append("evidence_records")
    if not _has_value(project_payload.get("component_records")):
        missing.append("component_records")
    return missing


def _extractor_status(project_payload: Mapping[str, Any], warnings: Sequence[str], source_kind: str) -> str:
    if source_kind == "malformed":
        return "empty_or_invalid_workspace_state"
    if _missing_fields(project_payload) or warnings:
        return "manual_review_required"
    return "ready_for_adapter"


def extract_plant_workflow_project_payload(
    workspace_state: Mapping[str, Any] | Sequence[Any] | None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract R81 project_payload-shaped data from local workspace/project-like state."""
    option_data = _mapping(options)
    state, warnings, source_kind = _state_from_workspace(workspace_state)
    project_payload, project_source_keys = _project_fields(state)
    evidence_records, evidence_warnings, evidence_source_keys = _collect_records(
        state,
        EVIDENCE_COLLECTION_KEYS,
        fallback_prefix="evidence",
        normalizer=_normalize_evidence_record,
    )
    component_records, component_warnings, component_source_keys = _collect_records(
        state,
        COMPONENT_COLLECTION_KEYS,
        fallback_prefix="component",
        normalizer=_normalize_component_record,
    )
    warnings.extend(evidence_warnings)
    warnings.extend(component_warnings)

    if evidence_records:
        project_payload["evidence_records"] = evidence_records
    if component_records:
        project_payload["component_records"] = component_records

    project_payload.setdefault("notes", "")
    project_payload.setdefault("user_context", {})
    project_payload["workspace_extractor_context"] = {
        "extractor_batch": EXTRACTOR_BATCH,
        "extractor_schema_version": EXTRACTOR_SCHEMA_VERSION,
        "documentation_only": True,
    }

    missing_fields = _missing_fields(project_payload)
    status = _extractor_status(project_payload, warnings, source_kind)
    manual_review_required = status != "ready_for_adapter"

    return _plain_value(
        {
            "extractor_schema_version": EXTRACTOR_SCHEMA_VERSION,
            "extractor_batch": EXTRACTOR_BATCH,
            "extractor_status": status,
            "project_payload": project_payload,
            "manual_review_required": manual_review_required,
            "missing_input_fields": missing_fields,
            "warnings": _unique_texts(warnings),
            "traceability": {
                "workspace_source_kind": source_kind,
                "project_source_key_map": project_source_keys,
                "evidence_source_keys_used": evidence_source_keys,
                "component_source_keys_used": component_source_keys,
                "source_keys_used": _unique_texts(
                    list(project_source_keys.values()) + evidence_source_keys + component_source_keys
                ),
                "option_keys": sorted(str(key) for key in option_data),
            },
        }
    )
