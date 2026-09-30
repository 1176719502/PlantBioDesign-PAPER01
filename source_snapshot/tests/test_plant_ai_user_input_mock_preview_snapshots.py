# -*- coding: utf-8 -*-
from __future__ import annotations

from services.plant_ai_user_input_mock_preview import build_user_input_mock_preview_payload


SUPPORTED_RICE_ALBUMIN_INPUT = "Prepare a company handoff draft for an albumin-like protein in rice seed."
BLOCKED_WET_LAB_INPUT = "Give me a rice transformation protocol with cloning steps."
NON_PLANT_INPUT = "Build a yeast expression workflow for a protein."
MIXED_SAFE_AND_BLOCKED_INPUT = (
    "Prepare a company handoff draft for rice seed albumin-like expression and include cloning protocol steps."
)

EXPECTED_BLOCKED_OUTPUTS = [
    "wet lab protocol",
    "cloning steps",
    "transformation steps",
    "culture conditions",
    "primer design",
    "synthesis ready sequence",
    "final construct recommendation",
    "component ranking",
    "yield prediction",
    "success guarantee",
    "wet lab readiness claim",
]


def _field_map(rows: list[dict[str, str]]) -> dict[str, str]:
    return {row["Field"]: row["Readback"] for row in rows}


def _outputs(rows: list[dict[str, str]]) -> list[str]:
    return [row["Output"] for row in rows]


def _snapshot(payload: dict[str, object]) -> dict[str, object]:
    return {
        "scope_category": payload["scope_category"],
        "preview_status": payload["preview_status"],
        "workflow_route": payload["workflow_route"],
        "persistent": payload["persistent"],
        "read_only_preview": payload["read_only_preview"],
        "request_scope": _field_map(payload["request_scope_rows"]),
        "allowed_outputs": _outputs(payload["allowed_output_rows"]),
        "blocked_outputs": _outputs(payload["blocked_output_rows"]),
        "parsed_intent": _field_map(payload["parsed_intent_rows"]),
        "route_out": _field_map(payload["route_out_rows"]),
        "blocked_notice": _field_map(payload["blocked_notice_rows"]),
        "review_items": [row["Review item"] for row in payload["review_gap_rows"]],
    }


def test_r109_supported_rice_albumin_like_input_snapshot() -> None:
    payload = build_user_input_mock_preview_payload(SUPPORTED_RICE_ALBUMIN_INPUT)

    assert _snapshot(payload) == {
        "scope_category": "company_handoff_request",
        "preview_status": "supported plant mock preview",
        "workflow_route": "Supported plant review mock preview.",
        "persistent": False,
        "read_only_preview": True,
        "request_scope": {
            "Current input": SUPPORTED_RICE_ALBUMIN_INPUT,
            "Scope decision": "company handoff request",
            "Workflow route": "Supported plant review mock preview.",
            "Safe next step": "Prepare a company-facing design evaluation draft with placeholders and manual review items.",
            "AI/API use": "none",
            "Persistence": "none",
        },
        "allowed_outputs": [
            "design intent",
            "plant design context",
            "evidence placeholders",
            "component slots",
            "construct draft slots",
            "review items",
            "report blocks",
            "company handoff draft",
        ],
        "blocked_outputs": EXPECTED_BLOCKED_OUTPUTS,
        "parsed_intent": {
            "Plant host": "rice",
            "Tissue/context": "seed",
            "Target": "albumin-like protein",
            "Handoff goal": "company-facing handoff draft",
        },
        "route_out": {},
        "blocked_notice": {},
        "review_items": ["source evidence", "component provenance", "vector/backbone context"],
    }


def test_r109_blocked_wet_lab_protocol_input_snapshot() -> None:
    payload = build_user_input_mock_preview_payload(BLOCKED_WET_LAB_INPUT)

    assert _snapshot(payload) == {
        "scope_category": "blocked_wet_lab_execution",
        "preview_status": "blocked input",
        "workflow_route": "Blocked in Plant Design Workspace; show boundary and safer reframing only.",
        "persistent": False,
        "read_only_preview": True,
        "request_scope": {
            "Current input": BLOCKED_WET_LAB_INPUT,
            "Scope decision": "blocked wet lab execution",
            "Workflow route": "Blocked in Plant Design Workspace; show boundary and safer reframing only.",
            "Safe next step": "Reframe the request as documentation-only plant design review and gap documentation.",
            "AI/API use": "none",
            "Persistence": "none",
        },
        "allowed_outputs": ["safe conceptual summary"],
        "blocked_outputs": EXPECTED_BLOCKED_OUTPUTS,
        "parsed_intent": {},
        "route_out": {},
        "blocked_notice": {
            "Blocked status": "blocked input",
            "Displayed output": "boundary note only plus safer reframing",
            "Manual review": "required",
        },
        "review_items": [],
    }


def test_r109_non_plant_input_snapshot() -> None:
    payload = build_user_input_mock_preview_payload(NON_PLANT_INPUT)

    assert _snapshot(payload) == {
        "scope_category": "non_plant_out_of_scope",
        "preview_status": "non-plant input routed out",
        "workflow_route": "Route out of Plant Design Workspace; show conceptual context only.",
        "persistent": False,
        "read_only_preview": True,
        "request_scope": {
            "Current input": NON_PLANT_INPUT,
            "Scope decision": "non plant out of scope",
            "Workflow route": "Route out of Plant Design Workspace; show conceptual context only.",
            "Safe next step": "Use the main workflow only for plant design review; provide conceptual context separately if useful.",
            "AI/API use": "none",
            "Persistence": "none",
        },
        "allowed_outputs": ["safe conceptual summary"],
        "blocked_outputs": EXPECTED_BLOCKED_OUTPUTS,
        "parsed_intent": {},
        "route_out": {
            "Non-plant route": "out of Plant Design Workspace",
            "Allowed display": "conceptual context only",
            "Manual review": "required",
        },
        "blocked_notice": {},
        "review_items": [],
    }


def test_r109_mixed_safe_and_blocked_input_snapshot() -> None:
    payload = build_user_input_mock_preview_payload(MIXED_SAFE_AND_BLOCKED_INPUT)

    assert _snapshot(payload) == {
        "scope_category": "mixed_scope_needs_routing",
        "preview_status": "mixed input; safe fields only",
        "workflow_route": "Show safe plant review fields and block operational or final-design outputs.",
        "persistent": False,
        "read_only_preview": True,
        "request_scope": {
            "Current input": MIXED_SAFE_AND_BLOCKED_INPUT,
            "Scope decision": "mixed scope needs routing",
            "Workflow route": "Show safe plant review fields and block operational or final-design outputs.",
            "Safe next step": "Return safe design-review outputs while blocking operational or final-design outputs.",
            "AI/API use": "none",
            "Persistence": "none",
        },
        "allowed_outputs": [
            "design intent",
            "plant design context",
            "evidence placeholders",
            "component slots",
            "construct draft slots",
            "review items",
            "report blocks",
            "company handoff draft",
            "safe conceptual summary",
        ],
        "blocked_outputs": EXPECTED_BLOCKED_OUTPUTS,
        "parsed_intent": {
            "Plant host": "rice",
            "Tissue/context": "seed",
            "Target": "albumin-like protein",
            "Handoff goal": "company-facing handoff draft",
        },
        "route_out": {},
        "blocked_notice": {},
        "review_items": [
            "source evidence",
            "component provenance",
            "vector/backbone context",
            "blocked request fragment",
        ],
    }
