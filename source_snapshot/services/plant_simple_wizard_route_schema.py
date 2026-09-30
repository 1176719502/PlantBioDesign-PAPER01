from __future__ import annotations

from copy import deepcopy
from typing import Any


SCHEMA_ID = "simple_plant_wizard_route_schema"
SCHEMA_VERSION = "v2.7-r167"
HANDOFF_STAGE_ID = "plant_handoff_package_review"

ENTRY_ROUTE_IDS: tuple[str, ...] = (
    "plant_protein_expression_review",
    "plant_metabolic_pathway_review",
    "plant_multigene_construct_review",
    "plant_regulatory_module_review",
)

COMMON_SAFE_BOUNDARY_NOTES_ZH: tuple[str, ...] = (
    "本路线只整理植物项目的本地文档记录、证据线索、缺口和人工复核状态。",
    "路线信息不自动选择生物组件，不生成湿实验步骤，不改写序列，也不判断实验可用性。",
    "后续交付内容保持为文档草稿和人工/公司复核材料。",
)


def _entry_route(
    *,
    route_id: str,
    label_en: str,
    label_zh: str,
    button_label_zh: str,
    short_description_zh: str,
    examples_zh: list[str],
    primary_user_goal_zh: str,
    required_slots: list[str],
    clarification_prompts_zh: list[str],
    safe_boundary_notes_zh: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "route_id": route_id,
        "route_kind": "entry_route",
        "label_en": label_en,
        "label_zh": label_zh,
        "button_label_zh": button_label_zh,
        "short_description_zh": short_description_zh,
        "examples_zh": examples_zh,
        "primary_user_goal_zh": primary_user_goal_zh,
        "required_slots": required_slots,
        "clarification_prompts_zh": clarification_prompts_zh,
        "safe_boundary_notes_zh": list(safe_boundary_notes_zh or COMMON_SAFE_BOUNDARY_NOTES_ZH),
        "handoff_stage_id": HANDOFF_STAGE_ID,
    }


_ENTRY_ROUTES: tuple[dict[str, Any], ...] = (
    _entry_route(
        route_id="plant_protein_expression_review",
        label_en="Plant Protein Expression Review",
        label_zh="植物蛋白表达复核路线",
        button_label_zh="整理植物蛋白表达记录",
        short_description_zh="用于整理目标蛋白、植物宿主、表达语境、组件来源和证据缺口。",
        examples_zh=[
            "在水稻种子中记录某个目标蛋白的表达设计资料。",
            "为烟草叶片表达项目整理CDS来源、启动子语境和复核缺口。",
        ],
        primary_user_goal_zh="把植物蛋白表达想法整理成可人工复核的设计记录。",
        required_slots=[
            "target_protein",
            "gene_or_cds",
            "host_plant",
            "expression_context",
            "promoter",
            "signal_or_transit_peptide",
            "terminator",
            "marker_or_reporter",
            "vector_or_backbone",
            "evidence_records",
            "manual_review_status",
        ],
        clarification_prompts_zh=[
            "目标蛋白或基因/CDS来源是什么？",
            "希望记录的植物宿主、组织或表达语境是什么？",
            "已有启动子、定位肽、终止子、标记或载体骨架的来源记录吗？",
            "哪些证据记录已经有来源，哪些仍需人工补充？",
        ],
    ),
    _entry_route(
        route_id="plant_metabolic_pathway_review",
        label_en="Plant Metabolic Pathway Review",
        label_zh="植物代谢通路复核路线",
        button_label_zh="整理植物代谢通路记录",
        short_description_zh="用于整理目标产物、通路步骤、候选酶/基因、定位语境和证据缺口。",
        examples_zh=[
            "为某个植物天然产物通路整理前体、中间体和步骤证据。",
            "记录候选酶/基因与植物亚细胞定位语境，保留缺失步骤。",
        ],
        primary_user_goal_zh="把植物代谢通路想法整理成证据可追溯的路线复核材料。",
        required_slots=[
            "target_product",
            "pathway_overview",
            "pathway_step",
            "precursor_or_intermediate",
            "enzyme_or_gene_candidate",
            "subcellular_localization",
            "host_plant",
            "pathway_evidence",
            "enzyme_evidence",
            "missing_pathway_steps",
            "manual_review_status",
        ],
        clarification_prompts_zh=[
            "目标产物或通路家族是什么？",
            "目前已知的通路步骤、前体或中间体有哪些？",
            "候选酶/基因与定位语境有哪些证据来源？",
            "哪些通路步骤或证据仍然缺失，需要人工复核？",
        ],
    ),
    _entry_route(
        route_id="plant_multigene_construct_review",
        label_en="Plant Multigene Construct Review",
        label_zh="植物多基因构建复核路线",
        button_label_zh="整理植物多基因构建记录",
        short_description_zh="用于整理多个表达盒、基因列表、模块关系、骨架语境和证据记录。",
        examples_zh=[
            "记录两个或多个植物表达盒的排列、来源和人工复核状态。",
            "整理多基因模块之间的关系、标记/报告基因和骨架语境。",
        ],
        primary_user_goal_zh="把植物多基因构建设想整理成可追踪的构建草稿资料。",
        required_slots=[
            "construct_goal",
            "gene_list",
            "cassette_list",
            "cassette_promoters",
            "cassette_genes",
            "cassette_terminators",
            "cassette_order",
            "module_relationships",
            "vector_or_backbone",
            "marker_or_reporter",
            "evidence_records",
            "manual_review_status",
        ],
        clarification_prompts_zh=[
            "多基因构建的文档目标是什么？",
            "需要记录哪些基因、表达盒和表达盒顺序？",
            "各表达盒的启动子、基因、终止子和模块关系是否有来源记录？",
            "载体骨架、标记/报告基因和证据缺口如何标注？",
        ],
    ),
    _entry_route(
        route_id="plant_regulatory_module_review",
        label_en="Plant Regulatory Module Review",
        label_zh="植物调控模块复核路线",
        button_label_zh="整理植物调控模块记录",
        short_description_zh="用于整理输入信号、传感/启动子、调控因子、顺式元件、输出基因和不确定性。",
        examples_zh=[
            "整理某个植物诱导型启动子或顺式元件的证据记录。",
            "记录转录因子、输出基因、报告读出和宿主语境之间的关系。",
        ],
        primary_user_goal_zh="把植物调控模块想法整理成边界清楚的人工复核资料。",
        required_slots=[
            "regulatory_goal",
            "input_signal",
            "sensor_or_promoter",
            "transcription_factor_or_regulator",
            "cis_element",
            "output_gene",
            "expression_pattern",
            "reporter_or_readout",
            "host_context",
            "regulatory_evidence",
            "uncertainty_or_risk",
            "manual_review_status",
        ],
        clarification_prompts_zh=[
            "调控模块想记录的输入信号或使用语境是什么？",
            "传感元件、启动子、调控因子或顺式元件有哪些来源记录？",
            "输出基因、表达模式、报告读出和宿主语境如何描述？",
            "哪些不确定性、证据缺口或风险需要人工复核？",
        ],
    ),
)

_HANDOFF_STAGE: dict[str, Any] = {
    "route_id": HANDOFF_STAGE_ID,
    "route_kind": "shared_handoff_stage",
    "label_en": "Plant Handoff Package Review",
    "label_zh": "植物交付包复核阶段",
    "short_description_zh": "四条入口路线共用的最终文档包复核阶段，用于汇总目标、证据、缺口、追溯关系和人工复核状态。",
    "applies_to_route_ids": list(ENTRY_ROUTE_IDS),
    "package_outputs": [
        "route_context_summary",
        "required_slot_checklist",
        "evidence_and_source_gap_notes",
        "manual_review_status_readback",
        "traceability_notes",
        "documentation_only_package_draft",
    ],
    "safe_boundary_notes_zh": [
        "交付包阶段只汇总文档草稿、证据缺口和人工复核状态。",
        "该阶段不改变导入/导出包结构，不写入数据库，也不触发构建或实验流程。",
        "交付包内容仍需人工/公司复核，不能替代专家判断。",
    ],
}


def get_simple_plant_wizard_entry_routes() -> list[dict[str, Any]]:
    """Return the four beginner-facing plant entry routes."""
    return deepcopy(list(_ENTRY_ROUTES))


def get_simple_plant_wizard_handoff_stage() -> dict[str, Any]:
    """Return the shared final documentation package review stage."""
    return deepcopy(_HANDOFF_STAGE)


def get_simple_plant_wizard_routes() -> list[dict[str, Any]]:
    """Return entry routes followed by the shared handoff stage."""
    return [*get_simple_plant_wizard_entry_routes(), get_simple_plant_wizard_handoff_stage()]


def get_simple_plant_wizard_route(route_id: str) -> dict[str, Any]:
    """Return a route or shared stage by ID, or an empty dict for unknown IDs."""
    for route in get_simple_plant_wizard_routes():
        if route["route_id"] == route_id:
            return route
    return {}


def build_simple_plant_wizard_route_summary() -> dict[str, Any]:
    """Return deterministic route counts and boundary notes for later presenters."""
    entry_routes = get_simple_plant_wizard_entry_routes()
    handoff_stage = get_simple_plant_wizard_handoff_stage()
    return {
        "schema_id": SCHEMA_ID,
        "schema_version": SCHEMA_VERSION,
        "entry_route_count": len(entry_routes),
        "shared_handoff_stage_count": 1,
        "total_route_count": len(entry_routes) + 1,
        "entry_route_ids": [route["route_id"] for route in entry_routes],
        "shared_handoff_stage_id": handoff_stage["route_id"],
        "documentation_only": True,
        "manual_review_required": True,
        "boundary_notes_zh": [
            "Simple Plant Wizard路线层只提供植物项目文档框架。",
            "摘要只统计入口路线和共享交付包阶段，不执行生物设计决策。",
            "所有路线都保留人工复核和证据追溯语境。",
        ],
    }
