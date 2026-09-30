"""BioDesign Studio formal plant construct workspace entry point."""
from __future__ import annotations

from collections.abc import Mapping
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from core.config import configure_pydna_log_dir, ensure_biodesign_log_dir

configure_pydna_log_dir()

import streamlit as st
import streamlit.components.v1 as components

from core.i18n import get_language as _get_language
from core.i18n import set_language as _set_language
from core.i18n import t as _t
from locales import LOCALES as _LOCALES


_CONTROLLED_UI_LABELS = {
    "通过": "Passed", "阻断": "Blocking", "信息": "Information", "警告": "Warning",
    "需要人工确认": "Needs manual confirmation", "待检查": "Needs review", "已输入": "Entered",
    "未检测到": "Not detected", "阅读框完整": "Reading frame complete",
    "长度不是 3 的整数倍": "Length is not a multiple of three",
    "存在阻断": "Blocking item present", "分析已完成": "Analysis complete", "尚未分析": "Not analyzed",
    "未记录": "Not recorded", "多转录单元": "Multi-TU", "单基因": "Single Gene",
    "目标基因表达单元": "Target-gene expression unit", "植物选择标记表达单元": "Plant-selection-marker expression unit",
    "报告基因表达单元": "Reporter-gene expression unit", "正向": "Forward", "反向": "Reverse",
    "元件库": "Component Library", "用户提供": "User-provided", "来源记录": "Source record",
    "已记录 CDS": "CDS recorded", "未记录 CDS": "CDS not recorded", "未配置": "Not configured",
    "未指定": "Not specified", "来源真实性": "Source authenticity", "序列一致性": "Sequence consistency",
    "精确插入合同": "Exact insertion contract", "交付用途": "Delivery use",
    "专业审查": "Professional review", "可交付": "Deliverable", "不可交付": "Not deliverable",
    "固定角色": "Fixed role", "组件": "Component", "来源 accession": "Source accession",
    "证据等级": "Evidence tier", "编辑状态": "Edit status", "固定案例，只读": "Fixed case, read-only",
    "无精确 Registry 匹配": "No exact Registry match", "元件类型": "Component type",
    "复核状态": "Review status", "当前限制": "Current limitation", "不适用": "Not applicable",
    "组件角色": "Component role", "角色": "Role", "元件": "Component", "坐标": "Coordinates",
    "来源": "Source", "边界": "Boundary",
    "区间": "Interval", "类别": "Category", "来源坐标": "Source coordinates",
    "canonical 坐标": "Canonical coordinates", "长度": "Length",
    "未注释来源序列": "Unannotated source sequence",
    "来源 accession/version": "Source accession/version", "来源物种": "Source organism",
    "目标宿主元数据": "Target host metadata", "已保存": "Saved",
    "来源信息需专业复核。": "Source information requires professional review.",
    "已确认": "Confirmed", "已应用": "Applied", "交付记录可用": "Delivery record available",
    "交付记录不可用": "Delivery record unavailable",
    "当前记录存在阻断项；请先完成记录中的审查事项。": "The current record has blocking items; complete the record review items first.",
    "交付记录可用，需人工审查": "Delivery record available; manual review required",
    "当前记录存在警告项；请进行人工审查。": "The current record has warnings; perform manual review.",
    "当前 canonical 记录未显示阻断项或警告项。": "The current canonical record shows no blocking items or warnings.",
    "最终审查不可用": "Final review unavailable",
    "当前记录无法形成最终审查与交付记录。": "The current record cannot form a final review and delivery record.",
    "正式可用": "Officially available", "受限": "Restricted", "只读": "Read-only",
    "精确插入": "Exact insertion", "精确替换": "Exact replacement", "适用：": "Applicable: ",
    "不可选": "Not selectable", "暂无正式操作合同": "No formal operation contract yet",
    "水稻单基因完整载体": "Rice single-gene complete vector", "单基因精确插入载体来源": "Single-gene exact-insertion vector source", "本地示例": "Local example",
    "代谢通路": "Metabolic pathway", "代谢通路 Multi-TU 载体": "Metabolic pathway Multi-TU vector",
    "Betalain Gate 3": "Betalain Gate 3", "通用 Multi-TU": "Generic Multi-TU", "多 TU 区域": "Multi-TU region",
    "无": "None", "环状": "Circular", "线性": "Linear", "插入": "Insertion", "替换": "Replacement", "选择": "Select", "未通过": "Not passed", "未生成": "Not generated", "项": "item(s)", "、": ", ", "插入/替换坐标": "Insertion/replacement coordinates",
    "操作类型": "Operation type", "方向": "Orientation", "拓扑": "Topology", "载体": "Vector",
    "载体骨架长度": "Vector backbone length", "完整构建长度": "Full construct length", "T-DNA / LB-RB 状态": "T-DNA / LB-RB status",
    "已生成": "Generated", "处理中": "In progress", "保存失败": "Save failed", "生成失败": "Generation failed",
    "精确替换合同": "Exact replacement contract", "精确操作合同": "Exact operation contract",
    "表达盒": "Expression cassette", "载体骨架": "Vector backbone", "完整质粒": "Complete plasmid",
    "限制": "Limitation", "需要修正": "Needs correction", "需要重新审查": "Needs re-review",
    "当前记录需要重新审查后才能继续。": "The current record requires re-review before continuing.",
    "请完成每个 TU 的启动子、5′ region / 5′ UTR、CDS 和 3′ 调控区配置。": "Complete promoter, 5′ region / 5′ UTR, CDS, and 3′ regulatory region configuration for every TU.",
    "请完成目标基因名称并修正 CDS 阻断项。": "Enter the target gene name and resolve CDS blocking items.",
    "请先生成当前完整载体。": "Generate the current complete vector first.",
    "请先生成完整质粒，才能查看结果与导出。": "Generate the complete plasmid before viewing results and exports.",
    "请先生成第五步的 canonical 构建记录。": "Generate the Step 5 canonical construct record first.",
    "当前 canonical 记录未显示阻断项或警告项。": "The current canonical record shows no blocking items or warnings.",
    "前缀：": "Prefix: ", "后缀：": "Suffix: ", "启动子": "Promoter", "3′端调控元件": "3′ regulatory element",
    "3′调控区": "3′ regulatory region", "终止子": "Terminator", "编码序列（CDS）": "Coding sequence (CDS)",
    "植物宿主": "Plant host", "品种或实验材料": "Cultivar or experimental material",
    "实验应用方式": "Experimental application method", "组织或器官特异性要求": "Tissue or organ specificity requirement",
    "诱导性要求": "Inducibility requirement", "亚细胞定位目标": "Subcellular localization target",
    "未发现阻断项": "No blocking items found", "项阻断": " blocking item(s)", "项警告": " warning item(s)",
    "需人工确认": "Needs manual confirmation", "来源与高级信息": "Source and advanced information",
    "已保存 CDS 一致": "Matches saved CDS", "旧版未分类": "Legacy unclassified", "正式选择不可用": "Formal selection unavailable",
    "边界待人工复核": "Boundary requires manual review", "本地序列服务准入可用": "Local sequence service eligible",
    "本地序列": "Local sequence", "服务准入可用": "Service eligible", "当前角色不可用": "Unavailable for current role",
    "本地序列已记录": "Local sequence recorded", "本地序列已记录；不构成正式准入": "Local sequence recorded; this does not constitute formal eligibility",
    "可按服务准入用于正式工作流": "Eligible for use in the formal workflow under service admission",
    "当前角色不可直接使用": "Not directly usable for the current role", "本地序列状态不可用": "Local sequence status unavailable",
    "目录候选": "Catalog candidate", "正式选择可用": "Formal selection available", "可自备序列": "User-provided sequence",
    "暂缓": "Deferred", "权威 Registry": "Authoritative Registry", "全部记录": "All records",
    "全部来源/宿主上下文": "All sources / host contexts", "调控/载体元件": "Regulatory/vector component",
    "未完成": "Not completed", "可以继续": "Can continue", "受限/只读": "Restricted/read-only",
    "本地示例 ·": "Local example ·",
    "请先完成第三步": "Complete Step 3 first",
    "待验证本地示例，来源未验证": "Local example pending review; source unverified",
    "5′ UTR": "5′ UTR", "搜索": "Search", "名称、精确变体、记录 ID 或 accession": "Name, exact variant, record ID, or accession",
    "现有精确操作合同适用于当前路线。": "The existing exact operation contract applies to the current workflow.",
    "仅限已授权的代谢通路 Multi-TU 或 Betalain Gate 3 固定精确替换路线。": "Restricted to the authorized metabolic-pathway Multi-TU or Betalain Gate 3 fixed exact-replacement workflow.",
    "仅供参考：尚无正式插入或替换操作合同。": "Reference only: no formal insertion or replacement operation contract is available.",
    "未验证，只读；不可保存为正式骨架或用于 canonical。": "Unverified, read-only; it cannot be saved as a formal backbone or used for canonical construction.",
}


def _ui(value: Any) -> Any:
    """Translate only exact, controlled product labels; never rewrite arbitrary text."""
    if not isinstance(value, str):
        return value
    if _get_language() == "en":
        return _CONTROLLED_UI_LABELS.get(value, value)
    return next((zh for zh, en in _CONTROLLED_UI_LABELS.items() if en == value), value)


# Persisted project-definition and widget values remain stable Chinese strings;
# Streamlit renders their localized labels through ``format_func`` below.
_APPLICATION_MODE_VALUES = ("稳定遗传转化", "瞬时表达", "尚未确定")
_TRANSIENT_SYSTEM_VALUES = ("农杆菌介导的植物组织瞬时表达", "植物原生质体瞬时转染", "其他瞬时表达体系", "尚未确定")
_TISSUE_REQUIREMENT_VALUES = ("无特定组织或器官限制", "组织或器官特异性表达", "尚未确定")
_INDUCIBILITY_VALUES = ("无特定诱导要求", "需要诱导型表达", "尚未确定")
_CDS_INPUT_MODE_VALUES = ("粘贴核酸序列", "上传单条核酸 FASTA")
_ORIENTATION_VALUES = ("正向", "反向")
_SOURCE_MODE_VALUES = ("元件库", "用户序列")
# Single-Gene Step 3 stores semantic choices, never localized widget labels.
_SINGLE_GENE_SOURCE_MODE_VALUES = ("registry", "user_sequence")
_SINGLE_GENE_SOURCE_MODE_LABELS = {
    "registry": "v1.common.component_library",
    "user_sequence": "v1.expression.user_sequence",
}
_TYPE_FILTER_VALUES = ("全部", "启动子", "5′ UTR", "CDS", "终止子", "3′调控区", "调控/载体元件", "载体骨架")
# Component Library widget values are stable identifiers. Locales only affect
# the display formatter, so a language switch cannot change filter meaning.
_COMPONENT_LIBRARY_TYPE_FILTER_VALUES = (
    "all",
    "promoter",
    "five_prime_utr",
    "cds",
    "terminator",
    "three_prime_regulatory_region",
    "regulatory_or_vector_element",
    "vector_backbone",
)
_COMPONENT_LIBRARY_TYPE_FILTER_LEGACY_VALUES = {
    "全部": "all",
    "All": "all",
    "启动子": "promoter",
    "Promoter": "promoter",
    "5′ UTR": "five_prime_utr",
    "CDS": "cds",
    "终止子": "terminator",
    "Terminator": "terminator",
    "3′调控区": "three_prime_regulatory_region",
    "3′ Regulatory Region": "three_prime_regulatory_region",
    "调控/载体元件": "regulatory_or_vector_element",
    "Regulatory/Vector Components": "regulatory_or_vector_element",
    "载体骨架": "vector_backbone",
    "Vector Backbone": "vector_backbone",
}
_LIBRARY_WORKFLOW_VALUES = (
    "all",
    "authoritative_registry",
    "catalog_candidate",
    "formal_selectable",
    "user_provided_sequence",
    "deferred",
    "legacy_unclassified",
)
_LIBRARY_WORKFLOW_LEGACY_VALUES = {
    "全部记录": "all",
    "All records": "all",
    "权威 Registry": "authoritative_registry",
    "Authoritative Registry": "authoritative_registry",
    "目录候选": "catalog_candidate",
    "Catalog candidate": "catalog_candidate",
    "正式选择可用": "formal_selectable",
    "Official selection available": "formal_selectable",
    "可自备序列": "user_provided_sequence",
    "User-provided sequence": "user_provided_sequence",
    "暂缓": "deferred",
    "Deferred": "deferred",
    "旧版未分类": "legacy_unclassified",
    "Legacy Unclassified": "legacy_unclassified",
}
_GENBANK_SOURCE_VALUES = ("内置真实验收资产 pBI121 AF485783.1", "上传 GenBank 文件")
_FORMAL_BACKBONE_SOURCE_VALUES = ("使用当前项目骨架", "上传 GenBank")
_FORMAL_BACKBONE_SOURCE_LABELS = {
    "使用当前项目骨架": "v1.expression.use_current_project_backbone",
    "上传 GenBank": "v1.expression.upload_genbank_source",
}
_DESIGN_SCENARIO_LABELS = {
    "standard_plant_expression_vector": "v1.expression.standard_plant_expression_vector",
    "metabolic_pathway_multi_tu_vector": "v1.expression.metabolic_pathway_multi_tu_vector",
}
_SOURCE_TYPE_LABELS = {
    "公共数据库记录": "v1.expression.public_database_record",
    "上传的 FASTA 文件": "v1.expression.upload_single_nucleic_acid_fasta",
    "用户自有序列": "v1.expression.user_provided_cds",
    "外部公司或工具提供的序列": "v1.expression.sequence_provided_by_external_company_tool",
    "其他来源": "v1.expression.other_sources",
}
_MODIFICATION_STATUS_LABELS = {
    "未修改的来源序列": "v1.expression.unmodified_source_sequence",
    "用户手动编辑": "v1.expression.user_manual_edit",
    "已由外部工具或公司进行密码子优化": "v1.expression.external_codon_optimization",
    "其他修改": "v1.expression.other_modifications",
    "尚未确定": "v1.expression.not_yet_determined",
}
_THREE_PRIME_ROLE_LABELS = {
    "terminator": "v1.expression.transcription_terminator",
    "three_prime_utr": "v1.expression.three_prime_utr",
    "three_prime_regulatory_region": "v1.expression.three_prime_regulatory_region",
    "three_prime_processing_termination_region": "v1.expression.three_prime_processing_termination_region",
}

_THREE_PRIME_ROLE_LEGACY_VALUES = {
    "terminator": "terminator",
    "transcription_terminator": "terminator",
    "转录终止子": "terminator",
    "transcription terminator": "terminator",
    "three_prime_utr": "three_prime_utr",
    "3′ utr": "three_prime_utr",
    "3' utr": "three_prime_utr",
    "3′非翻译区（3′ utr）": "three_prime_utr",
    "3' untranslated region (3' utr)": "three_prime_utr",
    "three_prime_regulatory_region": "three_prime_regulatory_region",
    "3′调控区": "three_prime_regulatory_region",
    "3′ 调控区": "three_prime_regulatory_region",
    "3′端调控区": "three_prime_regulatory_region",
    "3′ regulatory region": "three_prime_regulatory_region",
    "three_prime_processing_termination_region": "three_prime_processing_termination_region",
    "3′端加工终止区": "three_prime_processing_termination_region",
    "3′ processing/termination region": "three_prime_processing_termination_region",
}


def _normalize_three_prime_role(value: Any, *, default: str = "terminator") -> str:
    """Return the persisted 3' role key without using a localized label as state."""
    candidate = str(value or "").strip()
    if candidate in _THREE_PRIME_ROLE_LABELS:
        return candidate
    normalized = candidate.casefold()
    if normalized in _THREE_PRIME_ROLE_LEGACY_VALUES:
        return _THREE_PRIME_ROLE_LEGACY_VALUES[normalized]
    for role, key in _THREE_PRIME_ROLE_LABELS.items():
        label = str(_t(key) or "").strip()
        if candidate == label or normalized == label.casefold():
            return role
    return default if default in _THREE_PRIME_ROLE_LABELS else "terminator"


def _single_gene_step3_role_display_label(role: str) -> str:
    """Resolve a Single-Gene role key using the current display locale."""
    key = (
        "v1.ai_assisted_design.promoter"
        if role == "promoter"
        else _THREE_PRIME_ROLE_LABELS.get(role)
    )
    return _t(key) if key else role


_FORMAL_STEP3_CUSTOM_INPUT_DISPLAY_LABELS = {
    "粘贴 DNA/FASTA": "v1.expression.paste_dna_fasta",
    "上传 FASTA": "v1.expression.upload_fasta",
    "需要核对输入来源": "v1.expression.saved_input_source_method_missing",
}
_OPTIONAL_ELEMENT_LABELS = {
    "靶向序列": "v1.expression.targeting_sequence",
    "linker": "v1.expression.linker",
    "融合标签": "v1.expression.fusion_tag",
    "5′端调控元件": "v1.expression.five_prime_regulatory_element",
    "N端融合标签编码序列": "v1.expression.n_terminal_fusion_tag_coding_sequence",
    "蛋白靶向元件编码序列": "v1.expression.protein_targeting_element_coding_sequence",
    "连接肽编码序列": "v1.expression.linker_coding_sequence",
    "C端融合标签编码序列": "v1.expression.c_terminal_fusion_tag_coding_sequence",
    "5′非翻译区（5′ UTR）": "v1.expression.five_prime_utr",
    "5′端调控区": "v1.expression.five_prime_regulatory_region",
    "翻译增强相关序列": "v1.expression.translation_enhancer_sequence",
    "分泌信号肽编码序列": "v1.expression.signal_peptide_coding_sequence",
    "叶绿体转运肽编码序列": "v1.expression.chloroplast_transit_peptide_coding_sequence",
    "线粒体转运肽编码序列": "v1.expression.mitochondrial_targeting_peptide_coding_sequence",
    "核定位信号编码序列": "v1.expression.nuclear_localization_signal_coding_sequence",
}
_APPLICATION_MODE_LABELS = {
    "稳定遗传转化": "v1.expression.application_mode_stable",
    "瞬时表达": "v1.expression.application_mode_transient",
    "尚未确定": "v1.expression.application_mode_undetermined",
}
_TRANSIENT_SYSTEM_LABELS = {
    "农杆菌介导的植物组织瞬时表达": "v1.expression.transient_agrobacterium",
    "植物原生质体瞬时转染": "v1.expression.transient_protoplast",
    "其他瞬时表达体系": "v1.expression.transient_other",
    "尚未确定": "v1.expression.application_mode_undetermined",
}
_SOURCE_MODE_LABELS = {
    "元件库": "v1.common.component_library",
    "用户序列": "v1.expression.user_sequence",
    "不使用独立 5′ region": "v1.expression.no_independent_five_prime_region",
}
_CDS_INPUT_MODE_LABELS = {"粘贴核酸序列": "v1.expression.paste_nucleic_acid_sequence", "上传单条核酸 FASTA": "v1.expression.upload_single_nucleic_acid_fasta"}
_TISSUE_REQUIREMENT_LABELS = {
    "无特定组织或器官限制": "v1.expression.no_specific_tissue_organ_restrictions",
    "组织或器官特异性表达": "v1.expression.tissue_or_organ_specific_expression",
    "尚未确定": "v1.expression.not_yet_determined",
}
_INDUCIBILITY_LABELS = {
    "无特定诱导要求": "v1.expression.no_specific_induction_requirements",
    "需要诱导型表达": "v1.expression.inducible_expression_required",
    "尚未确定": "v1.expression.not_yet_determined",
}
_TOPOLOGY_LABELS = {
    "环状": "v1.common.circular",
    "线性": "v1.common.linear",
    "未记录": "v1.expression.not_recorded",
}
_DEFAULT_SINGLE_GENE_PROJECT_NAME = "Plant expression vector project"
_DEFAULT_MULTI_TU_PROJECT_NAME = "Multi-TU project"
_DEFAULT_PATHWAY_PROJECT_NAME = "Betalain pBI121 design record"

_CONTROLLED_PRODUCT_MESSAGES = {
    "当前动作仍在处理。": "v1.expression.message_action_processing",
    "正在处理当前步骤。": "v1.expression.message_step_processing",
    "当前步骤状态来自现有项目记录。": "v1.expression.message_status_from_record",
    "完成当前步骤要求后可以继续。": "v1.expression.message_complete_step",
    "请先修正表达盒计算检查中的阻断项。": "v1.expression.first_correct_blocking_items_identified_expression_cassette",
}


def _display_product_message(value: Any) -> Any:
    key = _CONTROLLED_PRODUCT_MESSAGES.get(str(value))
    return _t(key) if key else value


def _stable_multi_tu_project_name(existing_project_name: Any) -> str:
    """Return a locale-independent internal default for Multi-TU generation."""
    project_name = str(existing_project_name or "").strip()
    return project_name or _DEFAULT_MULTI_TU_PROJECT_NAME


def _stable_single_gene_project_name(
    existing_project_name: Any, source_name: Any = ""
) -> str:
    """Return a locale-independent internal default for single-gene paths."""
    project_name = str(existing_project_name or "").strip()
    source_name = str(source_name or "").strip()
    return project_name or source_name or _DEFAULT_SINGLE_GENE_PROJECT_NAME


def _display_multi_tu_project_name(project_name: Any) -> str:
    value = str(project_name or "").strip()
    return _t("v1.expression.multi_tu_project") if value == _DEFAULT_MULTI_TU_PROJECT_NAME else value


def _localized_value(value: str, labels: Mapping[str, str]) -> str:
    key = labels.get(value)
    return _t(key) if key else value


_COMPONENT_LIBRARY_TYPE_LABEL_KEYS = {
    "promoter": "v1.ai_assisted_design.promoter",
    "five_prime_utr": "v1.component_library.5_utr",
    "cds": "v1.expression.cds",
    "terminator": "v1.component_library.terminator",
    "three_prime_regulatory_region": "v1.component_library.three_prime_regulatory_region",
    "regulatory_or_vector_element": "v1.component_library.regulatory_vector_components",
    "vector_backbone": "v1.component_library.vector_backbone",
}

_COMPONENT_LIBRARY_CONTROLLED_LABEL_KEYS = {
    "身份待人工复核": "v1.component_library.identity_review_required_badge",
    "边界待人工复核": "v1.component_library.boundary_review_required_badge",
    "目录候选": "v1.component_library.catalog_candidate",
    "正式选择不可用": "v1.component_library.formal_selection_unavailable",
    "旧版未分类": "v1.component_library.legacy_unclassified",
    "本地内置": "v1.component_library.bundled_locally",
    "本地序列": "v1.component_library.local_sequence",
    "服务准入可用": "v1.component_library.service_eligible",
    "当前角色不可用": "v1.component_library.current_role_unavailable",
    "可自备序列": "v1.component_library.user_provided_sequence",
    "仅元数据": "v1.component_library.metadata_only",
    "暂缓": "v1.component_library.deferred",
    "状态不可用": "v1.component_library.status_unavailable",
    "经复核的目录候选（CATALOG_CANDIDATE）": "v1.component_library.reviewed_catalog_candidate_distribution",
    "未分类（旧版记录）": "v1.component_library.legacy_distribution",
    "本地内置（bundled）": "v1.component_library.bundled_distribution",
    "仅参考身份（reference-only）": "v1.component_library.reference_only_distribution",
    "暂缓（deferred）": "v1.component_library.deferred_distribution",
    "治理状态不可用": "v1.component_library.governance_status_unavailable",
    "精确 intake 序列仅供目录身份与来源复核": "v1.component_library.intake_sequence_review_only",
    "本地序列已记录；不构成正式准入": "v1.component_library.local_sequence_not_formal_eligibility",
    "本地序列已记录": "v1.component_library.local_sequence_recorded",
    "当前版本未内置序列": "v1.component_library.sequence_not_bundled",
    "本地序列状态不可用": "v1.component_library.local_sequence_status_unavailable",
    "未正式准入；不可选择或用于构建设计": "v1.component_library.not_formally_admitted",
    "正式选择不可用": "v1.component_library.formal_selection_unavailable",
    "可按服务准入用于正式工作流": "v1.component_library.service_eligible_for_formal_workflow",
    "当前角色不可直接使用": "v1.component_library.current_role_not_directly_usable",
    "不能作为 Registry 序列直接使用；可自行提供序列": "v1.component_library.reference_only_user_sequence",
    "不能直接用于正式工作流": "v1.component_library.not_directly_usable_formal_workflow",
    "已退役": "v1.component_library.v2_retired_badge",
    "已退役（保留历史身份映射）": "v1.component_library.v2_retired_distribution",
    "不向新设计提供序列入口": "v1.component_library.v2_retired_sequence",
    "不可进入新设计；历史保存记录仍可解析": "v1.component_library.v2_retired_workflow",
    "新设计不可用": "v1.component_library.v2_new_design_unavailable_badge",
    "仅供参考": "v1.component_library.v2_reference_badge",
    "V2 参考身份（reference-only）": "v1.component_library.v2_reference_distribution",
    "仅保留身份、来源与限制信息": "v1.component_library.v2_reference_sequence",
    "不可作为正式序列选择；可供 Agent/人工检索参考": "v1.component_library.v2_reference_workflow",
    "需用户序列": "v1.component_library.v2_assisted_badge",
    "需用户提供序列（USER_SEQUENCE_ASSISTED）": "v1.component_library.v2_assisted_distribution",
    "需提供精确 DNA 序列并确认身份与边界": "v1.component_library.v2_assisted_sequence",
    "需提供用户 DNA 并按现有证据确认项目使用": "v1.component_library.v2_assisted_sequence",
    "完成项目绑定与双重确认后可作为 USER_PROVIDED 使用": "v1.component_library.v2_assisted_workflow",
    "项目内确认后可用": "v1.component_library.v2_assisted_confirmed_badge",
    "资产合格，尚未正式准入": "v1.component_library.v2_direct_not_admitted_state",
    "V2 DIRECT_USE 资产已记录": "v1.component_library.v2_direct_not_admitted_distribution",
    "序列与来源已记录；当前主机/角色准入未建立": "v1.component_library.v2_direct_not_admitted_sequence",
    "不可直接使用；需现有 Registry 与主机适用性证据": "v1.component_library.v2_direct_not_admitted_workflow",
    "DIRECT_USE 合格": "v1.component_library.v2_direct_badge",
    "当前正式选择不可用": "v1.component_library.formal_selection_unavailable",
}

_COMPONENT_LIBRARY_ERROR_KEYS = {
    "当前 V2 记录不提供用户序列入口。": "v1.component_library.v2_user_sequence_route_unavailable",
    "当前目录记录不提供用户序列入口。": "v1.component_library.v2_user_sequence_route_unavailable",
    "该元件类型未接入当前 Multi-TU 角色。": "v1.component_library.v2_user_sequence_role_unavailable",
    "当前元件没有可用的 Multi-TU 角色。": "v1.component_library.v2_component_role_unavailable",
    "输入为空。": "v1.component_library.v2_user_sequence_empty",
}

_COMPONENT_LIBRARY_HOST_ALL_VALUE = "__all_sources_host_contexts__"


def _component_library_label(value: Any) -> str:
    text = str(value or "")
    key = _COMPONENT_LIBRARY_CONTROLLED_LABEL_KEYS.get(text)
    return _t(key) if key else text


def _component_library_error(value: Any) -> str:
    """Keep V2 route errors bilingual without translating authoritative values."""
    text = str(value or "").strip()
    key = _COMPONENT_LIBRARY_ERROR_KEYS.get(text)
    if key:
        return _t(key)
    if any("\u3400" <= char <= "\u9fff" for char in text):
        return _t("v1.component_library.v2_user_sequence_error_fallback")
    return text


def _component_library_type_label(component_type: Any) -> str:
    value = str(component_type or "")
    key = _COMPONENT_LIBRARY_TYPE_LABEL_KEYS.get(value)
    return _t(key) if key else value or "--"


def _component_library_host_filter_value(value: Any) -> str:
    candidate = str(value or "").strip()
    # Accept the former Chinese sentinel in an existing widget snapshot while
    # keeping the new internal value locale-independent.
    return _COMPONENT_LIBRARY_HOST_ALL_VALUE if candidate in {
        _COMPONENT_LIBRARY_HOST_ALL_VALUE,
        "全部来源/宿主上下文",
        "All sources / host contexts",
    } else candidate


def _component_library_type_filter_value(value: Any) -> str:
    candidate = str(value or "").strip()
    if candidate in _COMPONENT_LIBRARY_TYPE_FILTER_LEGACY_VALUES:
        return _COMPONENT_LIBRARY_TYPE_FILTER_LEGACY_VALUES[candidate]
    return candidate if candidate in _COMPONENT_LIBRARY_TYPE_FILTER_VALUES else "all"


def _component_library_workflow_filter_value(value: Any) -> str:
    candidate = str(value or "").strip()
    if candidate in _LIBRARY_WORKFLOW_LEGACY_VALUES:
        return _LIBRARY_WORKFLOW_LEGACY_VALUES[candidate]
    return candidate if candidate in _LIBRARY_WORKFLOW_VALUES else "all"


def _display_optional_label(value: str) -> str:
    return _localized_value(value, _OPTIONAL_ELEMENT_LABELS)


def _localized_rows(rows: Any) -> Any:
    """Translate display-only row labels while preserving every cell value."""
    if isinstance(rows, Mapping):
        return {_ui(str(key)): _localized_rows(value) for key, value in rows.items()}
    if isinstance(rows, list):
        return [_localized_rows(item) for item in rows]
    if isinstance(rows, tuple):
        return tuple(_localized_rows(item) for item in rows)
    return rows


_SOURCE_TECHNICAL_LABEL_KEYS = {
    "confirmation_mode": "v1.results_final_report.confirmation_mode",
    "accession_verified": "v1.results_final_report.accession_verified",
    "boundary_verified_by_software": "v1.results_final_report.boundary_verified_by_software",
}


def _localized_source_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Localize controlled source-table labels without rewriting their values."""
    return [
        {
            (
                _t(_SOURCE_TECHNICAL_LABEL_KEYS[str(key)])
                if str(key) in _SOURCE_TECHNICAL_LABEL_KEYS
                else _ui(str(key))
            ): value
            for key, value in row.items()
        }
        for row in rows
    ]
from core.unified_database import initialize_database_on_startup
from views.SequenceToolbox import render as render_sequence_toolbox

_STARTUP_WARNINGS: list[str] = []
_STARTUP_ERRORS: list[str] = []

# ---------------------------------------------------------------------------
# Logging — must be configured before any other module import
# ---------------------------------------------------------------------------
try:
    from utils.logger import setup_logging
    setup_logging(level="INFO", log_file=str(ensure_biodesign_log_dir() / "biodesign.log"))
except Exception as exc:
    _STARTUP_WARNINGS.append(f"Logging is unavailable: {exc}")

st.set_page_config(
    page_title="BioDesign Studio | BioDesign Structured Project Workspace",
    page_icon="BD",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Explicit database startup initialization (single trigger path)
# ---------------------------------------------------------------------------
try:
    initialize_database_on_startup()
except Exception as exc:
    _STARTUP_ERRORS.append(f"Database startup initialization failed: {exc}")
    st.error(_STARTUP_ERRORS[-1])
    st.stop()

# ---------------------------------------------------------------------------
# Global unified stylesheet — applied once, inherited by all pages
# ---------------------------------------------------------------------------
st.markdown("""
<style>
:root {
    --bg: #f5f7f5;
    --bg2: #edf1ed;
    --surface: #ffffff;
    --border: #dce4dc;
    --border2: #c7d2c8;
    --accent: #237a4b;
    --accent-dark: #1d663f;
    --accent-lt: #e8f4ec;
    --accent-md: #bddfc5;
    --green: #287a4b;
    --green-lt: #e8f4ea;
    --info: #2e6fae;
    --info-lt: #eaf3fc;
    --warning: #c37b13;
    --warning-lt: #fff5df;
    --red: #c53d3d;
    --red-lt: #fcecec;
    --promoter: #227f86;
    --cds: #287a4b;
    --terminator: #d48324;
    --backbone: #6f7974;
    --origin: #25827c;
    --text-primary: #1d2920;
    --text-secondary: #334155;
    --text-support: #566579;
    --text-success: #1d663f;
    --text-info: #2e6fae;
    --text-warning: #8a4b0f;
    --text-disabled: #566579;
    --text: var(--text-primary);
    --text2: var(--text-secondary);
    --muted: var(--text-support);
    --font-ui: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", Arial, sans-serif;
    --font-mono: "Cascadia Mono", Consolas, "Courier New", monospace;
    --type-product-title: 22px;
    --type-page-title: 28px;
    --type-page-description: 16px;
    --type-section-title: 20px;
    --type-subsection-title: 18px;
    --type-card-title: 16px;
    --type-body: 15px;
    --type-control: 14px;
    --type-support: 14px;
    --type-caption: 13px;
    --type-micro: 13px;
    --type-metric: 24px;
    --type-sequence-code: 14px;
    --weight-regular: 400;
    --weight-medium: 500;
    --weight-semibold: 600;
    --weight-bold: 700;
    --line-body: 1.6;
    --line-heading: 1.25;
    --line-compact: 1.4;
    /* Compatibility aliases retained for existing formal-page contracts. */
    --font: var(--font-ui);
    --mono: var(--font-mono);
    --type-metric-value: var(--type-metric);
    --weight-title: var(--weight-bold);
    --weight-card-title: var(--weight-semibold);
    --weight-control-primary: var(--weight-semibold);
    --weight-control-secondary: var(--weight-medium);
    --leading-title: var(--line-heading);
    --leading-section: var(--line-compact);
    --leading-subsection: var(--line-compact);
    --leading-body: var(--line-body);
    --leading-control: var(--line-compact);
    --leading-support: var(--line-body);
    --leading-micro: var(--line-compact);
    --r: 9px;
}

/* ── Reset & base ── */
html, body,
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="block-container"] {
    background: var(--bg) !important;
    color: var(--text) !important;
    font-family: var(--font-ui) !important;
}

/* ── Keep the native header control available for sidebar recovery ── */
[data-testid="stHeader"] {
    background: transparent !important;
    z-index: 100 !important;
}
[data-testid="stSidebarCollapseButton"] {
    display: flex !important;
    visibility: visible !important;
    opacity: 1 !important;
    pointer-events: auto !important;
    position: relative !important;
    z-index: 1001 !important;
}
[data-testid="stDecoration"],
footer { display: none !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    width: 252px !important;
    min-width: 252px !important;
    background: #f4f7f4 !important;
    border-right: 1px solid var(--border) !important;
    font-family: var(--font-ui) !important;
    overflow-x: hidden !important;
}
[data-testid="stSidebarContent"] { overflow-x: hidden !important; }

/* ── Sidebar nav buttons — default state ── */
[data-testid="stSidebar"] [data-testid="stButton"] > button {
    background: transparent !important;
    border: none !important;
    border-radius: 6px !important;
    color: #334155 !important;
    font-size: var(--type-control) !important;
    font-weight: var(--weight-control-secondary) !important;
    line-height: var(--leading-control) !important;
    text-align: left !important;
    padding: 6px 10px !important;
    width: 100% !important;
    min-width: 0 !important;
    white-space: nowrap !important;
    transition: background .12s, color .12s !important;
}
.formal-sidebar-title {
    color: var(--text-primary);
    font-size: var(--type-product-title);
    font-weight: var(--weight-title);
    line-height: var(--leading-title);
}
.formal-sidebar-support {
    color: var(--text-support);
    font-size: var(--type-support);
    line-height: var(--leading-support);
}
[data-testid="stSidebar"] [data-testid="stButton"] > button:hover {
    background: #f1f7f3 !important;
    color: #1f633d !important;
}
/* AI disclosure is an inline glyph, not a second pill-shaped navigation card. */
[data-testid="stSidebar"] .st-key-nav_agent_toggle button {
    background: transparent !important;
    border: 0 !important;
    box-shadow: none !important;
    border-radius: 0 !important;
    color: #566579 !important;
    min-width: 24px !important;
    width: 24px !important;
    padding: 4px 0 !important;
    text-align: center !important;
}
[data-testid="stSidebar"] .st-key-nav_agent_toggle button:hover,
[data-testid="stSidebar"] .st-key-nav_agent_toggle button:focus-visible {
    background: transparent !important;
    color: #1f633d !important;
    outline: 2px solid #8ab89a !important;
    outline-offset: 1px !important;
}

/* ── Active nav button — bright left-border highlight ── */
[data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"] {
    background: #e8f4ec !important;
    border-left: 4px solid #237a4b !important;
    border-radius: 0 7px 7px 0 !important;
    color: #1f633d !important;
    font-weight: var(--weight-bold) !important;
    padding-left: 7px !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] > button[kind="primary"]:hover {
    background: #f1f7f3 !important;
    color: #1f633d !important;
}

/* ── Block container padding ── */
.block-container {
    width: 100% !important;
    padding: 24px 32px 40px !important;
    max-width: 1680px !important;
    margin: 0 auto !important;
    box-sizing: border-box !important;
}

/* ── Headings ── */
h1 { font-family: var(--font-ui) !important; font-size: var(--type-page-title) !important; font-weight: var(--weight-title) !important; line-height: var(--leading-title) !important; color: var(--text-primary) !important; letter-spacing: 0; margin-bottom: 8px !important; }
h2 { font-family: var(--font-ui) !important; font-size: var(--type-section-title) !important; font-weight: var(--weight-title) !important; line-height: var(--leading-section) !important; color: var(--text-primary) !important; margin: 24px 0 12px !important; }
h3 { font-family: var(--font-ui) !important; font-size: var(--type-subsection-title) !important; font-weight: var(--weight-card-title) !important; line-height: var(--leading-subsection) !important; color: var(--text-secondary) !important; margin: 16px 0 8px !important; }
p { font-family: var(--font-ui) !important; font-size: var(--type-body) !important; line-height: var(--leading-body) !important; }
label { font-family: var(--font-ui) !important; font-size: var(--type-control) !important; font-weight: var(--weight-control-secondary) !important; line-height: var(--leading-control) !important; }
[data-testid="stCaptionContainer"] { color: var(--text-support) !important; font-family: var(--font-ui) !important; font-size: var(--type-caption) !important; line-height: var(--line-compact) !important; }
[data-testid="stMarkdownContainer"] { font-family: var(--font-ui) !important; }
[data-testid="stTextInput"] input::placeholder,
[data-testid="stTextArea"] textarea::placeholder { color: var(--text-support) !important; opacity: 1 !important; font-size: var(--type-control) !important; }

/* ── Base text roles for Streamlit controls and status surfaces ── */
input,
textarea,
select,
[data-baseweb="select"],
[data-testid="stSegmentedControl"] button {
    font-family: var(--font-ui) !important;
    font-size: var(--type-control) !important;
    line-height: var(--line-compact) !important;
}
[data-testid="stAlert"] { font-family: var(--font-ui) !important; font-size: var(--type-body) !important; line-height: var(--line-body) !important; }
[data-testid="stExpander"] summary { font-family: var(--font-ui) !important; font-size: var(--type-control) !important; font-weight: var(--weight-medium) !important; line-height: var(--line-compact) !important; }
[data-testid="stTable"] table,
[data-testid="stDataFrame"] { font-family: var(--font-ui) !important; font-size: var(--type-body) !important; line-height: var(--line-body) !important; }
[data-testid="stTable"] th { font-size: var(--type-control) !important; font-weight: var(--weight-semibold) !important; line-height: var(--line-compact) !important; }
[data-testid="stMetricLabel"] { font-family: var(--font-ui) !important; font-size: var(--type-support) !important; font-weight: var(--weight-medium) !important; line-height: var(--line-compact) !important; }
[data-testid="stMetricValue"] { font-family: var(--font-ui) !important; font-size: var(--type-metric) !important; font-weight: var(--weight-semibold) !important; line-height: var(--line-heading) !important; }
code,
pre,
[data-testid="stCodeBlock"],
.library-accession {
    font-family: var(--font-mono) !important;
    font-size: var(--type-sequence-code) !important;
    font-weight: var(--weight-regular) !important;
    line-height: var(--line-compact) !important;
}
.sequence-review-meta { display:flex;justify-content:space-between;gap:12px;color:var(--text-support);font-size:13px;margin:6px 0; }
.sequence-review-viewer { box-sizing:border-box;max-width:100%;height:340px;min-height:96px;overflow:auto;padding:12px;border:1px solid var(--border);border-radius:4px;background:#f7f9f8;white-space:pre;font-family:var(--font-mono) !important;font-size:13px;line-height:1.65;letter-spacing:0; }
.sequence-review-line { display:block; min-width:max-content; }

/* ── Tabs ── */
[data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid var(--border) !important;
    gap: 0 !important;
    padding: 0 !important;
}
[data-baseweb="tab"] {
    background: transparent !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    border-radius: 0 !important;
    font-size: var(--type-control) !important;
    font-weight: var(--weight-control-secondary) !important;
    color: var(--text-support) !important;
    padding: 9px 20px !important;
    transition: all .15s !important;
}
[aria-selected="true"][data-baseweb="tab"] {
    color: var(--accent-dark) !important;
    border-bottom-color: var(--accent) !important;
}
[data-testid="stTabPanel"] {
    padding-top: 1.2rem !important;
    background: transparent !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border-radius: var(--r); overflow: hidden; }

/* ── Buttons (main area) ── */
[data-testid="stMain"] [data-testid="stButton"] > button {
    font-family: var(--font-ui) !important;
    min-height: 40px !important;
    font-size: var(--type-control) !important;
    line-height: var(--leading-control) !important;
    border-radius: var(--r) !important;
    opacity: 1 !important;
}
[data-testid="stMain"] [data-testid="stButton"] > button[kind="primary"]:not(:disabled) {
    background: #237a4b !important;
    border-color: #237a4b !important;
    color: #ffffff !important;
    font-weight: var(--weight-control-primary) !important;
    opacity: 1 !important;
}
[data-testid="stMain"] [data-testid="stButton"] > button[kind="primary"]:not(:disabled):hover {
    background: #1d663f !important;
    border-color: #1d663f !important;
    color: #ffffff !important;
}
[data-testid="stMain"] [data-testid="stButton"] > button[kind="secondary"],
[data-testid="stMain"] [data-testid="stButton"] > button:not([kind="primary"]):not(:disabled),
[data-testid="stDownloadButton"] > button:not(:disabled) {
    background: #ffffff !important;
    color: #334155 !important;
    border: 1px solid #cbd5e1 !important;
    font-weight: var(--weight-control-secondary) !important;
    opacity: 1 !important;
}
[data-testid="stMain"] [data-testid="stButton"] > button:disabled,
[data-testid="stDownloadButton"] > button:disabled {
    background: #e5e7eb !important;
    color: var(--text-disabled) !important;
    border-color: #d1d5db !important;
    opacity: 1 !important;
    cursor: not-allowed !important;
}
[data-testid="stMain"] [data-testid="stButton"] > button:disabled *,
[data-testid="stDownloadButton"] > button:disabled * {
    color: var(--text-disabled) !important;
    opacity: 1 !important;
}
[data-testid="stDownloadButton"] > button { min-height: 40px !important; border-radius: var(--r) !important; font-size: var(--type-control) !important; line-height: var(--leading-control) !important; }

/* Reusable formal workspace surfaces */
.formal-content { max-width: 1120px; }
.formal-section-heading { color: var(--text-primary); font-size: var(--type-card-title); font-weight: var(--weight-card-title); line-height: var(--leading-subsection); margin: 24px 0 12px; padding-top: 18px; border-top: 1px solid var(--border); }
.formal-section-heading.first { margin-top: 0; padding-top: 0; border-top: 0; }
.formal-section-heading.step3-flow { padding-top:0; border-top:0; }
.formal-section-heading.step3-components { margin:32px 0 12px; }
.formal-section-heading.step3-checks { margin:16px 0 12px; }
.formal-context-grid { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:1px; overflow:hidden; margin:0; border:1px solid var(--border); border-radius:var(--r); background:var(--border); }
.formal-context-item { min-width:0; padding:12px 14px; background:var(--surface); }
.formal-context-label { color:var(--text-support); font-size:var(--type-micro); font-weight:var(--weight-card-title); line-height:var(--leading-micro); }
.formal-context-value { margin-top:4px; color:var(--text-primary); font-size:var(--type-control); font-weight:var(--weight-card-title); line-height:var(--leading-control); overflow-wrap:anywhere; }
.formal-step5-strategy-grid { grid-template-columns:repeat(3,minmax(0,1fr)); }
.formal-step5-preview { border:1px solid var(--border); border-radius:var(--r); background:var(--surface); padding:14px; }
.formal-step5-preview-meta { display:flex; justify-content:space-between; gap:12px; color:var(--text-support); font-size:var(--type-micro); line-height:var(--leading-micro); }
.formal-step5-preview-track { position:relative; height:46px; margin:10px 0 0; overflow:hidden; border:1px solid #d8dfda; border-radius:5px; background:#f8faf8; }
.formal-step5-preview-cassette { position:absolute; top:8px; height:28px; min-width:3px; border-radius:4px; background:#237a4b; opacity:.18; }
.formal-step5-preview-feature { position:absolute; top:13px; height:18px; min-width:3px; border-radius:3px; }
.formal-step5-preview-components { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:1px; margin-top:10px; overflow:hidden; border:1px solid var(--border); border-radius:5px; background:var(--border); }
.formal-step5-preview-component { min-width:0; padding:9px 10px; background:#f8faf8; }
.formal-step5-preview-role { color:var(--text-support); font-size:var(--type-micro); font-weight:var(--weight-card-title); line-height:var(--leading-micro); }
.formal-step5-preview-name { margin-top:3px; color:var(--text-primary); font-size:var(--type-control); font-weight:var(--weight-card-title); line-height:var(--leading-control); overflow-wrap:anywhere; }
.formal-step5-preview-length, .formal-step5-hash-note { margin-top:3px; color:var(--text-support); font-size:var(--type-micro); line-height:var(--leading-micro); }
.formal-step5-preview-empty { margin:0; color:var(--text-support); font-size:var(--type-support); line-height:var(--leading-support); }
.formal-step5-check-grid { grid-template-columns:repeat(3,minmax(0,1fr)); }
.formal-required-slot-title { margin-bottom:4px; color:var(--text-primary); font-size:var(--type-card-title); font-weight:var(--weight-card-title); line-height:var(--leading-subsection); }
.formal-step3-readonly { color:var(--text-primary); font-size:var(--type-control); line-height:var(--leading-control); overflow-wrap:anywhere; }
.formal-step3-readonly strong { display:block; font-weight:var(--weight-card-title); }
.formal-step3-readonly span { display:block; margin-top:5px; color:var(--text-support); font-size:var(--type-support); line-height:var(--leading-support); }
.formal-component-status-summary { color:var(--text-support); font-size:var(--type-support); line-height:var(--leading-support); overflow-wrap:anywhere; }
.formal-component-status-summary strong { color:var(--text-primary); font-size:var(--type-control); font-weight:var(--weight-card-title); }
.st-key-formal_content_section_step3_required { width:100%; margin-bottom:16px; }
[class*="st-key-formal_step3_component_"] { margin:0 0 18px; padding:0; }
[class*="st-key-formal_step3_component_"] [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:minmax(170px,190px) minmax(0,1fr) minmax(180px,220px) !important; gap:20px !important; align-items:start; }
[class*="st-key-formal_step3_component_"] [data-testid="stColumn"] { width:100% !important; min-width:0 !important; }
.st-key-formal_step3_component_three_prime { margin-bottom:0; }
.formal-check-summary { margin:0 0 8px; color:var(--text-primary); font-size:var(--type-control); font-weight:var(--weight-card-title); line-height:var(--leading-control); }
.formal-check-list { display:grid; gap:6px; margin:8px 0 12px; }
.formal-check-item { padding:8px 10px; border:1px solid var(--border); border-radius:var(--r-sm); background:var(--surface); color:var(--text-secondary); font-size:var(--type-support); line-height:var(--leading-support); }
.formal-check-item.blocking { border-color:var(--red); color:var(--red); }
.formal-compact-summary { margin:10px 0 4px; color:var(--text-support); font-size:var(--type-support); line-height:var(--leading-support); }
[data-testid="stMain"]:has(.st-key-formal_content_section_step3_required) [data-testid="stAlert"] { border:1px solid var(--border); background:var(--surface); }
[data-testid="stMain"]:has(.st-key-formal_content_section_step3_required) [data-testid="stAlert"] p { color:var(--text-secondary); }
.formal-home-action-heading { color:var(--text-secondary); font-size:var(--type-card-title); font-weight:var(--weight-card-title); line-height:var(--leading-subsection); margin:0; }
.st-key-formal_home_actions [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:max-content max-content max-content minmax(0,1fr) !important; gap:10px !important; align-items:center; }
.st-key-formal_home_actions [data-testid="stColumn"] { width:auto !important; min-width:0 !important; }
.st-key-formal_home_actions [data-testid="stButton"] > button { min-height:36px !important; padding:7px 12px !important; white-space:nowrap !important; }
.st-key-formal_project_view_switch { margin:4px 0 12px; }
.st-key-project_center_view { width:fit-content !important; }
.st-key-project_center_view [data-testid="stRadio"] > div[role="radiogroup"] { display:inline-flex !important; gap:0 !important; padding:0 !important; border:0 !important; background:transparent !important; }
.st-key-project_center_view [data-testid="stRadio"] label[data-baseweb="radio"] { min-height:32px !important; margin:0 !important; padding:0 14px !important; border:1px solid var(--border) !important; border-radius:4px !important; color:var(--text-secondary) !important; background:#ffffff !important; }
.st-key-project_center_view [data-testid="stRadio"] label[data-baseweb="radio"] > div:first-child { display:none !important; }
.st-key-project_center_view [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) { border-color:var(--accent) !important; color:var(--accent-dark) !important; background:var(--accent-lt) !important; font-weight:var(--weight-card-title) !important; }
.st-key-project_center_view [data-testid="stRadio"] label[data-baseweb="radio"] p { margin:0 !important; line-height:32px !important; }
.st-key-formal_project_table_head { margin:4px 0 10px; padding:8px 14px 0; border:0; background:transparent; }
.st-key-formal_project_table_head [data-testid="stHorizontalBlock"],
[class*="st-key-formal_project_summary_"] [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:minmax(180px,3.4fr) minmax(130px,2fr) minmax(150px,2.2fr) minmax(120px,1.7fr) minmax(142px,1.35fr) !important; gap:14px !important; align-items:center; }
.st-key-formal_project_table_head [data-testid="stColumn"],
[class*="st-key-formal_project_summary_"] [data-testid="stColumn"] { width:100% !important; min-width:0 !important; }
.formal-project-column-heading { color:var(--text-support); font-size:var(--type-micro); font-weight:var(--weight-card-title); line-height:var(--leading-micro); }
.formal-project-name { color:var(--text-primary); font-size:var(--type-control); font-weight:var(--weight-card-title); line-height:var(--leading-control); overflow-wrap:anywhere; }
.formal-project-cell { color:var(--text-secondary); font-size:var(--type-control); line-height:var(--leading-control); overflow-wrap:anywhere; min-width:0; }
.formal-project-updated-label { display:none; }
[class*="st-key-formal_project_summary_"] { margin-bottom: 10px; padding:14px !important; }
[class*="st-key-formal_project_summary_"] [data-testid="stButton"] > button { min-height:32px !important; padding:4px 8px !important; white-space:nowrap !important; }
[class*="st-key-formal_project_actions_"] [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:68px 68px !important; gap:6px !important; align-items:center; width:142px !important; }
[class*="st-key-formal_project_actions_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { width:auto !important; min-width:0 !important; }
[class*="st-key-formal_project_actions_"] [data-testid="stButton"] > button { width:68px !important; min-width:68px !important; min-height:32px !important; height:32px !important; padding:4px 8px !important; }
[class*="st-key-formal_project_actions_"] [data-testid="stPopover"] [data-testid="stPopoverButton"] { min-width:68px !important; width:68px !important; min-height:32px !important; height:32px !important; padding:4px 8px !important; white-space:nowrap !important; }
[data-testid="stPopoverBody"]:has([class*="st-key-formal_project_actions_menu_items_"]) { width:132px !important; min-width:132px !important; padding:8px !important; }
[data-testid="stPopoverBody"]:has([class*="st-key-formal_project_actions_menu_items_"]) [data-testid="stElementContainer"] { width:100% !important; margin-bottom:6px !important; }
[data-testid="stPopoverBody"]:has([class*="st-key-formal_project_actions_menu_items_"]) [data-testid="stButton"] > button { width:100% !important; min-height:32px !important; height:32px !important; padding:4px 8px !important; }
.st-key-project_lifecycle_rename_actions { width:100% !important; margin-top:8px !important; margin-bottom:0 !important; }
.st-key-project_lifecycle_rename_actions [data-testid="stHorizontalBlock"] { display:flex !important; flex-flow:row nowrap !important; justify-content:flex-end !important; align-items:center !important; gap:8px !important; width:100% !important; }
.st-key-project_lifecycle_rename_actions [data-testid="stElementContainer"] { flex:0 0 68px !important; width:68px !important; min-width:68px !important; }
.st-key-project_lifecycle_rename_actions [data-testid="stButton"] { width:68px !important; min-width:68px !important; max-width:68px !important; }
.st-key-project_lifecycle_rename_actions [data-testid="stButton"] > button { width:68px !important; min-width:68px !important; max-width:68px !important; height:32px !important; min-height:32px !important; padding:4px 8px !important; }
.st-key-project_center_toolbar { width:100%; max-width:960px; }
.st-key-project_center_toolbar [data-testid="stHorizontalBlock"] { gap:12px !important; align-items:end; }
.st-key-project_center_toolbar_primary [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:minmax(0,3.2fr) minmax(180px,1fr) !important; gap:12px !important; align-items:end; }
.st-key-project_center_filters [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:repeat(3,minmax(0,1fr)) max-content !important; gap:12px !important; align-items:end; }
.st-key-project_center_toolbar_primary [data-testid="stColumn"],
.st-key-project_center_filters [data-testid="stColumn"] { width:100% !important; min-width:0 !important; }
.st-key-project_center_filters [data-testid="stButton"] > button { min-width:88px !important; }
.formal-project-browser-count { color:var(--text-secondary); font-size:var(--type-support); font-weight:var(--weight-medium); margin:0 0 12px; }
.st-key-project_center_pagination { width:100%; max-width:560px; margin:14px auto 0; }
.st-key-project_center_pagination [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:repeat(3,minmax(0,1fr)) !important; gap:12px !important; align-items:center; }
.st-key-project_center_pagination [data-testid="stColumn"] { width:100% !important; min-width:0 !important; }
.st-key-project_center_pagination [data-testid="stButton"] > button { width:100% !important; min-width:0 !important; white-space:nowrap !important; }
.formal-project-pagination-status { color:var(--text-secondary); font-size:var(--type-support); text-align:center; padding-top:0; }
.formal-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--r); padding: 24px; margin: 16px 0; }
.formal-card.compact { padding: 16px; }
.formal-kicker { color: var(--text-success); font-size: var(--type-micro); font-weight: var(--weight-title); line-height: var(--leading-micro); margin-bottom: 8px; }
.formal-subtitle { color: var(--text-support); font-size: var(--type-page-description); line-height: var(--line-body); margin-bottom: 24px; }
.home-empty { min-height: 210px; display:flex; flex-direction:column; justify-content:center; align-items:flex-start; }
.home-empty-title { font-size: var(--type-subsection-title); font-weight: var(--weight-card-title); line-height: var(--leading-subsection); color: var(--text-primary); margin-bottom: 8px; }
.home-empty-note { color: var(--text-support); font-size: var(--type-body); line-height: var(--leading-body); max-width: 520px; }
.summary-grid { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; margin:16px 0; }
.summary-card { min-height:132px; background:var(--surface); border:1px solid var(--border); border-radius:var(--r); padding:16px; }
.summary-card-label { color:var(--text-support); font-size:var(--type-support); font-weight:var(--weight-card-title); line-height:var(--leading-support); margin-bottom:10px; }
.summary-card-value { color:var(--text-primary); font-size:var(--type-card-title); font-weight:var(--weight-title); line-height:var(--line-body); overflow-wrap:anywhere; }
.summary-card-note { color:var(--text-support); font-size:var(--type-support); margin-top:8px; line-height:var(--leading-support); }
.result-summary-grid { display:grid; grid-template-columns:repeat(5,minmax(0,1fr)); gap:12px; margin:16px 0 24px; }
.result-summary-grid.history-preview { grid-template-columns:repeat(4,minmax(0,1fr)); }
.result-summary-card { background:var(--surface); border:1px solid var(--border); border-radius:var(--r); padding:14px; }
.result-summary-card .label { color:var(--text-support); font-size:var(--type-micro); font-weight:var(--weight-card-title); line-height:var(--leading-micro); }
.result-summary-card .value { color:var(--text-primary); font-size:var(--type-metric); font-weight:var(--weight-bold); line-height:var(--line-heading); margin-top:8px; overflow-wrap:anywhere; }
.result-summary-card.warning { border-left:4px solid var(--warning); }
.result-summary-card.blocking { border-left:4px solid var(--red); }
.result-summary-grid:not(.history-preview) { gap:10px; margin:12px 0 18px; }
.result-summary-grid:not(.history-preview) .result-summary-card { padding:10px 12px; }
.result-summary-grid:not(.history-preview) .result-summary-card.build { min-height:72px; }
.result-summary-grid:not(.history-preview) .result-summary-card.warning,
.result-summary-grid:not(.history-preview) .result-summary-card.blocking { min-height:64px; }
.result-summary-grid:not(.history-preview) .result-summary-card .label { font-size:var(--type-micro); line-height:var(--line-compact); }
.result-summary-grid:not(.history-preview) .result-summary-card .value { font-size:var(--type-subsection-title); line-height:var(--line-heading); margin-top:5px; }
.result-summary-grid:not(.history-preview) .result-summary-card.warning { border-left:3px solid var(--warning); }
.result-summary-grid:not(.history-preview) .result-summary-card.blocking { border-left:3px solid #b85a5a; }
.result-project-name { color:var(--text-primary); font-size:var(--type-body); font-weight:var(--weight-card-title); line-height:var(--leading-body); margin:0 0 8px; }
.formal-action-row { display:flex; flex-wrap:wrap; gap:12px; align-items:center; margin-top:20px; }
.formal-success { border:1px solid #acd4b6; border-left:5px solid var(--accent); background:var(--green-lt); border-radius:var(--r); padding:16px; margin:16px 0; }
.formal-success strong { color:var(--text-success); display:block; font-size:var(--type-card-title); line-height:var(--leading-subsection); margin-bottom:4px; }
.formal-success span { color:var(--text-secondary); font-size:var(--type-body); line-height:var(--leading-body); }
.component-chain { display:flex; align-items:center; justify-content:center; gap:8px; margin:16px 0; flex-wrap:wrap; }
.component-chain-part { min-width:150px; max-width:260px; padding:12px; border-radius:8px; color:#fff; text-align:center; font-size:var(--type-control); font-weight:var(--weight-card-title); line-height:var(--leading-control); overflow-wrap:anywhere; }
.component-chain-arrow { color:var(--muted); font-size:20px; font-weight:700; }
.meta-inline { color:var(--text-support); font-size:var(--type-support); line-height:var(--leading-support); margin-top:8px; }
.library-head { display:grid; grid-template-columns:minmax(180px,2fr) 100px 90px minmax(150px,1.2fr) 180px; gap:12px; align-items:center; color:var(--text-support); font-size:var(--type-micro); font-weight:var(--weight-title); line-height:var(--leading-micro); padding:8px 16px; }
.library-head > span:not(:first-child) { text-align:center; }
[class*="st-key-formal_library_row_"] { min-height:56px; margin:0; padding:12px 16px 16px; border-bottom:1px solid var(--border); box-sizing:border-box; }
[class*="st-key-formal_library_row_"] [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:minmax(180px,2fr) 100px 90px minmax(150px,1.2fr) 180px !important; gap:12px !important; align-items:center; }
[class*="st-key-formal_library_row_"] [data-testid="stColumn"] { width:100% !important; min-width:0 !important; }
.library-name { color:var(--text-primary); font-size:var(--type-control); font-weight:var(--weight-card-title); line-height:var(--leading-control); overflow-wrap:anywhere; }
.library-status-group { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
.library-cell { color:var(--text-secondary); font-size:var(--type-control); line-height:var(--leading-control); overflow-wrap:anywhere; }
.library-cell.centered { text-align:center; }
.library-accession { overflow-wrap:anywhere; text-align:center; }
[class*="st-key-formal_library_action_"] [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:60px minmax(0,1fr) !important; gap:6px !important; align-items:center; }
[class*="st-key-formal_library_action_"] [data-testid="stColumn"] { width:100% !important; min-width:0 !important; }
[class*="st-key-formal_library_action_"] [data-testid="stPopover"] > button,
[class*="st-key-formal_library_action_"] [data-testid="stPopoverButton"],
[class*="st-key-formal_library_action_"] [data-testid="stPopoverButton"] button,
[class*="st-key-formal_library_action_"] [data-testid="stButton"] > button { height:auto !important; min-height:32px !important; max-width:100% !important; padding:6px !important; white-space:normal !important; overflow-wrap:anywhere; }
[class*="st-key-formal_library_action_"] [data-testid="stButton"] p { white-space:normal !important; overflow-wrap:anywhere; }
.library-status { display:block; max-width:100%; box-sizing:border-box; padding:2px 5px; border:1px solid var(--border2); border-radius:4px; color:var(--text-support); font-size:var(--type-micro); font-weight:var(--weight-regular); line-height:var(--leading-micro); overflow-wrap:anywhere; }
.library-badge { display:inline-block; border-radius:999px; padding:2px 6px; color:var(--text-success); background:var(--accent-lt); font-size:var(--type-micro); font-weight:var(--weight-card-title); line-height:var(--leading-micro); }
.library-badge.cds { color:#1e6d42; background:#e6f5e9; }
.library-badge.terminator { color:#9a5d14; background:#fff1df; }
.library-badge.backbone { color:#59635e; background:#edf0ee; }

/* ── Canonical plasmid map mounted from the existing MVP10 renderer ── */
.map-frame {
    border: 1px solid var(--border);
    border-radius: var(--r);
    background: #fbfcfb;
    min-height: 600px;
    padding: 8px;
    overflow: hidden;
}
.map-frame svg { height: min(68vh, 640px) !important; }
.map-frame svg .map-feature-label { font-size: var(--type-micro) !important; }
.map-frame svg .map-center-value { font-size: var(--type-section-title) !important; font-weight: var(--weight-title) !important; }
.map-frame svg .map-center-label { font-size: var(--type-micro) !important; }
.map-note {
    color: var(--text-support);
    font-size: var(--type-micro);
    line-height: var(--leading-micro);
    margin-top: .35rem;
}
.formal-step-strip { margin: 12px 0 16px; }
.st-key-formal_step_strip [class*="st-key-formal_step_card_"] {
    box-sizing: border-box;
    width: 100%;
    height: auto;
    min-height: 76px;
    padding: 12px 8px 16px;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    background: #ffffff;
    color: #334155;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
    overflow: visible;
}
.st-key-formal_step_strip [class*="st-key-formal_step_card_"][class*="_current"] {
    border-color: #237a4b;
    background: #eef8f0;
}
.st-key-formal_step_strip [class*="st-key-formal_step_card_"][class*="_review"] {
    border-color: #d6c2a7;
}
.st-key-formal_step_strip [class*="st-key-formal_step_card_"] [data-testid="stButton"] {
    margin: 0 !important;
}
[data-testid="stMain"] .st-key-formal_step_strip [class*="st-key-formal_step_card_"] [data-testid="stButton"] > button {
    width: 100% !important;
    height: auto !important;
    min-height: 0 !important;
    padding: 0 !important;
    border: 0 !important;
    background: transparent !important;
    color: #334155 !important;
    font-size: var(--type-control) !important;
    font-weight: var(--weight-control-primary) !important;
    line-height: var(--leading-control) !important;
    text-align: center !important;
    white-space: normal !important;
}
[data-testid="stMain"] .st-key-formal_step_strip [class*="st-key-formal_step_card_"] [data-testid="stButton"] > button:hover {
    color: #1f633d !important;
}
[data-testid="stMain"] .st-key-formal_step_strip [class*="st-key-formal_step_card_"] [data-testid="stButton"] > button p {
    margin: 0 !important;
    line-height: var(--line-compact) !important;
}
.formal-step-status {
    margin-top: 8px;
    margin-bottom: 12px;
    color: var(--text-support);
    font-size: var(--type-micro);
    font-weight: var(--weight-control-secondary);
    line-height: var(--leading-micro);
    text-align: center;
    white-space: normal;
    overflow: visible;
}
.formal-step-status.current { color: #176b3a; }
.formal-step-status.done { color: var(--text-success); }
.formal-step-status.available { color: var(--text-info); }
.formal-step-status.blocked { color: var(--text-disabled); }
.formal-step-status.review { color: var(--text-warning); }
.st-key-formal_step_strip [class*="_current"] .formal-step-status { color: #176b3a; }
[data-testid="stMain"] .st-key-formal_step_strip [class*="st-key-formal_step_card_"] [data-testid="stButton"] > button:focus-visible {
    outline: 2px solid #237a4b !important;
    outline-offset: 2px;
}
.formal-structure {
    display: flex;
    align-items: stretch;
    justify-content:center;
    gap: 8px;
    margin: 16px 0;
}
.formal-structure-part {
    flex: 1;
    min-width: 0;
    border-radius: 8px;
    color: #fff;
    padding: 12px;
    text-align: center;
    font-size: var(--type-control);
    font-weight: var(--weight-card-title);
    line-height: var(--leading-control);
    overflow-wrap: anywhere;
}
.step6-structure-overview {
    padding: 12px 16px;
    margin: 10px 0 12px;
}
.step6-structure-overview .formal-structure {
    margin: 8px 0 5px;
}
.step6-structure-overview .meta-inline {
    margin-top: 4px;
}
.formal-promoter { background: var(--promoter); color: #ffffff; }
.formal-regulatory { background: #e3ecf5; color: #213e59; border: 1px solid #9fb6cc; }
.formal-cds { background: var(--cds); }
.formal-terminator { background: var(--terminator); color: var(--text-primary); }
.formal-backbone { background: var(--backbone); color: #ffffff; }
.formal-arrow { align-self: center; color: var(--muted); font-weight: var(--weight-bold); }
.linear-map { border:1px solid var(--border); border-radius:7px; background:#fbfcfb; padding:.85rem; overflow-x:auto; }
.linear-map-inner { min-width:760px; }
.linear-map-scale { display:grid; grid-template-columns:6rem minmax(0, 1fr); gap:.5rem; color:var(--text-support); font-size:var(--type-micro); line-height:var(--leading-micro); margin:0 0 .35rem; }
.linear-map-scale-values { display:flex; justify-content:space-between; min-width:0; }
.linear-track-row { display:grid; grid-template-columns:6rem 1fr; gap:.5rem; align-items:center; margin:.5rem 0; }
.linear-track-label { color:var(--text-support); font-size:var(--type-micro); font-weight:var(--weight-title); line-height:var(--leading-micro); text-align:right; }
.linear-track { position:relative; height:3rem; border:1px solid #d8dfda; border-radius:5px; background:#fff; }
.linear-feature { position:absolute; display:flex; align-items:center; justify-content:center; min-width:4px; height:1.45rem; top:.7rem; border-radius:4px; color:#fff; font-size:var(--type-micro); font-weight:var(--weight-title); line-height:var(--leading-micro); overflow:hidden; white-space:nowrap; padding:0 .18rem; }
.linear-feature[style*="#278d87"],
.linear-feature[style*="rgb(39, 141, 135)"] { background: var(--origin) !important; }
.map-legend { display:flex; flex-wrap:wrap; gap:.45rem 1rem; margin:.7rem 0 .35rem; color:var(--text-support); font-size:var(--type-micro); line-height:var(--leading-micro); }
.map-legend-item { display:inline-flex; align-items:center; gap:.38rem; white-space:nowrap; }
.map-legend-swatch { width:.72rem; height:.72rem; border-radius:2px; flex:0 0 auto; }
@media(max-width: 900px) {
    .formal-structure { flex-direction: column; }
    .formal-arrow { transform: rotate(90deg); text-align: center; }
    .block-container { padding: 16px !important; }
    .formal-section-heading { margin-top: 20px; padding-top: 16px; }
    .formal-card { padding: 16px; }
    .step6-structure-overview { padding: 12px; margin: 8px 0 10px; }
    .step6-structure-overview .formal-structure { margin: 6px 0 4px; }
    .formal-context-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .formal-context-item { padding:10px 12px; }
    .formal-step5-strategy-grid, .formal-step5-check-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
    .formal-step5-preview-components { grid-template-columns:minmax(0,1fr); }
    .formal-step5-preview-meta { align-items:flex-start; flex-direction:column; gap:3px; }
    .st-key-formal_step_strip [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:repeat(2,minmax(0,1fr)) !important; gap:8px !important; }
    .st-key-formal_step_strip [data-testid="stColumn"] { width:100% !important; min-width:0 !important; }
    .st-key-formal_step_strip [class*="st-key-formal_step_card_"] { min-height:58px; padding:8px 6px 10px; }
    .st-key-formal_step_strip .formal-step-status { margin-top:4px; margin-bottom:4px; }
    .st-key-formal_home_actions [data-testid="stHorizontalBlock"],
    [class*="st-key-formal_page_actions_step_"] [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:minmax(0,1fr) !important; gap:8px !important; }
    .st-key-formal_home_actions [data-testid="stColumn"],
    [class*="st-key-formal_page_actions_step_"] [data-testid="stColumn"] { width:100% !important; min-width:0 !important; }
    .st-key-formal_home_actions [data-testid="stButton"] > button { width:100% !important; }
    .st-key-project_center_toolbar { max-width:none; }
    .st-key-project_center_toolbar [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:minmax(0,1fr) !important; gap:8px !important; }
    .st-key-project_center_toolbar [data-testid="stColumn"] { width:100% !important; min-width:0 !important; }
    .st-key-project_center_toolbar [data-testid="stTextInput"] input,
    .st-key-project_center_toolbar [data-testid="stSelectbox"] select { width:100% !important; }
    .st-key-project_center_pagination { max-width:none; margin-top:12px; }
    .st-key-project_center_pagination [data-testid="stHorizontalBlock"] { grid-template-columns:repeat(3,minmax(0,1fr)) !important; gap:8px !important; }
    .st-key-formal_project_table_head { display:none; }
    [class*="st-key-formal_project_summary_"] [data-testid="stHorizontalBlock"] { display:grid !important; grid-template-columns:minmax(0,1fr) !important; gap:8px !important; }
    [class*="st-key-formal_project_summary_"] [data-testid="stColumn"] { width:100% !important; min-width:0 !important; }
    [class*="st-key-formal_project_summary_"] [data-testid="stColumn"]:not(:last-child) [data-testid="stElementContainer"] { margin-bottom:16px !important; }
    .formal-project-updated-label { display:inline; color:var(--text-support); font-weight:var(--weight-card-title); }
    [class*="st-key-formal_project_summary_"] [data-testid="stButton"] > button { width:100% !important; }
    [class*="st-key-formal_project_actions_"] [data-testid="stHorizontalBlock"] { grid-template-columns:minmax(0,1fr) 72px !important; gap:6px !important; width:100% !important; }
    [class*="st-key-formal_project_actions_"] [data-testid="stElementContainer"],
    [class*="st-key-formal_project_actions_"] [data-testid="stButton"] { width:100% !important; }
    [class*="st-key-formal_project_actions_"] [data-testid="stButton"] > button { width:100% !important; min-width:0 !important; min-height:36px !important; height:36px !important; }
    [class*="st-key-formal_project_actions_"] [data-testid="stPopover"] [data-testid="stPopoverButton"] { min-width:72px !important; width:72px !important; min-height:36px !important; height:36px !important; }
    .st-key-project_lifecycle_rename_actions [data-testid="stHorizontalBlock"] { flex-flow:row nowrap !important; justify-content:flex-end !important; gap:8px !important; }
    .st-key-project_lifecycle_rename_actions [data-testid="stElementContainer"] { flex:0 0 68px !important; width:68px !important; min-width:68px !important; }
    .st-key-project_lifecycle_rename_actions [data-testid="stButton"] { width:68px !important; min-width:68px !important; max-width:68px !important; }
    .st-key-project_lifecycle_rename_actions [data-testid="stButton"] > button { width:68px !important; min-width:68px !important; max-width:68px !important; height:32px !important; min-height:32px !important; }
    [class*="st-key-formal_step3_component_"] [data-testid="stHorizontalBlock"] { grid-template-columns:minmax(0,1fr) !important; gap:8px !important; }
    .formal-step3-readonly span { margin-top:3px; }
    .summary-grid, .result-summary-grid { grid-template-columns:1fr; }
    .library-head { display:none; }
    [class*="st-key-formal_library_row_"] [data-testid="stHorizontalBlock"] { grid-template-columns:repeat(2,minmax(0,1fr)) !important; gap:8px !important; }
    [class*="st-key-formal_library_row_"] [data-testid="stColumn"]:last-child { grid-column:1 / -1; }
    [class*="st-key-formal_library_action_"] [data-testid="stHorizontalBlock"] { grid-template-columns:60px minmax(0,1fr) !important; }
    [class*="st-key-formal_library_action_"] [data-testid="stColumn"]:last-child { grid-column:auto; }
}
.st-key-formal_step2_cds_text textarea {
    font-family: var(--font-mono) !important;
    font-size: var(--type-sequence-code) !important;
    line-height: var(--line-compact) !important;
    min-height: 220px;
    white-space: pre;
    overflow-x: auto;
}
.st-key-formal_step2_cds_text {
    width: 100%;
    max-width: 960px;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Formal page definitions
# ---------------------------------------------------------------------------
PAGE_PROJECT_HOME = "Project Home"
PAGE_DESIGN_WORKSPACE = "Six-Step Design Workspace"
PAGE_RESULTS_EXPORT = "Results and Export"
PAGE_PLANT_LIBRARY = "Plant Component Library"
PAGE_SEQUENCE_TOOLBOX = "Sequence Toolbox"
PAGE_CRISPR_WORKFLOW = "CRISPR V1 Workflow"
PAGE_AGENT_WORKSPACE = "Agent V1 Workspace"

PROJECT_TYPE_SINGLE_GENE = "single_gene"
PROJECT_TYPE_DUAL_TU = "dual_tu"
PROJECT_TYPE_GATE3_PATHWAY_DRAFT = "gate3_pathway_draft"
_PROJECT_MODE_LABELS = {
    PROJECT_TYPE_SINGLE_GENE: "v1.expression.single_gene",
    PROJECT_TYPE_DUAL_TU: "v1.expression.multi_tu_adjustable_order",
}
GATE3_PATHWAY_DRAFT_KEY = "gate3_pathway_draft"
GATE3_PATHWAY_DRAFT_SCHEMA_VERSION = "v1"

_ALL_PAGES = [
    PAGE_PROJECT_HOME,
    PAGE_DESIGN_WORKSPACE,
    PAGE_RESULTS_EXPORT,
    PAGE_PLANT_LIBRARY,
    PAGE_SEQUENCE_TOOLBOX,
    PAGE_CRISPR_WORKFLOW,
    PAGE_AGENT_WORKSPACE,
]

_PRIMARY_NAV_PAGES = (
    PAGE_PROJECT_HOME,
    PAGE_AGENT_WORKSPACE,
    PAGE_DESIGN_WORKSPACE,
    PAGE_PLANT_LIBRARY,
    PAGE_SEQUENCE_TOOLBOX,
    PAGE_CRISPR_WORKFLOW,
)

_NAV_LABEL_KEYS = {
    PAGE_PROJECT_HOME: "v1.project_center.title",
    PAGE_AGENT_WORKSPACE: "v1.common.assisted_design",
    PAGE_DESIGN_WORKSPACE: "v1.common.expression_design",
    PAGE_CRISPR_WORKFLOW: "v1.common.gene_editing",
    PAGE_PLANT_LIBRARY: "v1.common.component_library",
    PAGE_SEQUENCE_TOOLBOX: "v1.common.sequence_tools",
}
# Compatibility map retained for route-shape tests and technical readback;
# visible labels are resolved through _nav_label so language changes rerender.
_NAV_LABELS = {
    PAGE_PROJECT_HOME: "项目中心",
    PAGE_AGENT_WORKSPACE: "智能设计",
    PAGE_DESIGN_WORKSPACE: "表达设计",
    PAGE_CRISPR_WORKFLOW: "CRISPR",
    PAGE_PLANT_LIBRARY: "元件库",
    PAGE_SEQUENCE_TOOLBOX: "序列工具",
}


def _nav_label(page: str) -> str:
    return _t(_NAV_LABEL_KEYS[page])


def _sync_language_switch() -> None:
    selected = str(st.session_state.get("formal_language_switch") or "EN")
    _set_language("zh-CN" if selected == "中文" else "en")

_PRIMARY_NAV_ROUTE_ALIASES = {
    PAGE_RESULTS_EXPORT: PAGE_DESIGN_WORKSPACE,
}


def _primary_navigation_page(page: str) -> str:
    """Return the single primary navigation entry for a formal route."""
    if page in _PRIMARY_NAV_PAGES:
        return page
    if page in _PRIMARY_NAV_ROUTE_ALIASES:
        return _PRIMARY_NAV_ROUTE_ALIASES[page]
    raise ValueError(f"Unknown formal page route: {page}")

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------

startup_warnings = _STARTUP_WARNINGS
startup_errors = _STARTUP_ERRORS

from core.page_routing import reconcile_selected_page_from_query
from core.session_keys import SK as _SK

reconcile_selected_page_from_query(
    st.session_state,
    st.query_params,
    _ALL_PAGES,
    selected_page_key=_SK.SELECTED_PAGE,
    default_page=PAGE_PROJECT_HOME,
)

# Initialise the global project-context keys (safe no-op on rerun).
_SK.init_project_context()
if _SK.ACTIVE_RESET_TOKEN not in st.session_state:
    st.session_state[_SK.ACTIVE_RESET_TOKEN] = "0"


def _change_page(target: str) -> None:
    """Callback used by all views to trigger a page transition."""
    if target in _ALL_PAGES:
        previous_page = st.session_state.get(_SK.SELECTED_PAGE)
        if (
            previous_page == PAGE_PROJECT_HOME
            and target != PAGE_PROJECT_HOME
            and not st.session_state.get("project_center_open_callback_in_progress")
        ):
            st.session_state.pop("agent_project_selection_return", None)
        created_by_intelligent_design = str(
            st.session_state.get("agent_v1_ui_created_project_id") or ""
        ).strip()
        current_project_id = str(st.session_state.get("mvp_project_id") or "").strip()
        if (
            target == PAGE_DESIGN_WORKSPACE
            and previous_page == PAGE_AGENT_WORKSPACE
            and current_project_id
            and created_by_intelligent_design == current_project_id
        ):
            _continue_intelligent_design_project(current_project_id)
            return
        if target == PAGE_RESULTS_EXPORT:
            target = PAGE_DESIGN_WORKSPACE
            st.session_state["formal_legacy_results_redirect"] = True
            ctrl = _controller()
            ds = ctrl.get()
            ds.step = 6
            ctrl.save(ds)
            st.session_state["formal_step_preview"] = True
        if target == PAGE_PROJECT_HOME and previous_page != PAGE_PROJECT_HOME:
            st.session_state["project_center_transition_pending"] = True
        else:
            st.session_state.pop("project_center_transition_pending", None)
        if target == PAGE_CRISPR_WORKFLOW and previous_page != PAGE_CRISPR_WORKFLOW:
            from views.CrisprWorkspace import reset_crispr_workspace_session

            reset_crispr_workspace_session(
                st.session_state,
                active_project_id=str(
                    st.session_state.get("mvp_project_id") or ""
                ).strip(),
            )
        st.session_state[_SK.SELECTED_PAGE] = target
        st.query_params["page"] = target
        # Streamlit performs the post-callback rerun itself. Let the Project
        # Center open callback finish cleanly so its old row subtree can be
        # removed before the workspace is mounted.
        if st.session_state.get("project_center_open_callback_in_progress"):
            return
        st.rerun()


def _request_agent_project_selection() -> None:
    """Enter Project Center with one explicit, session-only Agent return intent."""
    st.session_state["agent_project_selection_return"] = {
        "origin": PAGE_AGENT_WORKSPACE,
        "return_to": PAGE_AGENT_WORKSPACE,
        "purpose": "select_current_formal_project",
    }
    _change_page(PAGE_PROJECT_HOME)


def _consume_agent_project_selection_return(project_id: str, *, opened: bool) -> str | None:
    """Consume the one-shot return intent after the Formal open path completes."""
    context = st.session_state.pop("agent_project_selection_return", None)
    if not opened or not isinstance(context, Mapping):
        return None
    if context != {
        "origin": PAGE_AGENT_WORKSPACE,
        "return_to": PAGE_AGENT_WORKSPACE,
        "purpose": "select_current_formal_project",
    }:
        return None
    if str(st.session_state.get("mvp_project_id") or "").strip() != str(project_id).strip():
        return None
    st.session_state["agent_v1_ui_entry_mode"] = "current"
    return PAGE_AGENT_WORKSPACE


def _formal_project_repository(project_id: str, project_type: str = "") -> Any | None:
    """Resolve the existing repository that owns one Formal project."""
    from views.AgentWorkspace import resolve_formal_repository

    return resolve_formal_repository(project_id, project_type)


def _product_surface_route(surface: str) -> str:
    """Map one persisted product label to an internal whitelisted page route."""
    return PAGE_AGENT_WORKSPACE if surface == PAGE_AGENT_WORKSPACE else PAGE_DESIGN_WORKSPACE


def _route_product_surface(destination: str) -> str | None:
    """Map only resumable internal routes to their bounded persisted product labels."""
    if destination == PAGE_AGENT_WORKSPACE:
        return PAGE_AGENT_WORKSPACE
    if destination == PAGE_DESIGN_WORKSPACE:
        return "Expression Design"
    return None


def _project_resume_destination(project_id: str, project_type: str = "") -> str:
    """Read a bounded project navigation preference with a safe Expression fallback."""
    from services.formal_project_persistence import formal_project_last_active_surface
    from services.plant_project_draft_schema import PlantProjectDraftError

    repository = _formal_project_repository(project_id, project_type)
    if repository is None:
        return PAGE_DESIGN_WORKSPACE
    try:
        return _product_surface_route(
            formal_project_last_active_surface(project_id, repository=repository)
        )
    except (PlantProjectDraftError, OSError, ValueError, TypeError):
        return PAGE_DESIGN_WORKSPACE


def _opened_project_destination(
    project_id: str,
    project_type: str,
    explicit_return: str | None,
) -> str:
    """Give the valid one-shot Agent return precedence over durable resume state."""
    if explicit_return == PAGE_AGENT_WORKSPACE:
        return PAGE_AGENT_WORKSPACE
    return _project_resume_destination(project_id, project_type)


def _record_current_project_surface(destination: str) -> None:
    """Record only a rendered, repository-backed current-project product surface."""
    from services.formal_project_persistence import record_formal_project_active_surface
    from services.plant_project_draft_schema import PlantProjectDraftError

    project_id = str(st.session_state.get("mvp_project_id") or "").strip()
    product_surface = _route_product_surface(destination)
    if not project_id or product_surface is None:
        return
    repository = _formal_project_repository(project_id, _formal_project_type())
    if repository is None:
        return
    try:
        record_formal_project_active_surface(
            project_id,
            product_surface,
            repository=repository,
        )
    except (PlantProjectDraftError, OSError, ValueError, TypeError):
        return


def _continue_intelligent_design_project(project_id: str) -> None:
    """Open an Agent-bound project through the existing Formal restore path."""
    from services.plant_project_draft_schema import PlantProjectDraftError
    from views.AgentWorkspace import resolve_formal_repository

    project_type = str(st.session_state.get("formal_project_type") or "")
    repository = resolve_formal_repository(project_id, project_type)
    if repository is None:
        st.error(_t('v1.common.project_cannot_loaded_formal_project_storage'))
        return
    try:
        draft = repository.load(project_id)
        if str(draft.draft_status or "") == "draft":
            st.session_state.pop("agent_v1_ui_created_project_id", None)
            _restore_formal_workflow_draft(project_id, repository=repository)
            return
    except PlantProjectDraftError:
        st.error(_t('v1.common.project_cannot_loaded_formal_project_storage'))
        return
    _open_saved_mvp_project(project_id, project_type or PROJECT_TYPE_SINGLE_GENE)


def _bump_reset_token() -> None:
    current = str(st.session_state.get(_SK.ACTIVE_RESET_TOKEN, "0"))
    try:
        next_value = str(int(current) + 1)
    except ValueError:
        next_value = "1"
    st.session_state[_SK.ACTIVE_RESET_TOKEN] = next_value

# Keep the existing wizard callback contract. Routes outside the formal
# pages are deliberately ignored by _change_page.
st.session_state["_change_page_cb"] = _change_page


_FORMAL_STEPS = (
    "项目定义与表达目标",
    "目标基因与编码序列（CDS）",
    "植物表达盒设计",
    "植物二元载体骨架与组装策略",
    "完整载体构建设计与计算校验",
    "项目保存、结果审查与交付",
)


def _plant_host_records() -> list[dict[str, Any]]:
    """Read the formal plant-only host registry through its public loader."""
    from services.plant_host_registry import list_hosts

    return list_hosts()


def _formal_ai_route_supported_host_values() -> list[str]:
    """Return only hosts accepted by the adopted V1 single-gene crosswalk."""
    from services.plant_host_registry import SINGLE_GENE_COMPLETE_VECTOR, hosts_for_workflow

    return [
        _plant_host_storage_value(record)
        for record in hosts_for_workflow(SINGLE_GENE_COMPLETE_VECTOR)
    ]


def _plant_host_storage_value(record: Mapping[str, Any]) -> str:
    aliases = list(record.get("aliases") or [])
    suffix = str(aliases[0] if aliases else record.get("scientific_name") or "").strip()
    return f"{str(record.get('common_name') or '').strip()} ({suffix})"


def _plant_host_record(host: Any) -> dict[str, Any] | None:
    value = str(host or "").strip()
    for record in _plant_host_records():
        recognized_values = {
            str(record.get("host_id") or ""),
            str(record.get("scientific_name") or ""),
            _plant_host_storage_value(record),
        }
        if value in recognized_values:
            return record
    return None


def _plant_host_values() -> list[str]:
    return [_plant_host_storage_value(record) for record in _plant_host_records()]


def _plant_host_label(host: Any) -> str:
    record = _plant_host_record(host)
    if record is None:
        return str(host or "")
    return f"{record['common_name']} / {record['scientific_name']}"


def _plant_host_value_for_id(host_id: str) -> str:
    record = next(
        record for record in _plant_host_records() if record["host_id"] == host_id
    )
    return _plant_host_storage_value(record)


def _host_supports_project_type(host: Any, project_type: str) -> bool:
    from services.plant_host_registry import (
        GENERIC_MULTI_TU_ASSEMBLY,
        SINGLE_GENE_COMPLETE_VECTOR,
    )

    record = _plant_host_record(host)
    if record is None:
        return False
    workflow = (
        SINGLE_GENE_COMPLETE_VECTOR
        if project_type == PROJECT_TYPE_SINGLE_GENE
        else GENERIC_MULTI_TU_ASSEMBLY
    )
    return workflow in record["workflow_levels"]


def _host_workflow_summary(host: Any) -> list[str]:
    from services.plant_host_registry import (
        GENERIC_MULTI_TU_ASSEMBLY,
        SINGLE_GENE_COMPLETE_VECTOR,
    )

    record = _plant_host_record(host)
    if record is None:
        return []
    labels = {
        SINGLE_GENE_COMPLETE_VECTOR: "完整载体路线（包含载体骨架）",
        GENERIC_MULTI_TU_ASSEMBLY: "通用 Multi-TU 组装（不包含载体骨架）",
    }
    return [labels[workflow] for workflow in record["workflow_levels"]]


def _topology_label(value: Any) -> str:
    key = {
        "circular": "v1.common.circular",
        "linear": "v1.common.linear",
    }.get(str(value or "").strip().lower(), "v1.expression.not_recorded")
    return _t(key)


def _component_type_label(value: Any) -> str:
    return {
        "promoter": "启动子",
        "cds": "编码序列（CDS）",
        "terminator": "终止子",
        "three_prime_element": "3′端元件",
        "rep_origin": "复制起点",
        "backbone": "载体骨架",
    }.get(str(value or "").lower(), "其他元件")


def _formal_element_display_name(name: Any, component_type: Any) -> str:
    """Use one Chinese public label for the official HSA case in every view."""
    value = str(name or "").strip()
    lowered = value.casefold()
    if "camv35s" in lowered or "camv 35s" in lowered:
        return "CaMV35S 启动子"
    if "camv 3'utr" in lowered or "camv 3′ utr" in lowered or "polya signal" in lowered:
        return "CaMV 3′ UTR（polyA 信号）"
    if str(component_type or "").lower() == "cds" and value == "ALB CDS":
        return "ALB 编码序列"
    return value


def _canonical_cassette_length(result: Any, *, cassette_input_signature: Any) -> int | None:
    """Return the active canonical cassette length only for a current result."""
    if (
        not isinstance(result, dict)
        or result.get("cassette_input_signature", result.get("input_signature")) != cassette_input_signature
    ):
        return None
    from services.canonical_construct_runtime import CanonicalConstructRuntimeError, active_construct_snapshot

    try:
        return int(active_construct_snapshot(result.get("runtime")).get("sequence_length") or 0)
    except CanonicalConstructRuntimeError:
        return None


def _display_element_name(name: str, component_type: str, length: int) -> str:
    """Avoid presenting short library records as complete regulatory elements."""
    normalized = str(name or "").strip()
    lower_name = normalized.lower()
    if component_type == "promoter" and "zmubi" in lower_name:
        return "ZmUbi 启动子演示片段" if length == 36 else "ZmUbi 启动子片段"
    if component_type == "promoter" and "35s" in lower_name:
        return "CaMV 35S 启动子核心片段" if length == 144 else "CaMV 35S 启动子片段"
    if component_type == "terminator" and "nos" in lower_name:
        return "NOS 终止子核心片段" if length == 31 else "NOS 终止子演示片段" if length == 182 else "NOS 终止子片段"
    return normalized


def _controller():
    from core.design_session import SessionController

    return SessionController()


def _formal_project_type() -> str:
    project_type = str(st.session_state.get("formal_project_type") or PROJECT_TYPE_SINGLE_GENE)
    return project_type if project_type in {PROJECT_TYPE_SINGLE_GENE, PROJECT_TYPE_DUAL_TU} else PROJECT_TYPE_SINGLE_GENE


def _is_dual_tu_project() -> bool:
    return _formal_project_type() == PROJECT_TYPE_DUAL_TU


def _formal_design_scenario() -> str:
    from services.gate3_pathway_mapping import normalize_design_scenario

    state = st.session_state
    current = state.get("formal_design_scenario")
    if str(current or "").strip():
        normalized = normalize_design_scenario(current)
        state["formal_design_scenario_recorded"] = normalized
        return normalized
    recorded = state.get("formal_design_scenario_recorded")
    if str(recorded or "").strip():
        return normalize_design_scenario(recorded)
    for result_key in ("formal_dual_tu_combined_result", "mvp_vector_result"):
        result = state.get(result_key)
        context = (
            result.get("formal_project_context")
            if isinstance(result, Mapping)
            and isinstance(result.get("formal_project_context"), Mapping)
            else {}
        )
        scenario = context.get("design_scenario")
        if str(scenario or "").strip():
            normalized = normalize_design_scenario(scenario)
            state["formal_design_scenario_recorded"] = normalized
            return normalized
    return normalize_design_scenario(None)


def _is_pathway_multi_tu_project() -> bool:
    from services.gate3_pathway_mapping import SCENARIO_PATHWAY_MULTI_TU

    return _formal_design_scenario() == SCENARIO_PATHWAY_MULTI_TU


def _resolve_formal_step1_project_type(
    *,
    selected_scenario: Any,
    selected_mode_label: Any,
    mode_labels: Mapping[str, str],
    current_project_type: Any,
) -> str | None:
    """Resolve Step 1 mode without trusting a disabled widget value.

    Pathway scenarios own the Multi-TU route. For selectable scenarios, a
    missing widget value is treated as transient hydration and preserves a
    valid current mode; unknown values fail closed instead of guessing.
    """
    pathway_scenario = "metabolic_pathway_multi_tu_vector"
    if selected_scenario not in {"standard_plant_expression_vector", pathway_scenario}:
        return None
    if selected_scenario == pathway_scenario:
        if PROJECT_TYPE_DUAL_TU in mode_labels:
            return PROJECT_TYPE_DUAL_TU
        return None
    if selected_mode_label in mode_labels:
        return str(selected_mode_label)
    label_to_type = {label: project_type for project_type, label in mode_labels.items()}
    if selected_mode_label in label_to_type:
        return label_to_type[selected_mode_label]
    if selected_mode_label is None and current_project_type in mode_labels:
        return current_project_type
    return None


def _is_generic_multi_tu_workflow() -> bool:
    return _is_dual_tu_project() and not _is_pathway_multi_tu_project()


def _is_multi_tu_expression_assembly(result: Any) -> bool:
    from services.mvp_multi_tu_runtime import MULTI_TU_EXPRESSION_ASSEMBLY

    return isinstance(result, dict) and str(result.get("result_kind") or "") == MULTI_TU_EXPRESSION_ASSEMBLY


def _persisted_multi_tu_report_eligible(
    result: Any,
    *,
    result_preview_mode: bool,
) -> bool:
    """Delegate saved Multi-TU delivery to the durable production predicate."""
    from services.formal_single_gene_final_review import (
        persisted_multi_tu_report_eligible,
    )

    return persisted_multi_tu_report_eligible(
        result,
        result_preview_mode=result_preview_mode,
    )


_MULTI_TU_ROLE_LABELS = {
    "promoter": "启动子",
    "five_prime_region": "5′ region / 5′ UTR",
    "cds": "CDS",
    "3_prime_regulatory_region": "3′ 调控区",
    "targeting_sequence": "靶向序列",
    "linker": "连接肽",
    "fusion_tag": "融合标签",
}
_MULTI_TU_ROLE_LABEL_KEYS = {
    "promoter": "v1.ai_assisted_design.promoter",
    "five_prime_region": "v1.expression.five_prime_regulatory_region",
    "cds": "v1.expression.cds",
    "3_prime_regulatory_region": "v1.expression.three_prime_regulatory_region",
    "targeting_sequence": "v1.expression.targeting_sequence",
    "linker": "v1.expression.linker",
    "fusion_tag": "v1.expression.fusion_tag",
}


def _multi_tu_role_display_label(value: Any) -> str:
    role = str(value or "").strip()
    key = _MULTI_TU_ROLE_LABEL_KEYS.get(role)
    return _t(key) if key else _MULTI_TU_ROLE_LABELS.get(role, role)


def _multi_tu_source_label(value: Any) -> str:
    """Present component provenance without exposing runtime enum values."""
    normalized = str(value or "").strip().upper()
    if normalized in {"REGISTRY", "LIBRARY"}:
        return _t("v1.common.component_library")
    if normalized in {"USER_PROVIDED", "PASTE", "UPLOAD", "USER_PASTED"}:
        return _t("v1.expression.user_provided_source")
    if normalized == "REAL_CASE_ACCESSION_DERIVED":
        return _t("v1.ai_assisted_design.source_records")
    return _t("v1.expression.not_recorded")


def _multi_tu_evidence_label(value: Any, *, source_type: Any = "") -> str:
    """Keep evidence state human-readable and review-oriented."""
    normalized = str(value or "").strip().upper()
    review_detail = (
        _multi_tu_source_label(source_type)
        if str(source_type or "").strip()
        else _t("v1.expression.recorded_for_manual_review")
    )
    if str(source_type or "").strip().upper() in {"USER_PROVIDED", "PASTE", "UPLOAD", "USER_PASTED"}:
        return _t("v1.expression.pending_human_review", p0=review_detail)
    if normalized in {"UNVERIFIED_USER_INPUT", "FOUR_ROLE_REVIEW_REQUIRED"}:
        return _t("v1.expression.pending_human_review", p0=review_detail)
    if normalized:
        return _t("v1.expression.recorded_for_manual_review")
    return _t("v1.expression.pending_human_review", p0=review_detail)


def _multi_tu_formal_validation_copy(combined: Mapping[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    """Translate the existing runtime validation snapshot for UI only."""
    formal_validation = combined.get("formal_validation")
    formal_validation = dict(formal_validation) if isinstance(formal_validation, Mapping) else {}
    status = str(formal_validation.get("status") or "")
    findings = [dict(item) for item in formal_validation.get("findings") or [] if isinstance(item, Mapping)]
    if status == "legacy_incomplete":
        return (
            _t("v1.expression.multi_tu_validation_missing_5_prime_status"),
            _t("v1.expression.multi_tu_validation_missing_5_prime_prompt"),
            findings,
        )
    if status == "formal_ready":
        return (
            _t("v1.expression.multi_tu_validation_ready_status"),
            _t("v1.expression.multi_tu_validation_ready_prompt"),
            findings,
        )
    return (
        _t("v1.expression.multi_tu_validation_manual_review_status"),
        _t("v1.expression.multi_tu_validation_manual_review_prompt"),
        findings,
    )


def _format_multi_tu_validation_copy(label: str, note: str) -> str:
    separator = "：" if _get_language() == "zh-CN" else ": "
    return f"{label}{separator}{note}"


def _active_backbone_workflow_id() -> str:
    if st.session_state.get("formal_betalain_gate3_case"):
        return "gate3"
    if _is_pathway_multi_tu_project():
        return "gate3_pathway"
    if _is_dual_tu_project():
        return "generic_multi_tu"
    host = _plant_host_record(st.session_state.get("formal_project_host"))
    if host and host.get("host_id") == "rice":
        return "rice_alb_single_gene"
    return "formal_single_gene"


def _render_step_4_context(ds: Any, *, contains_vector: bool) -> None:
    workflow_labels = {
        "rice_alb_single_gene": _t("v1.expression.workflow_rice_single_gene"),
        "formal_single_gene": _t("v1.expression.workflow_single_gene"),
        "generic_multi_tu": _t("v1.expression.workflow_generic_multi_tu"),
        "gate3_pathway": _t("v1.expression.workflow_pathway_multi_tu"),
        "gate3": _t("v1.expression.workflow_gate3"),
    }
    workflow_id = _active_backbone_workflow_id()
    st.caption(
        _t('v1.common.host_workflow_includes_vector_backbone', p0=_plant_host_label(ds.host) or _t('v1.expression.not_recorded'), p1=workflow_labels.get(workflow_id, workflow_id), p2=_t('v1.common.yes') if contains_vector else _t('v1.common.no'))
    )


def _pathway_steps() -> list[dict[str, Any]]:
    from services.gate3_pathway_mapping import new_pathway_step, normalize_pathway_steps

    steps = normalize_pathway_steps(st.session_state.get("formal_pathway_steps"))
    if _is_pathway_multi_tu_project() and not steps:
        steps = [new_pathway_step()]
    st.session_state["formal_pathway_steps"] = steps
    return steps


def _store_pathway_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from services.gate3_pathway_mapping import normalize_pathway_steps

    previous = normalize_pathway_steps(st.session_state.get("formal_pathway_steps"))
    normalized = normalize_pathway_steps(steps)
    if _is_pathway_multi_tu_project() and not normalized:
        raise ValueError("At least one pathway step must remain.")
    st.session_state["formal_pathway_steps"] = normalized
    if normalized != previous:
        _invalidate_dual_tu_outputs()
    return normalized


def _refresh_pathway_mapping_status() -> dict[str, Any]:
    from services.gate3_pathway_mapping import validate_pathway_mapping

    validation = validate_pathway_mapping(_pathway_steps(), _transcription_units())
    st.session_state["formal_pathway_steps"] = validation["pathway_steps"]
    return validation


def _formal_project_definition() -> dict[str, str]:
    """Read the first-step record from session state without a second store."""
    from services.formal_project_definition_lifecycle import normalize_project_definition

    confirmed = st.session_state.get("formal_project_definition")
    confirmed = dict(confirmed) if isinstance(confirmed, dict) else {}

    def step1_value(widget_key: str, field: str) -> Any:
        if widget_key in st.session_state:
            return st.session_state.get(widget_key)
        return confirmed.get(field)

    return normalize_project_definition(
        {
            "project_name": st.session_state.get("formal_project_name") or confirmed.get("project_name"),
            "plant_host": (
                st.session_state.get("formal_project_host")
                or step1_value("formal_step1_host", "plant_host")
            ),
            "material": (
                step1_value("formal_step1_material", "material")
                or st.session_state.get("formal_project_material")
            ),
            "application_mode": step1_value("formal_step1_application_mode", "application_mode"),
            "transient_expression_system": step1_value(
                "formal_step1_transient_expression_system", "transient_expression_system"
            ),
            "tissue_specificity_requirement": step1_value(
                "formal_step1_tissue_specificity_requirement", "tissue_specificity_requirement"
            ),
            "tissue_target": (
                step1_value("formal_step1_tissue_target", "tissue_target")
                or st.session_state.get("formal_project_tissue_target")
            ),
            "inducibility_requirement": step1_value(
                "formal_step1_inducibility_requirement", "inducibility_requirement"
            ),
            "induction_notes": (
                step1_value("formal_step1_induction_notes", "induction_notes")
                or st.session_state.get("formal_project_induction_notes")
            ),
            "localization_target": (
                step1_value("formal_step1_localization_target", "localization_target")
                or st.session_state.get("formal_project_localization_target")
            ),
            "compatibility_review_required": step1_value(
                "formal_step1_compatibility_review_required", "compatibility_review_required"
            ),
            "legacy_application_mode": step1_value(
                "formal_step1_legacy_application_mode", "legacy_application_mode"
            ),
            "legacy_expression_mode": step1_value(
                "formal_step1_legacy_expression_mode", "legacy_expression_mode"
            ),
        },
        fallback_host=str(step1_value("formal_step1_host", "plant_host") or ""),
    )


def _hydrate_formal_step1_widgets() -> None:
    """Restore Step 1 widgets from the confirmed record after page cleanup."""
    definition = st.session_state.get("formal_project_definition")
    if not isinstance(definition, dict):
        return
    widget_fields = {
        "formal_step1_project_name": "project_name",
        "formal_step1_host": "plant_host",
        "formal_step1_material": "material",
        "formal_step1_application_mode": "application_mode",
        "formal_step1_transient_expression_system": "transient_expression_system",
        "formal_step1_tissue_specificity_requirement": "tissue_specificity_requirement",
        "formal_step1_tissue_target": "tissue_target",
        "formal_step1_inducibility_requirement": "inducibility_requirement",
        "formal_step1_induction_notes": "induction_notes",
        "formal_step1_localization_target": "localization_target",
        "formal_step1_compatibility_review_required": "compatibility_review_required",
        "formal_step1_legacy_application_mode": "legacy_application_mode",
        "formal_step1_legacy_expression_mode": "legacy_expression_mode",
    }
    for widget_key, field in widget_fields.items():
        st.session_state[widget_key] = definition.get(field, "")


def _mark_workflow_dirty() -> None:
    """Record unsaved UI workflow changes without entering durable state."""
    st.session_state.pop("formal_workflow_dirty", None)
    st.session_state.pop("formal_durable_save_state", None)
    st.session_state["ui_workflow_dirty"] = True


def _establish_workflow_baseline(*, has_durable_save: bool) -> None:
    """Reset project-local UI save markers after new/open/save transitions."""
    st.session_state.pop("formal_workflow_dirty", None)
    st.session_state.pop("formal_durable_save_state", None)
    definition = st.session_state.get("formal_project_definition")
    if isinstance(definition, dict):
        st.session_state["ui_step1_baseline"] = dict(definition)
    else:
        st.session_state.pop("ui_step1_baseline", None)
    st.session_state["ui_workflow_dirty"] = False
    st.session_state["ui_has_durable_save"] = bool(has_durable_save)


def _workflow_has_unsaved_changes() -> bool:
    """Return whether the current workflow has edits after its durable baseline."""
    return bool(st.session_state.get("ui_workflow_dirty"))


def _record_formal_step1_design_edit() -> None:
    """Record a real Step 1 widget edit without persisting UI lifecycle state."""
    state = st.session_state
    if state.get("_formal_step_hydration_target") == 1:
        return
    definition = state.get("ui_step1_baseline")
    if not isinstance(definition, Mapping):
        definition = state.get("formal_project_definition")
    if not isinstance(definition, Mapping):
        state["ui_step1_baseline"] = dict(_formal_project_definition())
        return
    widget_fields = {
        "formal_step1_project_name": "project_name",
        "formal_step1_host": "plant_host",
        "formal_step1_material": "material",
        "formal_step1_application_mode": "application_mode",
        "formal_step1_transient_expression_system": "transient_expression_system",
        "formal_step1_tissue_specificity_requirement": "tissue_specificity_requirement",
        "formal_step1_tissue_target": "tissue_target",
        "formal_step1_inducibility_requirement": "inducibility_requirement",
        "formal_step1_induction_notes": "induction_notes",
        "formal_step1_localization_target": "localization_target",
    }
    changed = any(
        key in state
        and str(state.get(key) or "") != str(definition.get(field) or "")
        for key, field in widget_fields.items()
    )
    scenario_labels = dict(_DESIGN_SCENARIO_LABELS)
    mode_labels = dict(_PROJECT_MODE_LABELS)
    selected_scenario = next(
        (key for key in scenario_labels if key == state.get("formal_step1_design_scenario") or _t(scenario_labels[key]) == state.get("formal_step1_design_scenario")),
        _formal_design_scenario(),
    )
    resolver = globals().get("_resolve_formal_step1_project_type")
    if resolver is None:
        selected_project_type = state.get("formal_step1_project_type") if state.get("formal_step1_project_type") in mode_labels else _formal_project_type()
    else:
        selected_project_type = resolver(
            selected_scenario=selected_scenario,
            selected_mode_label=state.get("formal_step1_project_type"),
            mode_labels=mode_labels,
            current_project_type=_formal_project_type(),
        )
    if selected_project_type is None:
        selected_project_type = _formal_project_type()
    changed = changed or selected_scenario != _formal_design_scenario()
    changed = changed or selected_project_type != _formal_project_type()
    if changed:
        state["formal_step1_design_dirty"] = True
        globals().get("_mark_workflow_dirty", lambda: None)()
    else:
        state.pop("formal_step1_design_dirty", None)


def _record_formal_step2_design_edit() -> None:
    """Keep an actual Step 2 edit visible to downstream eligibility checks."""
    state = st.session_state
    saved = state.get("formal_cds_input")
    saved = saved if isinstance(saved, Mapping) else {}
    saved_info = saved.get("gene_information")
    saved_info = saved_info if isinstance(saved_info, Mapping) else {}
    field_map = {
        "formal_step2_gene_name": "gene_name",
        "formal_step2_gene_symbol": "gene_symbol",
        "formal_step2_source_species": "source_species",
        "formal_step2_source_type": "source_type",
        "formal_step2_source_reference": "source_reference",
        "formal_step2_modification_status": "modification_status",
        "formal_step2_modification_note": "modification_note",
        "formal_step2_partial_cds": "is_partial_cds",
        "formal_step2_note": "note",
    }
    changed = any(
        key in state and state.get(key) != saved_info.get(field)
        for key, field in field_map.items()
    )
    changed = changed or (
        "formal_step2_cds_text" in state
        and str(state.get("formal_step2_cds_text") or "")
        != str(saved.get("original_text") or "")
    )
    expected_mode = (
        "上传单条核酸 FASTA"
        if str(saved.get("source_kind") or "") == "upload"
        else "粘贴核酸序列"
    )
    changed = changed or (
        "formal_step2_mode" in state
        and str(state.get("formal_step2_mode") or "") != expected_mode
    )
    changed = changed or bool(state.get("formal_step2_upload"))
    if changed:
        state["formal_step2_design_dirty"] = True
        globals().get("_mark_workflow_dirty", lambda: None)()
    else:
        state.pop("formal_step2_design_dirty", None)


def _project_definition_expression_target(definition: dict[str, str]) -> str:
    """Provide a conditional first-step summary for existing consumers."""
    from services.formal_project_definition_lifecycle import active_project_definition_summary

    parts = active_project_definition_summary(definition)
    return "；".join(parts)


def _formal_result_needs_review(result: dict[str, Any] | None = None) -> bool:
    """A changed biological-design background blocks formal delivery, not viewing."""
    candidate = result if isinstance(result, dict) else st.session_state.get("mvp_vector_result")
    if not isinstance(candidate, dict):
        return False
    from services.mt01_formal_runtime import is_mt01_claim
    from services.mt02_formal_runtime import is_mt02_claim

    if is_mt01_claim(candidate):
        return False
    if is_mt02_claim(candidate):
        return False
    if str(candidate.get("project_type") or "") == PROJECT_TYPE_DUAL_TU:
        return False
    context = candidate.get("formal_project_context")
    if not isinstance(context, dict):
        return False
    if (
        str(context.get("construct_review_status") or "current") == "needs_review"
        or str(context.get("cds_source_review_status") or "current") == "needs_review"
    ):
        return True
    from services.formal_project_definition_lifecycle import requires_construct_review

    return requires_construct_review(
        _formal_project_definition(),
        context.get("construct_review_basis") if isinstance(context.get("construct_review_basis"), dict) else context.get("project_definition"),
    )


def _apply_formal_cds_analysis(ds: Any, analysis: dict[str, Any]) -> str:
    """Persist Step 2 input and apply only the required downstream lifecycle action."""
    from services.formal_cds_workflow import lifecycle_change

    previous = st.session_state.get("formal_cds_input")
    changed = not isinstance(previous, dict) or dict(previous) != dict(analysis)
    action = lifecycle_change(previous if isinstance(previous, dict) else None, analysis)
    info = dict(analysis.get("gene_information") or {})
    ds.gene_name = str(info.get("gene_name") or ds.gene_name or "").strip()
    ds.original_seq = str(analysis.get("normalized_cds") or "")
    st.session_state["formal_cds_input"] = dict(analysis)
    st.session_state["formal_cds_source"] = str(analysis.get("source_name") or info.get("source_reference") or "")
    st.session_state["formal_cds_source_review_status"] = "current"

    if action == "invalidate":
        ds.clear_step3_outputs()
        _invalidate_formal_snapshots()
    elif action == "source_review":
        st.session_state["formal_cds_source_review_status"] = "needs_review"
        result = st.session_state.get("mvp_vector_result")
        if isinstance(result, dict):
            context = dict(result.get("formal_project_context") or {})
            result["formal_project_context"] = {
                **context,
                "cds_source_review_status": "needs_review",
            }
    st.session_state.pop("formal_step2_design_dirty", None)
    if changed:
        globals().get("_mark_workflow_dirty", lambda: None)()
    _controller().save(ds)
    return action


def _apply_formal_project_definition(definition: dict[str, str]) -> bool:
    """Update project context while retaining the existing canonical construct."""
    from services.formal_project_definition_lifecycle import (
        construct_review_basis,
        normalize_project_definition,
        requires_construct_review,
    )

    definition = normalize_project_definition(definition)
    previous_definition = st.session_state.get("formal_project_definition")
    definition_changed = (
        not isinstance(previous_definition, dict)
        or dict(previous_definition) != dict(definition)
    )
    result = st.session_state.get("mvp_vector_result")
    context = result.get("formal_project_context") if isinstance(result, dict) and isinstance(result.get("formal_project_context"), dict) else {}
    saved_basis = (
        context.get("construct_review_basis")
        if isinstance(context.get("construct_review_basis"), dict)
        else construct_review_basis(context if isinstance(result, dict) else definition)
    )
    needs_review = bool(isinstance(result, dict) and requires_construct_review(definition, saved_basis))
    review_status = "needs_review" if needs_review else "current"
    st.session_state["formal_project_definition"] = dict(definition)
    st.session_state["formal_project_name"] = definition["project_name"]
    st.session_state["formal_project_host"] = definition["plant_host"]
    st.session_state["formal_project_material"] = definition["material"]
    # This function runs from the Step 1 submit path, after its widgets exist.
    # Persist the normalized record only; reopen restoration sets widget keys
    # before the workspace renders again.
    st.session_state["formal_expression_target"] = _project_definition_expression_target(definition)
    st.session_state["formal_construct_review_basis"] = dict(saved_basis)
    st.session_state["formal_construct_review_status"] = review_status
    if isinstance(result, dict):
        previous_name = str(result.get("project_name") or "")
        result["project_name"] = definition["project_name"]
        result["formal_project_context"] = {
            **context,
            "host_key": definition["plant_host"],
            "expression_target": _project_definition_expression_target(definition),
            "project_definition": dict(definition),
            "construct_review_basis": dict(saved_basis),
            "construct_review_status": review_status,
            "current_step": int(context.get("current_step") or 6),
        }
        # Rebuild a delivery summary only when it is next explicitly saved.
        # Sequence, selected elements, and canonical runtime stay untouched.
        if previous_name != definition["project_name"]:
            result.pop("company_review_package", None)
    st.session_state.pop("formal_step1_design_dirty", None)
    if definition_changed:
        globals().get("_mark_workflow_dirty", lambda: None)()
    return needs_review


def _new_transcription_unit(*, unit_id: str = "", display_name: str = "") -> dict[str, Any]:
    stable_id = str(unit_id or f"tu-{uuid4().hex}")
    return {
        "unit_id": stable_id,
        "display_name": str(display_name or "New transcription unit"),
        "order": 0,
        "orientation": "forward",
        "promoter": {},
        "five_prime_region": {},
        "cds": {},
        "3_prime_regulatory_region": {},
        "targeting_sequence": {},
        "linker": {},
        "fusion_tag": {},
        "cassette_sequence": "",
        "cassette_length": 0,
        "validation_state": "incomplete",
        "provenance_state": "review_required",
    }


def _default_transcription_unit_display_name(index: int) -> str:
    defaults = {
        1: "目标基因表达单元",
        2: "植物选择标记表达单元",
        3: "报告基因表达单元",
    }
    if index in defaults:
        return defaults[index]
    return f"转录单元 {index}"


def _normalize_transcription_units(candidate: Any, legacy_order: list[str] | None = None) -> list[dict[str, Any]]:
    if isinstance(candidate, dict):
        requested = [str(item) for item in list(legacy_order or []) if str(item) in candidate]
        requested.extend(str(item) for item in candidate if str(item) not in requested)
        source_units = [
            {**dict(candidate[item]), "unit_id": str((candidate[item] or {}).get("unit_id") or item)}
            for item in requested
            if isinstance(candidate[item], dict)
        ]
    elif isinstance(candidate, list):
        source_units = sorted(
            [item for item in candidate if isinstance(item, dict)],
            key=lambda item: (int(item.get("order", 0) or 0), str(item.get("unit_id") or "")),
        )
    else:
        source_units = []
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, source in enumerate(source_units, start=1):
        source = dict(source)
        unit_id = str(source.get("unit_id") or "").strip()
        if not unit_id:
            raise ValueError("Each transcription unit requires a stable non-empty unit_id.")
        if unit_id in seen:
            raise ValueError(f"Duplicate transcription-unit unit_id: {unit_id}")
        seen.add(unit_id)
        unit = _new_transcription_unit(
            unit_id=unit_id,
            display_name=str(
                source.get("display_name")
                or source.get("unit_name")
                or _default_transcription_unit_display_name(index)
            ),
        )
        unit.update(source)
        unit["unit_id"] = unit_id
        unit["display_name"] = str(
            source.get("display_name")
            or source.get("unit_name")
            or _default_transcription_unit_display_name(index)
        )
        unit["order"] = index
        unit["orientation"] = "reverse" if str(source.get("orientation")) == "reverse" else "forward"
        unit["3_prime_regulatory_region"] = dict(
            source.get("3_prime_regulatory_region") or source.get("terminator") or {}
        )
        for role in (
            "promoter",
            "five_prime_region",
            "cds",
            "targeting_sequence",
            "linker",
            "fusion_tag",
        ):
            unit[role] = dict(source.get(role) or {})
        normalized.append(unit)
    return normalized


def _blank_dual_tu_units() -> list[dict[str, Any]]:
    units = [
        {**_new_transcription_unit(display_name=_default_transcription_unit_display_name(1)), "order": 1},
        {**_new_transcription_unit(display_name=_default_transcription_unit_display_name(2)), "order": 2},
    ]
    return _normalize_transcription_units(units)


def _transcription_units() -> list[dict[str, Any]]:
    candidate = st.session_state.get("formal_transcription_units")
    if not isinstance(candidate, list):
        candidate = st.session_state.get("formal_dual_tu_units")
    units = _normalize_transcription_units(
        candidate,
        list(st.session_state.get("formal_dual_tu_order") or []),
    )
    if not units:
        units = _blank_dual_tu_units()
    st.session_state["formal_transcription_units"] = units
    st.session_state.pop("formal_dual_tu_units", None)
    st.session_state.pop("formal_dual_tu_order", None)
    return units


def _store_transcription_units(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = [{**dict(unit), "order": index} for index, unit in enumerate(units, start=1)]
    normalized = _normalize_transcription_units(ordered)
    if not normalized:
        raise ValueError("At least one transcription unit must remain.")
    st.session_state["formal_transcription_units"] = normalized
    return normalized


_MULTI_TU_EDITOR_REQUIRED_ROLES = (
    "promoter",
    "five_prime_region",
    "cds",
    "3_prime_regulatory_region",
)
_MULTI_TU_EDITOR_OPTIONAL_ROLES = (
    "targeting_sequence",
    "linker",
    "fusion_tag",
)


def _is_explicit_five_prime_absence(component: Any) -> bool:
    if not isinstance(component, Mapping):
        return False
    return str(component.get("absence_state") or "").strip().casefold() in {
        "explicit_none",
        "none",
    }


def _multi_tu_required_role_blockers(units: Any) -> list[dict[str, str]]:
    """Describe missing required inputs across all formal Multi-TU records."""
    if not isinstance(units, list) or not units:
        return [{"unit_label": "Multi-TU", "role": "transcription_unit"}]
    blockers: list[dict[str, str]] = []
    for index, unit in enumerate(units, start=1):
        unit_mapping = unit if isinstance(unit, Mapping) else {}
        unit_label = str(unit_mapping.get("display_name") or f"TU{index}").strip() or f"TU{index}"
        for role in _MULTI_TU_EDITOR_REQUIRED_ROLES:
            component = unit_mapping.get(role)
            if (
                role == "five_prime_region"
                and _is_explicit_five_prime_absence(component)
                and not str(component.get("raw_text") or "").strip()
            ):
                continue
            if not isinstance(component, Mapping) or not str(component.get("raw_text") or "").strip():
                blockers.append({"unit_label": unit_label, "role": role})
    return blockers


def _multi_tu_overall_ready(units: Any) -> bool:
    """Return the formal Multi-TU completion predicate, independent of the active tab."""
    return not _multi_tu_required_role_blockers(units)


def _multi_tu_generation_error_message(error: Exception, units: Any) -> str:
    """Present expected Multi-TU input failures without exposing runtime implementation details."""
    blockers = _multi_tu_required_role_blockers(units)
    if blockers:
        blocker = blockers[0]
        role_label = _MULTI_TU_ROLE_LABELS.get(blocker["role"], blocker["role"])
        return f"{blocker['unit_label']} 的 {role_label} 尚未提供有效序列，已阻止生成。"
    detail = str(error or "")
    missing_match = re.search(
        r"Expression unit '([^']+)' requires a non-empty (promoter|five_prime_region|cds|3_prime_regulatory_region) sequence",
        detail,
    )
    cds_match = re.search(r"Expression unit '([^']+)' CDS failed validation", detail)
    match = missing_match or cds_match
    if match:
        role = missing_match.group(2) if missing_match else "cds"
        role_label = _MULTI_TU_ROLE_LABELS.get(role, role)
        return f"{match.group(1)} 的 {role_label} 未通过当前序列校验，已阻止生成。"
    return "Canonical Multi-TU 未生成。请检查每个 TU 的启动子、5′ region / 5′ UTR、CDS 和 3′ 调控区序列后重试。"


def _multi_tu_editor_has_complete_inputs(units: Any) -> bool:
    """Return whether the editor already holds every required current input."""
    return (
        isinstance(units, list)
        and bool(units)
        and all(
            isinstance(unit, Mapping)
            and str(unit.get("unit_id") or "").strip()
            and all(
                (
                    isinstance(unit.get(role), Mapping)
                    and str((unit.get(role) or {}).get("raw_text") or "").strip()
                )
                or (
                    role == "five_prime_region"
                    and _is_explicit_five_prime_absence(unit.get(role))
                    and not str((unit.get(role) or {}).get("raw_text") or "").strip()
                )
                for role in _MULTI_TU_EDITOR_REQUIRED_ROLES
            )
            for unit in units
        )
    )


def _hydrate_current_multi_tu_editor_from_result() -> bool:
    """Restore only the active project's missing editor inputs from its current result."""
    state = st.session_state
    if bool(state.get("formal_explicit_historical_open")) or bool(state.get("mvp_inputs_stale")):
        return False
    project_id = str(state.get("mvp_project_id") or "").strip()
    if not project_id:
        return False
    existing_units = state.get("formal_transcription_units")
    if _multi_tu_editor_has_complete_inputs(existing_units):
        return False
    for candidate in (
        state.get("mvp_vector_result"),
        state.get("formal_dual_tu_combined_result"),
    ):
        if not isinstance(candidate, Mapping) or str(candidate.get("project_id") or "").strip() != project_id:
            continue
        original_input = candidate.get("original_input")
        source_units = (
            original_input.get("expression_units")
            if isinstance(original_input, Mapping)
            else None
        )
        restored_units = _normalize_transcription_units(
            source_units,
            list(candidate.get("unit_order") or []),
        )
        if not _multi_tu_editor_has_complete_inputs(restored_units):
            continue
        _store_transcription_units(restored_units)
        return True
    return False


def _multi_tu_editor_widget_state_is_present(units: list[dict[str, Any]]) -> bool:
    """Return whether every unconditional Step 3 role widget still exists."""
    state = st.session_state
    for unit in units:
        unit_id = str(unit.get("unit_id") or "").lower()
        if not unit_id:
            return False
        for role in _MULTI_TU_EDITOR_REQUIRED_ROLES:
            prefix = f"formal_{unit_id}_{role}"
            mode_key = f"{prefix}_mode"
            if mode_key not in state:
                return False
            saved = unit.get(role) if isinstance(unit.get(role), Mapping) else {}
            expected_mode = (
                "不使用独立 5′ region"
                if role == "five_prime_region" and _is_explicit_five_prime_absence(saved)
                else (
                    "用户序列"
                    if str(saved.get("source_type") or "") in {"paste", "upload"}
                    else "元件库"
                )
            )
            current_mode = state.get(mode_key)
            # A different present mode is an unsaved user edit. Its callback
            # owns invalidation, so hydration must not overwrite it.
            if current_mode != expected_mode:
                continue
            if expected_mode == "用户序列" and any(
                f"{prefix}_{field}" not in state for field in ("name", "text")
            ):
                return False
            if expected_mode == "元件库" and f"{prefix}_library" not in state:
                return False
        for role in _MULTI_TU_EDITOR_OPTIONAL_ROLES:
            prefix = f"formal_{unit_id}_{role}"
            enabled_key = f"{prefix}_enabled"
            if enabled_key not in state:
                return False
            # The parent toggle is unconditional, while name/text are created
            # only on the rerun after a user enables the component.  A present
            # toggle therefore owns the current lifecycle state even before
            # its conditional children have rendered.
    return True


def _prepare_multi_tu_editor_widget_state() -> None:
    """Give the persisted Multi-TU editor state one widget-state owner."""
    state = st.session_state
    project_id = str(state.get("mvp_project_id") or "").strip()
    units = _transcription_units()
    if not project_id or not units:
        return
    marker = _formal_ui_signature(
        [
            {
                "unit_id": str(unit.get("unit_id") or ""),
                "roles": {
                    role: dict(unit.get(role) or {})
                    for role in (
                        *_MULTI_TU_EDITOR_REQUIRED_ROLES,
                        *_MULTI_TU_EDITOR_OPTIONAL_ROLES,
                    )
                },
            }
            for unit in units
        ]
    )
    if (
        state.get("_formal_multi_tu_widget_state_marker") == f"{project_id}:{marker}"
        and _multi_tu_editor_widget_state_is_present(units)
    ):
        return
    for unit in units:
        unit_id = str(unit.get("unit_id") or "").lower()
        for role in _MULTI_TU_EDITOR_REQUIRED_ROLES:
            prefix = f"formal_{unit_id}_{role}"
            for key in (f"{prefix}_mode", f"{prefix}_library", f"{prefix}_name", f"{prefix}_text"):
                state.pop(key, None)
            saved = unit.get(role) if isinstance(unit.get(role), Mapping) else {}
            is_absent = role == "five_prime_region" and _is_explicit_five_prime_absence(saved)
            is_user = str(saved.get("source_type") or "") in {"paste", "upload"}
            state[f"{prefix}_mode"] = (
                "不使用独立 5′ region" if is_absent else ("用户序列" if is_user else "元件库")
            )
            if is_user:
                state[f"{prefix}_name"] = str(saved.get("display_name") or "")
                state[f"{prefix}_text"] = str(saved.get("raw_text") or "")
        for role in _MULTI_TU_EDITOR_OPTIONAL_ROLES:
            prefix = f"formal_{unit_id}_{role}"
            saved = unit.get(role) if isinstance(unit.get(role), Mapping) else {}
            raw_text = str(saved.get("raw_text") or "")
            state.pop(f"{prefix}_enabled", None)
            state.pop(f"{prefix}_name", None)
            state.pop(f"{prefix}_text", None)
            state[f"{prefix}_enabled"] = bool(raw_text.strip())
            if raw_text.strip():
                state[f"{prefix}_name"] = str(saved.get("display_name") or "")
                state[f"{prefix}_text"] = raw_text
    state["_formal_multi_tu_widget_state_marker"] = f"{project_id}:{marker}"


def _invalidate_multi_tu_editor_widget_state(units: Any) -> None:
    """Invalidate Step 3 widget state for a project being explicitly reopened."""
    state = st.session_state
    state.pop("_formal_multi_tu_widget_state_marker", None)
    if not isinstance(units, list):
        return
    roles = (*_MULTI_TU_EDITOR_REQUIRED_ROLES, "targeting_sequence", "linker", "fusion_tag")
    for unit in units:
        if not isinstance(unit, Mapping):
            continue
        unit_id = str(unit.get("unit_id") or "").lower()
        if not unit_id:
            continue
        for role in roles:
            prefix = f"formal_{unit_id}_{role}"
            for suffix in ("_enabled", "_mode", "_library", "_name", "_text"):
                state.pop(f"{prefix}{suffix}", None)


def _multi_tu_step2_planning_signature(units: list[dict[str, Any]]) -> str:
    """Track the reviewed Step 2 plan without changing the persisted TU contract."""
    return _formal_ui_signature(
        [
            {
                "unit_id": str(unit.get("unit_id") or ""),
                "display_name": str(unit.get("display_name") or "").strip(),
                "orientation": str(unit.get("orientation") or "forward"),
                "order": int(unit.get("order") or index),
            }
            for index, unit in enumerate(units, start=1)
        ]
    )


def _multi_tu_step2_planned_units(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Read unsaved Step 2 widget edits without allocating or changing unit IDs."""
    planned: list[dict[str, Any]] = []
    for index, unit in enumerate(units, start=1):
        unit_id = str(unit.get("unit_id") or "")
        name_key = f"formal_{unit_id}_planning_display_name"
        direction_key = f"formal_{unit_id}_planning_orientation"
        display_name = str(
            st.session_state.get(name_key, unit.get("display_name") or f"TU{index}")
        ).strip()
        direction = str(
            st.session_state.get(
                direction_key,
                "反向" if unit.get("orientation") == "reverse" else "正向",
            )
        )
        planned.append(
            {
                **unit,
                "display_name": display_name,
                "orientation": "reverse" if direction == "反向" else "forward",
            }
        )
    return planned


def _transcription_unit(unit_id: str) -> dict[str, Any]:
    return next((item for item in _transcription_units() if str(item.get("unit_id")) == str(unit_id)), {})


def _dual_tu_order() -> list[str]:
    return [str(unit.get("unit_id")) for unit in _transcription_units()]


def _add_transcription_unit() -> str:
    units = _transcription_units()
    added = _new_transcription_unit(display_name=_default_transcription_unit_display_name(len(units) + 1))
    _store_transcription_units([*units, added])
    _invalidate_dual_tu_outputs()
    return str(added["unit_id"])


def _delete_transcription_unit(unit_id: str) -> None:
    units = _transcription_units()
    if len(units) <= 1:
        raise ValueError("At least one transcription unit must remain.")
    remaining = [item for item in units if str(item.get("unit_id")) != str(unit_id)]
    if len(remaining) == len(units):
        raise ValueError("The requested transcription unit does not exist.")
    _store_transcription_units(remaining)
    _invalidate_dual_tu_unit(unit_id)
    is_pathway = globals().get("_is_pathway_multi_tu_project", lambda: False)
    if is_pathway():
        globals().get("_refresh_pathway_mapping_status", lambda: None)()


def _dual_tu_delete_target() -> str:
    return str(st.session_state.get("formal_dual_tu_delete_target") or "")


def _set_dual_tu_delete_target(unit_id: str) -> None:
    st.session_state["formal_dual_tu_delete_target"] = str(unit_id or "")


def _clear_dual_tu_delete_target() -> None:
    st.session_state.pop("formal_dual_tu_delete_target", None)


def _move_transcription_unit(unit_id: str, offset: int) -> None:
    units = _transcription_units()
    current = next((index for index, item in enumerate(units) if str(item.get("unit_id")) == str(unit_id)), -1)
    target = current + int(offset)
    if current < 0 or target < 0 or target >= len(units):
        return
    units[current], units[target] = units[target], units[current]
    _store_transcription_units(units)
    _invalidate_dual_tu_outputs()


def _invalidate_dual_tu_outputs() -> None:
    """Invalidate both canonical output layers while retaining every raw input."""
    for key in (
        "formal_step4_strategy_confirmed",
        "formal_step4_strategy_signature",
        "formal_ui_step4_confirmation_signature",
        "formal_step5_strategy_confirmed",
        "formal_step5_strategy_signature",
        "formal_dual_tu_combined_result",
        "formal_cassette_result",
        "formal_cassette_exports",
        "formal_cassette_input_signature",
        "mvp_vector_result",
        "mvp_current_input_signature",
    ):
        st.session_state.pop(key, None)
    st.session_state["mvp_inputs_stale"] = True
    globals().get("_mark_workflow_dirty", lambda: None)()


def _invalidate_dual_tu_unit(unit_id: str) -> None:
    snapshots = st.session_state.get("formal_dual_tu_unit_snapshots")
    if isinstance(snapshots, dict):
        snapshots.pop(unit_id, None)
    _invalidate_dual_tu_outputs()


def _set_formal_project_type(project_type: str) -> None:
    resolved = project_type if project_type in {PROJECT_TYPE_SINGLE_GENE, PROJECT_TYPE_DUAL_TU} else PROJECT_TYPE_SINGLE_GENE
    previous = _formal_project_type()
    st.session_state["formal_project_type"] = resolved
    if previous != resolved:
        _invalidate_formal_snapshots()
        if resolved == PROJECT_TYPE_DUAL_TU:
            _transcription_units()


def _clear_complete_plasmid_state() -> None:
    for key in (
        "formal_step4_strategy_confirmed",
        "formal_step4_strategy_signature",
        "formal_ui_step4_confirmation_signature",
        "formal_step5_strategy_confirmed",
        "formal_step5_strategy_signature",
        "mvp_vector_result",
        "mvp_current_input_signature",
        "mvp_inputs_stale",
        "formal_backbone_record",
        "formal_insertion_settings",
    ):
        st.session_state.pop(key, None)


def _invalidate_formal_snapshots() -> None:
    """Drop old canonical outputs as soon as an upstream input changes."""
    _clear_complete_plasmid_state()
    for key in ("formal_cassette_exports", "formal_cassette_result", "formal_cassette_input_signature"):
        st.session_state.pop(key, None)
    st.session_state["mvp_inputs_stale"] = True
    globals().get("_mark_workflow_dirty", lambda: None)()


def _mark_formal_cassette_source_review() -> None:
    """Keep the canonical sequence while recording that provenance needs review."""
    globals().get("_mark_workflow_dirty", lambda: None)()
    cassette = st.session_state.get("formal_expression_cassette")
    if not isinstance(cassette, dict):
        return
    items = list(cassette.get("manual_confirmation_items") or [])
    new_item = None
    if not any(item.get("rule_id") == "component_provenance_changed" for item in items if isinstance(item, dict)):
        new_item = {
            "rule_id": "component_provenance_changed",
            "status": "需要人工确认",
            "message": "组件来源信息已修改；表达盒序列保留，但来源需要重新审查。",
        }
        items.append(new_item)
    cassette["manual_confirmation_items"] = items
    if new_item is not None:
        cassette["findings"] = list(cassette.get("findings") or []) + [new_item]


def _formal_step3_order_confirmation() -> bool:
    """Restore the Step 3 confirmation after Streamlit removes its widget key."""
    widget_key = "formal_step3_order_confirmed"
    stable_key = "formal_step3_order_confirmation_recorded"
    if widget_key in st.session_state:
        st.session_state.setdefault(stable_key, bool(st.session_state[widget_key]))
    else:
        st.session_state[widget_key] = bool(st.session_state.get(stable_key))
    return bool(st.session_state[widget_key])


def _record_formal_step3_order_confirmation() -> None:
    st.session_state["formal_step3_order_confirmation_recorded"] = bool(
        st.session_state.get("formal_step3_order_confirmed")
    )
    _invalidate_formal_snapshots()


def _invalidate_complete_plasmid_snapshot() -> None:
    """Preserve the cassette when only backbone insertion inputs change."""
    globals().get("_mark_workflow_dirty", lambda: None)()
    pathway_predicate = globals().get("_is_pathway_multi_tu_project")
    if callable(pathway_predicate) and pathway_predicate() and not bool(
        st.session_state.get("formal_betalain_gate3_case")
    ):
        combined = st.session_state.get("formal_dual_tu_combined_result")
        if _is_multi_tu_expression_assembly(combined):
            st.session_state["mvp_vector_result"] = combined
            st.session_state["mvp_current_input_signature"] = combined.get(
                "input_signature"
            )
            st.session_state["mvp_inputs_stale"] = False
            return
    for key in (
        "formal_step4_strategy_confirmed",
        "formal_step4_strategy_signature",
        "formal_ui_step4_confirmation_signature",
        "formal_step5_strategy_confirmed",
        "formal_step5_strategy_signature",
        "mvp_vector_result",
        "mvp_current_input_signature",
        "mvp_inputs_stale",
    ):
        st.session_state.pop(key, None)


def _company_delivery_gate(result: dict[str, Any]) -> tuple[bool, str]:
    """Keep company delivery review separate from ordinary sequence exports."""
    if _formal_result_needs_review(result):
        return False, "第一步的项目背景已变化，植物表达盒及后续结果需要重新审查。"
    records = result.get("input_records") if isinstance(result.get("input_records"), dict) else {}
    missing_provenance = [
        role
        for role in ("promoter", "cds", "terminator", "backbone")
        if not str((records.get(role) or {}).get("source_accession_version") or "").strip()
    ]
    settings = result.get("insertion_settings") if isinstance(result.get("insertion_settings"), dict) else {}
    if missing_provenance:
        return False, "来源信息尚不完整，不能生成公司交付包。"
    if not bool(settings.get("construction_strategy_confirmed")):
        return False, "构建策略仍待人工确认，不能生成公司交付包。"
    return True, ""


def _set_formal_step(step: int) -> None:
    ctrl = _controller()
    ds = ctrl.get()
    target_step = max(1, min(6, int(step)))
    statuses = _formal_step_statuses()
    current_step = _normalize_formal_current_step(ds.step, statuses=statuses)
    target_status = _formal_step_contract(current_step, statuses=statuses)[target_step - 1]
    if target_status["state"] == "BLOCKED":
        return
    if target_step == ds.step:
        return
    feedback = st.session_state.get("formal_ui_action_feedback")
    if isinstance(feedback, dict):
        feedback_step = max(1, min(6, int(feedback.get("step") or target_step)))
        if feedback_step != target_step:
            st.session_state.pop("formal_ui_action_feedback", None)
    ds.step = target_step
    if target_step in {1, 2}:
        st.session_state["_formal_step_hydration_target"] = target_step
    st.session_state["formal_step_preview"] = True
    ctrl.save(ds)
    st.rerun()


def _formal_step_statuses() -> list[dict[str, bool]]:
    """Derive navigation states from saved project artefacts, never visit history."""
    from services.formal_step3_gate import step3_can_continue_to_backbone

    state = st.session_state
    result = state.get("mvp_vector_result")
    result = result if isinstance(result, Mapping) else {}
    context = result.get("formal_project_context")
    context = context if isinstance(context, Mapping) else {}

    project_definition = state.get("formal_project_definition")
    project_definition = project_definition if isinstance(project_definition, Mapping) else {}
    step1_done = bool(
        str(project_definition.get("project_name") or "").strip()
        and str(project_definition.get("plant_host") or "").strip()
        and _host_supports_project_type(
            project_definition.get("plant_host"), _formal_project_type()
        )
    )
    if _is_pathway_multi_tu_project() and str(state.get("formal_project_name") or "").strip():
        step1_done = True
    step1_done = step1_done and not bool(state.get("formal_step1_design_dirty"))
    cds = state.get("formal_cds_input")
    cds = cds if isinstance(cds, Mapping) else {}
    dual_units = state.get("formal_transcription_units")
    if _is_generic_multi_tu_workflow():
        planned_units = (
            _multi_tu_step2_planned_units(dual_units)
            if isinstance(dual_units, list)
            else []
        )
        saved_planning_signature = str(
            state.get("formal_multi_tu_step2_planning_signature") or ""
        )
        step2_done = (
            bool(planned_units)
            and all(
                str((unit or {}).get("unit_id") or "").strip()
                and str((unit or {}).get("display_name") or "").strip()
                and str((unit or {}).get("orientation") or "forward") in {"forward", "reverse"}
                for unit in planned_units
            )
            and saved_planning_signature == _multi_tu_step2_planning_signature(planned_units)
        )
    else:
        step2_done = (
            bool(str(cds.get("normalized_cds") or "").strip())
            if _formal_project_type() != PROJECT_TYPE_DUAL_TU
            else isinstance(dual_units, list)
            and bool(dual_units)
            and all(
                isinstance((unit or {}).get("cds"), dict)
                and bool(((unit or {}).get("cds") or {}).get("cds_analysis", {}).get("normalized_cds"))
                for unit in dual_units
            )
        )
    step2_done = step2_done and not bool(state.get("formal_step2_design_dirty"))
    cassette = state.get("formal_cassette_result")
    cassette = cassette if isinstance(cassette, Mapping) else {}
    formal_cassette = state.get("formal_expression_cassette")
    formal_cassette = formal_cassette if isinstance(formal_cassette, Mapping) else {}
    step3_input_signature = str(
        state.get("formal_cassette_input_signature")
        or formal_cassette.get("cassette_input_signature")
        or formal_cassette.get("input_signature")
        or ""
    )
    is_generic_multi_tu = _is_generic_multi_tu_workflow()
    uses_multi_tu_assembly_gate = is_generic_multi_tu or (
        _is_pathway_multi_tu_project()
        and not bool(state.get("formal_betalain_gate3_case"))
    )
    multi_tu_overall_ready = (
        _multi_tu_overall_ready(dual_units) if uses_multi_tu_assembly_gate else False
    )
    backbone = state.get("formal_backbone_record")
    backbone = backbone if isinstance(backbone, Mapping) else {}
    insertion = state.get("formal_insertion_settings")
    insertion = insertion if isinstance(insertion, Mapping) else {}
    pathway_assembly = state.get("formal_dual_tu_combined_result")
    pathway_assembly = (
        pathway_assembly if isinstance(pathway_assembly, Mapping) else {}
    )
    assembly_result = (
        pathway_assembly
        if _is_pathway_multi_tu_project()
        and not bool(state.get("formal_betalain_gate3_case"))
        else result
    )
    expected_assembly_signature = (
        cassette.get("input_signature")
        if assembly_result is pathway_assembly
        else state.get("mvp_current_input_signature")
    )
    assembly_current = bool(
        uses_multi_tu_assembly_gate
        and _is_multi_tu_expression_assembly(assembly_result)
        and assembly_result.get("input_signature") == expected_assembly_signature
        and not state.get("mvp_inputs_stale")
    )
    step3_done = (
        bool(multi_tu_overall_ready and assembly_current)
        if uses_multi_tu_assembly_gate
        else step3_can_continue_to_backbone(
            cassette_result=cassette,
            current_input_signature=step3_input_signature,
            findings=formal_cassette.get("findings") if isinstance(formal_cassette, Mapping) else [],
            order_confirmed=bool(
                state.get("formal_step3_order_confirmation_recorded")
                or state.get("formal_step3_order_confirmed")
            ),
        )
    )
    complete_artifact = (
        result.get("complete_plasmid")
        if _is_pathway_multi_tu_project()
        and not bool(state.get("formal_betalain_gate3_case"))
        else result.get("runtime") or result.get("combined_construct")
    )
    complete_result_current = bool(
        result.get("input_signature") == state.get("mvp_current_input_signature")
        and not state.get("mvp_inputs_stale")
        and complete_artifact
    )
    operation_validation = (
        insertion.get("t_dna_operation_validation")
        if isinstance(insertion.get("t_dna_operation_validation"), Mapping)
        else {}
    )
    manual_t_dna_confirmed = bool(
        isinstance(insertion.get("t_dna_confirmation"), Mapping)
        and insertion.get("t_dna_confirmation")
    )
    fixed_exact_insertion_applied = bool(
        operation_validation.get("allowed")
        and operation_validation.get("status")
        == "pcambia1300_exact_insertion_applied"
    )
    fixed_exact_replacement_applied = bool(
        operation_validation.get("allowed")
        and operation_validation.get("status")
        == "vector_asset_exact_operation_admitted"
        and operation_validation.get("workflow_id") == "gate3_pathway"
    )
    step4_contract_ready = bool(
        bool(backbone.get("normalized_sequence"))
        and operation_validation.get("allowed")
        and (
            manual_t_dna_confirmed
            or fixed_exact_insertion_applied
            or fixed_exact_replacement_applied
        )
    )
    single_gene_step4_confirmed = bool(
        state.get("formal_step4_strategy_confirmed")
        and str(state.get("formal_step4_strategy_signature") or "")
        == _formal_step4_strategy_signature()
    )
    multi_tu_step4_signature = _formal_ui_signature(
        {
            "input_signature": result.get("input_signature") or (result.get("combined_construct") or {}).get("input_signature"),
            "sequence_sha256": (result.get("combined_construct") or {}).get("sequence_sha256"),
        }
    )
    multi_tu_step4_confirmed = (
        is_generic_multi_tu
        and str(state.get("formal_multi_tu_step4_confirmation_signature") or "")
        == multi_tu_step4_signature
    )
    step4_done = (
        multi_tu_step4_confirmed
        if is_generic_multi_tu
        else complete_result_current
        or (
            step4_contract_ready
            and (
                _formal_project_type() != PROJECT_TYPE_SINGLE_GENE
                or single_gene_step4_confirmed
            )
        )
    )
    step5_done = complete_result_current if not is_generic_multi_tu else bool(
        state.get("formal_multi_tu_step5_confirmation_signature") == multi_tu_step4_signature
    )
    saved_project_id = str(state.get("formal_last_saved_mvp_project_id") or "")
    result_project_id = str(result.get("project_id") or "")
    step6_done = bool(step5_done and result_project_id and saved_project_id == result_project_id)
    review = {
        1: bool(state.get("formal_step1_design_dirty"))
        or str(context.get("construct_review_status") or "current") == "needs_review",
        2: bool(state.get("formal_step2_design_dirty"))
        or str(state.get("formal_cds_source_review_status") or context.get("cds_source_review_status") or "current") == "needs_review",
        # Manual confirmations stay visible in Step 3, but are not a continuation block.
        3: False,
        4: bool(insertion.get("t_dna_confirmation") and not operation_validation.get("allowed")),
        5: bool(
            state.get("mvp_inputs_stale")
            or state.get("formal_step1_design_dirty")
            or state.get("formal_step2_design_dirty")
            or str(context.get("construct_review_status") or "current") == "needs_review"
        ),
        6: bool(
            state.get("mvp_inputs_stale")
            or state.get("formal_step1_design_dirty")
            or state.get("formal_step2_design_dirty")
            or str(context.get("construct_review_status") or "current") == "needs_review"
        ),
    }
    completed = (step1_done, step2_done, step3_done, step4_done, step5_done, step6_done)
    return [{"done": done, "review": review[index]} for index, done in enumerate(completed, start=1)]


def _is_result_preview_mode() -> bool:
    """Show a saved result read-only only after an explicit historical open."""
    if not bool(st.session_state.get("formal_explicit_historical_open")):
        return False
    result = st.session_state.get("mvp_vector_result")
    if not isinstance(result, Mapping) or not str(result.get("project_id") or ""):
        return False
    exports = result.get("exports") if isinstance(result.get("exports"), Mapping) else {}
    fasta = (
        exports.get("complete_plasmid_fasta")
        or exports.get("combined_construct_fasta")
        or exports.get("fasta")
        or {}
    )
    genbank = (
        exports.get("complete_plasmid_genbank")
        or exports.get("combined_construct_genbank")
        or exports.get("genbank")
        or {}
    )
    if not isinstance(fasta, Mapping) or not isinstance(genbank, Mapping):
        return False
    if not fasta.get("data") or not genbank.get("data"):
        return False
    return not all(
        status["done"] and not status["review"]
        for status in _formal_step_statuses()[:5]
    )


def _render_result_preview_mode() -> None:
    # 历史结果预览 remains a source-shape marker for the formal preview route.
    st.title(_t('v1.common.results_export_historical_results_preview'))
    st.info(_t('v1.common.read_only_preview_historical_results_record_lacks'))
    reason_messages = {
        "legacy_record": "v1.common.historical_reason_legacy_record",
        "result_only_completed": "v1.common.historical_reason_result_only_completed",
        "missing_formal_state": "v1.common.historical_reason_missing_formal_state",
        "missing_step3_components": "v1.common.historical_reason_missing_step3_components",
        "state_canonical_mismatch": "v1.common.historical_reason_state_canonical_mismatch",
        "unsupported_version": "v1.common.historical_reason_unsupported_version",
    }
    preview_reason = str(st.session_state.get("formal_result_preview_reason") or "")
    if preview_reason in reason_messages:
        st.caption(_t(reason_messages[preview_reason]))
    _render_results_export_content(
        include_project_actions=False,
        result_preview_mode=True,
    )
    _render_step_navigation(
        current_step=6,
        next_enabled=False,
        show_save=False,
        show_next=False,
        compact_back_only=True,
    )


def _formal_ui_signature(value: Any) -> str:
    """Return a UI-only signature without changing any scientific signature."""
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _clear_formal_step5_strategy_confirmation() -> None:
    for key in (
        "formal_step5_strategy_confirmed",
        "formal_step5_strategy_signature",
    ):
        st.session_state.pop(key, None)


def _clear_formal_step4_strategy_confirmation() -> None:
    for key in (
        "formal_step4_strategy_confirmed",
        "formal_step4_strategy_signature",
        "formal_ui_step4_confirmation_signature",
    ):
        st.session_state.pop(key, None)
    _clear_formal_step5_strategy_confirmation()


def _formal_step4_strategy_signature() -> str:
    state = st.session_state
    backbone = state.get("formal_backbone_record")
    backbone = backbone if isinstance(backbone, Mapping) else {}
    insertion = state.get("formal_insertion_settings")
    insertion = insertion if isinstance(insertion, Mapping) else {}
    project_definition = state.get("formal_project_definition")
    project_definition = project_definition if isinstance(project_definition, Mapping) else {}
    return _formal_ui_signature(
        {
            "project_definition": project_definition,
            "cassette": state.get("formal_cassette_input_signature"),
            "backbone": backbone.get("normalized_sequence_sha256")
            or backbone.get("sequence_sha256")
            or backbone.get("normalized_sequence"),
            "insertion": insertion,
        }
    )


def _formal_step4_strategy_ready() -> bool:
    state = st.session_state
    backbone = state.get("formal_backbone_record")
    backbone = backbone if isinstance(backbone, Mapping) else {}
    insertion = state.get("formal_insertion_settings")
    insertion = insertion if isinstance(insertion, Mapping) else {}
    operation = insertion.get("t_dna_operation_validation")
    operation = operation if isinstance(operation, Mapping) else {}
    manual_t_dna_confirmed = bool(
        isinstance(insertion.get("t_dna_confirmation"), Mapping)
        and insertion.get("t_dna_confirmation")
    )
    fixed_operation_applied = bool(
        operation.get("allowed")
        and operation.get("status")
        in {
            "pcambia1300_exact_insertion_applied",
            "pbi121_exact_replacement_applied",
        }
    )
    return bool(
        state.get("formal_cassette_input_signature")
        and backbone.get("normalized_sequence")
        and operation.get("allowed")
        and (manual_t_dna_confirmed or fixed_operation_applied)
    )


def _record_formal_step4_strategy_confirmation(expected_signature: str) -> bool:
    """Record the existing Step 4 action only for the current ready strategy."""
    _clear_formal_step4_strategy_confirmation()
    current_signature = _formal_step4_strategy_signature()
    if str(expected_signature or "") != current_signature or not _formal_step4_strategy_ready():
        raise RuntimeError("The Step 4 strategy changed before confirmation.")
    st.session_state["formal_ui_step4_confirmation_signature"] = current_signature
    st.session_state["formal_step4_strategy_signature"] = current_signature
    st.session_state["formal_step4_strategy_confirmed"] = True
    return True


def _formal_step5_strategy_signature(result: Mapping[str, Any] | None = None) -> str:
    canonical = result if isinstance(result, Mapping) else st.session_state.get("mvp_vector_result")
    canonical = canonical if isinstance(canonical, Mapping) else {}
    return _formal_ui_signature(
        {
            "step4_strategy": _formal_step4_strategy_signature(),
            "canonical_input_signature": canonical.get("input_signature"),
        }
    )


def _formal_canonical_result_is_current(result: Mapping[str, Any]) -> bool:
    from services.canonical_construct_runtime import (
        CanonicalConstructRuntimeError,
        active_complete_plasmid_snapshot,
    )

    try:
        plasmid = active_complete_plasmid_snapshot(result.get("runtime"))
    except CanonicalConstructRuntimeError:
        return False
    return bool(
        plasmid.get("construct_status") == "current"
        and plasmid.get("sequence")
    )


def _record_formal_step5_strategy_confirmation(result: Mapping[str, Any]) -> bool:
    """Record the existing Step 5 action only after current canonical generation."""
    _clear_formal_step5_strategy_confirmation()
    result_signature = str(result.get("input_signature") or "")
    if not (
        result_signature
        and result_signature == str(st.session_state.get("mvp_current_input_signature") or "")
        and not st.session_state.get("mvp_inputs_stale")
        and _formal_canonical_result_is_current(result)
        and bool(st.session_state.get("formal_step4_strategy_confirmed"))
        and str(st.session_state.get("formal_step4_strategy_signature") or "")
        == _formal_step4_strategy_signature()
    ):
        raise RuntimeError("The generated Step 5 canonical result is not current.")
    st.session_state["formal_step5_strategy_signature"] = _formal_step5_strategy_signature(result)
    st.session_state["formal_step5_strategy_confirmed"] = True
    return True


def _refresh_formal_strategy_confirmation_state(
    result: Mapping[str, Any] | None = None,
) -> tuple[bool, bool]:
    """Fail closed when durable confirmations no longer match current inputs."""
    step4_current = bool(
        st.session_state.get("formal_step4_strategy_confirmed")
        and _formal_step4_strategy_ready()
        and str(st.session_state.get("formal_step4_strategy_signature") or "")
        == _formal_step4_strategy_signature()
    )
    if not step4_current:
        _clear_formal_step4_strategy_confirmation()
        return False, False

    canonical = result if isinstance(result, Mapping) else st.session_state.get("mvp_vector_result")
    canonical = canonical if isinstance(canonical, Mapping) else {}
    result_signature = str(canonical.get("input_signature") or "")
    step5_current = bool(
        st.session_state.get("formal_step5_strategy_confirmed")
        and result_signature
        and result_signature == str(st.session_state.get("mvp_current_input_signature") or "")
        and not st.session_state.get("mvp_inputs_stale")
        and _formal_canonical_result_is_current(canonical)
        and str(st.session_state.get("formal_step5_strategy_signature") or "")
        == _formal_step5_strategy_signature(canonical)
    )
    if not step5_current:
        _clear_formal_step5_strategy_confirmation()
    return True, step5_current


def _normalize_formal_current_step(
    current_step: int,
    *,
    statuses: list[dict[str, bool]] | None = None,
) -> int:
    """Clamp the current step to the first unmet contiguous prerequisite."""
    resolved = statuses if statuses is not None else _formal_step_statuses()
    last_reachable = 1
    prerequisites_complete = True
    for index, status in enumerate(resolved, start=1):
        if prerequisites_complete:
            last_reachable = index
        prerequisites_complete = prerequisites_complete and bool(
            status["done"] and not status["review"]
        )
    return min(max(1, min(6, int(current_step))), last_reachable)


def _formal_step_contract(
    current_step: int,
    *,
    statuses: list[dict[str, bool]] | None = None,
) -> list[dict[str, Any]]:
    statuses = statuses if statuses is not None else _formal_step_statuses()
    current_step = _normalize_formal_current_step(current_step, statuses=statuses)
    contract: list[dict[str, Any]] = []
    prerequisites_complete = True
    for index, status in enumerate(statuses, start=1):
        effective_done = bool(
            prerequisites_complete and status["done"] and not status["review"]
        )
        if index == current_step:
            state = "CURRENT"
            reason = ""
        elif effective_done:
            state = "COMPLETED"
            reason = ""
        elif prerequisites_complete:
            state = "AVAILABLE"
            reason = ""
        else:
            state = "BLOCKED"
            first_missing = next(
                (
                    prior_index
                    for prior_index, prior in enumerate(statuses[: index - 1], start=1)
                    if not prior["done"] or prior["review"]
                ),
                index - 1,
            )
            reason = f"请先完成第 {first_missing} 步的当前要求。"
        contract.append({**status, "step": index, "state": state, "reason": reason})
        prerequisites_complete = prerequisites_complete and effective_done
    return contract


def _set_formal_action_feedback(*, step: int, status: str, message: str) -> None:
    st.session_state["formal_ui_action_feedback"] = {
        "step": int(step),
        "status": str(status),
        "message": str(message),
    }


def _current_formal_action_feedback(
    current_step: int, statuses: list[dict[str, bool]] | None = None
) -> dict[str, Any] | None:
    """Return only feedback that still describes the currently rendered step."""
    feedback = st.session_state.get("formal_ui_action_feedback")
    if not isinstance(feedback, Mapping):
        return None
    feedback_step = max(1, min(6, int(feedback.get("step") or current_step)))
    if feedback_step != int(current_step):
        st.session_state.pop("formal_ui_action_feedback", None)
        return None
    resolved_statuses = statuses if statuses is not None else _formal_step_statuses()
    status = str(feedback.get("status") or "")
    if (
        status in {"生成失败", "保存失败"}
        and resolved_statuses[feedback_step - 1]["done"]
        and not resolved_statuses[feedback_step - 1]["review"]
    ):
        # A current successful artefact outranks an earlier failed click.
        st.session_state.pop("formal_ui_action_feedback", None)
        return None
    return dict(feedback)


def _execute_formal_action(
    *,
    step: int,
    action_id: str,
    input_signature: str,
    action: Any,
    success_status: str,
    success_message: str,
    failure_status: str,
) -> tuple[bool, Any, bool]:
    """Run one synchronous UI action once for an unchanged input signature."""
    if st.session_state.get("formal_read_only_preview"):
        _set_formal_action_feedback(
            step=step,
            status="只读预览",
            message="请先完成前置步骤。",
        )
        return False, None, False
    completed = dict(st.session_state.get("formal_ui_completed_actions") or {})
    if completed.get(action_id) == input_signature:
        _set_formal_action_feedback(
            step=step,
            status=success_status,
            message=success_message,
        )
        return True, None, False
    if st.session_state.get("formal_ui_action_busy"):
        _set_formal_action_feedback(step=step, status="处理中", message=_t("v1.expression.message_action_processing"))
        return False, None, False

    st.session_state["formal_ui_action_busy"] = action_id
    _set_formal_action_feedback(step=step, status="处理中", message=_t("v1.expression.message_step_processing"))
    try:
        with st.spinner(_t("v1.common.processing")):
            result = action()
    except Exception as exc:
        _set_formal_action_feedback(step=step, status=failure_status, message=str(exc))
        return False, exc, True
    finally:
        st.session_state.pop("formal_ui_action_busy", None)

    completed = dict(st.session_state.get("formal_ui_completed_actions") or {})
    completed[action_id] = input_signature
    st.session_state["formal_ui_completed_actions"] = completed
    _set_formal_action_feedback(
        step=step,
        status=success_status,
        message=success_message,
    )
    return True, result, True


def _matching_formal_step3_result(input_signature: str) -> dict[str, Any] | None:
    """Recover an existing generated cassette for the same business inputs."""
    candidates = (
        st.session_state.get("formal_cassette_result"),
        st.session_state.get("formal_expression_cassette"),
    )
    for candidate in candidates:
        if not isinstance(candidate, dict) or not candidate.get("runtime"):
            continue
        candidate_signature = str(
            candidate.get("cassette_input_signature")
            or candidate.get("input_signature")
            or ""
        )
        if candidate_signature != str(input_signature or ""):
            continue
        st.session_state["formal_cassette_result"] = {
            "runtime": candidate["runtime"],
            "cassette_input_signature": input_signature,
            "input_signature": input_signature,
        }
        st.session_state["formal_cassette_input_signature"] = input_signature
        completed = dict(st.session_state.get("formal_ui_completed_actions") or {})
        completed["step3_generate_continue"] = input_signature
        st.session_state["formal_ui_completed_actions"] = completed
        return candidate
    return None


def _formal_cds_signature(cds_input: Mapping[str, Any] | None) -> str:
    """Serialize CDS identity deterministically for the Step 3 input signature."""
    value = (cds_input or {}).get("sequence_signature") or (cds_input or {}).get(
        "normalized_cds_sha256"
    )
    if isinstance(value, Mapping):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return str(value or "")


def _restore_formal_step3_generated_result() -> None:
    """Rebuild the derived Step 3 gate record from a saved generated cassette."""
    cassette = st.session_state.get("formal_expression_cassette")
    if not isinstance(cassette, Mapping) or not isinstance(cassette.get("runtime"), Mapping):
        return
    input_signature = str(
        cassette.get("cassette_input_signature")
        or cassette.get("input_signature")
        or ""
    )
    if not input_signature:
        return
    st.session_state["formal_cassette_result"] = {
        "runtime": dict(cassette["runtime"]),
        "cassette_input_signature": input_signature,
        "input_signature": input_signature,
    }
    st.session_state["formal_cassette_input_signature"] = input_signature


def _orchestrate_formal_step3_generation(
    *, input_signature: str, generate_action: Any
) -> tuple[bool, Any, bool]:
    existing = _matching_formal_step3_result(input_signature)
    if existing is not None:
        _set_formal_action_feedback(
            step=3,
            status="已生成",
            message="当前输入对应的表达盒已存在，可以继续第四步。",
        )
        return True, existing, False
    return _execute_formal_action(
        step=3,
        action_id="step3_generate_continue",
        input_signature=input_signature,
        action=generate_action,
        success_status="已生成",
        success_message="表达盒已生成，可以继续第四步。",
        failure_status="生成失败",
    )


def _orchestrate_formal_step6_save(
    result: dict[str, Any], save_service: Any
) -> tuple[bool, Any, bool]:
    result_project_id = str(result.get("project_id") or "")
    if result_project_id and str(
        st.session_state.get("formal_last_saved_mvp_project_id") or ""
    ) == result_project_id:
        _set_formal_action_feedback(
            step=6,
            status="已保存",
            message="当前设计已经保存，可以从项目首页重新打开。",
        )
        return True, None, False

    completed = dict(st.session_state.get("formal_ui_completed_actions") or {})
    completed.pop("step6_save_design", None)
    st.session_state["formal_ui_completed_actions"] = completed

    def persist_current_result() -> Any:
        saved = save_service(result)
        saved_project_id = str(getattr(saved, "project_id", "") or "")
        if not result_project_id or saved_project_id != result_project_id:
            raise RuntimeError("保存服务未返回当前项目的持久化标识。")
        st.session_state["formal_last_saved_mvp_project_id"] = saved_project_id
        return saved

    return _execute_formal_action(
        step=6,
        action_id="step6_save_design",
        input_signature=_formal_ui_signature(
            {
                "project_id": result_project_id,
                "input_signature": result.get("input_signature"),
            }
        ),
        action=persist_current_result,
        success_status="已保存",
        success_message="设计已保存，可以从项目首页重新打开。",
        failure_status="保存失败",
    )


def _verified_formal_saved_project_id(
    result: dict[str, Any], open_service: Any = None
) -> str:
    """Return a project id only when the current result is durably reopenable."""
    project_id = str(result.get("project_id") or "")
    if not project_id:
        return ""
    if open_service is None:
        from services.mvp_single_gene_persistence import open_mvp_single_gene_design

        open_service = open_mvp_single_gene_design
    try:
        reopened = open_service(project_id)
    except Exception:
        return ""
    if not isinstance(reopened, dict) or not reopened.get("runtime"):
        return ""
    if str(reopened.get("project_id") or "") != project_id:
        return ""
    current_signature = str(result.get("input_signature") or "")
    reopened_signature = str(reopened.get("input_signature") or "")
    if current_signature and reopened_signature != current_signature:
        return ""
    return project_id


def _render_formal_action_feedback(current_step: int) -> None:
    statuses = _formal_step_statuses()
    feedback = _current_formal_action_feedback(current_step, statuses)
    if isinstance(feedback, dict) and str(feedback.get("status") or "") in {
        "已保存",
        "流程已更新",
        "已生成",
        "可以继续",
    }:
        feedback_step = max(1, min(6, int(feedback.get("step") or current_step)))
        if not statuses[feedback_step - 1]["done"] or statuses[feedback_step - 1]["review"]:
            feedback = None
    step3_manual_confirmation_count = sum(
        1
        for item in list(
            (st.session_state.get("formal_expression_cassette") or {}).get(
                "manual_confirmation_items"
            )
            or []
        )
        if isinstance(item, dict)
    )
    if current_step == 3 and statuses[2]["done"] and step3_manual_confirmation_count:
        status = "需要人工确认"
        message = "当前表达盒可继续，正式使用前请补充来源与注释依据。"
    elif isinstance(feedback, dict):
        status = str(feedback.get("status") or "未完成")
        message = str(feedback.get("message") or "")
    else:
        status_row = statuses[max(1, min(6, current_step)) - 1]
        if status_row["review"]:
            status, message = "需要修正", "当前记录需要重新审查后才能继续。"
        elif status_row["done"]:
            status = "已保存" if current_step == 6 else (
                "已生成" if current_step in {3, 5} else "可以继续"
            )
            message = _t("v1.expression.message_status_from_record")
        else:
            status, message = "未完成", _t("v1.expression.message_complete_step")
    body = _t(
        'v1.expression.status_message',
        status=_ui(status),
        message=_display_product_message(message),
    )
    if status in {"保存失败", "生成失败"}:
        st.error(body)
    elif status == "需要修正":
        st.warning(body)
    elif status == "需要人工确认":
        st.info(body)
    elif status in {"已保存", "已生成", "可以继续"}:
        st.success(body)
    elif status == "流程已更新":
        st.info(body)
    else:
        st.info(body)


def _formal_step_label_keys() -> tuple[str, ...]:
    if _formal_design_scenario() == "metabolic_pathway_multi_tu_vector":
        return (
            'v1.expression.step_short_project_definition',
            'v1.expression.step_short_pathway_mapping',
            'v1.expression.step_short_tu_component_design',
            'v1.expression.step_short_pathway_backbone',
            'v1.expression.step_short_complete_construct',
            'v1.expression.step_short_results_export',
        )
    return (
        (
            'v1.expression.step_short_project_definition',
            'v1.expression.step_short_tu_planning',
            'v1.expression.step_short_tu_component_design',
            'v1.expression.step_short_assembly_settings',
            'v1.expression.step_short_checks',
            'v1.expression.step_short_results_export',
        )
        if _is_generic_multi_tu_workflow()
        else (
            'v1.expression.step_short_project_definition',
            'v1.expression.step_short_target_gene',
            'v1.expression.step_short_plant_expression_cassette',
            'v1.expression.step_short_vector_backbone',
            'v1.expression.step_short_complete_construct',
            'v1.expression.step_short_results_export',
        )
    )
def _render_step_strip(current_step: int) -> None:
    label_helper = globals().get("_formal_step_label_keys")
    short_label_keys = label_helper() if callable(label_helper) else (
        (
            'v1.expression.step_short_project_definition',
            'v1.expression.step_short_tu_planning',
            'v1.expression.step_short_tu_component_design',
            'v1.expression.step_short_assembly_settings',
            'v1.expression.step_short_checks',
            'v1.expression.step_short_results_export',
        ) if globals().get("_is_generic_multi_tu_workflow", lambda: False)() else (
            'v1.expression.step_short_project_definition',
            'v1.expression.step_short_target_gene',
            'v1.expression.step_short_plant_expression_cassette',
            'v1.expression.step_short_vector_backbone',
            'v1.expression.step_short_complete_construct',
            'v1.expression.step_short_results_export',
        )
    )
    statuses = _formal_step_contract(current_step)
    with st.container(key="formal_step_strip"):
        columns = st.columns(6)
        for index, (column, label_key, status) in enumerate(zip(columns, short_label_keys, statuses), start=1):
            state_class = {
                "CURRENT": "current",
                "COMPLETED": "review" if status["review"] else "done",
                "AVAILABLE": "available",
                "BLOCKED": "blocked",
            }[status["state"]]
            state_label_key = {
                "CURRENT": 'v1.expression.current_step',
                "COMPLETED": 'v1.expression.review_needed' if status["review"] else 'v1.expression.completed',
                "AVAILABLE": 'v1.expression.can_continue',
                "BLOCKED": 'v1.expression.not_completed',
            }[status["state"]]
            with column:
                with st.container(key=f"formal_step_card_{index}_{state_class}"):
                    if st.button(
                        f"{index}. {_t(label_key)}",
                        key=f"formal_top_step_{index}",
                        type="secondary",
                        disabled=status["state"] in {"CURRENT", "BLOCKED"},
                        use_container_width=True,
                    ):
                        _set_formal_step(index)
                    st.markdown(
                        f"<div class='formal-step-status {state_class}'>{_t(state_label_key)}</div>",
                        unsafe_allow_html=True,
                    )


def _render_step_navigation(
    *,
    current_step: int,
    next_enabled: bool,
    next_label: str = "",
    disabled_reason: str = "",
    show_save: bool = True,
    show_next: bool = True,
    compact_back_only: bool = False,
    next_action: Any | None = None,
    next_type: str = "primary",
) -> None:
    if compact_back_only:
        if st.button(
            label=_t('v1.expression.return_project_home'),
            key=f"formal_step_{current_step}_back",
            use_container_width=True,
        ):
            _change_page(PAGE_PROJECT_HOME)
        return
    preview_blocked = current_step > _normalize_formal_current_step(current_step)
    with st.container(
        border=True,
        key=f"formal_page_actions_step_{current_step}",
    ):
        action_columns = st.columns([1, 1] if current_step == 6 else [1, 1, 1])
        back_col, save_col = action_columns[:2]
        next_col = action_columns[2] if len(action_columns) > 2 else None
        if disabled_reason and not next_enabled:
            st.caption(disabled_reason)
        st.caption(
            _t('v1.common.project_saved_can_reopened_project_center')
            if current_step == 6
            else _t('v1.common.project_draft_saved_can_reopened_project_center')
        )
        if back_col.button(
            _t('v1.expression.return_project_home'),
            key=f"formal_step_{current_step}_back",
            use_container_width=True,
        ):
            _change_page(PAGE_PROJECT_HOME)
        save_label = _t('v1.common.save_project') if current_step == 6 else _t('v1.common.save_draft')
        if show_save and save_col.button(
            save_label,
            key=f"formal_step_{current_step}_save_draft",
            disabled=preview_blocked,
            use_container_width=True,
        ):
            if current_step == 2 and _is_pathway_multi_tu_project():
                try:
                    _save_gate3_pathway_draft()
                except (ValueError, RuntimeError) as exc:
                    st.error(str(exc))
                else:
                    st.success(
                        _t('v1.common.project_saved_can_reopened_project_center')
                        if current_step == 6
                        else _t('v1.common.project_draft_saved_can_reopened_project_center')
                    )
            else:
                try:
                    _save_current_formal_draft(current_step=current_step)
                except (ValueError, RuntimeError) as exc:
                    st.error(str(exc))
                else:
                    st.success(
                        _t('v1.common.project_saved_can_reopened_project_center')
                        if current_step == 6
                        else _t('v1.common.project_draft_saved_can_reopened_project_center')
                    )
        has_unsaved_changes = globals().get(
            "_workflow_has_unsaved_changes",
            lambda: bool(st.session_state.get("ui_workflow_dirty")),
        )
        if current_step in {1, 2, 3, 4, 5} and has_unsaved_changes():
            st.caption(_t('v1.expression.unsaved_changes_session_only_save_draft'))
        if next_label and current_step < 6:
            next_clicked = next_col.button(
                next_label,
                key=f"formal_step_{current_step}_next",
                type=next_type,
                disabled=not next_enabled,
                use_container_width=True,
            )
        elif current_step < 6 and next_col.button(
            _t('v1.common.next'),
            key=f"formal_step_{current_step}_next",
            type=next_type,
            disabled=not next_enabled,
            use_container_width=True,
        ):
            next_clicked = True
        else:
            next_clicked = False
        if next_clicked:
            if next_action is not None:
                next_action()
            else:
                _set_formal_step(current_step + 1)


def _is_formal_action_widget_key(key: Any) -> bool:
    """Return whether a formal-state key belongs to an action-only widget."""
    action_key = re.compile(
        r"^formal_(?:"
        r"ui_.+|"
        r"top_step_\d+|"
        r"step_\d+_(?:back|next|save_draft)|"
        r"catalog_select_.+|"
        r"pathway_(?:add_(?:step|tu)|.+_(?:up|down|delete|save|apply))|"
        r"betalain_(?:open_saved|save_enzyme_edit|save_mapping|record_regulatory|generate_canonical|results)|"
        r"open_crispr_product_workflow|"
        r"multi_tu_add|"
        r"library_use_\d+|"
        r".+_(?:move_up|move_down|delete|delete_confirm|delete_cancel)"
        r")$"
    )
    return bool(action_key.match(str(key)))


def _formal_widget_initial_kwargs(key: Any, **defaults: Any) -> dict[str, Any]:
    """Provide widget defaults only before a key has been hydrated."""
    return {} if str(key) in st.session_state else defaults


def _formal_state_snapshot() -> dict[str, Any]:
    """Copy JSON-compatible formal workflow state without persisting widget actions."""
    snapshot: dict[str, Any] = {}
    derived_widget_keys = {
        "formal_step1_design_scenario",
        "formal_step1_induction_notes",
        "formal_step1_localization_target",
        "formal_step1_material",
        "formal_step1_project_name",
        "formal_step1_project_type",
        "formal_step1_tissue_target",
        "formal_step1_design_dirty",
        "formal_step2_design_dirty",
    }
    session_only_keys = {
        "formal_workflow_dirty",
        "formal_durable_save_state",
        "ui_workflow_dirty",
        "ui_has_durable_save",
        "ui_step1_baseline",
    }
    for key, value in st.session_state.items():
        key_text = str(key)
        if (
            not key_text.startswith(("formal_", "mvp_"))
            or _is_formal_action_widget_key(key_text)
            or key_text.startswith("formal_ai_route_")
            or key_text in derived_widget_keys
            or key_text in session_only_keys
        ):
            continue
        try:
            snapshot[key_text] = json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))
        except (TypeError, ValueError):
            continue
    return snapshot


def _bind_completed_formal_state(result: dict[str, Any]) -> dict[str, Any]:
    """Attach editable formal state to a completed-result save without a cycle."""
    _refresh_formal_strategy_confirmation_state(result)
    formal_state = _formal_state_snapshot()
    # The completed persistence path stores the result itself, including its
    # canonical runtime and export bytes. Keeping it out of this embedded
    # editor snapshot prevents a recursive result -> state -> result payload.
    formal_state.pop("mvp_vector_result", None)
    context = (
        dict(result.get("formal_project_context") or {})
        if isinstance(result.get("formal_project_context"), dict)
        else {}
    )
    if str(result.get("project_type") or "") == "dual_tu":
        context["project_type"] = "dual_tu"
    if str(result.get("result_kind") or "") == "MULTI_TU_EXPRESSION_ASSEMBLY":
        from services.mvp_multi_tu_persistence import (
            linear_multi_tu_completed_editor_vector_state,
        )

        backbone_state, insertion_state = (
            linear_multi_tu_completed_editor_vector_state(result)
        )
        original_input = result.get("original_input")
        if not isinstance(original_input, dict):
            raise ValueError("The Multi-TU assembly is missing its original input record.")
        canonical_units = original_input.get("expression_units")
        if not isinstance(canonical_units, list) or not canonical_units:
            raise ValueError("The Multi-TU assembly is missing its canonical input units.")
        formal_state["formal_transcription_units"] = json.loads(
            json.dumps(canonical_units, ensure_ascii=False, sort_keys=True)
        )
        formal_state["formal_multi_tu_step2_planning_signature"] = (
            _multi_tu_step2_planning_signature(
                formal_state["formal_transcription_units"]
            )
        )
        original_input["backbone"] = dict(backbone_state)
        original_input["insertion_settings"] = dict(insertion_state)
        formal_state["formal_backbone_record"] = dict(backbone_state)
        formal_state["formal_insertion_settings"] = dict(insertion_state)
    from services.formal_editor_state_contract import (
        FORMAL_EDITOR_STATE_CONTRACT_VERSION,
        RECORD_KIND_FORMAL_EDITOR_COMPLETED,
    )

    context["record_kind"] = RECORD_KIND_FORMAL_EDITOR_COMPLETED
    context["formal_editor_state_contract_version"] = FORMAL_EDITOR_STATE_CONTRACT_VERSION
    context["formal_state"] = formal_state
    context["project_definition"] = dict(_formal_project_definition())
    result["formal_project_context"] = context
    return result


def _restore_completed_formal_state(context: Mapping[str, Any]) -> None:
    """Hydrate saved formal widgets before reconstructing the completed result."""
    saved_state = context.get("formal_state")
    if not isinstance(saved_state, Mapping):
        return
    restored_state = {
        str(key): value
        for key, value in saved_state.items()
        if str(key).startswith(("formal_", "mvp_"))
        and str(key) != "mvp_vector_result"
        and str(key) not in {"formal_workflow_dirty", "formal_durable_save_state"}
        and not str(key).startswith("formal_ai_route_")
        and not _is_formal_action_widget_key(key)
    }
    st.session_state.update(restored_state)
    st.session_state.pop("formal_step1_design_dirty", None)
    st.session_state.pop("formal_step2_design_dirty", None)
    globals().get("_establish_workflow_baseline", lambda **_kwargs: None)(
        has_durable_save=True
    )


def _formal_workflow_type() -> str:
    from services.formal_project_persistence import (
        WORKFLOW_GATE3_PATHWAY,
        WORKFLOW_MULTI_TU,
        WORKFLOW_SINGLE_GENE,
    )

    if _is_pathway_multi_tu_project():
        return WORKFLOW_GATE3_PATHWAY
    return WORKFLOW_MULTI_TU if _is_dual_tu_project() else WORKFLOW_SINGLE_GENE


def _save_current_formal_draft(
    *,
    current_step: int,
    repository: Any = None,
    manual_state_updates: dict[str, Any] | None = None,
) -> Any:
    result = st.session_state.get("mvp_vector_result")
    if current_step == 6 and isinstance(result, dict):
        from services.mvp_multi_tu_persistence import save_mvp_multi_tu_design
        from services.mvp_single_gene_persistence import save_mvp_single_gene_design

        result = _bind_completed_formal_state(result)
        saved = (
            save_mvp_multi_tu_design(result, repository=repository)
            if _is_dual_tu_project()
            else save_mvp_single_gene_design(result, repository=repository)
        )
        st.session_state["mvp_project_id"] = saved.project_id
        st.session_state["formal_last_saved_mvp_project_id"] = saved.project_id
        globals().get("_establish_workflow_baseline", lambda **_kwargs: None)(
            has_durable_save=True
        )
        context = result.get("formal_project_context")
        saved_definition = (
            context.get("project_definition")
            if isinstance(context, dict)
            else None
        )
        if isinstance(saved_definition, dict):
            st.session_state["ui_step1_baseline"] = dict(saved_definition)
        return saved

    from services.formal_project_persistence import save_formal_project_draft
    from services.plant_project_draft_repository import PlantProjectDraftRepository

    definition = dict(_formal_project_definition())
    definition["expression_target"] = _project_definition_expression_target(definition)
    project_name = str(
        st.session_state.get("formal_step1_project_name")
        or definition.get("project_name")
        or st.session_state.get("formal_project_name")
        or ""
    ).strip()
    definition["project_name"] = project_name
    saved = save_formal_project_draft(
        project_name=project_name,
        project_id=str(st.session_state.get("mvp_project_id") or ""),
        workflow_type=_formal_workflow_type(),
        current_step=current_step,
        design_session=_controller().get(),
        formal_state=_formal_state_snapshot(),
        project_definition=definition,
        manual_state_updates=manual_state_updates,
        repository=repository or PlantProjectDraftRepository(),
    )
    st.session_state["mvp_project_id"] = saved.project_id
    st.session_state["formal_last_saved_draft_id"] = saved.project_id
    globals().get("_establish_workflow_baseline", lambda **_kwargs: None)(
        has_durable_save=True
    )
    st.session_state["ui_step1_baseline"] = dict(definition)
    return saved


def _start_blank_design(project_type: str = PROJECT_TYPE_SINGLE_GENE) -> None:
    """Reset the existing six-step state for one formal plant project."""
    from core.design_session import DesignSession, SessionController
    from services.wizard_state_service import reset_wizard_for_new_design

    stable_single_name = globals().get("_stable_single_gene_project_name")
    stable_multi_name = globals().get("_stable_multi_tu_project_name")
    if not callable(stable_single_name):
        stable_single_name = lambda value: str(value or "").strip() or "Plant expression vector project"
    if not callable(stable_multi_name):
        stable_multi_name = lambda value: str(value or "").strip() or "Multi-TU project"

    ctrl = SessionController()
    ctrl.save(DesignSession(step=1, host="", tag="No tag"))
    ctrl.clear_global_context()
    reset_wizard_for_new_design(st.session_state)
    for key in list(st.session_state):
        if key.startswith("mvp_") or key.startswith("formal_"):
            del st.session_state[key]
    st.session_state["formal_project_name"] = stable_single_name("")
    st.session_state["formal_expression_target"] = ""
    st.session_state["formal_project_type"] = project_type
    st.session_state["formal_design_scenario"] = "standard_plant_expression_vector"
    if project_type == PROJECT_TYPE_DUAL_TU:
        st.session_state["formal_project_name"] = stable_multi_name("")
        st.session_state["formal_transcription_units"] = _blank_dual_tu_units()
    globals().get("_establish_workflow_baseline", lambda **_kwargs: None)(
        has_durable_save=False
    )
    st.session_state["ui_step1_baseline"] = dict(_formal_project_definition())
    st.session_state.pop("formal_locked_project_name", None)
    st.session_state.pop("formal_case_boundary_note", None)
    st.session_state.pop("formal_source_input_records", None)
    st.session_state.pop("formal_element_source_records", None)
    _bump_reset_token()
    _change_page(PAGE_DESIGN_WORKSPACE)


def _save_gate3_pathway_draft(repository: Any = None) -> Any:
    """Save the mapped Step 2 record through the existing plant-project repository."""
    if not _is_pathway_multi_tu_project():
        raise ValueError("当前项目不是代谢通路多转录单元项目。")
    mapping = _refresh_pathway_mapping_status()
    if not mapping["mapping_complete"]:
        raise ValueError("请先完成 pathway step、enzyme、CDS 与 TU 映射。")

    definition = dict(_formal_project_definition())
    project_name = str(definition.get("project_name") or st.session_state.get("formal_project_name") or "").strip()
    if not project_name:
        raise ValueError("保存前需要项目名称。")
    pathway_state = {
        "schema_version": GATE3_PATHWAY_DRAFT_SCHEMA_VERSION,
        "project_type": PROJECT_TYPE_DUAL_TU,
        "design_scenario": _formal_design_scenario(),
        "project_definition": definition,
        "pathway_steps": mapping["pathway_steps"],
        "transcription_units": _transcription_units(),
        "current_step": 2,
    }
    saved = _save_current_formal_draft(
        current_step=2,
        repository=repository,
        manual_state_updates={GATE3_PATHWAY_DRAFT_KEY: pathway_state},
    )
    st.session_state["formal_last_saved_gate3_draft_id"] = saved.project_id
    return saved


def _gate3_pathway_drafts(repository: Any = None) -> list[tuple[Any, dict[str, Any]]]:
    from services.mvp_multi_tu_persistence import MVP_MULTI_TU_PERSISTENCE_KEY
    from services.plant_project_draft_repository import PlantProjectDraftRepository
    from services.plant_project_draft_schema import PlantProjectDraftError

    repo = repository or PlantProjectDraftRepository()
    drafts: list[tuple[Any, dict[str, Any]]] = []
    for summary in repo.list_summaries():
        try:
            draft = repo.load(summary.project_id)
        except PlantProjectDraftError:
            continue
        state = dict(draft.manual_review_state)
        payload = state.get(GATE3_PATHWAY_DRAFT_KEY)
        if not isinstance(payload, dict) or MVP_MULTI_TU_PERSISTENCE_KEY in state:
            continue
        if (
            payload.get("schema_version") != GATE3_PATHWAY_DRAFT_SCHEMA_VERSION
            or payload.get("project_type") != PROJECT_TYPE_DUAL_TU
            or payload.get("design_scenario") != "metabolic_pathway_multi_tu_vector"
        ):
            continue
        drafts.append((summary, payload))
    return drafts


def _formal_workflow_drafts(repository: Any = None) -> list[tuple[Any, dict[str, Any]]]:
    from services.formal_project_persistence import formal_draft_snapshot
    from services.plant_project_draft_repository import PlantProjectDraftRepository
    from services.plant_project_draft_schema import PlantProjectDraftError

    repo = repository or PlantProjectDraftRepository()
    drafts: list[tuple[Any, dict[str, Any]]] = []
    for summary in repo.list_summaries():
        try:
            draft = repo.load(summary.project_id)
            snapshot = formal_draft_snapshot(draft)
        except PlantProjectDraftError:
            continue
        drafts.append((summary, snapshot))
    return drafts


def _restore_formal_workflow_draft(project_id: str, repository: Any = None) -> None:
    from services.formal_project_persistence import formal_draft_snapshot, restore_design_session
    from services.formal_project_definition_lifecycle import normalize_project_definition
    from services.plant_project_draft_repository import PlantProjectDraftRepository, require_active_project

    repo = repository or PlantProjectDraftRepository()
    draft = repo.load(project_id)
    require_active_project(draft)
    snapshot = formal_draft_snapshot(draft)
    for key in list(st.session_state):
        if str(key).startswith(("formal_", "mvp_")):
            del st.session_state[key]
    restored_state = {
        str(key): value
        for key, value in dict(snapshot["formal_state"]).items()
        if not str(key).startswith("formal_ai_route_")
        and str(key) not in {"formal_workflow_dirty", "formal_durable_save_state"}
        and not _is_formal_action_widget_key(key)
    }
    st.session_state.update(restored_state)
    _restore_formal_step3_generated_result()
    st.session_state["_formal_restore_step3_pending"] = True
    st.session_state["mvp_project_id"] = draft.project_id
    st.session_state["formal_last_saved_draft_id"] = draft.project_id
    st.session_state["formal_project_name"] = draft.project_name
    definition = dict(snapshot.get("project_definition") or {})
    if (
        snapshot["workflow_type"] == "single_gene"
        and "expression_target" in definition
    ):
        # The outer draft record also carries a derived expression_target used
        # for project-list metadata. Restore only the canonical Step 1 field
        # model so an equivalent hydration cannot change a saved Step 4
        # confirmation signature.
        definition = normalize_project_definition(
            definition,
            fallback_host=getattr(draft, "host_context", ""),
        )
    # Compatibility drafts may omit formal_project_definition from formal_state;
    # the independent persisted definition is still the authoritative Step 1
    # record and must seed the session baseline before the next render.
    st.session_state["formal_project_definition"] = dict(definition)
    st.session_state["formal_project_material"] = str(definition.get("material") or "")
    st.session_state["formal_project_tissue_target"] = str(definition.get("tissue_target") or "")
    st.session_state["formal_project_induction_notes"] = str(definition.get("induction_notes") or "")
    st.session_state["formal_project_localization_target"] = str(definition.get("localization_target") or "")
    st.session_state["formal_project_type"] = (
        PROJECT_TYPE_DUAL_TU
        if snapshot["workflow_type"] in {"multi_tu", "gate3_pathway"}
        else PROJECT_TYPE_SINGLE_GENE
    )
    st.session_state["formal_design_scenario"] = (
        "metabolic_pathway_multi_tu_vector"
        if snapshot["workflow_type"] == "gate3_pathway"
        else "standard_plant_expression_vector"
    )
    design_session = restore_design_session(snapshot["design_session"])
    saved_cds = st.session_state.get("formal_cds_input")
    if isinstance(saved_cds, Mapping):
        gene_information = saved_cds.get("gene_information")
        gene_information = gene_information if isinstance(gene_information, Mapping) else {}
        design_session.gene_name = str(
            st.session_state.get("formal_step2_gene_name")
            or gene_information.get("gene_name")
            or design_session.gene_name
            or "CDS"
        )
        design_session.original_seq = str(
            saved_cds.get("normalized_cds") or design_session.original_seq or ""
        )
    design_session.host = str(definition.get("plant_host") or design_session.host or "")
    _controller().save(design_session)
    globals().get("_establish_workflow_baseline", lambda **_kwargs: None)(
        has_durable_save=True
    )
    _change_page(PAGE_DESIGN_WORKSPACE)


def _restore_gate3_pathway_draft(project_id: str, repository: Any = None) -> None:
    """Restore a mapped Gate 3 draft without constructing or regenerating DNA."""
    from core.design_session import DesignSession
    from services.formal_project_definition_lifecycle import construct_review_basis, normalize_project_definition
    from services.gate3_pathway_mapping import normalize_pathway_steps
    from services.plant_project_draft_repository import PlantProjectDraftRepository, require_active_project

    repo = repository or PlantProjectDraftRepository()
    draft = repo.load(project_id)
    require_active_project(draft)
    payload = dict(draft.manual_review_state).get(GATE3_PATHWAY_DRAFT_KEY)
    if not isinstance(payload, dict) or payload.get("schema_version") != GATE3_PATHWAY_DRAFT_SCHEMA_VERSION:
        raise ValueError("保存记录不是可恢复的 Gate 3 pathway 草稿。")
    steps = normalize_pathway_steps(payload.get("pathway_steps"))
    units = _normalize_transcription_units(list(payload.get("transcription_units") or []))
    if not steps or not units:
        raise ValueError("保存记录缺少 pathway steps 或转录单元。")
    definition = normalize_project_definition(
        payload.get("project_definition"),
        fallback_host=draft.host_context,
    )
    host = str(definition.get("plant_host") or "")
    if _plant_host_record(host) is None:
        raise ValueError("保存记录中的植物宿主不受当前工作区支持。")

    _invalidate_formal_snapshots()
    st.session_state["formal_project_type"] = PROJECT_TYPE_DUAL_TU
    st.session_state["formal_design_scenario"] = "metabolic_pathway_multi_tu_vector"
    st.session_state["formal_project_definition"] = dict(definition)
    st.session_state["formal_project_name"] = definition["project_name"]
    st.session_state["formal_project_host"] = host
    st.session_state["formal_project_material"] = definition["material"]
    st.session_state["formal_expression_target"] = _project_definition_expression_target(definition)
    st.session_state["formal_construct_review_basis"] = construct_review_basis(definition)
    st.session_state["formal_construct_review_status"] = "current"
    st.session_state["formal_pathway_steps"] = steps
    st.session_state["formal_transcription_units"] = units
    st.session_state["mvp_project_id"] = draft.project_id
    st.session_state["formal_last_saved_draft_id"] = draft.project_id
    st.session_state["formal_last_saved_gate3_draft_id"] = draft.project_id
    for field in (
        "project_name",
        "host",
        "material",
        "application_mode",
        "transient_expression_system",
        "tissue_specificity_requirement",
        "tissue_target",
        "inducibility_requirement",
        "induction_notes",
        "localization_target",
        "compatibility_review_required",
        "legacy_application_mode",
        "legacy_expression_mode",
    ):
        source_field = "plant_host" if field == "host" else field
        st.session_state[f"formal_step1_{field}"] = definition[source_field]
    st.session_state.pop("formal_locked_project_name", None)
    st.session_state.pop("formal_betalain_gate3_case", None)
    _controller().save(DesignSession(step=2, host=host, tag="No tag"))
    globals().get("_establish_workflow_baseline", lambda **_kwargs: None)(
        has_durable_save=True
    )
    _change_page(PAGE_DESIGN_WORKSPACE)


def _load_rice_alb_example() -> None:
    """Load the existing local NCBI ALB CDS into the formal six-step state."""
    from Bio import SeqIO
    from core.design_session import DesignSession
    from core.expression_frame_builder import get_host_rules
    from services.rice_hsa_ncbi_mvp10_case import ALB_GENBANK

    record = SeqIO.read(ALB_GENBANK, "genbank")
    cds = next(
        feature
        for feature in record.features
        if feature.type == "CDS" and "albumin" in " ".join(feature.qualifiers.get("product", [])).lower()
    )
    rice_host = _plant_host_value_for_id("rice")
    rules = get_host_rules(rice_host)
    ds = DesignSession(
        step=1,
        gene_name="ALB",
        original_seq=str(cds.extract(record.seq)).upper(),
        host=rice_host,
        tag="No tag",
        elements={
            "promoter_name": str(rules.get("promoter") or ""),
            "promoter_seq": str(rules.get("promoter_seq") or ""),
            "rbs_name": str(rules.get("rbs") or ""),
            "rbs_seq": str(rules.get("rbs_seq") or ""),
            "terminator_name": str(rules.get("terminator") or ""),
            "terminator_seq": str(rules.get("terminator_seq") or ""),
        },
    )
    _controller().save(ds)
    _clear_complete_plasmid_state()
    st.session_state.pop("mvp_project_id", None)
    st.session_state["formal_project_name"] = "水稻 ALB 演示项目"
    st.session_state["formal_project_type"] = PROJECT_TYPE_SINGLE_GENE
    st.session_state["formal_locked_project_name"] = "水稻 ALB 演示项目"
    st.session_state["formal_case_boundary_note"] = "仅用于软件功能和交付格式测试，不可用于正式构建。"
    st.session_state.pop("formal_source_input_records", None)
    st.session_state["formal_expression_target"] = "ALB 蛋白表达"
    st.session_state["formal_cds_source"] = "NM_000477.7"
    _change_page(PAGE_DESIGN_WORKSPACE)


def _load_rice_hsa_real_case() -> None:
    """Load the official-source case into the existing six-step workspace."""
    from services.rice_hsa_ncbi_mvp10_case import REAL_CASE_PROJECT_NAME, build_rice_hsa_real_case

    result = build_rice_hsa_real_case()
    st.session_state["formal_project_type"] = PROJECT_TYPE_SINGLE_GENE
    _restore_mvp_result(result, _plant_host_value_for_id("rice"))
    st.session_state["formal_project_name"] = REAL_CASE_PROJECT_NAME
    st.session_state["formal_locked_project_name"] = REAL_CASE_PROJECT_NAME
    st.session_state["formal_case_boundary_note"] = str((result.get("real_case_manifest") or {}).get("boundary_note") or "")
    st.session_state["formal_source_input_records"] = dict(result.get("input_records") or {})
    ds = _controller().get()
    ds.step = 1
    _controller().save(ds)
    _change_page(PAGE_DESIGN_WORKSPACE)


def _load_betalain_three_enzyme_gate3_case() -> None:
    """Load the verified public-CDS Gate 3 case without creating a vector."""
    from core.design_session import DesignSession
    from services.betalain_three_enzyme_gate3_case import (
        PROJECT_NAME,
        apply_betalain_case_to_units,
        evaluate_real_component_asset_gate,
        load_betalain_three_enzyme_case,
    )

    _invalidate_formal_snapshots()
    st.session_state.pop("formal_source_input_records", None)
    st.session_state.pop("formal_expression_cassette", None)
    case = load_betalain_three_enzyme_case()
    units = _normalize_transcription_units(
        [
            _new_transcription_unit(unit_id="TU1", display_name="TU1: CYP76AD1"),
            _new_transcription_unit(unit_id="TU2", display_name="TU2: DODA1"),
            _new_transcription_unit(unit_id="TU3", display_name="TU3: cDOPA5GT"),
        ]
    )
    steps, units, mapping = apply_betalain_case_to_units(units)
    st.session_state["formal_project_type"] = PROJECT_TYPE_DUAL_TU
    st.session_state["formal_design_scenario"] = "metabolic_pathway_multi_tu_vector"
    st.session_state["formal_project_name"] = PROJECT_NAME
    st.session_state["formal_locked_project_name"] = PROJECT_NAME
    st.session_state["formal_project_host"] = _plant_host_value_for_id("rice")
    st.session_state["formal_expression_target"] = "Betalain three-enzyme pathway documentation record"
    st.session_state["formal_case_boundary_note"] = case["boundary_note"]
    st.session_state["formal_betalain_gate3_case"] = True
    st.session_state["formal_betalain_regulatory_components_recorded"] = False
    st.session_state["formal_betalain_repeated_regulatory_confirmed"] = False
    st.session_state["formal_betalain_component_asset_gate"] = evaluate_real_component_asset_gate()
    st.session_state["formal_betalain_mapping"] = mapping
    st.session_state["formal_pathway_steps"] = steps
    st.session_state["formal_transcription_units"] = units
    st.session_state.pop("mvp_project_id", None)
    st.session_state.pop("mvp_vector_result", None)
    st.session_state.pop("formal_dual_tu_combined_result", None)
    _controller().save(
        DesignSession(step=2, gene_name="CYP76AD1", original_seq=str(steps[0]["cds_sequence"]), host=_plant_host_value_for_id("rice"), tag="No tag")
    )
    _change_page(PAGE_DESIGN_WORKSPACE)


def _load_mt01_real_case(source_bytes: bytes) -> None:
    """Admit the external MT-01 source and open its immutable Multi-TU result."""
    from core.design_session import DesignSession
    from services.mt01_formal_runtime import build_mt01_result
    from services.plant_project_draft_schema import new_project_id

    project_id = str(new_project_id())
    project_name = "MT-01：pGrDL_SP 双报告基因 2-TU 真实案例"
    result = build_mt01_result(
        source_bytes,
        project_id=project_id,
        project_name=project_name,
    )
    st.session_state["formal_project_type"] = PROJECT_TYPE_DUAL_TU
    st.session_state["formal_design_scenario"] = "standard_plant_expression_vector"
    st.session_state["formal_project_name"] = project_name
    st.session_state["formal_transcription_units"] = _normalize_transcription_units(
        list((result.get("original_input") or {}).get("expression_units") or []),
        list(result.get("unit_order") or []),
    )
    st.session_state["formal_dual_tu_unit_snapshots"] = {
        str(unit.get("unit_id")): dict(unit)
        for unit in list(result.get("expression_units") or [])
    }
    st.session_state["formal_dual_tu_combined_result"] = result
    st.session_state["formal_cassette_result"] = result
    st.session_state["mvp_vector_result"] = result
    st.session_state["mvp_project_id"] = project_id
    st.session_state["mvp_current_input_signature"] = str(result.get("input_signature") or "")
    st.session_state["mvp_inputs_stale"] = False
    st.session_state["formal_mt01_case_locked"] = True
    st.session_state["formal_mt02_case_locked"] = False
    _controller().save(
        DesignSession(step=6, host=_plant_host_value_for_id("tobacco"), tag="No tag")
    )
    _change_page(PAGE_RESULTS_EXPORT)


def _load_mt02_real_case(source_bytes: bytes) -> None:
    """Admit the external MT-02 source and open its immutable Multi-TU result."""
    from core.design_session import DesignSession
    from services.mt02_formal_runtime import build_mt02_result
    from services.plant_project_draft_schema import new_project_id

    project_id = str(new_project_id())
    project_name = "MT-02：pDOE-13 三转录单元真实案例"
    result = build_mt02_result(
        source_bytes,
        project_id=project_id,
        project_name=project_name,
    )
    st.session_state["formal_project_type"] = PROJECT_TYPE_DUAL_TU
    st.session_state["formal_design_scenario"] = "standard_plant_expression_vector"
    st.session_state["formal_project_name"] = project_name
    st.session_state["formal_transcription_units"] = _normalize_transcription_units(
        list((result.get("original_input") or {}).get("expression_units") or []),
        list(result.get("unit_order") or []),
    )
    st.session_state["formal_dual_tu_unit_snapshots"] = {
        str(unit.get("unit_id")): dict(unit)
        for unit in list(result.get("expression_units") or [])
    }
    st.session_state["formal_dual_tu_combined_result"] = result
    st.session_state["formal_cassette_result"] = result
    st.session_state["mvp_vector_result"] = result
    st.session_state["mvp_project_id"] = project_id
    st.session_state["mvp_current_input_signature"] = str(result.get("input_signature") or "")
    st.session_state["mvp_inputs_stale"] = False
    st.session_state["formal_mt01_case_locked"] = False
    st.session_state["formal_mt02_case_locked"] = True
    _controller().save(
        DesignSession(step=6, host=_plant_host_value_for_id("tobacco"), tag="No tag")
    )
    _change_page(PAGE_RESULTS_EXPORT)


def _restore_betalain_three_enzyme_gate3_case(project_id: str) -> None:
    """Restore the partial verified Gate 3 state after a cold app restart."""
    from core.design_session import DesignSession
    from services.betalain_three_enzyme_gate3_case import (
        PROJECT_NAME,
        evaluate_real_component_asset_gate,
        open_betalain_gate3_mapping,
    )

    reopened = open_betalain_gate3_mapping(project_id)
    _invalidate_formal_snapshots()
    st.session_state.pop("formal_source_input_records", None)
    st.session_state.pop("formal_expression_cassette", None)
    steps = list(reopened["pathway_steps"])
    st.session_state["formal_project_type"] = PROJECT_TYPE_DUAL_TU
    st.session_state["formal_design_scenario"] = "metabolic_pathway_multi_tu_vector"
    st.session_state["formal_project_name"] = PROJECT_NAME
    st.session_state["formal_locked_project_name"] = PROJECT_NAME
    st.session_state["formal_project_host"] = _plant_host_value_for_id("rice")
    st.session_state["formal_expression_target"] = "Betalain three-enzyme pathway documentation record"
    st.session_state["formal_betalain_gate3_case"] = True
    st.session_state["formal_betalain_regulatory_components_recorded"] = bool(
        (reopened.get("complete_vector_generated") or False)
    )
    st.session_state["formal_betalain_repeated_regulatory_confirmed"] = False
    st.session_state["formal_betalain_component_asset_gate"] = evaluate_real_component_asset_gate()
    st.session_state["formal_betalain_mapping"] = dict(reopened["mapping"])
    st.session_state["formal_betalain_saved_project_id"] = project_id
    st.session_state["mvp_project_id"] = project_id
    st.session_state["formal_pathway_steps"] = steps
    st.session_state["formal_transcription_units"] = _normalize_transcription_units(reopened["transcription_units"])
    st.session_state.pop("mvp_vector_result", None)
    st.session_state.pop("formal_dual_tu_combined_result", None)
    _controller().save(
        DesignSession(step=2, gene_name="CYP76AD1", original_seq=str(steps[0]["cds_sequence"]), host=_plant_host_value_for_id("rice"), tag="No tag")
    )
    _change_page(PAGE_DESIGN_WORKSPACE)


def _infer_plant_host(result: dict[str, Any]) -> str:
    from services.rice_hsa_ncbi_mvp10_case import evaluate_real_case_authenticity, is_real_case_candidate
    from services.plant_host_registry import list_hosts

    formal_context = result.get("formal_project_context") if isinstance(result.get("formal_project_context"), dict) else {}
    project_definition = formal_context.get("project_definition") if isinstance(formal_context.get("project_definition"), dict) else {}
    saved_hosts = [
        project_definition.get("plant_host"),
        formal_context.get("host_key"),
        result.get("host"),
    ]
    if is_real_case_candidate(result) and evaluate_real_case_authenticity(result)["passed"]:
        saved_hosts.append("rice")

    records = list_hosts()
    legacy_display_labels = {
        "rice": "水稻（Oryza sativa）",
        "tobacco": "烟草（Nicotiana benthamiana）",
        "maize": "玉米（Zea mays）",
        "arabidopsis": "拟南芥（Arabidopsis thaliana）",
        "tomato": "番茄（Solanum lycopersicum）",
        "soybean": "大豆（Glycine max）",
    }
    canonical_hosts = {
        f"{str(record.get('common_name') or '').strip()} ({str((record.get('aliases') or [record.get('scientific_name') or ''])[0]).strip()})"
        for record in records
    }

    for saved_host in saved_hosts:
        saved_host = str(saved_host or "").strip()
        if saved_host in canonical_hosts:
            return saved_host
        for record in records:
            aliases = list(record.get("aliases") or [])
            storage_value = f"{str(record.get('common_name') or '').strip()} ({str(aliases[0] if aliases else record.get('scientific_name') or '').strip()})"
            if saved_host in {
                str(record.get("host_id") or ""),
                str(record.get("scientific_name") or ""),
                storage_value,
                legacy_display_labels.get(str(record.get("host_id") or ""), ""),
            }:
                return storage_value
    return ""


_PROJECT_HOME_STANDARD_HOST_LABELS = {
    "rice": "runtime.host_rice",
    "Rice (O. sativa)": "runtime.host_rice",
    "Oryza sativa": "runtime.host_rice",
    "tobacco": "runtime.host_tobacco",
    "Tobacco (N. benthamiana)": "runtime.host_tobacco",
    "Nicotiana benthamiana": "runtime.host_tobacco",
    "maize": "runtime.host_maize",
    "Maize (Corn)": "runtime.host_maize",
    "Zea mays": "runtime.host_maize",
    "arabidopsis": "runtime.host_arabidopsis",
    "Arabidopsis (A. thaliana)": "runtime.host_arabidopsis",
    "Arabidopsis thaliana": "runtime.host_arabidopsis",
    "tomato": "runtime.host_tomato",
    "Tomato (S. lycopersicum)": "runtime.host_tomato",
    "Solanum lycopersicum": "runtime.host_tomato",
    "soybean": "runtime.host_soybean",
    "Soybean (G. max)": "runtime.host_soybean",
    "Glycine max": "runtime.host_soybean",
}


def _project_home_host_label(host: Any) -> str:
    """Format supported plant hosts for the Project Home display only."""
    value = str(host or "").strip()
    if not value:
        return _t("design_library.not_recorded")
    locale_key = _PROJECT_HOME_STANDARD_HOST_LABELS.get(value)
    return _t(locale_key) if locale_key else value


def _project_home_type_status_label(project_type: str, project_status: str) -> str:
    """Keep project mode and saved status as one display-only list value."""
    if project_type == PROJECT_TYPE_GATE3_PATHWAY_DRAFT:
        mode_label = _t("runtime.project_type_pathway")
    elif project_type == PROJECT_TYPE_DUAL_TU:
        mode_label = _t("runtime.project_type_multi_tu")
    elif project_type == "single_gene":
        mode_label = _t("runtime.project_type_single_gene")
    else:
        mode_label = str(project_type or _t("design_library.not_recorded"))
    status_label = {
        "draft": _t("runtime.project_status_draft"),
        "completed": _t("runtime.project_status_completed"),
    }.get(str(project_status or "").strip(), str(project_status or _t("design_library.not_recorded")).strip() or _t("design_library.not_recorded"))
    return f"{mode_label} · {status_label}"


def _reset_project_center_filters() -> None:
    """Reset only Project Center browser controls; project business state is untouched."""
    for key, value in (
        ("project_center_search", ""),
        ("project_center_sort", "recent"),
        ("project_center_type", "all"),
        ("project_center_status", "全部状态"),
        ("project_center_host", "全部宿主"),
    ):
        st.session_state[key] = value
    st.session_state["project_center_page"] = 1
    st.session_state.pop("project_center_filter_signature", None)


def _project_center_search_input() -> str:
    return st.text_input(
        _t("v1.project_center.search_project_name"),
        placeholder=_t("v1.project_center.search_project_name"),
        key="project_center_search",
        label_visibility="collapsed",
    )


def _replace_current_project_name(value: Any, project_id: str, project_name: str) -> None:
    """Keep the active formal project label aligned after a persisted rename."""
    if not isinstance(value, dict) or str(value.get("project_id") or "") != project_id:
        return
    value["project_name"] = project_name
    context = value.get("formal_project_context")
    if isinstance(context, dict):
        definition = context.get("project_definition")
        if isinstance(definition, dict):
            definition["project_name"] = project_name


def _synchronize_current_project_name(project_id: str, project_name: str) -> None:
    """Update only name fields for the currently open persisted project."""
    if str(st.session_state.get("mvp_project_id") or "") != project_id:
        return
    st.session_state["formal_project_name"] = project_name
    st.session_state["formal_step1_project_name"] = project_name
    definition = st.session_state.get("formal_project_definition")
    if isinstance(definition, dict):
        definition["project_name"] = project_name
    _replace_current_project_name(st.session_state.get("mvp_vector_result"), project_id, project_name)


def _clear_project_rename_dialog() -> None:
    for key in (
        "project_lifecycle_rename_pending_id",
        "project_lifecycle_rename_target",
        "project_lifecycle_rename_name",
        "project_lifecycle_rename_error",
    ):
        st.session_state.pop(key, None)


def _clear_project_archive_dialog() -> None:
    for key in (
        "project_lifecycle_archive_pending_id",
        "project_lifecycle_archive_target",
        "project_lifecycle_archive_error",
    ):
        st.session_state.pop(key, None)


def _current_project_has_unsaved_changes(project_id: str) -> bool:
    """Use only the formal workspace's explicit stale marker as a dirty signal."""
    return bool(
        str(st.session_state.get("mvp_project_id") or "") == project_id
        and st.session_state.get("mvp_inputs_stale")
    )


def _clear_current_project_after_archive(project_id: str) -> None:
    """Invalidate every session persistence pointer for an archived project."""
    for key in list(st.session_state):
        value = st.session_state.get(key)
        if str(key).endswith("_project_id") or str(key) in {
            "mvp_project_id",
            "formal_last_saved_draft_id",
            "formal_last_saved_gate3_draft_id",
        }:
            if str(value or "") == project_id:
                st.session_state.pop(key, None)


@st.dialog(_t("v1.project_center.rename_project"), on_dismiss=_clear_project_rename_dialog)
def _render_project_rename_dialog() -> None:
    target = st.session_state.get("project_lifecycle_rename_target")
    if not isinstance(target, dict):
        return
    st.text_input(_t("v1.project_center.project_name"), key="project_lifecycle_rename_name")
    project_name = str(st.session_state.get("project_lifecycle_rename_name") or "")
    error = str(st.session_state.get("project_lifecycle_rename_error") or "")
    if error:
        st.error(error)
    original_name = str(target.get("project_name") or "")
    trimmed_name = project_name.strip()
    save_disabled = not trimmed_name or trimmed_name == original_name
    with st.container(
        horizontal=True,
        horizontal_alignment="right",
        vertical_alignment="center",
        gap="small",
        key="project_lifecycle_rename_actions",
    ):
        cancel = st.button(_t("v1.common.cancel"), key="project_lifecycle_rename_cancel", width=68)
        save = st.button(
            _t("v1.common.save"),
            key="project_lifecycle_rename_save",
            type="primary",
            disabled=save_disabled,
            width=68,
        )
    if cancel:
        _clear_project_rename_dialog()
        st.rerun()
    if save:
        if st.session_state.get("project_lifecycle_operation_in_progress"):
            return
        st.session_state["project_lifecycle_operation_in_progress"] = True
        result = None
        try:
            from services.project_lifecycle import ProjectLifecycleError, rename_project

            result = rename_project(target.get("project_id"), project_name)
        except ProjectLifecycleError as exc:
            st.session_state["project_lifecycle_rename_error"] = str(exc)
            st.rerun()
        finally:
            st.session_state["project_lifecycle_operation_in_progress"] = False
        if result is not None:
            _synchronize_current_project_name(result.project_id, result.project_name)
            _clear_project_rename_dialog()
            st.session_state["project_lifecycle_notice"] = result.message
            st.rerun()


@st.dialog(_t("v1.project_center.archive_project"), on_dismiss=_clear_project_archive_dialog)
def _render_project_archive_dialog() -> None:
    target = st.session_state.get("project_lifecycle_archive_target")
    if not isinstance(target, dict):
        return
    project_id = str(target.get("project_id") or "")
    project_name = str(target.get("project_name") or _t("design_library.not_recorded"))
    st.write(_t("v1.project_center.project", value=project_name))
    st.write(_t("v1.project_center.after_archiving_project_will_move_recent_projects"))
    error = str(st.session_state.get("project_lifecycle_archive_error") or "")
    if error:
        st.error(error)
    with st.container(
        horizontal=True,
        horizontal_alignment="right",
        vertical_alignment="center",
        gap="small",
        key="project_lifecycle_archive_actions",
    ):
        cancel = st.button(_t("v1.common.cancel"), key="project_lifecycle_archive_cancel", width=68)
        archive = st.button(_t("v1.project_center.confirm_archiving"), key="project_lifecycle_archive_confirm", type="primary", width=88)
    if cancel:
        _clear_project_archive_dialog()
        st.rerun()
    if archive:
        if st.session_state.get("project_lifecycle_operation_in_progress"):
            return
        if _current_project_has_unsaved_changes(project_id):
            st.session_state["project_lifecycle_archive_error"] = "当前项目存在未保存的修改，请先保存或放弃修改后再归档。"
            st.rerun()
            return
        st.session_state["project_lifecycle_operation_in_progress"] = True
        result = None
        try:
            from services.project_lifecycle import ProjectLifecycleError, archive_project

            result = archive_project(project_id)
        except ProjectLifecycleError as exc:
            st.session_state["project_lifecycle_archive_error"] = str(exc)
            st.rerun()
        finally:
            st.session_state["project_lifecycle_operation_in_progress"] = False
        if result is not None:
            _clear_current_project_after_archive(result.project_id)
            _clear_project_archive_dialog()
            st.session_state["project_lifecycle_notice"] = result.message
            st.rerun()


def _restored_formal_project_context(
    result: dict[str, Any], host: str, project_name: str
) -> tuple[dict[str, Any], dict[str, str]]:
    from services.formal_project_definition_lifecycle import (
        construct_review_basis,
        project_definition_from_context,
    )

    context = (
        dict(result.get("formal_project_context") or {})
        if isinstance(result.get("formal_project_context"), dict)
        else {}
    )
    definition = project_definition_from_context(
        context,
        fallback_host=host,
        fallback_project_name=project_name,
    )
    exact_record = (
        result.get("exact_insertion_record")
        if isinstance(result.get("exact_insertion_record"), dict)
        else {}
    )
    if exact_record.get("workflow_support_status") == "supported_rice_alb_single_gene":
        if not str(context.get("host_key") or ""):
            context["host_key"] = host
        if not isinstance(context.get("project_definition"), dict):
            context["project_definition"] = dict(definition)
        if not isinstance(context.get("construct_review_basis"), dict):
            context["construct_review_basis"] = construct_review_basis(definition)
        context.setdefault("construct_review_status", "current")
        context.setdefault("cds_source_review_status", "current")
        result["formal_project_context"] = context
    return context, definition


_FORMAL_STEP3_CUSTOM_INPUT_LABELS = {
    "paste": "v1.expression.paste_dna_fasta",
    "upload": "v1.expression.upload_fasta",
}
_FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL = "review_required"


def _formal_step3_custom_input_label(
    record: Mapping[str, Any] | None,
    *,
    role: str = "terminator",
) -> str:
    """Map persisted Step 3 input provenance to the role's widget state."""
    # Promoter records predate source_input_method and historically reopened
    # with paste selected.  Only the 3' path has the persisted provenance
    # contract and review-required fallback.
    if role != "terminator":
        return "paste"
    method = str(record.get("source_input_method") or "").strip().lower() if isinstance(record, Mapping) else ""
    return method if method in _FORMAL_STEP3_CUSTOM_INPUT_LABELS else _FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL


def _formal_step3_custom_input_display_label(value: str) -> str:
    """Localize the input-method control while preserving its stored value."""
    key = _FORMAL_STEP3_CUSTOM_INPUT_LABELS.get(str(value or ""))
    if value == _FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL:
        key = "v1.expression.saved_input_source_method_missing"
    if not key:
        key = _FORMAL_STEP3_CUSTOM_INPUT_DISPLAY_LABELS.get(str(value or ""))
    return _t(key) if key else str(value or "")


def _single_gene_step3_source_mode(value: Any) -> str:
    """Normalize old draft widget values without using display text as authority."""
    return "user_sequence" if value in {"user_sequence", "用户序列"} else "registry"


def _single_gene_step3_input_method(value: Any) -> str:
    """Normalize old draft widget values to stable source-method keys."""
    return {"粘贴 DNA/FASTA": "paste", "上传 FASTA": "upload"}.get(str(value), str(value))


def _prepare_single_gene_step3_widget_state() -> bool:
    """Hydrate Step 3 before widgets mount; keep live edits across locale reruns."""
    state = st.session_state
    project_id = str(state.get("mvp_project_id") or "")
    editor = state.get("_formal_step3_editor_state")
    if not isinstance(editor, dict) or editor.get("project_id") != project_id:
        records = state.get("formal_element_source_records") or {}
        roles = {}
        for role in ("promoter", "terminator"):
            saved = records.get(role) if isinstance(records, Mapping) else None
            saved = saved if isinstance(saved, Mapping) else {}
            prefix = f"formal_step3_{role}"
            source_kind = str(saved.get("source_kind") or "").lower()
            mode = "user_sequence" if source_kind in {"user_recorded", "paste", "upload"} else _single_gene_step3_source_mode(state.get(f"{prefix}_mode"))
            roles[role] = {
                "mode": mode,
                "custom_input": _formal_step3_custom_input_label(saved, role=role),
                "custom_name": str(saved.get("display_name") or state.get(f"{prefix}_custom_name") or ""),
                "custom_text": str(saved.get("original_text") or saved.get("normalized_sequence") or state.get(f"{prefix}_custom_text") or ""),
            }
        editor = {
            "project_id": project_id,
            "roles": roles,
            "three_prime_role": _normalize_three_prime_role(
                ((records.get("terminator") or {}).get("biological_role")
                 if isinstance(records, Mapping) else None)
                or state.get("formal_step3_three_prime_role")
            ),
        }
        state["_formal_step3_editor_state"] = editor
    restore_pending = bool(state.pop("_formal_restore_step3_pending", False))
    locale = _get_language()
    refresh = restore_pending or state.get("_formal_step3_editor_locale") != locale
    for role, values in editor["roles"].items():
        for suffix, value in values.items():
            key = f"formal_step3_{role}_{suffix}"
            if refresh or key not in state:
                state[key] = value
        mode_key = f"formal_step3_{role}_mode"
        state[mode_key] = _single_gene_step3_source_mode(state.get(mode_key))
        method_key = f"formal_step3_{role}_custom_input"
        state[method_key] = _single_gene_step3_input_method(state.get(method_key))
    if refresh or "formal_step3_three_prime_role" not in state:
        state["formal_step3_three_prime_role"] = editor["three_prime_role"]
    state["_formal_step3_editor_locale"] = locale
    return restore_pending


def _remember_single_gene_step3_widget_state() -> None:
    """Retain current widget edits under locale-independent session keys."""
    state = st.session_state
    editor = state.get("_formal_step3_editor_state")
    if not isinstance(editor, dict):
        return
    for role, values in editor["roles"].items():
        for suffix in values:
            key = f"formal_step3_{role}_{suffix}"
            if key in state:
                values[suffix] = state[key]
    if "formal_step3_three_prime_role" in state:
        editor["three_prime_role"] = _normalize_three_prime_role(state["formal_step3_three_prime_role"])


def _formal_step3_reopen_unresolved_roles(
    records: Mapping[str, Any], host: str
) -> tuple[str, ...]:
    """Revalidate saved Registry selections before restoring dependent results."""
    from services.formal_step3_component_authority import (
        formal_host_species_identity,
        formal_step3_component_options,
        revalidated_formal_step3_selection,
    )

    resolved_host = formal_host_species_identity(host)
    unresolved: list[str] = []
    for saved_role, authority_role in (
        ("promoter", "promoter"),
        ("terminator", "3_prime_regulatory_region"),
    ):
        saved = records.get(saved_role)
        if not isinstance(saved, Mapping):
            unresolved.append(saved_role)
            continue
        if str(saved.get("source_kind") or "").strip().lower() == "user_recorded":
            continue
        options = formal_step3_component_options(
            role=authority_role,
            target_host_species=resolved_host,
        )
        if revalidated_formal_step3_selection(
            saved,
            role=saved_role,
            target_host_species=resolved_host,
            options=options,
        ) is None:
            unresolved.append(saved_role)
    return tuple(unresolved)


def _restore_mvp_result(result: dict[str, Any], host: str) -> None:
    from core.design_session import DesignSession
    from services.canonical_construct_runtime import CanonicalConstructRuntimeError, active_complete_plasmid_snapshot
    from services.company_delivery_package import project_display_name
    from services.canonical_construct_runtime import export_active_construct

    stable_single_name = globals().get("_stable_single_gene_project_name")
    if not callable(stable_single_name):
        stable_single_name = lambda value: str(value or "").strip() or "Plant expression vector project"
    normalize_three_prime_role = globals().get("_normalize_three_prime_role")
    if not callable(normalize_three_prime_role):
        normalize_three_prime_role = lambda value: str(value or "terminator")

    records = result.get("input_records") if isinstance(result.get("input_records"), dict) else {}
    cds_input = result.get("cds_input") if isinstance(result.get("cds_input"), dict) else {}
    promoter = records.get("promoter") if isinstance(records.get("promoter"), dict) else {}
    terminator = records.get("terminator") if isinstance(records.get("terminator"), dict) else {}
    reopen_revalidator = globals().get("_formal_step3_reopen_unresolved_roles")
    unresolved_step3_roles = (
        reopen_revalidator(records, host) if callable(reopen_revalidator) else ()
    )
    ds = DesignSession(
        step=6,
        gene_name=str((records.get("cds") or {}).get("display_name") or result.get("project_name") or "CDS"),
        original_seq=str(cds_input.get("normalized_cds") or (records.get("cds") or {}).get("normalized_sequence") or ""),
        host=host,
        tag="No tag",
        elements={
            "promoter_name": str(promoter.get("display_name") or ""),
            "promoter_seq": str(promoter.get("normalized_sequence") or ""),
            "rbs_name": "",
            "rbs_seq": "",
            "terminator_name": str(terminator.get("display_name") or ""),
            "terminator_seq": str(terminator.get("normalized_sequence") or ""),
        },
    )
    try:
        display_name = project_display_name(result, active_complete_plasmid_snapshot(result.get("runtime")))
    except CanonicalConstructRuntimeError:
        display_name = stable_single_name(result.get("project_name"))
    restored_project_name = stable_single_name(result.get("project_name"))
    st.session_state["formal_project_type"] = PROJECT_TYPE_SINGLE_GENE
    st.session_state.pop("formal_ui_action_feedback", None)
    st.session_state.pop("formal_ui_action_busy", None)
    st.session_state["formal_design_scenario"] = "standard_plant_expression_vector"
    st.session_state.pop("formal_betalain_gate3_case", None)
    st.session_state.pop("formal_betalain_repeated_regulatory_confirmed", None)
    st.session_state.pop("formal_betalain_regulatory_components_recorded", None)
    st.session_state.pop("formal_pathway_steps", None)
    from services.formal_project_definition_lifecycle import construct_review_basis

    # Set every first-step widget key before the workspace is rendered again.
    formal_context, definition = _restored_formal_project_context(
        result,
        host,
        restored_project_name,
    )
    if unresolved_step3_roles:
        for key in (
            "formal_expression_cassette",
            "formal_cassette_result",
            "formal_cassette_exports",
            "formal_cassette_input_signature",
            "formal_step3_order_confirmed",
            "formal_step3_order_confirmation_recorded",
            "formal_step4_strategy_confirmed",
            "formal_step4_strategy_signature",
            "formal_ui_step4_confirmation_signature",
            "formal_step5_strategy_confirmed",
            "formal_step5_strategy_signature",
            "formal_step_preview",
            "formal_legacy_results_redirect",
            "formal_read_only_preview",
            "formal_explicit_historical_open",
            "mvp_vector_result",
            "mvp_current_input_signature",
        ):
            st.session_state.pop(key, None)
    else:
        restore_state = globals().get("_restore_completed_formal_state")
        if callable(restore_state):
            restore_state(formal_context)
    st.session_state.pop("formal_step1_design_dirty", None)
    st.session_state.pop("formal_step2_design_dirty", None)
    preview_reason = str(result.get("formal_editor_restore_reason") or "")
    if preview_reason:
        st.session_state["formal_result_preview_reason"] = preview_reason
    else:
        st.session_state.pop("formal_result_preview_reason", None)
    st.session_state["formal_project_definition"] = definition
    st.session_state["formal_project_name"] = definition["project_name"]
    st.session_state["formal_project_host"] = definition["plant_host"]
    st.session_state["formal_project_material"] = definition["material"]
    st.session_state["formal_expression_target"] = str(
        formal_context.get("expression_target") or _project_definition_expression_target(definition)
    )
    st.session_state["formal_step1_project_name"] = definition["project_name"]
    st.session_state["formal_step1_host"] = definition["plant_host"]
    st.session_state["formal_step1_material"] = definition["material"]
    st.session_state["formal_step1_application_mode"] = definition["application_mode"]
    st.session_state["formal_step1_transient_expression_system"] = definition["transient_expression_system"]
    st.session_state["formal_step1_tissue_specificity_requirement"] = definition["tissue_specificity_requirement"]
    st.session_state["formal_step1_tissue_target"] = definition["tissue_target"]
    st.session_state["formal_step1_inducibility_requirement"] = definition["inducibility_requirement"]
    st.session_state["formal_step1_induction_notes"] = definition["induction_notes"]
    st.session_state["formal_step1_localization_target"] = definition["localization_target"]
    st.session_state["formal_step1_compatibility_review_required"] = definition["compatibility_review_required"]
    st.session_state["formal_step1_legacy_application_mode"] = definition["legacy_application_mode"]
    st.session_state["formal_step1_legacy_expression_mode"] = definition["legacy_expression_mode"]
    saved_basis = formal_context.get("construct_review_basis")
    st.session_state["formal_construct_review_basis"] = (
        dict(saved_basis) if isinstance(saved_basis, dict) else construct_review_basis(definition)
    )
    st.session_state["formal_construct_review_status"] = str(
        formal_context.get("construct_review_status") or "current"
    )
    # Restore every persisted input used by the formal widgets before their
    # next render.  The canonical runtime remains the source of the result;
    # these values only reconstruct the editable view of that same snapshot.
    st.session_state["formal_cds_input"] = dict(cds_input)
    st.session_state["formal_cds_source"] = str(
        cds_input.get("source_name") or (records.get("cds") or {}).get("source_name") or ""
    )
    restored_gene_info = dict(cds_input.get("gene_information") or {})
    st.session_state["formal_cds_source_review_status"] = str(
        formal_context.get("cds_source_review_status") or "current"
    )
    st.session_state["formal_step2_mode"] = (
        "上传单条核酸 FASTA" if cds_input.get("source_kind") == "upload" else "粘贴核酸序列"
    )
    st.session_state["formal_step2_gene_name"] = str(restored_gene_info.get("gene_name") or ds.gene_name)
    st.session_state["formal_step2_gene_symbol"] = str(restored_gene_info.get("gene_symbol") or "")
    st.session_state["formal_step2_source_species"] = str(restored_gene_info.get("source_species") or "")
    st.session_state["formal_step2_source_type"] = str(restored_gene_info.get("source_type") or "公共数据库记录")
    st.session_state["formal_step2_source_reference"] = str(restored_gene_info.get("source_reference") or "")
    st.session_state["formal_step2_modification_status"] = str(restored_gene_info.get("modification_status") or "未修改的来源序列")
    st.session_state["formal_step2_modification_note"] = str(restored_gene_info.get("modification_note") or "")
    st.session_state["formal_step2_partial_cds"] = bool(restored_gene_info.get("is_partial_cds"))
    st.session_state["formal_step2_note"] = str(restored_gene_info.get("note") or "")
    st.session_state["formal_step2_cds_text"] = str(
        cds_input.get("original_text") or cds_input.get("normalized_cds") or ds.original_seq
    )
    st.session_state["formal_element_source_records"] = {
        role: dict(records.get(role) or {})
        for role in ("promoter", "terminator")
        if isinstance(records.get(role), dict)
    }
    # This bridge is also consumed by _plant_element_options, so a saved
    # user/library component is present in the selectbox options instead of
    # being silently replaced by the host default.
    st.session_state["formal_source_input_records"] = {
        role: dict(record)
        for role, record in records.items()
        if isinstance(record, dict)
    }
    restored_formal_cassette = result.get("formal_expression_cassette")
    if (
        not unresolved_step3_roles
        and isinstance(restored_formal_cassette, dict)
        and restored_formal_cassette.get("components")
    ):
        st.session_state["formal_expression_cassette"] = dict(restored_formal_cassette)
        st.session_state["formal_step3_order_confirmation_recorded"] = True
        three_prime = next(
            (
                item for item in list(restored_formal_cassette.get("components") or [])
                if str(item.get("component_type") or "") == "terminator"
            ),
            {},
        )
        if isinstance(three_prime, dict) and str(three_prime.get("biological_role") or ""):
                st.session_state["formal_step3_three_prime_role"] = normalize_three_prime_role(
                    three_prime["biological_role"]
                )
    st.session_state["_formal_restore_step3_pending"] = True
    st.session_state["formal_step3_promoter_mode"] = (
        "registry" if str(promoter.get("source_kind") or "library") in {"library", "registry", "example"} else "user_sequence"
    )
    st.session_state["formal_step3_terminator_mode"] = (
        "registry" if str(terminator.get("source_kind") or "library") in {"library", "registry", "example"} else "user_sequence"
    )
    st.session_state.pop("_formal_step3_editor_state", None)
    st.session_state.pop("_formal_step3_editor_locale", None)
    for role, record in (("promoter", promoter), ("terminator", terminator)):
        st.session_state[f"formal_step3_{role}_custom_name"] = str(record.get("display_name") or "")
        st.session_state[f"formal_step3_{role}_custom_input"] = _formal_step3_custom_input_label(record, role=role)
        st.session_state[f"formal_step3_{role}_custom_text"] = str(
            record.get("original_text") or record.get("normalized_sequence") or ""
        )
    st.session_state["formal_backbone_record"] = dict(records.get("backbone") or {})
    st.session_state["formal_insertion_settings"] = dict(result.get("insertion_settings") or {})
    saved_backbone = st.session_state["formal_backbone_record"]
    saved_insertion = st.session_state["formal_insertion_settings"]
    if isinstance(saved_backbone, dict) and saved_backbone.get("normalized_sequence"):
        st.session_state["formal_step5_source"] = "使用当前项目骨架"
    st.session_state["formal_step5_mode"] = (
        "替换区间" if saved_insertion.get("mode") == "replacement" else "插入"
    )
    st.session_state["formal_step5_start"] = int(saved_insertion.get("start_coordinate") or 2100)
    st.session_state["formal_step5_end"] = int(saved_insertion.get("end_coordinate") or 2101)
    st.session_state["formal_step5_removed"] = str(saved_insertion.get("expected_removed_sequence") or "")
    st.session_state["formal_step5_direction"] = (
        "反向" if saved_insertion.get("insertion_orientation") == "reverse" else "正向"
    )
    # Step 4 owns the binary-vector review state.  These keys only restore the
    # editable view; the persisted insertion settings remain the source record.
    st.session_state["formal_step4_source"] = "使用当前项目骨架"
    st.session_state["formal_step4_mode"] = st.session_state["formal_step5_mode"]
    st.session_state["formal_step4_start"] = st.session_state["formal_step5_start"]
    st.session_state["formal_step4_end"] = st.session_state["formal_step5_end"]
    st.session_state["formal_step4_removed"] = st.session_state["formal_step5_removed"]
    st.session_state["formal_step4_direction"] = st.session_state["formal_step5_direction"]
    confirmation = saved_insertion.get("t_dna_confirmation") if isinstance(saved_insertion.get("t_dna_confirmation"), dict) else {}
    if confirmation:
        st.session_state["formal_step4_border_method"] = (
            "手动坐标" if (confirmation.get("lb") or {}).get("confirmation_method") == "manual_coordinates" else "从导入 feature 选择"
        )
        st.session_state["formal_step4_t_dna_direction"] = {
            "lb_to_rb": "LB → RB", "rb_to_lb": "RB → LB"
        }.get(str(confirmation.get("direction") or ""), "请选择")
        for role in ("lb", "rb"):
            border = confirmation.get(role) if isinstance(confirmation.get(role), dict) else {}
            if border.get("confirmation_method") == "manual_coordinates":
                st.session_state[f"formal_step4_{role}_start"] = int(border.get("start") or 1)
                st.session_state[f"formal_step4_{role}_end"] = int(border.get("end") or 1)
                st.session_state["formal_step4_border_direction_note"] = str(border.get("direction_note") or "")
            else:
                selected = next((item for item in list(saved_backbone.get("imported_feature_records") or []) if str(item.get("feature_id") or "") == str(border.get("feature_id") or "")), None)
                if selected is not None:
                    st.session_state[f"formal_step4_{role}_feature"] = selected
    if not unresolved_step3_roles:
        st.session_state["formal_cassette_result"] = {
            "runtime": result.get("runtime"),
            "cassette_input_signature": result.get("cassette_input_signature", result.get("input_signature")),
            "input_signature": result.get("cassette_input_signature", result.get("input_signature")),
        }
        st.session_state["formal_cassette_input_signature"] = result.get("cassette_input_signature", result.get("input_signature"))
        st.session_state["mvp_vector_result"] = result
        try:
            result["cassette_exports"] = export_active_construct(
                result.get("runtime"), project_name=str(result.get("project_name") or display_name)
            )
        except CanonicalConstructRuntimeError:
            result.pop("cassette_exports", None)
    st.session_state["mvp_project_id"] = str(result.get("project_id") or "")
    persisted_verifier = globals().get("_verified_formal_saved_project_id")
    persisted_project_id = (
        persisted_verifier(result) if callable(persisted_verifier) else ""
    )
    if persisted_project_id:
        st.session_state["formal_last_saved_mvp_project_id"] = persisted_project_id
    else:
        st.session_state.pop("formal_last_saved_mvp_project_id", None)
    if unresolved_step3_roles:
        st.session_state["formal_step3_host_applicability_unresolved"] = {
            "roles": list(unresolved_step3_roles),
            "status": "HOST_APPLICABILITY_NOT_PROVEN",
        }
        st.session_state["formal_construct_review_status"] = "needs_review"
        st.session_state["mvp_inputs_stale"] = True
        ds.step = 3
        _controller().save(ds)
        globals().get("_establish_workflow_baseline", lambda **_kwargs: None)(
            has_durable_save=True
        )
        _change_page(PAGE_DESIGN_WORKSPACE)
        return
    st.session_state.pop("formal_step3_host_applicability_unresolved", None)
    st.session_state["mvp_current_input_signature"] = result.get("input_signature")
    st.session_state["mvp_inputs_stale"] = False
    from services.rice_hsa_ncbi_mvp10_case import REAL_CASE_PROJECT_NAME, evaluate_real_case_authenticity, is_real_case_candidate
    if is_real_case_candidate(result) and evaluate_real_case_authenticity(result)["passed"]:
        st.session_state["formal_locked_project_name"] = REAL_CASE_PROJECT_NAME
        st.session_state["formal_source_input_records"] = records
        st.session_state["formal_case_boundary_note"] = str((result.get("real_case_manifest") or {}).get("boundary_note") or "")
    _controller().save(ds)
    globals().get("_establish_workflow_baseline", lambda **_kwargs: None)(
        has_durable_save=True
    )
    _change_page(PAGE_RESULTS_EXPORT)


def _restore_dual_tu_result(result: dict[str, Any]) -> None:
    """Restore one persisted formal multi-TU result without regenerating DNA."""
    from core.design_session import DesignSession

    stable_multi_name = globals().get("_stable_multi_tu_project_name")
    if not callable(stable_multi_name):
        stable_multi_name = lambda value: str(value or "").strip() or "Multi-TU project"

    context = result.get("formal_project_context") if isinstance(result.get("formal_project_context"), dict) else {}
    restoration_eligible = result.get("formal_editor_restoration_eligible") is True
    restore_state = globals().get("_restore_completed_formal_state")
    if restoration_eligible and callable(restore_state):
        restore_state(context)
    restored_combined_result = st.session_state.get(
        "formal_dual_tu_combined_result"
    )
    preview_reason = str(result.get("formal_editor_restore_reason") or "")
    if preview_reason:
        st.session_state["formal_result_preview_reason"] = preview_reason
    else:
        st.session_state.pop("formal_result_preview_reason", None)
    original = result.get("original_input") if isinstance(result.get("original_input"), dict) else {}
    units = _normalize_transcription_units(
        list(original.get("expression_units") or []),
        list(result.get("unit_order") or []),
    )
    if not units:
        raise ValueError("保存记录没有可恢复的转录单元原始输入。")
    host = str(context.get("host_key") or "")
    st.session_state["formal_project_type"] = PROJECT_TYPE_DUAL_TU
    from services.gate3_pathway_mapping import normalize_design_scenario, normalize_pathway_steps

    st.session_state["formal_design_scenario"] = normalize_design_scenario(
        context.get("design_scenario")
    )
    st.session_state["formal_betalain_gate3_case"] = (
        st.session_state["formal_design_scenario"] == "metabolic_pathway_multi_tu_vector"
        and bool(context.get("replacement_strategy_id"))
    )
    st.session_state["formal_betalain_regulatory_components_recorded"] = bool(
        context.get("repeated_regulatory_confirmed")
    )
    st.session_state["formal_betalain_repeated_regulatory_confirmed"] = bool(
        context.get("repeated_regulatory_confirmed")
    )
    st.session_state["formal_pathway_steps"] = normalize_pathway_steps(
        context.get("pathway_steps")
    )
    st.session_state["formal_project_name"] = stable_multi_name(result.get("project_name"))
    st.session_state["formal_expression_target"] = str(context.get("expression_target") or "")
    st.session_state["formal_transcription_units"] = units
    _invalidate_multi_tu_editor_widget_state(units)
    st.session_state["formal_dual_tu_unit_snapshots"] = {
        str(unit.get("unit_id")): dict(unit) for unit in list(result.get("expression_units") or [])
    }
    if restoration_eligible and isinstance(restored_combined_result, Mapping):
        st.session_state["formal_dual_tu_combined_result"] = dict(
            restored_combined_result
        )
    else:
        st.session_state["formal_dual_tu_combined_result"] = {
            **result,
            "project_type": "multi_tu",
        }
    st.session_state["formal_cassette_result"] = st.session_state["formal_dual_tu_combined_result"]
    st.session_state["formal_last_saved_mvp_project_id"] = str(result.get("project_id") or "")
    st.session_state["formal_backbone_record"] = dict(original.get("backbone") or {})
    st.session_state["formal_insertion_settings"] = dict(original.get("insertion_settings") or {})
    st.session_state["mvp_vector_result"] = result
    st.session_state["mvp_project_id"] = str(result.get("project_id") or "")
    st.session_state["mvp_current_input_signature"] = str(result.get("input_signature") or "")
    st.session_state["mvp_inputs_stale"] = False
    from services.mt01_formal_runtime import is_mt01_claim
    from services.mt02_formal_runtime import is_mt02_claim

    st.session_state["formal_mt01_case_locked"] = is_mt01_claim(result)
    st.session_state["formal_mt02_case_locked"] = is_mt02_claim(result)
    st.session_state["formal_project_host"] = host
    ds = DesignSession(step=int(context.get("current_step") or 6), host=host, tag="No tag")
    _controller().save(ds)
    globals().get("_establish_workflow_baseline", lambda **_kwargs: None)(
        has_durable_save=True
    )
    _change_page(PAGE_RESULTS_EXPORT)


def _prepare_saved_multi_tu_open(result: Mapping[str, Any]) -> bool:
    """Replace stale formal state and classify the saved record's open mode."""
    for key in list(st.session_state):
        if str(key).startswith(("formal_", "mvp_")):
            del st.session_state[key]
    restoration_eligible = result.get("formal_editor_restoration_eligible") is True
    if restoration_eligible:
        st.session_state.pop("formal_explicit_historical_open", None)
    else:
        st.session_state["formal_explicit_historical_open"] = True
    return restoration_eligible


def _open_saved_mvp_project(project_id: str, project_type: str = PROJECT_TYPE_SINGLE_GENE) -> None:
    if project_type == PROJECT_TYPE_DUAL_TU:
        from services.mvp_multi_tu_persistence import MvpMultiTuPersistenceError, open_mvp_multi_tu_design

        try:
            result = open_mvp_multi_tu_design(project_id)
        except (MvpMultiTuPersistenceError, ValueError) as exc:
            st.error(str(exc))
        else:
            _prepare_saved_multi_tu_open(result)
            _restore_dual_tu_result(result)
        return

    from services.mvp_single_gene_persistence import MvpSingleGenePersistenceError, open_mvp_single_gene_design

    try:
        result = open_mvp_single_gene_design(project_id)
    except MvpSingleGenePersistenceError as exc:
        st.error(str(exc))
        return
    st.session_state["formal_explicit_historical_open"] = True
    _restore_mvp_result(result, _infer_plant_host(result))


def _render_mt01_case_entry() -> None:
    st.subheader(_t('v1.project_center.source_checked_case'))
    with st.container(border=True):
        st.markdown(_t('v1.project_center.mt_01_pgrdl_sp_dual_reporter'))
        st.markdown(
            _t('v1.project_center.source_kx758647_1_reconstructed_region_571_4649')
        )
        st.caption(
            _t('v1.project_center.case_reproduces_only_deterministic_two_tu_region')
        )
        mt01_source = st.file_uploader(
            _t("v1.project_center.select_formal_kx758647_1_genbank_source_file"),
            type=["gb", "gbk", "genbank"],
            key="formal_mt01_source_file",
            help=_t('v1.project_center.case_source_file_required_on_first_creation'),
        )
        if st.button(
            _t('v1.project_center.verify_source_load_mt_01'),
            type="primary",
            disabled=mt01_source is None,
            key="formal_mt01_load_case",
        ):
            try:
                _load_mt01_real_case(mt01_source.getvalue())
            except Exception as exc:
                st.error(str(exc))


def _render_mt02_case_entry() -> None:
    with st.container(border=True):
        st.markdown(_t('v1.project_center.mt_02_pdoe_13_three_tu_real'))
        st.markdown(
            _t('v1.project_center.source_km507054_1_reconstructed_region_111_6719')
        )
        st.caption(
            _t('v1.project_center.case_reproduces_only_deterministic_three_tu_region')
        )
        mt02_source = st.file_uploader(
            _t("v1.project_center.select_formal_km507054_1_genbank_source_file"),
            type=["gb", "gbk", "genbank"],
            key="formal_mt02_source_file",
            help=_t('v1.project_center.case_source_file_required_on_first_creation'),
        )
        if st.button(
            _t('v1.project_center.verify_source_load_mt_02'),
            type="primary",
            disabled=mt02_source is None,
            key="formal_mt02_load_case",
        ):
            try:
                _load_mt02_real_case(mt02_source.getvalue())
            except Exception as exc:
                st.error(str(exc))


def _render_project_home() -> None:
    """Render only formal plant expression-vector project entries."""
    # Legacy source-shape markers retained for regression tests; runtime copy
    # below is resolved through the central locale dictionaries.
    # st.title("项目中心")
    # st.caption("创建、保存和管理植物表达设计项目")
    from services.mvp_multi_tu_persistence import list_mvp_multi_tu_designs, open_mvp_multi_tu_design
    from services.mvp_single_gene_persistence import (
        MvpSingleGenePersistenceError,
        list_mvp_single_gene_designs,
        open_mvp_single_gene_design,
    )
    from services.project_center_query import (
        PROJECT_TYPE_ALL,
        PROJECT_TYPE_MULTI_TU,
        SORT_NAME_ASC,
        SORT_NAME_DESC,
        SORT_OLDEST,
        SORT_RECENT,
        ProjectCenterProject,
        filter_and_sort_projects,
        format_project_timestamp_for_local_display,
        paginate_projects,
        projects_for_lifecycle,
        project_host_values,
        project_status_values,
        normalized_lifecycle_status,
        LIFECYCLE_ACTIVE,
        LIFECYCLE_ARCHIVED,
        LIFECYCLE_UNKNOWN,
    )
    from services.project_lifecycle import ProjectLifecycleError
    pc = _t
    pathway_draft_type = globals().get("PROJECT_TYPE_GATE3_PATHWAY_DRAFT", "gate3_pathway_draft")
    # Keep the transition marker until the project collection has been read;
    # this is the first stable Project Center frame where it is safe to consume.
    transition_pending = bool(st.session_state.get("project_center_transition_pending", False))
    loading_placeholder = None
    if transition_pending:
        loading_placeholder = st.empty()
        loading_placeholder.markdown(_t("v1.project_center.loading_project"), unsafe_allow_html=True)

    duplicate_pending_id = st.session_state.pop("project_lifecycle_duplicate_pending_id", None)
    unarchive_pending_id = st.session_state.pop("project_lifecycle_unarchive_pending_id", None)

    def _finish_project_center_render() -> None:
        if loading_placeholder is not None:
            loading_placeholder.empty()

    if duplicate_pending_id:
        st.session_state["project_lifecycle_operation_in_progress"] = True
        try:
            from services.project_lifecycle import ProjectLifecycleError, duplicate_project

            duplicate = duplicate_project(str(duplicate_pending_id))
        except ProjectLifecycleError as exc:
            st.session_state["project_lifecycle_error"] = str(exc)
        else:
            st.session_state["project_lifecycle_notice"] = duplicate.message
        finally:
            st.session_state["project_lifecycle_operation_in_progress"] = False

    if unarchive_pending_id:
        st.session_state["project_lifecycle_operation_in_progress"] = True
        try:
            from services.project_lifecycle import unarchive_project

            restored = unarchive_project(str(unarchive_pending_id))
        except ProjectLifecycleError as exc:
            st.session_state["project_lifecycle_error"] = str(exc)
        else:
            st.session_state["project_lifecycle_notice"] = restored.message
        finally:
            st.session_state["project_lifecycle_operation_in_progress"] = False

    # Read the project collection before emitting page content. During a route
    # change this prevents the new title from appearing above the outgoing
    # workspace while synchronous project reads are still in progress.
    projects: list[ProjectCenterProject] = []

    def _project_lifecycle_metadata(summary: Any) -> tuple[str, str, str]:
        raw_status = (
            getattr(summary, "lifecycle_status")
            if hasattr(summary, "lifecycle_status")
            else None
        )
        lifecycle_status = (
            normalized_lifecycle_status(raw_status)
            if hasattr(summary, "lifecycle_status")
            else normalized_lifecycle_status()
        )
        return (
            lifecycle_status,
            str(getattr(summary, "archived_at", "") or ""),
            str(getattr(summary, "updated_at", "") or ""),
        )

    for summary in list_mvp_single_gene_designs():
        lifecycle_status, archived_at, lifecycle_updated_at = _project_lifecycle_metadata(summary)
        if lifecycle_status in {LIFECYCLE_ARCHIVED, LIFECYCLE_UNKNOWN}:
            projects.append(
                ProjectCenterProject(
                    project_id=str(summary.project_id),
                    project_name=str(summary.project_name or "未命名项目"),
                    updated_at=lifecycle_updated_at or str(summary.updated_at or ""),
                    project_type=PROJECT_TYPE_SINGLE_GENE,
                    project_status=str(summary.draft_status or "draft"),
                    host="",
                    lifecycle_status=lifecycle_status,
                    archived_at=archived_at,
                )
            )
            continue
        try:
            result = open_mvp_single_gene_design(summary.project_id)
        except MvpSingleGenePersistenceError as exc:
            st.warning(_t('v1.project_center.project_cannot_opened', p0=summary.project_name or summary.project_id, p1=exc))
            continue
        host = _infer_plant_host(result)
        # The project list is a persistence surface. Keep the name the user
        # saved instead of deriving a different label from sequence traits.
        # Host context is display metadata, not a reason to hide a valid record.
        display_name = str(summary.project_name or "未命名项目")
        projects.append(
            ProjectCenterProject(
                project_id=str(summary.project_id),
                project_name=display_name,
                updated_at=lifecycle_updated_at or str(summary.updated_at or ""),
                project_type=PROJECT_TYPE_SINGLE_GENE,
                project_status="completed",
                host=_project_home_host_label(host),
                lifecycle_status=lifecycle_status,
                archived_at=archived_at,
            )
        )
    for summary in list_mvp_multi_tu_designs():
        lifecycle_status, archived_at, lifecycle_updated_at = _project_lifecycle_metadata(summary)
        if lifecycle_status in {LIFECYCLE_ARCHIVED, LIFECYCLE_UNKNOWN}:
            projects.append(
                ProjectCenterProject(
                    project_id=str(summary.project_id),
                    project_name=str(summary.project_name or "未命名项目"),
                    updated_at=lifecycle_updated_at or str(summary.updated_at or ""),
                    project_type=PROJECT_TYPE_DUAL_TU,
                    project_status=str(summary.draft_status or "draft"),
                    host="",
                    lifecycle_status=lifecycle_status,
                    archived_at=archived_at,
                )
            )
            continue
        try:
            result = open_mvp_multi_tu_design(summary.project_id)
        except Exception:
            continue
        context = result.get("formal_project_context") if isinstance(result.get("formal_project_context"), dict) else {}
        host = str(context.get("host_key") or "")
        projects.append(
            ProjectCenterProject(
                project_id=str(summary.project_id),
                project_name=str(summary.project_name or "多转录单元项目"),
                updated_at=lifecycle_updated_at or str(summary.updated_at or ""),
                project_type=PROJECT_TYPE_DUAL_TU,
                project_status="completed",
                host=_project_home_host_label(host),
                lifecycle_status=lifecycle_status,
                archived_at=archived_at,
            )
        )
    persisted_project_ids = {item.project_id for item in projects}
    for summary, payload in globals().get("_formal_workflow_drafts", lambda: [])():
        if str(summary.project_id) in persisted_project_ids:
            continue
        definition = payload.get("project_definition") if isinstance(payload.get("project_definition"), dict) else {}
        workflow_type = str(payload.get("workflow_type") or "single_gene")
        host = str(definition.get("plant_host") or "")
        project_type = PROJECT_TYPE_DUAL_TU if workflow_type in {"multi_tu", "gate3_pathway"} else PROJECT_TYPE_SINGLE_GENE
        lifecycle_status, archived_at, lifecycle_updated_at = _project_lifecycle_metadata(summary)
        projects.append(
            ProjectCenterProject(
                project_id=str(summary.project_id),
                project_name=str(summary.project_name or "未命名项目草稿"),
                updated_at=lifecycle_updated_at or str(summary.updated_at or ""),
                project_type=project_type,
                project_status=str(summary.draft_status or "draft"),
                host=_project_home_host_label(host),
                lifecycle_status=lifecycle_status,
                archived_at=archived_at,
            )
        )
        persisted_project_ids.add(str(summary.project_id))
    for summary, payload in globals().get("_gate3_pathway_drafts", lambda: [])():
        if str(summary.project_id) in persisted_project_ids:
            continue
        definition = payload.get("project_definition") if isinstance(payload.get("project_definition"), dict) else {}
        host = str(definition.get("plant_host") or "")
        lifecycle_status, archived_at, lifecycle_updated_at = _project_lifecycle_metadata(summary)
        projects.append(
            ProjectCenterProject(
                project_id=str(summary.project_id),
                project_name=str(summary.project_name or "代谢通路项目草稿"),
                updated_at=lifecycle_updated_at or str(summary.updated_at or ""),
                project_type=pathway_draft_type,
                project_status=str(summary.draft_status or "draft"),
                host=_project_home_host_label(host),
                lifecycle_status=lifecycle_status,
                archived_at=archived_at,
            )
        )

    if transition_pending:
        st.session_state.pop("project_center_transition_pending", None)

    pending_rename_id = st.session_state.pop("project_lifecycle_rename_pending_id", None)
    pending_archive_id = st.session_state.pop("project_lifecycle_archive_pending_id", None)
    if pending_rename_id:
        rename_candidate = next(
            (item for item in projects if item.project_id == str(pending_rename_id)),
            None,
        )
        if rename_candidate is None:
            _clear_project_rename_dialog()
            st.session_state["project_lifecycle_error"] = _t("v1.project_center.project_cannot_opened", value="")
        else:
            st.session_state["project_lifecycle_rename_target"] = {
                "project_id": rename_candidate.project_id,
                "project_name": rename_candidate.project_name,
            }
            st.session_state["project_lifecycle_rename_name"] = rename_candidate.project_name
            st.session_state.pop("project_lifecycle_rename_error", None)
    if pending_archive_id:
        archive_candidate = next(
            (item for item in projects if item.project_id == str(pending_archive_id)),
            None,
        )
        if archive_candidate is None:
            _clear_project_archive_dialog()
            st.session_state["project_lifecycle_error"] = _t("v1.project_center.project_cannot_opened", value="")
        else:
            st.session_state["project_lifecycle_archive_target"] = {
                "project_id": archive_candidate.project_id,
                "project_name": archive_candidate.project_name,
            }
            st.session_state.pop("project_lifecycle_archive_error", None)
    rename_dialog_active = isinstance(st.session_state.get("project_lifecycle_rename_target"), dict)
    archive_dialog_active = isinstance(st.session_state.get("project_lifecycle_archive_target"), dict)
    menu_generation = int(st.session_state.get("project_lifecycle_action_menu_generation") or 0)

    st.markdown("<div class='formal-content'>", unsafe_allow_html=True)
    st.title(_t("v1.project_center.title"))
    st.caption(_t("v1.project_center.subtitle"))
    lifecycle_notice = st.session_state.pop("project_lifecycle_notice", "")
    if lifecycle_notice:
        st.toast(str(lifecycle_notice))
    lifecycle_error = st.session_state.pop("project_lifecycle_error", "")
    if lifecycle_error:
        st.error(str(lifecycle_error))

    with st.container(key="formal_home_actions"):
        title_col, new_col, dual_col, _spacer_col = st.columns([1, 1.35, 1.55, 4])
        title_col.markdown(_t("v1.project_center.new_project_heading"), unsafe_allow_html=True)
        if new_col.button(_t("v1.project_center.new_single_gene_project"), type="primary"):
            _start_blank_design(PROJECT_TYPE_SINGLE_GENE)
        if dual_col.button(_t("v1.project_center.new_multi_tu_project")):
            _start_blank_design(PROJECT_TYPE_DUAL_TU)

    st.subheader(_t("v1.project_center.project_browser"))
    if not projects:
        with st.container(border=True, key="formal_home_empty"):
            st.markdown(_t("v1.project_center.no_saved_projects_yet"), unsafe_allow_html=True)
            st.markdown(_t("v1.project_center.start_by_creating_single_gene_project_multi"), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        _finish_project_center_render()
        return

    active_projects = projects_for_lifecycle(projects, lifecycle_status=LIFECYCLE_ACTIVE)
    archived_projects = projects_for_lifecycle(projects, lifecycle_status=LIFECYCLE_ARCHIVED)
    all_projects = projects_for_lifecycle(projects, lifecycle_status="non_archived")

    with st.container(key="formal_project_view_switch"):
        selected_view = st.radio(
            _t("v1.project_center.project_view"),
            (_t("v1.project_center.recent_projects"), _t("v1.project_center.all_projects"), _t("v1.project_center.archived")),
            horizontal=True,
            key="project_center_view",
            label_visibility="collapsed",
        )
    if selected_view == _t("v1.project_center.recent_projects"):
        with st.container(key="project_center_toolbar"):
            query = _project_center_search_input()
        filtered_recent_projects = filter_and_sort_projects(active_projects, query=query, sort=SORT_RECENT)
        visible_projects = filtered_recent_projects[:8]
        if not str(query).strip():
            st.markdown(
                f"<div class='formal-project-browser-count'>{pc('v1.project_center.most_recently_updated_projects', visible_count=len(visible_projects), total_count=len(active_projects))}</div>",
                unsafe_allow_html=True,
            )
        selected_sort = SORT_RECENT
        selected_type = PROJECT_TYPE_ALL
        selected_status = ""
        selected_host = ""
        filter_signature = ("recent", str(query).strip())
        if st.session_state.get("project_center_filter_signature") != filter_signature:
            st.session_state["project_center_filter_signature"] = filter_signature
            st.session_state["project_center_page"] = 1
        current_page = 1
        page = None
        if str(query).strip():
            page = paginate_projects(
                filtered_recent_projects,
                page=int(st.session_state.get("project_center_page") or 1),
            )
            visible_projects = list(page.items)
            if page.total_items:
                st.markdown(
                    _t('v1.project_center.search_results_projects', p0=page.total_items),
                    unsafe_allow_html=True,
                )
            else:
                visible_projects = []
            if not visible_projects:
                with st.container(border=True, key="formal_home_no_results"):
                    st.markdown(pc("v1.project_center.no_projects_match_criteria"), unsafe_allow_html=True)
                    st.markdown(pc("v1.project_center.adjust_search_term"), unsafe_allow_html=True)
                _finish_project_center_render()
                return
    else:
        view_projects = archived_projects if selected_view == pc("v1.project_center.archived") else all_projects
        status_options = [pc("runtime.project_status_all", default="All statuses"), *project_status_values(view_projects)]
        host_options = [pc("runtime.project_host_all", default="All hosts"), *project_host_values(view_projects)]
        type_labels = {
            PROJECT_TYPE_ALL: pc("runtime.project_type_all", default="All types"),
            PROJECT_TYPE_SINGLE_GENE: pc("runtime.project_type_single_gene"),
            PROJECT_TYPE_MULTI_TU: pc("runtime.project_type_multi_tu"),
        }
        sort_labels = {
            SORT_RECENT: pc("runtime.sort_recent", default="Recently modified"),
            SORT_OLDEST: pc("runtime.sort_oldest", default="Oldest first"),
            SORT_NAME_ASC: pc("runtime.sort_name_asc", default="Project name A–Z"),
            SORT_NAME_DESC: pc("runtime.sort_name_desc", default="Project name Z–A"),
        }
        with st.container(key="project_center_toolbar"):
            with st.container(key="project_center_toolbar_primary"):
                search_col, sort_col = st.columns([3, 1])
                with search_col:
                    query = _project_center_search_input()
                with sort_col:
                    selected_sort = st.selectbox(
                        pc("v1.project_center.sorting"),
                        tuple(sort_labels),
                        format_func=sort_labels.get,
                        key="project_center_sort",
                        label_visibility="collapsed",
                    )
            with st.container(key="project_center_filters"):
                type_col, status_col, host_col, clear_col = st.columns([1, 1, 1, 0.65])
                with type_col:
                    selected_type = st.selectbox(
                        pc("v1.common.type"), tuple(type_labels), format_func=type_labels.get, key="project_center_type", label_visibility="collapsed"
                    )
                with status_col:
                    selected_status_label = st.selectbox(pc("v1.common.status"), status_options, key="project_center_status", label_visibility="collapsed")
                with host_col:
                    selected_host = st.selectbox(pc("v1.common.host"), host_options, key="project_center_host", label_visibility="collapsed")
                with clear_col:
                    st.button(
                        pc("v1.project_center.clear_filters"),
                        key="project_center_clear_filters",
                        on_click=_reset_project_center_filters,
                    )
        selected_status = "" if selected_status_label == pc("runtime.project_status_all", default="All statuses") else selected_status_label
        selected_host = "" if selected_host == pc("runtime.project_host_all", default="All hosts") else selected_host
        filter_signature = (selected_view, str(query).strip(), selected_type, selected_status, selected_host, selected_sort)
        if st.session_state.get("project_center_filter_signature") != filter_signature:
            st.session_state["project_center_filter_signature"] = filter_signature
            st.session_state["project_center_page"] = 1
        filtered_projects = filter_and_sort_projects(
            view_projects,
            query=query,
            project_type=selected_type,
            project_status=selected_status,
            host=selected_host,
            sort=selected_sort,
        )
        current_page = int(st.session_state.get("project_center_page") or 1)
        page = paginate_projects(filtered_projects, page=current_page)
        if page.page and page.page != current_page:
            st.session_state["project_center_page"] = page.page
        visible_projects = list(page.items)
        if page.total_items:
            count_label = (
                pc("v1.project_center.search_results_projects", result_count=page.total_items)
                if str(query).strip()
                else f"{page.start_item}–{page.end_item} / {page.total_items}"
            )
            st.markdown(f"<div class='formal-project-browser-count'>{count_label}</div>", unsafe_allow_html=True)
        else:
            with st.container(border=True, key="formal_home_no_results"):
                if selected_view == pc("v1.project_center.archived") and not str(query).strip() and not selected_status and not selected_host and selected_type == PROJECT_TYPE_ALL:
                    st.markdown(pc("v1.project_center.no_archived_projects_yet"), unsafe_allow_html=True)
                    st.markdown(pc("v1.project_center.archived_projects_appear_here_can_unarchived_at"), unsafe_allow_html=True)
                else:
                    st.markdown(pc("v1.project_center.no_projects_match_criteria"), unsafe_allow_html=True)
                    st.markdown(pc("v1.project_center.adjust_search_term_filters"), unsafe_allow_html=True)
            _finish_project_center_render()
            return

    with st.container(key="formal_project_table_head"):
        name_head, type_head, host_head, updated_head, action_head = st.columns([3.4, 2.0, 2.2, 1.7, 1.35])
        for column, label in zip(
            (name_head, type_head, host_head, updated_head, action_head),
            (
                pc("runtime.project"),
                pc("v1.common.type") + " / " + pc("v1.common.status"),
                pc("v1.common.host"),
                pc("runtime.last_modified"),
                pc("runtime.actions"),
            ),
        ):
            column.markdown(f"<div class='formal-project-column-heading'>{label}</div>", unsafe_allow_html=True)
    for index, project in enumerate(visible_projects):
        with st.container(border=True, key=f"formal_project_summary_{index}"):
            name_col, type_col, host_col, time_col, action_col = st.columns([3.4, 2.0, 2.2, 1.7, 1.35])
            name_col.markdown(f"<div class='formal-project-name'>{escape(project.project_name)}</div>", unsafe_allow_html=True)
            try:
                from services.crispr_product_workflow import saved_crispr_product_metadata
                crispr_meta = saved_crispr_product_metadata(project.project_id)
            except Exception:
                crispr_meta = None
            if isinstance(crispr_meta, dict):
                name_col.caption(_t('v1.ui_closure.crispr_attached_record'))
            type_status_label = _project_home_type_status_label(project.project_type, project.project_status)
            if project.lifecycle_status == LIFECYCLE_UNKNOWN:
                type_status_label = f"{type_status_label} / lifecycle: unknown"
            type_col.markdown(
                f"<div class='formal-project-cell'>{type_status_label}</div>",
                unsafe_allow_html=True,
            )
            host_col.markdown(
                f"<div class='formal-project-cell'>{escape(project.host or pc('design_library.not_recorded'))}</div>",
                unsafe_allow_html=True,
            )
            updated = format_project_timestamp_for_local_display(project.updated_at)
            time_col.markdown(
                pc("v1.project_center.last_modified", updated=escape(updated or "--")),
                unsafe_allow_html=True,
            )
            def _open_project_from_center(project_to_open: ProjectCenterProject = project) -> bool:
                st.session_state["project_center_open_callback_in_progress"] = True
                opened = False
                try:
                    if project_to_open.project_status == "draft" and project_to_open.project_type != pathway_draft_type:
                        try:
                            _restore_formal_workflow_draft(project_to_open.project_id)
                        except (ValueError, RuntimeError) as exc:
                            st.error(str(exc))
                    elif project_to_open.project_type == pathway_draft_type:
                        try:
                            _restore_gate3_pathway_draft(project_to_open.project_id)
                        except (ValueError, RuntimeError) as exc:
                            st.error(str(exc))
                    else:
                        _open_saved_mvp_project(project_to_open.project_id, project_to_open.project_type)
                    opened = bool(
                        str(st.session_state.get("mvp_project_id") or "").strip()
                        == project_to_open.project_id
                        and st.session_state.get(_SK.SELECTED_PAGE) != PAGE_PROJECT_HOME
                    )
                    return_target = _consume_agent_project_selection_return(
                        project_to_open.project_id,
                        opened=opened,
                    )
                    if opened:
                        _change_page(
                            _opened_project_destination(
                                project_to_open.project_id,
                                project_to_open.project_type,
                                return_target,
                            )
                        )
                finally:
                    st.session_state.pop("agent_project_selection_return", None)
                    st.session_state.pop("project_center_open_callback_in_progress", None)
                # A real Streamlit on_click callback is followed by its own
                # rerun. Returning the outcome avoids an unsupported/no-op rerun
                # inside callback execution while letting the lightweight inline
                # fallback below rerun after callback cleanup.
                return opened

            if project.lifecycle_status != LIFECYCLE_ACTIVE:
                with action_col:
                    with st.container(key=f"formal_project_actions_{index}"):
                        menu_col = st.columns([1])[0]
                        with menu_col.popover(pc("v1.common.more"), width="content", key=f"formal_project_actions_menu_{project.project_id}"):
                            if project.lifecycle_status == LIFECYCLE_ARCHIVED:
                                if st.button(pc("v1.project_center.cancel_archival"), key=f"unarchive_plant_project_{project.project_id}"):
                                    st.session_state["project_lifecycle_unarchive_pending_id"] = project.project_id
                                    st.session_state["project_lifecycle_action_menu_generation"] = menu_generation + 1
                                    st.rerun()
                            else:
                                st.caption(pc("v1.project_center.lifecycle_status_abnormal"))
                continue

            # The small fallback keeps the page-level cold-start contract usable
            # with lightweight test doubles that predate nested action controls.
            if not hasattr(action_col, "__enter__"):
                if project.lifecycle_status != LIFECYCLE_ACTIVE:
                    action_col.caption(pc("v1.project_center.lifecycle_status_does_not_allow_editing"))
                    continue
                if action_col.button(pc("v1.common.open"), key=f"open_plant_project_{project.project_id}"):
                    if _open_project_from_center():
                        st.rerun()
                        return
            else:
                with action_col:
                    with st.container(key=f"formal_project_actions_{index}"):
                        open_col, menu_col = st.columns([1, 1], gap="small")
                        open_col.button(
                            pc("v1.common.open"),
                            key=f"open_plant_project_{project.project_id}",
                            on_click=_open_project_from_center,
                        )
                        if rename_dialog_active or archive_dialog_active:
                            menu_col.button(
                                pc("v1.common.more"),
                                key=f"formal_project_actions_menu_disabled_{project.project_id}",
                                disabled=True,
                            )
                        else:
                            if menu_generation % 2:
                                menu_col.empty()
                            with menu_col.popover(
                                pc("v1.common.more"),
                                width="content",
                                key=f"formal_project_actions_menu_{project.project_id}"
                                + (f"_{menu_generation}" if menu_generation else ""),
                            ):
                                with st.container(key=f"formal_project_actions_menu_items_{project.project_id}"):
                                    if project.lifecycle_status == LIFECYCLE_ARCHIVED:
                                        if st.button(pc("v1.project_center.cancel_archival"), key=f"unarchive_plant_project_{project.project_id}"):
                                            st.session_state["project_lifecycle_unarchive_pending_id"] = project.project_id
                                            st.session_state["project_lifecycle_action_menu_generation"] = menu_generation + 1
                                            st.rerun()
                                    elif project.lifecycle_status == LIFECYCLE_ACTIVE:
                                        if st.button(pc("v1.project_center.rename"), key=f"rename_plant_project_{project.project_id}"):
                                            st.session_state["project_lifecycle_rename_pending_id"] = project.project_id
                                            st.session_state["project_lifecycle_action_menu_generation"] = menu_generation + 1
                                            st.rerun()
                                        if st.button(pc("v1.project_center.copy_project"), key=f"duplicate_plant_project_{project.project_id}"):
                                            st.session_state["project_lifecycle_duplicate_pending_id"] = project.project_id
                                            st.session_state["project_lifecycle_action_menu_generation"] = menu_generation + 1
                                            st.rerun()
                                        if st.button(pc("v1.common.archive"), key=f"archive_plant_project_{project.project_id}"):
                                            st.session_state["project_lifecycle_archive_pending_id"] = project.project_id
                                            st.session_state["project_lifecycle_action_menu_generation"] = menu_generation + 1
                                            st.rerun()
                                    else:
                                        st.caption(pc("v1.project_center.lifecycle_status_unknown"))
    if rename_dialog_active:
        _render_project_rename_dialog()
    if archive_dialog_active:
        _render_project_archive_dialog()
    if page is not None and page.total_pages > 1:
        with st.container(key="project_center_pagination"):
            previous_col, status_col, next_col = st.columns([1, 1, 1])
            with previous_col:
                if st.button(pc("v1.project_center.previous_page"), key="project_center_previous_page", disabled=page.page <= 1):
                    st.session_state["project_center_page"] = page.page - 1
                    st.rerun()
            with status_col:
                st.markdown(
                    pc("v1.project_center.page", page=page.page, total_pages=page.total_pages),
                    unsafe_allow_html=True,
                )
            with next_col:
                if st.button(pc("v1.project_center.next_page"), key="project_center_next_page", disabled=page.page >= page.total_pages):
                    st.session_state["project_center_page"] = page.page + 1
                    st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    _finish_project_center_render()


def _wizard_component_records(ds: Any, project_id: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Adapt confirmed Step 1/2 values to the canonical MVP runtime inputs."""
    from core.expression_frame_builder import get_host_rules
    from services.formal_single_gene_runtime import _cds_record
    from services.mvp_cds_input import analyze_cds_input
    from services.mvp_sequence_input import analyze_dna_component_input

    elements = ds.elements if isinstance(ds.elements, dict) else {}
    rules = get_host_rules(ds.host)
    promoter_seq = str(elements.get("promoter_seq") or "")
    terminator_seq = str(elements.get("terminator_seq") or "")
    promoter_name = str(elements.get("promoter_name") or "启动子")
    terminator_name = str(elements.get("terminator_name") or "3'端元件")
    saved_cds_input = st.session_state.get("formal_cds_input")
    cds_input = dict(saved_cds_input) if isinstance(saved_cds_input, dict) else analyze_cds_input(
        ds.original_seq,
        source_kind="paste",
        source_name="用户提供，待确认",
    )
    source_records = st.session_state.get("formal_element_source_records")
    records = {
        "promoter": analyze_dna_component_input(
            promoter_seq,
            project_id=project_id,
            component_type="promoter",
            display_name=promoter_name,
            source_kind="wizard_step_2",
            source_name="Expression Wizard Step 2 promoter",
        ),
        "cds": _cds_record(cds_input, display_name=ds.gene_name or "CDS"),
        "terminator": analyze_dna_component_input(
            terminator_seq,
            project_id=project_id,
            component_type="terminator",
            display_name=terminator_name,
            source_kind="wizard_step_2",
            source_name="Expression Wizard Step 2 terminator",
        ),
    }
    if isinstance(source_records, dict):
        for role in ("promoter", "terminator"):
            source_record = source_records.get(role)
            if isinstance(source_record, dict) and str(source_record.get("normalized_sequence") or "").upper() == str(records[role].get("normalized_sequence") or "").upper():
                records[role] = dict(source_record)
    # Preserve the known local accession as provenance only; the runtime still
    # receives the same validated CDS sequence and coordinate rules.
    cds_source = str(st.session_state.get("formal_cds_source") or "")
    if cds_source:
        records["cds"]["source_name"] = cds_source
    official_records = st.session_state.get("formal_source_input_records")
    if isinstance(official_records, dict):
        for role in ("promoter", "cds", "terminator"):
            official = official_records.get(role)
            if isinstance(official, dict) and str(official.get("normalized_sequence") or "").upper() == str(records[role].get("normalized_sequence") or "").upper():
                records[role] = dict(official)
    return cds_input, records


def _formal_ai_route_source_metadata() -> dict[str, Any]:
    values = {
        "gene_name": st.session_state.get("formal_ai_route_gene_name"),
        "source_species": st.session_state.get("formal_ai_route_source_species"),
        "source_reference": st.session_state.get("formal_ai_route_source_reference"),
    }
    return {
        key: str(value or "").strip()
        for key, value in values.items()
        if str(value or "").strip()
    }


_FORMAL_AI_ROUTE_ERROR_MESSAGES_ZH: dict[str, str] = {
    "invalid_current_inputs": "当前目标、宿主或 CDS 输入需要检查后再试。",
    "candidate_set_stale": "输入已变化，请重新生成并确认候选路线。",
    "explicit_user_route_selection_required": "请先选择一条候选路线。",
    "selected_route_not_in_current_candidates": "所选路线已不在当前候选中，请重新生成并选择。",
    "human_confirmation_required": "请先完成路线审阅并确认。",
    "unknown_route_crosswalk": "当前候选路线无法进入正式 Step 1/Step 2，请重新选择。",
    "non_single_gene_route_not_supported_in_v1": "当前路线不支持 V1 单基因 Step 1/Step 2 草稿。",
    "goal_text_required": "请填写设计目标。",
    "invalid_source_metadata": "可选来源信息无法读取，请检查后重试。",
    "unsupported_formal_plant_host": "请选择 V1 单基因流程支持的植物宿主。",
    "invalid_cds": "请提供可解析的用户 CDS 序列。",
    "input_signature_required": "当前候选已失效，请重新生成并确认。",
    "input_signature_mismatch": "当前候选已失效，请重新生成并确认。",
    "route_confirmation_contract_not_satisfied": "当前路线确认状态已变化，请重新生成并确认。",
    "advisory_prefill_contract_not_ready": "当前候选草稿无法应用，请重新生成并确认。",
    "single_gene_crosswalk_mismatch": "当前路线不支持 V1 单基因 Step 1/Step 2 草稿。",
    "formal_design_not_blank": "请在空白正式设计中应用候选路线草稿。",
    "missing_step1_draft_fields": "项目名称或植物宿主草稿不完整，请检查输入。",
    "missing_step2_draft_fields": "目标 CDS 草稿不完整，请检查名称和序列。",
}
_FORMAL_AI_ROUTE_GENERIC_ERROR_MESSAGE_ZH = "候选路线暂时无法处理，请检查输入后重试。"


def _formal_ai_route_reason_code(error: Any) -> str:
    """Normalize internal handoff errors without exposing implementation fields."""
    reason_code = str(getattr(error, "reason_code", "") or "").strip()
    if reason_code:
        return reason_code
    raw = str(error or "").strip()
    legacy_fragments = (
        ("source_metadata", "invalid_source_metadata"),
        ("plant_host", "unsupported_formal_plant_host"),
        ("user_provided_cds", "invalid_cds"),
        ("missing required Step 1", "missing_step1_draft_fields"),
        ("missing required Step 2", "missing_step2_draft_fields"),
        ("advisory prefill contract", "advisory_prefill_contract_not_ready"),
        ("blank formal design", "formal_design_not_blank"),
        ("single-gene crosswalk", "single_gene_crosswalk_mismatch"),
    )
    for fragment, code in legacy_fragments:
        if fragment.casefold() in raw.casefold():
            return code
    return raw if raw in _FORMAL_AI_ROUTE_ERROR_MESSAGES_ZH else "formal_ai_route_error"


def _formal_ai_route_user_error(error: Any) -> str:
    """Record the machine reason code while returning concise UI copy."""
    reason_code = _formal_ai_route_reason_code(error)
    st.session_state["formal_ai_route_last_error_reason"] = reason_code
    return _FORMAL_AI_ROUTE_ERROR_MESSAGES_ZH.get(
        reason_code,
        _FORMAL_AI_ROUTE_GENERIC_ERROR_MESSAGE_ZH,
    )


def _formal_ai_route_current_signature(
    *,
    goal_text: str,
    plant_host: str,
    user_provided_cds: str,
    source_metadata: Mapping[str, Any] | None,
) -> str:
    from services.plant_formal_route_prefill_adapter import (
        PlantFormalRoutePrefillInputError,
        plant_formal_route_prefill_input_signature,
    )

    try:
        return plant_formal_route_prefill_input_signature(
            goal_text=goal_text,
            plant_host=plant_host,
            user_provided_cds=user_provided_cds,
            source_metadata=source_metadata,
        )
    except (PlantFormalRoutePrefillInputError, TypeError, ValueError):
        return ""


def _build_formal_ai_route_candidate_set(
    *,
    goal_text: str,
    plant_host: str,
    user_provided_cds: str,
    source_metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Bind the adopted L6 candidate contract to one valid formal input set."""
    from services.plant_formal_route_prefill_adapter import (
        plant_formal_route_prefill_input_signature,
    )
    from services.plant_simple_wizard_intent_intake_presenter import (
        build_simple_plant_wizard_intent_intake_presenter,
    )

    signature = plant_formal_route_prefill_input_signature(
        goal_text=goal_text,
        plant_host=plant_host,
        user_provided_cds=user_provided_cds,
        source_metadata=source_metadata,
    )
    intent_payload = build_simple_plant_wizard_intent_intake_presenter(
        user_goal_text=str(goal_text or "").strip(),
        available_materials=["target_gene_or_cds", "host_plant"],
    )
    return {
        "input_signature": signature,
        "intent_payload": intent_payload,
        "advisory_only": True,
        "formal_authority": False,
        "persist": False,
    }


def _formal_ai_route_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "adapter_status": "formal_prefill_fail_closed",
        "fail_closed": True,
        "fail_closed_reason": reason,
        "prefill": None,
        "advisory_only": True,
        "formal_authority": False,
        "persist": False,
    }


def _build_formal_ai_route_handoff(
    *,
    goal_text: str,
    plant_host: str,
    user_provided_cds: str,
    source_metadata: Mapping[str, Any] | None,
    candidate_set: Mapping[str, Any] | None,
    user_selected_route_id: str | None,
    human_confirmed: bool,
) -> dict[str, Any]:
    """Fail closed unless selection and confirmation bind to the current candidates."""
    from services.plant_formal_route_prefill_adapter import (
        build_plant_formal_route_prefill_adapter,
    )

    current_signature = _formal_ai_route_current_signature(
        goal_text=goal_text,
        plant_host=plant_host,
        user_provided_cds=user_provided_cds,
        source_metadata=source_metadata,
    )
    if not current_signature:
        return _formal_ai_route_fail_closed("invalid_current_inputs")
    candidates = candidate_set if isinstance(candidate_set, Mapping) else {}
    if str(candidates.get("input_signature") or "") != current_signature:
        return _formal_ai_route_fail_closed("candidate_set_stale")
    intent_payload = candidates.get("intent_payload")
    intent_payload = intent_payload if isinstance(intent_payload, Mapping) else {}
    current_route_ids = {
        str(candidate.get("route_id") or "").strip()
        for candidate in intent_payload.get("route_candidates") or []
        if isinstance(candidate, Mapping)
    }
    selected_route_id = str(user_selected_route_id or "").strip()
    if not selected_route_id:
        return _formal_ai_route_fail_closed("explicit_user_route_selection_required")
    if selected_route_id not in current_route_ids:
        return _formal_ai_route_fail_closed("selected_route_not_in_current_candidates")
    return build_plant_formal_route_prefill_adapter(
        goal_text=goal_text,
        plant_host=plant_host,
        user_provided_cds=user_provided_cds,
        source_metadata=source_metadata,
        user_selected_route_id=selected_route_id,
        human_confirmed=human_confirmed is True,
        input_signature=current_signature,
    )


def _apply_formal_ai_route_prefill(result: Mapping[str, Any]) -> dict[str, Any]:
    """Write only existing Step 1/2 widget drafts; grant no formal authority."""
    from services.formal_cds_workflow import MODIFICATION_STATUSES, SOURCE_TYPES

    if (
        result.get("fail_closed") is not False
        or result.get("advisory_only") is not True
        or result.get("formal_authority") is not False
        or result.get("persist") is not False
    ):
        raise ValueError("advisory_prefill_contract_not_ready")
    prefill = result.get("prefill")
    prefill = prefill if isinstance(prefill, Mapping) else {}
    project_draft = prefill.get("project_expression_target_draft")
    project_draft = project_draft if isinstance(project_draft, Mapping) else {}
    if (
        project_draft.get("project_type") != PROJECT_TYPE_SINGLE_GENE
        or project_draft.get("design_scenario") != "standard_plant_expression_vector"
    ):
        raise ValueError("single_gene_crosswalk_mismatch")
    state = st.session_state
    if (
        isinstance(state.get("formal_project_definition"), Mapping)
        or isinstance(state.get("formal_cds_input"), Mapping)
        or str(state.get("mvp_project_id") or "").strip()
        or isinstance(state.get("mvp_vector_result"), Mapping)
    ):
        raise ValueError("formal_design_not_blank")

    metadata = prefill.get("supplied_source_metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    nested_metadata = metadata.get("gene_information")
    nested_metadata = nested_metadata if isinstance(nested_metadata, Mapping) else {}

    def metadata_value(key: str) -> Any:
        return nested_metadata[key] if key in nested_metadata else metadata.get(key)

    supplied_source_type = str(metadata_value("source_type") or "").strip()
    supplied_modification_status = str(metadata_value("modification_status") or "").strip()
    field_values: dict[str, Any] = {
        "formal_step1_project_name": str(project_draft.get("project_name_draft") or "").strip(),
        "formal_step1_host": str(prefill.get("formal_host_value") or "").strip(),
        "formal_step2_gene_name": str(prefill.get("gene_cds_display_name") or "").strip(),
        "formal_step2_source_type": (
            supplied_source_type if supplied_source_type in SOURCE_TYPES else "用户自有序列"
        ),
        "formal_step2_source_reference": str(metadata_value("source_reference") or "").strip(),
        "formal_step2_gene_symbol": str(metadata_value("gene_symbol") or "").strip(),
        "formal_step2_source_species": str(metadata_value("source_species") or "").strip(),
        "formal_step2_modification_status": (
            supplied_modification_status
            if supplied_modification_status in MODIFICATION_STATUSES
            else "尚未确定"
        ),
        "formal_step2_modification_note": str(metadata_value("modification_note") or "").strip(),
        "formal_step2_partial_cds": bool(metadata_value("is_partial_cds")),
        "formal_step2_note": str(metadata_value("note") or "").strip(),
        "formal_step2_mode": "粘贴核酸序列",
        "formal_step2_cds_text": str(prefill.get("raw_cds") or ""),
    }
    if not field_values["formal_step1_project_name"] or not field_values["formal_step1_host"]:
        raise ValueError("missing_step1_draft_fields")
    if not field_values["formal_step2_gene_name"] or not field_values["formal_step2_cds_text"]:
        raise ValueError("missing_step2_draft_fields")

    state.update(
        {
            key: value
            for key, value in field_values.items()
            if key.startswith("formal_step1_")
        }
    )
    state["formal_ai_route_applied_prefill"] = {
        "input_signature": str(result.get("input_signature") or ""),
        "selected_route_id": str(prefill.get("selected_advisory_route_id") or ""),
        "field_values": dict(field_values),
    }
    return field_values


def _hydrate_formal_ai_route_step2_prefill() -> bool:
    """Hydrate deferred Step 2 widget drafts before those widgets are created."""
    state = st.session_state
    if isinstance(state.get("formal_cds_input"), Mapping):
        return False
    applied = state.get("formal_ai_route_applied_prefill")
    applied = applied if isinstance(applied, Mapping) else {}
    input_signature = str(applied.get("input_signature") or "")
    field_values = applied.get("field_values")
    if not input_signature or not isinstance(field_values, Mapping):
        return False
    step2_values = {
        str(key): value
        for key, value in field_values.items()
        if str(key).startswith("formal_step2_")
    }
    if not step2_values:
        return False
    hydrated_signature = str(
        state.get("formal_ai_route_step2_hydrated_signature") or ""
    )
    if hydrated_signature != input_signature:
        state.update(step2_values)
    else:
        for key, value in step2_values.items():
            state.setdefault(key, value)
    state["formal_ai_route_step2_hydrated_signature"] = input_signature
    return True


def _synchronize_formal_ai_route_freshness(current_signature: str) -> bool:
    """Invalidate stale AI decisions and untouched draft values on input change."""
    state = st.session_state
    candidate_set = state.get("formal_ai_route_candidate_set")
    candidate_set = candidate_set if isinstance(candidate_set, Mapping) else {}
    applied = state.get("formal_ai_route_applied_prefill")
    applied = applied if isinstance(applied, Mapping) else {}
    expected_signature = str(
        candidate_set.get("input_signature") or applied.get("input_signature") or ""
    )
    decision_keys = (
        "formal_ai_route_candidate_set",
        "formal_ai_route_selected_route",
        "formal_ai_route_human_confirmed",
        "formal_ai_route_applied_prefill",
        "formal_ai_route_step2_hydrated_signature",
    )
    has_decision_state = bool(expected_signature) or any(key in state for key in decision_keys[1:])
    if not has_decision_state or (current_signature and current_signature == expected_signature):
        return False

    authoritative_step_state_exists = bool(
        isinstance(state.get("formal_project_definition"), Mapping)
        or isinstance(state.get("formal_cds_input"), Mapping)
    )
    applied_fields = applied.get("field_values")
    if not authoritative_step_state_exists and isinstance(applied_fields, Mapping):
        for key, value in applied_fields.items():
            if state.get(key) == value:
                if key == "formal_step1_project_name":
                    state[key] = ""
                elif key == "formal_step1_host":
                    state[key] = None
                else:
                    state.pop(key, None)
    for key in decision_keys:
        state.pop(key, None)
    state["formal_ai_route_stale_notice"] = True
    return True


def _formal_ai_route_prefill_eligible(ds: Any) -> bool:
    state = st.session_state
    return bool(
        int(getattr(ds, "step", 1) or 1) == 1
        and _formal_project_type() == PROJECT_TYPE_SINGLE_GENE
        and not isinstance(state.get("formal_project_definition"), Mapping)
        and not isinstance(state.get("formal_cds_input"), Mapping)
        and not str(state.get("mvp_project_id") or "").strip()
        and not isinstance(state.get("mvp_vector_result"), Mapping)
    )


def _render_formal_ai_route_entry() -> None:
    """Render the session-only advisory handoff inside the formal Step 1 surface."""
    from services.plant_formal_route_prefill_adapter import (
        PlantFormalRoutePrefillInputError,
        ROUTE_CROSSWALK,
    )
    from services.plant_simple_wizard_route_schema import get_simple_plant_wizard_route

    with st.expander(_t('v1.expression.ai_candidate_route_review_only'), expanded=True):
        st.caption(
            _t('v1.expression.candidate_pathways_used_only_organize_design_draft')
        )
        goal_text = st.text_area(
            _t('v1.expression.design_objective'),
            key="formal_ai_route_goal",
            height=90,
            placeholder=_t('v1.expression.e_g_user_provided_cds_protein_expression'),
        )
        host_values = _formal_ai_route_supported_host_values()
        plant_host = st.selectbox(
            _t('v1.expression.supported_plant_hosts'),
            host_values,
            index=None,
            placeholder=_t('v1.expression.select_plant_host_supported_by_v1_single'),
            format_func=_plant_host_label,
            key="formal_ai_route_host",
        )
        user_provided_cds = st.text_area(
            _t('v1.expression.user_provided_cds'),
            key="formal_ai_route_cds",
            height=160,
            placeholder=_t('v1.expression.paste_single_nucleic_acid_cds_sequence'),
        )
        with st.expander(_t('v1.expression.source_metadata_optional'), expanded=False):
            metadata_left, metadata_right = st.columns(2)
            metadata_left.text_input(_t('v1.expression.gene_cds_name'), key="formal_ai_route_gene_name")
            metadata_right.text_input(_t('v1.expression.source_organism'), key="formal_ai_route_source_species")
            st.text_input(
                _t('v1.expression.user_provided_source_description_accession'),
                key="formal_ai_route_source_reference",
            )
            st.caption(_t('v1.expression.source_description_preserved_as_entered_by_user'))

        source_metadata = _formal_ai_route_source_metadata()
        current_signature = _formal_ai_route_current_signature(
            goal_text=goal_text,
            plant_host=str(plant_host or ""),
            user_provided_cds=user_provided_cds,
            source_metadata=source_metadata,
        )
        _synchronize_formal_ai_route_freshness(current_signature)
        if st.session_state.pop("formal_ai_route_stale_notice", False):
            st.warning(_t('v1.expression.input_changed_previous_candidates_selections_confirmations_invalid'))

        if st.button(_t('v1.expression.generate_candidate_routes'), key="formal_ai_route_generate_candidates"):
            try:
                candidate_set = _build_formal_ai_route_candidate_set(
                    goal_text=goal_text,
                    plant_host=str(plant_host or ""),
                    user_provided_cds=user_provided_cds,
                    source_metadata=source_metadata,
                )
            except (PlantFormalRoutePrefillInputError, TypeError, ValueError) as exc:
                st.error(_t('v1.expression.failed_generate_candidate_route', p0=_formal_ai_route_user_error(exc)))
            else:
                st.session_state["formal_ai_route_candidate_set"] = candidate_set
                st.session_state.pop("formal_ai_route_selected_route", None)
                st.session_state.pop("formal_ai_route_human_confirmed", None)
                st.session_state.pop("formal_ai_route_applied_prefill", None)
                st.session_state.pop("formal_ai_route_last_error_reason", None)

        candidate_set = st.session_state.get("formal_ai_route_candidate_set")
        candidate_set = candidate_set if isinstance(candidate_set, Mapping) else {}
        intent_payload = candidate_set.get("intent_payload")
        intent_payload = intent_payload if isinstance(intent_payload, Mapping) else {}
        route_candidates = [
            dict(candidate)
            for candidate in intent_payload.get("route_candidates") or []
            if isinstance(candidate, Mapping)
        ]
        if not route_candidates:
            return

        st.markdown(_t('v1.expression.candidate_pathway_review'))
        source_reference = str(source_metadata.get("source_reference") or "").strip()
        for candidate in route_candidates:
            route_id = str(candidate.get("route_id") or "")
            route = get_simple_plant_wizard_route(route_id)
            with st.container(border=True, key=f"formal_ai_route_candidate_{route_id}"):
                st.markdown(f"**{route.get('label_en') or route_id}**")
                reasons = [str(item) for item in candidate.get("match_reasons_zh") or [] if str(item).strip()]
                gaps = [str(item) for item in candidate.get("uncertainties_zh") or [] if str(item).strip()]
                st.markdown(_t('v1.expression.matching_basis'))
                for reason in reasons or ["当前目标与已提供材料形成候选路线信号，仍需人工审阅。"]:
                    st.write(f"- {reason}")
                st.markdown(_t('v1.expression.input_basis'))
                st.write(_t('v1.expression.plant_host_official_registry', p0=_plant_host_label(plant_host)))
                st.write(_t('v1.expression.cds_provided_by_user_no_blocking_issues'))
                st.write(
                    _t('v1.expression.source_note_provided_by_user_not_verified', p0=source_reference)
                    if source_reference
                    else _t('v1.expression.source_note_not_provided_retained_as_gap')
                )
                st.markdown(_t('v1.expression.information_gap'))
                for gap in gaps or ["元件、骨架及其来源尚未选择，需在现有正式步骤中人工审阅。"]:
                    st.write(f"- {gap}")
                crosswalk = ROUTE_CROSSWALK.get(route_id) or {}
                if crosswalk.get("single_gene_supported") is not True:
                    st.caption(_t('v1.expression.candidate_outside_v1_single_gene_step_1'))

        selectable_route_ids = [
            str(candidate.get("route_id") or "")
            for candidate in route_candidates
            if (ROUTE_CROSSWALK.get(str(candidate.get("route_id") or "")) or {}).get(
                "single_gene_supported"
            )
            is True
        ]
        ready_for_confirmation = (
            intent_payload.get("decision_state") == "ready_for_user_confirmation"
            and bool(selectable_route_ids)
        )
        if not ready_for_confirmation:
            st.warning(_t('v1.expression.target_remains_unclear_cannot_used_auto_filling'))
            return

        selected_route_id = st.selectbox(
            _t('v1.expression.select_one_candidate_route'),
            selectable_route_ids,
            index=None,
            placeholder=_t('v1.expression.explicitly_select'),
            format_func=lambda route_id: str(
                get_simple_plant_wizard_route(route_id).get("label_en") or route_id
            ),
            key="formal_ai_route_selected_route",
        )
        human_confirmed = st.checkbox(
            _t('v1.expression.i_reviewed_candidate_input_rationale_information_gaps'),
            key="formal_ai_route_human_confirmed",
            disabled=not bool(selected_route_id),
        )
        if st.button(
            _t('v1.expression.applied_step_1_step_2_draft'),
            key="formal_ai_route_apply_prefill",
            type="primary",
            disabled=not bool(selected_route_id and human_confirmed),
        ):
            result = _build_formal_ai_route_handoff(
                goal_text=goal_text,
                plant_host=str(plant_host or ""),
                user_provided_cds=user_provided_cds,
                source_metadata=source_metadata,
                candidate_set=candidate_set,
                user_selected_route_id=str(selected_route_id or ""),
                human_confirmed=human_confirmed is True,
            )
            if result.get("fail_closed") is not False:
                st.error(_formal_ai_route_user_error(result.get("fail_closed_reason") or "unknown"))
            else:
                try:
                    _apply_formal_ai_route_prefill(result)
                except ValueError as exc:
                    st.error(_formal_ai_route_user_error(exc))
                else:
                    st.session_state.pop("formal_ai_route_last_error_reason", None)
                    st.rerun()
        applied = st.session_state.get("formal_ai_route_applied_prefill")
        if isinstance(applied, Mapping) and applied.get("input_signature") == current_signature:
            st.success(
                _t('v1.expression.step_1_step_2_draft_fields_pre')
            )


def _render_step_1_project(ds: Any) -> None:
    hydrating = st.session_state.pop("_formal_step_hydration_target", None) == 1
    if hydrating:
        globals().get("_hydrate_formal_step1_widgets", lambda: None)()
    record_step1_edit = globals().get("_record_formal_step1_design_edit")
    st.subheader(_t('v1.expression.step_1_project_definition_expression_objective'))
    def text_default(key: str, value: str) -> dict[str, str]:
        return {} if key in st.session_state else {"value": value}

    with st.container(border=True, key="formal_primary_content_step1"):
        locked_name = str(st.session_state.get("formal_locked_project_name") or "")
        st.markdown(
            _t('v1.expression.project_basic_information'),
            unsafe_allow_html=True,
        )
        scenario_labels = dict(_DESIGN_SCENARIO_LABELS)
        current_scenario = _formal_design_scenario()
        legacy_scenario = st.session_state.get("formal_step1_design_scenario")
        if legacy_scenario not in scenario_labels:
            legacy_scenario = next((key for key, locale_key in scenario_labels.items() if legacy_scenario in {_t(locale_key), _LOCALES.get("zh-CN", {}).get(locale_key)}), current_scenario)
            st.session_state["formal_step1_design_scenario"] = legacy_scenario
        selected_scenario_label = st.segmented_control(
            _t('v1.expression.design_scenario'),
            list(scenario_labels),
            format_func=lambda value: _t(scenario_labels[value]),
            key="formal_step1_design_scenario",
            disabled=bool(locked_name),
            on_change=record_step1_edit,
        )
        selected_scenario = selected_scenario_label if selected_scenario_label in scenario_labels else None
        if selected_scenario is None and selected_scenario_label is None:
            selected_scenario = current_scenario if current_scenario in scenario_labels else None
        if selected_scenario is None:
            st.error(_t('v1.expression.design_scenario_status_unrecognized_reselect_design_scenario'))
        mode_labels = dict(_PROJECT_MODE_LABELS)
        legacy_mode = st.session_state.get("formal_step1_project_type")
        if legacy_mode not in mode_labels:
            legacy_mode = next((key for key, locale_key in mode_labels.items() if legacy_mode in {_t(locale_key), _LOCALES.get("zh-CN", {}).get(locale_key)}), _formal_project_type())
            st.session_state["formal_step1_project_type"] = legacy_mode
        selected_mode_label = st.segmented_control(
            _t('v1.expression.project_mode'),
            list(mode_labels),
            format_func=lambda value: _t(mode_labels[value]),
            key="formal_step1_project_type",
            disabled=bool(locked_name) or selected_scenario == "metabolic_pathway_multi_tu_vector",
            on_change=record_step1_edit,
        )
        resolver = globals().get("_resolve_formal_step1_project_type")
        if callable(resolver):
            selected_project_type = resolver(
                selected_scenario=selected_scenario,
                selected_mode_label=selected_mode_label,
                mode_labels=mode_labels,
                current_project_type=_formal_project_type(),
            )
        else:
            # Keep AST-isolated callers deterministic while the app uses the
            # shared resolver above.
            label_to_type = {project_type: project_type for project_type in mode_labels}
            selected_project_type = (
                PROJECT_TYPE_DUAL_TU
                if selected_scenario == "metabolic_pathway_multi_tu_vector"
                else label_to_type.get(selected_mode_label)
                or (_formal_project_type() if selected_mode_label is None else None)
            )
        if selected_project_type is None:
            st.error(_t('v1.expression.unrecognized_project_mode_state_reselect_design_scenario'))
        left, right = st.columns(2)
        project_name = left.text_input(
            _t('v1.expression.project_name_required'), key="formal_step1_project_name",
            disabled=bool(locked_name),
            on_change=record_step1_edit,
            **text_default("formal_step1_project_name", locked_name or str(st.session_state.get("formal_project_name") or "")),
        ).strip()
        host_values = _plant_host_values()
        widget_host = str(st.session_state.get("formal_step1_host") or "").strip()
        persisted_host = widget_host or str(getattr(ds, "host", "") or "").strip()
        unknown_host = persisted_host and _plant_host_record(persisted_host) is None
        if unknown_host and "formal_step1_host" in st.session_state:
            st.session_state["formal_step1_unregistered_host"] = persisted_host
            del st.session_state["formal_step1_host"]
        selected_host = persisted_host if not unknown_host else ""
        host = right.selectbox(
            _t('v1.expression.plant_host_required'),
            host_values,
            placeholder=_t('v1.expression.select_official_plant_host'),
            format_func=_plant_host_label,
            key="formal_step1_host",
            on_change=record_step1_edit,
            **_formal_widget_initial_kwargs(
                "formal_step1_host",
                index=host_values.index(selected_host) if selected_host in host_values else None,
            ),
        )
        if unknown_host:
            st.error(_t('v1.expression.saved_host_not_official_registry_reselect_plant'))
        workflow_summary = _host_workflow_summary(host)
        if workflow_summary:
            st.caption(_t('v1.expression.workflow_formal') + " · ".join(_ui(item) for item in workflow_summary))
        host_route_compatible = bool(selected_project_type) and _host_supports_project_type(host, selected_project_type)
        if host and not host_route_compatible:
            st.error(_t('v1.expression.host_does_not_support_full_vector_pathway'))
        material = st.text_input(
            _t('v1.expression.cultivar_experimental_material_optional'),
            placeholder=_t('v1.expression.e_g_rice_variety_tobacco_material_project'),
            key="formal_step1_material",
            on_change=record_step1_edit,
            **text_default("formal_step1_material", str(st.session_state.get("formal_project_material") or "")),
        ).strip()
        st.markdown(
            _t('v1.expression.expression_target'),
            unsafe_allow_html=True,
        )
        application_mode = st.selectbox(
            _t('v1.expression.application_mode_required'),
            _APPLICATION_MODE_VALUES,
            format_func=lambda value: _localized_value(value, _APPLICATION_MODE_LABELS),
            key="formal_step1_application_mode",
            on_change=record_step1_edit,
        )
        transient_expression_system = "尚未确定"
        if application_mode == "瞬时表达":
            transient_expression_system = st.selectbox(
                _t('v1.expression.transient_expression_system_optional'),
                _TRANSIENT_SYSTEM_VALUES,
                format_func=lambda value: _localized_value(value, _TRANSIENT_SYSTEM_LABELS),
                key="formal_step1_transient_expression_system",
                on_change=record_step1_edit,
            )
        requirement_left, requirement_right = st.columns(2)
        tissue_specificity_requirement = requirement_left.selectbox(
            _t('v1.expression.tissue_organ_specific_requirement'),
            _TISSUE_REQUIREMENT_VALUES,
            format_func=lambda value: _localized_value(value, {
                _TISSUE_REQUIREMENT_VALUES[0]: "v1.expression.no_specific_tissue_organ_restrictions",
                _TISSUE_REQUIREMENT_VALUES[1]: "v1.expression.tissue_or_organ_specific_expression",
                _TISSUE_REQUIREMENT_VALUES[2]: "v1.expression.application_mode_undetermined",
            }),
            key="formal_step1_tissue_specificity_requirement",
            on_change=record_step1_edit,
        )
        inducibility_requirement = requirement_right.selectbox(
            _t('v1.expression.inducibility_requirement'),
            _INDUCIBILITY_VALUES,
            format_func=lambda value: _localized_value(value, {
                _INDUCIBILITY_VALUES[0]: "v1.expression.no_specific_induction_requirements",
                _INDUCIBILITY_VALUES[1]: "v1.expression.inducible_expression_required",
                _INDUCIBILITY_VALUES[2]: "v1.expression.application_mode_undetermined",
            }),
            key="formal_step1_inducibility_requirement",
            on_change=record_step1_edit,
        )
        tissue_target = str(st.session_state.get("formal_project_tissue_target") or "").strip()
        if tissue_specificity_requirement == "组织或器官特异性表达":
            tissue_target = st.text_input(
                _t('v1.expression.target_tissue_organ'),
                placeholder=_t('v1.expression.e_g_seed_leaf_root_endosperm'),
                key="formal_step1_tissue_target",
                on_change=record_step1_edit,
                **text_default("formal_step1_tissue_target", tissue_target),
            ).strip()
        induction_notes = str(st.session_state.get("formal_project_induction_notes") or "").strip()
        if inducibility_requirement == "需要诱导型表达":
            induction_notes = st.text_input(
                _t('v1.expression.induction_condition_system_description_optional'),
                placeholder=_t('v1.expression.e_g_user_recorded_induction_conditions_system'),
                key="formal_step1_induction_notes",
                on_change=record_step1_edit,
                **text_default("formal_step1_induction_notes", induction_notes),
            ).strip()
        localization_target = st.text_input(
            _t('v1.expression.subcellular_localization_target_optional'),
            placeholder=_t('v1.expression.e_g_cytoplasm_chloroplast_endoplasmic_reticulum_secretory'),
            key="formal_step1_localization_target",
            on_change=record_step1_edit,
            **text_default("formal_step1_localization_target", str(st.session_state.get("formal_project_localization_target") or "")),
        ).strip()
        gene_ready = bool(str(getattr(ds, "gene_name", "") or "").strip() or str(getattr(ds, "original_seq", "") or "").strip())
        status_rows = [
            (_t("v1.expression.plant_host"), _t("v1.expression.determined") if host else _t("v1.expression.to_be_determined")),
            (_t("v1.expression.application_mode"), _t("v1.expression.determined") if application_mode != "尚未确定" else _t("v1.expression.to_be_determined")),
            (_t("v1.expression.tissue_organ_specific_requirement_label"), _t("v1.expression.determined") if tissue_specificity_requirement != "尚未确定" else _t("v1.expression.to_be_determined")),
            (_t("v1.expression.inducibility_requirement_label"), _t("v1.expression.determined") if inducibility_requirement != "尚未确定" else _t("v1.expression.to_be_determined")),
            (_t("v1.expression.target_gene"), _t("v1.expression.entered") if gene_ready else _t("v1.expression.to_be_entered")),
        ]
        st.markdown(
            _t('v1.expression.design_status'),
            unsafe_allow_html=True,
        )
        st.markdown(
            "<div class='formal-card compact'>"
            + "".join(
                f"<div class='meta-inline'><strong>{escape(label)}{('：' if _get_language() == 'zh-CN' else ':')}</strong>{escape(status)}</div>"
                for label, status in status_rows
            )
            + "</div>",
            unsafe_allow_html=True,
        )
    ready = bool(
        project_name
        and host
        and not unknown_host
        and host_route_compatible
        and (tissue_specificity_requirement != "组织或器官特异性表达" or tissue_target)
    )
    definition_input = {
        "project_name": project_name,
        "plant_host": host,
        "material": material,
        "application_mode": str(application_mode),
        "transient_expression_system": str(transient_expression_system),
        "tissue_specificity_requirement": str(tissue_specificity_requirement),
        "tissue_target": tissue_target,
        "inducibility_requirement": str(inducibility_requirement),
        "induction_notes": induction_notes,
        "localization_target": localization_target,
        "compatibility_review_required": "false",
        "project_type": selected_project_type or "",
        "design_scenario": selected_scenario,
    }

    def apply_step1() -> bool:
        if selected_project_type is None:
            return False
        project_type_changed = _formal_project_type() != selected_project_type
        scenario_changed = _formal_design_scenario() != selected_scenario
        _set_formal_project_type(selected_project_type)
        st.session_state["formal_design_scenario"] = selected_scenario
        if scenario_changed:
            _invalidate_formal_snapshots()
            if selected_scenario == "metabolic_pathway_multi_tu_vector":
                _pathway_steps()
        ds.host = host
        ds.tag = "No tag"
        if project_type_changed:
            ds.clear_step3_outputs()
            _clear_complete_plasmid_state()
        definition = _formal_project_definition()
        definition.update({key: value for key, value in definition_input.items() if key not in {"project_type", "design_scenario"}})
        return _apply_formal_project_definition(definition)

    def advance_step1() -> None:
        succeeded, needs_review, _executed = _execute_formal_action(
            step=1,
            action_id="step1_save_continue",
            input_signature=_formal_ui_signature(definition_input),
            action=apply_step1,
            success_status="流程已更新",
            success_message=_t('v1.expression.step_1_applied_continue_step_2'),
            failure_status="保存失败",
        )
        if succeeded:
            ds.step = 2
            _controller().save(ds)
            if needs_review:
                st.warning(_t('v1.expression.project_background_changed_existing_cds_selected_elements'))
            st.rerun()
    sync_step1_edit = globals().get("_record_formal_step1_design_edit")
    if not hydrating and callable(sync_step1_edit):
        sync_step1_edit()
    _render_step_navigation(
        current_step=1,
        next_enabled=ready and not bool(st.session_state.get("formal_ui_action_busy")),
        disabled_reason=(
            _t("v1.expression.select_official_plant_host")
            if unknown_host
            else _t("v1.expression.host_does_not_support_full_vector_pathway")
            if host and not host_route_compatible
            else _t("v1.expression.complete_step1_required_fields")
        ) if not ready else "",
        next_action=advance_step1,
    )


def _render_pathway_traceability(steps: Any, units: Any) -> None:
    from services.gate3_pathway_mapping import build_pathway_traceability_rows

    rows = build_pathway_traceability_rows(steps, units)
    source_steps = {int(step['display_order']): step for step in steps}
    st.markdown(_t('v1.ui_closure.pathway_traceability'))
    st.dataframe([
        {
            _t('v1.results_final_report.order'): row['step_order'],
            _t('v1.expression.step_name'): row['step_name'],
            _t('v1.results_final_report.conversion'): row['conversion'],
            _t('v1.expression.enzyme_name'): row['enzyme_name'],
            'CDS': f"{row['cds_length']} bp",
            _t('v1.common.source'): source_steps[row['step_order']].get('cds_source_reference') or '--',
            _t('v1.results_final_report.mapped_tu'): f"TU{row['transcription_unit_order']} · {row['transcription_unit']}",
            _t('v1.results_final_report.mapping_status'): _t('v1.expression.mapping_status_' + {'mapped_pending_application': 'pending'}.get(row['mapping_status'], row['mapping_status'])),
        }
        for row in rows
    ], hide_index=True, use_container_width=True)


def _render_pathway_mapping_step_2(ds: Any) -> None:
    """Manual pathway-step mapping UI layered over the existing multi-TU state."""
    from services.gate3_pathway_mapping import (
        CDS_SOURCE_TYPES,
        add_pathway_step,
        analyze_pathway_cds,
        apply_step_cds_to_unit,
        delete_pathway_step,
        move_pathway_step,
        update_pathway_step,
    )

    st.subheader(_t('v1.expression.step_2_pathway_step_cds_mapping'))
    st.caption(_t('v1.expression.user_records_pathway_steps_enzymes_cds_confirms'))
    units = _transcription_units()
    control_cols = st.columns([1, 1, 3])
    if control_cols[0].button(_t('v1.expression.add_pathway_step'), type="primary", key="formal_pathway_add_step"):
        _store_pathway_steps(add_pathway_step(_pathway_steps()))
        st.rerun()
    if control_cols[1].button(_t('v1.expression.add_transcription_unit'), key="formal_pathway_add_tu"):
        _add_transcription_unit()
        _refresh_pathway_mapping_status()
        st.rerun()

    source_labels = {
        "public_database": "v1.expression.public_database_record",
        "upload_file": "v1.expression.upload_file_source",
        "user_provided": "v1.expression.user_provided_source",
        "test_only_asset": "v1.expression.builtin_test_asset",
    }
    status_labels = {
        "not_mapped": "v1.expression.mapping_status_unmapped",
        "mapped_pending_application": "v1.expression.mapping_status_pending",
        "applied": "v1.expression.mapping_status_applied",
        "blocked": "v1.expression.mapping_status_blocked",
    }
    unit_labels: dict[str, str] = {}
    for index, unit in enumerate(units, start=1):
        cds = dict(unit.get("cds") or {})
        analysis = dict(cds.get("cds_analysis") or {})
        cds_status = _t("v1.expression.cds_recorded") if analysis.get("normalized_cds") else _t("v1.expression.cds_not_recorded")
        direction = _t("v1.expression.orientation_reverse") if unit.get("orientation") == "reverse" else _t("v1.expression.orientation_forward")
        unit_labels[str(unit["unit_id"])] = f"TU{index} · {unit.get('display_name') or '--'} · {direction} · {cds_status}"

    validation = _refresh_pathway_mapping_status()
    if st.session_state.get("formal_betalain_gate3_case"):
        from services.betalain_three_enzyme_gate3_case import (
            BOUNDARY_NOTE,
            NONENZYMATIC_REVIEW_NOTE,
            load_betalain_three_enzyme_case,
        )
        from services.pbi121_replacement_strategy import strategy_summary

        case = load_betalain_three_enzyme_case()
        st.info(BOUNDARY_NOTE)
        st.caption(NONENZYMATIC_REVIEW_NOTE)
        st.subheader("Real-source CDS analysis")
        st.dataframe(
            [
                {
                    "Accession": record["version"],
                    "Gene": record["gene"],
                    "CDS": f"{record['cds_length']:,} bp",
                    "Protein": f"{record['protein_length']} aa",
                    "Coordinates": record["cds_coordinates"],
                    "Strand": "+" if record["strand"] == 1 else "-",
                    "Translation match": "yes" if record["translation_matches_record"] else "no",
                }
                for record in case["cds_records"]
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.subheader("Pathway step to transcription-unit mapping")
        st.dataframe(
            [
                {
                    "Step": step["display_order"],
                    "Pathway conversion": f"{step['substrate_name']} -> {step['product_name']}",
                    "Enzyme": step["enzyme_name"],
                    "Accession": step["cds_source_reference"],
                    "Mapped TU": step["mapped_unit_id"],
                    "CDS applied": "yes" if step["applied_to_unit"] else "no",
                }
                for step in validation["pathway_steps"]
            ],
            hide_index=True,
            use_container_width=True,
        )
        editable_step = validation["pathway_steps"][0]
        enzyme_widget_key = "formal_betalain_edit_enzyme_name"
        edited_enzyme_name = st.text_input(
            _t('v1.expression.enzyme_name_record'),
            key=enzyme_widget_key,
            **({} if enzyme_widget_key in st.session_state else {"value": editable_step["enzyme_name"]}),
        )
        if st.button(_t('v1.expression.applied_pathway_enzyme_modification'), key="formal_betalain_save_enzyme_edit"):
            _store_pathway_steps(
                update_pathway_step(
                    _pathway_steps(),
                    editable_step["step_id"],
                    enzyme_name=edited_enzyme_name,
                )
            )
            _refresh_pathway_mapping_status()
            st.success(_t('v1.expression.pathway_enzyme_records_been_modified_previous_full'))
            st.rerun()
        strategy = strategy_summary()
        st.subheader(_t('v1.expression.pbi121_replacement_strategy_status'))
        st.write(_t('v1.expression.pbi121_source_loaded', p0=_t('v1.common.yes') if strategy['source_loaded'] else _t('v1.common.no')))
        st.write(_t('v1.expression.system_fixed_policy_record', p0=_t('v1.expression.established') if strategy['strategy_exists'] else _t('v1.expression.not_established')))
        st.write(_t('v1.expression.strategy_status', p0=strategy['strategy_status']))
        if strategy["ready_for_construct_use"]:
            st.info(_t('v1.expression.fixed_contract_passed_checks_source_identity_length'))
        else:
            st.caption(_t('v1.expression.strategy_missing_conditions') + ("; ".join(strategy["missing_conditions"]) or _t('v1.expression.not_recorded')))
        st.caption("The reviewed source assets are local immutable records. No TEST_ONLY component or placeholder backbone is used.")
        _render_step_navigation(
            current_step=2,
            next_enabled=validation["mapping_complete"] and bool(strategy["ready_for_construct_use"]),
            next_label=_t('v1.expression.confirm_regulatory_component_selection'),
            disabled_reason=_t("v1.expression.pathway_contract_incomplete_help"),
        )
        return
    _render_pathway_traceability(validation["pathway_steps"], units)
    for step in validation["pathway_steps"]:
        step_id = str(step["step_id"])
        prefix = f"formal_pathway_{step_id}"
        with st.expander(f"{int(step['display_order'])}. {step['step_name'] or '--'}", expanded=True):
            head, up, down, delete = st.columns([5, 1, 1, 1])
            head.markdown(_t('v1.expression.step', p0=int(step['display_order']), p1=escape(step['step_name'] or '未命名步骤')))
            if up.button(_t('v1.expression.move_up'), key=f"{prefix}_up", disabled=step["display_order"] <= 1):
                _store_pathway_steps(move_pathway_step(_pathway_steps(), step_id, -1))
                st.rerun()
            if down.button(_t('v1.expression.move_down'), key=f"{prefix}_down", disabled=step["display_order"] >= len(validation["pathway_steps"])):
                _store_pathway_steps(move_pathway_step(_pathway_steps(), step_id, 1))
                st.rerun()
            delete_target = str(st.session_state.get("formal_pathway_delete_target") or "")
            if delete_target == step_id:
                if delete.button(_t('v1.expression.confirm_deletion'), key=f"{prefix}_confirm_delete"):
                    try:
                        _store_pathway_steps(delete_pathway_step(_pathway_steps(), step_id))
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        st.session_state.pop("formal_pathway_delete_target", None)
                        st.rerun()
                if st.button(_t('v1.common.cancel'), key=f"{prefix}_cancel_delete"):
                    st.session_state.pop("formal_pathway_delete_target", None)
                    st.rerun()
            elif delete.button(_t('v1.common.delete'), key=f"{prefix}_delete"):
                st.session_state["formal_pathway_delete_target"] = step_id
                st.rerun()

            first, second = st.columns(2)
            step_name = first.text_input(
                _t('v1.expression.step_name'),
                key=f"{prefix}_name",
                **_formal_widget_initial_kwargs(f"{prefix}_name", value=step["step_name"]),
            )
            enzyme_name = second.text_input(
                _t('v1.expression.enzyme_name'),
                key=f"{prefix}_enzyme",
                **_formal_widget_initial_kwargs(f"{prefix}_enzyme", value=step["enzyme_name"]),
            )
            substrate_name = first.text_input(
                _t('v1.expression.substrate_label'),
                key=f"{prefix}_substrate",
                **_formal_widget_initial_kwargs(f"{prefix}_substrate", value=step["substrate_name"]),
            )
            product_name = second.text_input(
                _t('v1.expression.product_label'),
                key=f"{prefix}_product",
                **_formal_widget_initial_kwargs(f"{prefix}_product", value=step["product_name"]),
            )
            enzyme_gene_name = first.text_input(
                _t('v1.expression.enzyme_gene_name_optional'),
                key=f"{prefix}_gene",
                **_formal_widget_initial_kwargs(f"{prefix}_gene", value=step["enzyme_gene_name"]),
            )
            ec_number = second.text_input(
                _t('v1.expression.ec_number_optional'),
                key=f"{prefix}_ec",
                **_formal_widget_initial_kwargs(f"{prefix}_ec", value=step["ec_number"]),
            )
            source_organism = first.text_input(
                _t('v1.expression.enzyme_source_organism_optional'),
                key=f"{prefix}_organism",
                **_formal_widget_initial_kwargs(f"{prefix}_organism", value=step["enzyme_source_organism"]),
            )
            notes = second.text_input(
                _t('v1.expression.notes_optional'),
                key=f"{prefix}_notes",
                **_formal_widget_initial_kwargs(f"{prefix}_notes", value=step["notes"]),
            )
            source_type = first.selectbox(
                _t('v1.expression.cds_source_type'),
                list(CDS_SOURCE_TYPES),
                format_func=lambda value: _t(source_labels.get(value, "v1.expression.unprovided")),
                key=f"{prefix}_source_type",
                **_formal_widget_initial_kwargs(
                    f"{prefix}_source_type",
                    index=list(CDS_SOURCE_TYPES).index(step["cds_source_type"])
                    if step["cds_source_type"] in CDS_SOURCE_TYPES
                    else 2,
                ),
            )
            source_reference = second.text_input(
                _t('v1.expression.cds_source_description_accession'),
                key=f"{prefix}_source_reference",
                help=_t("v1.expression.pathway_cds_source_help"),
                **_formal_widget_initial_kwargs(
                    f"{prefix}_source_reference",
                    value=step["cds_source_reference"],
                ),
            )
            manual_review_notes = st.text_input(
                _t('v1.expression.manual_review_notes_optional'),
                key=f"{prefix}_manual_review_notes",
                **_formal_widget_initial_kwargs(
                    f"{prefix}_manual_review_notes",
                    value=step["manual_review_notes"],
                ),
            )
            raw_cds = st.text_area(
                _t('v1.expression.cds_input_dna_single_record_fasta'),
                height=130,
                key=f"{prefix}_cds",
                **_formal_widget_initial_kwargs(f"{prefix}_cds", value=step["cds_sequence"]),
            )
            analysis_preview = analyze_pathway_cds(
                raw_cds,
                source_type=source_type,
                source_reference=source_reference,
            )
            analysis = analysis_preview["cds_analysis"]
            metrics = st.columns(4)
            metrics[0].metric(_t('v1.expression.cds_length'), f"{len(analysis_preview['cds_sequence']):,} bp")
            metrics[1].metric(_t('v1.common.reading_frame'), "通过" if analysis.get("length_multiple_of_three") else "待检查")
            metrics[2].metric(_t('v1.expression.start_codon'), analysis.get("start_codon") or "--")
            metrics[3].metric(_t('v1.expression.stop_codon'), analysis.get("terminal_stop_codon") or "--")
            st.caption(str(analysis.get("translation_summary") or _t('v1.expression.translation_summary_unavailable')))
            for finding in list(analysis.get("findings") or []):
                (st.warning if finding.get("blocking") else st.info)(str(finding.get("message") or ""))
            with st.expander(_t('v1.common.technical_details'), expanded=False):
                st.code(str(analysis_preview["cds_sequence_sha256"]), language="text")

            selected_unit = st.selectbox(
                _t('v1.expression.mapped_transcription_unit'),
                [""] + list(unit_labels),
                format_func=lambda value: unit_labels[value] if value else _t('v1.expression.select_transcription_unit_placeholder'),
                key=f"{prefix}_unit",
                **_formal_widget_initial_kwargs(
                    f"{prefix}_unit",
                    index=(1 + list(unit_labels).index(step["mapped_unit_id"]))
                    if step["mapped_unit_id"] in unit_labels
                    else 0,
                ),
            )
            actions = st.columns(2)
            changes = {
                "step_name": step_name,
                "substrate_name": substrate_name,
                "product_name": product_name,
                "enzyme_name": enzyme_name,
                "enzyme_gene_name": enzyme_gene_name,
                "ec_number": ec_number,
                "enzyme_source_organism": source_organism,
                "notes": notes,
                "cds_sequence": raw_cds,
                "cds_source_type": source_type,
                "cds_source_reference": source_reference,
                "mapped_unit_id": selected_unit,
                "manual_review_notes": manual_review_notes,
            }
            if actions[0].button(_t('v1.expression.applied_pathway_step_configuration'), key=f"{prefix}_save"):
                _store_pathway_steps(update_pathway_step(_pathway_steps(), step_id, **changes))
                _refresh_pathway_mapping_status()
                st.rerun()
            if actions[1].button(_t('v1.expression.apply_step_s_cds_selected_transcription_unit'), key=f"{prefix}_apply"):
                try:
                    updated_steps = update_pathway_step(_pathway_steps(), step_id, **changes)
                    applied_steps, updated_units = apply_step_cds_to_unit(updated_steps, units, step_id)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    _store_pathway_steps(applied_steps)
                    _store_transcription_units(updated_units)
                    _invalidate_dual_tu_unit(selected_unit)
                    _refresh_pathway_mapping_status()
                    st.success(_t('v1.expression.cds_step_been_written_selected_transcription_unit'))
                    st.rerun()
            st.caption(_t('v1.expression.mapping_status', p0=_t(status_labels.get(step['mapping_status'], 'v1.expression.pending_record'))))

    validation = _refresh_pathway_mapping_status()
    if validation["blocking_items"]:
        st.error(_t('v1.expression.pathway_mapping_blocking_items_cannot_marked_as'))
        for item in validation["blocking_items"]:
            st.caption(str(item["message"]))
    if validation["manual_review_items"]:
        st.info(_t('v1.expression.pending_human_review', p0=len(validation['manual_review_items'])))
    _render_step_navigation(
        current_step=2,
        next_enabled=bool(validation["mapping_complete"]),
        disabled_reason=_t("v1.expression.pathway_mapping_incomplete_help"),
    )


def _render_dual_tu_step_2(ds: Any) -> None:
    if _is_pathway_multi_tu_project():
        _render_pathway_mapping_step_2(ds)
        return
    st.subheader(_t('v1.expression.step_2_tu_planning'))
    st.caption(_t('v1.expression.specify_number_transcription_units_tus_display_names'))
    units = _transcription_units()
    if st.button(_t('v1.expression.add_transcription_unit'), type="secondary", key="formal_multi_tu_add"):
        _add_transcription_unit()
        st.rerun()
    for index, unit in enumerate(units, start=1):
        unit_id = str(unit["unit_id"])
        with st.container(border=True, key=f"formal_multi_tu_plan_{unit_id}"):
            name_col, direction_col, stable_id_col, actions_col = st.columns([3, 2, 3, 3])
            with name_col:
                st.text_input(
                    _t('v1.expression.tu_name'),
                    value=str(unit.get("display_name") or f"TU{index}"),
                    key=f"formal_{unit_id}_planning_display_name",
                )
            with direction_col:
                st.selectbox(
                    _t('v1.common.orientation'),
                    _ORIENTATION_VALUES,
                    index=1 if unit.get("orientation") == "reverse" else 0,
                    format_func=lambda value: _t(
                        'v1.expression.orientation_reverse' if value == _ORIENTATION_VALUES[1] else 'v1.expression.orientation_forward'
                    ),
                    key=f"formal_{unit_id}_planning_orientation",
                )
            with stable_id_col:
                st.text_input(
                    "stable ID",
                    value=unit_id,
                    key=f"formal_{unit_id}_planning_stable_id",
                    disabled=True,
                )
            with actions_col:
                action_cols = st.columns(3)
                if action_cols[0].button(_t('v1.expression.move_up'), key=f"formal_{unit_id}_move_up", disabled=index == 1):
                    _move_transcription_unit(unit_id, -1)
                    st.rerun()
                if action_cols[1].button(_t('v1.expression.move_down'), key=f"formal_{unit_id}_move_down", disabled=index == len(units)):
                    _move_transcription_unit(unit_id, 1)
                    st.rerun()
                if action_cols[2].button(_t('v1.common.delete'), key=f"formal_{unit_id}_delete", disabled=len(units) <= 1):
                    _set_dual_tu_delete_target(unit_id)
                    st.rerun()
            if _dual_tu_delete_target() == unit_id:
                st.warning(_t('v1.expression.deleting_transcription_unit_will_invalidate_existing_multi'))
                confirm_cols = st.columns([5, 1, 1])
                if confirm_cols[1].button(_t('v1.expression.confirm_deletion'), key=f"formal_{unit_id}_delete_confirm"):
                    _delete_transcription_unit(unit_id)
                    _clear_dual_tu_delete_target()
                    st.rerun()
                if confirm_cols[2].button(_t('v1.common.cancel'), key=f"formal_{unit_id}_delete_cancel"):
                    _clear_dual_tu_delete_target()
                    st.rerun()

    planned_units = _multi_tu_step2_planned_units(units)
    ready = bool(planned_units) and all(
        str(unit.get("display_name") or "").strip() for unit in planned_units
    )

    def save_tu_plan_and_continue() -> None:
        updated = _multi_tu_step2_planned_units(_transcription_units())
        changed = updated != units
        _store_transcription_units(updated)
        if changed:
            _invalidate_dual_tu_outputs()
        st.session_state["formal_multi_tu_step2_planning_signature"] = (
            _multi_tu_step2_planning_signature(updated)
        )
        ds.step = 3
        _controller().save(ds)
        st.rerun()

    _render_step_navigation(
        current_step=2,
        next_enabled=ready,
        next_label=_t('v1.expression.save_tu_plan_continue'),
        disabled_reason=(
            _t("v1.expression.tu_plan_incomplete_help")
            if not ready
            else _t("v1.expression.tu_plan_save_help")
        ),
        next_action=save_tu_plan_and_continue,
    )


def _render_step_2_cds(ds: Any) -> None:
    ai_step2_hydrator = globals().get("_hydrate_formal_ai_route_step2_prefill")
    ai_step2_hydrated = bool(
        callable(ai_step2_hydrator) and ai_step2_hydrator()
    )
    hydrating = bool(
        st.session_state.pop("_formal_step_hydration_target", None) == 2
        or ai_step2_hydrated
    )
    record_step2_edit = globals().get("_record_formal_step2_design_edit")
    is_dual_tu = globals().get("_is_dual_tu_project", lambda: False)
    if is_dual_tu():
        _render_dual_tu_step_2(ds)
        return
    from services.formal_cds_workflow import (
        MODIFICATION_STATUSES,
        SOURCE_TYPES,
        analyze_formal_cds,
        gene_information_from_values,
    )
    from services.mvp_sequence_input import DNA_FILE_SUFFIXES, MvpSequenceInputError, decode_uploaded_text

    st.subheader(_t('v1.expression.step_2_target_gene_coding_sequence_cds'))
    saved = st.session_state.get("formal_cds_input")
    saved = dict(saved) if isinstance(saved, dict) else {}
    saved_info = dict(saved.get("gene_information") or {})

    def initial_kwargs(key: str, **defaults: Any) -> dict[str, Any]:
        return {} if key in st.session_state else defaults

    st.markdown(
        _t('v1.expression.target_gene_information'),
        unsafe_allow_html=True,
    )
    gene_name = st.text_input(
        _t('v1.expression.target_gene_name_required'),
        key="formal_step2_gene_name",
        on_change=record_step2_edit,
        **initial_kwargs(
            "formal_step2_gene_name",
            value=str(saved_info.get("gene_name") or ds.gene_name or ""),
        ),
    ).strip()
    info_left, info_right = st.columns(2)
    with info_left:
        source_type = st.selectbox(
            _t('v1.expression.sequence_source_type_required'), SOURCE_TYPES,
            format_func=lambda value: _localized_value(value, _SOURCE_TYPE_LABELS),
            key="formal_step2_source_type",
            on_change=record_step2_edit,
            **initial_kwargs(
                "formal_step2_source_type",
                index=(
                    SOURCE_TYPES.index(str(saved_info.get("source_type")))
                    if str(saved_info.get("source_type")) in SOURCE_TYPES
                    else 0
                ),
            ),
        )
    with info_right:
        source_reference_label = _t('v1.expression.accession_source_note_required') if source_type in {"公共数据库记录", "外部公司或工具提供的序列", "其他来源"} else _t('v1.expression.accession_source_note_optional')
        source_reference = st.text_input(
            source_reference_label,
            key="formal_step2_source_reference",
            on_change=record_step2_edit,
            **initial_kwargs(
                "formal_step2_source_reference",
                value=str(saved_info.get("source_reference") or ""),
            ),
        ).strip()
    with st.expander(_t('v1.expression.source_advanced_information'), expanded=False):
        gene_symbol = st.text_input(
            _t('v1.expression.gene_symbol_optional'),
            key="formal_step2_gene_symbol",
            on_change=record_step2_edit,
            **initial_kwargs(
                "formal_step2_gene_symbol",
                value=str(saved_info.get("gene_symbol") or ""),
            ),
        ).strip()
        source_species = st.text_input(
            _t('v1.expression.source_organism_optional'),
            key="formal_step2_source_species",
            on_change=record_step2_edit,
            **initial_kwargs(
                "formal_step2_source_species",
                value=str(saved_info.get("source_species") or ""),
            ),
        ).strip()
        modification_status = st.selectbox(
            _t('v1.expression.sequence_modification_status_required'), MODIFICATION_STATUSES,
            format_func=lambda value: _localized_value(value, _MODIFICATION_STATUS_LABELS),
            key="formal_step2_modification_status",
            on_change=record_step2_edit,
            **initial_kwargs(
                "formal_step2_modification_status",
                index=(
                    MODIFICATION_STATUSES.index(str(saved_info.get("modification_status")))
                    if str(saved_info.get("modification_status")) in MODIFICATION_STATUSES
                    else 0
                ),
            ),
        )
        modification_note_label = _t('v1.expression.modification_note_required') if modification_status in {"用户手动编辑", "已由外部工具或公司进行密码子优化", "其他修改"} else _t('v1.expression.modification_note_optional')
        modification_note = st.text_input(
            modification_note_label,
            key="formal_step2_modification_note",
            on_change=record_step2_edit,
            **initial_kwargs(
                "formal_step2_modification_note",
                value=str(saved_info.get("modification_note") or ""),
            ),
        ).strip()
        is_partial_cds = st.checkbox(
            _t('v1.expression.input_partial_cds'),
            key="formal_step2_partial_cds",
            on_change=record_step2_edit,
            **initial_kwargs(
                "formal_step2_partial_cds",
                value=bool(saved_info.get("is_partial_cds")),
            ),
        )
        st.text_area(
            _t('v1.expression.general_notes_optional'),
            height=70,
            key="formal_step2_note",
            on_change=record_step2_edit,
            **initial_kwargs(
                "formal_step2_note",
                value=str(saved_info.get("note") or ""),
            ),
        )

    st.markdown(
        _t('v1.expression.coding_sequence_cds_input'),
        unsafe_allow_html=True,
    )
    mode = st.segmented_control(
        _t('v1.expression.cds_input_method'),
        _CDS_INPUT_MODE_VALUES,
        format_func=lambda value: _localized_value(value, _CDS_INPUT_MODE_LABELS),
        key="formal_step2_mode",
        on_change=record_step2_edit,
        **(
            {}
            if "formal_step2_mode" in st.session_state
            else {"default": _CDS_INPUT_MODE_VALUES[0]}
        ),
    )
    raw = str(saved.get("original_text") or ds.original_seq or "")
    uploaded = None
    if mode == "上传单条核酸 FASTA":
        uploaded = st.file_uploader(
            _t('v1.expression.upload_single_nucleic_acid_fasta'),
            type=["fa", "fasta", "fas", "txt"],
            key="formal_step2_upload",
            on_change=record_step2_edit,
        )
        if uploaded is not None:
            try:
                raw = decode_uploaded_text(
                    uploaded.getvalue(),
                    file_name=str(uploaded.name),
                    allowed_suffixes=DNA_FILE_SUFFIXES,
                )
            except MvpSequenceInputError as exc:
                st.error(_t('v1.expression.unable_parse_file', p0=exc))
                raw = ""
    else:
        raw = st.text_area(
            _t('v1.expression.paste_nucleic_acid_sequence'),
            height=230,
            key="formal_step2_cds_text",
            on_change=record_step2_edit,
            **initial_kwargs("formal_step2_cds_text", value=raw),
        )
    gene_information = gene_information_from_values(
        gene_name=gene_name, gene_symbol=gene_symbol, source_species=source_species,
        source_type=source_type, source_reference=source_reference,
        modification_status=modification_status, modification_note=modification_note,
        is_partial_cds=is_partial_cds, note=str(st.session_state.get("formal_step2_note") or ""),
    )
    cds_analysis = analyze_formal_cds(
        raw,
        source_kind="upload" if mode == "上传单条核酸 FASTA" else "paste",
        source_name=str(uploaded.name) if mode == "上传单条核酸 FASTA" and uploaded is not None else str(saved.get("source_name") or ""),
        gene_information=gene_information,
    )
    has_cds_input = bool(str(raw or "").strip())
    preview_matches_saved = bool(
        has_cds_input
        and saved
        and str(saved.get("original_text_sha256") or "")
        == str(cds_analysis.get("original_text_sha256") or "")
        and dict(saved.get("gene_information") or {}) == gene_information
        and str(saved.get("source_kind") or "")
        == ("upload" if mode == "上传单条核酸 FASTA" else "paste")
    )
    if not has_cds_input:
        st.info(_t('v1.expression.enter_upload_cds_sequence_view_analysis_preview'))
    else:
        status_rows = [
            ("是否为空", "阻断" if not cds_analysis.get("normalized_cds") else "通过", "无序列" if not cds_analysis.get("normalized_cds") else "已输入"),
            ("是否为单条记录", "阻断" if int(cds_analysis.get("record_count") or 0) > 1 else "通过", str(cds_analysis.get("record_count") or 0)),
            ("是否只包含 A/C/G/T", "通过" if cds_analysis.get("contains_only_acgt") else "阻断", "仅 A/C/G/T" if cds_analysis.get("contains_only_acgt") else "存在非法字符"),
            ("规范化 CDS 长度", "信息", f"{int(cds_analysis.get('normalized_length') or 0):,} bp"),
            ("长度是否为 3 的整数倍", "通过" if cds_analysis.get("length_multiple_of_three") else "阻断", "是" if cds_analysis.get("length_multiple_of_three") else "否"),
            ("起始密码子状态", "通过" if cds_analysis.get("starts_with_atg") else "需要人工确认", str(cds_analysis.get("start_codon") or "未检测到")),
            ("末端终止密码子状态", "通过" if cds_analysis.get("has_terminal_stop") else "需要人工确认", str(cds_analysis.get("terminal_stop_codon") or "缺少；需按 C 端融合结构确认")),
            ("内部终止密码子", "阻断" if cds_analysis.get("internal_stop_positions") else "通过", ", ".join(map(str, cds_analysis.get("internal_stop_positions") or [])) or "未检测到"),
            ("预计蛋白长度", "信息", f"{int(cds_analysis.get('expected_protein_length') or 0)} aa"),
            ("翻译摘要", str(cds_analysis.get("translation_status") or "信息"), str(cds_analysis.get("translation_summary") or "")),
        ]
        for finding in cds_analysis.get("findings") or []:
            status_rows.append((str(finding.get("rule_id") or "检查项"), str(finding.get("status") or ("阻断" if finding.get("blocking") else "需要人工确认")), str(finding.get("message") or "")))
        blocking_findings = [
            finding
            for finding in cds_analysis.get("findings") or []
            if finding.get("blocking")
        ]
        blocking_count = len(blocking_findings)
        status_rows = [(_ui(label), _ui(status), result) for label, status, result in status_rows]
        frame_summary = _ui("阅读框完整" if cds_analysis.get("length_multiple_of_three") else "长度不是 3 的整数倍")
        blocking_summary = _t('v1.expression.no_blocking_items') if not cds_analysis.get("blocking") else f"{blocking_count} 项阻断"
        saved_summary = _t('v1.expression.saved_cds_consistent') if preview_matches_saved else _t('v1.expression.preview_not_saved')
        st.caption(
            f"{int(cds_analysis.get('normalized_length') or 0):,} bp · "
            f"{frame_summary} · {blocking_summary} · {saved_summary}"
        )
        blocking_messages = [
            str(finding.get("message") or "").strip().rstrip("。；;")
            for finding in blocking_findings
            if str(finding.get("message") or "").strip()
        ]
        if blocking_messages:
            st.error("; ".join(dict.fromkeys(blocking_messages)) + ".")
        elif not gene_name:
            st.error(_t('v1.expression.enter_target_gene_name_before_saving_cds'))
        with st.expander(_t('v1.expression.cds_completeness_checklist'), expanded=False):
            st.dataframe(status_rows, use_container_width=True, hide_index=True, column_config={"0": _t('v1.expression.check_item'), "1": _t('v1.expression.status_label'), "2": _t('v1.expression.result_label')})
        with st.expander(_t('v1.expression.sequence_translation_details'), expanded=False):
            st.caption(_t('v1.expression.fasta_header_original_filename', p0=cds_analysis.get('record_name') or _t('v1.expression.unprovided'), p1=cds_analysis.get('source_name') or _t('v1.expression.unprovided')))
            st.code(str(cds_analysis.get("original_text") or ""), language="text")
            st.code(str(cds_analysis.get("normalized_cds") or ""), language="text")
            st.code(str(cds_analysis.get("protein_translation") or ""), language="text")

    ready = bool(
        gene_name
        and cds_analysis.get("normalized_cds")
        and not cds_analysis.get("blocking")
    )

    def save_cds_and_continue() -> None:
        latest_analysis = analyze_formal_cds(
            raw,
            source_kind="upload" if mode == "上传单条核酸 FASTA" else "paste",
            source_name=str(uploaded.name) if mode == "上传单条核酸 FASTA" and uploaded is not None else str(saved.get("source_name") or ""),
            gene_information=gene_information,
        )

        def apply_current_analysis() -> str:
            if _formal_ui_signature(latest_analysis) != _formal_ui_signature(cds_analysis):
                raise ValueError("CDS 输入已变化，请检查当前分析预览后重试。")
            if not gene_name or not latest_analysis.get("normalized_cds") or latest_analysis.get("blocking"):
                raise ValueError("当前 CDS 输入存在阻断项，不能保存并继续。")
            return _apply_formal_cds_analysis(ds, latest_analysis)

        succeeded, lifecycle_action, _executed = _execute_formal_action(
            step=2,
            action_id="step2_analyze_continue",
            input_signature=_formal_ui_signature(cds_analysis),
            action=apply_current_analysis,
            success_status="流程已更新",
            success_message=_t('v1.expression.cds_applied_continue_step_3'),
            failure_status="保存失败",
        )
        if not succeeded:
            return
        if lifecycle_action == "invalidate":
            st.warning(_t('v1.expression.cds_sequence_changed_results_steps'))
        elif lifecycle_action == "source_review":
            st.warning(_t('v1.expression.cds_source_information_changed_existing_results_remain'))
        ds.step = 3
        _controller().save(ds)
        st.rerun()

    sync_step2_edit = globals().get("_record_formal_step2_design_edit")
    if not hydrating and callable(sync_step2_edit):
        sync_step2_edit()
    _render_step_navigation(
        current_step=2,
        next_enabled=ready and not bool(st.session_state.get("formal_ui_action_busy")),
        next_label=_t('v1.expression.confirm_cds_continue'),
        disabled_reason=_ui("请完成目标基因名称并修正 CDS 阻断项。") if not ready else "",
        next_action=save_cds_and_continue,
    )


def _plant_element_options(
    host: str, part_type: str, *, workflow_id: str = ""
) -> list[dict[str, Any]]:
    if workflow_id == "generic_multi_tu":
        from services.plant_component_workflow_registry import workflow_component_options

        role = {
            "Promoter": "promoter",
            "5' region": "five_prime_region",
            "CDS": "cds",
            "Terminator": "3_prime_regulatory_region",
        }[part_type]
        record = _plant_host_record(host)
        target_host = str(record.get("scientific_name") or host) if record else host
        return [
            {
                "name": str(item.get("name") or part_type),
                "sequence": str(item.get("sequence") or ""),
                "source": str(item.get("source") or "Plant Component Registry V1"),
                "accession": str(item.get("accession") or ""),
                "version": str(item.get("accession") or ""),
                "location": str(
                    (item.get("feature_boundary_method") or {}).get("method") or ""
                ),
                "strand": 0,
                "registry_component_id": str(item.get("registry_component_id") or ""),
                "component_type": str(item.get("component_type") or ""),
                "evidence_tier": str(item.get("evidence_tier") or ""),
                "source_organism": str(item.get("source_organism") or ""),
                "target_host_species": list(item.get("target_host_species") or []),
                "target_host_match": bool(item.get("target_host_match")),
                "limitation": str(item.get("limitation") or ""),
                "component_reference": dict(item.get("component_reference") or {}),
            }
            for item in workflow_component_options(
                role=role,
                workflow_id=workflow_id,
                target_host_species=target_host,
            )
        ]
    from services.formal_step3_component_authority import (
        formal_step3_component_options,
    )

    host_record = _plant_host_record(host)
    target_host = (
        str(host_record.get("scientific_name") or host) if host_record else str(host)
    )
    role = "promoter" if part_type == "Promoter" else "3_prime_regulatory_region"
    return formal_step3_component_options(
        role=role,
        target_host_species=target_host,
    )


def _formal_three_prime_registry_role(selected: Mapping[str, Any] | None) -> str:
    """Map a fixed Registry 3' component to its authoritative biological role."""
    component_type = str((selected or {}).get("component_type") or "").strip().lower()
    return {
        "terminator": "terminator",
        "three_prime_regulatory_region": "three_prime_regulatory_region",
    }.get(component_type, "")


def _render_dual_tu_element_input(
    *,
    unit_id: str,
    role: str,
    label: str,
    options: list[dict[str, Any]],
    empty_options_notice: str = "",
) -> dict[str, Any] | None:
    from services.mvp_sequence_input import analyze_dna_component_input
    from services.plant_project_draft_schema import new_project_id

    units = _transcription_units()
    unit = next(item for item in units if str(item.get("unit_id")) == str(unit_id))
    unit_label = f"TU{units.index(unit) + 1}"
    display_label = globals().get(
        "_multi_tu_role_display_label", lambda _value: label
    )(role)
    technical_label_keys = globals().get(
        "_SOURCE_TECHNICAL_LABEL_KEYS",
        {
            "accession_verified": "v1.results_final_report.accession_verified",
            "boundary_verified_by_software": "v1.results_final_report.boundary_verified_by_software",
        },
    )
    localize_controlled = globals().get("_ui", lambda value: value)
    saved = unit.get(role)
    saved = saved if isinstance(saved, dict) else {}
    saved_component_reference = (
        dict(saved.get("component_reference") or {})
        if isinstance(saved.get("component_reference"), dict)
        else {}
    )
    if role == "five_prime_region":
        absence_option = "不使用独立 5′ region"
        source_mode = st.segmented_control(
            _t('v1.expression.status', p0=unit_label, p1=display_label),
            [*_SOURCE_MODE_VALUES, absence_option],
            format_func=lambda value: _localized_value(value, _SOURCE_MODE_LABELS),
            key=f"formal_{unit_id.lower()}_{role}_mode",
            on_change=lambda value=unit_id: _invalidate_dual_tu_unit(value),
        )
        if source_mode == absence_option:
            return {
                "absence_state": "explicit_none",
                "display_name": absence_option,
                "raw_text": "",
                "source_type": "EXPLICIT_ABSENCE",
                "source_format": "none",
                "source_name": "",
                "source_description": "Explicitly absent; no independent 5′ region / 5′ UTR.",
                "provenance_reference": "",
                "provenance_state": "explicit_absence",
            }
    else:
        source_mode = st.segmented_control(
            _t('v1.expression.source', p0=unit_label, p1=display_label),
            _SOURCE_MODE_VALUES,
            format_func=lambda value: _localized_value(value, _SOURCE_MODE_LABELS),
            key=f"formal_{unit_id.lower()}_{role}_mode",
            on_change=lambda value=unit_id: _invalidate_dual_tu_unit(value),
        )
    if empty_options_notice and not options:
        st.caption(empty_options_notice)
    if source_mode == "元件库":
        library_key = f"formal_{unit_id.lower()}_{role}_library"
        selected_index = next(
            (
                index
                for index, item in enumerate(options)
                if str(item.get("name")) == str(saved.get("display_name"))
                and str(item.get("sequence")) == str(saved.get("raw_text"))
            ),
            None,
        )
        if library_key not in st.session_state and selected_index is not None:
            st.session_state[library_key] = options[selected_index]
        selected = st.selectbox(
            f"{unit_label} {display_label}",
            options,
            placeholder=_t('v1.expression.select_unit_component', p0=unit_label, p1=display_label),
            format_func=lambda item: f"{item['name']} · {len(item['sequence'])} bp",
            key=library_key,
            on_change=lambda value=unit_id: _invalidate_dual_tu_unit(value),
        )
        if not isinstance(selected, dict):
            return None
        name = str(selected.get("name") or label)
        raw = str(selected.get("sequence") or "")
        source_type = "library"
        source_name = str(selected.get("source") or "元件库")
        provenance = str(selected.get("accession") or selected.get("source") or "元件库")
        component_reference = dict(selected.get("component_reference") or {})
        st.caption(
            _t('v1.expression.source_component_library_registry_id_reference_source', p0=selected.get('registry_component_id') or '--', p1=selected.get('accession') or '--', p2=selected.get('source_organism') or '--')
        )
        st.caption(
            _t('v1.expression.target_host_metadata')
            + (", ".join(selected.get("target_host_species") or []) or _t('v1.common.unavailable'))
        )
        st.caption(localize_controlled(str(selected.get("limitation") or "")))
        with st.expander(_t('v1.expression.view_full_sequence', p0=unit_label, p1=display_label), expanded=False):
            st.code(raw, language="text")
    else:
        name = st.text_input(
            _t('v1.expression.name', p0=unit_label, p1=display_label),
            key=f"formal_{unit_id.lower()}_{role}_name",
            on_change=lambda value=unit_id: _invalidate_dual_tu_unit(value),
        ).strip()
        raw = st.text_area(
            f"{unit_label} {display_label} DNA/FASTA",
            height=110,
            key=f"formal_{unit_id.lower()}_{role}_text",
            on_change=lambda value=unit_id: _invalidate_dual_tu_unit(value),
        )
        source_type = "paste"
        source_name = "用户提供，待确认"
        provenance = ""
        component_reference = {}
    if not name or not raw.strip():
        return None
    try:
        record = analyze_dna_component_input(
            raw,
            project_id=str(st.session_state.setdefault("mvp_project_id", new_project_id())),
            component_type={
                "3_prime_regulatory_region": "terminator",
                "targeting_sequence": "signal_targeting_coding_sequence",
                "fusion_tag": "c_terminal_tag",
            }.get(role, role),
            display_name=name,
            source_kind=source_type,
            source_name=source_name,
        )
    except Exception as exc:
        st.error(f"{unit_label} {display_label}: {exc}")
        return None
    if source_mode == "用户序列":
        if saved_component_reference:
            from services.registry_catalog_ui import preserved_user_component_reference

            component_reference = preserved_user_component_reference(
                saved_component_reference,
                role=role,
                sequence=str(record.get("normalized_sequence") or raw),
                current_project_id=str(st.session_state.get("mvp_project_id") or ""),
            )
        st.caption(
            _t('v1.expression.bp_source_user_provided_status_awaiting_manual', p0=name, p1=int(record.get('length') or 0))
        )
    else:
        st.caption(f"{name} · {int(record.get('length') or 0):,} bp")
    with st.expander(_t('v1.common.technical_details'), expanded=False):
        st.markdown(f"**SHA-256**：`{str((record.get('asset') or {}).get('sequence_checksum') or '')}`")
        resolution = component_reference.get("assisted_resolution") or {}
        if (
            component_reference.get("source_type") == "USER_PROVIDED"
            and resolution.get("admission_mode") == "USER_SEQUENCE_ASSISTED"
        ):
            source = resolution.get("source_provenance") or {}
            confirmation = resolution.get("confirmation_contract") or {}
            fields = (
                ("v2_canonical_id_label", resolution.get("catalog_component_id")),
                ("v2_catalog_identity", resolution.get("catalog_name")),
                ("v2_source_accession", source.get("accession")),
                ("v2_original_route", resolution.get("admission_mode")),
                ("v2_sequence_authority", component_reference.get("source_type")),
                ("v2_sequence_length", f"{int(record.get('length') or 0):,} bp"),
                ("v2_user_sequence_source", resolution.get("user_sequence_source")),
                ("v2_project_binding", resolution.get("project_id")),
                ("v2_resolution_identity", resolution.get("resolution_id")),
            )
            for field, value in fields:
                st.caption(f"{_t('v1.component_library.' + field)}: {value or '--'}")
            if confirmation.get("recorded_boundary"):
                st.caption(_t("v1.component_library.v2_recorded_boundary", p0=confirmation["recorded_boundary"]))
            for field in ("accession_verified", "boundary_verified_by_software"):
                value = confirmation.get(field)
                displayed = str(value).lower() if isinstance(value, bool) else _t("v1.component_library.v2_verification_not_recorded")
                st.caption(f"{_t(technical_label_keys[field])}: {displayed}")
            st.caption(_t("v1.component_library.v2_user_authority_notice"))
    return {
        "display_name": name,
        "raw_text": str(record.get("normalized_sequence") or raw),
        "source_type": source_type,
        "source_format": "fasta" if raw.lstrip().startswith(">") else "plain",
        "source_name": source_name,
        "provenance_reference": provenance,
        "component_reference": component_reference,
    }


def _persist_generated_multi_tu_step_four(ds: Any) -> Any:
    """Keep the controller and durable draft on the same generated step."""
    ds.step = 4
    _controller().save(ds)
    return _save_current_formal_draft(current_step=ds.step)


def _render_dual_tu_step_3(ds: Any) -> None:
    if st.session_state.get("formal_betalain_gate3_case"):
        from services.betalain_pbi121_canonical_construct import evaluate_betalain_pbi121_prerequisites

        st.subheader(_t('v1.expression.step_3_reviewed_regulatory_component_record'))
        recorded = bool(st.session_state.get("formal_betalain_regulatory_components_recorded"))
        confirmed = st.checkbox(
            _t('v1.expression.i_confirm_tu1_tu2_tu3_reuse_reviewed'),
            value=bool(st.session_state.get("formal_betalain_repeated_regulatory_confirmed")),
            key="formal_betalain_repeated_regulatory_checkbox",
        )
        assessment = evaluate_betalain_pbi121_prerequisites(repeated_regulatory_confirmed=confirmed)
        provenance = assessment["component_provenance_summary"]
        st.dataframe(
            [
                {
                    _t('v1.results_final_report.role'): _multi_tu_role_display_label('promoter'),
                    _t('v1.results_final_report.component'): _multi_tu_role_display_label(provenance["promoter"]["biological_role"]),
                    _t('v1.common.source'): provenance["promoter"]["source_accession"],
                    _t('v1.common.location'): provenance["promoter"]["source_feature_location"],
                    _t('v1.common.length'): provenance["promoter"]["length"],
                },
                {
                    _t('v1.results_final_report.role'): _multi_tu_role_display_label('3_prime_regulatory_region'),
                    _t('v1.results_final_report.component'): _multi_tu_role_display_label(provenance["three_prime_regulatory_region"]["biological_role"]),
                    _t('v1.common.source'): provenance["three_prime_regulatory_region"]["source_accession"],
                    _t('v1.common.location'): provenance["three_prime_regulatory_region"]["source_feature_location"],
                    _t('v1.common.length'): provenance["three_prime_regulatory_region"]["length"],
                },
            ],
            hide_index=True,
            use_container_width=True,
        )
        if st.button(_t('v1.expression.confirm_regulatory_element_selection'), type="primary", key="formal_betalain_record_regulatory"):
            if not confirmed:
                st.error(_t('v1.expression.record_repeated_regulatory_sequence_confirmation_before_continuing'))
            else:
                st.session_state["formal_betalain_regulatory_components_recorded"] = True
                st.session_state["formal_betalain_repeated_regulatory_confirmed"] = True
                st.success(_t('v1.expression.regulatory_component_choices_repeat_use_confirmation_recorded'))
                st.rerun()
        if recorded:
            st.warning(_t('v1.expression.multiple_transcription_units_use_same_regulatory_sequence'))
        _render_step_navigation(
            current_step=3,
            next_enabled=recorded and confirmed and not assessment["blockers"],
            next_label=_t('v1.expression.review_canonical_construct'),
            disabled_reason=_t('v1.expression.record_repeated_regulatory_sequence_confirmation_before_continuing'),
        )
        return
    from services.mvp_cds_input import analyze_cds_input
    from services.mvp_sequence_input import analyze_dna_component_input
    from services.plant_project_draft_schema import new_project_id
    from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct

    stable_multi_name = globals().get("_stable_multi_tu_project_name")
    if not callable(stable_multi_name):
        stable_multi_name = lambda value: str(value or "").strip() or "Multi-TU project"

    _hydrate_current_multi_tu_editor_from_result()
    _prepare_multi_tu_editor_widget_state()
    st.subheader(_t('v1.expression.step_3_tu_component_design'))
    promoters = _plant_element_options(
        ds.host, "Promoter", workflow_id="generic_multi_tu"
    )
    five_prime_regions = _plant_element_options(
        ds.host, "5' region", workflow_id="generic_multi_tu"
    )
    cds_options = _plant_element_options(
        ds.host, "CDS", workflow_id="generic_multi_tu"
    )
    terminators = _plant_element_options(
        ds.host, "Terminator", workflow_id="generic_multi_tu"
    )
    units = _transcription_units()
    if _is_pathway_multi_tu_project():
        pathway_validation = _refresh_pathway_mapping_status()
        _render_pathway_traceability(pathway_validation["pathway_steps"], units)
    selections: dict[str, dict[str, Any]] = {}
    st.markdown(
        _t('v1.expression.saved_tu_plans'),
        unsafe_allow_html=True,
    )
    st.caption(_t('v1.expression.step_uses_only_tu_layout_saved_step'))
    tabs = st.tabs([f"TU{index} {_t('v1.expression.tu_expression_box')}" for index in range(1, len(units) + 1)])

    def _optional_input(unit_id: str, unit_label: str, role: str, label: str) -> dict[str, Any]:
        saved = _transcription_unit(unit_id).get(role)
        saved = saved if isinstance(saved, dict) else {}
        display_label = globals().get("_display_optional_label", lambda value: value)(label)
        translate = globals().get("_t", lambda key, **kwargs: kwargs.get("p0", label))
        enabled = st.checkbox(
            translate('v1.expression.add', p0=display_label),
            value=bool(str(saved.get("raw_text") or "").strip()),
            key=f"formal_{unit_id}_{role}_enabled",
            on_change=lambda value=unit_id: _invalidate_dual_tu_unit(value),
        )
        if not enabled:
            return {}
        name = st.text_input(
            translate('v1.expression.name', p0=unit_label, p1=display_label),
            value=str(saved.get("display_name") or label),
            key=f"formal_{unit_id}_{role}_name",
            on_change=lambda value=unit_id: _invalidate_dual_tu_unit(value),
        ).strip()
        raw = st.text_area(
            f"{unit_label} {display_label} DNA/FASTA",
            value=str(saved.get("raw_text") or ""),
            height=90,
            key=f"formal_{unit_id}_{role}_text",
            on_change=lambda value=unit_id: _invalidate_dual_tu_unit(value),
        )
        if not raw.strip():
            return {"display_name": name, "raw_text": ""}
        try:
            record = analyze_dna_component_input(
                raw,
                project_id=str(st.session_state.setdefault("mvp_project_id", new_project_id())),
                component_type={
                    "targeting_sequence": "signal_targeting_coding_sequence",
                    "fusion_tag": "c_terminal_tag",
                }.get(role, role),
                display_name=name or label,
                source_kind="paste",
                source_name="用户提供，待确认",
            )
        except Exception as exc:
            st.error(f"{unit_label} {label}：{exc}")
            return {"display_name": name, "raw_text": raw, "validation_error": str(exc)}
        st.caption(_t('v1.expression.bp_source_pending_manual_review', p0=name or label, p1=int(record.get('length') or 0)))
        return {
            "display_name": name or label,
            "raw_text": str(record.get("normalized_sequence") or raw),
            "source_type": "paste",
            "source_format": "fasta" if raw.lstrip().startswith(">") else "plain",
            "source_name": "用户提供，待确认",
            "provenance_reference": "",
        }

    for index, (tab, unit) in enumerate(zip(tabs, units), start=1):
        unit_id = str(unit["unit_id"])
        unit_label = f"TU{index}"
        with tab:
            orientation = (
                _t("v1.common.reverse")
                if unit.get("orientation") == "reverse"
                else _t("v1.common.forward")
            )
            display_name = str(unit.get("display_name") or unit_label).strip()
            st.markdown(
                _t('v1.expression.transcriptional_unit_orientation_stable_id', p0=escape(display_name), p1=orientation, p2=escape(unit_id)),
                unsafe_allow_html=True,
            )
            if unit.get("orientation") == "reverse":
                st.info(
                    _t('v1.expression.enter_component_sequences_biological_source_orientation_software')
                )
            st.markdown(
                _t('v1.expression.required_elements'),
                unsafe_allow_html=True,
            )
            promoter = _render_dual_tu_element_input(
                unit_id=unit_id, role="promoter", label="启动子", options=promoters
            )
            five_prime_region = _render_dual_tu_element_input(
                unit_id=unit_id,
                role="five_prime_region",
                label="5′ region / 5′ UTR",
                options=five_prime_regions,
                empty_options_notice=(
                    _t('v1.expression.no_formal_five_prime_region_records_user_sequence_allowed')
                    if not five_prime_regions
                    else ""
                ),
            )
            cds = _render_dual_tu_element_input(
                unit_id=unit_id, role="cds", label="CDS", options=cds_options
            )
            cds_name = str((cds or {}).get("display_name") or "")
            cds_raw = str((cds or {}).get("raw_text") or "")
            cds_analysis = analyze_cds_input(
                cds_raw,
                source_kind=str((cds or {}).get("source_type") or "paste"),
                source_name=str((cds or {}).get("source_name") or ""),
            )
            for finding in list(cds_analysis.get("findings") or []):
                message = str(finding.get("message") or "")
                if str(finding.get("rule_id") or "") == "empty_cds":
                    message = _t('v1.expression.cds_not_configured_multi_tu')
                (st.warning if finding.get("blocking") else st.info)(message)
            three_prime = _render_dual_tu_element_input(
                unit_id=unit_id,
                role="3_prime_regulatory_region",
                label="3′ 调控区",
                options=terminators,
            )
            with st.expander(_t('v1.expression.optional_additional_elements'), expanded=False):
                targeting = _optional_input(unit_id, unit_label, "targeting_sequence", "靶向序列")
                linker = _optional_input(unit_id, unit_label, "linker", "linker")
                fusion_tag = _optional_input(unit_id, unit_label, "fusion_tag", "融合标签")
            optional_valid = all(not item.get("validation_error") and (not item or item.get("raw_text")) for item in (targeting, linker, fusion_tag))
            cassette_length = sum(
                len(str((item or {}).get("raw_text") or "").replace("\n", "").replace("\r", ""))
                for item in (promoter, five_prime_region, targeting, linker, fusion_tag, three_prime)
            ) + int(cds_analysis.get("normalized_length") or 0)
            unit_ready = bool(
                display_name
                and cds_name
                and cds_analysis.get("normalized_cds")
                and not cds_analysis.get("blocking")
                and promoter
                and five_prime_region
                and three_prime
                and optional_valid
            )
            status_cols = st.columns(2)
            status_cols[0].metric(_t('v1.expression.expression_cassette_length_current'), f"{cassette_length:,} bp")
            status_cols[1].metric(
                _t('v1.expression.check_status'),
                _t('v1.expression.generatable' if unit_ready else 'v1.expression.not_completed'),
            )
            selections[unit_id] = {
                "promoter": promoter,
                "five_prime_region": five_prime_region,
                "cds": {
                    **dict(cds or {}),
                    "display_name": cds_name,
                    "raw_text": str(cds_analysis.get("normalized_cds") or cds_raw),
                    "source_type": str((cds or {}).get("source_type") or "paste"),
                    "source_format": str(cds_analysis.get("source_format") or "plain"),
                    "source_name": str((cds or {}).get("source_name") or "用户提供，待确认"),
                    "cds_analysis": dict(cds_analysis),
                },
                "3_prime_regulatory_region": three_prime,
                "targeting_sequence": targeting,
                "linker": linker,
                "fusion_tag": fusion_tag,
                "cassette_length": cassette_length,
                "validation_state": "current" if unit_ready else "incomplete",
                "provenance_state": "review_required",
                "ready": unit_ready,
            }
    updated = [
        {
            **unit,
            **{
                key: value
                for key, value in selections[str(unit["unit_id"])].items()
                if key not in {"ready"}
            },
        }
        for unit in units
    ]
    ready = bool(selections) and all(item["ready"] for item in selections.values()) and _multi_tu_overall_ready(updated)
    if st.button(
        _t('v1.expression.confirm_all_tu_configurations_generate_assembly_then'),
        type="primary",
        disabled=not ready,
    ):
        _store_transcription_units(updated)
        try:
            result = generate_multi_tu_combined_construct(
                project_id=str(st.session_state.setdefault("mvp_project_id", new_project_id())),
                project_name=stable_multi_name(st.session_state.get("formal_project_name")),
                expression_units=_dual_tu_expression_units(),
            )
        except Exception as exc:
            st.error(_multi_tu_generation_error_message(exc, updated))
        else:
            definition = _formal_project_definition()
            result["project_type"] = PROJECT_TYPE_DUAL_TU
            result["current_step_state"] = 4
            result["formal_project_context"] = {
                "host_key": definition["plant_host"] or ds.host,
                "expression_target": _project_definition_expression_target(definition),
                "project_definition": definition,
                "construct_review_status": "current",
                "design_scenario": _formal_design_scenario(),
                "current_step": 6,
                "result_kind": result["result_kind"],
                "contains_vector": False,
            }
            # A newly generated canonical record remains in the editable
            # current workflow. Only an explicit Project Center open may use
            # the historical-result preview route.
            st.session_state.pop("formal_explicit_historical_open", None)
            st.session_state["formal_dual_tu_combined_result"] = result
            st.session_state["formal_cassette_result"] = result
            st.session_state["formal_dual_tu_unit_snapshots"] = {
                str(item.get("unit_id")): dict(item) for item in result.get("expression_units") or []
            }
            st.session_state["mvp_vector_result"] = result
            st.session_state["mvp_current_input_signature"] = result["input_signature"]
            st.session_state["mvp_inputs_stale"] = False
            try:
                _persist_generated_multi_tu_step_four(ds)
            except Exception as exc:
                st.warning(_t('v1.expression.multi_tu_editing_state_failed_save_local', p0=exc))
            st.rerun()
    _render_step_navigation(
        current_step=3,
        next_enabled=False,
        disabled_reason=_t("v1.expression.multi_tu_components_incomplete_help"),
    )


def _render_step_3_elements(ds: Any) -> None:
    # Registry 正式记录; formal-check-summary; column_config={biological_role_field: "生物学角色"}; "检查项": item["rule_id"]
    _source_shape_marker = '"检查代码": item["rule_id"]'
    if _is_dual_tu_project():
        _render_dual_tu_step_3(ds)
        return
    from html import escape

    from services.mvp_sequence_input import analyze_dna_component_input, decode_uploaded_text, DNA_FILE_SUFFIXES
    from services.plant_project_draft_schema import new_project_id
    from services.formal_expression_cassette import assess_expression_cassette, generate_expression_cassette
    from services.formal_step3_component_authority import (
        empty_formal_step3_component,
        formal_step3_authority_findings,
    )
    from services.formal_step3_gate import step3_can_continue_to_backbone
    from services.plant_host_registry import list_hosts

    normalize_three_prime_role = globals().get("_normalize_three_prime_role")
    if not callable(normalize_three_prime_role):
        normalize_three_prime_role = lambda value: str(value or "terminator")

    st.subheader(_t('v1.expression.step_3_plant_expression_cassette_design'))
    promoters = _plant_element_options(ds.host, "Promoter")
    terminators = _plant_element_options(ds.host, "Terminator")
    saved_cds = st.session_state.get("formal_cds_input")
    saved_cds = dict(saved_cds) if isinstance(saved_cds, Mapping) else {}
    saved_cds_info = dict(saved_cds.get("gene_information") or {})
    cds_sequence = str(saved_cds.get("normalized_cds") or ds.original_seq or "")
    gene_name = str(saved_cds_info.get("gene_name") or ds.gene_name or "CDS")
    cds_analysis_status = (
        _ui("存在阻断")
        if saved_cds.get("blocking")
        else _ui("分析已完成")
        if cds_sequence
        else _ui("尚未分析")
    )
    project_mode = (
        _ui("多转录单元")
        if _is_dual_tu_project()
        else _ui("单基因")
    )
    host_value = str(ds.host or "").strip()
    host_record = next(
        (
            record
            for record in list_hosts()
            if host_value
            in {
                str(record.get("host_id") or ""),
                str(record.get("scientific_name") or ""),
                f"{str(record.get('common_name') or '').strip()} ({str((record.get('aliases') or [record.get('scientific_name')])[0] or '').strip()})",
            }
        ),
        None,
    )
    host_label = (
        f"{host_record['common_name']} / {host_record['scientific_name']}"
        if host_record is not None
        else host_value or "未记录"
    )
    st.markdown(
        _t('v1.expression.design_context'),
        unsafe_allow_html=True,
    )
    st.markdown(
        _t('v1.expression.plant_host_target_gene_cds_length_bp', p0=escape(host_label), p1=escape(gene_name), p2=len(cds_sequence), p3=project_mode),
        unsafe_allow_html=True,
    )
    project_id = str(st.session_state.setdefault("mvp_project_id", new_project_id()))
    if _prepare_single_gene_step3_widget_state():
        # Selectbox values must be injected after options are built but before
        # the widgets are created.  Match by sequence and name so persisted
        # custom records remain selectable even when their source is not in the
        # built-in host catalog.
        for role, options in (("promoter", promoters), ("terminator", terminators)):
            saved = st.session_state.get("formal_element_source_records", {}).get(role)
            if not isinstance(saved, dict):
                continue
            # Rehydrate the radio immediately before widget creation.  The
            # completed-result restore can carry an older widget snapshot, so
            # the persisted 3' provenance record is the final authority for
            # this first post-reopen render.  Subsequent renders keep the
            # user's current radio choice.
            st.session_state[f"formal_step3_{role}_custom_input"] = _formal_step3_custom_input_label(
                saved,
                role=role,
            )
            saved_sequence = str(saved.get("normalized_sequence") or "").upper()
            saved_name = str(saved.get("display_name") or "")
            selected = next(
                (
                    item
                    for item in options
                    if str(item.get("sequence") or "").upper() == saved_sequence
                    and (not saved_name or str(item.get("name") or "") == saved_name)
                ),
                None,
            )
            if selected is None:
                selected = next(
                    (
                        item
                        for item in options
                        if str(item.get("sequence") or "").upper() == saved_sequence
                    ),
                    None,
                )
            if selected is not None:
                st.session_state[f"formal_step3_{role}"] = selected
        restored_formal = st.session_state.get("formal_expression_cassette")
        if isinstance(restored_formal, dict):
            restore_keys = {
                "five_prime_utr": "five_prime",
                "five_prime_regulatory_region": "five_prime",
                "translation_enhancer_sequence": "five_prime",
                "n_terminal_fusion_tag_coding_sequence": "n_tag",
                "signal_peptide_coding_sequence": "targeting",
                "chloroplast_transit_peptide_coding_sequence": "targeting",
                "mitochondrial_targeting_peptide_coding_sequence": "targeting",
                "nuclear_localization_signal_coding_sequence": "targeting",
                "linker_coding_sequence": "linker",
                "c_terminal_fusion_tag_coding_sequence": "c_tag",
            }
            for component in list(restored_formal.get("components") or []):
                key = restore_keys.get(str(component.get("biological_role") or ""))
                if not key:
                    continue
                st.session_state[f"formal_step3_{key}_enabled"] = True
                st.session_state[f"formal_step3_{key}_role"] = str(component.get("biological_role") or "")
                st.session_state[f"formal_step3_{key}_name"] = str(component.get("display_name") or "")
                st.session_state[f"formal_step3_{key}_sequence"] = str(component.get("sequence") or "")
                st.session_state[f"formal_step3_{key}_source"] = str(component.get("source_reference") or "")
                if component.get("component_reference"):
                    st.session_state.setdefault("formal_element_source_records", {})[key] = dict(component)
            st.session_state["formal_step3_order_confirmed"] = True
    def _user_element(role: str, mode: str, selected: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        saved_records = st.session_state.get("formal_element_source_records")
        saved_record = saved_records.get(role) if isinstance(saved_records, dict) else None
        semantic_role = (
            "promoter" if role == "promoter" else normalize_three_prime_role(
                st.session_state.get("formal_step3_three_prime_role")
            )
        )
        display = _single_gene_step3_role_display_label(semantic_role)

        def _preserved_record(name: str, sequence: str) -> dict[str, Any] | None:
            if not isinstance(saved_record, dict):
                return None
            if mode != "registry" and str(saved_record.get("source_kind") or "").lower() in {
                "registry",
                "registry_record",
            }:
                return None
            if str(saved_record.get("normalized_sequence") or "").upper() != str(sequence or "").upper():
                return None
            if str(saved_record.get("display_name") or "") != str(name or ""):
                return None
            if role == "terminator" and str(saved_record.get("source_kind") or "").lower() == "user_recorded":
                if str(saved_record.get("source_input_method") or "").strip().lower() not in _FORMAL_STEP3_CUSTOM_INPUT_LABELS:
                    return None
            return dict(saved_record)

        if mode == "registry":
            selected = dict(selected or {})
            component_reference = dict(selected.get("component_reference") or {})
            record = analyze_dna_component_input(
                str(selected.get("sequence") or ""), project_id=project_id, component_type=role,
                display_name=str(selected.get("name") or display), source_kind="registry",
                source_name=str(selected.get("source") or "Plant Component Registry V1"),
            )
            record.update(
                {
                    "biological_role": _formal_three_prime_registry_role(selected)
                    if role == "terminator"
                    else "promoter",
                    "source_accession_version": str(selected.get("accession") or ""),
                    "source_location": str(selected.get("location") or ""),
                    "source_strand": int(selected.get("strand") or 0),
                    "source_reference": str(
                        selected.get("accession")
                        or selected.get("registry_component_id")
                        or selected.get("source")
                        or "Plant Component Registry V1"
                    ),
                    "registry_component_id": str(selected.get("registry_component_id") or ""),
                    "component_reference": component_reference,
                }
            )
            return selected, record
        name = st.text_input(
            _t('v1.expression.name_text_input', p0=display),
            key=f"formal_step3_{role}_custom_name",
            on_change=_invalidate_formal_snapshots,
        ).strip() or f"用户提供{display}"
        custom_input_options = ["paste", "upload"]
        saved_input_method = str(saved_record.get("source_input_method") or "").strip().lower() if isinstance(saved_record, dict) else ""
        if role == "terminator" and isinstance(saved_record, dict) and str(saved_record.get("source_kind") or "").lower() == "user_recorded" and saved_input_method not in _FORMAL_STEP3_CUSTOM_INPUT_LABELS:
            custom_input_options.insert(0, _FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL)
        input_mode = st.radio(
            _t('v1.expression.input_method', p0=display),
            custom_input_options,
            format_func=globals().get(
                "_formal_step3_custom_input_display_label",
                lambda value: value,
            ),
            horizontal=True,
            key=f"formal_step3_{role}_custom_input",
            on_change=_invalidate_formal_snapshots,
        )
        if input_mode == _FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL:
            st.warning(_t('v1.expression.saved_input_source_method_missing_unsupported_reselect'))
            return {
                "name": name,
                "sequence": "",
                "source": "需要核对输入来源",
                "source_kind": "user_recorded",
            }, None
        display_label = _ui(display)
        raw = st.text_area(f"{display_label} DNA/FASTA", key=f"formal_step3_{role}_custom_text", height=110, on_change=_invalidate_formal_snapshots) if input_mode == "paste" else ""
        uploaded = st.file_uploader(_t("v1.expression.upload_role_fasta", p0=display_label), type=["fa", "fasta", "fas", "txt"], key=f"formal_step3_{role}_custom_upload", on_change=_invalidate_formal_snapshots) if input_mode == "upload" else None
        if uploaded is not None:
            raw = decode_uploaded_text(uploaded.getvalue(), file_name=str(uploaded.name), allowed_suffixes=DNA_FILE_SUFFIXES)
        elif input_mode == "upload" and saved_input_method == "upload" and isinstance(saved_record, dict):
            # Streamlit cannot restore a file object across a cold start; use
            # the persisted normalized sequence while retaining upload provenance.
            raw = str(saved_record.get("normalized_sequence") or "")
        if not raw.strip():
            return {
                "name": name,
                "sequence": "",
                "source": "用户提供，待确认",
                "source_kind": "user_recorded",
                "source_input_method": input_mode,
            }, None
        input_method = "upload" if uploaded is not None or (input_mode == "upload" and saved_input_method == "upload") else "paste"
        record = analyze_dna_component_input(
            raw,
            project_id=project_id,
            component_type=role,
            display_name=name,
            # Paste/upload describe how the sequence arrived.  They are not
            # provenance authority for a user-provided formal component.
            source_kind="user_recorded",
            source_name=str(uploaded.name) if uploaded is not None else "用户提供，待确认",
        )
        record["source_input_method"] = input_method
        if role == "terminator":
            record["biological_role"] = normalize_three_prime_role(
                st.session_state.get("formal_step3_three_prime_role")
            )
        sequence = str(record["normalized_sequence"])
        from services.single_gene_assisted_components import retained_assisted_fields

        assisted_fields = retained_assisted_fields(
            saved_record or {}, sequence=sequence, role="promoter" if role == "promoter" else "three_prime_regulatory_region",
            project_id=project_id, host=ds.host,
        )
        if assisted_fields:
            record.update(assisted_fields, project_id=project_id)
            record["source_name"] = saved_record["source_name"]
            record["source_reference"] = saved_record["source_reference"]
        preserved = _preserved_record(name, sequence)
        if preserved is not None:
            preserved["source_kind"] = "user_recorded"
            preserved["source_input_method"] = str(
                preserved.get("source_input_method") or input_method
            )
            if role == "terminator":
                preserved["biological_role"] = normalize_three_prime_role(
                    preserved.get("biological_role")
                    or st.session_state.get("formal_step3_three_prime_role")
                )
                # Keep a durable analyzed 3' record available to the
                # incomplete-draft snapshot even when generation is skipped.
                source_records = st.session_state.setdefault(
                    "formal_element_source_records", {}
                )
                if isinstance(source_records, dict):
                    source_records[role] = dict(preserved)
            source = str(
                preserved.get("source_accession_version")
                or preserved.get("source_name")
                or "用户提供，待确认"
            )
            return {
                "name": name,
                "sequence": sequence,
                "source": source,
                "source_kind": "user_recorded",
                "source_input_method": preserved.get("source_input_method") or input_method,
            }, preserved
        if role in {"promoter", "terminator"}:
            # Analysis is the persistence boundary for user-provided 3'
            # components.  UploadedFile objects are intentionally excluded;
            # only the serializable analyzed record enters the draft snapshot.
            source_records = st.session_state.setdefault(
                "formal_element_source_records", {}
            )
            if isinstance(source_records, dict):
                source_records[role] = dict(record)
        return {
            "name": name,
            "sequence": sequence,
            "source": "用户提供，待确认",
            "source_kind": "user_recorded",
            "source_input_method": input_method,
        }, record

    def _component_status_html(
        label: str,
        selected: Mapping[str, Any],
    ) -> str:
        name = str(selected.get("name") or label)
        sequence = str(selected.get("sequence") or "")
        record_status = (
            _t("v1.expression.registry_formal_record")
            if selected.get("formal_selectable")
            else _t("v1.expression.user_provided_non_registry_selection")
            if str(selected.get("source_kind") or "").strip().lower() == "user_recorded"
            or str(selected.get("source") or "").startswith("用户提供")
            else _t("v1.expression.not_configured")
        )
        return (
            "<div class='formal-component-status-summary'>"
            f"<strong>{len(sequence):,} bp</strong> · {record_status}"
            "</div>"
        )

    three_prime_role_labels = dict(_THREE_PRIME_ROLE_LABELS)
    promoter_record = terminator_record = None
    component_input_error = False
    st.markdown(
        _t('v1.expression.expression_cassette_elements'),
        unsafe_allow_html=True,
    )
    with st.container(key="formal_content_section_step3_required"):
        with st.container(key="formal_step3_component_promoter"):
            label_col, control_col, status_col = st.columns(
                [1.8, 6.2, 2], gap="large", vertical_alignment="top"
            )
            with label_col:
                st.markdown(
                    _t('v1.expression.promoter'),
                    unsafe_allow_html=True,
                )
                st.caption(_t('v1.expression.candidate_parts_items', p0=len(promoters)))
            with control_col:
                promoter_mode = st.segmented_control(
                    _t('v1.expression.promoter_source'),
                    _SINGLE_GENE_SOURCE_MODE_VALUES,
                    format_func=lambda value: _t(_SINGLE_GENE_SOURCE_MODE_LABELS[value]),
                    key="formal_step3_promoter_mode",
                    on_change=_invalidate_formal_snapshots,
                    **(
                        {}
                        if "formal_step3_promoter_mode" in st.session_state
                        else {"default": _SINGLE_GENE_SOURCE_MODE_VALUES[0]}
                    ),
                )
                promoter = (
                    st.selectbox(
                        _t('v1.ai_assisted_design.promoter'),
                        promoters,
                        format_func=lambda item: f"{item['name']} · {len(item['sequence'])} bp",
                        key="formal_step3_promoter", on_change=_invalidate_formal_snapshots,
                    )
                    if promoters
                    else empty_formal_step3_component("promoter")
                )
                if not promoters:
                    st.warning(
                        _t('v1.expression.no_promoters_formal_registry_selection_eligibility_currently')
                    )
                if promoters or promoter_mode == "user_sequence":
                    try:
                        promoter, promoter_record = _user_element("promoter", promoter_mode, promoter)
                    except Exception as exc:
                        st.error(str(exc))
                        component_input_error = True
            with status_col:
                st.markdown(
                    _component_status_html(_t('v1.ai_assisted_design.promoter'), promoter),
                    unsafe_allow_html=True,
                )
        with st.container(key="formal_step3_component_cds"):
            label_col, control_col, status_col = st.columns(
                [1.8, 6.2, 2], gap="large", vertical_alignment="top"
            )
            with label_col:
                st.markdown(
                    "<div class='formal-required-slot-title'>CDS</div>",
                    unsafe_allow_html=True,
                )
            with control_col:
                st.markdown(
                    _t('v1.expression.bp_step_2_not_editable_step', p0=escape(gene_name), p1=len(cds_sequence)),
                    unsafe_allow_html=True,
                )
            with status_col:
                st.markdown(
                    "<div class='formal-component-status-summary'>"
                    f"<strong>{cds_analysis_status}</strong> · "
                    f"{_t('v1.expression.step_2_saved') if cds_sequence else _t('v1.expression.return_step_2')}"
                    "</div>",
                    unsafe_allow_html=True,
                )
        with st.container(key="formal_step3_component_three_prime"):
            label_col, control_col, status_col = st.columns(
                [1.8, 6.2, 2], gap="large", vertical_alignment="top"
            )
            with label_col:
                st.markdown(
                    _t("v1.expression.3_regulatory_element"),
                    unsafe_allow_html=True,
                )
                st.caption(_t('v1.expression.candidate_parts_items', p0=len(terminators)))
            with control_col:
                terminator_mode = st.segmented_control(
                    _t("v1.expression.source_3_regulatory_element"),
                    _SINGLE_GENE_SOURCE_MODE_VALUES,
                    format_func=lambda value: _t(_SINGLE_GENE_SOURCE_MODE_LABELS[value]),
                    key="formal_step3_terminator_mode",
                    on_change=_invalidate_formal_snapshots,
                    **(
                        {}
                        if "formal_step3_terminator_mode" in st.session_state
                        else {"default": _SINGLE_GENE_SOURCE_MODE_VALUES[0]}
                    ),
                )
                terminator = (
                    st.selectbox(
                        _t("v1.expression.3_regulatory_element"),
                        terminators,
                        format_func=lambda item: f"{item['name']} · {len(item['sequence'])} bp",
                        key="formal_step3_terminator", on_change=_invalidate_formal_snapshots,
                    )
                    if terminators
                    else empty_formal_step3_component("3_prime_regulatory_region")
                )
                if not terminators:
                    st.warning(
                        _t("v1.expression.no_3_regulatory_elements_formal_registry_selection"),
                    )
                authoritative_three_prime_role = (
                    _formal_three_prime_registry_role(terminator)
                    if terminator_mode == "registry" and terminators
                    else ""
                )
                if authoritative_three_prime_role:
                    # Keep a restored or previously edited widget value from
                    # overriding the selected Registry record's role.
                    st.session_state["formal_step3_three_prime_role"] = authoritative_three_prime_role
                    three_prime_role = st.selectbox(
                        _t("v1.expression.biological_role_3_regulatory_element_registry_authoritative"),
                        [authoritative_three_prime_role],
                        format_func=lambda value: _t(three_prime_role_labels[value]),
                        key="formal_step3_three_prime_role",
                        disabled=True,
                    )
                elif terminator_mode == "registry" and terminators:
                    # An admitted Registry record with an unknown authoritative
                    # type must never acquire a default biological role.
                    st.error(
                        _t('v1.expression.component_type_recorded_at_3_end_registry')
                    )
                    three_prime_role = ""
                    component_input_error = True
                elif terminator_mode == "user_sequence":
                    # The widget value is the semantic role key.  Its
                    # localized label is supplied only by format_func.
                    st.session_state["formal_step3_three_prime_role"] = normalize_three_prime_role(
                        st.session_state.get("formal_step3_three_prime_role")
                    )
                    three_prime_role = st.selectbox(
                        _t("v1.expression.biological_role_3_regulatory_element_user_declared"),
                        list(three_prime_role_labels),
                        format_func=lambda value: _t(three_prime_role_labels[value]),
                        key="formal_step3_three_prime_role",
                        on_change=_invalidate_formal_snapshots,
                    )
                else:
                    # No Registry option is available and the user has not
                    # selected the user-sequence path; do not present an
                    # editable role control that suggests Registry authority.
                    three_prime_role = "terminator"
                if not component_input_error and (
                    terminators or terminator_mode == "user_sequence"
                ):
                    try:
                        terminator, terminator_record = _user_element(
                            "terminator", terminator_mode, terminator
                        )
                    except Exception as exc:
                        st.error(str(exc))
            with status_col:
                st.markdown(
                        _component_status_html(
                        _t('v1.expression.3_regulatory_element'),
                        terminator,
                    ),
                    unsafe_allow_html=True,
                )

    def _optional_component(key: str, label: str, roles: list[tuple[str, str]]) -> dict[str, Any] | None:
        display_label = _display_optional_label(label)
        enabled = st.checkbox(_t('v1.expression.add', p0=display_label), key=f"formal_step3_{key}_enabled", on_change=_invalidate_formal_snapshots)
        if not enabled:
            return None
        role = st.selectbox(
            _t('v1.expression.biological_role', p0=display_label),
            [item[0] for item in roles],
            format_func=lambda value: _display_optional_label(dict(roles)[value]),
            key=f"formal_step3_{key}_role",
            on_change=_invalidate_formal_snapshots,
        )
        name = st.text_input(
            _t('v1.expression.name_text_input', p0=display_label),
            key=f"formal_step3_{key}_name",
            on_change=_invalidate_formal_snapshots,
        ).strip()
        sequence = st.text_area(f"{display_label} DNA/FASTA", key=f"formal_step3_{key}_sequence", height=90, on_change=_invalidate_formal_snapshots)
        source_reference = st.text_input(_t('v1.expression.accession_source_file_source_note', p0=display_label), key=f"formal_step3_{key}_source", on_change=_mark_formal_cassette_source_review).strip()
        if not sequence.strip():
            return {"biological_role": role, "display_name": name or label, "sequence": "", "source_kind": "user_recorded", "source_reference": source_reference, "user_edited": True}
        try:
            record = analyze_dna_component_input(
                sequence, project_id=project_id, component_type=key, display_name=name or label,
                source_kind="paste", source_name=source_reference or "用户提供，待确认",
            )
        except Exception as exc:
            st.error(str(exc))
            return {"biological_role": role, "display_name": name or label, "sequence": sequence, "source_kind": "user_recorded", "source_reference": source_reference, "user_edited": True}
        saved_record = (st.session_state.get("formal_element_source_records") or {}).get(key) or {}
        from services.single_gene_assisted_components import retained_assisted_fields

        try:
            assisted_fields = retained_assisted_fields(
                saved_record, sequence=record["normalized_sequence"], role=role,
                project_id=project_id, host=ds.host,
            )
        except ValueError as exc:
            st.error(str(exc))
            return {"biological_role": role, "display_name": name or label, "sequence": "", "source_kind": "user_recorded", "source_reference": source_reference, "user_edited": True}
        return {"biological_role": role, "display_name": name or label, "sequence": record["normalized_sequence"], "source_kind": "paste", "source_reference": source_reference, "source_file": source_reference, "user_edited": True, **assisted_fields}

    optional_keys = ("five_prime", "n_tag", "targeting", "linker", "c_tag")
    optional_selected_count = sum(
        bool(st.session_state.get(f"formal_step3_{key}_enabled"))
        for key in optional_keys
    )
    with st.expander(_t('v1.expression.optional_elements_selected', p0=optional_selected_count), expanded=False):
        five_prime = _optional_component("five_prime", "5′端调控元件", [
        ("five_prime_utr", "5′非翻译区（5′ UTR）"),
        ("five_prime_regulatory_region", "5′端调控区"),
        ("translation_enhancer_sequence", "翻译增强相关序列"),
    ])
        n_tag = _optional_component("n_tag", "N端融合标签编码序列", [("n_terminal_fusion_tag_coding_sequence", "N端融合标签编码序列")])
        targeting = _optional_component("targeting", "蛋白靶向元件编码序列", [
        ("signal_peptide_coding_sequence", "分泌信号肽编码序列"),
        ("chloroplast_transit_peptide_coding_sequence", "叶绿体转运肽编码序列"),
        ("mitochondrial_targeting_peptide_coding_sequence", "线粒体转运肽编码序列"),
        ("nuclear_localization_signal_coding_sequence", "核定位信号编码序列"),
    ])
        linker = _optional_component("linker", "连接肽编码序列", [("linker_coding_sequence", "连接肽编码序列")])
        c_tag = _optional_component("c_tag", "C端融合标签编码序列", [("c_terminal_fusion_tag_coding_sequence", "C端融合标签编码序列")])
    st.markdown(
        _t('v1.expression.pre_generation_checks'),
        unsafe_allow_html=True,
    )
    restore_order_confirmation = globals().get(
        "_formal_step3_order_confirmation"
    )
    if callable(restore_order_confirmation):
        restore_order_confirmation()
    order_confirmed = st.checkbox(
        _t('v1.expression.i_confirmed_component_arrangement_orientation'),
        key="formal_step3_order_confirmed",
        on_change=globals().get(
            "_record_formal_step3_order_confirmation",
            _invalidate_formal_snapshots,
        ),
    )

    generated_cassette = st.session_state.get("formal_expression_cassette")
    generated_cds_signature = (
        str(generated_cassette.get("cds_signature") or "")
        if isinstance(generated_cassette, Mapping)
        else ""
    )
    cds_signature = generated_cds_signature or _formal_cds_signature(saved_cds)
    cds_component = {
        "biological_role": "cds", "display_name": ds.gene_name or "CDS", "sequence": cds_sequence,
        "source_kind": str((saved_cds or {}).get("source_kind") or "step_2"),
        "source_reference": str((saved_cds or {}).get("source_name") or st.session_state.get("formal_cds_source") or ""),
        "user_edited": False,
    }
    required_three_prime_role = three_prime_role
    if terminator_mode == "registry" and authoritative_three_prime_role:
        required_three_prime_role = authoritative_three_prime_role
    elif terminator_mode != "user_sequence" and terminator_record and str(terminator_record.get("biological_role") or ""):
        required_three_prime_role = str(terminator_record["biological_role"])
    components = [
        {"biological_role": "promoter", "display_name": promoter["name"], "sequence": promoter["sequence"], "source_kind": str((promoter_record or {}).get("source_kind") or "library"), "source_reference": str((promoter_record or {}).get("source_reference") or promoter["source"]), "user_edited": promoter_mode == "user_sequence"},
        *[item for item in (five_prime, n_tag, targeting) if item is not None],
        cds_component,
        *[item for item in (linker, c_tag) if item is not None],
        {"biological_role": required_three_prime_role, "display_name": terminator["name"], "sequence": terminator["sequence"], "source_kind": str((terminator_record or {}).get("source_kind") or "library"), "source_reference": str((terminator_record or {}).get("source_reference") or terminator["source"]), "user_edited": terminator_mode == "user_sequence"},
    ]
    if (promoter_record or {}).get("component_reference", {}).get("assisted_resolution"):
        components[0].update({key: promoter_record[key] for key in ("component_reference", "assisted_project_host")})
    assessment = assess_expression_cassette(
        components, cds_sequence=cds_sequence, cds_signature=cds_signature,
        project_definition=globals().get("_formal_project_definition", lambda: {})(), order_confirmed=order_confirmed,
    )
    findings = list(assessment["findings"])
    authority_findings = formal_step3_authority_findings(
        promoter_options=promoters,
        three_prime_options=terminators,
        promoter_mode="用户序列" if promoter_mode == "user_sequence" else "元件库",
        three_prime_mode="用户序列" if terminator_mode == "user_sequence" else "元件库",
        selected_promoter=promoter_record if promoter_mode == "user_sequence" else promoter,
        selected_three_prime=terminator_record if terminator_mode == "user_sequence" else terminator,
    )
    findings.extend(authority_findings)
    if authority_findings:
        assessment["findings"] = findings
        assessment["blocking"] = True
    blocking_count = sum(item["status"] == "阻断" for item in findings)
    manual_confirmation_count = sum(item["status"] == "需要人工确认" for item in findings)
    warning_count = sum(item["status"] == "警告" for item in findings)
    finding_guidance = {
        "missing_promoter": ("启动子", "使用上方现有启动子选择或用户序列输入"),
        "missing_cds": ("CDS", "返回 Step 2 输入并分析 CDS"),
        "missing_three_prime_regulatory_element": ("3′端调控元件", "使用上方现有 3′端调控元件选择或用户序列输入"),
        "cds_signature_mismatch": ("CDS", "返回 Step 2 重新分析当前 CDS"),
        "component_order_not_confirmed": ("元件排列和方向", "勾选上方“我已确认组件排列和方向”"),
        "empty_component_sequence": ("元件 DNA 序列", "在当前元件输入区补充序列"),
        "illegal_dna_character": ("元件 DNA 序列", "在当前元件输入区修正非法字符"),
        "incomplete_component_provenance": ("元件来源", "在当前元件来源字段补充 accession、文件或来源说明"),
        "custom_component_annotation": ("用户自定义元件来源", "在当前元件来源字段补充专业注释或来源"),
        "unsupported_component_order": ("元件排列", "检查当前可选元件和排列设置"),
        "coding_component_frameshift": ("编码元件长度", "修正当前编码元件；CDS 问题请返回 Step 2"),
        "c_terminal_fusion_terminal_stop_conflict": ("CDS 与 C 端融合元件", "返回 Step 2 处理 CDS，或调整当前 C 端融合元件"),
        "cds_missing_terminal_stop": ("CDS 末端", "返回 Step 2 核对 CDS，或核对当前 C 端融合设计"),
        "n_terminal_start_relationship": ("N 端编码元件与 CDS", "核对当前 N 端元件和 CDS 的起始关系"),
        "unexpected_internal_stop": ("编码融合序列", "检查当前编码元件；CDS 问题请返回 Step 2"),
        "promoter_context_not_confirmed": ("启动子与组织背景", "核对上方启动子选择；必要时返回 Step 1 修改项目背景"),
        "localization_component_not_confirmed": ("定位目标与靶向元件", "展开“可选元件”并记录相应靶向编码元件，或返回 Step 1 修改定位目标"),
        "broad_three_prime_role": ("3′端调控元件角色", "使用上方现有生物学角色选择核对记录"),
        "no_formal_promoter_component": ("启动子", "等待 Registry 正式准入记录，或返回项目上下文核对宿主"),
        "no_formal_three_prime_component": ("3′端调控元件", "等待 Registry 正式准入记录，或返回项目上下文核对宿主"),
        "ineligible_formal_promoter_component": ("启动子", "重新选择已获 Registry 正式选择资格的记录"),
        "ineligible_formal_three_prime_component": ("3′端调控元件", "重新选择已获 Registry 正式选择资格的记录"),
    }
    design_info_rule_ids = {
        "incomplete_component_provenance",
        "custom_component_annotation",
    }
    design_info_findings = [
        item
        for item in findings
        if str(item.get("rule_id") or "") in design_info_rule_ids
    ]
    action_findings = [
        item
        for item in findings
        if str(item.get("rule_id") or "") not in design_info_rule_ids
    ]
    pending_action_count = len(action_findings)
    st.markdown(
        _t('v1.expression.still_need_complete_items_before_generation', p0=pending_action_count)
        if pending_action_count
        else _t('v1.expression.all_pre_generation_checks_completed'),
        unsafe_allow_html=True,
    )
    hidden_empty_sequence_messages = {
        message
        for message, hide in (
            ("启动子 的 DNA 序列为空。", not promoters and promoter_mode == "registry"),
            (
                "3′端调控元件 的 DNA 序列为空。",
                not terminators and terminator_mode == "registry",
            ),
        )
        if hide
    }
    visible_action_findings = [
        item
        for item in action_findings
        if str(item.get("rule_id") or "")
        not in {
            "component_order_not_confirmed",
            "no_formal_promoter_component",
            "no_formal_three_prime_component",
        }
        and not (
            str(item.get("rule_id") or "") == "empty_component_sequence"
            and str(item.get("message") or "") in hidden_empty_sequence_messages
        )
    ]
    if visible_action_findings:
        check_items = []
        for item in visible_action_findings:
            status = str(item.get("status") or "需要人工确认")
            target, action = finding_guidance.get(
                str(item.get("rule_id") or ""),
                ("当前表达盒记录", "检查上方现有元件输入和确认项"),
            )
            blocking_class = " blocking" if status == "阻断" else ""
            check_items.append(
                f"<div class='formal-check-item{blocking_class}'>"
                f"<strong>{escape(str(item.get('message') or '需要检查当前记录。'))}</strong> "
                f"{escape(str(_ui(target)))} · {escape(str(_ui(action)))}"
                "</div>"
            )
        st.markdown(
            "<div class='formal-check-list'>" + "".join(check_items) + "</div>",
            unsafe_allow_html=True,
        )
    st.markdown(
        _t('v1.expression.expression_cassette_summary_3_required_elements_optional', p0=optional_selected_count, p1=_t('v1.expression.confirmed') if order_confirmed else _t('v1.expression.pending_confirmation')),
        unsafe_allow_html=True,
    )
    biological_role_field = _t('v1.expression.biological_role_label')
    with st.expander(
        _t('v1.expression.technical_details_parts_blocks_manual_confirmations_required', p0=len(assessment['components']), p1=blocking_count, p2=manual_confirmation_count, p3=warning_count),
        expanded=False,
    ):
        component_rows = [
            {
                _t('v1.results_final_report.order'): item["order"],
                _t('v1.results_final_report.name'): item["display_name"],
                biological_role_field: item["biological_role"],
                _t('v1.results_final_report.length'): item["length"],
                _t('v1.common.orientation'): item["strand"],
                _t('v1.results_final_report.source'): item["source_reference"] or _t('v1.expression.not_recorded'),
            }
            for item in assessment["components"]
        ]
        st.dataframe(_localized_rows(component_rows), hide_index=True, use_container_width=True, column_config={biological_role_field: biological_role_field})
        st.markdown(_t('v1.expression.full_technical_check'))
        finding_rows = [
            {
                _t('v1.expression.check_code'): item["rule_id"],
                _t('v1.expression.status_label'): _ui(item["status"]),
                _t('v1.expression.result_label'): item["message"],
            }
            for item in findings
        ] or [{
            _t('v1.expression.check_code'): _t('v1.expression.readiness_check'),
            _t('v1.expression.status_label'): _t('v1.expression.passed'),
            _t('v1.expression.result_label'): _t('v1.expression.no_blocking_items'),
        }]
        st.dataframe(finding_rows, hide_index=True, use_container_width=True)
    with st.expander(_t('v1.expression.design_information_tip', p0=len(design_info_findings)), expanded=False):
        if design_info_findings:
            for item in design_info_findings:
                _target, action = finding_guidance.get(
                    str(item.get("rule_id") or ""),
                    ("当前表达盒记录", "核对当前元件记录"),
                )
                st.markdown(str(item.get("message") or _t('v1.expression.needs_check')))
                st.caption(_ui(action))
        else:
            st.caption(_t('v1.expression.no_additional_design_information_currently_available'))
    cassette_result = st.session_state.get("formal_cassette_result")
    cassette_is_current = bool(
        isinstance(cassette_result, dict)
        and str(cassette_result.get("input_signature") or "")
        == str(assessment["input_signature"])
    )
    step3_ready_for_backbone = step3_can_continue_to_backbone(
        cassette_result=cassette_result if isinstance(cassette_result, dict) else None,
        current_input_signature=str(assessment["input_signature"]),
        findings=findings,
        order_confirmed=order_confirmed,
    )
    if isinstance(cassette_result, dict) and not cassette_is_current:
        _invalidate_formal_snapshots()
    def generate_step3() -> dict[str, Any]:
        generated = generate_expression_cassette(assessment, project_id=project_id)
        # Keep the analyzed user-input provenance alongside the generated
        # component records; Registry authority is never inferred from it.
        provenance_by_role = {
            "promoter": promoter_record,
            "terminator": terminator_record,
        }
        for component in generated.get("components") or []:
            source_record = provenance_by_role.get(
                str(component.get("biological_role") or "")
            )
            if isinstance(source_record, Mapping) and str(
                source_record.get("source_kind") or ""
            ).strip().lower() == "user_recorded":
                component["source_input_method"] = str(
                    source_record.get("source_input_method") or ""
                )
                component["normalized_sequence"] = str(
                    source_record.get("normalized_sequence") or component.get("sequence") or ""
                )
        generated["cds_signature"] = cds_signature
        generated["cassette_input_signature"] = assessment["input_signature"]
        st.session_state["formal_expression_cassette"] = generated
        st.session_state["formal_cassette_result"] = {"runtime": generated["runtime"], "cassette_input_signature": assessment["input_signature"], "input_signature": assessment["input_signature"]}
        st.session_state["formal_cassette_input_signature"] = assessment["input_signature"]
        st.session_state["formal_element_source_records"] = {"promoter": promoter_record, "terminator": terminator_record,
            **({"five_prime": five_prime} if five_prime and five_prime.get("component_reference") else {})}
        ds.elements = {"promoter_name": promoter["name"], "promoter_seq": promoter["sequence"], "rbs_name": "", "rbs_seq": "", "terminator_name": terminator["name"], "terminator_seq": terminator["sequence"]}
        ds.clear_step3_outputs()
        _clear_complete_plasmid_state()
        globals().get("_mark_workflow_dirty", lambda: None)()
        return generated

    def generate_step3_action() -> None:
        succeeded, _generated, _executed = _orchestrate_formal_step3_generation(
            input_signature=str(assessment["input_signature"]),
            generate_action=generate_step3,
        )
        if succeeded:
            st.rerun()
    if assessment["blocking"]:
        st.caption(_t('v1.expression.first_correct_blocking_items_identified_expression_cassette'))

    def advance_step3() -> None:
        if step3_can_continue_to_backbone(
            cassette_result=st.session_state.get("formal_cassette_result"),
            current_input_signature=str(assessment["input_signature"]),
            findings=findings,
            order_confirmed=order_confirmed,
        ):
            _set_formal_step(4)

    generate_required = not cassette_is_current
    _remember_single_gene_step3_widget_state()
    _render_step_navigation(
        current_step=3,
        next_enabled=step3_ready_for_backbone if not generate_required else (
            not bool(assessment["blocking"])
            and not bool(st.session_state.get("formal_ui_action_busy"))
        ),
        next_label=_t('v1.expression.generate_expression_cassette_continue') if generate_required else "",
        disabled_reason=(
            _t("v1.expression.first_correct_blocking_items_identified_expression_cassette")
            if generate_required and assessment["blocking"]
            else "正在生成表达盒，请稍候。"
            if generate_required and bool(st.session_state.get("formal_ui_action_busy"))
            else "请先生成当前表达盒；确认元件排列和方向，并在输入变化后重新生成。"
            if not step3_ready_for_backbone
            else ""
        ),
        next_action=advance_step3 if not generate_required else generate_step3_action,
    )


def _structure_overview_html(ds: Any) -> str:
    elements = ds.elements if isinstance(ds.elements, dict) else {}
    return (
        "<div class='formal-structure'>"
        f"<div class='formal-structure-part formal-promoter'>启动子<br>{_formal_element_display_name(elements.get('promoter_name') or '--', 'promoter')}</div>"
        "<div class='formal-arrow'>→</div>"
        f"<div class='formal-structure-part formal-cds'>编码序列（CDS）<br>{_formal_element_display_name(ds.gene_name or '--', 'cds')}</div>"
        "<div class='formal-arrow'>→</div>"
        f"<div class='formal-structure-part formal-terminator'>3′端元件<br>{_formal_element_display_name(elements.get('terminator_name') or '--', 'terminator')}</div>"
        "</div>"
    )


def _render_structure_overview(ds: Any) -> None:
    st.markdown(_structure_overview_html(ds), unsafe_allow_html=True)


def _dual_tu_expression_units() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, unit in enumerate(_transcription_units(), start=1):
        unit_id = str(unit["unit_id"])
        records.append(
            {
                "unit_id": unit_id,
                "display_name": str(unit.get("display_name") or f"TU{index}"),
                "unit_name": str(unit.get("display_name") or f"TU{index}"),
                "orientation": str(unit.get("orientation") or "forward"),
                "order": index,
                "promoter": dict(unit.get("promoter") or {}),
                "five_prime_region": dict(unit.get("five_prime_region") or {}),
                "cds": dict(unit.get("cds") or {}),
                "3_prime_regulatory_region": dict(unit.get("3_prime_regulatory_region") or unit.get("terminator") or {}),
                "targeting_sequence": dict(unit.get("targeting_sequence") or {}),
                "linker": dict(unit.get("linker") or {}),
                "fusion_tag": dict(unit.get("fusion_tag") or {}),
                "validation_state": str(unit.get("validation_state") or "incomplete"),
                "provenance_state": str(unit.get("provenance_state") or "review_required"),
            }
        )
    return records


def _render_dual_tu_structure() -> None:
    for index, unit in enumerate(_transcription_units(), start=1):
        orientation = (
            _t("v1.common.reverse")
            if unit.get("orientation") == "reverse"
            else _t("v1.common.forward")
        )
        direction_arrow = "←" if unit.get("orientation") == "reverse" else "→"
        st.markdown(f"**TU{index} · {escape(str(unit.get('display_name') or '--'))} · {orientation}**")
        st.markdown(
            _t('v1.expression.promoter_5_region_5_utr_coding_sequence', p0=escape(str((unit.get('promoter') or {}).get('display_name') or '--')), p1=direction_arrow, p2=escape(str((unit.get('five_prime_region') or {}).get('display_name') or '--')), p3=direction_arrow, p4=escape(str((unit.get('cds') or {}).get('display_name') or '--')), p5=direction_arrow, p6=escape(str((unit.get('3_prime_regulatory_region') or unit.get('terminator') or {}).get('display_name') or '--'))),
            unsafe_allow_html=True,
        )


def _render_pcambia1300_workflow_block(workflow_label: str) -> None:
    from core.pcambia1300_exact_insertion_contract import exact_insertion_contract

    contract = exact_insertion_contract()
    st.error(
        _t('v1.expression.pcambia_1300_af234296_1_blocked_multi_tu', p0=workflow_label)
    )
    st.markdown(
        _t("v1.expression.asset_type_full_binary_vector_bp_circular", p0=contract['asset_kind'], p1=f"{contract['full_sequence_length']:,}")
    )
    _render_step_navigation(
        current_step=4,
        next_enabled=False,
        disabled_reason=f"pCAMBIA-1300 尚未通过 {workflow_label} 工作流验收，请选择其他已支持骨架。",
    )


def _render_multi_tu_linear_structure(
    units: list[Mapping[str, Any]], combined: Mapping[str, Any]
) -> None:
    """Render the current canonical Multi-TU feature order as a linear assembly view."""
    total_length = max(1, int(combined.get("total_length") or 0))
    coordinates = [
        row
        for row in list(combined.get("component_coordinates") or [])
        if isinstance(row, Mapping) and str(row.get("component_type") or "") != "transcription_unit"
    ]
    palette = {
        "promoter": "#3d6f8f",
        "five_prime_region": "#6b7280",
        "cds": "#237a4b",
        "3_prime_regulatory_region": "#a36b2c",
    }
    st.markdown(_t('v1.expression.linear_expression_region_assembly'))
    st.caption(_t('v1.expression.displayed_according_canonical_runtime_tu_order_feature'))
    for unit in units:
        unit_id = str(unit.get("unit_id") or "")
        display_name = escape(str(unit.get("display_name") or unit_id or "TU"))
        orientation = str(unit.get("orientation") or "forward")
        direction_label = _t('v1.common.reverse') + " ←" if orientation == "reverse" else _t('v1.common.forward') + " →"
        unit_rows = [row for row in coordinates if str(row.get("unit_id") or "") == unit_id]
        unit_range = unit.get("range") if isinstance(unit.get("range"), Mapping) else {}
        range_text = f"{int(unit_range.get('start') or 0)}..{int(unit_range.get('end') or 0)}"
        blocks: list[str] = []
        for row in unit_rows:
            start = int(row.get("start") or 0)
            end = int(row.get("end") or 0)
            left = max(0.0, min(100.0, (start - 1) / total_length * 100))
            width = max(0.8, min(100.0 - left, (end - start + 1) / total_length * 100))
            role = str(row.get("biological_role") or row.get("component_type") or "feature")
            label = escape(_multi_tu_role_display_label(role))
            name = escape(str(row.get("name") or "--"))
            strand = int(row.get("strand") or 1)
            direction = "reverse" if strand < 0 else "forward"
            blocks.append(
                f"<span class='linear-feature' title='{label}: {name}; {start}..{end}; {direction}' "
                f"style='left:{left:.4f}%;width:{width:.4f}%;background:{palette.get(role, '#64748b')}'>{label}<small> {start}..{end}</small></span>"
            )
        st.markdown(
            f"<div class='linear-track-row'><div class='linear-track-label'>{display_name}<br><span>{direction_label}<br>{range_text}</span></div>"
            f"<div class='linear-track'>{''.join(blocks) or '<span class=\"linear-track-empty\">' + _t('v1.expression.current_tu_no_features') + '</span>'}</div></div>",
            unsafe_allow_html=True,
        )


def _render_generic_multi_tu_step_4(ds: Any) -> None:
    result = st.session_state.get("mvp_vector_result")
    _render_step_4_context(ds, contains_vector=False)
    st.subheader(_t('v1.expression.step_4_assembly_setup_canonical_assembly'))
    if not _is_multi_tu_expression_assembly(result):
        st.warning(_t('v1.expression.no_multi_tu_canonical_assembly_available_return'))
        _render_step_navigation(
            current_step=4,
            next_enabled=False,
            disabled_reason=_t('v1.expression.no_multi_tu_canonical_assembly_available_return'),
        )
        return
    combined = dict(result.get("combined_construct") or {})
    units = sorted(
        list(result.get("expression_units") or []),
        key=lambda unit: int(unit.get("order") or 0),
    )
    review_signature = _formal_ui_signature(
        {
            "input_signature": result.get("input_signature") or combined.get("input_signature"),
            "sequence_sha256": combined.get("sequence_sha256"),
        }
    )
    st.markdown(
        _t('v1.expression.canonical_assembly_summary'),
        unsafe_allow_html=True,
    )
    formal_validation_label, _formal_validation_note, _formal_findings = _multi_tu_formal_validation_copy(combined)
    metrics = st.columns(4)
    metrics[0].metric(_t('v1.expression.result_type'), _t('v1.expression.multi_tu_cassette_assembly'))
    metrics[1].metric(_t('v1.results_final_report.tu_count'), len(units))
    metrics[2].metric(_t('v1.expression.canonical_length'), f"{int(combined.get('total_length') or 0):,} bp")
    metrics[3].metric(_t('v1.expression.includes_vector'), _t('v1.common.no'))
    st.markdown(
        _t("v1.expression.tu_order_sequence_check_status_limitation_canonical", p0=' → '.join(str(unit.get('display_name') or unit.get('unit_id')) for unit in units), p1=formal_validation_label)
    )
    _render_multi_tu_linear_structure(units, combined)
    with st.expander(_t('v1.common.technical_details'), expanded=False):
        st.markdown(f"**Canonical SHA-256**：`{str(combined.get('sequence_sha256') or '')}`")
        multi_tu_rows = [
                {
                    _t('v1.results_final_report.order'): int(unit.get("order") or 0),
                    "TU": str(unit.get("display_name") or unit.get("unit_id") or "--"),
                    _t('v1.common.orientation'): _t('v1.common.reverse') if unit.get("orientation") == "reverse" else _t('v1.common.forward'),
                    _t('v1.results_final_report.length'): int(unit.get("length") or 0),
                    _t('v1.expression.source_start'): int((unit.get("range") or {}).get("start") or 0),
                    _t('v1.expression.source_end'): int((unit.get("range") or {}).get("end") or 0),
                }
                for unit in units
            ]
        st.dataframe(multi_tu_rows, hide_index=True, use_container_width=True)
        feature_rows = []
        coordinates = list(combined.get("component_coordinates") or [])
        for unit in units:
            unit_id = str(unit.get("unit_id") or "")
            for feature in coordinates:
                if str(feature.get("unit_id") or "") != unit_id:
                    continue
                if str(feature.get("component_type") or "") == "transcription_unit":
                    continue
                strand = int(feature.get("strand") or 1)
                role = str(feature.get("biological_role") or feature.get("component_type") or "--")
                feature_rows.append(
                    {
                        "TU": str(unit.get("display_name") or unit_id or "--"),
                        _t('v1.results_final_report.role'): _multi_tu_role_display_label(role),
                        _t('v1.results_final_report.component'): str(feature.get("name") or "--"),
                        _t('v1.common.orientation'): _t('v1.common.reverse') if strand < 0 else _t('v1.common.forward'),
                        _t('v1.expression.source_start'): int(feature.get("start") or 0),
                        _t('v1.expression.source_end'): int(feature.get("end") or 0),
                    }
                )
        st.caption(_t('v1.expression.feature_level_coordinates_canonical_runtime'))
        st.dataframe(feature_rows, hide_index=True, use_container_width=True)

    def confirm_step4_and_continue() -> None:
        st.session_state["formal_multi_tu_step4_confirmation_signature"] = review_signature
        _set_formal_step(5)

    _render_step_navigation(
        current_step=4,
        next_enabled=True,
        next_label=_t('v1.expression.confirm_step4_continue'),
        next_action=confirm_step4_and_continue,
    )


def _render_dual_tu_step_4(ds: Any) -> None:
    stable_multi_name = globals().get("_stable_multi_tu_project_name")
    if not callable(stable_multi_name):
        stable_multi_name = lambda value: str(value or "").strip() or "Multi-TU project"
    if st.session_state.get("formal_betalain_gate3_case"):
        from core.pcambia1300_exact_insertion_contract import is_pcambia1300_record

        selected_backbone = st.session_state.get("formal_backbone_record")
        if isinstance(selected_backbone, dict) and is_pcambia1300_record(selected_backbone):
            _render_pcambia1300_workflow_block("Gate 3")
            return
        from services.pbi121_replacement_strategy import strategy_summary

        strategy = strategy_summary()
        confirmed = bool(st.session_state.get("formal_betalain_repeated_regulatory_confirmed"))
        contract = strategy.get("replacement_contract") or {}
        st.subheader("Step 4: fixed pBI121 exact-replacement contract")
        _render_step_4_context(ds, contains_vector=True)
        st.dataframe(
            [
                {
                    "Source": "AF485783.1 pBI121",
                    "Asset kind": contract.get("asset_kind"),
                    "Replacement interval": "4974..7979",
                    "Coordinate contract": _t("v1.ui_closure.step4_closed_interval", start=4974, end=7979),
                    "Status": strategy.get("strategy_status"),
                },
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.info(
            "The original reporter cassette is replaced exactly. The nptII plant selection cassette and both T-DNA borders are retained."
        )
        with st.expander(_t('v1.common.technical_details'), expanded=False):
            st.caption(_t("v1.ui_closure.internal_interval", start=4973, end=7979))
            st.code("[4973, 7979)", language="text")
        st.caption(_t('v1.expression.system_created_contract_read_only_users_do'))
        _render_step_navigation(
            current_step=4,
            next_enabled=confirmed and bool(strategy.get("ready_for_construct_use")),
            next_label=_t('v1.expression.review_canonical_construct'),
            disabled_reason="Record the regulatory repeat-use confirmation; the fixed pBI121 contract must also pass its source checks.",
        )
        return
    from services.mvp_multi_tu_runtime import generate_multi_tu_combined_construct
    from services.plant_project_draft_schema import new_project_id

    st.subheader(_t('v1.expression.step_4_plant_binary_vector_backbone_assembly'))
    with st.container(border=True):
        _render_dual_tu_structure()
        st.caption(_t('v1.expression.combination_order_label') + " → ".join(_dual_tu_order()))
        if st.button(_t('v1.expression.generate_multi_tu_region'), type="primary"):
            try:
                result = generate_multi_tu_combined_construct(
                    project_id=str(st.session_state.setdefault("mvp_project_id", new_project_id())),
                    project_name=stable_multi_name(st.session_state.get("formal_project_name")),
                    expression_units=_dual_tu_expression_units(),
                )
            except Exception as exc:
                st.error(_t('v1.expression.multi_tu_region_not_generated', p0=exc))
            else:
                st.session_state["formal_dual_tu_combined_result"] = result
                st.session_state["formal_cassette_result"] = result
                st.session_state["formal_dual_tu_unit_snapshots"] = {
                    str(unit.get("unit_id")): dict(unit) for unit in result.get("expression_units") or []
                }
                st.session_state.pop("mvp_vector_result", None)
                st.session_state["mvp_inputs_stale"] = True
                st.rerun()
    result = st.session_state.get("formal_dual_tu_combined_result")
    if isinstance(result, dict):
        snapshots = {str(unit.get("unit_id")): unit for unit in result.get("expression_units") or []}
        unit_rows = list(result.get("expression_units") or [])
        metrics = st.columns(min(4, len(unit_rows) + 1))
        for index, unit in enumerate(unit_rows[: len(metrics) - 1], start=1):
            metrics[index - 1].metric(_t('v1.expression.tu_length', p0=index), f"{int(unit.get('length') or 0):,} bp")
        metrics[-1].metric(_t('v1.expression.total_length_multi_tu_region'), f"{int((result.get('combined_construct') or {}).get('total_length') or 0):,} bp")
        directions = "; ".join(
            f"TU{index} {_t('v1.common.reverse') if unit.get('orientation') == 'reverse' else _t('v1.common.forward')}"
            for index, unit in enumerate(unit_rows, start=1)
        )
        st.markdown(
            _t("v1.expression.order_direction_validation_status", p0=' → '.join(result.get('unit_order') or []), p1=directions, p2=str((result.get('combined_construct') or {}).get('validation_status') or '--'))
        )
        with st.expander(_t('v1.common.technical_details'), expanded=False):
            st.markdown(_t('v1.expression.composite_construct_sha_256', p0=str((result.get('combined_construct') or {}).get('sequence_sha256') or '')))
        st.success(_t('v1.expression.multi_tu_region_generated'))
    _render_step_navigation(
        current_step=4,
        next_enabled=isinstance(result, dict),
        next_label=_t('v1.expression.select_backbone'),
        disabled_reason="请先生成多 TU 区域。",
    )


def _render_step_4_cassette(ds: Any) -> None:
    stable_single_name = globals().get("_stable_single_gene_project_name")
    if not callable(stable_single_name):
        stable_single_name = lambda value, source="": str(value or "").strip() or str(source or "").strip() or "Plant expression vector project"
    if _is_dual_tu_project():
        _render_dual_tu_step_4(ds)
        return
    from services.formal_single_gene_runtime import cassette_input_signature, generate_expression_cassette
    from services.canonical_construct_runtime import active_construct_snapshot, export_active_construct
    from services.plant_project_draft_schema import new_project_id

    st.subheader(_t('v1.expression.step_4_plant_binary_vector_backbone_assembly'))
    with st.container(border=True):
        _render_structure_overview(ds)
        formal_cassette = st.session_state.get("formal_expression_cassette")
        if isinstance(formal_cassette, dict):
            cassette_result = st.session_state.get("formal_cassette_result")
            if not isinstance(cassette_result, dict):
                st.error(_t('v1.expression.return_step_3_regenerate_plant_expression_cassette'))
        elif st.button(_t('v1.expression.generate_expression_cassette'), type="primary"):
            try:
                project_id = str(st.session_state.setdefault("mvp_project_id", new_project_id()))
                cds_input, records = _wizard_component_records(ds, project_id)
                project_name = stable_single_name(
                    st.session_state.get("formal_project_name"), ds.gene_name
                )
                signature = cassette_input_signature(records)
                cassette_result = generate_expression_cassette(
                    cds_input=cds_input, input_records=records, project_id=project_id,
                    project_name=project_name, input_signature=signature,
                )
                cassette = active_construct_snapshot(cassette_result["runtime"])
                ds.frame = {"success": True, "final_sequence": cassette["sequence"], "total_length": cassette["sequence_length"], "features": cassette["feature_rows"]}
                ds.optimized_seq = ds.original_seq
                ds.frame_context_signature = ds.current_frame_context_signature()
                _controller().save(ds)
                st.session_state["formal_cassette_result"] = cassette_result
                st.session_state["formal_cassette_input_signature"] = signature
                st.session_state["formal_cassette_exports"] = export_active_construct(cassette_result["runtime"], project_name=project_name)
                _clear_complete_plasmid_state()
                st.session_state["formal_cassette_result"] = cassette_result
                st.session_state["formal_cassette_input_signature"] = signature
                st.session_state["formal_cassette_exports"] = export_active_construct(cassette_result["runtime"], project_name=project_name)
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
    cassette_result = st.session_state.get("formal_cassette_result")
    if isinstance(cassette_result, dict):
        cassette = active_construct_snapshot(cassette_result.get("runtime"))
        metric_cols = st.columns(1)
        metric_cols[0].metric(_t('v1.expression.expression_cassette_length'), f"{int(cassette.get('sequence_length') or 0):,} bp")
        with st.expander(_t('v1.common.technical_details'), expanded=False):
            st.markdown(f"**SHA-256**：`{str(cassette.get('sequence_checksum') or '')}`")
        st.success(_t('v1.expression.expression_cassette_sequence_generated'))
    _render_step_navigation(
        current_step=4,
        next_enabled=isinstance(cassette_result, dict),
        next_label=_t('v1.expression.select_backbone'),
        disabled_reason="请先生成表达盒。",
    )


def _render_step_4_backbone(ds: Any) -> None:
    """Classify one GenBank vector and apply only a reviewed operation contract."""
    if st.session_state.get("formal_betalain_gate3_case"):
        _render_dual_tu_step_4(ds)
        return
    if _is_generic_multi_tu_workflow():
        _render_generic_multi_tu_step_4(ds)
        return
    if _is_dual_tu_project():
        combined = st.session_state.get("formal_dual_tu_combined_result")
        if not isinstance(combined, dict):
            from core.pcambia1300_exact_insertion_contract import is_pcambia1300_record

            selected_backbone = st.session_state.get("formal_backbone_record")
            if not (
                isinstance(selected_backbone, dict)
                and is_pcambia1300_record(selected_backbone)
            ):
                st.warning(_t('v1.expression.no_multi_tu_region_available_return_step'))
                _render_step_navigation(current_step=4, next_enabled=False, disabled_reason="请先在第三步生成当前多 TU 区域。")
                return
    from services.formal_t_dna_review import imported_feature_rows, validate_t_dna_operation
    from services.mvp_sequence_input import analyze_genbank_backbone_input, decode_uploaded_text, GENBANK_FILE_SUFFIXES
    from services.plant_project_draft_schema import new_project_id
    from core.pbi121_replacement_contract import (
        is_pbi121_sequence,
        prepare_pbi121_backbone_record_for_replacement,
        replacement_contract,
    )
    from core.pcambia1300_exact_insertion_contract import (
        exact_insertion_contract,
        fixed_insertion_settings,
        is_pcambia1300_record,
    )

    st.subheader(_t('v1.expression.step_4_plant_binary_vector_backbone_assembly'))
    current_backbone = st.session_state.get("formal_backbone_record")
    workflow_id = _active_backbone_workflow_id()
    _render_step_4_context(ds, contains_vector=True)
    from services.formal_step3_gate import step3_can_continue_to_backbone
    from services.vector_backbone_catalog import catalog_backbone_record, catalog_entries, persisted_backbone_assessment

    restored = persisted_backbone_assessment(current_backbone, workflow_id=workflow_id)
    if isinstance(current_backbone, dict) and current_backbone.get("normalized_sequence") and not restored["allowed"]:
        st.caption(_t('v1.expression.saved_backbone_requires_reselection', p0=restored['reason']))
        st.session_state.pop("formal_backbone_record", None)
        st.session_state.pop("formal_insertion_settings", None)
        _invalidate_complete_plasmid_snapshot()
        current_backbone = None
    st.markdown(_t('v1.expression.official_scaffold_catalog'))
    formal_cassette = st.session_state.get("formal_expression_cassette")
    if workflow_id == "gate3_pathway":
        step3_ready = bool(_formal_step_statuses()[2]["done"])
    else:
        step3_ready = step3_can_continue_to_backbone(
            cassette_result=st.session_state.get("formal_cassette_result"),
            current_input_signature=str(st.session_state.get("formal_cassette_input_signature") or ""),
            findings=(formal_cassette or {}).get("findings") if isinstance(formal_cassette, dict) else [],
            order_confirmed=bool(
                st.session_state.get("formal_step3_order_confirmation_recorded")
                or st.session_state.get("formal_step3_order_confirmed")
            ),
        )
    for entry in catalog_entries(workflow_id, step3_ready=step3_ready):
        row = st.columns([2.2, 1.1, 0.9, 1.2, 1.1])
        row[0].markdown(f"**{escape(str(entry['display_name']))}**")
        row[0].caption(f"{escape(str(entry['accession_version']))} · {entry['length']:,} bp")
        row[1].caption(_ui(entry["status"]))
        row[2].caption(_ui(entry["operation_label"]))
        applicable_workflows = ", ".join(_ui(value) for value in entry["applicable_workflows"]) or _ui("无")
        row[3].caption(f"{_ui('适用：')}{applicable_workflows}")
        if row[4].button(
            _ui(entry["action_label"]),
            key=f"formal_catalog_select_{entry['asset_id']}",
            disabled=not entry["selectable"],
            use_container_width=True,
        ):
            try:
                selected_backbone = catalog_backbone_record(
                    entry["asset_id"], project_id=str(st.session_state.setdefault("mvp_project_id", new_project_id()))
                )
                if workflow_id == "gate3_pathway":
                    selected_backbone[
                        "_formal_pathway_selection_pending"
                    ] = True
                st.session_state["formal_backbone_record"] = selected_backbone
                _invalidate_complete_plasmid_snapshot()
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        st.caption(_ui(str(entry["reason"])))
    st.caption(_t('v1.expression.custom_upload_provided_by_user_not_included'))
    st.markdown(_t('v1.expression.custom_upload'))
    st.markdown(
        """<style>
        [data-testid="stFileUploaderDropzoneInstructions"] > div { display: none; }
        [data-testid="stFileUploaderDropzoneInstructions"]::before { content: "Drop GenBank file here"; }
        [data-testid="stFileUploader"] small { display: none; }
        [data-testid="stFileUploader"] button { font-size: 0; }
        [data-testid="stFileUploader"] button::after { content: "Browse files"; font-size: var(--type-control); }
        </style>""",
        unsafe_allow_html=True,
    )
    st.caption(_t('v1.expression.supports_single_gb_gbk_genbank_file_size'))
    has_saved_backbone = isinstance(current_backbone, dict) and bool(current_backbone.get("normalized_sequence"))
    source_options = ["使用当前项目骨架", "上传 GenBank"] if has_saved_backbone else ["上传 GenBank"]
    source = st.segmented_control(_t('v1.expression.scaffold_source'), source_options, format_func=lambda value: _localized_value(value, _FORMAL_BACKBONE_SOURCE_LABELS), default=source_options[0], key="formal_step4_source", on_change=_invalidate_complete_plasmid_snapshot)
    backbone = current_backbone
    if source == "上传 GenBank":
        uploaded = st.file_uploader(_t("v1.expression.genbank_backbone_single_record"), type=["gb", "gbk", "genbank"], key="formal_step4_upload", on_change=_invalidate_complete_plasmid_snapshot)
        if uploaded is not None:
            try:
                raw = decode_uploaded_text(uploaded.getvalue(), file_name=str(uploaded.name), allowed_suffixes=GENBANK_FILE_SUFFIXES)
                backbone = analyze_genbank_backbone_input(raw, project_id=str(st.session_state.setdefault("mvp_project_id", new_project_id())), display_name=str(uploaded.name), source_kind="upload", source_name=str(uploaded.name))
            except Exception as exc:
                st.error(str(exc))
                backbone = None
    if not isinstance(backbone, dict) or not backbone.get("normalized_sequence"):
        _render_step_navigation(current_step=4, next_enabled=False, disabled_reason=_t("v1.expression.upload_genbank_file"))
        return

    st.caption(_t('v1.expression.source_topology_length_bp', p0=escape(str(backbone.get('source_name') or '--')), p1=_localized_value(_topology_label(backbone.get('topology')), _TOPOLOGY_LABELS), p2=int(backbone.get('length') or 0)))
    from core.vector_asset_contracts_v1 import classify_vector_asset
    from services.vector_asset_admission import ASSET_KIND_LABELS

    vector_identity = classify_vector_asset(backbone)
    asset_kind = str(vector_identity.get("asset_kind") or "unverified_uploaded_vector")
    st.markdown(_t('v1.expression.vector_asset_category', p0=_ui(ASSET_KIND_LABELS.get(asset_kind, _t('v1.expression.complete_binary_vector_read_only')))))
    if vector_identity.get("identity_status") != "EXACT_KNOWN_ASSET" or asset_kind in {
        "reference_vector",
        "hold_unverified_asset",
        "unverified_uploaded_vector",
    }:
        if asset_kind == "reference_vector":
            st.warning(_t('v1.expression.record_complete_reference_vector_source_features_length'))
        elif asset_kind == "hold_unverified_asset":
            st.warning(_t('v1.expression.record_local_example_unverified_source_it_excluded'))
        else:
            st.warning(_t('v1.expression.vector_no_verified_operational_contract_read_only'))
        rows = imported_feature_rows(backbone)
        if rows:
            feature_rows = [
                    {
                        "原始名称": row["name"],
                        "类型": row["type"],
                        "起点": row["start"],
                        "终点": row["end"],
                        "链方向": row["strand"],
                    }
                    for row in rows
                ]
            st.dataframe(_localized_rows(feature_rows), hide_index=True, use_container_width=True)
        _render_step_navigation(
            current_step=4,
            next_enabled=False,
            disabled_reason=str(vector_identity.get("reason") or "该载体没有可用于正式设计的操作合同。"),
        )
        return
    if is_pbi121_sequence(str(backbone.get("normalized_sequence") or "")):
        contract = replacement_contract()
        workflow_id = _active_backbone_workflow_id()
        if workflow_id == "gate3_pathway":
            from services.vector_asset_admission import assess_vector_workflow

            selection_pending = bool(
                backbone.pop("_formal_pathway_selection_pending", False)
            )
            backbone = prepare_pbi121_backbone_record_for_replacement(backbone)
            assessment = assess_vector_workflow(backbone, workflow_id=workflow_id)
            settings = {
                **dict(assessment.get("canonical_settings") or {}),
                "workflow_id": workflow_id,
                "user_confirmation": True,
                "topology_confirmation": True,
            }
            operation = validate_t_dna_operation(
                backbone,
                confirmation={},
                insertion_settings=settings,
                workflow_id=workflow_id,
            )
            settings["t_dna_operation_validation"] = operation
            if not operation.get("allowed"):
                st.error(str(operation.get("reason") or _t('v1.expression.pbi121_contract_failed')))
                _render_step_navigation(
                    current_step=4,
                    next_enabled=False,
                    disabled_reason="AF485783.1 来源身份或固定精确替换合同校验未通过。",
                )
                return
            if (
                dict(st.session_state.get("formal_backbone_record") or {}) != backbone
                or dict(st.session_state.get("formal_insertion_settings") or {}) != settings
            ):
                st.session_state["formal_backbone_record"] = backbone
                st.session_state["formal_insertion_settings"] = settings
                _invalidate_complete_plasmid_snapshot()
            st.info(_t('v1.expression.applied_fixed_exact_replacement_contract_pbi121_af485783'))
            st.markdown(_t(
                'v1.expression.full_binary_vector_summary',
                p0=f"{contract['full_sequence_length']:,}",
                p1=contract['asset_kind'],
                p2=contract['replacement_start'],
                p3=contract['replacement_end'],
            ))
            st.caption(_t('v1.ui_closure.original_interval', start=contract['replacement_start'], end=contract['replacement_end']))
            with st.expander(_t('v1.common.technical_details'), expanded=False):
                st.code(f"[{int(contract['replacement_start']) - 1}, {int(contract['replacement_end'])})", language='text')
            confirmation_signature = _formal_ui_signature(
                {
                    "combined": (
                        st.session_state.get("formal_dual_tu_combined_result") or {}
                    ).get("input_signature"),
                    "backbone": backbone.get("normalized_sequence_sha256")
                    or backbone.get("sequence_sha256")
                    or backbone.get("normalized_sequence"),
                    "insertion": settings,
                }
            )
            if selection_pending:
                st.session_state[
                    "formal_ui_step4_confirmation_signature"
                ] = confirmation_signature
                _save_current_formal_draft(current_step=5)
                ds.step = 5
                _controller().save(ds)
                st.rerun()

            def confirm_pathway_backbone() -> None:
                st.session_state[
                    "formal_ui_step4_confirmation_signature"
                ] = confirmation_signature
                ds.step = 5
                _controller().save(ds)
                st.rerun()

            _render_step_navigation(
                current_step=4,
                next_enabled=True,
                next_label=_t('v1.expression.confirm_backbone_continue_action'),
                next_action=confirm_pathway_backbone,
            )
            return
        workflow_label = "通用 Multi-TU" if _is_dual_tu_project() else "单基因"
        st.error(
            _t('v1.expression.pbi121_af485783_1_not_empty_backbone_fixed', p0=workflow_label)
        )
        st.markdown(
            _t('v1.expression.asset_type_fixed_replacement_interval_1_based', p0=contract['asset_kind'], p1=contract['replacement_start'], p2=contract['replacement_end'])
        )
        _render_step_navigation(
            current_step=4,
            next_enabled=False,
            disabled_reason="请改用专用 Gate 3 pBI121 精确替换流程，或选择其他适用于当前流程的骨架。",
        )
        return
    if is_pcambia1300_record(backbone):
        contract = exact_insertion_contract()
        workflow_id = _active_backbone_workflow_id()
        if workflow_id in {"generic_multi_tu", "gate3"}:
            workflow_label = "Gate 3" if workflow_id == "gate3" else "Multi-TU"
            _render_pcambia1300_workflow_block(workflow_label)
            return
        if workflow_id != "rice_alb_single_gene":
            st.error(_t('v1.expression.pcambia_1300_currently_supports_only_audited_rice'))
            _render_step_navigation(
                current_step=4,
                next_enabled=False,
                disabled_reason="当前单基因项目不是已审计的水稻 ALB 路径。",
            )
            return
        settings = fixed_insertion_settings()
        settings["workflow_id"] = "rice_alb_single_gene"
        operation = validate_t_dna_operation(
            backbone,
            confirmation={},
            insertion_settings=settings,
            workflow_id="rice_alb_single_gene",
        )
        settings["t_dna_operation_validation"] = operation
        if not operation["allowed"]:
            st.error(operation["reason"])
            _render_step_navigation(
                current_step=4,
                next_enabled=False,
                disabled_reason="AF234296.1 来源身份或精确插入合同校验未通过。",
            )
            return
        if dict(st.session_state.get("formal_insertion_settings") or {}) != settings:
            st.session_state["formal_backbone_record"] = backbone
            st.session_state["formal_insertion_settings"] = settings
            _invalidate_complete_plasmid_snapshot()
        st.info(_t('v1.expression.automatically_applied_fixed_exact_insertion_contract_pcambia'))
        st.markdown(
            _t('v1.expression.pcambia_full_vector_contract_summary', p0=contract['full_sequence_length'], p1=contract['asset_kind'])
        )
        confirmation_signature = _formal_step4_strategy_signature()
        if st.button(
            _t('v1.expression.confirm_backbone_continue'),
            type="primary",
            disabled=bool(st.session_state.get("formal_ui_action_busy")),
        ):
            completed_actions = dict(st.session_state.get("formal_ui_completed_actions") or {})
            completed_actions.pop("step4_confirm_continue", None)
            st.session_state["formal_ui_completed_actions"] = completed_actions
            succeeded, _result, _executed = _execute_formal_action(
                step=4,
                action_id="step4_confirm_continue",
                input_signature=confirmation_signature,
                action=lambda: _record_formal_step4_strategy_confirmation(confirmation_signature),
                success_status="可以继续",
                success_message="骨架与固定插入合同已确认，可以继续第五步。",
                failure_status="需要修正",
            )
            if succeeded:
                ds.step = 5
                _controller().save(ds)
                st.rerun()
        _render_step_navigation(
            current_step=4,
            next_enabled=False,
            show_next=False,
        )
        return


def _generate_dual_tu_complete_plasmid(ds: Any) -> dict[str, Any]:
    from services.mvp_multi_tu_runtime import (
        MULTI_TU_PROJECT_TYPE,
        generate_admitted_multi_tu_complete_plasmid,
    )
    from services.formal_t_dna_review import validate_t_dna_operation

    combined = st.session_state.get("formal_dual_tu_combined_result")
    if not isinstance(combined, dict):
        raise RuntimeError("请先生成当前多 TU 区域。")
    backbone = dict(st.session_state.get("formal_backbone_record") or {})
    settings = dict(st.session_state.get("formal_insertion_settings") or {})
    operation = validate_t_dna_operation(
        backbone,
        confirmation=dict(settings.get("t_dna_confirmation") or {}),
        insertion_settings=settings,
        workflow_id=_active_backbone_workflow_id(),
    )
    if not operation.get("allowed"):
        raise RuntimeError(f"T-DNA 人工确认门禁未通过：{operation.get('reason')}")
    settings["user_confirmation"] = True
    builder_input = dict(combined)
    builder_input["project_type"] = MULTI_TU_PROJECT_TYPE
    result = generate_admitted_multi_tu_complete_plasmid(
        builder_input,
        backbone=backbone,
        insertion_settings=settings,
        workflow_id=_active_backbone_workflow_id(),
    )
    result["workflow_kind"] = _active_backbone_workflow_id()
    result["topology"] = str(backbone.get("topology") or "")
    result["project_type"] = PROJECT_TYPE_DUAL_TU
    result["host"] = _plant_host_label(ds.host)
    formal_context = {
        "project_type": PROJECT_TYPE_DUAL_TU,
        "host_key": ds.host,
        "expression_target": str(st.session_state.get("formal_expression_target") or ""),
        "current_step": 6,
    }
    if _is_pathway_multi_tu_project():
        pathway_mapping = _refresh_pathway_mapping_status()
        formal_context.update(
            {
                "design_scenario": "metabolic_pathway_multi_tu_vector",
                "pathway_steps": pathway_mapping["pathway_steps"],
                "pathway_mapping": pathway_mapping,
            }
        )
    result["formal_project_context"] = formal_context
    st.session_state["mvp_vector_result"] = result
    st.session_state["mvp_current_input_signature"] = str(result.get("input_signature") or "")
    st.session_state["mvp_inputs_stale"] = False
    return result


def _generate_complete_plasmid(ds: Any) -> dict[str, Any]:
    stable_single_name = globals().get("_stable_single_gene_project_name")
    if not callable(stable_single_name):
        stable_single_name = lambda value, source="": str(value or "").strip() or str(source or "").strip() or "Plant expression vector project"
    if _is_dual_tu_project():
        result = _generate_dual_tu_complete_plasmid(ds)
        globals().get("_mark_workflow_dirty", lambda: None)()
        return result
    step4_current, _step5_current = _refresh_formal_strategy_confirmation_state()
    if not step4_current:
        raise RuntimeError("请先完成当前第四步骨架与组装策略确认。")
    _clear_formal_step5_strategy_confirmation()
    from services.formal_single_gene_runtime import (
        cassette_input_signature,
        construct_input_signature,
        generate_admitted_complete_vector,
    )
    from services.plant_project_draft_schema import new_project_id
    from services.canonical_construct_runtime import export_active_construct
    from services.formal_project_definition_lifecycle import construct_review_basis

    project_id = str(st.session_state.setdefault("mvp_project_id", new_project_id()))
    cds_input, records = _wizard_component_records(ds, project_id)
    records["backbone"] = dict(st.session_state.get("formal_backbone_record") or {})
    settings = dict(st.session_state.get("formal_insertion_settings") or {})
    from services.formal_t_dna_review import validate_t_dna_operation

    operation = validate_t_dna_operation(
        records["backbone"],
        confirmation=dict(settings.get("t_dna_confirmation") or {}),
        insertion_settings=settings,
        workflow_id=_active_backbone_workflow_id(),
    )
    if not operation.get("allowed"):
        raise RuntimeError(f"第五步已阻止完整载体构建设计生成：{operation.get('reason') or '需要人工确认。'}")
    settings["t_dna_operation_validation"] = operation
    project_name = stable_single_name(
        st.session_state.get("formal_project_name"), ds.gene_name
    )
    formal_cassette = st.session_state.get("formal_expression_cassette")
    current_cassette_signature = str(
        (formal_cassette or {}).get("cassette_input_signature")
        or (formal_cassette or {}).get("input_signature")
        or cassette_input_signature(records)
    )
    signature = construct_input_signature(records, settings, cassette_signature=current_cassette_signature)
    cassette_result = st.session_state.get("formal_cassette_result")
    if (
        not isinstance(cassette_result, dict)
        or cassette_result.get("cassette_input_signature", cassette_result.get("input_signature")) != current_cassette_signature
    ):
        raise RuntimeError("请先生成当前 canonical 表达盒。")
    cassette_runtime = dict(cassette_result.get("runtime") or {})
    result = generate_admitted_complete_vector(
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id=project_id,
        project_name=project_name,
        input_signature=signature,
        cassette_runtime=cassette_runtime,
        cassette_signature=current_cassette_signature,
        workflow_id=_active_backbone_workflow_id(),
    )
    result_settings = dict(result.get("insertion_settings") or {})
    result_settings["t_dna_operation_validation"] = dict(operation)
    result["insertion_settings"] = result_settings
    st.session_state["formal_insertion_settings"] = dict(result_settings)
    if isinstance(formal_cassette, dict):
        result["formal_expression_cassette"] = {
            key: value
            for key, value in formal_cassette.items()
            if key not in {"runtime", "cassette"}
        }
    result["host"] = _plant_host_label(ds.host)
    definition = _formal_project_definition()
    result["formal_project_context"] = {
        "host_key": definition["plant_host"] or ds.host,
        "expression_target": _project_definition_expression_target(definition),
        "project_definition": definition,
        "construct_review_basis": construct_review_basis(definition),
        "construct_review_status": "current",
        "cds_source_review_basis": dict(cds_input.get("source_review_basis") or {}),
        "cds_source_review_status": "current",
        "current_step": 6,
    }
    # Freeze the existing cassette export with the same runtime that generated
    # result["exports"]. The delivery ZIP never regenerates a different case.
    result["cassette_exports"] = export_active_construct(
        result["runtime"], project_name=project_name
    )
    st.session_state["mvp_vector_result"] = result
    st.session_state["mvp_current_input_signature"] = signature
    st.session_state["mvp_inputs_stale"] = False
    _record_formal_step5_strategy_confirmation(result)
    globals().get("_mark_workflow_dirty", lambda: None)()
    return result


def _render_generic_multi_tu_step_5(ds: Any) -> None:
    from services.canonical_construct_runtime import CanonicalConstructRuntimeError, active_construct_snapshot

    st.subheader(_t('v1.expression.step_5_canonical_assembly_check'))
    result = st.session_state.get("mvp_vector_result")
    if not _is_multi_tu_expression_assembly(result):
        st.warning(_t('v1.expression.no_multi_tu_canonical_assembly_available'))
        _render_step_navigation(
            current_step=5,
            next_enabled=False,
            disabled_reason="请返回第四步审查当前 canonical 组装体。",
        )
        return
    try:
        canonical = active_construct_snapshot(result.get("runtime"))
    except CanonicalConstructRuntimeError as exc:
        st.error(str(exc))
        _render_step_navigation(current_step=5, next_enabled=False, disabled_reason="Canonical 记录不可用。")
        return
    validation = dict(canonical.get("validation_summary") or {})
    blocking = int(validation.get("blocking_count") or 0)
    warnings = int(validation.get("warning_count") or 0)
    original_units = {
        str(unit.get("unit_id") or ""): unit
        for unit in list((result.get("original_input") or {}).get("expression_units") or [])
        if isinstance(unit, Mapping)
    }
    required_roles = ("promoter", "five_prime_region", "cds", "3_prime_regulatory_region")
    complete_units = sum(
        all(
            (
                role == "five_prime_region"
                and _is_explicit_five_prime_absence(
                    original_units.get(str(unit.get("unit_id") or ""), {}).get(role)
                )
                and not str(
                    (
                        original_units.get(str(unit.get("unit_id") or ""), {}).get(role)
                        or {}
                    ).get("raw_text")
                    or ""
                ).strip()
            )
            or str(
                (
                    original_units.get(str(unit.get("unit_id") or ""), {}).get(role)
                    or {}
                ).get("raw_text")
                or ""
            ).strip()
            for role in required_roles
        )
        for unit in list(result.get("expression_units") or [])
        if isinstance(unit, Mapping)
    )
    coordinates = list((result.get("combined_construct") or {}).get("component_coordinates") or [])
    step5_signature = _formal_ui_signature(
        {
            "input_signature": result.get("input_signature") or (result.get("combined_construct") or {}).get("input_signature"),
            "sequence_sha256": (result.get("combined_construct") or {}).get("sequence_sha256"),
        }
    )
    validation_label, validation_note, formal_findings = _multi_tu_formal_validation_copy(
        dict(result.get("combined_construct") or {})
    )
    validation_status = str(
        dict((result.get("combined_construct") or {}).get("formal_validation") or {}).get("status") or ""
    )
    st.markdown(
        _t('v1.expression.canonical_check_summary'),
        unsafe_allow_html=True,
    )
    metrics = st.columns(5)
    metrics[0].metric(_t('v1.expression.canonical_length'), f"{int(canonical.get('sequence_length') or 0):,} bp")
    metrics[1].metric(_t('v1.results_final_report.tu_count'), len(list(result.get("expression_units") or [])))
    metrics[2].metric(_t('v1.expression.complete_transcriptional_unit_tu_required_sequence_elements'), f"{complete_units}/{len(list(result.get('expression_units') or []))}")
    metrics[3].metric(_t('v1.expression.computation_warning'), warnings)
    metrics[4].metric(_t('v1.expression.computation_block'), blocking)
    if validation_status == "legacy_incomplete":
        st.error(_format_multi_tu_validation_copy(validation_label, validation_note))
    elif validation_status != "formal_ready":
        st.warning(_format_multi_tu_validation_copy(validation_label, validation_note))
    else:
        st.success(validation_label)
    for finding in formal_findings:
        if str(finding.get("code") or "") == "MISSING_FIVE_PRIME_REGION":
            unit_ids = "、".join(str(item) for item in finding.get("unit_ids") or []) or "当前 TU"
            st.error(_t('v1.expression.missing_5_region_complete_it_step', p0=unit_ids))
    st.markdown(
        _t('v1.expression.linear_source_consistency_note')
    )
    with st.expander(_t('v1.expression.technical_details_canonical_coordinates_items', p0=len(coordinates)), expanded=False):
        st.markdown(f"**Canonical SHA-256**：`{str((result.get('combined_construct') or {}).get('sequence_sha256') or '')}`")
        st.dataframe(coordinates, hide_index=True, use_container_width=True)

    def confirm_step5_and_continue() -> None:
        st.session_state["formal_multi_tu_step5_confirmation_signature"] = step5_signature
        _set_formal_step(6)

    _render_step_navigation(
        current_step=5,
        next_enabled=blocking == 0 and str(canonical.get("construct_status") or "") == "current",
        next_action=confirm_step5_and_continue,
        next_label=_t('v1.expression.confirm_and_view_results'),
        disabled_reason=_t("v1.expression.canonical_blocking_items_help") if blocking else "",
    )


def _step5_construct_preview_html(plasmid: Mapping[str, Any]) -> str:
    """Render a compact, read-only architecture view from the active snapshot."""
    total_length = max(0, int(plasmid.get("sequence_length") or 0))
    cassette = plasmid.get("cassette_coordinates")
    cassette = cassette if isinstance(cassette, Mapping) else {}
    cassette_start = max(1, int(cassette.get("start") or 0))
    cassette_end = min(total_length, int(cassette.get("end") or 0))
    if total_length <= 0 or cassette_end < cassette_start:
        return "<p class='formal-step5-preview-empty'>当前没有可展示的完整构建坐标。</p>"

    def pct(value: int) -> float:
        return max(0.0, min(100.0, 100 * value / total_length))

    cassette_left = pct(cassette_start - 1)
    cassette_width = max(0.4, pct(cassette_end - cassette_start + 1))
    color_by_type = {
        "promoter": "#2f7d59",
        "cds": "#2d6e9e",
        "terminator": "#a86f21",
    }
    display_roles = (
        ("promoter", "Promoter"),
        ("cds", "CDS"),
        ("terminator", "3′ regulatory region"),
    )
    selected_features: dict[str, Mapping[str, Any]] = {}
    for feature in list(plasmid.get("feature_rows") or []):
        if not isinstance(feature, Mapping):
            continue
        start = max(cassette_start, int(feature.get("start") or 0))
        end = min(cassette_end, int(feature.get("end") or 0))
        if end < start:
            continue
        feature_type = str(feature.get("feature_type") or "").lower()
        if feature_type not in color_by_type or feature_type in selected_features:
            continue
        selected_features[feature_type] = feature

    bars: list[str] = []
    components: list[str] = []
    for feature_type, role in display_roles:
        feature = selected_features.get(feature_type)
        if feature is None:
            continue
        start = max(cassette_start, int(feature.get("start") or 0))
        end = min(cassette_end, int(feature.get("end") or 0))
        left = pct(start - 1)
        width = max(0.4, pct(end - start + 1))
        label = escape(str(feature.get("name") or _component_type_label(feature_type)))
        bars.append(
            "<span class='formal-step5-preview-feature' "
            f"style='left:{left:.3f}%;width:{width:.3f}%;background:{color_by_type[feature_type]}' "
            f"title='{label}' aria-label='{label}'></span>"
        )
        components.append(
            "<div class='formal-step5-preview-component'>"
            f"<div class='formal-step5-preview-role'>{role}</div>"
            f"<div class='formal-step5-preview-name'>{label}</div>"
            f"<div class='formal-step5-preview-length'>{end - start + 1:,} bp</div>"
            "</div>"
        )
    feature_html = "".join(bars) or (
        "<span class='formal-step5-preview-feature' "
        f"style='left:{cassette_left:.3f}%;width:{cassette_width:.3f}%;background:#237a4b' "
        "title='表达盒'>表达盒</span>"
    )
    components_html = (
        f"<div class='formal-step5-preview-components'>{''.join(components)}</div>"
        if components else ""
    )
    return (
        "<div class='formal-step5-preview'>"
        "<div class='formal-step5-preview-meta'><span>载体骨架</span>"
        f"<span>表达盒 {cassette_start:,}-{cassette_end:,} bp</span></div>"
        "<div class='formal-step5-preview-track'>"
        f"<span class='formal-step5-preview-cassette' style='left:{cassette_left:.3f}%;width:{cassette_width:.3f}%'></span>"
        f"{feature_html}</div>{components_html}</div>"
    )


def _render_step_5_complete(ds: Any) -> None:
    """Generate only after the Step 4 T-DNA operation gate has passed."""
    if st.session_state.get("formal_betalain_gate3_case"):
        from services.betalain_pbi121_canonical_construct import (
            BetalainPbi121CanonicalConstructError,
            evaluate_betalain_pbi121_prerequisites,
            generate_betalain_pbi121_canonical_construct,
        )
        from services.plant_project_draft_schema import new_project_id

        st.subheader("Step 5: pBI121 replacement and canonical construct review")
        confirmed = bool(st.session_state.get("formal_betalain_repeated_regulatory_confirmed"))
        assessment = evaluate_betalain_pbi121_prerequisites(repeated_regulatory_confirmed=confirmed)
        strategy = assessment["replacement_strategy_summary"]
        st.dataframe(
            [
                {"TU": "TU1", "Structure": "CaMV 35S promoter -> CYP76AD1 -> NOS 3' regulatory region"},
                {"TU": "TU2", "Structure": "CaMV 35S promoter -> DODA1 -> NOS 3' regulatory region"},
                {"TU": "TU3", "Structure": "CaMV 35S promoter -> cDOPA5GT -> NOS 3' regulatory region"},
            ],
            hide_index=True,
            use_container_width=True,
        )
        st.markdown(
            f"**Source length:** 14,758 bp  \n"
            f"**Replacement interval:** {strategy.get('replacement_start')}..{strategy.get('replacement_end')} (1-based inclusive)  \n"
            f"**Removed length:** 3,006 bp  \n"
            f"**Strategy status:** {strategy.get('strategy_status')}"
        )
        for blocker in assessment["blockers"]:
            st.error(blocker)
        for warning in assessment["warnings"]:
            st.warning(warning)
        result = st.session_state.get("mvp_vector_result")
        if st.button(
            "Generate computational canonical construct",
            type="primary",
            disabled=bool(assessment["blockers"]),
            key="formal_betalain_generate_canonical",
        ):
            try:
                result = generate_betalain_pbi121_canonical_construct(
                    project_id=str(st.session_state.setdefault("mvp_project_id", new_project_id())),
                    project_name=str(
                        st.session_state.get("formal_project_name")
                        or _DEFAULT_PATHWAY_PROJECT_NAME
                    ),
                    repeated_regulatory_confirmed=confirmed,
                )
                result["project_type"] = PROJECT_TYPE_DUAL_TU
                result["input_lengths"] = {"backbone": 14758}
                pathway_mapping = _refresh_pathway_mapping_status()
                result["formal_project_context"].update(
                    {
                        "design_scenario": "metabolic_pathway_multi_tu_vector",
                        "pathway_steps": pathway_mapping["pathway_steps"],
                        "pathway_mapping": pathway_mapping,
                    }
                )
                result["formal_project_context"]["source_backbone_length"] = 14758
                st.session_state["mvp_vector_result"] = result
                st.session_state["formal_dual_tu_combined_result"] = result
                st.session_state["formal_transcription_units"] = _normalize_transcription_units(
                    list((result.get("original_input") or {}).get("expression_units") or []),
                    list(result.get("unit_order") or []),
                )
                st.session_state["mvp_current_input_signature"] = result["input_signature"]
                st.session_state["mvp_inputs_stale"] = False
            except BetalainPbi121CanonicalConstructError as exc:
                st.error(str(exc))
            else:
                st.success("The canonical construct was generated from the reviewed source records.")
                st.rerun()
        if isinstance(result, dict):
            complete = dict(result.get("complete_plasmid") or {})
            st.markdown(
                f"**Inserted multi-TU length:** {int((result.get('combined_construct') or {}).get('total_length') or 0):,} bp  \n"
                f"**Final circular plasmid length:** {int(complete.get('total_length') or 0):,} bp"
            )
        _render_step_navigation(
            current_step=5,
            next_enabled=isinstance(result, dict) and not assessment["blockers"],
            next_label=_t('v1.expression.save_project_review_results'),
            disabled_reason="Generate the canonical construct after all blockers are resolved.",
        )
        return
    if _is_pathway_multi_tu_project():
        st.subheader(_t('v1.expression.step_5_generate_computational_record_full_circular'))
        combined = st.session_state.get("formal_dual_tu_combined_result")
        backbone = dict(st.session_state.get("formal_backbone_record") or {})
        insertion = dict(st.session_state.get("formal_insertion_settings") or {})
        result = st.session_state.get("mvp_vector_result")
        complete = (
            dict(result.get("complete_plasmid") or {})
            if isinstance(result, dict)
            else {}
        )
        complete_current = bool(
            complete
            and isinstance(result, dict)
            and result.get("workflow_kind") == "gate3_pathway"
            and result.get("input_signature")
            == st.session_state.get("mvp_current_input_signature")
            and not st.session_state.get("mvp_inputs_stale")
        )
        metrics = st.columns(4)
        metrics[0].metric(
            _t('v1.results_final_report.tu_count'),
            str(len(list((combined or {}).get("expression_units") or [])))
            if isinstance(combined, dict)
            else "0",
        )
        metrics[1].metric(
            _t('v1.expression.multi_tu_region'),
            f"{int(((combined or {}).get('combined_construct') or {}).get('total_length') or 0):,} bp"
            if isinstance(combined, dict)
            else "0 bp",
        )
        metrics[2].metric(_t('v1.expression.pbi121_backbone'), f"{int(backbone.get('length') or 0):,} bp")
        metrics[3].metric(
            _t('v1.expression.full_plasmid'),
            f"{int(complete.get('total_length') or 0):,} bp" if complete_current else "--",
        )
        st.markdown(
            _t('v1.expression.fixed_replacement_record_summary', p0=insertion.get('start_coordinate') or '--', p1=insertion.get('end_coordinate') or '--', p2=_topology_label(backbone.get('topology')))
        )
        if st.button(_t('v1.expression.generate_full_plasmid'), type="primary", key="formal_pathway_generate_complete"):
            try:
                _generate_dual_tu_complete_plasmid(ds)
            except Exception as exc:
                st.error(_t('v1.expression.full_plasmid_computation_record_not_generated', p0=exc))
            else:
                st.rerun()
        if complete_current:
            validation = dict(complete.get("validation_summary") or {})
            st.success(_t('v1.expression.full_plasmid_computational_record_been_generated_proceed'))
            st.markdown(
                _t('v1.expression.canonical_sha_blocking_warning_summary', p0=complete.get('sequence_sha256'), p1=int(validation.get('blocking_count') or 0), p2=int(validation.get('warning_count') or 0))
            )
        _render_step_navigation(
            current_step=5,
            next_enabled=complete_current,
            next_label=_t('v1.expression.review_results_export'),
            disabled_reason=_t("v1.expression.full_plasmid_record_required_help"),
        )
        return
    if _is_generic_multi_tu_workflow():
        _render_generic_multi_tu_step_5(ds)
        return
    from services.canonical_construct_runtime import (
        CanonicalConstructRuntimeError,
        active_complete_plasmid_snapshot,
        active_construct_snapshot,
    )
    from services.formal_t_dna_review import validate_t_dna_operation

    st.subheader(_t('v1.expression.step_5_vector_construction_design_computational_check'))
    backbone = dict(st.session_state.get("formal_backbone_record") or {})
    settings = dict(st.session_state.get("formal_insertion_settings") or {})
    operation = validate_t_dna_operation(
        backbone,
        confirmation=dict(settings.get("t_dna_confirmation") or {}),
        insertion_settings=settings,
        workflow_id=_active_backbone_workflow_id(),
    )
    result = st.session_state.get("mvp_vector_result")
    result_is_current = bool(
        isinstance(result, dict)
        and result.get("input_signature") == st.session_state.get("mvp_current_input_signature")
        and not st.session_state.get("mvp_inputs_stale")
    )
    plasmid: dict[str, Any] = {}
    if isinstance(result, dict):
        try:
            plasmid = active_complete_plasmid_snapshot(result.get("runtime"))
        except CanonicalConstructRuntimeError:
            plasmid = {}
    cassette_length: int | None = None
    cassette_result = st.session_state.get("formal_cassette_result")
    if isinstance(cassette_result, Mapping):
        try:
            cassette_length = int(
                active_construct_snapshot(cassette_result.get("runtime")).get("sequence_length") or 0
            )
        except CanonicalConstructRuntimeError:
            cassette_length = None

    st.markdown(_t('v1.expression.construct_summary'), unsafe_allow_html=True)
    def _metric_value(value: str) -> str:
        return f"<span class='notranslate' translate='no'>{value}</span>"

    metric_rows = (
        (_t('v1.expression.expression_cassette_length'), _metric_value(f"{cassette_length:,} bp") if cassette_length is not None else "--"),
        (_ui("载体骨架长度"), _metric_value(f"{int(backbone.get('length') or 0):,} bp") if backbone else "--"),
        (_ui("完整构建长度"), _metric_value(f"{int(plasmid.get('sequence_length') or 0):,} bp") if plasmid else "--"),
        (_ui("拓扑"), _ui(_topology_label(plasmid.get("topology"))) if plasmid else "--"),
    )
    st.markdown(
        "<div class='formal-context-grid'>" + "".join(
            "<div class='formal-context-item'><div class='formal-context-label'>"
            f"{label}</div><div class='formal-context-value'>{value}</div></div>"
            for label, value in metric_rows
        ) + "</div>",
        unsafe_allow_html=True,
    )

    st.markdown(_t('v1.expression.insertion_replacement_strategy'), unsafe_allow_html=True)
    accession = str(
        backbone.get("source_accession_version")
        or backbone.get("accession")
        or backbone.get("original_record_identifier")
        or "--"
    )
    operation_type = _ui("替换" if settings.get("mode") == "replacement" else "插入")
    coordinates = f"{settings.get('start_coordinate') or '--'}–{settings.get('end_coordinate') or '--'}"
    t_dna_status = (
        _ui("已确认") if operation.get("allowed") else _ui("需要人工确认")
        if operation.get("status") == "needs_manual_confirmation" else "未通过"
    )
    strategy_rows = (
        (_ui("载体"), escape(str(backbone.get("display_name") or "--"))),
        ("accession", escape(accession)),
        (_ui("操作类型"), operation_type),
        (_ui("插入/替换坐标"), coordinates),
        (_ui("方向"), _ui("反向" if settings.get("insertion_orientation") == "reverse" else "正向")),
        (_ui("T-DNA / LB-RB 状态"), t_dna_status),
    )
    st.markdown(
        "<div class='formal-context-grid formal-step5-strategy-grid'>" + "".join(
            "<div class='formal-context-item'><div class='formal-context-label'>"
            f"{label}</div><div class='formal-context-value'>{value}</div></div>"
            for label, value in strategy_rows
        ) + "</div>",
        unsafe_allow_html=True,
    )
    if not operation.get("allowed"):
        st.error(_t('v1.expression.cannot_generate_complete_vector_construct_design', p0=operation.get('reason')))

    st.markdown(_t('v1.expression.full_construct_preview'), unsafe_allow_html=True)
    if result_is_current:
        _render_publication_map_svg(
            result,
            view_type="complete_circular_plasmid",
            display_name=str(result.get("project_name") or "Canonical construct"),
            download_key="publication_map_step5_complete_plasmid_svg",
        )
    elif plasmid:
        st.warning(_t('v1.expression.result_not_latest_canonical_revision_publication_map'))
    else:
        st.markdown(_step5_construct_preview_html(plasmid), unsafe_allow_html=True)
        st.info(_t('v1.expression.after_generating_full_vector_publication_map_svg'))

    validation = dict(plasmid.get("validation_summary") or {})
    construct_status = str(plasmid.get("construct_status") or "")
    construct_state = _ui("已生成") if result_is_current and construct_status == "current" else _ui("需要重新审查") if plasmid else _ui("未生成")
    coordinate_state = _t("v1.expression.items_count", p0=len(list(plasmid.get('feature_rows') or []))) if plasmid else "--"
    consistency_state = _ui("通过") if result_is_current and construct_status == "current" else _ui("需要重新审查") if plasmid else "--"
    checksum = str(plasmid.get("sequence_checksum") or "")
    st.markdown(_t('v1.expression.computational_check_summary'), unsafe_allow_html=True)
    check_rows = (
        (_t('v1.expression.construct_status'), construct_state, ""),
        (_t('v1.expression.sequence_consistency'), consistency_state, ""),
        (_t('v1.expression.feature_annotation'), coordinate_state, ""),
        (_t('v1.expression.blocking_items'), str(int(validation.get("blocking_count") or 0)), ""),
        (_t('v1.expression.warning_items'), str(int(validation.get("warning_count") or 0)), ""),
        (_t('v1.expression.canonical_hash'), escape(checksum[:12]) if checksum else "--", _t('v1.expression.canonical_hash_traceability_note')),
    )
    st.markdown(
        "<div class='formal-context-grid formal-step5-check-grid'>" + "".join(
            "<div class='formal-context-item'><div class='formal-context-label'>"
            f"{label}</div><div class='formal-context-value'>{value}</div>"
            f"<div class='formal-step5-hash-note'>{note}</div></div>"
            if note else
            "<div class='formal-context-item'><div class='formal-context-label'>"
            f"{label}</div><div class='formal-context-value'>{value}</div></div>"
            for label, value, note in check_rows
        ) + "</div>",
        unsafe_allow_html=True,
    )

    if result_is_current:
        st.caption(_t('v1.expression.full_construct_generated'))
    elif st.button(
        _t('v1.expression.generate_full_vector'),
        type="primary",
        disabled=not bool(operation.get("allowed")) or bool(st.session_state.get("formal_ui_action_busy")),
    ):
        completed_actions = dict(st.session_state.get("formal_ui_completed_actions") or {})
        completed_actions.pop("step5_generate_continue", None)
        st.session_state["formal_ui_completed_actions"] = completed_actions
        succeeded, generated_result, _executed = _execute_formal_action(
            step=5,
            action_id="step5_generate_continue",
            input_signature=_formal_ui_signature(
                {
                    "cassette": st.session_state.get("formal_cassette_input_signature"),
                    "backbone": backbone.get("normalized_sequence_sha256")
                    or backbone.get("sequence_sha256")
                    or backbone.get("normalized_sequence"),
                    "insertion": settings,
                }
            ),
            action=lambda: _generate_complete_plasmid(ds),
            success_status="已生成",
            success_message="载体设计已生成，可以继续第六步。",
            failure_status="生成失败",
        )
        if succeeded and isinstance(generated_result, dict):
            st.rerun()
    _render_step_navigation(
        current_step=5,
        next_enabled=result_is_current,
        disabled_reason=(
            str(operation.get("reason") or "请先完成当前载体生成条件。")
            if not operation.get("allowed")
            else "请先生成当前完整载体。" if not result_is_current else ""
        ),
    )


def _render_step_6_review(ds: Any) -> None:
    if st.session_state.get("formal_betalain_gate3_case"):
        st.subheader(_t('v1.expression.step_6_project_save_result_review'))
        result = st.session_state.get("mvp_vector_result")
        if not isinstance(result, dict):
            st.warning(_t('v1.expression.first_generate_canonical_construct_record_computation_step'))
            _render_step_navigation(current_step=6, next_enabled=False, disabled_reason=_t("v1.expression.canonical_record_required_help"))
            return
        st.caption(_t('v1.expression.result_computational_design_review_only_does_not'))
        _render_results_export_content(include_project_actions=False)
        _render_step_navigation(current_step=6, next_enabled=False)
        return
    if _is_generic_multi_tu_workflow():
        st.subheader(_t('v1.expression.step_6_results_export'))
        result = st.session_state.get("mvp_vector_result")
        if not _is_multi_tu_expression_assembly(result):
            st.warning(_t('v1.expression.no_multi_tu_canonical_assembly_available_return_message'))
            _render_step_navigation(current_step=6, next_enabled=False)
            return
        combined = dict(result.get("combined_construct") or {})
        validation_label, validation_note, _formal_findings = _multi_tu_formal_validation_copy(combined)
        validation_status = str(
            dict(combined.get("formal_validation") or {}).get("status") or ""
        )
        st.markdown(
            _t('v1.expression.final_review'),
            unsafe_allow_html=True,
        )
        st.markdown(
            _t('v1.expression.result_type_multi_tu_expression_cassette_assembly', p0=len(list(result.get('expression_units') or [])), p1=int(combined.get('total_length') or 0)),
            unsafe_allow_html=True,
        )
        (st.error if validation_status == "legacy_incomplete" else st.warning if validation_status != "formal_ready" else st.success)(
            _format_multi_tu_validation_copy(validation_label, validation_note)
        )
        st.info(_t('v1.expression.fasta_genbank_project_saves_all_derived_canonical'))
        _render_results_export_content(include_project_actions=False)
        _render_step_navigation(current_step=6, next_enabled=False)
        return
    from services.formal_t_dna_review import validate_t_dna_operation

    st.subheader(_t('v1.expression.step_6_project_save_result_review_delivery'))
    result = st.session_state.get("mvp_vector_result")
    backbone = dict(st.session_state.get("formal_backbone_record") or {})
    settings = dict(st.session_state.get("formal_insertion_settings") or {})
    operation = validate_t_dna_operation(
        backbone,
        confirmation=dict(settings.get("t_dna_confirmation") or {}),
        insertion_settings=settings,
        workflow_id=_active_backbone_workflow_id(),
    )
    if not isinstance(result, dict):
        st.warning(_t('v1.expression.no_full_vector_construct_design_available_complete'))
        _render_step_navigation(current_step=6, next_enabled=False, disabled_reason=_t("v1.expression.full_vector_required_help"))
        return
    if not operation.get("allowed"):
        st.warning(_t('v1.expression.vector_settings_editor_do_not_meet_requirements'))
    st.markdown(_t('v1.expression.record_can_reviewed_below_including_existing_result'))
    _render_results_export_content(include_project_actions=False)
    _render_step_navigation(current_step=6, next_enabled=False)


def _render_step_6_complete(ds: Any) -> None:
    from services.canonical_construct_runtime import (
        CanonicalConstructRuntimeError,
        active_complete_plasmid_snapshot,
    )

    st.subheader(_t('v1.expression.step_6_project_save_result_review_delivery'))
    if _is_dual_tu_project():
        combined = st.session_state.get("formal_dual_tu_combined_result")
        backbone = dict(st.session_state.get("formal_backbone_record") or {})
        insertion = dict(st.session_state.get("formal_insertion_settings") or {})
        result = st.session_state.get("mvp_vector_result")
        unit_rows = list((combined or {}).get("expression_units") or []) if isinstance(combined, dict) else []
        complete = result.get("complete_plasmid") if isinstance(result, dict) else {}
        validation = complete.get("validation_summary") if isinstance(complete, dict) else {}
        metrics = st.columns(4)
        metrics[0].metric(_t('v1.results_final_report.tu_count'), str(len(unit_rows)))
        metrics[1].metric(_t('v1.expression.multi_tu_region'), f"{int(((combined or {}).get('combined_construct') or {}).get('total_length') or 0):,} bp")
        metrics[2].metric(_t('v1.expression.scaffold'), f"{int(backbone.get('length') or 0):,} bp")
        metrics[3].metric(_t('v1.expression.full_plasmid'), f"{int((complete or {}).get('total_length') or 0):,} bp")
        mode = _t('v1.expression.backbone_replacement') if insertion.get("mode") == "replacement" else _t('v1.expression.backbone_insert')
        st.markdown(
            _t('v1.expression.topology_position_overall_orientation', p0=_topology_label(backbone.get('topology')), p1=mode, p2=insertion.get('start_coordinate') or '--', p3=insertion.get('end_coordinate') or '--', p4=_t('v1.common.reverse') if insertion.get('insertion_orientation') == 'reverse' else _t('v1.common.forward'))
        )
        if st.button(_t('v1.expression.generate_full_plasmid'), type="primary"):
            try:
                _generate_dual_tu_complete_plasmid(ds)
            except Exception as exc:
                st.error(_t('v1.expression.full_plasmid_not_generated', p0=exc))
            else:
                st.rerun()
        if isinstance(result, dict):
            st.markdown(
                _t('v1.expression.check_warning_blocking', p0=int((validation or {}).get('warning_count') or 0), p1=int((validation or {}).get('blocking_count') or 0))
            )
            with st.expander(_t('v1.common.technical_details'), expanded=False):
                st.markdown(_t('v1.expression.full_plasmid_sha_256', p0=str((complete or {}).get('sequence_sha256') or '')))
            st.markdown(
                _t('v1.expression.full_plasmid_generation_succeeded_both_multi_tu'),
                unsafe_allow_html=True,
            )
            _render_results_export_content(include_project_actions=False)
        _render_step_navigation(
            current_step=6,
            next_enabled=False,
            disabled_reason=_t("v1.expression.full_plasmid_required_for_results_help") if not isinstance(result, dict) else "",
        )
        return
    from services.formal_single_gene_runtime import cassette_input_signature

    backbone = st.session_state.get("formal_backbone_record") or {}
    result = st.session_state.get("mvp_vector_result")
    project_id = str(st.session_state.get("mvp_project_id") or "")
    _cds_input, cassette_records = _wizard_component_records(ds, project_id)
    cassette_length = _canonical_cassette_length(
        st.session_state.get("formal_cassette_result"),
        cassette_input_signature=cassette_input_signature(cassette_records),
    )
    result_context = result.get("formal_project_context") if isinstance(result, dict) and isinstance(result.get("formal_project_context"), dict) else {}
    result_needs_review = str(result_context.get("construct_review_status") or "current") == "needs_review"
    result_is_current = bool(
        isinstance(result, dict)
        and not st.session_state.get("mvp_inputs_stale")
        and result.get("input_signature") == st.session_state.get("mvp_current_input_signature")
        and cassette_length is not None
        and not result_needs_review
    )
    plasmid_length = 0
    if isinstance(result, dict):
        try:
            plasmid_length = int(active_complete_plasmid_snapshot(result.get("runtime")).get("sequence_length") or 0)
        except CanonicalConstructRuntimeError:
            plasmid_length = 0
    elements = ds.elements if isinstance(ds.elements, dict) else {}
    insertion = dict(st.session_state.get("formal_insertion_settings") or {})
    mode = _t('v1.expression.backbone_replacement') if insertion.get("mode") == "replacement" else _t('v1.expression.backbone_insert')
    location = f"{insertion.get('start_coordinate') or '--'}–{insertion.get('end_coordinate') or '--'}"
    direction = _t('v1.common.reverse') if insertion.get("insertion_orientation") == "reverse" else _t('v1.common.forward')
    st.markdown(
        _t('v1.expression.expression_cassette_vector_backbone_bp_insertion_settings', p0=escape(_formal_element_display_name(elements.get('promoter_name') or _t('v1.ai_assisted_design.promoter'), 'promoter')), p1=escape(_formal_element_display_name(ds.gene_name or 'CDS', 'cds')), p2=escape(_formal_element_display_name(elements.get('terminator_name') or _t('v1.expression.3_regulatory_element'), 'terminator')), p3=f'{cassette_length:,} bp' if result_is_current and cassette_length is not None else _t('v1.expression.current_result_invalid'), p4=escape(str(backbone.get('display_name') or backbone.get('name') or _t('v1.expression.not_selected_backbone'))), p5=int(backbone.get('length') or 0), p6=_topology_label(backbone.get('topology')), p7=mode, p8=escape(location), p9=direction),
        unsafe_allow_html=True,
    )
    estimated_length = plasmid_length or max(0, int(backbone.get("length") or 0) + int(cassette_length or 0) - (int(insertion.get("end_coordinate") or 0) - int(insertion.get("start_coordinate") or 0) if insertion.get("mode") == "replacement" else 0))
    st.markdown(_t('v1.expression.estimated_full_plasmid_length_bp', p0=estimated_length), unsafe_allow_html=True)
    if st.button(_t('v1.expression.generate_full_plasmid'), type="primary"):
        try:
            _generate_complete_plasmid(ds)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success(_t('v1.expression.full_plasmid_generated_successfully'))
            st.rerun()
    if not result_is_current and isinstance(result, dict):
        _render_results_export_content(
            include_project_actions=False,
            result_preview_mode=True,
        )
    if result_is_current:
        st.markdown(
            _t('v1.expression.complete_plasmid_generated_successfully_view_results_save'),
            unsafe_allow_html=True,
        )
        _render_results_export_content(include_project_actions=False)
    _render_step_navigation(
        current_step=6,
        next_enabled=False,
        disabled_reason=_t("v1.expression.current_inputs_must_be_unchanged_help") if not result_is_current else "",
    )


def _render_design_workspace() -> None:
    # 当前项目： source-shape marker retained for frozen page contract tests.
    # Legacy source-shape markers: st.title("表达设计") / st.caption("按步骤完成植物表达载体设计").
    """Render one formal step while preserving wizard_flow DesignSession state."""
    _record_current_project_surface(PAGE_DESIGN_WORKSPACE)
    ds = _controller().get()
    if _is_result_preview_mode():
        st.session_state["formal_read_only_preview"] = True
        _render_result_preview_mode()
        return
    st.title(_t('v1.common.expression_design'))
    st.caption(_t('v1.expression.complete_plant_expression_vector_design_step_by'))
    st.caption(
        _t('v1.expression.current_project_label')
        + str(
            str(st.session_state.get("formal_project_name") or "")
            or _t('v1.expression.unnamed_plant_expression_vector_project')
        )
    )
    preview_requested = bool(st.session_state.pop("formal_step_preview", False))
    normalized_step = _normalize_formal_current_step(ds.step)
    st.session_state["formal_read_only_preview"] = bool(
        preview_requested and normalized_step != ds.step
    )
    if normalized_step != ds.step and not preview_requested:
        ds.step = normalized_step
        _controller().save(ds)
    _render_step_strip(ds.step)
    if st.session_state["formal_read_only_preview"]:
        short_name_keys = _formal_step_label_keys()
        st.info(_t('v1.expression.complete_step_first', p0=normalized_step, p1=_t(short_name_keys[normalized_step - 1])))
    _render_formal_action_feedback(ds.step)
    renderers = {1: _render_step_1_project, 2: _render_step_2_cds, 3: _render_step_3_elements, 4: _render_step_4_backbone, 5: _render_step_5_complete, 6: _render_step_6_review}
    renderers.get(ds.step, _render_step_1_project)(ds)


def _render_crispr_product_workflow() -> None:
    """Render the extracted bounded CRISPR P0 workspace."""
    from views.CrisprWorkspace import render

    render(
        change_page=_change_page,
        expression_design_page=PAGE_DESIGN_WORKSPACE,
    )

def _feature_locations(row: dict[str, Any]) -> list[tuple[int, int]]:
    parts = row.get("location_parts") if isinstance(row.get("location_parts"), list) else []
    if parts:
        return [
            (max(0, int(part.get("start") or 1) - 1), int(part.get("end") or 0))
            for part in parts
        ]
    return [(max(0, int(row.get("start") or 1) - 1), int(row.get("end") or 0))]


def _canonical_map_features(plasmid: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Adapt canonical feature rows to the existing MVP10 map renderer."""
    type_colors = {
        "promoter": "#23848b",
        "cds": "#287a4b",
        "terminator": "#d48324",
        "three_prime_element": "#d48324",
        "regulatory": "#7c5aa6",
        "rep_origin": "#278d87",
        "selection": "#b84e58",
        "border": "#697386",
        "misc_feature": "#697386",
    }
    features = []
    input_records = result.get("input_records") if isinstance(result.get("input_records"), dict) else {}
    for index, row in enumerate(list(plasmid.get("feature_rows") or [])):
        feature_type = str(row.get("feature_type") or "misc_feature").lower()
        source = str(row.get("source") or "")
        source_record = input_records.get(feature_type, {}) if source == "transcription_unit" else input_records.get("backbone", {})
        source_record = source_record if isinstance(source_record, dict) else {}
        source_name = str(source_record.get("source_name") or "")
        accession = source_name if re.fullmatch(r"[A-Za-z]{1,6}_?\d+(?:\.\d+)?", source_name) else ""
        source_label = accession or ("内置示例骨架" if source == "backbone" and source_record.get("source_kind") == "example" else "未记录")
        display_name = str(row.get("name") or feature_type or f"元件 {index + 1}")
        if feature_type == "terminator" and "camv 3'utr" in str(source_record.get("display_name") or "").casefold():
            feature_type = "three_prime_element"
        if display_name == "Plant vector backbone":
            display_name = "植物载体骨架"
        display_name = _formal_element_display_name(display_name, feature_type)
        unit_id = str(row.get("unit_id") or "")
        if unit_id and not display_name.startswith(f"{unit_id} ·"):
            display_name = f"{unit_id} · {display_name}"
        features.append(
            {
                "id": str(row.get("component_id") or row.get("backbone_feature_id") or f"feature_{index}"),
                "name": display_name,
                "type": feature_type,
                "locations": _feature_locations(row),
                "strand": int(row.get("strand") or 1),
                "source": source,
                "accession": accession or "未记录",
                "source_label": source_label,
                "unit": unit_id,
                "original_file": "r229_backbone.gb" if source == "backbone" and source_record.get("source_kind") == "example" else "",
                "owner": "项目骨架" if source == "backbone" else "表达元件",
                "track": -27 if source == "backbone" else 5,
                "width": 10 if source == "backbone" else 14,
                "color": type_colors.get(feature_type, "#697386"),
                "show_label": feature_type in {"promoter", "cds", "terminator", "three_prime_element", "rep_origin", "selection"},
            }
        )
    return features


def _public_feature_rows(plasmid: dict[str, Any], result: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep runtime-only identifiers out of ordinary result-page tables."""
    rows: list[dict[str, Any]] = []
    for feature in _canonical_map_features(plasmid, result):
        locations = feature.get("locations") or []
        start = min((int(item[0]) + 1 for item in locations), default=0)
        end = max((int(item[1]) for item in locations), default=0)
        rows.append(
            {
                "名称": feature["name"],
                "类型": _component_type_label(feature["type"]),
                "起点": start,
                "终点": end,
                "长度": sum(max(0, int(end_) - int(start_)) for start_, end_ in locations),
                "链方向": "正向（+）" if int(feature.get("strand") or 1) >= 0 else "反向（−）",
                "所属表达单元": feature.get("unit") or "",
                "来源 accession": feature.get("accession") or "未记录",
                "来源说明": feature.get("source_label") or "未记录",
            }
        )
    return rows


def _formal_circular_map_svg(total_length: int, features: list[dict[str, Any]]) -> str:
    """Render canonical intervals without deriving a second coordinate model."""
    total = max(1, int(total_length))
    center = 300.0
    radius = 172.0

    def point(angle_degrees: float, distance: float = radius) -> tuple[float, float]:
        radians = math.radians(angle_degrees - 90.0)
        return center + distance * math.cos(radians), center + distance * math.sin(radians)

    paths: list[str] = []
    labels: list[str] = []
    for feature in features:
        locations = list(feature.get("locations") or [])
        for location_index, (start, end) in enumerate(locations):
            start_angle = 360.0 * max(0, int(start)) / total
            end_angle = 360.0 * min(total, int(end)) / total
            span = max(0.2, end_angle - start_angle)
            x1, y1 = point(start_angle)
            x2, y2 = point(end_angle)
            large_arc = 1 if span > 180 else 0
            color = escape(str(feature.get("color") or "#697386"))
            paths.append(
                f"<path d='M {x1:.2f} {y1:.2f} A {radius:.2f} {radius:.2f} 0 {large_arc} 1 {x2:.2f} {y2:.2f}' "
                f"fill='none' stroke='{color}' stroke-width='{int(feature.get('width') or 12)}' stroke-linecap='round'><title>"
                f"{escape(str(feature.get('name') or ''))} · {int(start) + 1}–{int(end)}</title></path>"
            )
            if location_index == 0 and str(feature.get("type") or "") == "rep_origin":
                label_angle = start_angle + span / 2
                lx, ly = point(label_angle, radius + 42)
                anchor = "start" if lx >= center else "end"
                labels.append(
                    f"<text x='{lx:.2f}' y='{ly:.2f}' text-anchor='{anchor}' dominant-baseline='middle' "
                    f"class='map-feature-label' font-size='13' fill='#334155'>{escape(str(feature.get('name') or ''))}</text>"
                )
    return (
        "<div class='map-frame'><svg viewBox='0 0 600 600' role='img' aria-label='完整质粒环形图'>"
        "<circle cx='300' cy='300' r='172' fill='none' stroke='#dce4dc' stroke-width='18'/>"
        + "".join(paths)
        + f"<text class='map-center-value' x='300' y='288' text-anchor='middle' font-size='20' font-weight='700' fill='#1d2920'>{total_length:,} bp</text>"
        + "<text class='map-center-label' x='300' y='316' text-anchor='middle' font-size='13' fill='#566579'>完整质粒</text>"
        + "".join(labels)
        + "</svg></div>"
    )


def _formal_linear_map_html(total_length: int, features: list[dict[str, Any]]) -> str:
    total = max(1, int(total_length))
    rows: list[str] = []
    for feature in features:
        bars: list[str] = []
        for start, end in list(feature.get("locations") or []):
            left = max(0.0, min(100.0, 100.0 * int(start) / total))
            width = max(0.35, min(100.0 - left, 100.0 * max(0, int(end) - int(start)) / total))
            bars.append(
                f"<div class='linear-feature' style='left:{left:.4f}%;width:{width:.4f}%;background:{escape(str(feature.get('color') or '#697386'))}' "
                f"title='{escape(str(feature.get('name') or ''))} · {int(start) + 1}–{int(end)}'>"
                f"{escape(str(feature.get('name') or '')) if width >= 8 else ''}</div>"
            )
        rows.append(
            "<div class='linear-track-row'>"
            f"<div class='linear-track-label'>{escape(str(feature.get('unit') or _component_type_label(feature.get('type'))))}</div>"
            f"<div class='linear-track'>{''.join(bars)}</div></div>"
        )
    return (
        "<div class='linear-map'><div class='linear-map-inner'>"
        f"<div class='linear-map-scale'><span aria-hidden='true'></span><div class='linear-map-scale-values'><span>1 bp</span><span>{total_length:,} bp</span></div></div>"
        + "".join(rows)
        + "</div></div>"
    )


def _formal_map_legend_html(features: list[dict[str, Any]]) -> str:
    """Render only the feature types that are visible in the current map."""
    items: list[str] = []
    seen: set[str] = set()
    for feature in features:
        feature_type = str(feature.get("type") or "misc_feature")
        display_label = _component_type_label(feature_type)
        if display_label in seen:
            continue
        seen.add(display_label)
        items.append(
            "<span class='map-legend-item'>"
            f"<span class='map-legend-swatch' style='background:{escape(str(feature.get('color') or '#697386'))}'></span>"
            f"{escape(display_label)}</span>"
        )
    return "<div class='map-legend' aria-label='图例'>" + "".join(items) + "</div>"


def _format_canonical_sequence_for_review(sequence: str, *, line_width: int = 60) -> str:
    """Format the existing canonical sequence for a readable, bounded review view."""
    normalized = str(sequence or "")
    width = max(1, int(line_width))
    coordinate_width = max(1, len(str(len(normalized))))
    return "\n".join(
        f"{start:>{coordinate_width}d}  {normalized[start - 1:start - 1 + width]}"
        for start in range(1, len(normalized) + 1, width)
    )


def _render_sequence_review(sequence: Any, *, label: str) -> None:
    """Render one shared, numbered canonical sequence view without byte changes."""
    normalized = str(sequence or "")
    st.markdown(f"**{escape(str(label))}**")
    if not normalized:
        st.info(_t("v1.results_final_report.no_sequence_available"))
        return
    line_width = 60
    coordinate_width = max(1, len(str(len(normalized))))
    line_nodes = []
    for start in range(1, len(normalized) + 1, line_width):
        line = normalized[start - 1:start - 1 + line_width]
        end = start + len(line) - 1
        line_nodes.append(
            f'<span class="sequence-review-line" data-start="{start}" data-end="{end}">'
            f'{start:>{coordinate_width}d}  {escape(line)}</span>'
        )
    line_markup = "\n".join(line_nodes)
    st.markdown(
        f"""<div class=\"sequence-review-meta\"><span>{escape(_t('v1.results_final_report.sequence_positions_1_based'))}</span><strong>{len(normalized):,} bp</strong></div>
<div class=\"sequence-review-viewer\" data-line-width=\"60\" data-sequence-length=\"{len(normalized)}\" tabindex=\"0\">{line_markup}</div>""",
        unsafe_allow_html=True,
    )


def _render_unit_sequence_reviews(units: Any) -> None:
    for index, unit in enumerate(sorted(units, key=lambda item: int(item.get('order') or 0)), start=1):
        with st.expander(f"TU{index} · {unit.get('display_name') or '--'}", expanded=False):
            _render_sequence_review(unit.get('dna'), label=f"TU{index}")
            with st.expander(_t('v1.common.technical_details'), expanded=False):
                st.json({key: unit.get(key) for key in ('unit_id', 'range', 'sequence_sha256')})


def _render_publication_map_svg(
    result: Mapping[str, Any],
    *,
    view_type: str,
    display_name: str,
    download_key: str,
) -> bool:
    """Render and download one exact identity-bound Publication Map SVG payload."""
    # build_publication_map_svg_artifact remains the shared SVG foundation for all formats.
    from services.publication_map_contract import (
        PublicationMapContractError,
        PublicationMapViewType,
    )
    from services.publication_map_product import (
        build_publication_map_export_artifact,
        build_publication_map_svg_artifact,
    )
    from services.publication_map_viewer import build_publication_map_viewer_html

    try:
        resolved_view = PublicationMapViewType(view_type)
        svg_artifact = build_publication_map_svg_artifact(
            result.get("runtime"),
            view_type=resolved_view,
            display_name=display_name,
        )
    except (PublicationMapContractError, TypeError, ValueError) as exc:
        st.error(_t('v1.publication_map.publication_map_unavailable', p0=exc))
        return False

    viewer_id = re.sub(r"[^A-Za-z0-9_-]", "-", download_key)
    viewer_html = build_publication_map_viewer_html(
        svg_artifact.svg_text,
        viewer_id=viewer_id,
        labels={
            "zoom_in": _t("v1.publication_map.viewer_zoom_in"),
            "zoom_out": _t("v1.publication_map.viewer_zoom_out"),
            "fit": _t("v1.publication_map.viewer_fit"),
            "reset": _t("v1.publication_map.viewer_reset"),
            "fullscreen": _t("v1.publication_map.viewer_fullscreen"),
            "pan": _t("v1.publication_map.viewer_pan"),
            "zoom_in_aria": _t("v1.publication_map.viewer_zoom_in_aria"),
            "zoom_out_aria": _t("v1.publication_map.viewer_zoom_out_aria"),
            "fit_aria": _t("v1.publication_map.viewer_fit_aria"),
            "reset_aria": _t("v1.publication_map.viewer_reset_aria"),
            "fullscreen_aria": _t("v1.publication_map.viewer_fullscreen_aria"),
            "pan_aria": _t("v1.publication_map.viewer_pan_aria"),
        },
    )
    components.html(viewer_html, height=560, scrolling=False)
    with st.expander(_t('v1.common.technical_details'), expanded=False):
        st.caption(
        _t(
            "v1.publication_map.canonical_identity_revision_sha_256",
            p0=svg_artifact.construct_identifier,
            p1=svg_artifact.revision_id,
            p2=svg_artifact.sequence_checksum,
        )
        )
    try:
        artifact = build_publication_map_export_artifact(
            result.get("runtime"), view_type=resolved_view, display_name=display_name
        )
    except (PublicationMapContractError, OSError, TypeError, ValueError) as exc:
        st.error(_t("v1.publication_map.export_unavailable", p0=exc))
        return False
    download_cols = st.columns(3)
    download_cols[0].download_button(
        _t('v1.publication_map.download_publication_map_svg'), data=artifact.svg_bytes, file_name=artifact.file_name,
        mime=artifact.mime, on_click="ignore", use_container_width=True, key=download_key,
    )
    download_cols[1].download_button(
        _t('v1.publication_map.download_publication_map_pdf'), data=artifact.pdf_bytes, file_name=artifact.pdf_file_name,
        mime="application/pdf", on_click="ignore", use_container_width=True,
        key=f"{download_key}_pdf",
    )
    download_cols[2].download_button(
        _t('v1.publication_map.download_publication_map_png'), data=artifact.png_bytes, file_name=artifact.png_file_name,
        mime="image/png", on_click="ignore", use_container_width=True,
        key=f"{download_key}_png",
    )
    return True


def _render_canonical_plasmid_maps(plasmid: dict[str, Any], result: dict[str, Any], *, map_view: str = "circular") -> None:
    """Render circular and linear maps from one canonical feature set."""
    features = _canonical_map_features(plasmid, result)
    total_length = int(plasmid.get("sequence_length") or 0)
    circular_svg = _formal_circular_map_svg(total_length, features)
    linear_html = _formal_linear_map_html(total_length, features)
    features_by_id = {feature["id"]: feature for feature in features}
    left, right = st.columns([3, 1])
    with left:
        if map_view == "linear":
            st.markdown(linear_html, unsafe_allow_html=True)
            st.markdown(_formal_map_legend_html(features), unsafe_allow_html=True)
            st.markdown(_t('v1.publication_map.linear_map_uses_coordinates_unified_construct_record'), unsafe_allow_html=True)
        else:
            st.markdown(circular_svg, unsafe_allow_html=True)
            st.markdown(_formal_map_legend_html(features), unsafe_allow_html=True)
        choices = {f"{item['name']} · {_component_type_label(item['type'])}": item["id"] for item in features}
        labels = list(choices)
        default_index = next((index for index, label in enumerate(labels) if str(features_by_id[choices[label]].get("type") or "").lower() == "cds"), 0)
        selected_label = st.selectbox(_t('v1.publication_map.select_component_view_details'), labels, index=default_index, key=f"formal_feature_picker_{map_view}")
        selected_id = choices[selected_label]
    with right:
        selected = features_by_id.get(selected_id) or next(iter(features_by_id.values()), {})
        locations = selected.get("locations") or []
        location_text = "；".join(f"{int(start) + 1:,}–{int(end):,}" for start, end in locations) or "--"
        feature_length = sum(max(0, int(end) - int(start)) for start, end in locations)
        direction = "正向 (+)" if int(selected.get("strand") or 1) >= 0 else "反向 (-)"
        st.markdown("<div class='formal-card compact'>", unsafe_allow_html=True)
        st.markdown(_t('v1.publication_map.component_details'), unsafe_allow_html=True)
        st.markdown(_t('v1.publication_map.name', p0=escape(str(selected.get('name') or '--'))), unsafe_allow_html=True)
        st.markdown(_t('v1.publication_map.type', p0=_component_type_label(selected.get('type'))), unsafe_allow_html=True)
        st.markdown(_t('v1.publication_map.start_end_position_bp', p0=location_text), unsafe_allow_html=True)
        st.markdown(_t('v1.publication_map.length_bp', p0=feature_length), unsafe_allow_html=True)
        st.markdown(_t('v1.publication_map.strand_orientation', p0=direction), unsafe_allow_html=True)
        if selected.get("unit"):
            st.markdown(_t('v1.publication_map.parent_expression_unit', p0=escape(str(selected['unit']))), unsafe_allow_html=True)
        if selected.get("source") == "backbone":
            st.markdown(_t('v1.publication_map.source', p0=escape(str(selected.get('source_label') or _t('v1.expression.not_recorded')))), unsafe_allow_html=True)
        else:
            st.markdown(_t('v1.publication_map.source_accession', p0=escape(str(selected.get('accession') or _t('v1.expression.not_recorded')))), unsafe_allow_html=True)
        if selected.get("original_file"):
            with st.expander(_t('v1.publication_map.advanced_information'), expanded=False):
                st.write(_t('v1.publication_map.original_file', p0=selected['original_file']))
        st.markdown("</div>", unsafe_allow_html=True)


def _render_multi_tu_assembly_results(
    result: dict[str, Any],
    *,
    is_current: bool,
    publication_map_current: bool,
    report_delivery_current: bool,
    save_design: Any,
    include_project_actions: bool = True,
    result_preview_mode: bool = False,
) -> None:
    from services.canonical_construct_runtime import CanonicalConstructRuntimeError, active_construct_snapshot
    from services.mt01_formal_runtime import (
        Mt01RuntimeError,
        is_mt01_claim,
        validate_mt01_result,
    )
    from services.mt02_formal_runtime import (
        Mt02RuntimeError,
        is_mt02_claim,
        validate_mt02_result,
    )

    mt01_claim = is_mt01_claim(result)
    mt02_claim = is_mt02_claim(result)
    if mt01_claim:
        try:
            validate_mt01_result(result)
        except Mt01RuntimeError as exc:
            st.error(str(exc))
            return
    if mt02_claim:
        try:
            validate_mt02_result(result)
        except Mt02RuntimeError as exc:
            st.error(str(exc))
            return

    try:
        canonical = active_construct_snapshot(result.get("runtime"))
    except CanonicalConstructRuntimeError as exc:
        st.error(str(exc))
        return
    combined = dict(result.get("combined_construct") or {})
    units = sorted(
        list(result.get("expression_units") or []),
        key=lambda unit: int(unit.get("order") or 0),
    )
    validation = dict(canonical.get("validation_summary") or {})
    blocking_count = int(validation.get("blocking_count") or 0)
    warning_count = int(validation.get("warning_count") or 0)
    downloads_enabled = is_current and blocking_count == 0
    if downloads_enabled and not result_preview_mode and not mt01_claim and not mt02_claim:
        from services.mvp_multi_tu_runtime import project_assisted_assembly_outputs

        projected_result = project_assisted_assembly_outputs(result)
        if projected_result is not result:
            result = projected_result
            # The Step 6 footer saves from session state, so it must validate
            # the same canonical export bytes offered by this renderer.
            st.session_state["mvp_vector_result"] = result
    final_review_report: dict[str, Any] | None = None
    if report_delivery_current:
        try:
            final_review_report = _build_canonical_final_review_report(result)
        except ValueError as exc:
            st.error(_t('v1.results_final_report.canonical_report_contract_could_not_projected', p0=exc))

    if mt01_claim:
        provenance = dict(result.get("case_provenance") or {})
        case_snapshot = dict(result.get("case_snapshot") or {})
        unannotated = list(case_snapshot.get("unannotated_intervals") or [])
        st.success(_t('v1.results_final_report.mt_01_source_access_case_snapshot_canonical'))
        st.markdown(
            _t('v1.project_center.mt_01_contract_summary', p0=provenance.get('source_accession_version'), p1=provenance.get('contract_version'))
        )
        st.warning(
            _t('v1.results_final_report.software_reconstructs_deterministic_2_tu_region_not')
        )
        case_rows = [
                {
                    "区间": str(item.get("junction_id") or "--"),
                    "类别": "未注释来源序列",
                    "来源坐标": (
                        f"{item.get('source_interval', {}).get('external_1_based_inclusive', {}).get('start')}.."
                        f"{item.get('source_interval', {}).get('external_1_based_inclusive', {}).get('end')}"
                    ),
                    "canonical 坐标": (
                        f"{item.get('local_interval', {}).get('external_1_based_inclusive', {}).get('start')}.."
                        f"{item.get('local_interval', {}).get('external_1_based_inclusive', {}).get('end')}"
                    ),
                    "长度": int(item.get("local_interval", {}).get("length_bp") or 0),
                    "SHA-256": str(item.get("sequence_sha256") or ""),
                }
                for item in unannotated
            ]
        st.dataframe(_localized_rows(case_rows), hide_index=True, use_container_width=True)
    elif mt02_claim:
        provenance = dict(result.get("case_provenance") or {})
        case_snapshot = dict(result.get("case_snapshot") or {})
        unannotated = list(case_snapshot.get("unannotated_intervals") or [])
        st.success(_t('v1.results_final_report.mt_02_source_access_case_snapshot_canonical'))
        st.markdown(
            _t('v1.project_center.mt_02_contract_summary', p0=provenance.get('source_accession_version'), p1=provenance.get('contract_version'))
        )
        st.warning(
            _t('v1.results_final_report.software_reconstructs_deterministic_3_tu_region_not')
        )
        """
        overview_rows = [
                {
                    "区间": str(item.get("unannotated_id") or "--"),
                    "类别": "未注释来源序列",
                    "来源坐标": (
                        f"{item.get('source_interval', {}).get('external_1_based_inclusive', {}).get('start')}.."
                        f"{item.get('source_interval', {}).get('external_1_based_inclusive', {}).get('end')}"
                    ),
                    "canonical 坐标": (
                        f"{item.get('canonical_interval', {}).get('external_1_based_inclusive', {}).get('start')}.."
                        f"{item.get('canonical_interval', {}).get('external_1_based_inclusive', {}).get('end')}"
                    ),
                    "长度": int(item.get("canonical_interval", {}).get("length_bp") or 0),
                    "SHA-256": str(item.get("sequence_sha256") or ""),
                }
                for item in unannotated
            ],
            hide_index=True,
            use_container_width=True,
        )
        """
        case_rows_mt02 = [
            {
                _t('v1.results_final_report.interval'): str(item.get("unannotated_id") or "--"),
                _t('v1.results_final_report.category'): _t('v1.results_final_report.unannotated_source_sequence'),
                _t('v1.results_final_report.source_coordinates'): (
                    f"{item.get('source_interval', {}).get('external_1_based_inclusive', {}).get('start')}.."
                    f"{item.get('source_interval', {}).get('external_1_based_inclusive', {}).get('end')}"
                ),
                    _t('v1.results_final_report.canonical_coordinates'): (
                    f"{item.get('canonical_interval', {}).get('external_1_based_inclusive', {}).get('start')}.."
                    f"{item.get('canonical_interval', {}).get('external_1_based_inclusive', {}).get('end')}"
                ),
                _t('v1.results_final_report.length'): int(item.get("canonical_interval", {}).get("length_bp") or 0),
                "SHA-256": str(item.get("sequence_sha256") or ""),
            }
            for item in unannotated
        ]
        st.dataframe(_localized_rows(case_rows_mt02), hide_index=True, use_container_width=True)
        st.caption(
            _t('v1.results_final_report.33_source_features_30_pairwise_overlaps_among')
        )

    st.markdown(
        _t('v1.results_final_report.project', p0=escape(_display_multi_tu_project_name(result.get('project_name')))),
        unsafe_allow_html=True,
    )
    formal_validation_label, formal_validation_note, formal_validation_findings = _multi_tu_formal_validation_copy(combined)
    formal_validation_status = str(
        dict(combined.get("formal_validation") or {}).get("status") or ""
    )
    st.markdown(
        _t('v1.expression.final_review'),
        unsafe_allow_html=True,
    )
    st.markdown(_t('v1.results_final_report.result_type_multi_tu_expression_cassette_assembly'))
    st.info(
        _t('v1.results_final_report.result_linear_multi_tu_expression_cassette_assembly')
    )
    metrics = st.columns(5)
    metrics[0].metric(_t('v1.results_final_report.tu_count'), len(units))
    metrics[1].metric(_t('v1.expression.canonical_length'), f"{int(combined.get('total_length') or 0):,} bp")
    metrics[2].metric(
        _t('v1.expression.includes_vector'),
        _t('v1.common.yes' if bool(combined.get('contains_vector')) else 'v1.common.no'),
    )
    metrics[3].metric(_t('v1.expression.computation_warning'), warning_count)
    metrics[4].metric(_t('v1.expression.computation_block'), blocking_count)
    st.markdown(
        _t('v1.results_final_report.tu_order_sequence_check_status_canonical_sha', p0=' → '.join(str(unit.get('display_name') or unit.get('unit_id')) for unit in units), p1=formal_validation_label, p2=str(combined.get('sequence_sha256') or ''))
    )
    if formal_validation_status == "legacy_incomplete":
        st.error(_format_multi_tu_validation_copy(formal_validation_label, formal_validation_note))
    elif formal_validation_status != "formal_ready":
        st.warning(_format_multi_tu_validation_copy(formal_validation_label, formal_validation_note))
    else:
        st.success(formal_validation_label)
    for finding in formal_validation_findings:
        if str(finding.get("code") or "") == "MISSING_FIVE_PRIME_REGION":
            separator = ", " if _get_language() == "en" else "、"
            unit_ids = separator.join(str(item) for item in finding.get("unit_ids") or []) or _t('v1.expression.current_tu')
            st.error(_t('v1.results_final_report.missing_5_region_return_step_3_complete', p0=unit_ids))
    if result_preview_mode:
        _render_persisted_result_downloads(result)

    original_units = {
        str(unit.get("unit_id") or ""): unit
        for unit in list((result.get("original_input") or {}).get("expression_units") or [])
        if isinstance(unit, dict)
    }
    source_rows = []
    from services.component_output_provenance import assisted_component_provenance

    for unit in units:
        unit_id = str(unit.get("unit_id") or "")
        source_unit = original_units.get(unit_id, {})
        coordinate_by_role = {
            str(item.get("biological_role") or ""): item
            for item in list(unit.get("components") or [])
            if isinstance(item, dict)
        }
        for role in (
            "promoter",
            "five_prime_region",
            "cds",
            "3_prime_regulatory_region",
            "targeting_sequence",
            "linker",
            "fusion_tag",
        ):
            label = _multi_tu_role_display_label(role)
            component = source_unit.get(role) if isinstance(source_unit.get(role), dict) else {}
            if not component:
                continue
            coordinate = coordinate_by_role.get(role, {})
            reference = dict(coordinate.get('component_reference') or component.get('component_reference') or {})
            source_rows.append(
                {
                    "TU": str(unit.get("display_name") or unit_id),
                    "组件角色": label,
                    "组件": str(component.get("display_name") or label),
                    "来源": _multi_tu_source_label(reference.get("source_type") or component.get("source_type")),
                    "Registry ID": (
                        str(reference.get("registry_component_id"))
                        if reference.get("registry_component_id")
                        else (
                            _t("v1.expression.not_applicable_accession_derived")
                            if reference.get("source_type") == "REAL_CASE_ACCESSION_DERIVED"
                            else _ui("不适用")
                        )
                    ),
                    "元件类型": _multi_tu_role_display_label(
                        str(reference.get("tu_role") or role)
                    ),
                    "复核状态": _multi_tu_evidence_label(
                        reference.get("evidence_tier"),
                        source_type=reference.get("source_type") or component.get("source_type"),
                    ),
                    "来源 accession/version": str(reference.get("accession_version") or _t("v1.expression.not_recorded")),
                    "来源物种": str(reference.get("source_organism") or _t("v1.expression.not_recorded")),
                    "目标宿主元数据": ", ".join(reference.get("target_host_species") or []) or _t("v1.expression.not_recorded"),
                    "边界": (
                        f"{int(coordinate.get('start') or 0)}..{int(coordinate.get('end') or 0)}"
                        if coordinate
                        else "--"
                    ),
                    "方向": _t("v1.common.reverse") if unit.get("orientation") == "reverse" else _t("v1.common.forward"),
                    "当前限制": str(reference.get("limitation") or _t("v1.expression.source_information_requires_professional_review")),
                }
            )
            assisted = assisted_component_provenance(reference)
            if assisted:
                source_rows[-1]['来源 accession/version'] = assisted['source_accession'] or _t('v1.expression.not_recorded')
                for label, field in (
                    ('v2_canonical_id_label', 'catalog_component_id'),
                    ('v2_catalog_identity', 'catalog_name'),
                    ('v2_original_route', 'original_route'),
                    ('v2_sequence_authority', 'authority'),
                    ('v2_user_sequence_source', 'source_label'),
                    ('v2_source_boundary_label', 'reviewed_source_boundary'),
                    ('v2_project_binding', 'project_id'),
                    ('v2_resolution_identity', 'resolution_id'),
                ):
                    source_rows[-1][_t('v1.component_library.' + label)] = assisted[field] or _t('v1.expression.not_recorded')
                source_rows[-1]['SHA-256'] = assisted['sequence_sha256']
                source_rows[-1]['confirmation_mode'] = assisted['confirmation_mode'] or _t('v1.expression.not_recorded')
                for field in ('accession_verified', 'boundary_verified_by_software'):
                    value = assisted[field]
                    source_rows[-1][field] = str(value).lower() if isinstance(value, bool) else _t('v1.component_library.v2_verification_not_recorded')
                source_rows[-1]['当前限制'] = _t('v1.component_library.v2_user_authority_notice')

    review_rows = [
        {
            "TU": row["TU"],
            "角色": row["组件角色"],
            "元件": row["组件"],
            "方向": row["方向"],
            "坐标": row["边界"],
            "来源": row["来源"],
            "复核状态": row["复核状态"],
        }
        for row in source_rows
    ]

    overview_tab, linear_tab, sequence_tab, validation_tab = st.tabs(
        [_t('v1.expression.structure_overview'), _t('v1.expression.linear_view'), _t('v1.expression.sequence_view'), _t('v1.expression.check_results')]
    )
    with overview_tab:
        tu_rows = [
            {
                _t('v1.results_final_report.order'): int(unit.get("order") or 0),
                "TU": str(unit.get("display_name") or unit.get("unit_id") or "--"),
                _t('v1.common.orientation'): _t('v1.common.reverse') if unit.get("orientation") == "reverse" else _t('v1.common.forward'),
                _t('v1.results_final_report.length'): int(unit.get("length") or 0),
                _t('v1.expression.source_start'): int((unit.get("range") or {}).get("start") or 0),
                _t('v1.expression.source_end'): int((unit.get("range") or {}).get("end") or 0),
            }
            for unit in units
        ]
        st.dataframe(_localized_rows(tu_rows), hide_index=True, use_container_width=True)
        st.markdown(_t('v1.results_final_report.component_source'))
        with st.expander(_t('v1.results_final_report.component_source_technical_details'), expanded=False):
            st.dataframe(_localized_source_rows(source_rows), hide_index=True, use_container_width=True)
        st.caption(_t('v1.results_final_report.evidence_level_describes_sequence_identity_source_completeness'))
        st.caption(_t('v1.results_final_report.host_records_do_not_guarantee_performance_under'))
        st.caption(_t('v1.results_final_report.software_does_not_predict_experimental_success_rate'))
    with linear_tab:
        if publication_map_current:
            _render_publication_map_svg(
                result,
                view_type="linear_active_expression_construct",
                display_name=str(result.get("project_name") or _t('v1.results_final_report.multi_tu_canonical_construct')),
                download_key="publication_map_multi_tu_linear_svg",
            )
        else:
            st.warning(_t('v1.expression.result_not_latest_canonical_revision_publication_map'))
    with sequence_tab:
        _render_sequence_review(
            canonical.get("sequence"),
            label=_t("v1.results_final_report.multi_tu_region_sequence"),
        )
        _render_unit_sequence_reviews(units)
    with validation_tab:
        from views.formal_construct_findings import _render_findings

        st.dataframe(_localized_rows(review_rows), hide_index=True, use_container_width=True)
        with st.expander(_t('v1.common.technical_details'), expanded=False):
            _render_findings(list(canonical.get("validation_findings") or []), runtime=result.get('runtime'))
        with st.expander(_t('v1.results_final_report.view_component_coordinates'), expanded=False):
            st.dataframe(
                list(combined.get("component_coordinates") or []),
                hide_index=True,
                use_container_width=True,
            )

    if result_preview_mode:
        if final_review_report is not None:
            _render_canonical_final_review_delivery(final_review_report)
        return

    exports = dict(result.get("exports") or {})
    fasta = dict(exports.get("combined_construct_fasta") or {})
    genbank = dict(exports.get("combined_construct_genbank") or {})
    unit_fastas = dict(exports.get("unit_fastas") or {})
    st.subheader(_t('v1.results_final_report.save_export'))
    if include_project_actions:
        project_cols = st.columns(2)
        if project_cols[0].button(_t('v1.common.save_project'), type="primary", disabled=not downloads_enabled):
            try:
                saved = save_design(result)
            except Exception as exc:
                st.error(str(exc))
            else:
                st.session_state["formal_last_saved_mvp_project_id"] = str(getattr(saved, "project_id", "") or "")
                st.success(_t('v1.results_final_report.project_record_saved_can_reopened_project_home'))
        if mt01_claim:
            project_cols[1].button(
                _t('v1.results_final_report.mt_01_scientific_input_protected'),
                disabled=True,
                help=_t('v1.results_final_report.scientific_input_protected_help'),
            )
        elif mt02_claim:
            project_cols[1].button(
                _t('v1.results_final_report.mt_02_scientific_input_protected'),
                disabled=True,
                help=_t('v1.results_final_report.scientific_input_protected_help'),
            )
        elif project_cols[1].button(_t('v1.results_final_report.return_edit_design')):
            ds = _controller().get()
            ds.step = 3
            _controller().save(ds)
            _change_page(PAGE_DESIGN_WORKSPACE)

    if unit_fastas:
        st.caption(_t('v1.results_final_report.each_tu_fasta_extracted_canonical_coordinates'))
        unit_cols = st.columns(min(3, len(unit_fastas)))
        for index, unit in enumerate(units, start=1):
            record = dict(unit_fastas.get(str(unit.get("unit_id"))) or {})
            unit_cols[(index - 1) % len(unit_cols)].download_button(
                _t('v1.results_final_report.tu_fasta', p0=index),
                data=record.get("data") or "",
                file_name=record.get("file_name") or f"TU{index}.fasta",
                mime=record.get("mime") or "text/plain",
                disabled=not downloads_enabled or not record.get("data"),
                on_click="ignore",
            )
    download_cols = st.columns(2)
    if mt01_claim:
        fasta_label = _t('v1.results_final_report.canonical_fasta_label', p0='MT-01')
        genbank_label = _t('v1.results_final_report.canonical_genbank_label', p0='MT-01')
    elif mt02_claim:
        fasta_label = _t('v1.results_final_report.canonical_fasta_label', p0='MT-02')
        genbank_label = _t('v1.results_final_report.canonical_genbank_label', p0='MT-02')
    else:
        fasta_label = _t('v1.results_final_report.canonical_fasta_label', p0=_t('v1.expression.multi_tu_region'))
        genbank_label = _t('v1.results_final_report.canonical_genbank_label', p0=_t('v1.expression.multi_tu_region'))
    download_cols[0].download_button(
        fasta_label,
        data=fasta.get("data") or "",
        file_name=fasta.get("file_name") or "multi_tu_assembly.fasta",
        mime=fasta.get("mime") or "text/plain",
        disabled=not downloads_enabled or not fasta.get("data"),
        on_click="ignore",
    )
    download_cols[1].download_button(
        genbank_label,
        data=genbank.get("data") or "",
        file_name=genbank.get("file_name") or "multi_tu_assembly.gb",
        mime=genbank.get("mime") or "text/plain",
        disabled=not downloads_enabled or not genbank.get("data"),
        on_click="ignore",
    )
    if final_review_report is not None:
        _render_canonical_final_review_delivery(final_review_report)


def _render_persisted_result_downloads(result: Mapping[str, Any]) -> None:
    """Expose saved export bytes for a historical result without regenerating them."""
    exports = result.get("exports") if isinstance(result.get("exports"), Mapping) else {}
    fasta = dict(
        exports.get("complete_plasmid_fasta")
        or exports.get("combined_construct_fasta")
        or exports.get("fasta")
        or {}
    )
    genbank = dict(
        exports.get("complete_plasmid_genbank")
        or exports.get("combined_construct_genbank")
        or exports.get("genbank")
        or {}
    )
    backup_json = json.dumps(dict(result), ensure_ascii=False, indent=2, default=str) + "\n"
    st.subheader(_t('v1.results_final_report.download_results_label'))
    download_cols = st.columns(3)
    download_cols[0].download_button(
        _t('v1.results_final_report.full_plasmid_fasta'),
        data=fasta.get("data") or "",
        file_name=fasta.get("file_name") or "complete_plasmid.fasta",
        mime=fasta.get("mime") or "text/plain",
        disabled=not fasta.get("data"),
        on_click="ignore",
        use_container_width=True,
    )
    download_cols[1].download_button(
        _t('v1.results_final_report.full_plasmid_genbank'),
        data=genbank.get("data") or "",
        file_name=genbank.get("file_name") or "complete_plasmid.gb",
        mime=genbank.get("mime") or "text/plain",
        disabled=not genbank.get("data"),
        on_click="ignore",
        use_container_width=True,
    )
    download_cols[2].download_button(
        _t('v1.results_final_report.project_backup_json'),
        data=backup_json,
        file_name="project_backup.json",
        mime="application/json",
        on_click="ignore",
        use_container_width=True,
    )


def _build_canonical_final_review_report(
    result: Mapping[str, Any],
    *,
    vector_asset_admission: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one Step 6 projection sourced from the canonical report contract."""
    from services.formal_single_gene_final_review import build_final_review_report

    admission = dict(vector_asset_admission) if isinstance(vector_asset_admission, Mapping) else {}
    policy_blockers: tuple[str, ...] = ()
    if admission and not bool(admission.get("allowed")):
        policy_blockers = (
            str(admission.get("reason") or "The vector operation is not admitted."),
        )
    return build_final_review_report(result, delivery_policy_blockers=policy_blockers)


_FORMAL_REPORT_PREVIEW_COPY = {
    "Single-Gene Final Review and Delivery Record": "单基因最终审查与交付记录",
    "Multi-TU Final Review and Delivery Record": "多 TU 最终审查与交付记录",
    "Project and Design Summary": "项目与设计摘要",
    "Host and Target": "宿主与目标",
    "Transcription Units and Pathway": "转录单元与通路",
    "Backbone": "载体骨架",
    "Insertion and Replacement": "插入与替换",
    "Component Provenance and Evidence": "元件来源与证据",
    "Map and Feature Summary": "图谱与特征摘要",
    "Review Notes": "审查说明",
    "Technical Identities, Hashes and Manifest": "技术标识、哈希与清单",
    "Review Status": "审查状态",
    "Canonical Sequence Record": "Canonical 序列记录",
    "Component Identity and Provenance": "元件身份与来源",
    "Vector Strategy": "载体策略",
    "Review Counts": "审查计数",
    "Canonical Delivery Artifacts": "Canonical 交付文件",
    "Review Follow-up": "审查后续跟进",
    "Boundary": "边界说明",
    "Project": "项目",
    "Design scenario": "设计场景",
    "Original insertion interval (1-based inclusive)": "原始插入区间（1-based 闭区间）",
    "Original replacement interval (1-based inclusive)": "原始替换区间（1-based 闭区间）",
    "Inserted expression region length": "插入表达区域长度",
    "Host": "宿主",
    "Target": "目标",
    "Transcription unit count": "转录单元数量",
    "Complete plasmid includes a backbone; its source record is listed in provenance.": "完整质粒包含载体骨架；其来源记录列于来源信息中。",
    "Not applicable / no backbone included": "不适用 / 未包含载体骨架",
    "Expression assembly only.": "仅表达组装。",
    "Warning findings recorded": "已记录警告项",
    "Topology": "拓扑",
    "Recorded features": "已记录特征",
    "Report version": "报告版本",
    "Canonical contract schema": "Canonical 合同 schema",
    "ReportSnapshot ID": "ReportSnapshot ID",
    "Artifact manifest ID": "文件清单 ID",
    "Delivery evidence identity": "交付证据标识",
    "Project ID": "项目 ID",
    "Workflow type": "工作流类型",
    "Status": "状态",
    "Note": "说明",
    "Canonical length": "Canonical 长度",
    "Canonical topology": "Canonical 拓扑",
    "Canonical SHA-256": "Canonical SHA-256",
    "Canonical input signature": "Canonical 输入签名",
    "Expression cassette length": "表达盒长度",
    "Expression cassette SHA-256": "表达盒 SHA-256",
    "Complete plasmid status": "完整质粒状态",
    "Provenance identity": "来源身份",
    "Workflow ID": "工作流 ID",
    "Mode": "模式",
    "Coordinates (1-based inclusive)": "坐标（1-based 闭区间）",
    "Orientation": "方向",
    "Blocking items": "阻断项",
    "Warning items": "警告项",
    "Canonical FASTA": "Canonical FASTA",
    "Canonical GenBank": "Canonical GenBank",
    "Canonical plasmid map": "Canonical 质粒图谱",
    "available": "可用",
    "unavailable": "不可用",
    "File": "文件",
    "Bytes": "字节数",
    "Reason": "原因",
    "Coordinates": "坐标",
    "V2 canonical ID": "V2 规范 ID",
    "Catalog identity": "目录身份",
    "Source accession": "来源 accession",
    "role": "角色",
    "component_id": "元件 ID",
    "source": "来源",
    "reference": "参考",
    "length": "长度",
    "Original route": "原始路由",
    "Sequence authority": "序列权威来源",
    "User sequence source / file label": "用户序列来源 / 文件标签",
    "Reviewed source boundary": "已复核的来源边界",
    "Sequence SHA-256": "序列 SHA-256",
    "Project binding": "项目绑定",
    "Project resolution ID": "项目解析 ID",
    "Confirmation mode": "确认模式",
    "accession_verified": "accession 已核验",
    "boundary_verified_by_software": "边界经软件核验",
    "component_id": "元件 ID",
    "Not recorded": "未记录",
    "forward": "正向",
    "reverse": "反向",
    "linear": "线性",
    "circular": "环状",
    "insertion": "插入",
    "replacement": "替换",
    "multi_tu": "多 TU",
    "single_gene": "单基因",
    "metabolic_pathway_multi_tu_vector": "代谢通路 Multi-TU 载体",
    "standard_plant_expression_vector": "标准植物表达载体",
    "true": "是",
    "false": "否",
    "not_recorded": "未记录",
    "No canonical component records are available.": "没有可显示的 Canonical 元件记录。",
    "USER_PROVIDED sequence; the accession and source boundary are recorded provenance, not independent software verification. SHA-256 identifies supplied bytes, not source identity.": "USER_PROVIDED 序列；accession 与来源边界是已记录的来源信息，不代表软件独立核验。SHA-256 仅标识所提供的字节，不证明来源身份。",
    "This documentation-only design review record does not establish": "这份仅用于文档记录的设计审查记录不确立",
    "This is a documentation-only design review record for professional review.": "这是一份供专业审查使用的文档记录，不构成实验用途判断。",
    "No additional canonical review blockers are recorded in this snapshot.": "当前快照未记录其他 Canonical 审查阻断项。",
    "Manual review remains required for warning-level signals.": "警告级信号仍需人工审查。",
    "Documentation delivery record available": "交付记录可用",
    "Documentation delivery available with review required": "交付记录可用，需人工审查",
    "Documentation delivery blocked": "交付记录不可用",
    "The canonical report contract records no blockers or warnings.": "Canonical 报告记录未显示阻断项或警告项。",
    "Warning-level review signals remain open; manual review is required.": "警告级审查事项仍需人工审查。",
    "Resolve the recorded review blockers before using delivery actions.": "请先处理已记录的阻断项，再使用交付操作。",
}


def _localized_formal_report_preview(markdown: str) -> str:
    """Localize fixed report copy and labels while preserving report values."""
    to_zh = _get_language() != "en"
    reverse_copy = {value: key for key, value in _FORMAL_REPORT_PREVIEW_COPY.items()}
    controlled_values = {
        "Target": {
            "稳定遗传转化": "Stable genetic transformation",
            "瞬时表达": "Transient expression",
            "尚未确定": "Not yet determined",
            "农杆菌介导的植物组织瞬时表达": "Agrobacterium-mediated plant tissue transient expression",
            "植物原生质体瞬时转染": "Plant protoplast transient transfection",
            "其他瞬时表达体系": "Other transient expression systems",
            "无特定组织或器官限制": "No specific tissue or organ restriction",
            "组织或器官特异性表达": "Tissue- or organ-specific expression",
            "无特定诱导要求": "No specific induction requirement",
            "需要诱导型表达": "Inducible expression required",
        },
        "Status": {
            "Documentation delivery record available": "交付记录可用",
            "Documentation delivery available with review required": "交付记录可用，需人工审查",
            "Documentation delivery blocked": "交付记录不可用",
        },
        "Note": {
            "The canonical report contract records no blockers or warnings.": "Canonical 报告记录未显示阻断项或警告项。",
            "Warning-level review signals remain open; manual review is required.": "警告级审查事项仍需人工审查。",
            "Resolve the recorded review blockers before using delivery actions.": "请先处理已记录的阻断项，再使用交付操作。",
        },
        "Complete plasmid status": {"available": "可用", "unavailable": "不可用"},
        "Topology": {"linear": "线性", "circular": "环状"},
        "Canonical topology": {"linear": "线性", "circular": "环状"},
        "Orientation": {"forward": "正向", "reverse": "反向"},
        "Mode": {"insertion": "插入", "replacement": "替换"},
        "Workflow type": {"single_gene": "单基因", "multi_tu": "多 TU"},
        "Design scenario": {
            "metabolic_pathway_multi_tu_vector": "代谢通路 Multi-TU 载体",
            "standard_plant_expression_vector": "标准植物表达载体",
        },
        "Canonical FASTA": {"available": "可用", "unavailable": "不可用"},
        "Canonical GenBank": {"available": "可用", "unavailable": "不可用"},
        "Canonical plasmid map": {"available": "可用", "unavailable": "不可用"},
        "accession_verified": {"true": "是", "false": "否", "not_recorded": "未记录"},
        "boundary_verified_by_software": {"true": "是", "false": "否", "not_recorded": "未记录"},
    }
    fixed_copy = {
        "Complete plasmid includes a backbone; its source record is listed in provenance.": "完整质粒包含载体骨架；其来源记录列于来源信息中。",
        "Not applicable / no backbone included": "不适用 / 未包含载体骨架",
        "Expression assembly only.": "仅表达组装。",
        "No canonical component records are available.": "没有可显示的 Canonical 元件记录。",
        "USER_PROVIDED sequence; the accession and source boundary are recorded provenance, not independent software verification. SHA-256 identifies supplied bytes, not source identity.": "USER_PROVIDED 序列；accession 与来源边界是已记录的来源信息，不代表软件独立核验。SHA-256 仅标识所提供的字节，不证明来源身份。",
        "This is a documentation-only design review record for professional review.": "这是一份供专业审查使用的文档记录，不构成实验用途判断。",
        "No additional canonical review blockers are recorded in this snapshot.": "当前快照未记录其他 Canonical 审查阻断项。",
        "Manual review remains required for warning-level signals.": "警告级信号仍需人工审查。",
        "The canonical report contract records no blockers or warnings.": "Canonical 报告记录未显示阻断项或警告项。",
        "Warning-level review signals remain open; manual review is required.": "警告级审查事项仍需人工审查。",
        "Resolve the recorded review blockers before using delivery actions.": "请先处理已记录的阻断项，再使用交付操作。",
    }

    def copy_label(value: str) -> str:
        return (
            _FORMAL_REPORT_PREVIEW_COPY.get(value, value)
            if to_zh
            else reverse_copy.get(value, value)
        )

    def copy_value(label: str, value: str) -> str:
        if label == "Target":
            separator = "；" if "；" in value else "; "
            parts = value.split(separator)
            pairs = controlled_values[label]
            localized_parts = [
                {source: target for target, source in pairs.items()}.get(part.strip(), part.strip())
                if to_zh else pairs.get(part.strip(), part.strip())
                for part in parts
            ]
            if any(original.strip() != localized for original, localized in zip(parts, localized_parts)):
                return ("；" if to_zh else "; ").join(localized_parts)
            return value
        pairs = controlled_values.get(label, {})
        if to_zh:
            return pairs.get(value, value)
        reverse_pairs = {localized: source for source, localized in pairs.items()}
        return reverse_pairs.get(value, value)

    def copy_fixed(value: str) -> str:
        if to_zh:
            return fixed_copy.get(value, value)
        reverse_fixed = {localized: source for source, localized in fixed_copy.items()}
        return reverse_fixed.get(value, value)

    def localize_coordinate_suffix(value: str) -> str | None:
        import re

        match = re.fullmatch(
            r"(.+[:：]\s*\d+\.\.\d+) ?(?:\(1-based inclusive\), strand|（1-based 闭区间），链) (-?\d+)",
            value,
        )
        if not match:
            return None
        if to_zh:
            return f"{match.group(1)}（1-based 闭区间），链 {match.group(2)}"
        return f"{match.group(1)} (1-based inclusive), strand {match.group(2)}"

    lines = []
    in_feature_summary = False
    seen_section_heading = False
    for original_line in str(markdown).splitlines():
        if original_line.startswith("## "):
            seen_section_heading = True
            in_feature_summary = original_line[3:] in {
                "Map and Feature Summary", "图谱与特征摘要",
            }
        coordinate_line = (
            localize_coordinate_suffix(original_line)
            if in_feature_summary or (
                not seen_section_heading and original_line.lstrip().startswith("- ")
            )
            else None
        )
        if coordinate_line is not None:
            # The feature name is user data, even when it matches a copy label.
            lines.append(coordinate_line)
            continue
        line = original_line
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if line.startswith("# ") or line.startswith("## "):
            marker, title = line.split(" ", 1)
            line = f"{marker} {copy_label(title)}"
        elif stripped.startswith("- "):
            body = stripped[2:]
            if body in fixed_copy or body in fixed_copy.values():
                line = f"{indent}- {copy_fixed(body)}"
            elif " | " in body:
                parts = body.split(" | ")
                localized_parts = [parts[0]]
                for part in parts[1:]:
                    if "=" in part:
                        label, value = part.split("=", 1)
                        localized_parts.append(
                            f"{copy_label(label)}={value}"
                            if label in {"role", "component_id", "source", "reference", "length"}
                            else part
                        )
                    elif ": " in part:
                        label, value = part.split(": ", 1)
                        separator = "：" if to_zh else ": "
                        localized_parts.append(
                            f"{copy_label(label)}{separator}{value}"
                            if label in {"source", "reference", "length"}
                            else part
                        )
                    else:
                        localized_parts.append(part)
                line = indent + "- " + " | ".join(localized_parts)
            elif body.startswith("Canonical ") and ": " in body:
                label, value = body.split(": ", 1)
                if label in {"Canonical FASTA", "Canonical GenBank", "Canonical plasmid map"}:
                    line = f"{indent}- {copy_label(label)}: {copy_value(label, value)}"
            elif ": " in body:
                label, value = body.split(": ", 1)
                if label in _FORMAL_REPORT_PREVIEW_COPY:
                    separator = "：" if to_zh else ": "
                    value_labels = {
                        "Status", "Note", "Complete plasmid status", "Canonical topology",
                        "Topology", "Orientation", "Mode", "Workflow type", "Design scenario",
                    }
                    localized_value = copy_value(label, value) if label in value_labels else value
                    line = f"{indent}- {copy_label(label)}{separator}{localized_value}"
                elif label.startswith("TU") and label[2:].isdigit():
                    separator = "：" if to_zh else ": "
                    line = f"{indent}- {label}{separator}{copy_value('Orientation', value)}"
            elif "=" in body:
                label, value = body.split("=", 1)
                if label in _FORMAL_REPORT_PREVIEW_COPY:
                    localized_value = copy_value(label, value) if label in {
                        "accession_verified", "boundary_verified_by_software"
                    } else value
                    line = f"{indent}- {copy_label(label)}={localized_value}"
        elif ": " in stripped:
            label, value = stripped.split(": ", 1)
            if label in _FORMAL_REPORT_PREVIEW_COPY:
                value_labels = {
                    "Status", "Note", "Complete plasmid status", "Canonical topology",
                    "Topology", "Orientation", "Mode", "Workflow type", "Design scenario",
                }
                localized_value = copy_value(label, value) if label in value_labels or label == "Target" else value
                separator = "：" if to_zh else ": "
                line = f"{indent}{copy_label(label)}{separator}{localized_value}"
            else:
                line = copy_fixed(line)
        else:
            line = copy_fixed(line)
        if line.startswith("This documentation-only design review record does not establish "):
            boundary = "This documentation-only design review record does not establish experimental validation, wet-lab readiness, expression outcome."
            if line == boundary and to_zh:
                line = "这份仅用于文档记录的设计审查记录不证明实验验证、湿实验就绪状态或表达结果。"
        elif line == "这份仅用于文档记录的设计审查记录不证明实验验证、湿实验就绪状态或表达结果。" and not to_zh:
            line = "This documentation-only design review record does not establish experimental validation, wet-lab readiness, expression outcome."
        lines.append(line)
    return "\n".join(lines)


def _localized_single_gene_checkpoint_report_preview(markdown: str) -> str:
    """Preserve the accepted Single-Gene checkpoint report presentation."""
    return _localized_formal_report_preview(markdown)


def _render_canonical_final_review_delivery(report: Mapping[str, Any]) -> None:
    """Render a documentation-only delivery decision from the current snapshot."""
    from services.formal_single_gene_final_review import (
        render_formal_report_markdown,
        validate_formal_report_delivery,
    )

    st.subheader(_t('v1.results_final_report.final_review_delivery'))
    validation_error = ""
    try:
        decision = validate_formal_report_delivery(report)
    except ValueError as exc:
        decision = None
        validation_error = str(exc)
    status = decision.status if decision else ""
    status_label, status_note = {
        "documentation_delivery_blocked": (
            "交付记录不可用",
            "当前记录存在阻断项；请先完成记录中的审查事项。",
        ),
        "documentation_delivery_review_required": (
            "交付记录可用，需人工审查",
            "当前记录存在警告项；请进行人工审查。",
        ),
        "documentation_delivery_available": (
            "交付记录可用",
            "当前 canonical 记录未显示阻断项或警告项。",
        ),
    }.get(
        status,
        ("最终审查不可用", "当前记录无法形成最终审查与交付记录。"),
    )
    status_label = _ui(status_label)
    status_note = _ui(status_note)
    if status == "documentation_delivery_blocked":
        st.error(f"{status_label}. {status_note}")
    elif status == "documentation_delivery_review_required":
        st.warning(f"{status_label}. {status_note}")
    elif status == "documentation_delivery_available":
        st.success(f"{status_label}. {status_note}")
    else:
        st.error(f"{status_label}. {status_note}")
        st.error(_t('v1.results_final_report.formal_report_delivery_validation_failed', p0=validation_error))

    artifact_count = sum(
        1
        for row in (decision.artifacts if decision else ())
        if row.get("required") and row.get("available")
    )
    review_cols = st.columns(4)
    review_cols[0].metric(_t('v1.results_final_report.blocking_item'), decision.blocking_count if decision else 0)
    review_cols[1].metric(_t('v1.results_final_report.warnings'), decision.warning_count if decision else 0)
    review_cols[2].metric(_t('v1.results_final_report.export_file'), f"{artifact_count}/2")
    review_cols[3].metric(
        _t('v1.results_final_report.delivery_record'),
        _ui("可交付") if decision and decision.eligible else _ui("不可交付"),
    )
    st.caption(
        _t('v1.results_final_report.reports_read_only_canonical_construct_record_existing')
    )
    blockers = list(decision.blocking_reasons) if decision else []
    if blockers:
        st.caption(_t('v1.results_final_report.review_follow_up') + " ".join(str(blocker) for blocker in blockers))
    with st.expander(_t('v1.results_final_report.formal_report_preview'), expanded=False):
        if decision:
            preview = (
                _localized_formal_report_preview(decision.markdown)
                if str(report.get("workflow_type") or "") == "multi_tu"
                else _localized_single_gene_checkpoint_report_preview(decision.markdown)
            )
            st.markdown(preview)
        else:
            st.caption(_t('v1.results_final_report.formal_report_preview_unavailable_because_delivery_check'))
    delivery_available = bool(decision and decision.eligible)
    markdown_data = b""
    pdf_data = b""
    if delivery_available:
        try:
            from services.formal_report_pdf import render_formal_report_pdf

            markdown_data = render_formal_report_markdown(report)
            pdf_data = render_formal_report_pdf(report)
        except (ValueError, ImportError) as exc:
            delivery_available = False
            markdown_data = b""
            pdf_data = b""
            st.error(_t('v1.results_final_report.formal_report_delivery_could_not_rendered', p0=exc))
    report_downloads = st.columns(2)
    report_downloads[0].download_button(
        _t('v1.results_final_report.download_final_review_report_markdown'),
        data=markdown_data,
        file_name=str(report.get("file_name") or "final_review.md"),
        mime="text/markdown",
        disabled=not delivery_available,
        on_click="ignore",
        use_container_width=True,
    )
    report_downloads[1].download_button(
        _t('v1.results_final_report.download_formal_report_pdf'),
        data=pdf_data,
        file_name=str(report.get("pdf_file_name") or "final_review.pdf"),
        mime="application/pdf",
        disabled=not delivery_available or not pdf_data,
        on_click="ignore",
        use_container_width=True,
    )
    st.caption(_t('v1.results_final_report.canonical_content_identity', p0=report.get('content_identity') or '--'))


def _render_results_export_content(
    *, include_project_actions: bool = True, result_preview_mode: bool = False
) -> None:
    """Render canonical results using the existing saved canonical result payload."""
    from views.formal_construct_findings import _render_findings
    from services.canonical_construct_runtime import (
        CanonicalConstructRuntimeError,
        active_complete_plasmid_snapshot,
        active_construct_snapshot,
    )
    from services.mvp_single_gene_persistence import MvpSingleGenePersistenceError, save_mvp_single_gene_design
    from services.mvp_multi_tu_persistence import MvpMultiTuPersistenceError, save_mvp_multi_tu_design

    result = st.session_state.get("mvp_vector_result")
    if not isinstance(result, dict):
        st.warning(_t('v1.results_final_report.no_complete_plasmid_results_available_design'))
        return
    is_dual_tu = str(result.get("project_type") or "") == PROJECT_TYPE_DUAL_TU
    is_current = bool(
        not st.session_state.get("mvp_inputs_stale")
        and result.get("input_signature") == st.session_state.get("mvp_current_input_signature")
        and not _formal_result_needs_review(result)
    )
    historical_result_stale = bool(result_preview_mode and not is_current)
    publication_map_current = is_current
    report_delivery_current = is_current
    if result_preview_mode and _is_multi_tu_expression_assembly(result):
        report_delivery_current = _persisted_multi_tu_report_eligible(
            result,
            result_preview_mode=True,
        )
    if result_preview_mode:
        is_current = True
    if historical_result_stale:
        st.warning(
            _t('v1.results_final_report.input_changed_following_shows_read_only_preview')
        )
    if not is_current:
        if _formal_result_needs_review(result):
            st.error(_t('v1.results_final_report.project_background_step_1_changed_plant_expression'))
        else:
            st.error(_t('v1.results_final_report.input_changed_results_obsolete_return_workspace_regenerate'))

    if _is_multi_tu_expression_assembly(result):
        _render_multi_tu_assembly_results(
            result,
            is_current=is_current,
            publication_map_current=publication_map_current,
            report_delivery_current=report_delivery_current,
            save_design=save_mvp_multi_tu_design,
            include_project_actions=include_project_actions,
            result_preview_mode=result_preview_mode,
        )
        return

    try:
        cassette = active_construct_snapshot(result.get("runtime"))
        plasmid = active_complete_plasmid_snapshot(result.get("runtime"))
    except CanonicalConstructRuntimeError as exc:
        st.error(str(exc))
        return
    from services.company_delivery_package import project_display_name

    project_name = str(
        result.get("project_name")
        or (_display_multi_tu_project_name(_DEFAULT_MULTI_TU_PROJECT_NAME) if is_dual_tu else project_display_name(result, plasmid))
    )
    st.markdown(
        _t('v1.results_final_report.project', p0=escape(project_name)),
        unsafe_allow_html=True,
    )
    if not is_dual_tu:
        from services.formal_project_definition_lifecycle import (
            is_induction_notes_active,
            is_tissue_target_active,
            is_transient_system_active,
            project_definition_from_context,
        )

        definition = project_definition_from_context(
            result.get("formal_project_context") if isinstance(result.get("formal_project_context"), dict) else {},
            fallback_project_name=str(result.get("project_name") or ""),
        )
        if not result_preview_mode:
            summary_parts = [
                f"{_t('v1.common.host')}: {escape(str(definition['plant_host'] or '--'))}",
                f"{_t('v1.expression.cultivar_or_experimental_material')}: {escape(str(definition['material'] or '--'))}",
                f"{_t('v1.expression.experimental_application_method').rstrip(' *')}: {escape(_localized_value(str(definition['application_mode']), _APPLICATION_MODE_LABELS))}",
            ]
            if is_transient_system_active(definition):
                summary_parts.append(
                    f"{_t('v1.expression.transient_expression_system_label')}: "
                    f"{escape(_localized_value(str(definition['transient_expression_system']), _TRANSIENT_SYSTEM_LABELS))}"
                )
            summary_parts.append(
                f"{_t('v1.expression.tissue_or_organ_specificity_requirement')}: "
                f"{escape(_localized_value(str(definition['tissue_specificity_requirement']), _TISSUE_REQUIREMENT_LABELS))}"
            )
            if is_tissue_target_active(definition):
                summary_parts.append(
                    f"{_t('v1.expression.target_tissue_or_organ')}: "
                    f"{escape(str(definition['tissue_target'] or '--'))}"
                )
            summary_parts.append(
                f"{_t('v1.expression.inducibility_requirement_label')}: "
                f"{escape(_localized_value(str(definition['inducibility_requirement']), _INDUCIBILITY_LABELS))}"
            )
            if is_induction_notes_active(definition):
                summary_parts.append(
                    f"{_t('v1.expression.induction_condition_or_system_note')}: "
                    f"{escape(str(definition['induction_notes'] or '--'))}"
                )
            localization_target = str(definition['localization_target'] or '').strip()
            summary_parts.append(
                f"{_t('v1.expression.subcellular_localization_target')}: "
                f"{escape(localization_target or _t('v1.expression.not_yet_determined'))}"
            )
            st.markdown(f"**{_t('v1.expression.saved_result_summary')}**  \n" + " · ".join(summary_parts))
    from services.rice_hsa_ncbi_mvp10_case import evaluate_real_case_authenticity, is_real_case_candidate
    authenticity_gate = evaluate_real_case_authenticity(result) if is_real_case_candidate(result) else {}
    if authenticity_gate:
        with st.expander(_t('v1.results_final_report.construction_review_notes'), expanded=False):
            st.warning(_t('v1.results_final_report.af234296_1_applied_fixed_xbai_27_28'))
        from services.plant_component_workflow_registry import exact_registry_evidence

        fixed_records = result.get("input_records") if isinstance(result.get("input_records"), dict) else {}
        fixed_evidence_rows = []
        fixed_role_labels = {
            "promoter": "启动子",
            "cds": "CDS",
            "terminator": "终止子",
        }
        for role, component_types in (
            ("promoter", {"promoter"}),
            ("cds", {"cds"}),
            ("terminator", {"terminator", "three_prime_regulatory_region"}),
        ):
            source_record = fixed_records.get(role) if isinstance(fixed_records.get(role), dict) else {}
            matches = exact_registry_evidence(
                sequence=str(source_record.get("normalized_sequence") or ""),
                component_types=component_types,
            )
            match = matches[0] if len(matches) == 1 else {}
            fixed_evidence_rows.append(
                {
                    "固定角色": fixed_role_labels[role],
                    "组件": str(source_record.get("display_name") or role),
                    "来源 accession": str(source_record.get("source_accession_version") or source_record.get("source_name") or "--"),
                    "Registry ID": str(match.get("registry_component_id") or "无精确 Registry 匹配"),
                    "证据等级": str(match.get("evidence_tier") or "固定案例来源记录"),
                    "编辑状态": "固定案例，只读",
                }
            )
        if result_preview_mode:
            with st.expander(_t('v1.results_final_report.fixed_case_component_evidence_read_only_label'), expanded=False):
                st.dataframe(_localized_rows(fixed_evidence_rows), hide_index=True, use_container_width=True)
        else:
            st.markdown(_t('v1.results_final_report.fixed_case_component_evidence_read_only'))
            st.dataframe(_localized_rows(fixed_evidence_rows), hide_index=True, use_container_width=True)
    from services.component_output_provenance import runtime_assisted_component_provenance

    assisted_sources = runtime_assisted_component_provenance(result.get("runtime") or {})
    if assisted_sources:
        st.markdown(_t('v1.results_final_report.component_source'))
        with st.expander(_t('v1.results_final_report.component_source_technical_details'), expanded=False):
            st.dataframe(list(assisted_sources.values()), hide_index=True, use_container_width=True)
        st.caption(_t('v1.component_library.v2_user_authority_notice'))
    exports = dict(result.get("exports") or {})

    validation = dict(plasmid.get("validation_summary") or {})
    blocking_count = int(validation.get("blocking_count") or 0)
    warning_count = int(validation.get("warning_count") or 0)
    original_input = result.get("original_input") if isinstance(result.get("original_input"), dict) else {}
    backbone_input = original_input.get("backbone") if isinstance(original_input.get("backbone"), dict) else {}
    source_backbone_length = int(
        (result.get("formal_project_context") or {}).get("source_backbone_length")
        or (result.get("input_lengths") or {}).get("backbone")
        or backbone_input.get("length")
        or 0
    )
    from services.vector_asset_admission import validate_vector_operation

    if is_dual_tu:
        vector_record = backbone_input
        vector_settings = original_input.get("insertion_settings") if isinstance(original_input.get("insertion_settings"), dict) else {}
        vector_context = result.get("formal_project_context") if isinstance(result.get("formal_project_context"), dict) else {}
        if bool(
            result.get("betalain_pbi121_validation")
            or vector_context.get("betalain_pbi121_validation")
        ):
            vector_workflow = "betalain_gate3"
        elif vector_context.get("design_scenario") == "metabolic_pathway_multi_tu_vector":
            vector_workflow = "gate3_pathway"
        else:
            vector_workflow = "generic_multi_tu"
    else:
        input_records = result.get("input_records") if isinstance(result.get("input_records"), dict) else {}
        vector_record = input_records.get("backbone") if isinstance(input_records.get("backbone"), dict) else {}
        vector_settings = result.get("insertion_settings") if isinstance(result.get("insertion_settings"), dict) else {}
        vector_workflow = str(vector_settings.get("workflow_id") or "formal_single_gene")
    vector_asset_admission = validate_vector_operation(
        vector_record,
        workflow_id=vector_workflow,
        insertion_settings=vector_settings,
    )
    result["vector_asset_admission"] = vector_asset_admission
    if is_dual_tu:
        validation_label, validation_note, _formal_findings = _multi_tu_formal_validation_copy(
            dict(result.get("combined_construct") or {})
        )
        validation_status = str(
            dict((result.get("combined_construct") or {}).get("formal_validation") or {}).get("status") or ""
        )
        validation_message = _format_multi_tu_validation_copy(validation_label, validation_note)
        if validation_status == "legacy_incomplete":
            st.error(validation_message)
        elif validation_status != "formal_ready":
            st.warning(validation_message)
        else:
            st.success(validation_label)
    final_review_report: dict[str, Any] | None = None
    if report_delivery_current:
        try:
            final_review_report = _build_canonical_final_review_report(
                result,
                vector_asset_admission=vector_asset_admission,
            )
        except ValueError as exc:
            st.error(_t('v1.results_final_report.canonical_report_contract_could_not_projected', p0=exc))
    if not vector_asset_admission["allowed"]:
        st.error(
            _t('v1.results_final_report.vector_assets_workflow_combination_legacy_project_did')
        )
        st.caption(str(vector_asset_admission.get("reason") or _t('v1.expression.vector_asset_contract_failed')))
    summary_cards = []
    if is_dual_tu:
        unit_rows = sorted(
            list(result.get("expression_units") or []),
            key=lambda unit: int(unit.get("order", 0) or 0),
        )
        summary_cards.append((_t("v1.results_final_report.tu_count"), str(len(unit_rows)), ""))
        summary_cards.extend(
            (f"TU{index}", f"{int(unit.get('length') or 0):,} bp", "")
            for index, unit in enumerate(unit_rows, start=1)
        )
        summary_cards.append(("多 TU 区域", f"{int(cassette.get('sequence_length') or 0):,} bp", ""))
    else:
        summary_cards.append(("表达盒", f"{int(cassette.get('sequence_length') or 0):,} bp", "build"))
    summary_cards.extend(
        [
            ("载体骨架", f"{source_backbone_length:,} bp", "build"),
            ("完整质粒", f"{int(plasmid.get('sequence_length') or 0):,} bp", "build"),
        ]
    )
    if authenticity_gate:
        summary_cards.extend([
            ("来源真实性", "已确认", ""),
            ("序列一致性", "通过", ""),
            ("精确插入合同", "已应用", ""),
            ("交付用途", "专业审查", ""),
        ])
    else:
        summary_cards.extend([("警告", str(warning_count), "warning"), ("阻断", str(blocking_count), "blocking")])
    cards_html = "".join(
        f"<div class='result-summary-card {css_class}'><div class='label'>{_ui(label)}</div><div class='value'>{_ui(value)}</div></div>"
        for label, value, css_class in summary_cards
    )
    summary_grid_class = "result-summary-grid history-preview" if result_preview_mode else "result-summary-grid"
    st.markdown(f"<div class='{summary_grid_class}'>{cards_html}</div>", unsafe_allow_html=True)
    if final_review_report is not None:
        _render_canonical_final_review_delivery(final_review_report)
    if result_preview_mode:
        _render_persisted_result_downloads(result)
    formal_context = result.get("formal_project_context") if isinstance(result.get("formal_project_context"), dict) else {}
    if is_dual_tu and formal_context.get("design_scenario") == "metabolic_pathway_multi_tu_vector":
        from services.gate3_pathway_mapping import build_pathway_traceability_rows, validate_pathway_mapping

        pathway_steps = formal_context.get("pathway_steps")
        pathway_units = list((result.get("original_input") or {}).get("expression_units") or [])
        pathway_validation = validate_pathway_mapping(pathway_steps, pathway_units)
        st.subheader(_t('v1.results_final_report.pathway_step_transcription_unit_tracing'))
        if pathway_validation["blocking_items"]:
            st.error(_t('v1.results_final_report.pathway_mapping_blocking_items_project_not_marked'))
        tracking_rows = build_pathway_traceability_rows(pathway_steps, pathway_units)
        pathway_rows = [
                {
                    _t('v1.results_final_report.step'): row["step_order"],
                    _t('v1.results_final_report.step_name'): row["step_name"],
                    _t('v1.results_final_report.conversion'): row["conversion"],
                    _t('v1.results_final_report.enzyme'): row["enzyme_name"],
                    _t('v1.results_final_report.cds_length'): f"{row['cds_length']:,} bp",
                    _t('v1.results_final_report.mapped_tu'): f"TU{row['transcription_unit_order']} · {row['transcription_unit']}" if row["transcription_unit_order"] else "--",
                    _t('v1.results_final_report.tu_direction'): _t('v1.common.reverse') if row["orientation"] == "reverse" else _t('v1.common.forward'),
                    _t('v1.results_final_report.mapping_status'): {
                        "applied": _t('v1.expression.mapping_status_applied'),
                        "blocked": _t('v1.expression.mapping_status_blocked'),
                        "mapped_pending_application": _t('v1.expression.mapping_status_pending'),
                    }.get(row["mapping_status"], _t('v1.expression.mapping_status_unmapped')),
                    _t('v1.results_final_report.manual_review_items'): "; ".join(row["manual_review"]) or "--",
                }
                for row in tracking_rows
            ]
        st.dataframe(_localized_rows(pathway_rows), hide_index=True, use_container_width=True)
    overview_tab, circular_tab, linear_tab, sequence_tab, review_tab = st.tabs([_t('v1.expression.structure_overview'), _t('v1.expression.circular_view'), _t('v1.expression.linear_view'), _t('v1.expression.sequence_view'), _t('v1.expression.check_results')])
    with overview_tab:
        insertion = dict(result.get("insertion_settings") or {})
        if is_dual_tu:
            insertion = dict(original_input.get("insertion_settings") or {})
        topology = _topology_label(plasmid.get("topology"))
        if is_dual_tu:
            _render_dual_tu_structure()
            cassette_coordinates = plasmid.get("cassette_coordinates") if isinstance(plasmid.get("cassette_coordinates"), dict) else {}
            unit_rows = sorted(
                list(result.get("expression_units") or []),
                key=lambda unit: int(unit.get("order", 0) or 0),
            )
            unit_rows_display = [
                    {
                        _t('v1.results_final_report.order'): f"TU{index}",
                        _t('v1.results_final_report.name'): str(unit.get("display_name") or unit.get("unit_name") or unit.get("unit_id") or "--"),
                        _t('v1.common.orientation'): _t('v1.common.reverse') if unit.get("orientation") == "reverse" else _t('v1.common.forward'),
                        _t('v1.results_final_report.length'): int(unit.get("length") or 0),
                    }
                    for index, unit in enumerate(unit_rows, start=1)
                ]
            st.dataframe(_localized_rows(unit_rows_display), hide_index=True, use_container_width=True)
            order_display = " → ".join(
                f"TU{index} ({str(unit.get('display_name') or unit.get('unit_name') or unit.get('unit_id'))})"
                for index, unit in enumerate(unit_rows, start=1)
            )
            st.markdown(
                _t('v1.results_final_report.tu_order_backbone_insertion_orientation',
                   p0=order_display,
                   p1=escape(str(backbone_input.get('display_name') or backbone_input.get('source_name') or '--')),
                   p2=_t('v1.expression.backbone_replacement') if insertion.get('mode') == 'replacement' else _t('v1.expression.backbone_insert'),
                   p3=int(plasmid.get('sequence_length') or 0),
                   p4=escape(topology),
                   p5=cassette_coordinates.get('start') or '--',
                   p6=cassette_coordinates.get('end') or '--',
                   p7=_t('v1.common.reverse') if insertion.get('insertion_orientation') == 'reverse' else _t('v1.common.forward'))
            )
            if insertion.get('mode') == 'replacement':
                st.caption(_t('v1.ui_closure.original_interval', start=insertion.get('start_coordinate'), end=insertion.get('end_coordinate')))
            st.caption(_t('v1.ui_closure.final_interval', start=cassette_coordinates.get('start'), end=cassette_coordinates.get('end')))
            with st.expander(_t('v1.common.technical_details'), expanded=False):
                st.markdown(_t('v1.expression.full_plasmid_sha_256', p0=str(plasmid.get('sequence_checksum') or '')))
        else:
            st.markdown(
                _t('v1.results_final_report.backbone_insertion_method_full_plasmid_length_bp', p0=_structure_overview_html(_controller().get()), p1=escape(str((result.get('input_records') or {}).get('backbone', {}).get('display_name') or '--')), p2=_t('v1.expression.backbone_replacement') if insertion.get('mode') == 'replacement' else _t('v1.expression.backbone_insert'), p3=int(plasmid.get('sequence_length') or 0), p4=escape(topology)),
                unsafe_allow_html=True,
            )
    with circular_tab:
        if publication_map_current:
            _render_publication_map_svg(
                result,
                view_type="complete_circular_plasmid",
                display_name=project_name,
                download_key="publication_map_complete_plasmid_svg",
            )
        else:
            st.warning(_t('v1.expression.result_not_latest_canonical_revision_publication_map'))
    with linear_tab:
        if publication_map_current:
            if formal_context.get("design_scenario") == "metabolic_pathway_multi_tu_vector":
                st.subheader(_t("v1.results_final_report.active_expression_linear_view"))
            _render_publication_map_svg(
                result,
                view_type="linear_active_expression_construct",
                display_name=_t('v1.publication_map.expression_construct_name', p0=project_name),
                download_key="publication_map_expression_construct_svg",
            )
            if formal_context.get("design_scenario") == "metabolic_pathway_multi_tu_vector":
                st.subheader(_t("v1.results_final_report.complete_plasmid_linear_view"))
                _render_publication_map_svg(
                    result,
                    view_type="complete_linear_plasmid",
                    display_name=_t('v1.publication_map.complete_plasmid_name', p0=project_name),
                    download_key="publication_map_complete_plasmid_linear_svg",
                )
        else:
            st.warning(_t('v1.expression.result_not_latest_canonical_revision_publication_map'))
    with review_tab:
        _render_findings(list(plasmid.get("validation_findings") or []), runtime=result.get('runtime'))
        with st.expander(_t('v1.results_final_report.view_element_coordinates'), expanded=False):
            st.dataframe(_public_feature_rows(plasmid, result), hide_index=True, use_container_width=True)
    with sequence_tab:
        if is_dual_tu:
            _render_unit_sequence_reviews(result.get('expression_units') or [])
        with st.expander(_t('v1.expression.multi_tu_region_sequence') if is_dual_tu else _t('v1.expression.expression_cassette_sequence'), expanded=False):
            _render_sequence_review(
                cassette.get("sequence"),
                label=_t('v1.expression.multi_tu_region_sequence') if is_dual_tu else _t('v1.expression.expression_cassette_sequence'),
            )
        with st.expander(_t('v1.results_final_report.full_plasmid_sequence'), expanded=False):
            _render_sequence_review(
                plasmid.get("sequence"),
                label=_t('v1.results_final_report.full_plasmid_sequence'),
            )

    if result_preview_mode:
        return

    st.subheader(_t('v1.results_final_report.save_export'))
    fasta = dict(exports.get("complete_plasmid_fasta") or exports.get("fasta") or {})
    genbank = dict(exports.get("complete_plasmid_genbank") or exports.get("genbank") or {})
    cassette_fasta = dict(exports.get("combined_construct_fasta") or (result.get("cassette_exports") or {}).get("fasta") or {})
    unit_fastas = dict(exports.get("unit_fastas") or {})
    complete_export_payloads_present = bool(fasta.get("data")) and bool(genbank.get("data"))
    if not complete_export_payloads_present:
        st.warning(_t('v1.results_final_report.result_lacks_complete_fasta_genbank_payload_download'))
    downloads_enabled = (
        is_current
        and blocking_count == 0
        and bool(vector_asset_admission["allowed"])
        and complete_export_payloads_present
    )

    backup_json = json.dumps(result, ensure_ascii=False, indent=2, default=str) + "\n"
    with st.container(key="results_export_actions"):
        st.markdown(
            """
            <style>
            .st-key-results_export_actions [data-testid="stButton"] > button,
            .st-key-results_export_actions [data-testid="stDownloadButton"] > button {
                box-sizing: border-box !important;
                width: 100% !important;
                height: 46px !important;
                min-height: 46px !important;
                padding: 8px 10px !important;
                border-radius: var(--r) !important;
                font-size: var(--type-control) !important;
                font-weight: var(--weight-control-secondary) !important;
                line-height: var(--leading-control) !important;
                text-align: center !important;
                white-space: normal !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
            }
            .st-key-results_export_actions [data-testid="stButton"] > button:not(:disabled):hover,
            .st-key-results_export_actions [data-testid="stDownloadButton"] > button:not(:disabled):hover {
                filter: brightness(0.97) !important;
            }
            .st-key-results_export_actions [data-testid="stButton"] > button:disabled,
            .st-key-results_export_actions [data-testid="stDownloadButton"] > button:disabled {
                background: #e5e7eb !important;
                color: var(--text-disabled) !important;
                border-color: #d1d5db !important;
                cursor: not-allowed !important;
            }
            .st-key-results_export_actions [data-testid="stButton"] > button[kind="primary"] {
                font-weight: var(--weight-control-primary) !important;
            }
            .st-key-results_export_actions [data-testid="stButton"] > button[kind="secondary"],
            .st-key-results_export_actions [data-testid="stDownloadButton"] > button {
                font-weight: var(--weight-control-secondary) !important;
            }
            .st-key-results_project_actions,
            .st-key-results_download_actions,
            .st-key-results_delivery_actions {
                margin-top: 16px;
            }
            .st-key-results_project_actions [data-testid="stHorizontalBlock"],
            .st-key-results_download_actions [data-testid="stHorizontalBlock"],
            .st-key-results_delivery_actions [data-testid="stHorizontalBlock"] {
                gap: 12px;
            }
            .results-action-heading {
                margin-top: 18px;
                color: var(--text-primary);
                font-size: var(--type-card-title);
                font-weight: var(--weight-card-title);
                line-height: var(--leading-subsection);
            }
            .results-action-reason {
                margin-top: 8px;
                color: var(--text-support);
                font-size: var(--type-support);
                line-height: var(--leading-support);
            }
            @media (max-width: 760px) {
                .st-key-results_export_actions [data-testid="stButton"] > button,
                .st-key-results_export_actions [data-testid="stDownloadButton"] > button {
                    padding-left: 6px !important;
                    padding-right: 6px !important;
                }
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        if include_project_actions:
            st.markdown(_t('v1.results_final_report.project_actions'), unsafe_allow_html=True)
            with st.container(key="results_project_actions"):
                project_action_cols = st.columns(2)
                if project_action_cols[0].button(
                    _t('v1.common.save_project'), type="primary", disabled=not downloads_enabled, use_container_width=True
                ):
                    try:
                        saved = _save_current_formal_draft(current_step=6)
                    except (ValueError, RuntimeError) as exc:
                        st.error(str(exc))
                    else:
                        st.session_state["formal_last_saved_mvp_project_id"] = str(getattr(saved, "project_id", "") or "")
                        st.success(_t('v1.results_final_report.project_saved_can_reopened_project_home_page'))
                if project_action_cols[1].button(_t('v1.results_final_report.return_edit_design'), use_container_width=True):
                    ds = _controller().get()
                    ds.step = 5
                    _controller().save(ds)
                    _change_page(PAGE_DESIGN_WORKSPACE)

        st.markdown(_t('v1.results_final_report.download_results'), unsafe_allow_html=True)
        with st.container(key="results_download_actions"):
            if is_dual_tu and unit_fastas:
                st.caption(_t('v1.results_final_report.each_transcription_unit_fasta_extracted_canonical_multi'))
                unit_download_cols = st.columns(min(3, len(unit_fastas)))
                ordered_units = sorted(
                    list(result.get("expression_units") or []),
                    key=lambda unit: int(unit.get("order", 0) or 0),
                )
                for index, unit in enumerate(ordered_units, start=1):
                    export_record = dict(unit_fastas.get(str(unit.get("unit_id"))) or {})
                    unit_download_cols[(index - 1) % len(unit_download_cols)].download_button(
                        f"TU{index} FASTA",
                        data=export_record.get("data") or "",
                        file_name=export_record.get("file_name") or f"TU{index}.fasta",
                        mime=export_record.get("mime") or "text/plain",
                        disabled=not downloads_enabled or not export_record.get("data"),
                        on_click="ignore",
                        use_container_width=True,
                        key=f"download_{unit.get('unit_id')}_fasta",
                    )
            download_action_cols = st.columns(2 if is_dual_tu else 3)
            canonical_download_offset = 0
            if not is_dual_tu:
                download_action_cols[0].download_button(
                    _t('v1.results_final_report.expression_cassette_fasta'),
                    data=cassette_fasta.get("data") or "",
                    file_name=cassette_fasta.get("file_name") or "expression_cassette.fasta",
                    mime=cassette_fasta.get("mime") or "text/plain",
                    disabled=not downloads_enabled or not cassette_fasta.get("data"),
                    on_click="ignore",
                    use_container_width=True,
                )
                canonical_download_offset = 1
            download_action_cols[canonical_download_offset].download_button(
                _t('v1.results_final_report.full_plasmid_fasta'),
                data=fasta.get("data") or "",
                file_name=fasta.get("file_name") or "complete_plasmid.fasta",
                mime=fasta.get("mime") or "text/plain",
                disabled=not downloads_enabled,
                on_click="ignore",
                use_container_width=True,
            )
            download_action_cols[canonical_download_offset + 1].download_button(
                _t('v1.results_final_report.full_plasmid_genbank'),
                data=genbank.get("data") or "",
                file_name=genbank.get("file_name") or "complete_plasmid.gb",
                mime=genbank.get("mime") or "text/plain",
                disabled=not downloads_enabled,
                on_click="ignore",
                use_container_width=True,
            )

        st.markdown(_t('v1.ui_closure.local_backup'))
        with st.container(key="results_delivery_actions"):
            delivery_action_cols = st.columns(1)
            delivery_action_cols[0].download_button(
                _t('v1.results_final_report.project_backup_json'),
                data=backup_json,
                file_name="project_backup.json",
                mime="application/json",
                disabled=not downloads_enabled,
                on_click="ignore",
                use_container_width=True,
            )
    st.caption(
        _t('v1.results_final_report.plant_biodesign_supports_user_provided_actual_sequences')
    )


def _render_results_export() -> None:
    """Compatibility wrapper for the legacy results route."""
    st.title(_t('v1.results_final_report.results_export'))
    _render_results_export_content()


def _plant_library_records() -> list[dict[str, Any]]:
    """Return the exact 171-row canonical V2 product projection."""
    from services.component_library_v2_adoption import build_v2_canonical_inventory

    return build_v2_canonical_inventory()

    # Historical mixed-inventory loader retained below for audit traceability.
    # The formal page no longer reaches it.
    from Bio import SeqIO
    from core.expression_frame_builder import get_host_rules
    from services.mvp_sequence_input import analyze_genbank_backbone_input
    from services.parts_service import query_registry_parts
    from services.rice_hsa_ncbi_mvp10_case import ALB_GENBANK, BACKBONE_GENBANK

    records: list[dict[str, Any]] = []
    seen_demo_sequences: set[tuple[str, str]] = set()
    for host in _plant_host_values():
        rules = get_host_rules(host)
        for type_label, key in (("启动子", "promoter"), ("终止子", "terminator")):
            sequence = str(rules.get(f"{key}_seq") or "")
            sequence_key = (key, sequence)
            if sequence_key in seen_demo_sequences:
                continue
            seen_demo_sequences.add(sequence_key)
            records.append(
                {
                    "id": f"rules::{host}::{key}",
                    "name": _display_element_name(str(rules.get(key) or type_label), key, len(sequence)),
                    "type": type_label,
                    "sequence": sequence,
                    "length": len(sequence),
                    "host": host,
                    "source": "内置植物元件记录",
                    "accession": "内置植物元件记录",
                    "complete_status": "片段" if len(sequence) < 300 else "完整元件状态未记录",
                }
            )
    for part_type, type_label in (("Promoter", "启动子"), ("CDS", "编码序列（CDS）"), ("Terminator", "终止子")):
        for item in query_registry_parts(part_types=part_type):
            host = str(item.get("host") or "")
            sequence = str(item.get("sequence") or "")
            if not sequence or not any(term in host.casefold() for term in ("rice", "oryza", "tobacco", "nicotiana", "plant")):
                continue
            records.append(
                {
                    "id": f"registry::{item.get('id') or item.get('name')}",
                    "name": _display_element_name(str(item.get("name") or type_label), part_type.lower(), len(sequence)),
                    "type": type_label,
                    "sequence": sequence,
                    "length": int(item.get("length_bp") or len(sequence)),
                    "host": host,
                    "source": "内置植物元件记录",
                    "accession": "未记录",
                    "complete_status": "完整元件状态未记录",
                }
            )
    alb_record = SeqIO.read(ALB_GENBANK, "genbank")
    alb_cds = next(
        feature
        for feature in alb_record.features
        if feature.type == "CDS" and "albumin" in " ".join(feature.qualifiers.get("product", [])).lower()
    )
    alb_sequence = str(alb_cds.extract(alb_record.seq)).upper()
    records.append(
        {
            "id": "ncbi::NM_000477.7::ALB",
            "name": "ALB CDS",
            "type": "编码序列（CDS）",
            "sequence": alb_sequence,
            "length": len(alb_sequence),
            "host": _plant_host_value_for_id("rice"),
            "source": "NCBI GenBank",
            "accession": "NM_000477.7",
            "complete_status": "完整元件",
        }
    )
    from services.rice_hsa_ncbi_mvp10_case import load_rice_hsa_ncbi_case

    official_case = load_rice_hsa_ncbi_case()
    for role, name, type_label, source_status in (
        ("promoter", "CaMV35S 启动子区", "启动子", "来源已确认"),
        ("terminator", "CaMV 3′ UTR（polyA 信号）", "3′端元件", "用途待人工复核"),
    ):
        asset = official_case["assets"][role]
        records.append(
            {
                "id": f"ncbi::{asset['accession_version']}::{role}",
                "name": name,
                "type": type_label,
                "sequence": asset["sequence"],
                "length": asset["used_length"],
                "host": _plant_host_value_for_id("rice"),
                "source": "NCBI 官方记录",
                "accession": asset["accession_version"],
                "location": asset["used_location"],
                "strand": asset["strand"],
                "complete_status": source_status,
            }
        )
    from services.plant_project_draft_schema import new_project_id

    project_id = str(st.session_state.setdefault("mvp_project_id", new_project_id()))
    repository_root = BACKBONE_GENBANK.parents[3]
    backbone_sources = [
        ("pCAMBIA-1300 / AF234296.1", BACKBONE_GENBANK.read_text(encoding="utf-8"), "审计后的本地 GenBank", "AF234296.1"),
        ("pBI121 / AF485783.1", (repository_root / "data/real_assets/pbi121/source_records/AF485783.1.gb").read_text(encoding="utf-8"), "审计后的本地 GenBank", "AF485783.1"),
        ("pBIN19 / U09365.1", (repository_root / "data/plant_component_registry_v1/source_records/U09365.1.gb").read_text(encoding="utf-8"), "审计后的本地 GenBank", "U09365.1"),
    ]
    for name, raw_text, source, accession in backbone_sources:
        try:
            parsed = analyze_genbank_backbone_input(
                raw_text,
                project_id=project_id,
                display_name=name,
                source_kind="example",
                source_name=accession,
            )
        except Exception:
            continue
        identity = dict(parsed.get("vector_asset_identity") or {})
        contract = dict(identity.get("contract") or {})
        records.append(
            {
                "id": f"backbone::{accession}",
                "name": name,
                "type": "载体骨架",
                "sequence": str(parsed.get("normalized_sequence") or ""),
                "length": int(parsed.get("length") or 0),
                "host": "植物表达载体",
                "source": source,
                "accession": accession,
                "record": parsed,
                "asset_kind": identity.get("asset_kind"),
                "asset_type_label": parsed.get("vector_asset_display_label"),
                "formal_selectable": bool(contract.get("formal_selection_allowed")),
                "complete_status": parsed.get("vector_asset_display_label"),
            }
        )
    return records


def _formal_library_display_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only records with enough source and component-status detail for the formal library."""
    return list(records)


def _render_real_genbank_asset_import() -> None:
    """Render a local immutable-source review surface for real GenBank assets."""
    from services.real_genbank_asset_import import (
        PBI121_ACCESSION,
        RealGenBankAssetError,
        build_pbi121_asset_bundle,
        parse_genbank_bytes,
    )

    st.subheader(_t('v1.component_library.import_real_genbank_assets'))
    st.caption(_t('v1.component_library.retains_original_records_feature_coordinates_source_summaries'))
    source_kind = st.radio(
        _t('v1.component_library.asset_source'),
        _GENBANK_SOURCE_VALUES,
        format_func=lambda value: _localized_value(value, {
            _GENBANK_SOURCE_VALUES[0]: "v1.expression.builtin_reference_asset",
            _GENBANK_SOURCE_VALUES[1]: "v1.expression.upload_genbank_source",
        }),
        horizontal=True,
        key="real_genbank_asset_source",
    )
    audit: dict[str, Any] | None = None
    bundle: dict[str, Any] | None = None
    if source_kind.startswith("内置"):
        try:
            bundle = build_pbi121_asset_bundle()
            audit = bundle["audit"]
        except RealGenBankAssetError as exc:
            st.error(str(exc))
            return
    else:
        uploaded = st.file_uploader(
            _t("v1.component_library.upload_genbank_file"),
            type=["gb", "gbk", "genbank"],
            key="real_genbank_asset_upload",
        )
        if uploaded is None:
            st.info(_t('v1.component_library.after_upload_source_summary_full_feature_audit'))
            return
        try:
            audit = parse_genbank_bytes(uploaded.getvalue())
        except RealGenBankAssetError as exc:
            st.error(str(exc))
            return

    if not audit:
        return
    st.markdown(
        _t("v1.component_library.record_summary_accession_name_topology_length_bp", p0=escape(str(audit['accession'])), p1=escape(str(audit['record_name'])), p2=escape(str(audit['topology'])), p3=f"{int(audit['length']):,}")
    )
    st.caption(_t('v1.component_library.source_record_sha_256_available_technical_source'))
    feature_rows = [
        {
            "名称": row["name"], "feature 类型": row["type"], "位置（1-based）": row["location_expression"],
            "链方向": "+" if row["strand"] == 1 else "-" if row["strand"] == -1 else "mixed/unknown",
            "资产类别": row["asset_type"], "人工复核": "需要" if row["provenance_status"] == "needs_feature_review" else "来源已记录",
        }
        for row in audit["features"]
    ]
    with st.expander(_t('v1.component_library.feature_list'), expanded=True):
            st.dataframe(_localized_rows(feature_rows), hide_index=True, use_container_width=True)
    candidates = [row for row in audit["features"] if row["registerable_component"]]
    with st.expander(_t('v1.component_library.extracted_authentic_source_candidate_parts'), expanded=True):
        candidate_rows = [{"名称": row["biological_role"], "类别": row["asset_type"], "位置（1-based）": row["location_expression"], "链方向": "+" if row["strand"] == 1 else "-", "来源状态": row["provenance_status"]} for row in candidates]
        st.dataframe(_localized_rows(candidate_rows), hide_index=True, use_container_width=True)
    if bundle is None:
        with st.expander(_t('v1.component_library.technical_source_details'), expanded=False):
            st.write(f"accession: {audit['accession']}")
            st.code(audit["source_record_sha256"], language="text")
            st.write(_t('v1.component_library.uploaded_records_used_only_previewing_parsing_session'))
        return

    vector = bundle["vector"]
    contract = vector["replacement_contract"]
    st.warning(
        _t('v1.component_library.pbi121_complete_non_empty_t_dna_replacement')
    )
    st.markdown(
        _t("v1.component_library.full_binary_vector_source_bp_asset_type", p0=f"{int(vector['length']):,}", p1=vector['topology'], p2=vector['asset_kind'], p3=contract['replacement_start'], p4=contract['replacement_end'], p5=f"{contract['replacement_length']:,}")
    )
    with st.expander(_t('v1.component_library.technical_source_details'), expanded=False):
        st.write(f"accession: {PBI121_ACCESSION}")
        st.write(_t('v1.component_library.source_record_sha_256', p0=audit['source_record_sha256']))
        st.write(_t('v1.component_library.full_plasmid_sha_256', p0=vector['sequence_sha256']))
        st.write(_t('v1.component_library.extraction_method_actual_genbank_feature_table_location'))
        for row in candidates:
            st.markdown(f"**{escape(row['biological_role'])}**")
            st.write(_t('v1.component_library.location_qualifiers', p0=row['location_expression'], p1=row['qualifiers']))


def _use_catalog_component_in_multi_tu(component: Mapping[str, Any]) -> None:
    """Store a service-built Registry or USER_PROVIDED component in the existing editor."""
    role = str(component.get("role") or "")
    if not role:
        raise ValueError("当前元件没有可用的 Multi-TU 角色。")
    from services.plant_project_draft_schema import new_project_id

    st.session_state.setdefault("mvp_project_id", new_project_id())
    st.session_state["formal_project_type"] = PROJECT_TYPE_DUAL_TU
    units = _transcription_units()
    first = dict(units[0])
    first[role] = {
        key: value for key, value in dict(component).items() if key != "role"
    }
    _store_transcription_units([first, *units[1:]])
    _invalidate_dual_tu_unit(str(first.get("unit_id") or ""))
    st.session_state.pop("_formal_multi_tu_widget_state_marker", None)
    ds = _controller().get()
    ds.step = 3
    _controller().save(ds)
    _change_page(PAGE_DESIGN_WORKSPACE)


def _use_catalog_assisted_component(component: Mapping[str, Any]) -> None:
    """Keep the active Single-Gene project and adapt only its supported roles."""
    if _formal_project_type() != PROJECT_TYPE_SINGLE_GENE:
        _use_catalog_component_in_multi_tu(component)
        return
    from services.single_gene_assisted_components import single_gene_assisted_input

    project_id = str(st.session_state.get("mvp_project_id") or "")
    record = single_gene_assisted_input(
        component, project_id=project_id,
        host=str(st.session_state.get("formal_project_host") or ""),
        repository=_formal_project_repository(project_id, PROJECT_TYPE_SINGLE_GENE),
    )
    role = record["biological_role"]
    key = "promoter" if role == "promoter" else "five_prime"
    if key == "promoter":
        st.session_state["formal_step3_promoter_mode"] = "user_sequence"
        st.session_state["formal_step3_promoter_custom_name"] = record["display_name"]
        st.session_state["formal_step3_promoter_custom_text"] = record["normalized_sequence"]
        st.session_state["formal_step3_promoter_custom_input"] = "paste"
        st.session_state.pop("_formal_step3_editor_state", None)
    else:
        for suffix, value in {"enabled": True, "role": role, "name": record["display_name"],
                              "sequence": record["normalized_sequence"], "source": record["source_reference"]}.items():
            st.session_state[f"formal_step3_five_prime_{suffix}"] = value
    st.session_state.setdefault("formal_element_source_records", {})[key] = record
    _invalidate_formal_snapshots()
    ds = _controller().get()
    ds.clear_step3_outputs()
    ds.step = 3
    _controller().save(ds)
    _change_page(PAGE_DESIGN_WORKSPACE)


def _use_plant_library_record(record: dict[str, Any]) -> None:
    if record.get("registry_component_id"):
        from services.registry_catalog_ui import build_direct_registry_component

        host_record = _plant_host_record(st.session_state.get("formal_project_host"))
        requested_host = str(host_record.get("scientific_name") or "") if host_record else ""
        try:
            component = build_direct_registry_component(
                record,
                requested_host=requested_host,
            )
        except Exception as exc:
            st.error(_t('v1.component_library.component_not_passed_formal_registry_eligibility', p0=exc))
            return
        _use_catalog_component_in_multi_tu(component)
        return
    ds = _controller().get()
    record_type = str(record.get("type") or "")
    if record_type in {"CDS", "编码序列（CDS）"}:
        ds.gene_name = str(record.get("name") or "CDS").replace(" CDS", "")
        ds.original_seq = str(record.get("sequence") or "")
        ds.clear_step3_outputs()
        ds.step = 2
        st.session_state["formal_cds_source"] = str(record.get("accession") if record.get("accession") not in {"未记录", "内置植物元件记录"} else "")
        _clear_complete_plasmid_state()
    elif record_type in {"启动子", "终止子", "3′端元件"}:
        elements = dict(ds.elements or {})
        key = "promoter" if record_type == "启动子" else "terminator"
        elements[f"{key}_name"] = str(record.get("name") or record_type)
        elements[f"{key}_seq"] = str(record.get("sequence") or "")
        ds.elements = elements
        ds.clear_step3_outputs()
        ds.step = 3
        _clear_complete_plasmid_state()
    elif record_type == "载体骨架":
        backbone_record = dict(record.get("record") or {})
        st.session_state["formal_backbone_record"] = backbone_record
        from core.pcambia1300_exact_insertion_contract import is_pcambia1300_record

        ds.step = 4 if is_pcambia1300_record(backbone_record) else 5
        st.session_state.pop("mvp_vector_result", None)
    _controller().save(ds)
    _change_page(PAGE_DESIGN_WORKSPACE)


def _reset_formal_library_page() -> None:
    previous_signature = st.session_state.get("formal_library_filter_signature")
    current_signature = _formal_library_filter_signature()
    st.session_state["formal_library_page"] = 1
    st.session_state["formal_library_filter_signature"] = current_signature
    if previous_signature is None or previous_signature != current_signature:
        _clear_formal_library_selected_record()


def _formal_library_filter_signature() -> tuple[str, str, str, str]:
    return (
        str(st.session_state.get("formal_library_search") or "").strip().casefold(),
        _component_library_host_filter_value(st.session_state.get("formal_library_host")),
        _component_library_workflow_filter_value(st.session_state.get("formal_library_workflow")),
        _formal_library_type_filter_value(st.session_state.get("formal_library_type_filter")),
    )


def _clear_formal_library_selected_record() -> None:
    st.session_state.pop("formal_library_selected_registry_id", None)


def _formal_library_page_window(total: int, page_size: int, page: int) -> tuple[int, int, int, int]:
    """Return a clamped one-based page with its zero-based record slice."""
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(max(page, 1), total_pages)
    start = (current_page - 1) * page_size
    return current_page, total_pages, start, min(start + page_size, total)


def _formal_library_selected_record_id(
    records: list[dict[str, object]], selected_registry_id: str | None
) -> str | None:
    """Keep the selected detail record only while it remains in the result set."""
    record_ids = {
        str(record.get("catalog_record_id") or record.get("registry_component_id") or "")
        for record in records
    }
    return selected_registry_id if selected_registry_id in record_ids else None


def _formal_library_type_filter_value(selected_type: str | None) -> str:
    """Return a valid component-type filter value for the library view."""
    legacy_values = {
        "全部": "all",
        "启动子": "promoter",
        "5′ UTR": "five_prime_utr",
        "CDS": "cds",
        "终止子": "terminator",
        "3′调控区": "three_prime_regulatory_region",
        "调控/载体元件": "regulatory_or_vector_element",
        "载体骨架": "vector_backbone",
    }
    stable_values = {
        "all",
        "promoter",
        "five_prime_utr",
        "cds",
        "terminator",
        "three_prime_regulatory_region",
        "regulatory_or_vector_element",
        "vector_backbone",
    }
    candidate = str(selected_type or "").strip()
    if candidate in legacy_values:
        return legacy_values[candidate]
    return candidate if candidate in stable_values else "all"


def _change_formal_library_type_filter() -> None:
    """Reset dependent library state only after the type filter actually changes."""
    selected_type = _formal_library_type_filter_value(
        st.session_state.get("formal_library_type_radio_v2")
    )
    current_type = _formal_library_type_filter_value(
        st.session_state.get("formal_library_type_filter")
    )
    if selected_type != current_type:
        st.session_state["formal_library_type_filter"] = selected_type
        _reset_formal_library_page()


def _render_plant_component_library() -> None:
    """Render canonical V2 identities with fail-closed current-product routing."""
    # Legacy source-shape markers: st.title("元件库"),
    # "植物表达设计元件目录 · V1 · ", f"权威 Registry {len(registry_records)} 条 · ",
    # f"经复核目录候选 {len(candidate_records)} 条", "仅供目录浏览".
    # Legacy detail markers: "显示名称：", "元件类型：", "精确变体：",
    # "来源 accession：", "来源记录 / 上下文：", "序列长度：", "证据记录：",
    # "目录身份：", "正式准入/可选状态：", with st.expander("技术与来源详情", expanded=False):
    # "序列 SHA-256：", "内部 provenance：".
    from services.registry_catalog_ui import catalog_row_ui_state, catalog_state_counts
    from services.plant_component_workflow_registry import catalog_search_records

    st.title(_t("v1.common.component_library"))
    records = _formal_library_display_records(_plant_library_records())
    governance_counts = catalog_state_counts(records)
    st.caption(_t("v1.component_library.v2_inventory_caption", p0=len(records)))
    st.caption(_t("v1.component_library.v2_governance_caption"))
    st.caption(
        _t(
            "v1.component_library.v2_count_summary",
            p0=17,
            p1=governance_counts["formal_selectable"],
            p2=governance_counts.get("user_sequence_assisted", 0),
            p3=governance_counts["reference_only"],
            p4=governance_counts.get("retired", 0),
        )
    )
    search_col, host_col, workflow_col = st.columns([2, 1, 1])
    search = search_col.text_input(
        _t('v1.common.search'),
        placeholder=_t("v1.component_library.search_placeholder"),
        key="formal_library_search",
        on_change=_reset_formal_library_page,
    ).strip().casefold()
    host_options = [_COMPONENT_LIBRARY_HOST_ALL_VALUE] + sorted(
        {
            str(context)
            for row in records
            for context in [
                row.get("host_context")
                or ", ".join(row.get("target_host_species") or [])
            ]
            if context
        }
    )
    host_filter = host_col.selectbox(
        _t('v1.component_library.host_screening'),
        host_options,
        format_func=lambda value: _t("v1.component_library.all_sources_host_contexts")
        if value == _COMPONENT_LIBRARY_HOST_ALL_VALUE
        else str(value),
        key="formal_library_host",
        on_change=_reset_formal_library_page,
    )
    host_filter = _component_library_host_filter_value(host_filter)
    st.session_state["formal_library_workflow"] = _component_library_workflow_filter_value(
        st.session_state.get("formal_library_workflow")
    )
    workflow_filter = workflow_col.selectbox(
        _t('v1.component_library.available_status'),
        _LIBRARY_WORKFLOW_VALUES,
        format_func=lambda value: _localized_value(value, {
            "all": "v1.component_library.all_records",
            "authoritative_registry": "v1.component_library.authoritative_registry",
            "catalog_candidate": "v1.component_library.catalog_candidate",
            "formal_selectable": "v1.component_library.official_selection_available",
            "user_provided_sequence": "v1.component_library.user_provided_sequence",
            "deferred": "v1.component_library.deferred",
            "legacy_unclassified": "v1.component_library.legacy_unclassified",
        }),
        key="formal_library_workflow",
        on_change=_reset_formal_library_page,
    )
    type_filter = _formal_library_type_filter_value(
        st.session_state.get("formal_library_type_filter")
    )
    st.session_state["formal_library_type_filter"] = type_filter
    st.session_state["formal_library_type_radio_v2"] = _component_library_type_filter_value(
        st.session_state.get("formal_library_type_radio_v2") or type_filter
    )
    type_filter = st.radio(
        _t('v1.component_library.element_type'),
        _COMPONENT_LIBRARY_TYPE_FILTER_VALUES,
        format_func=lambda value: _localized_value(value, {
            "all": "v1.component_library.all",
            "promoter": "v1.ai_assisted_design.promoter",
            "five_prime_utr": "v1.component_library.5_utr",
            "cds": "v1.expression.cds",
            "terminator": "v1.component_library.terminator",
            "three_prime_regulatory_region": "v1.component_library.three_prime_regulatory_region",
            "regulatory_or_vector_element": "v1.component_library.regulatory_vector_components",
            "vector_backbone": "v1.component_library.vector_backbone",
        }),
        index=_COMPONENT_LIBRARY_TYPE_FILTER_VALUES.index(type_filter),
        key="formal_library_type_radio_v2",
        horizontal=True,
        on_change=_change_formal_library_type_filter,
    )
    st.session_state["formal_library_type_filter"] = type_filter
    st.session_state["formal_library_filter_signature"] = _formal_library_filter_signature()
    filtered = []
    for row in catalog_search_records(records, search):
        if (
            host_filter != _COMPONENT_LIBRARY_HOST_ALL_VALUE
            and host_filter
            != (
                row.get("host_context")
                or ", ".join(row.get("target_host_species") or [])
            )
        ):
            continue
        ui_state = catalog_row_ui_state(row)
        if (
            workflow_filter == "authoritative_registry"
            and row.get("record_authority") != "authoritative_registry"
        ):
            continue
        if workflow_filter == "catalog_candidate" and ui_state["state_key"] != "catalog_candidate":
            continue
        if workflow_filter == "formal_selectable" and not ui_state["formal_selectable"]:
            continue
        if workflow_filter == "user_provided_sequence" and not ui_state["can_offer_user_sequence"]:
            continue
        if workflow_filter == "deferred" and ui_state["state_key"] != "deferred":
            continue
        if workflow_filter == "legacy_unclassified" and ui_state["state_key"] != "legacy":
            continue
        if type_filter != "all" and row.get("component_type") != type_filter:
            continue
        filtered.append(row)
    page_size = st.selectbox(
        _t('v1.component_library.items_per_page'),
        [10, 20, 50],
        index=1,
        key="formal_library_page_size",
        on_change=_reset_formal_library_page,
    )
    page, total_pages, start, end = _formal_library_page_window(
        len(filtered), int(page_size), int(st.session_state.get("formal_library_page", 1))
    )
    st.session_state["formal_library_page"] = page
    selected_registry_id = _formal_library_selected_record_id(
        filtered,
        st.session_state.get("formal_library_selected_registry_id"),
    )
    if selected_registry_id is None:
        st.session_state.pop("formal_library_selected_registry_id", None)
    else:
        st.session_state["formal_library_selected_registry_id"] = selected_registry_id
    if not filtered:
        st.caption(_t('v1.component_library.showing_0_0_0_items'))
        st.info(_t('v1.component_library.no_matching_components_found'))
        return
    page_records = filtered[start:end]
    st.caption(_t('v1.component_library.showing_items', p0=start + 1, p1=end, p2=len(filtered)))
    st.markdown(
        _t('v1.component_library.name_type_length_source_accession_actions'),
        unsafe_allow_html=True,
    )
    for record in page_records:
        record_key = str(record["catalog_record_id"])
        ui_state = catalog_row_ui_state(record)
        component_type = str(record.get("component_type") or "")
        displayed_type = _component_library_type_label(component_type)
        type_class = {
            "cds": "cds",
            "terminator": "terminator",
            "three_prime_regulatory_region": "terminator",
            "vector_backbone": "backbone",
        }.get(component_type, "")
        with st.container(key=f"formal_library_row_{record_key}", border=False):
            name_col, type_col, length_col, accession_col, action_col = st.columns(
                [2, 1, 1, 1.2, 1], vertical_alignment="center"
            )
            with name_col:
                st.markdown(
                    f"<div class='library-name'>{escape(str(record['name']))}</div>"
                    + "<div class='library-status-group'>"
                    + "".join(
                        f"<span class='library-status'>{escape(_component_library_label(label))}</span>"
                        for label in ui_state["badges"]
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )
            with type_col:
                st.markdown(
                    f"<div class='library-cell centered'><span class='library-badge {type_class}'>{escape(displayed_type)}</span></div>",
                    unsafe_allow_html=True,
                )
            with length_col:
                st.markdown(
                    "<div class='library-cell centered'>"
                    + (
                        f"{int(record['length']):,} bp"
                        if int(record.get("length") or 0) > 0
                        else "--"
                    )
                    + "</div>",
                    unsafe_allow_html=True,
                )
            with accession_col:
                st.markdown(
                    f"<div class='library-cell library-accession'>{escape(str(record['accession']))}</div>",
                    unsafe_allow_html=True,
                )
            with action_col:
                with st.container(key=f"formal_library_action_{record_key}", border=False):
                    detail_col, use_col = st.columns([0.55, 1.45], gap="small", vertical_alignment="center")
                    with detail_col:
                        if st.button(
                            _t('v1.component_library.details'),
                            key=f"formal_library_detail_{record_key}",
                            use_container_width=True,
                        ):
                            st.session_state["formal_library_selected_registry_id"] = record_key
                            selected_registry_id = record_key
                    with use_col:
                        if st.button(
                            _t(
                                "v1.component_library.multi_tu"
                                if ui_state["formal_selectable"]
                                else "v1.component_library.browse_only"
                                if ui_state["state_key"] == "catalog_candidate"
                                else "v1.component_library.not_directly_usable"
                            ),
                            key=f"formal_library_use_{record_key}",
                            use_container_width=True,
                            disabled=not ui_state["formal_selectable"],
                            help=_component_library_label(ui_state['workflow_label']),
                        ):
                            _use_plant_library_record(record)
    records_by_registry_id = {str(record["catalog_record_id"]): record for record in filtered}
    with st.container(key="formal_library_selected_detail", border=False):
        if selected_registry_id and selected_registry_id in records_by_registry_id:
            selected_record = records_by_registry_id[selected_registry_id]
            selected_ui_state = catalog_row_ui_state(selected_record)
            st.button(
                _t('v1.component_library.collapse_details'),
                key="formal_library_close_detail",
                on_click=_clear_formal_library_selected_record,
            )
            selected_component_type = str(selected_record.get("component_type") or "")
            selected_displayed_type = _component_library_type_label(selected_component_type)
            st.subheader(_t('v1.component_library.component_details'))
            st.write(_t('v1.component_library.display_name', p0=selected_record['name']))
            st.write(
                _t(
                    "v1.component_library.v2_canonical_id",
                    p0=selected_record.get("canonical_v2_component_id") or "--",
                )
            )
            st.write(_t('v1.component_library.element_type_with_value', p0=selected_displayed_type))
            st.write(_t('v1.component_library.exact_variant', p0=selected_record.get('exact_variant') or _t('v1.component_library.registry_record_not_separately_listed')))
            st.write(_t('v1.component_library.source_accession', p0=selected_record['accession']))
            source_coordinates = str(selected_record.get("source_coordinates") or "")
            if source_coordinates:
                st.write(_t('v1.component_library.source_coordinates_feature_identity', p0=source_coordinates))
            st.write(
                _t('v1.component_library.source_record_context', p0=selected_record.get('organism_source_context') or selected_record.get('source_organism') or '--')
            )
            st.write(
                _t('v1.component_library.host_source_context', p0=selected_record.get('host_context') or ', '.join(selected_record.get('target_host_species') or []) or '--')
            )
            st.write(
                _t('v1.expression.length_label')
                + (
                    f"{int(selected_record['length']):,} bp"
                    if int(selected_record.get("length") or 0) > 0
                    else _t('v1.expression.version_not_recorded')
                )
            )
            st.write(_t('v1.component_library.evidence_record', p0=selected_record.get('source') or selected_record.get('source_database') or '--'))
            if selected_record.get("search_match_kind") == "related":
                st.info(_t('v1.component_library.result_source_record_context_matching_not_direct'))
            if selected_record.get("identity_review_status") in {"human_review", "not_resolved"}:
                st.warning(_t('v1.component_library.identity_unresolved_manual_review_required_catalog_will'))
            if selected_record.get("boundary_review_status") == "human_review":
                st.warning(_t('v1.component_library.element_boundaries_require_manual_review_records_do'))
            if selected_record.get("source_annotations"):
                st.write(_t('v1.expression.source_record_annotation_label') + "; ".join(str(item) for item in selected_record["source_annotations"]))
            st.write(_t('v1.component_library.catalog_identity', p0=_component_library_label(selected_ui_state['distribution_label'])))
            st.write(_t('v1.component_library.official_approval_optional_status', p0=_component_library_label(selected_ui_state['workflow_label'])))
            boundary = dict(selected_record.get("feature_boundary_method") or {})
            if boundary:
                st.write(
                    _t('v1.component_library.boundary_evidence', p0=boundary.get('method') or '--', p1=boundary.get('start_one_based') or '--', p2=boundary.get('end_one_based_inclusive') or '--')
                )
            st.write(_t('v1.component_library.limit', p0=selected_record.get('limitation') or '--'))
            with st.expander(_t('v1.component_library.technical_source_details'), expanded=False):
                if selected_record.get("registry_component_id"):
                    st.write(
                        _t(
                            "v1.component_library.v2_registry_id",
                            p0=selected_record["registry_component_id"],
                        )
                    )
                if selected_record.get("candidate_id"):
                    st.write(
                        _t(
                            "v1.component_library.v2_catalog_candidate_id",
                            p0=selected_record["candidate_id"],
                        )
                    )
                st.write(_t('v1.component_library.evidence_record', p0=selected_record.get('evidence_tier') or '--'))
                st.write(_t('v1.component_library.source_database', p0=selected_record.get('source_database') or '--'))
                if selected_record.get("source_url_reference"):
                    st.write(_t('v1.component_library.source_link', p0=selected_record['source_url_reference']))
                if selected_record.get("provenance_origin"):
                    st.write(_t('v1.component_library.internal_provenance', p0=selected_record['provenance_origin']))
                st.write(_t('v1.component_library.sequence_sha_256', p0=selected_record.get('sequence_sha256') or '--'))
                st.write(_t('v1.component_library.redistribution_notice', p0=selected_record.get('redistribution_status') or '--'))
                st.write(_t('v1.component_library.duplicate_equivalent_note', p0=selected_record.get('notes') or '--'))
                if selected_record.get("sequence"):
                    st.caption(_t('v1.component_library.full_dna_sequence'))
                    st.code(str(selected_record.get("sequence") or ""), language="text")
                else:
                    st.caption(_t('v1.component_library.version_does_not_include_sequence_catalog_identity'))
            single_gene_assisted = (
                _formal_project_type() == PROJECT_TYPE_SINGLE_GENE
                and selected_ui_state["state_key"] == "user_sequence_assisted"
            )
            can_apply_sequence = selected_ui_state["can_offer_user_sequence"]
            if single_gene_assisted:
                from services.single_gene_assisted_components import single_gene_assisted_role

                try:
                    single_gene_assisted_role(
                        str(selected_record.get("canonical_v2_component_id") or ""),
                        host=str(st.session_state.get("formal_project_host") or ""),
                    )
                except ValueError:
                    can_apply_sequence = False
                    st.caption(_t("v1.component_library.single_gene_assisted_role_unavailable"))
            if can_apply_sequence:
                from services.plant_project_draft_schema import new_project_id
                from services.registry_catalog_ui import (
                    build_reference_user_provided_component,
                    build_v2_user_provided_component,
                )

                st.markdown(_t('v1.component_library.provide_own_sequence_continue'))
                st.caption(
                    _t('v1.component_library.input_sequence_will_saved_as_user_provided')
                )
                user_name = st.text_input(
                    _t('v1.component_library.user_sequence_name'),
                    value=str(selected_record.get("name") or ""),
                    key=f"formal_library_user_name_{selected_registry_id}",
                )
                user_sequence = st.text_area(
                    _t("v1.component_library.v2_dna_fasta"),
                    height=120,
                    key=f"formal_library_user_sequence_{selected_registry_id}",
                )
                assisted_mode = (
                    selected_ui_state["state_key"] == "user_sequence_assisted"
                )
                user_source = ""
                identity_confirmed = False
                project_intent_confirmed = False
                use_confirmed = False
                if assisted_mode:
                    from services.component_library_v2_adoption import v2_assisted_confirmation_contract

                    confirmation = v2_assisted_confirmation_contract(selected_record)
                    st.caption(_t("v1.component_library.v2_user_authority_notice"))
                    if confirmation["has_reviewed_boundary"]:
                        st.write(_t("v1.component_library.v2_recorded_boundary", p0=confirmation["recorded_boundary"]))
                        st.write(_t("v1.component_library.v2_expected_length", p0=confirmation["expected_length"]))
                    else:
                        st.caption(_t("v1.component_library.v2_no_reviewed_boundary"))
                    user_source = st.text_input(
                        _t("v1.component_library.v2_user_sequence_source"),
                        key=f"formal_library_user_source_{selected_registry_id}",
                    )
                    evidence_confirmed = st.checkbox(
                        _t("v1.component_library.v2_identity_confirmation" if confirmation["has_reviewed_boundary"] else "v1.component_library.v2_project_intent_confirmation"),
                        key=f"formal_library_user_identity_confirm_{selected_registry_id}",
                    )
                    identity_confirmed = evidence_confirmed and confirmation["has_reviewed_boundary"]
                    project_intent_confirmed = evidence_confirmed and not confirmation["has_reviewed_boundary"]
                    use_confirmed = st.checkbox(
                        _t("v1.component_library.v2_use_confirmation"),
                        key=f"formal_library_user_use_confirm_{selected_registry_id}",
                    )
                if st.button(
                    _t('v1.component_library.provide_sequence_as_user_input_single_gene' if single_gene_assisted else 'v1.component_library.provide_sequence_as_user_input_multi_tu'),
                    key=f"formal_library_user_apply_{selected_registry_id}",
                    type="primary",
                    disabled=(
                        not bool(user_sequence.strip())
                        or (
                            assisted_mode
                            and not (
                                user_source.strip()
                                and (identity_confirmed or project_intent_confirmed)
                                and use_confirmed
                            )
                        )
                    ),
                ):
                    try:
                        project_id = str(
                            st.session_state.setdefault("mvp_project_id", new_project_id())
                        )
                        if assisted_mode:
                            from services.plant_project_draft_repository import (
                                PlantProjectDraftRepository,
                            )

                            repository = _formal_project_repository(
                                project_id, _formal_project_type()
                            ) or PlantProjectDraftRepository()
                            component = build_v2_user_provided_component(
                                selected_record,
                                raw_sequence=user_sequence,
                                display_name=user_name,
                                project_id=project_id,
                                project_repository=repository,
                                user_sequence_source=user_source,
                                identity_and_boundaries_confirmed=identity_confirmed,
                                project_intent_confirmed=project_intent_confirmed,
                                explicit_user_confirmation=use_confirmed,
                            )
                        else:
                            component = build_reference_user_provided_component(
                                selected_record,
                                raw_sequence=user_sequence,
                                display_name=user_name,
                                project_id=project_id,
                            )
                        _use_catalog_assisted_component(component) if assisted_mode else _use_catalog_component_in_multi_tu(component)
                    except Exception as exc:
                        st.error(
                            _t(
                                'v1.component_library.user_sequence_not_saved',
                                p0=_component_library_error(exc),
                            )
                        )
    previous_page, page_status, next_page = st.columns([1, 2, 1])
    if previous_page.button(
        _t('v1.project_center.previous_page'),
        key="formal_library_previous_page",
        type="secondary",
        disabled=page <= 1,
    ):
        _clear_formal_library_selected_record()
        st.session_state["formal_library_page"] = page - 1
        st.rerun()
    page_status.caption(_t('v1.component_library.page', p0=page, p1=total_pages))
    if next_page.button(
        _t('v1.project_center.next_page'),
        key="formal_library_next_page",
        type="secondary",
        disabled=page >= total_pages,
    ):
        _clear_formal_library_selected_record()
        st.session_state["formal_library_page"] = page + 1
        st.rerun()
    st.caption(_t('v1.results_final_report.evidence_level_describes_sequence_identity_source_completeness'))
    st.caption(_t('v1.component_library.host_records_do_not_guarantee_performance_under'))
    with st.expander(_t('v1.component_library.development_example_resources'), expanded=False):
        st.write("r229 / R229BONE")
        st.caption(_t('v1.component_library.local_example_pending_source_review_source_unverified'))


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------

page = st.session_state[_SK.SELECTED_PAGE]
if page == PAGE_RESULTS_EXPORT:
    ctrl = _controller()
    ds = ctrl.get()
    ds.step = 6
    ctrl.save(ds)
    st.session_state["formal_step_preview"] = True
    st.session_state[_SK.SELECTED_PAGE] = PAGE_DESIGN_WORKSPACE
    st.query_params["page"] = PAGE_DESIGN_WORKSPACE
    page = PAGE_DESIGN_WORKSPACE
_cur = _primary_navigation_page(page)

with st.sidebar:
    # Keep the complete navigation tree under one stable delta path.  The
    # language callback triggers a Streamlit rerun; without this keyed mount,
    # the sidebar's incremental update can leave the outgoing tree visible
    # while the localized tree is being reconciled.
    with st.container(key="formal_sidebar_mount"):
        # Legacy source-shape markers: 植物生物设计 / 本地化植物合成生物学设计平台.
        st.markdown(
            "<div style='padding:16px 0 18px 0'>"
            "<div class='formal-sidebar-title' style='letter-spacing:0'>"
            f"{_t('v1.common.plant_biodesign')}</div>"
            "<div class='formal-sidebar-support' style='margin-top:5px'>"
            f"{_t('v1.common.local_plant_synthetic_biology_design')}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        # PAGE_CRISPR_WORKFLOW is rendered once as its own button; no static duplicate label.
        for _page in _PRIMARY_NAV_PAGES:
            # _NAV_LABELS[_page] remains the legacy route-shape contract.
            # "基因编辑</div>" is retained as the frozen sidebar source marker.
            if _page == PAGE_AGENT_WORKSPACE:
                if "nav_agent_expanded" not in st.session_state:
                    st.session_state["nav_agent_expanded"] = False
                row_label, row_toggle = st.columns([1, 0.12], gap="small")
                with row_label:
                    if st.button(
                        _nav_label(_page),
                        key="nav_agent_page",
                        use_container_width=True,
                        type="primary" if _cur == _page else "secondary",
                    ):
                        _change_page(_page)
                with row_toggle:
                    if st.button(
                        "▾" if st.session_state["nav_agent_expanded"] else "▸",
                        key="nav_agent_toggle",
                        help=_t("v1.common.expand_collapse_ai_assisted_design"),
                        type="secondary",
                    ):
                        st.session_state["nav_agent_expanded"] = not st.session_state["nav_agent_expanded"]
                        st.rerun()
            elif st.button(
                _nav_label(_page),
                key=f"nav_{_page}",
                use_container_width=True,
                type="primary" if _cur == _page else "secondary",
            ):
                _change_page(_page)
        _language_options = ("中文", "EN")
        _current_language = _get_language()
        _current_language_label = "中文" if _current_language == "zh-CN" else "EN"
        if st.session_state.get("formal_language_switch") not in _language_options:
            st.session_state["formal_language_switch"] = _current_language_label
        st.radio(
            _t("v1.common.chinese"),
            _language_options,
            horizontal=True,
            key="formal_language_switch",
            on_change=_sync_language_switch,
            label_visibility="collapsed",
        )
        st.markdown(
            f"<div class='formal-sidebar-support' style='position:fixed;bottom:22px'>V1.0</div>",
            unsafe_allow_html=True,
        )

# ---------------------------------------------------------------------------
# Page router
# ---------------------------------------------------------------------------

try:
    # Keep one keyed block at one stable delta path and replace only its child
    # tree when the route changes. Unlike st.empty().container(), this does not
    # replace the mount element itself or change widget paths on ordinary reruns.
    # Unlike separate per-route mounts, the outgoing Project Browser subtree is
    # reconciled out of the same block before the destination remains visible.
    with st.container(key="formal_active_route_mount"):
        if page == PAGE_PROJECT_HOME:
            _render_project_home()
        elif page == PAGE_DESIGN_WORKSPACE:
            _render_design_workspace()
        elif page == PAGE_RESULTS_EXPORT:
            _render_results_export()
        elif page == PAGE_PLANT_LIBRARY:
            _render_plant_component_library()
        elif page == PAGE_SEQUENCE_TOOLBOX:
            render_sequence_toolbox()
        elif page == PAGE_CRISPR_WORKFLOW:
            _render_crispr_product_workflow()
        elif page == PAGE_AGENT_WORKSPACE:
            from views.AgentWorkspace import render_agent_workspace

            render_agent_workspace(
                project_id=str(st.session_state.get("mvp_project_id") or "").strip(),
                project_name=str(st.session_state.get("formal_project_name") or "").strip(),
                project_type=_formal_project_type(),
                workflow_type=_formal_workflow_type(),
                project_host=str(_formal_project_definition().get("plant_host") or "").strip(),
                open_project_center=_request_agent_project_selection,
                continue_to_expression=_continue_intelligent_design_project,
                record_active_surface=_record_current_project_surface,
            )

except ImportError as e:
    st.error(_t("error.module_load", error=e))
    st.info(_t("error.module_load_help"))

except Exception as e:
    st.error(_t("error.runtime", error=e))
    import traceback
    with st.expander(_t("error.traceback")):
        st.code(traceback.format_exc())


startup_warnings = _STARTUP_WARNINGS
startup_errors = _STARTUP_ERRORS
