from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _app_source() -> str:
    return (Path(ROOT) / "app.py").read_text(encoding="utf-8")


def _global_style_source() -> str:
    return _app_source().split("<style>", 1)[1].split("</style>", 1)[0]


def _root_tokens() -> dict[str, str]:
    root_match = re.search(r":root\s*\{(?P<body>.*?)\}", _global_style_source(), re.DOTALL)
    assert root_match is not None
    return dict(re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root_match.group("body")))


def _style_declarations(selector: str) -> dict[str, str]:
    rule_match = re.search(
        rf"^\s*{re.escape(selector)}\s*\{{(?P<body>.*?)\}}",
        _global_style_source(),
        re.DOTALL | re.MULTILINE,
    )
    assert rule_match is not None
    return {
        property_name: re.sub(r"\s*!important\s*$", "", value.strip())
        for property_name, value in re.findall(
            r"([\w-]+)\s*:\s*([^;]+);", rule_match.group("body")
        )
    }


def _contrast_ratio(foreground: str, background: str) -> float:
    def luminance(value: str) -> float:
        channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4 for channel in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_app_declares_formal_pages_and_primary_product_routes() -> None:
    content = _app_source()
    tree = ast.parse(content)
    expected_pages = [
        "Project Home",
        "Six-Step Design Workspace",
        "Results and Export",
        "Plant Component Library",
        "Sequence Toolbox",
        "CRISPR V1 Workflow",
        "Agent V1 Workspace",
    ]

    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.startswith("PAGE_")
    }
    assert list(assignments.values()) == expected_pages
    assert "_ALL_PAGES = [" in content
    assert all(f"    {constant}," in content for constant in assignments)


def test_app_primary_navigation_labels_are_current() -> None:
    content = _app_source()

    for label in (
        "项目中心",
        "表达设计",
        "基因编辑",
        "CRISPR",
        "智能设计",
        "元件库",
        "序列工具",
    ):
        assert label in content


def test_app_sidebar_brand_copy_is_current() -> None:
    content = _app_source()
    sidebar = content.split("with st.sidebar:", 1)[1].split("# Page router", 1)[0]

    assert "植物生物设计" in sidebar
    assert "本地化植物合成生物学设计平台" in sidebar
    assert "植物表达载体设计</div>" not in sidebar


def test_app_routes_each_formal_page_to_its_current_renderer() -> None:
    content = _app_source()

    expected_routes = {
        "PAGE_PROJECT_HOME": "_render_project_home()",
        "PAGE_DESIGN_WORKSPACE": "_render_design_workspace()",
        "PAGE_RESULTS_EXPORT": "_render_results_export()",
        "PAGE_PLANT_LIBRARY": "_render_plant_component_library()",
        "PAGE_SEQUENCE_TOOLBOX": "render_sequence_toolbox()",
        "PAGE_CRISPR_WORKFLOW": "_render_crispr_product_workflow()",
        "PAGE_AGENT_WORKSPACE": "render_agent_workspace(",
    }
    for page, renderer in expected_routes.items():
        assert f"if page == {page}:" in content or f"elif page == {page}:" in content
        assert renderer in content


def test_app_defaults_and_constrains_navigation_to_formal_pages() -> None:
    content = _app_source()

    assert "default_page=PAGE_PROJECT_HOME" in content
    assert "if target in _ALL_PAGES:" in content
    assert "for _page in _PRIMARY_NAV_PAGES:" in content


def test_app_keeps_native_sidebar_recovery_control_and_expands_main_content() -> None:
    content = _app_source()

    assert '[data-testid="stHeader"] {' in content
    assert '[data-testid="stSidebarCollapseButton"] {' in content
    assert "display: flex !important;" in content
    assert "visibility: visible !important;" in content
    assert "pointer-events: auto !important;" in content
    assert ".block-container {" in content
    assert "width: 100% !important;" in content
    assert "max-width: 1680px !important;" in content
    assert "padding: 24px 32px 40px !important;" in content
    assert '[data-testid="stHeader"],\n[data-testid="stToolbar"]' not in content


def test_results_export_actions_keep_review_zip_out_of_formal_scope() -> None:
    content = _app_source()

    action_block = content.split('with st.container(key="results_export_actions")', 1)[1].split(
        '    st.caption(\n        "植物生物设计已支持', 1
    )[0]
    assert 'key="results_project_actions"' in action_block
    assert 'key="results_download_actions"' in action_block
    assert 'key="results_delivery_actions"' in action_block
    assert "project_action_cols = st.columns(2)" in action_block
    assert "download_action_cols = st.columns(2 if is_dual_tu else 3)" in action_block
    assert "delivery_action_cols = st.columns(1)" in action_block
    assert "height: 46px !important" in action_block
    assert "font-size: var(--type-control) !important" in action_block
    assert "font-weight: var(--weight-control-primary) !important" in action_block
    assert "font-weight: var(--weight-control-secondary) !important" in action_block
    assert "line-height: var(--leading-control) !important" in action_block
    assert "v1.results_final_report.expression_cassette_fasta" in action_block
    assert "v1.results_final_report.full_plasmid_fasta" in action_block
    assert "v1.results_final_report.full_plasmid_genbank" in action_block
    assert "v1.results_final_report.project_backup_json" in action_block
    assert "Ready for professional review" not in action_block
    assert "review_metrics" not in action_block
    for forbidden_symbol in (
        "assess_professional_review_package",
        "build_professional_review_package",
        "assess_multi_tu_professional_review_package",
        "build_multi_tu_professional_review_package",
        "专业审查包 ZIP",
        "专业交付审查包 ZIP",
    ):
        assert forbidden_symbol not in action_block
    assert 'mime="application/zip"' not in action_block
    assert 'disabled=not downloads_enabled' in action_block


def test_formal_step_strip_uses_short_labels_and_one_in_card_status() -> None:
    content = _app_source()

    render_block = content.split("def _render_step_strip", 1)[1].split(
        "def _render_step_navigation", 1
    )[0]
    for key in (
        "v1.expression.step_short_project_definition",
        "v1.expression.step_short_target_gene",
        "v1.expression.step_short_plant_expression_cassette",
        "v1.expression.step_short_vector_backbone",
        "v1.expression.step_short_complete_construct",
        "v1.expression.step_short_results_export",
    ):
        assert key in render_block
    for key in (
        "v1.expression.step_short_tu_planning",
        "v1.expression.step_short_tu_component_design",
        "v1.expression.step_short_assembly_settings",
        "v1.expression.step_short_checks",
    ):
        assert key in render_block
    for key in (
        "v1.expression.completed",
        "v1.expression.current_step",
        "v1.expression.not_completed",
        "v1.expression.review_needed",
    ):
        assert key in render_block
    assert 'with st.container(key="formal_step_strip")' in render_block
    assert 'key=f"formal_step_card_{index}_{state_class}"' in render_block
    assert 'f"<div class=\'formal-step-status {state_class}\'>{_t(state_label_key)}</div>"' in render_block
    assert "_FORMAL_STEPS" not in render_block
    assert render_block.count("formal-step-status") == 1


def test_formal_step_strip_keeps_click_callback_and_status_styles() -> None:
    content = _app_source()

    assert "st.columns(6)" in content
    assert "_set_formal_step(index)" in content
    assert ".formal-step-status.current { color: #176b3a; }" in content
    assert ".formal-step-status.done { color: var(--text-success); }" in content
    assert ".formal-step-status.review { color: var(--text-warning); }" in content
    assert "min-height: 76px;" in content
    assert "height: auto;" in content
    assert "padding: 12px 8px 16px;" in content
    assert "white-space: normal !important;" in content


def test_formal_input_placeholders_use_readable_support_text() -> None:
    style = _global_style_source()

    assert '[data-testid="stTextInput"] input::placeholder' in style
    assert '[data-testid="stTextArea"] textarea::placeholder' in style
    assert "color: var(--text-support) !important" in style
    assert "opacity: 1 !important" in style


def test_result_summary_cards_protect_scientific_units_from_translation() -> None:
    content = _app_source()

    assert "notranslate" in content
    assert "translate='no'" in content
    assert ":,} bp" in content


def test_formal_typography_tokens_keep_roles_distinct_and_readable() -> None:
    tokens = _root_tokens()
    expected_sizes = {
        "--type-product-title": 22,
        "--type-page-title": 28,
        "--type-page-description": 16,
        "--type-section-title": 20,
        "--type-subsection-title": 18,
        "--type-card-title": 16,
        "--type-body": 15,
        "--type-control": 14,
        "--type-support": 14,
        "--type-caption": 13,
        "--type-micro": 13,
        "--type-metric": 24,
        "--type-sequence-code": 14,
    }
    assert {name: int(tokens[name].removesuffix("px")) for name in expected_sizes} == expected_sizes
    assert expected_sizes["--type-page-title"] > expected_sizes["--type-section-title"]
    assert expected_sizes["--type-section-title"] > expected_sizes["--type-subsection-title"]
    assert expected_sizes["--type-subsection-title"] > expected_sizes["--type-card-title"]
    assert expected_sizes["--type-card-title"] > expected_sizes["--type-body"]
    assert expected_sizes["--type-body"] > expected_sizes["--type-control"] >= expected_sizes["--type-micro"]
    assert min(expected_sizes.values()) >= 13
    assert tokens["--type-metric-value"] == "var(--type-metric)"
    assert "--muted2" not in tokens


def test_formal_role_selectors_use_body_support_table_and_button_tokens() -> None:
    assert _style_declarations("p")["font-size"] == "var(--type-body)"
    assert _style_declarations("label")["font-size"] == "var(--type-control)"
    caption = _style_declarations('[data-testid="stCaptionContainer"]')
    assert caption["color"] == "var(--text-support)"
    assert caption["font-size"] == "var(--type-caption)"
    library_head = _style_declarations(".library-head")
    assert {key: library_head[key] for key in ("color", "font-size")} == {
        "color": "var(--text-support)",
        "font-size": "var(--type-micro)",
    }
    library_cell = _style_declarations(".library-cell")
    assert {key: library_cell[key] for key in ("color", "font-size")} == {
        "color": "var(--text-secondary)",
        "font-size": "var(--type-control)",
    }
    assert _style_declarations(".library-badge")["font-size"] == "var(--type-micro)"
    assert _style_declarations(".result-summary-card .label")["font-size"] == "var(--type-micro)"
    style = _global_style_source()
    assert ".results-action-heading" in _app_source()
    assert "font-size: var(--type-card-title);" in _app_source()
    assert ".formal-sidebar-support" in style
    assert "font-size: var(--type-support);" in style


def test_formal_typography_keeps_390px_viewport_text_at_or_above_13px() -> None:
    content = _app_source()
    style_blocks = re.findall(r"<style>(.*?)</style>", content, re.DOTALL)
    declarations = re.findall(
        r"font-size\s*:\s*(?P<number>[0-9]*\.?[0-9]+)(?P<unit>px|rem)",
        "\n".join(style_blocks),
    )

    resolved_pixels = [float(number) * (16 if unit == "rem" else 1) for number, unit in declarations]
    assert resolved_pixels
    assert min(resolved_pixels) >= 13
    assert "@media(max-width: 900px)" in _global_style_source()
    assert "font-size:.59rem" not in content


def test_map_text_rules_preserve_hierarchy_without_global_svg_override() -> None:
    content = _app_source()
    style = _global_style_source()

    assert ".map-frame svg text" not in style
    assert ".map-frame svg .map-feature-label { font-size: var(--type-micro)" in style
    assert ".map-frame svg .map-center-value { font-size: var(--type-section-title)" in style
    assert ".map-frame svg .map-center-label { font-size: var(--type-micro)" in style
    assert "class='map-feature-label' font-size='13'" in content
    assert "class='map-center-value'" in content and "font-size='20'" in content
    assert "class='map-center-label'" in content and "font-size='13'" in content
    assert ".linear-feature" in style and "font-size:var(--type-micro)" in style
    assert "font-size:.59rem" not in style


def test_known_formal_text_pairs_meet_normal_text_contrast() -> None:
    tokens = _root_tokens()

    audited_failing_pairs = {
        "support_on_app_background": (tokens["--text-support"], tokens["--bg"]),
        "disabled_on_disabled_button": (tokens["--text-disabled"], "#e5e7eb"),
        "review_status_on_card": (tokens["--text-warning"], tokens["--surface"]),
        "promoter_tile": ("#ffffff", tokens["--promoter"]),
        "regulatory_region_tile": (tokens["--text-primary"], tokens["--terminator"]),
        "backbone_tile": ("#ffffff", tokens["--backbone"]),
    }
    assert len(audited_failing_pairs) == 6
    assert all(_contrast_ratio(*pair) >= 4.5 for pair in audited_failing_pairs.values())

    # Chromium exposed this previously unproven data-driven map color as another failing pair.
    assert _contrast_ratio("#ffffff", tokens["--origin"]) >= 4.5
    assert ".formal-promoter { background: var(--promoter); color: #ffffff; }" in _global_style_source()
    assert ".formal-terminator { background: var(--terminator); color: var(--text-primary); }" in _global_style_source()
    assert ".formal-backbone { background: var(--backbone); color: #ffffff; }" in _global_style_source()
    style = _global_style_source()
    assert '.linear-feature[style*="#278d87"],' in style
    assert '.linear-feature[style*="rgb(39, 141, 135)"] { background: var(--origin) !important; }' in style


def test_formal_typography_does_not_add_competing_toolbox_or_layout_tokens() -> None:
    tokens = _root_tokens()
    toolbox_source = (Path(ROOT) / "views" / "SequenceToolbox.py").read_text(encoding="utf-8")
    config_source = (Path(ROOT) / ".streamlit" / "config.toml").read_text(encoding="utf-8")

    assert not any(name.startswith(("--width", "--height", "--padding", "--margin", "--gap")) for name in tokens)
    assert "<style>" not in toolbox_source
    assert "TOOL_TYPOGRAPHY_CSS" not in toolbox_source
    assert "--type-" not in config_source
