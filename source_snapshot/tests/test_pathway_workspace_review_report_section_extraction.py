from __future__ import annotations

import copy
from pathlib import Path

from services.project_review_report_service import build_project_review_report
from tests.helpers.fake_streamlit import FakeStreamlit
import views.pathway_workspace_sections.project_review_report_section as review_report_section

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTIONS_DIR = ROOT / "views" / "pathway_workspace_sections"
SECTION = SECTIONS_DIR / "project_review_report_section.py"
PROJECT_OUTPUTS_SECTION = SECTIONS_DIR / "project_outputs_section.py"
SERVICE = ROOT / "services" / "project_review_report_service.py"
PACKAGE_TRAIL_SERVICE = ROOT / "services" / "project_package_review_trail_service.py"
PROJECT_OUTPUT_BOUNDARY_COPY = ROOT / "services" / "project_output_boundary_copy.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section_sources() -> str:
    return (
        _read(SECTION)
        + "\n"
        + _read(SERVICE)
        + "\n"
        + _read(PACKAGE_TRAIL_SERVICE)
        + "\n"
        + _read(PROJECT_OUTPUT_BOUNDARY_COPY)
    )


def test_section_module_exists() -> None:
    assert SECTION.exists()


def test_pathway_workspace_imports_and_calls_review_report_section() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    section_source = _read(PROJECT_OUTPUTS_SECTION)
    assert "from views.pathway_workspace_sections.project_review_report_section import render_project_review_report_section" in workspace_source
    assert "render_project_review_report_section=render_project_review_report_section" in workspace_source
    review_index = section_source.index("render_project_review_report_section(")
    call_block = section_source[review_index : section_source.index(")", review_index)]
    assert "project," in call_block
    assert "steps," in call_block
    assert "expression_links=expression_links" in call_block
    assert "test_records=test_records" in call_block
    assert "snapshots=snapshots" in call_block
    assert "review_signals=review_signals" in call_block
    assert "completeness_result=completeness_result" in call_block
    assert "project_catalog_links = persisted_project_links(project.get(\"id\"))" in section_source
    assert "linked_catalog_assets=project_catalog_links" in call_block
    assert "def _render_project_review_report_section" not in workspace_source


def test_project_review_report_copy_preserved() -> None:
    source = _section_sources()
    required = [
        "Project Review Report",
        "Generate Project Review Report",
        "Download Project Review Report (.md)",
        "No active pathway project selected.",
        "Select a pathway documentation workspace to generate a Project Review Report.",
        "Expression construct documentation",
        "Construct records",
        "Package Exchange Review Trail",
        "Workflow context",
        "Project Review Report and Project Quality Dashboard",
    ]
    for text in required:
        assert text in source


def test_project_review_report_boundary_copy_preserved() -> None:
    source = _section_sources()
    required = [
        "This report is documentation-only.",
        "This report summarizes review records and computational previews only.",
        "local, read-only, documentation-only Project Outputs review surface for manual review",
        "not a biology-use recommendation, validation claim, optimization claim, or wet-lab use judgment",
        "does not recommend, rank, score, validate, optimize, predict, or judge downstream-use state",
        "This report does not forecast yield.",
        "This report does not tune pathways.",
        "This report does not provide wet-lab instructions.",
        "Linked catalog assets are documentation references only.",
        "They do not indicate biological fit, source verification, or downstream use state.",
        "Human review is required before downstream use.",
        "Expression construct documentation is documentation-only context for review and traceability.",
        "Promoter source links are evidence and provenance context, not selection advice.",
        "Import Preview remains read-only.",
        "Blocked / NO-GO import states apply only to the gated create-as-new action.",
    ]
    for text in required:
        assert text in source


def test_project_review_report_no_project_guard_renders_empty_state_without_service_calls(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)

    def _unexpected_list_tool_artifacts(*_args, **_kwargs):
        raise AssertionError("list_tool_artifacts should not run without an active project")

    def _unexpected_build_project_review_report(*_args, **_kwargs):
        raise AssertionError("build_project_review_report should not run without an active project")

    monkeypatch.setattr(review_report_section, "list_tool_artifacts", _unexpected_list_tool_artifacts)
    monkeypatch.setattr(review_report_section, "build_project_review_report", _unexpected_build_project_review_report)

    review_report_section.render_project_review_report_section(None)
    rendered = "\n".join(fake_st.subheaders + fake_st.info_messages + fake_st.caption_messages).lower()

    assert "project review report" in rendered
    assert "no active pathway project selected" in rendered
    assert "select a pathway documentation workspace" in rendered
    assert fake_st.metric_calls == []
    assert fake_st.dataframes == []


def test_no_forbidden_import_execution_strings() -> None:
    source = _read(PATHWAY_WORKSPACE) + "\n" + _read(SECTION)
    forbidden = [
        "enable_database_write" + "=True",
        "execute_project_import" + "_as_new_project",
        "Import" + " Project",
        "Execute" + " Import",
        "Confirm" + " Import",
        "Import" + " now",
        "Ready" + " to import",
        "Ready" + " for execution",
        "Quality" + " Score",
        "Evidence" + " Score",
        "Readiness" + " Score",
        "Validation" + " Score",
        "Experiment" + " Ready",
        "Production" + " Ready",
        "validated" + " construct",
        "successful" + " cloning",
        "successful" + " PCR",
        "successful" + " expression",
        "optimized" + " pathway",
        "yield" + " prediction",
    ]
    for text in forbidden:
        assert text not in source


def test_report_service_output_structure_not_modified_by_extraction() -> None:
    project = {
        "id": 101,
        "name": "Demo Project",
        "target_product": "Demo product",
        "host": "Demo host",
        "status": "draft",
    }
    linked_artifacts = [{"id": 7, "title": "Artifact", "artifact_type": "review", "project_id": 101}]
    export_summary = {
        "status": "AVAILABLE",
        "package_contents_preview_status": "AVAILABLE",
        "last_export_status": "NOT_AVAILABLE",
        "documentation_only_boundary": "Project export packages are documentation-only review packages.",
    }

    before_project = copy.deepcopy(project)
    report = build_project_review_report(
        project,
        linked_artifacts=linked_artifacts,
        saved_designs=None,
        export_summary=export_summary,
        import_safety_summary=None,
    )

    assert project == before_project
    expected_keys = {
        "report_version",
        "generated_at",
        "overall_summary",
        "project_identity",
        "project_summary",
        "pathway_steps_summary",
        "linked_artifacts_summary",
        "saved_design_snapshot_summary",
        "expression_construct_documentation",
        "export_package_summary",
        "import_safety_summary",
        "package_exchange_review_trail",
        "missing_fields",
        "review_notes",
        "known_limitations",
        "boundary_notes",
        "next_steps",
        "markdown",
    }
    assert expected_keys.issubset(report.keys())
    assert isinstance(report["markdown"], str)
    assert isinstance(report["boundary_notes"], list)
