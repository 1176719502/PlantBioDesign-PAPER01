from __future__ import annotations

from typing import Any

from services.plant_ai_intake_mock_parser import RICE_ALBUMIN_LIKE_REQUEST, parse_rice_albumin_like_intake
from services.plant_ai_mock_preview_contracts import normalize_boundary_statements
from services.plant_design_domain_schema import (
    build_component_asset_record,
    build_construct_draft_record,
    build_evidence_record,
    build_handoff_package_record,
    build_report_block_record,
    build_review_item_record,
)


DOMAIN_CHAIN_VERSION = "plant_ai_guided_domain_chain.v2.7.r101"
DOMAIN_CHAIN_BATCH = "v2.7-r101"


def _text(value: Any) -> str:
    return str(value or "").strip()


def build_rice_albumin_like_domain_chain(raw_user_request: Any = RICE_ALBUMIN_LIKE_REQUEST) -> dict[str, Any]:
    request_text = _text(raw_user_request) or RICE_ALBUMIN_LIKE_REQUEST
    parsed = parse_rice_albumin_like_intake(request_text)

    project_id = "r101-rice-albumin-like-project"
    intent = dict(parsed["design_intent"])
    context = dict(parsed["plant_design_context"])
    construct_slots = [dict(slot) for slot in parsed["construct_slot_scaffold"]]
    boundary_statements = normalize_boundary_statements(parsed.get("boundary_statements"))

    intent["project_id"] = project_id
    intent["intent_id"] = "r101-rice-albumin-like-intent"
    context["project_id"] = project_id
    context["context_id"] = "r101-rice-seed-context"

    draft_id = "r101-rice-albumin-like-construct-draft"
    for slot in construct_slots:
        slot["draft_id"] = draft_id
        slot["slot_id"] = slot["slot_id"].replace("r100-", "r101-")

    evidence_placeholders = [
        build_evidence_record(
            evidence_id="r101-evidence-target-identity-placeholder",
            project_id=project_id,
            source_type="placeholder",
            title="Albumin-like target identity source placeholder",
            related_species=["rice"],
            related_context_ids=[context["context_id"]],
            summary="Target identity source and version require manual curation.",
        ),
        build_evidence_record(
            evidence_id="r101-evidence-rice-seed-context-placeholder",
            project_id=project_id,
            source_type="placeholder",
            title="Rice seed expression context source placeholder",
            related_species=["rice"],
            related_context_ids=[context["context_id"]],
            summary="Rice seed context evidence requires manual curation.",
        ),
        build_evidence_record(
            evidence_id="r101-evidence-company-handoff-placeholder",
            project_id=project_id,
            source_type="placeholder",
            title="Company review source matrix placeholder",
            related_species=["rice"],
            summary="Company-facing review sources remain placeholders until expert review.",
        ),
    ]

    component_placeholders = [
        build_component_asset_record(
            component_id="r101-component-albumin-like-cds-source-placeholder",
            component_name="Albumin-like CDS source placeholder",
            component_type="coding_sequence_source",
            source_species="rice",
            sequence_status="missing",
            evidence_ids=["r101-evidence-target-identity-placeholder"],
            manual_notes="CDS source and version remain missing.",
        ),
        build_component_asset_record(
            component_id="r101-component-rice-seed-context-placeholder",
            component_name="Rice seed context placeholder",
            component_type="plant_host_context",
            source_species="rice",
            sequence_status="missing",
            evidence_ids=["r101-evidence-rice-seed-context-placeholder"],
            manual_notes="Exact tissue/development context needs review.",
        ),
        build_component_asset_record(
            component_id="r101-component-vector-backbone-context-placeholder",
            component_name="Vector/backbone context placeholder",
            component_type="vector_backbone_context",
            sequence_status="missing",
            evidence_ids=["r101-evidence-company-handoff-placeholder"],
            manual_notes="Vector/backbone context is not supplied.",
        ),
    ]

    review_items = [
        build_review_item_record(
            review_item_id="r101-review-missing-source-fields",
            project_id=project_id,
            draft_id=draft_id,
            review_type="missing_source_fields",
            severity="manual_review",
            message="CDS source/version, evidence references, component provenance, localization, and vector/backbone context require manual review.",
            related_object_ids=[slot["slot_id"] for slot in construct_slots],
        ),
        build_review_item_record(
            review_item_id="r101-review-company-handoff-boundary",
            project_id=project_id,
            draft_id=draft_id,
            review_type="company_handoff_boundary",
            severity="boundary",
            message="Company-facing draft remains documentation-only and requires expert review before use in decisions.",
            related_object_ids=[project_id, intent["intent_id"], context["context_id"]],
        ),
    ]

    construct_draft = build_construct_draft_record(
        draft_id=draft_id,
        project_id=project_id,
        context_id=context["context_id"],
        intent_id=intent["intent_id"],
        route_template_id="r101-rice-seed-expression-review-template-placeholder",
        draft_status="manual_review_required",
        slot_ids=[slot["slot_id"] for slot in construct_slots],
        review_item_ids=[item["review_item_id"] for item in review_items],
    )

    report_blocks = [
        build_report_block_record(
            report_block_id="r101-report-original-request",
            project_id=project_id,
            block_type="original_request",
            title="Original user request",
            summary=request_text,
            rows=[{"field": "raw_user_request", "value": request_text}],
            source_object_ids=[intent["intent_id"]],
        ),
        build_report_block_record(
            report_block_id="r101-report-design-intent-context",
            project_id=project_id,
            block_type="design_intent_context",
            title="Design intent and plant context",
            summary="Draft block for target, rice seed context, and company-facing design evaluation goal.",
            rows=[
                {"field": "target", "value": intent["target_name"]},
                {"field": "plant_host", "value": intent["plant_host"]},
                {"field": "tissue_or_context", "value": intent["tissue_or_context"]},
                {"field": "handoff_goal", "value": intent["handoff_goal"]},
            ],
            source_object_ids=[intent["intent_id"], context["context_id"]],
        ),
        build_report_block_record(
            report_block_id="r101-report-review-gaps",
            project_id=project_id,
            block_type="manual_review_gap_summary",
            title="Manual review gaps",
            summary="Draft block for missing source, evidence, provenance, localization, and vector/backbone context.",
            rows=[{"missing_field": field} for field in parsed["missing_fields"]],
            source_object_ids=[item["review_item_id"] for item in review_items],
            ai_output_status="needs_manual_review",
        ),
    ]

    handoff_package_skeleton = build_handoff_package_record(
        package_id="r101-handoff-rice-albumin-like",
        project_id=project_id,
        package_version=DOMAIN_CHAIN_BATCH,
        design_intent_id=intent["intent_id"],
        context_id=context["context_id"],
        evidence_ids=[record["evidence_id"] for record in evidence_placeholders],
        component_ids=[record["component_id"] for record in component_placeholders],
        construct_draft_id=draft_id,
        review_item_ids=[item["review_item_id"] for item in review_items],
        report_block_ids=[block["report_block_id"] for block in report_blocks],
        package_status="manual_review_required",
        boundary_statements=boundary_statements,
        identity={
            "chain_version": DOMAIN_CHAIN_VERSION,
            "batch": DOMAIN_CHAIN_BATCH,
            "example": "rice albumin-like domain chain",
            "documentation_only": True,
            "company_review_draft": True,
        },
    )

    return {
        "chain_version": DOMAIN_CHAIN_VERSION,
        "batch": DOMAIN_CHAIN_BATCH,
        "input_request": request_text,
        "scope_decision": parsed["scope_decision"],
        "design_intent": intent,
        "plant_context": context,
        "evidence_placeholders": evidence_placeholders,
        "component_placeholders": component_placeholders,
        "construct_draft": construct_draft,
        "construct_slots": construct_slots,
        "review_gap_items": review_items,
        "report_block_placeholders": report_blocks,
        "handoff_package_skeleton": handoff_package_skeleton,
        "boundary_statements": boundary_statements,
        "status": {
            "draft": True,
            "manual_review_required": True,
            "company_review_draft": True,
        },
    }
