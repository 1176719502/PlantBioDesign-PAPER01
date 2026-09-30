from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
HOMEPAGE = ROOT / "views" / "Homepage.py"
PATHWAY_PROJECTS = ROOT / "views" / "PathwayProjects.py"
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
PROJECT_OUTPUTS_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py"
PROJECT_REPORT_DOWNLOAD_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_report_download_section.py"
OVERVIEW_SECTION = ROOT / "views" / "pathway_workspace_sections" / "overview_summary_section.py"
REVIEW_SIGNALS_SECTION = ROOT / "views" / "pathway_workspace_sections" / "review_signals_section.py"
MODULE_REGISTRY = ROOT / "core" / "module_registry.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _term(*parts: str) -> str:
    return "".join(parts)


def test_r111_demo_navigation_keeps_hidden_routes_out_of_visible_navigation() -> None:
    app_source = _read(APP)
    registry_source = _read(MODULE_REGISTRY)

    formal_block = app_source.split("_ALL_PAGES = [", 1)[1].split("]", 1)[0]
    registered_pages = tuple(re.findall(r"\bPAGE_[A-Z_]+\b", formal_block))
    visible_formal_pages = (
        "PAGE_PROJECT_HOME",
        "PAGE_DESIGN_WORKSPACE",
        "PAGE_RESULTS_EXPORT",
        "PAGE_PLANT_LIBRARY",
        "PAGE_SEQUENCE_TOOLBOX",
    )
    assert registered_pages == (*visible_formal_pages, "PAGE_CRISPR_WORKFLOW", "PAGE_AGENT_WORKSPACE")
    assert tuple(page for page in registered_pages if page not in {"PAGE_CRISPR_WORKFLOW", "PAGE_AGENT_WORKSPACE"}) == visible_formal_pages

    primary_block = app_source.split("_PRIMARY_NAV_PAGES = (", 1)[1].split(")", 1)[0]
    assert tuple(re.findall(r"\bPAGE_[A-Z_]+\b", primary_block)) == (
        "PAGE_PROJECT_HOME",
        "PAGE_AGENT_WORKSPACE",
        "PAGE_DESIGN_WORKSPACE",
        "PAGE_PLANT_LIBRARY",
        "PAGE_SEQUENCE_TOOLBOX",
        "PAGE_CRISPR_WORKFLOW",
    )
    assert "for _page in _PRIMARY_NAV_PAGES:" in app_source
    assert "PAGE_CRISPR_WORKFLOW: PAGE_DESIGN_WORKSPACE" not in app_source
    assert 'key="formal_open_crispr_product_workflow"' not in app_source
    assert "基因编辑" in app_source
    for hidden_route in (
        "Sequence Tools",
        "Codon Optimizer",
        "AI Literature Research",
        "Module Overview",
        "Assembly & Cloning",
        "Structure Analysis",
        "Lab Tools",
    ):
        assert hidden_route not in formal_block
        assert f'page == "{hidden_route}"' not in app_source

    assert '"layer": "hidden"' in registry_source
    assert '"status": "hidden"' in registry_source
    assert "not shown in sidebar or Homepage" in registry_source
    assert "future-facing local research brief surface retained outside visible product navigation." in registry_source.lower()



def test_r111_demo_entry_flow_copy_stays_documentation_only() -> None:
    combined = "\n".join(
        [
            _read(HOMEPAGE),
            _read(PATHWAY_PROJECTS),
            _read(PATHWAY_WORKSPACE),
            _read(PROJECT_OUTPUTS_SECTION),
            _read(PROJECT_REPORT_DOWNLOAD_SECTION),
            _read(OVERVIEW_SECTION),
            _read(REVIEW_SIGNALS_SECTION),
        ]
    ).lower()

    required = [
        "documentation-only",
        "pathway projects",
        "pathway workspace",
        "expression wizard",
        "design preparation",
        "import preview",
        "export package",
        "traceability",
    ]
    for term in required:
        assert term in combined

    assert "primary expression vector design preparation path" in combined
    assert "open pathway workspace to review linked expression wizard design records" in combined
    assert "open expression wizard" in combined
    assert "expression vector design records need optional project grouping" in combined
    assert "it is not a biological recommendation, not an experimental validation, and not a wet-lab readiness judgment." in combined
    assert "preview is read-only: no database writes, overwrite, merge, restore, or project creation during preview." in combined


def test_r111_demo_surfaces_do_not_present_positive_high_risk_product_claims() -> None:
    combined = "\n".join(
        [
            _read(APP),
            _read(HOMEPAGE),
            _read(PATHWAY_PROJECTS),
            _read(PATHWAY_WORKSPACE),
        ]
    ).lower()

    forbidden_phrases = [
        _term("ready ", "for execution"),
        _term("experiment", "-ready"),
        _term("production", "-ready"),
        _term("vali", "dated ", "construct"),
        _term("opti", "mized ", "pathway"),
        _term("experimentally ", "confirmed"),
        _term("host ", "suitability"),
        _term("wet-lab ", "ready"),
        _term("yield ", "prediction"),
        _term("project ", "imported"),
        _term("successful ", "import"),
    ]
    for phrase in forbidden_phrases:
        assert phrase not in combined


def test_r111_homepage_project_review_workflow_keeps_current_user_facing_scope() -> None:
    source = _read(HOMEPAGE)

    required = [
        "Expression Vector Design Package Workflow",
        "Create an expression design record",
        "Attach project review context when needed",
        "Review component source context",
        "Inspect gaps and follow-up notes",
        "Prepare the design package readback",
        "local documentation review only",
        "does not claim biological validation",
        "host compatibility",
        "wet-lab use",
    ]
    missing = [item for item in required if item not in source]
    assert not missing
