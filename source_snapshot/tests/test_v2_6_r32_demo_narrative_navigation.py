from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
HOMEPAGE = ROOT / "views" / "Homepage.py"
PACKAGE_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_documentation_package_section.py"
REPORT_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_review_report_section.py"
QUALITY_SECTION = ROOT / "views" / "pathway_workspace_sections" / "project_quality_dashboard_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _combined_source() -> str:
    return "\n".join(
        _read(path)
        for path in [APP, HOMEPAGE, PACKAGE_SECTION, REPORT_SECTION, QUALITY_SECTION]
    )


def _normalized_source() -> str:
    return " ".join(_combined_source().replace('"\n        "', "").split())


def _user_visible_source_for_claim_scan() -> str:
    source = _combined_source()
    unsafe_tuple_start = source.find("_PROTEIN_EXPRESSION_UNSAFE_PHRASES = (")
    if unsafe_tuple_start == -1:
        return source
    unsafe_tuple_end = source.find(")", unsafe_tuple_start)
    if unsafe_tuple_end == -1:
        return source
    return f"{source[:unsafe_tuple_start]}{source[unsafe_tuple_end + 1:]}"


def test_sidebar_compact_navigation_replaces_r32_helper_captions() -> None:
    source = _read(APP)

    required = [
        'PAGE_PROJECT_HOME = "Project Home"',
        'PAGE_DESIGN_WORKSPACE = "Six-Step Design Workspace"',
        'PAGE_RESULTS_EXPORT = "Results and Export"',
        'PAGE_PLANT_LIBRARY = "Plant Component Library"',
        "for _page in _PRIMARY_NAV_PAGES:",
        "_NAV_LABELS[_page]",
    ]
    missing = [item for item in required if item not in source]
    assert not missing

    removed_sidebar_captions = [
        "_NAV_HELPERS",
        "_render_nav_helper",
        "Start or select pathway documentation project records.",
        "Active project workspace for linked designs, Project Documentation Package, Project Review Report, and Quality Dashboard.",
        "Single gene-level design record subflow.",
        "Saved Expression Wizard design snapshots.",
        "Parts Registry plus metadata-only Local Design Asset Catalog.",
        "Read-only promoter profile documentation context.",
        "Sequence review utilities for documentation context.",
        "Codon usage preview and review context.",
        "_render_sidebar_group(\"Analysis Tools\", _ANALYSIS_TOOL_PAGES)",
        "_render_sidebar_group",
        "Simple Plant Wizard",
        "Show advanced / legacy entries",
    ]
    present = [item for item in removed_sidebar_captions if item in source]
    assert not present


def test_homepage_project_review_workflow_is_visible_and_bounded() -> None:
    source = _read(HOMEPAGE)

    required = [
        "PROJECT_REVIEW_WORKFLOW_BOUNDARY_COPY",
        "PROJECT_REVIEW_WORKFLOW_STEPS",
        "Expression Vector Design Package Workflow",
        "Create an expression design record",
        "Attach project review context when needed",
        "Review component source context",
        "Inspect gaps and follow-up notes",
        "Prepare the design package readback",
        "local documentation review only",
    ]
    missing = [item for item in required if item not in source]
    assert not missing


def test_r32_workspace_output_panels_have_navigation_cues() -> None:
    source = _normalized_source()

    required = [
        "Navigation cue: this panel is the Project Documentation Package surface",
        "package preview, manifest metadata review, and documentation-only package exchange context",
        "Import Manifest Review belongs to the Project Documentation Package workflow",
        "Project Review Report is a Project Outputs review surface",
        "linked design records, manifest/package exchange context, and human review prompts",
        "Project Quality Dashboard is a Project Outputs review surface",
        "Documentation-only dashboard for completeness, consistency, provenance, package exchange context, and missing-reference review prompts",
    ]
    missing = [item for item in required if item not in source]
    assert not missing


def test_r32_copy_avoids_high_risk_claim_terms() -> None:
    source = _user_visible_source_for_claim_scan().lower()
    forbidden = [
        "approved",
        "recommended",
        "safe for use",
        "compatible host",
        "ready for synthesis",
        "ready for wet " + "lab",
        "experimentally confirmed",
    ]

    present = [item for item in forbidden if item in source]
    assert not present
