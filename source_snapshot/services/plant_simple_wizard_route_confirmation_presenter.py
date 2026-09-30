from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.plant_simple_wizard_intent_intake_presenter import (
    build_simple_plant_wizard_intent_intake_presenter,
)
from services.plant_simple_wizard_route_schema import (
    HANDOFF_STAGE_ID,
    get_simple_plant_wizard_route,
)


CONFIRMATION_ACTIONS: tuple[dict[str, Any], ...] = (
    {
        "action_id": "confirm_route",
        "label_zh": "确认路线并进入资料补齐",
        "requires_user_confirmation": True,
    },
    {
        "action_id": "change_route",
        "label_zh": "修改目标描述",
        "requires_user_confirmation": False,
    },
)

SAFE_BOUNDARY_NOTES_ZH: tuple[str, ...] = (
    "本结果只回读系统对文档目标的理解，不代表生物学建议或实验判断。",
    "确认路线只会展开资料清单和审查包草稿入口，不会保存数据、创建项目或导出文件。",
)

LOW_CONFIDENCE_QUESTIONS_ZH: tuple[str, ...] = (
    "你更接近蛋白表达、代谢路线、多基因构建，还是调控模块？",
    "现在已有目标基因、目标产物、宿主植物、调控元件或文献证据中的哪几类材料？",
)

AMBIGUOUS_PRODUCT_QUESTIONS_ZH: tuple[str, ...] = (
    "代谢路线",
    "表达其中某个酶 / 蛋白",
    "多基因构建",
)

AMBIGUOUS_PRODUCT_TERMS: tuple[str, ...] = (
    "artemisinin",
    "青蒿素",
    "natural product",
    "target product",
)

RESULT_ROUTE_LABELS_ZH: dict[str, str] = {
    "plant_protein_expression_review": "蛋白表达审查",
    "plant_metabolic_pathway_review": "代谢路线审查",
    "plant_multigene_construct_review": "多基因构建审查",
    "plant_regulatory_module_review": "调控模块审查",
}

MULTIGENE_TERMS: tuple[str, ...] = (
    "multi",
    "multiple genes",
    "multigene",
    "多基因",
    "多表达盒",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _route_summary(route_id: str | None) -> dict[str, Any] | None:
    if not route_id:
        return None
    route = get_simple_plant_wizard_route(route_id)
    if not route:
        return None
    return {
        "route_id": route["route_id"],
        "label_zh": route["label_zh"],
        "result_label_zh": RESULT_ROUTE_LABELS_ZH.get(route["route_id"], route["label_zh"]),
        "label_en": route["label_en"],
        "button_label_zh": route["button_label_zh"],
        "short_description_zh": route["short_description_zh"],
        "requires_user_confirmation": True,
    }


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    route = _route_summary(_text(candidate.get("route_id")))
    if not route:
        return {}
    route["match_reasons_zh"] = list(candidate.get("match_reasons_zh") or [])
    route["uncertainties_zh"] = list(candidate.get("uncertainties_zh") or [])
    route["score"] = int(candidate.get("score") or 0)
    return route


def _intent_from_options(options: dict[str, Any] | None) -> dict[str, Any]:
    clean_options = dict(options or {})
    return build_simple_plant_wizard_intent_intake_presenter(
        user_goal_text=_text(clean_options.get("user_goal_text")),
        selected_goal_type=clean_options.get("selected_goal_type"),
        available_materials=list(clean_options.get("available_materials") or []),
        options=None,
    )


def _is_ambiguous_product_goal(intent_payload: dict[str, Any]) -> bool:
    input_summary = dict(intent_payload.get("input_summary") or {})
    text = _text(input_summary.get("user_goal_text")).casefold()
    if not text:
        return False
    has_product_term = any(term.casefold() in text for term in AMBIGUOUS_PRODUCT_TERMS)
    has_multigene_term = any(term.casefold() in text for term in MULTIGENE_TERMS)
    return has_product_term and not has_multigene_term


def _alternative_route_ids(
    *,
    intent_payload: dict[str, Any],
    recommended_route_id: str | None,
    force_product_ambiguity: bool,
) -> list[str]:
    if force_product_ambiguity:
        return [
            "plant_metabolic_pathway_review",
            "plant_multigene_construct_review",
        ]
    ids: list[str] = []
    for candidate in intent_payload.get("route_candidates") or []:
        if not isinstance(candidate, dict):
            continue
        route_id = _text(candidate.get("route_id"))
        if route_id and route_id != recommended_route_id and route_id not in ids:
            ids.append(route_id)
    return ids


def _prioritized_match_reasons(reasons: list[str]) -> list[str]:
    unique_reasons = list(dict.fromkeys(_text(reason) for reason in reasons if _text(reason)))
    specific_reasons = [
        reason
        for reason in unique_reasons
        if not reason.startswith("用户目标文本包含")
    ]
    generic_reasons = [reason for reason in unique_reasons if reason not in specific_reasons]
    return (specific_reasons + generic_reasons)[:3]


def _confirmation_state(
    *,
    intent_payload: dict[str, Any],
    selected_route_id: str | None,
) -> tuple[str | None, list[str], list[str], str, str]:
    confidence = _text(intent_payload.get("confidence")) or "low"
    decision_state = _text(intent_payload.get("decision_state"))
    force_product_ambiguity = _is_ambiguous_product_goal(intent_payload)

    if confidence == "low" or decision_state == "needs_clarification" or force_product_ambiguity:
        route_ids = _alternative_route_ids(
            intent_payload=intent_payload,
            recommended_route_id=None,
            force_product_ambiguity=force_product_ambiguity,
        )
        questions = (
            list(AMBIGUOUS_PRODUCT_QUESTIONS_ZH)
            if force_product_ambiguity
            else list(intent_payload.get("clarification_questions_zh") or LOW_CONFIDENCE_QUESTIONS_ZH)
        )
        return (
            None,
            route_ids,
            questions[:3],
            "needs_clarification",
            "需要更多信息后再由用户确认路线，不强制进入任何路线。",
        )

    selected = _text(selected_route_id)
    route_id = selected if _route_summary(selected) else _text(intent_payload.get("recommended_route_id"))
    alternative_ids = _alternative_route_ids(
        intent_payload=intent_payload,
        recommended_route_id=route_id,
        force_product_ambiguity=False,
    )
    questions = [] if confidence == "high" else list(intent_payload.get("clarification_questions_zh") or [])[:3]
    return (
        route_id or None,
        alternative_ids,
        questions,
        "ready_for_user_confirmation",
        _text(intent_payload.get("confidence_reason_zh")),
    )


def build_simple_plant_wizard_route_confirmation_presenter(
    intent_payload: dict[str, Any] | None = None,
    selected_route_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic read-only confirmation card payload for Simple Plant Wizard."""
    source_payload = deepcopy(intent_payload) if isinstance(intent_payload, dict) else _intent_from_options(options)
    recommended_route_id, alternative_ids, questions, state, confidence_reason = _confirmation_state(
        intent_payload=source_payload,
        selected_route_id=selected_route_id,
    )

    candidate_summaries = [
        _candidate_summary(candidate)
        for candidate in source_payload.get("route_candidates") or []
        if isinstance(candidate, dict)
    ]
    candidate_summaries = [candidate for candidate in candidate_summaries if candidate]
    recommended_route = _route_summary(recommended_route_id)
    alternative_routes = [
        route
        for route in (_route_summary(route_id) for route_id in alternative_ids)
        if route is not None
    ]

    match_reasons: list[str] = []
    uncertainties: list[str] = []
    for candidate in candidate_summaries:
        match_reasons.extend(candidate.get("match_reasons_zh") or [])
        uncertainties.extend(candidate.get("uncertainties_zh") or [])

    if state == "needs_clarification":
        uncertainties.append("当前信息不足，必须先澄清再确认。")

    return {
        "page_title_zh": "系统判断",
        "page_subtitle_zh": "系统只整理目标描述和候选路线，确认前不会进入后续资料清单。",
        "interpreted_goal_zh": _text(source_payload.get("interpreted_goal_zh")),
        "recommended_route": recommended_route,
        "alternative_routes": alternative_routes,
        "confidence": _text(source_payload.get("confidence")) or "low",
        "confidence_label_zh": {
            "high": "置信度：高",
            "medium": "置信度：中等",
            "low": "置信度：较低",
        }.get(_text(source_payload.get("confidence")), "置信度：较低"),
        "confidence_reason_zh": confidence_reason,
        "match_reasons_zh": _prioritized_match_reasons(match_reasons),
        "uncertainties_zh": list(dict.fromkeys(uncertainties)),
        "clarification_questions_zh": list(dict.fromkeys(questions))[:3],
        "decision_state": state,
        "confirmation_actions": deepcopy(list(CONFIRMATION_ACTIONS)),
        "safe_boundary_notes_zh": list(SAFE_BOUNDARY_NOTES_ZH),
        "handoff_stage_id": HANDOFF_STAGE_ID,
    }
