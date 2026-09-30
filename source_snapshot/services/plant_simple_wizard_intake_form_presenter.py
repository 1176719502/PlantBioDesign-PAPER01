from __future__ import annotations

from copy import deepcopy
from typing import Any


SELECTED_GOAL_TYPE_OPTIONS: tuple[dict[str, str], ...] = (
    {
        "option_id": "protein_expression",
        "label_zh": "蛋白表达",
        "helper_zh": "整理目标蛋白、目标基因或 CDS 的植物表达设计记录。",
    },
    {
        "option_id": "metabolic_pathway",
        "label_zh": "代谢路线",
        "helper_zh": "整理目标产物、代谢路线步骤、证据线索和待复核问题。",
    },
    {
        "option_id": "multigene_construct",
        "label_zh": "多基因构建",
        "helper_zh": "整理多个基因、表达盒或模块组合的文档审查材料。",
    },
    {
        "option_id": "regulatory_module",
        "label_zh": "调控模块",
        "helper_zh": "整理启动子、转录因子、顺式元件或报告模块的审查材料。",
    },
)

AVAILABLE_MATERIAL_OPTIONS: tuple[dict[str, str], ...] = (
    {
        "option_id": "target_gene_or_cds",
        "label_zh": "目标基因或 CDS",
        "helper_zh": "已有目标基因、CDS 名称或序列来源线索。",
    },
    {
        "option_id": "target_product",
        "label_zh": "目标产物",
        "helper_zh": "已有天然产物、代谢物或目标产物名称。",
    },
    {
        "option_id": "host_plant",
        "label_zh": "宿主植物",
        "helper_zh": "已有拟整理的植物宿主或表达背景。",
    },
    {
        "option_id": "promoter_or_vector",
        "label_zh": "启动子或载体线索",
        "helper_zh": "已有启动子、载体、表达盒或调控元件线索。",
    },
    {
        "option_id": "literature_evidence",
        "label_zh": "文献证据",
        "helper_zh": "已有论文、数据库条目或本地证据记录。",
    },
    {
        "option_id": "none",
        "label_zh": "暂时没有材料",
        "helper_zh": "先从目标描述开始，后续再补充文档材料。",
    },
)

EXAMPLE_GOALS: tuple[dict[str, str], ...] = (
    {
        "route_family": "protein_expression",
        "example_zh": "我想在水稻中表达一个种子蛋白",
    },
    {
        "route_family": "metabolic_pathway",
        "example_zh": "我想整理青蒿素相关代谢路线的证据线索。",
    },
    {
        "route_family": "multigene_construct",
        "example_zh": "我想整理多个酶的多表达盒构建审查材料。",
    },
    {
        "route_family": "regulatory_module",
        "example_zh": "我想整理一个 promoter / TF 调控模块的文档审查材料。",
    },
)

SAFE_BOUNDARY_NOTES_ZH: tuple[str, ...] = (
    "本工具只用于实验前设计审查和资料整理，结果需要人工复核。",
)


def build_simple_plant_wizard_intake_form_presenter(
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic beginner intake-form payload for Simple Plant Wizard."""
    del options

    return {
        "page_title_zh": "我们要帮你审查什么植物设计？",
        "page_subtitle_zh": "用一句话描述目标，系统会先判断路线，再告诉你还缺哪些信息。",
        "goal_input_label_zh": "植物设计目标",
        "goal_input_placeholder_zh": "例如：我想在水稻中表达一个种子蛋白",
        "selected_goal_type_options": deepcopy(list(SELECTED_GOAL_TYPE_OPTIONS)),
        "available_material_options": deepcopy(list(AVAILABLE_MATERIAL_OPTIONS)),
        "submit_label_zh": "开始分析",
        "example_goals": deepcopy(list(EXAMPLE_GOALS)),
        "safe_boundary_notes_zh": list(SAFE_BOUNDARY_NOTES_ZH),
        "advanced_detail_hint_zh": "清单和审查包草稿入口只在确认路线后折叠显示；本表单不会写入数据。",
    }
