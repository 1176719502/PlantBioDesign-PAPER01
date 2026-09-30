"""Formal Agent V1 workspace backed by the adopted Agent services."""
from __future__ import annotations

import hashlib
import json
import os
from enum import Enum
from html import escape
from pathlib import Path
import secrets
from typing import Any, Callable, Mapping, MutableMapping

import streamlit as st
from core.i18n import t as _t

from services.agent_candidate_store import CandidateStore, CandidateStoreError
from services.agent_contracts import (
    AdoptionRequest,
    AgentCandidate,
    AgentRequest,
    AgentRunState,
    CandidateState,
    ComponentReference,
    DeterministicValidationStatus,
    candidate_digest,
)
from services.agent_product_adapter import AgentProductAdapter
from services.agent_provider import QwenProvider
from services.agent_service import AgentBackend, AgentServiceError, ProductComponentRepository, V2ComponentRepository
from services.formal_project_definition_lifecycle import normalize_project_definition
from services.formal_project_persistence import save_formal_project_draft
from services.plant_host_registry import (
    GENERIC_MULTI_TU_ASSEMBLY,
    SINGLE_GENE_COMPLETE_VECTOR,
    list_hosts,
)
from services.plant_project_draft_repository import (
    PlantProjectDraftError,
    PlantProjectDraftRepository,
    SqlitePlantProjectDraftRepository,
)


AGENT_STATE_DIR_ENV = "BIODESIGN_AGENT_STATE_DIR"
_SESSION_PREFIX = "agent_v1_ui_"
_PROJECT_TYPE_BY_WORKFLOW = {"single_gene": "single_gene", "multi_tu": "dual_tu"}
_WORKFLOW_LEVEL_BY_TYPE = {
    "single_gene": SINGLE_GENE_COMPLETE_VECTOR,
    "multi_tu": GENERIC_MULTI_TU_ASSEMBLY,
    "pathway": GENERIC_MULTI_TU_ASSEMBLY,
    "gate3_pathway": GENERIC_MULTI_TU_ASSEMBLY,
}
_HOST_NAMES_ZH = {
    "rice": "水稻",
    "tobacco": "烟草",
    "maize": "玉米",
    "arabidopsis": "拟南芥",
    "tomato": "番茄",
    "soybean": "大豆",
}
_HOST_LOCALE_KEYS = {
    "rice": "runtime.host_rice",
    "tobacco": "runtime.host_tobacco",
    "maize": "runtime.host_maize",
    "arabidopsis": "runtime.host_arabidopsis",
    "tomato": "runtime.host_tomato",
    "soybean": "runtime.host_soybean",
}
_REQUEST_WIDGET_FIELDS = ("user_intent", "host", "workflow", "cds", "component_ids")

AGENT_CSS = """
<style>
.st-key-agent_v1_workspace { max-width: 1120px; }
.st-key-agent_v1_workspace > [data-testid="stVerticalBlock"] { gap: .75rem; }
.agent-page-subtitle { color:#566579; font-size:15px; line-height:1.6; margin:0 0 14px; }
.agent-context-bar { display:grid; grid-template-columns:minmax(0,1.7fr) minmax(180px,.7fr); gap:16px;
  padding:12px 14px; border:1px solid #dce4dc; border-radius:6px; background:#f7f9f7; margin:4px 0 16px; }
.agent-context-bar span, .agent-fact span { display:block; color:#667085; font-size:12px; margin-bottom:3px; }
.agent-context-bar strong, .agent-fact strong { color:#1d2920; font-size:14px; overflow-wrap:anywhere; }
.agent-state-band { border-left:4px solid #2e6fae; padding:12px 16px; background:#eef5fb; margin:6px 0 18px; }
.agent-state-band.ready { border-left-color:#237a4b; background:#edf6f0; }
.agent-state-band.warning { border-left-color:#b7791f; background:#fff8e8; }
.agent-state-band.error { border-left-color:#c53d3d; background:#fdf0f0; }
.agent-state-band strong { display:block; color:#1d2920; font-size:16px; margin-bottom:4px; }
.agent-state-band span { color:#4b596b; font-size:14px; line-height:1.55; }
.agent-input-guidance { color:#4d3510; background:#fff8e8; border:1px solid #ead6a8;
  border-radius:6px; padding:10px 12px; margin:-8px 0 16px; font-size:14px; line-height:1.55; }
.st-key-agent_cds_input_attention { border-left:4px solid #b7791f; padding:10px 12px 12px;
  background:#fff8e8; border-radius:0 6px 6px 0; }
.agent-facts { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; margin:4px 0 14px; }
.agent-fact { border-bottom:1px solid #dce4dc; padding:8px 2px 10px; min-width:0; }
.agent-section-title { color:#1d2920; font-size:16px; font-weight:650; margin:20px 0 8px; }
.agent-component-row { display:grid; grid-template-columns:minmax(0,1fr) 150px 130px; gap:12px;
  align-items:center; padding:10px 0; border-bottom:1px solid #e3e8e3; font-size:14px; }
.agent-component-row code { overflow-wrap:anywhere; white-space:normal; }
.agent-status { display:inline-block; width:max-content; padding:2px 7px; border-radius:4px; background:#e8f4ec;
  color:#1d663f; font-size:12px; font-weight:650; }
.agent-status.reference { background:#f1f3f5; color:#56606b; }
.agent-status.assisted { background:#fff3d6; color:#875b14; }
.agent-adoption-summary { border:1px solid #c7d2c8; border-radius:6px; padding:14px 16px; background:#fff; }
.agent-receipt { border-left:4px solid #237a4b; padding:14px 16px; background:#edf6f0; margin-bottom:16px; }
.agent-receipt > strong, .agent-receipt > span { display:block; }
.agent-receipt > span { margin-top:4px; color:#4b596b; }
.agent-receipt dl { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px 18px; margin:10px 0 0; }
.agent-receipt dt { color:#667085; font-size:12px; }.agent-receipt dd { margin:2px 0 0; overflow-wrap:anywhere; font-size:13px; }
@media(max-width:800px) {
  .agent-context-bar, .agent-facts, .agent-receipt dl { grid-template-columns:1fr; }
  .agent-component-row { grid-template-columns:1fr; gap:4px; }
}
</style>
"""


def default_agent_state_dir() -> Path:
    override = os.getenv(AGENT_STATE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA")
        if root:
            return Path(root) / "BioDesignStudio" / "agent_state"
    return Path.home() / ".biodesign_studio" / "agent_state"


def resolve_formal_repository(project_id: str, project_type: str = "") -> Any | None:
    """Resolve the repository already owning the current Formal project."""
    json_repository = PlantProjectDraftRepository()
    sqlite_repository = SqlitePlantProjectDraftRepository()
    repositories = (
        (sqlite_repository, json_repository)
        if project_type in {"dual_tu", "multi_tu"}
        else (json_repository, sqlite_repository)
    )
    for repository in repositories:
        try:
            repository.load(project_id)
        except PlantProjectDraftError:
            continue
        return repository
    return None


def build_agent_backend(project_id: str, project_type: str = "") -> AgentBackend | None:
    repository = resolve_formal_repository(project_id, project_type)
    if repository is None:
        return None
    store = CandidateStore(default_agent_state_dir())
    return AgentBackend(
        QwenProvider(),
        candidate_store=store,
        project_repository=repository,
        component_repository=ProductComponentRepository(),
    )


def _host_record(value: str) -> dict[str, Any] | None:
    host = str(value or "").strip()
    for record in list_hosts():
        aliases = list(record.get("aliases") or ())
        storage_value = (
            f"{str(record.get('common_name') or '').strip()} "
            f"({str(aliases[0] if aliases else record.get('scientific_name') or '').strip()})"
        )
        if host in {
            str(record.get("host_id") or ""),
            str(record.get("scientific_name") or ""),
            storage_value,
        }:
            return record
    return None


def _host_storage_value(record: Mapping[str, Any]) -> str:
    aliases = list(record.get("aliases") or ())
    suffix = str(aliases[0] if aliases else record.get("scientific_name") or "").strip()
    return f"{str(record.get('common_name') or '').strip()} ({suffix})"


def _host_display_name(value: str) -> str:
    record = _host_record(value)
    if record is None:
        return str(value or "")
    host_id = str(record.get("host_id") or "")
    locale_key = _HOST_LOCALE_KEYS.get(host_id)
    if locale_key:
        return _t(locale_key)
    return f"{str(record.get('common_name') or '').strip()} ({str(record.get('scientific_name') or '').strip()})"


def _host_values_for_workflow(workflow_type: str) -> tuple[str, ...]:
    workflow_level = _WORKFLOW_LEVEL_BY_TYPE.get(workflow_type)
    return tuple(
        str(record.get("scientific_name") or "").strip()
        for record in list_hosts()
        if workflow_level in set(record.get("workflow_levels") or ())
    )


def _widget_initial_kwargs(state: Mapping[str, Any], key: str, **defaults: Any) -> dict[str, Any]:
    return {} if key in state else defaults


def create_agent_formal_draft(
    *,
    project_name: str,
    host: str,
    workflow_type: str,
    design_goal: str,
    repository: PlantProjectDraftRepository | None = None,
) -> Any:
    """Create a cold-reopenable project through the existing Formal draft boundary."""
    from core.design_session import DesignSession

    name = str(project_name or "").strip()
    goal = str(design_goal or "").strip()
    if not name:
        raise PlantProjectDraftError(_t("v1.ai_assisted_design.project_name_required"))
    if not goal:
        raise PlantProjectDraftError(_t("v1.ai_assisted_design.design_goal_required"))
    if workflow_type not in _PROJECT_TYPE_BY_WORKFLOW:
        raise PlantProjectDraftError(_t("v1.ai_assisted_design.design_type_required"))
    record = _host_record(host)
    workflow_level = _WORKFLOW_LEVEL_BY_TYPE[workflow_type]
    if record is None or workflow_level not in set(record.get("workflow_levels") or ()):
        raise PlantProjectDraftError(_t("v1.ai_assisted_design.host_not_supported_by_design_type"))

    formal_host = _host_storage_value(record)
    project_type = _PROJECT_TYPE_BY_WORKFLOW[workflow_type]
    definition = normalize_project_definition(
        {
            "project_name": name,
            "plant_host": formal_host,
            "application_mode": "尚未确定",
            "transient_expression_system": "尚未确定",
            "tissue_specificity_requirement": "尚未确定",
            "inducibility_requirement": "尚未确定",
        },
        fallback_host=formal_host,
    )
    definition["expression_target"] = goal
    formal_state = {
        "formal_project_name": name,
        "formal_project_host": formal_host,
        "formal_expression_target": goal,
        "formal_project_type": project_type,
        "formal_design_scenario": "standard_plant_expression_vector",
        "formal_project_definition": definition,
    }
    saved = save_formal_project_draft(
        project_name=name,
        project_id="",
        workflow_type=workflow_type,
        current_step=1,
        design_session=DesignSession(step=1, host=formal_host, tag="No tag"),
        formal_state=formal_state,
        project_definition=definition,
        repository=repository or PlantProjectDraftRepository(),
    )
    return saved


def _key(name: str) -> str:
    return f"{_SESSION_PREFIX}{name}"


def _semantic_enum_value(value: Any) -> str:
    """Return a stable value even when Streamlit reloads an Enum class."""
    return str(getattr(value, "value", value) or "").strip()


def _result_state_is(result: Any, expected: AgentRunState) -> bool:
    return _strict_enum_member(getattr(result, "state", None), expected)


def _candidate_review_ready(candidate: Any) -> bool:
    """Gate review presentation on stable candidate and validation values."""
    validation = getattr(candidate, "deterministic_validation", None)
    return (
        _strict_enum_member(
            getattr(candidate, "state", None), CandidateState.VALIDATED_CANDIDATE
        )
        and _strict_enum_member(
            getattr(validation, "status", None), DeterministicValidationStatus.PASS
        )
    )


def _strict_enum_member(value: Any, expected: Enum) -> bool:
    """Accept the expected Enum family across reloads, never value-like impostors."""
    if not isinstance(value, Enum) or not isinstance(expected, Enum):
        return False
    value_type = type(value)
    expected_type = type(expected)
    return (
        value_type.__module__ == expected_type.__module__
        and value_type.__qualname__ == expected_type.__qualname__
        and value.name == expected.name
        and value.value == expected.value
    )


def _clear_derived(state: MutableMapping[str, Any]) -> None:
    for name in (
        "run_result",
        "candidate_id",
        "selected_candidate_id",
        "adoption_preview",
        "adoption_receipt",
        "error",
        "screen",
        "generated_signature",
    ):
        state.pop(_key(name), None)


def _clear_request_form(state: MutableMapping[str, Any]) -> None:
    for field in _REQUEST_WIDGET_FIELDS:
        state.pop(_key(field), None)
    for name in ("form_snapshot", "restore_form_pending", "missing_input_codes", "missing_input_fields"):
        state.pop(_key(name), None)
    for key in tuple(state):
        if str(key).startswith(_key("component_choice_")):
            state.pop(key, None)


def _capture_request_form(
    state: MutableMapping[str, Any],
    *,
    project_id: str,
    workflow_type: str,
    host: str,
    user_intent: str,
    cds: str,
    component_ids: str,
    component_choices: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Keep widget-independent values while the form is absent from a rerun."""
    snapshot = {
        "project_id": str(project_id),
        "workflow": str(workflow_type),
        "host": str(host),
        "user_intent": str(user_intent),
        "cds": str(cds),
        "component_ids": str(component_ids),
        "component_choices": dict(component_choices or {}),
    }
    state[_key("form_snapshot")] = snapshot
    return snapshot


def _restore_request_form(
    state: MutableMapping[str, Any], *, project_id: str, workflow_type: str
) -> bool:
    if not state.pop(_key("restore_form_pending"), False):
        return False
    snapshot = state.get(_key("form_snapshot"))
    if (
        not isinstance(snapshot, Mapping)
        or str(snapshot.get("project_id") or "") != str(project_id)
        or str(snapshot.get("workflow") or "") != str(workflow_type)
    ):
        _clear_request_form(state)
        return False
    for field in _REQUEST_WIDGET_FIELDS:
        if field in snapshot:
            state[_key(field)] = snapshot[field]
    choices = snapshot.get("component_choices")
    if isinstance(choices, Mapping):
        for role, component_id in choices.items():
            state[_key(f"component_choice_{role}")] = str(component_id)
    return True


def _needs_input_presentation(needs: Any) -> dict[str, Any]:
    missing_role_messages = {
        "promoter": _t("v1.ai_assisted_design.missing_promoter_candidate"),
        "3_prime_regulatory_region": _t("v1.ai_assisted_design.missing_three_prime_candidate"),
    }
    exact = {
        ("MISSING_CDS_OR_REFERENCE", "cds_or_reference_input"): (
            _t("v1.ai_assisted_design.provide_cds_sequence_cite_traceable_sequence_reference"),
            "cds",
        ),
        ("MISSING_CDS_OR_REFERENCE", "user_intent"): (
            _t("v1.ai_assisted_design.describe_design_request"),
            "user_intent",
        ),
        ("HOST_NOT_SELECTED", "host"): (
            _t("v1.ai_assisted_design.select_plant_host_supported_by_design_type"),
            "host",
        ),
        ("COMPONENT_RIGHTS_UNRESOLVED", "component_references"): (
            _t("v1.ai_assisted_design.select_eligible_component_for_missing_role"),
            "component_choices",
        ),
    }
    by_code = {
        "MISSING_VERIFIED_SEQUENCE": (
            _t("v1.ai_assisted_design.provide_verifiable_sequence_information"),
            "component_ids",
        ),
        "ASSISTED_COMPONENT_SEQUENCE_REQUIRED": (
            _t("v1.ai_assisted_design.provide_referenced_component_sequence"),
            "component_ids",
        ),
        "COMPONENT_RIGHTS_UNRESOLVED": (
            _t("v1.ai_assisted_design.review_component_source_and_use"),
            "component_ids",
        ),
        "PROVIDER_FAILURE": (
            _t("v1.ai_assisted_design.retry_request_no_project_changes"),
            "",
        ),
    }
    resolved: list[tuple[str, str]] = []
    for need in tuple(needs or ()):
        key = (
            _semantic_enum_value(getattr(need, "code", "")),
            str(getattr(need, "field", "") or ""),
        )
        details = getattr(need, "details", {})
        missing_roles = (
            tuple(str(role) for role in details.get("missing_roles") or ())
            if isinstance(details, Mapping)
            else ()
        )
        if key == ("COMPONENT_RIGHTS_UNRESOLVED", "component_references") and missing_roles:
            resolved.extend(
                (
                    missing_role_messages.get(
                        role,
                        _t("v1.ai_assisted_design.select_eligible_component_for_missing_role"),
                    ),
                    "component_choices",
                )
                for role in missing_roles
            )
            continue
        resolved.append(
            exact.get(key)
            or by_code.get(key[0])
            or (
                _t("v1.ai_assisted_design.complete_request_no_project_changes"),
                "",
            )
        )
    if not resolved:
        resolved.append((_t("v1.ai_assisted_design.complete_request_information"), ""))
    return {
        "title": _t("v1.ai_assisted_design.candidate_not_ready_title"),
        "messages": tuple(dict.fromkeys(item[0] for item in resolved)),
        "fields": tuple(dict.fromkeys(item[1] for item in resolved if item[1])),
        "status": _t("v1.ai_assisted_design.complete_following_information_no_project_changes"),
    }


def _request_signature(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _component_references(raw_ids: str, repository: V2ComponentRepository) -> tuple[ComponentReference, ...]:
    component_ids = tuple(dict.fromkeys(item.strip() for item in raw_ids.split(",") if item.strip()))
    references: list[ComponentReference] = []
    for component_id in component_ids:
        record = repository.resolve(component_id)
        if record is None:
            raise ValueError(f"Unknown Component Library V2 identity: {component_id}")
        references.append(
            ComponentReference(
                component_id=record.component_id,
                role=record.roles[0] if record.roles else "",
                tier=record.tier,
                evidence_references=record.evidence_references,
                provenance_references=record.provenance_references,
                library_tier=record.library_tier,
                canonical_v2_component_id=record.canonical_v2_component_id,
                sequence_sha256=record.sequence_sha256,
            )
        )
    return tuple(references)


def _candidate_for_result(result: Any, state: Mapping[str, Any]) -> AgentCandidate | None:
    candidates = tuple(getattr(result, "candidates", ()) or ())
    selected_id = str(state.get(_key("selected_candidate_id")) or "")
    if selected_id:
        return next((item for item in candidates if item.candidate_id == selected_id), None)
    return candidates[0] if candidates else None


def _safe_error_message(code: str, message: str = "") -> str:
    messages = {
        "api_key_missing": _t("v1.ai_assisted_design.provider_not_configured_candidate_not_generated_retry"),
        "provider_unavailable": _t("v1.ai_assisted_design.provider_unavailable_candidate_not_generated_retry"),
        "provider_timeout": _t("v1.ai_assisted_design.provider_timeout_candidate_not_generated_retry"),
        "malformed_response": _t("v1.ai_assisted_design.provider_response_contract_invalid"),
        "unsupported_model_response": _t("v1.ai_assisted_design.provider_response_structure_unsupported"),
        "governance_violation": _t("v1.ai_assisted_design.candidate_governance_check_failed"),
    }
    return messages.get(str(code), _t("v1.ai_assisted_design.request_not_completed_no_project_changes"))


def _load_adopted_readback(backend: AgentBackend, project_id: str) -> tuple[Any, Any] | None:
    """Return only a project-matched candidate with an authoritative receipt."""
    try:
        formal = backend.adoption.formal_repository.load(project_id)
        marker = dict(getattr(formal, "extra_fields", {}) or {}).get("agent_adoption")
        if not isinstance(marker, Mapping):
            return None
        candidate_id = str(marker.get("candidate_id") or "")
        expected_digest = str(marker.get("candidate_digest") or "")
        payload = backend.store.load_payload(candidate_id, verify=True) or {}
        if str(payload.get("project_id") or "") != project_id:
            return None
        receipt_id = str(payload.get("adoption_receipt_id") or "")
        receipt = backend.store.load_receipt(receipt_id)
        candidate = backend.store.load(candidate_id)
        if (
            not backend.store.receipt_is_authoritative(receipt_id)
            or receipt.project_id != project_id
            or receipt.candidate_id != candidate_id
            or receipt.candidate_digest != expected_digest
            or not _strict_enum_member(candidate.state, CandidateState.USER_ADOPTED)
            or not _strict_enum_member(
                backend._revalidate_adoption_authority(candidate).deterministic_validation.status,
                DeterministicValidationStatus.PASS,
            )
        ):
            return None
        return candidate, receipt
    except (CandidateStoreError, PlantProjectDraftError, OSError, ValueError, TypeError):
        return None


def _project_requires_recovery(backend: AgentBackend, project_id: str) -> bool:
    """Conservatively detect unresolved adoption state after a cold start."""
    try:
        if any(row.get("project_id") == project_id for row in backend.store.list_recovery_markers()):
            return True
        return any(
            row.get("project_id") == project_id
            and row.get("status") in {"IN_PROGRESS", "RECOVERY_REQUIRED"}
            for row in backend.store.list_journal()
        )
    except CandidateStoreError:
        return True


def _render_header() -> None:
    st.title(_t("v1.common.ai_assisted_design"))
    st.markdown(
        '<div class="agent-page-subtitle">'
        + _t(
            "v1.ai_assisted_design."
            "generate_reviewable_candidate_project_confirmed_design_information"
        )
        + "</div>",
        unsafe_allow_html=True,
    )


def _render_project_context(project_id: str, project_name: str, project_host: str = "") -> None:
    display_id = project_id
    if project_id.startswith("plant-draft-") and len(project_id) > 20:
        display_id = f"{_t('v1.ai_assisted_design.ai_assisted_design_project')} · {project_id[-8:].upper()}"
    st.markdown(
        '<div class="agent-context-bar">'
        f'<div><span>{_t("v1.common.current_project")}</span><strong>{escape(project_name or _t("v1.ai_assisted_design.unnamed_project"))}</strong></div>'
        f'<div><span>{_t("v1.ai_assisted_design.project_id")}</span><strong title="{_t("v1.ai_assisted_design.full_project_identifier")}: {escape(project_id)}">{escape(display_id)}</strong></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    if project_host:
        st.caption(_t("v1.ai_assisted_design.plant_host_value", value=_host_display_name(project_host)))


def _bind_created_project(state: MutableMapping[str, Any], draft: Any, design_goal: str) -> None:
    snapshot = dict(getattr(draft, "manual_review_state", {})).get("formal_project_workflow_v1")
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    definition = dict(snapshot.get("project_definition") or {})
    definition.setdefault("project_name", str(getattr(draft, "project_name", "") or ""))
    definition.setdefault("plant_host", str(getattr(draft, "host_context", "") or ""))
    _clear_derived(state)
    _clear_request_form(state)
    state["mvp_project_id"] = draft.project_id
    state["formal_last_saved_draft_id"] = draft.project_id
    state["formal_project_name"] = draft.project_name
    state["formal_project_host"] = str(definition.get("plant_host") or draft.host_context or "")
    state["formal_expression_target"] = design_goal
    state["formal_project_definition"] = definition
    state["formal_project_type"] = _PROJECT_TYPE_BY_WORKFLOW.get(draft.workflow_type, "single_gene")
    state["formal_design_scenario"] = "standard_plant_expression_vector"
    for field in (
        "project_name",
        "host",
        "material",
        "application_mode",
        "transient_expression_system",
        "tissue_specificity_requirement",
        "tissue_target",
        "inducibility_requirement",
        "induction_notes",
        "localization_target",
        "compatibility_review_required",
        "legacy_application_mode",
        "legacy_expression_mode",
    ):
        definition_field = "plant_host" if field == "host" else field
        state[f"formal_step1_{field}"] = definition.get(definition_field, "")
    state[_key("user_intent")] = design_goal
    state[_key("entry_mode")] = "current"
    state[_key("created_project_id")] = draft.project_id


def _render_new_project_form(state: MutableMapping[str, Any]) -> None:
    st.subheader(_t("v1.ai_assisted_design.new_ai_assisted_design"))
    st.caption(_t("v1.ai_assisted_design.enter_minimum_information_formal_project_draft_candidate"))
    project_name = st.text_input(_t("v1.ai_assisted_design.project_name"), key=_key("new_project_name"))
    design_goal = st.text_area(
        _t("v1.ai_assisted_design.design_goal"),
        height=120,
        placeholder=_t("v1.ai_assisted_design.example_prepare_reviewable_candidate_rice_single_gene"),
        key=_key("new_design_goal"),
    )
    workflow_type = st.segmented_control(
        _t("v1.ai_assisted_design.design_type_required"),
        ("single_gene", "multi_tu"),
        format_func={"single_gene": _t("v1.ai_assisted_design.single_gene_complete_vector"), "multi_tu": _t("v1.ai_assisted_design.general_multi_tu_assembly")}.get,
        key=_key("new_workflow_type"),
        **_widget_initial_kwargs(state, _key("new_workflow_type"), default="single_gene"),
    )
    host_values = _host_values_for_workflow(str(workflow_type or ""))
    current_host = str(state.get(_key("new_host")) or "")
    if current_host and current_host not in host_values:
        state.pop(_key("new_host"), None)
    host = st.selectbox(
        _t("v1.ai_assisted_design.plant_host_required"),
        host_values,
        index=None,
        placeholder=_t("v1.ai_assisted_design.select_plant_host_supported_by_design_type"),
        format_func=_host_display_name,
        key=_key("new_host"),
    )
    actions = st.columns((1.5, 0.7, 4))
    if actions[0].button(
        _t("v1.ai_assisted_design.create_project_start_design"),
        type="primary",
        disabled=not bool(project_name.strip() and design_goal.strip() and workflow_type and host),
        key="intelligent_design_create_project",
    ):
        try:
            draft = create_agent_formal_draft(
                project_name=project_name,
                host=str(host or ""),
                workflow_type=str(workflow_type or ""),
                design_goal=design_goal,
            )
        except (PlantProjectDraftError, OSError, ValueError) as exc:
            st.error(str(exc) or _t("v1.ai_assisted_design.project_draft_could_not_created_check_inputs"))
        else:
            _bind_created_project(state, draft, design_goal.strip())
            st.rerun()
    if actions[1].button(_t("v1.common.cancel"), key="intelligent_design_cancel_new"):
        state.pop(_key("entry_mode"), None)
        st.rerun()


def _render_component_shortlist(
    shortlist: Mapping[str, Any],
    state: MutableMapping[str, Any],
    *,
    attention: bool = False,
) -> tuple[tuple[str, ...], dict[str, str]]:
    selected_ids: list[str] = []
    choices: dict[str, str] = {}
    st.markdown(f'<div class="agent-section-title">{_t("v1.ai_assisted_design.available_components")}</div>', unsafe_allow_html=True)
    st.caption(_t("v1.ai_assisted_design.candidates_come_components_available_project_bound_request"))
    for group in tuple(shortlist.get("roles") or ()):
        role = str(group.get("role") or "")
        label = str(group.get("label") or role)
        existing = group.get("existing")
        options = tuple(group.get("options") or ())
        direct = tuple(item for item in options if item.get("selectable"))
        assisted = tuple(item for item in options if item.get("sequence_required"))
        st.markdown(f"**{escape(label)}**")
        if isinstance(existing, Mapping):
            component_id = str(existing.get("component_id") or "")
            selected_ids.append(component_id)
            choices[role] = component_id
            st.write(f"{existing.get('name') or component_id} · {_t('v1.ai_assisted_design.confirmed_project')}")
            st.caption(f"{_t('v1.ai_assisted_design.source_identity')}: {component_id} · {existing.get('tier') or 'DIRECT_USE'}")
        elif direct:
            option_by_id = {str(item["component_id"]): item for item in direct}
            choice = st.selectbox(
                _t("v1.ai_assisted_design.select_candidate", value=label),
                tuple(option_by_id),
                index=None,
                placeholder=_t("v1.ai_assisted_design.select_eligible_candidate", value=label),
                format_func=lambda component_id, rows=option_by_id: rows[component_id]["name"],
                key=_key(f"component_choice_{role}"),
            )
            if choice:
                selected_ids.append(str(choice))
                choices[role] = str(choice)
                st.caption(f"{_t('v1.ai_assisted_design.source_identity')}: {choice} · DIRECT_USE")
        else:
            st.warning(_t("v1.ai_assisted_design.no_eligible_candidate_available_host", value=label))
        if assisted:
            names = "；".join(
                f"{item['name']}（{item['component_id']}）" for item in assisted
            )
            st.caption(_t("v1.ai_assisted_design.candidates_requiring_user_provided_sequence_they_not", value=names))
    if attention:
        st.error(_t("v1.ai_assisted_design.complete_selection_directly_usable_components_currently_missing"))
    st.info(_t("v1.ai_assisted_design.review_component_candidates_here_confirm_vector_backbone"))
    return tuple(selected_ids), choices


def _render_initial(
    backend: AgentBackend | None,
    project_id: str,
    workflow_type: str,
    project_host: str,
    state: MutableMapping[str, Any],
) -> None:
    adapter = AgentProductAdapter(
        project_repository=backend.adoption.formal_repository if backend is not None else None,
        component_repository=backend.service.component_repository if backend is not None else None,
    )
    try:
        project_context = adapter.read_project_context(project_id) if project_id else {"available": False}
    except (PlantProjectDraftError, OSError, ValueError, TypeError):
        project_context = {"project_id": project_id, "available": False}
    workflow_type = str(project_context.get("workflow_type") or workflow_type)
    _restore_request_form(state, project_id=project_id, workflow_type=workflow_type)
    resolved_workflow = workflow_type
    attention_fields = set(state.get(_key("missing_input_fields")) or ())
    projected_intent = str(project_context.get("user_intent") or "")
    if _key("user_intent") not in state and projected_intent:
        state[_key("user_intent")] = projected_intent
    st.markdown(f'<div class="agent-section-title">{_t("v1.ai_assisted_design.design_request")}</div>', unsafe_allow_html=True)
    user_intent = st.text_area(
        _t("v1.ai_assisted_design.describe_plant_expression_design_review"),
        placeholder=_t("v1.ai_assisted_design.example_prepare_single_gene_candidate_project_while"),
        height=150,
        key=_key("user_intent"),
    )
    authoritative_project_host = str(project_context.get("host") or project_host)
    default_host_record = _host_record(authoritative_project_host)
    default_host = (
        str(default_host_record.get("scientific_name") or "")
        if default_host_record is not None
        else ""
    )
    host_values = _host_values_for_workflow(resolved_workflow)
    if _key("host") not in state and default_host in host_values:
        state[_key("host")] = default_host
    host = st.selectbox(
        _t("v1.ai_assisted_design.plant_host"),
        host_values,
        index=None,
        placeholder=_t("v1.ai_assisted_design.select_plant_host"),
        format_func=_host_display_name,
        key=_key("host"),
        disabled=bool(default_host),
    )
    st.caption(_t("v1.ai_assisted_design.design_type") + ": " + (_t("v1.ai_assisted_design.single_gene") if resolved_workflow == "single_gene" else resolved_workflow) + " · " + _t("v1.ai_assisted_design.bound_project"))
    projected_cds = project_context.get("cds")
    projected_cds = dict(projected_cds) if isinstance(projected_cds, Mapping) else {}
    if _key("cds") not in state and projected_cds.get("value"):
        state[_key("cds")] = str(projected_cds["value"])
    with st.container(key="agent_cds_input_attention" if "cds" in attention_fields else "agent_cds_input"):
        cds = st.text_area(
            _t("v1.ai_assisted_design.cds_traceable_sequence_reference"),
            placeholder=_t("v1.ai_assisted_design.paste_cds_enter_traceable_sequence_reference_project"),
            height=120,
            key=_key("cds"),
            disabled=bool(projected_cds.get("value")),
        )
        if projected_cds.get("value"):
            source_name = str(projected_cds.get("source_name") or "Formal Step 2")
            st.caption(f"{_t('v1.ai_assisted_design.reused_project')} · {source_name}")
        if "cds" in attention_fields:
            st.error(_t("v1.ai_assisted_design.provide_cds_sequence_cite_traceable_sequence_reference"))
    if _key("workflow") not in state:
        state[_key("workflow")] = resolved_workflow
    existing_components = list(project_context.get("existing_components") or ())
    if project_context.get("limitations"):
        st.warning(_t("v1.ai_assisted_design.some_existing_components_project_not_passed_eligibility"))
    shortlist = adapter.component_shortlist(
        workflow_type=resolved_workflow,
        host=str(host or ""),
        existing_components=existing_components,
    )
    if shortlist.get("supported"):
        selected_component_ids, component_choices = _render_component_shortlist(
            shortlist,
            state,
            attention="component_choices" in attention_fields,
        )
    else:
        selected_component_ids, component_choices = (), {}
        st.info(_t("v1.ai_assisted_design.design_type_does_not_yet_support_component"))
    state[_key("component_ids")] = ", ".join(selected_component_ids)

    payload = {
        "project_id": project_id,
        "workflow": resolved_workflow,
        "host": host,
        "user_intent": user_intent.strip(),
        "cds": cds.strip(),
        "component_ids": selected_component_ids,
    }
    signature = _request_signature(payload)
    generated_signature = str(state.get(_key("generated_signature")) or "")
    if generated_signature and generated_signature != signature:
        _clear_derived(state)
        state.pop(_key("generated_signature"), None)

    unavailable = backend is None or not project_id
    if unavailable:
        st.info(_t("v1.ai_assisted_design.first_open_readable_formal_project_project_center"))
    if st.button(
        _t("v1.ai_assisted_design.edit_request") if attention_fields else _t("v1.ai_assisted_design.start_ai_assisted_design"),
        type="primary",
        disabled=unavailable or not bool(user_intent.strip()),
        key="agent_generate_candidate_design",
    ):
        _capture_request_form(
            state,
            project_id=project_id,
            workflow_type=resolved_workflow,
            host=str(host or ""),
            user_intent=user_intent,
            cds=cds,
            component_ids=str(state.get(_key("component_ids")) or ""),
            component_choices=component_choices,
        )
        try:
            references = adapter.resolve_component_references(
                selected_component_ids,
                workflow_type=resolved_workflow,
                host=str(host or ""),
                existing_components=existing_components,
            )
            request = AgentRequest(
                workflow_type=resolved_workflow,
                host=host or None,
                user_intent=user_intent,
                cds_or_reference_input=cds.strip() or None,
                component_references=references,
                evidence_references=tuple(
                    dict.fromkeys(
                        evidence
                        for reference in references
                        for evidence in reference.evidence_references
                    )
                ),
                project_id=project_id,
                context={
                    "project_id": project_id,
                    "cds_source": "formal_project" if projected_cds.get("value") else "user_input",
                },
            )
            with st.status(_t("v1.ai_assisted_design.generating_candidate_running_required_checks_wait"), expanded=True) as status:
                st.write(_t("v1.ai_assisted_design.read_current_project_context"))
                if not project_context.get("available"):
                    raise ValueError("current Formal project is unavailable")
                st.write(_t("v1.ai_assisted_design.request_structured_candidate"))
                result = backend.generate_and_validate(request)
                st.write(_t("v1.ai_assisted_design.bind_candidate_revision_project_identity"))
                status.update(label=_t("v1.ai_assisted_design.design_request_returned"), state="complete", expanded=False)
            state[_key("run_result")] = result
            state[_key("generated_signature")] = signature
            if _result_state_is(result, AgentRunState.NEEDS_INPUT):
                state[_key("screen")] = "initial"
                presentation = _needs_input_presentation(result.needs_input)
                state[_key("missing_input_codes")] = tuple(
                    _semantic_enum_value(getattr(need, "code", ""))
                    for need in result.needs_input
                )
                state[_key("missing_input_fields")] = presentation["fields"]
                state[_key("restore_form_pending")] = True
            else:
                state[_key("screen")] = (
                    "alternatives"
                    if _result_state_is(result, AgentRunState.ALTERNATIVES)
                    else "review"
                )
                state.pop(_key("missing_input_codes"), None)
                state.pop(_key("missing_input_fields"), None)
            state.pop(_key("error"), None)
            st.rerun()
        except (ValueError, CandidateStoreError) as exc:
            state[_key("error")] = _safe_error_message("", str(exc))
            state[_key("screen")] = "error"
            st.rerun()


def _render_needs_input(result: Any) -> None:
    presentation = _needs_input_presentation(result.needs_input)
    st.markdown(
        '<div class="agent-state-band warning">'
        f'<strong>{escape(presentation["title"])}</strong>'
        f'<span>{escape(presentation["status"])}</span></div>',
        unsafe_allow_html=True,
    )
    for message in presentation["messages"]:
        st.markdown(
            f'<div class="agent-input-guidance">{escape(message)}</div>',
            unsafe_allow_html=True,
        )


def _render_components(candidate: AgentCandidate) -> None:
    st.markdown(f'<div class="agent-section-title">{_t("v1.ai_assisted_design.component_identity_admission_mode")}</div>', unsafe_allow_html=True)
    if not candidate.component_references:
        st.caption(_t("v1.ai_assisted_design.no_component_identity_bound_candidate_request"))
        return
    for item in candidate.component_references:
        css = "reference" if item.tier.value == "REFERENCE_ONLY" else "assisted" if item.tier.value == "USER_SEQUENCE_ASSISTED" else ""
        st.markdown(
            '<div class="agent-component-row">'
            f'<div><code>{escape(item.canonical_v2_component_id)}</code><br><small>{escape(item.role or _t("v1.ai_assisted_design.unspecified_role"))}</small></div>'
            f'<div>{escape(item.library_tier)}</div><div><span class="agent-status {css}">{escape(item.tier.value)}</span></div>'
            '</div>',
            unsafe_allow_html=True,
        )


def _render_candidate(candidate: AgentCandidate, backend: AgentBackend, state: MutableMapping[str, Any]) -> None:
    validation = candidate.deterministic_validation
    ready = _candidate_review_ready(candidate)
    band = "ready" if ready else "warning"
    st.markdown(
        f'<div class="agent-state-band {band}"><strong>{escape(_semantic_enum_value(candidate.state))}</strong>'
        f'<span>{_t("v1.ai_assisted_design.state_records_software_design_adoption_only_it")}</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="agent-facts">'
        f'<div class="agent-fact"><span>{_t("v1.ai_assisted_design.candidate_id")}</span><strong>{escape(candidate.candidate_id)}</strong></div>'
        f'<div class="agent-fact"><span>{_t("v1.ai_assisted_design.plant_host")}</span><strong>{escape(candidate.host or _t("v1.ai_assisted_design.not_provided"))}</strong></div>'
        f'<div class="agent-fact"><span>{_t("v1.ai_assisted_design.workflow")}</span><strong>{escape(candidate.workflow_type)}</strong></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="agent-section-title">{_t("v1.ai_assisted_design.candidate_notes")}</div>', unsafe_allow_html=True)
    st.write(candidate.rationale or _t("v1.ai_assisted_design.no_additional_candidate_notes_were_returned"))
    _render_components(candidate)

    left, right = st.columns(2)
    with left:
        st.markdown(f'<div class="agent-section-title">{_t("v1.ai_assisted_design.deterministic_check")}</div>', unsafe_allow_html=True)
        st.write(f"{_t('v1.ai_assisted_design.check_status')}: {_semantic_enum_value(validation.status)}")
        for check in validation.checks:
            st.caption(check)
        for reason in validation.blocking_reasons:
            st.warning(reason)
    with right:
        st.markdown(f'<div class="agent-section-title">{_t("v1.ai_assisted_design.source_records")}</div>', unsafe_allow_html=True)
        st.write(f"{_t('v1.ai_assisted_design.provider')}: {candidate.provider_metadata.get('provider') or 'unknown'}")
        st.write(f"{_t('v1.ai_assisted_design.model')}: {candidate.provider_metadata.get('model') or 'unknown'}")
        for reference in candidate.provenance_references or candidate.evidence_references:
            st.caption(reference)

    actions = st.columns((1, 1, 1))
    if actions[0].button(_t("v1.ai_assisted_design.edit_request"), key="agent_edit_request"):
        state[_key("screen")] = "initial"
        st.rerun()
    if actions[1].button(_t("v1.ai_assisted_design.compare_candidates"), disabled=True, help=_t("v1.ai_assisted_design.available_only_when_multiple_candidates_returned"), key="agent_compare_disabled"):
        pass
    if actions[2].button(_t("v1.ai_assisted_design.review_adoption"), type="primary", disabled=not ready, key="agent_review_adoption"):
        try:
            state[_key("adoption_preview")] = backend.service.build_adoption_preview(candidate)
            state[_key("selected_candidate_id")] = candidate.candidate_id
            state[_key("screen")] = "adoption"
            st.rerun()
        except (ValueError, CandidateStoreError, AgentServiceError) as exc:
            state[_key("error")] = _safe_error_message("", str(exc))
            state[_key("screen")] = "error"
            st.rerun()


def _render_alternatives(result: Any, backend: AgentBackend, state: MutableMapping[str, Any]) -> None:
    st.markdown(
        _t("v1.ai_assisted_design.multiple_candidates_available_comparison_candidates_displayed_equal"),
        unsafe_allow_html=True,
    )
    candidates = tuple(result.candidates or ())
    columns = st.columns(min(len(candidates), 3))
    for index, candidate in enumerate(candidates):
        with columns[index % len(columns)]:
            with st.container(border=True, key=f"agent_alternative_{candidate.candidate_id}"):
                st.markdown(f"**{candidate.candidate_id}**")
                st.caption(f"{candidate.host or _t('v1.ai_assisted_design.not_provided')} · {candidate.workflow_type}")
                st.write(candidate.rationale or _t("v1.ai_assisted_design.no_additional_notes"))
                st.caption(_t("v1.ai_assisted_design.deterministic_check", value=candidate.deterministic_validation.status.value))
                if st.button(_t("v1.ai_assisted_design.select_review"), key=f"agent_select_{candidate.candidate_id}"):
                    state[_key("selected_candidate_id")] = candidate.candidate_id
                    state[_key("screen")] = "review"
                    st.rerun()
    if result.alternatives:
        st.markdown(_t("v1.ai_assisted_design.provider_provided_rationale_differences"), unsafe_allow_html=True)
        for alternative in result.alternatives:
            st.write(f"{alternative.alternative_id}: {alternative.rationale}")
            for difference in alternative.differences:
                st.caption(difference)


def _render_adoption(candidate: AgentCandidate, backend: AgentBackend, project_id: str, state: MutableMapping[str, Any]) -> None:
    preview = state.get(_key("adoption_preview"))
    if preview is None or preview.candidate_id != candidate.candidate_id:
        state[_key("screen")] = "review"
        st.warning(_t("v1.ai_assisted_design.adoption_preview_expired_review_candidate_again"))
        return
    st.markdown(
        '<div class="agent-state-band warning"><strong>'
        + _t("v1.ai_assisted_design.confirm_adoption")
        + '</strong><span>'
        + _t("v1.ai_assisted_design.candidate_not_been_written_formal_project_confirmation")
        + '</span></div>',
        unsafe_allow_html=True,
    )
    with st.container(border=True, key="agent_adoption_summary"):
        st.write(f"{_t('v1.ai_assisted_design.target_project')}: {project_id}")
        st.write(f"{_t('v1.ai_assisted_design.candidate_id')}: {candidate.candidate_id}")
        st.write(f"{_t('v1.ai_assisted_design.candidate_digest')}: {candidate_digest(candidate)}")
        st.markdown(f"**{_t('v1.ai_assisted_design.records_write_project')}**")
        for change in preview.intended_project_changes:
            st.write(f"- {change}")
        st.markdown(f"**{_t('v1.ai_assisted_design.preconditions')}**")
        for condition in preview.deterministic_preconditions:
            st.write(f"- {condition}")
    acknowledged = st.checkbox(
        _t("v1.ai_assisted_design.i_reviewed_project_candidate_identity_deterministic_checks"),
        key=_key("adoption_ack"),
    )
    back, confirm = st.columns((1, 2))
    if back.button(_t("v1.ai_assisted_design.back_candidate"), key="agent_back_to_candidate"):
        state[_key("screen")] = "review"
        st.rerun()
    if confirm.button(
        _t("v1.ai_assisted_design.confirm_adoption_project"),
        type="primary",
        disabled=not acknowledged,
        key="agent_confirm_adoption",
    ):
        token = f"confirm-{secrets.token_urlsafe(18)}"
        try:
            confirmed = backend.service.confirm_candidate(candidate, confirmation_id=token, preview=preview)
            receipt = backend.adopt(
                AdoptionRequest(
                    candidate_id=confirmed.candidate_id,
                    project_id=project_id,
                    candidate_digest=candidate_digest(confirmed),
                    confirmation_token=token,
                )
            )
            if not backend.store.receipt_is_authoritative(receipt.receipt_id):
                raise CandidateStoreError("adoption receipt is not authoritative")
            readback = _load_adopted_readback(backend, project_id)
            if readback is None or readback[1].receipt_id != receipt.receipt_id:
                raise CandidateStoreError("adoption could not be verified after cold readback")
            state[_key("adoption_receipt")] = receipt
            state[_key("screen")] = "adopted"
            st.rerun()
        except (CandidateStoreError, AgentServiceError) as exc:
            message = str(exc).casefold()
            recovery = "recovery required" in message
            state[_key("error")] = (
                _t("v1.ai_assisted_design.recovery_check_required_plain")
                if recovery
                else _t("v1.ai_assisted_design.adoption_not_completed_check_revision")
            )
            state[_key("screen")] = "recovery" if recovery else "error"
            st.rerun()


def _render_adopted(candidate: AgentCandidate, receipt: Any) -> None:
    st.markdown(
        '<div class="agent-receipt"><strong>USER_ADOPTED</strong>'
        f'<span>{_t("v1.ai_assisted_design.user_explicitly_confirmed_software_design_candidate_state")}</span>'
        '<dl>'
        f'<div><dt>{_t("v1.ai_assisted_design.project_label")}</dt><dd>{escape(receipt.project_id)}</dd></div>'
        f'<div><dt>{_t("v1.ai_assisted_design.candidate_id")}</dt><dd>{escape(receipt.candidate_id)}</dd></div>'
        f'<div><dt>{_t("v1.ai_assisted_design.authenticated_receipt")}</dt><dd>{escape(receipt.receipt_id)}</dd></div>'
        f'<div><dt>{_t("v1.ai_assisted_design.adopted_at")}</dt><dd>{escape(receipt.adopted_at)}</dd></div>'
        f'<div><dt>{_t("v1.ai_assisted_design.candidate_revision")}</dt><dd>{receipt.candidate_revision}</dd></div>'
        f'<div><dt>{_t("v1.ai_assisted_design.check_version")}</dt><dd>{escape(receipt.validation_version)}</dd></div>'
        '</dl></div>',
        unsafe_allow_html=True,
    )
    _render_components(candidate)
    st.caption(_t("v1.ai_assisted_design.state_records_software_design_adoption_only_it"))


def render_agent_workspace(
    *,
    project_id: str,
    project_name: str,
    project_type: str = "",
    workflow_type: str = "",
    project_host: str = "",
    state: MutableMapping[str, Any] | None = None,
    backend: AgentBackend | None = None,
    open_project_center: Callable[[], None] | None = None,
    continue_to_expression: Callable[[str], None] | None = None,
    record_active_surface: Callable[[str], None] | None = None,
) -> None:
    """Render intelligent design over the adopted project-bound Agent contracts."""
    session = state if state is not None else st.session_state
    st.markdown(AGENT_CSS, unsafe_allow_html=True)
    with st.container(key="agent_v1_workspace"):
        _render_header()

        backend_key = _key("backend_project_id")
        if str(session.get(backend_key) or "") != project_id:
            created_here = str(session.get(_key("created_project_id")) or "") == project_id
            _clear_derived(session)
            if not created_here:
                _clear_request_form(session)
                session.pop(_key("entry_mode"), None)
            session[backend_key] = project_id
            session.pop(_key("backend"), None)
        if backend is None and project_id:
            backend = session.get(_key("backend"))
            if backend is None:
                backend = build_agent_backend(project_id, project_type)
                if backend is not None:
                    session[_key("backend")] = backend

        if backend is not None and project_id and record_active_surface is not None:
            record_active_surface("Agent V1 Workspace")

        if backend is not None and project_id:
            # Recovery is authoritative on cold read. Resolve it before loading
            # or presenting any adopted readback so a stale success cannot flash.
            requires_recovery = _project_requires_recovery(backend, project_id)
            if requires_recovery:
                session[_key("screen")] = "recovery"
                session[_key("error")] = (
                    f"RECOVERY_REQUIRED: {_t('v1.ai_assisted_design.recovery_check_required_plain')}"
                )
                _render_project_context(project_id, project_name, project_host)
                st.markdown(
                    '<div class="agent-state-band error"><strong>RECOVERY_REQUIRED: ' + _t("v1.ai_assisted_design.recovery_check_required_plain") +
                    f'<span>{escape(str(session[_key("error")]))}</span></div>',
                    unsafe_allow_html=True,
                )
                return
            readback = _load_adopted_readback(backend, project_id)
            if readback is not None:
                _render_project_context(project_id, project_name, project_host)
                _render_adopted(*readback)
                if continue_to_expression is not None and st.button(
                    _t("v1.ai_assisted_design.continue_expression_design"), type="primary", key="intelligent_design_continue_after_adoption"
                ):
                    continue_to_expression(project_id)
                return

        entry_mode = str(session.get(_key("entry_mode")) or "")
        if entry_mode == "new":
            if project_id:
                _render_project_context(project_id, project_name, project_host)
                st.info(_t("v1.ai_assisted_design.starting_new_project_creates_another_project_does"))
            _render_new_project_form(session)
            return
        if backend is None or not project_id:
            st.markdown(
                f'<div class="agent-section-title">'
                f'{_t("v1.ai_assisted_design.start_ai_assisted_design")}</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                _t(
                    "v1.ai_assisted_design."
                    "select_project_generate_candidate_confirm_manually"
                )
            )
            actions = st.columns((1.5, 1.5, 4))
            if actions[0].button(
                _t("v1.ai_assisted_design.start_new_project"),
                type="primary",
                key="intelligent_design_new",
            ):
                session[_key("entry_mode")] = "new"
                st.rerun()
            if actions[1].button(
                _t("v1.ai_assisted_design.start_existing_project"),
                key="intelligent_design_open_existing",
            ):
                if open_project_center is not None:
                    open_project_center()
            if project_id and backend is None:
                st.warning(_t("v1.ai_assisted_design.project_cannot_loaded_formal_project_storage_reopen"))
            return

        created_here = str(session.get(_key("created_project_id")) or "") == project_id
        if entry_mode != "current" and not created_here:
            _render_project_context(project_id, project_name, project_host)
            st.markdown(f'<div class="agent-section-title">{_t("v1.ai_assisted_design.choose_how_continue")}</div>', unsafe_allow_html=True)
            actions = st.columns((1.5, 1.1, 1.25, 2.4))
            if actions[0].button(
                _t("v1.ai_assisted_design.continue_project"),
                type="primary",
                key="intelligent_design_use_current",
            ):
                session[_key("entry_mode")] = "current"
                st.rerun()
            if actions[1].button(_t("v1.ai_assisted_design.switch_project"), key="intelligent_design_switch_project"):
                if open_project_center is not None:
                    open_project_center()
            if actions[2].button(_t("v1.ai_assisted_design.start_ai_assisted_design"), key="intelligent_design_start_another"):
                session[_key("entry_mode")] = "new"
                st.rerun()
            return

        _render_project_context(project_id, project_name, project_host)
        if continue_to_expression is not None and st.button(
            _t("v1.ai_assisted_design.view_project_expression_design"), key="intelligent_design_return_expression"
        ):
            continue_to_expression(project_id)

        screen = str(session.get(_key("screen")) or "initial")
        result = session.get(_key("run_result"))
        if screen in {"error", "recovery"}:
            css = "error" if screen == "recovery" else "warning"
            st.markdown(
                f'<div class="agent-state-band {css}"><strong>{"RECOVERY_REQUIRED: " if screen == "recovery" else ""}{_t("v1.ai_assisted_design.recovery_check_required_plain") if screen == "recovery" else _t("v1.ai_assisted_design.request_not_completed")}</strong>'
                f'<span>{escape(str(session.get(_key("error")) or _t("v1.ai_assisted_design.no_project_changes")))}</span></div>',
                unsafe_allow_html=True,
            )
            if screen != "recovery" and st.button(_t("v1.ai_assisted_design.return_request"), key="agent_error_return"):
                session[_key("screen")] = "initial"
                st.rerun()
            return
        resolved_workflow = workflow_type or (
            "multi_tu" if project_type in {"dual_tu", "multi_tu"} else "single_gene"
        )
        if result is not None and _result_state_is(result, AgentRunState.NEEDS_INPUT):
            session[_key("screen")] = "initial"
            _render_needs_input(result)
            _render_initial(backend, project_id, resolved_workflow, project_host, session)
            return
        if screen == "initial" or result is None:
            _render_initial(backend, project_id, resolved_workflow, project_host, session)
            return
        if _result_state_is(result, AgentRunState.FAILED):
            st.markdown(
                '<div class="agent-state-band error"><strong>' + _t("v1.ai_assisted_design.candidate_not_generated_plain") +
                f'<span>{escape(_safe_error_message(result.error_code, result.error_message))}</span></div>',
                unsafe_allow_html=True,
            )
            if st.button(_t("v1.ai_assisted_design.return_request"), key="agent_failed_return"):
                session[_key("screen")] = "initial"
                st.rerun()
            return
        if _result_state_is(result, AgentRunState.ALTERNATIVES) and screen == "alternatives":
            _render_alternatives(result, backend, session)
            return
        candidate = _candidate_for_result(result, session)
        if candidate is None:
            st.error(_t("v1.ai_assisted_design.backend_returned_no_reviewable_candidates_no_changes"))
            return
        session[_key("candidate_id")] = candidate.candidate_id
        if screen == "adoption":
            _render_adoption(candidate, backend, project_id, session)
        else:
            _render_candidate(candidate, backend, session)


__all__ = [
    "AGENT_STATE_DIR_ENV",
    "build_agent_backend",
    "create_agent_formal_draft",
    "default_agent_state_dir",
    "render_agent_workspace",
    "resolve_formal_repository",
]
