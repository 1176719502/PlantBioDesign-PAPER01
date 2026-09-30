from __future__ import annotations

from typing import Any

from services.plant_project_draft_schema import (
    PlantDesignProjectDraft,
    PlantProjectDraftError,
    build_plant_project_draft_completeness,
)


R223_SLOT_MAP: dict[str, str] = {
    "promoter_or_regulatory_element": "promoter_slot",
    "target_gene_or_cds": "cds_label",
    "expression_context": "localization_context",
    "terminator": "terminator_slot",
    "vector_or_backbone": "backbone_label",
}


def _draft(value: PlantDesignProjectDraft | dict[str, Any]) -> PlantDesignProjectDraft:
    if isinstance(value, PlantDesignProjectDraft):
        return value
    if isinstance(value, dict):
        return PlantDesignProjectDraft.from_dict(value)
    raise PlantProjectDraftError("Plant expression workspace requires a plant project draft.")


def plant_project_draft_to_r223_chain_output(value: PlantDesignProjectDraft | dict[str, Any]) -> dict[str, Any]:
    draft = _draft(value)
    completeness = build_plant_project_draft_completeness(draft)
    slot_rows: list[dict[str, str]] = []
    candidate_rows: list[dict[str, str]] = []
    gap_rows: list[dict[str, str]] = []

    for slot in draft.construct_slots:
        r223_slot = R223_SLOT_MAP.get(slot.slot_key, slot.slot_key)
        slot_rows.append(
            {
                "slot_name": r223_slot,
                "slot_label": slot.slot_role,
                "value": slot.component_name,
                "source_reference": slot.source_reference,
                "evidence_reference": slot.evidence_reference,
                "notes": slot.notes,
                "record_origin": draft.record_origin,
            }
        )
        if slot.source_reference or slot.evidence_reference:
            candidate_rows.append(
                {
                    "slot_type": r223_slot,
                    "candidate_label": slot.component_name or slot.slot_role,
                    "review_status": "manual review pending",
                    "source_reference": slot.source_reference,
                    "evidence_reference": slot.evidence_reference,
                }
            )
        if not slot.component_name and slot.slot_key in completeness["missing_construct_slots"]:
            gap_rows.append(
                {
                    "gap_id": f"r224-missing-{slot.slot_key}",
                    "field_name": r223_slot,
                    "message": f"{slot.slot_role} is not recorded in the user draft.",
                    "source_section": "persisted user draft",
                }
            )
        elif slot.component_name and not (slot.source_reference or slot.evidence_reference):
            gap_rows.append(
                {
                    "gap_id": f"r224-evidence-{slot.slot_key}",
                    "field_name": r223_slot,
                    "message": f"{slot.slot_role} has a component note but no source or evidence reference.",
                    "source_section": "persisted user draft",
                }
            )

    evidence_summary = [
        {
            "evidence_id": record.evidence_id,
            "label": record.label,
            "summary": record.reference_text,
            "record_origin": record.record_origin,
            "status": "manual_review",
        }
        for record in draft.evidence_references
    ]
    return {
        "fixture_id": "",
        "project_id": draft.project_id,
        "record_origin": draft.record_origin,
        "chain_summary": {"route_id": "user_plant_design_project_draft"},
        "route_draft": {
            "draft_status": draft.draft_status,
            "route_id": "user_plant_design_project_draft",
            "intent_summary": {
                "target_or_product_terms": draft.plant_design_goal,
                "host_plant_terms": draft.host_context,
            },
            "evidence_summary": evidence_summary,
        },
        "package_snapshot": {
            "package_title": draft.project_name or "Untitled plant design draft",
            "package_status": completeness["review_state"],
            "package_scope": "user-entered plant design project draft",
            "construct_slot_plan_section": {"construct_slot_rows": slot_rows},
            "component_candidate_section": {
                "slot_candidate_rows": candidate_rows,
                "unmatched_slot_rows": [],
            },
            "gap_queue_section": {"queue_items": gap_rows},
        },
        "markdown_readback": {
            "markdown_text": (
                f"# {draft.project_name or 'Untitled plant design draft'}\n\n"
                f"Project ID: {draft.project_id}\n\n"
                f"Goal: {draft.plant_design_goal or 'not recorded'}\n"
            )
        },
    }
