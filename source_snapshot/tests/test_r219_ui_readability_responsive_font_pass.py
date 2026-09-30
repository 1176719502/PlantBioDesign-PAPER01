from __future__ import annotations

from pathlib import Path

from core import module_registry
from views import ApplicationScenario

ROOT = Path(__file__).resolve().parents[1]

UI_FILES = [
    ROOT / "views" / "Homepage.py",
    ROOT / "views" / "ApplicationScenario.py",
    ROOT / "views" / "Dashboard.py",
    ROOT / "views" / "Data.py",
    ROOT / "views" / "ExpressionConstructs.py",
    ROOT / "views" / "tool_typography.py",
    ROOT / "views" / "pathway_workspace_sections" / "project_quality_dashboard_section.py",
    ROOT / "views" / "pathway_workspace_sections" / "project_review_report_section.py",
    ROOT / "services" / "project_output_boundary_copy.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _combined_source() -> str:
    return "\n".join(_read(path) for path in UI_FILES)


def test_shared_typography_helper_raises_readability_and_responsive_layout_hooks() -> None:
    source = _read(ROOT / "views" / "tool_typography.py")

    required = [
        ".tool-title",
        ".tool-subtitle",
        ".tool-boundary-note",
        ".tool-help-text",
        ".tool-summary-grid",
        "grid-template-columns:repeat(auto-fit,minmax(160px,1fr))",
        "@media (max-width: 760px)",
        "overflow-wrap:anywhere",
    ]
    missing = [text for text in required if text not in source]

    assert not missing


def test_homepage_and_dashboard_keep_narrow_screen_readability_hooks() -> None:
    homepage = _read(ROOT / "views" / "Homepage.py")
    dashboard = _read(ROOT / "views" / "Dashboard.py")

    for text in [
        "@media (max-width: 900px)",
        ".homepage-root .hp-workflow-step",
        "overflow-wrap: anywhere",
        "Application Scenario",
        'btn_label = f"Open {m[\'name\']} ->"',
    ]:
        assert text in homepage

    for text in [
        "flex-wrap:wrap",
        "@media (max-width: 760px)",
        ".pw-preview",
        "overflow-wrap:anywhere",
    ]:
        assert text in dashboard


def test_application_scenario_remains_reachable_and_scan_friendly() -> None:
    source = _read(ROOT / "views" / "ApplicationScenario.py")
    entry = module_registry.get_by_route_key("Application Scenario")
    text = ApplicationScenario.scenario_text()

    assert entry is not None
    assert entry["id"] == "application_scenario"
    assert "application-scenario-list" in source
    assert "application-scenario-flow" in source
    assert "Open Pathway Projects" in source
    assert "Biological workflow" in text
    assert "Documentation/review only" in text


def test_key_review_surfaces_render_readable_boundary_helper_blocks() -> None:
    quality = _read(ROOT / "views" / "pathway_workspace_sections" / "project_quality_dashboard_section.py")
    report = _read(ROOT / "views" / "pathway_workspace_sections" / "project_review_report_section.py")

    for text in [
        "Readability note: review the summary metrics first",
        "Boundary: {PROJECT_QUALITY_DASHBOARD_BOUNDARY_COPY}",
        "Summary of existing local documentation records for review context only",
        "_render_readability_note",
    ]:
        assert text in quality

    for text in [
        "Readability note: start with Report summary",
        "Boundary: {PROJECT_REVIEW_REPORT_BOUNDARY_COPY}",
        "PROJECT_OUTPUT_SCOPE_NOTE",
        "Documentation report draft for the research to catalog to design to review to report workflow.",
        "_render_readability_note",
    ]:
        assert text in report


def test_r219_ui_copy_keeps_documentation_only_boundary_and_avoids_unsafe_claims() -> None:
    combined = _combined_source().lower()

    required_safe_copy = [
        "documentation-only",
        "local project workspace",
        "design record",
        "import preview",
        "export package",
        "human review",
    ]
    missing_safe_copy = [phrase for phrase in required_safe_copy if phrase not in combined]

    forbidden_positive_claims = [
        "automatic optimization",
        "guaranteed expression",
        "yield " + "prediction",
        "clinical readiness",
        "product readiness",
        "replacement of expert review",
        "replaces expert review",
        "successful " + "import",
        "project " + "imported",
        "ready for " + "execution",
        "experiment" + "-ready",
        "production" + "-ready",
        "validated " + "construct",
        "optimized " + "pathway",
        "wet-lab ready",
        "wet-lab readiness confirmed",
        "is wet-lab readiness",
        "proven construct",
        "validated " + "pathway",
    ]
    present_forbidden = [phrase for phrase in forbidden_positive_claims if phrase in combined]

    assert not missing_safe_copy
    assert not present_forbidden
