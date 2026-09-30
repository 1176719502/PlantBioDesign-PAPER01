from __future__ import annotations

from typing import Any

import streamlit as st

from services.pathway_report_service import PathwayReportConfig, generate_pathway_markdown_report
from services.project_export_package_service import (
    build_project_export_contents_preview,
    build_project_export_filename,
    build_project_export_payload,
    build_project_export_zip,
)
from services.tool_artifact_service import list_tool_artifacts
from views.pathway_workspace_sections.project_documentation_package_section import (
    render_project_documentation_package_export_panel,
)


def render_export_package_section(
    project: dict[str, Any],
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    completeness_result: dict[str, Any],
    review_signals: list[dict[str, Any]],
) -> None:
    st.markdown("**Project Export Package**")
    st.caption("Documentation-only package summary for review, traceability, and local archive use.")
    st.caption(
        "Next action: review package contents, download the package, then use Import Preview for read-only structure and field checks."
    )
    st.caption(
        "Boundary: this export does not certify experimental readiness, predict yield, optimize pathways, or provide wet-lab instructions."
    )
    # Source-only boundary anchor for regression tests: does not provide wet-lab protocols.
    st.caption(
        "Import Preview stays read-only. A separate gated import-as-new action may create a local "
        "documentation-only project only after validation, safety review, dry-run planning, and explicit confirmation."
    )
    linked_tool_artifacts = list_tool_artifacts(project_id=project.get("id"))
    contents_preview = build_project_export_contents_preview(linked_tool_artifacts)
    st.caption("Package contents preview")
    st.caption(
        "Includes project summary, pathway steps, review notes, documentation snapshots, linked documentation artifacts, and manifest metadata when available."
    )
    st.caption("Package contents are documentation records only.")
    st.caption("Raw payload previews are for traceability only.")
    with st.expander("Package contents", expanded=False):
        for section in contents_preview["sections"]:
            st.caption(f"- {section}")
        st.caption("Boundary summary: documentation-only package for review and traceability; no readiness, yield, optimization, or protocol claims.")
    with st.expander("Post-download next steps", expanded=False):
        st.caption("- Download the documentation package.")
        st.caption("- Keep the package as a review/archive artifact.")
        st.caption("- Use Project Import Package Preview for read-only package structure checks.")
        st.caption("- Keep review decisions separate from readiness or execution claims.")
        st.caption(
            "- Blocked / NO-GO states apply only to the gated create-as-new action or to prohibited biological "
            "execution/readiness claims."
        )
    documentation_report = generate_pathway_markdown_report(
        project,
        steps,
        expression_links,
        test_records,
        completeness_result,
        review_signals,
        generated_at=None,
        config=PathwayReportConfig(),
    )
    payload = build_project_export_payload(
        project=project,
        steps=steps,
        expression_links=expression_links,
        test_records=test_records,
        completeness_result=completeness_result,
        review_signals=review_signals,
        linked_tool_artifacts=linked_tool_artifacts,
        documentation_report=documentation_report,
    )
    st.download_button(
        "Download Project Export Package",
        data=build_project_export_zip(payload),
        file_name=build_project_export_filename(project, payload.get("manifest", {}).get("exported_at")),
        mime="application/zip",
        use_container_width=True,
    )
    st.markdown("---")
    render_project_documentation_package_export_panel(project)
