from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from services.plant_manual_evidence_package_readback import (
    build_manual_evidence_package_readback,
)
from services.plant_manual_evidence_input_adapter import (
    build_manual_evidence_input_adapter_payload,
)


PRESENTER_SCHEMA_VERSION = "plant_review_package_readback_presenter.v2.7.r75"
PRESENTER_VERSION = "v2.7-r75"

SAFE_BOUNDARY_NOTE = (
    "Documentation-only Plant review package readback for human review. It preserves "
    "upstream route, slot, evidence, component, queue, boundary, and traceability data "
    "without selecting components, generating sequences or procedures, predicting "
    "outcomes, resolving gaps, or judging downstream use."
)
EMPTY_STATE_WARNING = "missing package payload: provide an R74 Plant Review Package payload mapping"

SECTION_KEYS: tuple[str, ...] = (
    "presenter_schema_version",
    "package_header",
    "status_summary_card",
    "design_intent_section",
    "design_slot_completion_section",
    "route_summary_section",
    "module_card_section",
    "construct_slot_section",
    "evidence_section",
    "component_candidate_section",
    "gap_manual_review_section",
    "review_queue_section",
    "manual_evidence_review_queue_section",
    "blocked_output_boundary_section",
    "traceability_section",
    "warning_section",
    "empty_state",
)

MANUAL_EVIDENCE_PAYLOAD_KEYS: tuple[str, ...] = (
    "manual_evidence_review_queue_readback",
    "manual_evidence_review_queue_payload",
    "manual_evidence_preflight_payload",
    "manual_evidence_preflight_result",
    "manual_evidence_preflight_batch",
    "manual_evidence_preflight_records",
    "r193_manual_evidence_preflight_payload",
)

GAP_COUNT_KEYS: tuple[str, ...] = (
    "route_context_gap",
    "required_slot_gap",
    "evidence_gap",
    "component_gap",
    "provenance_gap",
    "ambiguity_or_duplicate_review",
    "blocked_output_boundary",
    "unsupported_scope",
)

_GAP_SUMMARY_SOURCE_KEYS: dict[str, str] = {
    "route_context_gap": "route_context_gap_count",
    "required_slot_gap": "missing_required_slot_count",
    "evidence_gap": "evidence_gap_count",
    "component_gap": "component_gap_count",
    "provenance_gap": "provenance_gap_count",
    "ambiguity_or_duplicate_review": "ambiguity_or_duplicate_count",
    "blocked_output_boundary": "blocked_output_boundary_count",
    "unsupported_scope": "unsupported_scope_count",
}

_REVIEW_HINTS: tuple[tuple[str, str], ...] = (
    ("route_context_gap", "Confirm scope manually."),
    ("required_slot_gap", "Review missing construct slot documentation before handoff."),
    ("evidence_gap", "Review missing evidence/source context before handoff."),
    ("component_gap", "Review missing component candidate records before handoff."),
    ("provenance_gap", "Review missing source/provenance before handoff."),
    ("ambiguity_or_duplicate_review", "Check duplicate/alias candidates manually."),
    ("blocked_output_boundary", "Keep blocked output categories as documentation boundaries."),
    ("unsupported_scope", "Confirm scope manually."),
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (bytes, bytearray, str)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        values: Iterable[Any] = [value]
    elif isinstance(value, Mapping):
        values = sorted(value.keys(), key=lambda item: str(item))
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        values = value
    else:
        values = [value] if _text(value) else []
    return [_text(item) for item in values if _text(item)]


def _unique_texts(values: Iterable[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            unique.append(clean)
            seen.add(key)
    return unique


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().casefold() in {"true", "yes", "y", "1"}
    return bool(value)


def _row_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        _int(row.get("priority")) if _text(row.get("priority")) else 999,
        _text(row.get("severity")).casefold(),
        _text(row.get("category")).casefold(),
        _text(row.get("module_id")).casefold(),
        _text(row.get("slot_id")).casefold(),
        ",".join(_list_texts(row.get("evidence_ids"))).casefold(),
        ",".join(_list_texts(row.get("component_ids"))).casefold(),
        _text(row.get("item_id")).casefold(),
    )


def _slot_sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _text(row.get("module_id")).casefold(),
        _text(row.get("slot_id")).casefold(),
        _text(row.get("slot_label")).casefold(),
    )


def _id_list_from_rows(rows: Sequence[Mapping[str, Any]], field: str) -> list[str]:
    ids: list[str] = []
    for row in rows:
        ids.extend(_list_texts(row.get(field)))
    return sorted(_unique_texts(ids), key=str.casefold)


def _empty_presenter(warnings: Sequence[str] | None = None) -> dict[str, Any]:
    warning_rows = sorted(_unique_texts(warnings or [EMPTY_STATE_WARNING]), key=str.casefold)
    return {
        "presenter_schema_version": PRESENTER_SCHEMA_VERSION,
        "package_header": {
            "package_id": "",
            "package_schema_version": "",
            "package_type": "",
            "package_status": "empty_or_invalid_input",
            "manual_review_required": True,
            "route_id": "",
            "route_label": "",
            "route_status": "",
        },
        "status_summary_card": {
            "status_label": "empty_or_invalid_input",
            "manual_review_label": "Manual Review Needed",
            "blocker_count": 0,
            "review_required_count": 0,
            "informational_count": 0,
            "package_warnings_count": len(warning_rows),
            "safe_boundary_note": SAFE_BOUNDARY_NOTE,
        },
        "design_intent_section": {"rows": []},
        "design_slot_completion_section": {
            "summary": {
                "completed_slots": [],
                "missing_slots": [],
                "completed_slot_count": 0,
                "missing_slot_count": 0,
                "completion_status": "information_completion_needed",
                "manual_review_required": True,
            },
            "rows": [],
            "boundary_note": "Design slot completion is documentation-only manual review readback.",
        },
        "route_summary_section": {},
        "module_card_section": {"rows": []},
        "construct_slot_section": {"rows": []},
        "evidence_section": {"rows": []},
        "component_candidate_section": {"rows": []},
        "gap_manual_review_section": {"counts": {key: 0 for key in GAP_COUNT_KEYS}, "rows": []},
        "review_queue_section": {"rows": []},
        "manual_evidence_review_queue_section": build_manual_evidence_package_readback(),
        "blocked_output_boundary_section": {
            "blocked_output_categories": [],
            "boundary_note": "Blocked output categories are displayed only as safety boundaries.",
        },
        "traceability_section": {
            "source_payloads_present": {},
            "route_ids": [],
            "module_ids": [],
            "slot_ids": [],
            "evidence_ids": [],
            "component_ids": [],
            "upstream_result_versions": {},
            "package_builder_version": "",
            "presenter_version": PRESENTER_VERSION,
        },
        "warning_section": {"warnings": warning_rows, "warning_count": len(warning_rows)},
        "empty_state": {
            "empty_state": True,
            "package_status": "empty_or_invalid_input",
            "manual_review_required": True,
            "warnings": warning_rows,
        },
    }


def _package_header(package: Mapping[str, Any], route: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "package_id": _text(package.get("package_id")),
        "package_schema_version": _text(package.get("package_schema_version")),
        "package_type": _text(package.get("package_type")),
        "package_status": _text(package.get("package_status")) or "empty_or_invalid_input",
        "manual_review_required": _as_bool(package.get("manual_review_required", True)),
        "route_id": _text(route.get("route_id")),
        "route_label": _text(route.get("route_label")),
        "route_status": _text(route.get("route_status")),
    }


def _status_summary(package: Mapping[str, Any], gaps: Mapping[str, Any], warnings: Sequence[str]) -> dict[str, Any]:
    return {
        "status_label": _text(package.get("package_status")) or "empty_or_invalid_input",
        "manual_review_label": "Manual Review Needed" if _as_bool(package.get("manual_review_required", True)) else "Manual Review Not Flagged",
        "blocker_count": _int(gaps.get("blocker_count")),
        "review_required_count": _int(gaps.get("review_required_count")),
        "informational_count": _int(gaps.get("informational_count")),
        "package_warnings_count": len(warnings),
        "safe_boundary_note": SAFE_BOUNDARY_NOTE,
    }


def _design_intent_rows(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    unresolved = _list_texts(summary.get("unresolved_intent_fields"))
    review_notes = _list_texts(summary.get("manual_review_notes"))
    for field in ("target_terms", "product_terms", "host_terms", "context_terms"):
        values = _list_texts(summary.get(field))
        field_key = field.removesuffix("_terms")
        missing_reasons = [reason for reason in unresolved if field_key in reason.casefold()]
        if not values and not missing_reasons:
            missing_reasons = [f"{field_key}_not_recorded"]
        rows.append(
            {
                "field": field,
                "value": values,
                "status": "recorded" if values and not missing_reasons else "manual_review_needed",
                "missing_or_unresolved_reason": "; ".join(_unique_texts([*missing_reasons, *review_notes])),
            }
        )
    return sorted(rows, key=lambda row: _text(row["field"]).casefold())


def _route_summary_section(route: Mapping[str, Any], warnings: Sequence[str]) -> dict[str, Any]:
    notes = [
        warning
        for warning in warnings
        if "unsupported" in warning.casefold() or "mixed" in warning.casefold() or "scope" in warning.casefold()
    ]
    return {
        "route_id": _text(route.get("route_id")),
        "route_label": _text(route.get("route_label")),
        "route_status": _text(route.get("route_status")),
        "route_template_id": _text(route.get("route_template_id")),
        "matched_trigger_terms": _list_texts(route.get("matched_trigger_terms")),
        "matched_context_terms": _list_texts(route.get("matched_context_terms")),
        "unsupported_or_mixed_scope_notes": sorted(_unique_texts(notes), key=str.casefold),
        "documentation_only_boundary": SAFE_BOUNDARY_NOTE,
    }


def _design_slot_completion_source(
    package: Mapping[str, Any],
    presenter_options: Mapping[str, Any],
) -> dict[str, Any]:
    for source in (presenter_options, package):
        completion = _mapping(source.get("design_slot_completion"))
        if completion:
            return dict(completion)
        summary = _mapping(source.get("design_slot_completion_summary"))
        if summary:
            return {"completion_summary": summary, "slot_rows": _mapping_list(source.get("design_slot_completion_rows"))}
    return {}


def _design_slot_completion_section(
    package: Mapping[str, Any],
    presenter_options: Mapping[str, Any],
) -> dict[str, Any]:
    source = _design_slot_completion_source(package, presenter_options)
    summary = _mapping(source.get("completion_summary"))
    rows: list[dict[str, Any]] = []
    for row in _mapping_list(source.get("slot_rows")):
        rows.append(
            {
                "slot_key": _text(row.get("slot_key")),
                "slot_label": _text(row.get("slot_label")),
                "required": _as_bool(row.get("required")),
                "slot_status": _text(row.get("slot_status")) or "missing_manual_entry",
                "manual_review_required": _as_bool(row.get("manual_review_required", True)),
            }
        )
    return {
        "summary": {
            "completed_slots": sorted(_unique_texts(_list_texts(summary.get("completed_slots"))), key=str.casefold),
            "missing_slots": sorted(_unique_texts(_list_texts(summary.get("missing_slots"))), key=str.casefold),
            "completed_slot_count": _int(summary.get("completed_slot_count")),
            "missing_slot_count": _int(summary.get("missing_slot_count")),
            "completion_status": _text(summary.get("completion_status")) or "information_completion_needed",
            "manual_review_required": _as_bool(summary.get("manual_review_required", True)),
        },
        "rows": sorted(rows, key=lambda row: _text(row.get("slot_key")).casefold()),
        "boundary_note": _text(source.get("boundary_note"))
        or "Design slot completion is documentation-only manual review readback.",
    }


def _module_rows(module_summary: Mapping[str, Any], package: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for module in _mapping_list(module_summary.get("modules")):
        rows.append(
            {
                "module_id": _text(module.get("module_id")),
                "module_label": _text(module.get("module_label")),
                "route_id": _text(module.get("route_id")),
                "blocked_output_categories": sorted(_unique_texts(_list_texts(module.get("blocked_output_categories"))), key=str.casefold),
                "manual_review_required": _as_bool(package.get("manual_review_required", True))
                or bool(_list_texts(module.get("blocked_output_categories"))),
            }
        )
    return sorted(rows, key=lambda row: (_text(row["module_id"]).casefold(), _text(row["module_label"]).casefold()))


def _review_reasons_by_slot(review_queue: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    by_slot: dict[str, list[str]] = {}
    for item in review_queue:
        slot_id = _text(item.get("slot_id"))
        if not slot_id:
            continue
        reasons = [
            _text(item.get("category")),
            _text(item.get("reason")),
            *_list_texts(item.get("manual_review_reasons")),
            *_list_texts(item.get("missing_context_reasons")),
        ]
        by_slot.setdefault(slot_id, [])
        by_slot[slot_id] = _unique_texts([*by_slot[slot_id], *reasons])
    return by_slot


def _construct_slot_rows(slot_summary: Mapping[str, Any], review_queue: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    reasons_by_slot = _review_reasons_by_slot(review_queue)
    rows: list[dict[str, Any]] = []
    for slot in _mapping_list(slot_summary.get("slots")):
        slot_id = _text(slot.get("slot_id"))
        evidence_ids = _list_texts(slot.get("evidence_ids"))
        component_ids = _list_texts(slot.get("component_ids"))
        missing_required = _as_bool(slot.get("missing_required_slot"))
        rows.append(
            {
                "slot_id": slot_id,
                "slot_label": _text(slot.get("slot_label")),
                "slot_status": _plain_value(slot.get("slot_status")),
                "required_or_optional": "required" if _as_bool(slot.get("required")) else "optional",
                "missing_required_slot": missing_required,
                "evidence_count": len(evidence_ids),
                "component_count": len(component_ids),
                "review_state": "manual_review_needed" if missing_required or reasons_by_slot.get(slot_id) else "documented_for_review",
            }
        )
    return sorted(rows, key=_slot_sort_key)


def _evidence_rows(evidence_summary: Mapping[str, Any], review_queue: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    reasons_by_slot = _review_reasons_by_slot(review_queue)
    rows: list[dict[str, Any]] = []
    for slot in _mapping_list(evidence_summary.get("slots")):
        slot_id = _text(slot.get("slot_id"))
        evidence_ids = sorted(_unique_texts(_list_texts(slot.get("evidence_ids"))), key=str.casefold)
        rows.append(
            {
                "slot_id": slot_id,
                "evidence_ids": evidence_ids,
                "evidence_count": _int(slot.get("evidence_count")) if "evidence_count" in slot else len(evidence_ids),
                "evidence_gap": _as_bool(slot.get("evidence_gap")),
                "source_provenance_completeness_status": _text(slot.get("source_completeness_status")),
                "manual_review_reasons": sorted(_unique_texts(reasons_by_slot.get(slot_id, [])), key=str.casefold),
            }
        )
    return sorted(rows, key=lambda row: (_text(row["slot_id"]).casefold(), ",".join(row["evidence_ids"]).casefold()))


def _component_rows(component_summary: Mapping[str, Any], review_queue: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    reasons_by_slot = _review_reasons_by_slot(review_queue)
    rows: list[dict[str, Any]] = []
    for slot in _mapping_list(component_summary.get("slots")):
        slot_id = _text(slot.get("slot_id"))
        candidates = _mapping_list(slot.get("candidate_components"))
        candidate_ids = sorted(_unique_texts(_list_texts(slot.get("component_ids"))), key=str.casefold)
        if not candidate_ids:
            candidate_ids = sorted(_unique_texts(candidate.get("component_id") for candidate in candidates), key=str.casefold)
        provenance_gap = any(_as_bool(candidate.get("missing_provenance")) for candidate in candidates)
        duplicate_or_alias = any(_as_bool(candidate.get("duplicate_or_alias_flag")) for candidate in candidates)
        candidate_statuses = sorted(_unique_texts(candidate.get("candidate_status") for candidate in candidates), key=str.casefold)
        provenance_statuses = sorted(_unique_texts(candidate.get("provenance_status") for candidate in candidates), key=str.casefold)
        rows.append(
            {
                "slot_id": slot_id,
                "component_ids": candidate_ids,
                "component_count": _int(slot.get("component_count")) if "component_count" in slot else len(candidate_ids),
                "candidate_status": candidate_statuses[0] if len(candidate_statuses) == 1 else candidate_statuses,
                "provenance_status": provenance_statuses[0] if len(provenance_statuses) == 1 else provenance_statuses,
                "duplicate_or_alias_flag": duplicate_or_alias,
                "manual_review_required": provenance_gap or duplicate_or_alias or bool(reasons_by_slot.get(slot_id)),
                "manual_review_reasons": sorted(_unique_texts(reasons_by_slot.get(slot_id, [])), key=str.casefold),
            }
        )
    return sorted(rows, key=lambda row: (_text(row["slot_id"]).casefold(), ",".join(row["component_ids"]).casefold()))


def _gap_manual_review_section(gap_summary: Mapping[str, Any], review_queue: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = {
        gap_key: _int(gap_summary.get(source_key))
        for gap_key, source_key in _GAP_SUMMARY_SOURCE_KEYS.items()
    }
    for item in review_queue:
        category = _text(item.get("category"))
        if category in counts:
            counts[category] = max(counts[category], 1)
    rows = [
        {
            "category": category,
            "count": counts[category],
            "manual_review_required": counts[category] > 0,
        }
        for category in GAP_COUNT_KEYS
    ]
    return {"counts": counts, "rows": rows}


def _reviewer_action_hint(category: str) -> str:
    for category_key, hint in _REVIEW_HINTS:
        if category == category_key:
            return hint
    return "Review documentation context manually before handoff."


def _review_queue_rows(review_queue: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in review_queue:
        category = _text(item.get("category"))
        reason = _text(item.get("reason") or item.get("note"))
        if not reason:
            reason = "; ".join(_list_texts(item.get("manual_review_reasons")))
        rows.append(
            {
                "priority": _int(item.get("priority")) if _text(item.get("priority")) else 999,
                "severity": _text(item.get("severity")),
                "category": category,
                "item_id": _text(item.get("item_id")),
                "route_id": _text(item.get("route_id")),
                "module_id": _text(item.get("module_id")),
                "slot_id": _text(item.get("slot_id")),
                "evidence_ids": sorted(_unique_texts(_list_texts(item.get("evidence_ids"))), key=str.casefold),
                "component_ids": sorted(_unique_texts(_list_texts(item.get("component_ids"))), key=str.casefold),
                "title": _text(item.get("title")) or category.replace("_", " ").title(),
                "reason": reason,
                "reviewer_action_hint": _reviewer_action_hint(category),
            }
        )
    return sorted(rows, key=_row_sort_key)


def _blocked_boundary_section(package: Mapping[str, Any]) -> dict[str, Any]:
    categories = sorted(_unique_texts(_list_texts(package.get("blocked_output_boundaries"))), key=str.casefold)
    return {
        "blocked_output_categories": categories,
        "boundary_note": (
            "Blocked output categories are displayed only as safety boundaries; they are not "
            "generated outputs or product claims."
        ),
    }


def _warnings(package: Mapping[str, Any]) -> list[str]:
    warnings = _list_texts(package.get("package_warnings"))
    for field in (
        "package_id",
        "package_schema_version",
        "package_type",
        "route_summary",
        "construct_slot_summary",
        "evidence_summary",
        "component_candidate_summary",
        "gap_manual_review_summary",
        "review_queue",
        "traceability",
    ):
        if field not in package:
            warnings.append(f"missing upstream payload warning: package field {field} is missing")
    return sorted(_unique_texts(warnings), key=str.casefold)


def _manual_evidence_payload(
    package: Mapping[str, Any],
    presenter_options: Mapping[str, Any],
) -> Any:
    for source in (presenter_options, package):
        for key in MANUAL_EVIDENCE_PAYLOAD_KEYS:
            value = source.get(key)
            if value is not None:
                return value
    adapter_payload = build_manual_evidence_input_adapter_payload(
        [presenter_options, package]
    )
    if adapter_payload["input_summary"]["normalized_record_count"]:
        return adapter_payload
    return None


def _traceability_section(
    traceability: Mapping[str, Any],
    module_rows: Sequence[Mapping[str, Any]],
    slot_rows: Sequence[Mapping[str, Any]],
    evidence_rows: Sequence[Mapping[str, Any]],
    component_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "source_payloads_present": _plain_value(traceability.get("source_payloads_present") or {}),
        "route_ids": sorted(_unique_texts(_list_texts(traceability.get("route_ids"))), key=str.casefold),
        "module_ids": sorted(
            _unique_texts([*_list_texts(traceability.get("module_ids")), *(row.get("module_id") for row in module_rows)]),
            key=str.casefold,
        ),
        "slot_ids": sorted(
            _unique_texts([*_list_texts(traceability.get("slot_ids")), *(row.get("slot_id") for row in slot_rows)]),
            key=str.casefold,
        ),
        "evidence_ids": sorted(
            _unique_texts([*_list_texts(traceability.get("evidence_ids")), *_id_list_from_rows(evidence_rows, "evidence_ids")]),
            key=str.casefold,
        ),
        "component_ids": sorted(
            _unique_texts([*_list_texts(traceability.get("component_ids")), *_id_list_from_rows(component_rows, "component_ids")]),
            key=str.casefold,
        ),
        "upstream_result_versions": _plain_value(traceability.get("upstream_result_versions") or {}),
        "package_builder_version": _text(traceability.get("package_builder_version")),
        "presenter_version": PRESENTER_VERSION,
    }


def build_plant_review_package_readback_presenter(
    package_payload: Mapping[str, Any] | None,
    presenter_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return deterministic plain readback sections for an R74 Plant Review Package payload."""
    option_data = _mapping(presenter_options)
    if not isinstance(package_payload, Mapping) or not package_payload:
        return _empty_presenter()

    package = package_payload
    warnings = _warnings(package)
    if _text(package.get("package_status")) == "empty_or_invalid_input":
        warnings = sorted(_unique_texts([*warnings, EMPTY_STATE_WARNING]), key=str.casefold)

    route = _mapping(package.get("route_summary"))
    gaps = _mapping(package.get("gap_manual_review_summary"))
    module_summary = _mapping(package.get("module_card_summary"))
    slot_summary = _mapping(package.get("construct_slot_summary"))
    evidence_summary = _mapping(package.get("evidence_summary"))
    component_summary = _mapping(package.get("component_candidate_summary"))
    review_queue = _mapping_list(package.get("review_queue"))

    review_rows = _review_queue_rows(review_queue)
    module_rows = _module_rows(module_summary, package)
    slot_rows = _construct_slot_rows(slot_summary, review_rows)
    evidence_rows = _evidence_rows(evidence_summary, review_rows)
    component_rows = _component_rows(component_summary, review_rows)
    traceability = _traceability_section(
        _mapping(package.get("traceability")),
        module_rows,
        slot_rows,
        evidence_rows,
        component_rows,
    )
    required_package_fields = {
        "package_id",
        "package_schema_version",
        "package_type",
        "package_status",
        "route_summary",
        "construct_slot_summary",
        "evidence_summary",
        "component_candidate_summary",
        "gap_manual_review_summary",
        "review_queue",
        "traceability",
    }
    is_empty = (
        _text(package.get("package_status")) == "empty_or_invalid_input"
        or not required_package_fields.issubset(set(package))
    )

    presenter = {
        "presenter_schema_version": PRESENTER_SCHEMA_VERSION,
        "package_header": _package_header(package, route),
        "status_summary_card": _status_summary(package, gaps, warnings),
        "design_intent_section": {"rows": _design_intent_rows(_mapping(package.get("design_intent_summary")))},
        "design_slot_completion_section": _design_slot_completion_section(package, option_data),
        "route_summary_section": _route_summary_section(route, warnings),
        "module_card_section": {"rows": module_rows},
        "construct_slot_section": {"rows": slot_rows},
        "evidence_section": {"rows": evidence_rows},
        "component_candidate_section": {"rows": component_rows},
        "gap_manual_review_section": _gap_manual_review_section(gaps, review_rows),
        "review_queue_section": {"rows": review_rows},
        "manual_evidence_review_queue_section": build_manual_evidence_package_readback(
            _manual_evidence_payload(package, option_data)
        ),
        "blocked_output_boundary_section": _blocked_boundary_section(package),
        "traceability_section": traceability,
        "warning_section": {"warnings": warnings, "warning_count": len(warnings)},
        "empty_state": {
            "empty_state": is_empty,
            "package_status": _text(package.get("package_status")) or "empty_or_invalid_input",
            "manual_review_required": _as_bool(package.get("manual_review_required", True)),
            "warnings": warnings if is_empty else [],
        },
    }
    return {key: _plain_value(presenter[key]) for key in SECTION_KEYS}
