from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")
SEQUENCE_TOOLBOX_SOURCE = (ROOT / "views" / "SequenceToolbox.py").read_text(encoding="utf-8")
GLOBAL_CSS = APP_SOURCE.split("<style>", 1)[1].split("</style>", 1)[0]
APP_TREE = ast.parse(APP_SOURCE)


def _function_source(name: str) -> str:
    node = next(
        item
        for item in APP_TREE.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(APP_SOURCE, node) or ""


def _tokens() -> dict[str, str]:
    root = re.search(r":root\s*\{(?P<body>.*?)\}", GLOBAL_CSS, re.DOTALL)
    assert root is not None
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root.group("body")))


def _declarations(selector: str) -> dict[str, str]:
    match = re.search(
        rf"^\s*{re.escape(selector)}\s*\{{(?P<body>[^{{}}]*)\}}",
        GLOBAL_CSS,
        re.MULTILINE,
    )
    assert match is not None, f"missing selector: {selector}"
    return {
        name: re.sub(r"\s*!important\s*$", "", value.strip())
        for name, value in re.findall(r"([\w-]+)\s*:\s*([^;]+);", match.group("body"))
    }


def test_home_and_workspace_share_the_page_header_contract() -> None:
    for renderer in ("_render_project_home", "_render_design_workspace"):
        source = _function_source(renderer)
        assert "st.title(" in source
        assert "st.caption(" in source

    project_home = _function_source("_render_project_home")
    assert 'v1.project_center.subtitle' in project_home
    assert 'st.title("植物表达载体设计")' not in project_home
    workspace = _function_source("_render_design_workspace")
    assert 'v1.expression.complete_plant_expression_vector_design_step_by' in workspace
    assert 'st.title("植物表达载体设计工作区")' not in workspace
    assert "当前项目：" in workspace

    caption = _declarations('[data-testid="stCaptionContainer"]')
    assert caption["font-size"] == "var(--type-caption)"
    assert caption["color"] == "var(--text-support)"


def test_project_home_reads_projects_before_emitting_its_page_content() -> None:
    home = _function_source("_render_project_home")
    change_page = _function_source("_change_page")

    title_index = home.index('st.title(_t("v1.project_center.title"))')
    assert home.index("for summary in list_mvp_single_gene_designs():") < title_index
    assert home.index("for summary in list_mvp_multi_tu_designs():") < title_index
    assert home.index('globals().get("_formal_workflow_drafts"') < title_index
    assert home.index('globals().get("_gate3_pathway_drafts"') < title_index
    assert "loading_placeholder = st.empty()" in APP_SOURCE
    assert "正在加载项目..." not in APP_SOURCE
    assert "loading_placeholder.empty()" in APP_SOURCE
    assert 'st.session_state.get("project_center_transition_pending", False)' in home
    assert home.index("if transition_pending:") < home.index("loading_placeholder = st.empty()")
    assert home.index('st.session_state.pop("project_center_transition_pending", None)') > home.index("for summary, payload in globals().get(\"_gate3_pathway_drafts\"" )
    assert "previous_page != PAGE_PROJECT_HOME" in change_page
    assert 'st.session_state["project_center_transition_pending"] = True' in change_page
    assert 'st.session_state.pop("project_center_transition_pending", None)' in change_page


def test_project_center_actions_defer_and_consume_interaction_state_once() -> None:
    home = _function_source("_render_project_home")

    duplicate_pop = 'st.session_state.pop("project_lifecycle_duplicate_pending_id", None)'
    duplicate_call = "duplicate_project(str(duplicate_pending_id))"
    rename_pop = 'st.session_state.pop("project_lifecycle_rename_pending_id", None)'
    rename_target = 'st.session_state["project_lifecycle_rename_target"]'

    assert home.index(duplicate_pop) < home.index(duplicate_call)
    assert home.count(duplicate_call) == 1
    assert home.index(rename_pop) < home.index(rename_target)
    assert 'st.session_state["project_lifecycle_action_menu_generation"] = menu_generation + 1' in home
    assert "if menu_generation % 2:" in home
    assert "menu_col.empty()" in home
    assert "if rename_dialog_active:" in home
    assert "time.sleep" not in home
    assert "session_state.clear" not in home


def test_formal_router_reuses_one_keyed_mount_without_placeholder_replacement() -> None:
    router = APP_SOURCE.split("# Page router", 1)[1]

    assert "page_mount = st.empty()" not in router
    assert "with page_mount.container():" not in router
    assert 'with st.container(key="formal_active_route_mount"):' in router
    assert "route_slots =" not in router
    assert "route_mounts =" not in router
    assert router.count("_render_project_home()") == 1
    assert router.count("_render_design_workspace()") == 1
    assert router.count("_render_results_export()") == 1
    assert router.count("_render_plant_component_library()") == 1
    assert router.count("render_sequence_toolbox()") == 1
    assert router.count("render_agent_workspace(") == 1


def test_project_summary_is_not_reused_by_workspace_or_step_six() -> None:
    home = _function_source("_render_project_home")
    workspace = _function_source("_render_design_workspace")
    step_six = _function_source("_render_step_6_review")

    # A single persisted record reaches the only formal project-row loop once;
    # workspace and Step 6 must not mount that full row/card renderer.
    assert home.count('key=f"formal_project_summary_{index}"') == 1
    assert "formal_project_summary_" not in workspace
    assert "formal_project_summary_" not in step_six
    assert workspace.count("当前项目：") == 1
    assert "formal_project_summary_" not in _function_source("_render_results_export_content")


def test_project_center_open_uses_a_callback_rerun_boundary() -> None:
    home = _function_source("_render_project_home")
    change_page = _function_source("_change_page")

    assert 'on_click=_open_project_from_center' in home
    assert 'project_center_open_callback_in_progress' in home
    assert 'project_center_open_callback_in_progress' in change_page
    assert "st.rerun()" in change_page


def test_project_rename_dialog_uses_live_input_and_safe_save_state() -> None:
    home = _function_source("_render_project_rename_dialog")

    assert 'with st.form(' not in home
    assert "st.form_submit_button" not in home
    assert '@st.dialog(_t("v1.project_center.rename_project"), on_dismiss=_clear_project_rename_dialog)' in APP_SOURCE
    assert 'key="project_lifecycle_rename_name"' in home
    assert 'project_name.strip()' in home
    assert 'trimmed_name = project_name.strip()' in home
    assert 'save_disabled = not trimmed_name or trimmed_name == original_name' in home
    assert "ProjectNameConflict" not in home
    assert "InvalidProjectName" not in home
    assert 'disabled=save_disabled' in home
    assert 'key="project_lifecycle_rename_actions"' in home
    assert "horizontal=True" in home
    assert 'horizontal_alignment="right"' in home
    assert 'key="project_lifecycle_rename_cancel"' in home
    assert 'key="project_lifecycle_rename_save"' in home
    assert "InputInstructions" not in GLOBAL_CSS
    assert ".st-key-project_lifecycle_rename_form" not in GLOBAL_CSS


def test_project_rename_dialog_actions_have_a_fixed_mobile_safe_layout() -> None:
    action_css = _declarations(
        '.st-key-project_lifecycle_rename_actions [data-testid="stHorizontalBlock"]'
    )
    button_css = _declarations(
        '.st-key-project_lifecycle_rename_actions [data-testid="stButton"] > button'
    )
    mobile_css = GLOBAL_CSS.split("@media(max-width: 900px)", 1)[1]

    assert action_css["display"] == "flex"
    assert action_css["flex-flow"] == "row nowrap"
    assert action_css["justify-content"] == "flex-end"
    assert action_css["gap"] == "8px"
    assert button_css["width"] == "68px"
    assert button_css["height"] == "32px"
    assert '.st-key-project_lifecycle_rename_actions [data-testid="stHorizontalBlock"]' in mobile_css
    assert "flex-flow:row nowrap !important" in mobile_css


def test_primary_navigation_labels_match_component_library_and_sequence_tool_titles() -> None:
    component_library = _function_source("_render_plant_component_library")

    assert 'st.title(_t("v1.common.component_library"))' in component_library
    assert 'st.title("植物元件库")' not in component_library
    assert 'v1.component_library.v2_inventory_caption' in component_library
    assert 'v1.component_library.v2_count_summary' in component_library
    assert 'v1.component_library.v2_governance_caption' in component_library
    assert 'st.title(_t("v1.common.sequence_tools"))' in SEQUENCE_TOOLBOX_SOURCE
    assert 'st.title("序列工具箱")' not in SEQUENCE_TOOLBOX_SOURCE
    assert 'v1.sequence_tools.basic_dna_sequence_analysis_conversion' in SEQUENCE_TOOLBOX_SOURCE


def test_sidebar_language_rerun_uses_one_stable_mount_and_one_selector() -> None:
    sidebar = APP_SOURCE.split("with st.sidebar:", 1)[1].split("# Page router", 1)[0]

    # The language widget callback causes a full Streamlit rerun.  Keeping the
    # whole sidebar under one keyed block prevents the outgoing and localized
    # trees from occupying separate incremental delta paths.
    assert sidebar.count('st.container(key="formal_sidebar_mount")') == 1
    assert 'with st.container(key="formal_sidebar_mount"):' in sidebar
    assert sidebar.count("st.radio(") == 1
    assert sidebar.count('key="formal_language_switch"') == 1
    assert "on_change=_sync_language_switch" in sidebar


def test_sidebar_language_callback_only_updates_locale_before_streamlit_rerun() -> None:
    callback = _function_source("_sync_language_switch")

    assert "_set_language(\"zh-CN\" if selected == \"中文\" else \"en\")" in callback
    assert "st.rerun()" not in callback


def test_steps_one_to_three_use_the_shared_section_heading_contract() -> None:
    step_sources = {
        1: _function_source("_render_step_1_project"),
        2: _function_source("_render_step_2_cds"),
        3: _function_source("_render_step_3_elements"),
    }
    assert "v1.expression.step_1_project_definition_expression_objective" in step_sources[1]
    assert "v1.expression.step_2_target_gene_coding_sequence_cds" in step_sources[2]
    assert "v1.expression.step_3_plant_expression_cassette_design" in step_sources[3]
    assert 'key="formal_primary_content_step1"' in step_sources[1]
    assert 'key="formal_content_section_step3_required"' in step_sources[3]
    assert "v1.expression.target_gene_information" in step_sources[2]
    assert "v1.expression.coding_sequence_cds_input" in step_sources[2]

    section_heading = _declarations(".formal-section-heading")
    assert section_heading["font-size"] == "var(--type-card-title)"
    assert section_heading["font-weight"] == "var(--weight-card-title)"
    assert section_heading["margin"] == "24px 0 12px"


def test_page_actions_keep_one_primary_continuation_contract() -> None:
    navigation = _function_source("_render_step_navigation")
    assert 'key=f"formal_page_actions_step_{current_step}"' in navigation
    assert 'next_type: str = "primary"' in navigation
    assert "type=next_type" in navigation
    assert 'next_col.button(' in navigation
    assert 'back_col.button(' in navigation
    assert 'save_col.button(' in navigation

    home = _function_source("_render_project_home")
    assert 'key="formal_home_actions"' in home
    assert home.count('type="primary"') == 1


def test_project_home_has_compact_semantic_project_summaries() -> None:
    home = _function_source("_render_project_home")
    assert 'key=f"formal_project_summary_{index}"' in home
    assert 'key="formal_project_table_head"' in home
    assert 'key="formal_home_empty"' in home
    assert 'st.columns([3.4, 2.0, 2.2, 1.7, 1.35])' in home
    assert 'st.columns([1, 1], gap="small")' in home
    assert 'width="content"' in home
    assert 'key=f"formal_project_actions_menu_{project.project_id}"' in home
    assert 'key=f"formal_project_actions_menu_items_{project.project_id}"' in home
    assert 'help="项目操作"' not in home
    for key in ("runtime.project", "v1.common.type", "v1.common.status", "v1.common.host", "runtime.last_modified", "runtime.actions"):
        assert key in home
    assert "宿主植物" not in home
    assert "最后修改\\n\\n" not in home
    assert "_project_home_type_status_label" in home
    assert "_project_home_host_label" in home
    assert "format_project_timestamp_for_local_display(project.updated_at)" in home
    assert '.replace("T", " ").replace("Z", "")[:16]' not in home

    assert 'padding:0 !important; border:0 !important; background:transparent !important;' in GLOBAL_CSS
    assert 'label[data-baseweb="radio"] { min-height:32px !important;' in GLOBAL_CSS
    assert 'border:1px solid var(--border) !important;' in GLOBAL_CSS
    assert 'border-color:var(--accent) !important;' in GLOBAL_CSS
    table_header_css = _declarations(".st-key-formal_project_table_head")
    assert table_header_css["border"] == "0"
    assert "border-top" not in table_header_css
    assert "border-bottom" not in table_header_css
    assert table_header_css["background"] == "transparent"
    assert '.st-key-formal_project_table_head [data-testid="stHorizontalBlock"]' in GLOBAL_CSS
    assert '[class*="st-key-formal_project_summary_"] [data-testid="stHorizontalBlock"]' in GLOBAL_CSS
    assert "grid-template-columns:minmax(180px,3.4fr)" in GLOBAL_CSS
    assert "grid-template-columns:68px 68px" in GLOBAL_CSS
    assert "width:142px" in GLOBAL_CSS
    assert "width:68px" in GLOBAL_CSS
    assert '[data-testid="stPopoverBody"]:has([class*="st-key-formal_project_actions_menu_items_"])' in GLOBAL_CSS
    assert "width:132px" in GLOBAL_CSS
    assert '[data-testid="stPopover"] [data-testid="stPopoverButton"]' in GLOBAL_CSS
    assert '[class*="st-key-formal_project_actions_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] { width:auto !important;' in GLOBAL_CSS
    assert "grid-template-columns:minmax(0,1fr) 72px" in GLOBAL_CSS
    assert '[class*="st-key-formal_project_actions_"] [data-testid="stElementContainer"]' in GLOBAL_CSS
    assert ".formal-project-updated-label { display:none; }" in GLOBAL_CSS

    assert 'key="project_center_pagination"' in home
    assert ".st-key-project_center_pagination [data-testid=\"stHorizontalBlock\"]" in GLOBAL_CSS
    assert ".st-key-project_center_pagination [data-testid=\"stButton\"] > button" in GLOBAL_CSS


def test_project_center_uses_one_shared_search_and_keeps_recent_search_global() -> None:
    home = _function_source("_render_project_home")
    search_helper = _function_source("_project_center_search_input")

    assert search_helper.count('key="project_center_search"') == 1
    assert home.count("_project_center_search_input()") == 2
    assert "filtered_recent_projects = filter_and_sort_projects(active_projects, query=query, sort=SORT_RECENT)" in home
    assert "visible_projects = filtered_recent_projects[:8]" in home
    assert "v1.project_center.search_results_projects" in home
    assert "project_center_toolbar_primary" in home


def test_project_center_toolbar_and_mobile_contracts_keep_controls_bounded() -> None:
    assert _declarations(".st-key-project_center_toolbar")["max-width"] == "960px"
    assert "grid-template-columns:minmax(0,3.2fr) minmax(180px,1fr)" in GLOBAL_CSS
    assert "grid-template-columns:repeat(3,minmax(0,1fr)) max-content" in GLOBAL_CSS
    mobile_css = GLOBAL_CSS.split("@media(max-width: 900px)", 1)[1]
    assert ".st-key-project_center_toolbar [data-testid=\"stHorizontalBlock\"]" in mobile_css
    assert "grid-template-columns:minmax(0,1fr) !important" in mobile_css


def test_archive_view_and_lifecycle_actions_reuse_the_project_center_state_machine() -> None:
    home = _function_source("_render_project_home")

    assert 'v1.project_center.recent_projects' in home
    assert 'v1.project_center.all_projects' in home
    assert 'v1.project_center.archived' in home
    assert "projects_for_lifecycle(projects, lifecycle_status=LIFECYCLE_ACTIVE)" in home
    assert "projects_for_lifecycle(projects, lifecycle_status=LIFECYCLE_ARCHIVED)" in home
    assert 'st.session_state.pop("project_lifecycle_archive_pending_id", None)' in home
    assert 'st.session_state.pop("project_lifecycle_unarchive_pending_id", None)' in home
    assert 'st.session_state["project_lifecycle_action_menu_generation"] = menu_generation + 1' in home
    assert 'if project.lifecycle_status == LIFECYCLE_ARCHIVED:' in home
    assert 'pc("v1.project_center.cancel_archival")' in home
    assert 'elif project.lifecycle_status == LIFECYCLE_ACTIVE:' in home
    assert 'pc("v1.common.archive")' in home
    assert "删除" not in home
    assert "回收站" not in home


def test_archived_project_rows_do_not_render_open_action() -> None:
    home = _function_source("_render_project_home")
    assert "if project.lifecycle_status != LIFECYCLE_ACTIVE:" in home
    unknown_branch = home.split("if project.lifecycle_status != LIFECYCLE_ACTIVE:", 1)[1].split("continue", 1)[0]
    assert "if project.lifecycle_status == LIFECYCLE_UNKNOWN:" in home
    assert "lifecycle: unknown" in home
    assert "open_plant_project_{project.project_id}" not in unknown_branch
    assert "rename_plant_project_{project.project_id}" not in unknown_branch
    assert "duplicate_plant_project_{project.project_id}" not in unknown_branch
    assert 'key=f"archive_plant_project_{project.project_id}"' not in unknown_branch
    assert 'pc("v1.project_center.cancel_archival")' in home


def test_unknown_project_rows_have_a_diagnostic_only_action_branch() -> None:
    home = _function_source("_render_project_home")
    unknown_branch = home.split("if project.lifecycle_status != LIFECYCLE_ACTIVE:", 1)[1].split("continue", 1)[0]
    assert "st.caption(" in unknown_branch


def test_archive_dialog_is_deferred_and_protects_explicit_unsaved_state() -> None:
    dialog = _function_source("_render_project_archive_dialog")
    helper = _function_source("_current_project_has_unsaved_changes")

    assert '@st.dialog(_t("v1.project_center.archive_project"), on_dismiss=_clear_project_archive_dialog)' in APP_SOURCE
    assert "v1.project_center.after_archiving_project_will_move_recent_projects" in dialog
    assert 'key="project_lifecycle_archive_confirm"' in dialog
    assert "archive_project(project_id)" in dialog
    assert "project_lifecycle_archive_error" in dialog
    assert "mvp_inputs_stale" in helper
    assert "session_state.clear" not in dialog


def test_step_two_sequence_input_uses_the_existing_monospace_contract() -> None:
    sequence_input = _declarations(".st-key-formal_step2_cds_text textarea")
    sequence_container = _declarations(".st-key-formal_step2_cds_text")
    assert sequence_input["font-family"] == "var(--font-mono)"
    assert sequence_input["font-size"] == "var(--type-sequence-code)"
    assert sequence_input["min-height"] == "220px"
    assert sequence_input["overflow-x"] == "auto"
    assert sequence_input["white-space"] == "pre"
    assert sequence_container["max-width"] == "960px"
    assert sequence_container["width"] == "100%"

    step_two = _function_source("_render_step_2_cds")
    assert 'key="formal_step2_cds_text"' in step_two
    assert "height=230" in step_two
    assert "next_label=_t('v1.expression.confirm_cds_continue')" in step_two
    assert 'next_label="保存 CDS 并继续"' not in step_two


def test_durable_save_boundary_is_explicit_and_session_transitions_are_not_saved() -> None:
    step_one = _function_source("_render_step_1_project")
    step_two = _function_source("_render_step_2_cds")
    navigation = _function_source("_render_step_navigation")
    feedback = _function_source("_render_formal_action_feedback")

    assert 'success_status="流程已更新"' in step_one
    assert "v1.expression.step_1_applied_continue_step_2" in step_one
    assert 'success_status="流程已更新"' in step_two
    assert "v1.expression.cds_applied_continue_step_3" in step_two
    assert 'status = "已保存" if current_step == 6 else' in feedback
    assert '"流程已更新"' in feedback
    assert "v1.common.project_draft_saved_can_reopened_project_center" in navigation
    assert "v1.expression.unsaved_changes_session_only_save_draft" in navigation
    assert 'st.session_state.get("ui_workflow_dirty")' in navigation
    assert 'or st.session_state.get("mvp_inputs_stale")' not in navigation


def test_durable_draft_feedback_is_only_emitted_after_save_helper_returns() -> None:
    navigation = _function_source("_render_step_navigation")
    save_helper = _function_source("_save_current_formal_draft")

    assert "_save_current_formal_draft(current_step=current_step)" in navigation
    assert "v1.common.project_draft_saved_can_reopened_project_center" in navigation
    assert "v1.common.project_saved_can_reopened_project_center" in navigation
    assert 'st.error(str(exc))' in navigation
    assert "save_formal_project_draft" in save_helper
    assert "st.success(\"项目草稿已保存" not in save_helper
    assert "_establish_workflow_baseline" in save_helper


def test_step_three_preserves_library_badge_and_identifier_contracts() -> None:
    step_three = _function_source("_render_step_3_elements")
    assert "_plant_element_options" in step_three
    assert 'key="formal_step3_promoter"' in step_three
    assert 'key="formal_step3_terminator"' in step_three
    assert 'key="formal_step3_three_prime_role"' in step_three
    assert 'key="formal_step3_component_promoter"' in step_three
    assert 'key="formal_step3_component_cds"' in step_three
    assert 'key="formal_step3_component_three_prime"' in step_three

    assert _declarations(".library-badge")["font-size"] == "var(--type-micro)"
    assert _declarations(".library-accession")["font-family"] == "var(--font-mono)"
    assert ".library-head" in GLOBAL_CSS


def test_component_library_names_and_badges_have_separate_flow_and_divider_space() -> None:
    source = _function_source("_render_plant_component_library")
    assert "{escape(str(record['name']))}</div>" in source
    assert "<div class='library-status-group'>" in source
    name = _declarations(".library-name")
    assert "-webkit-line-clamp" not in name
    assert name.get("overflow") != "hidden"
    assert name["overflow-wrap"] == "anywhere"
    group = _declarations(".library-status-group")
    assert group["display"] == "flex" and group["flex-wrap"] == "wrap"
    assert group["gap"] == "6px" and group["margin-top"] == "8px"
    row = _declarations('[class*="st-key-formal_library_row_"]')
    assert row["padding"] == "12px 16px 16px"
    badge = _declarations(".library-status")
    assert badge["max-width"] == "100%"
    assert badge["overflow-wrap"] == "anywhere"
    for style in (name, group, row, badge):
        assert style.get("position") not in {"absolute", "fixed"}
        assert "height" not in style


def test_component_library_long_actions_wrap_and_keep_nested_mobile_columns() -> None:
    button = _declarations('[class*="st-key-formal_library_action_"] [data-testid="stButton"] > button')
    assert button["height"] == "auto"
    assert button["white-space"] == "normal"
    assert button["max-width"] == "100%"
    text = _declarations('[class*="st-key-formal_library_action_"] [data-testid="stButton"] p')
    assert text["white-space"] == "normal" and text["overflow-wrap"] == "anywhere"
    mobile = GLOBAL_CSS.split("@media(max-width: 900px)", 1)[1]
    assert '[class*="st-key-formal_library_action_"] [data-testid="stHorizontalBlock"] { grid-template-columns:60px minmax(0,1fr) !important; }' in mobile
    assert '[class*="st-key-formal_library_action_"] [data-testid="stColumn"]:last-child { grid-column:auto; }' in mobile
    source = _function_source("_render_plant_component_library")
    assert 'disabled=not ui_state["formal_selectable"]' in source


def test_step_three_shows_existing_context_and_three_required_slots() -> None:
    step_three = _function_source("_render_step_3_elements")
    assert "v1.expression.step_3_plant_expression_cassette_design" in step_three
    assert "_plant_element_options" in step_three
    assert "_render_formal_step3_component" in step_three or "formal_step3_component" in step_three

    assert 'st.session_state.get("formal_cds_input")' in step_three
    assert 'saved_cds.get("normalized_cds")' in step_three
    assert "v1.expression.bp_step_2_not_editable_step" in step_three or "step_2" in step_three
    assert 'key="formal_step3_cds' not in step_three
    assert "1. 启动子" not in step_three
    assert "2. CDS（只读）" not in step_three
    assert "3. 3′端调控元件" not in step_three


def test_step_three_uses_full_width_rows_without_component_cards() -> None:
    step_three = _function_source("_render_step_3_elements")
    assert "formal_step3_component" in step_three
    assert "当前选择" not in step_three
    assert "Registry 正式记录" in step_three
    assert "演示记录" not in step_three
    assert "formal-component-status-summary" in step_three
    assert "formal-neutral-tag" not in GLOBAL_CSS
    component_spacing = _declarations('[class*="st-key-formal_step3_component_"]')
    assert component_spacing == {
        "margin": "0 0 18px",
        "padding": "0",
    }
    required_flow = _declarations(".st-key-formal_content_section_step3_required")
    assert required_flow == {"width": "100%", "margin-bottom": "16px"}
    assert "max-width" not in component_spacing
    assert "max-width" not in required_flow
    assert "border=True" not in step_three
    assert ".formal-selection-summary" not in GLOBAL_CSS


def test_step_three_uses_spacing_without_full_width_dividers() -> None:
    step_three = _function_source("_render_step_3_elements")
    flow_heading = _declarations(".formal-section-heading.step3-flow")
    assert flow_heading == {
        "padding-top": "0",
        "border-top": "0",
    }
    assert _declarations(".formal-section-heading.step3-components")["margin"] == (
        "32px 0 12px"
    )
    assert _declarations(".formal-section-heading.step3-checks")["margin"] == (
        "16px 0 12px"
    )
    assert "formal-section-heading" in GLOBAL_CSS
    assert _declarations(".formal-context-grid")["margin"] == "0"
    assert "st.divider" not in step_three
    assert "<hr" not in step_three
    assert "st.empty" not in step_three


def test_step_three_uses_three_horizontal_semantic_rows() -> None:
    step_three = _function_source("_render_step_3_elements")
    assert 'st.caption("启动子 → CDS → 3′端调控元件")' not in step_three
    assert "st.columns(3" not in step_three
    assert step_three.count("label_col, control_col, status_col = st.columns(") == 3
    assert step_three.count("[1.8, 6.2, 2]") == 3
    assert step_three.count("with label_col:") == 3
    assert step_three.count("with control_col:") == 3
    assert step_three.count("with status_col:") == 3
    assert "promoter_arrow" not in step_three
    assert "cds_arrow" not in step_three
    assert "formal-expression-arrow" not in step_three
    assert ".formal-expression-arrow" not in GLOBAL_CSS

    assert "_render_formal_step3_component" in step_three or "formal_step3_component" in step_three
    promoter = step_three.index('key="formal_step3_component_promoter"')
    cds = step_three.index('key="formal_step3_component_cds"')
    three_prime = step_three.index('key="formal_step3_component_three_prime"')
    assert promoter < cds < three_prime
    component_layout = _declarations('[class*="st-key-formal_step3_component_"]')
    assert "height" not in component_layout
    assert "min-height" not in component_layout
    assert "background" not in component_layout
    assert "box-shadow" not in component_layout
    assert "border" not in component_layout

    row_layout = _declarations(
        '[class*="st-key-formal_step3_component_"] [data-testid="stHorizontalBlock"]'
    )
    assert row_layout["grid-template-columns"] == (
        "minmax(170px,190px) minmax(0,1fr) minmax(180px,220px)"
    )
    assert row_layout["align-items"] == "start"


def test_step_three_uses_compact_checks_and_collapsed_technical_details() -> None:
    step_three = _function_source("_render_step_3_elements")
    assert "formal-check-summary" in step_three
    assert "finding_guidance" in step_three
    assert "formal-review-item" not in step_three
    assert "formal-check-item" in step_three
    assert '"component_order_not_confirmed"' in step_three
    assert '"incomplete_component_provenance"' in step_three
    assert '"custom_component_annotation"' in step_three
    assert "v1.expression.design_information_tip" in step_three
    assert "v1.expression.technical_details_parts_blocks_manual_confirmations_required" in step_three
    assert "v1.expression.full_technical_check" in step_three
    assert '"检查代码": item["rule_id"]' in step_three
    assert step_three.index("formal-check-summary") < step_three.index("v1.expression.design_information_tip")
    assert "summary_columns = st.columns(5)" not in step_three
    assert ".metric(" not in step_three
    assert "页面操作" not in step_three


def test_step_three_uses_one_bottom_right_slot_for_generation_or_navigation() -> None:
    step_three = _function_source("_render_step_3_elements")
    navigation = _function_source("_render_step_navigation")

    assert "generate_required = not cassette_is_current" in step_three
    assert "v1.expression.generate_expression_cassette_continue" in step_three
    assert "next_action=advance_step3 if not generate_required else generate_step3_action" in step_three
    assert 'if next_label' in navigation
    assert 'key=f"formal_step_{current_step}_next"' in navigation
    assert "next_label=_t('v1.expression.generate_expression_cassette_continue')" in step_three
    assert 'st.button(\n        "生成表达盒"' not in step_three
    assert "页面操作" not in step_three
    assert "_orchestrate_formal_step3_generation" in step_three
    assert "step3_can_continue_to_backbone" in step_three


def test_step_three_feedback_is_neutral_without_changing_status_rendering() -> None:
    workspace = _function_source("_render_design_workspace")
    feedback = _function_source("_render_formal_action_feedback")
    assert "_render_formal_action_feedback(ds.step)" in workspace
    assert "st.error(body)" in feedback
    assert "st.warning(body)" in feedback
    assert "st.success(body)" in feedback

    step_three_scope = '[data-testid="stMain"]:has(.st-key-formal_content_section_step3_required)'
    alert = _declarations(f'{step_three_scope} [data-testid="stAlert"]')
    copy = _declarations(f'{step_three_scope} [data-testid="stAlert"] p')
    assert alert["border"] == "1px solid var(--border)"
    assert alert["background"] == "var(--surface)"
    assert copy["color"] == "var(--text-secondary)"


def test_step_three_copy_is_consistently_chinese_for_role_labels() -> None:
    step_three = _function_source("_render_step_3_elements")
    assert "biological_role_field" in step_three
    assert "precise biological role" not in step_three
    assert "biological_role_field = _t('v1.expression.biological_role_label')" in step_three
    assert "column_config={biological_role_field: biological_role_field}" in step_three


def test_step_three_candidate_sources_use_formal_registry_authority_only() -> None:
    options = _function_source("_plant_element_options")
    step_three = _function_source("_render_step_3_elements")
    assert "formal_step3_component_options" in options
    assert 'role = "promoter" if part_type == "Promoter" else "3_prime_regulatory_region"' in options
    assert 'get_host_rules(host)' not in options
    assert 'query_registry_parts(host=host, part_types=part_type)' not in options
    assert 'st.session_state.get("formal_element_source_records")' not in options
    assert 'st.session_state.get("formal_source_input_records")' not in options
    assert '_plant_element_options(ds.host, "Promoter")' in step_three
    assert '_plant_element_options(ds.host, "Terminator")' in step_three
    assert "formal_step3_authority_findings" in step_three
    assert "v1.expression.no_promoters_formal_registry_selection_eligibility_currently" in step_three
    assert "_plant_library_records" not in step_three


def test_step_three_zero_formal_options_keep_render_safe_user_input_paths() -> None:
    step_three = _function_source("_render_step_3_elements")
    assert 'else empty_formal_step3_component("promoter")' in step_three
    assert 'else empty_formal_step3_component("3_prime_regulatory_region")' in step_three
    assert 'if promoters or promoter_mode == "user_sequence":' in step_three
    assert 'terminators or terminator_mode == "user_sequence"' in step_three
    assert 'promoter["name"]' in step_three
    assert 'terminator["name"]' in step_three

    promoter_empty_state = step_three.split("if not promoters:", 1)[1].split(
        'if promoters or promoter_mode == "user_sequence":', 1
    )[0]
    three_prime_empty_state = step_three.split("if not terminators:", 1)[1].split(
        'three_prime_role = st.selectbox(', 1
    )[0]
    for empty_state in (promoter_empty_state, three_prime_empty_state):
        assert "st.warning(" in empty_state
        assert "st.error(" not in empty_state
        assert "v1.expression.no_" in empty_state

    visible_findings = step_three.split("visible_action_findings = [", 1)[1].split(
        "if visible_action_findings:", 1
    )[0]
    assert '"no_formal_promoter_component"' in visible_findings
    assert '"no_formal_three_prime_component"' in visible_findings
    assert '"empty_component_sequence"' in visible_findings
    assert "hidden_empty_sequence_messages" in visible_findings
    assert 'not promoters and promoter_mode == "registry"' in step_three
    assert 'not terminators and terminator_mode == "registry"' in step_three


def test_mobile_step_strip_is_compact_without_changing_the_breakpoint() -> None:
    assert "@media(max-width: 900px)" in GLOBAL_CSS
    assert '.st-key-formal_step_strip [data-testid="stHorizontalBlock"]' in GLOBAL_CSS
    assert "grid-template-columns:repeat(2,minmax(0,1fr)) !important" in GLOBAL_CSS
    assert '.st-key-formal_step_strip [class*="st-key-formal_step_card_"]' in GLOBAL_CSS
    assert "min-height:58px" in GLOBAL_CSS


def test_mobile_form_and_action_columns_stack_without_page_overflow() -> None:
    single_column_contracts = (
        '.st-key-formal_home_actions [data-testid="stHorizontalBlock"]',
        '[class*="st-key-formal_page_actions_step_"] [data-testid="stHorizontalBlock"]',
    )
    for selector in single_column_contracts:
        assert selector in GLOBAL_CSS
    assert "grid-template-columns:minmax(0,1fr) !important" in GLOBAL_CSS
    assert ".st-key-formal_project_table_head { display:none; }" in GLOBAL_CSS
    assert '[class*="st-key-formal_project_summary_"] [data-testid="stColumn"]:not(:last-child) [data-testid="stElementContainer"]' in GLOBAL_CSS
    assert ".formal-project-updated-label { display:inline;" in GLOBAL_CSS
    assert ".st-key-project_center_pagination { max-width:none; margin-top:12px; }" in GLOBAL_CSS
    assert (
        '.st-key-project_center_pagination [data-testid="stHorizontalBlock"] '
        '{ grid-template-columns:repeat(3,minmax(0,1fr)) !important; gap:8px !important; }'
    ) in GLOBAL_CSS
    step_three_rows = (
        '[class*="st-key-formal_step3_component_"] [data-testid="stHorizontalBlock"]'
    )
    assert step_three_rows in GLOBAL_CSS
    mobile_css = GLOBAL_CSS.split("@media(max-width: 900px)", 1)[1]
    assert (
        f'{step_three_rows} {{ grid-template-columns:minmax(0,1fr) !important; '
        "gap:8px !important; }"
    ) in mobile_css


def test_typography_tokens_and_remote_font_governance_remain_unchanged() -> None:
    tokens = _tokens()
    assert tokens["--font-ui"] == (
        '"Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", '
        '"PingFang SC", Arial, sans-serif'
    )
    assert tokens["--font-mono"] == '"Cascadia Mono", Consolas, "Courier New", monospace'
    assert tokens["--type-page-description"] == "16px"
    assert tokens["--type-sequence-code"] == "14px"
    assert "@import" not in GLOBAL_CSS.casefold()
    assert "@font-face" not in GLOBAL_CSS.casefold()
    assert "fonts.googleapis.com" not in GLOBAL_CSS.casefold()


def test_critical_widget_keys_and_navigation_helpers_are_preserved() -> None:
    expected_widget_keys = {
        "formal_step1_project_name",
        "formal_step1_host",
        "formal_step1_application_mode",
        "formal_step2_gene_name",
        "formal_step2_source_type",
        "formal_step2_cds_text",
        "formal_step3_promoter_mode",
        "formal_step3_promoter",
        "formal_step3_terminator_mode",
        "formal_step3_terminator",
        "formal_step3_three_prime_role",
        "formal_step3_order_confirmed",
    }
    assert all(f'key="{key}"' in APP_SOURCE for key in expected_widget_keys)

    step_strip = _function_source("_render_step_strip")
    navigation = _function_source("_render_step_navigation")
    assert "_set_formal_step(index)" in step_strip
    assert "_set_formal_step(current_step + 1)" in navigation
    assert "_change_page(PAGE_PROJECT_HOME)" in navigation


def test_page_consistency_routes_include_scoped_crispr_product_entry() -> None:
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in APP_TREE.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.startswith("PAGE_")
    }
    assert assignments == {
        "PAGE_PROJECT_HOME": "Project Home",
        "PAGE_DESIGN_WORKSPACE": "Six-Step Design Workspace",
        "PAGE_RESULTS_EXPORT": "Results and Export",
        "PAGE_PLANT_LIBRARY": "Plant Component Library",
        "PAGE_SEQUENCE_TOOLBOX": "Sequence Toolbox",
        "PAGE_CRISPR_WORKFLOW": "CRISPR V1 Workflow",
        "PAGE_AGENT_WORKSPACE": "Agent V1 Workspace",
    }
