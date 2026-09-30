from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.plant_simple_wizard_route_schema import (
    HANDOFF_STAGE_ID,
    get_simple_plant_wizard_entry_routes,
    get_simple_plant_wizard_handoff_stage,
)


SAFE_BOUNDARY_NOTES_ZH: tuple[str, ...] = (
    "本工具只用于实验前设计审查和资料整理，结果需要人工复核。",
)

QUICK_SELECT_OPTIONS: tuple[dict[str, str], ...] = (
    {"option_id": "protein_expression", "label_zh": "蛋白表达"},
    {"option_id": "metabolic_pathway", "label_zh": "代谢路线"},
    {"option_id": "multigene_construct", "label_zh": "多基因构建"},
    {"option_id": "regulatory_module", "label_zh": "调控模块"},
)


def _route_card(route: dict[str, Any]) -> dict[str, Any]:
    return {
        "route_id": route["route_id"],
        "label_zh": route["label_zh"],
        "label_en": route["label_en"],
        "button_label_zh": route["button_label_zh"],
        "short_description_zh": route["short_description_zh"],
        "examples_zh": list(route["examples_zh"]),
        "primary_user_goal_zh": route["primary_user_goal_zh"],
        "required_slot_count": len(route.get("required_slots", [])),
        "handoff_stage_id": route["handoff_stage_id"],
        "requires_user_confirmation": True,
    }


def build_simple_plant_wizard_homepage_presenter(
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the beginner-facing single-step Simple Plant Wizard payload."""
    del options

    entry_routes = get_simple_plant_wizard_entry_routes()
    handoff_stage = get_simple_plant_wizard_handoff_stage()

    return {
        "page_title_zh": "我们要帮你审查什么植物设计？",
        "page_subtitle_zh": "用一句话描述目标，系统会先判断路线，再告诉你还缺哪些信息。",
        "goal_input_label_zh": "植物设计目标",
        "goal_input_placeholder_zh": "例如：我想在水稻中表达一个种子蛋白",
        "primary_action_label_zh": "开始分析",
        "quick_select_options": deepcopy(list(QUICK_SELECT_OPTIONS)),
        "route_cards": [_route_card(route) for route in entry_routes],
        "shared_handoff_stage": deepcopy(handoff_stage),
        "safe_boundary_notes_zh": list(SAFE_BOUNDARY_NOTES_ZH),
        "advanced_detail_hint_zh": "高级审查细节保留在审查员模式中，默认不展示。",
        "handoff_stage_id": HANDOFF_STAGE_ID,
    }
