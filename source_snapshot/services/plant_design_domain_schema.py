from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


DOMAIN_SCHEMA_VERSION = "plant_design_domain_schema.v2.7.r98"
DOMAIN_SCHEMA_BATCH = "v2.7-r98"

AI_OUTPUT_STATUSES: tuple[str, ...] = (
    "draft",
    "user_confirmed",
    "evidence_supported",
    "component_library_supported",
    "knowledge_supported",
    "needs_manual_review",
    "unsupported_ai_suggestion",
    "blocked_claim",
)

PLANT_DESIGN_SCOPE_STATUSES: tuple[str, ...] = (
    "plant_supported_design_review",
    "safe_conceptual_explanation",
    "company_handoff_request",
    "blocked_wet_lab_execution",
    "blocked_final_sequence_or_primer",
    "non_plant_out_of_scope",
    "mixed_scope_needs_routing",
)

REVIEW_STATUSES: tuple[str, ...] = (
    "draft",
    "manual_review_required",
    "user_confirmed",
    "blocked",
    "ready_for_company_review_draft",
)

SOURCE_STATUSES: tuple[str, ...] = (
    "missing",
    "placeholder",
    "source_recorded",
    "manual_review_required",
    "unsupported",
)

CONSTRUCT_SLOT_STATUSES: tuple[str, ...] = (
    "missing",
    "placeholder",
    "candidate_recorded",
    "source_recorded",
    "manual_review_required",
    "blocked",
)

HANDOFF_ELIGIBILITY_STATUSES: tuple[str, ...] = (
    "draft",
    "manual_review_required",
    "blocked",
    "eligible_for_company_review_draft",
    "not_eligible_boundary_review",
)

SEQUENCE_STATUSES: tuple[str, ...] = (
    "missing",
    "placeholder",
    "source_recorded",
    "manual_review_required",
    "blocked",
)

DEFAULT_BOUNDARY_STATEMENTS: tuple[str, ...] = (
    "Documentation-only plant design review skeleton.",
    "No final component choice, final sequence, biological performance claim, or wet-lab step is generated.",
    "Company-facing handoff content remains a draft for expert review.",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        clean = _text(value)
        return [clean] if clean else []
    if isinstance(value, Mapping):
        return [_plain_value(value)]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return [_plain_value(value)]


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _status(value: Any, allowed: Sequence[str], default: str) -> str:
    clean = _text(value)
    return clean if clean in allowed else default


def _record(fields: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    return {key: _plain_value(value) for key, value in fields}


def build_project_record(
    project_id: Any = "",
    project_name: Any = "",
    raw_user_request: Any = "",
    project_status: Any = "draft",
    source_status: Any = "placeholder",
    notes: Any = "",
) -> dict[str, Any]:
    return _record(
        (
            ("project_id", _text(project_id)),
            ("project_name", _text(project_name)),
            ("raw_user_request", _text(raw_user_request)),
            ("project_status", _status(project_status, REVIEW_STATUSES, "draft")),
            ("source_status", _status(source_status, SOURCE_STATUSES, "placeholder")),
            ("notes", _text(notes)),
        )
    )


def build_design_intent_record(
    intent_id: Any = "",
    project_id: Any = "",
    raw_user_request: Any = "",
    target_name: Any = "",
    target_type: Any = "",
    plant_host: Any = "",
    tissue_or_context: Any = "",
    design_purpose: Any = "",
    handoff_goal: Any = "",
    scope_status: Any = "plant_supported_design_review",
    missing_fields: Any = None,
    ai_output_status: Any = "draft",
    manual_review_required: Any = True,
) -> dict[str, Any]:
    return _record(
        (
            ("intent_id", _text(intent_id)),
            ("project_id", _text(project_id)),
            ("raw_user_request", _text(raw_user_request)),
            ("target_name", _text(target_name)),
            ("target_type", _text(target_type)),
            ("plant_host", _text(plant_host)),
            ("tissue_or_context", _text(tissue_or_context)),
            ("design_purpose", _text(design_purpose)),
            ("handoff_goal", _text(handoff_goal)),
            ("scope_status", _status(scope_status, PLANT_DESIGN_SCOPE_STATUSES, "plant_supported_design_review")),
            ("missing_fields", _as_list(missing_fields)),
            ("ai_output_status", _status(ai_output_status, AI_OUTPUT_STATUSES, "draft")),
            ("manual_review_required", bool(manual_review_required)),
        )
    )


def build_plant_design_context_record(
    context_id: Any = "",
    project_id: Any = "",
    plant_species: Any = "",
    cultivar_or_variety: Any = "",
    tissue_or_organ: Any = "",
    expression_context: Any = "",
    subcellular_localization: Any = "",
    target_product_type: Any = "",
    uncertainty_flags: Any = None,
    review_status: Any = "manual_review_required",
) -> dict[str, Any]:
    return _record(
        (
            ("context_id", _text(context_id)),
            ("project_id", _text(project_id)),
            ("plant_species", _text(plant_species)),
            ("cultivar_or_variety", _text(cultivar_or_variety)),
            ("tissue_or_organ", _text(tissue_or_organ)),
            ("expression_context", _text(expression_context)),
            ("subcellular_localization", _text(subcellular_localization)),
            ("target_product_type", _text(target_product_type)),
            ("uncertainty_flags", _as_list(uncertainty_flags)),
            ("review_status", _status(review_status, REVIEW_STATUSES, "manual_review_required")),
        )
    )


def build_evidence_record(
    evidence_id: Any = "",
    project_id: Any = "",
    source_type: Any = "",
    title: Any = "",
    source_reference: Any = "",
    related_species: Any = None,
    related_component_ids: Any = None,
    related_context_ids: Any = None,
    summary: Any = "",
    source_status: Any = "placeholder",
    review_status: Any = "manual_review_required",
) -> dict[str, Any]:
    return _record(
        (
            ("evidence_id", _text(evidence_id)),
            ("project_id", _text(project_id)),
            ("source_type", _text(source_type)),
            ("title", _text(title)),
            ("source_reference", _text(source_reference)),
            ("related_species", _as_list(related_species)),
            ("related_component_ids", _as_list(related_component_ids)),
            ("related_context_ids", _as_list(related_context_ids)),
            ("summary", _text(summary)),
            ("source_status", _status(source_status, SOURCE_STATUSES, "placeholder")),
            ("review_status", _status(review_status, REVIEW_STATUSES, "manual_review_required")),
        )
    )


def build_component_asset_record(
    component_id: Any = "",
    component_name: Any = "",
    component_type: Any = "",
    source_species: Any = "",
    sequence_status: Any = "missing",
    source_reference: Any = "",
    compatible_contexts: Any = None,
    evidence_ids: Any = None,
    review_status: Any = "manual_review_required",
    manual_notes: Any = "",
) -> dict[str, Any]:
    return _record(
        (
            ("component_id", _text(component_id)),
            ("component_name", _text(component_name)),
            ("component_type", _text(component_type)),
            ("source_species", _text(source_species)),
            ("sequence_status", _status(sequence_status, SEQUENCE_STATUSES, "missing")),
            ("source_reference", _text(source_reference)),
            ("compatible_contexts", _as_list(compatible_contexts)),
            ("evidence_ids", _as_list(evidence_ids)),
            ("review_status", _status(review_status, REVIEW_STATUSES, "manual_review_required")),
            ("manual_notes", _text(manual_notes)),
        )
    )


def build_knowledge_record(
    knowledge_id: Any = "",
    knowledge_type: Any = "",
    title: Any = "",
    plant_scope: Any = "",
    component_scope: Any = "",
    design_context_scope: Any = "",
    summary: Any = "",
    source_evidence_ids: Any = None,
    review_status: Any = "manual_review_required",
) -> dict[str, Any]:
    return _record(
        (
            ("knowledge_id", _text(knowledge_id)),
            ("knowledge_type", _text(knowledge_type)),
            ("title", _text(title)),
            ("plant_scope", _text(plant_scope)),
            ("component_scope", _text(component_scope)),
            ("design_context_scope", _text(design_context_scope)),
            ("summary", _text(summary)),
            ("source_evidence_ids", _as_list(source_evidence_ids)),
            ("review_status", _status(review_status, REVIEW_STATUSES, "manual_review_required")),
        )
    )


def build_construct_draft_record(
    draft_id: Any = "",
    project_id: Any = "",
    context_id: Any = "",
    intent_id: Any = "",
    route_template_id: Any = "",
    draft_status: Any = "manual_review_required",
    slot_ids: Any = None,
    review_item_ids: Any = None,
    manual_review_required: Any = True,
) -> dict[str, Any]:
    return _record(
        (
            ("draft_id", _text(draft_id)),
            ("project_id", _text(project_id)),
            ("context_id", _text(context_id)),
            ("intent_id", _text(intent_id)),
            ("route_template_id", _text(route_template_id)),
            ("draft_status", _status(draft_status, REVIEW_STATUSES, "manual_review_required")),
            ("slot_ids", _as_list(slot_ids)),
            ("review_item_ids", _as_list(review_item_ids)),
            ("manual_review_required", bool(manual_review_required)),
        )
    )


def build_construct_slot_record(
    slot_id: Any = "",
    draft_id: Any = "",
    slot_type: Any = "",
    label: Any = "",
    required: Any = True,
    selected_component_id: Any = "",
    candidate_component_ids: Any = None,
    evidence_ids: Any = None,
    slot_status: Any = "missing",
    missing_reason: Any = "",
    manual_review_required: Any = True,
) -> dict[str, Any]:
    return _record(
        (
            ("slot_id", _text(slot_id)),
            ("draft_id", _text(draft_id)),
            ("slot_type", _text(slot_type)),
            ("label", _text(label)),
            ("required", bool(required)),
            ("selected_component_id", _text(selected_component_id)),
            ("candidate_component_ids", _as_list(candidate_component_ids)),
            ("evidence_ids", _as_list(evidence_ids)),
            ("slot_status", _status(slot_status, CONSTRUCT_SLOT_STATUSES, "missing")),
            ("missing_reason", _text(missing_reason)),
            ("manual_review_required", bool(manual_review_required)),
        )
    )


def build_review_item_record(
    review_item_id: Any = "",
    project_id: Any = "",
    draft_id: Any = "",
    review_type: Any = "",
    severity: Any = "",
    message: Any = "",
    related_object_ids: Any = None,
    status: Any = "manual_review_required",
    manual_review_required: Any = True,
) -> dict[str, Any]:
    return _record(
        (
            ("review_item_id", _text(review_item_id)),
            ("project_id", _text(project_id)),
            ("draft_id", _text(draft_id)),
            ("review_type", _text(review_type)),
            ("severity", _text(severity)),
            ("message", _text(message)),
            ("related_object_ids", _as_list(related_object_ids)),
            ("status", _status(status, REVIEW_STATUSES, "manual_review_required")),
            ("manual_review_required", bool(manual_review_required)),
        )
    )


def build_report_block_record(
    report_block_id: Any = "",
    project_id: Any = "",
    block_type: Any = "",
    title: Any = "",
    summary: Any = "",
    rows: Any = None,
    source_object_ids: Any = None,
    ai_output_status: Any = "draft",
    review_status: Any = "manual_review_required",
) -> dict[str, Any]:
    return _record(
        (
            ("report_block_id", _text(report_block_id)),
            ("project_id", _text(project_id)),
            ("block_type", _text(block_type)),
            ("title", _text(title)),
            ("summary", _text(summary)),
            ("rows", _as_list(rows)),
            ("source_object_ids", _as_list(source_object_ids)),
            ("ai_output_status", _status(ai_output_status, AI_OUTPUT_STATUSES, "draft")),
            ("review_status", _status(review_status, REVIEW_STATUSES, "manual_review_required")),
        )
    )


def build_handoff_package_record(
    package_id: Any = "",
    project_id: Any = "",
    package_version: Any = "",
    design_intent_id: Any = "",
    context_id: Any = "",
    evidence_ids: Any = None,
    component_ids: Any = None,
    construct_draft_id: Any = "",
    review_item_ids: Any = None,
    report_block_ids: Any = None,
    package_status: Any = "manual_review_required",
    boundary_statements: Any = None,
    identity: Any = None,
) -> dict[str, Any]:
    boundary_values = _as_list(boundary_statements)
    if not boundary_values:
        boundary_values = list(DEFAULT_BOUNDARY_STATEMENTS)
    return _record(
        (
            ("package_id", _text(package_id)),
            ("project_id", _text(project_id)),
            ("package_version", _text(package_version)),
            ("design_intent_id", _text(design_intent_id)),
            ("context_id", _text(context_id)),
            ("evidence_ids", _as_list(evidence_ids)),
            ("component_ids", _as_list(component_ids)),
            ("construct_draft_id", _text(construct_draft_id)),
            ("review_item_ids", _as_list(review_item_ids)),
            ("report_block_ids", _as_list(report_block_ids)),
            ("package_status", _status(package_status, HANDOFF_ELIGIBILITY_STATUSES, "manual_review_required")),
            ("boundary_statements", boundary_values),
            ("identity", _plain_value(identity or {})),
        )
    )


def build_rice_albumin_like_domain_seed() -> dict[str, Any]:
    raw_request = (
        "I want to express an albumin-like protein in rice seed and prepare a "
        "company-facing design evaluation package."
    )
    project_id = "r98-rice-albumin-like-project"
    intent_id = "r98-rice-albumin-like-intent"
    context_id = "r98-rice-seed-context"
    draft_id = "r98-rice-albumin-like-construct-draft"

    missing_fields = [
        "CDS/source/version",
        "exact tissue/development context",
        "subcellular localization",
        "evidence references",
        "component provenance",
        "vector/backbone context",
    ]

    project = build_project_record(
        project_id=project_id,
        project_name="Rice seed albumin-like design review skeleton",
        raw_user_request=raw_request,
        project_status="manual_review_required",
        source_status="placeholder",
        notes="Seed bundle for deterministic domain schema review only.",
    )
    design_intent = build_design_intent_record(
        intent_id=intent_id,
        project_id=project_id,
        raw_user_request=raw_request,
        target_name="albumin-like protein",
        target_type="protein expression review target",
        plant_host="Oryza sativa rice",
        tissue_or_context="seed",
        design_purpose="documentation-only plant design review",
        handoff_goal="company-facing design evaluation package",
        scope_status="company_handoff_request",
        missing_fields=missing_fields,
        ai_output_status="needs_manual_review",
        manual_review_required=True,
    )
    plant_design_context = build_plant_design_context_record(
        context_id=context_id,
        project_id=project_id,
        plant_species="Oryza sativa rice",
        tissue_or_organ="seed",
        expression_context="rice seed expression context",
        target_product_type="albumin-like protein",
        uncertainty_flags=[
            "exact seed developmental context needs review",
            "subcellular localization not supplied",
        ],
        review_status="manual_review_required",
    )
    evidence_records = [
        build_evidence_record(
            evidence_id="r98-evidence-placeholder-target",
            project_id=project_id,
            source_type="placeholder",
            title="Albumin-like target identity evidence placeholder",
            related_species=["Oryza sativa rice"],
            related_context_ids=[context_id],
            summary="Evidence reference still needs manual curation before handoff drafting.",
        ),
        build_evidence_record(
            evidence_id="r98-evidence-placeholder-context",
            project_id=project_id,
            source_type="placeholder",
            title="Rice seed context evidence placeholder",
            related_species=["Oryza sativa rice"],
            related_context_ids=[context_id],
            summary="Seed context evidence remains a review gap.",
        ),
    ]
    component_assets = [
        build_component_asset_record(
            component_id="r98-component-placeholder-cds",
            component_name="Albumin-like CDS source placeholder",
            component_type="coding_sequence_source",
            source_species="Oryza sativa rice",
            sequence_status="missing",
            evidence_ids=["r98-evidence-placeholder-target"],
            manual_notes="CDS source, accession/version, and provenance remain missing.",
        ),
        build_component_asset_record(
            component_id="r98-component-placeholder-vector-context",
            component_name="Vector/backbone context placeholder",
            component_type="vector_backbone_context",
            sequence_status="missing",
            manual_notes="Backbone context is not selected and remains a company/expert review input.",
        ),
    ]
    knowledge_records = [
        build_knowledge_record(
            knowledge_id="r98-knowledge-placeholder-boundary",
            knowledge_type="boundary_note",
            title="Plant design review boundary",
            plant_scope="Oryza sativa rice seed",
            component_scope="albumin-like target and construct slots",
            design_context_scope="company-facing design evaluation package draft",
            summary="The seed records organize review inputs and gaps without choosing components or creating final sequence content.",
            source_evidence_ids=["r98-evidence-placeholder-target", "r98-evidence-placeholder-context"],
        )
    ]
    construct_slots = [
        build_construct_slot_record(
            slot_id="r98-slot-target-cds",
            draft_id=draft_id,
            slot_type="coding_sequence_source",
            label="Albumin-like CDS/source/version",
            candidate_component_ids=["r98-component-placeholder-cds"],
            evidence_ids=["r98-evidence-placeholder-target"],
            slot_status="manual_review_required",
            missing_reason="CDS/source/version not supplied.",
        ),
        build_construct_slot_record(
            slot_id="r98-slot-seed-context",
            draft_id=draft_id,
            slot_type="plant_host_context",
            label="Rice seed host/context",
            candidate_component_ids=[],
            evidence_ids=["r98-evidence-placeholder-context"],
            slot_status="source_recorded",
            missing_reason="Exact tissue/development context still needs review.",
        ),
        build_construct_slot_record(
            slot_id="r98-slot-localization",
            draft_id=draft_id,
            slot_type="subcellular_localization",
            label="Subcellular localization",
            slot_status="missing",
            missing_reason="Localization context not supplied.",
        ),
        build_construct_slot_record(
            slot_id="r98-slot-vector-context",
            draft_id=draft_id,
            slot_type="vector_backbone_context",
            label="Vector/backbone context",
            candidate_component_ids=["r98-component-placeholder-vector-context"],
            slot_status="manual_review_required",
            missing_reason="Vector/backbone context not supplied.",
        ),
    ]
    review_items = [
        build_review_item_record(
            review_item_id="r98-review-missing-source-provenance",
            project_id=project_id,
            draft_id=draft_id,
            review_type="missing_source_provenance",
            severity="manual_review",
            message="CDS source/version, evidence references, and component provenance need manual review.",
            related_object_ids=["r98-slot-target-cds", "r98-component-placeholder-cds"],
        ),
        build_review_item_record(
            review_item_id="r98-review-boundary",
            project_id=project_id,
            draft_id=draft_id,
            review_type="documentation_boundary",
            severity="boundary",
            message="Keep this bundle as documentation-only review data until expert review supplies missing context.",
            related_object_ids=[project_id, draft_id],
        ),
    ]
    construct_draft = build_construct_draft_record(
        draft_id=draft_id,
        project_id=project_id,
        context_id=context_id,
        intent_id=intent_id,
        route_template_id="r98-rice-seed-expression-review-template-placeholder",
        draft_status="manual_review_required",
        slot_ids=[slot["slot_id"] for slot in construct_slots],
        review_item_ids=[item["review_item_id"] for item in review_items],
    )
    report_blocks = [
        build_report_block_record(
            report_block_id="r98-report-intent-context",
            project_id=project_id,
            block_type="intent_context_summary",
            title="Intent and rice seed context",
            summary="Draft block for target, rice seed context, handoff goal, and missing context review.",
            rows=[
                {"field": "target", "value": "albumin-like protein"},
                {"field": "plant_host", "value": "Oryza sativa rice"},
                {"field": "tissue_or_context", "value": "seed"},
            ],
            source_object_ids=[intent_id, context_id],
            ai_output_status="draft",
        ),
        build_report_block_record(
            report_block_id="r98-report-gap-review",
            project_id=project_id,
            block_type="manual_review_gap_summary",
            title="Manual review gaps",
            summary="Draft block for missing evidence, component provenance, localization, and vector/backbone context.",
            rows=[{"missing_field": field} for field in missing_fields],
            source_object_ids=[item["review_item_id"] for item in review_items],
            ai_output_status="needs_manual_review",
        ),
    ]
    handoff_package = build_handoff_package_record(
        package_id="r98-handoff-rice-albumin-like",
        project_id=project_id,
        package_version=DOMAIN_SCHEMA_BATCH,
        design_intent_id=intent_id,
        context_id=context_id,
        evidence_ids=[record["evidence_id"] for record in evidence_records],
        component_ids=[record["component_id"] for record in component_assets],
        construct_draft_id=draft_id,
        review_item_ids=[item["review_item_id"] for item in review_items],
        report_block_ids=[block["report_block_id"] for block in report_blocks],
        package_status="manual_review_required",
        identity={
            "schema_version": DOMAIN_SCHEMA_VERSION,
            "batch": DOMAIN_SCHEMA_BATCH,
            "example": "rice albumin-like domain seed",
            "documentation_only": True,
        },
    )

    return {
        "schema_version": DOMAIN_SCHEMA_VERSION,
        "batch": DOMAIN_SCHEMA_BATCH,
        "project": project,
        "design_intent": design_intent,
        "plant_design_context": plant_design_context,
        "evidence_records": evidence_records,
        "component_assets": component_assets,
        "knowledge_records": knowledge_records,
        "construct_draft": construct_draft,
        "construct_slots": construct_slots,
        "review_items": review_items,
        "report_blocks": report_blocks,
        "handoff_package": handoff_package,
    }
