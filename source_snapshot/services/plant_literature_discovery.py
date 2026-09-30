from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_synbio_knowledge_base import build_plant_goal_evidence_intake


DISCOVERY_BOUNDARY = (
    "Plant literature discovery is offline search planning only. It creates query intents and "
    "evidence-gap tasks for manual review; it does not download PDFs, store full text, validate "
    "a route, or claim biological correctness."
)
SUPPORTED_SEARCH_SOURCES = ("PubMed", "Europe PMC", "Crossref", "Semantic Scholar")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _contains_any(text: str, terms: Sequence[str]) -> bool:
    normalized = text.casefold()
    return any(term.casefold() in normalized for term in terms)


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            unique_values.append(clean)
    return unique_values


def _goal_texts(plant_goal: str, intake: Mapping[str, Any]) -> tuple[str, str]:
    goal_text = _text(plant_goal)
    matched_goal_type = dict(intake.get("matched_goal_type") or {})
    goal_type_id = _text(matched_goal_type.get("goal_type_id"))
    return goal_text, goal_type_id


def _base_queries_for_goal(goal_text: str, goal_type_id: str) -> list[str]:
    if goal_type_id == "plant_metabolic_engineering_sugar_metabolism":
        if _contains_any(goal_text, ("sugarcane", "saccharum", "\u7518\u8517")):
            return [
                "sugarcane sucrose metabolism engineering",
                "Saccharum sugar metabolism transgenic",
                "sugarcane rare sugar metabolic engineering",
                "plant rare sugar pathway engineering",
                "sugarcane sucrose transporter engineering",
                "sugarcane promoter stem expression",
                "sugarcane transformation expression vector",
            ]
        return [
            "plant sugar metabolism engineering",
            "plant rare sugar pathway engineering",
            "plant sucrose transporter engineering",
            "plant metabolic engineering promoter evidence",
        ]
    if goal_type_id == "plant_molecular_farming_protein_expression":
        return [
            "plant molecular farming expression evidence",
            "plant recombinant protein expression promoter vector",
            "plant expression compartment case evidence",
            "plant transformation expression vector documentation",
        ]
    return [
        f"{goal_text} plant evidence",
        f"{goal_text} plant expression evidence",
        f"{goal_text} plant case study",
    ]


def _queries_from_missing_information(missing_information: Sequence[str], goal_text: str) -> list[str]:
    labels = {
        "target_trait_or_metabolite": "target metabolite plant evidence",
        "candidate_pathway": "candidate pathway plant evidence",
        "candidate_gene_or_enzyme": "candidate gene enzyme plant evidence",
        "tissue_context": "plant tissue expression context evidence",
        "evidence_context": "plant adjacent case evidence",
        "plant_context": "plant species context evidence",
        "target_product": "plant target protein expression evidence",
        "gene_or_cds_source": "plant gene CDS source evidence",
        "component_evidence_context": "plant promoter vector component evidence",
        "case_evidence_context": "adjacent plant case evidence",
    }
    prefix = goal_text if goal_text else "plant synbio goal"
    return [f"{prefix} {labels.get(field, field.replace('_', ' ') + ' evidence')}" for field in missing_information]


def _search_intent(source: str, query: str, index: int) -> dict[str, str]:
    source_key = source.casefold().replace(" ", "_")
    return {
        "intent_id": f"{source_key}-{index:03d}",
        "source": source,
        "query": query,
        "purpose": "manual evidence discovery",
        "storage_policy": "metadata/query intent only; no PDFs or full text",
    }


def _build_search_intents(queries: Sequence[str]) -> list[dict[str, str]]:
    intents: list[dict[str, str]] = []
    for query_index, query in enumerate(queries, start=1):
        for source in SUPPORTED_SEARCH_SOURCES:
            intents.append(_search_intent(source, query, query_index))
    return intents


def _evidence_gap_search_tasks(intake: Mapping[str, Any], queries: Sequence[str]) -> list[dict[str, str]]:
    missing = [str(item) for item in intake.get("missing_information") or []]
    discovery_plan = [
        row for row in intake.get("evidence_discovery_plan") or [] if isinstance(row, Mapping)
    ]
    tasks: list[dict[str, str]] = []
    for index, field in enumerate(missing, start=1):
        tasks.append(
            {
                "task_id": f"literature-gap-{index:03d}",
                "gap_field": field,
                "task": f"Search plant literature metadata for {field.replace('_', ' ')} evidence.",
                "status": "manual_review_required",
            }
        )
    offset = len(tasks)
    for index, row in enumerate(discovery_plan, start=1):
        tasks.append(
            {
                "task_id": f"evidence-plan-{offset + index:03d}",
                "gap_field": _text(row.get("task_id")),
                "task": _text(row.get("task")),
                "status": "manual_review_required",
            }
        )
    if not tasks:
        for index, query in enumerate(queries, start=1):
            tasks.append(
                {
                    "task_id": f"literature-review-{index:03d}",
                    "gap_field": "recorded_context_review",
                    "task": f"Review metadata returned for query: {query}",
                    "status": "manual_review_required",
                }
            )
    return tasks


def build_plant_literature_discovery_plan(
    plant_goal: str,
    matched_goal_type: str | Mapping[str, Any] | None = None,
    user_context: Mapping[str, Any] | None = None,
    *,
    intake: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create deterministic offline search intents from a plant goal and evidence gaps."""
    intake_result = dict(intake or build_plant_goal_evidence_intake(plant_goal, user_context))
    goal_text, goal_type_id = _goal_texts(plant_goal, intake_result)
    if isinstance(matched_goal_type, str) and matched_goal_type.strip():
        goal_type_id = matched_goal_type.strip()
    elif isinstance(matched_goal_type, Mapping) and _text(matched_goal_type.get("goal_type_id")):
        goal_type_id = _text(matched_goal_type.get("goal_type_id"))

    base_queries = _base_queries_for_goal(goal_text, goal_type_id)
    gap_queries = _queries_from_missing_information(
        [str(item) for item in intake_result.get("missing_information") or []],
        goal_text,
    )
    queries = _unique([*base_queries, *gap_queries])

    return {
        "plant_goal": goal_text,
        "matched_goal_type_id": goal_type_id,
        "queries": queries,
        "search_intents": _build_search_intents(queries),
        "evidence_gap_search_tasks": _evidence_gap_search_tasks(intake_result, queries),
        "source_policy": {
            "supported_sources": list(SUPPORTED_SEARCH_SOURCES),
            "offline_deterministic": True,
            "pdf_download_allowed": False,
            "full_text_storage_allowed": False,
            "api_required_for_tests": False,
        },
        "route_claim_policy": "Search planning does not claim route correctness or component suitability.",
        "documentation_boundary": DISCOVERY_BOUNDARY,
    }
