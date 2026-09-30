from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
REGISTRY = ROOT / "core" / "module_registry.py"
OVERVIEW = ROOT / "views" / "pathway_workspace_sections" / "overview_summary_section.py"
LINKED_CATALOG_ASSETS = ROOT / "views" / "pathway_workspace_sections" / "linked_catalog_assets_section.py"
QUALITY_DASHBOARD = ROOT / "views" / "pathway_workspace_sections" / "project_quality_dashboard_section.py"
DESIGN_LIBRARY = ROOT / "views" / "DesignLibrary.py"
CODON_USAGE_PREVIEW = ROOT / "views" / "CodonOptimizer.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _app_page_assignment(assignment_name: str) -> list[str]:
    tree = ast.parse(_read(APP), filename=str(APP))
    constants: dict[str, str] = {}
    page_nodes: ast.List | ast.Tuple | None = None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            constants[target.id] = node.value.value
        elif target.id == assignment_name and isinstance(node.value, (ast.List, ast.Tuple)):
            page_nodes = node.value
    assert page_nodes is not None
    assert all(isinstance(item, ast.Name) for item in page_nodes.elts)
    return [constants[item.id] for item in page_nodes.elts]


def _registry_modules() -> list[dict]:
    tree = ast.parse(_read(REGISTRY))
    assignment = next(
        node
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "MODULE_REGISTRY"
    )
    return ast.literal_eval(assignment.value)


def test_r227_sidebar_navigation_order_matches_user_workflow() -> None:
    expected_formal_surface = [
        "Project Home",
        "Six-Step Design Workspace",
        "Results and Export",
        "Plant Component Library",
        "Sequence Toolbox",
    ]
    expected_sidebar_order = [
        "Project Home",
        "Agent V1 Workspace",
        "Six-Step Design Workspace",
        "Plant Component Library",
        "Sequence Toolbox",
        "CRISPR V1 Workflow",
    ]

    route_registry = _app_page_assignment("_ALL_PAGES")
    assert route_registry == [*expected_formal_surface, "CRISPR V1 Workflow", "Agent V1 Workspace"]
    assert [page for page in route_registry if page not in {"CRISPR V1 Workflow", "Agent V1 Workspace"}] == expected_formal_surface
    assert _app_page_assignment("_PRIMARY_NAV_PAGES") == expected_sidebar_order
    app_source = _read(APP)
    assert "for _page in _PRIMARY_NAV_PAGES:" in app_source
    assert "PAGE_CRISPR_WORKFLOW: PAGE_DESIGN_WORKSPACE" not in app_source

    workflow_routes = [
        module["route_key"]
        for module in _registry_modules()
        if module.get("category") == "workflow" and module.get("status") == "active"
    ]
    assert workflow_routes[:4] == [
        "Application Scenario",
        "Pathway Projects",
        "Pathway Workspace",
        "Plant Design Workspace",
    ]
    assert workflow_routes[:5] == [
        "Application Scenario",
        "Pathway Projects",
        "Pathway Workspace",
        "Plant Design Workspace",
        "Expression Wizard",
    ]


def test_r227_legacy_modules_remain_retained_but_not_formally_reachable() -> None:
    source = _read(APP)
    registry_routes = {module["route_key"] for module in _registry_modules()}
    legacy_routes = [
        "Application Scenario",
        "Pathway Projects",
        "Plant Design Workspace",
        "Pathway Workspace",
        "Expression Wizard",
        "Data",
        "Sequence Tools",
        "Codon Optimizer",
        "Module Overview",
        "AI Literature Research",
    ]
    for route in legacy_routes:
        assert route in registry_routes
        assert f'page == "{route}"' not in source
    assert (ROOT / "views" / "DesignLibrary.py").is_file()
    assert 'page == "Design Library"' not in source


def test_r227_overview_and_linked_catalog_summaries_use_compact_cards() -> None:
    overview = _read(OVERVIEW)
    project_status = overview.split("def _render_project_status_summary", 1)[1].split("def _step_evidence_matrix_rows", 1)[0]
    catalog_overview = overview.split("def _render_catalog_reference_overview_panel", 1)[1].split("def render_overview_summary_section", 1)[0]
    linked_assets = _read(LINKED_CATALOG_ASSETS).split("st.markdown(\"**Linked catalog assets summary**\")", 1)[1].split("if summary.get(\"by_asset_type\")", 1)[0]

    for section in [project_status, catalog_overview, linked_assets]:
        assert "render_compact_summary_cards" in section
        assert ".metric(" not in section

    assert "Documentation coverage" in project_status
    assert "Missing documentation items" in project_status
    assert "Linked catalog references" in catalog_overview
    assert "Total linked assets" in linked_assets


def test_r227_quality_dashboard_top_summary_uses_compact_cards() -> None:
    source = _read(QUALITY_DASHBOARD)
    top_summary = source.split("st.markdown(\"**documentation review summary**\")", 1)[1].split("host_context_status = dashboard.get", 1)[0]

    assert top_summary.count("render_compact_summary_cards") == 2
    assert '.metric("documentation status"' not in top_summary
    assert '.metric("pathway steps count"' not in top_summary
    assert '.metric("linked artifacts count"' not in top_summary
    assert '.metric("review gaps count"' not in top_summary
    assert "Documentation status" in top_summary
    assert "Pathway steps count" in top_summary


def test_r227_design_library_and_codon_preview_stay_compact() -> None:
    design_library = _read(DESIGN_LIBRARY)
    design_detail = design_library.split("def _render_detail", 1)[1].split("def render", 1)[0]
    codon_usage = _read(CODON_USAGE_PREVIEW)

    assert "render_compact_summary_cards" in design_detail
    assert ".metric(" not in design_detail
    assert "st.metric" not in codon_usage
