from __future__ import annotations

import ast
from pathlib import Path

from services.simple_plant_wizard_ui_surface_registry import (
    ADVANCED_REVIEWER_ONLY,
    DEFAULT_BEGINNER_VISIBLE,
    DEVELOPER_DEBUG_ONLY,
    KEEP_BUT_COLLAPSE,
    LEGACY_FROZEN,
    SIMPLE_PLANT_WIZARD_RUNTIME_MARKER,
    build_ui_surface_inventory_summary,
    list_ui_surfaces,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
PLANT_REVIEW_SECTION = ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py"

FORMAL_PAGES = [
    "Project Home",
    "Six-Step Design Workspace",
    "Results and Export",
    "Plant Component Library",
    "Sequence Toolbox",
]
CRISPR_PAGE = "CRISPR V1 Workflow"
AGENT_PAGE = "Agent V1 Workspace"
SIDEBAR_PAGES = [
    "Project Home",
    "Agent V1 Workspace",
    "Six-Step Design Workspace",
    "Plant Component Library",
    "Sequence Toolbox",
    "CRISPR V1 Workflow",
]


def _app_page_assignment(assignment_name: str) -> list[str]:
    tree = ast.parse(APP.read_text(encoding="utf-8"), filename=str(APP))
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


def _string_nodes(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
    _term("vali", "dated"),
    _term("opti", "mized"),
    _term("experiment", "-ready"),
    _term("proto", "col"),
    _term("yield ", "prediction"),
    _term("best ", "component"),
    _term("wet-lab ", "ready"),
    _term("final ", "package"),
    _term("exported ", "package"),
)


def _surface(surface_id: str) -> dict:
    surfaces = {surface["surface_id"]: surface for surface in list_ui_surfaces()}
    assert surface_id in surfaces
    return surfaces[surface_id]


def test_ui_surface_registry_includes_known_beginner_surfaces() -> None:
    surfaces = list_ui_surfaces()
    beginner = {
        surface["surface_id"]: surface
        for surface in surfaces
        if surface["visibility_status"] == DEFAULT_BEGINNER_VISIBLE
    }

    assert {
        "homepage",
        "simple_plant_wizard",
        "my_projects",
        "saved_designs",
        "component_library",
    }.issubset(beginner)
    for surface in beginner.values():
        assert surface["default_visible"] is True
        assert surface["advanced_mode_required"] is False


def test_ui_surface_registry_includes_advanced_frozen_and_developer_surfaces() -> None:
    surfaces = list_ui_surfaces()
    by_status: dict[str, list[dict]] = {}
    for surface in surfaces:
        by_status.setdefault(surface["visibility_status"], []).append(surface)

    assert by_status[ADVANCED_REVIEWER_ONLY]
    assert by_status[LEGACY_FROZEN]
    assert by_status[DEVELOPER_DEBUG_ONLY]
    assert by_status[KEEP_BUT_COLLAPSE]
    assert _surface("expression_wizard")["visibility_status"] == LEGACY_FROZEN
    assert _surface("plant_design_workspace")["visibility_status"] == ADVANCED_REVIEWER_ONLY
    assert _surface("pathway_workspace_advanced_sections")["visibility_status"] == KEEP_BUT_COLLAPSE

    for status in (ADVANCED_REVIEWER_ONLY, LEGACY_FROZEN, DEVELOPER_DEBUG_ONLY, KEEP_BUT_COLLAPSE):
        for surface in by_status[status]:
            assert surface["default_visible"] is False
            assert surface["advanced_mode_required"] is True
            assert surface["freeze_reason_zh"].strip()


def test_ui_surface_registry_returns_plain_deterministic_payload() -> None:
    first = list_ui_surfaces()
    second = list_ui_surfaces()
    summary = build_ui_surface_inventory_summary()

    assert first == second
    assert summary["documentation_only"] is True
    assert summary["runtime_marker"] == SIMPLE_PLANT_WIZARD_RUNTIME_MARKER
    assert summary["surface_count"] == len(first)
    for surface in first:
        assert set(surface) == {
            "surface_id",
            "label_zh",
            "label_en",
            "file_hint",
            "page_key",
            "visibility_status",
            "default_visible",
            "advanced_mode_required",
            "freeze_reason_zh",
            "beginner_replacement_zh",
            "safety_notes_zh",
        }


def test_default_navigation_is_the_formal_v1_surface_and_hides_legacy_entries() -> None:
    app = APP.read_text(encoding="utf-8")

    route_registry = _app_page_assignment("_ALL_PAGES")
    assert route_registry == [*FORMAL_PAGES, CRISPR_PAGE, AGENT_PAGE]
    assert [page for page in route_registry if page not in {CRISPR_PAGE, AGENT_PAGE}] == FORMAL_PAGES
    assert _app_page_assignment("_PRIMARY_NAV_PAGES") == SIDEBAR_PAGES
    assert "for _page in _PRIMARY_NAV_PAGES:" in app
    assert "PAGE_CRISPR_WORKFLOW: PAGE_DESIGN_WORKSPACE" not in app
    assert 'key="formal_open_crispr_product_workflow"' not in app
    assert "基因编辑" in app
    for legacy_page in (
        "Pathway Workspace",
        "Expression Wizard",
        "Expression Constructs",
        "Plant Design Workspace",
        "Design Library",
        "Application Scenario",
        "Simple Plant Wizard",
        "Plant Expression Workspace",
    ):
        assert f'page == "{legacy_page}"' not in app


def test_advanced_reviewer_modules_are_retained_without_formal_routes() -> None:
    app = APP.read_text(encoding="utf-8")

    assert "_ADVANCED_REVIEWER_PAGES" not in app
    assert "_DEVELOPER_DEBUG_PAGES" not in app
    retained_surfaces = {
        "plant_design_workspace": ROOT / "views" / "PlantDesignWorkspace.py",
        "application_scenario": ROOT / "views" / "ApplicationScenario.py",
        "plant_expression_workspace": ROOT / "views" / "Plant_Expression_Workspace.py",
    }
    for surface_id, module_path in retained_surfaces.items():
        assert _surface(surface_id)["default_visible"] is False
        assert module_path.is_file()


def test_simple_plant_wizard_module_is_retained_but_not_formally_mounted() -> None:
    source = PLANT_REVIEW_SECTION.read_text(encoding="utf-8")
    registry_source = (ROOT / "services" / "simple_plant_wizard_ui_surface_registry.py").read_text(encoding="utf-8")

    assert "SIMPLE_PLANT_WIZARD_RUNTIME_MARKER" in source
    assert SIMPLE_PLANT_WIZARD_RUNTIME_MARKER in registry_source
    assert "Simple Plant Wizard" in SIMPLE_PLANT_WIZARD_RUNTIME_MARKER
    assert "Beginner Mode Active" in SIMPLE_PLANT_WIZARD_RUNTIME_MARKER
    assert "R179" in SIMPLE_PLANT_WIZARD_RUNTIME_MARKER
    assert "render_simple_plant_design_wizard_landing" not in APP.read_text(encoding="utf-8")
    assert "Simple Plant Wizard" not in APP.read_text(encoding="utf-8")
    assert "Pathway Workspace" not in APP.read_text(encoding="utf-8")
    assert "render_simple_plant_wizard_homepage_route_cards()" in source
    assert "render_simple_plant_wizard_intake_form_mock()" in source
    assert "render_simple_plant_wizard_route_checklist_section(" in source
    assert "render_simple_plant_wizard_package_entry_section(" in source
    assert "st.subheader(\"Plant Review Workflow\")" in source


def test_default_render_gate_precedes_advanced_readback_and_proof_path() -> None:
    source = PLANT_REVIEW_SECTION.read_text(encoding="utf-8")

    intake_index = source.rindex("render_simple_plant_wizard_intake_form_mock()")
    checklist_index = source.rindex("render_simple_plant_wizard_route_checklist_section(")
    package_entry_index = source.rindex("render_simple_plant_wizard_package_entry_section(")
    gate_index = source.index("if not show_advanced_details:")
    build_workflow_index = source.index("workflow = build_workflow(workspace_state)")
    advanced_index = source.index("with st.expander(PLANT_REVIEW_ADVANCED_DETAIL_EXPANDER_LABEL")
    proof_path_index = source.index("with st.expander(PLANT_REVIEW_PROOF_PATH_EXPANDER_LABEL")
    readback_index = source.index("with st.expander(PLANT_REVIEW_READBACK_EXPANDER_LABEL")

    assert intake_index < checklist_index < package_entry_index < gate_index < build_workflow_index
    assert 'with st.expander("查看需要补充的信息", expanded=False):' in source
    assert 'with st.expander("查看审查包草稿预览", expanded=False):' in source
    assert gate_index < advanced_index < proof_path_index < readback_index
    assert "render_plant_goal_review_package_draft_visible_mvp()" in source
    assert "render_plant_review_handoff_preview_section" in source
    assert "render_rice_albumin_seed_review_visible_mount()" in source


def test_r178_does_not_introduce_write_export_or_persistence_action() -> None:
    registry = (ROOT / "services" / "simple_plant_wizard_ui_surface_registry.py").read_text(encoding="utf-8")
    section = PLANT_REVIEW_SECTION.read_text(encoding="utf-8")

    changed_runtime = f"{registry}\n{section}"
    assert "download_button(" not in changed_runtime
    assert "file_uploader(" not in changed_runtime
    assert "to_sql(" not in changed_runtime
    assert "INSERT INTO" not in changed_runtime
    assert "UPDATE " not in changed_runtime
    assert "DELETE FROM" not in changed_runtime


def test_r178_safety_copy_avoids_forbidden_claims() -> None:
    changed_text = "\n".join(
        value
        for path in (
            ROOT / "services" / "simple_plant_wizard_ui_surface_registry.py",
            PLANT_REVIEW_SECTION,
            APP,
        )
        for value in _string_nodes(path)
    ).casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase not in changed_text
    assert "documentation-only" in changed_text
