from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as streamlit_module

from core.design_session import DesignSession
from services import project_catalog_asset_link_repository
from services.pathway_traceability_view_model import traceability_summary_counts
from services.pathway_wizard_context import PATHWAY_WIZARD_CONTEXT_KEY
from tests.helpers.fake_streamlit import FakeStreamlit
import views.PathwayWorkspace as pathway_workspace
import views.pathway_workspace_sections.overview_summary_section as overview_summary_section
import views.pathway_workspace_sections.review_signals_section as review_signals_section
import views.pathway_workspace_sections.traceability_section as traceability_section
import views.wizard_steps.step6_export as step6_export


def _project():
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
                "linked_expression_designs_reviewed": False,
                "suggestions_reviewed": False,
                "test_records_reviewed": False,
                "markdown_documentation_report_reviewed": False,
                "unresolved_documentation_items_reviewed": False,
            },
            "reviewer_name_or_initials": "AB",
            "review_date": "2026-05-22",
            "review_notes": "Existing note",
            "follow_up_actions": "Existing follow-up",
            "unresolved_items": "Existing unresolved item",
            "last_updated": "",
            "review_scope": "",
            "review_context": "",
        },
    }


def _step(**overrides):
    data = {
        "id": 10,
        "project_id": 5,
        "step_order": 1,
        "step_name": "First step",
        "reaction_name": "Demo reaction",
        "substrate": "A",
        "product": "B",
        "enzyme_name": "Demo enzyme",
        "gene_name": "demo_gene",
        "gene_sequence": "atg aaa ccc taa",
        "organism_source": "Demo organism",
        "notes": "",
    }
    data.update(overrides)
    return data


def _install_fake_streamlit(monkeypatch):
    fake_st = FakeStreamlit()
    monkeypatch.setattr(pathway_workspace, "st", fake_st)
    monkeypatch.setattr(overview_summary_section, "st", fake_st)
    monkeypatch.setattr(review_signals_section, "st", fake_st)
    monkeypatch.setattr(traceability_section, "st", fake_st)
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)
    return fake_st


def _make_signal(signal_type="linked_design_validation_risk", priority="high_review", scope="step-level", related_step_id=10):
    return {
        "signal_type": signal_type,
        "priority": priority,
        "scope": scope,
        "related_step_id": related_step_id,
        "evidence": {"step_id": related_step_id, "design_id": 77, "warning_count": 1},
        "message": "Recorded validation notes suggest this linked design should be reviewed before the next design iteration.",
        "suggested_next_check": "Review validation warnings, blocking issues, and primer risk notes for the linked expression design.",
        "boundary_note": "Documentation-only recommendation. This does not change primer risk status or certify experimental use.",
    }


def _render_workspace(monkeypatch, fake_st, steps, expression_links=None, test_records=None):
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: list(steps))
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: list(expression_links or []))
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: list(test_records or []))
    page_calls = []

    def change_page(page_name: str):
        page_calls.append(page_name)

    monkeypatch.setattr(pathway_workspace, "update_pathway_documentation_review", lambda *args, **kwargs: (True, "ok"))
    pathway_workspace.render(change_page)
    return page_calls


def test_workspace_import_preview_discovery_points_to_project_outputs(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[{"step_id": 10, "design_id": 77}], test_records=[])

    rendered_text = "\n".join(
        fake_st.tab_labels
        + fake_st.subheaders
        + fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )

    for phrase in [
        "Review import package",
        "Pathway Workspace > Project Outputs > Import Preview",
        "documentation-only package inspection for validation and dry-run planning",
        "preview does not create a project, overwrite, or merge existing projects",
        "separate gated import-as-new action",
        "Import Preview",
    ]:
        assert phrase in rendered_text

    for forbidden in [
        "ready for execution",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "experiment-ready",
        "production-ready",
        "wet-lab protocol provided",
    ]:
        assert forbidden not in rendered_text.lower()


def test_review_notes_tab_renders_required_documentation_ui(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[{"step_id": 10, "design_id": 77}], test_records=[])

    rendered_text = "\n".join(
        fake_st.tab_labels
        + fake_st.subheaders
        + fake_st.caption_messages
        + [call["label"] for call in fake_st.checkbox_calls]
        + [call["label"] for call in fake_st.button_calls]
    )
    assert "Review Notes" in fake_st.tab_labels
    assert "Documentation Review Notes" in fake_st.subheaders
    assert "Manual Review Checklist" in fake_st.subheaders
    assert "Review Notes are human-authored documentation review notes for unresolved questions" in rendered_text
    assert "source review, documentation gaps, and manual follow-up notes" in rendered_text
    assert "They are not an ELN, protocol, approval workflow" in rendered_text
    for label in [
        "Pathway description reviewed for documentation completeness",
        "Gene entries reviewed for documentation completeness",
        "Linked Expression Wizard designs reviewed for documentation completeness",
        "Review signals reviewed as documentation-only prompts",
        "Test Records reviewed",
        "Markdown Documentation Report reviewed",
        "Unresolved documentation items and follow-up actions reviewed",
    ]:
        assert label in rendered_text
    assert any(call["label"] == "Save documentation review notes" for call in fake_st.button_calls)
    assert any(
        "Documentation review notes do not change completeness score, review signals, Wizard validation" in message
        for message in fake_st.caption_messages
    )


def test_review_notes_fields_and_safe_help_text_render(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(monkeypatch, fake_st, [_step()])

    reviewer_call = next(
        call for call in fake_st.text_input_calls if call["label"] == "Reviewer name or initials"
    )
    date_call = next(call for call in fake_st.text_input_calls if call["label"] == "Review date")
    text_area_labels = [call["label"] for call in fake_st.text_area_calls]
    placeholders = "\n".join(str(call.get("placeholder") or "") for call in fake_st.text_area_calls)

    assert reviewer_call["help"] == "Optional user-authored documentation field. This is not an electronic signature."
    assert date_call["help"] == "Optional documentation review date. This is not a validation or approval date."
    assert "Review notes" in text_area_labels
    assert "Follow-up actions" in text_area_labels
    assert "Unresolved documentation items" in text_area_labels
    assert "Add user-authored notes about the documentation review scope, assumptions, limitations, or context." in placeholders
    assert "Add documentation follow-up items. These do not block or unblock supporting preview workspace behavior." in placeholders
    assert "Do not record these as confirmed bottlenecks unless independently established outside this tool." in placeholders


def test_forbidden_review_notes_wording_is_absent(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(monkeypatch, fake_st, [_step()])

    review_notes_text = "\n".join(
        [label for label in fake_st.tab_labels if label == "Review Notes"]
        + fake_st.subheaders
        + fake_st.caption_messages
        + [call["label"] for call in fake_st.checkbox_calls]
        + [call["label"] for call in fake_st.button_calls if call["label"] == "Save documentation review notes"]
        + [str(call.get("help") or "") for call in fake_st.text_input_calls]
        + [str(call.get("placeholder") or "") for call in fake_st.text_area_calls]
    )
    for phrase in [
        "Approved",
        "Ready",
        "Certified",
        "Validated",
        "Experimentally confirmed",
        "Lab-ready",
        "Release",
        "Pass/fail",
        "Sign-off complete",
    ]:
        assert phrase not in review_notes_text


def test_review_notes_save_calls_repository_with_expected_payload(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.button_values["pathway_save_documentation_review"] = True
    fake_st.checkbox_values.update(
        {
            "pathway_documentation_review_pathway_description_reviewed": True,
            "pathway_documentation_review_gene_entries_reviewed": True,
            "pathway_documentation_review_linked_expression_designs_reviewed": False,
            "pathway_documentation_review_suggestions_reviewed": True,
            "pathway_documentation_review_test_records_reviewed": False,
            "pathway_documentation_review_markdown_documentation_report_reviewed": True,
            "pathway_documentation_review_unresolved_documentation_items_reviewed": True,
        }
    )
    fake_st.text_input_values.update(
        {
            "pathway_documentation_review_reviewer_name_or_initials": "CD",
            "pathway_documentation_review_review_date": "2026-05-23",
        }
    )
    fake_st.text_area_values.update(
        {
            "pathway_documentation_review_review_notes": "Scope note",
            "pathway_documentation_review_follow_up_actions": "Follow-up note",
            "pathway_documentation_review_unresolved_items": "Unresolved note",
        }
    )
    update_calls = []

    def fake_update(project_id, payload):
        update_calls.append((project_id, payload))
        return True, "ok"

    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = 5
    monkeypatch.setattr(pathway_workspace, "get_pathway_project", lambda project_id: _project())
    monkeypatch.setattr(pathway_workspace, "list_pathway_steps", lambda project_id: [_step()])
    monkeypatch.setattr(pathway_workspace, "list_expression_design_links", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "list_pathway_test_records", lambda project_id: [])
    monkeypatch.setattr(pathway_workspace, "update_pathway_documentation_review", fake_update)

    pathway_workspace.render(lambda page_name: None)

    assert update_calls == [
        (
            5,
            {
                "review_items": {
                    "pathway_description_reviewed": True,
                    "gene_entries_reviewed": True,
                    "linked_expression_designs_reviewed": False,
                    "suggestions_reviewed": True,
                    "test_records_reviewed": False,
                    "markdown_documentation_report_reviewed": True,
                    "unresolved_documentation_items_reviewed": True,
                },
                "reviewer_name_or_initials": "CD",
                "review_date": "2026-05-23",
                "review_notes": "Scope note",
                "follow_up_actions": "Follow-up note",
                "unresolved_items": "Unresolved note",
                "last_updated": "",
                "review_scope": "",
                "review_context": "",
            },
        )
    ]
    assert fake_st.session_state["pathway_documentation_review_saved_feedback"] is True
    assert fake_st.rerun_calls == 1

    fake_st.button_values["pathway_save_documentation_review"] = False
    pathway_workspace.render(lambda page_name: None)

    assert "Review notes saved." in fake_st.success_messages


def test_saving_review_notes_does_not_change_completeness_or_suggestions(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.button_values["pathway_save_documentation_review"] = True
    signal = _make_signal()
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [signal])
    monkeypatch.setattr(
        pathway_workspace,
        "build_pathway_completeness",
        lambda project, steps, links: {"score": 73, "status": "partial", "missing_items": ["one"], "step_summaries": []},
    )

    _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[{"step_id": 10, "design_id": 77}], test_records=[])

    rendered_text = "\n".join(fake_st.caption_messages + fake_st.write_messages)
    rendered_summary = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)
    assert "Documentation coverage" in rendered_summary
    assert ">73%<" in rendered_summary
    assert signal["message"] in rendered_text
    assert "pathway_suggestions" not in fake_st.session_state


def test_existing_tabs_and_report_ui_still_render(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[{"step_id": 10, "design_id": 77}], test_records=[])

    assert fake_st.tab_groups == [
        ["Overview", "Plant Review", "Pathway Steps", "Linked Designs", "Linked Catalog Assets", "Traceability", "Review Signals", "Review Notes"],
        ["Documentation Snapshots", "Reports", "Quality Review", "Handoff Review", "Export Package", "Import Preview"],
    ]
    assert "Documentation Report" in fake_st.subheaders
    assert any(call["label"] == "Download Documentation Report" for call in fake_st.download_button_calls)


def test_workspace_project_centered_clarity_copy_renders(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(
        monkeypatch,
        fake_st,
        [_step()],
        expression_links=[{"step_id": 10, "design_id": 77, "design_name": "Local design record"}],
        test_records=[],
    )

    rendered_text = "\n".join(
        fake_st.caption_messages
        + fake_st.subheaders
        + fake_st.tab_labels
        + [call["label"] for call in fake_st.button_calls]
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )
    for phrase in [
        "current project as the main local project workspace",
        "Continue current project: work on the active pathway project as the main local project workspace",
        "Project Outputs holds documentation snapshots, reports, Quality Review, documentation-only Export Package review, and Import Preview inspection",
        "Handoff Review: first-class read-only workspace",
        "Expression Wizard is a design record subflow",
        "Linked Designs lists local Expression Wizard design records",
        "A design record can be reviewed in linked Pathway Project context",
        "documentation traceability only",
        "Traceability is a documentation lineage view",
        "Review Signals / Review Notes are documentation review surfaces",
        "Quality Review: review documentation completeness",
        "Build / review documentation-only export package",
        "Output actions",
        "Save documentation snapshot",
        "Download documentation report",
        "Review import package preview",
        "Package/report contents",
        "local documentation records, summaries, linked record references, traceability context, and review context only",
        "does not change export package schema, report payload schema, import/export behavior, or stored documentation snapshot schema",
        "Next documentation steps",
        "Add or review pathway steps",
        "Use the Pathway Steps tab",
        "Open / review linked Expression Wizard design records",
        "Use Linked Designs for recorded links",
        "Open Expression Wizard",
        "Save documentation snapshot",
        "Project Outputs > Documentation Snapshots",
        "Review import package in Pathway Workspace > Project Outputs > Import Preview",
        "Project Outputs holds documentation snapshots, reports, Quality Review, documentation-only Export Package review, and Import Preview inspection",
        "Use Project Outputs > Import Preview for read-only package inspection.",
    ]:
        assert phrase in rendered_text

    forbidden_positive_implications = [
        "wet-lab automation",
        "experimental validation complete",
        "prediction engine",
        "optimization engine",
        "recommendation engine output confirms",
        "readiness approval granted",
        "protocol generation available",
    ]
    for phrase in forbidden_positive_implications:
        assert phrase not in rendered_text


def test_next_documentation_steps_expression_wizard_action_navigates_only(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.button_values["pathway_workspace_next_steps_open_expression_wizard"] = True

    page_calls = _render_workspace(
        monkeypatch,
        fake_st,
        [_step()],
        expression_links=[{"step_id": 10, "design_id": 77, "design_name": "Local design record"}],
        test_records=[],
    )

    rendered_text = "\n".join(
        fake_st.caption_messages
        + fake_st.subheaders
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )
    assert page_calls == ["Expression Wizard"]
    assert "Next documentation steps" in rendered_text
    assert "Use Project Outputs > Documentation Snapshots to preserve the current documentation state." in rendered_text
    assert "Use the Pathway Steps tab to update pathway context and step-level documentation." in rendered_text
    assert "Use Project Outputs > Import Preview for read-only package inspection." in rendered_text
    assert PATHWAY_WIZARD_CONTEXT_KEY not in fake_st.session_state


def test_traceability_graph_lite_section_renders_summary_and_rows(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    graph = {
        "nodes": [{"id": "project:5"}, {"id": "step:10"}, {"id": "expression_design:77"}],
        "edges": [{"source": "project:5"}, {"source": "missing_step:999"}],
        "rows": [
            {
                "Source": "Terpene Pathway",
                "Relationship": "project_contains_step",
                "Target": "First step",
                "Status": "linked",
                "Review note": "Pathway step is part of the project documentation lineage.",
            },
            {
                "Source": "Missing step reference 999",
                "Relationship": "step_links_expression_design",
                "Target": "Stale linked design",
                "Status": "missing_reference",
                "Review note": "Referenced step is not present in the provided step records; human review is needed.",
            },
            {
                "Source": "Terpene Pathway",
                "Relationship": "project_has_review_signal",
                "Target": "stale_step_reference",
                "Status": "needs_review",
                "Review note": "Review signal references a step that is not present in the provided step records.",
            },
        ],
    }
    calls = []

    def fake_graph_builder(project, steps, expression_links, test_records, review_signals, snapshots=None):
        calls.append(
            {
                "project": project,
                "steps": steps,
                "expression_links": expression_links,
                "test_records": test_records,
                "review_signals": review_signals,
                "snapshots": snapshots,
            }
        )
        return graph

    monkeypatch.setattr(traceability_section, "build_traceability_graph_lite", fake_graph_builder)
    project = _project()
    steps = [_step()]
    expression_links = [{"id": 77, "step_id": 999, "design_name": "Stale linked design"}]
    test_records = [{"id": 1, "step_id": 10, "sample_name": "Observation"}]
    review_signals = [{"id": 2, "related_step_id": 999, "signal_type": "stale_step_reference"}]
    snapshots = [{"id": 3, "snapshot_title": "Local documentation snapshot"}]

    traceability_section.render_traceability_graph_lite_section(
        project,
        steps,
        expression_links,
        test_records,
        review_signals,
        snapshots,
        lineage_copy=pathway_workspace.TRACEABILITY_LINEAGE_COPY,
        boundary_copy=pathway_workspace.TRACEABILITY_BOUNDARY_COPY,
        status_helper_copy=pathway_workspace.TRACEABILITY_STATUS_HELPER_COPY,
        empty_state_copy=pathway_workspace.TRACEABILITY_EMPTY_STATE_COPY,
    )

    assert calls == [
        {
            "project": project,
            "steps": steps,
            "expression_links": expression_links,
            "test_records": test_records,
            "review_signals": review_signals,
            "snapshots": snapshots,
        }
    ]
    assert "Traceability Graph Lite" in fake_st.subheaders
    rendered_text = "\n".join(fake_st.caption_messages + [str(call["body"]) for call in fake_st.markdown_calls])
    for phrase in [
        "documentation-only",
        "linked = local record relationship exists",
        "missing_reference = referenced local record was not found",
        "needs_review = documentation record needs human review",
        "no_records = no local documentation lineage rows yet",
        "human review",
    ]:
        assert phrase in rendered_text
    for phrase in ["validate experiments", "predict outcomes", "recommend actions", "determine readiness"]:
        assert phrase in rendered_text
    for phrase in ["Traceability nodes", "Traceability edges", "Rows needing review", "Missing references"]:
        assert phrase in rendered_text
    assert [call["body"] for call in fake_st.markdown_calls if str(call["body"]).isdigit()] == ["3", "2", "1", "1"]
    assert len(fake_st.dataframes) == 1
    rows = fake_st.dataframes[0].to_dict("records")
    assert rows == graph["rows"]
    assert {row["Status"] for row in rows} >= {"missing_reference", "needs_review"}


def test_traceability_graph_lite_section_empty_rows_state_is_clear(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(
        traceability_section,
        "build_traceability_graph_lite",
        lambda *args, **kwargs: {"nodes": [], "edges": [], "rows": []},
    )

    traceability_section.render_traceability_graph_lite_section(
        _project(),
        [],
        [],
        [],
        [],
        [],
        lineage_copy=pathway_workspace.TRACEABILITY_LINEAGE_COPY,
        boundary_copy=pathway_workspace.TRACEABILITY_BOUNDARY_COPY,
        status_helper_copy=pathway_workspace.TRACEABILITY_STATUS_HELPER_COPY,
        empty_state_copy=pathway_workspace.TRACEABILITY_EMPTY_STATE_COPY,
    )

    assert "Traceability Graph Lite" in fake_st.subheaders
    assert any("No local documentation lineage rows are available yet" in message for message in fake_st.info_messages)
    assert any("local project documentation records" in message for message in fake_st.info_messages)
    assert any("reviewing traceability" in message for message in fake_st.info_messages)
    assert fake_st.dataframes == []


def test_traceability_graph_lite_section_has_no_positive_readiness_or_prediction_copy(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(
        traceability_section,
        "build_traceability_graph_lite",
        lambda *args, **kwargs: {
            "nodes": [],
            "edges": [],
            "rows": [
                {
                    "Source": "Project",
                    "Relationship": "no_records",
                    "Target": "Traceability Graph Lite",
                    "Status": "no_records",
                    "Review note": "No project documentation records are available for lineage review.",
                }
            ],
        },
    )

    traceability_section.render_traceability_graph_lite_section(
        _project(),
        [],
        [],
        [],
        [],
        [],
        lineage_copy=pathway_workspace.TRACEABILITY_LINEAGE_COPY,
        boundary_copy=pathway_workspace.TRACEABILITY_BOUNDARY_COPY,
        status_helper_copy=pathway_workspace.TRACEABILITY_STATUS_HELPER_COPY,
        empty_state_copy=pathway_workspace.TRACEABILITY_EMPTY_STATE_COPY,
    )

    text = "\n".join(
        fake_st.caption_messages
        + fake_st.info_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [str(value) for row in fake_st.dataframes[0].to_dict("records") for value in row.values()]
    ).lower()
    positive_claims = [
        "predicts",
        "prediction result",
        "recommended action",
        "recommendation result",
        "experimentally validated",
        "validation complete",
        "certifies readiness",
        "determines readiness",
        "ready for experimental use",
        "experimental readiness",
    ]
    for phrase in positive_claims:
        assert phrase not in text


def test_project_outputs_traceability_summary_counts_and_boundary_copy(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    graph = {
        "nodes": [],
        "edges": [],
        "rows": [
            {
                "Source": "Terpene Pathway",
                "Relationship": "project_contains_step",
                "Target": "First step",
                "Status": "linked",
                "Review note": "Pathway step is part of the project documentation lineage.",
            },
            {
                "Source": "Missing step reference 999",
                "Relationship": "step_links_expression_design",
                "Target": "Stale linked design",
                "Status": "missing_reference",
                "Review note": "Referenced step is not present in the provided step records; human review is needed.",
            },
            {
                "Source": "Terpene Pathway",
                "Relationship": "project_has_review_signal",
                "Target": "stale_step_reference",
                "Status": "needs_review",
                "Review note": "Review signal references a step that is not present in the provided step records.",
            },
        ],
    }
    calls = []

    def fake_graph_builder(project, steps, expression_links, test_records, review_signals, snapshots=None):
        calls.append(
            {
                "project": project,
                "steps": steps,
                "expression_links": expression_links,
                "test_records": test_records,
                "review_signals": review_signals,
                "snapshots": snapshots,
            }
        )
        return graph

    monkeypatch.setattr(traceability_section, "build_traceability_graph_lite", fake_graph_builder)
    project = _project()
    steps = [_step()]
    expression_links = [{"id": 77, "step_id": 999, "design_name": "Stale linked design"}]
    test_records = [{"id": 1, "step_id": 10, "sample_name": "Observation"}]
    review_signals = [{"id": 2, "related_step_id": 999, "signal_type": "stale_step_reference"}]
    snapshots = [{"id": 3, "snapshot_title": "Local documentation snapshot"}]

    traceability_section.render_project_outputs_traceability_summary(
        project,
        steps,
        expression_links,
        test_records,
        review_signals,
        snapshots,
        status_helper_copy=pathway_workspace.TRACEABILITY_STATUS_HELPER_COPY,
    )

    assert calls == [
        {
            "project": project,
            "steps": steps,
            "expression_links": expression_links,
            "test_records": test_records,
            "review_signals": review_signals,
            "snapshots": snapshots,
        }
    ]
    rendered_text = "\n".join(fake_st.caption_messages + [str(call["body"]) for call in fake_st.markdown_calls])
    for phrase in [
        "Traceability Summary for documentation review only",
        "not experimental validation",
        "not prediction",
        "not a recommendation",
        "does not determine readiness",
        "linked = local record relationship exists",
        "missing_reference = referenced local record was not found",
        "needs_review = documentation record needs human review",
        "no_records = no local documentation lineage rows yet",
        "Traceability rows",
        "Rows needing review",
        "Missing references",
        "Local documentation lineage records exist",
    ]:
        assert phrase in rendered_text
    assert [call["body"] for call in fake_st.markdown_calls if str(call["body"]) in {"3", "1", "Yes"}] == [
        "3",
        "1",
        "1",
        "Yes",
    ]


def test_project_outputs_traceability_summary_reports_no_lineage_records(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(
        traceability_section,
        "build_traceability_graph_lite",
        lambda *args, **kwargs: {
            "nodes": [],
            "edges": [],
            "rows": [
                {
                    "Source": "Project",
                    "Relationship": "no_records",
                    "Target": "Traceability Graph Lite",
                    "Status": "no_records",
                    "Review note": "No project documentation records are available for lineage review.",
                }
            ],
        },
    )

    traceability_section.render_project_outputs_traceability_summary(
        {},
        [],
        [],
        [],
        [],
        [],
        status_helper_copy=pathway_workspace.TRACEABILITY_STATUS_HELPER_COPY,
    )

    rendered_values = [call["body"] for call in fake_st.markdown_calls]
    assert "Local documentation lineage records exist" in "\n".join(str(value) for value in rendered_values)
    assert rendered_values[-1] == "No"
    assert [call["body"] for call in fake_st.markdown_calls if str(call["body"]).isdigit()] == ["1", "0", "0"]


def test_traceability_summary_counts_handles_mixed_statuses_and_no_records():
    summary = traceability_summary_counts(
        {
            "rows": [
                {"Status": "linked"},
                {"Status": "missing_reference"},
                {"Status": "needs_review"},
                {"Status": "no_records"},
            ]
        }
    )

    assert summary == {
        "traceability_rows": 4,
        "rows_needing_review": 1,
        "missing_references": 1,
        "lineage_records_exist": True,
    }


def test_traceability_summary_counts_no_records_only_has_no_lineage():
    summary = traceability_summary_counts({"rows": [{"Status": "no_records"}]})

    assert summary == {
        "traceability_rows": 1,
        "rows_needing_review": 0,
        "missing_references": 0,
        "lineage_records_exist": False,
    }


def test_project_outputs_tabs_render_traceability_summary_before_review_surfaces(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "render_documentation_snapshots_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(pathway_workspace, "_render_documentation_report_download", lambda *args, **kwargs: None)
    monkeypatch.setattr(pathway_workspace, "render_project_quality_dashboard_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(pathway_workspace, "render_project_review_report_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(pathway_workspace, "render_export_package_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(pathway_workspace, "_render_import_package_preview", lambda *args, **kwargs: None)

    pathway_workspace._render_project_outputs_tabs(
        project=_project(),
        project_id=5,
        steps=[_step()],
        expression_links=[{"id": 77, "step_id": 999, "design_name": "Stale linked design"}],
        test_records=[],
        completeness_result={"score": 88, "status": "partial", "missing_items": [], "step_summaries": []},
        suggestions=[],
        review_signals=[{"id": 2, "related_step_id": 999, "signal_type": "stale_step_reference"}],
        snapshots=[],
    )

    rendered_text = "\n".join(fake_st.caption_messages + [str(call["body"]) for call in fake_st.markdown_calls])
    assert "Traceability Summary for documentation review only" in rendered_text
    assert "local documentation lineage snapshot" in rendered_text
    assert "not experimental validation" in rendered_text
    assert "not prediction" in rendered_text
    assert "not a recommendation" in rendered_text
    assert "does not determine readiness" in rendered_text
    assert "missing_reference = referenced local record was not found" in rendered_text
    for phrase in [
        "Output actions",
        "Save documentation snapshot",
        "Download documentation report",
        "Build / review documentation-only export package",
        "Review import package preview",
        "Documentation-only boundary",
        "Quality Review",
        "Handoff Review",
        "Package/report contents",
        "local documentation records, summaries, linked record references, traceability context, and review context only",
        "does not change export package schema, report payload schema, import/export behavior, or stored documentation snapshot schema",
    ]:
        assert phrase in rendered_text
    assert "Documentation Snapshots" in fake_st.tab_labels
    assert "Quality Review" in fake_st.tab_labels
    assert "Handoff Review" in fake_st.tab_labels


def test_project_outputs_tabs_summary_cards_pin_read_only_counts(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    summary_calls = []
    workflow_rows = [
        {"label": "Documentation Snapshots", "level": "review_available"},
        {"label": "Reports", "level": "review_available"},
        {"label": "Quality Review", "level": "review_attention"},
        {"label": "Export Package", "level": "review_available"},
        {"label": "Import Preview", "level": "lifecycle_preview"},
    ]
    risk_rows = [
        {"label": "Project metadata", "status": "ok"},
        {"label": "Traceability", "status": "human_review_needed"},
        {"label": "Provenance", "status": "complete"},
    ]

    monkeypatch.setattr(pathway_workspace, "build_project_outputs_workflow_state", lambda *args, **kwargs: workflow_rows)
    monkeypatch.setattr(pathway_workspace, "build_documentation_risk_summary", lambda *args, **kwargs: risk_rows)
    monkeypatch.setattr(pathway_workspace, "render_compact_summary_cards", lambda items: summary_calls.append(list(items)))
    monkeypatch.setattr(pathway_workspace, "render_documentation_snapshots_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(pathway_workspace, "_render_documentation_report_download", lambda *args, **kwargs: None)
    monkeypatch.setattr(pathway_workspace, "render_project_quality_dashboard_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(pathway_workspace, "render_project_review_report_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(pathway_workspace, "render_export_package_section", lambda *args, **kwargs: None)
    monkeypatch.setattr(pathway_workspace, "_render_import_package_preview", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        traceability_section,
        "build_traceability_graph_lite",
        lambda *args, **kwargs: {"nodes": [], "edges": [], "rows": [{"Status": "no_records"}]},
    )

    pathway_workspace._render_project_outputs_tabs(
        project=_project(),
        project_id=5,
        steps=[_step()],
        expression_links=[],
        test_records=[],
        completeness_result={"score": 88, "status": "partial", "missing_items": [], "step_summaries": []},
        suggestions=[],
        review_signals=[],
        snapshots=[],
    )

    assert summary_calls == [
        [
            ("Output surfaces", "5", "Snapshots, reports, quality review, export, import preview"),
            ("Review attention", "1", "Workflow rows with documentation review prompts"),
            ("Source review needed", "1", "Risk summary rows needing human review"),
            ("Report draft", "Available", "Markdown report draft and quality review tabs"),
        ]
    ]


def test_linked_catalog_assets_add_reference_panel_renders_without_changing_navigation(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[{"step_id": 10, "design_id": 77}], test_records=[])

    rendered_text = "\n".join(
        fake_st.caption_messages
        + fake_st.subheaders
        + fake_st.tab_labels
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [call["label"] for call in fake_st.text_input_calls]
        + [call["label"] for call in fake_st.selectbox_calls]
        + [call["label"] for call in fake_st.text_area_calls]
        + [call["label"] for call in fake_st.button_calls]
    )
    for phrase in [
        "Linked Catalog Assets",
        "Add catalog asset reference",
        "Search existing catalog assets",
        "Select catalog asset",
        "Select linkage role",
        "Optional documentation note",
        "Add documentation reference",
        "Linked assets are documentation references only.",
        "Linking an asset does not indicate biological fit, source verification, or downstream use state.",
        "Human review is required before downstream use; links do not endorse or select an asset.",
    ]:
        assert phrase in rendered_text


def test_pathway_step_with_gene_record_shows_launch_button(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(monkeypatch, fake_st, [_step()])

    labels = [call["label"] for call in fake_st.button_calls]
    assert "Open in Expression Wizard" in labels
    assert any(
        "Use Expression Wizard for gene-level expression design for this pathway step." in message
        for message in fake_st.caption_messages
    )
    assert not any("Add both a gene name" in message for message in fake_st.info_messages)


def test_pathway_step_missing_gene_record_hides_launch_button_and_shows_prompt(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(monkeypatch, fake_st, [_step(gene_sequence="")])

    labels = [call["label"] for call in fake_st.button_calls]
    assert "Open in Expression Wizard" not in labels
    assert any("Add both a gene name and a gene sequence" in message for message in fake_st.info_messages)


def test_pathway_launch_writes_context_and_fresh_step1_design_session(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.button_values["pathway_design_expression_10"] = True

    page_calls = _render_workspace(monkeypatch, fake_st, [_step()])

    context = fake_st.session_state[PATHWAY_WIZARD_CONTEXT_KEY]
    assert context["source"] == "pathway_workspace"
    assert context["project_id"] == 5
    assert context["step_id"] == 10
    assert context["gene_name"] == "demo_gene"

    ds = fake_st.session_state["design_session"]
    assert isinstance(ds, DesignSession)
    assert ds.step == 1
    assert ds.gene_name == "demo_gene"
    assert ds.original_seq == "ATGAAACCCTAA"
    assert ds.host == ""
    assert ds.frame == {}
    assert ds.primers == []
    assert ds.validation_results == []
    assert page_calls == ["Expression Wizard"]


def test_no_pathway_context_is_created_without_launch_click(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(monkeypatch, fake_st, [_step()])

    assert PATHWAY_WIZARD_CONTEXT_KEY not in fake_st.session_state
    assert "design_session" not in fake_st.session_state


def test_pathway_steps_show_step_level_linked_design_counts(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(
        monkeypatch,
        fake_st,
        [_step(), _step(id=11, step_order=2, step_name="Second step")],
        expression_links=[
            {"step_id": 10, "design_id": 77},
            {"step_id": 10, "design_id": 78},
            {"step_id": 11, "design_id": 79},
        ],
    )

    steps_table = next(
        dataframe for dataframe in fake_st.dataframes if "Linked designs" in getattr(dataframe, "columns", [])
    )
    rows = steps_table.to_dict("records")
    assert rows[0]["Linked designs"] == 2
    assert rows[1]["Linked designs"] == 1
    assert "Linked designs: 2" in fake_st.caption_messages
    assert "Linked designs: 1" in fake_st.caption_messages


def test_pathway_steps_count_links_for_string_numeric_step_ids(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(
        monkeypatch,
        fake_st,
        [_step(id="10")],
        expression_links=[{"step_id": 10, "design_id": 77}],
    )

    steps_table = next(
        dataframe for dataframe in fake_st.dataframes if "Linked designs" in getattr(dataframe, "columns", [])
    )
    assert steps_table.to_dict("records")[0]["Linked designs"] == 1
    assert "Linked designs: 1" in fake_st.caption_messages


def test_pathway_steps_bad_or_missing_step_ids_do_not_crash(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(
        monkeypatch,
        fake_st,
        [_step(id="not-a-number"), _step(id=None, step_order=2, step_name="Missing id")],
        expression_links=[{"step_id": 10, "design_id": 77}],
    )

    steps_table = next(
        dataframe for dataframe in fake_st.dataframes if "Linked designs" in getattr(dataframe, "columns", [])
    )
    rows = steps_table.to_dict("records")
    assert rows[0]["Linked designs"] == 0
    assert rows[1]["Linked designs"] == 0
    assert "Linked designs: 0" in fake_st.caption_messages


def test_pathway_steps_show_zero_linked_design_status(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[])

    steps_table = next(
        dataframe for dataframe in fake_st.dataframes if "Linked designs" in getattr(dataframe, "columns", [])
    )
    assert steps_table.to_dict("records")[0]["Linked designs"] == 0
    assert "Linked designs: 0" in fake_st.caption_messages


def test_linked_designs_tab_shows_step_evidence_panel_fields(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(
        monkeypatch,
        fake_st,
        [_step()],
        expression_links=[
            {
                "id": 91,
                "step_id": 10,
                "design_name": "Alpha design",
                "design_source": "expression_wizard",
                "linked_at": "2026-06-10T10:00:00",
            }
        ],
    )

    assert "Step-level linked design evidence" in fake_st.subheaders
    assert any(
        "A linked design record can be reviewed in this Pathway Project context" in message
        for message in fake_st.caption_messages
    )
    evidence_table = next(
        dataframe for dataframe in fake_st.dataframes if "Linked design" in getattr(dataframe, "columns", [])
    )
    rows = evidence_table.to_dict("records")
    assert rows == [
        {
            "Linked design": "Alpha design",
            "Linked/saved time": "2026-06-10T10:00:00",
            "Source/context": "expression_wizard",
        }
    ]
    assert any("Step 1: First step" in str(call["body"]) for call in fake_st.markdown_calls)
    assert "Linked designs: 1" in fake_st.caption_messages


def test_linked_designs_tab_shows_empty_state_for_unlinked_step(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[])

    assert "Step-level linked design evidence" in fake_st.subheaders
    assert "Linked designs: 0" in fake_st.caption_messages
    assert any("No linked design records yet" in message for message in fake_st.info_messages)
    assert any("Open Expression Wizard" in message for message in fake_st.info_messages)
    assert any("local documentation record for this Pathway Project context" in message for message in fake_st.info_messages)


def test_linked_designs_tab_groups_multiple_links_to_correct_steps(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(
        monkeypatch,
        fake_st,
        [_step(), _step(id=11, step_order=2, step_name="Second step")],
        expression_links=[
            {"step_id": 10, "design_name": "Step one A", "linked_at": "t1", "design_source": "wizard"},
            {"step_id": 11, "design_name": "Step two A", "linked_at": "t2", "design_source": "wizard"},
            {"step_id": 10, "design_name": "Step one B", "linked_at": "t3", "design_source": "library"},
        ],
    )

    evidence_tables = [
        dataframe for dataframe in fake_st.dataframes if "Linked design" in getattr(dataframe, "columns", [])
    ]
    assert [len(dataframe.to_dict("records")) for dataframe in evidence_tables] == [2, 1]
    assert [row["Linked design"] for row in evidence_tables[0].to_dict("records")] == ["Step one A", "Step one B"]
    assert [row["Linked design"] for row in evidence_tables[1].to_dict("records")] == ["Step two A"]
    assert "Linked designs: 2" in fake_st.caption_messages
    assert "Linked designs: 1" in fake_st.caption_messages


def test_linked_designs_tab_ignores_bad_step_ids_without_crashing(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    _render_workspace(
        monkeypatch,
        fake_st,
        [_step()],
        expression_links=[
            {"step_id": "bad", "design_name": "Bad id design"},
            {"step_id": None, "design_name": "Missing id design"},
        ],
    )

    evidence_tables = [
        dataframe for dataframe in fake_st.dataframes if "Linked design" in getattr(dataframe, "columns", [])
    ]
    assert evidence_tables == []
    assert "Linked designs: 0" in fake_st.caption_messages
    assert any("No linked design records yet" in message for message in fake_st.info_messages)


def test_pathway_link_success_preserves_return_context(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)

    from services import pathway_wizard_context

    monkeypatch.setattr(pathway_wizard_context, "st", fake_st, raising=False)
    fake_st.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = {
        "source": "pathway_workspace",
        "status": "active",
        "project_id": 5,
        "project_name": "Terpene Pathway",
        "step_id": 10,
        "step_order": 1,
        "step_name": "First step",
        "reaction_name": "Demo reaction",
        "gene_sequence_hash": "abc",
        "started_at": "2026-06-10T10:00:00",
    }
    link_calls = []

    def fake_link_expression_design_to_step(**kwargs):
        link_calls.append(kwargs)
        return True, "linked", 99

    monkeypatch.setattr(pathway_wizard_context, "link_expression_design_to_step", fake_link_expression_design_to_step, raising=False)
    monkeypatch.setattr("services.pathway_repository.link_expression_design_to_step", fake_link_expression_design_to_step)
    monkeypatch.setattr("services.pathway_repository.safe_json_dumps", lambda payload: payload)

    ds = DesignSession(gene_name="demo_gene", host="E.coli", optimized_seq="ATGAAA")
    ds.frame = {"final_sequence": "ATGAAATAA"}

    ok, message, attempted = pathway_wizard_context.link_saved_design_to_active_pathway_context(
        ds,
        saved_design_name="demo design",
        validation_state={"status": "completed_review", "is_complete": True},
        export_recommendation={"recommendation": "Export with Review Required"},
        documentation_only_export=True,
    )

    assert ok is True
    assert message == "linked"
    assert attempted is True
    assert link_calls[0]["project_id"] == 5
    assert link_calls[0]["step_id"] == 10
    assert fake_st.session_state[PATHWAY_WIZARD_CONTEXT_KEY]["status"] == "linked"
    assert fake_st.session_state[PATHWAY_WIZARD_CONTEXT_KEY]["linked_design_name"] == "demo design"


def test_suggestions_tab_disclaimer_and_empty_state_are_rendered(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [])

    _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[{"step_id": 10, "design_id": 77}], test_records=[])

    assert "Review Signals" in fake_st.tab_labels
    assert (
        "Review Signals are documentation-only prompts for unresolved questions, source review, documentation gaps, manual follow-up notes, record consistency checks, and evidence-chain review."
        in fake_st.caption_messages
    )
    assert (
        "They are not experimental judgments, predictions, optimization instructions, readiness approval, recommendation engine output, experimental guidance, action instructions, or protocol generation."
        in fake_st.caption_messages
    )
    assert (
        "Review Signals do not identify established results or forecast production. They are transient prompts for reviewing the current workspace documentation context."
        in fake_st.caption_messages
    )
    assert "No documentation-only review signals were generated from the currently recorded data." in fake_st.info_messages


def test_suggestions_signals_render_message_evidence_next_check_and_boundary(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    signal = _make_signal()
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: [signal])

    _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[{"step_id": 10, "design_id": 77}], test_records=[{"id": 1, "step_id": 10, "sample_name": "doc"}])

    rendered_text = "\n".join(fake_st.caption_messages + fake_st.write_messages + fake_st.info_messages + fake_st.warning_messages)
    assert signal["message"] in rendered_text
    assert signal["suggested_next_check"] in rendered_text
    assert signal["boundary_note"] in rendered_text
    assert any("Evidence summary:" in message for message in fake_st.caption_messages)


def test_forbidden_wording_is_absent_from_workspace_ui(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[{"step_id": 10, "design_id": 77, "validation_summary_json": {"warnings": ["warning"]}}], test_records=[])

    ui_text = "\n".join(
        fake_st.titles
        + fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.warning_messages
        + fake_st.success_messages
        + fake_st.write_messages
        + fake_st.tab_labels
        + [call["label"] for call in fake_st.button_calls]
        + [call["label"] for call in fake_st.download_button_calls]
    )
    forbidden = [
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
    for phrase in forbidden:
        assert phrase not in ui_text


def test_suggestions_are_not_persisted_and_completeness_unchanged(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    stored = []
    monkeypatch.setattr(pathway_workspace, "analyze_pathway_bottlenecks", lambda context: stored.append(context) or [_make_signal()])
    monkeypatch.setattr(pathway_workspace, "build_pathway_completeness", lambda project, steps, links: {"score": 88, "status": "partial", "missing_items": ["one"], "step_summaries": []})

    _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[{"step_id": 10, "design_id": 77, "validation_summary_json": {"warnings": ["warning"]}}], test_records=[{"id": 1, "step_id": 10, "sample_name": "doc"}])

    assert stored
    assert "pathway_suggestions" not in fake_st.session_state
    assert all("suggestion" not in str(key).lower() for key in fake_st.session_state)
    rendered_summary = "\n".join(str(call["body"]) for call in fake_st.markdown_calls)
    assert "Documentation coverage" in rendered_summary
    assert ">88%<" in rendered_summary


def test_existing_tests_tab_and_expression_launch_remain_unchanged(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.button_values["pathway_design_expression_10"] = True

    page_calls = _render_workspace(monkeypatch, fake_st, [_step()], expression_links=[{"step_id": 10, "design_id": 77, "validation_summary_json": {"warnings": ["warning"]}}], test_records=[{"id": 1, "step_id": None, "sample_name": "project doc"}])

    assert "Pathway Steps" in fake_st.tab_labels
    assert "Overview" in fake_st.tab_labels
    assert "Review Notes" in fake_st.tab_labels
    assert page_calls == ["Expression Wizard"]
    assert PATHWAY_WIZARD_CONTEXT_KEY in fake_st.session_state


def test_step6_catalog_reference_bridge_adds_selected_links_to_project_session(tmp_path, monkeypatch):
    fake_st = FakeStreamlit()
    db_path = tmp_path / "wizard_catalog_picker_ui.db"
    monkeypatch.setattr(project_catalog_asset_link_repository, "DB_PATH", str(db_path))
    monkeypatch.setattr(step6_export, "st", fake_st)
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)
    fake_st.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = {
        "source": "pathway_workspace",
        "status": "active",
        "project_id": 5,
        "project_name": "Terpene Pathway",
        "step_id": 10,
    }
    fake_st.selectbox_values["wf_p6_catalog_picker_select_5"] = "plant::plant_promoter_profile::plant-promoter-seed-001"
    fake_st.button_values["wf_p6_catalog_picker_add_5"] = True

    step6_export._render_catalog_documentation_references(
        DesignSession(gene_name="demo_gene", host="E.coli BL21(DE3)")
    )

    stored_links = fake_st.session_state["project_asset_links_5"]
    persisted_links = project_catalog_asset_link_repository.list_project_catalog_asset_links("5")
    assert len(stored_links) == 1
    assert len(persisted_links) == 1
    assert stored_links[0]["asset_id"] == "plant-promoter-seed-001"
    assert stored_links[0]["asset_type"] == "plant_promoter_profile"
    assert stored_links[0]["linkage_role"] == "design_record_context"
    assert stored_links[0]["human_review_required"] is True
    rendered_text = "\n".join(
        fake_st.caption_messages
        + fake_st.success_messages
        + [call["label"] for call in fake_st.selectbox_calls]
        + [call["label"] for call in fake_st.text_area_calls]
        + [call["label"] for call in fake_st.button_calls]
    )
    assert "documentation-level reference" in rendered_text
    assert "does not advise which record to choose" in rendered_text
    assert "verify biology" in rendered_text
    assert "certify downstream-use state" in rendered_text
    assert "forecast outcomes" in rendered_text
    assert "Select catalog context reference" in rendered_text
    assert "Add documentation-level reference" in rendered_text
    assert fake_st.rerun_calls == 1


def test_step6_catalog_traceability_summary_is_visible(tmp_path, monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    db_path = tmp_path / "wizard_catalog_traceability_ui.db"
    monkeypatch.setattr(project_catalog_asset_link_repository, "DB_PATH", str(db_path))
    monkeypatch.setattr(step6_export, "st", fake_st)
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)
    fake_st.session_state[PATHWAY_WIZARD_CONTEXT_KEY] = {
        "source": "pathway_workspace",
        "status": "active",
        "project_id": 5,
        "project_name": "Terpene Pathway",
        "step_id": 10,
    }
    project_catalog_asset_link_repository.add_project_catalog_asset_link(
        {
            "project_id": "5",
            "asset_id": "plant-promoter-seed-001",
            "asset_display_name": "Maize ubiquitin promoter source context",
            "asset_type": "plant_promoter_profile",
            "linkage_role": "design_record_context",
            "documentation_note": "Documentation-only Expression Wizard catalog context reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-seed-001",
                "plant_clade": "monocot",
                "species": "Zea mays (maize)",
                "source_labels": "Literature source placeholder: ZMU-ROOT",
                "reference_origin": "Expression Wizard catalog context",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 1,
            },
            "human_review_required": True,
        }
    )

    step6_export._render_catalog_documentation_references(DesignSession(gene_name="demo_gene", host="E.coli BL21(DE3)"))

    rendered_text = "\n".join(
        fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.success_messages
        + [call["label"] for call in fake_st.selectbox_calls]
        + [call["label"] for call in fake_st.text_area_calls]
        + [call["label"] for call in fake_st.button_calls]
    )
    assert "documentation-level linked context" in rendered_text
    assert "Expression Wizard catalog traceability" in rendered_text
    assert "1 reference(s)" in rendered_text
    assert "Component Library promoter asset reference(s)" in rendered_text
    assert "No project context is linked to this Wizard session." not in rendered_text
    assert len(fake_st.dataframes) >= 2
    assert any("Reference origin" in getattr(df, "columns", []) for df in fake_st.dataframes)


def test_step6_catalog_traceability_no_project_context_is_safe(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    monkeypatch.setattr(step6_export, "st", fake_st)
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)

    step6_export._render_catalog_documentation_references(DesignSession(gene_name="demo_gene", host="E.coli BL21(DE3)"))

    rendered_text = "\n".join(fake_st.caption_messages + fake_st.info_messages)
    assert "No project context is linked to this Wizard session." in rendered_text
    assert "documentation-level linked context" not in rendered_text
