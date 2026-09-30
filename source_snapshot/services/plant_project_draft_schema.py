from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


PLANT_PROJECT_DRAFT_SCHEMA_VERSION = "v2.7-r224-plant-design-project-draft"
PLANT_PROJECT_DRAFT_RECORD_ORIGIN = "user"
PLANT_PROJECT_DRAFT_DEFAULT_STATUS = "draft"
PLANT_PROJECT_DRAFT_REVIEW_REQUIRED = "review-required"

REQUIRED_CONSTRUCT_SLOT_KEYS: tuple[str, ...] = (
    "target_protein",
    "target_gene_or_cds",
    "host_plant",
    "expression_context",
    "promoter_or_regulatory_element",
    "terminator",
    "marker_or_reporter",
    "vector_or_backbone",
)

CONSTRUCT_SLOT_LABELS: dict[str, str] = {
    "target_protein": "Target protein",
    "target_gene_or_cds": "Target gene or CDS",
    "host_plant": "Host plant",
    "expression_context": "Expression context",
    "promoter_or_regulatory_element": "Promoter or regulatory element",
    "terminator": "Terminator",
    "marker_or_reporter": "Marker or reporter",
    "vector_or_backbone": "Vector or backbone",
}


class PlantProjectDraftError(ValueError):
    """Base error for plant project draft validation and persistence."""


class UnsupportedPlantProjectDraftSchemaError(PlantProjectDraftError):
    """Raised when a persisted draft has a future or unsupported schema."""


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def new_project_id() -> str:
    return f"plant-draft-{uuid4().hex}"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


@dataclass
class PlantDesignConstructSlot:
    slot_key: str
    slot_role: str
    component_name: str = ""
    source_reference: str = ""
    evidence_reference: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "slot_key": self.slot_key,
            "slot_role": self.slot_role,
            "component_name": self.component_name,
            "source_reference": self.source_reference,
            "evidence_reference": self.evidence_reference,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlantDesignConstructSlot":
        slot_key = _text(payload.get("slot_key"))
        if not slot_key:
            raise PlantProjectDraftError("Construct slot is missing slot_key.")
        return cls(
            slot_key=slot_key,
            slot_role=_text(payload.get("slot_role")) or CONSTRUCT_SLOT_LABELS.get(slot_key, slot_key),
            component_name=_text(payload.get("component_name")),
            source_reference=_text(payload.get("source_reference")),
            evidence_reference=_text(payload.get("evidence_reference")),
            notes=_text(payload.get("notes")),
        )


@dataclass
class PlantDesignEvidenceReference:
    evidence_id: str
    label: str = ""
    reference_text: str = ""
    source_type: str = "user-entered"
    record_origin: str = PLANT_PROJECT_DRAFT_RECORD_ORIGIN
    notes: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "evidence_id": self.evidence_id,
            "label": self.label,
            "reference_text": self.reference_text,
            "source_type": self.source_type,
            "record_origin": self.record_origin,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlantDesignEvidenceReference":
        evidence_id = _text(payload.get("evidence_id"))
        if not evidence_id:
            raise PlantProjectDraftError("Evidence reference is missing evidence_id.")
        origin = _text(payload.get("record_origin")) or PLANT_PROJECT_DRAFT_RECORD_ORIGIN
        if origin != PLANT_PROJECT_DRAFT_RECORD_ORIGIN:
            raise PlantProjectDraftError("Only user-entered evidence references are valid for saved drafts.")
        return cls(
            evidence_id=evidence_id,
            label=_text(payload.get("label")),
            reference_text=_text(payload.get("reference_text")),
            source_type=_text(payload.get("source_type")) or "user-entered",
            record_origin=origin,
            notes=_text(payload.get("notes")),
        )


@dataclass
class PlantDesignProjectDraft:
    project_id: str
    project_name: str
    created_at: str
    updated_at: str
    plant_design_goal: str = ""
    host_context: str = ""
    expression_context: str = ""
    construct_slots: list[PlantDesignConstructSlot] = field(default_factory=list)
    evidence_references: list[PlantDesignEvidenceReference] = field(default_factory=list)
    canonical_construct_runtime: dict[str, Any] = field(default_factory=dict)
    manual_review_state: dict[str, Any] = field(default_factory=dict)
    draft_status: str = PLANT_PROJECT_DRAFT_DEFAULT_STATUS
    workflow_type: str = ""
    canonical_available: bool = False
    schema_version: str = PLANT_PROJECT_DRAFT_SCHEMA_VERSION
    record_origin: str = PLANT_PROJECT_DRAFT_RECORD_ORIGIN
    extra_fields: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            **dict(self.extra_fields),
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "project_name": self.project_name,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "plant_design_goal": self.plant_design_goal,
            "host_context": self.host_context,
            "expression_context": self.expression_context,
            "construct_slots": [slot.to_dict() for slot in self.construct_slots],
            "evidence_references": [evidence.to_dict() for evidence in self.evidence_references],
            "canonical_construct_runtime": dict(self.canonical_construct_runtime),
            "manual_review_state": dict(self.manual_review_state),
            "draft_status": self.draft_status,
            "workflow_type": self.workflow_type,
            "canonical_available": self.canonical_available,
            "record_origin": self.record_origin,
        }

    @classmethod
    def blank(cls, project_name: str = "") -> "PlantDesignProjectDraft":
        timestamp = utc_timestamp()
        return cls(
            project_id=new_project_id(),
            project_name=_text(project_name),
            created_at=timestamp,
            updated_at=timestamp,
            construct_slots=[
                PlantDesignConstructSlot(slot_key=slot_key, slot_role=CONSTRUCT_SLOT_LABELS[slot_key])
                for slot_key in REQUIRED_CONSTRUCT_SLOT_KEYS
            ],
            manual_review_state={"review_state": PLANT_PROJECT_DRAFT_REVIEW_REQUIRED},
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PlantDesignProjectDraft":
        if not isinstance(payload, dict):
            raise PlantProjectDraftError("Plant project draft payload must be an object.")
        schema_version = _text(payload.get("schema_version"))
        if not schema_version:
            raise PlantProjectDraftError("Plant project draft is missing schema_version.")
        if schema_version != PLANT_PROJECT_DRAFT_SCHEMA_VERSION:
            raise UnsupportedPlantProjectDraftSchemaError(
                f"Unsupported plant project draft schema_version: {schema_version}"
            )
        project_id = _text(payload.get("project_id"))
        created_at = _text(payload.get("created_at"))
        updated_at = _text(payload.get("updated_at"))
        if not project_id:
            raise PlantProjectDraftError("Plant project draft is missing project_id.")
        if not created_at or not updated_at:
            raise PlantProjectDraftError("Plant project draft is missing timestamps.")
        origin = _text(payload.get("record_origin")) or PLANT_PROJECT_DRAFT_RECORD_ORIGIN
        if origin != PLANT_PROJECT_DRAFT_RECORD_ORIGIN:
            raise PlantProjectDraftError("Saved plant project drafts must be user data, not examples.")
        slots = [
            PlantDesignConstructSlot.from_dict(slot)
            for slot in _list(payload.get("construct_slots"))
            if isinstance(slot, dict)
        ]
        slot_index = {slot.slot_key: slot for slot in slots}
        for slot_key in REQUIRED_CONSTRUCT_SLOT_KEYS:
            if slot_key not in slot_index:
                slots.append(PlantDesignConstructSlot(slot_key=slot_key, slot_role=CONSTRUCT_SLOT_LABELS[slot_key]))
        evidence = [
            PlantDesignEvidenceReference.from_dict(record)
            for record in _list(payload.get("evidence_references"))
            if isinstance(record, dict)
        ]
        known_fields = {
            "schema_version",
            "project_id",
            "project_name",
            "created_at",
            "updated_at",
            "plant_design_goal",
            "host_context",
            "expression_context",
            "construct_slots",
            "evidence_references",
            "canonical_construct_runtime",
            "manual_review_state",
            "draft_status",
            "workflow_type",
            "canonical_available",
            "record_origin",
        }
        runtime = _mapping(payload.get("canonical_construct_runtime"))
        return cls(
            schema_version=schema_version,
            project_id=project_id,
            project_name=_text(payload.get("project_name")),
            created_at=created_at,
            updated_at=updated_at,
            plant_design_goal=_text(payload.get("plant_design_goal")),
            host_context=_text(payload.get("host_context")),
            expression_context=_text(payload.get("expression_context")),
            construct_slots=slots,
            evidence_references=evidence,
            canonical_construct_runtime=runtime,
            manual_review_state=_mapping(payload.get("manual_review_state")),
            draft_status=_text(payload.get("draft_status")) or PLANT_PROJECT_DRAFT_DEFAULT_STATUS,
            workflow_type=_text(payload.get("workflow_type")),
            canonical_available=bool(payload.get("canonical_available", bool(runtime))),
            record_origin=origin,
            extra_fields={key: value for key, value in payload.items() if key not in known_fields},
        )


def build_plant_project_draft_completeness(draft: PlantDesignProjectDraft | dict[str, Any]) -> dict[str, Any]:
    resolved = draft if isinstance(draft, PlantDesignProjectDraft) else PlantDesignProjectDraft.from_dict(draft)
    slot_rows = []
    missing_slots = []
    slot_evidence_gaps = []
    for slot in resolved.construct_slots:
        is_required = slot.slot_key in REQUIRED_CONSTRUCT_SLOT_KEYS
        has_component = bool(slot.component_name)
        has_evidence = bool(slot.evidence_reference or slot.source_reference)
        if is_required and not has_component:
            missing_slots.append(slot.slot_key)
        if has_component and not has_evidence:
            slot_evidence_gaps.append(slot.slot_key)
        slot_rows.append(
            {
                "slot_key": slot.slot_key,
                "slot_role": slot.slot_role,
                "component_recorded": has_component,
                "evidence_or_source_recorded": has_evidence,
                "required": is_required,
            }
        )

    missing_fields = []
    if not resolved.plant_design_goal:
        missing_fields.append("plant_design_goal")
    if not resolved.host_context:
        missing_fields.append("host_context")
    if not resolved.expression_context:
        missing_fields.append("expression_context")
    missing_fields.extend(missing_slots)
    completeness_state = "complete" if not missing_fields and not slot_evidence_gaps else "incomplete"
    workflow_eligibility = "eligible" if completeness_state == "complete" else "blocked"
    next_action = (
        "Review the completed documentation record manually."
        if workflow_eligibility == "eligible"
        else "Fill missing project fields, construct slots, and source or evidence notes."
    )
    return {
        "completeness_state": completeness_state,
        "workflow_eligibility": workflow_eligibility,
        "review_state": resolved.manual_review_state.get("review_state", PLANT_PROJECT_DRAFT_REVIEW_REQUIRED),
        "missing_fields": missing_fields,
        "missing_construct_slots": missing_slots,
        "component_evidence_gaps": slot_evidence_gaps,
        "slot_rows": slot_rows,
        "manual_review_required": True,
        "next_action": next_action,
    }


def update_plant_project_draft(
    draft: PlantDesignProjectDraft,
    *,
    project_name: str | None = None,
    plant_design_goal: str | None = None,
    host_context: str | None = None,
    expression_context: str | None = None,
    construct_slot_updates: dict[str, dict[str, Any]] | None = None,
    evidence_references: list[dict[str, Any]] | None = None,
    canonical_construct_runtime: dict[str, Any] | None = None,
    draft_status: str | None = None,
    workflow_type: str | None = None,
    canonical_available: bool | None = None,
    updated_at: str | None = None,
) -> PlantDesignProjectDraft:
    slot_updates = construct_slot_updates or {}
    updated_slots: list[PlantDesignConstructSlot] = []
    for slot in draft.construct_slots:
        patch = _mapping(slot_updates.get(slot.slot_key))
        updated_slots.append(
            PlantDesignConstructSlot(
                slot_key=slot.slot_key,
                slot_role=slot.slot_role,
                component_name=_text(patch.get("component_name", slot.component_name)),
                source_reference=_text(patch.get("source_reference", slot.source_reference)),
                evidence_reference=_text(patch.get("evidence_reference", slot.evidence_reference)),
                notes=_text(patch.get("notes", slot.notes)),
            )
        )
    evidence = draft.evidence_references
    if evidence_references is not None:
        evidence = [
            PlantDesignEvidenceReference.from_dict(record)
            for record in evidence_references
            if isinstance(record, dict) and _text(record.get("evidence_id"))
        ]
    return PlantDesignProjectDraft(
        schema_version=draft.schema_version,
        project_id=draft.project_id,
        project_name=_text(project_name if project_name is not None else draft.project_name),
        created_at=draft.created_at,
        updated_at=updated_at or utc_timestamp(),
        plant_design_goal=_text(plant_design_goal if plant_design_goal is not None else draft.plant_design_goal),
        host_context=_text(host_context if host_context is not None else draft.host_context),
        expression_context=_text(expression_context if expression_context is not None else draft.expression_context),
        construct_slots=updated_slots,
        evidence_references=evidence,
        canonical_construct_runtime=_mapping(
            canonical_construct_runtime
            if canonical_construct_runtime is not None
            else draft.canonical_construct_runtime
        ),
        manual_review_state=dict(draft.manual_review_state),
        draft_status=_text(draft_status if draft_status is not None else draft.draft_status),
        workflow_type=_text(workflow_type if workflow_type is not None else draft.workflow_type),
        canonical_available=(
            bool(canonical_available) if canonical_available is not None else draft.canonical_available
        ),
        record_origin=draft.record_origin,
        extra_fields=dict(draft.extra_fields),
    )
