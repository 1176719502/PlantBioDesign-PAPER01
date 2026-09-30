from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


CONSTRUCT_TASK_STATUS_CREATED = "task_list_created"
CONSTRUCT_TASK_STATUS_REFUSED = "route_not_allowed"
SLOT_STATUS_NEEDS_SOURCE = "missing / needs source"
SLOT_STATUS_NEEDS_CONFIRMATION = "manual review required"
CONSTRUCT_TASK_BOUNDARY = (
    "Route-to-construct bridge output is a manual-review task list. It preserves missing "
    "sources per slot and does not create final constructs, sequences, cloning instructions, "
    "component rankings, biological forecasts, or downstream-use approvals."
)

SLOT_ALIASES = {
    "plant_context": "plant_host_context",
    "plant_species": "plant_host_context",
    "tissue_context": "plant_host_context",
    "expression_compartment": "plant_host_context",
    "target_product": "target_payload_cds_or_gene_enzyme",
    "target_trait_or_metabolite": "target_payload_cds_or_gene_enzyme",
    "candidate_gene_or_enzyme": "target_payload_cds_or_gene_enzyme",
    "gene": "target_payload_cds_or_gene_enzyme",
    "enzyme": "target_payload_cds_or_gene_enzyme",
    "cds": "target_payload_cds_or_gene_enzyme",
    "gene_or_cds_source": "target_payload_cds_or_gene_enzyme",
    "promoter": "promoter_need",
    "terminator": "terminator_need",
    "marker": "marker_need",
    "vector": "vector_backbone_need",
    "backbone": "vector_backbone_need",
    "localization": "optional_tag_signal_peptide_localization",
    "signal_peptide": "optional_tag_signal_peptide_localization",
    "tag": "optional_tag_signal_peptide_localization",
}

BASE_REQUIRED_SLOTS = (
    "plant_host_context",
    "target_payload_cds_or_gene_enzyme",
    "promoter_need",
    "terminator_need",
    "marker_need",
    "vector_backbone_need",
)
OPTIONAL_SLOT = "optional_tag_signal_peptide_localization"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_text(item) for item in value if _text(item)]
    return []


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)
    return result


def _candidate_route(route_result: Mapping[str, Any]) -> Mapping[str, Any]:
    candidate = route_result.get("candidate_route")
    return candidate if isinstance(candidate, Mapping) else {}


def _route_allowed(route_result: Mapping[str, Any]) -> bool:
    return _text(route_result.get("route_generation_status")).casefold() == "allowed" and bool(_candidate_route(route_result))


def _canonical_slot(raw_slot: str) -> str:
    return SLOT_ALIASES.get(raw_slot, raw_slot)


def _required_slots(candidate_route: Mapping[str, Any]) -> list[str]:
    slots = list(BASE_REQUIRED_SLOTS)
    route_slots = _as_list(candidate_route.get("required_component_slots"))
    canonical_route_slots = [_canonical_slot(slot) for slot in route_slots]
    if OPTIONAL_SLOT in canonical_route_slots:
        slots.append(OPTIONAL_SLOT)
    for slot in canonical_route_slots:
        if slot in BASE_REQUIRED_SLOTS and slot not in slots:
            slots.append(slot)
    return _unique(slots)


def _slot_source_ids(candidate_route: Mapping[str, Any]) -> dict[str, list[str]]:
    raw_sources = candidate_route.get("slot_source_ids")
    if not isinstance(raw_sources, Mapping):
        return {}
    sources: dict[str, list[str]] = {}
    for raw_slot, raw_ids in raw_sources.items():
        slot = _canonical_slot(_text(raw_slot))
        ids = _as_list(raw_ids)
        if ids:
            sources[slot] = _unique([*sources.get(slot, []), *ids])
    return sources


def _missing_slots(candidate_route: Mapping[str, Any]) -> set[str]:
    return {_canonical_slot(slot) for slot in _as_list(candidate_route.get("missing_fields"))}


def _task_for_slot(
    slot: str,
    source_ids: Sequence[str],
    missing_slots: set[str],
    index: int,
) -> dict[str, Any]:
    missing_source = slot in missing_slots or not source_ids
    return {
        "task_id": f"construct-slot-{index:02d}",
        "slot": slot,
        "requirement": slot.replace("_", " "),
        "evidence_source_ids": list(source_ids),
        "status": SLOT_STATUS_NEEDS_SOURCE if missing_source else SLOT_STATUS_NEEDS_CONFIRMATION,
        "manual_review_required": True,
        "missing_source": missing_source,
    }


def build_plant_construct_task_requirements(
    candidate_route_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Convert an allowed candidate route draft into source-aware construct task requirements."""
    route_result = dict(candidate_route_result or {})
    if not _route_allowed(route_result):
        return {
            "construct_task_status": CONSTRUCT_TASK_STATUS_REFUSED,
            "reason": "route not allowed",
            "construct_tasks": [],
            "missing_fields": _as_list(route_result.get("evidence_gaps")),
            "manual_review_required": True,
            "safety_boundary": CONSTRUCT_TASK_BOUNDARY,
        }

    candidate = dict(_candidate_route(route_result))
    slot_sources = _slot_source_ids(candidate)
    missing_slots = _missing_slots(candidate)
    tasks = [
        _task_for_slot(slot, slot_sources.get(slot, []), missing_slots, index)
        for index, slot in enumerate(_required_slots(candidate), start=1)
    ]
    missing_fields = _unique(
        [
            *[task["slot"] for task in tasks if task["missing_source"]],
            *_as_list(candidate.get("missing_fields")),
        ]
    )

    return {
        "construct_task_status": CONSTRUCT_TASK_STATUS_CREATED,
        "route_id": _text(candidate.get("route_id")),
        "route_framing": _text(candidate.get("route_framing")),
        "supporting_source_ids": _as_list(candidate.get("supporting_source_ids")),
        "construct_tasks": tasks,
        "missing_fields": missing_fields,
        "manual_review_required": True,
        "task_list_only": True,
        "safety_boundary": CONSTRUCT_TASK_BOUNDARY,
    }
