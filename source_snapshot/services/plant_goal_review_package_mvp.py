from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from services.plant_evidence_seed_intake import DEFAULT_RICE_ALBUMIN_SEED_DIR
from services.plant_seed_dataset_gate_registry import get_plant_seed_dataset_gate_record
from services.rice_albumin_operator_chain_continuity_readback import (
    build_rice_albumin_operator_chain_continuity_readback,
)
from services.rice_albumin_seed_review_workflow import build_rice_albumin_seed_review_workflow
from services.plant_manual_evidence_package_readback import (
    build_manual_evidence_package_readback,
)


PLANT_GOAL_REVIEW_PACKAGE_MVP_SCHEMA_VERSION = "plant_goal_review_package_mvp.v2.7.r163"
PLANT_GOAL_REVIEW_PACKAGE_MVP_BATCH = "v2.7-r163"

SUPPORTED_DATASET_KEY = "rice_albumin"
SUPPORTED_PACKAGE_KEY = "r163-rice-albumin-design-review-package-draft"

DOCUMENTATION_BOUNDARY = (
    "Documentation-only plant goal review package draft. It summarizes local rice albumin "
    "review records without writing data, filling identifiers, creating construct work, "
    "promoting records, choosing components, or judging downstream use."
)

SUPPORTED_SCOPE_NOTE = (
    "R163 supports only rice_albumin as the local MVP example. The package draft is a "
    "deterministic review record built from local services."
)

FAIL_CLOSED_STATUS = "fail_closed"
PACKAGE_STATUS_READY = "design_review_package_draft_ready"
PACKAGE_STATUS_FAIL_CLOSED = "design_review_package_draft_fail_closed"

DESIGN_SLOT_BLUEPRINTS: tuple[dict[str, str], ...] = (
    {
        "slot_key": "target_protein_product_goal",
        "slot_label": "target protein / product goal",
        "source_stage": "seed_records",
    },
    {
        "slot_key": "plant_host_or_expression_context",
        "slot_label": "plant host or expression context",
        "source_stage": "seed_intake",
    },
    {
        "slot_key": "candidate_route",
        "slot_label": "candidate route",
        "source_stage": "route_to_construct_traceability",
    },
    {
        "slot_key": "expression_component_slots",
        "slot_label": "expression component slots",
        "source_stage": "evidence_worksheet",
    },
    {
        "slot_key": "evidence_records",
        "slot_label": "evidence/source records",
        "source_stage": "evidence_worksheet",
    },
    {
        "slot_key": "provenance_identifiers",
        "slot_label": "provenance identifiers",
        "source_stage": "provenance_verification",
    },
    {
        "slot_key": "construct_task",
        "slot_label": "construct task",
        "source_stage": "construct_task",
    },
    {
        "slot_key": "construct_draft",
        "slot_label": "construct draft",
        "source_stage": "construct_draft",
    },
    {
        "slot_key": "manual_review_status",
        "slot_label": "manual review status",
        "source_stage": "manual_verification_queue",
    },
)

NON_PLANT_MARKERS: tuple[str, ...] = (
    "bacterial",
    "bacteria",
    "e coli",
    "e. coli",
    "ecoli",
    "escherichia",
    "yeast",
    "mammalian",
    "cho",
    "hek293",
    "animal cell",
)

PLANT_MARKERS: tuple[str, ...] = (
    "plant",
    "rice",
    "oryza",
    "seed",
    "leaf",
    "root",
    "chloroplast",
)

RICE_ALBUMIN_MARKERS: tuple[str, ...] = (
    "rice albumin",
    "albumin-like",
    "albumin like",
    "rice_albumin",
)


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_PACKAGE_TERMS: tuple[str, ...] = (
    _term("recom", "mendation"),
    _term("recom", "mended"),
    _term("rank", "ing"),
    _term("valid", "ation"),
    _term("valid", "ated"),
    _term("opti", "mization"),
    _term("opti", "mized"),
    _term("suc", "cess"),
    _term("yield ", "pre", "diction"),
    _term("accepted", "-", "evidence"),
    _term("accepted ", "evidence"),
    _term("production", "-ready"),
    _term("wet", "-lab", "-ready"),
    _term("wet-lab ", "ready"),
    _term("experiment", "-ready"),
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _key(value: Any) -> str:
    clean = _text(value).casefold().replace("-", "_").replace("/", "_").replace(" ", "_")
    return "_".join(part for part in clean.split("_") if part)


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


def _goal_text_and_dataset(user_plant_goal: Any, dataset_key: str | None) -> tuple[str, str]:
    if isinstance(user_plant_goal, Mapping):
        goal_text = _text(
            user_plant_goal.get("goal_text")
            or user_plant_goal.get("plant_goal")
            or user_plant_goal.get("goal")
            or user_plant_goal.get("request")
        )
        source_dataset = _text(dataset_key or user_plant_goal.get("dataset_key"))
        return goal_text, _key(source_dataset)
    return _text(user_plant_goal), _key(dataset_key)


def _infer_dataset_key(goal_text: str, explicit_dataset_key: str) -> str:
    if explicit_dataset_key:
        return explicit_dataset_key
    searchable = goal_text.casefold().replace("_", " ")
    if any(marker in searchable for marker in RICE_ALBUMIN_MARKERS):
        return SUPPORTED_DATASET_KEY
    if "artemisia" in searchable:
        return "artemisia_annua"
    return ""


def _is_non_plant_goal(goal_text: str) -> bool:
    searchable = goal_text.casefold().replace("_", " ")
    return any(marker in searchable for marker in NON_PLANT_MARKERS)


def _has_supported_rice_albumin_goal(goal_text: str) -> bool:
    searchable = goal_text.casefold().replace("_", " ")
    return (
        any(marker in searchable for marker in PLANT_MARKERS)
        and any(marker in searchable for marker in RICE_ALBUMIN_MARKERS)
    )


def _stage_by_key(chain_payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _text(stage.get("stage_key")): _mapping(stage)
        for stage in _sequence(chain_payload.get("stages"))
        if isinstance(stage, Mapping)
    }


def _seed_rows(seed_workflow_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    seed_intake = _mapping(seed_workflow_payload.get("seed_intake"))
    file_sections = _mapping(seed_intake.get("file_sections"))
    rows: list[dict[str, Any]] = []
    for section_key in sorted(file_sections, key=str.casefold):
        section = _mapping(file_sections.get(section_key))
        for record in _sequence(section.get("records")):
            row = _mapping(record)
            record_id = _text(row.get("record_id"))
            if not record_id:
                continue
            rows.append(
                {
                    "record_id": record_id,
                    "record_type": _text(row.get("record_type"), "SeedRecord"),
                    "record_label": _text(
                        row.get("component_name")
                        or row.get("evidence_label")
                        or row.get("target_or_route")
                        or row.get("slot_id"),
                        record_id,
                    ),
                    "seed_section": _text(section_key),
                    "review_status": _text(row.get("review_status"), "needs_manual_review"),
                    "needs_manual_review": row.get("needs_manual_review") is not False,
                    "provenance_status": _text(row.get("provenance_status"), "missing"),
                }
            )
    return sorted(rows, key=lambda item: (_text(item["seed_section"]).casefold(), _text(item["record_id"]).casefold()))


def _stage_status(stages: Mapping[str, Mapping[str, Any]], stage_key: str) -> str:
    return _text(_mapping(stages.get(stage_key)).get("stage_status"), "unavailable_manual_review_required")


def _design_slots(chain_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    stages = _stage_by_key(chain_payload)
    rows: list[dict[str, Any]] = []
    for blueprint in DESIGN_SLOT_BLUEPRINTS:
        stage_key = blueprint["source_stage"]
        stage = _mapping(stages.get(stage_key))
        rows.append(
            {
                **blueprint,
                "slot_status": _stage_status(stages, stage_key),
                "manual_review_required": True,
                "available_in_local_mvp": "unavailable" not in _stage_status(stages, stage_key).casefold(),
                "record_count": _count(stage.get("record_count")),
                "gap_count": _count(stage.get("gap_count")),
                "notes": _text(stage.get("output_summary"), "No local payload is available for this slot."),
            }
        )
    return _plain_value(rows)


def _matched_seed_records(seed_workflow_payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(seed_workflow_payload.get("summary"))
    records = _seed_rows(seed_workflow_payload)
    return {
        "dataset_key": SUPPORTED_DATASET_KEY,
        "represented_seed_record_count": _count(summary.get("seed_record_count")) or len(records),
        "manual_review_required_count": len([record for record in records if record.get("needs_manual_review") is True]),
        "records": records,
    }


def _evidence_summary(seed_workflow_payload: Mapping[str, Any], chain_payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(seed_workflow_payload.get("summary"))
    stage = _stage_by_key(chain_payload).get("evidence_worksheet", {})
    identifiers = _mapping(chain_payload.get("identifier_autofill_status"))
    return {
        "worksheet_evidence_row_count": _count(summary.get("worksheet_evidence_row_count")),
        "worksheet_component_slot_row_count": _count(summary.get("worksheet_component_slot_row_count")),
        "worksheet_followup_queue_count": _count(summary.get("worksheet_followup_queue_count")),
        "stage_status": _text(stage.get("stage_status")),
        "manual_review_required": True,
        "identifier_autofill_performed": identifiers.get("source_or_accession_auto_filled") is True
        or identifiers.get("pmid_doi_database_id_auto_filled") is True,
        "evidence_standing_changed": False,
    }


def _provenance_gap_summary(chain_payload: Mapping[str, Any]) -> dict[str, Any]:
    stages = _stage_by_key(chain_payload)
    provenance_stage = _mapping(stages.get("provenance_verification"))
    queue_stage = _mapping(stages.get("manual_verification_queue"))
    identifiers = _mapping(chain_payload.get("identifier_autofill_status"))
    return {
        "provenance_gap_count": _count(provenance_stage.get("gap_count")),
        "manual_provenance_queue_task_count": _count(queue_stage.get("record_count")),
        "represented_record_count": 12,
        "manual_review_required": True,
        "identifier_autofill": {
            "performed": False,
            "source_or_accession": identifiers.get("source_or_accession_auto_filled") is True,
            "pmid_doi_database_identifier": identifiers.get("pmid_doi_database_id_auto_filled") is True,
        },
    }


def _candidate_route_summary(seed_workflow_payload: Mapping[str, Any], chain_payload: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(seed_workflow_payload.get("summary"))
    stages = _stage_by_key(chain_payload)
    traceability = _mapping(stages.get("route_to_construct_traceability"))
    artemisia_gate = get_plant_seed_dataset_gate_record("artemisia_annua")
    return {
        "candidate_route_status": _text(traceability.get("stage_status"), "manual_review_required"),
        "dataset_key": SUPPORTED_DATASET_KEY,
        "active_local_dataset": True,
        "traceability_row_count": _count(summary.get("traceability_row_count")),
        "gap_or_followup_count": _count(traceability.get("gap_count")),
        "artemisia_annua_status": {
            "dataset_key": "artemisia_annua",
            "active_dataset_profile": artemisia_gate.get("active_dataset_profile") is True,
            "conversion_allowed": artemisia_gate.get("conversion_allowed") is True,
            "gate_status": _text(artemisia_gate.get("gate_status")),
            "included_in_mvp_path": False,
        },
    }


def _construct_status_summary(chain_payload: Mapping[str, Any]) -> dict[str, Any]:
    stages = _stage_by_key(chain_payload)
    task = _mapping(stages.get("construct_task"))
    draft = _mapping(stages.get("construct_draft"))
    return {
        "construct_task": {
            "status": _text(task.get("stage_status"), "unavailable_manual_review_required"),
            "auto_created": False,
            "unavailable_reason": _text(
                task.get("output_summary"),
                "Construct task is not created by the R163 MVP package draft.",
            ),
        },
        "construct_draft": {
            "status": _text(draft.get("stage_status"), "unavailable_manual_review_required"),
            "auto_created": False,
            "unavailable_reason": _text(
                draft.get("output_summary"),
                "Construct draft is not created by the R163 MVP package draft.",
            ),
        },
        "manual_review_required": True,
    }


def _manual_review_task_summary(chain_payload: Mapping[str, Any]) -> dict[str, Any]:
    promotion = _mapping(chain_payload.get("promotion_status"))
    stages = _stage_by_key(chain_payload)
    queue_stage = _mapping(stages.get("manual_verification_queue"))
    return {
        "manual_provenance_queue_task_count": _count(queue_stage.get("record_count")),
        "represented_record_count": _count(promotion.get("records_blocked_from_promotion")),
        "records_blocked_from_promotion": _count(promotion.get("records_blocked_from_promotion")),
        "ready_to_promote_count": _count(promotion.get("ready_to_promote_count")),
        "promotion_allowed_count": _count(promotion.get("promotion_allowed_count")),
        "manual_review_required": True,
    }


def _promotion_boundary(chain_payload: Mapping[str, Any]) -> dict[str, Any]:
    promotion = _mapping(chain_payload.get("promotion_status"))
    return {
        "promotion_allowed": False,
        "promotion_allowed_count": 0,
        "ready_to_promote_count": 0,
        "records_blocked_from_promotion": _count(promotion.get("records_blocked_from_promotion")),
        "record_was_promoted": False,
        "boundary_note": "Record promotion remains blocked for local documentation review.",
    }


def _next_human_actions(chain_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    manual_summary = _manual_review_task_summary(chain_payload)
    return [
        {
            "action_key": "review_design_intent",
            "action_label": "Confirm the rice albumin-like plant goal and local dataset scope.",
            "action_status": "manual_review_required",
        },
        {
            "action_key": "complete_manual_provenance_queue",
            "action_label": "Review open provenance tasks before any separately scoped seed-data update.",
            "action_status": "manual_review_required",
            "task_count": manual_summary["manual_provenance_queue_task_count"],
        },
        {
            "action_key": "keep_construct_work_uncreated",
            "action_label": "Keep construct task and draft unavailable until missing review context is handled.",
            "action_status": "blocked_in_this_mvp",
        },
        {
            "action_key": "keep_artemisia_inactive",
            "action_label": "Keep Artemisia annua outside the active MVP path.",
            "action_status": "blocked_in_this_mvp",
        },
    ]


def _blocked_outputs() -> list[dict[str, Any]]:
    return [
        {
            "output_key": "construct_task_auto_create",
            "blocked": True,
            "reason": "R163 returns a review package draft only.",
        },
        {
            "output_key": "construct_draft_auto_create",
            "blocked": True,
            "reason": "Construct draft remains unavailable in this MVP.",
        },
        {
            "output_key": "identifier_autofill",
            "blocked": True,
            "reason": "No source or database identifier is filled.",
        },
        {
            "output_key": "record_promotion",
            "blocked": True,
            "reason": "Manual review remains required and promotion is blocked.",
        },
        {
            "output_key": "external_lookup",
            "blocked": True,
            "reason": "The service uses local deterministic payloads only.",
        },
        {
            "output_key": "ui_report_export_persistence",
            "blocked": True,
            "reason": "R163 adds no UI mount, report path, export file, or storage behavior.",
        },
    ]


def _sections() -> list[dict[str, str]]:
    return [
        {"section_key": "design_intent", "section_title": "Design Intent"},
        {"section_key": "required_design_slots", "section_title": "Required design slots"},
        {"section_key": "matched_seed_records", "section_title": "Matched local rice_albumin seed records"},
        {"section_key": "evidence_provenance_gaps", "section_title": "Evidence/provenance gaps"},
        {"section_key": "candidate_route_status", "section_title": "Candidate route status"},
        {"section_key": "construct_task_draft_status", "section_title": "Construct task/draft status"},
        {"section_key": "manual_review_tasks", "section_title": "Manual review tasks"},
        {"section_key": "manual_evidence_queue_readback", "section_title": "Manual evidence queue readback"},
        {"section_key": "promotion_boundary", "section_title": "Promotion boundary"},
        {"section_key": "next_human_actions", "section_title": "Next human actions"},
    ]


def _copy_safety_findings(payload: Mapping[str, Any]) -> list[str]:
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
        for term in FORBIDDEN_PACKAGE_TERMS:
            if term in text:
                findings.append(term)

    walk(payload)
    return sorted(set(findings), key=str.casefold)


def _empty_fail_closed_package(
    *,
    goal_text: str,
    dataset_key: str,
    reason: str,
    guidance: str,
    manual_evidence_preflight_payload: Any = None,
) -> dict[str, Any]:
    artemisia_gate = get_plant_seed_dataset_gate_record("artemisia_annua")
    payload = {
        "package_schema_version": PLANT_GOAL_REVIEW_PACKAGE_MVP_SCHEMA_VERSION,
        "package_batch": PLANT_GOAL_REVIEW_PACKAGE_MVP_BATCH,
        "package_key": f"r163-{_key(dataset_key) or 'unknown'}-design-review-package-draft",
        "package_status": PACKAGE_STATUS_FAIL_CLOSED,
        "goal_text": goal_text,
        "dataset_key": dataset_key or "unknown_dataset",
        "intent_summary": {
            "section_title": "Design Intent",
            "intent_status": FAIL_CLOSED_STATUS,
            "summary": reason,
            "guidance": guidance,
        },
        "supported_scope": {
            "supported": False,
            "supported_dataset_key": SUPPORTED_DATASET_KEY,
            "scope_note": SUPPORTED_SCOPE_NOTE,
        },
        "design_slots": [],
        "matched_seed_records": {"represented_seed_record_count": 0, "records": []},
        "evidence_summary": {"manual_review_required": True, "identifier_autofill_performed": False},
        "provenance_gap_summary": {
            "manual_review_required": True,
            "identifier_autofill": {
                "performed": False,
                "source_or_accession": False,
                "pmid_doi_database_identifier": False,
            },
        },
        "candidate_route_summary": {
            "candidate_route_status": FAIL_CLOSED_STATUS,
            "dataset_key": dataset_key or "unknown_dataset",
            "active_local_dataset": False,
            "artemisia_annua_status": {
                "dataset_key": "artemisia_annua",
                "active_dataset_profile": artemisia_gate.get("active_dataset_profile") is True,
                "conversion_allowed": artemisia_gate.get("conversion_allowed") is True,
                "gate_status": _text(artemisia_gate.get("gate_status")),
                "included_in_mvp_path": False,
            },
        },
        "construct_status_summary": {
            "construct_task": {"status": "unavailable_manual_review_required", "auto_created": False},
            "construct_draft": {"status": "unavailable_manual_review_required", "auto_created": False},
            "manual_review_required": True,
        },
        "manual_review_task_summary": {
            "manual_provenance_queue_task_count": 0,
            "records_blocked_from_promotion": 0,
            "ready_to_promote_count": 0,
            "promotion_allowed_count": 0,
            "manual_review_required": True,
        },
        "manual_evidence_review_queue_readback": build_manual_evidence_package_readback(
            manual_evidence_preflight_payload
        ),
        "promotion_boundary": {
            "promotion_allowed": False,
            "promotion_allowed_count": 0,
            "ready_to_promote_count": 0,
            "record_was_promoted": False,
            "boundary_note": "Record promotion remains blocked for local documentation review.",
        },
        "next_human_actions": [
            {
                "action_key": "use_supported_rice_albumin_example",
                "action_label": "Use a rice albumin-like plant goal with dataset_key rice_albumin.",
                "action_status": "manual_review_required",
            }
        ],
        "blocked_outputs": _blocked_outputs(),
        "documentation_boundary": DOCUMENTATION_BOUNDARY,
        "sections": _sections(),
        "fail_closed": True,
        "copy_safety_findings": [],
    }
    payload["copy_safety_findings"] = _copy_safety_findings(payload)
    return _plain_value(payload)

def build_plant_goal_review_package_mvp(
    user_plant_goal: Any,
    dataset_key: str | None = None,
    *,
    seed_dir: str | Path = DEFAULT_RICE_ALBUMIN_SEED_DIR,
    manual_evidence_preflight_payload: Any = None,
) -> dict[str, Any]:
    """Return a deterministic plant goal to Design Review Package Draft payload."""
    goal_text, explicit_dataset_key = _goal_text_and_dataset(user_plant_goal, dataset_key)
    resolved_dataset_key = _infer_dataset_key(goal_text, explicit_dataset_key)

    if not goal_text:
        return _empty_fail_closed_package(
            goal_text=goal_text,
            dataset_key=resolved_dataset_key,
            reason="No plant goal text was supplied.",
            guidance="Provide a rice albumin-like plant goal and use dataset_key rice_albumin.",
            manual_evidence_preflight_payload=manual_evidence_preflight_payload,
        )
    if _is_non_plant_goal(goal_text):
        return _empty_fail_closed_package(
            goal_text=goal_text,
            dataset_key=resolved_dataset_key,
            reason="The goal appears outside the plant-only R163 MVP scope.",
            guidance="Use a plant-focused rice albumin-like goal for the local MVP path.",
            manual_evidence_preflight_payload=manual_evidence_preflight_payload,
        )
    if resolved_dataset_key != SUPPORTED_DATASET_KEY:
        return _empty_fail_closed_package(
            goal_text=goal_text,
            dataset_key=resolved_dataset_key,
            reason="The requested dataset is not an active R163 MVP dataset.",
            guidance="R163 supports only dataset_key rice_albumin. Artemisia annua remains inactive.",
            manual_evidence_preflight_payload=manual_evidence_preflight_payload,
        )
    if not _has_supported_rice_albumin_goal(goal_text):
        return _empty_fail_closed_package(
            goal_text=goal_text,
            dataset_key=resolved_dataset_key,
            reason="The goal does not match the supported rice albumin-like plant MVP path.",
            guidance="Use a rice albumin-like plant review goal for the R163 local package draft.",
            manual_evidence_preflight_payload=manual_evidence_preflight_payload,
        )

    seed_workflow = build_rice_albumin_seed_review_workflow(seed_dir=seed_dir)
    chain_payload = build_rice_albumin_operator_chain_continuity_readback(seed_dir=seed_dir)
    matched_seed_records = _matched_seed_records(seed_workflow)
    manual_summary = _manual_review_task_summary(chain_payload)
    promotion_boundary = _promotion_boundary(chain_payload)

    payload = {
        "package_schema_version": PLANT_GOAL_REVIEW_PACKAGE_MVP_SCHEMA_VERSION,
        "package_batch": PLANT_GOAL_REVIEW_PACKAGE_MVP_BATCH,
        "package_key": SUPPORTED_PACKAGE_KEY,
        "package_status": PACKAGE_STATUS_READY,
        "goal_text": goal_text,
        "dataset_key": SUPPORTED_DATASET_KEY,
        "intent_summary": {
            "section_title": "Design Intent",
            "intent_status": "supported_local_rice_albumin_goal",
            "summary": "Review a rice albumin-like protein expression design in a plant system.",
            "manual_review_required": True,
            "local_dataset_key": SUPPORTED_DATASET_KEY,
        },
        "supported_scope": {
            "supported": True,
            "supported_dataset_key": SUPPORTED_DATASET_KEY,
            "scope_note": SUPPORTED_SCOPE_NOTE,
            "local_only": True,
        },
        "design_slots": _design_slots(chain_payload),
        "matched_seed_records": matched_seed_records,
        "evidence_summary": _evidence_summary(seed_workflow, chain_payload),
        "provenance_gap_summary": _provenance_gap_summary(chain_payload),
        "candidate_route_summary": _candidate_route_summary(seed_workflow, chain_payload),
        "construct_status_summary": _construct_status_summary(chain_payload),
        "manual_review_task_summary": manual_summary,
        "manual_evidence_review_queue_readback": build_manual_evidence_package_readback(
            manual_evidence_preflight_payload
        ),
        "promotion_boundary": promotion_boundary,
        "next_human_actions": _next_human_actions(chain_payload),
        "blocked_outputs": _blocked_outputs(),
        "documentation_boundary": DOCUMENTATION_BOUNDARY,
        "sections": _sections(),
        "side_effects": {
            "seed_data_changed": False,
            "record_promoted": False,
            "construct_task_created": False,
            "construct_draft_created": False,
            "ui_added": False,
            "report_added": False,
            "export_added": False,
            "persistence_added": False,
        },
        "fail_closed": chain_payload.get("fail_closed") is True,
        "copy_safety_findings": [],
    }
    payload["copy_safety_findings"] = _copy_safety_findings(payload)
    if payload["copy_safety_findings"]:
        payload["package_status"] = PACKAGE_STATUS_FAIL_CLOSED
        payload["fail_closed"] = True

    return _plain_value(payload)
