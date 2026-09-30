from __future__ import annotations

import html
import re
from collections.abc import Mapping
from contextlib import contextmanager
from typing import Any

import streamlit as st

from services.project_review_report_service import (
    EXPRESSION_CONSTRUCT_SECTION_COPY,
    build_project_review_report,
)
from services.project_output_boundary_copy import (
    PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE,
    PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE,
    PROJECT_OUTPUT_SCOPE_NOTE,
)
from services.expression_construct_review_decision_summary_presenter import (
    build_expression_construct_review_decision_summary,
)
from services.expression_construct_review_action_panel_presenter import (
    build_expression_construct_review_action_panel,
)
from services.documentation_review_label_helper import REVIEW_NEXT_COLUMN_LABEL
from services import expression_construct_workflow_router
from services import expression_construct_workflow_router_presenter
from services import plant_construct_draft_preview_presenter
from services import plant_construct_draft_readback_adapter
from services import plant_construct_draft_readback_preview_adapter
from services import plant_construct_task_draft_builder
from services import plant_route_construct_task_bridge
from services.plant_design_review_user_context import (
    USER_CONTEXT_FIELD_SPECS,
    build_plant_design_review_user_context_preview,
)
from services.plant_candidate_route_decision_matrix import (
    DECISION_STATUS_OPTIONS,
    ROUTE_DECISION_FIELD_SPECS,
    build_route_decision_matrix,
    build_route_review_workspace,
    format_route_decision_matrix_markdown,
    format_route_review_workspace_markdown,
)
from services.tool_artifact_service import list_tool_artifacts
from views import (
    expression_construct_workflow_router_preview_section,
    plant_construct_draft_preview_section,
    tool_typography,
)
from views.pathway_workspace_sections.step2_component_context_session import (
    current_step2_component_context_readback,
)

PROJECT_REVIEW_REPORT_BOUNDARY_COPY = (
    f"{PROJECT_OUTPUT_SCOPE_NOTE} This report is documentation-only. "
    "This report summarizes review records and computational previews only. "
    f"{PROJECT_OUTPUT_NO_BIOLOGICAL_DECISION_NOTE} {PROJECT_OUTPUT_NO_RANK_SCORE_DECISION_NOTE} "
    "This report does not forecast yield. "
    "This report does not tune pathways. This report does not provide wet-lab instructions."
)
PLANT_REVIEW_SESSION_CONTEXT_KEY = "plant_design_review_user_context"
PLANT_ROUTE_DECISION_MATRIX_SESSION_KEY = "plant_candidate_route_decision_matrix"
EXPRESSION_CONSTRUCT_WORKFLOW_ROUTER_PREVIEW_SESSION_KEY = (
    "expression_construct_workflow_router_presenter_payload"
)
EXPRESSION_CONSTRUCT_WORKFLOW_ROUTER_PREVIEW_UPSTREAM_SESSION_KEY = (
    "expression_construct_workflow_router_upstream_payload"
)
EXPRESSION_CONSTRUCT_WORKFLOW_ROUTER_PREVIEW_UPSTREAM_PROJECT_KEYS = (
    "expression_construct_workflow_router_presenter_payload",
    "expression_construct_workflow_router_payload",
    "expression_construct_workflow_route_result",
    "expression_construct_workflow_router_result",
    "expression_construct_workflow_intent_payload",
)
PLANT_CONSTRUCT_DRAFT_PREVIEW_SESSION_KEY = "plant_construct_draft_preview_presenter_payload"
PLANT_CONSTRUCT_DRAFT_PREVIEW_UPSTREAM_SESSION_KEY = "plant_construct_draft_preview_upstream_payload"
PLANT_CONSTRUCT_DRAFT_PREVIEW_UPSTREAM_PROJECT_KEYS = (
    "plant_construct_draft_preview_presenter_payload",
    "plant_construct_draft_preview_payload",
    "plant_construct_draft_readback_payload",
    "plant_construct_draft",
    "plant_construct_draft_payload",
    "construct_draft",
    "construct_draft_payload",
    "plant_construct_task_result",
    "construct_task_result",
    "plant_candidate_route_result",
    "candidate_route_result",
)


@contextmanager
def _temporary_streamlit_bindings(*modules: Any):
    """Keep extracted render helpers on the caller's Streamlit object without leaking it."""
    previous = [(module, module.st) for module in modules]
    try:
        for module, _previous_st in previous:
            module.st = st
        yield
    finally:
        for module, previous_st in reversed(previous):
            module.st = previous_st
PLANT_CONSTRUCT_DRAFT_PREVIEW_SOURCE_FALLBACK = "normalized in-memory construct draft preview"
PLANT_CONSTRUCT_DRAFT_PREVIEW_SOURCE_LABELS = {
    "candidate_route_payload": "candidate route payload",
    "construct_task_payload": "construct task payload",
    "construct_draft_payload": "construct draft payload",
    "readback_payload": "readback payload",
    "preview_payload": "preview payload",
    "presenter_payload": "R333 presenter payload",
}
QR_PAYLOAD_READBACK_WRAP_STYLE = (
    "font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace;"
    "font-size: 0.84rem;"
    "line-height: 1.45;"
    "white-space: pre-wrap;"
    "overflow-wrap: anywhere;"
    "word-break: break-word;"
    "background: #f8fafc;"
    "border: 1px solid #cbd5e1;"
    "border-radius: 0.45rem;"
    "padding: 0.65rem 0.75rem;"
    "margin: 0.25rem 0 0.4rem;"
    "color: #0f172a;"
)


def _render_readability_note(copy: str) -> None:
    st.markdown(f"<div class='tool-help-text'>{html.escape(copy)}</div>", unsafe_allow_html=True)


def _render_qr_payload_readback(payload: Any) -> None:
    payload_text = str(payload or "")
    st.caption(
        "QR payload text readback: wraps long identity text for review only; payload content is unchanged."
    )
    st.markdown(
        f"<div style=\"{QR_PAYLOAD_READBACK_WRAP_STYLE}\">{html.escape(payload_text)}</div>",
        unsafe_allow_html=True,
    )


def _safe_project_review_report_filename(project: dict[str, Any]) -> str:
    name = str(project.get("name") or project.get("target_product") or "pathway_project").strip().lower()
    safe_name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return f"project_review_report_{safe_name or 'pathway_project'}.md"


def _safe_detailed_report_draft_filename(project: dict[str, Any]) -> str:
    name = str(project.get("name") or project.get("target_product") or "pathway_project").strip().lower()
    safe_name = re.sub(r"[^a-z0-9]+", "_", name).strip("_")
    return f"detailed_documentation_report_draft_{safe_name or 'pathway_project'}.md"


def _safe_plant_review_markdown_draft_filename(
    project: dict[str, Any],
    user_context: dict[str, str] | None = None,
    identity: dict[str, Any] | None = None,
) -> str:
    context = user_context or {}
    package_identity = identity or {}
    name = str(context.get("project_name") or project.get("name") or "").strip().lower()
    fallback = str(package_identity.get("snapshot_id") or "runtime_preview").strip().lower()
    safe_name = re.sub(r"[^a-z0-9]+", "_", name or fallback).strip("_")
    return f"plant_design_review_package_draft_{safe_name or 'runtime_preview'}.md"


def _plant_user_context_defaults(project: dict[str, Any]) -> dict[str, str]:
    return {
        "project_name": str(project.get("name") or project.get("project_name") or ""),
        "target_product": str(project.get("target_product") or project.get("target_protein") or ""),
        "plant_species": str(project.get("plant_species") or project.get("host") or project.get("organism") or ""),
        "target_tissue": str(project.get("target_tissue") or project.get("target_organ") or ""),
        "expression_mode": str(project.get("expression_mode") or project.get("expression_strategy") or ""),
        "gene_cds_source": str(project.get("gene_cds_source") or project.get("gene_source") or ""),
        "plant_promoter": str(project.get("plant_promoter") or project.get("promoter") or ""),
        "utr_kozak": str(project.get("utr_kozak") or project.get("utr_context") or ""),
        "signal_transit_targeting": str(project.get("signal_transit_targeting") or project.get("targeting_context") or ""),
        "terminator": str(project.get("terminator") or ""),
        "selectable_marker_reporter": str(project.get("selectable_marker_reporter") or project.get("marker_reporter") or ""),
        "vector_backbone": str(project.get("vector_backbone") or project.get("vector") or project.get("backbone") or ""),
        "transformation_context": str(project.get("transformation_context") or project.get("delivery_context") or ""),
        "evidence_provenance_notes": str(project.get("evidence_provenance_notes") or project.get("review_notes") or ""),
        "manual_follow_up_notes": str(project.get("manual_follow_up_notes") or project.get("manual_follow_up") or ""),
    }


def _plant_user_context_project_key(project: dict[str, Any]) -> str:
    return str(project.get("id") or project.get("project_id") or "active")


def _plant_user_context_widget_key(project: dict[str, Any], field_key: str) -> str:
    return f"r317_plant_review_context_{_plant_user_context_project_key(project)}_{field_key}"


def _route_decision_matrix_widget_key(project: dict[str, Any], row_index: int, field_key: str) -> str:
    return (
        "r325_route_decision_matrix_"
        f"{_plant_user_context_project_key(project)}_{row_index}_{field_key}"
    )


def _expression_construct_workflow_router_preview_project_key(project: dict[str, Any]) -> str:
    return (
        f"{EXPRESSION_CONSTRUCT_WORKFLOW_ROUTER_PREVIEW_SESSION_KEY}_"
        f"{_plant_user_context_project_key(project)}"
    )


def _expression_construct_workflow_router_preview_upstream_project_key(project: dict[str, Any]) -> str:
    return (
        f"{EXPRESSION_CONSTRUCT_WORKFLOW_ROUTER_PREVIEW_UPSTREAM_SESSION_KEY}_"
        f"{_plant_user_context_project_key(project)}"
    )


def _plant_construct_draft_preview_project_key(project: dict[str, Any]) -> str:
    return f"{PLANT_CONSTRUCT_DRAFT_PREVIEW_SESSION_KEY}_{_plant_user_context_project_key(project)}"


def _plant_construct_draft_preview_upstream_project_key(project: dict[str, Any]) -> str:
    return f"{PLANT_CONSTRUCT_DRAFT_PREVIEW_UPSTREAM_SESSION_KEY}_{_plant_user_context_project_key(project)}"


def _plant_construct_draft_preview_session_payload(project: dict[str, Any]) -> dict[str, Any] | None:
    project_payload = st.session_state.get(_plant_construct_draft_preview_project_key(project))
    if isinstance(project_payload, dict):
        return project_payload
    shared_payload = st.session_state.get(PLANT_CONSTRUCT_DRAFT_PREVIEW_SESSION_KEY)
    return shared_payload if isinstance(shared_payload, dict) else None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _is_available_r342_presenter(payload: dict[str, Any]) -> bool:
    if payload.get("status") != expression_construct_workflow_router_presenter.PRESENTER_STATUS_AVAILABLE:
        return False
    if _mapping(payload.get("empty_state")).get("is_empty") is True:
        return False
    summary = _mapping(payload.get("route_summary_card"))
    return bool(_text(summary.get("matched_workflow_route")))


def _expression_construct_workflow_router_session_payload(project: dict[str, Any]) -> dict[str, Any] | None:
    project_payload = st.session_state.get(_expression_construct_workflow_router_preview_project_key(project))
    if isinstance(project_payload, dict):
        return project_payload
    shared_payload = st.session_state.get(EXPRESSION_CONSTRUCT_WORKFLOW_ROUTER_PREVIEW_SESSION_KEY)
    return shared_payload if isinstance(shared_payload, dict) else None


def _expression_construct_workflow_router_upstream_payload(project: dict[str, Any]) -> dict[str, Any] | None:
    project_payload = st.session_state.get(
        _expression_construct_workflow_router_preview_upstream_project_key(project)
    )
    if isinstance(project_payload, dict):
        return project_payload
    shared_payload = st.session_state.get(EXPRESSION_CONSTRUCT_WORKFLOW_ROUTER_PREVIEW_UPSTREAM_SESSION_KEY)
    if isinstance(shared_payload, dict):
        return shared_payload
    for key in EXPRESSION_CONSTRUCT_WORKFLOW_ROUTER_PREVIEW_UPSTREAM_PROJECT_KEYS:
        value = project.get(key)
        if isinstance(value, dict):
            return value
    return None


def _r342_presenter_from_router_upstream_payload(upstream_payload: Any) -> dict[str, Any] | None:
    payload = _mapping(upstream_payload)
    if not payload:
        return None

    if "route_summary_card" in payload and "route_status" in payload:
        return payload if _is_available_r342_presenter(payload) else None

    if "matched_workflow_route" in payload and "required_information_slots" in payload:
        presenter = (
            expression_construct_workflow_router_presenter
            .build_expression_construct_workflow_router_presenter(payload)
        )
        return presenter if _is_available_r342_presenter(presenter) else None

    intent_text = _text(
        payload.get("intent_text")
        or payload.get("user_intent_text")
        or payload.get("matched_intent_text")
        or payload.get("source_intent_text")
    )
    if intent_text:
        routed = expression_construct_workflow_router.route_expression_construct_workflow(
            intent_text,
            _mapping(payload.get("context")),
        )
        routed["matched_intent_text"] = intent_text
        presenter = (
            expression_construct_workflow_router_presenter
            .build_expression_construct_workflow_router_presenter(routed)
        )
        return presenter if _is_available_r342_presenter(presenter) else None

    return None


def _expression_construct_workflow_router_presenter_payload(project: dict[str, Any]) -> dict[str, Any] | None:
    existing = _expression_construct_workflow_router_session_payload(project)
    if isinstance(existing, dict) and _is_available_r342_presenter(existing):
        return existing
    return _r342_presenter_from_router_upstream_payload(
        _expression_construct_workflow_router_upstream_payload(project)
    )


def _is_available_r333_presenter(payload: dict[str, Any]) -> bool:
    if payload.get("status") != plant_construct_draft_preview_presenter.PRESENTER_STATUS_AVAILABLE:
        return False
    if _mapping(payload.get("empty_state")).get("is_empty") is True:
        return False
    rows = _mapping(payload.get("slot_table")).get("rows")
    return isinstance(rows, list) and bool(rows)


def _preview_from_readback_payload(readback: dict[str, Any]) -> dict[str, Any]:
    preview = plant_construct_draft_readback_preview_adapter.build_plant_construct_draft_readback_preview(readback)
    preview.update(
        {
            "draft_id": _text(readback.get("draft_id")),
            "draft_status": _text(readback.get("draft_status")),
            "manual_review_required": readback.get("manual_review_required") is not False,
            "safety_boundary": _text(readback.get("safety_boundary")),
            "review_items": readback.get("review_items") or preview.get("review_items") or [],
        }
    )
    return preview


def _r333_presenter_from_upstream_payload(upstream_payload: Any) -> dict[str, Any] | None:
    payload = _mapping(upstream_payload)
    if not payload:
        return None

    if "draft_summary_card" in payload and "slot_table" in payload:
        return payload if _is_available_r333_presenter(payload) else None

    if "slot_rows" in payload:
        presenter = plant_construct_draft_preview_presenter.build_plant_construct_draft_preview_presenter(payload)
        return presenter if _is_available_r333_presenter(presenter) else None

    if "readback_status" in payload:
        presenter = plant_construct_draft_preview_presenter.build_plant_construct_draft_preview_presenter(
            _preview_from_readback_payload(payload)
        )
        return presenter if _is_available_r333_presenter(presenter) else None

    if "construct_slots" in payload or "construct_draft_status" in payload:
        readback = plant_construct_draft_readback_adapter.build_plant_construct_draft_readback(payload)
        presenter = plant_construct_draft_preview_presenter.build_plant_construct_draft_preview_presenter(
            _preview_from_readback_payload(readback)
        )
        return presenter if _is_available_r333_presenter(presenter) else None

    if "construct_tasks" in payload or "construct_task_status" in payload:
        draft = plant_construct_task_draft_builder.build_plant_construct_task_draft(payload)
        readback = plant_construct_draft_readback_adapter.build_plant_construct_draft_readback(draft)
        presenter = plant_construct_draft_preview_presenter.build_plant_construct_draft_preview_presenter(
            _preview_from_readback_payload(readback)
        )
        return presenter if _is_available_r333_presenter(presenter) else None

    if "candidate_route" in payload or "route_generation_status" in payload:
        task_result = plant_route_construct_task_bridge.build_plant_construct_task_requirements(payload)
        draft = plant_construct_task_draft_builder.build_plant_construct_task_draft(task_result)
        readback = plant_construct_draft_readback_adapter.build_plant_construct_draft_readback(draft)
        presenter = plant_construct_draft_preview_presenter.build_plant_construct_draft_preview_presenter(
            _preview_from_readback_payload(readback)
        )
        return presenter if _is_available_r333_presenter(presenter) else None

    return None


def _plant_construct_draft_preview_upstream_payload(project: dict[str, Any]) -> dict[str, Any] | None:
    project_payload = st.session_state.get(_plant_construct_draft_preview_upstream_project_key(project))
    if isinstance(project_payload, dict):
        return project_payload
    shared_payload = st.session_state.get(PLANT_CONSTRUCT_DRAFT_PREVIEW_UPSTREAM_SESSION_KEY)
    if isinstance(shared_payload, dict):
        return shared_payload
    for key in PLANT_CONSTRUCT_DRAFT_PREVIEW_UPSTREAM_PROJECT_KEYS:
        value = project.get(key)
        if isinstance(value, dict):
            return value
    return None


def _populate_plant_construct_draft_preview_payload_bridge(project: dict[str, Any]) -> dict[str, Any] | None:
    existing = _plant_construct_draft_preview_session_payload(project)
    if isinstance(existing, dict) and _is_available_r333_presenter(existing):
        return existing

    presenter = _r333_presenter_from_upstream_payload(
        _plant_construct_draft_preview_upstream_payload(project)
    )
    if not presenter:
        return None

    st.session_state[_plant_construct_draft_preview_project_key(project)] = presenter
    return presenter


def _plant_construct_draft_preview_source_type(payload: Any, *, infer_presenter: bool = True) -> str:
    source = _mapping(payload)
    if not source:
        return ""

    explicit_value = (
        source.get("preview_source_type")
        or source.get("upstream_source_type")
        or source.get("source_payload_type")
        or source.get("source_type")
    )
    explicit = _text(explicit_value).casefold()
    if explicit in PLANT_CONSTRUCT_DRAFT_PREVIEW_SOURCE_LABELS:
        return explicit
    if explicit:
        return ""

    if "slot_rows" in source:
        return "preview_payload"
    if "readback_status" in source:
        return "readback_payload"
    if "construct_slots" in source or "construct_draft_status" in source:
        return "construct_draft_payload"
    if "construct_tasks" in source or "construct_task_status" in source:
        return "construct_task_payload"
    if "candidate_route" in source or "route_generation_status" in source:
        return "candidate_route_payload"
    if infer_presenter and "draft_summary_card" in source and "slot_table" in source:
        return "presenter_payload"
    return ""


def _plant_construct_draft_preview_source_indicator_model(
    project: dict[str, Any],
    presenter_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    presenter = _mapping(presenter_payload)
    if not _is_available_r333_presenter(presenter):
        return {"is_visible": False}

    upstream_payload = _plant_construct_draft_preview_upstream_payload(project)
    upstream_source_type = _plant_construct_draft_preview_source_type(upstream_payload)
    presenter_source_type = _plant_construct_draft_preview_source_type(presenter, infer_presenter=True)
    source_type = upstream_source_type or presenter_source_type
    source_label = PLANT_CONSTRUCT_DRAFT_PREVIEW_SOURCE_LABELS.get(
        source_type,
        PLANT_CONSTRUCT_DRAFT_PREVIEW_SOURCE_FALLBACK,
    )

    summary = _mapping(presenter.get("draft_summary_card"))
    manual_review = summary.get("manual_review_required")
    manual_review_text = "yes" if manual_review is True else "no" if manual_review is False else "not provided"
    if upstream_source_type:
        bridge_status = "normalized from in-memory upstream payload"
    elif presenter_source_type:
        bridge_status = "project-scoped R333 presenter payload available"
    else:
        bridge_status = "project-scoped presenter payload available; source type not recorded"

    return {
        "is_visible": True,
        "source_type": source_type,
        "source_label": source_label,
        "draft_id": _text(summary.get("draft_id"), "not provided"),
        "draft_status": _text(summary.get("draft_status"), "not provided"),
        "manual_review_required": manual_review_text,
        "bridge_status": bridge_status,
    }


def _render_plant_construct_draft_preview_source_indicator(indicator: dict[str, Any]) -> None:
    if not indicator.get("is_visible"):
        return
    st.markdown("**Preview source/provenance and status**")
    st.caption(
        "Readback-only source/status for the construct draft preview below; manual review remains required."
    )
    st.caption(f"Preview source: {indicator.get('source_label') or PLANT_CONSTRUCT_DRAFT_PREVIEW_SOURCE_FALLBACK}")
    st.caption(f"Draft ID: {indicator.get('draft_id') or 'not provided'}")
    st.caption(f"Draft status: {indicator.get('draft_status') or 'not provided'}")
    st.caption(f"Manual review required: {indicator.get('manual_review_required') or 'not provided'}")
    st.caption(f"Upstream bridge status: {indicator.get('bridge_status') or 'not provided'}")


def _render_plant_construct_draft_preview_mount(project: dict[str, Any]) -> dict[str, Any]:
    st.markdown("**Plant Construct Draft Preview**")
    st.caption(
        "Read-only construct draft preview mount for the current Plant Design Review Package. "
        "Source/provenance and status captions stay next to the preview, followed by draft slot readback, "
        "missing information, review items, and warnings. This mount does not save records, create package data, "
        "change export behavior, or generate final sequences."
    )
    _populate_plant_construct_draft_preview_payload_bridge(project)
    presenter_payload = _plant_construct_draft_preview_session_payload(project)
    _render_plant_construct_draft_preview_source_indicator(
        _plant_construct_draft_preview_source_indicator_model(project, presenter_payload)
    )
    with _temporary_streamlit_bindings(plant_construct_draft_preview_section, tool_typography):
        section = plant_construct_draft_preview_section.render_plant_construct_draft_preview_section(
            presenter_payload
        )
    if section.get("status") == plant_construct_draft_preview_section.SECTION_STATUS_EMPTY:
        st.caption(
            "No current construct draft presenter payload is available in this review surface; "
            "the preview remains an empty read-only documentation section."
        )
    return section


def _render_expression_construct_workflow_router_preview_mount(project: dict[str, Any]) -> dict[str, Any]:
    st.markdown("**Expression Construct Workflow Router Preview**")
    st.caption(
        "Read-only route readback preview for expression construct/vector design review intents inside the "
        "current Plant Design Review Package surface. It displays an existing R342 presenter payload or a "
        "locally prepared router readback only; it does not save records, create package data, change export "
        "behavior, generate sequences, or add downstream procedure steps."
    )
    presenter_payload = _expression_construct_workflow_router_presenter_payload(project)
    with _temporary_streamlit_bindings(expression_construct_workflow_router_preview_section, tool_typography):
        section = (
            expression_construct_workflow_router_preview_section
            .render_expression_construct_workflow_router_preview_section(presenter_payload)
        )
    if section.get("status") == expression_construct_workflow_router_preview_section.SECTION_STATUS_EMPTY:
        st.caption(
            "No current expression construct workflow router presenter payload is available in this review surface; "
            "the route preview remains an empty read-only documentation section."
        )
    return section


def _render_plant_design_review_package_context(
    plant_package: dict[str, Any],
    plant_identity: dict[str, Any],
    plant_summary: dict[str, Any],
) -> None:
    st.markdown("**Plant Design Review Package context**")
    st.caption(
        "Documentation-only plant review package skeleton/readback for plant expression construct review context. "
        "Read-only design review package readback for plant expression construct documentation. "
        "Review order: package context and identity -> expression construct workflow route preview -> "
        "construct draft preview source/provenance -> construct draft preview readback -> missing information -> "
        "review items -> warnings."
    )
    st.caption(
        "This area summarizes existing documentation and in-memory preview context only; it is not saved/exported "
        "from this readback surface."
    )
    for note in plant_package.get("boundary_notes") or []:
        st.caption(f"- {note}")

    pi1, pi2, pi3 = st.columns(3, gap="small")
    pi1.metric("package sections", plant_summary.get("section_count", 0))
    pi2.metric("missing information fields", plant_summary.get("not_available_count", 0))
    pi3.metric("manual review rows", plant_summary.get("manual_follow_up_count", 0))

    st.markdown("**Report Identity / Verification**")
    st.caption(
        "Identity readback for traceability only; QR/MD5 text identifies this package snapshot."
    )
    st.caption(f"Package type: {plant_identity.get('package_type') or 'NOT_AVAILABLE'}")
    st.caption(f"Project direction: {plant_identity.get('project_direction') or 'NOT_AVAILABLE'}")
    st.caption(f"Report scope: {plant_identity.get('report_scope') or 'NOT_AVAILABLE'}")
    st.caption(f"Snapshot ID: {plant_identity.get('snapshot_id') or 'NOT_AVAILABLE'}")
    st.caption(f"MD5 checksum: {plant_identity.get('md5_checksum') or 'NOT_AVAILABLE'}")
    st.caption("QR payload:")
    _render_qr_payload_readback(plant_identity.get("qr_payload"))
    st.caption(str(plant_identity.get("qr_dependency_note") or "Payload-only QR payload preview."))
    for note in plant_identity.get("boundary_notes") or []:
        st.caption(f"- {note}")


def _render_plant_design_review_package_readback(plant_package: dict[str, Any]) -> None:
    st.markdown("**Plant package readback rows and missing information**")
    st.caption(
        "Readback rows summarize package fields already available to this report. "
        "NOT_AVAILABLE marks missing information for manual review required before any handoff note."
    )
    if plant_package.get("sections"):
        st.dataframe(
            [
                {
                    "Review section": row.get("title", ""),
                    "Readback": row.get("readback", ""),
                    "Missing information / manual review": row.get("manual_follow_up", ""),
                }
                for row in plant_package.get("sections") or []
                if isinstance(row, dict)
            ],
            hide_index=True,
        )
    else:
        st.info("No Plant Design Review Package readback rows are currently available.")


def _plant_user_context_session_store() -> dict[str, dict[str, str]]:
    store = st.session_state.get(PLANT_REVIEW_SESSION_CONTEXT_KEY)
    if not isinstance(store, dict):
        store = {}
        st.session_state[PLANT_REVIEW_SESSION_CONTEXT_KEY] = store
    return store


def _plant_user_context_session_values(project: dict[str, Any]) -> dict[str, str]:
    store = _plant_user_context_session_store()
    project_key = _plant_user_context_project_key(project)
    values = store.get(project_key)
    if not isinstance(values, dict):
        values = _plant_user_context_defaults(project)
        store[project_key] = values
    return {spec["key"]: str(values.get(spec["key"], "")) for spec in USER_CONTEXT_FIELD_SPECS}


def _save_plant_user_context_session_values(project: dict[str, Any], values: dict[str, str]) -> None:
    store = _plant_user_context_session_store()
    project_key = _plant_user_context_project_key(project)
    store[project_key] = {
        spec["key"]: str(values.get(spec["key"], ""))
        for spec in USER_CONTEXT_FIELD_SPECS
    }


def _clear_plant_user_context_session_values(project: dict[str, Any]) -> None:
    store = _plant_user_context_session_store()
    project_key = _plant_user_context_project_key(project)
    store.pop(project_key, None)
    for spec in USER_CONTEXT_FIELD_SPECS:
        st.session_state.pop(_plant_user_context_widget_key(project, spec["key"]), None)


def _route_decision_matrix_session_store() -> dict[str, list[dict[str, str]]]:
    store = st.session_state.get(PLANT_ROUTE_DECISION_MATRIX_SESSION_KEY)
    if not isinstance(store, dict):
        store = {}
        st.session_state[PLANT_ROUTE_DECISION_MATRIX_SESSION_KEY] = store
    return store


def _default_route_decision_rows(project: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "route_label": str(project.get("name") or project.get("project_name") or "Candidate route 1"),
            "route_type": "Plant expression construct review",
            "plant_host_context": str(project.get("plant_species") or project.get("host") or project.get("organism") or ""),
            "tissue_or_compartment_context": str(project.get("target_tissue") or project.get("target_organ") or ""),
            "expression_mode_context": str(project.get("expression_mode") or project.get("expression_strategy") or ""),
            "component_context_summary": str(project.get("component_context_summary") or ""),
            "linked_evidence_notes": str(project.get("evidence_provenance_notes") or project.get("review_notes") or ""),
            "route_risk_notes": "",
            "missing_information": "",
            "manual_follow_up": str(project.get("manual_follow_up_notes") or project.get("manual_follow_up") or ""),
            "decision_status": "Under review",
            "decision_rationale": "",
            "rejection_rationale": "",
        },
        {spec["key"]: "Under review" if spec["key"] == "decision_status" else "" for spec in ROUTE_DECISION_FIELD_SPECS},
        {spec["key"]: "Under review" if spec["key"] == "decision_status" else "" for spec in ROUTE_DECISION_FIELD_SPECS},
    ]


def _route_decision_matrix_session_values(project: dict[str, Any]) -> list[dict[str, str]]:
    store = _route_decision_matrix_session_store()
    project_key = _plant_user_context_project_key(project)
    rows = store.get(project_key)
    if not isinstance(rows, list):
        rows = _default_route_decision_rows(project)
        store[project_key] = rows
    normalized_rows: list[dict[str, str]] = []
    for row in rows[:3]:
        source = row if isinstance(row, dict) else {}
        normalized_rows.append(
            {
                spec["key"]: str(source.get(spec["key"], "Under review" if spec["key"] == "decision_status" else ""))
                for spec in ROUTE_DECISION_FIELD_SPECS
            }
        )
    while len(normalized_rows) < 3:
        normalized_rows.append(
            {
                spec["key"]: "Under review" if spec["key"] == "decision_status" else ""
                for spec in ROUTE_DECISION_FIELD_SPECS
            }
        )
    return normalized_rows


def _save_route_decision_matrix_session_values(project: dict[str, Any], rows: list[dict[str, str]]) -> None:
    store = _route_decision_matrix_session_store()
    project_key = _plant_user_context_project_key(project)
    store[project_key] = [
        {
            spec["key"]: str(row.get(spec["key"], "Under review" if spec["key"] == "decision_status" else ""))
            for spec in ROUTE_DECISION_FIELD_SPECS
        }
        for row in rows[:3]
        if isinstance(row, dict)
    ]


def _clear_route_decision_matrix_session_values(project: dict[str, Any]) -> None:
    store = _route_decision_matrix_session_store()
    project_key = _plant_user_context_project_key(project)
    store.pop(project_key, None)
    for row_index in range(3):
        for spec in ROUTE_DECISION_FIELD_SPECS:
            st.session_state.pop(
                _route_decision_matrix_widget_key(project, row_index, spec["key"]),
                None,
            )


def _plant_user_context_input(project: dict[str, Any]) -> dict[str, str]:
    session_values = _plant_user_context_session_values(project)
    context: dict[str, str] = {}
    st.markdown("**Manual plant review context input**")
    st.caption(
        "Session-only preview: these fields are not saved as a structured project record."
    )
    if st.button(
        "Clear plant review session fields",
        key=f"r319_clear_plant_review_context_{_plant_user_context_project_key(project)}",
    ):
        _clear_plant_user_context_session_values(project)
        session_values = _plant_user_context_session_values(project)
    for spec in USER_CONTEXT_FIELD_SPECS:
        key = spec["key"]
        widget_key = _plant_user_context_widget_key(project, key)
        label = spec["label"]
        value = session_values.get(key, "")
        if key in {"evidence_provenance_notes", "manual_follow_up_notes"}:
            context[key] = st.text_area(label, value=value, key=widget_key, height=72)
        else:
            context[key] = st.text_input(label, value=value, key=widget_key)
    _save_plant_user_context_session_values(project, context)
    return context


def _render_plant_review_markdown_reference_reopen(project: dict[str, Any]) -> None:
    st.markdown("**Re-open Plant Design Review Markdown draft for reference**")
    st.caption(
        "Reference-only preview: paste a Plant Design Review Package Markdown draft to view it beside "
        "the current runtime fields."
    )
    st.caption(
        "Not parsed into fields. Not saved as a structured project record. Does not modify current Plant Review session fields."
    )
    st.caption(
        "QR/MD5, if present, is package identity text only and does not validate biological correctness."
    )
    reference_markdown = st.text_area(
        "Paste Plant Design Review Package Markdown draft for reference",
        value="",
        height=220,
        key=f"r322_plant_review_markdown_reference_{_plant_user_context_project_key(project)}",
    )
    if reference_markdown.strip():
        st.markdown("**Reference-only preview**")
        st.caption(
            "Displayed as reference text only. This preview is not parsed, not saved, and does not update the current form."
        )
        st.code(reference_markdown, language="markdown")
    else:
        st.info(
            "Paste a Plant Design Review Package Markdown draft to display it as reference text only."
        )


def _render_plant_user_context_preview(project: dict[str, Any]) -> None:
    user_context = _plant_user_context_input(project)
    preview = build_plant_design_review_user_context_preview(user_context)
    package = preview.get("package") or {}
    identity = package.get("identity") or {}
    gaps = preview.get("source_provenance_gaps") or []

    st.markdown("**Plant Design Review Package preview from manual context**")
    st.caption(str(preview.get("documentation_only_copy") or "Documentation-only preview."))
    st.caption(str(preview.get("identity_only_copy") or "QR/MD5 verifies package identity only."))
    p1, p2, p3 = st.columns(3, gap="small")
    p1.metric("manual fields", len(preview.get("field_readback") or []))
    p2.metric("source/provenance gaps", len(gaps))
    p3.metric("preview status", preview.get("status") or "RUNTIME_PREVIEW_ONLY")

    st.markdown("**Manual context readback**")
    st.dataframe(
        [
            {
                "Field": row.get("field_label", ""),
                "Readback": row.get("readback", ""),
            }
            for row in preview.get("field_readback") or []
            if isinstance(row, dict)
        ],
        hide_index=True,
    )

    st.markdown("**Source/provenance gaps**")
    if gaps:
        st.dataframe(
            [
                {
                    "Field": row.get("field_label", ""),
                    "Issue": row.get("issue", ""),
                    "Manual follow-up": row.get("manual_follow_up", ""),
                }
                for row in gaps
                if isinstance(row, dict)
            ],
            hide_index=True,
        )
    else:
        st.info("No source/provenance gaps were detected from the manual context fields.")

    st.markdown("**Package identity for this preview**")
    st.caption(f"Snapshot ID: {identity.get('snapshot_id') or 'NOT_AVAILABLE'}")
    st.caption(f"MD5 checksum: {identity.get('md5_checksum') or 'NOT_AVAILABLE'}")
    st.caption("QR payload:")
    _render_qr_payload_readback(identity.get("qr_payload"))
    for note in identity.get("boundary_notes") or []:
        st.caption(f"- {note}")

    st.markdown("**Copyable Plant Design Review Package draft**")
    st.caption(
        "Runtime-only Markdown draft from the current manual context. Copy for review notes only; "
        "it is not saved, exported, or treated as a finalized package."
    )
    markdown_draft = str(preview.get("markdown_draft") or "")
    st.text_area(
        "Plant Design Review Package Markdown draft",
        value=markdown_draft,
        height=360,
        key=(
            "r318_plant_review_markdown_draft_"
            f"{_plant_user_context_project_key(project)}_"
            f"{identity.get('md5_checksum') or 'no_checksum'}"
        ),
    )
    st.caption(
        "Runtime download only: this does not save a structured project record or modify package export."
    )
    st.download_button(
        "Download current Plant Design Review Package draft (.md)",
        data=markdown_draft,
        file_name=_safe_plant_review_markdown_draft_filename(
            project,
            user_context=user_context,
            identity=identity,
        ),
        mime="text/markdown",
        use_container_width=True,
    )
    _render_plant_review_markdown_reference_reopen(project)


def _route_decision_matrix_input(project: dict[str, Any]) -> list[dict[str, str]]:
    session_rows = _route_decision_matrix_session_values(project)
    rows: list[dict[str, str]] = []
    st.markdown("**Plant candidate route decision matrix**")
    st.caption(
        "Session-only candidate route review rows for documentation follow-up. "
        "Rows are not saved as structured project records and do not modify package export."
    )
    if st.button(
        "Clear candidate route matrix session rows",
        key=f"r325_clear_route_decision_matrix_{_plant_user_context_project_key(project)}",
    ):
        _clear_route_decision_matrix_session_values(project)
        session_rows = _route_decision_matrix_session_values(project)

    for row_index, session_row in enumerate(session_rows):
        with st.expander(f"Candidate route row {row_index + 1}", expanded=(row_index == 0)):
            row: dict[str, str] = {}
            for spec in ROUTE_DECISION_FIELD_SPECS:
                key = spec["key"]
                widget_key = _route_decision_matrix_widget_key(project, row_index, key)
                label = spec["label"]
                value = session_row.get(key, "")
                if key == "decision_status":
                    options = list(DECISION_STATUS_OPTIONS)
                    index = options.index(value) if value in options else 0
                    row[key] = str(st.selectbox(label, options, index=index, key=widget_key))
                elif key in {
                    "component_context_summary",
                    "linked_evidence_notes",
                    "route_risk_notes",
                    "missing_information",
                    "manual_follow_up",
                    "decision_rationale",
                    "rejection_rationale",
                }:
                    row[key] = st.text_area(label, value=value, key=widget_key, height=72)
                else:
                    row[key] = st.text_input(label, value=value, key=widget_key)
            rows.append(row)
    _save_route_decision_matrix_session_values(project, rows)
    return rows


def _render_route_decision_matrix_preview(project: dict[str, Any]) -> None:
    rows = _route_decision_matrix_input(project)
    workspace = build_route_review_workspace(rows)
    matrix = workspace.get("matrix") or build_route_decision_matrix(rows)
    evidence_cards = workspace.get("evidence_cards") or {}
    component_traceability = workspace.get("component_traceability") or {}
    summary = matrix.get("summary") or {}
    markdown_snapshot = format_route_decision_matrix_markdown(matrix)
    workspace_markdown = format_route_review_workspace_markdown(workspace)

    st.caption(str(matrix.get("boundary_note") or "Documentation-only candidate route review."))
    m1, m2, m3, m4, m5 = st.columns(5, gap="small")
    m1.metric("candidate route rows", summary.get("route_count", 0))
    m2.metric("documentation gaps", summary.get("documentation_gap_count", 0))
    m3.metric("manual follow-up rows", summary.get("manual_follow_up_count", 0))
    m4.metric(
        "documentation follow-up",
        summary.get("selected_for_documentation_follow_up_count", 0),
    )
    m5.metric(
        "evidence cards",
        (evidence_cards.get("summary") or {}).get("evidence_card_count", 0),
    )

    if matrix.get("rows"):
        st.dataframe(
            [
                {
                    "Route label": row.get("route_label", ""),
                    "Route type": row.get("route_type", ""),
                    "Plant host context": row.get("plant_host_context", ""),
                    "Linked evidence notes": row.get("linked_evidence_notes", ""),
                    "Manual review status": row.get("decision_status", ""),
                    "Review focus": row.get("review_focus", ""),
                    "Manual follow-up": row.get("manual_follow_up", ""),
                }
                for row in matrix.get("rows") or []
                if isinstance(row, dict)
            ],
            hide_index=True,
        )
    else:
        st.info(str(matrix.get("empty_state_message") or "No candidate route rows are currently recorded."))

    st.markdown("**Candidate route documentation gaps**")
    if matrix.get("gap_rows"):
        st.dataframe(
            [
                {
                    "Route label": row.get("route_label", ""),
                    "Route type": row.get("route_type", ""),
                    "Missing fields": ", ".join(row.get("missing_fields") or []),
                    "Gap label": row.get("gap_label", ""),
                    "Next manual action": row.get("next_manual_action", ""),
                }
                for row in matrix.get("gap_rows") or []
                if isinstance(row, dict)
            ],
            hide_index=True,
        )
    else:
        st.info("No required documentation gaps were detected in the current candidate route rows.")

    st.markdown("**Route-linked evidence cards**")
    st.caption(
        "Evidence cards summarize route-linked notes for manual source/provenance review only."
    )
    if evidence_cards.get("cards"):
        st.dataframe(
            [
                {
                    "Evidence card": row.get("card_id", ""),
                    "Route label": row.get("route_label", ""),
                    "Evidence status": row.get("evidence_context_status", ""),
                    "Source/provenance status": row.get("source_provenance_status", ""),
                    "Uncertainty status": row.get("uncertainty_status", ""),
                    "Manual follow-up": row.get("manual_follow_up", ""),
                }
                for row in evidence_cards.get("cards") or []
                if isinstance(row, dict)
            ],
            hide_index=True,
        )
    else:
        st.info(
            str(
                evidence_cards.get("empty_state_message")
                or "No route-linked evidence cards are currently available."
            )
        )

    st.markdown("**Route-to-component traceability**")
    st.caption(
        "Traceability rows preserve component context summaries and source notes without selecting components."
    )
    if component_traceability.get("rows"):
        st.dataframe(
            [
                {
                    "Traceability row": row.get("traceability_row_id", ""),
                    "Route label": row.get("route_label", ""),
                    "Component context": row.get("component_trace_status", ""),
                    "Source trace": row.get("source_trace_status", ""),
                    "Manual review status": row.get("manual_review_status", ""),
                    "Manual follow-up": row.get("manual_follow_up", ""),
                }
                for row in component_traceability.get("rows") or []
                if isinstance(row, dict)
            ],
            hide_index=True,
        )
    else:
        st.info(
            str(
                component_traceability.get("empty_state_message")
                or "No component traceability rows are currently available."
            )
        )

    st.markdown("**Copyable candidate route matrix snapshot**")
    st.caption(
        "Runtime-only Markdown snapshot for manual review notes. It is not saved, exported, or treated as a finalized package."
    )
    st.text_area(
        "Plant Candidate Route Decision Matrix Markdown snapshot",
        value=markdown_snapshot,
        height=300,
        key=(
            "r325_route_decision_matrix_markdown_"
            f"{_plant_user_context_project_key(project)}"
        ),
    )
    st.markdown("**Copyable route review workspace snapshot**")
    st.caption(
        "Combined runtime-only snapshot of route rows, evidence cards, component traceability, gaps, and manual follow-up."
    )
    st.text_area(
        "Plant Route Review Workspace Markdown snapshot",
        value=workspace_markdown,
        height=340,
        key=(
            "r326_route_review_workspace_markdown_"
            f"{_plant_user_context_project_key(project)}"
        ),
    )


def render_project_review_report_section(
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None = None,
    expression_links: list[dict[str, Any]] | None = None,
    test_records: list[dict[str, Any]] | None = None,
    snapshots: list[dict[str, Any]] | None = None,
    review_signals: list[dict[str, Any]] | None = None,
    completeness_result: dict[str, Any] | None = None,
    linked_catalog_assets: list[dict[str, Any]] | None = None,
) -> None:
    st.subheader("Project Review Report")
    if not project:
        st.info("No active pathway project selected.")
        st.caption("Select a pathway documentation workspace to generate a Project Review Report.")
        return

    st.caption(
        "Documentation-only report surface for project documentation, linked design records, manifest/package "
        "exchange context, human review prompts, and computational previews."
    )
    st.caption("Project Review Report is a Project Outputs review surface.")
    st.caption(
        "This review surface summarizes linked design records, manifest/package exchange context, and human review prompts."
    )
    st.caption("Documentation-only report for review records and computational previews.")
    st.caption(f"Boundary: {PROJECT_REVIEW_REPORT_BOUNDARY_COPY}")
    _render_readability_note(
        "Readability note: start with Report summary and Project Review Follow-up Index, then inspect collapsed "
        "queues for source/provenance, package exchange, host/chassis context, and handoff review details."
    )
    _render_readability_note(f"Boundary: {PROJECT_REVIEW_REPORT_BOUNDARY_COPY}")
    st.caption(
        "Import Preview remains read-only. Blocked / NO-GO import states apply only to the gated create-as-new "
        "action, and any allowed action creates a local documentation-only project only after validation, safety "
        "review, dry-run planning, and explicit confirmation."
    )

    linked_tool_artifacts = list_tool_artifacts(project_id=project.get("id"))
    report_project = dict(project)
    report_project["pathway_steps"] = steps or []
    report_project["project_asset_links"] = linked_catalog_assets or []
    export_summary = {
        "status": "AVAILABLE",
        "package_contents_preview_status": "AVAILABLE",
        "last_export_status": "NOT_AVAILABLE",
        "documentation_only_boundary": "Project export packages are documentation-only review packages.",
    }
    report = build_project_review_report(
        report_project,
        linked_artifacts=linked_tool_artifacts,
        saved_designs=None,
        export_summary=export_summary,
        import_safety_summary=None,
        expression_links=expression_links,
        test_records=test_records,
        snapshots=snapshots,
        review_signals=review_signals,
        completeness_result=completeness_result,
        step2_component_context=current_step2_component_context_readback(),
    )

    if st.button("Generate Project Review Report", use_container_width=True):
        st.session_state[f"project_review_report_{project.get('id')}"] = report
    report = st.session_state.get(f"project_review_report_{project.get('id')}", report)
    detailed_draft = report["detailed_documentation_report_draft"]

    st.markdown("**Report summary**")
    st.caption(report["overall_summary"])
    _render_readability_note(str(report["overall_summary"]))
    identity = report["project_identity"]["fields"]
    st.caption(
        f"Project identity: {identity.get('project_name') or 'NOT_AVAILABLE'} "
        f"(project_id: {identity.get('project_id') or 'NOT_AVAILABLE'})"
    )
    c1, c2, c3, c4, c5 = st.columns(5, gap="small")
    with c1:
        st.metric("Missing fields", len(report.get("missing_fields") or []))
    with c2:
        st.metric("Linked artifacts", report["linked_artifacts_summary"].get("artifact_count", 0))
    with c3:
        st.metric("Pathway steps", report["pathway_steps_summary"].get("step_count", 0))
    with c4:
        construct_counts = report["expression_construct_documentation"].get("summary_counts") or {}
        st.metric("Construct records", construct_counts.get("construct_profile_count", 0))
    with c5:
        st.metric("Project construct links", construct_counts.get("project_link_count", 0))

    with st.expander("Boundary notes", expanded=False):
        for note in report.get("boundary_notes") or []:
            st.caption(f"- {note}")

    package_trail = report.get("package_exchange_review_trail") or {}
    manifest_review = package_trail.get("manifest_review") or {}
    record_counts = manifest_review.get("record_counts") or {}
    with st.expander("Package Exchange Review Trail", expanded=False):
        st.caption(
            "Documentation-only package exchange review trail for export/import context, manifest review, "
            "included sections, record count context, and review notes."
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

    host_context = report.get("host_chassis_context_summary") or {}
    with st.expander("Host / chassis documentation context", expanded=False):
        st.caption(
            "Read-only host / chassis context readback for chassis-neutral project review documentation."
        )
        st.caption(
            str(
                host_context.get("documentation_only_note")
                or "Host / chassis context readback is documentation context only."
            )
        )
        st.caption(
            f"Active project context: {host_context.get('project_context_label') or 'Generic / unspecified'}"
        )
        st.caption(
            "Supported chassis-neutral contexts: "
            + ", ".join(host_context.get("supported_contexts") or [])
        )
        st.caption(
            "Contexts present in readback: "
            + ", ".join(host_context.get("contexts_present_labels") or ["Generic / unspecified"])
        )
        st.caption(
            str(
                host_context.get("limitation_note")
                or "Plant and Nicotiana examples remain examples, not defaults."
            )
        )

        if host_context.get("rows"):
            st.dataframe(
                [
                    {
                        "Source label": row.get("source_label", ""),
                        "Source value": row.get("source_value", ""),
                        "Normalized context": row.get("normalized_context_label", ""),
                        "Record label": row.get("asset_display_name", ""),
                    }
                    for row in host_context.get("rows") or []
                    if isinstance(row, dict)
                ],
                hide_index=True,
            )
        else:
            st.info(
                "No host / chassis context readback rows are currently available for this report."
            )

    human_review_queue = report.get("candidate_evidence_human_review_queue") or {}
    queue_summary = human_review_queue.get("summary") or {}
    with st.expander("Candidate Evidence Human Review Queue", expanded=False):
        st.caption(
            "Read-only documentation, provenance, and manual follow-up context for candidate evidence rows "
            "visible in the project review report."
        )
        for note in human_review_queue.get("boundary_notes") or []:
            st.caption(f"- {note}")

        q1, q2, q3, q4 = st.columns(4, gap="small")
        q1.metric("queue items", queue_summary.get("queue_item_count", 0))
        q2.metric("source/provenance gaps", queue_summary.get("provenance_gap_count", 0))
        q3.metric("metadata needs review", queue_summary.get("metadata_gap_count", 0))
        q4.metric("manual follow-up", queue_summary.get("review_follow_up_count", 0))

        if not human_review_queue.get("rows"):
            st.info(
                str(
                    human_review_queue.get("empty_state_message")
                    or "No human review follow-up items are currently queued for this report."
                )
            )
        else:
            st.dataframe(
                [
                    {
                        "Queue item id": row.get("queue_item_id", ""),
                        "Candidate label": row.get("candidate_label", ""),
                        "Category": row.get("category_label", ""),
                        "Severity": row.get("severity_label", ""),
                        "Issue": row.get("issue", ""),
                        "Human follow-up": row.get("human_follow_up", ""),
                        "Source context": row.get("source_context", ""),
                    }
                    for row in human_review_queue.get("rows") or []
                    if isinstance(row, dict)
                ],
                hide_index=True,
            )
            if human_review_queue.get("total_rows_available", 0) > len(human_review_queue.get("rows") or []):
                st.caption(
                    "Additional queued items not shown in this preview: "
                    f"{human_review_queue.get('total_rows_available', 0) - len(human_review_queue.get('rows') or [])}"
                )

    follow_up_index = report.get("project_review_follow_up_index") or {}
    follow_up_summary = follow_up_index.get("summary") or {}
    with st.expander("Project Review Follow-up Index", expanded=True):
        st.caption(
            "Aggregates documentation and provenance follow-up items from project review queues. Review next: "
            "use the rows below to return to existing review surfaces for source/provenance, metadata, or manual follow-up."
        )
        for note in follow_up_index.get("boundary_notes") or []:
            st.caption(f"- {note}")

        f1, f2, f3 = st.columns(3, gap="small")
        f1.metric("total follow-up items", follow_up_summary.get("total_follow_up_items", 0))
        f2.metric(
            "candidate evidence items",
            (follow_up_summary.get("source_section_counts") or {}).get("candidate_evidence", 0),
        )
        f3.metric(
            "Component Library promoter asset items",
            (follow_up_summary.get("source_section_counts") or {}).get("plant_promoter_catalog", 0),
        )

        category_counts = follow_up_summary.get("category_counts") or {}
        if category_counts:
            st.caption(
                "Counts by category: "
                + ", ".join(f"{label}: {count}" for label, count in category_counts.items())
            )
            st.caption(
                "Review next: open the rows below for source/provenance, metadata, or manual follow-up context "
                "in existing review surfaces before preparing a handoff note."
            )

        if not follow_up_index.get("rows"):
            st.info(
                str(
                    follow_up_index.get("empty_state_message")
                    or "No manual documentation follow-up items are currently aggregated for this project review context."
                )
            )
        else:
            st.dataframe(
                [
                    {
                        "Follow-up id": row.get("follow_up_id", ""),
                        "Source section": row.get("source_section", ""),
                        "Item label": row.get("item_label", ""),
                        "Category": row.get("category", ""),
                        "Issue": row.get("issue", ""),
                        REVIEW_NEXT_COLUMN_LABEL: row.get("human_follow_up", ""),
                        "Manual review context": row.get("manual_review_context", ""),
                    }
                    for row in follow_up_index.get("rows") or []
                    if isinstance(row, dict)
                ],
                hide_index=True,
            )
            if follow_up_index.get("total_rows_available", 0) > len(follow_up_index.get("rows") or []):
                st.caption(
                    "Additional aggregated follow-up rows not shown in this preview: "
                    f"{follow_up_index.get('total_rows_available', 0) - len(follow_up_index.get('rows') or [])}"
                )

    promoter_gap_review = report.get("plant_promoter_evidence_gap_review") or {}
    promoter_summary = promoter_gap_review.get("summary_counts") or {}
    with st.expander("Component Library Promoter Asset Evidence Gap Review", expanded=False):
        st.caption(
            "Read-only Component Library promoter asset evidence gap review for documentation follow-up and catalog curation only."
        )
        st.caption(
            "Project-linked Component Library promoter asset references are preferred when available; otherwise the section stays in a safe catalog-context empty state."
        )
        for note in promoter_gap_review.get("boundary_notes") or []:
            st.caption(f"- {note}")

        p1, p2, p3 = st.columns(3, gap="small")
        p1.metric("promoter asset queue items", promoter_summary.get("queue_item_count", 0))
        p2.metric("promoter asset categories", promoter_summary.get("category_count", 0))
        p3.metric("promoter asset references in scope", promoter_summary.get("profile_count", 0))

        category_counts = promoter_gap_review.get("category_counts") or {}
        if category_counts:
            st.caption(
                "Counts by category: "
                + ", ".join(
                    f"{label}: {count}"
                    for label, count in category_counts.items()
                )
            )

        if not promoter_gap_review.get("rows"):
            st.info(
                str(
                    promoter_gap_review.get("empty_state_message")
                    or "No Component Library promoter asset evidence gap items are currently queued for this report."
                )
            )
        else:
            st.dataframe(
                [
                    {
                        "Queue item id": row.get("queue_item_id", ""),
                        "Promoter label": row.get("promoter_label", ""),
                        "Category": row.get("category", ""),
                        "Issue": row.get("issue", ""),
                        "Human follow-up": row.get("human_follow_up", ""),
                        "Source context": row.get("source_context", ""),
                    }
                    for row in promoter_gap_review.get("rows") or []
                    if isinstance(row, dict)
                ],
                hide_index=True,
            )
            if promoter_gap_review.get("total_rows_available", 0) > len(promoter_gap_review.get("rows") or []):
                st.caption(
                    "Additional queued promoter items not shown in this preview: "
                    f"{promoter_gap_review.get('total_rows_available', 0) - len(promoter_gap_review.get('rows') or [])}"
                )

    asset_snapshot = report.get("component_library_asset_readback_snapshot") or {}
    asset_summary = asset_snapshot.get("summary") or {}
    with st.expander("Component Library Asset Readback Report Snapshot", expanded=False):
        st.caption(
            "Read-only Component Library asset readback snapshot for Project Review Report output."
        )
        st.caption(
            str(
                asset_snapshot.get("presenter_reuse_note")
                or "Reuses the generic Component Library asset readback presenter."
            )
        )
        for note in asset_snapshot.get("boundary_notes") or []:
            st.caption(f"- {note}")

        a1, a2, a3 = st.columns(3, gap="small")
        a1.metric("asset rows", asset_summary.get("total_asset_rows", 0))
        a2.metric("asset types", asset_summary.get("asset_type_count", 0))
        a3.metric(
            "source/provenance rows",
            asset_summary.get("rows_with_source_provenance_identity", 0),
        )
        st.caption(
            "Review next rows: "
            f"{asset_summary.get('rows_with_next_documentation_review_action', 0)}"
        )

        if not asset_snapshot.get("rows"):
            st.info(
                str(
                    asset_snapshot.get("empty_state_message")
                    or "No Component Library asset metadata is available for generic readback."
                )
            )
        else:
            st.dataframe(asset_snapshot.get("rows") or [], hide_index=True)
            if asset_snapshot.get("total_rows_available", 0) > len(asset_snapshot.get("rows") or []):
                st.caption(
                    "Additional Component Library asset readback rows not shown in this preview: "
                    f"{asset_snapshot.get('total_rows_available', 0) - len(asset_snapshot.get('rows') or [])}"
                )

    plant_package = report.get("plant_design_review_package") or {}
    plant_identity = plant_package.get("identity") or {}
    plant_summary = plant_package.get("summary") or {}
    with st.expander("Plant Design Review Package", expanded=True):
        _render_plant_design_review_package_context(plant_package, plant_identity, plant_summary)

        _render_expression_construct_workflow_router_preview_mount(project)

        construct_summary = build_expression_construct_review_decision_summary(
            report.get("expression_construct_documentation")
        )
        st.markdown("**Documentation review summary**")
        st.caption(
            "Review-only construct documentation summary for the current Plant Design Review Package surface. "
            "It summarizes already recorded review payloads and does not make biological recommendations or "
            "build-ready judgments."
        )
        s1, s2, s3, s4 = st.columns(4, gap="small")
        s1.metric("review summary status", construct_summary.get("review_summary_status", "Missing documentation"))
        s2.metric("documented slots", construct_summary.get("documented_slots_count", 0))
        s3.metric("missing slots", construct_summary.get("missing_slots_count", 0))
        s4.metric("manual follow-up", construct_summary.get("manual_follow_up_count", 0))
        st.caption(
            "Source/provenance coverage count: "
            f"{construct_summary.get('source_provenance_coverage_count', 0)}"
        )
        st.caption(
            "Coverage label: "
            f"{construct_summary.get('source_provenance_coverage_label', 'Missing documentation')}"
        )
        for note in construct_summary.get("boundary_notes") or []:
            st.caption(f"- {note}")
        for warning in construct_summary.get("warnings") or []:
            st.warning(str(warning))

        action_panel = plant_package.get("review_action_panel") or build_expression_construct_review_action_panel(
            report.get("expression_construct_documentation"),
            construct_summary,
        )
        st.markdown("**Review action panel**")
        st.caption(
            str(
                action_panel.get("panel_note")
                or "Read-only documentation review actions from the current construct review payload."
            )
        )
        st.dataframe(
            [
                {
                    "Action row": row.get("label", ""),
                    "Status": row.get("status", ""),
                    "Count": row.get("count", 0),
                    "Review action": row.get("review_action", ""),
                    "Source": row.get("source", ""),
                    "Boundary": row.get("boundary_note", ""),
                }
                for row in action_panel.get("rows") or []
                if isinstance(row, dict)
            ],
            hide_index=True,
        )
        for note in action_panel.get("boundary_notes") or []:
            st.caption(f"- {note}")

        _render_plant_construct_draft_preview_mount(project)

        _render_plant_user_context_preview(project)

        _render_route_decision_matrix_preview(project)

        _render_plant_design_review_package_readback(plant_package)

    construct_section = report["expression_construct_documentation"]
    with st.expander("Expression construct documentation", expanded=False):
        st.caption(EXPRESSION_CONSTRUCT_SECTION_COPY)
        st.caption(
            "Documentation-only construct, cassette, part, linked gene, linked pathway step, promoter source-link, "
            "and review gap context."
        )
        st.caption(
            "Construct component readback records documented component labels, categories, source/reference context, "
            "sequence availability status, and metadata gaps only. It is not validation, selection advice, or a downstream-use state decision."
        )
        st.caption(f"Project-scoped filtering: {construct_section.get('project_scoped_filtering') or 'NOT_AVAILABLE'}")
        if construct_section.get("message"):
            st.caption(construct_section["message"])
        supported_vocabulary = construct_section.get("supported_component_vocabulary") or []
        if supported_vocabulary:
            st.caption(
                "Supported documented component vocabulary: "
                + ", ".join(str(item) for item in supported_vocabulary)
            )
        if construct_section.get("construct_component_rows"):
            st.dataframe(
                [
                    {
                        "Component label": row.get("component_label", ""),
                        "Component category": row.get("component_category", ""),
                        "Source/reference": row.get("component_reference_label", ""),
                        "Sequence availability": row.get("sequence_availability_status", ""),
                        "Metadata review status": row.get("review_metadata_status", ""),
                        "Review note": row.get("review_note", ""),
                    }
                    for row in construct_section.get("construct_component_rows") or []
                    if isinstance(row, dict)
                ],
                hide_index=True,
            )
        else:
            st.info("No construct component documentation rows are recorded for this report.")
        for note in construct_section.get("boundary_notes") or []:
            st.caption(f"- {note}")

    with st.expander("Markdown preview", expanded=False):
        st.markdown(report["markdown"])

    st.markdown("**Detailed documentation report draft**")
    st.caption(
        "Documentation report draft for the research to catalog to design to review to report workflow. "
        "It includes provenance context, traceability summary, data completeness review, human review questions, "
        "known limitations, and a documentation-only boundary note."
    )
    _render_readability_note(
        "Documentation report draft for the research to catalog to design to review to report workflow. "
        "It includes provenance context, traceability summary, data completeness review, human review questions, "
        "known limitations, and a documentation-only boundary note."
    )
    st.caption("Human review required; source review needed for draft research and catalog context.")
    research_context = detailed_draft["research_context"]
    catalog_context = detailed_draft["catalog_context"]
    traceability = detailed_draft["traceability_summary"]
    d1, d2, d3 = st.columns(3, gap="small")
    with d1:
        st.metric("Catalog records", catalog_context.get("record_count", 0))
    with d2:
        st.metric("Source review needed", catalog_context.get("source_review_needed", 0))
    with d3:
        st.metric("Traceability records", traceability.get("pathway_step_count", 0) + traceability.get("linked_artifact_count", 0))

    with st.expander("Detailed documentation report draft preview", expanded=True):
        st.caption(f"Research context source mode: {research_context.get('source_mode') or 'NOT_AVAILABLE'}")
        st.caption(detailed_draft["documentation_only_boundary_note"])
        st.markdown(detailed_draft["markdown"])

    st.download_button(
        "Download Project Review Report (.md)",
        data=report["markdown"],
        file_name=_safe_project_review_report_filename(project),
        mime="text/markdown",
        use_container_width=True,
    )
    st.download_button(
        "Download Detailed Documentation Report Draft (.md)",
        data=detailed_draft["markdown"],
        file_name=_safe_detailed_report_draft_filename(project),
        mime="text/markdown",
        use_container_width=True,
    )
