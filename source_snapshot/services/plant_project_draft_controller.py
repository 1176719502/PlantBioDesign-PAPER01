from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.plant_project_draft_repository import (
    PlantProjectDraftRepository,
    PlantProjectDraftSummary,
    require_active_project,
)
from services.plant_project_draft_schema import (
    PlantDesignProjectDraft,
    PlantProjectDraftError,
    build_plant_project_draft_completeness,
    update_plant_project_draft,
)


ACTIVE_PLANT_PROJECT_DRAFT_ID_KEY = "r224_active_plant_project_draft_id"
ACTIVE_PLANT_PROJECT_DRAFT_KEY = "r224_active_plant_project_draft"
ACTIVE_PLANT_PROJECT_SAVE_STATE_KEY = "r224_active_plant_project_save_state"
ACTIVE_PLANT_PROJECT_DIRTY_KEY = "r224_active_plant_project_dirty"


@dataclass(frozen=True)
class PlantProjectDraftControllerResult:
    ok: bool
    message: str
    draft: PlantDesignProjectDraft | None = None


class PlantProjectDraftController:
    def __init__(
        self,
        *,
        session_state: dict[str, Any],
        repository: PlantProjectDraftRepository | None = None,
    ):
        self.session_state = session_state
        self.repository = repository or PlantProjectDraftRepository()

    def list_saved_projects(self) -> list[PlantProjectDraftSummary]:
        return self.repository.list_summaries()

    def active_draft(self) -> PlantDesignProjectDraft | None:
        payload = self.session_state.get(ACTIVE_PLANT_PROJECT_DRAFT_KEY)
        if isinstance(payload, PlantDesignProjectDraft):
            return payload
        if isinstance(payload, dict):
            try:
                draft = PlantDesignProjectDraft.from_dict(payload)
            except PlantProjectDraftError:
                self.session_state.pop(ACTIVE_PLANT_PROJECT_DRAFT_KEY, None)
                return None
            self._set_active(draft, dirty=bool(self.session_state.get(ACTIVE_PLANT_PROJECT_DIRTY_KEY)))
            return draft
        project_id = self.session_state.get(ACTIVE_PLANT_PROJECT_DRAFT_ID_KEY)
        if project_id:
            result = self.open_project(str(project_id))
            if result.ok:
                return result.draft
        return None

    def create_blank(self, project_name: str = "") -> PlantProjectDraftControllerResult:
        draft = self.repository.create_blank(project_name=project_name)
        self._set_active(draft, dirty=True)
        return PlantProjectDraftControllerResult(True, "Blank plant design project draft created.", draft)

    def open_project(self, project_id: str) -> PlantProjectDraftControllerResult:
        try:
            draft = self.repository.load(project_id)
            require_active_project(draft)
        except PlantProjectDraftError as exc:
            return PlantProjectDraftControllerResult(False, str(exc), None)
        self._set_active(draft, dirty=False)
        self.session_state[ACTIVE_PLANT_PROJECT_SAVE_STATE_KEY] = "saved"
        return PlantProjectDraftControllerResult(True, "Plant design project draft opened.", draft)

    def update_active(
        self,
        *,
        project_name: str | None = None,
        plant_design_goal: str | None = None,
        host_context: str | None = None,
        expression_context: str | None = None,
        construct_slot_updates: dict[str, dict[str, Any]] | None = None,
        evidence_references: list[dict[str, Any]] | None = None,
        canonical_construct_runtime: dict[str, Any] | None = None,
    ) -> PlantProjectDraftControllerResult:
        draft = self.active_draft()
        if draft is None:
            return PlantProjectDraftControllerResult(False, "No active plant design project draft is selected.", None)
        updated = update_plant_project_draft(
            draft,
            project_name=project_name,
            plant_design_goal=plant_design_goal,
            host_context=host_context,
            expression_context=expression_context,
            construct_slot_updates=construct_slot_updates,
            evidence_references=evidence_references,
            canonical_construct_runtime=canonical_construct_runtime,
        )
        self._set_active(updated, dirty=True)
        self.session_state[ACTIVE_PLANT_PROJECT_SAVE_STATE_KEY] = "unsaved"
        return PlantProjectDraftControllerResult(True, "Plant design project draft updated in the current session.", updated)

    def save_active(self) -> PlantProjectDraftControllerResult:
        draft = self.active_draft()
        if draft is None:
            self.session_state[ACTIVE_PLANT_PROJECT_SAVE_STATE_KEY] = "save-error"
            return PlantProjectDraftControllerResult(False, "No active plant design project draft is selected.", None)
        try:
            saved = self.repository.save(draft)
        except Exception as exc:
            self.session_state[ACTIVE_PLANT_PROJECT_SAVE_STATE_KEY] = "save-error"
            return PlantProjectDraftControllerResult(False, f"Plant design project draft was not saved: {exc}", draft)
        self._set_active(saved, dirty=False)
        self.session_state[ACTIVE_PLANT_PROJECT_SAVE_STATE_KEY] = "saved"
        return PlantProjectDraftControllerResult(True, "Plant design project draft saved as local user data.", saved)

    def active_completeness(self) -> dict[str, Any]:
        draft = self.active_draft()
        if draft is None:
            return {
                "completeness_state": "incomplete",
                "workflow_eligibility": "blocked",
                "review_state": "review-required",
                "missing_fields": ["active_project"],
                "missing_construct_slots": [],
                "component_evidence_gaps": [],
                "slot_rows": [],
                "manual_review_required": True,
                "next_action": "Create or open a plant design project draft.",
            }
        return build_plant_project_draft_completeness(draft)

    def _set_active(self, draft: PlantDesignProjectDraft, *, dirty: bool) -> None:
        self.session_state[ACTIVE_PLANT_PROJECT_DRAFT_ID_KEY] = draft.project_id
        self.session_state[ACTIVE_PLANT_PROJECT_DRAFT_KEY] = draft.to_dict()
        self.session_state[ACTIVE_PLANT_PROJECT_DIRTY_KEY] = dirty


def get_active_plant_project_draft(session_state: dict[str, Any]) -> PlantDesignProjectDraft | None:
    return PlantProjectDraftController(session_state=session_state).active_draft()
