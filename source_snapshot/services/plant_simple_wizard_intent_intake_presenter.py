from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.plant_simple_wizard_route_schema import (
    HANDOFF_STAGE_ID,
    get_simple_plant_wizard_entry_routes,
)


GOAL_TYPE_TO_ROUTE_ID = {
    "protein_expression": "plant_protein_expression_review",
    "metabolic_pathway": "plant_metabolic_pathway_review",
    "multigene_construct": "plant_multigene_construct_review",
    "regulatory_module": "plant_regulatory_module_review",
}

MATERIAL_TO_ROUTE_HINTS = {
    "target_gene_or_cds": ("plant_protein_expression_review",),
    "target_product": ("plant_metabolic_pathway_review",),
    "host_plant": (),
    "promoter_or_vector": (
        "plant_protein_expression_review",
        "plant_multigene_construct_review",
        "plant_regulatory_module_review",
    ),
    "literature_evidence": (),
}

ROUTE_KEYWORDS = {
    "plant_protein_expression_review": (
        "protein",
        "enzyme",
        "express",
        "expression",
        "enzyme expression",
        "express enzyme",
        "express protein",
        "cds",
        "target gene",
        "目标蛋白",
        "蛋白",
        "白蛋白",
        "种子蛋白",
        "抗原",
        "抗原蛋白",
        "酶表达",
        "表达酶",
        "表达蛋白",
        "表达白蛋白",
        "表达种子蛋白",
        "表达抗原",
        "表达目标基因",
    ),
    "plant_metabolic_pathway_review": (
        "target product",
        "natural product",
        "pathway",
        "metabolism",
        "metabolic",
        "artemisinin",
        "terpenoid",
        "flavonoid",
        "alkaloid",
        "specialized metabolite",
        "specialized metabolites",
        "sweet metabolism",
        "目标产物",
        "天然产物",
        "通路",
        "代谢",
        "青蒿素",
        "萜",
        "黄酮",
        "生物碱",
        "专门代谢物",
        "甜味代谢",
    ),
    "plant_multigene_construct_review": (
        "multiple genes",
        "multi gene",
        "multigene",
        "multiple enzymes",
        "multi enzyme",
        "multi-cassette",
        "multi cassette",
        "stacked expression",
        "several modules",
        "several cassettes",
        "多个基因",
        "多基因",
        "多个酶",
        "多酶",
        "多表达盒",
        "多个表达盒",
        "叠加表达",
        "多个模块",
    ),
    "plant_regulatory_module_review": (
        "promoter",
        "tf",
        "transcription factor",
        "cis-element",
        "cis element",
        "inducible expression",
        "tissue-specific expression",
        "reporter module",
        "stress response",
        "regulatory module",
        "启动子",
        "转录因子",
        "顺式元件",
        "诱导表达",
        "组织特异",
        "报告模块",
        "胁迫响应",
        "调控模块",
    ),
}

GENERIC_PRODUCT_PHRASES = (
    "make ",
    "produce ",
    "do ",
    "做",
    "生产",
    "产生",
)

EXPRESSION_SIGNAL_TERMS = (
    "express",
    "expression",
    "表达",
)

PROTEIN_SIGNAL_TERMS = (
    "protein",
    "enzyme",
    "albumin",
    "antigen",
    "蛋白",
    "白蛋白",
    "种子蛋白",
    "抗原",
    "酶",
)

PLANT_HOST_SIGNAL_TERMS = (
    "plant",
    "rice",
    "tobacco",
    "seed",
    "植物",
    "水稻",
    "烟草",
    "种子",
)

SAFE_BOUNDARY_NOTES_ZH = [
    "本页面只整理本地项目文档意图、候选路线和人工复核问题。",
    "路线候选不是自动生物学建议，也不代表最终组件选择。",
    "本步骤不生成实验步骤、不改写序列、不预测表达或产量，也不判断实验可用性。",
    "用户确认后仍只是进入文档记录和人工复核流程。",
]

EMPTY_CLARIFICATION_QUESTIONS_ZH = [
    "你想先整理蛋白/酶表达记录、代谢通路记录、多基因构建记录，还是调控模块记录？",
    "你现在已有目标基因、目标产物、宿主植物、启动子/载体或文献证据中的哪几类材料？",
]

AMBIGUOUS_PRODUCT_QUESTIONS_ZH = [
    "你是想整理青蒿素相关代谢路线？",
    "你是想表达其中某个酶 / 蛋白？",
    "你是想做多个酶的多基因构建？",
]


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _route_lookup() -> dict[str, dict[str, Any]]:
    return {route["route_id"]: route for route in get_simple_plant_wizard_entry_routes()}


def _new_scorecard() -> dict[str, dict[str, Any]]:
    return {
        route_id: {"score": 0, "match_reasons_zh": [], "uncertainties_zh": []}
        for route_id in GOAL_TYPE_TO_ROUTE_ID.values()
    }


def _add_score(
    scorecard: dict[str, dict[str, Any]],
    route_id: str,
    amount: int,
    reason_zh: str,
) -> None:
    scorecard[route_id]["score"] += amount
    if reason_zh not in scorecard[route_id]["match_reasons_zh"]:
        scorecard[route_id]["match_reasons_zh"].append(reason_zh)


def _add_uncertainty(
    scorecard: dict[str, dict[str, Any]], route_id: str, uncertainty_zh: str
) -> None:
    if uncertainty_zh not in scorecard[route_id]["uncertainties_zh"]:
        scorecard[route_id]["uncertainties_zh"].append(uncertainty_zh)


def _apply_selected_goal_type(
    scorecard: dict[str, dict[str, Any]], selected_goal_type: str | None
) -> None:
    selected = _normalize_text(selected_goal_type)
    route_id = GOAL_TYPE_TO_ROUTE_ID.get(selected)
    if route_id:
        _add_score(scorecard, route_id, 4, "用户选择的目标类型与此路线最接近。")
    elif selected == "unsure":
        for route_id in scorecard:
            _add_uncertainty(scorecard, route_id, "用户选择了不确定，需要先确认路线方向。")


def _apply_material_hints(
    scorecard: dict[str, dict[str, Any]], available_materials: list[str] | None
) -> None:
    for material in available_materials or []:
        normalized = _normalize_text(material)
        if not normalized or normalized == "none":
            continue
        for route_id in MATERIAL_TO_ROUTE_HINTS.get(normalized, ()):
            _add_score(scorecard, route_id, 1, f"已提供的材料包含 {normalized}。")


def _apply_text_keywords(scorecard: dict[str, dict[str, Any]], text: str) -> None:
    text_lower = text.casefold()
    for route_id, keywords in ROUTE_KEYWORDS.items():
        matched = [keyword for keyword in keywords if keyword.casefold() in text_lower]
        if matched:
            _add_score(
                scorecard,
                route_id,
                min(3, len(matched)),
                "用户目标文本包含与此路线相关的关键词。",
            )


def _has_any_term(text: str, terms: tuple[str, ...]) -> bool:
    text_lower = text.casefold()
    return any(term.casefold() in text_lower for term in terms)


def _apply_clear_protein_expression_pattern(
    scorecard: dict[str, dict[str, Any]], text: str
) -> None:
    if not text:
        return
    has_expression = _has_any_term(text, EXPRESSION_SIGNAL_TERMS)
    has_protein = _has_any_term(text, PROTEIN_SIGNAL_TERMS)
    if not (has_expression and has_protein):
        return

    route_id = "plant_protein_expression_review"
    _add_score(scorecard, route_id, 2, "提到了“表达”")
    if "种子蛋白" in text:
        protein_reason = "提到了“种子蛋白”"
    elif "白蛋白" in text:
        protein_reason = "提到了“白蛋白”"
    elif "抗原" in text:
        protein_reason = "提到了“抗原蛋白”"
    elif "酶" in text:
        protein_reason = "提到了“酶”"
    else:
        protein_reason = "提到了“蛋白”"
    _add_score(scorecard, route_id, 2, protein_reason)
    if "水稻" in text:
        host_reason = "提到了植物宿主“水稻”"
    elif "烟草" in text:
        host_reason = "提到了植物宿主“烟草”"
    elif "植物" in text:
        host_reason = "提到了植物语境“植物”"
    elif "seed" in text.casefold() or "种子" in text:
        host_reason = "提到了植物表达语境“种子”"
    else:
        host_reason = ""
    if host_reason:
        _add_score(scorecard, route_id, 1, host_reason)


def _has_keyword_for(route_id: str, text: str) -> bool:
    text_lower = text.casefold()
    return any(keyword.casefold() in text_lower for keyword in ROUTE_KEYWORDS[route_id])


def _looks_like_broad_product_goal(text: str) -> bool:
    if not text:
        return False
    text_lower = text.casefold()
    has_product_signal = _has_keyword_for("plant_metabolic_pathway_review", text)
    has_generic_phrase = any(phrase.casefold() in text_lower for phrase in GENERIC_PRODUCT_PHRASES)
    has_specific_route_detail = any(
        _has_keyword_for(route_id, text)
        for route_id in (
            "plant_protein_expression_review",
            "plant_multigene_construct_review",
            "plant_regulatory_module_review",
        )
    )
    return has_product_signal and has_generic_phrase and not has_specific_route_detail


def _mark_conflicts_and_missing_context(
    scorecard: dict[str, dict[str, Any]],
    text: str,
    selected_goal_type: str | None,
) -> None:
    selected = _normalize_text(selected_goal_type)
    selected_route_id = GOAL_TYPE_TO_ROUTE_ID.get(selected)
    matched_route_ids = [
        route_id for route_id, card in scorecard.items() if card["score"] > 0
    ]
    if selected_route_id and any(route_id != selected_route_id for route_id in matched_route_ids):
        for route_id in matched_route_ids:
            _add_uncertainty(
                scorecard,
                route_id,
                "用户选择的目标类型与文本关键词不完全一致，需要人工确认。",
            )
    if _looks_like_broad_product_goal(text):
        for route_id in (
            "plant_metabolic_pathway_review",
            "plant_protein_expression_review",
            "plant_multigene_construct_review",
        ):
            _add_uncertainty(
                scorecard,
                route_id,
                "目标产物描述较宽，需要确认是通路复核、蛋白/酶表达记录，还是多基因构建记录。",
            )


def _candidate_route_ids(scorecard: dict[str, dict[str, Any]], text: str) -> list[str]:
    scored = [
        (route_id, card["score"])
        for route_id, card in scorecard.items()
        if card["score"] > 0
    ]
    if not scored:
        return list(GOAL_TYPE_TO_ROUTE_ID.values()) if not text else []

    scored.sort(key=lambda item: (-item[1], list(GOAL_TYPE_TO_ROUTE_ID.values()).index(item[0])))
    top_score = scored[0][1]
    included = [route_id for route_id, score in scored if score >= max(1, top_score - 2)]

    if _looks_like_broad_product_goal(text):
        for route_id in (
            "plant_metabolic_pathway_review",
            "plant_protein_expression_review",
            "plant_multigene_construct_review",
        ):
            if route_id not in included:
                included.append(route_id)
    return included


def _build_candidate(
    route: dict[str, Any], scorecard_entry: dict[str, Any], text: str
) -> dict[str, Any]:
    uncertainties = list(scorecard_entry["uncertainties_zh"])
    if not text:
        uncertainties.append("用户还没有输入目标，需要先补充意图和已有材料。")

    return {
        "route_id": route["route_id"],
        "label_zh": route["label_zh"],
        "button_label_zh": route["button_label_zh"],
        "match_reasons_zh": scorecard_entry["match_reasons_zh"]
        or ["暂无明确关键词，作为入门候选路线展示。"],
        "uncertainties_zh": uncertainties,
        "score": int(scorecard_entry["score"]),
        "requires_user_confirmation": True,
    }


def _confidence_and_decision(
    *,
    text: str,
    candidates: list[dict[str, Any]],
    selected_goal_type: str | None,
) -> tuple[str, str, str]:
    if not text and not _normalize_text(selected_goal_type):
        return (
            "low",
            "needs_clarification",
            "还没有足够目标信息，只能先提示用户补充意图。",
        )
    if not candidates:
        return (
            "low",
            "needs_clarification",
            "未识别到稳定路线信号，需要用户先说明目标类型。",
        )
    if _looks_like_broad_product_goal(text):
        return (
            "medium",
            "needs_clarification",
            "目标产物信号存在，但尚不能区分通路、蛋白/酶表达或多基因构建记录。",
        )

    top_score = candidates[0]["score"]
    close_candidates = [candidate for candidate in candidates if candidate["score"] >= top_score - 1]
    has_uncertainty = any(candidate["uncertainties_zh"] for candidate in candidates)
    if top_score >= 3 and len(close_candidates) == 1 and not has_uncertainty:
        return (
            "high",
            "ready_for_user_confirmation",
            "用户选择和文本关键词集中指向同一条路线，但仍需要用户确认。",
        )
    if top_score >= 2:
        return (
            "medium",
            "ready_for_user_confirmation",
            "文本或用户选择提供了路线信号，但候选仍需用户确认。",
        )
    return (
        "low",
        "needs_clarification",
        "路线信号较弱，需要先回答澄清问题。",
    )


def _clarification_questions(
    *, text: str, decision_state: str, candidates: list[dict[str, Any]]
) -> list[str]:
    if not text:
        return list(EMPTY_CLARIFICATION_QUESTIONS_ZH)
    if _looks_like_broad_product_goal(text):
        return list(AMBIGUOUS_PRODUCT_QUESTIONS_ZH)
    if decision_state == "needs_clarification":
        return [
            "请说明你更接近蛋白/酶表达、代谢通路、多基因构建，还是调控模块记录。",
            "请补充现在已有的目标基因、目标产物、宿主植物、启动子/载体或文献证据。",
        ]
    questions: list[str] = []
    for candidate in candidates[:2]:
        route = _route_lookup().get(candidate["route_id"], {})
        questions.extend(route.get("clarification_prompts_zh", [])[:1])
    return questions


def _interpreted_goal(text: str, selected_goal_type: str | None) -> str:
    if text:
        return f"根据当前输入，系统仅整理为待确认的植物文档意图：{text}"
    if _normalize_text(selected_goal_type):
        return "用户已选择目标类型，但还需要补充具体植物项目目标。"
    return "请先描述你想整理的植物项目目标。"


def build_simple_plant_wizard_intent_intake_presenter(
    user_goal_text: str = "",
    selected_goal_type: str | None = None,
    available_materials: list[str] | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic documentation-only route-intake presenter payload."""
    del options

    text = _normalize_text(user_goal_text)
    scorecard = _new_scorecard()
    _apply_selected_goal_type(scorecard, selected_goal_type)
    _apply_material_hints(scorecard, available_materials)
    _apply_text_keywords(scorecard, text)
    _apply_clear_protein_expression_pattern(scorecard, text)
    _mark_conflicts_and_missing_context(scorecard, text, selected_goal_type)

    route_lookup = _route_lookup()
    candidate_ids = _candidate_route_ids(scorecard, text)
    candidates = [
        _build_candidate(route_lookup[route_id], scorecard[route_id], text)
        for route_id in candidate_ids
    ]
    confidence, decision_state, confidence_reason = _confidence_and_decision(
        text=text,
        candidates=candidates,
        selected_goal_type=selected_goal_type,
    )
    recommended_route_id = candidates[0]["route_id"] if candidates else None

    payload = {
        "page_title_zh": "Simple Plant Wizard 意图确认",
        "page_subtitle_zh": "先把目标整理成候选文档路线，再由用户确认后进入下一步。",
        "input_summary": {
            "user_goal_text": text,
            "selected_goal_type": _normalize_text(selected_goal_type) or None,
            "available_materials": list(available_materials or []),
        },
        "interpreted_goal_zh": _interpreted_goal(text, selected_goal_type),
        "route_candidates": candidates,
        "recommended_route_id": recommended_route_id,
        "confidence": confidence,
        "confidence_reason_zh": confidence_reason,
        "decision_state": decision_state,
        "clarification_questions_zh": _clarification_questions(
            text=text, decision_state=decision_state, candidates=candidates
        ),
        "route_confirmation_prompt_zh": "请用户确认是否采用上方候选路线；未确认前不进入路线选择。",
        "safe_boundary_notes_zh": deepcopy(SAFE_BOUNDARY_NOTES_ZH),
        "handoff_stage_id": HANDOFF_STAGE_ID,
    }
    return payload
