from __future__ import annotations

from typing import Any

import html
import re

import pandas as pd
import streamlit as st

from services.pathway_documentation_risk_view_model import build_documentation_risk_summary
from services.pathway_bottleneck_service import analyze_pathway_bottlenecks
from services.pathway_completeness_service import (
    build_pathway_completeness,
    build_pathway_review_signals,
    summarize_review_signals,
)
from services.pathway_linked_design_view_model import (
    build_linked_design_evidence_rows,
    build_pathway_steps_table_rows,
    expression_link_counts_by_step,
    safe_step_id,
)
from services.pathway_outputs_workflow_view_model import (
    build_project_outputs_risk_table_rows,
    build_project_outputs_summary_card_items,
    build_project_outputs_workflow_table_rows,
    build_project_outputs_workflow_state,
)
from services.pathway_report_service import PathwayReportConfig, generate_pathway_markdown_report
from services.project_import_package_validator import validate_project_import_package
from services.host_chassis_context_presenter import build_host_chassis_context_summary
from services.pathway_repository import (
    create_pathway_step,
    create_pathway_test_record,
    delete_pathway_step,
    delete_pathway_test_record,
    get_default_documentation_review,
    get_pathway_project,
    list_expression_design_links,
    list_pathway_documentation_snapshots,
    list_pathway_steps,
    list_pathway_test_records,
    normalize_documentation_review,
    update_pathway_documentation_review,
    update_pathway_step,
    update_pathway_test_record,
)
from services.pathway_wizard_context import (
    build_pathway_wizard_context,
    can_launch_expression_design,
    create_design_session_from_pathway_step,
    set_pathway_wizard_context,
)
from views.pathway_workspace_sections import (
    import_preview_section,
    import_safety_section,
    linked_artifacts_section,
    linked_catalog_assets_section,
    project_report_download_section,
    project_outputs_section,
)
from views.pathway_workspace_sections.plant_review_workflow_section import render_plant_review_workflow_section
from views.pathway_workspace_sections.documentation_snapshots_section import render_documentation_snapshots_section
from views.pathway_workspace_sections.export_package_section import render_export_package_section
from views.pathway_workspace_sections.import_preview_section import render_import_preview_section
from views.pathway_workspace_sections.import_safety_section import render_import_safety_section
from views.pathway_workspace_sections.linked_artifacts_section import render_linked_artifacts_section, list_tool_artifacts
from views.pathway_workspace_sections.linked_catalog_assets_section import render_linked_catalog_assets_section
from views.pathway_workspace_sections.project_header import render_project_header
from views.pathway_workspace_sections.project_quality_dashboard_section import (
    render_project_handoff_review_workspace_section,
    render_project_quality_dashboard_section,
)
from views.pathway_workspace_sections.project_review_report_section import render_project_review_report_section
from views.pathway_workspace_sections.review_signals_section import render_review_signals_tab
from views.pathway_workspace_sections.overview_summary_section import render_overview_summary_section
from views.pathway_workspace_sections.traceability_section import (
    render_project_outputs_traceability_summary,
    render_traceability_graph_lite_section,
)
from views.pathway_workspace_sections.empty_state import render_no_active_project_empty_state
from views.tool_typography import inject_tool_typography_css, render_compact_summary_cards, render_help_text

_PATHWAY_WORKSPACE_EXTRACTED_COPY_ANCHOR = """
This Pathway workflow is documentation-only. It organizes pathway steps, test records, linked designs, and review signals without predicting yield, optimizing production, or certifying experimental readiness.
Saved design = wizard snapshot
Pathway project = documentation project for pathway context
Active project = currently selected pathway project for Pathway Workspace
Linked artifact = documentation record connected to a pathway project
No active pathway project selected
Pathway Workspace shows one documentation project at a time.
Go to Pathway Projects
Design Library
traceability
"""

CURRENT_PROJECT_KEY = "pathway_current_project_id"
TRACEABILITY_LINEAGE_COPY = (
    "Traceability is a documentation lineage view for existing local project records: project, pathway steps, "
    "linked design records, test records, review signals, and documentation snapshots."
)
TRACEABILITY_BOUNDARY_COPY = (
    "It does not validate experiments, predict outcomes, recommend actions, or determine readiness. "
    "missing_reference and needs_review statuses are documentation-only prompts that human review is needed."
)
TRACEABILITY_STATUS_HELPER_COPY = (
    "Relationship/status guide: linked = local record relationship exists; "
    "missing_reference = referenced local record was not found; "
    "needs_review = documentation record needs human review; "
    "no_records = no local documentation lineage rows yet."
)
TRACEABILITY_EMPTY_STATE_COPY = (
    "No local documentation lineage rows are available yet. Add local project documentation records before "
    "reviewing traceability."
)
PROJECT_OUTPUTS_GUIDE_COPY = (
    "Output actions: Save documentation snapshot; "
    "Download documentation report; "
    "Build / review documentation-only export package; "
    "Review import package preview. Documentation-only."
)
PROJECT_OUTPUTS_STRUCTURE_COPY = (
    "Project Outputs structure: summary cards first, traceability summary second, detailed review surfaces in tabs."
)
IMPORT_PREVIEW_DISCOVERY_COPY = (
    "Review import package in Pathway Workspace > Project Outputs > Import Preview. Import Preview is "
    "documentation-only package inspection for validation and dry-run planning; preview does not create a project, "
    "overwrite, or merge existing projects. A separate gated import-as-new action may create a local "
    "documentation-only project after validation, safety review, dry-run planning, and explicit confirmation."
)
PROJECT_OUTPUTS_CONTENTS_GUIDE_COPY = (
    "Package/report contents: local documentation records, summaries, linked record references, traceability context, "
    "and review context only."
)
PROJECT_OUTPUTS_BOUNDARY_COPY = (
    "Documentation-only boundary: outputs support local review and traceability; they do not validate experiments, "
    "certify readiness, predict yield, optimize pathways, choose actions, or provide wet-lab guidance."
)
PROJECT_OUTPUTS_SCHEMA_BOUNDARY_COPY = (
    "Layout polish only: this view does not change export package schema, report payload schema, import/export "
    "behavior, or stored documentation snapshot schema."
)
OUTPUT_NAVIGATION_ITEMS: tuple[tuple[str, str, str, str], ...] = (
    (
        "Plant Design Review Package",
        "Workspace > Plant Review",
        "Review package status, route readback, evidence, component context, and manual-review notes.",
        "pathway-workspace-plant-review",
    ),
    (
        "Slot Coverage / Review Matrix",
        "Workspace > Plant Review",
        "Check construct-slot coverage and traceability gaps in the Plant Review tab.",
        "pathway-workspace-plant-review",
    ),
    (
        "Project Review Report",
        "Project Outputs > Quality Review",
        "Open the Quality Review tab for documentation status and the Project Review Report.",
        "pathway-project-output-quality-review",
    ),
    (
        "Handoff Review",
        "Project Outputs > Handoff Review",
        "Inspect handoff center, package preview, traceability matrix, and report markdown review.",
        "pathway-project-output-handoff-review",
    ),
    (
        "Package / Markdown Preview",
        "Project Outputs > Reports / Export Package",
        "Find the Markdown report and documentation-only export package review surfaces.",
        "pathway-project-outputs",
    ),
)

OUTPUT_NAVIGATION_BOUNDARY_COPY = (
    "Output map for quick review only. Links jump to existing sections and tabs; they do not create files, "
    "change project records, or alter import/export behavior."
)
_PATHWAY_WORKSPACE_FORM_KEYS = (
    "pathway_report_include_project_metadata",
    "pathway_report_include_pathway_steps",
    "pathway_report_include_linked_designs",
    "pathway_report_include_test_records",
    "pathway_report_include_suggestions",
    "pathway_report_include_review_notes",
    "pathway_report_include_full_gene_sequences",
    "pathway_documentation_snapshot_include_markdown",
    "pathway_documentation_snapshot_title",
    "pathway_documentation_snapshot_note",
    "pathway_documentation_review_reviewer_name_or_initials",
    "pathway_documentation_review_review_date",
    "pathway_documentation_review_review_notes",
    "pathway_documentation_review_follow_up_actions",
    "pathway_documentation_review_unresolved_items",
)


def _clear_pathway_workspace_form_state() -> None:
    for key in _PATHWAY_WORKSPACE_FORM_KEYS:
        st.session_state.pop(key, None)


def _safe_report_filename(project: dict[str, Any]) -> str:
    name = str(project.get("name") or project.get("target_product") or "pathway").strip().lower()
    safe_name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return f"pathway_report_{safe_name or 'pathway'}.md"


def _render_documentation_report_download(
    project: dict[str, Any],
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    completeness_result: dict[str, Any],
    review_signals: list[dict[str, Any]],
) -> None:
    project_report_download_section.st = st
    project_report_download_section.render_documentation_report_download_section(
        project,
        steps,
        expression_links,
        test_records,
        completeness_result,
        review_signals,
        generate_markdown_report=generate_pathway_markdown_report,
        build_report_filename=_safe_report_filename,
    )


_IMPORT_SECTION_EXTRACTED_COPY_ANCHOR = """
Project Import Package Preview
Import Package Safety Check Report
Import Execution Preflight Review
Import Execution Result Preview
Create New Documentation Project is available only after package validation, safety review, dry-run planning, and explicit final confirmation.
Create New Documentation Project
Execution creates a new documentation-only project only
Final confirmation is required before creating a new documentation project.
read-only preview
no database writes
This preview does not import or modify any project.
It validates package structure and shows a dry-run import plan.
No database writes are performed by preview and safety checks.
Documentation project creation requires all explicit gates.
Blocked / NO-GO safety states stop the separate gated create-as-new action.
A separate gated import-as-new action may create a local documentation-only project only after validation, safety review, dry-run planning, and explicit confirmation.
No overwrite
No merge
No project creation during preview
No project creation is performed during preview.
Execution only creates a documentation project after final confirmation.
This checkbox is the final confirmation gate before documentation project creation.
does not provide wet-lab instructions
import as new project only
no overwrite
no merge
no raw payload_json restoration
documentation-only
computational previews
review records only
disabled_in_this_build
blocked_preflight
no readiness boost
no evidence boost
no validation claim
limited rollback note
audit summary required before future execution
"""


def _sync_import_section_dependencies() -> None:
    import_preview_section.st = st
    import_safety_section.st = st
    import_preview_section.render_import_safety_section = render_import_safety_section
    import_preview_section.validate_project_import_package = validate_project_import_package


def _render_import_validation_report(report: dict[str, Any]) -> None:
    _sync_import_section_dependencies()
    import_preview_section._render_import_validation_report(report)


def _render_import_dry_run_plan(plan: dict[str, Any]) -> None:
    _sync_import_section_dependencies()
    import_preview_section._render_import_dry_run_plan(plan)


def _render_import_package_safety_check_report(report: dict[str, Any]) -> None:
    _sync_import_section_dependencies()
    render_import_safety_section(report)


def _render_import_package_preview() -> None:
    _sync_import_section_dependencies()
    # Delegate to render_import_preview_section; dependency wiring keeps validate_project_import_package and
    # present_import_execution_result in the extracted preview path.
    # Static copy anchors preserved for import safety regression tests: Dry-run import plan; Result preview only.;
    # Create New Documentation Project; read-only preview; no database writes;
    # No database writes are performed.; No database writes are performed by preview and safety checks.
    # This preview does not import or modify any project.; No project creation is performed.
    # Blocked / NO-GO safety states stop the separate gated create-as-new action.
    # A separate gated import-as-new action may create a local documentation-only project only after validation,
    # safety review, dry-run planning, and explicit confirmation.
    # Create New Documentation Project is available only after package validation, safety review, dry-run planning, and explicit final confirmation.
    # Execution creates a new documentation-only project only; Documentation project creation requires all explicit gates.
    # The extracted import preview section owns the gated execution path after validation, safety,
    # dry-run planning, and final confirmation pass.
    # Gate-state construction and the final explicit confirmation key remain delegated to that section.
    # source-only anchor for legacy static tests: does not provide wet-lab protocols
    # Runtime copy uses wet-lab instructions to keep preview sections free of protocol wording.
    # This checkbox is the final confirmation gate before documentation project creation.
    render_import_preview_section()


def _safe_int(value: Any, fallback: int = 1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _has_duplicate_step_orders(steps: list[dict[str, Any]]) -> bool:
    orders: list[int] = []
    for step in steps:
        order = _safe_int(step.get("step_order"), 0)
        if order > 0:
            orders.append(order)
    return len(orders) != len(set(orders))


def _render_duplicate_order_warning(steps: list[dict[str, Any]]) -> None:
    if _has_duplicate_step_orders(steps):
        st.warning("Duplicate step order values detected; pathway order may be ambiguous.")


def _sequence_preview(sequence: str, length: int = 36) -> str:
    seq = str(sequence or "").strip().upper()
    if not seq:
        return ""
    return seq if len(seq) <= length else f"{seq[:length]}..."


def _selectbox(label: str, options: list[str], index: int = 0, key: str | None = None) -> str:
    if hasattr(st, "selectbox"):
        return st.selectbox(label, options, index=index, key=key)
    if not options:
        return ""
    safe_index = min(max(index, 0), len(options) - 1)
    return options[safe_index]


def _render_add_step_form(project_id: int, next_order: int) -> None:
    with st.expander("Add pathway step", expanded=False):
        st.caption("Use this form only to create a new pathway step.")
        with st.form("pathway_add_step_form", clear_on_submit=True):
            c1, c2 = st.columns([0.5, 1.5])
            with c1:
                step_order = st.number_input("Step order", min_value=1, value=next_order, step=1)
            with c2:
                step_name = st.text_input("Step name", placeholder="For example: Precursor activation")
            reaction_name = st.text_input("Reaction name", placeholder="Optional reaction label")
            c3, c4 = st.columns(2)
            with c3:
                substrate = st.text_input("Substrate", placeholder="Input compound or intermediate")
            with c4:
                product = st.text_input("Product", placeholder="Output compound or intermediate")
            c5, c6 = st.columns(2)
            with c5:
                enzyme_name = st.text_input("Enzyme name", placeholder="For example: CHS")
            with c6:
                gene_name = st.text_input("Gene name", placeholder="For example: chalcone synthase")
            gene_sequence = st.text_area(
                "Gene sequence",
                placeholder="Paste CDS sequence for this step. Only documentation is stored in this phase.",
                height=120,
            )
            organism_source = st.text_input("Organism source", placeholder="Optional source organism")
            notes = st.text_area("Notes", placeholder="Optional design notes", height=80)
            submitted = st.form_submit_button("Add step", use_container_width=True)
        if submitted:
            ok, _message, _step_id = create_pathway_step(
                project_id=project_id,
                step_order=int(step_order),
                step_name=step_name,
                reaction_name=reaction_name,
                substrate=substrate,
                product=product,
                enzyme_name=enzyme_name,
                gene_name=gene_name,
                gene_sequence=gene_sequence,
                organism_source=organism_source,
                notes=notes,
            )
            if ok:
                st.success("New pathway step created.")
                st.rerun()
            else:
                st.error(_message)


def _safe_step_id(step: dict[str, Any] | None) -> int:
    return safe_step_id(step)


def _steps_with_safe_ids(steps: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [{**step, "id": safe_step_id(step)} for step in (steps or []) if isinstance(step, dict)]


def _render_step_linked_design_evidence_panel(
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]] | None,
) -> None:
    evidence_rows = build_linked_design_evidence_rows(steps, expression_links)
    st.subheader("Step-level linked design evidence")
    st.caption(
        "This panel summarizes existing linked Expression Wizard records by pathway step for documentation traceability only. "
        "A linked design record can be reviewed in this Pathway Project context without changing saved design fields."
    )
    if not evidence_rows:
        st.info("No pathway steps have been added yet.")
        return

    for row in evidence_rows:
        with st.container(border=True):
            st.markdown(f"**Step {row.get('step_order')}: {row.get('step_title')}**")
            st.caption(f"Linked designs: {row.get('linked_design_count', 0)}")
            linked_design_rows = row.get("linked_design_rows") or []
            if not linked_design_rows:
                st.info(
                    "No linked design records yet. Open Expression Wizard from this pathway step to create or review "
                    "a local documentation record for this Pathway Project context."
                )
                continue

            rows = [
                {
                    "Linked design": linked_row.get("linked_design_name") or "Linked design",
                    "Linked/saved time": linked_row.get("linked_timestamp") or "Not recorded",
                    "Source/context": linked_row.get("source_context") or "Not recorded",
                }
                for linked_row in linked_design_rows
                if isinstance(linked_row, dict)
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_steps_table(steps: list[dict[str, Any]], expression_links: list[dict[str, Any]] | None = None) -> None:
    if not steps:
        st.info("No pathway steps have been added yet.")
        return
    linked_design_counts = expression_link_counts_by_step(expression_links or [])
    rows = build_pathway_steps_table_rows(steps, linked_design_counts)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _launch_expression_wizard_from_step(project: dict[str, Any], step: dict[str, Any], change_page) -> None:
    from core.design_session import SessionController

    context = build_pathway_wizard_context(project, step)
    design_session = create_design_session_from_pathway_step(step)
    set_pathway_wizard_context(context)
    SessionController().save(design_session)
    change_page("Expression Wizard")


def _render_expression_design_launcher(project: dict[str, Any], step: dict[str, Any], change_page) -> None:
    step_id = _safe_step_id(step)
    st.divider()
    st.subheader("Expression construct design")
    st.caption("Use Expression Wizard for gene-level expression design for this pathway step.")
    st.caption(
        "Launch the Expression Wizard to create or review a single-gene design associated with this pathway step. "
        "Returning a Wizard design link records traceability only; it does not change pathway scoring semantics or "
        "certify experimental readiness."
    )
    st.caption(
        "Linked Wizard designs remain governed by Wizard validation, Step 6 export rules, and primer-risk semantics."
    )
    if can_launch_expression_design(step):
        st.caption(
            "This step has a gene name and sequence. Start a standard Expression Wizard run with Step 1 prefilled."
        )
        if st.button(
            "Open in Expression Wizard",
            key=f"pathway_design_expression_{step_id}",
            type="primary",
            use_container_width=True,
        ):
            _launch_expression_wizard_from_step(project, step, change_page)
    else:
        st.info("Add both a gene name and a gene sequence to enable Expression Wizard launch for this step.")


def _render_step_editor(project: dict[str, Any], step: dict[str, Any], change_page, linked_design_count: int = 0) -> None:
    step_id = _safe_step_id(step)
    step_order_value = _safe_int(step.get("step_order"))
    title = step.get("step_name") or f"Step {step.get('step_order')}"
    with st.container(border=True):
        st.caption(f"Linked designs: {linked_design_count}")
        _render_expression_design_launcher(project, step, change_page)
        st.caption(
            "Edit an existing pathway step below. Saving changes here updates the selected step and does not create a new step."
        )
        with st.expander(f"Edit {title}", expanded=False):
            form_key = f"pathway_edit_step_{step_id}"
            with st.form(form_key):
                c1, c2 = st.columns([0.5, 1.5])
                with c1:
                    step_order = st.number_input(
                        "Step order",
                        min_value=1,
                        value=step_order_value,
                        step=1,
                        key=f"step_order_{step_id}",
                    )
                with c2:
                    step_name = st.text_input("Step name", value=step.get("step_name") or "", key=f"step_name_{step_id}")
                reaction_name = st.text_input(
                    "Reaction name",
                    value=step.get("reaction_name") or "",
                    key=f"reaction_name_{step_id}",
                )
                c3, c4 = st.columns(2)
                with c3:
                    substrate = st.text_input("Substrate", value=step.get("substrate") or "", key=f"substrate_{step_id}")
                with c4:
                    product = st.text_input("Product", value=step.get("product") or "", key=f"product_{step_id}")
                c5, c6 = st.columns(2)
                with c5:
                    enzyme_name = st.text_input("Enzyme name", value=step.get("enzyme_name") or "", key=f"enzyme_{step_id}")
                with c6:
                    gene_name = st.text_input("Gene name", value=step.get("gene_name") or "", key=f"gene_{step_id}")
                gene_sequence = st.text_area(
                    "Gene sequence",
                    value=step.get("gene_sequence") or "",
                    height=120,
                    key=f"gene_sequence_{step_id}",
                )
                organism_source = st.text_input(
                    "Organism source",
                    value=step.get("organism_source") or "",
                    key=f"organism_{step_id}",
                )
                notes = st.text_area("Notes", value=step.get("notes") or "", height=80, key=f"notes_{step_id}")
                save_clicked = st.form_submit_button("Save changes", use_container_width=True)
            if save_clicked:
                ok, _message = update_pathway_step(
                    step_id,
                    {
                        "step_order": int(step_order),
                        "step_name": step_name,
                        "reaction_name": reaction_name,
                        "substrate": substrate,
                        "product": product,
                        "enzyme_name": enzyme_name,
                        "gene_name": gene_name,
                        "gene_sequence": gene_sequence,
                        "organism_source": organism_source,
                        "notes": notes,
                    },
                )
                if ok:
                    st.success(f"Step {step_order_value} updated. No new pathway step was created.")
                    st.rerun()
                else:
                    st.error(_message)

            st.caption(f"Sequence preview: {_sequence_preview(step.get('gene_sequence') or '') or 'No sequence recorded.'}")
            delete_key = f"pathway_delete_step_confirm_{step_id}"
            if st.session_state.get(delete_key):
                st.warning(
                    "Confirm permanent deletion of "
                    f"Step {step.get('step_order')}: "
                    f"{step.get('step_name') or step.get('reaction_name') or 'Untitled step'}."
                )
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Confirm delete step", key=f"confirm_delete_step_{step_id}", use_container_width=True):
                        ok, message = delete_pathway_step(step_id)
                        if ok:
                            st.session_state.pop(delete_key, None)
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)
                with c2:
                    if st.button("Cancel", key=f"cancel_delete_step_{step_id}", use_container_width=True):
                        st.session_state.pop(delete_key, None)
                        st.rerun()
            elif st.button("Delete step", key=f"delete_step_{step_id}", use_container_width=True):
                st.session_state[delete_key] = True
                st.warning("Press the confirmation button to permanently delete this step.")
                st.rerun()


def _render_steps_tab(
    project: dict[str, Any],
    project_id: int,
    steps: list[dict[str, Any]],
    change_page,
    expression_links: list[dict[str, Any]] | None = None,
) -> None:
    next_order = max([_safe_int(step.get("step_order"), 0) for step in steps] or [0]) + 1
    linked_design_counts = expression_link_counts_by_step(expression_links or [])
    st.caption(
        "Pathway steps document intended pathway components, roles, sequences, notes, and optional traceability links "
        "to single-gene Expression Wizard designs."
    )
    st.caption(
        "Linked Expression Wizard designs are traceability links only and remain governed by Wizard validation, "
        "Step 6 export rules, and primer-risk semantics."
    )
    st.subheader("Pathway step entry")
    _render_add_step_form(project_id, next_order)
    st.markdown("---")
    st.subheader("Pathway steps")
    _render_duplicate_order_warning(steps)
    _render_steps_table(steps, expression_links)
    for step in steps:
        _render_step_editor(project, step, change_page, linked_design_counts.get(_safe_step_id(step), 0))


def _format_step_reaction(step: dict[str, Any]) -> str:
    reaction = str(step.get("reaction_name") or step.get("reaction") or "").strip()
    if reaction:
        return reaction

    substrate = str(step.get("substrate") or "").strip()
    product = str(step.get("product") or "").strip()
    if substrate and product:
        return f"{substrate} -> {product}"

    return "Not recorded"


def _step_label(step: dict[str, Any]) -> str:
    title = step.get("step_name") or step.get("reaction_name") or step.get("product") or "Untitled step"
    return f"Step {step.get('step_order')}: {title}"


def _step_options(steps: list[dict[str, Any]]) -> dict[str, int | None]:
    options: dict[str, int | None] = {"Project-level record": None}
    for step in steps:
        options[_step_label(step)] = int(step["id"])
    return options


def _selected_step_label(step_id: Any, steps: list[dict[str, Any]]) -> str:
    if step_id in (None, "", 0, "0"):
        return "Project-level record"
    try:
        resolved_step_id = int(step_id)
    except (TypeError, ValueError):
        return "Project-level record"
    for label, option_step_id in _step_options(steps).items():
        if option_step_id == resolved_step_id:
            return label
    return "Project-level record"


def _test_record_scope(record: dict[str, Any]) -> str:
    if record.get("step_id") is None:
        return "Project-level"
    step_name = record.get("step_name") or record.get("reaction_name") or "Untitled step"
    return f"Step {record.get('step_order')}: {step_name}"


def _test_record_counts(test_records: list[dict[str, Any]]) -> tuple[int, int, dict[int, int]]:
    project_level_count = 0
    step_associated_count = 0
    step_counts: dict[int, int] = {}
    for record in test_records:
        step_id = record.get("step_id")
        if step_id is None:
            project_level_count += 1
            continue
        try:
            resolved_step_id = int(step_id)
        except (TypeError, ValueError):
            project_level_count += 1
            continue
        step_associated_count += 1
        step_counts[resolved_step_id] = step_counts.get(resolved_step_id, 0) + 1
    return project_level_count, step_associated_count, step_counts


def _render_add_test_record_form(project_id: int, steps: list[dict[str, Any]]) -> None:
    step_options = _step_options(steps)
    with st.container(border=True):
        st.subheader("Add test record")
        st.caption(
            "Test Records are user-entered observations only. They are not experimental validation, automated analysis, "
            "predictive results, or readiness certification, and they do not change completeness score semantics."
        )
        with st.form("pathway_add_test_record_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                sample_name = st.text_input("Sample name", placeholder="For example: Flask sample 24 h")
            with c2:
                selected_scope = _selectbox("Record scope", list(step_options.keys()))
            c3, c4 = st.columns(2)
            with c3:
                measured_product = st.text_input("Measured product", placeholder="Target product or intermediate")
            with c4:
                titer = st.text_input("Observed amount note", placeholder="Optional user-entered observation note")
            c5, c6 = st.columns(2)
            with c5:
                yield_value = st.text_input("Yield", placeholder="For example: 0.18 g/g")
            with c6:
                productivity = st.text_input("Productivity", placeholder="For example: 4.2 mg/L/h")
            c7, c8 = st.columns(2)
            with c7:
                intermediate_accumulation = st.text_input(
                    "Intermediate accumulation",
                    placeholder="Qualitative or measured observation",
                )
            with c8:
                enzyme_activity = st.text_input("Enzyme activity", placeholder="Qualitative or measured observation")
            growth_status = st.text_input("Growth status", placeholder="For example: Normal growth")
            condition = st.text_area("Condition", placeholder="Culture, induction, timepoint, or assay conditions", height=80)
            notes = st.text_area("Notes", placeholder="Optional documentation notes", height=80)
            submitted = st.form_submit_button("Add test record", use_container_width=True)
        if submitted:
            ok, message, _test_id = create_pathway_test_record(
                project_id=project_id,
                step_id=step_options[selected_scope],
                sample_name=sample_name,
                measured_product=measured_product,
                titer=titer,
                yield_value=yield_value,
                productivity=productivity,
                intermediate_accumulation=intermediate_accumulation,
                enzyme_activity=enzyme_activity,
                growth_status=growth_status,
                condition=condition,
                notes=notes,
            )
            if ok:
                st.success(message)
                st.rerun()
            else:
                st.error(message)


def _render_test_records_table(test_records: list[dict[str, Any]]) -> None:
    if not test_records:
        st.info("No pathway test records have been added yet.")
        return
    rows = [
        {
            "Sample": record.get("sample_name") or "",
            "Scope": _test_record_scope(record),
            "Measured Product": record.get("measured_product") or "",
            "Observed Amount Note": record.get("titer") or "",
            "Yield": record.get("yield_value") or "",
            "Productivity": record.get("productivity") or "",
            "Intermediate Accumulation": record.get("intermediate_accumulation") or "",
            "Enzyme Activity": record.get("enzyme_activity") or "",
            "Growth Status": record.get("growth_status") or "",
            "Condition": record.get("condition") or "",
            "Updated": record.get("updated_at") or "",
        }
        for record in test_records
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _render_test_record_editor(record: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    test_id = int(record["id"])
    step_options = _step_options(steps)
    current_label = _selected_step_label(record.get("step_id"), steps)
    selected_index = list(step_options.keys()).index(current_label)
    title = record.get("sample_name") or f"Test record {test_id}"
    with st.expander(f"Edit {title}", expanded=False):
        with st.form(f"pathway_edit_test_record_{test_id}"):
            c1, c2 = st.columns(2)
            with c1:
                sample_name = st.text_input(
                    "Sample name",
                    value=record.get("sample_name") or "",
                    key=f"test_sample_{test_id}",
                )
            with c2:
                selected_scope = _selectbox(
                    "Record scope",
                    list(step_options.keys()),
                    index=selected_index,
                    key=f"test_scope_{test_id}",
                )
            c3, c4 = st.columns(2)
            with c3:
                measured_product = st.text_input(
                    "Measured product",
                    value=record.get("measured_product") or "",
                    key=f"test_product_{test_id}",
                )
            with c4:
                titer = st.text_input("Observed amount note", value=record.get("titer") or "", key=f"test_titer_{test_id}")
            c5, c6 = st.columns(2)
            with c5:
                yield_value = st.text_input(
                    "Yield",
                    value=record.get("yield_value") or "",
                    key=f"test_yield_{test_id}",
                )
            with c6:
                productivity = st.text_input(
                    "Productivity",
                    value=record.get("productivity") or "",
                    key=f"test_productivity_{test_id}",
                )
            c7, c8 = st.columns(2)
            with c7:
                intermediate_accumulation = st.text_input(
                    "Intermediate accumulation",
                    value=record.get("intermediate_accumulation") or "",
                    key=f"test_intermediate_{test_id}",
                )
            with c8:
                enzyme_activity = st.text_input(
                    "Enzyme activity",
                    value=record.get("enzyme_activity") or "",
                    key=f"test_enzyme_activity_{test_id}",
                )
            growth_status = st.text_input(
                "Growth status",
                value=record.get("growth_status") or "",
                key=f"test_growth_{test_id}",
            )
            condition = st.text_area(
                "Condition",
                value=record.get("condition") or "",
                height=80,
                key=f"test_condition_{test_id}",
            )
            notes = st.text_area("Notes", value=record.get("notes") or "", height=80, key=f"test_notes_{test_id}")
            save_clicked = st.form_submit_button("Save test record", use_container_width=True)
        if save_clicked:
            ok, message = update_pathway_test_record(
                test_id,
                {
                    "step_id": step_options[selected_scope],
                    "sample_name": sample_name,
                    "measured_product": measured_product,
                    "titer": titer,
                    "yield_value": yield_value,
                    "productivity": productivity,
                    "intermediate_accumulation": intermediate_accumulation,
                    "enzyme_activity": enzyme_activity,
                    "growth_status": growth_status,
                    "condition": condition,
                    "notes": notes,
                },
            )
            if ok:
                st.success(message)
                st.rerun()
            else:
                st.error(message)

        delete_key = f"pathway_delete_test_confirm_{test_id}"
        if st.session_state.get(delete_key):
            st.warning(f"Confirm permanent deletion of test record: {title}.")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Confirm delete test record", key=f"confirm_delete_test_{test_id}", use_container_width=True):
                    ok, message = delete_pathway_test_record(test_id)
                    if ok:
                        st.session_state.pop(delete_key, None)
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(message)
            with c2:
                if st.button("Cancel", key=f"cancel_delete_test_{test_id}", use_container_width=True):
                    st.session_state.pop(delete_key, None)
                    st.rerun()
        elif st.button("Delete test record", key=f"delete_test_{test_id}", use_container_width=True):
            st.session_state[delete_key] = True
            st.warning("Press the confirmation button to permanently delete this test record.")
            st.rerun()


def _render_tests_tab(project_id: int, steps: list[dict[str, Any]], test_records: list[dict[str, Any]]) -> None:
    st.caption(
        "Test Records capture user-entered observations and notes only. They do not provide experimental validation, "
        "automated analysis, predictive results, readiness certification, or changes to completeness score semantics."
    )
    _render_add_test_record_form(project_id, steps)
    st.markdown("---")
    st.subheader("Pathway test records")
    _render_test_records_table(test_records)
    for record in test_records:
        _render_test_record_editor(record, steps)


def _step_test_records_by_step(test_records: list[dict[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for record in test_records:
        step_id = record.get("step_id")
        if step_id is None:
            continue
        try:
            resolved_step_id = int(step_id)
        except (TypeError, ValueError):
            continue
        grouped.setdefault(resolved_step_id, []).append(record)
    return grouped


_DOCUMENTATION_REVIEW_CHECKLIST_LABELS = {
    "pathway_description_reviewed": "Pathway description reviewed for documentation completeness",
    "gene_entries_reviewed": "Gene entries reviewed for documentation completeness",
    "linked_expression_designs_reviewed": "Linked Expression Wizard designs reviewed for documentation completeness",
    "suggestions_reviewed": "Review signals reviewed as documentation-only prompts",
    "test_records_reviewed": "Test Records reviewed",
    "markdown_documentation_report_reviewed": "Markdown Documentation Report reviewed",
    "unresolved_documentation_items_reviewed": "Unresolved documentation items and follow-up actions reviewed",
}


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


def _render_documentation_review_tab(project: dict[str, Any], project_id: int) -> None:
    review = normalize_documentation_review(project.get("documentation_review") or get_default_documentation_review())
    review_items = review.get("review_items") or {}

    st.subheader("Documentation Review Notes")
    st.caption(
        "Review Notes are human-authored documentation review notes for unresolved questions, source review, "
        "documentation gaps, and manual follow-up notes. They are not an ELN, protocol, approval workflow, "
        "automated experimental suggestion, or readiness decision."
    )

    st.subheader("Manual Review Checklist")
    checklist_payload: dict[str, bool] = {}
    for item_key, label in _DOCUMENTATION_REVIEW_CHECKLIST_LABELS.items():
        checklist_payload[item_key] = _checkbox(
            label,
            value=bool(review_items.get(item_key, False)),
            key=f"pathway_documentation_review_{item_key}",
        )

    reviewer_name_or_initials = st.text_input(
        "Reviewer name or initials",
        value=review.get("reviewer_name_or_initials") or "",
        help="Optional user-authored documentation field. This is not an electronic signature.",
        key="pathway_documentation_review_reviewer_name_or_initials",
    )
    review_date = st.text_input(
        "Review date",
        value=review.get("review_date") or "",
        help="Optional documentation review date. This is not a validation or approval date.",
        key="pathway_documentation_review_review_date",
    )
    review_notes = st.text_area(
        "Review notes",
        value=review.get("review_notes") or "",
        placeholder="Add user-authored notes about the documentation review scope, assumptions, limitations, or context.",
        height=120,
        key="pathway_documentation_review_review_notes",
    )
    follow_up_actions = st.text_area(
        "Follow-up actions",
        value=review.get("follow_up_actions") or "",
        placeholder="Add documentation follow-up items. These do not block or unblock supporting preview workspace behavior.",
        height=100,
        key="pathway_documentation_review_follow_up_actions",
    )
    unresolved_items = st.text_area(
        "Unresolved documentation items",
        value=review.get("unresolved_items") or "",
        placeholder=(
            "Add unresolved risks, uncertainties, missing documentation, or items requiring later review. "
            "Do not record these as confirmed bottlenecks unless independently established outside this tool."
        ),
        height=100,
        key="pathway_documentation_review_unresolved_items",
    )

    if st.session_state.pop("pathway_documentation_review_saved_feedback", False):
        st.success("Review notes saved.")

    if st.button("Save documentation review notes", key="pathway_save_documentation_review", use_container_width=True):
        review_payload = {
            "review_items": checklist_payload,
            "reviewer_name_or_initials": reviewer_name_or_initials,
            "review_date": review_date,
            "review_notes": review_notes,
            "follow_up_actions": follow_up_actions,
            "unresolved_items": unresolved_items,
            "last_updated": review.get("last_updated") or "",
            "review_scope": review.get("review_scope") or "",
            "review_context": review.get("review_context") or "",
        }
        ok, message = update_pathway_documentation_review(project_id, review_payload)
        if ok:
            st.session_state["pathway_documentation_review_saved_feedback"] = True
            st.rerun()
        else:
            st.error(message or "Review notes could not be saved.")

    st.caption(
        "Documentation review notes do not change completeness score, review signals, Wizard validation, primer-risk "
        "status, Step 6 export recommendations, or supporting preview workspace behavior."
    )


def _render_active_project_summary(project: dict[str, Any], steps: list[dict[str, Any]], expression_links: list[dict[str, Any]], test_records: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> None:
    host_context = build_host_chassis_context_summary(project)
    st.subheader("Active Project Summary")
    render_help_text(
        "Current project = main local project workspace. Review context first, then use Workspace tabs for records "
        "and Project Outputs for snapshots, reports, export package review, and import preview review."
    )
    render_compact_summary_cards(
        [
            ("Project", str(project.get("name") or project.get("target_product") or "Untitled pathway project"), None),
            ("Pathway steps", str(len(steps)), None),
            ("Linked designs", str(len(expression_links)), None),
            ("Snapshots", str(len(snapshots)), None),
        ]
    )
    st.caption(
        f"Host: {project.get('host') or 'Not set'} | Target: {project.get('target_product') or 'Not set'} | "
        f"Test records: {len(test_records)} | Updated: {project.get('updated_at') or 'Not recorded'}"
    )
    with st.expander("Host / Chassis Context Summary", expanded=False):
        st.caption(
            "Read-only host / chassis documentation context for the active project. This is chassis-neutral review "
            "context only; plant is one supported context and not the default frame."
        )
        st.caption(host_context["boundary_note"])
        st.caption(
            "Supported contexts: "
            + ", ".join(host_context.get("supported_context_labels") or [])
        )
        st.caption(
            "Contexts present in current documentation: "
            + ", ".join(host_context.get("contexts_present_labels") or ["Generic / unspecified"])
        )
        st.caption(
            f"Project context label: {host_context.get('project_context_label') or 'Generic / unspecified'}"
        )
        st.caption(
            "Plant context is supported as one documentation example only; bacterial, yeast, mammalian, and generic / unspecified contexts are also supported."
        )
    st.caption("Documentation-only project summary; no readiness, yield, optimization, or wet-lab guidance claims.")
    if project.get("description"):
        with st.expander("Project description", expanded=False):
            st.write(project.get("description"))


def _render_output_navigation_strip() -> None:
    cards: list[str] = []
    for label, location, description, anchor in OUTPUT_NAVIGATION_ITEMS:
        cards.append(
            "<a class='pathway-output-nav-card' "
            f"href='#{html.escape(anchor, quote=True)}'>"
            f"<span class='pathway-output-nav-label'>{html.escape(label)}</span>"
            f"<span class='pathway-output-nav-location'>{html.escape(location)}</span>"
            f"<span class='pathway-output-nav-desc'>{html.escape(description)}</span>"
            "</a>"
        )
    st.markdown(
        """
<style>
.pathway-output-nav-strip{
  margin:.8rem 0 1rem 0;
  padding:.78rem .85rem;
  border:1px solid #cbd5e1;
  border-left:4px solid #2563eb;
  border-radius:8px;
  background:#f8fafc;
}
.pathway-output-nav-heading{
  font-size:.78rem;
  font-weight:800;
  letter-spacing:.06em;
  text-transform:uppercase;
  color:#1e40af;
  margin:0 0 .22rem 0;
}
.pathway-output-nav-copy{
  font-size:.88rem;
  line-height:1.45;
  color:#475569;
  margin:0 0 .65rem 0;
}
.pathway-output-nav-grid{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(178px,1fr));
  gap:.55rem;
}
.pathway-output-nav-card{
  display:block;
  min-height:92px;
  padding:.68rem .72rem;
  border:1px solid #dbe4ee;
  border-radius:8px;
  background:#ffffff;
  color:#0f172a !important;
  text-decoration:none !important;
}
.pathway-output-nav-card:hover{
  border-color:#2563eb;
  background:#eff6ff;
}
.pathway-output-nav-label{
  display:block;
  font-size:.92rem;
  font-weight:760;
  line-height:1.24;
}
.pathway-output-nav-location{
  display:block;
  margin-top:.22rem;
  font-size:.74rem;
  font-weight:760;
  line-height:1.28;
  color:#2563eb;
}
.pathway-output-nav-desc{
  display:block;
  margin-top:.32rem;
  font-size:.78rem;
  line-height:1.36;
  color:#64748b;
}
@media (max-width: 760px){
  .pathway-output-nav-strip{padding:.7rem}
  .pathway-output-nav-grid{grid-template-columns:1fr}
  .pathway-output-nav-card{min-height:auto}
}
</style>
""",
        unsafe_allow_html=True,
    )
    st.markdown(
        "<div id='pathway-workspace-output-navigation' class='pathway-output-nav-strip'>"
        "<div class='pathway-output-nav-heading'>Output navigation</div>"
        f"<div class='pathway-output-nav-copy'>{html.escape(OUTPUT_NAVIGATION_BOUNDARY_COPY)}</div>"
        "<div class='pathway-output-nav-grid'>"
        + "".join(cards)
        + "</div></div>",
        unsafe_allow_html=True,
    )


def _render_next_documentation_steps(change_page) -> None:
    st.subheader("Next documentation steps")
    render_help_text(
        "Use these compact actions to continue the active documentation project. They point to existing workspace "
        "tabs and outputs; they do not change project schemas, import/export behavior, or readiness semantics."
    )
    a1, a2, a3, a4 = st.columns(4, gap="small")
    with a1:
        st.markdown("**Add or review pathway steps**")
        st.caption("Use the Pathway Steps tab to update pathway context and step-level documentation.")
    with a2:
        st.markdown("**Open / review linked Expression Wizard design records**")
        st.caption("Use Linked Designs for recorded links, or open Expression Wizard as the gene-level design record subflow.")
        if st.button(
            "Open Expression Wizard",
            key="pathway_workspace_next_steps_open_expression_wizard",
            help="Open Expression Wizard for gene-level design records linked back to this local documentation project.",
        ):
            change_page("Expression Wizard")
    with a3:
        st.markdown("**Save documentation snapshot**")
        st.caption("Use Project Outputs > Documentation Snapshots to preserve the current documentation state.")
    with a4:
        st.markdown("**Review import package**")
        st.caption("Use Project Outputs > Import Preview for read-only package inspection.")


def _render_linked_designs_tab(
    project: dict[str, Any],
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
) -> None:
    st.subheader("Linked Designs")
    st.caption(
        "Linked Designs lists local Expression Wizard design records connected to this pathway project. Treat the "
        "Expression Wizard as a design record subflow, and use these links for documentation traceability only. "
        "A design record can be reviewed in linked Pathway Project context."
    )
    st.caption(
        "Linked design records do not change pathway scoring semantics, certify readiness, or replace Expression Wizard "
        "validation and primer-risk semantics."
    )
    _render_step_linked_design_evidence_panel(steps, expression_links)
    linked_artifacts_section.list_tool_artifacts = list_tool_artifacts
    render_linked_artifacts_section(project.get("id"))
    if expression_links:
        with st.expander("Linked design raw details", expanded=False):
            st.dataframe(pd.DataFrame(expression_links), use_container_width=True, hide_index=True)


def _render_workspace_tabs(
    *,
    project: dict[str, Any],
    project_id: int,
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    completeness_result: dict[str, Any],
    suggestions: list[dict[str, Any]],
    review_signals: list[dict[str, Any]],
    review_signal_summary: dict[str, Any],
    snapshots: list[dict[str, Any]],
    change_page,
) -> None:
    linked_catalog_assets_section.st = st
    st.markdown("<span id='pathway-workspace-tabs'></span>", unsafe_allow_html=True)
    st.subheader("Workspace")
    st.caption(
        "Workspace tabs keep records separated by purpose: overview, pathway records, linked design records, catalog "
        "references, traceability, review signals, and human review notes. Review Signals / Review Notes are "
        "documentation review surfaces."
    )
    overview_tab, plant_review_tab, steps_tab, linked_designs_tab, linked_catalog_assets_tab, traceability_tab, review_signals_tab, review_notes_tab = st.tabs(
        ["Overview", "Plant Review", "Pathway Steps", "Linked Designs", "Linked Catalog Assets", "Traceability", "Review Signals", "Review Notes"]
    )
    with overview_tab:
        project_level_tests, step_associated_tests, step_test_counts = _test_record_counts(test_records)
        _render_duplicate_order_warning(steps)
        render_overview_summary_section(
            project=project,
            steps=steps,
            expression_links=expression_links,
            test_records=test_records,
            completeness_result=completeness_result,
            review_signals=review_signals,
            review_signal_summary=review_signal_summary,
            snapshots=snapshots,
            project_catalog_links=linked_catalog_assets_section._persisted_project_links(project.get("id")),
            project_level_tests=project_level_tests,
            step_associated_tests=step_associated_tests,
            step_test_counts=step_test_counts,
            format_step_reaction=_format_step_reaction,
        )
    with plant_review_tab:
        st.markdown("<span id='pathway-workspace-plant-review'></span>", unsafe_allow_html=True)
        render_plant_review_workflow_section(
            project=project,
            steps=steps,
            expression_links=expression_links,
            test_records=test_records,
            review_signals=review_signals,
        )
    with steps_tab:
        _render_steps_tab(project, project_id, steps, change_page, expression_links)
        st.markdown("---")
        _render_tests_tab(project_id, steps, test_records)
    with linked_designs_tab:
        _render_linked_designs_tab(project, steps, expression_links)
    with linked_catalog_assets_tab:
        render_linked_catalog_assets_section(project)
    with traceability_tab:
        render_traceability_graph_lite_section(
            project,
            steps,
            expression_links,
            test_records,
            review_signals,
            snapshots,
            lineage_copy=TRACEABILITY_LINEAGE_COPY,
            boundary_copy=TRACEABILITY_BOUNDARY_COPY,
            status_helper_copy=TRACEABILITY_STATUS_HELPER_COPY,
            empty_state_copy=TRACEABILITY_EMPTY_STATE_COPY,
        )
    with review_signals_tab:
        render_review_signals_tab(suggestions, steps)
    with review_notes_tab:
        _render_documentation_review_tab(project, project_id)


def _render_project_outputs_tabs(
    *,
    project: dict[str, Any],
    project_id: int,
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    test_records: list[dict[str, Any]],
    completeness_result: dict[str, Any],
    suggestions: list[dict[str, Any]],
    review_signals: list[dict[str, Any]],
    snapshots: list[dict[str, Any]] | None = None,
) -> None:
    project_outputs_section.st = st
    st.markdown("<span id='pathway-project-outputs'></span>", unsafe_allow_html=True)
    project_outputs_section.render_project_outputs_section(
        project=project,
        project_id=project_id,
        steps=steps,
        expression_links=expression_links,
        test_records=test_records,
        completeness_result=completeness_result,
        suggestions=suggestions,
        review_signals=review_signals,
        snapshots=snapshots,
        project_outputs_boundary_copy=PROJECT_OUTPUTS_BOUNDARY_COPY,
        project_outputs_structure_copy=PROJECT_OUTPUTS_STRUCTURE_COPY,
        project_outputs_guide_copy=PROJECT_OUTPUTS_GUIDE_COPY,
        import_preview_discovery_copy=IMPORT_PREVIEW_DISCOVERY_COPY,
        project_outputs_contents_guide_copy=PROJECT_OUTPUTS_CONTENTS_GUIDE_COPY,
        project_outputs_schema_boundary_copy=PROJECT_OUTPUTS_SCHEMA_BOUNDARY_COPY,
        traceability_status_helper_copy=TRACEABILITY_STATUS_HELPER_COPY,
        build_project_outputs_workflow_state=build_project_outputs_workflow_state,
        build_documentation_risk_summary=build_documentation_risk_summary,
        build_project_outputs_summary_card_items=build_project_outputs_summary_card_items,
        build_project_outputs_workflow_table_rows=build_project_outputs_workflow_table_rows,
        build_project_outputs_risk_table_rows=build_project_outputs_risk_table_rows,
        render_help_text=render_help_text,
        render_compact_summary_cards=render_compact_summary_cards,
        render_project_outputs_traceability_summary=render_project_outputs_traceability_summary,
        render_documentation_snapshots_section=render_documentation_snapshots_section,
        render_documentation_report_download=_render_documentation_report_download,
        render_project_quality_dashboard_section=render_project_quality_dashboard_section,
        render_project_review_report_section=render_project_review_report_section,
        render_project_handoff_review_workspace_section=render_project_handoff_review_workspace_section,
        render_export_package_section=render_export_package_section,
        render_import_package_preview=_render_import_package_preview,
        persisted_project_links=linked_catalog_assets_section._persisted_project_links,
    )


def render(change_page) -> None:
    inject_tool_typography_css()
    project_id = st.session_state.get(CURRENT_PROJECT_KEY)
    project = get_pathway_project(project_id)
    if not project:
        render_no_active_project_empty_state(change_page)
        return

    resolved_project_id = int(project["id"])
    if st.session_state.get(CURRENT_PROJECT_KEY) != resolved_project_id:
        st.session_state[CURRENT_PROJECT_KEY] = resolved_project_id
    steps = list_pathway_steps(resolved_project_id)
    safe_id_steps = _steps_with_safe_ids(steps)
    expression_links = list_expression_design_links(resolved_project_id)
    test_records = list_pathway_test_records(resolved_project_id)
    completeness_result = build_pathway_completeness(project, safe_id_steps, expression_links)
    project_test_records = [record for record in test_records if record.get("step_id") is None]
    suggestions_context = {
        "pathway_project": project,
        "project": project,
        "pathway_steps": safe_id_steps,
        "expression_design_links": expression_links,
        "pathway_completeness": completeness_result,
        "project_test_records": project_test_records,
        "step_test_records": _step_test_records_by_step(test_records),
    }
    suggestions = analyze_pathway_bottlenecks(suggestions_context)
    review_signals = build_pathway_review_signals(project, safe_id_steps, expression_links, test_records)
    review_signal_summary = summarize_review_signals(review_signals)

    snapshots = list_pathway_documentation_snapshots(resolved_project_id)
    _clear_pathway_workspace_form_state()

    render_project_header(project, change_page)
    st.caption(
        "Continue current project: work on the active pathway project as the main local project workspace by adding "
        "pathway steps, linked Expression Wizard design records, test records, and review notes before generating "
        "documentation-only project outputs."
    )
    _render_output_navigation_strip()
    _render_active_project_summary(project, steps, expression_links, test_records, snapshots)
    _render_next_documentation_steps(change_page)
    with st.expander("Workspace guide", expanded=False):
        st.markdown(
            "**Workspace guide**\n\n"
            "Next documentation steps points to common actions. Workspace tabs hold pathway records, linked design "
            "records, traceability, review signals, and review notes. Project Outputs holds documentation snapshots, "
            "reports, Quality Review, documentation-only Export Package review, and Import Preview inspection."
        )
        st.caption("Use Project Outputs after the project context, linked design records, and review notes are documented.")

    _render_workspace_tabs(
        project=project,
        project_id=resolved_project_id,
        steps=safe_id_steps,
        expression_links=expression_links,
        test_records=test_records,
        completeness_result=completeness_result,
        suggestions=suggestions,
        review_signals=review_signals,
        review_signal_summary=review_signal_summary,
        snapshots=snapshots,
        change_page=change_page,
    )

    st.markdown("---")
    _render_project_outputs_tabs(
        project=project,
        project_id=resolved_project_id,
        steps=steps,
        expression_links=expression_links,
        test_records=test_records,
        completeness_result=completeness_result,
        suggestions=suggestions,
        review_signals=review_signals,
        snapshots=snapshots,
    )
