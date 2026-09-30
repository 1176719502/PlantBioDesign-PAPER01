from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st


Renderer = Callable[..., None]


def render_project_outputs_section(
    *,
    project: dict[str, Any],
    project_id: int,
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    completeness_result: dict[str, Any],
    suggestions: list[dict[str, Any]],
    review_signals: list[dict[str, Any]],
    snapshots: list[dict[str, Any]] | None,
    project_outputs_boundary_copy: str,
    project_outputs_structure_copy: str,
    project_outputs_guide_copy: str,
    import_preview_discovery_copy: str,
    project_outputs_contents_guide_copy: str,
    project_outputs_schema_boundary_copy: str,
    traceability_status_helper_copy: str,
    build_project_outputs_workflow_state: Callable[..., list[dict[str, Any]]],
    build_documentation_risk_summary: Callable[..., list[dict[str, Any]]],
    build_project_outputs_summary_card_items: Callable[..., list[tuple[str, str, str]]],
    build_project_outputs_workflow_table_rows: Callable[[list[dict[str, Any]] | None], list[dict[str, Any]]],
    build_project_outputs_risk_table_rows: Callable[[list[dict[str, Any]] | None], list[dict[str, Any]]],
    render_help_text: Callable[[str], None],
    render_compact_summary_cards: Callable[[list[tuple[str, str, str]]], None],
    render_project_outputs_traceability_summary: Renderer,
    render_documentation_snapshots_section: Renderer,
    render_documentation_report_download: Renderer,
    render_project_quality_dashboard_section: Renderer,
    render_project_review_report_section: Renderer,
    render_project_handoff_review_workspace_section: Renderer,
    render_export_package_section: Renderer,
    render_import_package_preview: Renderer,
    persisted_project_links: Callable[[Any], list[dict[str, Any]]],
) -> None:
    st.subheader("Project Outputs")
    render_help_text(
        "Project Outputs is the review and traceability area for the current local documentation workspace. It keeps "
        "snapshots, reports, quality review, export package review, and import preview together. Metrics stay visible; "
        "tables are supporting details."
    )
    workflow_rows = build_project_outputs_workflow_state(
        project,
        steps,
        expression_links,
        test_records,
        completeness_result,
        review_signals,
        snapshots=snapshots,
    )
    risk_rows = build_documentation_risk_summary(
        project,
        steps,
        expression_links,
        test_records,
        review_signals,
        snapshots=snapshots,
    )
    render_compact_summary_cards(build_project_outputs_summary_card_items(workflow_rows, risk_rows))
    st.caption(project_outputs_boundary_copy)
    st.caption(project_outputs_structure_copy)
    st.caption(project_outputs_guide_copy)
    with st.expander("Project Outputs detail tables and boundaries", expanded=False):
        st.caption(import_preview_discovery_copy)
        st.caption(project_outputs_contents_guide_copy)
        st.caption(project_outputs_schema_boundary_copy)
        st.caption(
            "Workflow state summary: documentation-only review status for output surfaces, package structure checks, "
            "traceability, and context completeness."
        )
        st.dataframe(
            pd.DataFrame(build_project_outputs_workflow_table_rows(workflow_rows)),
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "Documentation Risk Summary: documentation gaps, traceability gaps, and human review prompts for local project review only."
        )
        st.dataframe(
            pd.DataFrame(build_project_outputs_risk_table_rows(risk_rows)),
            width="stretch",
            hide_index=True,
        )
    render_project_outputs_traceability_summary(
        project,
        steps,
        expression_links,
        test_records,
        review_signals,
        snapshots,
        status_helper_copy=traceability_status_helper_copy,
    )
    snapshots_tab, reports_tab, quality_tab, handoff_tab, export_tab, import_tab = st.tabs(
        ["Documentation Snapshots", "Reports", "Quality Review", "Handoff Review", "Export Package", "Import Preview"]
    )
    with snapshots_tab:
        st.caption("Save documentation snapshot: preserve the current documentation state as a local review record.")
        render_documentation_snapshots_section(
            project_id,
            project,
            steps,
            expression_links,
            test_records,
            completeness_result,
            suggestions,
        )
    with reports_tab:
        st.markdown("<span id='pathway-project-output-reports'></span>", unsafe_allow_html=True)
        st.caption("Download documentation report: create a Markdown documentation review output from the recorded workspace fields.")
        render_documentation_report_download(
            project,
            steps,
            expression_links,
            test_records,
            completeness_result,
            review_signals,
        )
    with quality_tab:
        st.markdown("<span id='pathway-project-output-quality-review'></span>", unsafe_allow_html=True)
        st.caption(
            "Quality Review: review documentation completeness, linked records, traceability context, and missing documentation."
        )
        project_catalog_links = persisted_project_links(project.get("id"))
        render_project_quality_dashboard_section(
            project,
            steps,
            expression_links=expression_links,
            snapshots=snapshots,
            review_signals=review_signals,
            linked_catalog_assets=project_catalog_links,
        )
        st.markdown("---")
        render_project_review_report_section(
            project,
            steps,
            expression_links=expression_links,
            test_records=test_records,
            snapshots=snapshots,
            review_signals=review_signals,
            completeness_result=completeness_result,
            linked_catalog_assets=project_catalog_links,
        )
    with handoff_tab:
        st.markdown("<span id='pathway-project-output-handoff-review'></span>", unsafe_allow_html=True)
        st.caption(
            "Handoff Review: first-class read-only workspace for handoff center, package preview, "
            "snapshot / MD5 / QR payload, copy views, traceability matrix, and report markdown review."
        )
        project_catalog_links = persisted_project_links(project.get("id"))
        render_project_handoff_review_workspace_section(
            project,
            steps,
            linked_catalog_assets=project_catalog_links,
        )
    with export_tab:
        st.markdown("<span id='pathway-project-output-export-package'></span>", unsafe_allow_html=True)
        st.caption(
            "Build / review documentation-only export package: inspect package contents before downloading a local review artifact."
        )
        render_export_package_section(
            project,
            steps,
            expression_links,
            test_records,
            completeness_result,
            review_signals,
        )
    with import_tab:
        st.subheader("Import Preview")
        st.caption(
            "Review import package preview: inspect package structure, documentation fields, and dry-run planning. "
            "Preview is read-only: no database writes, overwrite, merge, restore, or project creation during preview."
        )
        render_import_package_preview()
