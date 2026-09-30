from __future__ import annotations

import copy
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as streamlit_module

from services.pathway_report_service import PathwayReportConfig
from tests.helpers.fake_streamlit import FakeStreamlit
import views.PathwayWorkspace as pathway_workspace
import views.pathway_workspace_sections.export_package_section as export_package_section
import views.pathway_workspace_sections.linked_artifacts_section as linked_artifacts_section
import views.pathway_workspace_sections.overview_summary_section as overview_summary_section
import views.pathway_workspace_sections.project_quality_dashboard_section as project_quality_dashboard_section
import views.pathway_workspace_sections.project_review_report_section as project_review_report_section
import views.pathway_workspace_sections.review_signals_section as review_signals_section

FORBIDDEN = [
    "This is the bottleneck",
    "Bottleneck identified",
    "Yield will improve",
    "Predicted production",
    "Predicted yield",
    "Automatically optimized pathway",
    "Ready for Experimental Use",
    "Experimental Ready",
    "Recommended optimization",
]


def _project() -> dict:
    return {
        "id": 5,
        "name": "Terpene Pathway",
        "target_product": "Demo Product",
        "host": "E.coli",
        "description": "",
        "status": "draft",
        "documentation_review": {
            "review_items": {
                "pathway_description_reviewed": True,
                "gene_entries_reviewed": False,
                "linked_expression_designs_reviewed": True,
                "suggestions_reviewed": False,
                "test_records_reviewed": True,
                "markdown_documentation_report_reviewed": True,
                "unresolved_documentation_items_reviewed": False,
            },
            "reviewer_name_or_initials": "AB",
            "review_date": "2026-05-22",
            "review_notes": "Review note for UI test.",
            "follow_up_actions": "Follow-up note for UI test.",
            "unresolved_items": "Unresolved note for UI test.",
            "last_updated": "2026-05-22T10:30:00",
            "review_scope": "Local documentation review",
            "review_context": "UI integration test",
        },
    }


def _step() -> dict:
    return {
        "id": 10,
        "project_id": 5,
        "step_order": 1,
        "step_name": "First step",
        "reaction_name": "Demo reaction",
        "substrate": "A",
        "product": "B",
        "enzyme_name": "Demo enzyme",
        "gene_name": "demo_gene",
        "gene_sequence": "ATGAAACCCTAA",
        "organism_source": "Demo organism",
        "notes": "",
    }


def _signal() -> dict:
    return {
        "signal_type": "missing_expression_design",
        "priority": "medium_review",
        "scope": "step-level",
        "related_step_id": 10,
        "evidence": {"step_id": 10},
        "message": "Review the documented expression design link for this step.",
        "suggested_next_check": "Review documentation completeness.",
        "boundary_note": "Documentation-only review signal.",
    }


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(pathway_workspace, "st", fake_st)
    monkeypatch.setattr(export_package_section, "st", fake_st)
    monkeypatch.setattr(linked_artifacts_section, "st", fake_st)
    monkeypatch.setattr(overview_summary_section, "st", fake_st)
    monkeypatch.setattr(project_quality_dashboard_section, "st", fake_st)
    monkeypatch.setattr(project_review_report_section, "st", fake_st)
    monkeypatch.setattr(review_signals_section, "st", fake_st)
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)
    fake_artifacts = lambda project_id=None, **kwargs: [
        {
            "created_at": "2026-06-02T10:00:00",
            "artifact_type": "protein_structure_analysis",
            "title": "Structure Preview",
            "source_module": "Structure Analysis",
            "summary": "Documentation preview summary",
            "boundary_label": "Documentation artifact / computational preview record only.",
            "project_id": project_id,
        }
    ]
    monkeypatch.setattr(pathway_workspace, "list_tool_artifacts", fake_artifacts)
    monkeypatch.setattr(export_package_section, "list_tool_artifacts", fake_artifacts)
    monkeypatch.setattr(linked_artifacts_section, "list_tool_artifacts", fake_artifacts)
    monkeypatch.setattr(project_quality_dashboard_section, "list_tool_artifacts", fake_artifacts)
    monkeypatch.setattr(project_review_report_section, "list_tool_artifacts", fake_artifacts)
    return fake_st


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.warning_messages
        + fake_st.success_messages
        + fake_st.write_messages
        + fake_st.tab_labels
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [call["label"] for call in fake_st.button_calls]
        + [call["label"] for call in fake_st.download_button_calls]
        + [call["label"] for call in fake_st.file_uploader_calls]
    )


def test_project_outputs_guide_is_concise_and_actionable() -> None:
    guide = pathway_workspace.PROJECT_OUTPUTS_GUIDE_COPY
    boundary = pathway_workspace.PROJECT_OUTPUTS_BOUNDARY_COPY

    assert len(guide) <= 190
    assert guide.count(";") == 3
    for action in [
        "Save documentation snapshot",
        "Download documentation report",
        "Build / review documentation-only export package",
        "Review import package preview",
    ]:
        assert action in guide

    assert "Documentation-only boundary" in boundary
    assert "do not validate experiments" in boundary
    assert "certify readiness" in boundary
    assert "predict yield" in boundary
    assert "optimize pathways" in boundary
    assert "choose actions" in boundary
    assert "wet-lab guidance" in boundary


def test_linked_tool_artifact_rows_and_boundary_copy(monkeypatch):
    artifact = {
        "created_at": "2026-06-02T10:00:00",
        "artifact_type": "protein_structure_analysis",
        "title": "Structure Preview",
        "source_module": "Structure Analysis",
        "summary": "Documentation preview summary",
        "boundary_label": "Documentation artifact / computational preview record only.",
        "payload_json": {"ignored": True},
    }
    calls = []
    monkeypatch.setattr(
        linked_artifacts_section,
        "list_tool_artifacts",
        lambda project_id=None, **kwargs: calls.append(project_id) or [artifact],
    )

    rows = linked_artifacts_section._linked_tool_artifact_rows(5)

    assert calls == [5]
    assert rows == [{
        "created_at": "2026-06-02T10:00:00",
        "artifact_type": "protein_structure_analysis",
        "title": "Structure Preview",
        "source_module": "Structure Analysis",
        "summary": "Documentation preview summary",
        "linked_project_context": "Pathway Project 5",
        "review_location": "Pathway Workspace / Linked Documentation Artifacts",
        "boundary_label": "Documentation artifact / computational preview record only.",
    }]
    assert "documentation references only" in linked_artifacts_section.LINKED_TOOL_ARTIFACT_BOUNDARY_COPY
    assert "do not certify experimental readiness" in linked_artifacts_section.LINKED_TOOL_ARTIFACT_BOUNDARY_COPY
    assert "predict yield" in linked_artifacts_section.LINKED_TOOL_ARTIFACT_BOUNDARY_COPY
    assert "optimize pathways" in linked_artifacts_section.LINKED_TOOL_ARTIFACT_BOUNDARY_COPY
    assert "review saved tool outputs in the active pathway project context" in linked_artifacts_section.LINKED_TOOL_ARTIFACT_REVIEW_CONTEXT_COPY
    assert "not validation" in linked_artifacts_section.LINKED_TOOL_ARTIFACT_REVIEW_CONTEXT_COPY
    assert "not wet-lab protocol" in linked_artifacts_section.LINKED_TOOL_ARTIFACT_REVIEW_CONTEXT_COPY


def test_report_download_trigger_appears_and_uses_existing_in_memory_data(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    project = _project()
    steps = [_step()]
    expression_links = [{"id": 100, "step_id": 10, "design_id": 77, "design_name": "Linked design"}]
    test_records = [{"id": 200, "step_id": 10, "sample_name": "Observation"}]
    completeness = {"score": 88, "status": "partial", "missing_items": ["one"], "step_summaries": []}
    current_review_signals = [_signal()]
    snapshots = copy.deepcopy((project, steps, expression_links, test_records, completeness, current_review_signals))
    calls = []

    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: project)
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: steps)
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: expression_links)
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: test_records)
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda p, s, links: completeness)
    monkeypatch.setattr(pathway_workspace, "build_pathway_review_signals", lambda p, s, links, records: current_review_signals)

    def fake_report_service(*args, **kwargs):
        calls.append({"args": args, "kwargs": kwargs})
        return "# Pathway Documentation Report\n"

    monkeypatch.setattr(pathway_workspace, "generate_pathway_markdown_report", fake_report_service)
    monkeypatch.setattr(export_package_section, "generate_pathway_markdown_report", fake_report_service)
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5

    pathway_workspace.render(lambda page_name: None)

    assert len(fake_st.download_button_calls) >= 2
    download_call = fake_st.download_button_calls[0]
    assert download_call["label"] == "Download Documentation Report"
    assert download_call["data"] == "# Pathway Documentation Report\n"
    assert download_call["file_name"] == "pathway_report_terpene_pathway.md"
    assert download_call["mime"] == "text/markdown"
    export_call = next(
        call for call in fake_st.download_button_calls if call["label"] == "Download Project Export Package"
    )
    review_call = next(
        call for call in fake_st.download_button_calls if call["label"] == "Download Project Review Report (.md)"
    )
    assert review_call["mime"] == "text/markdown"
    assert export_call["file_name"].startswith("pathway_project_export_terpene_pathway_")
    assert export_call["mime"] == "application/zip"
    assert calls == [
        {
            "args": (project, steps, expression_links, test_records, completeness, current_review_signals),
            "kwargs": {"generated_at": None, "config": PathwayReportConfig()},
        },
        {
            "args": (project, steps, expression_links, test_records, completeness, current_review_signals),
            "kwargs": {"generated_at": None, "config": PathwayReportConfig()},
        },
    ]
    assert (project, steps, expression_links, test_records, completeness, current_review_signals) == snapshots


def test_report_ui_copy_is_documentation_only_and_forbidden_wording_absent(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [_step()])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(
        pathway_workspace,
        "build_pathway_completeness",
        lambda project, steps, links: {"score": 88, "status": "partial", "missing_items": [], "step_summaries": []},
    )
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5

    pathway_workspace.render(lambda page_name: None)

    ui_text = _rendered_text(fake_st)
    source_text = open(pathway_workspace.__file__, encoding="utf-8").read()
    export_source_text = open(export_package_section.__file__, encoding="utf-8").read()
    normalized_source_text = " ".join(f"{source_text}\n{export_source_text}".split())
    ui_and_source_text = f"{ui_text}\n{normalized_source_text}"
    export_section_source = export_source_text
    assert "Documentation Report" in ui_text
    assert "Project Export Package" in ui_text
    assert "Download a documentation-only Markdown report" in ui_text
    assert "Markdown documentation review output" in ui_text
    assert "Documentation-only package summary" in ui_text
    assert "Download Project Export Package" in ui_text
    assert "recorded project data, pathway steps, linked designs, test records, completeness coverage, and review signals" in ui_text
    assert "does not certify experimental readiness" in ui_text
    for project_outputs_phrase in [
        "Output actions",
        "Save documentation snapshot",
        "Download documentation report",
        "Build / review documentation-only export package",
        "Review import package preview",
        "Documentation-only boundary",
        "Quality Review: review documentation completeness",
        "Build / review documentation-only export package: inspect package contents",
        "Review import package preview: inspect package structure",
        "Package/report contents",
        "local documentation records, summaries, linked record references, traceability context, and review context only",
        "does not change export package schema, report payload schema, import/export behavior, or stored documentation snapshot schema",
    ]:
        assert project_outputs_phrase in ui_text
    guide_text = pathway_workspace.PROJECT_OUTPUTS_GUIDE_COPY
    assert len(guide_text) <= 190
    for action in [
        "Save documentation snapshot",
        "Download documentation report",
        "Build / review documentation-only export package",
        "Review import package preview",
    ]:
        assert action in guide_text
    for required_phrase in [
        "Project Export Package",
        "Download Project Export Package",
        "Package contents preview",
        "Project summary",
        "Pathway steps",
        "Test records summary",
        "Linked expression designs",
        "Linked tool artifacts",
        "Linked tool artifacts: 1",
        "Documentation report",
        "Boundary README",
        "documentation-only",
        "package structure checks",
        "review and traceability",
    ]:
        assert required_phrase in ui_and_source_text
    export_section_source_lower = export_section_source.lower()
    for safe_boundary_phrase in [
        "this export does not certify experimental readiness, predict yield, optimize pathways, or provide wet-lab instructions",
        "no readiness, yield, optimization, or protocol claims",
        "does not provide wet-lab protocols",
    ]:
        assert safe_boundary_phrase in export_section_source_lower
    for forbidden_positive_claim in [
        "experimental readiness certification",
        "yield prediction available",
        "yield prediction result",
        "pathway optimization available",
        "wet-lab protocol generated",
        "ready for execution",
        "fabrication-ready",
        "execution-ready",
    ]:
        assert forbidden_positive_claim not in export_section_source
    for phrase in FORBIDDEN:
        assert phrase not in ui_text


def test_project_export_package_preview_negative_copy_absent(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [_step()])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(
        pathway_workspace,
        "build_pathway_completeness",
        lambda project, steps, links: {"score": 88, "status": "partial", "missing_items": [], "step_summaries": []},
    )
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5

    pathway_workspace.render(lambda page_name: None)

    ui_text = _rendered_text(fake_st)
    preview_text = ui_text.split("Package contents preview", 1)[1].split("Review import package preview", 1)[0]
    preview_text_without_negative_boundary = preview_text
    for allowed_negative_boundary in [
        "does not provide wet-lab protocols",
        "does not generate wet-lab protocols",
    ]:
        preview_text_without_negative_boundary = preview_text_without_negative_boundary.replace(allowed_negative_boundary, "")
    for forbidden_phrase in [
        "experimental readiness certification",
        "yield prediction",
        "pathway optimization",
        "wet-lab protocol",
    ]:
        assert forbidden_phrase not in preview_text_without_negative_boundary


def test_project_import_package_preview_copy_and_boundaries(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [_step()])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(
        pathway_workspace,
        "build_pathway_completeness",
        lambda project, steps, links: {"score": 88, "status": "partial", "missing_items": [], "step_summaries": []},
    )
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5

    pathway_workspace.render(lambda page_name: None)

    ui_text = _rendered_text(fake_st)
    assert "Project Import Package Preview" in ui_text
    assert "Upload Project Export Package (.zip)" in ui_text
    assert "documentation-only" in ui_text
    assert "read-only" in ui_text
    assert "does not import or modify any project" in ui_text
    assert "No database writes are performed" in ui_text
    assert "does not certify experimental readiness" in ui_text
    assert "does not predict yield" in ui_text
    assert "does not optimize pathways" in ui_text
    assert "does not provide wet-lab protocols" in ui_text
    labels = "\n".join([call["label"] for call in fake_st.button_calls] + [call["label"] for call in fake_st.download_button_calls])
    for forbidden_label in ["Import Project", "Create Imported Project", "Merge Project", "Overwrite Project"]:
        assert forbidden_label not in labels


def test_project_import_package_preview_uses_validator_and_renders_report(monkeypatch):
    class UploadedZip:
        def getvalue(self) -> bytes:
            return b"zip-bytes"

    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.file_uploader_value = UploadedZip()
    calls = []
    monkeypatch.setattr(
        pathway_workspace,
        "validate_project_import_package",
        lambda zip_bytes: calls.append(zip_bytes) or {
            "is_valid": True,
            "errors": [],
            "warnings": ["Review package metadata before any future import workflow."],
            "package_version": "1.0",
            "project_name": "Preview Project",
            "included_files": ["manifest.json", "README_BOUNDARY.txt"],
            "boundary_confirmed": True,
            "json_files_valid": True,
            "unsafe_files": [],
        },
    )

    pathway_workspace._render_import_package_preview()

    ui_text = _rendered_text(fake_st)
    assert calls == [b"zip-bytes"]
    assert "Valid package" in ui_text
    assert "package_version: 1.0" in ui_text
    assert "project_name: Preview Project" in ui_text
    assert "boundary_confirmed: True" in ui_text
    assert "json_files_valid: True" in ui_text
    assert "manifest.json" in ui_text
    assert "No validation errors found." in ui_text
    assert "Review package metadata before any future import workflow." in ui_text
    assert "No unsafe files detected." in ui_text


def test_project_import_package_preview_static_read_only_guarantees():
    source_text = open(pathway_workspace.__file__, encoding="utf-8").read()
    assert "from services.project_import_package_validator import validate_project_import_package" in source_text
    import_preview_source = source_text.split("def _render_import_package_preview", 1)[1].split("def _safe_int", 1)[0]
    assert "validate_project_import_package" in import_preview_source
    for forbidden_call in [
        "create_pathway_project(",
        "create_pathway_step(",
        "create_pathway_test_record(",
        "update_pathway_project(",
        "update_pathway_step(",
        "update_pathway_test_record(",
        "delete_pathway_step(",
        "delete_pathway_test_record(",
        "insert(",
        "update(",
        "delete(",
        "commit(",
    ]:
        assert forbidden_call not in import_preview_source
    for forbidden_label in ["Import Project", "Create Imported Project", "Merge Project", "Overwrite Project"]:
        assert forbidden_label not in import_preview_source
    for forbidden_phrase in [
        "experimental readiness certification",
        "yield prediction",
        "pathway optimization",
    ]:
        assert forbidden_phrase not in import_preview_source
    assert "does not provide wet-lab protocols" in import_preview_source


def test_report_ui_does_not_persist_suggestions_or_change_completeness_or_wizard_launch(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    project = _project()
    steps = [_step()]
    completeness = {"score": 88, "status": "partial", "missing_items": ["one"], "step_summaries": []}
    suggestions = [_signal()]
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: project)
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: steps)
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda p, s, links: completeness)
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: suggestions)
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5

    pathway_workspace.render(lambda page_name: None)

    assert "Open in Expression Wizard" in [call["label"] for call in fake_st.button_calls]
    rendered_summary = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)
    assert "Documentation coverage" in rendered_summary
    assert ">88%<" in rendered_summary
    assert "pathway_suggestions" not in fake_st.session_state
    assert all("suggestion" not in str(key).lower() for key in fake_st.session_state)
    assert fake_st.rerun_calls == 0


def _render_report_with_real_service(monkeypatch, checkbox_values: dict[str, bool] | None = None) -> tuple[FakeStreamlit, dict]:
    fake_st = _install_fake_streamlit(monkeypatch)
    if checkbox_values:
        fake_st.checkbox_values.update(checkbox_values)
    project = _project()
    steps = [_step()]
    expression_links = [
        {
            "id": 100,
            "step_id": 10,
            "design_id": 77,
            "design_name": "Linked design",
            "primer_risk": "not recommended primer risk remains recorded",
        }
    ]
    test_records = [{"id": 200, "step_id": 10, "sample_name": "Observation"}]
    completeness = {"score": 88, "status": "partial", "missing_items": ["one"], "step_summaries": []}
    suggestions = [_signal()]

    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: project)
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: steps)
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: expression_links)
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: test_records)
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda p, s, links: completeness)
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: suggestions)
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5

    pathway_workspace.render(lambda page_name: None)

    return fake_st, project


def _downloaded_report(fake_st: FakeStreamlit) -> str:
    assert fake_st.download_button_calls
    return fake_st.download_button_calls[0]["data"]


def test_markdown_report_options_expander_and_safety_description_appear(monkeypatch):
    fake_st, _project_data = _render_report_with_real_service(monkeypatch)

    assert {call["label"] for call in fake_st.expander_calls} >= {"Markdown Report Options"}
    assert any(
        "Choose optional sections for this Markdown report only. Required documentation-only, readiness, limitation, "
        "and primer-risk language cannot be disabled." in message
        for message in fake_st.caption_messages
    )


def test_all_report_option_checkboxes_have_expected_defaults(monkeypatch):
    fake_st, _project_data = _render_report_with_real_service(monkeypatch)

    expected_defaults = {
        "Include project metadata": True,
        "Include pathway step details": True,
        "Include linked Expression Wizard design summaries": True,
        "Include Test Records": True,
        "Include review signals": True,
        "Include Review Notes": True,
        "Include full gene sequences": False,
    }
    calls_by_label = {call["label"]: call for call in fake_st.checkbox_calls}
    for label, expected_value in expected_defaults.items():
        assert calls_by_label[label]["value"] is expected_value
    assert calls_by_label["Include full gene sequences"]["help"] == (
        "Includes complete gene sequence text in the Markdown report. Use caution when sharing reports."
    )


def test_toggling_options_changes_generated_markdown_content(monkeypatch):
    fake_st, _project_data = _render_report_with_real_service(
        monkeypatch,
        {
            "pathway_report_include_project_metadata": False,
            "pathway_report_include_pathway_steps": False,
            "pathway_report_include_linked_designs": False,
            "pathway_report_include_test_records": False,
            "pathway_report_include_suggestions": False,
            "pathway_report_include_review_notes": False,
        },
    )
    report = _downloaded_report(fake_st)

    assert "## Project Summary" not in report
    assert "## Pathway Steps" not in report
    assert "## Linked Expression Wizard Design Summary" not in report
    assert "## Test Records Summary" not in report
    assert "## Suggestions / Review Signals Summary" not in report
    assert "## User-Authored Documentation Review Notes" not in report
    assert "Some optional documentation sections were omitted by user selection" in report
    assert "## Documentation-Only Boundary Statement" in report
    assert "## Known Limitations" in report


def test_disabling_suggestions_omits_section_but_keeps_mandatory_safety(monkeypatch):
    fake_st, _project_data = _render_report_with_real_service(
        monkeypatch,
        {"pathway_report_include_suggestions": False},
    )
    report = _downloaded_report(fake_st)

    assert "## Suggestions / Review Signals Summary" not in report
    assert "Review the documented expression design link for this step." not in report
    assert "This report is documentation-only" in report
    assert "does not certify experimental readiness" in report
    assert "## Known Limitations" in report


def test_disabling_test_records_omits_records_but_keeps_completeness(monkeypatch):
    fake_st, _project_data = _render_report_with_real_service(
        monkeypatch,
        {"pathway_report_include_test_records": False},
    )
    report = _downloaded_report(fake_st)

    assert "## Test Records Summary" not in report
    assert "Observation" not in report
    assert "## Completeness Summary" in report
    assert "| Score | 88% |" in report


def test_disabling_review_notes_omits_section_without_mutating_review_data(monkeypatch):
    fake_st, project = _render_report_with_real_service(
        monkeypatch,
        {"pathway_report_include_review_notes": False},
    )
    report = _downloaded_report(fake_st)

    assert "## User-Authored Documentation Review Notes" not in report
    assert "Review note for UI test." not in report
    assert project["documentation_review"]["review_notes"] == "Review note for UI test."


def test_enabling_full_gene_sequences_includes_sequence_text(monkeypatch):
    fake_st, _project_data = _render_report_with_real_service(
        monkeypatch,
        {"pathway_report_include_full_gene_sequences": True},
    )
    report = _downloaded_report(fake_st)

    assert "ATGAAACCCTAA" in report
    assert "Full gene sequence text was user-selected for this Markdown report" in report
    assert "does not certify experimental readiness" in report


def test_default_options_preserve_existing_report_output_behavior(monkeypatch):
    fake_st, _project_data = _render_report_with_real_service(monkeypatch)
    report = _downloaded_report(fake_st)

    assert "## Project Summary" in report
    assert "## Pathway Steps" in report
    assert "## Linked Expression Wizard Design Summary" in report
    assert "## Test Records Summary" in report
    assert "## Suggestions / Review Signals Summary" in report
    assert "## User-Authored Documentation Review Notes" in report
    assert "ATGAAACCCTAA" not in report
    assert "Recorded (12 nt)" in report
    assert "Some optional documentation sections were omitted by user selection" not in report


def test_ui_options_are_not_persisted_to_project_data(monkeypatch):
    fake_st, project = _render_report_with_real_service(
        monkeypatch,
        {
            "pathway_report_include_suggestions": False,
            "pathway_report_include_full_gene_sequences": True,
        },
    )

    assert "report_config" not in project
    assert "markdown_report_options" not in project
    assert "saved_report_configuration" not in project
    assert all("report_config" not in str(key) for key in fake_st.session_state)
    assert all("markdown_report_options" not in str(key) for key in fake_st.session_state)


def test_no_report_save_default_template_or_non_markdown_export_controls_appear(monkeypatch):
    fake_st, _project_data = _render_report_with_real_service(monkeypatch)
    labels = "\n".join(
        [call["label"] for call in fake_st.button_calls]
        + [call["label"] for call in fake_st.download_button_calls]
        + [call["label"] for call in fake_st.checkbox_calls]
        + [call["label"] for call in fake_st.expander_calls]
    )

    forbidden_labels = [
        "Save report configuration",
        "Save defaults",
        "Template",
        "Report history",
        "PDF",
        "DOCX",
        "HTML",
    ]
    for label in forbidden_labels:
        assert label not in labels
    assert fake_st.download_button_calls[0]["mime"] == "text/markdown"
    assert fake_st.download_button_calls[0]["file_name"].endswith(".md")


def test_report_download_still_works_with_options(monkeypatch):
    fake_st, _project_data = _render_report_with_real_service(
        monkeypatch,
        {"pathway_report_include_project_metadata": False},
    )
    call = fake_st.download_button_calls[0]

    assert call["label"] == "Download Documentation Report"
    assert call["data"].startswith("# Pathway Documentation Report")
    assert "## Project Summary" not in call["data"]
    assert call["mime"] == "text/markdown"


def test_no_positive_approval_readiness_certification_claims_appear(monkeypatch):
    fake_st, _project_data = _render_report_with_real_service(monkeypatch)
    ui_and_report_text = "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.warning_messages
        + fake_st.success_messages
        + fake_st.write_messages
        + fake_st.tab_labels
        + [call["label"] for call in fake_st.button_calls]
        + [call["label"] for call in fake_st.download_button_calls]
        + [_downloaded_report(fake_st)]
    ).lower()

    forbidden_positive_claims = [
        "approved for experimental use",
        "certifies experimental readiness",
        "certified ready",
        "validated for experimental use",
        "predicts improved yield",
        "optimization recommendation",
        "this report confirms bottlenecks",
    ]
    for phrase in forbidden_positive_claims:
        assert phrase not in ui_and_report_text
