from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


def _function_source(name: str) -> str:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
    return ast.get_source_segment(source, node) or ""


def test_step_six_reuses_one_results_export_content_renderer() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step_six = source.split("def _render_step_6_review", 1)[1].split(
        "def _render_design_workspace", 1
    )[0]

    assert "def _render_results_export_content(" in source
    assert step_six.count("_render_results_export_content(include_project_actions=False)") == 5
    assert "_change_page(PAGE_RESULTS_EXPORT)" not in step_six
    assert '"查看结果与导出"' not in step_six


def test_results_route_is_only_a_legacy_redirect_and_not_a_second_renderer() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    legacy_wrapper = _function_source("_render_results_export")
    router = source.split("# Page router", 1)[1]

    assert "if page == PAGE_RESULTS_EXPORT:" in source
    assert "PAGE_DESIGN_WORKSPACE" in source
    assert "_render_results_export_content()" in legacy_wrapper
    assert "elif page == PAGE_RESULTS_EXPORT:" in router


def test_inline_renderer_preserves_existing_download_payload_sources() -> None:
    content = _function_source("_render_results_export_content")

    assert 'exports = dict(result.get("exports") or {})' in content
    assert 'result = st.session_state.get("mvp_vector_result")' in content
    assert 'data=fasta.get("data") or ""' in content
    assert 'data=genbank.get("data") or ""' in content
    assert 'file_name=fasta.get("file_name") or "complete_plasmid.fasta"' in content
    assert 'file_name=genbank.get("file_name") or "complete_plasmid.gb"' in content
    assert "active_complete_plasmid_snapshot(result.get(\"runtime\"))" in content
    assert "export_active_construct(" not in content


def test_inline_mode_avoids_a_second_save_or_navigation_action_bar() -> None:
    content = _function_source("_render_results_export_content")
    multi_tu = _function_source("_render_multi_tu_assembly_results")
    navigation = _function_source("_render_step_navigation")

    assert "if include_project_actions:" in content
    assert "if include_project_actions:" in multi_tu
    assert '"查看结果与导出"' not in navigation
    assert "if current_step < 6 and next_col.button(" in navigation


def test_persisted_result_with_incomplete_editor_state_uses_history_preview() -> None:
    workspace = _function_source("_render_design_workspace")
    preview = _function_source("_is_result_preview_mode")
    preview_renderer = _function_source("_render_result_preview_mode")

    assert 'result.get("project_id")' in preview
    assert 'exports.get("complete_plasmid_fasta")' in preview
    assert 'exports.get("complete_plasmid_genbank")' in preview
    assert "_formal_step_statuses()[:5]" in preview
    assert "if _is_result_preview_mode():" in workspace
    assert "_render_step_strip(ds.step)" in workspace
    assert "v1.common.results_export_historical_results_preview" in preview_renderer
    assert "v1.common.read_only_preview_historical_results_record_lacks" in preview_renderer
    assert preview_renderer.count("st.info(") == 1
    content = _function_source("_render_results_export_content")
    assert "此历史记录未保存完整编辑参数，仅展示已保存的设计结果和导出文件。" not in content
    assert "项目定义摘要（数据来源：第一步）" not in content
    assert "v1.expression.saved_result_summary" in content
    assert 'show_save=False' in preview_renderer
    assert 'show_next=False' in preview_renderer
    assert 'compact_back_only=True' in preview_renderer
    assert "请先完成第" not in preview_renderer
    assert "v1.results_final_report.fixed_case_component_evidence_read_only_label" in content
    assert "v1.results_final_report.construction_review_notes" in content


def test_history_preview_reuses_persisted_export_bytes_and_omits_review_zip_copy() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    downloads = _function_source("_render_persisted_result_downloads")

    assert 'data=fasta.get("data") or ""' in downloads
    assert 'data=genbank.get("data") or ""' in downloads
    assert 'file_name=fasta.get("file_name") or "complete_plasmid.fasta"' in downloads
    assert 'file_name=genbank.get("file_name") or "complete_plasmid.gb"' in downloads
    assert 'mime=fasta.get("mime") or "text/plain"' in downloads
    assert 'mime=genbank.get("mime") or "text/plain"' in downloads
    assert "专业审查 ZIP" not in source


def test_history_preview_uses_compact_navigation_and_four_plus_three_summary_grid() -> None:
    navigation = _function_source("_render_step_navigation")
    content = _function_source("_render_results_export_content")

    assert "compact_back_only: bool = False" in navigation
    assert "if compact_back_only:" in navigation
    assert "border=True" in navigation
    assert 'key=f"formal_page_actions_step_{current_step}"' in navigation
    assert 'summary_grid_class = "result-summary-grid history-preview" if result_preview_mode else "result-summary-grid"' in content
    assert ".result-summary-grid.history-preview { grid-template-columns:repeat(4,minmax(0,1fr)); }" in APP_PATH.read_text(encoding="utf-8")
    assert "v1.results_final_report.project" in content


def test_step6_copy_uses_chinese_role_labels_and_unspecified_localization() -> None:
    content = _function_source("_render_results_export_content")
    navigation = _function_source("_render_step_navigation")

    assert "v1.expression.subcellular_localization_target" in content
    assert '"promoter": "启动子"' in content
    assert '"terminator": "终止子"' in content
    assert "A completed project cannot be replaced by an incomplete draft." not in navigation
    assert "v1.common.project_saved_can_reopened_project_center" in navigation


def test_completed_step6_save_binds_formal_state_without_reopening_the_draft_path() -> None:
    save_current = _function_source("_save_current_formal_draft")
    bind_state = _function_source("_bind_completed_formal_state")
    restore_single = _function_source("_restore_mvp_result")
    restore_multi = _function_source("_restore_dual_tu_result")

    assert "result = _bind_completed_formal_state(result)" in save_current
    assert 'formal_state.pop("mvp_vector_result", None)' in bind_state
    assert 'context["formal_state"] = formal_state' in bind_state
    assert "save_formal_project_draft" in save_current
    assert 'globals().get("_restore_completed_formal_state")' in restore_single
    assert 'globals().get("_restore_completed_formal_state")' in restore_multi
