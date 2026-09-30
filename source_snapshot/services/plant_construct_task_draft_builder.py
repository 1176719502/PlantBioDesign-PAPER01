from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


CONSTRUCT_DRAFT_STATUS_CREATED = "construct_draft_created"
CONSTRUCT_DRAFT_STATUS_BLOCKED = "route_generation_blocked"

DRAFT_STATUS_INCOMPLETE = "incomplete"
DRAFT_STATUS_NEEDS_MANUAL_REVIEW = "needs_manual_review"
DRAFT_STATUS_COMPLETE_PENDING_REVIEW = "draft_complete_pending_review"

SLOT_STATUS_PRESENT = "present"
SLOT_STATUS_MISSING = "missing"
SLOT_STATUS_NEEDS_SOURCE = "needs_source"
SLOT_STATUS_NEEDS_CONFIRMATION = "needs_confirmation"
SLOT_STATUS_NOT_APPLICABLE = "not_applicable"

CONSTRUCT_DRAFT_BOUNDARY = (
    "Construct draft output preserves route-derived task slots for source review. "
    "It does not create final sequences, assembly instructions, component choices, "
    "biological forecasts, or downstream-use approval."
)

REQUIRED_SLOT_ORDER = (
    "promoter",
    "cds_payload_gene_or_enzyme",
    "terminator",
    "selectable_marker",
    "vector_backbone",
    "plant_host_context",
)

OPTIONAL_SLOT_ORDER = (
    "tag",
    "signal_peptide",
    "subcellular_localization",
)

SLOT_ROLES = {
    "promoter": "regulatory slot",
    "cds_payload_gene_or_enzyme": "CDS / payload / gene_or_enzyme slot",
    "terminator": "terminator slot",
    "selectable_marker": "selectable marker slot",
    "vector_backbone": "vector backbone slot",
    "plant_host_context": "plant host context slot",
    "tag": "optional tag slot",
    "signal_peptide": "optional signal peptide slot",
    "subcellular_localization": "optional subcellular localization slot",
}

SLOT_ALIASES = {
    "plant_context": "plant_host_context",
    "plant_species": "plant_host_context",
    "tissue_context": "plant_host_context",
    "expression_compartment": "plant_host_context",
    "plant_host_or_context": "plant_host_context",
    "target_payload_cds_or_gene_enzyme": "cds_payload_gene_or_enzyme",
    "target_product": "cds_payload_gene_or_enzyme",
    "target_trait_or_metabolite": "cds_payload_gene_or_enzyme",
    "candidate_gene_or_enzyme": "cds_payload_gene_or_enzyme",
    "gene": "cds_payload_gene_or_enzyme",
    "enzyme": "cds_payload_gene_or_enzyme",
    "cds": "cds_payload_gene_or_enzyme",
    "payload": "cds_payload_gene_or_enzyme",
    "gene_or_enzyme": "cds_payload_gene_or_enzyme",
    "gene_or_cds_source": "cds_payload_gene_or_enzyme",
    "promoter_need": "promoter",
    "terminator_need": "terminator",
    "marker": "selectable_marker",
    "marker_need": "selectable_marker",
    "vector": "vector_backbone",
    "backbone": "vector_backbone",
    "vector_backbone_need": "vector_backbone",
    "optional_tag_signal_peptide_localization": "tag",
    "localization": "subcellular_localization",
}


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


def _canonical_slot(slot_name: Any) -> str:
    raw = _text(slot_name).casefold().replace(" ", "_").replace("-", "_")
    return SLOT_ALIASES.get(raw, raw)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _route_blocked(task_result: Mapping[str, Any]) -> bool:
    route_status = _text(task_result.get("route_generation_status")).casefold()
    task_status = _text(task_result.get("construct_task_status")).casefold()
    return route_status == "blocked" or task_status == "route_not_allowed"


def _candidate_route(task_result: Mapping[str, Any]) -> Mapping[str, Any]:
    return _mapping(task_result.get("candidate_route"))


def _first_text(*values: Any) -> str:
    for value in values:
        clean = _text(value)
        if clean:
            return clean
    return ""


def _draft_id(source_route_id: str, route_label: str) -> str:
    source = source_route_id or route_label or "unassigned_route"
    clean = "".join(char.lower() if char.isalnum() else "-" for char in source)
    clean = "-".join(part for part in clean.split("-") if part)
    return f"construct-draft-{clean or 'unassigned-route'}"


def _task_list(task_result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw_tasks = task_result.get("construct_tasks", task_result.get("tasks", []))
    if not isinstance(raw_tasks, Sequence) or isinstance(raw_tasks, (str, bytes, bytearray)):
        return []
    return [task for task in raw_tasks if isinstance(task, Mapping)]


def _task_slot(task: Mapping[str, Any]) -> str:
    return _canonical_slot(task.get("slot", task.get("slot_name", "")))


def _task_value(task: Mapping[str, Any]) -> str:
    return _first_text(
        task.get("value"),
        task.get("slot_value"),
        task.get("recorded_value"),
        task.get("explicit_value"),
        task.get("provided_value"),
    )


def _task_confirmed(task: Mapping[str, Any]) -> bool:
    if task.get("confirmed") is True or task.get("explicitly_confirmed") is True:
        return True
    status = _text(task.get("confirmation_status", task.get("status"))).casefold()
    return status in {"confirmed", "explicitly_confirmed", "source_confirmed", "present"}


def _source_ids(task: Mapping[str, Any]) -> list[str]:
    return _unique(
        [
            *_as_list(task.get("source_ids")),
            *_as_list(task.get("supporting_source_ids")),
        ]
    )


def _evidence_ids(task: Mapping[str, Any]) -> list[str]:
    return _unique(
        [
            *_as_list(task.get("evidence_ids")),
            *_as_list(task.get("evidence_source_ids")),
        ]
    )


def _missing_reason(
    slot_name: str,
    task: Mapping[str, Any] | None,
    upstream_missing_slots: set[str],
    required: bool,
) -> str:
    if task:
        explicit_reason = _text(task.get("missing_reason"))
        if explicit_reason:
            return explicit_reason
        if task.get("missing_source") is True:
            return "upstream task has no source for this slot"
    if slot_name in upstream_missing_slots:
        return "listed in upstream missing fields"
    if required and task is None:
        return "required slot absent from upstream construct task list"
    return ""


def _slot_status(
    slot_name: str,
    task: Mapping[str, Any] | None,
    value: str,
    source_ids: Sequence[str],
    evidence_ids: Sequence[str],
    upstream_missing_slots: set[str],
    required: bool,
) -> str:
    if not required and task is None:
        return SLOT_STATUS_NOT_APPLICABLE
    if task is None:
        return SLOT_STATUS_MISSING if required else SLOT_STATUS_NOT_APPLICABLE

    upstream_status = _text(task.get("status")).casefold()
    missing_source = (
        task.get("missing_source") is True
        or slot_name in upstream_missing_slots
        or "needs source" in upstream_status
        or "missing" in upstream_status
    )
    if missing_source:
        return SLOT_STATUS_NEEDS_SOURCE
    if value and _task_confirmed(task):
        return SLOT_STATUS_PRESENT
    if value or source_ids or evidence_ids:
        return SLOT_STATUS_NEEDS_CONFIRMATION
    return SLOT_STATUS_MISSING if required else SLOT_STATUS_NOT_APPLICABLE


def _tasks_by_slot(tasks: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    by_slot: dict[str, Mapping[str, Any]] = {}
    for task in tasks:
        slot = _task_slot(task)
        if slot and slot not in by_slot:
            by_slot[slot] = task
    return by_slot


def _upstream_missing_slots(task_result: Mapping[str, Any], tasks: Sequence[Mapping[str, Any]]) -> set[str]:
    missing = {_canonical_slot(slot) for slot in _as_list(task_result.get("missing_fields"))}
    for task in tasks:
        if task.get("missing_source") is True or _text(task.get("missing_reason")):
            slot = _task_slot(task)
            if slot:
                missing.add(slot)
    return missing


def _build_slot(
    slot_name: str,
    task: Mapping[str, Any] | None,
    upstream_missing_slots: set[str],
    required: bool,
) -> dict[str, Any]:
    task = task if isinstance(task, Mapping) else None
    value = _task_value(task) if task else ""
    sources = _source_ids(task) if task else []
    evidence = _evidence_ids(task) if task else []
    status = _slot_status(slot_name, task, value, sources, evidence, upstream_missing_slots, required)
    reason = _missing_reason(slot_name, task, upstream_missing_slots, required)
    return {
        "slot_name": slot_name,
        "role": SLOT_ROLES.get(slot_name, "route-derived task slot"),
        "required": required,
        "status": status,
        "value": value,
        "source_ids": sources,
        "evidence_ids": evidence,
        "missing_reason": reason,
        "manual_review_required": status != SLOT_STATUS_NOT_APPLICABLE,
    }


def _slot_order(tasks_by_slot: Mapping[str, Mapping[str, Any]]) -> list[tuple[str, bool]]:
    ordered: list[tuple[str, bool]] = [(slot, True) for slot in REQUIRED_SLOT_ORDER]
    ordered.extend((slot, False) for slot in OPTIONAL_SLOT_ORDER)
    known = {slot for slot, _required in ordered}
    ordered.extend((slot, False) for slot in tasks_by_slot if slot not in known)
    return ordered


def build_plant_construct_task_draft(construct_task_result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a safe construct draft record from route-derived construct tasks."""
    task_result = dict(construct_task_result or {})
    if _route_blocked(task_result):
        return {
            "construct_draft_status": CONSTRUCT_DRAFT_STATUS_BLOCKED,
            "reason": "route not allowed / route generation blocked",
            "construct_slots": [],
            "manual_review_required": True,
            "safety_boundary": CONSTRUCT_DRAFT_BOUNDARY,
        }

    candidate = _candidate_route(task_result)
    tasks = _task_list(task_result)
    tasks_by_slot = _tasks_by_slot(tasks)
    upstream_missing_slots = _upstream_missing_slots(task_result, tasks)
    construct_slots = [
        _build_slot(slot, tasks_by_slot.get(slot), upstream_missing_slots, required)
        for slot, required in _slot_order(tasks_by_slot)
    ]
    required_slots = [slot for slot in construct_slots if slot["required"]]
    missing_required = [
        slot["slot_name"]
        for slot in required_slots
        if slot["status"] in {SLOT_STATUS_MISSING, SLOT_STATUS_NEEDS_SOURCE}
    ]
    unconfirmed_required = [
        slot["slot_name"] for slot in required_slots if slot["status"] != SLOT_STATUS_PRESENT
    ]
    if missing_required:
        draft_status = DRAFT_STATUS_INCOMPLETE
    elif unconfirmed_required:
        draft_status = DRAFT_STATUS_NEEDS_MANUAL_REVIEW
    else:
        draft_status = DRAFT_STATUS_COMPLETE_PENDING_REVIEW

    source_route_id = _first_text(
        task_result.get("source_route_id"),
        task_result.get("route_id"),
        candidate.get("route_id"),
    )
    route_label = _first_text(
        task_result.get("route_label"),
        task_result.get("route_framing"),
        candidate.get("route_framing"),
    )
    by_slot = {slot["slot_name"]: slot for slot in construct_slots}
    plant_host_or_context = _first_text(
        task_result.get("plant_host_or_context"),
        task_result.get("plant_host_context"),
        candidate.get("plant_host_context"),
        by_slot.get("plant_host_context", {}).get("value"),
    )

    return {
        "construct_draft_status": CONSTRUCT_DRAFT_STATUS_CREATED,
        "draft_id": _draft_id(source_route_id, route_label),
        "source_route_id": source_route_id,
        "route_label": route_label,
        "plant_host_or_context": plant_host_or_context,
        "goal_type": _first_text(task_result.get("goal_type"), task_result.get("matched_goal_type_id")),
        "route_type": _first_text(task_result.get("route_type"), task_result.get("route_framing"), route_label),
        "draft_status": draft_status,
        "manual_review_required": True,
        "required_slots_explicitly_confirmed": not unconfirmed_required,
        "missing_required_slots": missing_required,
        "safety_boundary": CONSTRUCT_DRAFT_BOUNDARY,
        "construct_slots": construct_slots,
    }
