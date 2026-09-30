from __future__ import annotations

from pathlib import Path

from tests.helpers.fake_streamlit import FakeStreamlit
import views.pathway_workspace_sections.project_quality_dashboard_section as quality_dashboard_section

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTIONS_DIR = ROOT / "views" / "pathway_workspace_sections"
SECTION = SECTIONS_DIR / "project_quality_dashboard_section.py"
PROJECT_OUTPUTS_SECTION = SECTIONS_DIR / "project_outputs_section.py"
SECTION_INIT = SECTIONS_DIR / "__init__.py"
SERVICE = ROOT / "services" / "project_quality_dashboard_service.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _dashboard_sources() -> str:
    return _read(SECTION) + "\n" + _read(SERVICE)


def test_section_module_exists() -> None:
    assert SECTION.exists()
    assert SECTION_INIT.exists()


def test_pathway_workspace_delegates_dashboard_section() -> None:
    workspace_source = _read(PATHWAY_WORKSPACE)
    project_outputs_source = _read(PROJECT_OUTPUTS_SECTION)
    dashboard_sources = _dashboard_sources()

    assert "from views.pathway_workspace_sections.project_quality_dashboard_section import (" in workspace_source
    assert "render_project_handoff_review_workspace_section," in workspace_source
    assert "render_project_quality_dashboard_section," in workspace_source
    assert "render_project_quality_dashboard_section=render_project_quality_dashboard_section" in workspace_source
    assert "render_project_quality_dashboard_section(" in project_outputs_source
    assert "expression_links=expression_links" in project_outputs_source
    assert "snapshots=snapshots" in project_outputs_source
    assert "review_signals=review_signals" in project_outputs_source
    assert "Project Quality Dashboard" in dashboard_sources
    assert "overall documentation status" in dashboard_sources


def test_no_disallowed_multi_section_extraction() -> None:
    forbidden_modules = [
        "pathway_steps_section.py",
        "delete_confirmation_section.py",
    ]
    for module_name in forbidden_modules:
        assert not (SECTIONS_DIR / module_name).exists()


def test_section_copy_preserved() -> None:
    source = _dashboard_sources()
    required = [
        "Project Quality Dashboard",
        "documentation review summary",
        "overall documentation status",
        "pathway steps count",
        "linked artifacts count",
        "saved design snapshot status",
        "export package status",
        "import safety check status",
        "review gaps count",
        "review guidance",
        "Documentation Consistency / Provenance",
        "documentation consistency",
        "provenance context",
        "source/provenance review",
        "record review status",
        "human review needed",
        "Component Library promoter asset reference summary",
        "Component Library promoter asset references are documentation context only.",
        "No Component Library promoter asset reference summary is available.",
        "Linked promoter asset reference count",
        "Component Library promoter asset reference count",
        "Generic Component Library asset readback",
        "build_component_library_asset_readback_presenter",
        "Read-only generic Component Library asset readback",
        "does not create a universal asset database model",
        "asset readback rows",
    ]
    for text in required:
        assert text in source


def test_boundary_copy_preserved() -> None:
    source = _dashboard_sources()
    required = [
        "This dashboard summarizes documentation completeness only.",
        "It does not certify experiment-use state.",
        "It does not forecast yield.",
        "It does not tune pathways.",
        "It does not provide wet-lab instructions.",
        "Import Preview remains read-only.",
        "Blocked / NO-GO import states apply only to the gated create-as-new action",
    ]
    for text in required:
        assert text in source


def test_quality_dashboard_no_project_guard_renders_empty_state_without_service_calls(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(quality_dashboard_section, "st", fake_st)

    def _unexpected_list_tool_artifacts(*_args, **_kwargs):
        raise AssertionError("list_tool_artifacts should not run without an active project")

    monkeypatch.setattr(quality_dashboard_section, "list_tool_artifacts", _unexpected_list_tool_artifacts)

    quality_dashboard_section.render_project_quality_dashboard_section(None)
    rendered = "\n".join(fake_st.subheaders + fake_st.info_messages + fake_st.caption_messages).lower()

    assert "project quality dashboard" in rendered
    assert "no active pathway project selected" in rendered
    assert "select a pathway documentation workspace" in rendered
    assert fake_st.metric_calls == []
    assert fake_st.dataframes == []


def test_import_safety_unaffected() -> None:
    source = _read(PATHWAY_WORKSPACE) + "\n" + _read(SECTION)
    forbidden = [
        "enable_database_write=True",
        "execute_project_import_as_new_project",
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Import now",
        "Ready to import",
        "Ready" + " for execution",
    ]
    for text in forbidden:
        assert text not in source


def test_no_misleading_score_labels() -> None:
    source = _read(PATHWAY_WORKSPACE) + "\n" + _read(SECTION)
    forbidden = [
        "Quality Score",
        "Evidence Score",
        "Readiness Score",
        "Validation Score",
        "Experiment Ready",
        "Production Ready",
        "next recommended actions",
        "analysis review summary",
    ]
    for text in forbidden:
        assert text not in source
