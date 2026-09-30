from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from services.pathway_report_service import PathwayReportConfig


MarkdownReportGenerator = Callable[..., str]
ReportFilenameBuilder = Callable[[dict[str, Any]], str]


def render_documentation_report_download_section(
    project: dict[str, Any],
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    completeness_result: dict[str, Any],
    review_signals: list[dict[str, Any]],
    *,
    generate_markdown_report: MarkdownReportGenerator,
    build_report_filename: ReportFilenameBuilder,
) -> None:
    st.subheader("Documentation Report")
    st.caption(
        "Download a documentation-only Markdown report for the current Pathway workspace. The report summarizes "
        "recorded project data, pathway steps, linked designs, test records, completeness coverage, and review signals. "
        "It is a Markdown documentation review output for traceability and review only, and it does not certify "
        "experimental readiness."
    )
    with st.expander("Markdown Report Options", expanded=False):
        st.caption(
            "Choose optional sections for this Markdown report only. Required documentation-only, readiness, limitation, "
            "and primer-risk language cannot be disabled."
        )
        include_project_metadata = st.checkbox(
            "Include project metadata",
            value=True,
            key="pathway_report_include_project_metadata",
        )
        include_pathway_steps = st.checkbox(
            "Include pathway step details",
            value=True,
            key="pathway_report_include_pathway_steps",
        )
        include_linked_designs = st.checkbox(
            "Include linked Expression Wizard design summaries",
            value=True,
            key="pathway_report_include_linked_designs",
        )
        include_test_records = st.checkbox(
            "Include Test Records",
            value=True,
            key="pathway_report_include_test_records",
        )
        include_suggestions = st.checkbox(
            "Include review signals",
            value=True,
            key="pathway_report_include_suggestions",
        )
        include_review_notes = st.checkbox(
            "Include Review Notes",
            value=True,
            key="pathway_report_include_review_notes",
        )
        include_full_gene_sequences = st.checkbox(
            "Include full gene sequences",
            value=False,
            key="pathway_report_include_full_gene_sequences",
            help="Includes complete gene sequence text in the Markdown report. Use caution when sharing reports.",
        )
        report_config = PathwayReportConfig(
            include_project_metadata=include_project_metadata,
            include_pathway_steps=include_pathway_steps,
            include_linked_designs=include_linked_designs,
            include_test_records=include_test_records,
            include_suggestions=include_suggestions,
            include_review_notes=include_review_notes,
            include_full_gene_sequences=include_full_gene_sequences,
        )
    report_markdown = generate_markdown_report(
        project,
        steps,
        expression_links,
        test_records,
        completeness_result,
        review_signals,
        generated_at=None,
        config=report_config,
    )
    st.download_button(
        "Download Documentation Report",
        data=report_markdown,
        file_name=build_report_filename(project),
        mime="text/markdown",
        use_container_width=True,
    )
