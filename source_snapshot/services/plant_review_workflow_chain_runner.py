from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Callable

from services.evidence_record_normalizer import normalize_evidence_records
from services.plant_component_candidate_matcher import match_plant_component_candidates
from services.plant_evidence_slot_matcher import match_plant_evidence_to_slots
from services.plant_gap_manual_review_queue_builder import build_plant_gap_manual_review_queue
from services.plant_review_package_builder import build_plant_review_package
from services.plant_review_package_readback_presenter import build_plant_review_package_readback_presenter
from services.plant_user_intent_route_draft_builder import build_plant_expression_route_draft


CHAIN_SCHEMA_VERSION = "plant_review_workflow_chain.v2.7.r76"
CHAIN_RUNNER_VERSION = "v2.7-r76"

CHAIN_BOUNDARY_NOTE = (
    "Documentation-only Plant review workflow chain for manual review. It preserves "
    "upstream route, evidence, component, gap, package, readback, and traceability "
    "payloads without selecting final components, generating sequences or procedures, "
    "predicting outcomes, resolving gaps, or judging downstream use."
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


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


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence_payload(value: Any, collection_keys: Sequence[str]) -> tuple[list[Any], list[str]]:
    warnings: list[str] = []
    if value is None:
        return [], warnings
    if isinstance(value, Mapping):
        for key in collection_keys:
            nested = value.get(key)
            if isinstance(nested, Sequence) and not isinstance(nested, (bytes, bytearray, str)):
                return list(nested), warnings
        return [dict(value)], warnings
    if isinstance(value, str):
        return [value], warnings
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value), warnings
    warnings.append(f"input warning: unsupported {collection_keys[0]} payload type was ignored")
    return [], warnings


def _normalize_evidence_input(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    payloads, warnings = _sequence_payload(value, ("evidence_records", "records", "items"))
    skipped = sum(1 for item in payloads if not isinstance(item, (Mapping, str)))
    if skipped:
        warnings.append("input warning: malformed evidence records were ignored")
    return normalize_evidence_records([item for item in payloads if isinstance(item, (Mapping, str))]), warnings


def _component_record_from_string(value: str, index: int) -> dict[str, Any]:
    return {
        "component_id": f"local-component-{index:03d}",
        "component_name": value,
        "component_type": "component",
        "provenance_status": "source_provenance_missing",
        "raw_input": value,
    }


def _normalize_component_input(value: Any) -> tuple[list[dict[str, Any]], list[str]]:
    payloads, warnings = _sequence_payload(value, ("component_records", "records", "items"))
    records: list[dict[str, Any]] = []
    skipped = 0
    for index, item in enumerate(payloads, start=1):
        if isinstance(item, Mapping):
            records.append(dict(item))
        elif isinstance(item, str):
            records.append(_component_record_from_string(item, index))
        else:
            skipped += 1
    if skipped:
        warnings.append("input warning: malformed component records were ignored")
    return records, warnings


def _context_payload(user_intent: Any, context: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if isinstance(user_intent, Mapping):
        for key in (
            "target",
            "target_name",
            "product",
            "host",
            "plant_host",
            "context",
            "plant_context",
            "tissue_context",
            "query",
            "user_query",
        ):
            if key in user_intent:
                payload[key] = user_intent[key]
    elif isinstance(user_intent, str):
        payload["user_query"] = user_intent

    if isinstance(context, Mapping):
        payload.update(dict(context))
    elif isinstance(context, str):
        payload["context_text"] = context
    return payload


def _options_payload(options: Any) -> dict[str, Any]:
    return dict(options) if isinstance(options, Mapping) else {}


def _run_step(
    label: str,
    warnings: list[str],
    step: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    try:
        result = step()
    except Exception as exc:  # pragma: no cover - defensive safety boundary
        warnings.append(f"{label} warning: upstream step failed safe with {exc.__class__.__name__}")
        return {}
    if not isinstance(result, Mapping):
        warnings.append(f"{label} warning: upstream step returned malformed payload")
        return {}
    return dict(result)


def _status_value(result: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        value = _text(result.get(key))
        if value:
            return value
    return ""


def _has_blocker(result: Mapping[str, Any]) -> bool:
    summary = result.get("summary")
    if isinstance(summary, Mapping) and int(summary.get("blocker_count") or 0) > 0:
        return True
    gap_summary = result.get("gap_manual_review_summary")
    if isinstance(gap_summary, Mapping) and int(gap_summary.get("blocker_count") or 0) > 0:
        return True
    status_blob = " ".join(
        _status_value(
            result,
            "chain_status",
            "draft_status",
            "matcher_status",
            "queue_status",
            "package_status",
        ).casefold()
        for _ in (0,)
    )
    return "blocked" in status_blob or "unsupported" in status_blob


def _manual_review_required(*results: Mapping[str, Any]) -> bool:
    return any(bool(result.get("manual_review_required")) for result in results if isinstance(result, Mapping))


def _chain_status(
    *,
    route_draft: Mapping[str, Any],
    evidence_result: Mapping[str, Any],
    component_result: Mapping[str, Any],
    queue_result: Mapping[str, Any],
    package_payload: Mapping[str, Any],
    readback: Mapping[str, Any],
    warnings: Sequence[str],
) -> str:
    results = (route_draft, evidence_result, component_result, queue_result, package_payload, readback)
    if any(_has_blocker(result) for result in results):
        return "blocked"
    package_status = _text(package_payload.get("package_status"))
    if package_status == "empty_or_invalid_input":
        return "manual_review_required"
    if warnings:
        return "manual_review_required"
    if _manual_review_required(*results) and package_status != "review_ready":
        return "manual_review_required"
    return package_status or "manual_review_required"


def _collect_warnings(
    warnings: Sequence[str],
    package_payload: Mapping[str, Any],
    readback: Mapping[str, Any],
) -> list[str]:
    collected: list[str] = list(warnings)
    collected.extend(package_payload.get("package_warnings") or [])
    warning_section = readback.get("warning_section")
    if isinstance(warning_section, Mapping):
        collected.extend(warning_section.get("warnings") or [])
    return _unique_texts(collected)


def _traceability(
    *,
    user_intent: Any,
    evidence_records: Sequence[Mapping[str, Any]],
    component_records: Sequence[Mapping[str, Any]],
    route_draft: Mapping[str, Any],
    evidence_result: Mapping[str, Any],
    component_result: Mapping[str, Any],
    queue_result: Mapping[str, Any],
    package_payload: Mapping[str, Any],
    readback: Mapping[str, Any],
) -> dict[str, Any]:
    package_traceability = package_payload.get("traceability")
    readback_traceability = readback.get("traceability_section")
    return {
        "chain_runner_version": CHAIN_RUNNER_VERSION,
        "input_summary": {
            "user_intent_type": type(user_intent).__name__,
            "evidence_record_count": len(evidence_records),
            "component_record_count": len(component_records),
        },
        "source_payloads_present": {
            "route_draft": bool(route_draft),
            "evidence_slot_match_result": bool(evidence_result),
            "component_candidate_match_result": bool(component_result),
            "gap_manual_review_queue_result": bool(queue_result),
            "plant_review_package": bool(package_payload),
            "readback_presenter": bool(readback),
        },
        "upstream_statuses": {
            "route_draft": _status_value(route_draft, "draft_status"),
            "evidence_slot_match_result": _status_value(evidence_result, "matcher_status"),
            "component_candidate_match_result": _status_value(component_result, "matcher_status"),
            "gap_manual_review_queue_result": _status_value(queue_result, "queue_status"),
            "plant_review_package": _status_value(package_payload, "package_status"),
            "readback_presenter": _status_value(_mapping(readback.get("package_header")), "package_status"),
        },
        "package_traceability": _plain_value(package_traceability if isinstance(package_traceability, Mapping) else {}),
        "readback_traceability": _plain_value(readback_traceability if isinstance(readback_traceability, Mapping) else {}),
    }


def run_plant_review_workflow_chain(
    user_intent: Mapping[str, Any] | Sequence[Any] | str | None,
    evidence_records: Sequence[Mapping[str, Any] | str] | Mapping[str, Any] | str | None,
    component_records: Sequence[Mapping[str, Any] | str] | Mapping[str, Any] | str | None,
    context: Mapping[str, Any] | str | None = None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the R68-R75 Plant review chain and return a deterministic plain payload."""
    warnings: list[str] = []
    normalized_evidence, evidence_warnings = _normalize_evidence_input(evidence_records)
    normalized_components, component_warnings = _normalize_component_input(component_records)
    warnings.extend(evidence_warnings)
    warnings.extend(component_warnings)

    context_data = _context_payload(user_intent, context)
    option_data = _options_payload(options)
    package_metadata = _mapping(option_data.get("package_metadata"))
    package_metadata.setdefault("review_batch", "R76")
    package_metadata.setdefault("chain_schema_version", CHAIN_SCHEMA_VERSION)
    presenter_options = _mapping(option_data.get("presenter_options"))

    route_input: Mapping[str, Any] | str
    if isinstance(user_intent, (Mapping, str)):
        route_input = user_intent
    else:
        route_input = {}
        if user_intent not in (None, [], ()):
            warnings.append("input warning: unsupported user intent payload was routed to safe empty review")

    route_draft = _run_step(
        "R68 route draft",
        warnings,
        lambda: build_plant_expression_route_draft(route_input),
    )
    evidence_slot_match_result = _run_step(
        "R69 evidence slot matcher",
        warnings,
        lambda: match_plant_evidence_to_slots(route_draft, normalized_evidence, context_data),
    )
    component_candidate_match_result = _run_step(
        "R70 component candidate matcher",
        warnings,
        lambda: match_plant_component_candidates(
            route_draft,
            evidence_slot_match_result,
            normalized_components,
            context_data,
        ),
    )
    gap_manual_review_queue_result = _run_step(
        "R72 gap manual review queue",
        warnings,
        lambda: build_plant_gap_manual_review_queue(
            route_draft,
            evidence_slot_match_result,
            component_candidate_match_result,
            context_data,
        ),
    )
    plant_review_package = _run_step(
        "R74 Plant review package",
        warnings,
        lambda: build_plant_review_package(
            route_draft,
            evidence_slot_match_result,
            component_candidate_match_result,
            gap_manual_review_queue_result,
            package_metadata=package_metadata,
            user_context=context_data,
        ),
    )
    readback_presenter = _run_step(
        "R75 readback presenter",
        warnings,
        lambda: build_plant_review_package_readback_presenter(plant_review_package, presenter_options),
    )
    collected_warnings = _collect_warnings(warnings, plant_review_package, readback_presenter)
    status = _chain_status(
        route_draft=route_draft,
        evidence_result=evidence_slot_match_result,
        component_result=component_candidate_match_result,
        queue_result=gap_manual_review_queue_result,
        package_payload=plant_review_package,
        readback=readback_presenter,
        warnings=collected_warnings,
    )
    blocked = status == "blocked"
    manual_review_required = blocked or _manual_review_required(
        route_draft,
        evidence_slot_match_result,
        component_candidate_match_result,
        gap_manual_review_queue_result,
        plant_review_package,
    )

    return _plain_value(
        {
            "chain_schema_version": CHAIN_SCHEMA_VERSION,
            "chain_runner_version": CHAIN_RUNNER_VERSION,
            "chain_status": status,
            "route_draft": route_draft,
            "evidence_slot_match_result": evidence_slot_match_result,
            "component_candidate_match_result": component_candidate_match_result,
            "gap_manual_review_queue_result": gap_manual_review_queue_result,
            "plant_review_package": plant_review_package,
            "readback_presenter": readback_presenter,
            "manual_review_required": manual_review_required,
            "blocked": blocked,
            "warnings": collected_warnings,
            "traceability": _traceability(
                user_intent=user_intent,
                evidence_records=normalized_evidence,
                component_records=normalized_components,
                route_draft=route_draft,
                evidence_result=evidence_slot_match_result,
                component_result=component_candidate_match_result,
                queue_result=gap_manual_review_queue_result,
                package_payload=plant_review_package,
                readback=readback_presenter,
            ),
            "boundary_note": CHAIN_BOUNDARY_NOTE,
        }
    )
