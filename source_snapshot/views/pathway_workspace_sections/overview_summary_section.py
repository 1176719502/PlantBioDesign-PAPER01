from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from services.project_catalog_reference_overview_presenter import build_project_catalog_reference_overview
from views import tool_typography
from views.pathway_workspace_sections.review_signals_section import (
    render_documentation_gaps,
    render_review_signals_summary,
)


def _render_project_status_summary(
    project: dict[str, Any],
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    completeness_summary: dict[str, Any] | None,
    suggestions: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
) -> None:
    """Render the Project Status Summary section at the top of the Overview tab."""
    st.subheader("Project Status Summary")
    st.caption(
        "Completeness score and Documentation status are documentation quality context only. They summarize coverage, "
        "linked records, traceability context, and missing documentation; they are not biological readiness, "
        "experimental conclusions, approvals, or scores for execution."
    )

    completeness_summary = completeness_summary or {}
    score = completeness_summary.get("score", 0)
    status = completeness_summary.get("status", "Unavailable")
    missing_items = completeness_summary.get("missing_items") or []

    with st.container(border=True):
        with tool_typography.temporary_streamlit_binding(st):
            tool_typography.render_compact_summary_cards(
                [
                    ("Documentation coverage", f"{score}%", "Across recorded workspace items"),
                    ("Documentation status", str(status), "Based on recorded documentation"),
                    ("Missing documentation items", str(len(missing_items)), "Flagged in current workspace summary"),
                ]
            )

        st.caption(
            f"Project: {project.get('name') or 'Not set'} | Host: {project.get('host') or 'Not set'} | "
            f"Target: {project.get('target_product') or 'Not set'} | Updated: {project.get('updated_at') or 'Not recorded'}"
        )
        if project.get("description"):
            st.caption(project["description"])
        if snapshots:
            latest = snapshots[0]
            st.caption(f"Latest snapshot: {latest.get('created_at') or 'Unknown time'} | {latest.get('snapshot_title') or 'Untitled'}")


def _step_evidence_matrix_rows(
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    review_signals: list[dict[str, Any]],
    completeness_result: dict[str, Any] | None,
    format_step_reaction,
) -> list[dict[str, Any]]:
    links_by_step: dict[int, list[dict[str, Any]]] = {}
    for link in expression_links:
        try:
            step_id = int(link.get("step_id"))
        except (TypeError, ValueError, AttributeError):
            continue
        links_by_step.setdefault(step_id, []).append(link)

    tests_by_step: dict[int, int] = {}
    for record in test_records:
        try:
            step_id = int(record.get("step_id"))
        except (TypeError, ValueError, AttributeError):
            continue
        tests_by_step[step_id] = tests_by_step.get(step_id, 0) + 1

    signals_by_step: dict[int, int] = {}
    for signal in review_signals:
        try:
            step_id = int(signal.get("related_step_id"))
        except (TypeError, ValueError, AttributeError):
            continue
        signals_by_step[step_id] = signals_by_step.get(step_id, 0) + 1

    completeness_result = completeness_result or {}
    step_summary_by_id: dict[int, dict[str, Any]] = {}
    for item in completeness_result.get("step_summaries") or []:
        try:
            step_id = int(item.get("step_id"))
        except (TypeError, ValueError, AttributeError):
            continue
        step_summary_by_id[step_id] = item

    rows: list[dict[str, Any]] = []
    for step in steps:
        try:
            step_id = int(step.get("id"))
        except (TypeError, ValueError):
            continue
        step_summary = step_summary_by_id.get(step_id, {})
        sequence_present = bool(str(step.get("gene_sequence") or "").strip())
        linked_design_present = bool(links_by_step.get(step_id))
        test_record_count = tests_by_step.get(step_id, 0)
        review_signal_count = signals_by_step.get(step_id, 0)
        if not review_signal_count:
            review_signal_count = len(step_summary.get("review_signals") or []) if isinstance(step_summary.get("review_signals"), list) else 0
        missing_parts: list[str] = []
        if not sequence_present:
            missing_parts.append("Missing sequence")
        if not linked_design_present:
            missing_parts.append("no linked expression design")
        if test_record_count == 0:
            missing_parts.append("no step-associated test record")
        if not missing_parts and step_summary.get("missing_items"):
            missing_parts.extend(str(item) for item in step_summary.get("missing_items") if str(item).strip())
        missing_documentation = "; ".join(missing_parts) if missing_parts else "No missing documentation recorded"
        rows.append(
            {
                "Step": step.get("step_name") or f"Step {step.get('step_order')}",
                "Reaction": format_step_reaction(step),
                "Gene / Enzyme": "/".join([value for value in [step.get("gene_name") or "", step.get("enzyme_name") or ""] if value]) or "",
                "Sequence recorded?": "Yes" if sequence_present else "No",
                "Expression design linked?": "Yes" if linked_design_present else "No",
                "Test record exists?": "Yes" if test_record_count > 0 else "No",
                "Review signals": review_signal_count,
                "Missing documentation": missing_documentation,
            }
        )
    return rows


def _render_step_evidence_matrix(
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    review_signals: list[dict[str, Any]],
    completeness_result: dict[str, Any] | None,
    format_step_reaction,
) -> None:
    st.subheader("Step Documentation Coverage Matrix")
    st.caption(
        "This matrix summarizes documentation coverage per pathway step. It is documentation-only, traceability-only, "
        "and it does not forecast production, optimize pathways, or certify readiness."
    )
    with st.expander("What the columns mean", expanded=False):
        st.markdown(
            """
- `Sequence recorded?` - whether a step sequence has been documented.
- `Expression design linked?` - whether an Expression Wizard design is linked for traceability.
- `Test record exists?` - whether a user-entered test record is associated with the step.
- `Review signals` - number of documentation review prompts for the step.
- `Missing documentation` - summarized documentation gaps for the step.
            """.strip()
        )
    rows = _step_evidence_matrix_rows(
        steps,
        expression_links,
        test_records,
        review_signals,
        completeness_result,
        format_step_reaction,
    )
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Add pathway steps to view the Step Documentation Coverage Matrix.")
    st.caption(
        "This matrix is for documentation and traceability only. It does not forecast production, optimize pathways, or certify readiness."
    )


def _render_demo_guide() -> None:
    with st.expander("Demo Guide", expanded=False):
        st.markdown(
            """
**Current project**

This is the documentation-only Nicotiana benthamiana artemisinin precursor documentation case. It is meant to show
how the workspace organizes project notes, candidate pathway records, source context, provenance context,
traceability records, review prompts, and documentation package value; it does not validate experiments or make
biological claims.

**Presenter focus**

Use this case to point at recorded context, not biological conclusions: pathway step records, linked design record
traceability, catalog/source context, review status, documentation snapshots, reports, and documentation-only
export package review.

**Next documentation steps**

1. Add or review pathway steps in the current documentation-only workspace.
2. Link Expression Wizard design records for traceability.
3. Review traceability status as documentation lineage context.
4. Capture review notes for unresolved questions, source review, documentation gaps, and manual follow-up.
5. Check Quality Review for documentation completeness and consistency.
6. Generate a documentation snapshot, report, or export package from **Project Outputs**.

**What each workspace tab is for**

- **Overview** - view project status and documentation coverage.
- **Pathway Steps** - record pathway step information and user-entered test records.
- **Linked Designs** - review traceability links to Expression Wizard design snapshots.
- **Linked Catalog Assets** - inspect source context, provenance context, and review metadata as documentation references.
- **Traceability** - review local lineage records for project, step, design, review, and snapshot context.
- **Review Signals** - review documentation gaps and documentation-only prompts.
- **Review Notes** - record human review context.

**Safety boundary**

- This workflow does not validate experiments.
- It does not predict yield.
- It does not optimize pathways.
- It does not provide wet-lab instructions.
- It does not recommend promoters or confirm host compatibility.
- It is not a biological recommendation, not an experimental validation, and not a wet-lab readiness judgment.
- It only helps organize and review project documentation.

**Important constraints**

- No new database tables are added.
- No external dependencies are added.
- No scoring logic is changed.
- Demo data uses bundled documentation-only seed records.
- This guide is UX-only.
            """.strip()
        )


def _render_catalog_reference_overview_panel(overview: dict[str, Any]) -> None:
    st.subheader("Catalog Reference Overview")
    st.caption(
        "Documentation-level overview of linked catalog references, pinned snapshots, source/provenance review, and record review gaps. "
        "It is not recommendation, validation, readiness, or prediction."
    )
    st.caption(
        "Bridge fields keep record identifier, catalog reference context, source/provenance review, record review status, documentation note, and project documentation context visible in the active workspace."
    )
    with st.container(border=True):
        with tool_typography.temporary_streamlit_binding(st):
            tool_typography.render_compact_summary_cards(
                [
                    ("Linked catalog references", str(overview.get("total_catalog_links", 0)), "Documentation links"),
                    ("Plant promoter references", str(overview.get("plant_promoter_link_count", 0)), "Catalog context rows"),
                    ("Pinned snapshots", str(overview.get("pinned_snapshot_count", 0)), "Reference snapshots"),
                    ("Review gaps", str(overview.get("missing_source_or_review_metadata_count", 0)), "Source/review metadata"),
                ]
            )
        st.caption(str(overview.get("coverage_note") or "No catalog reference context recorded."))
        st.caption(
            "Package/report/quality context: "
            f"package links {overview.get('package_export_context', {}).get('record_count', 0)}; "
            f"report {overview.get('review_report_note') or 'documentation-only review context'}; "
            f"quality {overview.get('quality_dashboard_note') or 'NOT_AVAILABLE'}."
        )

    rows = overview.get("linked_catalog_assets") or []
    if not rows:
        st.info("No catalog references are recorded for this project yet.")
        return

    with st.expander("Linked catalog reference rows", expanded=False):
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Asset": row.get("asset_label", ""),
                        "Type": row.get("asset_type", ""),
                        "Record identifier": row.get("record_identifier", ""),
                        "Link role": row.get("linkage_role", ""),
                        "Reference origin": row.get("reference_origin", ""),
                        "Catalog source/status": row.get("catalog_source_status", ""),
                        "Source context readback": row.get("source_context_readback", ""),
                        "Review-needed context": row.get("review_needed_context", ""),
                        "Review gap context": row.get("metadata_gap_context", ""),
                        "Catalog reference context": row.get("catalog_reference_context", ""),
                        "Snapshot": row.get("snapshot_state", ""),
                        "Source": row.get("source_label", ""),
                        "Record review status": row.get("documentation_status", ""),
                        "Project documentation context": row.get("project_documentation_context", ""),
                        "Documentation note": row.get("documentation_note", ""),
                    }
                    for row in rows
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )


def render_overview_summary_section(
    *,
    project: dict[str, Any],
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    completeness_result: dict[str, Any] | None,
    review_signals: list[dict[str, Any]],
    review_signal_summary: dict[str, Any],
    snapshots: list[dict[str, Any]],
    project_catalog_links: list[dict[str, Any]],
    project_level_tests: int,
    step_associated_tests: int,
    step_test_counts: dict[int, int],
    format_step_reaction,
) -> None:
    st.caption(
        "Overview summarizes the current project as the main local project workspace. Start with the Pathway Steps "
        "tab if this project has no pathway steps yet, then add linked design records, review notes, and project "
        "outputs as needed."
    )
    st.caption(
        "Expression Wizard is a design record subflow for gene-level records; Linked Designs shows local design records "
        "connected back to this project for documentation traceability."
    )

    _render_demo_guide()
    _render_catalog_reference_overview_panel(
        build_project_catalog_reference_overview(project, linked_catalog_assets=project_catalog_links)
    )

    completeness_summary = completeness_result or {}
    _render_project_status_summary(project, steps, expression_links, test_records, completeness_summary, [], snapshots)
    _render_step_evidence_matrix(
        steps,
        expression_links,
        test_records,
        review_signals,
        completeness_result,
        format_step_reaction,
    )
    render_review_signals_summary(
        review_signal_summary=review_signal_summary,
        expression_links=expression_links,
        steps=steps,
        test_records=test_records,
    )

    step_summaries = completeness_summary.get("step_summaries") or []
    with st.expander("Step-level documentation details", expanded=False):
        if step_summaries:
            rows = []
            for item in step_summaries:
                try:
                    step_id = int(item.get("step_id"))
                except (TypeError, ValueError):
                    step_id = 0
                rows.append(
                    {
                        "Order": item.get("step_order"),
                        "Step": item.get("step_name"),
                        "Score": item.get("score"),
                        "Expression Design Linked": "Yes" if item.get("has_expression_design") else "No",
                        "Has Test Records": "Yes" if step_test_counts.get(step_id, 0) > 0 else "No",
                        "Test Records": step_test_counts.get(step_id, 0),
                        "Missing Count": len(item.get("missing_items") or []),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.info("Add pathway steps to calculate step-level documentation details.")

    st.subheader("Test / Review / Snapshot status")
    t1, t2 = st.columns(2, gap="small")
    with t1:
        st.markdown("**Project-level test records**")
        st.markdown(str(project_level_tests))
    with t2:
        st.markdown("**Step-associated test records**")
        st.markdown(str(step_associated_tests))

    with st.expander("Documentation gaps summary", expanded=False):
        render_documentation_gaps(review_signals, steps)
