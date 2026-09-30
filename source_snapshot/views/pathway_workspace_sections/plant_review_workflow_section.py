from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable

import streamlit as st

from services.plant_goal_review_package_mvp import build_plant_goal_review_package_mvp
from services.plant_simple_wizard_homepage_presenter import (
    build_simple_plant_wizard_homepage_presenter,
)
from services.plant_simple_wizard_intake_form_presenter import (
    build_simple_plant_wizard_intake_form_presenter,
)
from services.plant_simple_wizard_intent_intake_presenter import (
    build_simple_plant_wizard_intent_intake_presenter,
)
from services.plant_simple_wizard_package_entry_presenter import (
    build_simple_plant_wizard_package_entry_presenter,
)
from services.plant_simple_wizard_route_confirmation_presenter import (
    build_simple_plant_wizard_route_confirmation_presenter,
)
from services.plant_simple_wizard_route_checklist_presenter import (
    build_simple_plant_wizard_route_checklist_presenter,
)
from services.simple_plant_wizard_ui_surface_registry import SIMPLE_PLANT_WIZARD_RUNTIME_MARKER
from services.plant_project_draft_controller import (
    ACTIVE_PLANT_PROJECT_DIRTY_KEY,
    ACTIVE_PLANT_PROJECT_SAVE_STATE_KEY,
    PlantProjectDraftController,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.plant_project_draft_schema import (
    CONSTRUCT_SLOT_LABELS,
    REQUIRED_CONSTRUCT_SLOT_KEYS,
    PlantDesignProjectDraft,
    build_plant_project_draft_completeness,
)
from services.plant_manual_evidence_review_queue_presenter import (
    present_manual_evidence_review_queue,
)
from services.plant_manual_evidence_input_adapter import (
    build_manual_evidence_input_adapter_payload,
    manual_evidence_queue_payload_from_project_input,
)
from services.plant_manual_evidence_package_readback import (
    build_manual_evidence_package_readback,
)
from services.plant_manual_evidence_gap_assistant import (
    build_manual_evidence_gap_assistant,
)
from services.plant_candidate_route_review_draft import build_candidate_route_review_draft
from services.plant_construct_task_readback_gate import build_construct_task_readback_gate
from services.plant_review_handoff_data_adapter import build_plant_review_handoff_payload
from services.plant_review_package_readback_presenter import (
    build_plant_review_package_readback_presenter,
)
from services.plant_review_readback_helpers import (
    coerce_list,
    coerce_mapping,
    coerce_text,
    first_text,
    readback_list,
    readback_summary,
    status_label,
)
from services.plant_review_slot_coverage_matrix import build_plant_review_slot_coverage_matrix
from services.plant_review_workspace_workflow_orchestrator import build_plant_review_workspace_workflow
from views.pathway_workspace_sections.plant_review_handoff_preview_section import (
    render_plant_review_handoff_preview_section,
    render_rice_albumin_seed_review_visible_mount,
)
from views.pathway_workspace_sections.responsive_review_tables import (
    render_responsive_detail_table,
    render_wrapped_summary_cards,
)


PLANT_REVIEW_WORKFLOW_BOUNDARY_COPY = (
    "Read-only Plant Review Workflow for documentation-only manual review. It organizes route, evidence, "
    "component, gap, package, and traceability context without biological recommendation, experiment confirmation "
    "claim, route improvement claim, sequence generation, export action, or wet-lab readiness judgment."
)
MANUAL_EVIDENCE_REVIEW_QUEUE_BOUNDARY_COPY = (
    "Manual Evidence Review Queue is preflight/readback only. It does not import evidence, approve evidence, "
    "confirm source status, permit package draft completion, permit package export, or make biological "
    "recommendations."
)
MANUAL_EVIDENCE_PREFLIGHT_PAYLOAD_KEYS = (
    "manual_evidence_review_queue_payload",
    "manual_evidence_review_queue_readback",
    "manual_evidence_preflight_payload",
    "manual_evidence_preflight_result",
    "manual_evidence_preflight_batch",
    "manual_evidence_preflight_records",
    "r193_manual_evidence_preflight_payload",
)
SIMPLE_PLANT_WIZARD_BEGINNER_GUIDANCE_COPY = (
    "本工具只用于实验前设计审查和资料整理，结果需要人工复核。"
)
SIMPLE_PLANT_DESIGN_WIZARD_TITLE = "我们要帮你审查什么植物设计？"
SIMPLE_PLANT_DESIGN_WIZARD_SUBTITLE = (
    "用一句话描述目标，系统会先判断路线，再告诉你还缺哪些信息。"
)
SIMPLE_PLANT_WIZARD_ADVANCED_MODE_LABEL = "显示高级审查内容"
SIMPLE_PLANT_WIZARD_ADVANCED_MODE_NOTE = (
    "审查员模式仅用于查看保留的详细审查内容；不会改变上方输入和结果。"
)
SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY = "simple_plant_wizard_show_advanced_review_details"
SIMPLE_PLANT_WIZARD_ADVANCED_EXPANDER_LABEL = "高级审查内容"
PLANT_REVIEW_ADVANCED_DETAIL_EXPANDER_LABEL = "Plant Review detail readbacks"
PLANT_REVIEW_READBACK_EXPANDER_LABEL = "审查员 / 开发者 readback 信息"
PLANT_REVIEW_PROOF_PATH_EXPANDER_LABEL = "现有审查包 proof path"
SIMPLE_PLANT_WIZARD_GOAL_TEXT_KEY = "r180_simple_plant_wizard_goal_text"
SIMPLE_PLANT_WIZARD_SELECTED_GOAL_TYPE_KEY = "r180_simple_plant_wizard_selected_goal_type"
SIMPLE_PLANT_WIZARD_ANALYZED_KEY = "r180_simple_plant_wizard_analyzed"
SIMPLE_PLANT_WIZARD_ANALYZED_GOAL_TEXT_KEY = "r180_simple_plant_wizard_analyzed_goal_text"
SIMPLE_PLANT_WIZARD_CONFIRMED_KEY = "r180_simple_plant_wizard_confirmed"
SIMPLE_PLANT_WIZARD_ROUTE_ID_KEY = "r180_simple_plant_wizard_route_id"
SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY = "r205_simple_plant_wizard_project_draft"
R224_PLANT_PROJECT_DRAFT_SECTION_TITLE = "Plant design project drafts / Local saved drafts"
R224_PLANT_PROJECT_DRAFT_BOUNDARY_COPY = (
    "Editable local plant design project drafts are documentation-only user data. They record manual design notes, "
    "source/provenance references, and review gaps without automatic biological design, sequence generation, "
    "prediction, validation, optimization, lab instruction output, or downstream use judgment."
)
R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX = "r224_plant_project_draft"
R206_DESIGN_SLOT_COMPLETION_SCHEMA_VERSION = "v2.7-r206"
R206_REQUIRED_DESIGN_SLOT_PANEL_TITLE = "Required Design Information / 设计资料补齐"
R206_REQUIRED_DESIGN_SLOT_BOUNDARY_COPY = (
    "Documentation-only design slot completion for the current session project draft. "
    "Entries are manual review notes; this panel does not choose components, claim source status, "
    "create records, allow package output, or judge downstream use."
)
R207_PROJECT_REVIEW_COMPLETION_GATE_SCHEMA_VERSION = "v2.7-r207"
R207_PROJECT_REVIEW_COMPLETION_GATE_TITLE = "Project Review Completion / 项目审查完成度"
R207_PROJECT_REVIEW_COMPLETION_GATE_BOUNDARY_COPY = (
    "Documentation-only, readback-only completion checklist for the current Plant Review session. It combines route, "
    "required design slots, manual evidence, gap, and package/handoff status without changing records, "
    "checking sources, enabling package output, or judging biological use."
)
R208_GUIDED_WORKFLOW_DETAIL_TITLE = PLANT_REVIEW_ADVANCED_DETAIL_EXPANDER_LABEL
R208_PACKAGE_HANDOFF_ENTRY_TITLE = "Package / Handoff readback entry points"
R208_PACKAGE_HANDOFF_ENTRY_HELPER = (
    "Open these readback areas after reviewing the current draft, completion status, required design information, "
    "and manual evidence. They remain documentation-only and do not change project records."
)
R206_REQUIRED_DESIGN_SLOT_FIELDS: tuple[dict[str, str], ...] = (
    {"slot_key": "target_protein", "label": "Target protein", "widget": "text_input", "required": "yes"},
    {"slot_key": "target_gene_or_cds", "label": "Target gene or CDS", "widget": "text_input", "required": "yes"},
    {"slot_key": "host_plant", "label": "Host plant", "widget": "text_input", "required": "yes"},
    {"slot_key": "expression_context", "label": "Expression context", "widget": "text_area", "required": "yes"},
    {
        "slot_key": "promoter_or_regulatory_element",
        "label": "Promoter or regulatory element",
        "widget": "text_input",
        "required": "yes",
    },
    {"slot_key": "terminator", "label": "Terminator", "widget": "text_input", "required": "yes"},
    {"slot_key": "marker_or_reporter", "label": "Marker or reporter", "widget": "text_input", "required": "yes"},
    {"slot_key": "vector_or_backbone", "label": "Vector or backbone", "widget": "text_input", "required": "yes"},
    {"slot_key": "notes", "label": "Notes", "widget": "text_area", "required": "no"},
)
SIMPLE_PLANT_WIZARD_CONFIRM_ROUTE_LABEL = "确认路线并进入资料补齐"
R203_MANUAL_EVIDENCE_ENTRY_KEYS = {
    "evidence_label": "r203_manual_evidence_label",
    "source_note": "r203_manual_source_note",
    "evidence_type": "r203_manual_evidence_type",
    "review_note": "r203_manual_review_note",
    "traceability_label": "r203_manual_traceability_label",
    "beginner_preview": "r203_manual_beginner_preview",
    "demo_example": "r203_manual_demo_example",
    "conflict_deprecated": "r203_manual_conflict_deprecated",
}
R203_MANUAL_EVIDENCE_TYPES = (
    "evidence_note",
    "source_note",
    "literature_note",
    "manual_review_note",
    "curator_note",
)
DEFAULT_PLANT_GOAL_REVIEW_PACKAGE_GOAL = (
    "Review a rice albumin-like protein expression design in a plant system."
)
PLANT_GOAL_REVIEW_PACKAGE_GOAL_OPTIONS: tuple[tuple[str, str, str | None], ...] = (
    ("Rice albumin-like plant MVP goal", DEFAULT_PLANT_GOAL_REVIEW_PACKAGE_GOAL, "rice_albumin"),
    ("Unsupported non-plant example", "Review an E. coli protein expression design.", "rice_albumin"),
    ("Unsupported plant dataset example", "Review an Artemisia annua plant design.", "artemisia_annua"),
)


def _text(value: Any) -> str:
    return coerce_text(value)


def _mapping(value: Any) -> dict[str, Any]:
    return coerce_mapping(value)


def _list(value: Any) -> list[Any]:
    return coerce_list(value)


def _first_text(*values: Any) -> str:
    return first_text(*values)


def _status_label(value: Any) -> str:
    return status_label(value)


def _st_button(streamlit_module: Any, *args: Any, **kwargs: Any) -> bool:
    return bool(getattr(streamlit_module, "button")(*args, **kwargs))


def _slot_values_from_plant_project_draft(draft: PlantDesignProjectDraft) -> dict[str, str]:
    return {slot.slot_key: slot.component_name for slot in draft.construct_slots}


def _plant_project_draft_to_simple_project_draft_payload(draft: PlantDesignProjectDraft) -> dict[str, Any]:
    completeness = build_plant_project_draft_completeness(draft)
    slot_values = _slot_values_from_plant_project_draft(draft)
    missing_required_fields = [
        {
            "slot_id": field,
            "slot_label_en": CONSTRUCT_SLOT_LABELS.get(field, field.replace("_", " ").title()),
            "status": "missing" if field in completeness["missing_fields"] else "documented_for_manual_review",
            "status_label_zh": "manual documentation needed"
            if field in completeness["missing_fields"]
            else "manual documentation entered",
            "evidence_status": "manual review required",
            "manual_review_status": "review-required",
            "next_action_label_zh": completeness["next_action"],
        }
        for field in completeness["missing_fields"]
    ]
    payload = {
        "draft_schema_version": "v2.7-r224-adapted",
        "draft_id": draft.project_id,
        "project_id": draft.project_id,
        "project_name": draft.project_name,
        "draft_status": draft.draft_status,
        "record_origin": draft.record_origin,
        "documentation_only": True,
        "manual_review_required": True,
        "goal_description": draft.plant_design_goal,
        "interpreted_goal": draft.plant_design_goal,
        "selected_route": {
            "route_id": "user_plant_design_project_draft",
            "label_zh": "User plant design project draft",
            "label_en": "User plant design project draft",
            "result_label_zh": "User plant design project draft",
        },
        "confidence_readback": {
            "confidence": "not_applicable",
            "confidence_label_zh": "Manual user draft",
            "confidence_reason_zh": "Persisted user-entered project data; no automatic route decision is made.",
            "match_reasons_zh": [],
        },
        "missing_required_fields": missing_required_fields,
        "missing_information_checklist": [],
        "gap_summary": {
            "missing_fields": {"count": len(completeness["missing_fields"]), "slot_ids": completeness["missing_fields"]}
        },
        "route_checklist_completion_summary": completeness,
        "next_step": {
            "label": "Continue editing the saved local plant design project draft",
            "target_surfaces": ["Plant design project drafts", "Plant Expression Workspace"],
            "readback": completeness["next_action"],
        },
        "boundary_note": R224_PLANT_PROJECT_DRAFT_BOUNDARY_COPY,
    }
    for key, value in slot_values.items():
        payload[key] = value
    payload["host_plant"] = draft.host_context
    payload["expression_context"] = draft.expression_context
    payload["design_slot_completion"] = build_required_design_slot_completion_payload(
        project_draft_payload=payload,
        slot_values=slot_values,
    )
    payload["design_slot_completion_summary"] = payload["design_slot_completion"]["completion_summary"]
    return payload


def _sync_active_plant_project_draft_to_session(
    draft: PlantDesignProjectDraft | None,
    *,
    streamlit_module: Any = st,
) -> dict[str, Any]:
    if draft is None:
        return {}
    payload = _plant_project_draft_to_simple_project_draft_payload(draft)
    getattr(streamlit_module, "session_state", {})[SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY] = payload
    return payload


def _reset_simple_plant_wizard_analysis_state(streamlit_module: Any = st) -> None:
    session_state = getattr(streamlit_module, "session_state", {})
    session_state[SIMPLE_PLANT_WIZARD_ANALYZED_KEY] = False
    session_state[SIMPLE_PLANT_WIZARD_CONFIRMED_KEY] = False
    session_state.pop(SIMPLE_PLANT_WIZARD_ANALYZED_GOAL_TEXT_KEY, None)
    session_state.pop(SIMPLE_PLANT_WIZARD_ROUTE_ID_KEY, None)
    session_state.pop(SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY, None)


def _advanced_mode_already_requested(streamlit_module: Any = st) -> bool:
    if bool(getattr(streamlit_module, "session_state", {}).get(SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY)):
        return True
    return bool(getattr(streamlit_module, "checkbox_values", {}).get(SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY))


def _project_workspace_state(
    project: Mapping[str, Any] | None,
    steps: Sequence[Mapping[str, Any]] | None,
    expression_links: Sequence[Mapping[str, Any]] | None,
    test_records: Sequence[Mapping[str, Any]] | None,
    review_signals: Sequence[Mapping[str, Any]] | None,
    project_draft: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    project_data = _mapping(project)
    step_rows = [dict(step) for step in steps or [] if isinstance(step, Mapping)]
    expression_link_rows = [dict(link) for link in expression_links or [] if isinstance(link, Mapping)]
    test_rows = [dict(record) for record in test_records or [] if isinstance(record, Mapping)]
    signal_rows = [dict(signal) for signal in review_signals or [] if isinstance(signal, Mapping)]

    component_records: list[dict[str, Any]] = []
    for index, step in enumerate(step_rows, start=1):
        component_name = _first_text(step.get("gene_name"), step.get("enzyme_name"), step.get("step_name"))
        if not component_name:
            continue
        component_records.append(
            {
                "component_id": _first_text(step.get("id"), f"pathway-step-{index}"),
                "component_name": component_name,
                "component_type": "pathway_step_component_context",
                "source_label": _first_text(step.get("organism_source"), "pathway step record"),
                "provenance_note": _first_text(step.get("notes"), step.get("reaction_name")),
            }
        )

    evidence_records: list[dict[str, Any]] = []
    for index, record in enumerate(test_rows + signal_rows + expression_link_rows, start=1):
        evidence_records.append(
            {
                "id": _first_text(record.get("id"), record.get("record_id"), f"workspace-evidence-{index}"),
                "paper_title": _first_text(
                    record.get("test_name"),
                    record.get("signal_label"),
                    record.get("linked_design_name"),
                    record.get("title"),
                    "Local workspace review record",
                ),
                "summary": _first_text(record.get("notes"), record.get("summary"), record.get("source_context")),
                "source_label": "local workspace record",
            }
        )

    workspace_state = {
        "project_id": _first_text(project_data.get("id"), project_data.get("project_id")),
        "project_name": _first_text(project_data.get("name"), project_data.get("project_name")),
        "design_goal": _first_text(
            project_data.get("description"),
            project_data.get("goal"),
            project_data.get("target_product"),
            "Document Plant expression vector review route.",
        ),
        "target_product": _first_text(project_data.get("target_product"), project_data.get("product")),
        "target_gene": _first_text(project_data.get("target_gene"), project_data.get("gene_name")),
        "host_plant": _first_text(project_data.get("host"), project_data.get("host_plant"), project_data.get("plant_host")),
        "expression_context": _first_text(project_data.get("expression_context"), project_data.get("plant_context")),
        "route_hint": "plant expression vector review",
        "construct_slots": {
            "documented_step_count": len(step_rows),
            "linked_design_count": len(expression_link_rows),
        },
        "component_records": component_records,
        "evidence_records": evidence_records,
        "notes": _first_text(project_data.get("notes")),
        "user_context": {
            "workspace_surface": "Pathway Workspace Plant Review tab",
            "documentation_only": True,
        },
    }
    draft = _mapping(project_draft)
    if draft:
        selected_route = _mapping(draft.get("selected_route"))
        workspace_state["design_goal"] = _first_text(draft.get("goal_description"), workspace_state["design_goal"])
        workspace_state["route_hint"] = _first_text(
            selected_route.get("route_id"),
            selected_route.get("label_en"),
            workspace_state["route_hint"],
        )
        workspace_state["simple_plant_wizard_project_draft"] = draft
        workspace_state["design_slot_completion"] = _mapping(draft.get("design_slot_completion"))
        workspace_state["design_slot_completion_summary"] = _mapping(draft.get("design_slot_completion_summary"))
        workspace_state["user_context"]["simple_plant_wizard_project_draft"] = True
        workspace_state["user_context"]["simple_plant_wizard_route_id"] = _text(selected_route.get("route_id"))
    return workspace_state


def _summary_metric_rows(workflow: Mapping[str, Any]) -> list[tuple[str, str, str]]:
    handoff = _mapping(workflow.get("handoff_preview_payload"))
    chain = _mapping(workflow.get("chain_result"))
    package = _mapping(chain.get("plant_review_package"))
    return [
        ("Workflow status", _status_label(workflow.get("workflow_status")), "R83 workspace workflow status"),
        ("Package status", _status_label(package.get("package_status")), "Read-only review package status"),
        ("Manual review", "yes" if workflow.get("manual_review_required") else "no", "Manual review flag"),
        ("Handoff preview", _status_label(handoff.get("handoff_status")), "Read-only handoff preview status"),
    ]


def _summary_status_cards(workflow: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {"label": label, "value": value, "note": help_text}
        for label, value, help_text in _summary_metric_rows(workflow)
    ]


def _review_map_cards(workflow: Mapping[str, Any], slot_matrix: Mapping[str, Any]) -> list[dict[str, str]]:
    handoff = _mapping(workflow.get("handoff_preview_payload"))
    queue_rows = _gap_rows(workflow)
    seed_note = "Rice albumin seed review mount appears after the handoff/provenance summary."
    return [
        {
            "label": "Seed review",
            "value": "local seed-data review",
            "note": seed_note,
        },
        {
            "label": "Provenance verification",
            "value": "manual review readback",
            "note": "Source/accession gaps stay visible and no identifiers are filled.",
        },
        {
            "label": "Manual verification queue",
            "value": f"{len(queue_rows)} workspace gap row(s)",
            "note": "R146 provenance queue details remain sourced from the queue service.",
        },
        {
            "label": "Route-to-construct traceability",
            "value": "slot matrix context",
            "note": f"Matrix status: {_status_label(slot_matrix.get('matrix_status'))}; detail is grouped below.",
        },
        {
            "label": "Handoff readback",
            "value": _status_label(handoff.get("handoff_status")),
            "note": "Review items and readback tables remain read-only detail.",
        },
    ]


def _route_summary_rows(workflow: Mapping[str, Any]) -> list[dict[str, str]]:
    chain = _mapping(workflow.get("chain_result"))
    package = _mapping(chain.get("plant_review_package"))
    route_summary = _mapping(package.get("route_summary"))
    route_draft = _mapping(chain.get("route_draft"))
    return [
        {"Field": "Route id", "Readback": _first_text(route_summary.get("route_id"), route_draft.get("route_id"))},
        {"Field": "Route label", "Readback": _first_text(route_summary.get("route_label"), route_draft.get("route_name"))},
        {"Field": "Route type", "Readback": _first_text(route_summary.get("route_type"), route_draft.get("route_type"))},
        {"Field": "Route status", "Readback": _status_label(route_draft.get("draft_status"))},
    ]


def _slot_rows(workflow: Mapping[str, Any]) -> list[dict[str, Any]]:
    package = _mapping(_mapping(workflow.get("chain_result")).get("plant_review_package"))
    summary = _mapping(package.get("construct_slot_summary"))
    rows: list[dict[str, Any]] = []
    for slot in _list(summary.get("slots")):
        if not isinstance(slot, Mapping):
            continue
        rows.append(
            {
                "Slot id": _text(slot.get("slot_id")),
                "Slot label": _text(slot.get("slot_label")),
                "Required": "yes" if slot.get("required") else "no",
                "Evidence count": len(_list(slot.get("evidence_ids"))),
                "Component count": len(_list(slot.get("component_ids"))),
                "Gap flags": ", ".join(_text(value) for value in _list(slot.get("slot_status")) if _text(value)),
                "Manual review": "yes" if slot.get("missing_required_slot") else "review context",
            }
        )
    return rows


def _slot_coverage_matrix_rows(slot_matrix: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _list(slot_matrix.get("rows")):
        if not isinstance(row, Mapping):
            continue
        gap_flags = [
            label
            for flag, label in (
                ("evidence_gap", "evidence gap"),
                ("component_gap", "component gap"),
                ("provenance_gap", "provenance gap"),
                ("duplicate_or_alias_review", "duplicate/alias review"),
            )
            if row.get(flag)
        ]
        rows.append(
            {
                "Slot id": _text(row.get("slot_id")),
                "Slot label": _text(row.get("slot_label")),
                "Required / optional": _status_label(row.get("required_or_optional")),
                "Evidence count": row.get("evidence_count", 0),
                "Component count": row.get("component_count", 0),
                "Gap flags": ", ".join(gap_flags) or "none recorded",
                "Manual review": "yes" if row.get("manual_review_required") else "no",
                "Traceability ids": ", ".join(_list(row.get("traceability_ids"))),
            }
        )
    return rows


def _evidence_rows(workflow: Mapping[str, Any]) -> list[dict[str, Any]]:
    adapter_input = _mapping(workflow.get("adapter_input"))
    rows = []
    for record in _list(adapter_input.get("evidence_records")):
        if isinstance(record, Mapping):
            rows.append(
                {
                    "Evidence id": _first_text(record.get("id"), record.get("source_id")),
                    "Label": _first_text(record.get("paper_title"), record.get("title"), record.get("source_label")),
                    "Source key": _text(record.get("workspace_source_key")),
                }
            )
    return rows


def _component_rows(workflow: Mapping[str, Any]) -> list[dict[str, Any]]:
    adapter_input = _mapping(workflow.get("adapter_input"))
    rows = []
    for record in _list(adapter_input.get("component_records")):
        if isinstance(record, Mapping):
            rows.append(
                {
                    "Component id": _first_text(record.get("component_id"), record.get("asset_id")),
                    "Label": _first_text(record.get("component_name"), record.get("asset_label")),
                    "Type": _text(record.get("component_type")),
                    "Source key": _text(record.get("workspace_source_key")),
                }
            )
    return rows


def _gap_rows(workflow: Mapping[str, Any]) -> list[dict[str, Any]]:
    handoff = _mapping(workflow.get("handoff_preview_payload"))
    rows: list[dict[str, Any]] = []
    for item in _list(handoff.get("missing_information_items") or handoff.get("required_review_items")):
        if isinstance(item, Mapping):
            rows.append(
                {
                    "Item": _first_text(item.get("item_id"), item.get("title")),
                    "Category": _text(item.get("category")),
                    "Slot": _text(item.get("slot_id")),
                    "Reason": _first_text(item.get("reason"), item.get("reviewer_action_hint")),
                }
            )
    return rows


def _traceability_rows(workflow: Mapping[str, Any]) -> list[dict[str, str]]:
    traceability = _mapping(workflow.get("traceability"))
    upstream = _mapping(traceability.get("upstream_statuses"))
    adapter = _mapping(traceability.get("adapter_traceability"))
    extractor = _mapping(traceability.get("extractor_traceability"))
    return [
        {"Traceability": "Extractor", "Readback": _status_label(upstream.get("extractor"))},
        {"Traceability": "Adapter", "Readback": _status_label(upstream.get("adapter"))},
        {"Traceability": "Chain", "Readback": _status_label(upstream.get("chain"))},
        {"Traceability": "Handoff", "Readback": _status_label(upstream.get("handoff"))},
        {"Traceability": "Evidence ids", "Readback": ", ".join(_list(adapter.get("evidence_record_ids")))},
        {"Traceability": "Component ids", "Readback": ", ".join(_list(adapter.get("component_record_ids")))},
        {"Traceability": "Source keys", "Readback": ", ".join(_list(extractor.get("source_keys_used")))},
    ]


def _is_manual_evidence_queue_payload(value: Any) -> bool:
    value_map = _mapping(value)
    return isinstance(value_map.get("rows"), list) and isinstance(value_map.get("summary"), Mapping)


def _manual_evidence_queue_payload_from_any(
    payload: Any,
    build_presenter: Callable[[Any], dict[str, Any]] = present_manual_evidence_review_queue,
) -> dict[str, Any]:
    if _is_manual_evidence_queue_payload(payload):
        return _mapping(payload)
    return build_presenter(payload)


def _manual_evidence_payload_context(
    *,
    manual_evidence_panel_payload: Mapping[str, Any] | None = None,
    workflow: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    panel_payload = _mapping(manual_evidence_panel_payload)
    workflow_data = _mapping(workflow)
    queue_payload = _mapping(panel_payload.get("queue_payload"))
    if not queue_payload:
        queue_payload = _manual_evidence_queue_payload_from_any(
            _find_manual_evidence_preflight_payload(workflow_data)
        )
    gap_payload = _mapping(panel_payload.get("gap_assistant_payload"))
    if not gap_payload:
        gap_payload = build_manual_evidence_gap_assistant(queue_payload)
    return {
        "panel_payload": panel_payload,
        "panel_record": _mapping(panel_payload.get("panel_record")),
        "queue_payload": queue_payload,
        "queue_counts": _r207_queue_counts(queue_payload),
        "gap_payload": gap_payload,
    }


def _r203_panel_has_draft_text(record: Mapping[str, Any]) -> bool:
    return any(
        _text(record.get(field))
        for field in (
            "evidence_label",
            "source_note",
            "review_note",
            "traceability_label",
        )
    )


def build_manual_evidence_entry_panel_payload(
    record: Mapping[str, Any] | None,
    *,
    project: Mapping[str, Any] | None = None,
    workflow: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the R202/R193/R196/R200 preview payload for one panel draft."""

    record_data = _mapping(record)
    project_data = _mapping(project)
    workflow_data = _mapping(workflow)
    manual_records: list[dict[str, Any]] = []
    if _r203_panel_has_draft_text(record_data):
        beginner_preview = bool(record_data.get("beginner_preview"))
        demo_example = bool(record_data.get("demo_example"))
        conflict_deprecated = bool(record_data.get("conflict_deprecated"))
        source_note = _text(record_data.get("source_note"))
        evidence_label = _first_text(record_data.get("evidence_label"), "Manual evidence preview draft")
        manual_records.append(
            {
                "record_id": "R203_PANEL_MANUAL_EVIDENCE_DRAFT",
                "evidence_label": evidence_label,
                "source_note": source_note,
                "route_scope": _first_text(
                    workflow_data.get("route_id"),
                    project_data.get("route_scope"),
                    "plant_protein_expression_review",
                ),
                "evidence_type": _first_text(record_data.get("evidence_type"), "evidence_note"),
                "manual_review_status": "needs_manual_review",
                "readback_state": "preview_only" if beginner_preview else "",
                "allowed_usage_scope": "beginner_preview"
                if beginner_preview
                else "demo_only"
                if demo_example
                else "manual_review_only",
                "demo_or_real_flag": "demo_example" if demo_example or beginner_preview else "user_supplied_unverified",
                "record_status": "demo_example" if demo_example else "",
                "provenance_status": "demo_only" if demo_example or beginner_preview else "source_present_needs_review",
                "conflict_status": "unresolved" if conflict_deprecated else "no_known_conflict",
                "deprecated_flag": conflict_deprecated,
                "review_note": _text(record_data.get("review_note")),
                "traceability_label": _text(record_data.get("traceability_label")),
                "manual_evidence": True,
            }
        )

    adapted = build_manual_evidence_input_adapter_payload(
        {
            "project_id": _first_text(project_data.get("project_id"), project_data.get("id"), "R203_PANEL_PROJECT"),
            "workflow_id": _first_text(workflow_data.get("workflow_id"), "R203_PANEL_WORKFLOW"),
            "manual_evidence_records": manual_records,
        }
    )
    package_readback = build_manual_evidence_package_readback(adapted)
    gap_assistant = build_manual_evidence_gap_assistant(adapted)
    presenter = build_plant_review_package_readback_presenter(
        {
            "package_id": "R203_PANEL_READBACK_PACKAGE",
            "package_schema_version": "plant_review_package.r203.panel_preview",
            "package_type": "plant_review_package",
            "package_status": "manual_review_required",
            "manual_review_required": True,
            "route_summary": {
                "route_id": "R203_PANEL_ROUTE",
                "route_label": "R203 panel route readback",
                "route_status": "manual_review_required",
            },
            "design_intent_summary": {},
            "module_card_summary": {"modules": []},
            "construct_slot_summary": {"slots": []},
            "evidence_summary": {"slots": []},
            "component_candidate_summary": {"slots": []},
            "gap_manual_review_summary": {"review_required_count": package_readback["summary"]["row_count"]},
            "review_queue": [],
            "traceability": {"route_ids": ["R203_PANEL_ROUTE"]},
            "blocked_output_boundaries": ["manual_review_boundary"],
            "manual_evidence_review_queue_payload": adapted["manual_evidence_review_queue_payload"],
        }
    )
    handoff = build_plant_review_handoff_payload(presenter)
    return {
        "panel_record": dict(record_data),
        "adapter_payload": adapted,
        "queue_payload": adapted["manual_evidence_review_queue_payload"],
        "package_readback": package_readback,
        "gap_assistant_payload": gap_assistant,
        "package_presenter_manual_readback": presenter["manual_evidence_review_queue_section"],
        "handoff_manual_readback": handoff["manual_evidence_review_queue_readback"],
        "read_only": True,
        "display_readback_only": True,
    }


def _manual_evidence_entry_panel_record() -> dict[str, Any]:
    evidence_label = st.text_input(
        "Evidence label",
        value="",
        key=R203_MANUAL_EVIDENCE_ENTRY_KEYS["evidence_label"],
        placeholder="Optional placeholder label for local review",
        help="Label for this local manual evidence draft; keep it placeholder-only.",
    )
    source_note = st.text_area(
        "Source note",
        value="",
        key=R203_MANUAL_EVIDENCE_ENTRY_KEYS["source_note"],
        placeholder="Optional source/provenance note without external identifiers",
        help="Use a short manual source trail note; no lookup or confirmation is performed.",
    )
    evidence_type = st.selectbox(
        "Evidence type",
        R203_MANUAL_EVIDENCE_TYPES,
        index=0,
        key=R203_MANUAL_EVIDENCE_ENTRY_KEYS["evidence_type"],
        help="Safe manual evidence note type for preflight/readback.",
    )
    review_note = st.text_area(
        "Review note",
        value="",
        key=R203_MANUAL_EVIDENCE_ENTRY_KEYS["review_note"],
        placeholder="Optional reviewer note for local documentation review",
        help="Preserved as a manual review note in the preview payload.",
    )
    traceability_label = st.text_input(
        "Traceability label",
        value="",
        key=R203_MANUAL_EVIDENCE_ENTRY_KEYS["traceability_label"],
        placeholder="Optional local traceability label",
        help="Preserved as local traceability context for readback.",
    )
    flag_columns = st.columns(3)
    with flag_columns[0]:
        beginner_preview = st.checkbox(
            "Beginner preview",
            value=False,
            key=R203_MANUAL_EVIDENCE_ENTRY_KEYS["beginner_preview"],
            help="Marks this draft as preview-only context.",
        )
    with flag_columns[1]:
        demo_example = st.checkbox(
            "Demo/example",
            value=False,
            key=R203_MANUAL_EVIDENCE_ENTRY_KEYS["demo_example"],
            help="Keeps this draft blocked for package support.",
        )
    with flag_columns[2]:
        conflict_deprecated = st.checkbox(
            "Conflict/deprecated",
            value=False,
            key=R203_MANUAL_EVIDENCE_ENTRY_KEYS["conflict_deprecated"],
            help="Keeps this draft blocked and visible for manual follow-up.",
        )
    return {
        "evidence_label": evidence_label,
        "source_note": source_note,
        "evidence_type": evidence_type,
        "review_note": review_note,
        "traceability_label": traceability_label,
        "beginner_preview": beginner_preview,
        "demo_example": demo_example,
        "conflict_deprecated": conflict_deprecated,
    }


def _manual_evidence_readback_summary_rows(readback: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = _mapping(readback.get("summary"))
    return [
        {"Field": "Readback status", "Readback": _status_label(readback.get("section_status"))},
        {"Field": "Queue rows", "Readback": summary.get("row_count", 0)},
        {"Field": "Review-needed rows", "Readback": summary.get("review_needed_count", 0)},
        {"Field": "Blocked rows", "Readback": summary.get("blocked_count", 0)},
        {"Field": "Preview-only rows", "Readback": summary.get("preview_only_count", 0)},
        {"Field": "Malformed/empty rows", "Readback": summary.get("malformed_or_empty_count", 0)},
    ]


def _manual_evidence_gap_assistant_rows(assistant_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _list(assistant_payload.get("rows")):
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "Evidence label": _first_text(row.get("evidence_label"), "Manual evidence preflight input"),
                "Queue state": _status_label(row.get("queue_state")),
                "Gap summary": _text(row.get("gap_summary")),
                "State explanation": _text(row.get("state_explanation")),
                "Package support": _text(row.get("package_support_explanation")),
                "Safe next actions": _readback_list(row.get("safe_next_data_completion_actions")),
                "Top blockers": _readback_list(row.get("blocking_reasons_preserved")),
                "Warnings": _readback_list(row.get("warnings_preserved")),
            }
        )
    return rows


def _manual_evidence_gap_assistant_summary_cards(assistant_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    summary = _mapping(assistant_payload.get("summary"))
    counts = _mapping(summary.get("queue_state_counts"))
    return [
        {
            "label": "Assistant rows",
            "value": str(summary.get("row_count", 0)),
            "note": "Rows summarized from manual evidence readback.",
        },
        {
            "label": "Missing fields",
            "value": str(summary.get("missing_field_count", 0)),
            "note": "Data-completion gaps only.",
        },
        {
            "label": "Blocked/preview",
            "value": str(counts.get("blocked", 0) + counts.get("preview_only", 0) + counts.get("malformed_blocked", 0)),
            "note": "Blocked states remain readback-only.",
        },
        {
            "label": "Boundary",
            "value": "documentation-only",
            "note": "No source confirmation or package permission is granted.",
        },
    ]


def render_manual_evidence_gap_assistant_preview(input_payload: Any) -> dict[str, Any]:
    assistant_payload = build_manual_evidence_gap_assistant(input_payload)
    st.markdown("**Manual Evidence Gap Assistant**")
    st.caption(_text(assistant_payload.get("boundary_note")))
    for reason in _list(assistant_payload.get("top_blockers"))[:5]:
        st.caption(f"- {_text(reason)}")
    for warning in _list(assistant_payload.get("top_warnings"))[:5]:
        st.caption(f"- {_text(warning)}")
    render_wrapped_summary_cards(
        st,
        _manual_evidence_gap_assistant_summary_cards(assistant_payload),
        class_suffix="bds-r204-manual-evidence-gap-assistant",
    )
    _render_table(
        "Manual Evidence Gap Assistant",
        _manual_evidence_gap_assistant_rows(assistant_payload),
        _first_text(
            _mapping(assistant_payload.get("empty_state")).get("message"),
            "No manual evidence draft is available; this assistant has no rows to show.",
        ),
    )
    return assistant_payload


def render_manual_evidence_entry_preview_panel(
    *,
    project: Mapping[str, Any] | None,
    workflow: Mapping[str, Any] | None,
) -> dict[str, Any]:
    st.markdown("**Manual Evidence Entry / Preview**")
    st.caption(
        "Enter placeholder/manual evidence draft fields for immediate preflight/readback. "
        "This panel does not write records, import evidence, confirm sources, allow approval, or change package output behavior."
    )
    panel_record = _manual_evidence_entry_panel_record()
    payload = build_manual_evidence_entry_panel_payload(panel_record, project=project, workflow=workflow)
    queue_payload = _mapping(payload.get("queue_payload"))
    package_readback = _mapping(payload.get("package_readback"))
    gap_assistant = _mapping(payload.get("gap_assistant_payload"))

    _render_manual_evidence_queue_readback(
        queue_payload,
        class_suffix="bds-r203-manual-evidence-entry",
        empty_message="No manual evidence draft fields are entered yet; this panel is showing the safe empty readback state.",
    )
    render_manual_evidence_gap_assistant_preview(gap_assistant)
    _render_table(
        "Manual evidence package readback",
        _manual_evidence_readback_summary_rows(package_readback),
        "No manual evidence package readback summary is available.",
    )
    return payload


def _r207_design_slot_completion(project_draft_payload: Mapping[str, Any]) -> dict[str, Any]:
    if not project_draft_payload:
        return {
            "completion_summary": {
                "completed_slots": [],
                "missing_slots": [],
                "completed_slot_count": 0,
                "missing_slot_count": 0,
                "completion_status": "no_current_project_draft",
                "manual_review_required": True,
            },
            "slot_rows": [],
            "boundary_note": R206_REQUIRED_DESIGN_SLOT_BOUNDARY_COPY,
        }
    completion = _mapping(project_draft_payload.get("design_slot_completion"))
    if completion:
        return completion
    return build_required_design_slot_completion_payload(
        project_draft_payload=project_draft_payload,
        slot_values={},
    )


def _r207_queue_counts(queue_payload: Mapping[str, Any]) -> dict[str, int]:
    summary = _mapping(queue_payload.get("summary"))
    counts = _mapping(summary.get("queue_state_counts"))
    blocked_count = int(summary.get("blocked_count") or counts.get("blocked") or 0)
    blocked_count += int(counts.get("malformed_blocked") or 0)
    return {
        "row_count": int(summary.get("row_count") or 0),
        "review_needed_count": int(summary.get("review_needed_count") or counts.get("review_needed") or 0),
        "blocked_count": blocked_count,
        "preview_only_count": int(summary.get("preview_only_count") or counts.get("preview_only") or 0),
    }


def _r207_manual_entry_status(panel_payload: Mapping[str, Any], queue_counts: Mapping[str, int]) -> str:
    record = _mapping(panel_payload.get("panel_record"))
    if int(queue_counts.get("row_count") or 0) <= 0:
        return "safe_empty_manual_evidence_entry"
    if _r203_panel_has_draft_text(record):
        return "manual_evidence_draft_entered_for_readback"
    return "manual_evidence_queue_readback_present"


def _r207_missing_slot_labels(completion_payload: Mapping[str, Any]) -> list[str]:
    missing = set(_list(_mapping(completion_payload.get("completion_summary")).get("missing_slots")))
    labels: list[str] = []
    for row in _list(completion_payload.get("slot_rows")):
        item = _mapping(row)
        slot_key = _text(item.get("slot_key"))
        if slot_key in missing:
            labels.append(_first_text(item.get("slot_label"), slot_key))
    return labels


def _r207_gap_rows(gap_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in _list(gap_payload.get("rows")) if isinstance(row, Mapping)]


def _r207_count_rows_with_missing(rows: Sequence[Mapping[str, Any]], field_name: str) -> int:
    return sum(1 for row in rows if field_name in _list(row.get("missing_fields")))


def _r207_count_rows_with_reason(rows: Sequence[Mapping[str, Any]], needle: str) -> int:
    needle_lower = needle.casefold()
    count = 0
    for row in rows:
        values = [
            *_list(row.get("blocking_reasons_preserved")),
            *_list(row.get("warnings_preserved")),
            _text(row.get("state_explanation")),
            _text(row.get("package_support_explanation")),
        ]
        if any(needle_lower in _text(value).casefold() for value in values):
            count += 1
    return count


def _r207_blocker_rows(
    *,
    completion_payload: Mapping[str, Any],
    queue_counts: Mapping[str, int],
    gap_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    missing_slot_labels = _r207_missing_slot_labels(completion_payload)
    gap_rows = _r207_gap_rows(gap_payload)
    blockers: list[dict[str, Any]] = []
    if missing_slot_labels:
        blockers.append(
            {
                "Type": "missing_required_design_slots",
                "Blocker": "; ".join(missing_slot_labels[:6]),
                "Count": len(missing_slot_labels),
                "Action": "Fill required design information.",
            }
        )
    missing_source_count = _r207_count_rows_with_missing(gap_rows, "source_note")
    if missing_source_count:
        blockers.append(
            {
                "Type": "missing_source_notes",
                "Blocker": "Manual evidence row is missing a source note.",
                "Count": missing_source_count,
                "Action": "Add source note.",
            }
        )
    preview_count = int(queue_counts.get("preview_only_count") or 0)
    if preview_count:
        blockers.append(
            {
                "Type": "preview_only_evidence",
                "Blocker": "Beginner preview/manual evidence row is preview-only.",
                "Count": preview_count,
                "Action": "Review manual evidence gaps.",
            }
        )
    conflict_count = _r207_count_rows_with_reason(gap_rows, "conflict") + _r207_count_rows_with_reason(
        gap_rows,
        "deprecated",
    )
    if conflict_count:
        blockers.append(
            {
                "Type": "conflict_deprecated_markers",
                "Blocker": "Conflict/deprecated marker remains visible.",
                "Count": conflict_count,
                "Action": "Review manual evidence gaps.",
            }
        )
    return blockers


def _r207_safe_next_actions(
    *,
    blocker_rows: Sequence[Mapping[str, Any]],
    completion_payload: Mapping[str, Any],
    gap_payload: Mapping[str, Any],
    panel_missing_evidence_type: bool = False,
) -> list[dict[str, Any]]:
    blocker_types = {_text(row.get("Type")) for row in blocker_rows}
    gap_rows = _r207_gap_rows(gap_payload)
    actions: list[dict[str, Any]] = []
    if _list(_mapping(completion_payload.get("completion_summary")).get("missing_slots")):
        actions.append(
            {
                "Area": "Design slots",
                "Action": "Fill required design information",
                "Reason": "Required session draft slots are blank.",
                "Readback-only": "yes",
            }
        )
    if "missing_source_notes" in blocker_types:
        actions.append(
            {
                "Area": "Manual evidence",
                "Action": "Add source note",
                "Reason": "A manual evidence row has no source note.",
                "Readback-only": "yes",
            }
        )
    if panel_missing_evidence_type or _r207_count_rows_with_missing(gap_rows, "evidence_type"):
        actions.append(
            {
                "Area": "Manual evidence",
                "Action": "Add evidence type",
                "Reason": "A manual evidence row is missing evidence type.",
                "Readback-only": "yes",
            }
        )
    if any(row.get("Type") in {"preview_only_evidence", "conflict_deprecated_markers"} for row in blocker_rows):
        actions.append(
            {
                "Area": "Manual evidence gaps",
                "Action": "Review manual evidence gaps",
                "Reason": "Preview-only or conflict/deprecated readback remains visible.",
                "Readback-only": "yes",
            }
        )
    actions.append(
        {
            "Area": "Package/handoff readback",
            "Action": "Refresh package readback",
            "Reason": "Review the combined readback after session-only edits.",
            "Readback-only": "yes",
        }
    )
    return actions


def _r207_package_handoff_status(
    *,
    workflow: Mapping[str, Any],
    blocker_rows: Sequence[Mapping[str, Any]],
    queue_counts: Mapping[str, int],
    missing_slot_count: int,
) -> str:
    handoff = _mapping(workflow.get("handoff_preview_payload"))
    chain = _mapping(workflow.get("chain_result"))
    package = _mapping(chain.get("plant_review_package"))
    status_values = {
        _text(workflow.get("workflow_status")),
        _text(handoff.get("handoff_status")),
        _text(package.get("package_status")),
    }
    if (
        blocker_rows
        or missing_slot_count
        or int(queue_counts.get("blocked_count") or 0)
        or int(queue_counts.get("preview_only_count") or 0)
        or any(value in {"blocked", "blocked_unsupported"} for value in status_values)
    ):
        return "blocked_readback_only"
    if not workflow:
        return "safe_empty_readback"
    return "manual_review_readback_only"


def _r207_status_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    route = _mapping(payload.get("route_confirmation"))
    slots = _mapping(payload.get("design_slot_completion"))
    evidence = _mapping(payload.get("manual_evidence"))
    package = _mapping(payload.get("package_handoff_readback"))
    return [
        {
            "Checkpoint": "Route confirmation",
            "Status": _status_label(route.get("status")),
            "Readback": _text(route.get("readback")),
            "Next action": _text(route.get("next_action")),
        },
        {
            "Checkpoint": "Required design slots",
            "Status": _status_label(slots.get("status")),
            "Readback": (
                f"{slots.get('completed_slot_count', 0)} completed / "
                f"{slots.get('missing_slot_count', 0)} missing"
            ),
            "Next action": _text(slots.get("next_action")),
        },
        {
            "Checkpoint": "Manual evidence entry",
            "Status": _status_label(evidence.get("entry_status")),
            "Readback": f"{evidence.get('row_count', 0)} row(s) in readback",
            "Next action": _text(evidence.get("next_action")),
        },
        {
            "Checkpoint": "Manual evidence queue",
            "Status": _status_label(evidence.get("queue_status")),
            "Readback": (
                f"review_needed {evidence.get('review_needed_count', 0)} / "
                f"blocked {evidence.get('blocked_count', 0)} / "
                f"preview_only {evidence.get('preview_only_count', 0)}"
            ),
            "Next action": "Review manual evidence gaps.",
        },
        {
            "Checkpoint": "Package/handoff readback",
            "Status": _status_label(package.get("status")),
            "Readback": _text(package.get("readback")),
            "Next action": _text(package.get("next_action")),
        },
    ]


def _r207_summary_cards(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    slots = _mapping(payload.get("design_slot_completion"))
    evidence = _mapping(payload.get("manual_evidence"))
    blockers = _list(payload.get("top_blockers"))
    package = _mapping(payload.get("package_handoff_readback"))
    return [
        {
            "label": "Route",
            "value": _status_label(_mapping(payload.get("route_confirmation")).get("status")),
            "note": "User route confirmation readback only.",
        },
        {
            "label": "Design slots",
            "value": f"{slots.get('completed_slot_count', 0)}/{slots.get('total_required_slot_count', 0)}",
            "note": f"{slots.get('missing_slot_count', 0)} required slot(s) missing.",
        },
        {
            "label": "Manual evidence",
            "value": (
                f"review {evidence.get('review_needed_count', 0)} / "
                f"blocked {evidence.get('blocked_count', 0)} / "
                f"preview {evidence.get('preview_only_count', 0)}"
            ),
            "note": "Manual evidence remains preflight/readback-only.",
        },
        {
            "label": "Top blockers",
            "value": str(len(blockers)),
            "note": _status_label(package.get("status")),
        },
    ]


def build_project_review_completion_gate_payload(
    *,
    project_draft_payload: Mapping[str, Any] | None,
    workflow: Mapping[str, Any] | None = None,
    manual_evidence_panel_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    draft = _mapping(project_draft_payload)
    workflow_data = _mapping(workflow)
    panel_payload = _mapping(manual_evidence_panel_payload)
    selected_route = _mapping(draft.get("selected_route"))
    route_id = _text(selected_route.get("route_id"))
    route_status = "route_confirmed_for_review" if route_id else "no_current_project_draft"
    completion_payload = _r207_design_slot_completion(draft)
    completion_summary = _mapping(completion_payload.get("completion_summary"))
    missing_slot_count = int(completion_summary.get("missing_slot_count") or 0)
    completed_slot_count = int(completion_summary.get("completed_slot_count") or 0)
    total_required_slot_count = completed_slot_count + missing_slot_count
    manual_evidence_context = _manual_evidence_payload_context(
        manual_evidence_panel_payload=panel_payload,
        workflow=workflow_data,
    )
    queue_counts = _mapping(manual_evidence_context.get("queue_counts"))
    gap_payload = _mapping(manual_evidence_context.get("gap_payload"))
    panel_record = _mapping(manual_evidence_context.get("panel_record"))
    panel_missing_evidence_type = _r203_panel_has_draft_text(panel_record) and not _text(
        panel_record.get("evidence_type")
    )
    blocker_rows = _r207_blocker_rows(
        completion_payload=completion_payload,
        queue_counts=queue_counts,
        gap_payload=gap_payload,
    )
    safe_next_actions = _r207_safe_next_actions(
        blocker_rows=blocker_rows,
        completion_payload=completion_payload,
        gap_payload=gap_payload,
        panel_missing_evidence_type=panel_missing_evidence_type,
    )
    package_status = _r207_package_handoff_status(
        workflow=workflow_data,
        blocker_rows=blocker_rows,
        queue_counts=queue_counts,
        missing_slot_count=missing_slot_count,
    )
    design_status = (
        "required_design_slots_complete_for_review"
        if total_required_slot_count and missing_slot_count == 0
        else "required_design_slots_missing"
        if total_required_slot_count
        else "no_design_slot_readback"
    )
    queue_status = (
        "manual_evidence_queue_empty"
        if int(queue_counts.get("row_count") or 0) == 0
        else "manual_evidence_blocked_or_preview_only"
        if int(queue_counts.get("blocked_count") or 0) or int(queue_counts.get("preview_only_count") or 0)
        else "manual_evidence_review_needed"
    )
    payload = {
        "schema_version": R207_PROJECT_REVIEW_COMPLETION_GATE_SCHEMA_VERSION,
        "panel_title": R207_PROJECT_REVIEW_COMPLETION_GATE_TITLE,
        "boundary_note": R207_PROJECT_REVIEW_COMPLETION_GATE_BOUNDARY_COPY,
        "read_only": True,
        "session_state_only": True,
        "documentation_only": True,
        "manual_review_required": True,
        "route_confirmation": {
            "status": route_status,
            "route_id": route_id,
            "route_label": _first_text(selected_route.get("label_en"), selected_route.get("label_zh")),
            "readback": _first_text(
                selected_route.get("label_en"),
                selected_route.get("route_id"),
                "No confirmed route is in the current session.",
            ),
            "next_action": "Confirm route in the session draft." if not route_id else "Continue design and evidence readback.",
        },
        "design_slot_completion": {
            "status": design_status,
            "completed_slot_count": completed_slot_count,
            "missing_slot_count": missing_slot_count,
            "total_required_slot_count": total_required_slot_count,
            "completed_slots": _list(completion_summary.get("completed_slots")),
            "missing_slots": _list(completion_summary.get("missing_slots")),
            "next_action": "Fill required design information." if missing_slot_count else "Review manual evidence gaps.",
        },
        "manual_evidence": {
            "entry_status": _r207_manual_entry_status(panel_payload, queue_counts),
            "queue_status": queue_status,
            "row_count": int(queue_counts.get("row_count") or 0),
            "review_needed_count": int(queue_counts.get("review_needed_count") or 0),
            "blocked_count": int(queue_counts.get("blocked_count") or 0),
            "preview_only_count": int(queue_counts.get("preview_only_count") or 0),
            "gap_status": _status_label(_mapping(gap_payload.get("summary")).get("gap_status")),
            "next_action": "Add source note." if _r207_count_rows_with_missing(_r207_gap_rows(gap_payload), "source_note") else "Review manual evidence gaps.",
        },
        "package_handoff_readback": {
            "status": package_status,
            "readback": "Package/handoff status remains readback-only while blockers are visible.",
            "next_action": "Refresh package readback.",
        },
        "top_blockers": blocker_rows,
        "safe_next_actions": safe_next_actions,
    }
    payload["status_rows"] = _r207_status_rows(payload)
    return payload


def render_project_review_completion_gate_panel(
    *,
    project_draft_payload: Mapping[str, Any] | None,
    workflow: Mapping[str, Any] | None = None,
    manual_evidence_panel_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_project_review_completion_gate_payload(
        project_draft_payload=project_draft_payload,
        workflow=workflow,
        manual_evidence_panel_payload=manual_evidence_panel_payload,
    )
    st.markdown(f"**{R207_PROJECT_REVIEW_COMPLETION_GATE_TITLE}**")
    st.caption(R207_PROJECT_REVIEW_COMPLETION_GATE_BOUNDARY_COPY)
    render_wrapped_summary_cards(
        st,
        _r207_summary_cards(payload),
        class_suffix="bds-r207-project-review-completion-gate",
    )
    _render_table_sections(
        (
            (
                "Project Review Completion status",
                _list(payload.get("status_rows")),
                "No project review completion status rows are available.",
            ),
            (
                "Project Review Completion blockers",
                _list(payload.get("top_blockers")),
                "No top blockers are visible in the current readback.",
            ),
            (
                "Project Review Completion actions",
                _list(payload.get("safe_next_actions")),
                "No safe next actions are visible in the current readback.",
            ),
        )
    )
    return payload


def _candidate_route_review_summary_cards(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    route = _mapping(payload.get("route_readback"))
    slots = _mapping(payload.get("required_design_slots"))
    evidence = _mapping(payload.get("manual_evidence"))
    return [
        {
            "label": "Route draft",
            "value": _status_label(route.get("route_review_status")),
            "note": _first_text(route.get("route_label"), route.get("route_id"), "No confirmed route in session."),
        },
        {
            "label": "Design slots",
            "value": f"{slots.get('completed_slot_count', 0)}/{slots.get('total_required_slot_count', 0)}",
            "note": f"{slots.get('missing_slot_count', 0)} required slot(s) missing.",
        },
        {
            "label": "Manual evidence",
            "value": (
                f"blocked {evidence.get('blocked_count', 0)} / "
                f"preview {evidence.get('preview_only_count', 0)}"
            ),
            "note": _status_label(evidence.get("gap_status")),
        },
        {
            "label": "Construct task",
            "value": "not created",
            "note": _text(payload.get("advance_blocker_reason")),
        },
    ]


def _construct_task_readback_gate_summary_cards(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "label": "Readback gate",
            "value": _status_label(payload.get("gate_status")),
            "note": "Construct task draft readback remains separate from route review.",
        },
        {
            "label": "Can enter readback",
            "value": "yes" if payload.get("can_enter_construct_task_draft_readback") else "no",
            "note": _first_text(payload.get("route_label"), payload.get("route_id"), "No candidate route recorded."),
        },
        {
            "label": "Blockers",
            "value": str(len(_list(payload.get("blocked_reasons")))),
            "note": "Visible route, slot, and evidence gaps only.",
        },
        {
            "label": "Construct output",
            "value": "not created",
            "note": "No task, draft, sequence, validation, or optimization output.",
        },
    ]


def render_candidate_route_review_draft_section(
    *,
    project_draft_payload: Mapping[str, Any] | None,
    workflow: Mapping[str, Any] | None = None,
    manual_evidence_panel_payload: Mapping[str, Any] | None = None,
    completion_gate_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_candidate_route_review_draft(
        project_draft_payload=project_draft_payload,
        workflow=workflow,
        manual_evidence_panel_payload=manual_evidence_panel_payload,
        completion_gate_payload=completion_gate_payload,
    )
    st.markdown("**Candidate Route Review Draft**")
    st.caption(_text(payload.get("boundary_note")))
    st.caption(
        "Candidate route draft, construct task draft, and package/handoff readback stay separate review surfaces."
    )
    render_wrapped_summary_cards(
        st,
        _candidate_route_review_summary_cards(payload),
        class_suffix="bds-r220-candidate-route-review-draft",
    )
    _render_table_sections(
        (
            (
                "Candidate Route Review Draft status",
                _list(payload.get("status_rows")),
                "No candidate route review status rows are available.",
            ),
            (
                "Candidate Route Review Draft blockers",
                _list(payload.get("blocker_rows")),
                "No candidate route review blockers are available.",
            ),
            (
                "Candidate Route Review Draft actions",
                _list(payload.get("safe_next_actions")),
                "No safe candidate route next actions are available.",
            ),
        )
    )
    return payload


def render_construct_task_readback_gate_section(
    *,
    candidate_route_review_draft: Mapping[str, Any] | None,
    completion_gate_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = build_construct_task_readback_gate(
        candidate_route_review_draft=candidate_route_review_draft,
        completion_gate_payload=completion_gate_payload,
    )
    st.markdown("**Construct Task Readback Gate**")
    st.caption(_text(payload.get("boundary_note")))
    render_wrapped_summary_cards(
        st,
        _construct_task_readback_gate_summary_cards(payload),
        class_suffix="bds-r222-construct-task-readback-gate",
    )
    _render_table_sections(
        (
            (
                "Construct Task Readback Gate status",
                _list(payload.get("status_rows")),
                "No construct task readback gate status rows are available.",
            ),
            (
                "Construct Task Readback Gate blockers",
                _list(payload.get("blocked_reasons")),
                "No construct task readback gate blockers are visible.",
            ),
            (
                "Construct Task Readback Gate completion items",
                _list(payload.get("next_completion_items")),
                "No construct task readback completion items are visible.",
            ),
        )
    )
    return payload


TABLE_CARD_FIELDS: dict[str, tuple[str, str | None, tuple[str, ...]]] = {
    "Route summary": ("Field", None, ("Readback",)),
    "Construct slot summary": (
        "Slot label",
        "Required",
        ("Evidence count", "Component count", "Manual review", "Gap flags"),
    ),
    "Slot coverage matrix": (
        "Slot label",
        "Required / optional",
        ("Evidence count", "Component count", "Manual review", "Gap flags"),
    ),
    "Evidence summary": ("Label", "Evidence id", ("Source key",)),
    "Component candidate summary": ("Label", "Component id", ("Type", "Source key")),
    "Gap / manual review queue": ("Item", "Category", ("Slot", "Reason")),
    "Manual Evidence Review Queue": (
        "Evidence label",
        "Queue state",
        (
            "Manual review state",
            "Source readback/status",
            "Package support readback",
            "Primary reason",
            "Blocking reasons",
            "Warnings",
            "Traceability readback",
        ),
    ),
    "Manual evidence package readback": ("Field", None, ("Readback",)),
    "Manual Evidence Gap Assistant": (
        "Evidence label",
        "Queue state",
        (
            "Gap summary",
            "State explanation",
            "Package support",
            "Safe next actions",
            "Top blockers",
            "Warnings",
        ),
    ),
    "Project Review Completion status": (
        "Checkpoint",
        "Status",
        ("Readback", "Next action"),
    ),
    "Project Review Completion blockers": (
        "Blocker",
        "Type",
        ("Count", "Action"),
    ),
    "Project Review Completion actions": (
        "Action",
        "Area",
        ("Reason", "Readback-only"),
    ),
    "Candidate Route Review Draft status": (
        "Checkpoint",
        "Status",
        ("Readback", "Next action"),
    ),
    "Candidate Route Review Draft blockers": (
        "Blocker",
        "Type",
        ("Count", "Action"),
    ),
    "Candidate Route Review Draft actions": (
        "Action",
        "Area",
        ("Reason", "Readback-only"),
    ),
    "Required Design Information missing slots": (
        "Slot",
        "Status",
        ("Slot key", "Required", "Value", "Manual review"),
    ),
    "Required Design Information slot summary": (
        "Slot",
        "Status",
        ("Slot key", "Required", "Value", "Manual review"),
    ),
    "Manual evidence package rows": (
        "Evidence label",
        "Queue state",
        ("Primary reason", "Blocking reasons", "Warnings", "Traceability readback"),
    ),
    "Traceability": ("Traceability", None, ("Readback",)),
    "Simple package preview sections": ("Section", "Status", ("Summary",)),
    "Simple package mock actions": ("Action", "Kind", ("Mock", "Writes data")),
    "Simple package identity preview": ("Identity", "Status", ("Readback",)),
}


def _find_manual_evidence_preflight_payload(*sources: Mapping[str, Any] | None) -> Any:
    for source in sources:
        source_map = _mapping(source)
        for key in MANUAL_EVIDENCE_PREFLIGHT_PAYLOAD_KEYS:
            value = source_map.get(key)
            if isinstance(value, Mapping) or (
                isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str))
            ):
                return value
    adapter_payload = manual_evidence_queue_payload_from_project_input(
        [source for source in sources if source]
    )
    if _mapping(adapter_payload.get("summary")).get("row_count"):
        return adapter_payload
    return []


def _readback_summary(value: Any, preferred_keys: Sequence[str] = ()) -> str:
    return readback_summary(value, preferred_keys)


def _readback_list(values: Any) -> str:
    return readback_list(values)


def _manual_evidence_review_queue_rows(queue_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _list(queue_payload.get("rows")):
        if not isinstance(row, Mapping):
            continue
        rows.append(_manual_evidence_review_readback_row(row, include_queue_detail=True))
    return rows


def _manual_evidence_review_readback_row(
    row: Mapping[str, Any],
    *,
    include_queue_detail: bool,
) -> dict[str, Any]:
    traceability_readback = _mapping(row.get("traceability_readback") or row.get("traceability"))
    if include_queue_detail:
        package_readback = _mapping(row.get("package_support_readback"))
        source_readback = _mapping(row.get("source_readback") or row.get("source_status"))
        return {
            "Queue state": _status_label(row.get("queue_state")),
            "Evidence label": _first_text(row.get("evidence_label"), "Manual evidence preflight input"),
            "Manual review state": _status_label(row.get("manual_review_state")),
            "Source readback/status": _readback_summary(
                source_readback,
                ("status", "source_type", "input_provenance_status"),
            ),
            "Package support readback": (
                f"status: {_status_label(package_readback.get('status'))}; "
                f"supported: {'yes' if package_readback.get('supported') is True else 'no'}; "
                "package output action: no"
            ),
            "Primary reason": _first_text(row.get("primary_reason"), "manual evidence preflight readback"),
            "Blocking reasons": _readback_list(row.get("visible_blocking_reasons")),
            "Warnings": _readback_list(row.get("visible_warnings")),
            "Traceability readback": _readback_summary(
                traceability_readback,
                ("record_id", "record_type", "route_scope", "input_shape"),
            ),
        }
    return {
        "Evidence label": _first_text(row.get("evidence_label"), "Manual evidence preflight input"),
        "Queue state": _status_label(row.get("queue_state")),
        "Primary reason": _first_text(row.get("primary_reason"), "manual evidence preflight readback"),
        "Blocking reasons": _readback_list(row.get("visible_blocking_reasons")),
        "Warnings": _readback_list(row.get("visible_warnings")),
        "Traceability readback": _readback_summary(
            traceability_readback,
            ("record_id", "record_type", "route_scope", "input_shape"),
        ),
    }


def _manual_evidence_review_queue_summary_cards(queue_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    summary = _mapping(queue_payload.get("summary"))
    counts = _mapping(summary.get("queue_state_counts"))
    return [
        {
            "label": "Queue rows",
            "value": str(summary.get("row_count", 0)),
            "note": "Rows supplied by the R196 read-only presenter.",
        },
        {
            "label": "Blocked rows",
            "value": str(counts.get("blocked", 0) + counts.get("malformed_blocked", 0)),
            "note": "Blocked means review/preflight attention, not export behavior.",
        },
        {
            "label": "Preview-only rows",
            "value": str(counts.get("preview_only", 0)),
            "note": "Beginner preview context remains separate from package support.",
        },
        {
            "label": "Readback mode",
            "value": "read-only",
            "note": "No import, evidence sign-off, source confirmation, or package output action.",
        },
    ]


def _render_manual_evidence_queue_readback(
    queue_payload: Mapping[str, Any],
    *,
    class_suffix: str,
    empty_message: str,
) -> None:
    render_wrapped_summary_cards(
        st,
        _manual_evidence_review_queue_summary_cards(queue_payload),
        class_suffix=class_suffix,
    )
    _render_table(
        "Manual Evidence Review Queue",
        _manual_evidence_review_queue_rows(queue_payload),
        empty_message,
    )


def render_manual_evidence_review_queue_preview(
    *,
    project: Mapping[str, Any] | None,
    workflow: Mapping[str, Any] | None,
    build_presenter: Callable[[Any], dict[str, Any]] = present_manual_evidence_review_queue,
) -> dict[str, Any]:
    preflight_payload = _find_manual_evidence_preflight_payload(project, workflow)
    queue_payload = _manual_evidence_queue_payload_from_any(preflight_payload, build_presenter)
    st.markdown("**Manual Evidence Review Queue**")
    st.caption(MANUAL_EVIDENCE_REVIEW_QUEUE_BOUNDARY_COPY)
    st.caption(
        "Placeholder/demo entries remain visible as review context only; this preview does not add real evidence "
        "or realistic external identifiers."
    )
    for reason in _list(queue_payload.get("batch_blocking_reasons")):
        st.caption(f"- {_text(reason)}")
    for warning in _list(queue_payload.get("batch_warnings")):
        st.caption(f"- {_text(warning)}")
    _render_manual_evidence_queue_readback(
        queue_payload,
        class_suffix="bds-manual-evidence-review-queue",
        empty_message="No manual evidence preflight payload is available yet; this read-only queue has no rows to show.",
    )
    render_manual_evidence_gap_assistant_preview(queue_payload)
    return queue_payload


def _package_goal_choice() -> tuple[str, str | None]:
    labels = [label for label, _goal, _dataset in PLANT_GOAL_REVIEW_PACKAGE_GOAL_OPTIONS]
    selected_label = st.selectbox(
        "Plant goal review package draft goal",
        labels,
        index=0,
        key="r165_plant_goal_review_package_goal_choice",
        help="Select the local deterministic MVP goal to render in this documentation-only review section.",
    )
    for label, goal_text, dataset_key in PLANT_GOAL_REVIEW_PACKAGE_GOAL_OPTIONS:
        if selected_label == label:
            return goal_text, dataset_key
    return DEFAULT_PLANT_GOAL_REVIEW_PACKAGE_GOAL, "rice_albumin"


def _simple_wizard_route_card_rows(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for card in _list(payload.get("route_cards")):
        if not isinstance(card, Mapping):
            continue
        examples = [str(example) for example in _list(card.get("examples_zh")) if _text(example)]
        rows.append(
            {
                "label": _first_text(card.get("label_zh"), card.get("label_en")),
                "value": _text(card.get("button_label_zh")),
                "note": (
                    f"{_text(card.get('short_description_zh'))} "
                    f"Example: {' / '.join(examples[:2])}. "
                    f"Slots: {card.get('required_slot_count', 0)}; user confirmation required."
                ),
            }
        )
    return rows


def render_simple_plant_wizard_homepage_route_cards(
    *,
    build_presenter: Callable[[dict[str, Any] | None], dict[str, Any]] = build_simple_plant_wizard_homepage_presenter,
) -> dict[str, Any]:
    payload = build_presenter(None)

    st.markdown(f"### {_text(payload.get('page_title_zh'))}")
    st.caption(_text(payload.get("page_subtitle_zh")))
    return payload


def _simple_wizard_basic_info_cards() -> list[dict[str, str]]:
    return [
        {
            "label": "这个工具做什么？",
            "value": "整理目标",
            "note": "整理植物设计目标、元件、证据和缺口。",
        },
        {
            "label": "你需要准备什么？",
            "value": "一句目标即可开始",
            "note": "目标、宿主、基因 / CDS、文献或已有材料；没有也可以先填目标。",
        },
        {
            "label": "会得到什么？",
            "value": "审查草稿",
            "note": "设计审查草稿、缺口清单、人工复核提示。",
        },
    ]


def _option_label_lookup(options: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    return {
        _text(option.get("label_zh")): _text(option.get("option_id"))
        for option in options
        if _text(option.get("label_zh")) and _text(option.get("option_id"))
    }


def _option_id_from_label(options: Sequence[Mapping[str, Any]], label: str | None) -> str | None:
    return _option_label_lookup(options).get(_text(label))


def _option_ids_from_labels(options: Sequence[Mapping[str, Any]], labels: Sequence[str]) -> list[str]:
    lookup = _option_label_lookup(options)
    selected = [lookup[label] for label in labels if label in lookup]
    if "none" in selected and len(selected) > 1:
        selected = [value for value in selected if value != "none"]
    return selected


def _simple_wizard_intake_result_rows(
    *,
    intent_payload: Mapping[str, Any],
    confirmation_payload: Mapping[str, Any],
) -> list[dict[str, str]]:
    recommended = _mapping(confirmation_payload.get("recommended_route"))
    alternatives = [
        _first_text(route.get("label_zh"), route.get("label_en"))
        for route in _list(confirmation_payload.get("alternative_routes"))
        if isinstance(route, Mapping)
    ]
    reasons = [
        _text(reason)
        for reason in _list(confirmation_payload.get("match_reasons_zh"))
        if _text(reason)
    ]
    questions = [
        _text(question)
        for question in _list(confirmation_payload.get("clarification_questions_zh"))
        if _text(question)
    ]
    return [
        {
            "label": "系统理解目标",
            "value": _text(intent_payload.get("decision_state")),
            "note": _text(intent_payload.get("interpreted_goal_zh")),
        },
        {
            "label": "候选主路线",
            "value": _first_text(recommended.get("label_zh"), "需要先澄清"),
            "note": _text(confirmation_payload.get("confidence_reason_zh")),
        },
        {
            "label": "候选其他路线",
            "value": str(len(alternatives)),
            "note": ", ".join(alternatives) if alternatives else "当前没有额外候选路线。",
        },
        {
            "label": "置信度",
            "value": _text(confirmation_payload.get("confidence")),
            "note": "仅表示文档意图信号强弱，不是实验或生物学结论。",
        },
        {
            "label": "判断依据",
            "value": str(len(reasons)),
            "note": " / ".join(reasons[:3]) if reasons else "当前信息不足，需要补充目标或材料。",
        },
        {
            "label": "澄清问题",
            "value": str(len(questions)),
            "note": " / ".join(questions[:3]) if questions else "暂无额外问题，但路线仍需用户确认。",
        },
        {
            "label": "请确认",
            "value": "用户确认必需",
            "note": _text(intent_payload.get("route_confirmation_prompt_zh")),
        },
    ]


def render_simple_plant_wizard_intake_form_mock(
    *,
    build_form_presenter: Callable[[dict[str, Any] | None], dict[str, Any]] = build_simple_plant_wizard_intake_form_presenter,
    build_intent_presenter: Callable[[str, str | None, list[str] | None, dict[str, Any] | None], dict[str, Any]]
    = build_simple_plant_wizard_intent_intake_presenter,
    build_confirmation_presenter: Callable[[dict[str, Any] | None, str | None, dict[str, Any] | None], dict[str, Any]]
    = build_simple_plant_wizard_route_confirmation_presenter,
) -> dict[str, Any]:
    payload = build_form_presenter(None)
    goal_text = st.text_area(
        _text(payload.get("goal_input_label_zh")),
        value=_text(st.session_state.get(SIMPLE_PLANT_WIZARD_GOAL_TEXT_KEY)),
        placeholder=_text(payload.get("goal_input_placeholder_zh")),
        key=SIMPLE_PLANT_WIZARD_GOAL_TEXT_KEY,
        height=90,
    )

    submitted = _st_button(
        st,
        _text(payload.get("submit_label_zh")),
        key="r180_simple_plant_wizard_start_analysis",
        type="primary",
    )

    if submitted:
        clean_goal_text = _text(goal_text)
        if clean_goal_text:
            st.session_state[SIMPLE_PLANT_WIZARD_ANALYZED_KEY] = True
            st.session_state[SIMPLE_PLANT_WIZARD_ANALYZED_GOAL_TEXT_KEY] = clean_goal_text
            st.session_state[SIMPLE_PLANT_WIZARD_CONFIRMED_KEY] = False
            st.session_state.pop(SIMPLE_PLANT_WIZARD_ROUTE_ID_KEY, None)
        else:
            _reset_simple_plant_wizard_analysis_state(st)

    clean_goal_text = _text(goal_text)
    if not clean_goal_text:
        _reset_simple_plant_wizard_analysis_state(st)
    analyzed_goal_text = _text(st.session_state.get(SIMPLE_PLANT_WIZARD_ANALYZED_GOAL_TEXT_KEY))
    if clean_goal_text and analyzed_goal_text and clean_goal_text != analyzed_goal_text:
        _reset_simple_plant_wizard_analysis_state(st)
        analyzed_goal_text = ""
    should_analyze = bool(
        st.session_state.get(SIMPLE_PLANT_WIZARD_ANALYZED_KEY)
        and clean_goal_text
        and analyzed_goal_text == clean_goal_text
    )
    selected_goal_type = _text(st.session_state.get(SIMPLE_PLANT_WIZARD_SELECTED_GOAL_TYPE_KEY)) or None
    for note in _list(payload.get("safe_boundary_notes_zh")):
        st.caption(_text(note))
    intent_payload = build_intent_presenter(goal_text, selected_goal_type, [], None)
    confirmation_payload = build_confirmation_presenter(dict(intent_payload), None, None)

    if should_analyze:
        _render_simple_wizard_analysis_result(
            intent_payload=intent_payload,
            confirmation_payload=confirmation_payload,
        )
    else:
        render_wrapped_summary_cards(
            st,
            _simple_wizard_basic_info_cards(),
            class_suffix="bds-simple-plant-wizard-basic-info",
        )

    return {
        "form_payload": payload,
        "intent_payload": intent_payload,
        "confirmation_payload": confirmation_payload,
        "submitted": bool(submitted),
        "confirmed": bool(st.session_state.get(SIMPLE_PLANT_WIZARD_CONFIRMED_KEY)),
    }


def _simple_wizard_match_reasons(confirmation_payload: Mapping[str, Any]) -> list[str]:
    return [
        _text(reason)
        for reason in _list(confirmation_payload.get("match_reasons_zh"))
        if _text(reason)
    ][:3]


def _simple_wizard_missing_required_fields(checklist_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    missing_statuses = {"missing", "missing_provenance", "needs_manual_review", "blocked"}
    rows: list[dict[str, Any]] = []
    for row in _list(checklist_payload.get("slot_rows")):
        if not isinstance(row, Mapping) or _text(row.get("status")) not in missing_statuses:
            continue
        rows.append(
            {
                "slot_id": _text(row.get("slot_id")),
                "slot_label_zh": _text(row.get("slot_label_zh")),
                "slot_label_en": _text(row.get("slot_label_en")),
                "status": _text(row.get("status")),
                "status_label_zh": _text(row.get("status_label_zh")),
                "evidence_status": _text(row.get("evidence_status")),
                "manual_review_status": _text(row.get("manual_review_status")),
                "next_action_label_zh": _text(row.get("next_action_label_zh")),
            }
        )
    return rows


def _required_design_slot_definitions() -> list[dict[str, Any]]:
    return [
        {
            "slot_key": _text(field.get("slot_key")),
            "slot_label": _text(field.get("label")),
            "required": field.get("required") == "yes",
            "widget": _text(field.get("widget")),
        }
        for field in R206_REQUIRED_DESIGN_SLOT_FIELDS
    ]


def _design_slot_values_from_draft(project_draft_payload: Mapping[str, Any]) -> dict[str, str]:
    completion = _mapping(project_draft_payload.get("design_slot_completion"))
    slots = _mapping(completion.get("slots"))
    values: dict[str, str] = {}
    for field in _required_design_slot_definitions():
        slot_key = _text(field.get("slot_key"))
        values[slot_key] = _text(slots.get(slot_key) or project_draft_payload.get(slot_key))
    return values


def build_required_design_slot_completion_payload(
    *,
    project_draft_payload: Mapping[str, Any] | None,
    slot_values: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    draft = _mapping(project_draft_payload)
    values = _design_slot_values_from_draft(draft)
    for key, value in _mapping(slot_values).items():
        if key in values:
            values[key] = _text(value)

    completed_slots: list[str] = []
    missing_slots: list[str] = []
    rows: list[dict[str, Any]] = []
    for field in _required_design_slot_definitions():
        slot_key = _text(field.get("slot_key"))
        required = bool(field.get("required"))
        value = _text(values.get(slot_key))
        if required and value:
            completed_slots.append(slot_key)
        elif required:
            missing_slots.append(slot_key)
        rows.append(
            {
                "slot_key": slot_key,
                "slot_label": _text(field.get("slot_label")),
                "required": required,
                "value": value,
                "slot_status": "documented_for_manual_review" if value else "missing_manual_entry",
                "manual_review_required": True,
            }
        )

    completion_status = "manual_review_documentation_entered" if not missing_slots else "information_completion_needed"
    summary = {
        "completed_slots": completed_slots,
        "missing_slots": missing_slots,
        "completed_slot_count": len(completed_slots),
        "missing_slot_count": len(missing_slots),
        "completion_status": completion_status,
        "manual_review_required": True,
    }
    return {
        "slot_completion_schema_version": R206_DESIGN_SLOT_COMPLETION_SCHEMA_VERSION,
        "panel_title": R206_REQUIRED_DESIGN_SLOT_PANEL_TITLE,
        "goal_description": _text(draft.get("goal_description")),
        "selected_route": _mapping(draft.get("selected_route")),
        "missing_information_checklist": [
            dict(row) for row in _list(draft.get("missing_information_checklist")) if isinstance(row, Mapping)
        ],
        "slots": values,
        "slot_rows": rows,
        "completion_summary": summary,
        "boundary_note": R206_REQUIRED_DESIGN_SLOT_BOUNDARY_COPY,
        "documentation_only": True,
        "manual_review_required": True,
    }


def build_simple_plant_wizard_project_draft_payload(
    *,
    goal_text: str,
    confirmation_payload: Mapping[str, Any],
    checklist_payload: Mapping[str, Any],
) -> dict[str, Any]:
    recommended = _mapping(confirmation_payload.get("recommended_route"))
    route_id = _first_text(recommended.get("route_id"), checklist_payload.get("route_id"))
    payload = {
        "draft_schema_version": "v2.7-r205",
        "draft_id": "simple_plant_wizard_session_project_draft",
        "draft_status": "information_completion_needed",
        "documentation_only": True,
        "manual_review_required": True,
        "goal_description": _text(goal_text),
        "interpreted_goal": _text(confirmation_payload.get("interpreted_goal_zh")),
        "selected_route": {
            "route_id": route_id,
            "label_zh": _first_text(recommended.get("label_zh"), checklist_payload.get("route_label_zh")),
            "label_en": _first_text(recommended.get("label_en"), checklist_payload.get("route_label_en")),
            "result_label_zh": _first_text(recommended.get("result_label_zh"), checklist_payload.get("route_label_zh")),
        },
        "confidence_readback": {
            "confidence": _text(confirmation_payload.get("confidence")),
            "confidence_label_zh": _text(confirmation_payload.get("confidence_label_zh")),
            "confidence_reason_zh": _text(confirmation_payload.get("confidence_reason_zh")),
            "match_reasons_zh": _simple_wizard_match_reasons(confirmation_payload),
        },
        "missing_required_fields": _simple_wizard_missing_required_fields(checklist_payload),
        "missing_information_checklist": [
            dict(row) for row in _list(checklist_payload.get("slot_rows")) if isinstance(row, Mapping)
        ],
        "gap_summary": _mapping(checklist_payload.get("gap_summary")),
        "route_checklist_completion_summary": _mapping(checklist_payload.get("completion_summary")),
        "next_step": {
            "label": "Complete missing information in Plant Review",
            "target_surfaces": ["Manual evidence entry", "Manual Evidence Review Queue"],
            "readback": (
                "Use the Plant Review Required Design Information panel for design slots and the Manual Evidence "
                "Entry / Preview area plus Manual Evidence Review Queue for source/provenance context and manual "
                "review notes. Continue adding documentation notes, source/provenance context, and manual review notes."
            ),
        },
        "boundary_note": (
            "Current project draft is a session readback for documentation-only manual review. It does not "
            "make a biological recommendation, confirm experiment status, improve a route, grant package output "
            "permission, or judge wet-lab use."
        ),
    }
    payload["design_slot_completion"] = build_required_design_slot_completion_payload(
        project_draft_payload=payload,
        slot_values={},
    )
    payload["design_slot_completion_summary"] = payload["design_slot_completion"]["completion_summary"]
    return payload


def _store_simple_plant_wizard_project_draft(
    *,
    goal_text: str,
    confirmation_payload: Mapping[str, Any],
    checklist_payload: Mapping[str, Any],
    streamlit_module: Any = st,
) -> dict[str, Any]:
    payload = build_simple_plant_wizard_project_draft_payload(
        goal_text=goal_text,
        confirmation_payload=confirmation_payload,
        checklist_payload=checklist_payload,
    )
    getattr(streamlit_module, "session_state", {})[SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY] = payload
    return payload


def _simple_wizard_project_draft_summary_cards(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    selected_route = _mapping(payload.get("selected_route"))
    confidence = _mapping(payload.get("confidence_readback"))
    return [
        {
            "label": "Goal description",
            "value": _text(payload.get("goal_description")) or "not recorded",
            "note": _text(payload.get("interpreted_goal")) or "Original user goal is preserved as written.",
        },
        {
            "label": "Selected route",
            "value": _first_text(selected_route.get("result_label_zh"), selected_route.get("label_en"), "not recorded"),
            "note": f"Route id: {_text(selected_route.get('route_id')) or 'not recorded'}",
        },
        {
            "label": "Confidence/readback",
            "value": _text(confidence.get("confidence")) or "not recorded",
            "note": _text(confidence.get("confidence_reason_zh")) or "No confidence readback is recorded.",
        },
        {
            "label": "Missing required fields",
            "value": str(len(_list(payload.get("missing_required_fields")))),
            "note": "Use Plant Review manual evidence entry and review queue areas for documentation follow-up.",
        },
    ]


def _simple_wizard_project_draft_missing_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _list(payload.get("missing_required_fields")):
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "Field": _first_text(row.get("slot_label_zh"), row.get("slot_label_en"), row.get("slot_id")),
                "Slot id": _text(row.get("slot_id")),
                "Status": _first_text(row.get("status_label_zh"), row.get("status")),
                "Evidence": _text(row.get("evidence_status")),
                "Manual review": _text(row.get("manual_review_status")),
                "Next": _text(row.get("next_action_label_zh")),
            }
        )
    return rows


def _required_design_slot_summary_cards(completion_payload: Mapping[str, Any]) -> list[dict[str, str]]:
    summary = _mapping(completion_payload.get("completion_summary"))
    return [
        {
            "label": "Completed slots",
            "value": str(summary.get("completed_slot_count", 0)),
            "note": "Manual entries saved in the session project draft.",
        },
        {
            "label": "Missing slots",
            "value": str(summary.get("missing_slot_count", 0)),
            "note": "Blank required slots remain visible for manual review.",
        },
        {
            "label": "Completion status",
            "value": _status_label(summary.get("completion_status")),
            "note": "Status is documentation review state, not experimental status.",
        },
        {
            "label": "Manual review",
            "value": "yes" if summary.get("manual_review_required") else "not flagged",
            "note": "Human/company review remains required for interpretation.",
        },
    ]


def _required_design_slot_rows(completion_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _list(completion_payload.get("slot_rows")):
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "Slot": _text(row.get("slot_label")),
                "Slot key": _text(row.get("slot_key")),
                "Required": "yes" if row.get("required") else "no",
                "Status": _status_label(row.get("slot_status")),
                "Value": _text(row.get("value")) or "not entered",
                "Manual review": "yes" if row.get("manual_review_required") else "not flagged",
            }
        )
    return rows


def _required_design_missing_slot_rows(completion_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    missing = set(_list(_mapping(completion_payload.get("completion_summary")).get("missing_slots")))
    return [
        row
        for row in _required_design_slot_rows(completion_payload)
        if row["Slot key"] in missing
    ]


def _render_required_design_slot_inputs(
    completion_payload: Mapping[str, Any],
) -> dict[str, str]:
    values = _mapping(completion_payload.get("slots"))
    updated: dict[str, str] = {}
    for field in _required_design_slot_definitions():
        slot_key = _text(field.get("slot_key"))
        label = _text(field.get("slot_label"))
        value = _text(values.get(slot_key))
        help_text = (
            "Manual documentation entry saved only in the current session project draft. "
            "Leave blank when the information is not recorded."
        )
        widget_key = f"r206_required_design_slot_{slot_key}"
        if field.get("widget") == "text_area":
            updated[slot_key] = _text(st.text_area(label, value=value, key=widget_key, help=help_text))
        else:
            updated[slot_key] = _text(st.text_input(label, value=value, key=widget_key, help=help_text))
    return updated


def render_required_design_information_completion_panel(
    project_draft_payload: Mapping[str, Any] | None = None,
    *,
    streamlit_module: Any | None = None,
) -> dict[str, Any]:
    global st
    original_st = st
    st = streamlit_module or original_st
    try:
        payload = _mapping(project_draft_payload)
        completion_payload = build_required_design_slot_completion_payload(
            project_draft_payload=payload,
            slot_values={},
        )
        st.markdown(f"**{R206_REQUIRED_DESIGN_SLOT_PANEL_TITLE}**")
        st.caption(R206_REQUIRED_DESIGN_SLOT_BOUNDARY_COPY)
        selected_route = _mapping(completion_payload.get("selected_route"))
        st.caption(f"Goal description: {_text(completion_payload.get('goal_description')) or 'not recorded'}")
        st.caption(
            "Selected route: "
            f"{_first_text(selected_route.get('label_en'), selected_route.get('route_id'), 'not recorded')}"
        )
        render_wrapped_summary_cards(
            st,
            _required_design_slot_summary_cards(completion_payload),
            class_suffix="bds-r206-required-design-slots",
        )
        _render_table(
            "Required Design Information missing slots",
            _required_design_missing_slot_rows(completion_payload),
            "No blank required design slots are visible in the current session draft.",
        )
        updated_values = _render_required_design_slot_inputs(completion_payload)
        updated_completion = build_required_design_slot_completion_payload(
            project_draft_payload=payload,
            slot_values=updated_values,
        )
        _render_table(
            "Required Design Information slot summary",
            _required_design_slot_rows(updated_completion),
            "No design slot rows are available for the current session draft.",
        )

        updated_draft = dict(payload)
        for slot_key, value in updated_values.items():
            if value or slot_key in updated_draft:
                updated_draft[slot_key] = value
        updated_draft["design_slot_completion"] = updated_completion
        updated_draft["design_slot_completion_summary"] = updated_completion["completion_summary"]
        updated_draft["documentation_only"] = True
        updated_draft["manual_review_required"] = True
        if updated_draft:
            getattr(st, "session_state", {})[SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY] = updated_draft
        return updated_draft or updated_completion
    finally:
        st = original_st


def render_current_project_draft_summary(
    project_draft_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = _mapping(project_draft_payload)
    if not payload:
        st.caption(
            "Current project draft / 当前项目草稿: no confirmed Simple Plant Wizard route is in session. "
            "Plant Review stays in documentation-only manual review mode."
        )
        return {
            "draft_status": "no_current_project_draft",
            "documentation_only": True,
            "manual_review_required": True,
            "missing_required_fields": [],
        }

    st.markdown("**Current project draft / 当前项目草稿**")
    st.caption(_text(payload.get("boundary_note")))
    render_wrapped_summary_cards(
        st,
        _simple_wizard_project_draft_summary_cards(payload),
        class_suffix="bds-r205-current-project-draft",
    )
    _render_table(
        "Current project draft missing fields",
        _simple_wizard_project_draft_missing_rows(payload),
        "No missing required fields are recorded for the current draft.",
    )
    next_step = _mapping(payload.get("next_step"))
    st.info(_first_text(next_step.get("readback"), "Continue in Plant Review manual review areas."))
    return dict(payload)


def _render_simple_wizard_analysis_result(
    *,
    intent_payload: Mapping[str, Any],
    confirmation_payload: Mapping[str, Any],
) -> None:
    recommended = _mapping(confirmation_payload.get("recommended_route"))
    route_id = _text(recommended.get("route_id"))
    if route_id:
        st.markdown("**系统判断**")
        st.markdown(
            f"推荐路线：{_first_text(recommended.get('result_label_zh'), recommended.get('label_zh'))}"
        )
        st.markdown(_text(confirmation_payload.get("confidence_label_zh")))
        reasons = _simple_wizard_match_reasons(confirmation_payload)
        if reasons:
            st.markdown("**判断依据：**")
            for reason in reasons:
                st.caption(f"- {reason}")
        st.markdown("**下一步：**")
        st.caption("请确认这个路线是否符合你的目标。")
        confirm_column, change_column = st.columns(2)
        with confirm_column:
            if _st_button(st, SIMPLE_PLANT_WIZARD_CONFIRM_ROUTE_LABEL, key="r180_simple_plant_wizard_confirm_route"):
                goal_text = _text(_mapping(intent_payload.get("input_summary")).get("user_goal_text"))
                checklist_payload = build_simple_plant_wizard_route_checklist_presenter(route_id, None, None)
                st.session_state[SIMPLE_PLANT_WIZARD_CONFIRMED_KEY] = True
                st.session_state[SIMPLE_PLANT_WIZARD_ROUTE_ID_KEY] = route_id
                _store_simple_plant_wizard_project_draft(
                    goal_text=goal_text,
                    confirmation_payload=confirmation_payload,
                    checklist_payload=checklist_payload,
                    streamlit_module=st,
                )
                st.info("已创建当前项目草稿；下一步在 Plant Review 中补齐资料。")
        with change_column:
            if _st_button(st, "修改目标描述", key="r180_simple_plant_wizard_change_goal"):
                _reset_simple_plant_wizard_analysis_state(st)
        return

    st.markdown("**还需要确认一个**")
    st.caption("你想从哪个角度整理青蒿素相关设计？")
    questions = [
        _text(question)
        for question in _list(confirmation_payload.get("clarification_questions_zh"))
        if _text(question)
    ][:3]
    if not questions:
        questions = ["请补充目标类型、植物宿主或已有证据线索。"]
    for index, question in enumerate(questions, start=1):
        _st_button(st, question, key=f"r180_simple_plant_wizard_clarify_{index}")
    st.caption("信息明确前不会强制进入任何路线。")


def _simple_wizard_confirmation_rows(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    recommended = _mapping(payload.get("recommended_route"))
    if recommended:
        rows.append(
            {
                "label": "Recommended route",
                "value": _first_text(recommended.get("label_zh"), recommended.get("label_en")),
                "note": (
                    f"{_text(recommended.get('short_description_zh'))} "
                    "User confirmation is required before entering route records."
                ),
            }
        )
    else:
        rows.append(
            {
                "label": "Recommended route",
                "value": "needs clarification",
                "note": "No route is forced until the user answers the clarification questions.",
            }
        )

    alternatives = [
        _first_text(route.get("label_zh"), route.get("label_en"))
        for route in _list(payload.get("alternative_routes"))
        if isinstance(route, Mapping)
    ]
    rows.append(
        {
            "label": "Alternative routes",
            "value": str(len(alternatives)),
            "note": ", ".join(alternatives) if alternatives else "No additional route candidates in this card.",
        }
    )
    rows.append(
        {
            "label": "Confidence",
            "value": _text(payload.get("confidence")),
            "note": _text(payload.get("confidence_reason_zh")),
        }
    )
    return rows


def render_simple_plant_wizard_route_confirmation_card(
    *,
    build_presenter: Callable[[dict[str, Any] | None, str | None, dict[str, Any] | None], dict[str, Any]]
    = build_simple_plant_wizard_route_confirmation_presenter,
) -> dict[str, Any]:
    payload = build_presenter(
        None,
        None,
        {
            "user_goal_text": "Express a target protein enzyme in rice seed",
            "available_materials": ["target_gene_or_cds", "host_plant"],
        },
    )

    st.markdown(f"**{_text(payload.get('page_title_zh'))}**")
    st.caption(_text(payload.get("page_subtitle_zh")))
    st.caption(_text(payload.get("interpreted_goal_zh")))
    render_wrapped_summary_cards(
        st,
        _simple_wizard_confirmation_rows(payload),
        class_suffix="bds-simple-plant-wizard-confirmation",
    )
    questions = [
        _text(question)
        for question in _list(payload.get("clarification_questions_zh"))
        if _text(question)
    ]
    if questions:
        st.info("Clarification questions: " + " / ".join(questions[:3]))
    actions = [
        _text(action.get("label_zh"))
        for action in _list(payload.get("confirmation_actions"))
        if isinstance(action, Mapping) and _text(action.get("label_zh"))
    ]
    st.caption("Confirmation actions shown as read-only labels: " + " / ".join(actions))
    for note in _list(payload.get("safe_boundary_notes_zh")):
        st.caption(f"- {_text(note)}")
    st.caption(f"Shared handoff stage remains: {_text(payload.get('handoff_stage_id'))}.")
    return payload


def _simple_wizard_checklist_summary_cards(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    summary = _mapping(payload.get("completion_summary"))
    return [
        {
            "label": "Route",
            "value": _first_text(payload.get("route_label_zh"), payload.get("route_label_en")),
            "note": f"Route id: {_text(payload.get('route_id'))}",
        },
        {
            "label": "Completion",
            "value": _text(summary.get("completion_label_zh")),
            "note": (
                f"Filled {summary.get('filled_slots', 0)} of {summary.get('total_slots', 0)} slots; "
                f"missing {summary.get('missing_slots', 0)}, provenance gaps "
                f"{summary.get('missing_provenance_slots', 0)}."
            ),
        },
        {
            "label": "Manual review",
            "value": str(summary.get("manual_review_slots", 0)),
            "note": _text(summary.get("package_readiness_label_zh")),
        },
    ]


def _simple_wizard_checklist_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _list(payload.get("slot_rows")):
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                "Slot": _first_text(row.get("slot_label_zh"), row.get("slot_label_en")),
                "Status": _text(row.get("status_label_zh")),
                "Evidence": _text(row.get("evidence_status_label_zh")),
                "Manual review": _text(row.get("manual_review_status_label_zh")),
                "Next": _text(row.get("next_action_label_zh")),
                "Helper": _text(row.get("helper_text_zh")),
            }
        )
    return rows


def _simple_wizard_gap_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for group_id, group in _mapping(payload.get("gap_summary")).items():
        if not isinstance(group, Mapping):
            continue
        rows.append(
            {
                "Gap group": group_id.replace("_", " "),
                "Count": group.get("count", 0),
                "Slots": ", ".join(_list(group.get("slot_ids"))),
                "Explanation": _text(group.get("explanation_zh")),
            }
        )
    return rows


def _simple_wizard_action_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for action in _list(payload.get("next_step_actions")):
        if not isinstance(action, Mapping):
            continue
        rows.append(
            {
                "Action": _text(action.get("label_zh")),
                "Slot id": _text(action.get("slot_id")),
                "Kind": _text(action.get("action_kind")),
                "Mock": "yes" if action.get("is_mock") else "no",
                "Writes data": "no" if action.get("does_not_write_data") else "unexpected",
            }
        )
    return rows


def render_simple_plant_wizard_route_checklist_section(
    *,
    route_id: str | None = "plant_protein_expression_review",
    build_presenter: Callable[[str | None, Any, dict[str, Any] | None], dict[str, Any]]
    = build_simple_plant_wizard_route_checklist_presenter,
) -> dict[str, Any]:
    payload = build_presenter(route_id, None, None)

    st.markdown(f"**{_text(payload.get('page_title_zh'))}**")
    st.caption(_text(payload.get("page_subtitle_zh")))
    render_wrapped_summary_cards(
        st,
        _simple_wizard_checklist_summary_cards(payload),
        class_suffix="bds-simple-plant-wizard-checklist",
    )
    _render_table_sections(
        (
            (
                "Simple route checklist",
                _simple_wizard_checklist_rows(payload),
                "No beginner route checklist rows are available for this route.",
            ),
            (
                "Simple route gap summary",
                _simple_wizard_gap_rows(payload),
                "No beginner route gap rows are available for this route.",
            ),
            (
                "Simple next-step mock actions",
                _simple_wizard_action_rows(payload),
                "No mock next-step actions are available for this route.",
            ),
        )
    )
    for note in _list(payload.get("safe_boundary_notes_zh")):
        st.caption(f"- {_text(note)}")
    st.caption(_text(payload.get("advanced_detail_hint_zh")))
    st.caption(f"Shared handoff stage remains: {_text(payload.get('handoff_stage_id'))}.")
    return payload


def _simple_wizard_package_summary_cards(payload: Mapping[str, Any]) -> list[dict[str, str]]:
    gaps = _mapping(payload.get("gap_summary"))
    manual = _mapping(payload.get("manual_review_summary"))
    return [
        {
            "label": "Package status",
            "value": _text(payload.get("package_status_label_zh")),
            "note": _text(payload.get("package_readiness_summary_zh")),
        },
        {
            "label": "Route",
            "value": _text(payload.get("route_label_zh")),
            "note": f"Route id: {_text(payload.get('route_id'))}",
        },
        {
            "label": "Gap / review",
            "value": (
                f"gaps {gaps.get('missing_field_count', 0)} / "
                f"sources {gaps.get('missing_evidence_or_provenance_count', 0)} / "
                f"manual {manual.get('manual_review_item_count', 0)}"
            ),
            "note": _text(manual.get("summary_zh")),
        },
    ]


def _simple_wizard_package_preview_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for section in _list(payload.get("package_preview_sections")):
        if not isinstance(section, Mapping):
            continue
        rows.append(
            {
                "Section": _text(section.get("title_zh")),
                "Status": _text(section.get("status_label_zh")),
                "Summary": _text(section.get("summary_zh")),
            }
        )
    return rows


def _simple_wizard_package_action_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for action in _list(payload.get("package_entry_actions")):
        if not isinstance(action, Mapping):
            continue
        rows.append(
            {
                "Action": _text(action.get("label_zh")),
                "Kind": _text(action.get("action_kind")),
                "Mock": "yes" if action.get("is_mock") else "unexpected",
                "Writes data": "no" if action.get("does_not_write_data") else "unexpected",
            }
        )
    return rows


def _simple_wizard_package_identity_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    identity = _mapping(payload.get("identity_preview"))
    return [
        {
            "Identity": _text(identity.get("label_zh")),
            "Status": "disabled" if identity.get("enabled") is False else "unexpected",
            "Readback": (
                f"QR: {_text(identity.get('qr_status_zh'))}; "
                f"MD5: {_text(identity.get('md5_status_zh'))}; "
                f"Snapshot: {_text(identity.get('snapshot_status_zh'))}"
            ),
        }
    ]


def render_simple_plant_wizard_package_entry_section(
    *,
    route_id: str | None = "plant_protein_expression_review",
    checklist_payload: Mapping[str, Any] | None = None,
    build_presenter: Callable[[str | None, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None], dict[str, Any]]
    = build_simple_plant_wizard_package_entry_presenter,
) -> dict[str, Any]:
    payload = build_presenter(route_id, dict(checklist_payload or {}), None, None)

    st.markdown(f"**{_text(payload.get('page_title_zh'))}**")
    st.caption(_text(payload.get("page_subtitle_zh")))
    render_wrapped_summary_cards(
        st,
        _simple_wizard_package_summary_cards(payload),
        class_suffix="bds-simple-plant-wizard-package-entry",
    )
    _render_table_sections(
        (
            (
                "Simple package preview sections",
                _simple_wizard_package_preview_rows(payload),
                "No package preview sections are available for this route.",
            ),
            (
                "Simple package mock actions",
                _simple_wizard_package_action_rows(payload),
                "No package entry mock actions are available for this route.",
            ),
            (
                "Simple package identity preview",
                _simple_wizard_package_identity_rows(payload),
                "No package identity preview is available for this route.",
            ),
        )
    )
    for note in _list(payload.get("safe_boundary_notes_zh")):
        st.caption(f"- {_text(note)}")
    st.caption(_text(payload.get("advanced_detail_hint_zh")))
    st.caption(f"Shared handoff stage remains: {_text(payload.get('package_stage_id'))}.")
    return payload


def _package_summary_cards(package: Mapping[str, Any]) -> list[dict[str, str]]:
    matched = _mapping(package.get("matched_seed_records"))
    manual = _mapping(package.get("manual_review_task_summary"))
    promotion = _mapping(package.get("promotion_boundary"))
    package_status = _status_label(package.get("package_status"))
    if package.get("package_status") == "design_review_package_draft_ready":
        package_status = "design review package draft available"
    return [
        {
            "label": "Package status",
            "value": package_status,
            "note": "R163 deterministic package draft status.",
        },
        {
            "label": "Seed records represented",
            "value": str(matched.get("represented_seed_record_count", 0)),
            "note": "Local rice_albumin seed records summarized.",
        },
        {
            "label": "Manual review tasks",
            "value": str(manual.get("manual_provenance_queue_task_count", 0)),
            "note": "Manual provenance queue task count.",
        },
        {
            "label": "Records blocked from promotion",
            "value": str(manual.get("records_blocked_from_promotion", 0)),
            "note": "Promotion remains blocked in this MVP.",
        },
        {
            "label": "Ready-to-promote count",
            "value": str(promotion.get("ready_to_promote_count", 0)),
            "note": "Expected to remain 0 for R165.",
        },
        {
            "label": "Promotion-allowed count",
            "value": str(promotion.get("promotion_allowed_count", 0)),
            "note": "Expected to remain 0 for R165.",
        },
    ]


def _package_design_slot_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for slot in _list(package.get("design_slots")):
        if not isinstance(slot, Mapping):
            continue
        rows.append(
            {
                "Slot label": _text(slot.get("slot_label")),
                "Slot status": _status_label(slot.get("slot_status")),
                "Source stage": _text(slot.get("source_stage")),
                "Manual review": "yes" if slot.get("manual_review_required") else "no",
                "Record count": slot.get("record_count", 0),
                "Gap count": slot.get("gap_count", 0),
                "Notes": _text(slot.get("notes")),
            }
        )
    return rows


def _package_seed_record_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    matched = _mapping(package.get("matched_seed_records"))
    rows: list[dict[str, Any]] = []
    for record in _list(matched.get("records")):
        if not isinstance(record, Mapping):
            continue
        rows.append(
            {
                "Record id": _text(record.get("record_id")),
                "Label": _text(record.get("record_label")),
                "Section": _text(record.get("seed_section")),
                "Review status": _status_label(record.get("review_status")),
                "Provenance status": _status_label(record.get("provenance_status")),
                "Manual review": "yes" if record.get("needs_manual_review") else "no",
            }
        )
    return rows


def _package_evidence_gap_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    evidence = _mapping(package.get("evidence_summary"))
    provenance = _mapping(package.get("provenance_gap_summary"))
    identifier = _mapping(provenance.get("identifier_autofill"))
    return [
        {
            "Field": "Worksheet evidence rows",
            "Readback": str(evidence.get("worksheet_evidence_row_count", 0)),
            "Boundary": "local review summary",
        },
        {
            "Field": "Worksheet component slot rows",
            "Readback": str(evidence.get("worksheet_component_slot_row_count", 0)),
            "Boundary": "local review summary",
        },
        {
            "Field": "Worksheet follow-up queue",
            "Readback": str(evidence.get("worksheet_followup_queue_count", 0)),
            "Boundary": "manual review required",
        },
        {
            "Field": "Provenance gaps",
            "Readback": str(provenance.get("provenance_gap_count", 0)),
            "Boundary": "source/provenance review",
        },
        {
            "Field": "Manual provenance queue tasks",
            "Readback": str(provenance.get("manual_provenance_queue_task_count", 0)),
            "Boundary": "manual review required",
        },
        {
            "Field": "Identifier autofill performed",
            "Readback": "no" if identifier.get("performed") is False else "unexpected",
            "Boundary": "no source or database identifier is filled",
        },
    ]


def _package_status_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    route = _mapping(package.get("candidate_route_summary"))
    construct = _mapping(package.get("construct_status_summary"))
    task = _mapping(construct.get("construct_task"))
    draft = _mapping(construct.get("construct_draft"))
    promotion = _mapping(package.get("promotion_boundary"))
    artemisia = _mapping(route.get("artemisia_annua_status"))
    return [
        {
            "Area": "Candidate route",
            "Status": _status_label(route.get("candidate_route_status")),
            "Readback": f"dataset_key={_text(route.get('dataset_key'))}",
        },
        {
            "Area": "Construct task",
            "Status": _status_label(task.get("status")),
            "Readback": _first_text(task.get("unavailable_reason"), "not created by this MVP"),
        },
        {
            "Area": "Construct draft",
            "Status": _status_label(draft.get("status")),
            "Readback": _first_text(draft.get("unavailable_reason"), "not created by this MVP"),
        },
        {
            "Area": "Promotion boundary",
            "Status": "blocked",
            "Readback": _text(promotion.get("boundary_note")),
        },
        {
            "Area": "Artemisia annua",
            "Status": _status_label(artemisia.get("gate_status")),
            "Readback": "inactive in the R165 visible MVP path",
        },
    ]


def _package_manual_review_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    manual = _mapping(package.get("manual_review_task_summary"))
    return [
        {"Field": "Manual provenance queue tasks", "Readback": manual.get("manual_provenance_queue_task_count", 0)},
        {"Field": "Represented records", "Readback": manual.get("represented_record_count", 0)},
        {"Field": "Records blocked from promotion", "Readback": manual.get("records_blocked_from_promotion", 0)},
        {"Field": "Ready-to-promote count", "Readback": manual.get("ready_to_promote_count", 0)},
        {"Field": "Promotion-allowed count", "Readback": manual.get("promotion_allowed_count", 0)},
        {"Field": "Manual review required", "Readback": "yes" if manual.get("manual_review_required") else "no"},
    ]


def _package_manual_evidence_summary_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    readback = _mapping(package.get("manual_evidence_review_queue_readback"))
    summary = _mapping(readback.get("summary"))
    return [
        {"Field": "Readback status", "Readback": _status_label(readback.get("section_status"))},
        {"Field": "Queue rows", "Readback": summary.get("row_count", 0)},
        {"Field": "Review-needed rows", "Readback": summary.get("review_needed_count", 0)},
        {"Field": "Blocked rows", "Readback": summary.get("blocked_count", 0)},
        {"Field": "Preview-only rows", "Readback": summary.get("preview_only_count", 0)},
        {"Field": "Malformed/empty rows", "Readback": summary.get("malformed_or_empty_count", 0)},
        {"Field": "Readback boundary", "Readback": _text(readback.get("boundary_note"))},
    ]


def _package_manual_evidence_detail_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    readback = _mapping(package.get("manual_evidence_review_queue_readback"))
    rows: list[dict[str, Any]] = []
    for row in _list(readback.get("rows")):
        if not isinstance(row, Mapping):
            continue
        detail_row = _manual_evidence_review_readback_row(row, include_queue_detail=False)
        detail_row["Primary reason"] = _text(row.get("primary_reason"))
        rows.append(detail_row)
    return rows


def _package_next_action_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for action in _list(package.get("next_human_actions")):
        if not isinstance(action, Mapping):
            continue
        rows.append(
            {
                "Action": _text(action.get("action_label")),
                "Status": _status_label(action.get("action_status")),
                "Task count": action.get("task_count", ""),
            }
        )
    return rows


def _package_blocked_output_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for output in _list(package.get("blocked_outputs")):
        if not isinstance(output, Mapping):
            continue
        rows.append(
            {
                "Output": _text(output.get("output_key")),
                "Blocked": "yes" if output.get("blocked") else "no",
                "Reason": _text(output.get("reason")),
            }
        )
    return rows


def render_plant_goal_review_package_draft_visible_mvp(
    *,
    build_package: Callable[[Any, str | None], dict[str, Any]] = build_plant_goal_review_package_mvp,
) -> dict[str, Any]:
    st.markdown("**Plant Goal -> Design Review Package Draft**")
    st.caption(
        "Documentation-only local deterministic MVP. Manual review is required; this section does not write records, "
        "fill source identifiers, create construct work, promote records, or add report/export/persistence behavior."
    )
    goal_text, dataset_key = _package_goal_choice()
    package = build_package(goal_text, dataset_key)

    st.caption(f"Selected plant goal: {goal_text}")
    if package.get("fail_closed"):
        intent = _mapping(package.get("intent_summary"))
        st.info(
            _first_text(
                intent.get("summary"),
                "The selected goal is outside the active rice_albumin MVP path and failed closed.",
            )
        )

    render_wrapped_summary_cards(st, _package_summary_cards(package), class_suffix="bds-r165-package")

    intent = _mapping(package.get("intent_summary"))
    with st.expander("Design Intent", expanded=True):
        st.markdown(f"**{_first_text(intent.get('section_title'), 'Design Intent')}**")
        st.caption(_first_text(intent.get("summary"), "No design intent summary is available."))
        st.caption(f"Intent status: {_status_label(intent.get('intent_status'))}")
        st.caption(f"Dataset key: {_text(package.get('dataset_key'))}")
        st.caption(_text(package.get("documentation_boundary")))

    _render_expander_table_sections(
        (
            (
                "Required design slots",
                "Required design slots",
                _package_design_slot_rows(package),
                "No required design slot rows are available for this package state.",
            ),
            (
                "Matched seed records",
                "Matched seed records",
                _package_seed_record_rows(package),
                "No matched seed records are represented for this package state.",
            ),
            (
                "Evidence/provenance gaps",
                "Evidence/provenance gaps",
                _package_evidence_gap_rows(package),
                "No evidence/provenance gap summary is available.",
            ),
            (
                "Candidate route and construct status",
                "Candidate route and construct status",
                _package_status_rows(package),
                "No candidate route or construct status is available.",
            ),
            (
                "Manual review tasks",
                "Manual review tasks",
                _package_manual_review_rows(package),
                "No manual review task summary is available.",
            ),
        )
    )
    with st.expander("Manual evidence package readback", expanded=False):
        readback = _mapping(package.get("manual_evidence_review_queue_readback"))
        st.caption(
            _first_text(
                readback.get("boundary_note"),
                "Manual evidence queue status is preflight/readback only.",
            )
        )
        _render_table_sections(
            (
                (
                    "Manual evidence package readback",
                    _package_manual_evidence_summary_rows(package),
                    "No manual evidence package readback summary is available.",
                ),
                (
                    "Manual evidence package rows",
                    _package_manual_evidence_detail_rows(package),
                    "No manual evidence preflight payload is available for package readback.",
                ),
            )
        )
    _render_expander_table_sections(
        (
            (
                "Next human actions",
                "Next human actions",
                _package_next_action_rows(package),
                "No next human action rows are available.",
            ),
        )
    )
    with st.expander("Blocked outputs / safety boundary", expanded=False):
        st.caption("R163 service side-effect boundary; R165 adds only this read-only UI mount.")
        _render_table(
            "Blocked outputs / safety boundary",
            _package_blocked_output_rows(package),
            "No blocked output boundary rows are available.",
        )
    return package


def _render_table(title: str, rows: list[dict[str, Any]], empty_message: str) -> None:
    title_field, subtitle_field, visible_fields = TABLE_CARD_FIELDS.get(title, ("", None, ()))
    render_responsive_detail_table(
        st,
        rows,
        title=title,
        empty_message=empty_message,
        title_field=title_field or None,
        subtitle_field=subtitle_field,
        visible_fields=visible_fields,
    )


def _render_table_sections(sections: Sequence[tuple[str, list[dict[str, Any]], str]]) -> None:
    for title, rows, empty_message in sections:
        _render_table(title, rows, empty_message)


def _render_expander_table_sections(
    sections: Sequence[tuple[str, str, list[dict[str, Any]], str]],
) -> None:
    for expander_label, title, rows, empty_message in sections:
        with st.expander(expander_label, expanded=False):
            _render_table(title, rows, empty_message)


def _should_show_simple_plant_wizard_advanced_details(streamlit_module: Any = st) -> bool:
    return bool(
        streamlit_module.checkbox(
            SIMPLE_PLANT_WIZARD_ADVANCED_MODE_LABEL,
            value=False,
            key=SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY,
            help=(
                "Show preserved reviewer details for manual review and regression checks. "
                "The beginner wizard above remains unchanged."
            ),
        )
    )


def _evidence_records_from_widgets(draft: PlantDesignProjectDraft) -> list[dict[str, Any]]:
    existing = draft.evidence_references
    row_count = max(1, len(existing))
    rows: list[dict[str, Any]] = []
    for index in range(row_count):
        current = existing[index] if index < len(existing) else None
        default_id = current.evidence_id if current else f"{draft.project_id}-evidence-{index + 1}"
        label = st.text_input(
            f"Evidence label {index + 1}",
            value=current.label if current else "",
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_evidence_label_{draft.project_id}_{index}",
        )
        reference_text = st.text_area(
            f"Evidence or provenance note {index + 1}",
            value=current.reference_text if current else "",
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_evidence_text_{draft.project_id}_{index}",
            height=72,
        )
        notes = st.text_area(
            f"Manual review note {index + 1}",
            value=current.notes if current else "",
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_evidence_notes_{draft.project_id}_{index}",
            height=56,
        )
        if _text(label) or _text(reference_text) or _text(notes):
            rows.append(
                {
                    "evidence_id": default_id,
                    "label": _text(label),
                    "reference_text": _text(reference_text),
                    "source_type": "user-entered",
                    "record_origin": "user",
                    "notes": _text(notes),
                }
            )
    return rows


def _construct_slot_updates_from_widgets(draft: PlantDesignProjectDraft) -> dict[str, dict[str, str]]:
    updates: dict[str, dict[str, str]] = {}
    for slot in draft.construct_slots:
        component_name = st.text_input(
            slot.slot_role,
            value=slot.component_name,
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_slot_component_{draft.project_id}_{slot.slot_key}",
            help="Manual component or context note for this saved documentation draft.",
        )
        source_reference = st.text_input(
            f"{slot.slot_role} source/provenance reference",
            value=slot.source_reference,
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_slot_source_{draft.project_id}_{slot.slot_key}",
            help="Optional user-entered source/provenance note. This is not source approval.",
        )
        evidence_reference = st.text_input(
            f"{slot.slot_role} evidence reference",
            value=slot.evidence_reference,
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_slot_evidence_{draft.project_id}_{slot.slot_key}",
            help="Optional user-entered evidence label or note.",
        )
        notes = st.text_area(
            f"{slot.slot_role} review comment",
            value=slot.notes,
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_slot_notes_{draft.project_id}_{slot.slot_key}",
            height=56,
        )
        updates[slot.slot_key] = {
            "component_name": _text(component_name),
            "source_reference": _text(source_reference),
            "evidence_reference": _text(evidence_reference),
            "notes": _text(notes),
        }
    return updates


def _active_draft_changed(
    draft: PlantDesignProjectDraft,
    *,
    project_name: str,
    plant_design_goal: str,
    host_context: str,
    expression_context: str,
    construct_slot_updates: dict[str, dict[str, str]],
    evidence_references: list[dict[str, Any]],
) -> bool:
    if (
        draft.project_name != project_name
        or draft.plant_design_goal != plant_design_goal
        or draft.host_context != host_context
        or draft.expression_context != expression_context
    ):
        return True
    for slot in draft.construct_slots:
        update = construct_slot_updates.get(slot.slot_key, {})
        if (
            slot.component_name != update.get("component_name", "")
            or slot.source_reference != update.get("source_reference", "")
            or slot.evidence_reference != update.get("evidence_reference", "")
            or slot.notes != update.get("notes", "")
        ):
            return True
    return [record.to_dict() for record in draft.evidence_references] != evidence_references


def _render_plant_project_draft_completeness_readback(draft: PlantDesignProjectDraft) -> None:
    completeness = build_plant_project_draft_completeness(draft)
    cards = [
        {
            "label": "Completeness",
            "value": _status_label(completeness["completeness_state"]),
            "note": f"Missing fields: {len(completeness['missing_fields'])}",
        },
        {
            "label": "Workflow eligibility",
            "value": _status_label(completeness["workflow_eligibility"]),
            "note": "Eligibility is documentation workflow state, not lab-use judgment.",
        },
        {
            "label": "Manual review",
            "value": _status_label(completeness["review_state"]),
            "note": "Human/company review remains required.",
        },
        {
            "label": "Component evidence gaps",
            "value": str(len(completeness["component_evidence_gaps"])),
            "note": "Entered components still need source or evidence notes when listed here.",
        },
    ]
    render_wrapped_summary_cards(st, cards, class_suffix="bds-r224-plant-project-draft-completeness")
    st.info(completeness["next_action"])


def render_plant_project_draft_persistence_panel(
    *,
    repository: PlantProjectDraftRepository | None = None,
) -> dict[str, Any]:
    controller = PlantProjectDraftController(
        session_state=st.session_state,
        repository=repository or PlantProjectDraftRepository(),
    )
    st.markdown(f"**{R224_PLANT_PROJECT_DRAFT_SECTION_TITLE}**")
    st.caption(R224_PLANT_PROJECT_DRAFT_BOUNDARY_COPY)

    saved_projects = controller.list_saved_projects()
    if saved_projects:
        options = [summary.display_label() for summary in saved_projects]
        selected_label = st.selectbox(
            "Saved user plant project drafts",
            options,
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_saved_project_selector",
            help="Saved drafts are user data, not example data.",
        )
        selected_index = options.index(selected_label) if selected_label in options else 0
        selected_summary = saved_projects[selected_index]
    else:
        selected_summary = None
        st.caption("No saved user plant project drafts are listed in local storage yet.")

    new_column, open_column = st.columns(2)
    with new_column:
        if _st_button(st, "Create blank plant project draft", key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_new"):
            result = controller.create_blank()
            if result.ok:
                st.success(result.message)
    with open_column:
        if selected_summary and _st_button(
            st,
            "Open selected plant project draft",
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_open",
        ):
            result = controller.open_project(selected_summary.project_id)
            if result.ok:
                st.success(result.message)
            else:
                st.error(result.message)

    draft = controller.active_draft()
    if draft is None:
        return {
            "active_draft": None,
            "saved_project_count": len(saved_projects),
            "persistence_state": "no-active-project",
        }

    st.caption(f"Project ID: {draft.project_id}")
    st.caption(f"Created: {draft.created_at} | Updated: {draft.updated_at}")
    save_state = _text(st.session_state.get(ACTIVE_PLANT_PROJECT_SAVE_STATE_KEY)) or "unsaved"
    dirty = bool(st.session_state.get(ACTIVE_PLANT_PROJECT_DIRTY_KEY))
    st.caption(f"Save state: {save_state}; unsaved changes visible: {'yes' if dirty else 'no'}")

    project_name = _text(
        st.text_input(
            "Project name",
            value=draft.project_name,
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_name_{draft.project_id}",
        )
    )
    plant_design_goal = _text(
        st.text_area(
            "Plant design goal",
            value=draft.plant_design_goal,
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_goal_{draft.project_id}",
            height=82,
        )
    )
    host_context = _text(
        st.text_input(
            "Host and plant context",
            value=draft.host_context,
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_host_{draft.project_id}",
        )
    )
    expression_context = _text(
        st.text_area(
            "Expression context",
            value=draft.expression_context,
            key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_expression_{draft.project_id}",
            height=82,
        )
    )
    with st.expander("Construct slots and component references", expanded=True):
        construct_slot_updates = _construct_slot_updates_from_widgets(draft)
    with st.expander("Evidence and provenance references", expanded=False):
        evidence_references = _evidence_records_from_widgets(draft)

    if _active_draft_changed(
        draft,
        project_name=project_name,
        plant_design_goal=plant_design_goal,
        host_context=host_context,
        expression_context=expression_context,
        construct_slot_updates=construct_slot_updates,
        evidence_references=evidence_references,
    ):
        update_result = controller.update_active(
            project_name=project_name,
            plant_design_goal=plant_design_goal,
            host_context=host_context,
            expression_context=expression_context,
            construct_slot_updates=construct_slot_updates,
            evidence_references=evidence_references,
        )
        if update_result.draft is not None:
            draft = update_result.draft

    save_column, workspace_column = st.columns(2)
    with save_column:
        if _st_button(st, "Save plant project draft", key=f"{R224_PLANT_PROJECT_DRAFT_WIDGET_PREFIX}_save", type="primary"):
            result = controller.save_active()
            if result.ok:
                st.success(result.message)
                draft = result.draft or draft
            else:
                st.error(result.message)
    with workspace_column:
        st.caption("Open Plant Expression Workspace to review the active saved user draft.")

    _render_plant_project_draft_completeness_readback(draft)
    project_draft_payload = _sync_active_plant_project_draft_to_session(draft, streamlit_module=st)
    return {
        "active_draft": draft.to_dict(),
        "project_draft_payload": project_draft_payload,
        "saved_project_count": len(saved_projects),
        "persistence_state": _text(st.session_state.get(ACTIVE_PLANT_PROJECT_SAVE_STATE_KEY)) or "unsaved",
    }


def render_simple_plant_design_wizard_landing(
    *,
    change_page: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    del change_page
    return render_plant_review_workflow_section(
        project=None,
        steps=[],
        expression_links=[],
        test_records=[],
        review_signals=[],
    )


def render_plant_review_workflow_section(
    *,
    project: Mapping[str, Any] | None,
    steps: Sequence[Mapping[str, Any]] | None = None,
    expression_links: Sequence[Mapping[str, Any]] | None = None,
    test_records: Sequence[Mapping[str, Any]] | None = None,
    review_signals: Sequence[Mapping[str, Any]] | None = None,
    build_workflow: Callable[[Mapping[str, Any]], dict[str, Any]] = build_plant_review_workspace_workflow,
) -> dict[str, Any]:
    advanced_requested = _advanced_mode_already_requested(st)
    persistence_state = render_plant_project_draft_persistence_panel()
    intake_state: dict[str, Any] = {}
    if not advanced_requested:
        _left, center_column, _right = st.columns([1, 1.7, 1])
        with center_column:
            render_simple_plant_wizard_homepage_route_cards()
            intake_state = render_simple_plant_wizard_intake_form_mock()
    route_id = _text(st.session_state.get(SIMPLE_PLANT_WIZARD_ROUTE_ID_KEY))
    simple_checklist_payload: dict[str, Any] = {}
    project_draft_payload = _mapping(st.session_state.get(SIMPLE_PLANT_WIZARD_PROJECT_DRAFT_KEY))
    active_persisted_project = _mapping(persistence_state.get("active_draft"))
    design_slot_panel_rendered = False
    has_beginner_confirmed_route = bool(intake_state.get("confirmed") and route_id)
    if not advanced_requested and (has_beginner_confirmed_route or active_persisted_project):
        with st.expander("查看需要补充的信息", expanded=False):
            simple_checklist_payload = render_simple_plant_wizard_route_checklist_section(route_id=route_id)
        confirmation_payload = _mapping(intake_state.get("confirmation_payload"))
        goal_text = _text(st.session_state.get(SIMPLE_PLANT_WIZARD_ANALYZED_GOAL_TEXT_KEY))
        selected_route = _mapping(project_draft_payload.get("selected_route"))
        if (
            not active_persisted_project
            and (
                not project_draft_payload
                or _text(project_draft_payload.get("goal_description")) != goal_text
                or _text(selected_route.get("route_id")) != route_id
            )
        ):
            project_draft_payload = _store_simple_plant_wizard_project_draft(
                goal_text=goal_text,
                confirmation_payload=confirmation_payload,
                checklist_payload=simple_checklist_payload,
                streamlit_module=st,
            )
        render_current_project_draft_summary(project_draft_payload)
        completion_gate_payload = render_project_review_completion_gate_panel(
            project_draft_payload=project_draft_payload,
            workflow=None,
            manual_evidence_panel_payload=None,
        )
        project_draft_payload = render_required_design_information_completion_panel(project_draft_payload)
        completion_gate_payload = build_project_review_completion_gate_payload(
            project_draft_payload=project_draft_payload,
            workflow=None,
            manual_evidence_panel_payload=None,
        )
        candidate_route_review_draft = render_candidate_route_review_draft_section(
            project_draft_payload=project_draft_payload,
            workflow=None,
            manual_evidence_panel_payload=None,
            completion_gate_payload=completion_gate_payload,
        )
        construct_task_readback_gate = render_construct_task_readback_gate_section(
            candidate_route_review_draft=candidate_route_review_draft,
            completion_gate_payload=completion_gate_payload,
        )
        design_slot_panel_rendered = True
        with st.expander("查看审查包草稿预览", expanded=False):
            render_simple_plant_wizard_package_entry_section(
                route_id=route_id,
                checklist_payload=simple_checklist_payload,
            )
    with st.expander(SIMPLE_PLANT_WIZARD_ADVANCED_EXPANDER_LABEL, expanded=False):
        st.caption(SIMPLE_PLANT_WIZARD_ADVANCED_MODE_NOTE)
        show_advanced_details = _should_show_simple_plant_wizard_advanced_details(st)
    show_advanced_details = bool(show_advanced_details or advanced_requested)
    if not show_advanced_details:
        return {
            "workflow_status": "simple_plant_wizard_beginner_mode",
            "advanced_details_visible": False,
            "plant_project_draft_persistence": persistence_state,
            "intake_state": intake_state,
            "simple_checklist_payload": simple_checklist_payload,
            "current_project_draft": project_draft_payload,
            "candidate_route_review_draft": candidate_route_review_draft
            if "candidate_route_review_draft" in locals()
            else {},
            "construct_task_readback_gate": construct_task_readback_gate
            if "construct_task_readback_gate" in locals()
            else {},
        }

    st.subheader("Plant Review Workflow")
    st.caption(SIMPLE_PLANT_WIZARD_RUNTIME_MARKER)
    st.caption(PLANT_REVIEW_WORKFLOW_BOUNDARY_COPY)
    workspace_state = _project_workspace_state(
        project,
        steps,
        expression_links,
        test_records,
        review_signals,
        project_draft=project_draft_payload,
    )
    workflow = build_workflow(workspace_state)
    workflow["advanced_details_visible"] = True
    workflow["plant_project_draft_persistence"] = persistence_state
    if project_draft_payload:
        workflow["current_project_draft"] = project_draft_payload

    render_current_project_draft_summary(project_draft_payload)
    workflow["project_review_completion_gate"] = render_project_review_completion_gate_panel(
        project_draft_payload=project_draft_payload,
        workflow=workflow,
        manual_evidence_panel_payload=None,
    )
    if project_draft_payload and not design_slot_panel_rendered:
        project_draft_payload = render_required_design_information_completion_panel(project_draft_payload)
        workflow["current_project_draft"] = project_draft_payload
        workspace_state = _project_workspace_state(
            project,
            steps,
            expression_links,
            test_records,
            review_signals,
            project_draft=project_draft_payload,
        )
        workflow = build_workflow(workspace_state)
        workflow["advanced_details_visible"] = True
        workflow["plant_project_draft_persistence"] = persistence_state
        workflow["current_project_draft"] = project_draft_payload

    existing_manual_evidence_preflight_payload = _find_manual_evidence_preflight_payload(project, workflow)
    panel_payload = render_manual_evidence_entry_preview_panel(project=project, workflow=workflow)
    manual_evidence_context = _manual_evidence_payload_context(
        manual_evidence_panel_payload=panel_payload,
        workflow=workflow,
    )
    if _mapping(manual_evidence_context.get("queue_payload")).get("summary", {}).get("row_count"):
        workflow["manual_evidence_entry_panel_payload"] = panel_payload
        workflow["manual_evidence_review_queue_payload"] = panel_payload["queue_payload"]
    workflow["project_review_completion_gate"] = build_project_review_completion_gate_payload(
        project_draft_payload=project_draft_payload,
        workflow=workflow,
        manual_evidence_panel_payload=panel_payload,
    )
    workflow["candidate_route_review_draft"] = render_candidate_route_review_draft_section(
        project_draft_payload=project_draft_payload,
        workflow=workflow,
        manual_evidence_panel_payload=panel_payload,
        completion_gate_payload=workflow["project_review_completion_gate"],
    )
    workflow["construct_task_readback_gate"] = render_construct_task_readback_gate_section(
        candidate_route_review_draft=workflow["candidate_route_review_draft"],
        completion_gate_payload=workflow["project_review_completion_gate"],
    )

    slot_matrix = build_plant_review_slot_coverage_matrix(workflow)
    with st.expander(PLANT_REVIEW_ADVANCED_DETAIL_EXPANDER_LABEL, expanded=False):
        st.markdown("**Plant Review section map**")
        st.caption("Compact overview for the long Plant Review flow; detailed tables stay below in read-only sections.")
        render_wrapped_summary_cards(st, _review_map_cards(workflow, slot_matrix), class_suffix="bds-review-map")
        st.markdown("**Workflow status summary**")
        render_wrapped_summary_cards(st, _summary_status_cards(workflow), class_suffix="bds-review-status")
        _render_table_sections(
            (
                ("Route summary", _route_summary_rows(workflow), "No route summary is available yet."),
                ("Construct slot summary", _slot_rows(workflow), "No construct slot rows are available yet."),
            )
        )
        with st.expander("Slot coverage matrix detail", expanded=False):
            _render_table(
                "Slot coverage matrix",
                _slot_coverage_matrix_rows(slot_matrix),
                "No slot coverage rows are available yet.",
            )
            st.caption(f"Slot coverage matrix status: {_status_label(slot_matrix.get('matrix_status'))}")
        with st.expander("Evidence, component, and gap detail", expanded=False):
            _render_table_sections(
                (
                    ("Evidence summary", _evidence_rows(workflow), "No evidence records are available yet."),
                    (
                        "Component candidate summary",
                        _component_rows(workflow),
                        "No component candidate records are available yet.",
                    ),
                    (
                        "Gap / manual review queue",
                        _gap_rows(workflow),
                        "No manual review queue rows are available yet.",
                    ),
                )
            )
            if existing_manual_evidence_preflight_payload:
                render_manual_evidence_review_queue_preview(project=project, workflow=workflow)

        package = _mapping(_mapping(workflow.get("chain_result")).get("plant_review_package"))
        st.markdown("**Package status / warnings**")
        st.caption(f"Package status: {_status_label(package.get('package_status'))}")
        warnings = _list(workflow.get("warnings"))
        if warnings:
            for warning in warnings[:6]:
                st.caption(f"- {_text(warning)}")
        else:
            st.caption("No workflow warnings recorded.")

        _render_table("Traceability", _traceability_rows(workflow), "No traceability rows are available yet.")
    st.markdown(f"**{R208_PACKAGE_HANDOFF_ENTRY_TITLE}**")
    st.caption(R208_PACKAGE_HANDOFF_ENTRY_HELPER)
    with st.expander(PLANT_REVIEW_PROOF_PATH_EXPANDER_LABEL, expanded=False):
        render_plant_goal_review_package_draft_visible_mvp()
    with st.expander(PLANT_REVIEW_READBACK_EXPANDER_LABEL, expanded=False):
        st.markdown("**Plant Review handoff and provenance readback**")
        render_plant_review_handoff_preview_section(_mapping(workflow.get("handoff_preview_payload")))
        st.markdown("**Rice albumin seed review**")
        render_rice_albumin_seed_review_visible_mount()
        st.caption("Documentation-only/manual-review boundary: this tab is read-only and does not mutate project records.")
    return workflow
