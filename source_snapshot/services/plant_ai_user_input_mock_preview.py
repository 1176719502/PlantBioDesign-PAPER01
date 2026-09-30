from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_ai_mock_preview_contracts import (
    BLOCKED_OUTPUT_BOUNDARY,
    STABLE_PREVIEW_CONTRACT_KEYS,
    SUPPORTED_PLANT_PREVIEW_CATEGORIES,
    allowed_output_boundary,
    boundary_statement_rows,
    normalize_boundary_statements,
    output_rows,
    preview_status,
    sequence,
    status_label,
    text,
)
from services.plant_ai_intake_safety_router import route_ai_intake_request
from services.plant_ai_intake_mock_parser import MISSING_FIELDS


USER_INPUT_MOCK_PREVIEW_VERSION = "plant_ai_user_input_mock_preview.v2.7.r108"
USER_INPUT_MOCK_PREVIEW_BATCH = "v2.7-r108"

DEFAULT_USER_INPUT_MOCK_REQUEST = (
    "Please prepare a documentation-only plant design review preview for an albumin-like protein "
    "in rice seed for a company-facing handoff draft."
)

USER_INPUT_MOCK_TITLE = "User-input Plant Design Mock Preview"
USER_INPUT_MOCK_SUBTITLE = "Deterministic, unsaved mock preview from the current text input"
USER_INPUT_MOCK_BOUNDARY = (
    "This preview is deterministic and documentation-only. It reads the current text input, routes scope, "
    "and displays review fields without calling AI services, writing records, exporting files, selecting "
    "components, scoring components, generating sequence content, or judging wet-lab use."
)

def _text(value: Any, fallback: str = "") -> str:
    return text(value, fallback)


def _sequence(value: Any) -> list[Any]:
    return sequence(value)


def _field_rows(pairs: Sequence[tuple[str, Any]]) -> list[dict[str, str]]:
    return [{"Field": label, "Readback": status_label(value)} for label, value in pairs]


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in terms)


def _parsed_preview_fields(request_text: str) -> dict[str, str]:
    lowered = request_text.casefold()
    plant_host = "rice" if _contains_any(lowered, ("rice", "oryza")) else "plant context not specified"
    tissue = "seed" if "seed" in lowered else "not specified"
    target = "albumin-like protein" if "albumin" in lowered else "not specified"
    handoff_goal = (
        "company-facing handoff draft"
        if _contains_any(lowered, ("company", "handoff", "evaluation package"))
        else "plant design review draft"
    )
    return {
        "plant_host": plant_host,
        "tissue_or_context": tissue,
        "target": target,
        "handoff_goal": handoff_goal,
    }


def _workflow_route(scope_category: str) -> str:
    if scope_category == "non_plant_out_of_scope":
        return "Route out of Plant Design Workspace; show conceptual context only."
    if scope_category in {"blocked_wet_lab_execution", "blocked_final_sequence_or_primer"}:
        return "Blocked in Plant Design Workspace; show boundary and safer reframing only."
    if scope_category == "mixed_scope_needs_routing":
        return "Show safe plant review fields and block operational or final-design outputs."
    if scope_category in SUPPORTED_PLANT_PREVIEW_CATEGORIES:
        return "Supported plant review mock preview."
    return "Conceptual-only review route."


def _review_gap_rows(scope_category: str, parsed_fields: Mapping[str, str]) -> list[dict[str, str]]:
    rows = [
        {
            "Review item": "source evidence",
            "Reason": "evidence references remain missing",
            "Status": "manual review required",
        },
        {
            "Review item": "component provenance",
            "Reason": "component provenance remains missing",
            "Status": "manual review required",
        },
        {
            "Review item": "vector/backbone context",
            "Reason": "vector/backbone context remains missing",
            "Status": "manual review required",
        },
    ]
    if parsed_fields.get("tissue_or_context") == "not specified":
        rows.append(
            {
                "Review item": "plant context",
                "Reason": "tissue or context was not detected by the deterministic mock parser",
                "Status": "manual review required",
            }
        )
    if scope_category == "mixed_scope_needs_routing":
        rows.append(
            {
                "Review item": "blocked request fragment",
                "Reason": "safe design-review fields are separated from blocked operational wording",
                "Status": "blocked fragment retained as review note",
            }
        )
    return rows


def build_user_input_mock_preview_payload(raw_user_request: Any = DEFAULT_USER_INPUT_MOCK_REQUEST) -> dict[str, Any]:
    """Build a deterministic read-only preview from current user text without persistence or AI calls."""
    request_text = _text(raw_user_request) or DEFAULT_USER_INPUT_MOCK_REQUEST
    scope_decision = dict(route_ai_intake_request(request_text))
    scope_category = _text(scope_decision.get("scope_category"), "safe_conceptual_explanation")
    parsed_fields = _parsed_preview_fields(request_text)
    show_parsed_fields = scope_category in SUPPORTED_PLANT_PREVIEW_CATEGORIES or scope_category == "mixed_scope_needs_routing"
    non_plant = scope_category == "non_plant_out_of_scope"
    blocked = scope_category in {"blocked_wet_lab_execution", "blocked_final_sequence_or_primer"}
    allowed_outputs = _sequence(scope_decision.get("allowed_outputs"))
    blocked_outputs = _sequence(scope_decision.get("blocked_outputs"))
    boundary_statements = normalize_boundary_statements(scope_decision.get("boundary_statements"), USER_INPUT_MOCK_BOUNDARY)
    parsed_intent_rows = (
        _field_rows(
            [
                ("Plant host", parsed_fields["plant_host"]),
                ("Tissue/context", parsed_fields["tissue_or_context"]),
                ("Target", parsed_fields["target"]),
                ("Handoff goal", parsed_fields["handoff_goal"]),
            ]
        )
        if show_parsed_fields
        else []
    )

    payload = {
        "preview_version": USER_INPUT_MOCK_PREVIEW_VERSION,
        "batch": USER_INPUT_MOCK_PREVIEW_BATCH,
        "title": USER_INPUT_MOCK_TITLE,
        "subtitle": USER_INPUT_MOCK_SUBTITLE,
        "boundary_note": USER_INPUT_MOCK_BOUNDARY,
        "source_request": request_text,
        "read_only_preview": True,
        "persistent": False,
        "scope_category": scope_category,
        "preview_status": preview_status(scope_category),
        "allowed_outputs": allowed_outputs,
        "blocked_outputs": blocked_outputs,
        "boundary_statements": boundary_statements,
        "workflow_route": _workflow_route(scope_category),
        "status_badges": [
            {"label": "Mock status", "value": preview_status(scope_category), "tone": "attention" if blocked else "neutral"},
            {"label": "Workflow route", "value": "out of plant workflow" if non_plant else "Plant Design Workspace", "tone": "attention" if non_plant else "neutral"},
            {"label": "Preview mode", "value": "deterministic and unsaved", "tone": "neutral"},
            {"label": "Manual review", "value": "required", "tone": "attention"},
        ],
        "request_scope_rows": _field_rows(
            [
                ("Current input", request_text),
                ("Scope decision", scope_category),
                ("Workflow route", _workflow_route(scope_category)),
                ("Safe next step", scope_decision.get("safe_next_step")),
                ("AI/API use", "none"),
                ("Persistence", "none"),
            ]
        ),
        "allowed_output_rows": output_rows(allowed_outputs, allowed_output_boundary(scope_category)),
        "blocked_output_rows": output_rows(blocked_outputs, BLOCKED_OUTPUT_BOUNDARY),
        "parsed_intent_rows": parsed_intent_rows,
        "missing_information_rows": [
            {
                "Missing information": field,
                "Why this is still open": "manual review required before company-facing use",
            }
            for field in MISSING_FIELDS
        ]
        if show_parsed_fields
        else [],
        "review_gap_rows": _review_gap_rows(scope_category, parsed_fields) if show_parsed_fields else [],
        "boundary_statement_rows": boundary_statement_rows(boundary_statements),
        "route_out_rows": _field_rows(
            [
                ("Non-plant route", "out of Plant Design Workspace"),
                ("Allowed display", "conceptual context only"),
                ("Manual review", "required"),
            ]
        )
        if non_plant
        else [],
        "blocked_notice_rows": _field_rows(
            [
                ("Blocked status", preview_status(scope_category)),
                ("Displayed output", "boundary note only plus safer reframing"),
                ("Manual review", "required"),
            ]
        )
        if blocked
        else [],
        "empty_state": {
            "is_empty": False,
            "message": "",
            "manual_review_required": True,
        },
    }
    assert set(STABLE_PREVIEW_CONTRACT_KEYS).issubset(payload)
    return payload
