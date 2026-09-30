from __future__ import annotations

from copy import deepcopy
from typing import Any


DEFAULT_BEGINNER_VISIBLE = "default_beginner_visible"
BEGINNER_SIMPLIFY_NOW = "beginner_simplify_now"
ADVANCED_REVIEWER_ONLY = "advanced_reviewer_only"
DEVELOPER_DEBUG_ONLY = "developer_debug_only"
LEGACY_FROZEN = "legacy_frozen"
KEEP_BUT_COLLAPSE = "keep_but_collapse"
UNKNOWN_NEEDS_FOLLOWUP = "unknown_needs_followup"

BEGINNER_NAVIGATION_PAGE_KEYS: tuple[str, ...] = (
    "Simple Plant Wizard",
    "Pathway Projects",
    "Dashboard",
)

BEGINNER_LIBRARY_PAGE_KEYS: tuple[str, ...] = (
    "Data",
)

ADVANCED_NAVIGATION_PAGE_KEYS: tuple[str, ...] = (
    "Pathway Workspace",
    "Plant Expression Workspace",
    "Expression Wizard",
    "Expression Constructs",
    "Plant Design Workspace",
    "Design Library",
    "Application Scenario",
    "Plant Promoter Catalog",
    "Case Library",
    "Sequence Tools",
    "Codon Optimizer",
    "Assembly & Cloning",
    "AI Literature Research",
)

DEVELOPER_NAVIGATION_PAGE_KEYS: tuple[str, ...] = (
    "Structure Analysis",
    "Lab Tools",
    "Module Overview",
)

SIMPLE_PLANT_WIZARD_RUNTIME_MARKER = "Simple Plant Wizard | Beginner Mode Active | R179"


_SURFACES: tuple[dict[str, Any], ...] = (
    {
        "surface_id": "homepage",
        "label_zh": "首页",
        "label_en": "Home",
        "file_hint": "views/Homepage.py",
        "page_key": "Homepage",
        "visibility_status": DEFAULT_BEGINNER_VISIBLE,
        "default_visible": True,
        "advanced_mode_required": False,
        "freeze_reason_zh": "",
        "beginner_replacement_zh": "默认入口继续使用首页，但旧模块地图保持折叠。",
        "safety_notes_zh": "仅提供文档型导航，不代表生物推荐或实验判断。",
    },
    {
        "surface_id": "simple_plant_wizard",
        "label_zh": "植物设计向导 / 开始设计审查",
        "label_en": "Simple Plant Wizard / Start Review",
        "file_hint": "views/pathway_workspace_sections/plant_review_workflow_section.py",
        "page_key": "Simple Plant Wizard",
        "visibility_status": DEFAULT_BEGINNER_VISIBLE,
        "default_visible": True,
        "advanced_mode_required": False,
        "freeze_reason_zh": "",
        "beginner_replacement_zh": "默认显示路线卡、目标输入、确认卡、清单/缺口摘要和包草稿入口。",
        "safety_notes_zh": "文档型人工审查入口，不自动选择元件、不生成实验方案。",
    },
    {
        "surface_id": "my_projects",
        "label_zh": "我的项目",
        "label_en": "My Projects",
        "file_hint": "views/PathwayProjects.py",
        "page_key": "Pathway Projects",
        "visibility_status": DEFAULT_BEGINNER_VISIBLE,
        "default_visible": True,
        "advanced_mode_required": False,
        "freeze_reason_zh": "",
        "beginner_replacement_zh": "保留项目列表作为本地项目工作区入口。",
        "safety_notes_zh": "项目记录仅用于本地文档组织和追踪。",
    },
    {
        "surface_id": "saved_designs",
        "label_zh": "已保存设计",
        "label_en": "Saved Designs",
        "file_hint": "views/Dashboard.py",
        "page_key": "Dashboard",
        "visibility_status": DEFAULT_BEGINNER_VISIBLE,
        "default_visible": True,
        "advanced_mode_required": False,
        "freeze_reason_zh": "",
        "beginner_replacement_zh": "保留快照回看入口，避免新用户寻找历史记录困难。",
        "safety_notes_zh": "保存状态不代表实验可用性或验证结论。",
    },
    {
        "surface_id": "component_library",
        "label_zh": "元件库",
        "label_en": "Component Library",
        "file_hint": "views/Data.py",
        "page_key": "Data",
        "visibility_status": DEFAULT_BEGINNER_VISIBLE,
        "default_visible": True,
        "advanced_mode_required": False,
        "freeze_reason_zh": "",
        "beginner_replacement_zh": "作为来源/出处和元件文档浏览入口。",
        "safety_notes_zh": "元件库是文档记录，不代表最佳元件或实验确认。",
    },
    {
        "surface_id": "expression_wizard",
        "label_zh": "表达向导",
        "label_en": "Expression Wizard",
        "file_hint": "views/ExpressionWizard.py",
        "page_key": "Expression Wizard",
        "visibility_status": LEGACY_FROZEN,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "旧的表达设计入口对初学者过重，R178 后不作为默认入口。",
        "beginner_replacement_zh": "使用 Simple Plant Wizard 的植物目标到审查路线流程。",
        "safety_notes_zh": "保留直接路由和回归测试，不新增生物设计行为。",
    },
    {
        "surface_id": "expression_constructs",
        "label_zh": "表达式构造",
        "label_en": "Expression Constructs",
        "file_hint": "views/ExpressionConstructs.py",
        "page_key": "Expression Constructs",
        "visibility_status": ADVANCED_REVIEWER_ONLY,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "构造记录浏览属于审查员/旧工作流细节。",
        "beginner_replacement_zh": "在 Simple Plant Wizard 中先看路线和缺口摘要。",
        "safety_notes_zh": "只保留文档型记录浏览，不作为默认构造任务入口。",
    },
    {
        "surface_id": "plant_expression_workspace",
        "label_zh": "Plant Expression Workspace Prototype",
        "label_en": "Plant Expression Workspace",
        "file_hint": "views/Plant_Expression_Workspace.py",
        "page_key": "Plant Expression Workspace",
        "visibility_status": ADVANCED_REVIEWER_ONLY,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "Standalone read-only prototype for reviewing a clearer plant expression workspace structure.",
        "beginner_replacement_zh": "Use the default Simple Plant Wizard unless reviewing this focused expression workspace prototype.",
        "safety_notes_zh": "Read-only review of existing records; no component choice, sequence output, or biological conclusion.",
    },
    {
        "surface_id": "plant_design_workspace",
        "label_zh": "植物设计工作区",
        "label_en": "Plant Design Workspace",
        "file_hint": "views/PlantDesignWorkspace.py",
        "page_key": "Plant Design Workspace",
        "visibility_status": ADVANCED_REVIEWER_ONLY,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "长篇 readback、proof path 和追踪表格对默认初学者流程过重。",
        "beginner_replacement_zh": "使用 Simple Plant Wizard 默认流；需要审查细节时再进入高级模式。",
        "safety_notes_zh": "保持只读人工审查边界。",
    },
    {
        "surface_id": "pathway_workspace_advanced_sections",
        "label_zh": "路径工作区高级审查细节",
        "label_en": "Pathway Workspace advanced details",
        "file_hint": "views/pathway_workspace_sections/",
        "page_key": "Pathway Workspace",
        "visibility_status": KEEP_BUT_COLLAPSE,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "proof path、readback、traceability 等细节默认折叠。",
        "beginner_replacement_zh": "默认只显示 Simple Plant Wizard 流。",
        "safety_notes_zh": "高级细节仍然是只读人工审查信息。",
    },
    {
        "surface_id": "design_library",
        "label_zh": "设计库",
        "label_en": "Design Library",
        "file_hint": "views/DesignLibrary.py",
        "page_key": "Design Library",
        "visibility_status": ADVANCED_REVIEWER_ONLY,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "旧设计库会扩大默认导航面。",
        "beginner_replacement_zh": "默认使用已保存设计入口查看历史状态。",
        "safety_notes_zh": "设计快照不代表实验确认。",
    },
    {
        "surface_id": "application_scenario",
        "label_zh": "应用场景",
        "label_en": "Application Scenario",
        "file_hint": "views/ApplicationScenario.py",
        "page_key": "Application Scenario",
        "visibility_status": ADVANCED_REVIEWER_ONLY,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "场景页属于方向说明，默认导航不再展开。",
        "beginner_replacement_zh": "首页和 Simple Plant Wizard 承担初始说明。",
        "safety_notes_zh": "不得表达生产或实验可用性判断。",
    },
    {
        "surface_id": "plant_promoter_catalog",
        "label_zh": "植物启动子资产",
        "label_en": "Plant Promoter Catalog",
        "file_hint": "views/PlantPromoterCatalog.py",
        "page_key": "Plant Promoter Catalog",
        "visibility_status": ADVANCED_REVIEWER_ONLY,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "启动子资料属于审查资料细节，不作为初学者第一屏入口。",
        "beginner_replacement_zh": "从元件库进入来源/出处记录。",
        "safety_notes_zh": "资料浏览不代表推荐或表现预测。",
    },
    {
        "surface_id": "case_library",
        "label_zh": "案例库",
        "label_en": "Case Library",
        "file_hint": "views/CaseLibrary.py",
        "page_key": "Case Library",
        "visibility_status": KEEP_BUT_COLLAPSE,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "案例细节默认折叠，避免压过向导流程。",
        "beginner_replacement_zh": "默认从 Simple Plant Wizard 开始。",
        "safety_notes_zh": "案例仅作本地文档参考。",
    },
    {
        "surface_id": "sequence_tools",
        "label_zh": "序列工具",
        "label_en": "Sequence Tools",
        "file_hint": "views/SequenceTools.py",
        "page_key": "Sequence Tools",
        "visibility_status": LEGACY_FROZEN,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "独立序列工具属于旧专家入口。",
        "beginner_replacement_zh": "在向导流程中查看需要的文档型检查摘要。",
        "safety_notes_zh": "不得新增序列改写或实验操作行为。",
    },
    {
        "surface_id": "codon_usage_preview",
        "label_zh": "密码子使用预览",
        "label_en": "Codon Usage Preview",
        "file_hint": "views/CodonOptimizer.py",
        "page_key": "Codon Optimizer",
        "visibility_status": LEGACY_FROZEN,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "密码子页面属于旧专家入口，避免被误解为优化输出。",
        "beginner_replacement_zh": "默认向导仅保留文档型上下文。",
        "safety_notes_zh": "只允许使用预览/记录措辞，不表示优化。",
    },
    {
        "surface_id": "assembly_cloning",
        "label_zh": "组装与克隆",
        "label_en": "Assembly and Cloning",
        "file_hint": "views/AssemblyCloning.py",
        "page_key": "Assembly & Cloning",
        "visibility_status": LEGACY_FROZEN,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "克隆相关入口容易被理解为实验执行路径。",
        "beginner_replacement_zh": "默认仅显示文档型审查向导。",
        "safety_notes_zh": "不提供实验执行、协议或就绪判断。",
    },
    {
        "surface_id": "ai_literature_research",
        "label_zh": "AI 文献研究",
        "label_en": "AI Literature Research",
        "file_hint": "views/AILiteratureResearch.py",
        "page_key": "AI Literature Research",
        "visibility_status": LEGACY_FROZEN,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "旧研究入口不属于当前初学者 MVP 主路径。",
        "beginner_replacement_zh": "使用向导中的文献/证据审查占位和人工审查提示。",
        "safety_notes_zh": "不新增知识库导入或自动结论。",
    },
    {
        "surface_id": "structure_analysis",
        "label_zh": "结构分析",
        "label_en": "Structure Analysis",
        "file_hint": "views/StructureAnalysis.py",
        "page_key": "Structure Analysis",
        "visibility_status": DEVELOPER_DEBUG_ONLY,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "结构分析不属于植物初学者文档主流程。",
        "beginner_replacement_zh": "不在默认 UI 显示。",
        "safety_notes_zh": "保持内部/回归入口，不扩展功能。",
    },
    {
        "surface_id": "lab_tools",
        "label_zh": "实验工具",
        "label_en": "Lab Tools",
        "file_hint": "views/LabTools.py",
        "page_key": "Lab Tools",
        "visibility_status": DEVELOPER_DEBUG_ONLY,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "实验工具不属于文档型初学者默认入口。",
        "beginner_replacement_zh": "不在默认 UI 显示。",
        "safety_notes_zh": "不得暗示实验执行或湿实验就绪。",
    },
    {
        "surface_id": "module_overview",
        "label_zh": "模块总览",
        "label_en": "Module Overview",
        "file_hint": "views/ModuleOverview.py",
        "page_key": "Module Overview",
        "visibility_status": DEVELOPER_DEBUG_ONLY,
        "default_visible": False,
        "advanced_mode_required": True,
        "freeze_reason_zh": "模块管理视图属于开发/维护入口。",
        "beginner_replacement_zh": "使用首页和默认导航。",
        "safety_notes_zh": "仅作内部结构查看。",
    },
)


def list_ui_surfaces() -> list[dict[str, Any]]:
    return deepcopy(list(_SURFACES))


def get_ui_surface(surface_id: str) -> dict[str, Any] | None:
    for surface in _SURFACES:
        if surface["surface_id"] == surface_id:
            return deepcopy(surface)
    return None


def list_surfaces_by_visibility(visibility_status: str) -> list[dict[str, Any]]:
    return [
        deepcopy(surface)
        for surface in _SURFACES
        if surface["visibility_status"] == visibility_status
    ]


def build_ui_surface_inventory_summary() -> dict[str, Any]:
    surfaces = list_ui_surfaces()
    status_counts: dict[str, int] = {}
    for surface in surfaces:
        status = str(surface["visibility_status"])
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "surface_count": len(surfaces),
        "status_counts": status_counts,
        "default_beginner_visible_page_keys": list(BEGINNER_NAVIGATION_PAGE_KEYS + BEGINNER_LIBRARY_PAGE_KEYS),
        "advanced_page_keys": list(ADVANCED_NAVIGATION_PAGE_KEYS),
        "developer_page_keys": list(DEVELOPER_NAVIGATION_PAGE_KEYS),
        "runtime_marker": SIMPLE_PLANT_WIZARD_RUNTIME_MARKER,
        "documentation_only": True,
    }
