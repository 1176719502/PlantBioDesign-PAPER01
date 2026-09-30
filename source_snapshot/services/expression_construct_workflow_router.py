from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


ACTIVE_MAINLINE_ROUTE = "expression_construct_review_mainline"
PLANT_MAINLINE_ROUTE = "expression_construct_review_mainline_plant_context"
HOST_MAINLINE_ROUTE = "expression_construct_review_mainline_host_context"
FUTURE_METABOLIC_ROUTE = "future_route_candidate_metabolic_pathway"
FUTURE_CIRCUIT_ROUTE = "future_route_candidate_genetic_circuit"
FALLBACK_ROUTE = "expression_construct_review_fallback"

ROUTE_CATEGORY_ACTIVE = "active_mainline"
ROUTE_CATEGORY_FUTURE = "future_route_candidate"
ROUTE_CATEGORY_FALLBACK = "fallback"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

BASE_BOUNDARY_NOTES = [
    "documentation-only review route",
    "manual review required",
    "not a build-ready design",
    "no component-choice guidance or procedure steps",
    "no biological feasibility, validation, or optimization claim",
]

ACTIVE_REVIEW_STAGES = [
    "intent review",
    "target identity review",
    "host context review",
    "construct/vector review",
    "source/provenance review",
    "manual handoff review",
]

FUTURE_ROUTE_STAGES = [
    "intent review",
    "manual route triage",
    "source/provenance review",
    "future route review",
]

BASE_REQUIRED_SLOTS = [
    "target_identity",
    "host_system",
    "construct_or_vector_context",
    "source_or_provenance",
]

PATHWAY_REQUIRED_SLOTS = [
    "target_pathway_or_product",
    "host_system",
    "source_or_provenance",
    "manual_review_context",
]

CIRCUIT_REQUIRED_SLOTS = [
    "circuit_or_module_goal",
    "host_system",
    "source_or_provenance",
    "manual_review_context",
]

TARGET_CUES = (
    "protein",
    "enzyme",
    "gene",
    "cds",
    "albumin",
    "白蛋白",
    "蛋白",
    "酶",
    "基因",
    "target protein",
    "target gene",
    "reporter",
)

ACTIVE_ROUTE_CUES = (
    "expression",
    "construct",
    "vector",
    "cassette",
    "plasmid",
    "protein expression",
    "expression vector",
    "recombinant protein",
    "载体",
    "构建",
    "表达",
    "蛋白表达",
    "重组蛋白",
)

PLANT_CUES = (
    "plant",
    "rice",
    "oryza",
    "arabidopsis",
    "tobacco",
    "nicotiana",
    "maize",
    "corn",
    "wheat",
    "soybean",
    "barley",
    "sugarcane",
    "水稻",
    "植物",
    "烟草",
    "玉米",
    "大豆",
    "小麦",
    "甘蔗",
)

YEAST_CUES = (
    "yeast",
    "saccharomyces",
    "pichia",
    "komagataella",
    "酵母",
)

ECOLI_CUES = (
    "e. coli",
    "e coli",
    "ecoli",
    "escherichia",
    "bl21",
    "k-12",
    "大肠杆菌",
)

MAMMALIAN_CUES = (
    "mammalian",
    "hek293",
    "cho",
    "hela",
    "293t",
    "human cell",
    "哺乳",
    "哺乳动物",
)

FUTURE_PATHWAY_CUES = (
    "pathway",
    "metabolic",
    "biosynthesis",
    "biosynthetic",
    "metabolite",
    "product biosynthesis",
    "secondary metabolite",
    "生物合成",
    "代谢通路",
    "代谢途径",
    "代谢产物",
)

FUTURE_CIRCUIT_CUES = (
    "circuit",
    "regulatory module",
    "module",
    "logic gate",
    "toggle",
    "switch",
    "feedback",
    "sensor",
    "repressor",
    "gene network",
    "基因回路",
    "调控模块",
)

SOURCE_CUES = (
    "source",
    "provenance",
    "reference",
    "literature",
    "paper",
    "doi",
    "database",
    "来源",
    "出处",
    "文献",
    "参考",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower_text(*values: Any) -> str:
    return " ".join(_text(value).lower() for value in values if _text(value))


def _flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, Mapping):
        return " ".join(_flatten_text(item) for item in value.values() if _flatten_text(item))
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return " ".join(_flatten_text(item) for item in value if _flatten_text(item))
    return _text(value)


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _text(value)
        if not clean:
            continue
        key = clean.casefold()
        if key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _has_any(text: str, cues: Sequence[str]) -> bool:
    return any(cue in text for cue in cues)


def _presence(text: str, cues: Sequence[str], context: Mapping[str, Any], keys: Sequence[str]) -> bool:
    if _has_any(text, cues):
        return True
    return any(_text(context.get(key)) for key in keys)


def _host_notes(text: str, context: Mapping[str, Any]) -> list[str]:
    notes: list[str] = []
    if _has_any(text, PLANT_CUES) or _text(context.get("host_system")).lower() == "plant":
        notes.append("plant context noted; host suitability not judged")
    if _has_any(text, YEAST_CUES):
        notes.append("host context noted: yeast; host suitability not judged")
    if _has_any(text, ECOLI_CUES):
        notes.append("host context noted: E. coli; host suitability not judged")
    if _has_any(text, MAMMALIAN_CUES):
        notes.append("host context noted: mammalian; host suitability not judged")
    return _unique(notes)


def _route_context_notes(route_category: str, host_notes: Sequence[str]) -> list[str]:
    notes = list(BASE_BOUNDARY_NOTES)
    if host_notes:
        notes.extend(host_notes)
    if route_category == ROUTE_CATEGORY_FUTURE:
        notes.append("future route candidate only; not active in this skeleton")
    return _unique(notes)


def _route_confidence(route_category: str, text: str, host_notes: Sequence[str]) -> str:
    if route_category == ROUTE_CATEGORY_FALLBACK:
        return CONFIDENCE_LOW
    if route_category == ROUTE_CATEGORY_FUTURE:
        return CONFIDENCE_MEDIUM
    if _has_any(text, ACTIVE_ROUTE_CUES) and host_notes:
        return CONFIDENCE_HIGH
    if _has_any(text, ACTIVE_ROUTE_CUES):
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_MEDIUM


def _present_slots(text: str, context: Mapping[str, Any]) -> dict[str, bool]:
    return {
        "target_identity": _presence(
            text,
            TARGET_CUES,
            context,
            ("target", "target_identity", "target_name", "target_product", "goal"),
        ),
        "host_system": _presence(
            text,
            PLANT_CUES + YEAST_CUES + ECOLI_CUES + MAMMALIAN_CUES,
            context,
            ("host", "host_system", "organism", "species", "expression_host"),
        ),
        "construct_or_vector_context": _presence(
            text,
            ("construct", "vector", "cassette", "plasmid", "backbone", "expression vector"),
            context,
            ("construct", "vector", "cassette", "plasmid", "backbone", "expression_vector"),
        ),
        "source_or_provenance": _presence(
            text,
            SOURCE_CUES,
            context,
            ("source", "source_provenance", "provenance", "reference", "evidence"),
        ),
        "manual_review_context": _presence(
            text,
            ("review", "manual review", "documentation", "documentation-only", "复核", "审阅"),
            context,
            ("review_context", "notes"),
        ),
        "target_pathway_or_product": _presence(
            text,
            FUTURE_PATHWAY_CUES,
            context,
            ("pathway", "product", "metabolite", "goal"),
        ),
        "circuit_or_module_goal": _presence(
            text,
            FUTURE_CIRCUIT_CUES,
            context,
            ("circuit", "module", "goal", "function"),
        ),
    }


def _missing_slots(required_slots: Sequence[str], present_slots: Mapping[str, bool]) -> list[str]:
    return [slot for slot in required_slots if not present_slots.get(slot, False)]


def _active_mainline_result(
    *,
    text: str,
    context: Mapping[str, Any],
    host_notes: Sequence[str],
    route_value: str,
    route_category: str,
) -> dict[str, Any]:
    present = _present_slots(text, context)
    required_slots = list(BASE_REQUIRED_SLOTS)
    missing = _missing_slots(required_slots, present)
    if _has_any(text, PLANT_CUES):
        route_value = PLANT_MAINLINE_ROUTE
    elif _has_any(text, YEAST_CUES + ECOLI_CUES + MAMMALIAN_CUES):
        route_value = HOST_MAINLINE_ROUTE

    if route_value == PLANT_MAINLINE_ROUTE:
        stages = ["intent review", "plant context review", *ACTIVE_REVIEW_STAGES[1:]]
    elif route_value == HOST_MAINLINE_ROUTE:
        stages = ACTIVE_REVIEW_STAGES[:]
    else:
        stages = ACTIVE_REVIEW_STAGES[:]

    return {
        "matched_workflow_route": route_value,
        "route_category": route_category,
        "confidence_category": _route_confidence(route_category, text, host_notes),
        "suggested_review_stages": _unique(stages),
        "required_information_slots": required_slots,
        "missing_information_slots": missing,
        "safe_next_review_action": (
            "Open the expression construct review mainline and record the missing target, host, construct/vector, "
            "and source/provenance details."
        ),
        "documentation_only_boundary_notes": list(_route_context_notes(route_category, host_notes)),
        "manual_review_required": True,
    }


def _future_route_result(
    *,
    text: str,
    context: Mapping[str, Any],
    host_notes: Sequence[str],
    route_value: str,
) -> dict[str, Any]:
    present = _present_slots(text, context)
    if route_value == FUTURE_METABOLIC_ROUTE:
        required_slots = list(PATHWAY_REQUIRED_SLOTS)
        missing = _missing_slots(required_slots, present)
        safe_action = (
            "Keep this as a future route candidate and collect pathway or product context for manual review."
        )
    else:
        required_slots = list(CIRCUIT_REQUIRED_SLOTS)
        missing = _missing_slots(required_slots, present)
        safe_action = (
            "Keep this as a future route candidate and collect circuit or module context for manual review."
        )

    return {
        "matched_workflow_route": route_value,
        "route_category": ROUTE_CATEGORY_FUTURE,
        "confidence_category": _route_confidence(ROUTE_CATEGORY_FUTURE, text, host_notes),
        "suggested_review_stages": list(FUTURE_ROUTE_STAGES),
        "required_information_slots": required_slots,
        "missing_information_slots": missing,
        "safe_next_review_action": safe_action,
        "documentation_only_boundary_notes": list(_route_context_notes(ROUTE_CATEGORY_FUTURE, host_notes)),
        "manual_review_required": True,
    }


def _fallback_result(*, text: str, context: Mapping[str, Any], host_notes: Sequence[str]) -> dict[str, Any]:
    present = _present_slots(text, context)
    required_slots = list(BASE_REQUIRED_SLOTS)
    missing = _missing_slots(required_slots, present)
    return {
        "matched_workflow_route": FALLBACK_ROUTE,
        "route_category": ROUTE_CATEGORY_FALLBACK,
        "confidence_category": CONFIDENCE_LOW,
        "suggested_review_stages": [
            "intent review",
            "target clarification review",
            "host clarification review",
            "construct/vector clarification review",
            "source/provenance review",
        ],
        "required_information_slots": required_slots,
        "missing_information_slots": missing,
        "safe_next_review_action": (
            "Collect target, host, construct/vector, and source/provenance information before entering the review mainline."
        ),
        "documentation_only_boundary_notes": list(_route_context_notes(ROUTE_CATEGORY_FALLBACK, host_notes)),
        "manual_review_required": True,
    }


def route_expression_construct_workflow(
    user_intent_text: str,
    context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Map user intent text to a deterministic documentation-only expression construct review route."""
    context_map = context if isinstance(context, Mapping) else {}
    intent_text = _text(user_intent_text)
    context_text = _flatten_text(context_map)
    combined_text = _lower_text(intent_text, context_text)
    host_notes = _host_notes(combined_text, context_map)

    if _has_any(combined_text, FUTURE_PATHWAY_CUES):
        return _future_route_result(
            text=combined_text,
            context=context_map,
            host_notes=host_notes,
            route_value=FUTURE_METABOLIC_ROUTE,
        )
    if _has_any(combined_text, FUTURE_CIRCUIT_CUES):
        return _future_route_result(
            text=combined_text,
            context=context_map,
            host_notes=host_notes,
            route_value=FUTURE_CIRCUIT_ROUTE,
        )
    if _has_any(combined_text, ACTIVE_ROUTE_CUES) or host_notes:
        return _active_mainline_result(
            text=combined_text,
            context=context_map,
            host_notes=host_notes,
            route_value=ACTIVE_MAINLINE_ROUTE,
            route_category=ROUTE_CATEGORY_ACTIVE,
        )
    return _fallback_result(text=combined_text, context=context_map, host_notes=host_notes)
