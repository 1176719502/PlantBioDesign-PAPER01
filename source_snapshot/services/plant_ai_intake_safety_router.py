from __future__ import annotations

from typing import Any

from services.plant_ai_mock_preview_contracts import ROUTER_BOUNDARY_APPEND, normalize_boundary_statements
from services.plant_design_domain_schema import DEFAULT_BOUNDARY_STATEMENTS


ROUTER_VERSION = "plant_ai_intake_safety_router.v2.7.r99"
ROUTER_BATCH = "v2.7-r99"

ALLOWED_OUTPUTS: tuple[str, ...] = (
    "design_intent",
    "plant_design_context",
    "evidence_placeholders",
    "component_slots",
    "construct_draft_slots",
    "review_items",
    "report_blocks",
    "company_handoff_draft",
    "safe_conceptual_summary",
)

BLOCKED_OUTPUTS: tuple[str, ...] = (
    "wet_lab_protocol",
    "cloning_steps",
    "transformation_steps",
    "culture_conditions",
    "primer_design",
    "synthesis_ready_sequence",
    "final_construct_recommendation",
    "component_ranking",
    "yield_prediction",
    "success_guarantee",
    "wet_lab_readiness_claim",
)

PLANT_TERMS: tuple[str, ...] = (
    "plant",
    "rice",
    "oryza",
    "seed",
    "leaf",
    "maize",
    "corn",
    "wheat",
    "soybean",
    "arabidopsis",
    "nicotiana",
    "tobacco",
)

NON_PLANT_TERMS: tuple[str, ...] = (
    "yeast",
    "saccharomyces",
    "e. coli",
    "ecoli",
    "escherichia",
    "bacteria",
    "bacterial",
    "microbial",
    "mammalian cell",
)

WET_LAB_TERMS: tuple[str, ...] = (
    "protocol",
    "step-by-step",
    "step by step",
    "clone",
    "cloning",
    "transform",
    "transformation",
    "culture",
    "incubate",
    "plasmid prep",
    "lab procedure",
)

SEQUENCE_OR_PRIMER_TERMS: tuple[str, ...] = (
    "primer",
    "primers",
    "final sequence",
    "full sequence",
    "synthesis ready",
    "synthesis-ready",
    "final construct",
    "ready-to-order",
)

HANDOFF_TERMS: tuple[str, ...] = (
    "handoff",
    "company",
    "company-facing",
    "design evaluation package",
    "evaluation package",
)

CONCEPTUAL_TERMS: tuple[str, ...] = (
    "explain",
    "compare",
    "conceptual",
    "overview",
    "difference",
    "summary",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(term in lowered for term in terms)


def _allowed_for_category(category: str) -> list[str]:
    if category == "safe_conceptual_explanation":
        return ["safe_conceptual_summary"]
    if category in {"blocked_wet_lab_execution", "blocked_final_sequence_or_primer", "non_plant_out_of_scope"}:
        return ["safe_conceptual_summary"]
    if category == "company_handoff_request":
        return [
            "design_intent",
            "plant_design_context",
            "evidence_placeholders",
            "component_slots",
            "construct_draft_slots",
            "review_items",
            "report_blocks",
            "company_handoff_draft",
        ]
    if category == "mixed_scope_needs_routing":
        return [
            "design_intent",
            "plant_design_context",
            "evidence_placeholders",
            "component_slots",
            "construct_draft_slots",
            "review_items",
            "report_blocks",
            "company_handoff_draft",
            "safe_conceptual_summary",
        ]
    return [
        "design_intent",
        "plant_design_context",
        "evidence_placeholders",
        "component_slots",
        "construct_draft_slots",
        "review_items",
        "report_blocks",
    ]


def _safe_next_step(category: str) -> str:
    if category == "blocked_wet_lab_execution":
        return "Reframe the request as documentation-only plant design review and gap documentation."
    if category == "blocked_final_sequence_or_primer":
        return "Capture the requested target as review context without generating final sequence or primer content."
    if category == "non_plant_out_of_scope":
        return "Use the main workflow only for plant design review; provide conceptual context separately if useful."
    if category == "safe_conceptual_explanation":
        return "Provide a bounded conceptual summary and invite manual expert review for project-specific decisions."
    if category == "company_handoff_request":
        return "Prepare a company-facing design evaluation draft with placeholders and manual review items."
    if category == "mixed_scope_needs_routing":
        return "Return safe design-review outputs while blocking operational or final-design outputs."
    return "Prepare a plant design review draft with evidence placeholders and manual review items."


def route_ai_intake_request(raw_user_request: Any) -> dict[str, Any]:
    request_text = _text(raw_user_request)
    lowered = request_text.casefold()

    has_plant = _contains_any(lowered, PLANT_TERMS)
    has_non_plant = _contains_any(lowered, NON_PLANT_TERMS)
    asks_wet_lab = _contains_any(lowered, WET_LAB_TERMS)
    asks_sequence_or_primer = _contains_any(lowered, SEQUENCE_OR_PRIMER_TERMS)
    asks_handoff = _contains_any(lowered, HANDOFF_TERMS)
    asks_conceptual = _contains_any(lowered, CONCEPTUAL_TERMS)

    if has_non_plant and not has_plant:
        category = "non_plant_out_of_scope"
    elif asks_sequence_or_primer and (has_plant or asks_handoff):
        category = "mixed_scope_needs_routing" if asks_handoff or asks_wet_lab else "blocked_final_sequence_or_primer"
    elif asks_wet_lab and (has_plant or asks_handoff):
        category = "mixed_scope_needs_routing" if asks_handoff else "blocked_wet_lab_execution"
    elif asks_sequence_or_primer:
        category = "blocked_final_sequence_or_primer"
    elif asks_wet_lab:
        category = "blocked_wet_lab_execution"
    elif asks_conceptual and not asks_handoff:
        category = "safe_conceptual_explanation"
    elif asks_handoff:
        category = "company_handoff_request"
    elif has_plant:
        category = "plant_supported_design_review"
    else:
        category = "safe_conceptual_explanation"

    return {
        "router_version": ROUTER_VERSION,
        "batch": ROUTER_BATCH,
        "raw_user_request": request_text,
        "scope_category": category,
        "allowed_outputs": _allowed_for_category(category),
        "blocked_outputs": list(BLOCKED_OUTPUTS),
        "boundary_statements": normalize_boundary_statements(DEFAULT_BOUNDARY_STATEMENTS, ROUTER_BOUNDARY_APPEND),
        "manual_review_required": True,
        "safe_next_step": _safe_next_step(category),
        "ai_output_status": "blocked_claim"
        if category in {"blocked_wet_lab_execution", "blocked_final_sequence_or_primer", "non_plant_out_of_scope"}
        else "needs_manual_review",
    }
