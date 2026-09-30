from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


SCHEMA_VERSION = "v2.7-r220"
BOUNDARY_NOTE = (
    "Candidate Route Review Draft is read-only and session-scoped. It organizes the current plant goal, "
    "route readback, required design slot status, manual evidence status, review gate status, and safe next "
    "actions without creating construct tasks, construct drafts, package output, source confirmation, "
    "biological recommendation, validation, optimization, sequence content, or wet-lab use judgment."
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _first_text(*values: Any) -> str:
    for value in values:
        clean = _text(value)
        if clean:
            return clean
    return ""


def _status_label(value: Any) -> str:
    return _text(value).replace("_", " ") or "not recorded"


def _completion_from_draft(project_draft: Mapping[str, Any]) -> dict[str, Any]:
    completion = _mapping(project_draft.get("design_slot_completion"))
    summary = _mapping(project_draft.get("design_slot_completion_summary"))
    if completion:
        return completion
    return {"completion_summary": summary, "slot_rows": []}


def _missing_slot_labels(completion: Mapping[str, Any], gate_slots: Mapping[str, Any]) -> list[str]:
    summary = _mapping(completion.get("completion_summary"))
    missing_keys = {_text(value) for value in _list(summary.get("missing_slots")) if _text(value)}
    labels: list[str] = []
    for row in _list(completion.get("slot_rows")):
        row_map = _mapping(row)
        slot_key = _text(row_map.get("slot_key"))
        if slot_key and slot_key in missing_keys:
            labels.append(_first_text(row_map.get("slot_label"), slot_key))
    if labels:
        return labels
    for value in _list(gate_slots.get("missing_slots")):
        clean = _text(value)
        if clean:
            labels.append(clean)
    return labels


def _manual_evidence_context(
    manual_evidence_panel_payload: Mapping[str, Any],
    completion_gate_payload: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = _mapping(completion_gate_payload.get("manual_evidence"))
    panel = _mapping(manual_evidence_panel_payload)
    queue_payload = _mapping(panel.get("queue_payload"))
    queue_summary = _mapping(queue_payload.get("summary"))
    gap_payload = _mapping(panel.get("gap_assistant_payload"))
    gap_summary = _mapping(gap_payload.get("summary"))
    return {
        "entry_status": _first_text(evidence.get("entry_status"), "safe_empty_manual_evidence_entry"),
        "queue_status": _first_text(evidence.get("queue_status"), "manual_evidence_queue_empty"),
        "gap_status": _first_text(evidence.get("gap_status"), gap_summary.get("gap_status"), "not recorded"),
        "row_count": int(evidence.get("row_count") or queue_summary.get("row_count") or 0),
        "review_needed_count": int(
            evidence.get("review_needed_count") or queue_summary.get("review_needed_count") or 0
        ),
        "blocked_count": int(evidence.get("blocked_count") or queue_summary.get("blocked_count") or 0),
        "preview_only_count": int(evidence.get("preview_only_count") or queue_summary.get("preview_only_count") or 0),
    }


def _evidence_blockers(
    top_blockers: Sequence[Mapping[str, Any]],
    manual_evidence: Mapping[str, Any],
) -> list[dict[str, Any]]:
    blocker_types = {
        "missing_source_notes",
        "preview_only_evidence",
        "conflict_deprecated_markers",
    }
    rows = [
        {
            "Blocker": _text(row.get("Blocker")),
            "Type": _text(row.get("Type")),
            "Count": row.get("Count", 0),
            "Action": _text(row.get("Action")),
        }
        for row in top_blockers
        if _text(row.get("Type")) in blocker_types
    ]
    if not rows and (
        int(manual_evidence.get("blocked_count") or 0) or int(manual_evidence.get("preview_only_count") or 0)
    ):
        rows.append(
            {
                "Blocker": "Manual evidence has blocked or preview-only rows.",
                "Type": "manual_evidence_readback_blocker",
                "Count": int(manual_evidence.get("blocked_count") or 0)
                + int(manual_evidence.get("preview_only_count") or 0),
                "Action": "Review manual evidence gaps.",
            }
        )
    return rows


def _route_review_status(
    *,
    route_id: str,
    missing_slot_count: int,
    evidence_blocker_count: int,
    completed_slot_count: int,
) -> str:
    if not route_id:
        return "safe_empty_candidate_route_draft"
    if missing_slot_count:
        return "blocked_by_required_design_slots"
    if evidence_blocker_count:
        return "blocked_by_manual_evidence"
    if completed_slot_count:
        return "reviewable_draft_only"
    return "draft_needs_manual_review"


def _safe_next_actions(
    *,
    missing_slot_count: int,
    evidence_blocker_count: int,
    gate_actions: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if missing_slot_count:
        actions.append(
            {
                "Area": "Required design slots",
                "Action": "Fill required design information",
                "Reason": "Candidate route draft cannot move toward construct-task review while required slots are blank.",
                "Readback-only": "yes",
            }
        )
    if evidence_blocker_count:
        actions.append(
            {
                "Area": "Manual evidence gap assistant",
                "Action": "Review manual evidence gaps",
                "Reason": "Evidence blockers or preview-only rows remain visible in the readback.",
                "Readback-only": "yes",
            }
        )
    for row in gate_actions:
        row_map = _mapping(row)
        action = _text(row_map.get("Action"))
        if action and all(action != existing.get("Action") for existing in actions):
            actions.append(
                {
                    "Area": _first_text(row_map.get("Area"), "Project review completion gate"),
                    "Action": action,
                    "Reason": _text(row_map.get("Reason")),
                    "Readback-only": _first_text(row_map.get("Readback-only"), "yes"),
                }
            )
    if not any(row.get("Action") == "Review package/handoff readback" for row in actions):
        actions.append(
            {
                "Area": "Package/handoff readback",
                "Action": "Review package/handoff readback",
                "Reason": "Keep package and handoff context separate from the candidate route draft.",
                "Readback-only": "yes",
            }
        )
    return actions


def build_candidate_route_review_draft(
    *,
    project_draft_payload: Mapping[str, Any] | None,
    workflow: Mapping[str, Any] | None = None,
    manual_evidence_panel_payload: Mapping[str, Any] | None = None,
    completion_gate_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    project_draft = _mapping(project_draft_payload)
    workflow_data = _mapping(workflow)
    gate = _mapping(completion_gate_payload)
    manual_evidence_panel = _mapping(manual_evidence_panel_payload)
    selected_route = _mapping(project_draft.get("selected_route"))
    route_gate = _mapping(gate.get("route_confirmation"))
    gate_slots = _mapping(gate.get("design_slot_completion"))
    completion = _completion_from_draft(project_draft)
    completion_summary = _mapping(completion.get("completion_summary"))
    route_id = _first_text(selected_route.get("route_id"), route_gate.get("route_id"))
    route_label = _first_text(
        selected_route.get("label_en"),
        selected_route.get("result_label_zh"),
        selected_route.get("label_zh"),
        route_gate.get("route_label"),
    )
    completed_slot_count = int(
        completion_summary.get("completed_slot_count") or gate_slots.get("completed_slot_count") or 0
    )
    missing_slot_count = int(
        completion_summary.get("missing_slot_count") or gate_slots.get("missing_slot_count") or 0
    )
    total_required_slot_count = int(
        gate_slots.get("total_required_slot_count") or completed_slot_count + missing_slot_count
    )
    missing_slots = _missing_slot_labels(completion, gate_slots)
    top_blockers = [_mapping(row) for row in _list(gate.get("top_blockers")) if isinstance(row, Mapping)]
    manual_evidence = _manual_evidence_context(manual_evidence_panel, gate)
    evidence_blockers = _evidence_blockers(top_blockers, manual_evidence)
    review_status = _route_review_status(
        route_id=route_id,
        missing_slot_count=missing_slot_count,
        evidence_blocker_count=len(evidence_blockers),
        completed_slot_count=completed_slot_count,
    )
    construct_reason = (
        "Missing required design slots remain visible."
        if missing_slot_count
        else "Manual evidence blockers or preview-only rows remain visible."
        if evidence_blockers
        else "Construct task draft is separate and is not created automatically from this route draft."
    )
    package_gate = _mapping(gate.get("package_handoff_readback"))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "section_title": "Candidate Route Review Draft",
        "boundary_note": BOUNDARY_NOTE,
        "read_only": True,
        "session_state_only": True,
        "documentation_only": True,
        "manual_review_required": True,
        "draft_only": True,
        "construct_task_created": False,
        "construct_draft_created": False,
        "can_advance_to_construct_task": False,
        "advance_blocker_reason": construct_reason,
        "current_plant_goal": _first_text(project_draft.get("goal_description"), "No plant goal is recorded."),
        "route_readback": {
            "route_id": route_id,
            "route_label": route_label or "No confirmed route is in the current session.",
            "route_confirmation_status": _first_text(route_gate.get("status"), "no_current_project_draft"),
            "route_review_status": review_status,
            "route_readiness_status": review_status,
            "readback": _first_text(route_gate.get("readback"), route_label, route_id, "No route readback is available."),
        },
        "required_design_slots": {
            "status": _first_text(gate_slots.get("status"), _status_label(completion_summary.get("completion_status"))),
            "completed_slot_count": completed_slot_count,
            "missing_slot_count": missing_slot_count,
            "total_required_slot_count": total_required_slot_count,
            "missing_slots": missing_slots,
        },
        "manual_evidence": manual_evidence,
        "evidence_blockers": evidence_blockers,
        "manual_review_requirements": [
            "Manual review remains required for route interpretation.",
            "Manual evidence gap assistant rows remain readback-only.",
            "Package/handoff readback is separate from this candidate route draft.",
        ],
        "project_review_completion_status": _first_text(package_gate.get("status"), "not recorded"),
        "package_handoff_readback": {
            "status": _first_text(package_gate.get("status"), "not recorded"),
            "readback": _first_text(package_gate.get("readback"), "Package/handoff readback remains separate."),
        },
        "workflow_status": _first_text(workflow_data.get("workflow_status"), "not recorded"),
    }
    payload["safe_next_actions"] = _safe_next_actions(
        missing_slot_count=missing_slot_count,
        evidence_blocker_count=len(evidence_blockers),
        gate_actions=[_mapping(row) for row in _list(gate.get("safe_next_actions")) if isinstance(row, Mapping)],
    )
    payload["status_rows"] = candidate_route_status_rows(payload)
    payload["blocker_rows"] = candidate_route_blocker_rows(payload)
    return payload


def candidate_route_status_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    route = _mapping(payload.get("route_readback"))
    slots = _mapping(payload.get("required_design_slots"))
    evidence = _mapping(payload.get("manual_evidence"))
    package = _mapping(payload.get("package_handoff_readback"))
    return [
        {
            "Checkpoint": "Current plant goal",
            "Status": "recorded" if _text(payload.get("current_plant_goal")) != "No plant goal is recorded." else "not recorded",
            "Readback": _text(payload.get("current_plant_goal")),
            "Next action": "Confirm route and complete review fields." if not _text(route.get("route_id")) else "Review route draft context.",
        },
        {
            "Checkpoint": "Selected/confirmed route",
            "Status": _status_label(route.get("route_confirmation_status")),
            "Readback": _first_text(route.get("route_label"), route.get("route_id"), "not recorded"),
            "Next action": "Keep as candidate route draft for manual review.",
        },
        {
            "Checkpoint": "Route review status",
            "Status": _status_label(route.get("route_review_status")),
            "Readback": "Draft-only candidate route readback; no construct task is created.",
            "Next action": _text(payload.get("advance_blocker_reason")),
        },
        {
            "Checkpoint": "Required design slots",
            "Status": _status_label(slots.get("status")),
            "Readback": (
                f"{slots.get('completed_slot_count', 0)} completed / "
                f"{slots.get('missing_slot_count', 0)} missing"
            ),
            "Next action": "Fill required design information." if slots.get("missing_slot_count") else "Review manual evidence gaps.",
        },
        {
            "Checkpoint": "Manual evidence",
            "Status": _status_label(evidence.get("queue_status")),
            "Readback": (
                f"review {evidence.get('review_needed_count', 0)} / "
                f"blocked {evidence.get('blocked_count', 0)} / "
                f"preview {evidence.get('preview_only_count', 0)}"
            ),
            "Next action": "Review manual evidence gaps.",
        },
        {
            "Checkpoint": "Package/handoff readback",
            "Status": _status_label(package.get("status")),
            "Readback": _text(package.get("readback")),
            "Next action": "Keep package/handoff readback separate.",
        },
    ]


def candidate_route_blocker_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    slots = _mapping(payload.get("required_design_slots"))
    missing_slots = _list(slots.get("missing_slots"))
    if missing_slots:
        rows.append(
            {
                "Blocker": "; ".join(_text(value) for value in missing_slots[:6] if _text(value)),
                "Type": "missing_required_design_slots",
                "Count": len(missing_slots),
                "Action": "Fill required design information.",
            }
        )
    rows.extend(_mapping(row) for row in _list(payload.get("evidence_blockers")) if isinstance(row, Mapping))
    if not rows:
        rows.append(
            {
                "Blocker": "No route blocker is calculated beyond manual review.",
                "Type": "draft_manual_review_boundary",
                "Count": 0,
                "Action": "Keep candidate route as draft-only readback.",
            }
        )
    return rows
