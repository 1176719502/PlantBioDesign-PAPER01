# -*- coding: utf-8 -*-
"""
views/wizard_steps/step6_export.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Step 6 -- Export.
"""
from __future__ import annotations

import hashlib
import json

import pandas as pd
import streamlit as st

from core.session_keys import SK
from services.export_recommendation_service import build_export_recommendation
from services.validation_summary_service import (
    PRIMER_HIGH_RISK_CODE,
    PRIMER_REVIEW_CODE,
    build_validation_run_state,
)
from views.wizard_steps._shared import (
    _section_label,
    _status_panel,
    _step_header,
    render_flow_strip,
    render_report_download_button,
    render_report_preview_container,
    render_report_sequence_preview,
)

def _na(value) -> str:
    if value is None or value == "" or value == 0:
        return "Not set"
    return str(value)


def _plasmid_png_signature(seq: str, feats: list[dict], title: str) -> str:
    """Return a stable signature for the current plasmid PNG payload."""
    payload = {
        "sequence": seq,
        "features": feats,
        "title": title,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _render_plasmid_png(seq: str, feats: list[dict], title: str):
    """Render the current construct into a matplotlib figure and PNG bytes."""
    from utils.plasmid_visualizer import PlasmidVisualizer

    viz = PlasmidVisualizer()
    return viz.draw_circular_map(sequence=seq, features=feats, title=title)


def _close_plasmid_figure(fig) -> None:
    """Close a stale cached plasmid figure without affecting the active preview figure."""
    if fig is None:
        return
    try:
        import matplotlib.pyplot as plt

        plt.close(fig)
    except Exception:
        pass


def _clear_plasmid_cache_state() -> None:
    for key in (
        "wf_plasmid_png",
        "wf_plasmid_fig",
        "wf_plasmid_png_signature",
    ):
        st.session_state.pop(key, None)


def _clear_step6_save_state() -> None:
    for key in (
        "wf_p6_saved_name",
        "pathway_link_warning",
    ):
        st.session_state.pop(key, None)


@st.cache_data(show_spinner=False)
def _build_cached_report_payload(report_signature: str, report_json: str) -> dict:
    from services.report_service import render_markdown_report

    report = json.loads(report_json)
    report_markdown = render_markdown_report(report)
    report_presenter = report.get("report_presenter") or {}
    return {
        "signature": report_signature,
        "report": report,
        "markdown": report_markdown,
        "presenter": report_presenter,
    }


def _resolve_element_name(ds, part_type: str, name_key: str) -> str:
    elems = ds.elements if isinstance(ds.elements, dict) else {}
    frame = ds.frame if isinstance(ds.frame, dict) else {}
    name = elems.get(name_key) or frame.get(name_key)
    if name:
        return str(name)

    parts = frame.get("parts") if isinstance(frame.get("parts"), list) else []
    part_type_norm = part_type.lower()
    for part in parts:
        if not isinstance(part, dict):
            continue
        current_type = str(part.get("type") or "").lower()
        if current_type == part_type_norm or (part_type_norm == "rbs" and current_type == "kozak"):
            return str(part.get("name") or "")
    return ""


def _review_panel(ds, summary: dict) -> None:
    rows = [
        ("Gene", _na(summary.get("gene_name"))),
        ("Host", _na(summary.get("host"))),
        ("Tag", _na(summary.get("tag"))),
        ("Promoter", _na(_resolve_element_name(ds, "promoter", "promoter_name"))),
        ("RBS / Kozak", _na(_resolve_element_name(ds, "rbs", "rbs_name"))),
        ("Terminator", _na(_resolve_element_name(ds, "terminator", "terminator_name"))),
        ("Cloning method", _na(summary.get("cloning_method"))),
        ("Vector suggestion", _na(summary.get("vector_suggestion"))),
        ("Frame length (bp)", _na(summary.get("frame_length_bp") or None)),
        ("GC content", f"{summary.get('gc_content', 0.0):.1f}%" if summary.get("gc_content") else "Not set"),
        ("Designed primers", str(summary.get("n_primers", 0))),
        ("Review-check issues", str(summary.get("n_issues", 0))),
    ]
    with st.expander("Design record summary", expanded=True):
        col_a, col_b = st.columns(2)
        mid = len(rows) // 2 + len(rows) % 2
        for i, (label, val) in enumerate(rows):
            col = col_a if i < mid else col_b
            col.markdown(
                f"<div style='margin-bottom:4px'><span style='color:#888;font-size:0.78rem;text-transform:uppercase;letter-spacing:0.05em'>{label}</span><br/><span style='font-weight:600'>{val}</span></div>",
                unsafe_allow_html=True,
            )


def _map_orientation_label(raw_strand) -> str:
    try:
        strand = int(raw_strand)
    except Exception:
        strand = 1 if str(raw_strand or "").strip() != "-1" else -1
    if strand < 0:
        return "reverse"
    return "forward"


def _is_minimal_map_feature_set(features: list[dict], seq_len: int) -> bool:
    """Detect whole-sequence fallback annotations that need manual documentation review."""
    if not features or seq_len <= 0:
        return True
    if len(features) != 1:
        return False
    feature = features[0] if isinstance(features[0], dict) else {}
    start = int(feature.get("start", 0) or 0)
    end = int(feature.get("end", 0) or 0)
    feature_type = str(feature.get("type") or "").strip().casefold()
    return start <= 0 and end >= seq_len and feature_type in {"cds", "coding_sequence", "gene"}


def _build_map_feature_readback_rows(features: list[dict], seq_len: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    minimal_feature_set = _is_minimal_map_feature_set(features, seq_len)
    for index, feature in enumerate(features or [], start=1):
        if not isinstance(feature, dict):
            continue
        label = str(feature.get("label") or feature.get("name") or f"Feature {index}").strip()
        feature_type = str(feature.get("type") or "misc").strip()
        start = int(feature.get("start", 0) or 0)
        end = int(feature.get("end", start) or start)
        source_status = str(
            feature.get("source_status")
            or feature.get("provenance_status")
            or feature.get("source")
            or feature.get("provenance")
            or ""
        ).strip()
        review_status = str(feature.get("review_status") or feature.get("documentation_status") or "").strip()
        if not source_status:
            source_status = "Source/provenance status not recorded"
        if not review_status:
            review_status = "Manual documentation review needed"
        if minimal_feature_set:
            review_status = "Manual feature documentation follow-up"
        rows.append(
            {
                "Feature": label or f"Feature {index}",
                "Type": feature_type or "misc",
                "Direction": _map_orientation_label(feature.get("strand", 1)),
                "Source/provenance": source_status,
                "Review status": review_status,
                "Position/order note": f"{max(1, start + 1)}-{max(start + 1, end)} bp; approximate documentation readback",
            }
        )
    return rows


def _render_map_feature_readback(features: list[dict], seq_len: int) -> None:
    rows = _build_map_feature_readback_rows(features, seq_len)
    st.caption(
        "Feature order preview: rows summarize map labels, feature types, orientation, and documentation gaps. "
        "Positions/order are approximate documentation readback and do not validate sequence correctness, "
        "cloning feasibility, or experimental readiness."
    )
    if not rows:
        _status_panel(
            "Map feature documentation follow-up",
            "No feature annotations are available for this construct/cassette map preview. Add feature documentation before using the map for handoff review.",
            tone="info",
        )
        return
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _catalog_context_readback_rows(traceability_rows: list[dict]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    missing_source_labels = {"source review context not recorded", "source status not recorded", ""}
    missing_review_labels = {"human review needed", "not recorded", ""}
    for row in traceability_rows:
        if not isinstance(row, dict):
            continue
        source_label = str(row.get("source_label") or "").strip()
        documentation_status = str(row.get("documentation_status") or "").strip()
        has_gap = source_label.casefold() in missing_source_labels or documentation_status.casefold() in missing_review_labels
        rows.append(
            {
                "Catalog context": str(row.get("asset_label") or row.get("asset_id") or "Not recorded"),
                "Source/review context": (
                    f"Source: {source_label or 'source review context not recorded'}; "
                    f"review: {documentation_status or 'human review needed'}"
                ),
                "Metadata gap": "source/review metadata gap present" if has_gap else "source/review evidence metadata recorded",
                "Handoff/export context": "documentation context only; not a biological recommendation, not an optimization result, not an experimental validation, and not a wet-lab readiness judgment",
            }
        )
    return rows


def _render_catalog_documentation_references(ds) -> None:
    from services.pathway_wizard_context import get_pathway_wizard_context
    from services import project_catalog_asset_link_repository as persistent_catalog_links
    from services.expression_wizard_catalog_picker_presenter import (
        DEFAULT_WIZARD_REFERENCE_NOTE,
        WIZARD_CATALOG_PICKER_TITLE,
        add_expression_wizard_catalog_context_link,
        build_expression_wizard_catalog_picker_view_model,
        build_expression_wizard_catalog_traceability_summary,
    )
    from views.pathway_workspace_sections.linked_catalog_assets_section import project_links_storage_key

    context = get_pathway_wizard_context()
    view_model = build_expression_wizard_catalog_picker_view_model(
        project_context=context,
        session_state=st.session_state,
    )
    project_id = view_model.get("project_id")

    _section_label(WIZARD_CATALOG_PICKER_TITLE)
    st.caption(view_model.get("boundary_copy", ""))
    st.caption(view_model.get("seed_context_copy", ""))

    if not project_id:
        if hasattr(st, "info"):
            st.info(view_model.get("message") or "No project context is linked to this Wizard session.")
        else:
            st.caption(view_model.get("message") or "No project context is linked to this Wizard session.")
        return

    if not all(hasattr(st, attr) for attr in ("selectbox", "text_area", "dataframe", "button")):
        st.caption("Catalog context picker controls are unavailable in this test harness.")
        return

    options = [row for row in view_model.get("options") or [] if isinstance(row, dict)]
    if not options:
        if hasattr(st, "info"):
            st.info(view_model.get("message") or "No catalog context is available for this design record.")
        else:
            st.caption(view_model.get("message") or "No catalog context is available for this design record.")
        return

    current_links = persistent_catalog_links.list_project_catalog_asset_links(project_id)
    traceability_summary = build_expression_wizard_catalog_traceability_summary(current_links, project_id=project_id)
    st.caption(
        "Catalog references shown here are documentation-level linked context for source/review tracing; "
        "they are not selection advice, not source review completion, not downstream-use state, and no outcome forecast."
    )
    if traceability_summary.get("traceability_rows"):
        st.caption(
            "Expression Wizard catalog traceability: "
            f"{traceability_summary.get('reference_count', 0)} reference(s); "
            f"{traceability_summary.get('plant_promoter_reference_count', 0)} Component Library promoter asset reference(s); "
            f"{traceability_summary.get('missing_metadata_count', 0)} missing source/review metadata field(s)."
        )
        st.caption(
            "Catalog context readback summarizes existing linked source/review context and metadata gaps for Step 6 "
            "handoff/export context. It is not a biological recommendation, not an optimization result, "
            "not an experimental validation, and not a wet-lab readiness judgment."
        )
        st.dataframe(
            pd.DataFrame(_catalog_context_readback_rows(traceability_summary.get("traceability_rows") or [])),
            use_container_width=True,
            hide_index=True,
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Asset type": row.get("asset_type"),
                        "Asset id": row.get("asset_id"),
                        "Record identifier": row.get("record_identifier"),
                        "Asset label": row.get("asset_label"),
                        "Catalog source/status": row.get("catalog_source_status"),
                        "Source label": row.get("source_label"),
                        "Documentation status": row.get("documentation_status"),
                        "Linked project": row.get("linked_project_id"),
                        "Reference origin": row.get("reference_origin"),
                        "Documentation note": row.get("reference_note"),
                        "Limitation note": row.get("limitation_note"),
                    }
                    for row in traceability_summary.get("traceability_rows") or []
                ]
            ),
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption(traceability_summary.get("message") or "No Expression Wizard catalog context references are recorded.")
    linked_identity = {
        (
            str(row.get("asset_type") or "").strip().casefold(),
            str(row.get("asset_id") or "").strip().casefold(),
            str(row.get("linkage_role") or "").strip().casefold(),
        )
        for row in current_links
        if isinstance(row, dict)
    }

    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Catalog context": row.get("display_label"),
                    "Asset type": row.get("asset_type"),
                    "Asset id": row.get("asset_id"),
                    "Record identifier": row.get("record_identifier"),
                    "Species / clade": row.get("species_or_clade"),
                    "Catalog source/status": row.get("catalog_source_status"),
                    "Source label": row.get("source_label"),
                    "Documentation status": row.get("documentation_status"),
                    "Documentation note": row.get("reference_note"),
                    "Limitation note": row.get("limitation_note"),
                    "Existing reference context": (
                        "already linked"
                        if (
                            str(row.get("asset_type") or "").strip().casefold(),
                            str(row.get("asset_id") or "").strip().casefold(),
                            "design_record_context",
                        )
                        in linked_identity
                        else ""
                    ),
                }
                for row in options
            ]
        ),
        use_container_width=True,
        hide_index=True,
    )

    selected_option_id = st.selectbox(
        "Select catalog context reference",
        options=[row["option_id"] for row in options],
        format_func=lambda option_id: next(
            (
                row.get("select_label") or row.get("display_label") or str(option_id)
                for row in options
                if row.get("option_id") == option_id
            ),
            str(option_id),
        ),
        key=f"wf_p6_catalog_picker_select_{project_id}",
    )
    documentation_note = st.text_area(
        "Catalog context note",
        value=DEFAULT_WIZARD_REFERENCE_NOTE,
        key=f"wf_p6_catalog_picker_note_{project_id}",
        height=80,
        placeholder="Optional local review note",
    )
    if st.button(
        "Add documentation-level reference",
        key=f"wf_p6_catalog_picker_add_{project_id}",
        use_container_width=True,
    ):
        result = add_expression_wizard_catalog_context_link(
            project_context=context,
            session_state=st.session_state,
            option_id=selected_option_id,
            documentation_note=documentation_note or DEFAULT_WIZARD_REFERENCE_NOTE,
        )
        st.session_state[project_links_storage_key(project_id)] = persistent_catalog_links.list_project_catalog_asset_links(project_id)
        if result.get("added"):
            st.success(result.get("message") or "Catalog asset documentation reference saved.")
            st.rerun()
        elif result.get("duplicate"):
            st.info("This catalog context is already linked as an existing reference context for this project.")
        else:
            st.info(result.get("message") or "Catalog context reference was not added.")


def _build_export_recommendation(ds, seq: str, validation_state: dict | None = None) -> dict:
    """Backward-compatible wrapper around services.export_recommendation_service."""
    return build_export_recommendation(
        ds.validation_results or [],
        ds.primers or [],
        seq,
        validation_complete=(validation_state or {}).get("is_complete"),
    )


def _render_export_risk_summary(summary: dict) -> None:
    """Render the top-of-page export recommendation summary."""
    display_title = {
        "Documentation Export Available": "Documentation export records available",
        "Export with Review Required": "Export requires review",
        "Review blocked by unresolved risk signals": "Review blocked by unresolved risk signals",
    }.get(summary["recommendation"], summary["recommendation"])
    display_conclusion = {
        "Documentation Export Available": (
            "Current documentation checks are complete, the active primer option is acceptable, and no "
            "recorded review blockers remain in this workspace record."
        ),
        "Export with Review Required": (
            "Review-check or primer-risk signals still require review. Keep exports as "
            "documentation-only records while review remains open."
        ),
        "Review blocked by unresolved risk signals": (
            "Primer or review-check risks remain. Exports are documentation-only records while risks remain."
        ),
    }.get(summary["recommendation"], summary["conclusion"])
    display_action = {
        "Documentation Export Available": "Download documentation export records for traceability.",
        "Export with Review Required": "Review Step 5 and primer-risk signals before relying on this record.",
        "Review blocked by unresolved risk signals": "Resolve risk signals before opening supporting preview workspaces.",
    }.get(summary["recommendation"], summary["action"])

    _section_label("Export review status")
    _status_panel(display_title, display_conclusion, tone=summary["tone"])
    st.caption(f"Current review status: {str(summary['recommendation']).lower()}.")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Critical issues", summary["critical_count"])
    c2.metric("Warning issues", summary["warning_count"])
    c3.metric("Primer high-risk count", summary["primer_high_risk_count"])
    c4.metric("Usable-with-risk primer count", summary["primer_review_count"])

    action_required_count = summary.get(
        "primer_action_required_count",
        summary["primer_high_risk_count"] + summary["primer_review_count"],
    )
    st.metric("Primer action-required count", action_required_count)

    if summary["affected_fragments"]:
        st.caption("Affected primer fragments: " + ", ".join(summary["affected_fragments"]))
    if summary["primer_high_risk_count"]:
        st.caption("High-risk primers are counted separately and require action before documentation export review.")
    st.caption("Next review action: " + display_action)


def _render_report_preview_summary_cards(report_presenter: dict) -> None:
    """Backward-compatible wrapper around the shared report preview container."""
    render_report_preview_container(
        report_presenter,
        step_keys=["step4", "step5", "step6"],
        section_title="Preview design report",
    )


def _render_step6_report_display(report_presenter: dict, report_markdown: str) -> None:
    """Render the unified Step 6 report display using shared components."""
    _render_report_preview_summary_cards(report_presenter)
    render_report_sequence_preview(report_presenter, heading="Final construct sequence")
    render_report_download_button(
        report_presenter,
        report_markdown,
        button_key="wf_p6_report_md",
    )


def _render_save_to_construct_bridge(ds) -> None:
    if not hasattr(st, "form"):
        return

    from services import expression_construct_repository as construct_repo
    from services.expression_wizard_construct_bridge import (
        DEFAULT_CASSETTE_LABEL,
        DEFAULT_CONSTRUCT_LABEL,
        PATHWAY_LINK_DEFERRED_NOTE,
        save_wizard_draft_to_construct,
    )

    _section_label("Save to Expression Construct")
    st.caption(
        "Save the current single-cassette Wizard state as expression cassette documentation in the editable construct workspace. "
        "This creates local documentation rows only."
    )

    construct_options = construct_repo.list_construct_profiles()
    option_labels = [
        f"{row.get('construct_label') or 'Untitled construct draft'} / {row.get('construct_id')}"
        for row in construct_options
        if row.get("construct_id")
    ]
    has_constructs = bool(option_labels)

    with st.form("wf_p6_construct_bridge_form"):
        if has_constructs:
            save_mode = st.radio(
                "Construct save target",
                ["Existing construct draft", "New construct draft"],
                horizontal=True,
                key="wf_p6_construct_save_mode",
            )
            selected_label = st.selectbox(
                "Existing construct draft",
                options=option_labels,
                key="wf_p6_construct_existing",
                disabled=save_mode != "Existing construct draft",
            )
            selected_construct_id = next(
                (
                    row.get("construct_id")
                    for row, label in zip(construct_options, option_labels)
                    if label == selected_label
                ),
                "",
            )
        else:
            save_mode = "New construct draft"
            selected_construct_id = ""
            st.info("No construct drafts are present yet. Create a new construct draft from this Wizard cassette.")

        default_construct_label = ds.gene_name or DEFAULT_CONSTRUCT_LABEL
        new_construct_label = st.text_input(
            "New construct label",
            value=default_construct_label,
            key="wf_p6_construct_new_label",
            disabled=has_constructs and save_mode != "New construct draft",
        )
        cassette_label = st.text_input(
            "Cassette label",
            value=ds.gene_name or DEFAULT_CASSETTE_LABEL,
            key="wf_p6_construct_cassette_label",
        )
        submitted = st.form_submit_button(
            "Save cassette documentation to construct",
            key="wf_p6_construct_save_submit",
        )

    if not submitted:
        saved_summary = st.session_state.get("wf_p6_construct_bridge_saved_summary")
        if isinstance(saved_summary, dict) and saved_summary.get("cassette_label"):
            st.caption(
                "Last saved cassette documentation: "
                f"{saved_summary.get('cassette_label')} in {saved_summary.get('construct_label')} "
                f"({saved_summary.get('part_count', 0)} part row(s))."
            )
        return

    try:
        from services.pathway_wizard_context import get_pathway_wizard_context

        pathway_context = get_pathway_wizard_context()
        result = save_wizard_draft_to_construct(
            ds,
            construct_id=str(selected_construct_id or ""),
            cassette_label=cassette_label,
            create_new_construct=(save_mode == "New construct draft"),
            new_construct_label=new_construct_label,
            pathway_context=pathway_context,
        )
    except Exception as exc:
        st.error(f"Cassette documentation could not be saved to the construct workspace: {exc}")
        return

    cassette_id = str(result.cassette.get("cassette_id") or "")
    if not cassette_id:
        st.error("Cassette documentation could not be saved to the construct workspace.")
        return

    summary = {
        "construct_label": result.construct.get("construct_label") or "Untitled construct draft",
        "construct_id": result.construct.get("construct_id") or "",
        "cassette_label": result.cassette.get("cassette_label") or "Untitled cassette draft",
        "cassette_id": cassette_id,
        "part_count": len(result.cassette_parts),
    }
    st.session_state["wf_p6_construct_bridge_saved_summary"] = summary
    st.success("Cassette documentation saved to the local construct workspace.")
    st.caption("Open Expression Constructs to review saved cassette documentation.")
    st.markdown(
        "\n".join(
            [
                f"- Construct: {summary['construct_label']}",
                f"- Cassette: {summary['cassette_label']}",
                f"- Cassette part rows: {summary['part_count']}",
                f"- Gene link: {'recorded' if result.gene_link else 'not recorded'}",
                f"- Pathway step link: {'deferred' if result.pathway_link_deferred else 'recorded'}",
            ]
        )
    )
    if result.pathway_link_deferred:
        st.caption(result.pathway_link_note or PATHWAY_LINK_DEFERRED_NOTE)
    if st.button(
        "Open Expression Constructs",
        key="wf_p6_open_expression_constructs",
        use_container_width=True,
        help="Open the construct workspace to review saved cassette documentation.",
    ):
        st.session_state[SK.SELECTED_PAGE] = "Expression Constructs"
        st.rerun()


def page(ctrl) -> None:
    ds = ctrl.get()
    _step_header(
        6,
        "Export Review",
        "Review documentation status, Plant Design Review Package direction/readback, export files, and saved design record status.",
        [
            "Confirm preview, export, and validation status for documentation.",
            "Plant MVP context: Plant Design Review Package direction/readback for documentation handoff.",
            "Download sequence files, the construct/cassette map preview PNG, and the design report.",
            "Save to the dashboard or open supporting preview workspaces when available.",
        ],
    )

    from components.export_manager import (
        build_design_session_export_payload,
        build_export_manifest,
        build_export_manifest_payload,
    )

    summary = ds.summary()
    export_payload = build_design_session_export_payload(ds)
    seq = export_payload["sequence"]
    validation_state = build_validation_run_state(
        ds,
        task_status=st.session_state.get("validation_task_status"),
        task_error=st.session_state.get("validation_task_error"),
    )
    export_recommendation = _build_export_recommendation(ds, seq, validation_state)
    has_sequence = export_payload["has_sequence"]
    preview_ready = has_sequence
    delivery_ready = (
        has_sequence
        and validation_state["is_complete"]
        and not validation_state["is_stale"]
        and not validation_state["is_running"]
        and not validation_state["is_failed"]
        and validation_state["critical_count"] == 0
        and export_recommendation["recommendation"] == "Documentation Export Available"
    )

    _render_export_risk_summary(export_recommendation)
    render_flow_strip(
        [
            ("Input", "Final construct sequence, review-check state, and active primer context"),
            ("Output", "Documentation-only export files, report, and saved design state"),
        ]
    )

    _section_label("Design record review")
    c1, c2, c3 = st.columns(3)
    c1.metric("Gene", summary["gene_name"] or "--")
    c2.metric("Host", summary["host"] or "--")
    c3.metric("Length (bp)", summary["frame_length_bp"])
    c4, c5, c6 = st.columns(3)
    c4.metric("GC content", f"{summary.get('gc_content', 0.0):.1f}%" if summary.get("gc_content") else "--")
    c5.metric("Primer count", summary.get("n_primers", 0))
    c6.metric("Issue count", summary.get("n_issues", 0))

    if not preview_ready:
        _status_panel(
            "Preview not available yet",
            "No final construct sequence is available yet. Complete sequence/frame generation before previewing or exporting.",
            tone="warn",
        )
    elif validation_state["status"] == "not_run":
        _status_panel(
            "Review checks have not been run",
            "Sequence preview and file export are available, but final review checks have not been run yet. Treat this design as preview-only until review checks are finished.",
            tone="info",
        )
    elif validation_state["status"] == "running":
        _status_panel(
            "Review checks are running",
            "Sequence preview and file export are available, but final review checks are still running. Treat this design as preview-only until review checks are finished.",
            tone="info",
        )
    elif validation_state["status"] == "failed":
        _status_panel(
            "Review checks failed or are unavailable",
            "The review-check task failed or the review-check tool is unavailable. Retry Step 5 review checks before using this as a completed documentation record.",
            tone="warn",
        )
    elif validation_state["status"] == "stale":
        _status_panel(
            "Stored review-check result is stale",
            "The frame or primer context changed since the last review-check run. Run Step 5 review checks again before completing the documentation review.",
            tone="warn",
        )
    elif validation_state["status"] == "completed_blocked":
        _status_panel(
            "Review checks have blocking issues - review remains open",
            "Review checks completed, but critical issues are still present. Keep this design as a review record until those blocking issues are resolved.",
            tone="warn",
        )
    elif validation_state["status"] == "completed_review":
        _status_panel(
            "Review checks complete - manual review remains open",
            "Review checks completed with warning-level signals. Export files can be generated as documentation records, but review notes remain important.",
            tone="info",
        )
    else:
        _status_panel(
            "Documentation checks completed - documentation review complete",
            "Sequence preview, FASTA/GenBank export, and documentation checks are complete for this documentation record.",
            tone="ready",
        )

    validation_readiness = "complete" if validation_state["is_complete"] else validation_state["status"]
    st.caption(
        f"Artifact generation status: preview {'available' if preview_ready else 'not available'} · "
        f"export files {'available' if has_sequence else 'not available'} · "
        f"review checks {validation_readiness} · "
        f"documentation review {'complete' if delivery_ready else 'open'}"
    )

    _review_panel(ds, summary)
    _render_catalog_documentation_references(ds)

    _section_label("Design report")
    try:
        _report = export_payload["report"]
        _report_json = json.dumps(_report, ensure_ascii=False, sort_keys=True, default=str)
        _report_signature = hashlib.sha256(_report_json.encode("utf-8")).hexdigest()
        _cached_report = _build_cached_report_payload(_report_signature, _report_json)
        _md_report = _cached_report["markdown"]
        _report_presenter = _cached_report["presenter"]
        _render_step6_report_display(_report_presenter, _md_report)
        if _report_presenter.get("alignment_rows"):
            st.caption("The report preview below mirrors the Step 4, Step 5, and Step 6 summaries shown on this page.")
    except Exception as _rep_err:
        _status_panel("Report preview unavailable", f"Unable to generate the report: {_rep_err}", tone="info")

    _section_label("Construct/cassette map preview")
    _png_cached = st.session_state.get("wf_plasmid_png")
    _fig_cached = st.session_state.get("wf_plasmid_fig")
    _feats = export_payload["plasmid_map_features"]
    _title = export_payload["plasmid_map_title"]
    _png_signature = None
    _minimal_map_features = _is_minimal_map_feature_set(_feats, len(seq))
    st.caption(
        "Documentation map preview for construct/cassette handoff review. This preview is not sequence validation, "
        "not cloning feasibility verification, and not experimental readiness approval."
    )
    if seq and len(seq) >= 30 and not _minimal_map_features:
        _png_signature = _plasmid_png_signature(seq, _feats, _title)
        if st.session_state.get("wf_plasmid_png_signature") != _png_signature or _png_cached is None or _fig_cached is None:
            try:
                _cache_fig, _png = _render_plasmid_png(seq, _feats, _title)
                if _fig_cached is not None and _fig_cached is not _cache_fig:
                    _close_plasmid_figure(_fig_cached)
                st.session_state["wf_plasmid_png"] = _png
                st.session_state["wf_plasmid_fig"] = _cache_fig
                st.session_state["wf_plasmid_png_signature"] = _png_signature
                _png_cached = _png
                _fig_cached = _cache_fig
            except Exception:
                _close_plasmid_figure(st.session_state.get("wf_plasmid_fig"))
                _clear_plasmid_cache_state()
                _png_cached = None
                _fig_cached = None

        with st.expander("Preview construct/cassette map", expanded=False):
            try:
                map_col_l, map_col_c, map_col_r = st.columns([2, 3, 2])
                with map_col_c:
                    if _fig_cached is not None:
                        st.pyplot(_fig_cached, use_container_width=False)
                    else:
                        raise ValueError("Construct/cassette map figure is not available.")
            except Exception as _e:
                st.caption(f"Construct/cassette map rendering was skipped: {_e}")
            _render_map_feature_readback(_feats, len(seq))
    elif seq and len(seq) >= 30:
        _close_plasmid_figure(st.session_state.get("wf_plasmid_fig"))
        _clear_plasmid_cache_state()
        _png_cached = None
        _fig_cached = None
        _status_panel(
            "Map feature documentation follow-up",
            "Only a whole-sequence fallback feature is available. Add feature annotations before rendering a construct/cassette map preview for handoff review.",
            tone="info",
        )
        _render_map_feature_readback(_feats, len(seq))
    else:
        _close_plasmid_figure(st.session_state.get("wf_plasmid_fig"))
        _clear_plasmid_cache_state()
        _png_cached = None
        _fig_cached = None
        _status_panel(
            "No construct/cassette map preview yet",
            "A renderable construct sequence with documented features is required before a map preview can be generated. Treat missing data as manual documentation follow-up, not design failure.",
            tone="info",
        )

    _section_label("Export files")
    export_is_ready_for_handoff = export_recommendation["recommendation"] == "Documentation Export Available"
    documentation_only_export = has_sequence and not export_is_ready_for_handoff
    if export_is_ready_for_handoff:
        export_panel_title = "Documentation export records available"
        export_panel_body = "The export set is aligned with the current review recommendation. Continue with FASTA, GenBank, report, and construct/cassette map downloads as documentation records."
        export_panel_tone = "ready"
        export_caption = "Export review status: documentation export records available for traceability."
        sequence_export_help = "Download a documentation sequence export."
        genbank_export_help = "Download an annotated GenBank documentation export."
        map_export_help = "Download a construct/cassette documentation map preview for handoff review; not sequence validation, cloning feasibility verification, or experimental readiness approval."
    elif export_recommendation["recommendation"] == "Export with Review Required":
        export_panel_title = "Documentation-only exports"
        export_panel_body = "Review-check or primer-risk signals still require review. Export files can be generated as documentation-only records while review remains open."
        export_panel_tone = "info"
        export_caption = "Export review status: review required. Exports are documentation-only records."
        sequence_export_help = "Documentation-only sequence export. Review risks remain."
        genbank_export_help = "Documentation-only GenBank export. Review risks remain."
        map_export_help = "Documentation-only construct/cassette map preview. Review risks remain; not sequence validation or experimental readiness approval."
    else:
        export_panel_title = "Documentation-only exports"
        export_panel_body = "The export files can still be used for record-keeping and communication, but primer or review-check risks remain unresolved."
        export_panel_tone = "warn"
        export_caption = "Export review status: blocked by unresolved risk signals. Exports are documentation-only records while risks remain."
        sequence_export_help = "Documentation-only sequence export. Risks remain unresolved."
        genbank_export_help = "Documentation-only GenBank export. Risks remain unresolved."
        map_export_help = "Documentation-only construct/cassette map preview. Risks remain unresolved; not sequence validation or experimental readiness approval."

    if has_sequence or _png_cached:
        _status_panel(export_panel_title, export_panel_body, tone=export_panel_tone)
    else:
        _status_panel(
            "Export files not available yet",
            "Generate the construct sequence first to enable FASTA and GenBank export.",
            tone="info",
        )

    payloads = export_payload["payloads"]
    fasta_payload = payloads.get("fasta")
    genbank_payload = payloads.get("genbank")
    manifest_payload = None
    if has_sequence:
        manifest = build_export_manifest(
            export_payload=export_payload,
            report=export_payload.get("report") or {},
            validation_state=validation_state,
            export_recommendation=export_recommendation,
            delivery_ready=delivery_ready,
        )
        manifest_payload = build_export_manifest_payload(
            manifest,
            export_payload.get("safe_name") or "construct",
        )

    dl = st.columns(4)
    if fasta_payload:
        dl[0].download_button(
            "Download FASTA (.fasta)",
            fasta_payload["data"],
            file_name=fasta_payload["file_name"],
            mime=fasta_payload["mime"],
            key="wf_p6_fasta",
            use_container_width=True,
            help=sequence_export_help,
        )
    else:
        dl[0].button(
            "Download FASTA (.fasta)",
            key="wf_p6_fasta_disabled",
            use_container_width=True,
            disabled=True,
            help="Generate the final construct sequence first.",
        )

    if genbank_payload:
        dl[1].download_button(
            "Download GenBank (.gb)",
            genbank_payload["data"],
            file_name=genbank_payload["file_name"],
            mime=genbank_payload["mime"],
            key="wf_p6_genbank",
            use_container_width=True,
            help=genbank_export_help,
        )
    else:
        dl[1].button(
            "Download GenBank (.gb)",
            key="wf_p6_genbank_disabled",
            use_container_width=True,
            disabled=True,
            help="Annotated construct features are required before GenBank export can be generated.",
        )

    if _png_cached:
        dl[2].download_button(
            "Download construct/cassette map (PNG)",
            _png_cached,
            file_name=export_payload["png_filename"],
            mime="image/png",
            key="wf_p6_map_png",
            use_container_width=True,
            help=map_export_help,
        )
    else:
        dl[2].button(
            "Download construct/cassette map (PNG)",
            key="wf_p6_map_png_disabled",
            use_container_width=True,
            disabled=True,
            help="Document construct/cassette features before rendering the documentation map preview.",
        )

    if manifest_payload:
        dl[3].download_button(
            "Download export manifest (.json)",
            manifest_payload["data"],
            file_name=manifest_payload["file_name"],
            mime=manifest_payload["mime"],
            key="wf_p6_export_manifest",
            use_container_width=True,
            help="Download a structured metadata manifest for this export set. This file documents export status and does not certify experimental readiness.",
        )
    else:
        dl[3].button(
            "Download export manifest (.json)",
            key="wf_p6_export_manifest_disabled",
            use_container_width=True,
            disabled=True,
            help="Generate the final construct sequence first.",
        )

    st.caption(export_caption)


    try:
        from core.design_session import SessionController as _SC
        _SC().sync_to_global_state()
    except Exception:
        pass

    if has_sequence:
        st.divider()
        _section_label("Supporting preview workspace")
        if delivery_ready:
            _status_panel(
                "Open the assembly preview workspace",
                "Send the current expression frame to the Assembly and Cloning preview workspace for documentation-only review.",
                tone="info",
            )
            handoff_help = "Send the current expression frame to the Assembly and Cloning preview workspace."
        else:
            _status_panel(
                "Assembly preview workspace is blocked",
                "Resolve primer risks and rerun review checks before opening the supporting assembly preview workspace.",
                tone="warn",
            )
            handoff_help = "Resolve primer risks and rerun review checks before opening the supporting assembly preview workspace."
        if st.button(
            "Send to Assembly and Cloning",
            key="wf_p6_send_assembly",
            type="primary",
            use_container_width=False,
            disabled=not delivery_ready,
            help=handoff_help,
        ):
            try:
                from core.context_bridge import send_wizard_to_assembly
                _cp = st.session_state.get("_change_page_cb")
                send_wizard_to_assembly(change_page=_cp)
            except Exception as _e:
                st.error(f"Page navigation failed: {_e}")

    st.divider()
    _section_label("Save & finish")
    _save_key = "wf_p6_saved_name"
    _saved_name = st.session_state.get(_save_key)
    _pathway_link_warning = st.session_state.pop("pathway_link_warning", "")
    if _pathway_link_warning:
        st.warning(f"Design was saved to the dashboard, but pathway linking failed: {_pathway_link_warning}")
    if _saved_name:
        if delivery_ready:
            _status_panel(
                "Design saved - documentation review complete",
                f"Design **{_saved_name}** has been saved to the dashboard as a reviewed design record. You can open it there or start a new design.",
                tone="ready",
            )
        else:
            _status_panel(
                "Design saved - preview / export only",
                f"Design **{_saved_name}** has been saved to the dashboard. It is available for preview and documentation-only export while review remains open.",
                tone="info",
            )
        from services.pathway_wizard_context import get_pathway_wizard_context
        _saved_pathway_context = get_pathway_wizard_context()
        _show_pathway_return = _saved_pathway_context.get("source") == "pathway_workspace" and _saved_pathway_context.get("status") == "linked"
        if _show_pathway_return:
            st.caption(
                "This design is linked to the pathway step. Return to Pathway Workspace to review the updated linked design count."
            )
            col_pathway, col_dash, col_new = st.columns(3)
            if col_pathway.button("Return to Pathway Workspace", key="wf_p6_return_pathway", type="primary", use_container_width=True):
                from services.pathway_wizard_context import clear_pathway_wizard_context
                import streamlit as _st
                clear_pathway_wizard_context()
                _st.session_state[SK.SELECTED_PAGE] = "Pathway Workspace"
                _st.rerun()
        else:
            col_dash, col_new = st.columns(2)
        if col_dash.button("Open dashboard", key="wf_p6_goto_dash", type="primary" if not _show_pathway_return else "secondary", use_container_width=True):
            import streamlit as _st
            _st.session_state[SK.SELECTED_PAGE] = "Dashboard"
            _st.rerun()
        if col_new.button("Start new design", key="wf_p6_reset", use_container_width=True):
            from core.design_session import SessionController as _SC2
            from services.pathway_wizard_context import clear_pathway_wizard_context
            _clear_step6_save_state()
            clear_pathway_wizard_context()
            _SC2().reset()
    else:
        if has_sequence:
            _status_panel(
                "Save the current design",
                "You can save now. If review checks are still pending, treat the saved record as a preview record with review still open.",
                tone="ready" if delivery_ready else "info",
            )
        else:
            _status_panel("Save is unavailable", "Generate the core construct sequence before enabling save actions.", tone="warn")

        col_save, col_new2 = st.columns(2)
        if col_save.button("Save to dashboard", key="wf_p6_save", type="primary", use_container_width=True, disabled=not has_sequence, help="Generate the construct sequence first."):
            try:
                from services.design_saver import save_wizard_design
                _ok, _msg = save_wizard_design(ds)
                if _ok:
                    from services.pathway_wizard_context import (
                        has_active_pathway_wizard_context,
                        link_saved_design_to_active_pathway_context,
                    )
                    if has_active_pathway_wizard_context():
                        _link_ok, _link_msg, _link_attempted = link_saved_design_to_active_pathway_context(
                            ds,
                            saved_design_name=_msg,
                            validation_state=validation_state,
                            export_recommendation=export_recommendation,
                            documentation_only_export=documentation_only_export,
                        )
                        if _link_attempted and not _link_ok:
                            st.session_state["pathway_link_warning"] = _link_msg
                            st.warning(f"Design was saved to the dashboard, but pathway linking failed: {_link_msg}")
                    st.session_state[_save_key] = _msg
                    st.rerun()
                else:
                    st.error(f"Save failed: {_msg}")
            except Exception as _e:
                st.error(f"Save failed: {_e}")
        if col_new2.button("Start new design", key="wf_p6_reset", use_container_width=True):
            from core.design_session import SessionController as _SC
            from services.pathway_wizard_context import clear_pathway_wizard_context
            st.session_state.pop(_save_key, None)
            clear_pathway_wizard_context()
            _SC().reset()

    st.divider()
    _render_save_to_construct_bridge(ds)
