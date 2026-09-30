from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tests.helpers.fake_streamlit import FakeStreamlit
import views.PathwayProjects as pathway_projects
import views.PathwayWorkspace as pathway_workspace
import views.tool_typography as tool_typography


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(pathway_projects, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    return fake_st


def test_pathway_projects_start_here_and_quick_start_copy_render(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)

    pathway_projects._render_page_header()
    pathway_projects._render_quick_start([], lambda page_name: None)

    rendered_text = "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [call["label"] for call in fake_st.expander_calls]
    )
    for phrase in [
        "Use Pathway Projects when expression vector design records need optional project grouping",
        "Expression Wizard is the primary expression vector design preparation path",
        "Pathway Workspace is the optional project-level documentation workspace",
        "Project Outputs covers documentation snapshots, reports, documentation-only export package review, and import preview review",
        "Review import package in Pathway Workspace > Project Outputs > Import Preview",
        "documentation-only package inspection for validation and dry-run planning",
        "preview does not create a project, overwrite, or merge existing projects",
        "Final import-as-new stays gated by the existing controls",
        "Open Pathway Workspace to review linked Expression Wizard design records",
        "Start expression vector design preparation in Expression Wizard",
        "To review an import package, go to **Pathway Workspace > Project Outputs > Import Preview**",
        "Import preview boundary",
        "Example project path: this documentation case highlights source context, provenance context",
        "traceability records, review prompts, and documentation package value",
        "not a biological recommendation, not an experimental validation, and not a wet-lab readiness judgment",
        "Load a documentation-only Nicotiana example project to try the main workspace flow",
    ]:
        assert phrase in rendered_text

    for forbidden in [
        "ready for execution",
        "validated construct",
        "optimized pathway",
        "yield prediction",
        "experiment-ready",
        "production-ready",
    ]:
        assert forbidden not in rendered_text.lower()


def test_pathway_projects_active_card_continue_current_project_copy_render(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {
        "id": 1,
        "name": "QA Project",
        "target_product": "Documentation Review Product",
        "host": "Local documentation context",
        "status": "draft",
        "updated_at": "",
        "description": "",
    }

    pathway_projects._render_active_project_card(project, lambda page_name: None)

    rendered_text = "\n".join(
        fake_st.subheaders
        + fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [call["label"] for call in fake_st.button_calls]
    )
    assert "Continue current project in Pathway Workspace" in rendered_text
    assert "linked Expression Wizard design records" in rendered_text
    assert "project outputs" in rendered_text
    assert "Open Pathway Workspace" in rendered_text
    assert "Project" in rendered_text
    assert "Target" in rendered_text


def test_pathway_projects_active_card_shows_catalog_reference_overview(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {
        "id": 11,
        "name": "Catalog Project",
        "target_product": "Documentation Review Product",
        "host": "Local documentation context",
        "status": "draft",
        "updated_at": "",
        "description": "Project with catalog references.",
    }

    monkeypatch.setattr(
        pathway_projects,
        "build_project_catalog_reference_overview",
        lambda current_project: {
            "total_catalog_links": 2,
            "plant_promoter_link_count": 1,
            "pinned_snapshot_count": 1,
            "missing_source_or_review_metadata_count": 1,
            "coverage_note": "2 catalog references; 1 pinned snapshot(s); 1 with missing source/provenance or record review status.",
            "linked_catalog_assets": [
                {
                    "asset_label": "Alpha promoter",
                    "asset_type": "plant_promoter_profile",
                    "record_identifier": "a-1",
                    "linkage_role": "source_review_context",
                    "reference_origin": "Project documentation reference",
                    "catalog_source_status": "Plant Promoter Catalog / Source A / Reviewed",
                    "source_context_readback": "Source context readback: catalog Plant Promoter Catalog; source/provenance review Source A",
                    "host_chassis_context_readback": "Recorded host / chassis context only: Nicotiana benthamiana documentation context; normalized review context: Plant. This is source/readback context, not compatibility evidence.",
                    "review_needed_context": "Review-needed context: curation status Reviewed; human review flag not recorded",
                    "metadata_gap_context": "Source/provenance and record review status recorded for documentation review",
                    "catalog_reference_context": "Catalog reference context: origin Project documentation reference; link state Linked catalog reference; snapshot state pinned documentation snapshot",
                    "snapshot_state": "pinned snapshot",
                    "source_label": "Source A",
                    "documentation_status": "Reviewed",
                    "project_documentation_context": "Pathway Workspace linked catalog assets",
                    "documentation_note": "Documentation-only project reference.",
                }
            ],
        },
    )

    pathway_projects._render_active_project_card(project, lambda page_name: None)

    rendered_text = "\n".join(
        fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [call["label"] for call in fake_st.button_calls]
    )
    assert "Catalog Reference Overview" in rendered_text
    assert "Documentation-level overview of linked catalog references" in rendered_text
    assert "not recommendation, not validation, not readiness, and not prediction" in rendered_text
    assert "linked catalog references" in rendered_text
    assert "pinned snapshot context, source/provenance review, and record review gaps" in rendered_text
    assert "1 with missing source/provenance or record review status" in rendered_text
    assert "record identifier, catalog reference context, source/provenance review, record review status, documentation note, and project documentation context visible" in rendered_text
    assert "Alpha promoter" in str(fake_st.dataframes[0])
    assert (
        fake_st.dataframes[0].iloc[0]["Host / chassis context readback"]
        == "Recorded host / chassis context only: Nicotiana benthamiana documentation context; normalized review context: Plant. This is source/readback context, not compatibility evidence."
    )
    assert "Open Pathway Workspace" in rendered_text


def test_pathway_projects_project_switching_copy_is_explicit(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    projects = [
        {"id": 1, "name": "Project A", "target_product": "Product A", "host": "Host A", "updated_at": ""},
        {"id": 2, "name": "Project B", "target_product": "Product B", "host": "Host B", "updated_at": ""},
    ]

    pathway_projects._render_project_table(projects)
    pathway_projects._render_project_selector(projects, lambda page_name: None)

    rendered_text = "\n".join(
        fake_st.caption_messages
        + fake_st.success_messages
        + fake_st.info_messages
        + fake_st.write_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [call["label"] for call in fake_st.button_calls]
        + [call["label"] for call in fake_st.text_input_calls]
        + [call["label"] for call in fake_st.selectbox_calls]
        + [call["label"] for call in fake_st.expander_calls]
        + fake_st.subheaders
    )
    assert "Continue a Project" in rendered_text
    assert "Search existing projects" in rendered_text
    assert "Search filters existing records only. It does not edit, rename, or delete projects." in rendered_text
    assert "compact overview of project, target product, host/context, status, updated time" in rendered_text
    assert "Select project to preview" in rendered_text
    assert "Typing filters the list only. Use Set as Active Project to change the active project." in rendered_text
    assert "Showing all existing projects." in rendered_text
    assert "Selected Project" in rendered_text
    assert "Project name: Project A" in rendered_text
    assert "Ref: Ref #1" in rendered_text
    assert "Target product: Product A" in rendered_text
    assert "Host / context: Host A" in rendered_text
    assert "Selected project: Project A" not in rendered_text
    assert "This only changes the active project. It does not edit, rename, or delete records." in rendered_text
    assert "Set as Active Project" in rendered_text
    assert "Open Active Project in Pathway Workspace" in rendered_text
    assert "Set a project as active first." in rendered_text
    assert "Project record removal" in rendered_text
    assert len(fake_st.radio_calls) == 0
    assert len(fake_st.selectbox_calls) == 1
    open_workspace_button = next(
        call for call in fake_st.button_calls if call["label"] == "Open Active Project in Pathway Workspace"
    )
    assert open_workspace_button["disabled"] is True


def test_pathway_projects_filter_panel_shows_selected_summary_once(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    projects = [
        {"id": 1, "name": "Project A", "target_product": "Product A", "host": "Host A", "updated_at": ""},
        {
            "id": 2,
            "name": "Nicotiana benthamiana artemisinin precursor documentation case",
            "target_product": "Artemisinin precursor documentation context",
            "host": "Nicotiana benthamiana documentation context",
            "updated_at": "",
        },
    ]
    fake_st.text_input_values[pathway_projects._PROJECT_SEARCH_KEY] = "Nicotiana"

    pathway_projects._render_project_selector(projects, lambda page_name: None)

    rendered_text = "\n".join(
        fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.write_messages
        + fake_st.subheaders
        + [call["label"] for call in fake_st.button_calls]
        + [call["label"] for call in fake_st.text_input_calls]
        + [call["label"] for call in fake_st.selectbox_calls]
    )

    assert "Showing 1 matching projects." in rendered_text
    assert "Selected Project" in rendered_text
    assert "Project name: Nicotiana benthamiana artemisinin precursor documentation case" in rendered_text
    assert "Ref: Ref #2" in rendered_text
    assert "Target product: Artemisinin precursor documentation context" in rendered_text
    assert "Host / context: Nicotiana benthamiana documentation context" in rendered_text
    assert "Selected project: Nicotiana benthamiana artemisinin precursor documentation case" not in rendered_text
    assert "Project name: Project A" not in rendered_text


def test_pathway_projects_filter_panel_shows_info_when_no_results_match(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    projects = [
        {"id": 1, "name": "Project A", "target_product": "Product A", "host": "Host A", "updated_at": ""},
        {"id": 2, "name": "Project B", "target_product": "Product B", "host": "Host B", "updated_at": ""},
    ]
    fake_st.text_input_values[pathway_projects._PROJECT_SEARCH_KEY] = "No Match"

    pathway_projects._render_project_selector(projects, lambda page_name: None)

    rendered_text = "\n".join(
        fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.write_messages
        + [call["label"] for call in fake_st.button_calls]
        + [call["label"] for call in fake_st.text_input_calls]
        + [call["label"] for call in fake_st.selectbox_calls]
    )

    assert "No existing projects match this search." in rendered_text
    assert "Set as Active Project" in rendered_text
    assert "Open Active Project in Pathway Workspace" in rendered_text
    assert "Set a project as active first." in rendered_text


def test_pathway_projects_open_workspace_action_is_enabled_when_active_project_exists(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    projects = [
        {"id": 1, "name": "Project A", "target_product": "Product A", "host": "Host A", "updated_at": ""},
        {"id": 2, "name": "Project B", "target_product": "Product B", "host": "Host B", "updated_at": ""},
    ]
    fake_st.session_state[pathway_projects.CURRENT_PROJECT_KEY] = 1

    pathway_projects._render_project_selector(projects, lambda page_name: None)

    rendered_text = "\n".join(
        fake_st.caption_messages
        + fake_st.write_messages
        + [call["label"] for call in fake_st.button_calls]
    )

    assert "Current active project: Project A" in rendered_text
    assert "Set a project as active first." not in rendered_text
    open_workspace_button = next(
        call for call in fake_st.button_calls if call["label"] == "Open Active Project in Pathway Workspace"
    )
    assert open_workspace_button["disabled"] is False


def test_pathway_projects_overview_uses_compact_dataframe_without_raw_html(monkeypatch):
    fake_st = _install_fake_streamlit(monkeypatch)
    projects = [
        {
            "id": 7,
            "name": "Nicotiana benthamiana artemisinin precursor documentation case",
            "target_product": "Artemisinin precursor documentation context",
            "host": "Nicotiana benthamiana documentation context",
            "status": "draft",
            "updated_at": "2026-06-15T09:45:00",
        }
    ]

    fake_st.session_state[pathway_projects.CURRENT_PROJECT_KEY] = 7
    pathway_projects._render_project_table(projects)

    rendered_text = "\n".join(
        fake_st.caption_messages
        + fake_st.write_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
    )
    overview_rows = fake_st.dataframes[0]

    assert len(fake_st.dataframes) == 1
    assert overview_rows == [
        {
            "Project": "Nicotiana benthamiana artemisinin precursor documentation case (Active)",
            "Target product": "Artemisinin precursor documentation context",
            "Host / context": "Nicotiana benthamiana documentation context",
            "Status": "draft",
            "Updated": "2026-06-15 09:45",
            "Ref": "Ref #7",
        }
    ]
    assert "Nicotiana benthamiana artemisinin precursor documentation case" not in rendered_text
    for forbidden in [
        "<div class='pathway-project-row'>",
        "<div class=\"pathway-project-row\">",
        "pathway-project-overview",
        "pathway-project-detail",
    ]:
        assert forbidden not in rendered_text


def test_pathway_workspace_active_project_summary_shows_chassis_neutral_host_context(monkeypatch):
    fake_st = FakeStreamlit()
    monkeypatch.setattr(pathway_workspace, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)

    pathway_workspace._render_active_project_summary(
        {
            "id": 7,
            "name": "Yeast project",
            "target_product": "General synbio review context",
            "host": "Saccharomyces cerevisiae documentation context",
            "updated_at": "",
        },
        steps=[],
        expression_links=[],
        test_records=[],
        snapshots=[],
    )

    rendered_text = "\n".join(
        fake_st.subheaders
        + fake_st.caption_messages
        + [call["label"] for call in fake_st.expander_calls]
    )

    assert "Host / Chassis Context Summary" in rendered_text
    assert "Supported contexts: Bacterial, Yeast, Mammalian, Plant, Generic / unspecified" in rendered_text
    assert "Project context label: Yeast" in rendered_text
    assert "plant is one supported context and not the default frame" in rendered_text.lower()
