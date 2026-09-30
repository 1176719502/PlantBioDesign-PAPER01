from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable

from services.plant_review_handoff_data_adapter import build_plant_review_handoff_payload
from services.plant_review_package_readback_presenter import build_plant_review_package_readback_presenter
from services.plant_review_workflow_chain_runner import run_plant_review_workflow_chain
from services.plant_workflow_input_adapter import prepare_plant_review_workflow_input
from services.plant_workspace_state_input_extractor import extract_plant_workflow_project_payload


WORKSPACE_WORKFLOW_SCHEMA_VERSION = "plant_review_workspace_workflow.v2.7.r83"
WORKSPACE_WORKFLOW_BATCH = "v2.7-r83"


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


def _run_step(label: str, warnings: list[str], step: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        result = step()
    except Exception as exc:  # pragma: no cover - defensive safe-partial boundary
        warnings.append(f"{label} warning: workspace workflow step failed safe with {exc.__class__.__name__}")
        return {}
    if not isinstance(result, Mapping):
        warnings.append(f"{label} warning: workspace workflow step returned malformed payload")
        return {}
    return dict(result)


def _chain_context(adapter_input: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    chain_options = _mapping(adapter_input.get("chain_options"))
    return _mapping(chain_options.get("context")), _mapping(chain_options.get("options"))


def _presenter_sections(chain_result: Mapping[str, Any], options: Mapping[str, Any], warnings: list[str]) -> dict[str, Any]:
    readback = chain_result.get("readback_presenter")
    if isinstance(readback, Mapping) and readback:
        return dict(readback)
    presenter_options = _mapping(options.get("presenter_options"))
    return _run_step(
        "R75 presenter",
        warnings,
        lambda: build_plant_review_package_readback_presenter(
            _mapping(chain_result.get("plant_review_package")),
            presenter_options,
        ),
    )


def _blocked(
    extractor_result: Mapping[str, Any],
    adapter_input: Mapping[str, Any],
    chain_result: Mapping[str, Any],
    handoff_payload: Mapping[str, Any],
) -> bool:
    if _text(extractor_result.get("extractor_status")) == "empty_or_invalid_workspace_state":
        return False
    adapter_status = _text(adapter_input.get("adapter_status"))
    return (
        adapter_status == "unsupported_or_manual_review"
        or bool(chain_result.get("blocked"))
        or _text(handoff_payload.get("handoff_status")) == "blocked"
    )


def _manual_review_required(*payloads: Mapping[str, Any]) -> bool:
    return any(bool(payload.get("manual_review_required")) for payload in payloads if isinstance(payload, Mapping))


def _workflow_status(*, blocked: bool, manual_review_required: bool, warnings: Sequence[str]) -> str:
    if blocked:
        return "blocked"
    if manual_review_required or warnings:
        return "manual_review_required"
    return "review_ready"


def _collect_warnings(*payloads: Mapping[str, Any], local_warnings: Sequence[str]) -> list[str]:
    warnings: list[str] = list(local_warnings)
    for payload in payloads:
        warnings.extend(_list(payload.get("warnings")))
    return _unique_texts(warnings)


def _traceability(
    *,
    extractor_result: Mapping[str, Any],
    adapter_input: Mapping[str, Any],
    chain_result: Mapping[str, Any],
    handoff_payload: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "workflow_batch": WORKSPACE_WORKFLOW_BATCH,
        "workspace_workflow_schema_version": WORKSPACE_WORKFLOW_SCHEMA_VERSION,
        "extractor_traceability": _mapping(extractor_result.get("traceability")),
        "adapter_traceability": _mapping(adapter_input.get("traceability")),
        "chain_traceability": _mapping(chain_result.get("traceability")),
        "handoff_source_traceability": _mapping(handoff_payload.get("source_traceability")),
        "upstream_statuses": {
            "extractor": _text(extractor_result.get("extractor_status")),
            "adapter": _text(adapter_input.get("adapter_status")),
            "chain": _text(chain_result.get("chain_status")),
            "handoff": _text(handoff_payload.get("handoff_status")),
        },
    }


def build_plant_review_workspace_workflow(
    workspace_state: Mapping[str, Any] | Sequence[Any] | None,
    options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the read-only Plant review workspace workflow from local workspace-like state."""
    option_data = _mapping(options)
    warnings: list[str] = []
    extractor_result = _run_step(
        "R82 extractor",
        warnings,
        lambda: extract_plant_workflow_project_payload(
            workspace_state,
            _mapping(option_data.get("extractor_options")),
        ),
    )
    project_payload = _mapping(extractor_result.get("project_payload"))
    adapter_input = _run_step(
        "R81 input adapter",
        warnings,
        lambda: prepare_plant_review_workflow_input(
            project_payload,
            _mapping(option_data.get("adapter_options")),
        ),
    )
    context, chain_options = _chain_context(adapter_input)
    chain_result = _run_step(
        "R76 chain runner",
        warnings,
        lambda: run_plant_review_workflow_chain(
            adapter_input.get("user_intent"),
            _list(adapter_input.get("evidence_records")),
            _list(adapter_input.get("component_records")),
            context,
            chain_options,
        ),
    )
    presenter_sections = _presenter_sections(chain_result, chain_options, warnings)
    chain_for_handoff = dict(chain_result)
    chain_for_handoff["readback_presenter"] = presenter_sections
    handoff_preview_payload = _run_step(
        "R79 handoff adapter",
        warnings,
        lambda: build_plant_review_handoff_payload(
            chain_for_handoff,
            _mapping(option_data.get("handoff_context")),
        ),
    )

    all_warnings = _collect_warnings(
        extractor_result,
        adapter_input,
        chain_result,
        handoff_preview_payload,
        local_warnings=warnings,
    )
    blocked = _blocked(extractor_result, adapter_input, chain_result, handoff_preview_payload)
    manual_review_required = blocked or _manual_review_required(
        extractor_result,
        adapter_input,
        chain_result,
        handoff_preview_payload,
    )

    return _plain_value(
        {
            "workspace_workflow_schema_version": WORKSPACE_WORKFLOW_SCHEMA_VERSION,
            "workspace_workflow_batch": WORKSPACE_WORKFLOW_BATCH,
            "workflow_status": _workflow_status(
                blocked=blocked,
                manual_review_required=manual_review_required,
                warnings=all_warnings,
            ),
            "project_payload": project_payload,
            "adapter_input": adapter_input,
            "chain_result": chain_result,
            "presenter_sections": presenter_sections,
            "handoff_preview_payload": handoff_preview_payload,
            "manual_review_required": manual_review_required,
            "blocked": blocked,
            "warnings": all_warnings,
            "traceability": _traceability(
                extractor_result=extractor_result,
                adapter_input=adapter_input,
                chain_result=chain_result,
                handoff_payload=handoff_preview_payload,
            ),
        }
    )
