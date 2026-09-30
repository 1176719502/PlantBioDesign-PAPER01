from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"
APP_SOURCE = APP_PATH.read_text(encoding="utf-8")
APP_TREE = ast.parse(APP_SOURCE)

EXPECTED_ROUTES = {
    "PAGE_PROJECT_HOME": "Project Home",
    "PAGE_DESIGN_WORKSPACE": "Six-Step Design Workspace",
    "PAGE_RESULTS_EXPORT": "Results and Export",
    "PAGE_PLANT_LIBRARY": "Plant Component Library",
    "PAGE_SEQUENCE_TOOLBOX": "Sequence Toolbox",
    "PAGE_CRISPR_WORKFLOW": "CRISPR V1 Workflow",
    "PAGE_AGENT_WORKSPACE": "Agent V1 Workspace",
}
EXPECTED_PRIMARY_NAV = (
    "PAGE_PROJECT_HOME",
    "PAGE_AGENT_WORKSPACE",
    "PAGE_DESIGN_WORKSPACE",
    "PAGE_PLANT_LIBRARY",
    "PAGE_SEQUENCE_TOOLBOX",
    "PAGE_CRISPR_WORKFLOW",
)
EXPECTED_LABELS = {
    "PAGE_PROJECT_HOME": "项目中心",
    "PAGE_DESIGN_WORKSPACE": "表达设计",
    "PAGE_AGENT_WORKSPACE": "智能设计",
    "PAGE_CRISPR_WORKFLOW": "CRISPR",
    "PAGE_PLANT_LIBRARY": "元件库",
    "PAGE_SEQUENCE_TOOLBOX": "序列工具",
}


def _assignment(name: str) -> ast.expr:
    node = next(
        item
        for item in APP_TREE.body
        if isinstance(item, ast.Assign)
        and len(item.targets) == 1
        and isinstance(item.targets[0], ast.Name)
        and item.targets[0].id == name
    )
    return node.value


def _name_sequence(name: str) -> tuple[str, ...]:
    value = _assignment(name)
    assert isinstance(value, (ast.List, ast.Tuple))
    assert all(isinstance(item, ast.Name) for item in value.elts)
    return tuple(item.id for item in value.elts)


def _name_to_literal_dict(name: str) -> dict[str, str]:
    value = _assignment(name)
    assert isinstance(value, ast.Dict)
    assert all(isinstance(key, ast.Name) for key in value.keys)
    return {
        key.id: ast.literal_eval(item)
        for key, item in zip(value.keys, value.values, strict=True)
    }


def _name_to_name_dict(name: str) -> dict[str, str]:
    value = _assignment(name)
    assert isinstance(value, ast.Dict)
    assert all(isinstance(key, ast.Name) for key in value.keys)
    assert all(isinstance(item, ast.Name) for item in value.values)
    return {
        key.id: item.id
        for key, item in zip(value.keys, value.values, strict=True)
    }


def _function(name: str) -> ast.FunctionDef:
    return next(
        item
        for item in APP_TREE.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )


def _function_source(name: str) -> str:
    return ast.get_source_segment(APP_SOURCE, _function(name)) or ""


def _navigation_namespace() -> dict[str, Any]:
    namespace: dict[str, Any] = {
        **EXPECTED_ROUTES,
        "ValueError": ValueError,
    }
    nodes = [
        next(
            item
            for item in APP_TREE.body
            if isinstance(item, ast.Assign)
            and isinstance(item.targets[0], ast.Name)
            and item.targets[0].id == name
        )
        for name in ("_PRIMARY_NAV_PAGES", "_PRIMARY_NAV_ROUTE_ALIASES")
    ]
    nodes.append(_function("_primary_navigation_page"))
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace


def test_primary_navigation_has_exactly_six_ordered_entries() -> None:
    assert _name_sequence("_PRIMARY_NAV_PAGES") == EXPECTED_PRIMARY_NAV
    assert _name_to_literal_dict("_NAV_LABELS") == EXPECTED_LABELS


def test_brand_and_page_header_copy_matches_primary_navigation() -> None:
    sidebar = APP_SOURCE.split("with st.sidebar:", 1)[1].split("# Page router", 1)[0]
    project_home = _function_source("_render_project_home")
    workspace = _function_source("_render_design_workspace")
    component_library = _function_source("_render_plant_component_library")

    assert "植物生物设计" in sidebar
    assert "本地化植物合成生物学设计平台" in sidebar
    assert "植物表达载体设计</div>" not in sidebar

    assert 'st.title("项目中心")' in project_home
    assert 'st.caption("创建、保存和管理植物表达设计项目")' in project_home
    assert 'st.title("植物表达载体设计")' not in project_home

    assert 'st.title("表达设计")' in workspace
    assert 'st.caption("按步骤完成植物表达载体设计")' in workspace
    assert 'st.title("植物表达载体设计工作区")' not in workspace

    assert 'st.title("元件库")' in component_library
    assert 'st.title("植物元件库")' not in component_library
    assert '"植物表达设计元件目录 · V1 · "' in component_library
    assert 'f"权威 Registry {len(registry_records)} 条 · "' in component_library
    assert 'f"经复核目录候选 {len(candidate_records)} 条"' in component_library
    assert "records = _formal_library_display_records(_plant_library_records())" in component_library


def test_primary_navigation_exposes_crispr_but_no_unavailable_entry() -> None:
    labels = set(_name_to_literal_dict("_NAV_LABELS").values())
    assert "CRISPR" in labels
    assert labels.isdisjoint(
        {
            "CRISPR设计",
            "AI辅助规划",
            "知识库",
            "Results",
            "Gate 3",
            "Multi-TU",
            "Historical Preview",
        }
    )


def test_internal_formal_route_ids_include_crispr_compatibility_route() -> None:
    assignments = {
        node.targets[0].id: ast.literal_eval(node.value)
        for node in APP_TREE.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id.startswith("PAGE_")
    }
    assert assignments == EXPECTED_ROUTES
    assert _name_sequence("_ALL_PAGES") == tuple(EXPECTED_ROUTES)


def test_display_labels_map_to_existing_formal_routes() -> None:
    route_by_label = {
        label: EXPECTED_ROUTES[route_name]
        for route_name, label in _name_to_literal_dict("_NAV_LABELS").items()
    }
    assert route_by_label == {
        "项目中心": "Project Home",
        "表达设计": "Six-Step Design Workspace",
        "智能设计": "Agent V1 Workspace",
        "CRISPR": "CRISPR V1 Workflow",
        "元件库": "Plant Component Library",
        "序列工具": "Sequence Toolbox",
    }


def test_compatibility_routes_have_closed_primary_aliases() -> None:
    assert _name_to_name_dict("_PRIMARY_NAV_ROUTE_ALIASES") == {
        "PAGE_RESULTS_EXPORT": "PAGE_DESIGN_WORKSPACE",
    }


def test_every_formal_route_resolves_to_exactly_one_primary_entry() -> None:
    namespace = _navigation_namespace()
    resolve = namespace["_primary_navigation_page"]

    assert resolve("Project Home") == "Project Home"
    assert resolve("Six-Step Design Workspace") == "Six-Step Design Workspace"
    assert resolve("Results and Export") == "Six-Step Design Workspace"
    assert resolve("Plant Component Library") == "Plant Component Library"
    assert resolve("Sequence Toolbox") == "Sequence Toolbox"
    assert resolve("CRISPR V1 Workflow") == "CRISPR V1 Workflow"
    assert resolve("Agent V1 Workspace") == "Agent V1 Workspace"
    with pytest.raises(ValueError, match="Unknown formal page route"):
        resolve("Unknown")


def test_sidebar_renders_only_primary_entries_and_uses_route_selected_state() -> None:
    sidebar = APP_SOURCE.split("with st.sidebar:", 1)[1].split("# Page router", 1)[0]

    assert "for _page in _PRIMARY_NAV_PAGES:" in sidebar
    assert "基因编辑" in sidebar
    assert set(_name_to_literal_dict("_NAV_LABELS")) == set(EXPECTED_PRIMARY_NAV)
    assert "_cur = _primary_navigation_page(page)" in APP_SOURCE
    assert 'type="primary" if _cur == _page else "secondary"' in sidebar


def test_legacy_results_route_still_redirects_to_step_six() -> None:
    change_page = _function_source("_change_page")
    compatibility_block = APP_SOURCE.split("page = st.session_state[_SK.SELECTED_PAGE]", 1)[1].split(
        "with st.sidebar:", 1
    )[0]

    for source in (change_page, compatibility_block):
        assert "PAGE_RESULTS_EXPORT" in source
        assert "PAGE_DESIGN_WORKSPACE" in source
        assert 'st.session_state["formal_step_preview"] = True' in source
    assert "ds.step = 6" in change_page


def test_workspace_modes_and_historical_preview_remain_inside_expression_design() -> None:
    workspace = _function_source("_render_design_workspace")
    preview = _function_source("_render_result_preview_mode")

    assert "_is_result_preview_mode()" in workspace
    assert "_render_result_preview_mode()" in workspace
    assert "历史结果预览" in preview
    assert "PAGE_GATE3" not in APP_SOURCE
    assert "PAGE_MULTI_TU" not in APP_SOURCE
    assert "PAGE_HISTORICAL_PREVIEW" not in APP_SOURCE
    assert "formal_crispr_product_entry" not in workspace


def test_session_and_query_restore_continue_to_use_internal_routes() -> None:
    from core.page_routing import reconcile_selected_page_from_query

    pages = list(EXPECTED_ROUTES.values())
    for route in pages:
        state = {"selected_page": "Project Home"}
        selected = reconcile_selected_page_from_query(
            state,
            {"page": route},
            pages,
            selected_page_key="selected_page",
            default_page="Project Home",
        )
        assert selected == route
        assert state["selected_page"] == route


def test_router_keeps_existing_renderers_and_adds_crispr_product_renderer() -> None:
    router = APP_SOURCE.split("# Page router", 1)[1]
    expected = {
        "PAGE_PROJECT_HOME": "_render_project_home()",
        "PAGE_DESIGN_WORKSPACE": "_render_design_workspace()",
        "PAGE_RESULTS_EXPORT": "_render_results_export()",
        "PAGE_PLANT_LIBRARY": "_render_plant_component_library()",
        "PAGE_SEQUENCE_TOOLBOX": "render_sequence_toolbox()",
        "PAGE_CRISPR_WORKFLOW": "_render_crispr_product_workflow()",
    }
    for route, renderer in expected.items():
        assert f"page == {route}" in router
        assert renderer in router
    crispr_renderer = _function_source("_render_crispr_product_workflow")
    assert "from views.CrisprWorkspace import render" in crispr_renderer


def test_page_transition_updates_both_route_sources_before_rerunning() -> None:
    change_page = _function_source("_change_page")

    selected_page_write = change_page.index("st.session_state[_SK.SELECTED_PAGE] = target")
    query_write = change_page.index('st.query_params["page"] = target')
    rerun = change_page.index("st.rerun()")
    assert selected_page_write < rerun
    assert query_write < rerun


def test_mobile_sidebar_contract_prevents_primary_label_overflow() -> None:
    style = APP_SOURCE.split("<style>", 1)[1].split("</style>", 1)[0]
    sidebar_rule = style.split('[data-testid="stSidebar"] {', 1)[1].split("}", 1)[0]
    button_rule = style.split(
        '[data-testid="stSidebar"] [data-testid="stButton"] > button {', 1
    )[1].split("}", 1)[0]

    assert "overflow-x: hidden !important;" in sidebar_rule
    assert "width: 100% !important;" in button_rule
    assert "min-width: 0 !important;" in button_rule
    assert "white-space: nowrap !important;" in button_rule
    assert '[data-testid="stSidebarCollapseButton"]' in style
    assert "pointer-events: auto !important;" in style


def test_navigation_contract_adds_no_permissive_fallback_or_test_bypass() -> None:
    navigation_contract = APP_SOURCE.split("_PRIMARY_NAV_PAGES =", 1)[1].split(
        "# Session state initialisation", 1
    )[0]

    assert "globals().get(" not in navigation_contract
    assert "except NameError" not in navigation_contract
    assert "lambda:" not in navigation_contract
    bypass_attributes = {
        node.attr
        for node in ast.walk(ast.parse(Path(__file__).read_text(encoding="utf-8")))
        if isinstance(node, ast.Attribute)
    }
    assert bypass_attributes.isdisjoint({"skip", "skipif", "xfail"})
