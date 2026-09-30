from __future__ import annotations

from typing import Any

from services.plant_ai_guided_domain_chain import build_rice_albumin_like_domain_chain
from services.plant_ai_mock_preview_contracts import (
    HANDOFF_BOUNDARY_LABELS,
    HANDOFF_BOUNDARY_SECTION_STATEMENTS,
    normalize_boundary_statements,
)


HANDOFF_DRAFT_ASSEMBLER_VERSION = "plant_company_handoff_draft_assembler.v2.7.r102"
HANDOFF_DRAFT_ASSEMBLER_BATCH = "v2.7-r102"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _plain_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _section(section_id: str, title: str, rows: list[dict[str, Any]], summary: str = "") -> dict[str, Any]:
    return {
        "section_id": section_id,
        "title": title,
        "summary": summary,
        "rows": rows,
        "manual_review_required": True,
    }


def assemble_company_handoff_draft(domain_bundle: Any = None) -> dict[str, Any]:
    bundle = _plain_mapping(domain_bundle) or build_rice_albumin_like_domain_chain()
    intent = _plain_mapping(bundle.get("design_intent"))
    context = _plain_mapping(bundle.get("plant_context"))
    construct_draft = _plain_mapping(bundle.get("construct_draft"))
    handoff_skeleton = _plain_mapping(bundle.get("handoff_package_skeleton"))

    evidence_rows = [
        {
            "evidence_id": record["evidence_id"],
            "title": record["title"],
            "source_type": record["source_type"],
            "source_status": record["source_status"],
            "review_status": record["review_status"],
        }
        for record in bundle.get("evidence_placeholders", [])
    ]

    component_rows = [
        {
            "slot_id": slot["slot_id"],
            "slot_type": slot["slot_type"],
            "label": slot["label"],
            "slot_status": slot["slot_status"],
            "selected_component_id": slot["selected_component_id"],
            "candidate_component_ids": slot["candidate_component_ids"],
            "manual_review_required": slot["manual_review_required"],
        }
        for slot in bundle.get("construct_slots", [])
    ]

    construct_rows = [
        {
            "draft_id": construct_draft.get("draft_id", ""),
            "slot_id": slot["slot_id"],
            "slot_type": slot["slot_type"],
            "missing_reason": slot["missing_reason"],
            "manual_review_required": slot["manual_review_required"],
        }
        for slot in bundle.get("construct_slots", [])
    ]

    review_rows = [
        {
            "review_item_id": item["review_item_id"],
            "review_type": item["review_type"],
            "severity": item["severity"],
            "message": item["message"],
            "status": item["status"],
        }
        for item in bundle.get("review_gap_items", [])
    ]

    checklist_rows = [
        {"check": "Confirm CDS/source/version provenance", "status": "manual_review_required"},
        {"check": "Confirm rice seed tissue/development context", "status": "manual_review_required"},
        {"check": "Confirm localization context", "status": "manual_review_required"},
        {"check": "Confirm evidence/source matrix", "status": "manual_review_required"},
        {"check": "Confirm vector/backbone context", "status": "manual_review_required"},
        {"check": "Confirm company/expert review signoff path", "status": "manual_review_required"},
    ]

    boundary_rows = [
        {"statement": statement}
        for statement in normalize_boundary_statements(
            bundle.get("boundary_statements", []),
            HANDOFF_BOUNDARY_SECTION_STATEMENTS,
        )
    ]
    identity = _plain_mapping(handoff_skeleton.get("identity"))

    sections = [
        _section(
            "cover_title",
            "Cover / Title",
            [
                {"field": "label", "value": "company-facing design evaluation draft"},
                {"field": "project", "value": "Rice seed albumin-like design review"},
                {"field": "package_id", "value": handoff_skeleton.get("package_id", "")},
            ],
            "Company-facing design evaluation draft for manual expert review.",
        ),
        _section(
            "project_summary",
            "Project Summary",
            [
                {"field": "target", "value": intent.get("target_name", "")},
                {"field": "plant_host", "value": intent.get("plant_host", "")},
                {"field": "tissue_or_context", "value": intent.get("tissue_or_context", "")},
                {"field": "handoff_goal", "value": intent.get("handoff_goal", "")},
            ],
        ),
        _section(
            "original_user_request",
            "Original User Request",
            [{"field": "raw_user_request", "value": bundle.get("input_request", "")}],
        ),
        _section(
            "parsed_design_intent",
            "Parsed Design Intent",
            [
                {"field": "intent_id", "value": intent.get("intent_id", "")},
                {"field": "target_type", "value": intent.get("target_type", "")},
                {"field": "scope_status", "value": intent.get("scope_status", "")},
                {"field": "manual_review_required", "value": intent.get("manual_review_required", True)},
            ],
        ),
        _section(
            "plant_design_context",
            "Plant Design Context",
            [
                {"field": "context_id", "value": context.get("context_id", "")},
                {"field": "plant_species", "value": context.get("plant_species", "")},
                {"field": "tissue_or_organ", "value": context.get("tissue_or_organ", "")},
                {"field": "expression_context", "value": context.get("expression_context", "")},
                {"field": "uncertainty_flags", "value": context.get("uncertainty_flags", [])},
            ],
        ),
        _section(
            "evidence_source_placeholder_matrix",
            "Evidence / Source Placeholder Matrix",
            evidence_rows,
        ),
        _section(
            "component_candidate_slot_table",
            "Component Candidate / Slot Table",
            component_rows,
        ),
        _section(
            "construct_draft_slot_scaffold",
            "Construct Draft Slot Scaffold",
            construct_rows,
        ),
        _section(
            "review_gap_items",
            "Review / Gap Items",
            review_rows,
        ),
        _section(
            "manual_review_checklist",
            "Manual Review Checklist",
            checklist_rows,
        ),
        _section(
            "boundary_statement",
            "Boundary Statement",
            boundary_rows,
        ),
        _section(
            "version_identity_placeholder",
            "Version / Identity Placeholder",
            [
                {"field": "assembler_version", "value": HANDOFF_DRAFT_ASSEMBLER_VERSION},
                {"field": "batch", "value": HANDOFF_DRAFT_ASSEMBLER_BATCH},
                {"field": "source_chain_version", "value": identity.get("chain_version", "")},
                {"field": "documentation_only", "value": identity.get("documentation_only", True)},
                {"field": "company_review_draft", "value": identity.get("company_review_draft", True)},
            ],
        ),
    ]

    return {
        "assembler_version": HANDOFF_DRAFT_ASSEMBLER_VERSION,
        "batch": HANDOFF_DRAFT_ASSEMBLER_BATCH,
        "package_label": "company-facing design evaluation draft",
        "boundary_labels": list(HANDOFF_BOUNDARY_LABELS),
        "source_chain_version": bundle.get("chain_version", ""),
        "source_request": bundle.get("input_request", ""),
        "sections": sections,
        "manual_review_required": True,
        "package_status": "manual_review_required",
    }
