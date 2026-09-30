from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from typing import Any, Mapping

from core.design_session import DesignSession
from services.plant_project_draft_repository import (
    PlantProjectDraftRepository,
    require_active_project,
)
from services.plant_project_draft_schema import (
    PlantDesignProjectDraft,
    PlantProjectDraftError,
    new_project_id,
    update_plant_project_draft,
)


FORMAL_DRAFT_STATE_KEY = "formal_project_workflow_v1"
FORMAL_DRAFT_STATE_VERSION = "1.0.0"
FORMAL_PRODUCT_NAVIGATION_STATE_KEY = "formal_product_navigation_v1"
FORMAL_PRODUCT_NAVIGATION_STATE_VERSION = "1.0.0"
PRODUCT_SURFACE_AGENT = "Agent V1 Workspace"
PRODUCT_SURFACE_EXPRESSION = "Expression Design"
VALID_PRODUCT_SURFACES = frozenset(
    {PRODUCT_SURFACE_AGENT, PRODUCT_SURFACE_EXPRESSION}
)
STATUS_DRAFT = "draft"
STATUS_COMPLETED = "completed"
WORKFLOW_SINGLE_GENE = "single_gene"
WORKFLOW_MULTI_TU = "multi_tu"
WORKFLOW_GATE3_PATHWAY = "gate3_pathway"
VALID_WORKFLOW_TYPES = frozenset(
    {WORKFLOW_SINGLE_GENE, WORKFLOW_MULTI_TU, WORKFLOW_GATE3_PATHWAY}
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json_copy(value: Any, *, label: str) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise PlantProjectDraftError(f"{label} must contain JSON-compatible project data.") from exc


def _design_session_payload(session: DesignSession | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(session, DesignSession):
        payload = asdict(session)
    elif isinstance(session, Mapping):
        payload = dict(session)
    elif is_dataclass(session):
        payload = asdict(session)
    else:
        raise PlantProjectDraftError("Formal draft requires a DesignSession snapshot.")
    return _json_copy(payload, label="DesignSession snapshot")


def _validated_workflow_type(value: str) -> str:
    workflow_type = _text(value)
    if workflow_type not in VALID_WORKFLOW_TYPES:
        raise PlantProjectDraftError(f"Unsupported formal workflow_type: {workflow_type or '<empty>'}.")
    return workflow_type


def formal_project_last_active_surface(
    project_id: str,
    *,
    repository: PlantProjectDraftRepository | None = None,
) -> str:
    """Return one bounded project resume destination, failing closed to Expression Design."""
    resolved_id = _text(project_id)
    if not resolved_id:
        return PRODUCT_SURFACE_EXPRESSION
    repo = repository or PlantProjectDraftRepository()
    draft = repo.load(resolved_id)
    payload = dict(draft.manual_review_state).get(FORMAL_PRODUCT_NAVIGATION_STATE_KEY)
    if not isinstance(payload, Mapping):
        return PRODUCT_SURFACE_EXPRESSION
    if payload.get("schema_version") != FORMAL_PRODUCT_NAVIGATION_STATE_VERSION:
        return PRODUCT_SURFACE_EXPRESSION
    if _text(payload.get("project_id")) != resolved_id:
        return PRODUCT_SURFACE_EXPRESSION
    destination = _text(payload.get("last_active_surface"))
    return destination if destination in VALID_PRODUCT_SURFACES else PRODUCT_SURFACE_EXPRESSION


def record_formal_project_active_surface(
    project_id: str,
    destination: str,
    *,
    repository: PlantProjectDraftRepository | None = None,
) -> bool:
    """Persist navigation preference only; do not grant it project or biological authority."""
    resolved_id = _text(project_id)
    resolved_destination = _text(destination)
    if not resolved_id:
        raise PlantProjectDraftError("Project id is required for product navigation state.")
    if resolved_destination not in VALID_PRODUCT_SURFACES:
        raise PlantProjectDraftError("Unsupported product navigation destination.")
    repo = repository or PlantProjectDraftRepository()
    draft = repo.load(resolved_id)
    require_active_project(draft)
    if draft.project_id != resolved_id:
        raise PlantProjectDraftError("Product navigation state does not match the current project.")
    payload = dict(draft.manual_review_state).get(FORMAL_PRODUCT_NAVIGATION_STATE_KEY)
    expected = {
        "schema_version": FORMAL_PRODUCT_NAVIGATION_STATE_VERSION,
        "project_id": resolved_id,
        "last_active_surface": resolved_destination,
    }
    if payload == expected:
        return False
    review_state = dict(draft.manual_review_state)
    review_state[FORMAL_PRODUCT_NAVIGATION_STATE_KEY] = expected
    draft.manual_review_state = review_state
    if isinstance(repo, PlantProjectDraftRepository):
        repo.restore_exact(draft)
    else:
        repo.save(draft)
    return True


def save_formal_project_draft(
    *,
    project_name: str,
    project_id: str,
    workflow_type: str,
    current_step: int,
    design_session: DesignSession | Mapping[str, Any],
    formal_state: Mapping[str, Any],
    project_definition: Mapping[str, Any] | None = None,
    manual_state_updates: Mapping[str, Any] | None = None,
    repository: PlantProjectDraftRepository | None = None,
) -> PlantDesignProjectDraft:
    """Persist one incomplete formal workflow without requiring a canonical construct."""
    name = _text(project_name)
    if not name:
        raise PlantProjectDraftError("Project name is required before saving a draft.")
    workflow = _validated_workflow_type(workflow_type)
    resolved_id = _text(project_id) or new_project_id()
    repo = repository or PlantProjectDraftRepository()
    try:
        draft = repo.load(resolved_id)
    except PlantProjectDraftError:
        draft = repo.create_blank(project_name=name)
        draft.project_id = resolved_id

    if draft.draft_status == STATUS_COMPLETED:
        raise PlantProjectDraftError("A completed project cannot be replaced by an incomplete draft.")
    if draft.workflow_type and draft.workflow_type != workflow:
        raise PlantProjectDraftError("An existing project cannot change workflow_type during draft save.")

    definition = _json_copy(dict(project_definition or {}), label="Project definition")
    state = _json_copy(dict(formal_state), label="Formal workflow state")
    snapshot = {
        "schema_version": FORMAL_DRAFT_STATE_VERSION,
        "workflow_type": workflow,
        "current_step": max(1, min(6, int(current_step or 1))),
        "design_session": _design_session_payload(design_session),
        "formal_state": state,
        "project_definition": definition,
    }
    review_state = dict(draft.manual_review_state)
    review_state[FORMAL_DRAFT_STATE_KEY] = snapshot
    if manual_state_updates:
        review_state.update(
            _json_copy(dict(manual_state_updates), label="Manual review state updates")
        )
    draft.manual_review_state = review_state
    draft = update_plant_project_draft(
        draft,
        project_name=name,
        plant_design_goal=_text(definition.get("expression_target")),
        host_context=_text(definition.get("plant_host")),
        expression_context=_text(definition.get("application_mode")),
        draft_status=STATUS_DRAFT,
        workflow_type=workflow,
        canonical_available=False,
    )
    draft.manual_review_state = review_state
    return repo.save(draft)


def formal_draft_snapshot(draft: PlantDesignProjectDraft) -> dict[str, Any]:
    if draft.draft_status != STATUS_DRAFT:
        raise PlantProjectDraftError("The selected record is not a formal draft.")
    payload = dict(draft.manual_review_state).get(FORMAL_DRAFT_STATE_KEY)
    if not isinstance(payload, dict) or payload.get("schema_version") != FORMAL_DRAFT_STATE_VERSION:
        raise PlantProjectDraftError("The selected draft does not contain a compatible workflow snapshot.")
    _validated_workflow_type(_text(payload.get("workflow_type")))
    if not isinstance(payload.get("design_session"), dict) or not isinstance(payload.get("formal_state"), dict):
        raise PlantProjectDraftError("The selected draft workflow snapshot is incomplete.")
    return _json_copy(payload, label="Formal draft snapshot")


def formal_agent_project_projection(
    project_id: str,
    *,
    repository: PlantProjectDraftRepository | None = None,
) -> dict[str, Any]:
    """Read persisted Formal facts without granting Agent a separate project identity."""
    repo = repository or PlantProjectDraftRepository()
    draft = repo.load(project_id)
    workflow_type = _text(draft.workflow_type)
    formal_state: dict[str, Any] = {}
    definition: dict[str, Any] = {}
    cds_input: dict[str, Any] = {}

    if draft.draft_status == STATUS_DRAFT:
        snapshot = formal_draft_snapshot(draft)
        formal_state = dict(snapshot.get("formal_state") or {})
        definition = dict(snapshot.get("project_definition") or {})
        cds_input = dict(formal_state.get("formal_cds_input") or {})
    elif workflow_type == WORKFLOW_SINGLE_GENE:
        from services.mvp_single_gene_persistence import open_mvp_single_gene_design

        opened = open_mvp_single_gene_design(project_id, repository=repo)
        context = dict(opened.get("formal_project_context") or {})
        formal_state = dict(context.get("formal_state") or {})
        definition = dict(context.get("project_definition") or {})
        cds_input = dict(opened.get("cds_input") or {})

    if not cds_input:
        cds_input = dict(formal_state.get("formal_cds_input") or {})
    normalized_cds = _text(cds_input.get("normalized_cds"))
    cds = (
        {
            "value": normalized_cds,
            "source": "formal_project",
            "source_name": _text(cds_input.get("source_name")),
        }
        if normalized_cds and not bool(cds_input.get("blocking"))
        else None
    )
    selections = []
    for state_key in ("formal_step3_promoter", "formal_step3_terminator"):
        selected = formal_state.get(state_key)
        selected = dict(selected) if isinstance(selected, Mapping) else {}
        reference = selected.get("component_reference")
        if isinstance(reference, Mapping) and reference:
            selections.append(
                {
                    "state_key": state_key,
                    "display_name": _text(selected.get("name") or selected.get("display_name")),
                    "sequence": _text(selected.get("sequence") or selected.get("normalized_sequence")),
                    "component_reference": dict(reference),
                }
            )
    return {
        "project_id": draft.project_id,
        "project_name": draft.project_name,
        "workflow_type": workflow_type,
        "host": _text(definition.get("plant_host")) or _text(draft.host_context),
        "user_intent": _text(definition.get("expression_target")) or _text(draft.plant_design_goal),
        "cds": cds,
        "component_selections": selections,
        "canonical_available": bool(draft.canonical_available),
    }


def restore_design_session(payload: Mapping[str, Any]) -> DesignSession:
    allowed = {item.name for item in fields(DesignSession)}
    values = {key: value for key, value in dict(payload).items() if key in allowed}
    try:
        return DesignSession(**values)
    except (TypeError, ValueError) as exc:
        raise PlantProjectDraftError("The saved DesignSession snapshot is invalid.") from exc


def mark_formal_project_completed(
    draft: PlantDesignProjectDraft,
    *,
    workflow_type: str,
) -> PlantDesignProjectDraft:
    """Apply completion metadata after existing canonical validation has succeeded."""
    workflow = _validated_workflow_type(workflow_type)
    if not draft.canonical_construct_runtime:
        raise PlantProjectDraftError("A completed project requires a canonical construct runtime.")
    updated = update_plant_project_draft(
        draft,
        draft_status=STATUS_COMPLETED,
        workflow_type=workflow,
        canonical_available=True,
    )
    updated.manual_review_state = dict(draft.manual_review_state)
    return updated
