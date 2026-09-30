from __future__ import annotations

from typing import Any

import streamlit as st

from services.pathway_report_service import PathwayReportConfig, generate_pathway_markdown_report
from services.pathway_repository import (
    create_pathway_documentation_snapshot,
    get_default_documentation_review,
    list_pathway_documentation_snapshots,
)
from services.pathway_snapshot_service import (
    DOCUMENTATION_SNAPSHOT_BOUNDARY_STATEMENT,
    build_documentation_snapshot_payload,
)


def _checkbox(label: str, value: bool = False, key: str | None = None) -> bool:
    if hasattr(st, "checkbox"):
        return bool(st.checkbox(label, value=value, key=key))
    return bool(value)


def _current_report_config_from_state() -> PathwayReportConfig:
    return PathwayReportConfig(
        include_project_metadata=bool(st.session_state.get("pathway_report_include_project_metadata", True)),
        include_pathway_steps=bool(st.session_state.get("pathway_report_include_pathway_steps", True)),
        include_linked_designs=bool(st.session_state.get("pathway_report_include_linked_designs", True)),
        include_test_records=bool(st.session_state.get("pathway_report_include_test_records", True)),
        include_suggestions=bool(st.session_state.get("pathway_report_include_suggestions", True)),
        include_review_notes=bool(st.session_state.get("pathway_report_include_review_notes", True)),
        include_full_gene_sequences=bool(st.session_state.get("pathway_report_include_full_gene_sequences", False)),
    )


def render_documentation_snapshots_section(
    project_id: int,
    project: dict[str, Any],
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    completeness_result: dict[str, Any],
    suggestions: list[dict[str, Any]],
) -> None:
    with st.expander("Documentation Snapshots", expanded=False):
        st.caption(DOCUMENTATION_SNAPSHOT_BOUNDARY_STATEMENT)
        st.caption(
            "Next action: save a documentation-only snapshot of the current Pathway workspace state for local traceability."
        )
        report_config = _current_report_config_from_state()
        include_markdown = _checkbox(
            "Include generated Markdown report text in this documentation snapshot",
            value=False,
            key="pathway_documentation_snapshot_include_markdown",
        )
        snapshot_title = st.text_input(
            "Snapshot title",
            placeholder="Optional label for this documentation snapshot",
            key="pathway_documentation_snapshot_title",
        )
        snapshot_note = st.text_area(
            "Snapshot note",
            placeholder="Optional note describing why this snapshot was saved.",
            height=90,
            key="pathway_documentation_snapshot_note",
        )
        save_clicked = st.button(
            "Save Documentation Snapshot",
            key="pathway_save_documentation_snapshot",
            use_container_width=True,
        )
        if save_clicked:
            report_markdown = None
            if include_markdown:
                report_markdown = generate_pathway_markdown_report(
                    project,
                    steps,
                    expression_links,
                    test_records,
                    completeness_result,
                    suggestions,
                    generated_at=None,
                    config=report_config,
                )
            ok, message, payload = build_documentation_snapshot_payload(
                project_id=project_id,
                snapshot_title=snapshot_title,
                snapshot_note=snapshot_note,
                report_config=report_config.__dict__,
                suggestions=suggestions,
                review_notes=project.get("documentation_review") or get_default_documentation_review(),
            )
            if ok:
                payload["snapshot_counts"] = {
                    "steps": len(steps),
                    "linked_expression_designs": len(expression_links),
                    "test_records": len(test_records),
                    "suggestions": len(suggestions),
                }
                payload["generated_markdown"] = {
                    "included": bool(include_markdown),
                    "text": report_markdown if include_markdown else None,
                }
                ok, message, _snapshot_id = create_pathway_documentation_snapshot(
                    project_id=project_id,
                    snapshot_title=snapshot_title,
                    snapshot_note=snapshot_note,
                    snapshot_payload=payload,
                    report_config=report_config.__dict__,
                    generated_markdown_text=report_markdown if include_markdown else None,
                    include_generated_markdown=include_markdown,
                )
            if ok:
                st.success("Documentation snapshot saved.")
                st.rerun()
            else:
                st.error(message)

        snapshots = list_pathway_documentation_snapshots(project_id)
        st.subheader("Saved Snapshots")
        if not snapshots:
            st.info("No documentation snapshots have been saved for this project yet.")
            return

        for snapshot in snapshots:
            title = snapshot.get("snapshot_title") or "Untitled Documentation Snapshot"
            preview = snapshot.get("snapshot_note") or "No snapshot note recorded."
            with st.expander(f"{snapshot.get('created_at') or 'Unknown time'} - {title}", expanded=False):
                st.caption(DOCUMENTATION_SNAPSHOT_BOUNDARY_STATEMENT)
                st.write(f"**Created:** {snapshot.get('created_at') or 'Not recorded'}")
                st.write(f"**Title:** {title}")
                st.write(f"**Note:** {preview}")
                st.write(f"**Schema version:** {snapshot.get('schema_version') or 'Not recorded'}")
                st.write(
                    f"**Generated Markdown captured:** {'Yes' if snapshot.get('include_generated_markdown') else 'No'}"
                )
                payload = snapshot.get("snapshot_payload") or {}
                metadata = payload.get("snapshot_metadata") or {}
                counts = payload.get("snapshot_counts") or {}
                st.write(
                    f"**Payload counts:** Steps {counts.get('steps', len(payload.get('pathway_steps') or []))}, "
                    f"Linked designs {counts.get('linked_expression_designs', len(payload.get('linked_expression_designs') or []))}, "
                    f"Test Records {counts.get('test_records', len(payload.get('test_records') or []))}, "
                    f"Suggestions {counts.get('suggestions', len(payload.get('suggestions') or []))}"
                )
                st.write(f"**Snapshot note:** {metadata.get('snapshot_note') or ''}")
