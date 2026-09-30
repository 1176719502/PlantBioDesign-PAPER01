from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from services.plant_evidence_seed_intake import DEFAULT_RICE_ALBUMIN_SEED_DIR
from services.plant_review_manual_verification_consistency_audit import (
    build_plant_review_manual_verification_consistency_audit,
)
from services.plant_review_manual_verification_promotion_gate import (
    build_plant_review_manual_verification_promotion_gate,
)
from services.plant_review_manual_verification_status import (
    build_plant_review_manual_verification_status,
)
from services.plant_review_manual_verification_status_snapshot import (
    build_plant_review_manual_verification_status_snapshot,
)
from services.plant_review_task_queue import build_rice_albumin_manual_provenance_task_queue
from services.plant_review_task_queue_snapshot_readback import build_plant_review_task_queue_snapshot
from services.plant_seed_dataset_gate_registry import get_plant_seed_dataset_gate_record
from services.rice_albumin_manual_provenance_verification import (
    build_rice_albumin_manual_provenance_verification_payload,
)
from services.rice_albumin_manual_provenance_verification_queue import (
    build_rice_albumin_manual_provenance_verification_queue,
)
from services.rice_albumin_seed_review_workflow import build_rice_albumin_seed_review_workflow


OPERATOR_CHAIN_SCHEMA_VERSION = (
    "rice_albumin_operator_chain_continuity_readback.v2.7.r162"
)
OPERATOR_CHAIN_BATCH = "v2.7-r162"

CHAIN_KEY = "rice_albumin_operator_chain_continuity"
DATASET_KEY = "rice_albumin"
DATASET_LABEL = "Rice albumin local seed documentation review"

DOCUMENTATION_BOUNDARY = (
    "Read-only documentation-only rice albumin operator chain continuity readback. It "
    "summarizes existing local documentation-review payloads without writing data, "
    "filling identifiers, changing evidence standing, promoting records, choosing "
    "components, or judging downstream use."
)

CHAIN_STATUS_MANUAL_REVIEW = "manual_review_required"
CHAIN_STATUS_FAIL_CLOSED = "fail_closed_manual_review_required"
HANDOFF_STATUS_MANUAL_REVIEW = "documentation_readback_continuity_manual_review_required"
HANDOFF_STATUS_FAIL_CLOSED = "documentation_readback_continuity_fail_closed"

EXPECTED_STAGE_KEYS: tuple[str, ...] = (
    "seed_records",
    "seed_intake",
    "evidence_worksheet",
    "seed_review_workflow",
    "route_to_construct_traceability",
    "construct_task",
    "construct_draft",
    "provenance_verification",
    "manual_verification_queue",
    "manual_verification_status",
    "promotion_gate",
    "consistency_audit",
    "handoff_readback",
)

def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_CHAIN_TERMS: tuple[str, ...] = (
    _term("recommended ", "component"),
    _term("best ", "component"),
    _term("rank", "ing"),
    _term("valid", "ation"),
    _term("valid", "ated"),
    _term("opti", "mization"),
    _term("opti", "mized"),
    _term("suc", "cess"),
    _term("yield ", "pre", "diction"),
    _term("wet", "-lab", "-ready"),
    _term("wet-lab ", "ready"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("accepted ", "evidence"),
    _term("verified", "-ID"),
    _term("verified ", "ID"),
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _count(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _status_requires_manual_review(*values: Any) -> bool:
    joined = " ".join(_text(value).casefold() for value in values if _text(value))
    return (
        not joined
        or "manual_review" in joined
        or "review_required" in joined
        or "missing" in joined
        or "blocked" in joined
        or "fail_closed" in joined
        or "gap" in joined
        or "pending" in joined
    )


def _source_payload(
    explicit_payload: Mapping[str, Any] | None,
    builder: Any,
    *,
    warnings: list[str],
    label: str,
    **kwargs: Any,
) -> tuple[dict[str, Any], bool]:
    if explicit_payload is not None:
        if isinstance(explicit_payload, Mapping):
            return dict(explicit_payload), False
        warnings.append(f"{label} input is missing or malformed; chain readback fails closed.")
        return {}, True
    try:
        payload = builder(**kwargs)
    except Exception as exc:  # pragma: no cover - defensive readback guard
        warnings.append(f"{label} could not be built: {exc.__class__.__name__}; chain readback fails closed.")
        return {}, True
    if not isinstance(payload, Mapping):
        warnings.append(f"{label} builder returned non-mapping payload; chain readback fails closed.")
        return {}, True
    return dict(payload), False


def _stage(
    *,
    stage_key: str,
    stage_label: str,
    stage_status: str,
    stage_type: str,
    input_summary: str,
    output_summary: str,
    source_service: str,
    record_count: int = 0,
    gap_count: int = 0,
    manual_review_required: bool = True,
    promotion_blocked: bool = True,
    boundary_note: str = DOCUMENTATION_BOUNDARY,
    connected_to_previous: bool = True,
    connected_to_next: bool = True,
) -> dict[str, Any]:
    return {
        "stage_key": stage_key,
        "stage_label": stage_label,
        "stage_status": stage_status,
        "stage_type": stage_type,
        "input_summary": input_summary,
        "output_summary": output_summary,
        "connected_to_previous": connected_to_previous,
        "connected_to_next": connected_to_next,
        "source_service": source_service,
        "record_count": record_count,
        "gap_count": gap_count,
        "manual_review_required": manual_review_required,
        "promotion_blocked": promotion_blocked,
        "boundary_note": boundary_note,
    }


def _unavailable_stage(stage_key: str, stage_label: str, source_service: str) -> dict[str, Any]:
    return _stage(
        stage_key=stage_key,
        stage_label=stage_label,
        stage_status="unavailable_manual_review_required",
        stage_type="safe_unavailable_readback",
        input_summary="No upstream payload was supplied for this stage in the current rice albumin chain.",
        output_summary="Stage is represented as unavailable; no identifiers, records, or status changes were added.",
        source_service=source_service,
        gap_count=1,
        connected_to_previous=True,
        connected_to_next=True,
    )


def _seed_record_stage(seed_intake: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(seed_intake.get("summary"))
    total_records = _count(summary.get("total_records"))
    manual_count = _count(summary.get("manual_review_required_count"))
    gap_count = _count(summary.get("gap_record_count")) + _count(summary.get("rejected_row_count"))
    return _stage(
        stage_key="seed_records",
        stage_label="Seed records",
        stage_status="review_required_records_visible" if total_records else "no_seed_records_visible",
        stage_type="seed_record_readback",
        input_summary="Local rice albumin seed JSON records.",
        output_summary=f"{total_records} seed records represented; {manual_count} remain review-required.",
        source_service="services.plant_evidence_seed_intake.load_plant_evidence_seed_intake",
        record_count=total_records,
        gap_count=gap_count,
        connected_to_previous=False,
    )


def _seed_intake_stage(seed_intake: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(seed_intake.get("summary"))
    total_records = _count(summary.get("total_records"))
    gap_count = _count(summary.get("gap_record_count")) + _count(summary.get("rejected_row_count"))
    return _stage(
        stage_key="seed_intake",
        stage_label="Seed intake",
        stage_status=_text(seed_intake.get("seed_intake_status"), "seed_intake_unavailable"),
        stage_type="loader_readback",
        input_summary="R132 local seed intake loader output.",
        output_summary=f"{total_records} records loaded with {gap_count} visible gap or rejected rows.",
        source_service="services.plant_evidence_seed_intake",
        record_count=total_records,
        gap_count=gap_count,
    )


def _worksheet_stage(workflow_payload: Mapping[str, Any]) -> dict[str, Any]:
    worksheet = _mapping(workflow_payload.get("evidence_worksheet"))
    summary = _mapping(worksheet.get("summary"))
    evidence_count = _count(summary.get("evidence_row_count") or summary.get("total_evidence_rows"))
    component_count = _count(summary.get("component_slot_row_count"))
    followup_count = _count(summary.get("followup_queue_count"))
    return _stage(
        stage_key="evidence_worksheet",
        stage_label="Evidence worksheet",
        stage_status=_text(worksheet.get("worksheet_status"), "worksheet_unavailable"),
        stage_type="evidence_review_readback",
        input_summary="R132 worksheet input from seed intake.",
        output_summary=(
            f"{evidence_count} evidence rows, {component_count} component-slot rows, "
            f"{followup_count} follow-up rows."
        ),
        source_service="services.plant_evidence_review_worksheet_presenter",
        record_count=evidence_count + component_count,
        gap_count=followup_count,
    )


def _seed_review_stage(workflow_payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(workflow_payload.get("summary"))
    record_count = _count(summary.get("seed_record_count"))
    gap_count = _count(summary.get("seed_gap_record_count"))
    return _stage(
        stage_key="seed_review_workflow",
        stage_label="Seed review workflow",
        stage_status=_text(workflow_payload.get("workflow_status"), "seed_review_unavailable"),
        stage_type="workflow_readback",
        input_summary="R133 rice albumin seed review workflow.",
        output_summary=f"{record_count} seed records stitched into worksheet, traceability, and handoff readbacks.",
        source_service="services.rice_albumin_seed_review_workflow",
        record_count=record_count,
        gap_count=gap_count,
    )


def _traceability_stage(workflow_payload: Mapping[str, Any]) -> dict[str, Any]:
    traceability = _mapping(workflow_payload.get("route_construct_traceability"))
    summary = _mapping(traceability.get("summary"))
    trace_count = _count(summary.get("trace_row_count"))
    gap_count = _count(summary.get("gap_or_followup_count"))
    return _stage(
        stage_key="route_to_construct_traceability",
        stage_label="Route-to-construct traceability",
        stage_status=_text(traceability.get("traceability_status"), "traceability_unavailable"),
        stage_type="traceability_readback",
        input_summary="Seed worksheet plus existing route/context records.",
        output_summary=f"{trace_count} trace rows and {gap_count} gap or follow-up rows remain visible.",
        source_service="services.plant_route_construct_traceability_readback",
        record_count=trace_count,
        gap_count=gap_count,
    )


def _provenance_stage(provenance_payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(provenance_payload.get("summary"))
    total_records = _count(summary.get("total_records"))
    gaps = _count(summary.get("missing_source_id_count")) + _count(summary.get("missing_accession_count"))
    return _stage(
        stage_key="provenance_verification",
        stage_label="Provenance verification",
        stage_status=_text(provenance_payload.get("workflow_status"), "provenance_unavailable"),
        stage_type="manual_provenance_readback",
        input_summary="R143 manual provenance verification payload.",
        output_summary=f"{total_records} records checked for manual status; identifier gaps remain visible.",
        source_service="services.rice_albumin_manual_provenance_verification",
        record_count=total_records,
        gap_count=gaps,
    )


def _queue_stage(queue_payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(queue_payload.get("summary"))
    total_tasks = _count(summary.get("total_tasks"))
    represented = _count(summary.get("represented_record_count"))
    blocked = _count(summary.get("records_blocked_from_promotion"))
    return _stage(
        stage_key="manual_verification_queue",
        stage_label="Manual verification queue",
        stage_status=_text(queue_payload.get("workflow_status"), "manual_queue_unavailable"),
        stage_type="manual_task_queue",
        input_summary="R146 rice albumin manual provenance queue.",
        output_summary=f"{total_tasks} tasks represent {represented} records; {blocked} records remain blocked.",
        source_service="services.rice_albumin_manual_provenance_verification_queue",
        record_count=total_tasks,
        gap_count=total_tasks,
    )


def _manual_status_stage(status_snapshot_payload: Mapping[str, Any]) -> dict[str, Any]:
    task_summary = _mapping(status_snapshot_payload.get("task_summary"))
    status_summary = _mapping(status_snapshot_payload.get("verification_status_summary"))
    total_tasks = _count(task_summary.get("total_tasks"))
    status_records = _count(status_summary.get("total_status_records"))
    return _stage(
        stage_key="manual_verification_status",
        stage_label="Manual verification status",
        stage_status=_text(status_snapshot_payload.get("workflow_status"), "manual_status_unavailable"),
        stage_type="status_snapshot_readback",
        input_summary="R153 task snapshot plus R155 status readback.",
        output_summary=f"{total_tasks} tasks and {status_records} status records remain read-only.",
        source_service="services.plant_review_manual_verification_status_snapshot",
        record_count=status_records,
        gap_count=_count(task_summary.get("records_blocked_from_promotion")),
    )


def _promotion_gate_stage(gate_payload: Mapping[str, Any]) -> dict[str, Any]:
    total_tasks = _count(gate_payload.get("total_tasks"))
    blocked = _count(gate_payload.get("promotion_blocked_count"))
    return _stage(
        stage_key="promotion_gate",
        stage_label="Promotion gate",
        stage_status=_text(gate_payload.get("promotion_gate_status"), "promotion_gate_unavailable"),
        stage_type="promotion_gate_readback",
        input_summary="R158 manual verification promotion gate.",
        output_summary=f"{blocked} records remain blocked; no record is allowed to promote.",
        source_service="services.plant_review_manual_verification_promotion_gate",
        record_count=total_tasks,
        gap_count=blocked,
    )


def _audit_stage(audit_payload: Mapping[str, Any]) -> dict[str, Any]:
    return _stage(
        stage_key="consistency_audit",
        stage_label="Consistency audit",
        stage_status=_text(audit_payload.get("audit_status"), "consistency_audit_unavailable"),
        stage_type="consistency_audit_readback",
        input_summary="R159 queue, status, snapshot, and gate audit.",
        output_summary=(
            f"{_count(audit_payload.get('total_tasks'))} tasks audited; "
            f"{_count(audit_payload.get('promotion_conflict_count'))} promotion conflicts reported."
        ),
        source_service="services.plant_review_manual_verification_consistency_audit",
        record_count=_count(audit_payload.get("total_tasks")),
        gap_count=_count(audit_payload.get("tasks_without_status_count")),
    )


def _handoff_stage(workflow_payload: Mapping[str, Any], *, fail_closed: bool) -> dict[str, Any]:
    handoff = _mapping(workflow_payload.get("handoff_readback"))
    required_items = _sequence(handoff.get("required_review_items"))
    traceability = _mapping(handoff.get("route_construct_traceability_readback"))
    trace_summary = _mapping(traceability.get("summary"))
    return _stage(
        stage_key="handoff_readback",
        stage_label="Handoff readback",
        stage_status=HANDOFF_STATUS_FAIL_CLOSED if fail_closed else _text(handoff.get("handoff_status"), "handoff_unavailable"),
        stage_type="handoff_readback",
        input_summary="R133 handoff readback view from seed workflow.",
        output_summary=(
            f"{len(required_items)} required review items; "
            f"{_count(trace_summary.get('trace_row_count'))} trace rows available for readback."
        ),
        source_service="services.plant_review_handoff_data_adapter",
        record_count=len(required_items),
        gap_count=len(required_items),
        connected_to_next=False,
    )


def _stage_summary(stages: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    statuses = Counter(_text(stage.get("stage_status"), "unknown") for stage in stages)
    types = Counter(_text(stage.get("stage_type"), "unknown") for stage in stages)
    return {
        "stage_count": len(stages),
        "stage_keys": [_text(stage.get("stage_key")) for stage in stages],
        "available_stage_count": sum(
            1 for stage in stages if "unavailable" not in _text(stage.get("stage_status")).casefold()
        ),
        "unavailable_stage_count": sum(
            1 for stage in stages if "unavailable" in _text(stage.get("stage_status")).casefold()
        ),
        "manual_review_required_stage_count": sum(
            1 for stage in stages if stage.get("manual_review_required") is True
        ),
        "promotion_blocked_stage_count": sum(
            1 for stage in stages if stage.get("promotion_blocked") is True
        ),
        "total_record_rows_represented": sum(_count(stage.get("record_count")) for stage in stages),
        "total_gap_rows_represented": sum(_count(stage.get("gap_count")) for stage in stages),
        "stage_status_counts": {key: statuses[key] for key in sorted(statuses, key=str.casefold)},
        "stage_type_counts": {key: types[key] for key in sorted(types, key=str.casefold)},
    }


def _open_gaps(
    *,
    seed_intake: Mapping[str, Any],
    queue_payload: Mapping[str, Any],
    task_queue_payload: Mapping[str, Any],
    status_snapshot_payload: Mapping[str, Any],
    gate_payload: Mapping[str, Any],
    audit_payload: Mapping[str, Any],
    fail_closed: bool,
) -> list[dict[str, Any]]:
    seed_summary = _mapping(seed_intake.get("summary"))
    queue_summary = _mapping(queue_payload.get("summary"))
    task_summary = _mapping(task_queue_payload.get("summary"))
    snapshot_task_summary = _mapping(status_snapshot_payload.get("task_summary"))
    rows = [
        {
            "gap_key": "seed_records_review_required",
            "gap_label": "Seed records remain review-required",
            "gap_count": _count(seed_summary.get("manual_review_required_count")),
            "manual_review_required": True,
            "promotion_blocked": True,
        },
        {
            "gap_key": "manual_queue_tasks",
            "gap_label": "Manual provenance queue tasks remain open",
            "gap_count": _count(queue_summary.get("total_tasks")),
            "manual_review_required": True,
            "promotion_blocked": True,
        },
        {
            "gap_key": "records_blocked_from_promotion",
            "gap_label": "Records remain blocked from promotion",
            "gap_count": max(
                _count(queue_summary.get("records_blocked_from_promotion")),
                _count(task_summary.get("records_blocked_from_promotion")),
                _count(snapshot_task_summary.get("records_blocked_from_promotion")),
                _count(gate_payload.get("promotion_blocked_count")),
            ),
            "manual_review_required": True,
            "promotion_blocked": True,
        },
        {
            "gap_key": "missing_status_rows_default_pending",
            "gap_label": "Missing manual status rows are treated as pending review",
            "gap_count": _count(audit_payload.get("tasks_without_status_count")),
            "manual_review_required": True,
            "promotion_blocked": True,
        },
    ]
    if fail_closed:
        rows.append(
            {
                "gap_key": "upstream_payload_fail_closed",
                "gap_label": "One or more upstream payloads were missing or malformed",
                "gap_count": 1,
                "manual_review_required": True,
                "promotion_blocked": True,
            }
        )
    return _plain_value([row for row in rows if _count(row.get("gap_count")) or row["gap_key"] == "upstream_payload_fail_closed"])


def _manual_actions(queue_payload: Mapping[str, Any], gate_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = _mapping(queue_payload.get("summary"))
    reasons = [_text(reason) for reason in _sequence(gate_payload.get("blocking_reasons")) if _text(reason)]
    return _plain_value(
        [
            {
                "action_key": "complete_manual_provenance_review",
                "action_label": "Complete manual provenance review outside this readback",
                "source_stage": "manual_verification_queue",
                "task_count": _count(summary.get("total_tasks")),
                "record_count": _count(summary.get("represented_record_count")),
                "readback_only": True,
            },
            {
                "action_key": "keep_promotion_blocked",
                "action_label": "Keep record promotion blocked until a separately scoped review update",
                "source_stage": "promotion_gate",
                "task_count": _count(gate_payload.get("total_tasks")),
                "record_count": _count(gate_payload.get("represented_records")),
                "readback_only": True,
            },
            {
                "action_key": "review_gate_blocking_reasons",
                "action_label": "Review gate blocking reasons",
                "source_stage": "promotion_gate",
                "task_count": len(reasons),
                "record_count": _count(gate_payload.get("represented_records")),
                "readback_only": True,
            },
        ]
    )


def _promotion_status(
    *,
    queue_payload: Mapping[str, Any],
    task_queue_payload: Mapping[str, Any],
    status_snapshot_payload: Mapping[str, Any],
    gate_payload: Mapping[str, Any],
    audit_payload: Mapping[str, Any],
) -> dict[str, Any]:
    queue_summary = _mapping(queue_payload.get("summary"))
    task_summary = _mapping(task_queue_payload.get("summary"))
    snapshot_task_summary = _mapping(status_snapshot_payload.get("task_summary"))
    return {
        "promotion_allowed": False,
        "promotion_allowed_count": 0,
        "ready_to_promote_count": 0,
        "queue_ready_to_promote_count": _count(queue_summary.get("ready_to_promote_count")),
        "task_queue_ready_to_promote_count": _count(task_summary.get("ready_to_promote_count")),
        "status_snapshot_ready_to_promote_count": _count(snapshot_task_summary.get("ready_to_promote_count")),
        "gate_ready_to_promote_count": _count(gate_payload.get("ready_to_promote_count")),
        "audit_ready_to_promote_count": _count(audit_payload.get("ready_to_promote_count")),
        "records_blocked_from_promotion": max(
            _count(queue_summary.get("records_blocked_from_promotion")),
            _count(task_summary.get("records_blocked_from_promotion")),
            _count(snapshot_task_summary.get("records_blocked_from_promotion")),
            _count(gate_payload.get("promotion_blocked_count")),
        ),
        "record_was_promoted": False,
        "promotion_note": "Promotion remains blocked for documentation review.",
    }


def _identifier_autofill_status(provenance_payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(provenance_payload.get("summary"))
    return {
        "source_or_accession_auto_filled": summary.get("any_source_or_accession_auto_filled") is True,
        "pmid_doi_database_id_auto_filled": False,
        "record_was_promoted": summary.get("any_record_promoted") is True,
        "source_policy": _text(provenance_payload.get("source_policy")),
    }


def _inactive_dataset_gates() -> list[dict[str, Any]]:
    artemisia = get_plant_seed_dataset_gate_record("artemisia_annua")
    return [
        {
            "dataset_key": _text(artemisia.get("dataset_key")),
            "dataset_label": _text(artemisia.get("dataset_label")),
            "active_dataset_profile": artemisia.get("active_dataset_profile") is True,
            "conversion_allowed": artemisia.get("conversion_allowed") is True,
            "gate_status": _text(artemisia.get("gate_status")),
            "manual_review_required": artemisia.get("manual_review_required") is not False,
            "included_in_active_chain": False,
        }
    ]


def _assert_copy_safe(payload: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            for nested in value.values():
                walk(nested)
            return
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
            for nested in value:
                walk(nested)
            return
        if not isinstance(value, str):
            return
        text = value.casefold()
        for term in FORBIDDEN_CHAIN_TERMS:
            if term in text:
                findings.append(term)

    walk(payload)
    return sorted(set(findings), key=str.casefold)


def build_rice_albumin_operator_chain_continuity_readback(
    *,
    seed_dir: str | Path = DEFAULT_RICE_ALBUMIN_SEED_DIR,
    manual_verification_dir: str | Path | None = None,
    source_review_dir: str | Path | None = None,
    seed_review_payload: Mapping[str, Any] | None = None,
    provenance_payload: Mapping[str, Any] | None = None,
    manual_queue_payload: Mapping[str, Any] | None = None,
    task_queue_payload: Mapping[str, Any] | None = None,
    task_snapshot_payload: Mapping[str, Any] | None = None,
    manual_status_payload: Mapping[str, Any] | None = None,
    status_snapshot_payload: Mapping[str, Any] | None = None,
    promotion_gate_payload: Mapping[str, Any] | None = None,
    consistency_audit_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a read-only operator continuity payload for the rice albumin chain."""
    warnings: list[str] = []
    source_kwargs = {
        "seed_dir": seed_dir,
        "manual_verification_dir": manual_verification_dir,
        "source_review_dir": source_review_dir,
    }

    workflow, workflow_bad = _source_payload(
        seed_review_payload,
        build_rice_albumin_seed_review_workflow,
        warnings=warnings,
        label="seed review workflow",
        seed_dir=seed_dir,
    )
    provenance, provenance_bad = _source_payload(
        provenance_payload,
        build_rice_albumin_manual_provenance_verification_payload,
        warnings=warnings,
        label="manual provenance verification",
        **source_kwargs,
    )
    queue, queue_bad = _source_payload(
        manual_queue_payload,
        build_rice_albumin_manual_provenance_verification_queue,
        warnings=warnings,
        label="manual verification queue",
        payload=provenance,
        **source_kwargs,
    )
    task_queue, task_queue_bad = _source_payload(
        task_queue_payload,
        build_rice_albumin_manual_provenance_task_queue,
        warnings=warnings,
        label="plant review task queue",
        queue_payload=queue,
        **source_kwargs,
    )
    task_snapshot, task_snapshot_bad = _source_payload(
        task_snapshot_payload,
        build_plant_review_task_queue_snapshot,
        warnings=warnings,
        label="plant review task queue snapshot",
        source_kwargs_by_key={"rice_albumin_manual_provenance_verification": source_kwargs},
    )
    manual_status, manual_status_bad = _source_payload(
        manual_status_payload,
        build_plant_review_manual_verification_status,
        warnings=warnings,
        label="manual verification status",
        source_payload_or_rows=task_queue,
    )
    status_snapshot, status_snapshot_bad = _source_payload(
        status_snapshot_payload,
        build_plant_review_manual_verification_status_snapshot,
        warnings=warnings,
        label="manual verification status snapshot",
        task_snapshot_payload=task_queue,
        status_payload=manual_status,
    )
    gate, gate_bad = _source_payload(
        promotion_gate_payload,
        build_plant_review_manual_verification_promotion_gate,
        warnings=warnings,
        label="promotion gate",
        status_snapshot_payload=status_snapshot,
    )
    audit, audit_bad = _source_payload(
        consistency_audit_payload,
        build_plant_review_manual_verification_consistency_audit,
        warnings=warnings,
        label="consistency audit",
        task_queue_payload=task_queue,
        task_snapshot_payload=task_snapshot,
        status_payload=manual_status,
        status_snapshot_payload=status_snapshot,
        promotion_gate_payload=gate,
        queue_key="rice_albumin_manual_provenance_verification",
        dataset_key=DATASET_KEY,
    )

    seed_intake = _mapping(workflow.get("seed_intake"))
    fail_closed = any(
        (
            workflow_bad,
            provenance_bad,
            queue_bad,
            task_queue_bad,
            task_snapshot_bad,
            manual_status_bad,
            status_snapshot_bad,
            gate_bad,
            audit_bad,
            _mapping(task_queue.get("summary")).get("fail_closed") is True,
            status_snapshot.get("fail_closed") is True,
            gate.get("fail_closed") is True,
            audit.get("fail_closed") is True,
        )
    )

    stages = [
        _seed_record_stage(seed_intake),
        _seed_intake_stage(seed_intake),
        _worksheet_stage(workflow),
        _seed_review_stage(workflow),
        _traceability_stage(workflow),
        _unavailable_stage(
            "construct_task",
            "Construct task",
            "services.plant_route_construct_task_bridge",
        ),
        _unavailable_stage(
            "construct_draft",
            "Construct draft",
            "services.plant_construct_draft_readback_adapter",
        ),
        _provenance_stage(provenance),
        _queue_stage(queue),
        _manual_status_stage(status_snapshot),
        _promotion_gate_stage(gate),
        _audit_stage(audit),
        _handoff_stage(workflow, fail_closed=fail_closed),
    ]

    payload = {
        "operator_chain_schema_version": OPERATOR_CHAIN_SCHEMA_VERSION,
        "operator_chain_batch": OPERATOR_CHAIN_BATCH,
        "chain_key": CHAIN_KEY,
        "dataset_key": DATASET_KEY,
        "dataset_label": DATASET_LABEL,
        "active_dataset_keys": [DATASET_KEY],
        "chain_status": CHAIN_STATUS_FAIL_CLOSED if fail_closed else CHAIN_STATUS_MANUAL_REVIEW,
        "documentation_boundary": DOCUMENTATION_BOUNDARY,
        "stages": stages,
        "stage_summary": _stage_summary(stages),
        "open_gaps": _open_gaps(
            seed_intake=seed_intake,
            queue_payload=queue,
            task_queue_payload=task_queue,
            status_snapshot_payload=status_snapshot,
            gate_payload=gate,
            audit_payload=audit,
            fail_closed=fail_closed,
        ),
        "manual_actions": _manual_actions(queue, gate),
        "promotion_status": _promotion_status(
            queue_payload=queue,
            task_queue_payload=task_queue,
            status_snapshot_payload=status_snapshot,
            gate_payload=gate,
            audit_payload=audit,
        ),
        "handoff_readiness_status": HANDOFF_STATUS_FAIL_CLOSED if fail_closed else HANDOFF_STATUS_MANUAL_REVIEW,
        "fail_closed": fail_closed,
        "identifier_autofill_status": _identifier_autofill_status(provenance),
        "inactive_dataset_gates": _inactive_dataset_gates(),
        "copy_safety_findings": [],
        "warnings": warnings
        + [_text(warning) for warning in _sequence(workflow.get("warnings")) if _text(warning)]
        + [_text(warning) for warning in _sequence(provenance.get("warnings")) if _text(warning)]
        + [_text(warning) for warning in _sequence(queue.get("warnings")) if _text(warning)],
    }
    payload["copy_safety_findings"] = _assert_copy_safe(payload)
    if payload["copy_safety_findings"]:
        payload["fail_closed"] = True
        payload["chain_status"] = CHAIN_STATUS_FAIL_CLOSED
        payload["handoff_readiness_status"] = HANDOFF_STATUS_FAIL_CLOSED
        payload["warnings"].append("Chain readback copy-safety scan found blocked wording.")

    return _plain_value(payload)


def build_rice_albumin_operator_chain_continuity_stage_rows(
    payload: Mapping[str, Any] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Return compact stage rows for future readback consumers."""
    source = _mapping(payload) or build_rice_albumin_operator_chain_continuity_readback(**kwargs)
    return _plain_value([_mapping(stage) for stage in _sequence(source.get("stages"))])
