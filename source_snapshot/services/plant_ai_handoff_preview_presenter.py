from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_ai_mock_preview_contracts import (
    ALLOWED_OUTPUT_BOUNDARY_DOCUMENTATION,
    STABLE_PREVIEW_CONTRACT_KEYS,
    status_label,
    text,
)
from services.plant_ai_preview_row_builder import build_preview_contract_rows, field_rows
from services.plant_ai_guided_domain_chain import build_rice_albumin_like_domain_chain
from services.plant_ai_intake_mock_parser import RICE_ALBUMIN_LIKE_REQUEST
from services.plant_company_handoff_draft_assembler import assemble_company_handoff_draft


HANDOFF_PREVIEW_PRESENTER_VERSION = "plant_ai_handoff_preview_presenter.v2.7.r113"
HANDOFF_PREVIEW_PRESENTER_BATCH = "v2.7-r113"

PREVIEW_TITLE = "AI-guided Plant Design Handoff Preview"
PREVIEW_SUBTITLE = "Fixed rice albumin-like read-only mock preview - deterministic fixture - manual review required"
PREVIEW_BOUNDARY_NOTE = (
    "Read-only UI preview for the fixed rice albumin-like company handoff draft. It displays deterministic "
    "R99-R102 review data for manual review only; it does not call an AI service, write project records, "
    "export files, generate sequences, create operational oligo records, rank components, score components, "
    "or judge wet-lab use."
)


def _text(value: Any, fallback: str = "") -> str:
    return text(value, fallback)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _yes_no(value: Any) -> str:
    return "yes" if value is True else "no" if value is False else "not recorded"


def _status_label(value: Any, fallback: str = "not recorded") -> str:
    return status_label(value, fallback)


def _join_values(value: Any) -> str:
    items = [_text(item) for item in _sequence(value)]
    items = [item for item in items if item]
    return ", ".join(items) if items else _text(value, "not recorded")


def _section_by_id(handoff_draft: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    sections: dict[str, dict[str, Any]] = {}
    for section in _sequence(handoff_draft.get("sections")):
        item = _mapping(section)
        section_id = _text(item.get("section_id"))
        if section_id:
            sections[section_id] = item
    return sections


def _missing_information_rows(fields: Sequence[Any]) -> list[dict[str, str]]:
    return [
        {
            "Missing information": _text(field, "not recorded"),
            "Why this is still open": "manual review required before any company-facing use",
        }
        for field in fields
        if _text(field)
    ]


def _evidence_rows(records: Sequence[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in records:
        item = _mapping(record)
        if not item:
            continue
        rows.append(
            {
                "Evidence id": _text(item.get("evidence_id"), "not recorded"),
                "Title": _text(item.get("title"), "not recorded"),
                "Source type": _status_label(item.get("source_type")),
                "Source status": _status_label(item.get("source_status")),
                "Review status": _status_label(item.get("review_status"), "manual review required"),
            }
        )
    return rows


def _component_placeholder_rows(records: Sequence[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for record in records:
        item = _mapping(record)
        if not item:
            continue
        rows.append(
            {
                "Component id": _text(item.get("component_id"), "not recorded"),
                "Label": _text(item.get("component_name"), "not recorded"),
                "Component type": _status_label(item.get("component_type")),
                "Source species": _text(item.get("source_species"), "not recorded"),
                "Sequence/documentation status": _status_label(item.get("sequence_status")),
                "Manual notes": _text(item.get("manual_notes"), "manual review required"),
            }
        )
    return rows


def _slot_rows(section: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _sequence(section.get("rows")):
        item = _mapping(row)
        if not item:
            continue
        rows.append(
            {
                "Slot id": _text(item.get("slot_id"), "not recorded"),
                "Slot type": _status_label(item.get("slot_type")),
                "Label": _text(item.get("label"), "not recorded"),
                "Draft status": _status_label(item.get("slot_status")),
                "Selected component": _text(item.get("selected_component_id"), "not recorded"),
                "Candidate placeholders": _join_values(item.get("candidate_component_ids")),
                "Manual review": _yes_no(item.get("manual_review_required")),
            }
        )
    return rows


def _construct_rows(section: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _sequence(section.get("rows")):
        item = _mapping(row)
        if not item:
            continue
        rows.append(
            {
                "Draft id": _text(item.get("draft_id"), "not recorded"),
                "Slot id": _text(item.get("slot_id"), "not recorded"),
                "Slot type": _status_label(item.get("slot_type")),
                "Missing reason": _text(item.get("missing_reason"), "manual review required"),
                "Manual review": _yes_no(item.get("manual_review_required")),
            }
        )
    return rows


def _review_rows(section: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _sequence(section.get("rows")):
        item = _mapping(row)
        if not item:
            continue
        rows.append(
            {
                "Review item": _text(item.get("review_item_id"), _text(item.get("check"), "not recorded")),
                "Type": _status_label(item.get("review_type"), _status_label(item.get("status"))),
                "Severity": _status_label(item.get("severity"), "manual review"),
                "Message": _text(item.get("message"), _text(item.get("check"), "manual review required")),
                "Review status": _status_label(item.get("status"), "manual review required"),
            }
        )
    return rows


def _handoff_section_rows(handoff_draft: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for section in _sequence(handoff_draft.get("sections")):
        item = _mapping(section)
        if not item:
            continue
        rows.append(
            {
                "Section id": _text(item.get("section_id"), "not recorded"),
                "Title": _text(item.get("title"), "not recorded"),
                "Summary": _text(item.get("summary"), "manual review draft section"),
                "Rows": str(len(_sequence(item.get("rows")))),
                "Manual review": _yes_no(item.get("manual_review_required")),
            }
        )
    return rows


def _empty_payload(reason: str) -> dict[str, Any]:
    shared_contract = build_preview_contract_rows(
        scope_category="company_handoff_request",
        allowed_outputs=[],
        blocked_outputs=[],
        boundary_statements=[PREVIEW_BOUNDARY_NOTE],
        persistent=False,
        allowed_output_boundary_label=ALLOWED_OUTPUT_BOUNDARY_DOCUMENTATION,
    )
    return {
        "presenter_version": HANDOFF_PREVIEW_PRESENTER_VERSION,
        "batch": HANDOFF_PREVIEW_PRESENTER_BATCH,
        "title": PREVIEW_TITLE,
        "subtitle": PREVIEW_SUBTITLE,
        "boundary_note": PREVIEW_BOUNDARY_NOTE,
        "source_request": RICE_ALBUMIN_LIKE_REQUEST,
        "read_only": True,
        "scope_category": "company_handoff_request",
        **shared_contract,
        "status_badges": [
            {"label": "Preview status", "value": "empty", "tone": "attention"},
            {"label": "Manual review", "value": "required", "tone": "attention"},
            {"label": "Output mode", "value": "read-only mock", "tone": "neutral"},
        ],
        "request_scope_rows": field_rows(
            [
                ("Original user request", RICE_ALBUMIN_LIKE_REQUEST),
                ("Preview status", "empty"),
                ("Reason", reason or "handoff draft unavailable"),
            ]
        ),
        "design_intent_rows": [],
        "plant_context_rows": [],
        "missing_information_rows": [],
        "evidence_placeholder_rows": [],
        "component_placeholder_rows": [],
        "component_candidate_rows": [],
        "construct_slot_rows": [],
        "review_gap_rows": [],
        "manual_checklist_rows": [],
        "handoff_section_rows": [],
        "manual_review_status_rows": field_rows([("Manual review", "required"), ("Preview status", "empty")]),
        "empty_state": {
            "is_empty": True,
            "message": "The fixed rice albumin-like handoff draft is unavailable. The preview remains read-only.",
            "manual_review_required": True,
        },
    }


def build_rice_albumin_handoff_preview_payload(
    domain_bundle: Mapping[str, Any] | None = None,
    handoff_draft: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a UI-safe read-only payload from the existing R101/R102 rice albumin handoff draft."""
    try:
        bundle = (
            build_rice_albumin_like_domain_chain(RICE_ALBUMIN_LIKE_REQUEST)
            if domain_bundle is None
            else _mapping(domain_bundle)
        )
        draft = assemble_company_handoff_draft(bundle) if handoff_draft is None else _mapping(handoff_draft)
    except Exception as exc:  # pragma: no cover - exercised defensively by UI callers.
        return _empty_payload(_text(exc, "handoff draft unavailable"))

    if not draft:
        return _empty_payload("handoff draft unavailable")

    scope_decision = _mapping(bundle.get("scope_decision"))
    intent = _mapping(bundle.get("design_intent"))
    context = _mapping(bundle.get("plant_context"))
    construct_draft = _mapping(bundle.get("construct_draft"))
    sections = _section_by_id(draft)
    scope_category = _text(scope_decision.get("scope_category"), "company_handoff_request")
    shared_contract = build_preview_contract_rows(
        scope_category=scope_category,
        allowed_outputs=scope_decision.get("allowed_outputs"),
        blocked_outputs=scope_decision.get("blocked_outputs"),
        boundary_statements=[
            bundle.get("boundary_statements"),
            draft.get("boundary_labels"),
            PREVIEW_BOUNDARY_NOTE,
        ],
        parsed_intent_pairs=[
            ("Plant host", intent.get("plant_host")),
            ("Tissue/context", intent.get("tissue_or_context")),
            ("Target", intent.get("target_name")),
            ("Handoff goal", intent.get("handoff_goal")),
        ],
        persistent=False,
        allowed_output_boundary_label=ALLOWED_OUTPUT_BOUNDARY_DOCUMENTATION,
    )

    payload = {
        "presenter_version": HANDOFF_PREVIEW_PRESENTER_VERSION,
        "batch": HANDOFF_PREVIEW_PRESENTER_BATCH,
        "title": PREVIEW_TITLE,
        "subtitle": PREVIEW_SUBTITLE,
        "boundary_note": PREVIEW_BOUNDARY_NOTE,
        "source_request": _text(draft.get("source_request"), RICE_ALBUMIN_LIKE_REQUEST),
        "read_only": True,
        "scope_category": scope_category,
        **shared_contract,
        "status_badges": [
            {"label": "Preview status", "value": shared_contract["preview_status"], "tone": "neutral"},
            {"label": "Preview source", "value": "fixed rice albumin-like request", "tone": "neutral"},
            {"label": "Manual review", "value": "required", "tone": "attention"},
            {"label": "Package label", "value": _text(draft.get("package_label"), "company-facing design evaluation draft"), "tone": "neutral"},
            {"label": "Boundary", "value": "documentation-only, non-operational", "tone": "attention"},
            {"label": "Construct output", "value": "draft slots only", "tone": "attention"},
        ],
        "request_scope_rows": field_rows(
            [
                ("Original user request", draft.get("source_request")),
                ("Safety / scope decision", _status_label(scope_decision.get("scope_category"))),
                ("Safe next step", scope_decision.get("safe_next_step")),
                ("AI output status", _status_label(scope_decision.get("ai_output_status"))),
                ("Manual review", _yes_no(scope_decision.get("manual_review_required"))),
            ]
        ),
        "design_intent_rows": field_rows(
            [
                ("Intent id", intent.get("intent_id")),
                ("Target", intent.get("target_name")),
                ("Target type", intent.get("target_type")),
                ("Plant host", intent.get("plant_host")),
                ("Tissue/context", intent.get("tissue_or_context")),
                ("Design purpose", intent.get("design_purpose")),
                ("Handoff goal", intent.get("handoff_goal")),
                ("Scope status", _status_label(intent.get("scope_status"))),
                ("Manual review", _yes_no(intent.get("manual_review_required"))),
            ]
        ),
        "plant_context_rows": field_rows(
            [
                ("Context id", context.get("context_id")),
                ("Plant species", context.get("plant_species")),
                ("Tissue/organ", context.get("tissue_or_organ")),
                ("Expression context", context.get("expression_context")),
                ("Subcellular localization", context.get("subcellular_localization")),
                ("Target product type", context.get("target_product_type")),
                ("Uncertainty flags", context.get("uncertainty_flags")),
                ("Review status", _status_label(context.get("review_status"))),
            ]
        ),
        "missing_information_rows": _missing_information_rows(_sequence(intent.get("missing_fields"))),
        "evidence_placeholder_rows": _evidence_rows(_sequence(bundle.get("evidence_placeholders"))),
        "component_placeholder_rows": _component_placeholder_rows(_sequence(bundle.get("component_placeholders"))),
        "component_candidate_rows": _slot_rows(sections.get("component_candidate_slot_table", {})),
        "construct_slot_rows": _construct_rows(sections.get("construct_draft_slot_scaffold", {})),
        "review_gap_rows": _review_rows(sections.get("review_gap_items", {})),
        "manual_checklist_rows": _review_rows(sections.get("manual_review_checklist", {})),
        "handoff_section_rows": _handoff_section_rows(draft),
        "manual_review_status_rows": field_rows(
            [
                ("Package status", draft.get("package_status")),
                ("Manual review", _yes_no(draft.get("manual_review_required"))),
                ("Package label", draft.get("package_label")),
                ("Source chain version", draft.get("source_chain_version")),
                ("Assembler batch", draft.get("batch")),
                ("Construct draft status", construct_draft.get("draft_status")),
            ]
        ),
        "empty_state": {
            "is_empty": False,
            "message": "",
            "manual_review_required": True,
        },
    }
    assert set(STABLE_PREVIEW_CONTRACT_KEYS).issubset(payload)
    return payload
