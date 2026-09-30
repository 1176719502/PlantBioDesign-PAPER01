from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


ROUTE_GENERATION_BLOCKED = "blocked"
ROUTE_GENERATION_ALLOWED = "allowed"
SUPPORT_CLASSIFICATIONS = {"direct", "adjacent"}
ROUTE_GENERATOR_BOUNDARY = (
    "Candidate route drafts are case-supported review options. They preserve source IDs, "
    "missing fields, and manual review items; they do not choose final components, certify "
    "biology, forecast expression or yield, or provide lab instructions."
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_text(item) for item in value if _text(item)]
    return []


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _goal_type_id(matched_goal_type: str | Mapping[str, Any] | None) -> str:
    if isinstance(matched_goal_type, str):
        return _text(matched_goal_type)
    if isinstance(matched_goal_type, Mapping):
        return _text(matched_goal_type.get("goal_type_id"))
    return ""


def _matched_route_templates(
    goal_type_id: str,
    route_templates: Sequence[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    templates = [dict(template) for template in route_templates or [] if isinstance(template, Mapping)]
    if not goal_type_id:
        return templates
    return [
        template
        for template in templates
        if not _text(template.get("goal_type_id")) or _text(template.get("goal_type_id")) == goal_type_id
    ]


def _case_source_id(case: Mapping[str, Any]) -> str:
    source_reference = case.get("source_reference")
    if isinstance(source_reference, Mapping):
        source_id = _text(source_reference.get("source_id"))
        if source_id:
            return source_id
    return _text(case.get("source_id")) or _text(case.get("case_id"))


def _supported_cases(case_or_evidence_drafts: Sequence[Mapping[str, Any]] | None) -> list[dict[str, Any]]:
    supported: list[dict[str, Any]] = []
    for draft in case_or_evidence_drafts or []:
        if not isinstance(draft, Mapping):
            continue
        classification = _text(draft.get("classification") or draft.get("evidence_classification")).casefold()
        if classification not in SUPPORT_CLASSIFICATIONS:
            continue
        source_id = _case_source_id(draft)
        if not source_id:
            continue
        supported.append(dict(draft))
    return supported


def _component_context(case: Mapping[str, Any]) -> Mapping[str, Any]:
    value = case.get("component_context")
    return value if isinstance(value, Mapping) else case


def _plant_context(case: Mapping[str, Any]) -> Mapping[str, Any]:
    value = case.get("plant_context")
    return value if isinstance(value, Mapping) else case


def _target_context(case: Mapping[str, Any]) -> Mapping[str, Any]:
    value = case.get("target_context")
    return value if isinstance(value, Mapping) else case


def _required_component_slots(templates: Sequence[Mapping[str, Any]]) -> list[str]:
    slots: list[str] = []
    for template in templates:
        slots.extend(_as_list(template.get("required_inputs")))
    return _unique(slots)


def _template_evidence_gaps(templates: Sequence[Mapping[str, Any]]) -> list[str]:
    gaps: list[str] = []
    for template in templates:
        gaps.extend(_as_list(template.get("evidence_needed")))
    return _unique(gaps)


def _default_evidence_gaps(goal_type_id: str) -> list[str]:
    if goal_type_id == "plant_metabolic_engineering_sugar_metabolism":
        return [
            "exact target metabolite",
            "pathway",
            "gene/enzyme",
            "tissue/context",
            "sugarcane or adjacent plant cases",
            "expression system evidence",
        ]
    if goal_type_id == "plant_molecular_farming_protein_expression":
        return [
            "target protein identity",
            "gene/CDS source provenance",
            "plant host/context",
            "promoter/vector/source evidence",
            "direct or adjacent plant case evidence",
        ]
    return [
        "plant goal type",
        "direct or adjacent plant case evidence",
        "source-backed component context",
    ]


def _evidence_gaps(goal_type_id: str, templates: Sequence[Mapping[str, Any]]) -> list[str]:
    template_gaps = _template_evidence_gaps(templates)
    if goal_type_id == "plant_metabolic_engineering_sugar_metabolism":
        return _unique([*template_gaps, *_default_evidence_gaps(goal_type_id)])
    return template_gaps or _default_evidence_gaps(goal_type_id)


def _discovery_tasks(goal_type_id: str, evidence_gaps: Sequence[str]) -> list[dict[str, str]]:
    prefix = goal_type_id or "plant-goal"
    return [
        {
            "task_id": f"{prefix}-route-gap-{index:02d}",
            "gap": gap,
            "task": f"Find direct or adjacent plant evidence for {gap}.",
            "status": "manual_review_required",
        }
        for index, gap in enumerate(evidence_gaps, start=1)
    ]


def _slot_sources(supported_cases: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    slot_fields = (
        "plant_species",
        "tissue_context",
        "target_trait_or_product",
        "pathway",
        "gene",
        "enzyme",
        "promoter",
        "cds",
        "vector",
    )
    sources: dict[str, list[str]] = {field: [] for field in slot_fields}
    for case in supported_cases:
        source_id = _case_source_id(case)
        contexts = (_plant_context(case), _target_context(case), _component_context(case), case)
        for field in slot_fields:
            if any(_text(context.get(field)) for context in contexts if isinstance(context, Mapping)):
                sources[field].append(source_id)
    return {field: _unique(ids) for field, ids in sources.items() if ids}


def _missing_fields(
    templates: Sequence[Mapping[str, Any]],
    supported_cases: Sequence[Mapping[str, Any]],
) -> list[str]:
    missing: list[str] = []
    for template in templates:
        missing.extend(_as_list(template.get("required_inputs")))
    for case in supported_cases:
        missing.extend(_as_list(case.get("missing_fields")))
    return _unique(missing)


def _manual_review_items(templates: Sequence[Mapping[str, Any]], missing_fields: Sequence[str]) -> list[str]:
    items = [
        "Confirm each source supports the route context before downstream task drafting.",
        "Confirm component slots are source-backed before any component choice is recorded.",
        "Keep this route as a case-supported option until expert review is complete.",
    ]
    if missing_fields:
        items.append("Resolve missing fields before construct task handoff.")
    if not templates:
        items.append("Add or select a route template before continuing route review.")
    return items


def generate_plant_candidate_route(
    plant_goal: str,
    matched_goal_type: str | Mapping[str, Any] | None,
    route_templates: Sequence[Mapping[str, Any]] | None,
    case_or_evidence_drafts: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Gate candidate route drafting on direct or adjacent plant evidence support."""
    goal_type_id = _goal_type_id(matched_goal_type)
    templates = _matched_route_templates(goal_type_id, route_templates)
    supported_cases = _supported_cases(case_or_evidence_drafts)
    gaps = _evidence_gaps(goal_type_id, templates)

    if not templates or not supported_cases:
        return {
            "plant_goal": _text(plant_goal),
            "matched_goal_type_id": goal_type_id,
            "route_generation_status": ROUTE_GENERATION_BLOCKED,
            "manual_review_required": True,
            "evidence_gaps": gaps,
            "discovery_tasks": _discovery_tasks(goal_type_id, gaps),
            "candidate_route": None,
            "supporting_source_ids": [],
            "safety_boundary": ROUTE_GENERATOR_BOUNDARY,
        }

    supporting_source_ids = _unique([_case_source_id(case) for case in supported_cases])
    missing_fields = _missing_fields(templates, supported_cases)
    required_component_slots = _required_component_slots(templates)
    template = templates[0]
    candidate_route = {
        "route_id": f"{_text(template.get('route_template_id')) or goal_type_id or 'plant-route'}-candidate",
        "route_label": _text(template.get("label")) or "Plant candidate route draft",
        "route_framing": "case-supported option",
        "supporting_source_ids": supporting_source_ids,
        "supporting_case_ids": _unique([_text(case.get("case_id")) for case in supported_cases]),
        "required_component_slots": required_component_slots,
        "slot_source_ids": _slot_sources(supported_cases),
        "missing_fields": missing_fields,
        "manual_review_items": _manual_review_items(templates, missing_fields),
        "manual_review_required": True,
        "safety_boundary": ROUTE_GENERATOR_BOUNDARY,
    }

    return {
        "plant_goal": _text(plant_goal),
        "matched_goal_type_id": goal_type_id,
        "route_generation_status": ROUTE_GENERATION_ALLOWED,
        "manual_review_required": True,
        "evidence_gaps": [],
        "discovery_tasks": [],
        "candidate_route": candidate_route,
        "supporting_source_ids": supporting_source_ids,
        "safety_boundary": ROUTE_GENERATOR_BOUNDARY,
    }
