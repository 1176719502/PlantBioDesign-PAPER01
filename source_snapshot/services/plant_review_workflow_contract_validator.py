from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


VALIDATOR_SCHEMA_VERSION = "plant_review_workflow_contract_validator.v2.7.r78"
VALIDATOR_BATCH = "v2.7-r78"

REQUIRED_TOP_LEVEL_KEYS = (
    "chain_schema_version",
    "chain_status",
    "route_draft",
    "evidence_slot_match_result",
    "component_candidate_match_result",
    "gap_manual_review_queue_result",
    "plant_review_package",
    "readback_presenter",
    "manual_review_required",
    "blocked",
    "warnings",
    "traceability",
)

REQUIRED_READBACK_SECTIONS = (
    "package_header",
    "status_summary_card",
    "review_queue_section",
)

BLOCKED_BOUNDARY_PATH_PARTS = (
    "route_draft.blocked_outputs",
    "route_draft.required_modules[",
    "route_draft.selected_template.blocked_outputs",
    "gap_manual_review_queue_result.blocked_output_categories",
    "plant_review_package.blocked_output_boundaries",
    "plant_review_package.module_card_summary.modules[",
    "readback_presenter.blocked_output_boundary_section.blocked_output_categories",
    "readback_presenter.module_card_section.rows[",
)


def _term(*parts: str) -> str:
    return "".join(parts)


UNSAFE_COPY_FRAGMENTS = (
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
)

UNSAFE_OUTPUT_FIELD_FRAGMENTS = (
    "final_component",
    "selected_component",
    "best_component",
    "recommended_component",
)

SAFE_FALSE_BOUNDARY_FIELD_FRAGMENTS = (
    "final_design_present",
    "final_or_recommended_component_present",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _contract(status: str, errors: list[str] | None = None, warnings: list[str] | None = None, **extra: Any) -> dict[str, Any]:
    payload = {
        "status": status,
        "errors": list(errors or []),
        "warnings": list(warnings or []),
    }
    payload.update(extra)
    return payload


def _is_plain_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _is_plain_list(value: Any) -> bool:
    return isinstance(value, list) and all(_is_plain_scalar(item) for item in value)


def _route_id_from_summary(summary: Mapping[str, Any]) -> str:
    for key in ("route_id", "selected_route_id", "route"):
        value = _text(summary.get(key))
        if value:
            return value
    return ""


def _safe_false_boundary_field(key: str, value: Any) -> bool:
    key_text = key.casefold()
    return any(fragment in key_text for fragment in SAFE_FALSE_BOUNDARY_FIELD_FRAGMENTS) and value is False


def _allowed_blocked_output_path(path: str) -> bool:
    if path in {
        "route_draft.blocked_outputs",
        "route_draft.selected_template.blocked_outputs",
        "gap_manual_review_queue_result.blocked_output_categories",
        "plant_review_package.blocked_output_boundaries",
        "readback_presenter.blocked_output_boundary_section.blocked_output_categories",
    }:
        return True
    return any(part in path for part in BLOCKED_BOUNDARY_PATH_PARTS if part.endswith("["))


def _scan_safety(value: Any, path: str = "") -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key)
            key_fold = key.casefold()
            nested_path = f"{path}.{key}" if path else key
            if any(fragment in key_fold for fragment in UNSAFE_OUTPUT_FIELD_FRAGMENTS):
                if _safe_false_boundary_field(key, nested):
                    warnings.append(f"safety: boundary absence flag retained at {nested_path}")
                else:
                    errors.append(f"safety: unsafe output field is present at {nested_path}")
            if _safe_false_boundary_field(key, nested):
                warnings.append(f"safety: final-design absence flag retained at {nested_path}")
            if key_fold in {"blocked_output_categories", "blocked_outputs"}:
                if not _allowed_blocked_output_path(nested_path):
                    errors.append(f"safety: blocked-output categories appear outside boundary metadata at {nested_path}")
            child_errors, child_warnings = _scan_safety(nested, nested_path)
            errors.extend(child_errors)
            warnings.extend(child_warnings)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            child_errors, child_warnings = _scan_safety(nested, f"{path}[{index}]")
            errors.extend(child_errors)
            warnings.extend(child_warnings)
    elif isinstance(value, str):
        text = value.casefold()
        for phrase in UNSAFE_COPY_FRAGMENTS:
            if phrase in text:
                errors.append(f"safety: unsafe claim text appears at {path}")
    return errors, warnings


def _validate_required_sections(chain_result: Mapping[str, Any]) -> tuple[list[str], list[str], list[str]]:
    present = [key for key in REQUIRED_TOP_LEVEL_KEYS if key in chain_result]
    missing = [key for key in REQUIRED_TOP_LEVEL_KEYS if key not in chain_result]
    errors = [f"missing required top-level section: {key}" for key in missing]
    return present, missing, errors


def _validate_route_contract(chain_result: Mapping[str, Any]) -> dict[str, Any]:
    route = _mapping(chain_result.get("route_draft"))
    errors: list[str] = []
    warnings: list[str] = []
    route_id = _text(route.get("route_id"))
    if not route:
        errors.append("route_draft is missing or malformed")
    if route and not route_id:
        errors.append("route_draft route_id is missing")
    if route and not isinstance(route.get("manual_review_required"), bool):
        warnings.append("route_draft manual_review_required is not a boolean")
    return _contract("invalid" if errors else "valid", errors, warnings, route_id=route_id)


def _validate_evidence_contract(chain_result: Mapping[str, Any]) -> dict[str, Any]:
    evidence = _mapping(chain_result.get("evidence_slot_match_result"))
    slots = _list(evidence.get("slots"))
    errors: list[str] = []
    warnings: list[str] = []
    if not evidence:
        errors.append("evidence_slot_match_result is missing or malformed")
    if evidence and "candidate_slot_evidence_present" not in evidence:
        warnings.append("evidence candidate presence flag is missing")
    for slot in slots:
        slot_map = _mapping(slot)
        ids = slot_map.get("evidence_ids")
        if ids is not None and not _is_plain_list(ids):
            errors.append(f"evidence ids are not a plain list for slot {_text(slot_map.get('slot_id'))}")
    return _contract("invalid" if errors else "valid", errors, warnings, slot_count=len(slots))


def _validate_component_contract(chain_result: Mapping[str, Any]) -> dict[str, Any]:
    component = _mapping(chain_result.get("component_candidate_match_result"))
    slots = _list(component.get("slots"))
    errors: list[str] = []
    warnings: list[str] = []
    if not component:
        errors.append("component_candidate_match_result is missing or malformed")
    if component and "candidate_component_matches_present" not in component:
        warnings.append("component candidate presence flag is missing")
    for slot in slots:
        slot_map = _mapping(slot)
        ids = slot_map.get("component_ids")
        if ids is not None and not _is_plain_list(ids):
            errors.append(f"component ids are not a plain list for slot {_text(slot_map.get('slot_id'))}")
    return _contract("invalid" if errors else "valid", errors, warnings, slot_count=len(slots))


def _validate_queue_contract(chain_result: Mapping[str, Any]) -> dict[str, Any]:
    queue = _mapping(chain_result.get("gap_manual_review_queue_result"))
    items = _list(queue.get("review_items") or queue.get("queue"))
    errors: list[str] = []
    warnings: list[str] = []
    if not queue:
        errors.append("gap_manual_review_queue_result is missing or malformed")
    for item in items:
        item_map = _mapping(item)
        item_id = _text(item_map.get("item_id"))
        if not item_id:
            warnings.append("queue item without item_id")
        for key in ("slot_id", "evidence_ids", "component_ids"):
            value = item_map.get(key)
            if key.endswith("_ids") and value is not None and not _is_plain_list(value):
                errors.append(f"queue item {item_id or '<missing>'} has non-plain {key}")
    return _contract("invalid" if errors else "valid", errors, warnings, review_item_count=len(items))


def _validate_package_contract(chain_result: Mapping[str, Any]) -> dict[str, Any]:
    package = _mapping(chain_result.get("plant_review_package"))
    errors: list[str] = []
    warnings: list[str] = []
    package_status = _text(package.get("package_status"))
    chain_blocked = bool(chain_result.get("blocked"))
    chain_manual = bool(chain_result.get("manual_review_required"))
    if not package:
        errors.append("plant_review_package is missing or malformed")
    if package and not package_status:
        errors.append("plant_review_package package_status is missing")
    if chain_blocked and package_status != "blocked":
        errors.append("blocked chain does not have blocked package_status")
    if not chain_blocked and package_status == "blocked":
        errors.append("package_status is blocked but chain blocked flag is false")
    if chain_manual and package_status not in {"manual_review_required", "blocked"}:
        warnings.append("manual-review chain has a package status outside manual-review or blocked states")
    return _contract("invalid" if errors else "valid", errors, warnings, package_status=package_status)


def _validate_presenter_contract(chain_result: Mapping[str, Any]) -> dict[str, Any]:
    presenter = _mapping(chain_result.get("readback_presenter"))
    errors: list[str] = []
    warnings: list[str] = []
    missing_sections = [section for section in REQUIRED_READBACK_SECTIONS if section not in presenter]
    errors.extend(f"readback presenter missing required section: {section}" for section in missing_sections)
    package_header = _mapping(presenter.get("package_header"))
    status_summary = _mapping(presenter.get("status_summary_card"))
    package_status = _text(package_header.get("package_status"))
    status_label = _text(status_summary.get("status_label"))
    if package_status and status_label and package_status != status_label:
        errors.append("readback package header status does not match status summary label")
    return _contract(
        "invalid" if errors else "valid",
        errors,
        warnings,
        checked_presenter_sections=[section for section in REQUIRED_READBACK_SECTIONS if section in presenter],
        missing_presenter_sections=missing_sections,
    )


def _validate_route_package_alignment(chain_result: Mapping[str, Any]) -> list[str]:
    route = _mapping(chain_result.get("route_draft"))
    package = _mapping(chain_result.get("plant_review_package"))
    presenter = _mapping(chain_result.get("readback_presenter"))
    route_id = _text(route.get("route_id"))
    errors: list[str] = []
    package_route_summary = _mapping(package.get("route_summary"))
    presenter_route_summary = _mapping(presenter.get("route_summary_section"))
    for label, summary in (
        ("package route summary", package_route_summary),
        ("presenter route summary", presenter_route_summary),
    ):
        summary_route_id = _route_id_from_summary(summary)
        if route_id and summary_route_id and route_id != summary_route_id:
            errors.append(f"route_draft route_id contradicts {label}")
    return errors


def _validate_traceability_contract(chain_result: Mapping[str, Any]) -> dict[str, Any]:
    traceability = _mapping(chain_result.get("traceability"))
    errors: list[str] = []
    warnings: list[str] = []
    if not traceability:
        errors.append("traceability is missing or malformed")
    source_payloads = traceability.get("source_payloads_present")
    if source_payloads is not None and not isinstance(source_payloads, Mapping):
        errors.append("traceability source_payloads_present is not a mapping")
    for section_name in ("package_traceability", "readback_traceability"):
        section = _mapping(traceability.get(section_name))
        for key in ("slot_ids", "evidence_ids", "component_ids", "route_ids"):
            if key in section and not _is_plain_list(section.get(key)):
                errors.append(f"{section_name} {key} is not a plain list")
    if isinstance(source_payloads, Mapping):
        missing_sources = [key for key, present in source_payloads.items() if present is False]
        if missing_sources:
            warnings.append("source payload warning: one or more source payloads are absent")
    return _contract("invalid" if errors else "valid", errors, warnings)


def validate_plant_review_workflow_contract(
    chain_result: Mapping[str, Any] | None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a Plant review workflow chain payload without changing it."""
    option_data = _mapping(options)
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(chain_result, Mapping):
        errors.append("chain result is missing or malformed")
        chain_map: dict[str, Any] = {}
    else:
        chain_map = dict(chain_result)

    checked_sections, missing_sections, section_errors = _validate_required_sections(chain_map)
    errors.extend(section_errors)

    route_contract = _validate_route_contract(chain_map)
    evidence_contract = _validate_evidence_contract(chain_map)
    component_contract = _validate_component_contract(chain_map)
    queue_contract = _validate_queue_contract(chain_map)
    package_contract = _validate_package_contract(chain_map)
    presenter_contract = _validate_presenter_contract(chain_map)
    traceability_contract = _validate_traceability_contract(chain_map)

    contracts = (
        route_contract,
        evidence_contract,
        component_contract,
        queue_contract,
        package_contract,
        presenter_contract,
        traceability_contract,
    )
    for contract in contracts:
        errors.extend(contract.get("errors") or [])
        warnings.extend(contract.get("warnings") or [])

    errors.extend(_validate_route_package_alignment(chain_map))
    safety_errors, safety_warnings = _scan_safety(chain_map)
    errors.extend(safety_errors)
    warnings.extend(safety_warnings)

    strict = bool(option_data.get("strict"))
    if strict and warnings:
        errors.append("strict contract mode treats warnings as errors")

    blocked = bool(chain_map.get("blocked")) if chain_map else False
    manual_review_required = bool(chain_map.get("manual_review_required")) if chain_map else True
    contract_status = "invalid" if errors else "valid"

    return _plain_value(
        {
            "validator_schema_version": VALIDATOR_SCHEMA_VERSION,
            "validator_batch": VALIDATOR_BATCH,
            "contract_status": contract_status,
            "is_valid_for_review": contract_status == "valid",
            "manual_review_required": manual_review_required or contract_status == "invalid",
            "blocked": blocked,
            "errors": errors,
            "warnings": warnings,
            "checked_sections": checked_sections,
            "missing_sections": missing_sections,
            "route_contract": route_contract,
            "evidence_contract": evidence_contract,
            "component_contract": component_contract,
            "queue_contract": queue_contract,
            "package_contract": package_contract,
            "presenter_contract": presenter_contract,
            "traceability_contract": traceability_contract,
        }
    )
