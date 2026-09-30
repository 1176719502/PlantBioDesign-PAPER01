from __future__ import annotations

from typing import Any

from services.plant_ai_intake_safety_router import route_ai_intake_request
from services.plant_ai_mock_preview_contracts import normalize_boundary_statements
from services.plant_design_domain_schema import (
    build_construct_slot_record,
    build_design_intent_record,
    build_plant_design_context_record,
    build_review_item_record,
)


MOCK_PARSER_VERSION = "plant_ai_intake_mock_parser.v2.7.r100"
MOCK_PARSER_BATCH = "v2.7-r100"
RICE_ALBUMIN_LIKE_REQUEST = (
    "I want to express an albumin-like protein in rice seed and prepare a "
    "company-facing design evaluation package."
)

MISSING_FIELDS: tuple[str, ...] = (
    "CDS/source/version",
    "exact tissue/development context if needed",
    "subcellular localization",
    "evidence references",
    "component provenance",
    "vector/backbone context",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def parse_rice_albumin_like_intake(raw_user_request: Any = RICE_ALBUMIN_LIKE_REQUEST) -> dict[str, Any]:
    request_text = _text(raw_user_request) or RICE_ALBUMIN_LIKE_REQUEST
    scope_decision = dict(route_ai_intake_request(request_text))
    scope_decision["boundary_statements"] = normalize_boundary_statements(scope_decision.get("boundary_statements"))

    project_id = "r100-rice-albumin-like-project"
    intent_id = "r100-rice-albumin-like-intent"
    context_id = "r100-rice-seed-context"
    draft_id = "r100-rice-albumin-like-construct-draft"

    design_intent = build_design_intent_record(
        intent_id=intent_id,
        project_id=project_id,
        raw_user_request=request_text,
        target_name="albumin-like protein",
        target_type="protein expression review target",
        plant_host="rice",
        tissue_or_context="seed",
        design_purpose="documentation-only plant design review",
        handoff_goal="company-facing design evaluation package",
        scope_status=scope_decision["scope_category"],
        missing_fields=list(MISSING_FIELDS),
        ai_output_status="needs_manual_review",
        manual_review_required=True,
    )

    plant_design_context = build_plant_design_context_record(
        context_id=context_id,
        project_id=project_id,
        plant_species="rice",
        tissue_or_organ="seed",
        expression_context="rice seed expression context",
        subcellular_localization="missing",
        target_product_type="albumin-like protein",
        uncertainty_flags=[
            "exact tissue/development context if needed",
            "subcellular localization not supplied",
            "component provenance not supplied",
        ],
        review_status="manual_review_required",
    )

    construct_slot_scaffold = [
        build_construct_slot_record(
            slot_id="r100-slot-cds-source-version",
            draft_id=draft_id,
            slot_type="coding_sequence_source",
            label="CDS/source/version",
            slot_status="missing",
            missing_reason="CDS/source/version not supplied.",
        ),
        build_construct_slot_record(
            slot_id="r100-slot-plant-host-context",
            draft_id=draft_id,
            slot_type="plant_host_context",
            label="Rice seed host/context",
            slot_status="placeholder",
            missing_reason="Exact tissue/development context may need review.",
        ),
        build_construct_slot_record(
            slot_id="r100-slot-subcellular-localization",
            draft_id=draft_id,
            slot_type="subcellular_localization",
            label="Subcellular localization",
            slot_status="missing",
            missing_reason="Localization context not supplied.",
        ),
        build_construct_slot_record(
            slot_id="r100-slot-evidence-references",
            draft_id=draft_id,
            slot_type="evidence_references",
            label="Evidence references",
            slot_status="missing",
            missing_reason="Evidence references require manual curation.",
        ),
        build_construct_slot_record(
            slot_id="r100-slot-component-provenance",
            draft_id=draft_id,
            slot_type="component_provenance",
            label="Component provenance",
            slot_status="missing",
            missing_reason="Component provenance not supplied.",
        ),
        build_construct_slot_record(
            slot_id="r100-slot-vector-backbone-context",
            draft_id=draft_id,
            slot_type="vector_backbone_context",
            label="Vector/backbone context",
            slot_status="missing",
            missing_reason="Vector/backbone context not supplied.",
        ),
    ]

    review_items = [
        build_review_item_record(
            review_item_id="r100-review-missing-inputs",
            project_id=project_id,
            draft_id=draft_id,
            review_type="missing_input_fields",
            severity="manual_review",
            message="Missing source, context, localization, evidence, provenance, and vector/backbone fields require manual review.",
            related_object_ids=[slot["slot_id"] for slot in construct_slot_scaffold],
        ),
        build_review_item_record(
            review_item_id="r100-review-boundary",
            project_id=project_id,
            draft_id=draft_id,
            review_type="documentation_boundary",
            severity="boundary",
            message="Keep the parsed intake as documentation-only review context and company handoff draft input.",
            related_object_ids=[project_id, intent_id, context_id],
        ),
    ]

    return {
        "parser_version": MOCK_PARSER_VERSION,
        "batch": MOCK_PARSER_BATCH,
        "raw_user_request": request_text,
        "scope_decision": scope_decision,
        "parsed_fields": {
            "plant_host": "rice",
            "tissue_or_context": "seed",
            "target": "albumin-like protein",
            "handoff_goal": "company-facing design evaluation package",
        },
        "design_intent": design_intent,
        "plant_design_context": plant_design_context,
        "missing_fields": list(MISSING_FIELDS),
        "construct_slot_scaffold": construct_slot_scaffold,
        "review_items": review_items,
        "review_status": {
            "status": "manual_review_required",
            "manual_review_required": True,
            "ai_output_status": "needs_manual_review",
        },
        "boundary_statements": scope_decision["boundary_statements"],
    }
