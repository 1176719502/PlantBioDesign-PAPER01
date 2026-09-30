"""Focused locale checks for the formal UI copy corrected after smoke review."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from core.i18n import translate


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


@pytest.mark.parametrize(
    ("key", "zh", "en"),
    [
        ("v1.project_center.title", "项目中心", "Project Center"),
        ("v1.common.expression_design", "表达设计", "Expression Design"),
        ("v1.expression.step_3_plant_expression_cassette_design", "第三步：植物表达盒设计", "Step 3: Plant Expression Cassette Design"),
        ("v1.expression.pre_generation_checks", "生成前检查", "Pre-Generation Checks"),
        ("v1.expression.biological_role_label", "生物学角色", "Biological role"),
        ("v1.expression.full_technical_check", "完整技术检查", "Full technical check"),
        ("v1.expression.step_5_vector_construction_design_computational_check", "第五步：载体构建设计与计算校验", "Step 5: Vector Construction Design and Computational Check"),
        ("v1.expression.step_6_project_save_result_review_delivery", "第六步：项目保存、结果审查与交付", "Step 6: Project Save, Result Review, and Delivery"),
        ("v1.results_final_report.final_review_delivery", "最终审查与交付", "Final review and delivery"),
        ("v1.results_final_report.formal_report_preview", "正式报告预览", "Formal report preview"),
        ("v1.results_final_report.blocking_item", "阻断项", "Blocking Item"),
        ("v1.results_final_report.warnings", "警告项", "Warnings"),
        ("v1.results_final_report.export_file", "导出文件", "Export file"),
        ("v1.results_final_report.delivery_record", "交付记录", "Delivery record"),
        ("v1.expression.structure_overview", "结构概览", "Structural overview"),
        ("v1.expression.circular_view", "环状图", "Circular view"),
        ("v1.expression.linear_view", "线性图", "Linear view"),
        ("v1.expression.sequence_view", "序列", "Sequence"),
        ("v1.expression.check_results", "校验结果", "Check results"),
        ("v1.results_final_report.view_element_coordinates", "查看元件坐标", "View Element Coordinates"),
        ("v1.results_final_report.save_export", "保存与导出", "Save and Export"),
        ("v1.results_final_report.download_results_label", "下载结果", "Download results"),
        ("v1.results_final_report.download_formal_report_pdf", "下载正式报告", "Download formal report"),
    ],
)
def test_targeted_copy_is_bilingual(key: str, zh: str, en: str) -> None:
    assert zh in translate(key, language="zh-CN")
    assert en in translate(key, language="en")


def test_report_preview_localizes_only_controlled_lines() -> None:
    assignment = next(
        node for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "_FORMAL_REPORT_PREVIEW_COPY" for target in node.targets)
    )
    function = next(
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name == "_localized_formal_report_preview"
    )
    namespace = {"_get_language": lambda: "zh-CN"}
    exec(compile(ast.Module(body=[assignment, function], type_ignores=[]), str(ROOT / "app.py"), "exec"), namespace)
    original = "\n".join(
        [
            "# Single-Gene Final Review and Delivery Record",
            "## Project and Design Summary",
            "Project: Project Available Biological Role",
            "Project: available",
            "- Project Available Biological Role | promoter | source: Registry ID X | reference: AF234296.1",
            "Canonical SHA-256: abcdef012345",
            "Status: Documentation delivery record available",
            "- Canonical FASTA: available",
            "Delivery evidence identity: sha256:abcdef012345",
        ]
    )
    localized = namespace["_localized_formal_report_preview"](original)
    assert "# 单基因最终审查与交付记录" in localized
    assert "## 项目与设计摘要" in localized
    assert "项目：Project Available Biological Role" in localized
    assert "项目：available" in localized
    assert "- Project Available Biological Role | promoter | 来源：Registry ID X | 参考：AF234296.1" in localized
    assert "Canonical SHA-256：abcdef012345" in localized
    assert "状态：交付记录可用" in localized
    assert "- Canonical FASTA: 可用" in localized
    assert "sha256:abcdef012345" in localized
    namespace["_get_language"] = lambda: "en"
    assert namespace["_localized_formal_report_preview"](original) == original


def test_step_three_uses_plain_role_label_without_placeholder() -> None:
    assert "biological_role_field = _t('v1.expression.biological_role_label')" in SOURCE
    assert "column_config={biological_role_field: biological_role_field}" in SOURCE
    assert "_t('v1.expression.biological_role')" not in SOURCE
