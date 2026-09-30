from __future__ import annotations

import html
from typing import Any

import streamlit as st

from services.documentation_consistency_provenance_view_model import (
    build_documentation_consistency_provenance_panel,
)
from services.candidate_evidence_review_matrix import (
    build_candidate_evidence_review_matrix,
)
from services.candidate_evidence_human_review_queue import (
    build_candidate_evidence_human_review_queue,
)
from services.candidate_evidence_review_snapshot_formatter import (
    format_candidate_evidence_review_snapshot,
)
from services.component_library_asset_readback_presenter import (
    build_component_library_asset_readback_presenter,
)
from services.documentation_review_label_helper import REVIEW_NEXT_COLUMN_LABEL, review_next_table_value
from services.project_quality_dashboard_service import (
    build_project_quality_dashboard,
)
from services.generated_output_boundary import normalize_generated_output_claims
from services.project_output_boundary_copy import (
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE,
    PROJECT_OUTPUT_SCOPE_NOTE,
)
from services.project_output_section_overview import build_project_output_sections_overview
from services.project_review_report_service import build_project_review_report
from services.project_review_follow_up_index import build_project_review_follow_up_index
from services.project_review_handoff_center_service import (
    COMPONENT_LIBRARY_HANDOFF_READBACK_BOUNDARY_NOTE,
    COMPONENT_LIBRARY_HANDOFF_READBACK_EMPTY_STATE,
    COMPONENT_LIBRARY_HANDOFF_READBACK_INTRO,
    build_project_review_handoff_center,
)
from services.project_handoff_package_preview_service import build_project_handoff_package_preview
from services.validation_case_package_service import build_validation_case_package
from services.host_chassis_context_presenter import build_host_chassis_context_summary
from services.expression_vector_design_package_markdown_formatter import (
    format_expression_vector_design_package_preview_markdown,
)
from services.expression_vector_package_record_input_adapter import (
    CURRENT_RECORD_SOURCE,
    EMPTY_RECORD_SOURCE,
    build_expression_vector_package_record_input,
    build_expression_vector_package_source_readback_rows,
)
from services.expression_vector_sample_walkthrough_helper import (
    build_single_gene_expression_vector_sample_walkthrough,
)
from services.expression_construct_presenter import (
    COMPONENT_REVIEW_SUMMARY_LABELS,
    build_project_construct_component_review_queue,
    build_expression_construct_report_views,
)
from services.tool_artifact_service import list_tool_artifacts
from views import tool_typography
from views.pathway_workspace_sections.responsive_review_tables import (
    render_responsive_detail_table,
    render_wrapped_summary_cards,
)
from views.pathway_workspace_sections.step2_component_context_session import (
    current_step2_component_context_readback,
)

PROJECT_QUALITY_DASHBOARD_BOUNDARY_COPY = (
    f"{PROJECT_OUTPUT_SCOPE_NOTE} This dashboard summarizes documentation completeness only. "
    f"{PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE} {PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE} "
    "It does not certify experiment-use state. It does not forecast yield. "
    "It does not tune pathways. It does not provide wet-lab instructions."
)

CANDIDATE_EVIDENCE_MATRIX_FIELD_LEGEND = (
    ("candidate_label", "display name used for the local review row"),
    ("source_category", "source family or catalog context recorded with the row"),
    ("source_identifier", "source accession, profile id, URL, or local reference id"),
    ("provenance_status", "whether source category, identifier, and hash are recorded"),
    ("record_review_status", "whether required documentation fields are complete"),
    ("review_focus", "whether the row needs source/provenance review, evidence-record review, or manual follow-up"),
    ("review_status", "manual review state recorded with the source context"),
    ("missing_fields", "documentation fields still absent from the row"),
    ("next_manual_action", "manual documentation review note for follow-up"),
    ("boundary_note", "documentation-only boundary for this matrix row"),
)

CANDIDATE_EVIDENCE_MATRIX_MANUAL_REVIEW_NOTE = (
    "This matrix supports manual documentation review planning only; it is read-only and does not select, "
    "assign numeric review values, or make downstream-use clearance decisions for candidates."
)
CANDIDATE_EVIDENCE_REVIEW_SNAPSHOT_NOTE = (
    "Collapsed read-only Markdown snapshot for mentor/demo walkthroughs, human review support, and documentation triage only."
)
CANDIDATE_EVIDENCE_REVIEW_SNAPSHOT_BOUNDARY_NOTE = (
    "Use this snapshot to summarize documented source trace, missing fields, and manual follow-up. "
    "It is not a candidate decision or biological proof record."
)
HUMAN_REVIEW_QUEUE_NOTE = (
    "Collapsed read-only queue for documentation triage and human review follow-up only."
)
HUMAN_REVIEW_QUEUE_BOUNDARY_NOTE = (
    "This queue supports manual review only. It does not rank, recommend, validate, "
    "or confirm biological use suitability."
)
GENERIC_COMPONENT_LIBRARY_ASSET_READBACK_DASHBOARD_COPY = (
    "Read-only generic Component Library asset readback for existing linked project documentation rows. "
    "This section reuses the Component Library presenter and does not create a universal asset database model."
)
STEP2_COMPONENT_CONTEXT_MANUAL_FOLLOW_UP_DASHBOARD_COPY = (
    "Current-session review context for source/provenance review, record review status, and manual follow-up only. "
    "This summary is not counted as a Dashboard gap and is not saved as evidence."
)
STEP2_COMPONENT_CONTEXT_MANUAL_FOLLOW_UP_EMPTY_STATE = (
    "No current Step 2 Component Library context is available for this Dashboard summary."
)
STEP2_COMPONENT_CONTEXT_MANUAL_FOLLOW_UP_BOUNDARY_COPY = (
    "This collapsed summary stays separate from Dashboard gap accounting, saved state, package data, "
    "Codon Usage Preview linkage, biological recommendation logic, validation, optimization, expression prediction, "
    "and wet-lab use judgment."
)
EXPRESSION_VECTOR_PACKAGE_PREVIEW_COPY = (
    "Read-only Markdown preview for documentation review only. It summarizes recorded project context; "
    "no export package, saved record, final vector sequence, component choice, procedure content, forecast, "
    "or wet-lab use judgment is created here."
)
EXPRESSION_VECTOR_PACKAGE_PREVIEW_LIMITATION_COPY = (
    "Draft / needs review: check source/provenance, cassette slots, sequence checks, and manual follow-up."
)
EXPRESSION_VECTOR_PACKAGE_SOURCE_READBACK_COPY = (
    "Current-record source readback: shows which preview fields came from current records, which fields are missing, "
    "and what needs source/provenance or manual review before reading the Markdown preview."
)
SINGLE_GENE_SAMPLE_WALKTHROUGH_COPY = (
    "Learning aid only for one gene / one protein / one enzyme expression-vector preparation. "
    "It shows where to start, what is recorded, which source/provenance gaps remain, and what manual follow-up is needed."
)
SINGLE_GENE_SAMPLE_WALKTHROUGH_BOUNDARY_COPY = (
    "The sample is read-only and in-memory only. It does not save records, export packages, create package data, "
    "generate a final vector sequence, rewrite codons, choose biological components, provide procedure content, "
    "forecast outcomes, validate biology, or judge downstream use."
)


def _render_readability_note(copy: str) -> None:
    st.markdown(f"<div class='tool-help-text'>{html.escape(copy)}</div>", unsafe_allow_html=True)


def _render_consistency_item(item: dict[str, Any]) -> None:
    label = item.get("label") or "Documentation consistency item"
    status = item.get("status") or "not_available"
    detail = item.get("detail") or "No detail recorded."
    source = item.get("source") or "Local documentation records"
    st.caption(f"- {label}: {status}. {detail} Source: {source}.")


def _dashboard_review_context_summary(dashboard: dict[str, Any]) -> dict[str, Any]:
    metrics = dashboard.get("metrics") if isinstance(dashboard.get("metrics"), dict) else {}
    completeness = dashboard.get("documentation_completeness")
    guidance = dashboard.get("review_guidance") or dashboard.get("next_actions") or []
    boundary_notes = dashboard.get("boundary_notes") or []
    return {
        "status": dashboard.get("overall_documentation_status", "NOT_AVAILABLE"),
        "pathway_steps": metrics.get("pathway_steps_count", 0),
        "linked_artifacts": metrics.get("linked_artifacts_count", 0),
        "host_context_records": metrics.get("host_context_record_count", 0),
        "linked_promoter_profiles": metrics.get("linked_plant_promoter_profile_count", 0),
        "review_gaps": metrics.get("review_gap_count", 0),
        "checklist_items": len(completeness) if isinstance(completeness, list) else 0,
        "guidance_items": len(guidance) if isinstance(guidance, list) else 0,
        "boundary_notes": len(boundary_notes) if isinstance(boundary_notes, list) else 0,
    }


def _safe_int(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _step2_component_context_manual_follow_up_summary(
    step2_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(step2_context, dict):
        return {
            "status": "NOT_AVAILABLE",
            "total_rows": 0,
            "source_provenance_review_rows": 0,
            "record_review_status_rows": 0,
            "manual_follow_up_rows": 0,
            "empty_state": STEP2_COMPONENT_CONTEXT_MANUAL_FOLLOW_UP_EMPTY_STATE,
        }

    rows = [row for row in step2_context.get("rows") or [] if isinstance(row, dict)]
    source_rows = sum(1 for row in rows if _first_text(row.get("source_provenance_review")))
    record_review_rows = sum(1 for row in rows if _first_text(row.get("record_review_status")))
    manual_follow_up_rows = sum(
        1
        for row in rows
        if "manual follow-up"
        in " ".join(
            [
                _first_text(row.get("context_state")),
                _first_text(row.get("source_provenance_review")),
                _first_text(row.get("record_review_status")),
                _first_text(row.get("manual_follow_up")),
            ]
        ).casefold()
    )
    summary = step2_context.get("summary") if isinstance(step2_context.get("summary"), dict) else {}
    total_rows = _safe_int(summary.get("total_rows"), len(rows))
    if total_rows <= 0:
        total_rows = len(rows)

    return {
        "status": "AVAILABLE" if rows else "NOT_AVAILABLE",
        "total_rows": total_rows,
        "source_provenance_review_rows": source_rows,
        "record_review_status_rows": record_review_rows,
        "manual_follow_up_rows": _safe_int(summary.get("manual_follow_up_rows"), manual_follow_up_rows),
        "empty_state": _first_text(
            step2_context.get("empty_state"),
            STEP2_COMPONENT_CONTEXT_MANUAL_FOLLOW_UP_EMPTY_STATE,
        ),
    }


def _render_step2_component_context_manual_follow_up_summary(
    step2_context: dict[str, Any] | None,
) -> None:
    summary = _step2_component_context_manual_follow_up_summary(step2_context)

    with st.expander("Step 2 Component Library context - manual follow-up summary", expanded=False):
        st.caption(STEP2_COMPONENT_CONTEXT_MANUAL_FOLLOW_UP_DASHBOARD_COPY)
        st.caption(STEP2_COMPONENT_CONTEXT_MANUAL_FOLLOW_UP_BOUNDARY_COPY)
        st.caption("Shows current-session review context only; it does not list component choices as Dashboard review items.")
        if summary["status"] != "AVAILABLE":
            st.info(str(summary.get("empty_state") or STEP2_COMPONENT_CONTEXT_MANUAL_FOLLOW_UP_EMPTY_STATE))
            return

        summary_cols = st.columns(4, gap="small")
        summary_cols[0].metric("current-session review context", summary.get("total_rows", 0))
        summary_cols[1].metric("source/provenance review", summary.get("source_provenance_review_rows", 0))
        summary_cols[2].metric("record review status", summary.get("record_review_status_rows", 0))
        summary_cols[3].metric("manual follow-up", summary.get("manual_follow_up_rows", 0))


def _nested_mapping(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    return value if isinstance(value, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        clean = str(value or "").strip()
        if clean:
            return clean
    return ""


def _candidate_evidence_records_from_linked_catalog_assets(
    linked_catalog_assets: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for link in linked_catalog_assets or []:
        if not isinstance(link, dict):
            continue
        source_context = _nested_mapping(link, "source_context_snapshot")
        review_context = _nested_mapping(link, "review_status_snapshot")
        asset_snapshot = _nested_mapping(link, "asset_snapshot")
        records.append(
            {
                "candidate_label": _first_text(
                    link.get("asset_display_name"),
                    asset_snapshot.get("asset_label"),
                    asset_snapshot.get("display_name"),
                    link.get("asset_id"),
                ),
                "source_category": _first_text(
                    source_context.get("catalog"),
                    source_context.get("source_category"),
                    link.get("asset_type"),
                ),
                "source_identifier": _first_text(
                    source_context.get("profile_id"),
                    source_context.get("stable_source_identifier"),
                    source_context.get("source_accession"),
                    link.get("asset_id"),
                ),
                "source_hash": _first_text(
                    asset_snapshot.get("snapshot_hash"),
                    asset_snapshot.get("source_hash"),
                    asset_snapshot.get("content_hash"),
                    link.get("snapshot_hash"),
                ),
                "review_status": _first_text(
                    review_context.get("review_status"),
                    review_context.get("human_review_status"),
                    review_context.get("curation_statuses"),
                    review_context.get("status"),
                    link.get("review_status"),
                ),
                "source_review_status": _first_text(
                    source_context.get("source_review_status"),
                    review_context.get("source_review_status"),
                ),
                "curation_status": _first_text(
                    review_context.get("curation_status"),
                    review_context.get("curation_statuses"),
                ),
                "not_runtime_seed": link.get("not_runtime_seed"),
                "snapshot_scope": asset_snapshot.get("snapshot_scope"),
            }
        )
    return records


def _candidate_evidence_matrix_table_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    table_rows: list[dict[str, Any]] = []
    for row in matrix.get("rows") or []:
        if not isinstance(row, dict):
            continue
        missing_fields = row.get("missing_fields")
        table_rows.append(
            {
                "Candidate label": row.get("candidate_label", ""),
                "Source trace": row.get("source_category", ""),
                "Source identifier": row.get("source_identifier", ""),
                "Record review status": row.get("record_review_status") or row.get("metadata_status", ""),
                "Review focus": row.get("review_focus", ""),
                "Source trace status": row.get("provenance_status", ""),
                "Review status": row.get("review_status", ""),
                "Missing fields": ", ".join(missing_fields) if isinstance(missing_fields, list) else "",
                "Next documentation review action": row.get("next_manual_action", ""),
            }
        )
    return table_rows


def _render_candidate_evidence_matrix_field_legend() -> None:
    st.caption("Field legend:")
    for field_name, explanation in CANDIDATE_EVIDENCE_MATRIX_FIELD_LEGEND:
        st.caption(f"- {field_name}: {explanation}.")


def _candidate_evidence_human_review_queue_table_rows(queue: dict[str, Any]) -> list[dict[str, Any]]:
    table_rows: list[dict[str, Any]] = []
    for row in queue.get("rows") or []:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            {
                "Queue item id": row.get("queue_item_id", ""),
                "Candidate label": row.get("candidate_label", ""),
                "Category": row.get("category_label", ""),
                "Severity": row.get("severity_label", ""),
                "Issue": row.get("issue", ""),
                "Human follow-up": row.get("human_follow_up", ""),
                "Source context": row.get("source_context", ""),
            }
        )
    return table_rows


def _expression_construct_follow_up_table_rows(queue: dict[str, Any]) -> list[dict[str, Any]]:
    table_rows: list[dict[str, Any]] = []
    for row in queue.get("rows") or []:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            {
                "Construct label": row.get("Construct label", ""),
                "Cassette label": row.get("Cassette label", ""),
                "Component label": row.get("Component label", ""),
                "Component category": row.get("Component category", ""),
                "Issue type": row.get("Issue type", ""),
                "Issue detail": row.get("Issue detail", ""),
                "Manual follow-up note": row.get("Manual follow-up note", ""),
            }
        )
    return table_rows


def _generic_component_library_asset_readback_table_rows(
    presenter: dict[str, Any],
) -> list[dict[str, str]]:
    columns = presenter.get("columns") if isinstance(presenter.get("columns"), list) else []
    rows: list[dict[str, str]] = []
    for row in presenter.get("rows") or []:
        if not isinstance(row, dict):
            continue
        row_view = dict(row)
        if "Record review status" in columns and "Record review status" not in row_view:
            row_view["Record review status"] = row_view.get("Evidence/review metadata", "")
        rows.append({str(column): str(row_view.get(column, "")) for column in columns})
    return rows


def _render_generic_component_library_asset_readback_review(
    linked_catalog_assets: list[dict[str, Any]] | None,
) -> None:
    presenter = build_component_library_asset_readback_presenter(
        linked_catalog_assets=linked_catalog_assets or []
    )
    summary = presenter.get("summary") if isinstance(presenter.get("summary"), dict) else {}
    table_rows = _generic_component_library_asset_readback_table_rows(presenter)

    with st.expander("Generic Component Library asset readback", expanded=False):
        st.caption(GENERIC_COMPONENT_LIBRARY_ASSET_READBACK_DASHBOARD_COPY)
        st.caption(str(presenter.get("documentation_boundary_note") or "Documentation-only asset readback."))
        st.caption(str(presenter.get("source_identity_note") or "Stored source and provenance identifiers are preserved."))

        metric_cols = st.columns(4, gap="small")
        metric_cols[0].metric("asset readback rows", summary.get("total_asset_rows", 0))
        metric_cols[1].metric("asset type groups", summary.get("asset_type_count", 0))
        metric_cols[2].metric(
            "source/provenance rows",
            summary.get("rows_with_source_provenance_identity", 0),
        )
        metric_cols[3].metric(
            "record review rows",
            summary.get("rows_with_evidence_review_metadata", 0),
        )

        if not table_rows:
            st.info(str(presenter.get("empty_state") or "No Component Library source/provenance or record review status is available."))
            return

        st.dataframe(table_rows, hide_index=True)


def _render_expression_construct_documentation_follow_up(queue: dict[str, Any]) -> None:
    summary = queue.get("summary") if isinstance(queue.get("summary"), dict) else {}
    table_rows = _expression_construct_follow_up_table_rows(queue)

    with st.expander("Expression construct documentation follow-up", expanded=False):
        st.caption(
            "Read-only project-level queue for Expression Construct component documentation follow-up."
        )
        st.caption(
            str(
                queue.get("caption")
                or (
                    "Review full construct, cassette, component, source/reference, provenance, and review-note readback in Expression Constructs."
                )
            )
        )
        for note in queue.get("boundary_notes") or []:
            st.caption(f"- {note}")

        metric_cols = st.columns(4, gap="small")
        metric_cols[0].metric(
            COMPONENT_REVIEW_SUMMARY_LABELS["total_component_rows"],
            summary.get("total_component_rows", 0),
        )
        metric_cols[1].metric(
            COMPONENT_REVIEW_SUMMARY_LABELS["rows_with_source_reference_context"],
            summary.get("rows_with_source_reference_context", 0),
        )
        metric_cols[2].metric(
            COMPONENT_REVIEW_SUMMARY_LABELS["rows_missing_source_reference_context"],
            summary.get("rows_missing_source_reference_context", 0),
        )
        metric_cols[3].metric(
            COMPONENT_REVIEW_SUMMARY_LABELS["rows_needing_manual_follow_up"],
            summary.get("rows_needing_manual_follow_up", 0),
        )

        detail_cols = st.columns(3, gap="small")
        detail_cols[0].metric(
            COMPONENT_REVIEW_SUMMARY_LABELS["rows_with_sequence_availability_note"],
            summary.get("rows_with_sequence_availability_note", 0),
        )
        detail_cols[1].metric(
            COMPONENT_REVIEW_SUMMARY_LABELS["rows_with_review_metadata_status"],
            summary.get("rows_with_review_metadata_status", 0),
        )
        detail_cols[2].metric(
            COMPONENT_REVIEW_SUMMARY_LABELS["rows_with_review_note"],
            summary.get("rows_with_review_note", 0),
        )

        if not table_rows:
            st.info(str(queue.get("empty_state_message") or "No construct documentation follow-up items are visible."))
            return

        st.dataframe(table_rows, hide_index=True)


def _render_candidate_evidence_human_review_queue(matrix: dict[str, Any]) -> None:
    queue = build_candidate_evidence_human_review_queue(matrix)
    summary = queue.get("summary") if isinstance(queue.get("summary"), dict) else {}
    table_rows = _candidate_evidence_human_review_queue_table_rows(queue)

    with st.expander("Human Review Queue", expanded=False):
        st.caption(HUMAN_REVIEW_QUEUE_NOTE)
        st.caption(HUMAN_REVIEW_QUEUE_BOUNDARY_NOTE)

        summary_cols = st.columns(4, gap="small")
        summary_cols[0].metric("queue items", summary.get("queue_item_count", 0))
        summary_cols[1].metric("source/provenance gaps", summary.get("provenance_gap_count", 0))
        summary_cols[2].metric("metadata needs review", summary.get("metadata_gap_count", 0))
        summary_cols[3].metric("manual follow-up", summary.get("review_follow_up_count", 0))

        for note in queue.get("boundary_notes") or []:
            st.caption(f"- {note}")

        if not table_rows:
            st.info(
                str(
                    queue.get("empty_state_message")
                    or "No human review follow-up items are currently queued."
                )
            )
            return

        st.dataframe(table_rows, hide_index=True)


def _render_project_review_follow_up_index_summary(
    project: dict[str, Any],
    steps: list[dict[str, Any]] | None,
    linked_tool_artifacts: list[dict[str, Any]] | None,
    linked_catalog_assets: list[dict[str, Any]] | None,
    step2_component_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    report_project = dict(project)
    report_project["pathway_steps"] = steps or []
    report_project["project_asset_links"] = linked_catalog_assets or []
    report = build_project_review_report(
        report_project,
        linked_artifacts=linked_tool_artifacts,
        saved_designs=None,
        export_summary={
            "status": "AVAILABLE",
            "package_contents_preview_status": "AVAILABLE",
            "last_export_status": "NOT_AVAILABLE",
            "documentation_only_boundary": "Project export packages are documentation-only review packages.",
        },
        import_safety_summary=None,
        step2_component_context=step2_component_context,
    )
    candidate_queue = report.get("candidate_evidence_human_review_queue") or {}
    promoter_queue = report.get("plant_promoter_evidence_gap_review") or {}
    follow_up_index = report.get("project_review_follow_up_index") or build_project_review_follow_up_index({}, {})
    summary = follow_up_index.get("summary") or {}

    with st.expander("Project Review Follow-up Index", expanded=False):
        st.markdown("**Project Review Follow-up Index**")
        st.caption(
            "Collapsed read-only follow-up summary for manual documentation triage across project review queues."
        )
        for note in follow_up_index.get("boundary_notes") or []:
            st.caption(f"- {note}")
        s1, s2 = st.columns(2, gap="small")
        s1.metric("total follow-up items", summary.get("total_follow_up_items", 0))
        s2.metric(
            "candidate evidence items",
            (summary.get("source_section_counts") or {}).get("candidate_evidence", 0),
        )
        category_counts = summary.get("category_counts") or {}
        if category_counts:
            st.caption(
                "Counts by category: "
                + ", ".join(f"{label}: {count}" for label, count in category_counts.items())
            )
        if not follow_up_index.get("rows"):
            st.info(str(follow_up_index.get("empty_state_message") or "No follow-up items are currently aggregated."))
    return follow_up_index, candidate_queue, promoter_queue, report.get("step2_component_context_appendix") or {}


def _handoff_center_table_rows(handoff: dict[str, Any]) -> list[dict[str, Any]]:
    table_rows: list[dict[str, Any]] = []
    for row in handoff.get("follow_up_rows") or []:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            {
                "Source surface": row.get("source_surface", ""),
                "Item label": row.get("item_label", ""),
                "Issue type": row.get("issue_type", ""),
                "Manual follow-up note": row.get("manual_follow_up_note", ""),
                REVIEW_NEXT_COLUMN_LABEL: review_next_table_value(row),
            }
        )
    return table_rows


def _handoff_package_preview_surface_rows(preview: dict[str, Any]) -> list[dict[str, Any]]:
    table_rows: list[dict[str, Any]] = []
    for row in preview.get("included_documentation_preview") or []:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            {
                "Documentation surface": row.get("label", ""),
                "Status": row.get("status", ""),
                "Manual follow-up": row.get("manual_follow_up_count", 0),
                "Review note": row.get("note", ""),
            }
        )
    return table_rows


def _handoff_review_sheet_section_rows(preview: dict[str, Any]) -> list[dict[str, str]]:
    table_rows: list[dict[str, str]] = []
    for row in preview.get("review_sheet_sections") or []:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            {
                "Review sheet section": str(row.get("label", "")),
                "Purpose": str(row.get("description", "")),
            }
        )
    return table_rows


def _handoff_traceability_matrix_rows(preview: dict[str, Any]) -> list[dict[str, Any]]:
    table_rows: list[dict[str, Any]] = []
    for row in preview.get("traceability_matrix_rows") or []:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            {
                "Source surface": row.get("source_surface", ""),
                "Item label": row.get("item_label", ""),
                "Documentation context": row.get("documentation_context", ""),
                "Source/reference context": row.get("source_reference_context", ""),
                "Provenance/review context": row.get("provenance_review_context", ""),
                "Manual follow-up status": row.get("manual_follow_up_status", ""),
                REVIEW_NEXT_COLUMN_LABEL: review_next_table_value(row),
                "Included in review sheet": row.get("included_in_review_sheet", ""),
            }
        )
    return table_rows


def _handoff_workspace_nav_table_rows(preview: dict[str, Any]) -> list[dict[str, str]]:
    table_rows: list[dict[str, str]] = []
    for row in preview.get("handoff_workspace_nav_rows") or []:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            {
                "Workspace area": str(row.get("workspace_area", "")),
                "Current status": str(row.get("current_status", "")),
                "Key count or identity": str(row.get("key_count_or_identity", "")),
                "Review surface": str(row.get("review_surface", "")),
                "Where to inspect next": str(row.get("where_to_inspect_next", "")),
                "Boundary note": str(row.get("boundary_note", "")),
            }
        )
    return table_rows


def _output_sections_overview_table_rows(overview: dict[str, Any]) -> list[dict[str, Any]]:
    table_rows: list[dict[str, Any]] = []
    for row in overview.get("rows") or []:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            {
                "Section": str(row.get("section_name", "")),
                "Status": str(row.get("status", "")),
                "Count": row.get("count", 0),
                "Inspect next": str(row.get("inspect_next", "")),
            }
        )
    return table_rows


def _render_output_sections_overview(overview: dict[str, Any]) -> None:
    table_rows = _output_sections_overview_table_rows(overview)
    if not table_rows:
        return

    with st.expander("Output sections overview", expanded=False):
        st.caption(
            "Compact read-only map of Project Outputs sections for manual documentation review."
        )
        for note in overview.get("boundary_notes") or []:
            st.caption(f"- {note}")
        overview_cols = st.columns(3, gap="small")
        overview_cols[0].metric("sections listed", overview.get("section_count", len(table_rows)))
        overview_cols[1].metric("available sections", overview.get("available_section_count", 0))
        overview_cols[2].metric("overview status", overview.get("status", "NOT_AVAILABLE"))
        st.dataframe(table_rows, hide_index=True)


def _validation_case_gap_table_rows(package: dict[str, Any]) -> list[dict[str, str]]:
    table_rows: list[dict[str, str]] = []
    for row in package.get("review_gaps_manual_follow_up_list") or []:
        if not isinstance(row, dict):
            continue
        table_rows.append(
            {
                "Source surface": str(row.get("source_surface", "")),
                "Item label": str(row.get("item_label", "")),
                "Issue type": str(row.get("issue_type", "")),
                "Manual follow-up note": str(row.get("manual_follow_up_note", "")),
            }
        )
    return table_rows


def _render_validation_case_package(package: dict[str, Any]) -> None:
    identity = (
        package.get("software_package_identity")
        if isinstance(package.get("software_package_identity"), dict)
        else {}
    )
    construct = (
        package.get("construct_design_summary")
        if isinstance(package.get("construct_design_summary"), dict)
        else {}
    )
    evidence = (
        package.get("component_evidence_provenance_summary")
        if isinstance(package.get("component_evidence_provenance_summary"), dict)
        else {}
    )
    codon = (
        package.get("codon_usage_optimization_status_summary")
        if isinstance(package.get("codon_usage_optimization_status_summary"), dict)
        else {}
    )
    conservation = (
        package.get("component_conservation_review_summary")
        if isinstance(package.get("component_conservation_review_summary"), dict)
        else {}
    )
    gap_rows = _validation_case_gap_table_rows(package)

    st.markdown("**Validation Case Package**")
    st.caption(str(package.get("subtitle") or "Documentation-only pre-experiment package for feasibility review."))
    st.caption(
        "Use this package to show one documented design case before external preliminary validation planning; "
        "it remains a pre-experiment review package and does not choose an experimental route."
    )
    for note in package.get("boundary_notes") or []:
        st.caption(f"- {note}")

    summary_cols = st.columns(4, gap="small")
    summary_cols[0].metric("candidate systems", len(package.get("candidate_expression_systems") or []))
    summary_cols[1].metric("component rows", construct.get("component_rows_reviewed", 0))
    summary_cols[2].metric("review gaps", len(gap_rows))
    summary_cols[3].metric("MD5 preview checksum", identity.get("snapshot_checksum", "NOT_AVAILABLE"))

    with st.expander("Validation case overview", expanded=True):
        st.caption(f"Case objective: {package.get('case_objective') or 'NOT_AVAILABLE'}")
        st.caption(
            "Candidate target protein/product/pathway: "
            f"{package.get('candidate_target') or 'NOT_AVAILABLE'}"
        )
        st.caption(
            "Candidate expression systems: "
            + ", ".join(package.get("candidate_expression_systems") or [])
        )
        st.caption(
            "Company feasibility feedback placeholder: "
            f"{package.get('company_feasibility_feedback_placeholder') or 'NOT_AVAILABLE'}"
        )
        st.caption(
            "Experiment status placeholder: "
            f"{package.get('experiment_status_placeholder') or 'NOT_AVAILABLE'}"
        )
        st.caption(
            "Result summary placeholder: "
            f"{package.get('result_summary_placeholder') or 'NOT_AVAILABLE'}"
        )

    with st.expander("Construct, evidence, codon, and conservation summaries", expanded=False):
        st.caption(f"Construct label: {construct.get('construct_label') or 'NOT_AVAILABLE'}")
        st.caption(f"Construct summary note: {construct.get('summary_note') or 'NOT_AVAILABLE'}")
        st.caption(f"Component evidence rows reviewed: {evidence.get('component_rows_reviewed', 0)}")
        st.caption(
            "Component source/reference context rows: "
            f"{evidence.get('source_reference_context_rows', 0)}"
        )
        st.caption(
            "Component missing source/reference rows: "
            f"{evidence.get('missing_source_reference_context_rows', 0)}"
        )
        st.caption(f"Codon status: {codon.get('status') or 'NOT_AVAILABLE'}")
        st.caption(f"Codon host context: {codon.get('host_context') or 'NOT_AVAILABLE'}")
        st.caption(f"Codon boundary: {codon.get('boundary_note') or 'Documentation context only.'}")
        st.caption(
            "Conservation context rows: "
            f"{conservation.get('conservation_context_rows', 0)}"
        )
        st.caption(
            "Conservation follow-up rows: "
            f"{conservation.get('conservation_follow_up_rows', 0)}"
        )
        st.caption(
            "Conservation boundary: "
            f"{conservation.get('boundary_note') or 'Manual documentation review only.'}"
        )

    with st.expander("Validation case review gaps / manual follow-up list", expanded=True):
        st.caption(
            "Manual follow-up list for teacher/company review; these rows are documentation cues, not route decisions."
        )
        if gap_rows:
            st.dataframe(gap_rows, hide_index=True)
        else:
            st.info("No validation case manual follow-up rows are visible.")

    with st.expander("Validation case package identity", expanded=False):
        st.caption("Software/package identity for preview matching only.")
        st.caption(f"Software: {identity.get('software_name') or 'BioDesign Studio'}")
        st.caption(f"Git tag: {identity.get('git_tag') or 'NOT_RECORDED'}")
        st.caption(f"Commit: {identity.get('commit') or 'NOT_RECORDED'}")
        st.caption(f"Snapshot ID: {identity.get('snapshot_id') or 'NOT_AVAILABLE'}")
        st.caption(f"Checksum algorithm: {identity.get('checksum_algorithm') or 'MD5'}")
        st.caption(
            "Identity boundary: "
            f"{identity.get('identity_boundary_note') or 'MD5 for preview matching only.'}"
        )
        st.code(str(package.get("qr_verification_payload_text") or ""), language="text")

    with st.expander("Validation case Markdown package", expanded=False):
        st.caption(
            "Read-only Markdown package for teacher/company feasibility review; no export file is created here."
        )
        st.code(str(package.get("markdown") or ""), language="markdown")

    with st.expander("Validation case plain-text package", expanded=False):
        st.caption(
            "Read-only plain-text package for meeting notes or email review; no export file is created here."
        )
        st.code(str(package.get("plain_text") or ""), language="text")


def _render_project_handoff_review_workspace(preview: dict[str, Any]) -> None:
    summary = (
        preview.get("handoff_workspace_summary")
        if isinstance(preview.get("handoff_workspace_summary"), dict)
        else {}
    )
    nav_rows = _handoff_workspace_nav_table_rows(preview)

    st.markdown("**Project handoff review workspace**")
    st.caption(
        "Read-only workspace for mentor, collaborator, platform, or internal project documentation review."
    )
    st.caption(
        str(
            summary.get("boundary_note")
            or (
                "This workspace organizes local, read-only, documentation-only review surfaces for manual review. "
                "It does not create files, packages, exports, biology-use recommendations, validation claims, "
                "optimization claims, or wet-lab use judgments."
            )
        )
    )
    st.caption("No export package is created here. No file or download is created here.")

    render_wrapped_summary_cards(
        st,
        [
            {
                "label": "Workspace areas",
                "value": summary.get("workspace_area_count", len(nav_rows)),
                "note": "Review surfaces visible in this workspace.",
            },
            {
                "label": "Manual follow-up items",
                "value": summary.get("total_manual_follow_up_items", 0),
                "note": "Documentation follow-up rows collected for human review.",
            },
            {
                "label": "Documentation surfaces",
                "value": summary.get("included_documentation_surface_count", 0),
                "note": "Included read-only documentation surfaces.",
            },
            {
                "label": "Traceability rows",
                "value": summary.get("traceability_matrix_row_count", 0),
                "note": "Source-to-review traceability rows.",
            },
            {
                "label": "Workspace snapshot checksum",
                "value": summary.get("snapshot_checksum", "NOT_AVAILABLE"),
                "note": "Preview matching identity only.",
            },
            {
                "label": "QR payload status",
                "value": summary.get("qr_payload_status", "NOT_AVAILABLE"),
                "note": "Payload text availability for preview matching.",
            },
        ],
    )

    with st.expander("Handoff workspace metric details", expanded=False):
        workspace_cols = st.columns(4, gap="small")
        workspace_cols[0].metric("workspace areas", summary.get("workspace_area_count", len(nav_rows)))
        workspace_cols[1].metric(
            "manual follow-up items",
            summary.get("total_manual_follow_up_items", 0),
        )
        workspace_cols[2].metric(
            "documentation surfaces",
            summary.get("included_documentation_surface_count", 0),
        )
        workspace_cols[3].metric(
            "traceability rows",
            summary.get("traceability_matrix_row_count", 0),
        )

        detail_cols = st.columns(2, gap="small")
        detail_cols[0].metric("workspace snapshot checksum", summary.get("snapshot_checksum", "NOT_AVAILABLE"))
        detail_cols[1].metric("QR payload status", summary.get("qr_payload_status", "NOT_AVAILABLE"))

    if nav_rows:
        render_responsive_detail_table(
            st,
            nav_rows,
            title="Handoff workspace review rows",
            empty_message="No project handoff review workspace rows are available.",
            title_field="Workspace area",
            subtitle_field="Current status",
            visible_fields=("Key count or identity", "Review surface", "Where to inspect next"),
            dataframe=False,
        )
    else:
        st.info("No project handoff review workspace rows are available.")

    with st.expander("Workspace Markdown map", expanded=False):
        st.caption(
            "Read-only Markdown map of handoff review surfaces; no export package, file, or download is created here."
        )
        st.code(str(preview.get("handoff_workspace_markdown") or ""), language="markdown")


def _render_handoff_snapshot_review_card(preview: dict[str, Any]) -> None:
    card = preview.get("snapshot_review_card") if isinstance(preview.get("snapshot_review_card"), dict) else {}
    if not card:
        return

    st.markdown("**Handoff snapshot review card**")
    st.caption(
        "Read-only snapshot identity for preview review matching. "
        "The MD5 code is for preview matching only, not a security signature or certification."
    )
    st.caption(str(card.get("boundary_note") or "Documentation preview only; no export package is created here."))

    render_wrapped_summary_cards(
        st,
        [
            {
                "label": "Snapshot title",
                "value": card.get("snapshot_title", "Project handoff package preview"),
                "note": "Read-only preview identity.",
            },
            {
                "label": "Preview checksum",
                "value": card.get("snapshot_checksum", "NOT_AVAILABLE"),
                "note": "Preview matching code, not a certification.",
            },
            {
                "label": "Included surfaces",
                "value": card.get("snapshot_included_surface_count", 0),
                "note": "Documentation surfaces counted in the preview.",
            },
            {
                "label": "Manual follow-up",
                "value": card.get("snapshot_manual_follow_up_count", 0),
                "note": "Visible follow-up rows for human review.",
            },
        ],
    )

    with st.expander("Snapshot metric details", expanded=False):
        card_cols = st.columns(4, gap="small")
        card_cols[0].metric("snapshot title", card.get("snapshot_title", "Project handoff package preview"))
        card_cols[1].metric("preview checksum", card.get("snapshot_checksum", "NOT_AVAILABLE"))
        card_cols[2].metric("included surfaces", card.get("snapshot_included_surface_count", 0))
        card_cols[3].metric("manual follow-up", card.get("snapshot_manual_follow_up_count", 0))

        detail_cols = st.columns(3, gap="small")
        detail_cols[0].metric("checksum algorithm", card.get("snapshot_checksum_algorithm", "MD5"))
        detail_cols[1].metric("preview sections", card.get("snapshot_section_count", 0))
        detail_cols[2].metric("content length", card.get("snapshot_content_length", 0))

    with st.expander("Snapshot included surfaces", expanded=False):
        st.caption(
            "Included documentation surfaces: "
            + ", ".join(card.get("snapshot_included_surfaces") or [])
        )
        st.caption(f"Snapshot ID: {card.get('snapshot_id') or 'NOT_AVAILABLE'}")


def _render_handoff_qr_verification_preview(preview: dict[str, Any]) -> None:
    payload = preview.get("qr_verification_payload") if isinstance(preview.get("qr_verification_payload"), dict) else {}
    payload_text = str(preview.get("qr_verification_payload_text") or "")
    if not payload and not payload_text:
        return

    st.markdown("**Handoff QR verification preview**")
    st.caption(str(preview.get("qr_verification_intended_use") or "Use this preview identity to match the same handoff snapshot during human review."))
    st.caption(str(preview.get("qr_verification_dependency_decision") or "Payload-only fallback is used; no QR image is rendered."))
    st.caption(
        str(
            preview.get("qr_verification_boundary_note")
            or (
                "Read-only QR verification payload for preview matching only; no export package, "
                "file, or download is created here."
            )
        )
    )

    render_wrapped_summary_cards(
        st,
        [
            {
                "label": "QR checksum algorithm",
                "value": payload.get("checksum_algorithm", "MD5"),
                "note": "Preview matching identity field.",
            },
            {
                "label": "QR MD5 preview checksum",
                "value": payload.get("snapshot_checksum", "NOT_AVAILABLE"),
                "note": "Text payload checksum for human matching.",
            },
            {
                "label": "QR included surfaces",
                "value": payload.get("included_surfaces_count", 0),
                "note": "Documentation surfaces represented in the payload.",
            },
            {
                "label": "QR manual follow-up",
                "value": payload.get("manual_follow_up_count", 0),
                "note": "Follow-up rows represented in the payload.",
            },
        ],
    )

    with st.expander("QR metric details", expanded=False):
        qr_cols = st.columns(4, gap="small")
        qr_cols[0].metric("QR checksum algorithm", payload.get("checksum_algorithm", "MD5"))
        qr_cols[1].metric("QR MD5 preview checksum", payload.get("snapshot_checksum", "NOT_AVAILABLE"))
        qr_cols[2].metric("QR included surfaces", payload.get("included_surfaces_count", 0))
        qr_cols[3].metric("QR manual follow-up", payload.get("manual_follow_up_count", 0))

    with st.expander("QR verification payload", expanded=True):
        st.caption(
            "Read-only payload text for QR matching workflows; it is displayed as text because no QR rendering dependency is present."
        )
        st.code(payload_text, language="text")


def _render_project_handoff_review_sheet(preview: dict[str, Any]) -> None:
    section_rows = _handoff_review_sheet_section_rows(preview)

    st.markdown("**Project handoff review sheet**")
    st.caption("Read-only review sheet copy view for documentation handoff review.")
    st.caption("Copy view only; no export package is created here and no file is generated here.")
    st.caption(
        "The MD5 code is for preview matching only, not a security signature or certification."
    )
    st.caption(str(preview.get("review_sheet_boundary_note") or "Documentation handoff review copy view only."))

    if section_rows:
        with st.expander("Review sheet sections", expanded=False):
            st.caption("Structured sections included in the read-only review sheet copy view.")
            render_responsive_detail_table(
                st,
                section_rows,
                title="Review sheet section rows",
                empty_message="No review sheet sections are available.",
                title_field="Review sheet section",
                subtitle_field="Purpose",
                table_expander=False,
                dataframe=False,
            )

    with st.expander("Markdown copy view", expanded=False):
        st.caption(
            "Read-only Markdown copy view for mentor, collaborator, platform, or internal review notes; "
            "no export package or file is created here."
        )
        st.code(str(preview.get("review_sheet_markdown") or ""), language="markdown")

    with st.expander("Plain-text copy view", expanded=False):
        st.caption(
            "Read-only plain-text copy view for chat, email, or meeting notes; "
            "no export package or file is created here."
        )
        st.code(str(preview.get("review_sheet_plain_text") or ""), language="text")


def _render_project_handoff_package_preview(preview: dict[str, Any]) -> None:
    cover = preview.get("handoff_cover_summary") if isinstance(preview.get("handoff_cover_summary"), dict) else {}
    surface_rows = _handoff_package_preview_surface_rows(preview)
    queue_rows = _handoff_center_table_rows({"follow_up_rows": preview.get("manual_follow_up_queue") or []})
    traceability_summary = (
        preview.get("traceability_matrix_summary")
        if isinstance(preview.get("traceability_matrix_summary"), dict)
        else {}
    )
    traceability_rows = _handoff_traceability_matrix_rows(preview)

    st.markdown("**Project handoff package preview**")
    st.caption(str(preview.get("subtitle") or "Read-only preview for human handoff review."))
    st.caption("Package preview only; no export package is created here.")
    for note in preview.get("boundary_notes") or []:
        st.caption(f"- {note}")

    _render_handoff_snapshot_review_card(preview)
    _render_handoff_qr_verification_preview(preview)

    render_wrapped_summary_cards(
        st,
        [
            {
                "label": "Project label",
                "value": cover.get("project_label", "Active pathway documentation project"),
                "note": "Local documentation project label.",
            },
            {
                "label": "Manual follow-up items",
                "value": cover.get("total_manual_follow_up_items", 0),
                "note": "Review queue rows visible in the package preview.",
            },
            {
                "label": "Documentation surfaces included",
                "value": len(cover.get("documentation_surfaces_included") or []),
                "note": "Read-only surfaces represented in this preview.",
            },
        ],
    )

    with st.expander("Package preview metric details", expanded=False):
        cover_cols = st.columns(3, gap="small")
        cover_cols[0].metric("project label", cover.get("project_label", "Active pathway documentation project"))
        cover_cols[1].metric("manual follow-up items", cover.get("total_manual_follow_up_items", 0))
        cover_cols[2].metric(
            "documentation surfaces included",
            len(cover.get("documentation_surfaces_included") or []),
        )

    with st.expander("Handoff cover summary", expanded=False):
        st.caption(f"Project label/name: {cover.get('project_label') or 'Active pathway documentation project'}")
        st.caption(f"Total manual follow-up items: {cover.get('total_manual_follow_up_items', 0)}")
        st.caption(
            "Documentation surfaces included: "
            + ", ".join(cover.get("documentation_surfaces_included") or [])
        )

    with st.expander("Included documentation preview", expanded=True):
        st.caption(
            "Read-only preview of documentation surfaces that a human handoff review could inspect."
        )
        if surface_rows:
            render_responsive_detail_table(
                st,
                surface_rows,
                title="Included documentation preview rows",
                empty_message="No included documentation preview rows are available.",
                title_field="Documentation surface",
                subtitle_field="Status",
                visible_fields=("Manual follow-up", "Review note"),
                table_expander=False,
                dataframe=False,
            )
        else:
            st.info("No included documentation preview rows are available.")

    with st.expander("Handoff checklist", expanded=False):
        st.caption("Checklist for human handoff review planning; review source records before handoff.")
        for item in preview.get("handoff_checklist") or []:
            if not isinstance(item, dict):
                continue
            st.caption(
                f"- {item.get('label', 'handoff item')}: "
                f"{item.get('status', 'Follow-up visible')} - "
                f"{item.get('note', 'Review documentation context manually.')}"
            )

    with st.expander("Manual follow-up queue", expanded=True):
        st.caption("Manual follow-up queue for human handoff review; review provenance notes before handoff.")
        if queue_rows:
            render_responsive_detail_table(
                st,
                queue_rows,
                title="Manual follow-up queue rows",
                empty_message="No manual follow-up items are visible from the supplied review queues.",
                title_field="Item label",
                subtitle_field="Issue type",
                visible_fields=("Source surface", "Manual follow-up note", REVIEW_NEXT_COLUMN_LABEL),
                table_expander=False,
                dataframe=False,
            )
        else:
            st.info("No manual follow-up items are visible from the supplied review queues.")

    with st.expander("Project handoff traceability matrix", expanded=True):
        st.caption(
            "Read-only traceability matrix linking each documentation source, manual follow-up status, "
            "where-to-review-next context, and whether the item is included in the review sheet."
        )
        st.caption(
            str(
                traceability_summary.get("boundary_note")
                or "Documentation source review only; no project data or package data is changed here."
            )
        )
        render_wrapped_summary_cards(
            st,
            [
                {
                    "label": "Matrix rows",
                    "value": traceability_summary.get("row_count", 0),
                    "note": "Traceability rows in the preview matrix.",
                },
                {
                    "label": "Included in review sheet",
                    "value": traceability_summary.get("included_in_review_sheet_count", 0),
                    "note": "Rows represented in the copy view.",
                },
                {
                    "label": "Source/reference follow-up",
                    "value": traceability_summary.get("source_reference_context_follow_up_count", 0),
                    "note": "Rows needing source/reference context review.",
                },
                {
                    "label": "Provenance/review follow-up",
                    "value": traceability_summary.get("provenance_review_context_follow_up_count", 0),
                    "note": "Rows needing provenance or review context.",
                },
            ],
        )
        st.caption("Traceability metric details are shown below for continuity with prior review checks.")
        matrix_cols = st.columns(2, gap="small")
        matrix_cols[0].metric("matrix rows", traceability_summary.get("row_count", 0))
        matrix_cols[1].metric(
            "included in review sheet",
            traceability_summary.get("included_in_review_sheet_count", 0),
        )
        matrix_cols = st.columns(2, gap="small")
        matrix_cols[0].metric(
            "source/reference follow-up",
            traceability_summary.get("source_reference_context_follow_up_count", 0),
        )
        matrix_cols[1].metric(
            "provenance/review follow-up",
            traceability_summary.get("provenance_review_context_follow_up_count", 0),
        )
        if traceability_rows:
            render_responsive_detail_table(
                st,
                traceability_rows,
                title="Project handoff traceability rows",
                empty_message="No traceability matrix rows are visible from the supplied review queues.",
                title_field="Source surface",
                subtitle_field=REVIEW_NEXT_COLUMN_LABEL,
                visible_fields=("Item label", "Manual follow-up status", "Included in review sheet"),
                table_expander=False,
                dataframe=False,
            )
        else:
            st.info("No traceability matrix rows are visible from the supplied review queues.")

    with st.expander("Markdown handoff preview", expanded=False):
        st.caption("Read-only Markdown handoff preview for human review/copying; no export package is created here.")
        st.code(str(preview.get("markdown_handoff_preview") or ""), language="markdown")

    _render_project_handoff_review_sheet(preview)


def _build_expression_vector_design_package_dashboard_preview(
    project: dict[str, Any],
    steps: list[dict[str, Any]] | None = None,
    linked_catalog_assets: list[dict[str, Any]] | None = None,
    handoff_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return build_expression_vector_package_record_input(
        project=project,
        steps=steps,
        linked_catalog_assets=linked_catalog_assets,
        handoff_preview=handoff_preview,
        expression_construct_views=build_expression_construct_report_views(
            project_id=_first_text(project.get("id"), project.get("project_id")) if isinstance(project, dict) else None
        ),
    )


def _build_expression_vector_design_package_review_preview(
    project: dict[str, Any],
    steps: list[dict[str, Any]] | None = None,
    linked_catalog_assets: list[dict[str, Any]] | None = None,
    handoff_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return _build_expression_vector_design_package_dashboard_preview(
        project,
        steps=steps,
        linked_catalog_assets=linked_catalog_assets,
        handoff_preview=handoff_preview,
    )


def _render_expression_vector_design_package_markdown_preview(
    preview: dict[str, Any],
    *,
    section_title: str = "Expression Vector Design Package preview",
    status_metric_label: str = "EV package status",
    md5_metric_label: str = "EV package MD5",
) -> None:
    record_source = str(preview.get("record_source") or CURRENT_RECORD_SOURCE)
    if record_source == EMPTY_RECORD_SOURCE or not isinstance(preview.get("preview"), dict):
        st.markdown(f"**{section_title}**")
        st.caption(EXPRESSION_VECTOR_PACKAGE_PREVIEW_COPY)
        st.caption(EXPRESSION_VECTOR_PACKAGE_SOURCE_READBACK_COPY)
        source_readback_rows = preview.get("source_readback_rows") or build_expression_vector_package_source_readback_rows(preview)
        st.dataframe(source_readback_rows, hide_index=True)
        st.info(str(preview.get("empty_state") or "No current expression vector record is available yet."))
        st.caption(str(preview.get("next_step") or "Start from Expression Wizard or open a saved design."))
        st.caption(
            "Sample walkthrough remains available below as a learning aid only; it is not current project data."
        )
        return

    preview_result = preview
    preview = preview["preview"]
    identity = preview.get("package_identity") if isinstance(preview.get("package_identity"), dict) else {}
    presenter = (
        preview.get("cassette_slot_rows_presenter")
        if isinstance(preview.get("cassette_slot_rows_presenter"), dict)
        else {}
    )
    presenter_summary = presenter.get("summary") if isinstance(presenter.get("summary"), dict) else {}
    markdown_preview = format_expression_vector_design_package_preview_markdown(preview)

    st.markdown(f"**{section_title}**")
    st.caption("Current record preview")
    st.caption(EXPRESSION_VECTOR_PACKAGE_PREVIEW_COPY)
    st.caption(EXPRESSION_VECTOR_PACKAGE_PREVIEW_LIMITATION_COPY)
    st.caption(EXPRESSION_VECTOR_PACKAGE_SOURCE_READBACK_COPY)

    preview_cols = st.columns(4, gap="small")
    preview_cols[0].metric(status_metric_label, identity.get("package_status", "draft / needs review"))
    preview_cols[1].metric(md5_metric_label, identity.get("md5", "NOT_AVAILABLE"))
    preview_cols[2].metric("cassette slot rows", presenter_summary.get("total_slot_rows", len(preview.get("cassette_slot_rows") or [])))
    preview_cols[3].metric("manual follow-up rows", len(preview.get("gap_follow_up_summary") or []))

    source_readback_rows = preview_result.get("source_readback_rows") or build_expression_vector_package_source_readback_rows(preview_result)
    st.dataframe(source_readback_rows, hide_index=True)

    with st.expander("Expression Vector Design Package Markdown preview", expanded=False):
        st.caption("Documentation review only. Markdown is read-only; no file, export package, or saved record is created here.")
        st.code(markdown_preview, language="markdown")


def _render_single_gene_expression_vector_sample_walkthrough() -> None:
    sample = build_single_gene_expression_vector_sample_walkthrough()
    preview = sample.get("preview") if isinstance(sample.get("preview"), dict) else {}
    identity = preview.get("package_identity") if isinstance(preview.get("package_identity"), dict) else {}
    presenter = preview.get("cassette_slot_rows_presenter") if isinstance(preview.get("cassette_slot_rows_presenter"), dict) else {}
    presenter_summary = presenter.get("summary") if isinstance(presenter.get("summary"), dict) else {}

    st.markdown("**Single-gene sample walkthrough helper (learning aid)**")
    st.caption(SINGLE_GENE_SAMPLE_WALKTHROUGH_COPY)
    st.caption(SINGLE_GENE_SAMPLE_WALKTHROUGH_BOUNDARY_COPY)

    sample_cols = st.columns(4, gap="small")
    sample_cols[0].metric("sample status", identity.get("package_status", "sample / needs review"))
    sample_cols[1].metric("sample MD5", identity.get("md5", "NOT_AVAILABLE"))
    sample_cols[2].metric("sample slot rows", presenter_summary.get("total_slot_rows", len(preview.get("cassette_slot_rows") or [])))
    sample_cols[3].metric("sample follow-up rows", len(preview.get("gap_follow_up_summary") or []))

    with st.expander("Single-gene sample walkthrough readback", expanded=False):
        st.caption(str(sample.get("boundary_note") or SINGLE_GENE_SAMPLE_WALKTHROUGH_BOUNDARY_COPY))
        st.markdown(f"**Start here:** {sample.get('start_here', 'Start in Expression Wizard.')}")
        st.markdown("**What has been recorded:**")
        for item in sample.get("recorded_context") or []:
            st.caption(f"- {item}")
        st.markdown("**Source/provenance gaps:**")
        for item in sample.get("source_provenance_gaps") or []:
            st.caption(f"- {item}")
        st.markdown("**Manual follow-up:**")
        for item in sample.get("manual_follow_up") or []:
            st.caption(f"- {item}")
        st.code(str(sample.get("markdown") or ""), language="markdown")


def _render_project_review_handoff_center(handoff: dict[str, Any]) -> None:
    summary = handoff.get("summary") if isinstance(handoff.get("summary"), dict) else {}
    table_rows = _handoff_center_table_rows(handoff)
    component_readback = (
        handoff.get("component_library_source_provenance_readback")
        if isinstance(handoff.get("component_library_source_provenance_readback"), dict)
        else {}
    )

    st.markdown("**Project review handoff center**")
    st.caption(str(handoff.get("subtitle") or "Read-only project handoff summary."))
    for note in handoff.get("boundary_notes") or []:
        st.caption(f"- {note}")

    summary_cols = st.columns(5, gap="small")
    summary_cols[0].metric("total follow-up items", summary.get("total_follow_up_items", 0))
    summary_cols[1].metric(
        "expression construct follow-up",
        summary.get("expression_construct_documentation_follow_up_count", 0),
    )
    summary_cols[2].metric("candidate evidence follow-up", summary.get("candidate_evidence_follow_up_count", 0))
    summary_cols[3].metric(
        "Component Library promoter asset source/review follow-up",
        summary.get("promoter_source_review_follow_up_count", 0),
    )
    summary_cols[4].metric(
        "host/context follow-up",
        summary.get("host_context_documentation_follow_up_count", 0),
    )

    with st.expander("Handoff checklist", expanded=False):
        st.caption("Read-only checklist for human handoff review planning.")
        for item in handoff.get("checklist") or []:
            if not isinstance(item, dict):
                continue
            st.caption(
                f"- {item.get('label', 'handoff item')}: "
                f"{item.get('status', 'Follow-up visible')} - "
                f"{item.get('note', 'Review documentation context manually.')}"
            )

    with st.expander("Follow-up queue overview", expanded=True):
        st.caption(
            "Read-only queue overview showing where existing documentation follow-up remains visible."
        )
        if table_rows:
            st.dataframe(table_rows, hide_index=True)
        else:
            st.info(str(handoff.get("empty_state_message") or "No project review handoff follow-up items are visible."))

    with st.expander("Component Library source/provenance readback", expanded=True):
        st.caption(str(component_readback.get("intro") or COMPONENT_LIBRARY_HANDOFF_READBACK_INTRO))
        st.caption(str(component_readback.get("boundary_note") or COMPONENT_LIBRARY_HANDOFF_READBACK_BOUNDARY_NOTE))
        readback_summary = (
            component_readback.get("summary")
            if isinstance(component_readback.get("summary"), dict)
            else {}
        )
        readback_cols = st.columns(4, gap="small")
        readback_cols[0].metric(
            "Component Library slot rows",
            readback_summary.get("slot_row_count", 0),
        )
        readback_cols[1].metric(
            "slots with records",
            readback_summary.get("slot_rows_with_records", 0),
        )
        readback_cols[2].metric(
            "source/provenance follow-up slots",
            readback_summary.get("source_follow_up_slot_count", 0),
        )
        readback_cols[3].metric(
            "manual follow-up slots",
            readback_summary.get("manual_follow_up_slot_count", 0),
        )
        readback_rows = [
            row for row in component_readback.get("rows") or [] if isinstance(row, dict)
        ]
        if readback_rows:
            st.dataframe(readback_rows, hide_index=True)
        else:
            st.info(str(component_readback.get("empty_state") or COMPONENT_LIBRARY_HANDOFF_READBACK_EMPTY_STATE))

    with st.expander("Markdown handoff summary", expanded=False):
        st.caption("Read-only Markdown summary for copy/review only; no export, package, or schema changes are made here.")
        st.code(str(handoff.get("markdown") or ""), language="markdown")


def _build_project_handoff_review_preview(
    project: dict[str, Any],
    steps: list[dict[str, Any]] | None,
    linked_tool_artifacts: list[dict[str, Any]] | None,
    linked_catalog_assets: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    report_project = dict(project)
    report_project["pathway_steps"] = steps or []
    report_project["project_asset_links"] = linked_catalog_assets or []
    report = build_project_review_report(
        report_project,
        linked_artifacts=linked_tool_artifacts,
        saved_designs=None,
        export_summary={
            "status": "AVAILABLE",
            "package_contents_preview_status": "AVAILABLE",
            "last_export_status": "NOT_AVAILABLE",
            "documentation_only_boundary": "Project export packages are documentation-only review packages.",
        },
        import_safety_summary=None,
        step2_component_context=current_step2_component_context_readback(),
    )
    candidate_queue = report.get("candidate_evidence_human_review_queue") or {}
    promoter_queue = report.get("plant_promoter_evidence_gap_review") or {}
    follow_up_index = report.get("project_review_follow_up_index") or build_project_review_follow_up_index({}, {})
    expression_construct_queue = build_project_construct_component_review_queue(
        project_id=_first_text(project.get("id"), project.get("project_id"))
    )
    host_context_status = build_host_chassis_context_summary(project, linked_catalog_assets or [])
    handoff = build_project_review_handoff_center(
        expression_construct_queue=expression_construct_queue,
        candidate_queue=candidate_queue,
        promoter_queue=promoter_queue,
        follow_up_index=follow_up_index,
        host_chassis_context=host_context_status,
        step2_component_context_appendix=report.get("step2_component_context_appendix") or {},
        component_library_records=linked_catalog_assets or [],
        report_markdown_available=True,
    )
    handoff_preview = build_project_handoff_package_preview(
        handoff,
        project_label=_first_text(project.get("name"), project.get("project_name"), project.get("target_product")),
        construct_review_payload=expression_construct_queue,
    )
    return handoff, handoff_preview


def render_project_handoff_review_workspace_section(
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None = None,
    linked_catalog_assets: list[dict[str, Any]] | None = None,
) -> None:
    st.subheader("Handoff Review")
    if not project:
        st.info("No active pathway project selected.")
        st.caption("Select a pathway documentation workspace to view the Handoff Review workspace.")
        return

    st.caption(
        "First-class read-only workspace for project handoff review surfaces, copy-only review sheets, "
        "preview-only package context, snapshot identity, QR payload text, traceability matrix, and report markdown review."
    )
    st.caption(
        "This Handoff Review workspace does not export, download, create files, save records, package data, "
        "validate biology, recommend options, or judge downstream-use state."
    )

    linked_tool_artifacts = list_tool_artifacts(project_id=project.get("id"))
    handoff, handoff_preview = _build_project_handoff_review_preview(
        project,
        steps,
        linked_tool_artifacts,
        linked_catalog_assets,
    )
    _render_output_sections_overview(
        build_project_output_sections_overview(handoff_preview=handoff_preview)
    )
    _render_project_handoff_review_workspace(handoff_preview)
    _render_project_review_handoff_center(handoff)
    _render_project_handoff_package_preview(handoff_preview)
    expression_vector_package_preview = _build_expression_vector_design_package_review_preview(
        project,
        steps=steps,
        linked_catalog_assets=linked_catalog_assets,
        handoff_preview=handoff_preview,
    )
    st.caption(
        "Read-only documentation-review preview for target, source/provenance, host, vector/backbone, "
        "sequence basic-check context, and manual follow-up summary. No export package, saved record, "
        "complete vector sequence, component choice, protocol, or downstream-use judgment is created here."
    )
    _render_expression_vector_design_package_markdown_preview(
        expression_vector_package_preview,
        section_title="Expression Vector Design Package review preview",
        status_metric_label="Expression Vector Design Package status",
        md5_metric_label="Expression Vector Design Package MD5",
    )
    _render_single_gene_expression_vector_sample_walkthrough()


def render_candidate_evidence_review_matrix_panel(
    linked_catalog_assets: list[dict[str, Any]] | None,
) -> None:
    matrix = build_candidate_evidence_review_matrix(
        _candidate_evidence_records_from_linked_catalog_assets(linked_catalog_assets)
    )
    summary = matrix.get("summary") if isinstance(matrix.get("summary"), dict) else {}

    st.markdown("**Candidate Evidence Review Matrix**")
    st.caption(str(matrix.get("subtitle") or "Documentation-only evidence review."))
    st.caption(str(matrix.get("boundary_note") or "Documentation-only manual review context."))
    st.caption(CANDIDATE_EVIDENCE_MATRIX_MANUAL_REVIEW_NOTE)
    _render_readability_note(CANDIDATE_EVIDENCE_MATRIX_MANUAL_REVIEW_NOTE)
    _render_candidate_evidence_matrix_field_legend()

    summary_cols = st.columns(4, gap="small")
    summary_cols[0].metric("evidence review records", summary.get("candidate_count", 0))
    summary_cols[1].metric("record review complete", summary.get("documentation_complete_count", 0))
    summary_cols[2].metric("record review gaps", summary.get("metadata_incomplete_count", 0))
    summary_cols[3].metric("source trace missing", summary.get("source_trace_missing_count", 0))

    table_rows = _candidate_evidence_matrix_table_rows(matrix)
    snapshot_text = format_candidate_evidence_review_snapshot(matrix)
    with st.expander("Review Snapshot", expanded=False):
        st.caption(CANDIDATE_EVIDENCE_REVIEW_SNAPSHOT_NOTE)
        st.caption(CANDIDATE_EVIDENCE_REVIEW_SNAPSHOT_BOUNDARY_NOTE)
        st.code(snapshot_text, language="markdown")
    _render_candidate_evidence_human_review_queue(matrix)

    if not table_rows:
        st.info(str(matrix.get("empty_state_message") or "No candidate evidence records are available."))
        st.caption(
            "Use this empty state as a documentation gap cue; no candidate evidence rows are "
            "available to inspect in this read-only matrix. Inspect existing Component Library "
            "source/provenance rows, Candidate Evidence Review Matrix inputs, or Project Review Report "
            "follow-up surfaces next."
        )
        return

    st.dataframe(table_rows, hide_index=True)


def render_documentation_consistency_provenance_panel(
    project: dict[str, Any],
    steps: list[dict[str, Any]] | None = None,
    expression_links: list[dict[str, Any]] | None = None,
    snapshots: list[dict[str, Any]] | None = None,
    review_signals: list[dict[str, Any]] | None = None,
    linked_tool_artifacts: list[dict[str, Any]] | None = None,
    export_summary: dict[str, Any] | None = None,
    import_summary: dict[str, Any] | None = None,
    duplicate_guard_context: dict[str, Any] | None = None,
) -> None:
    panel = build_documentation_consistency_provenance_panel(
        project=project,
        steps=steps,
        expression_links=expression_links,
        snapshots=snapshots,
        documentation_review=project.get("documentation_review") if isinstance(project, dict) else None,
        review_signals=review_signals,
        linked_tool_artifacts=linked_tool_artifacts,
        export_summary=export_summary,
        import_summary=import_summary,
        duplicate_guard_context=duplicate_guard_context,
    )

    st.subheader("Documentation Consistency / Provenance")
    st.caption(
        "documentation consistency and provenance context for source/provenance review, record review status, traceability review, "
        "and human review needed signals."
    )
    st.caption(
        "This section is documentation-only. It summarizes existing local records and supplied package context; "
        "it does not change project data, package data, snapshots, saved design records, or Wizard logic."
    )

    summary = panel.get("summary") or {}
    c1, c2 = st.columns(2, gap="small")
    with c1:
        st.metric("consistency sections", summary.get("section_count", 0))
    with c2:
        st.metric("human review needed", summary.get("human_review_needed_count", 0))

    sections = panel.get("sections") if isinstance(panel.get("sections"), dict) else {}
    for section_key in (
        "metadata_completeness",
        "linked_record_coverage",
        "snapshot_coverage",
        "review_notes_follow_up",
        "traceability_gaps",
        "package_review_context",
        "duplicate_guard_context",
    ):
        section = sections.get(section_key)
        if not isinstance(section, dict):
            continue
        title = str(section.get("title") or section_key).replace("_", " ").title()
        with st.expander(title, expanded=False):
            st.caption(f"Status: {section.get('status') or 'not_available'}")
            st.caption(str(section.get("summary") or "No summary recorded."))
            for item in section.get("items") or []:
                if isinstance(item, dict):
                    _render_consistency_item(item)


def render_project_quality_dashboard_section(
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None = None,
    expression_links: list[dict[str, Any]] | None = None,
    snapshots: list[dict[str, Any]] | None = None,
    review_signals: list[dict[str, Any]] | None = None,
    linked_catalog_assets: list[dict[str, Any]] | None = None,
    export_summary: dict[str, Any] | None = None,
    import_summary: dict[str, Any] | None = None,
    duplicate_guard_context: dict[str, Any] | None = None,
) -> None:
    st.subheader("Project Quality Dashboard")
    if not project:
        st.info("No active pathway project selected.")
        st.caption("Select a pathway documentation workspace to view the Project Quality Dashboard.")
        return

    linked_catalog_assets = normalize_generated_output_claims(linked_catalog_assets or [])
    linked_tool_artifacts = list_tool_artifacts(project_id=project.get("id"))
    dashboard_project = dict(project)
    dashboard_project["pathway_steps"] = steps or []
    export_summary = export_summary or {
        "status": "AVAILABLE",
        "package_contents_preview_status": "AVAILABLE",
        "documentation_only_package_note": "Export packages are documentation-only project packages.",
    }
    dashboard = build_project_quality_dashboard(
        dashboard_project,
        linked_artifacts=linked_tool_artifacts,
        linked_catalog_assets=linked_catalog_assets,
        saved_designs=None,
        export_summary=export_summary,
        import_safety_summary=import_summary,
    )

    if st.button("Refresh Project Quality Dashboard", use_container_width=True):
        st.session_state[f"project_quality_dashboard_{project.get('id')}"] = dashboard
    dashboard = st.session_state.get(f"project_quality_dashboard_{project.get('id')}", dashboard)
    step2_component_context = current_step2_component_context_readback()

    st.caption(
        "Documentation-only dashboard for completeness, consistency, provenance, package exchange context, "
        "and missing-reference review prompts."
    )
    st.caption("Project Quality Dashboard is a Project Outputs review surface.")
    st.caption(
        "This review surface summarizes local documentation state, package exchange context, and metadata-gap follow-up prompts."
    )
    st.caption(f"Boundary: {PROJECT_QUALITY_DASHBOARD_BOUNDARY_COPY}")
    _render_readability_note(
        "Readability note: review the summary metrics first, then open the collapsed detail sections for source/provenance, "
        "handoff, package, and boundary context. All status language remains documentation-only."
    )
    _render_readability_note(f"Boundary: {PROJECT_QUALITY_DASHBOARD_BOUNDARY_COPY}")
    st.caption(
        "Import Preview remains read-only. Blocked / NO-GO import states apply only to the gated create-as-new "
        "action, and any allowed action creates a local documentation-only project only after validation, safety "
        "review, dry-run planning, and explicit confirmation."
    )

    review_context = _dashboard_review_context_summary(dashboard)
    st.markdown("**documentation review summary**")
    st.caption(
        "Summary of existing local documentation records for review context only; this is not selection advice, "
        "behavior forecast, source-verification, biological-fit, downstream-use, or approval decision."
    )
    _render_readability_note(
        "Summary of existing local documentation records for review context only; this is not selection advice, "
        "behavior forecast, source-verification, biological-fit, downstream-use, or approval decision."
    )
    with tool_typography.temporary_streamlit_binding(st):
        tool_typography.render_compact_summary_cards(
            [
                ("Documentation status", str(review_context["status"]), "Recorded project review context"),
                ("Checklist items", str(review_context["checklist_items"]), "Documentation checklist rows"),
                ("Guidance items", str(review_context["guidance_items"]), "guidance items for manual review prompts"),
                ("Boundary notes", str(review_context["boundary_notes"]), "boundary notes for documentation-only context"),
            ]
        )

    st.markdown("**overall documentation status**")
    st.caption(str(dashboard.get("overall_documentation_status", "NOT_AVAILABLE")))
    metrics = dashboard.get("metrics") or {}
    with tool_typography.temporary_streamlit_binding(st):
        tool_typography.render_compact_summary_cards(
            [
                ("Pathway steps count", str(metrics.get("pathway_steps_count", 0)), "pathway steps count in local records"),
                ("Linked artifacts count", str(metrics.get("linked_artifacts_count", 0)), "linked artifacts count in local records"),
                ("Review gaps count", str(metrics.get("review_gap_count", 0)), "review gaps count for manual follow-up context"),
            ]
        )

    _render_step2_component_context_manual_follow_up_summary(step2_component_context)

    host_context_status = dashboard.get("host_chassis_context_status") or {}
    with st.expander("Host / Chassis Context Summary", expanded=False):
        st.caption(
            "Read-only host / chassis documentation context for the active project. This is chassis-neutral review "
            "context only; plant is one supported context and not the default frame."
        )
        st.caption(
            str(
                host_context_status.get("boundary_note")
                or "Documentation-only host context summary."
            )
        )
        st.caption(
            "Supported contexts: "
            + ", ".join(host_context_status.get("supported_context_labels") or [])
        )
        st.caption(
            "Contexts present in current documentation: "
            + ", ".join(host_context_status.get("contexts_present_labels") or ["Generic / unspecified"])
        )
        st.caption(
            f"Project context label: {host_context_status.get('project_context_label') or 'Generic / unspecified'}"
        )
        st.caption(
            "Plant context is supported as one documentation example only; bacterial, yeast, mammalian, and generic / unspecified contexts are also supported."
        )
        rows = host_context_status.get("rows") or []
        if not rows:
            st.info(str(host_context_status.get("empty_state_message") or "No specific host context is recorded yet."))
        else:
            st.dataframe(
                [
                    {
                        "Source": row.get("source_label", ""),
                        "Recorded context": row.get("source_value", ""),
                        "Normalized context": row.get("normalized_context_label", ""),
                        "Reference label": row.get("asset_display_name", ""),
                    }
                    for row in rows
                ],
                hide_index=True,
            )

    linked_catalog_status = dashboard.get("linked_catalog_assets_status") or {}
    promoter_summary = linked_catalog_status.get("plant_promoter_reference_summary") or {}
    with st.expander("Component Library promoter asset reference summary", expanded=False):
        st.caption(str(promoter_summary.get("boundary_note") or "Component Library promoter asset references are documentation context only."))
        st.caption(str(promoter_summary.get("limitation_note") or "No Component Library promoter asset reference summary is available."))
        st.caption(f"Linked promoter asset reference count: {promoter_summary.get('linked_promoter_count', 0)}")
        st.caption(f"Missing metadata count: {promoter_summary.get('missing_metadata_count', 0)}")
        st.caption(f"Source status summary: {promoter_summary.get('source_status_summary') or {}}")
        st.caption(f"Review status summary: {promoter_summary.get('review_status_summary') or {}}")
    wizard_catalog_traceability = linked_catalog_status.get("expression_wizard_catalog_traceability") or {}
    with st.expander("Expression Wizard catalog traceability summary", expanded=False):
        st.caption(str(wizard_catalog_traceability.get("boundary_note") or "Wizard catalog references are documentation-level source/review context."))
        st.caption(str(wizard_catalog_traceability.get("limitation_note") or "No Expression Wizard catalog traceability summary is available."))
        st.caption(f"Documentation-level reference count: {wizard_catalog_traceability.get('reference_count', 0)}")
        st.caption(f"Component Library promoter asset reference count: {wizard_catalog_traceability.get('plant_promoter_reference_count', 0)}")
        st.caption(f"Missing metadata count: {wizard_catalog_traceability.get('missing_metadata_count', 0)}")

    _render_generic_component_library_asset_readback_review(linked_catalog_assets)

    with st.expander("Candidate Evidence Review Matrix", expanded=False):
        render_candidate_evidence_review_matrix_panel(linked_catalog_assets)
    expression_construct_queue = build_project_construct_component_review_queue(
        project_id=_first_text(project.get("id"), project.get("project_id"))
    )
    _render_expression_construct_documentation_follow_up(expression_construct_queue)
    (
        follow_up_index,
        candidate_queue,
        promoter_queue,
        step2_component_context_appendix,
    ) = _render_project_review_follow_up_index_summary(
        project,
        steps,
        linked_tool_artifacts,
        linked_catalog_assets,
        step2_component_context,
    )
    handoff = build_project_review_handoff_center(
        expression_construct_queue=expression_construct_queue,
        candidate_queue=candidate_queue,
        promoter_queue=promoter_queue,
        follow_up_index=follow_up_index,
        host_chassis_context=host_context_status,
        step2_component_context_appendix=step2_component_context_appendix,
        component_library_records=linked_catalog_assets,
        report_markdown_available=True,
    )
    _render_project_review_handoff_center(handoff)
    handoff_preview = build_project_handoff_package_preview(
        handoff,
        project_label=_first_text(project.get("name"), project.get("project_name"), project.get("target_product")),
        construct_review_payload=expression_construct_queue,
    )
    _render_output_sections_overview(
        build_project_output_sections_overview(
            dashboard=dashboard,
            handoff_preview=handoff_preview,
        )
    )
    _render_project_handoff_review_workspace(handoff_preview)
    _render_project_handoff_package_preview(handoff_preview)
    expression_vector_package_preview = _build_expression_vector_design_package_dashboard_preview(
        project,
        steps=steps,
        linked_catalog_assets=linked_catalog_assets,
        handoff_preview=handoff_preview,
    )
    _render_expression_vector_design_package_markdown_preview(expression_vector_package_preview)
    validation_case_package = build_validation_case_package(
        case_context={
            "case_objective": (
                "Prepare one documented design case for teacher/company feasibility review before any "
                "external preliminary validation planning."
            ),
        },
        project=project,
        construct_component_queue=expression_construct_queue,
        handoff_preview=handoff_preview,
    )
    _render_validation_case_package(validation_case_package)

    s1, s2, s3 = st.columns(3, gap="small")
    with s1:
        st.caption(f"saved design snapshot status: {dashboard['saved_design_snapshot_status'].get('status', 'NOT_AVAILABLE')}")
    with s2:
        st.caption(f"export package status: {dashboard['export_package_status'].get('status', 'NOT_AVAILABLE')}")
    with s3:
        st.caption(f"import safety check status: {dashboard['import_safety_status'].get('overall_status') or dashboard['import_safety_status'].get('status', 'NOT_AVAILABLE')}")

    package_trail = dashboard.get("package_exchange_review_trail") or {}
    manifest_review = package_trail.get("manifest_review") or {}
    record_counts = manifest_review.get("record_counts") or {}
    with st.expander("Package Exchange Review Trail", expanded=False):
        st.caption(
            "Documentation-only trail for package export/import review context, manifest review, included sections, "
            "record count context, and review notes."
        )
        st.caption(f"Export package status: {(package_trail.get('export_context') or {}).get('status') or 'NOT_AVAILABLE'}")
        st.caption(f"Import package review status: {(package_trail.get('import_context') or {}).get('status') or 'NOT_AVAILABLE'}")
        st.caption(f"Manifest review available: {manifest_review.get('is_manifest_present', False)}")
        st.caption(f"Included sections: {manifest_review.get('included_section_count', 0)}")
        st.caption(f"Record count context: {record_counts.get('record_count_total', 0)}")
        for item in package_trail.get("demo_workflow_context") or []:
            st.caption(f"Workflow context: {item}")
        for note in package_trail.get("review_notes") or []:
            st.caption(f"- {note}")
        st.caption(f"Documentation boundary: {package_trail.get('documentation_boundary') or 'documentation-only context'}")
        for note in package_trail.get("boundary_notes") or []:
            st.caption(f"- {note}")

    with st.expander("documentation completeness checklist", expanded=False):
        for item in dashboard.get("documentation_completeness") or []:
            st.caption(f"- {item['label']}: {item['status']} — {item['summary']}")

    with st.expander("review guidance", expanded=True):
        for guidance in dashboard.get("review_guidance") or dashboard.get("next_actions") or []:
            st.caption(f"- {guidance}")

    with st.expander("boundary notes", expanded=False):
        for note in dashboard.get("boundary_notes") or []:
            st.caption(f"- {note}")

    st.markdown("---")
    render_documentation_consistency_provenance_panel(
        project,
        steps=steps,
        expression_links=expression_links,
        snapshots=snapshots,
        review_signals=review_signals,
        linked_tool_artifacts=linked_tool_artifacts,
        export_summary=export_summary,
        import_summary=import_summary,
        duplicate_guard_context=duplicate_guard_context,
    )
