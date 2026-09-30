"""Focused R2 checks for Multi-TU, Pathway Results, and Project Center Open."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path

import pytest

from core.i18n import translate


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _function_source(name: str) -> str:
    node = next(
        item for item in TREE.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(SOURCE, node) or ""


@pytest.mark.parametrize(
    ("key", "zh", "en"),
    [
        ("v1.expression.no_independent_five_prime_region", "不使用独立", "No independent"),
        ("v1.expression.cds_not_configured_multi_tu", "CDS 尚未配置", "CDS is not configured"),
        ("v1.results_final_report.role", "角色", "Role"),
        ("v1.results_final_report.component", "元件", "Component"),
        ("v1.results_final_report.confirmation_mode", "确认模式", "Confirmation mode"),
        ("v1.results_final_report.accession_verified", "accession 已核验", "Accession verified"),
        ("v1.results_final_report.boundary_verified_by_software", "边界经软件核验", "Boundary verified by software"),
        ("v1.results_final_report.formal_report_delivery_validation_failed", "正式报告交付验证失败", "Formal report delivery validation failed"),
    ],
)
def test_r2_controlled_copy_is_bilingual(key: str, zh: str, en: str) -> None:
    assert zh in translate(key, language="zh-CN")
    assert en in translate(key, language="en")


def test_multi_tu_step3_and_step4_use_display_only_locale_labels() -> None:
    selector = _function_source("_render_dual_tu_element_input")
    step3 = _function_source("_render_dual_tu_step_3")
    step4 = _function_source("_render_generic_multi_tu_step_4")

    assert "display_label" in selector
    assert "target host metadata: " not in selector
    assert 'or "unavailable"' not in selector
    assert '"可生成" if unit_ready else "未完成"' not in step3
    assert "no_formal_five_prime_region_records_user_sequence_allowed" in step3
    assert "formal_validation_label" in step4
    assert '"direction": "反向（reverse）"' not in step4
    for key in ("v1.results_final_report.role", "v1.results_final_report.component", "v1.common.orientation"):
        assert key in step4


def test_source_table_localizes_only_labels_and_preserves_exact_values() -> None:
    assignment = next(
        node for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_SOURCE_TECHNICAL_LABEL_KEYS" for target in node.targets)
    )
    function = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_localized_source_rows"
    )
    language = "zh-CN"
    namespace = {
        "Any": object,
        "Mapping": Mapping,
        "_t": lambda key: translate(key, language=language),
        "_ui": lambda value: value,
    }
    exec(compile(ast.Module(body=[assignment, function], type_ignores=[]), "app.py", "exec"), namespace)
    digest = "ab" * 32
    rows = namespace["_localized_source_rows"]([
        {
            "confirmation_mode": "IDENTITY_AND_RECORDED_BOUNDARY",
            "accession_verified": "false",
            "Registry ID": "REG-RAW-001",
            "来源 accession/version": "AF308778.1",
            "SHA-256": digest,
            "组件": "User Project Component",
        }
    ])
    row = rows[0]
    assert row["确认模式"] == "IDENTITY_AND_RECORDED_BOUNDARY"
    assert row["accession 已核验"] == "false"
    assert row["Registry ID"] == "REG-RAW-001"
    assert row["来源 accession/version"] == "AF308778.1"
    assert row["SHA-256"] == digest
    assert row["组件"] == "User Project Component"


def test_pathway_report_preview_translates_controlled_copy_only() -> None:
    assignment = next(
        node for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_FORMAL_REPORT_PREVIEW_COPY" for target in node.targets)
    )
    function = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_localized_formal_report_preview"
    )
    language = "zh-CN"
    namespace = {"_get_language": lambda: language}
    exec(compile(ast.Module(body=[assignment, function], type_ignores=[]), "app.py", "exec"), namespace)
    digest = "cd" * 32
    original = "\n".join([
        "# Multi-TU Final Review and Delivery Record",
        "Design scenario: metabolic_pathway_multi_tu_vector",
        "Workflow type: multi_tu",
        "Canonical topology: circular",
        "- TU1: forward",
        "- 1. User Project Component | role=promoter | component_id=V2-CMP-004 | source=USER_PROVIDED | reference=AF308778.1 | length=1202 bp",
        "  - Confirmation mode: IDENTITY_AND_RECORDED_BOUNDARY",
        "  - accession_verified=false",
        f"  - Sequence SHA-256: {digest}",
        "Canonical SHA-256: " + digest,
    ])
    localized = namespace["_localized_formal_report_preview"](original)
    assert "# 多 TU 最终审查与交付记录" in localized
    assert "设计场景：代谢通路 Multi-TU 载体" in localized
    assert "工作流类型：多 TU" in localized
    assert "Canonical 拓扑：环状" in localized
    assert "- TU1：正向" in localized
    assert "角色=promoter" in localized
    assert "元件 ID=V2-CMP-004" in localized
    assert "参考=AF308778.1" in localized
    assert "确认模式：IDENTITY_AND_RECORDED_BOUNDARY" in localized
    assert "accession 已核验=否" in localized
    assert digest in localized
    assert "V2-CMP-004" in localized
    language = "en"
    assert namespace["_localized_formal_report_preview"](original) == original


def test_single_gene_report_preview_keeps_checkpoint_projection() -> None:
    renderer = _function_source("_render_canonical_final_review_delivery")
    assert "_localized_single_gene_checkpoint_report_preview" in renderer
    assert 'report.get("workflow_type")' in renderer


def test_pathway_results_use_all_requested_controlled_copy_keys() -> None:
    results = _function_source("_render_results_export_content")
    delivery = _function_source("_render_canonical_final_review_delivery")
    findings = (ROOT / "views" / "formal_construct_findings.py").read_text(encoding="utf-8")
    for key in (
        "v1.results_final_report.pathway_step_transcription_unit_tracing",
        "v1.expression.structure_overview",
        "v1.expression.circular_view",
        "v1.expression.linear_view",
        "v1.expression.sequence_view",
        "v1.expression.check_results",
        "v1.results_final_report.view_element_coordinates",
        "v1.results_final_report.save_export",
        "v1.results_final_report.download_results",
    ):
        assert key in results
    for key in (
        "v1.results_final_report.blocking_item",
        "v1.results_final_report.warnings",
        "v1.results_final_report.export_file",
        "v1.results_final_report.delivery_record",
        "v1.results_final_report.formal_report_preview",
        "v1.results_final_report.download_final_review_report_markdown",
        "v1.results_final_report.download_formal_report_pdf",
        "v1.results_final_report.canonical_content_identity",
    ):
        assert key in delivery
    assert "v1.results_findings.software_check_no_issues_requiring_display_were" in findings


def test_multi_tu_download_layout_is_three_then_two_columns() -> None:
    assembly_results = _function_source("_render_multi_tu_assembly_results")
    complete_results = _function_source("_render_results_export_content")
    assert "unit_cols = st.columns(min(3, len(unit_fastas)))" in assembly_results
    assert "download_cols = st.columns(2)" in assembly_results
    assert "unit_download_cols = st.columns(min(3, len(unit_fastas)))" in complete_results
    assert "download_action_cols = st.columns(2 if is_dual_tu else 3)" in complete_results
    assert "if not is_dual_tu:" in complete_results
    assert "canonical_download_offset" in complete_results


def test_project_center_open_ends_browser_render_with_real_rerun_boundary() -> None:
    home = _function_source("_render_project_home")
    callback = home.split("def _open_project_from_center", 1)[1].split(
        "if project.lifecycle_status != LIFECYCLE_ACTIVE", 1
    )[0]
    cleanup = 'st.session_state.pop("project_center_open_callback_in_progress", None)'
    assert "opened = False" in callback
    assert callback.index(cleanup) < callback.rindex("return opened")
    assert "st.rerun()" not in callback
    assert "if _open_project_from_center():" in home
    assert home.index("if _open_project_from_center():") < home.index("st.rerun()", home.index("if _open_project_from_center():"))
    assert 'with st.container(key="formal_active_route_mount"):' in SOURCE
    assert "route_slots =" not in SOURCE
    assert "display: none" not in callback
    assert "visibility: hidden" not in callback
