# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from services import plant_goal_review_package_mvp as r163


ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "plant_seed" / "rice_albumin"
SEED_FILES = (
    SEED_DIR / "route_contexts.json",
    SEED_DIR / "component_records.json",
    SEED_DIR / "evidence_records.json",
)

RICE_ALBUMIN_GOAL = "Review a rice albumin-like protein expression design in a plant system."


def _term(*parts: str) -> str:
    return "".join(parts)


BLOCKED_OUTPUT_COPY = (
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


def _payload() -> dict[str, object]:
    return r163.build_plant_goal_review_package_mvp(RICE_ALBUMIN_GOAL)


def _walk_strings(value: object) -> list[str]:
    if isinstance(value, dict):
        rows: list[str] = []
        for key, nested in value.items():
            rows.append(str(key))
            rows.extend(_walk_strings(nested))
        return rows
    if isinstance(value, list):
        rows = []
        for nested in value:
            rows.extend(_walk_strings(nested))
        return rows
    if isinstance(value, str):
        return [value]
    return []


def _copy_scan_value(value: object) -> None:
    text = "\n".join(_walk_strings(value)).casefold()
    for phrase in BLOCKED_OUTPUT_COPY:
        assert phrase not in text


def test_r163_rice_albumin_goal_returns_complete_package_draft() -> None:
    payload = _payload()

    assert payload["package_schema_version"] == r163.PLANT_GOAL_REVIEW_PACKAGE_MVP_SCHEMA_VERSION
    assert payload["package_key"] == r163.SUPPORTED_PACKAGE_KEY
    assert payload["package_status"] == r163.PACKAGE_STATUS_READY
    assert payload["goal_text"] == RICE_ALBUMIN_GOAL
    assert payload["dataset_key"] == "rice_albumin"
    assert payload["fail_closed"] is False
    assert payload["documentation_boundary"]

    expected_keys = {
        "intent_summary",
        "supported_scope",
        "design_slots",
        "matched_seed_records",
        "evidence_summary",
        "provenance_gap_summary",
        "candidate_route_summary",
        "construct_status_summary",
        "manual_review_task_summary",
        "promotion_boundary",
        "next_human_actions",
        "blocked_outputs",
        "documentation_boundary",
    }
    assert expected_keys.issubset(payload)


def test_r163_output_contains_design_intent_and_required_design_slots() -> None:
    payload = _payload()
    section_titles = [section["section_title"] for section in payload["sections"]]
    slot_labels = [slot["slot_label"] for slot in payload["design_slots"]]

    assert "Design Intent" in section_titles
    assert payload["intent_summary"]["section_title"] == "Design Intent"
    assert payload["intent_summary"]["intent_status"] == "supported_local_rice_albumin_goal"
    assert payload["supported_scope"]["supported_dataset_key"] == "rice_albumin"
    assert {
        "target protein / product goal",
        "plant host or expression context",
        "candidate route",
        "expression component slots",
        "evidence/source records",
        "provenance identifiers",
        "construct task",
        "construct draft",
        "manual review status",
    }.issubset(set(slot_labels))
    assert all(slot["manual_review_required"] is True for slot in payload["design_slots"])


def test_r163_preserves_rice_albumin_seed_and_manual_queue_counts() -> None:
    payload = _payload()

    assert payload["matched_seed_records"]["represented_seed_record_count"] == 12
    assert len(payload["matched_seed_records"]["records"]) == 12
    assert payload["matched_seed_records"]["manual_review_required_count"] == 12
    assert payload["manual_review_task_summary"]["manual_provenance_queue_task_count"] == 46
    assert payload["manual_review_task_summary"]["represented_record_count"] == 12
    assert payload["manual_review_task_summary"]["records_blocked_from_promotion"] == 12
    assert payload["promotion_boundary"]["records_blocked_from_promotion"] == 12
    assert payload["promotion_boundary"]["ready_to_promote_count"] == 0
    assert payload["promotion_boundary"]["promotion_allowed_count"] == 0
    assert payload["manual_review_task_summary"]["ready_to_promote_count"] == 0
    assert payload["manual_review_task_summary"]["promotion_allowed_count"] == 0


def test_r163_construct_task_and_draft_are_explicitly_unavailable() -> None:
    payload = _payload()
    construct_status = payload["construct_status_summary"]

    assert construct_status["construct_task"]["status"] == "unavailable_manual_review_required"
    assert construct_status["construct_task"]["auto_created"] is False
    assert construct_status["construct_task"]["unavailable_reason"]
    assert construct_status["construct_draft"]["status"] == "unavailable_manual_review_required"
    assert construct_status["construct_draft"]["auto_created"] is False
    assert construct_status["construct_draft"]["unavailable_reason"]
    assert payload["side_effects"]["construct_task_created"] is False
    assert payload["side_effects"]["construct_draft_created"] is False


def test_r163_unsupported_dataset_fails_closed_and_keeps_artemisia_inactive() -> None:
    payload = r163.build_plant_goal_review_package_mvp(
        RICE_ALBUMIN_GOAL,
        dataset_key="artemisia_annua",
    )

    assert payload["fail_closed"] is True
    assert payload["package_status"] == r163.PACKAGE_STATUS_FAIL_CLOSED
    assert payload["dataset_key"] == "artemisia_annua"
    assert payload["supported_scope"]["supported"] is False
    artemisia = payload["candidate_route_summary"]["artemisia_annua_status"]
    assert artemisia["active_dataset_profile"] is False
    assert artemisia["conversion_allowed"] is False
    assert artemisia["included_in_mvp_path"] is False
    assert payload["promotion_boundary"]["promotion_allowed_count"] == 0
    assert payload["construct_status_summary"]["construct_task"]["auto_created"] is False


def test_r163_non_plant_or_out_of_scope_goal_fails_closed() -> None:
    non_plant = r163.build_plant_goal_review_package_mvp(
        "Review an E. coli protein expression design.",
        dataset_key="rice_albumin",
    )
    out_of_scope_plant = r163.build_plant_goal_review_package_mvp(
        "Review a maize terpene pathway plant design.",
        dataset_key="rice_albumin",
    )

    for payload in (non_plant, out_of_scope_plant):
        assert payload["fail_closed"] is True
        assert payload["package_status"] == r163.PACKAGE_STATUS_FAIL_CLOSED
        assert payload["matched_seed_records"]["represented_seed_record_count"] == 0
        assert payload["manual_review_task_summary"]["promotion_allowed_count"] == 0
        assert payload["manual_review_task_summary"]["ready_to_promote_count"] == 0
        assert payload["construct_status_summary"]["construct_task"]["auto_created"] is False
        assert payload["construct_status_summary"]["construct_draft"]["auto_created"] is False


def test_r163_does_not_fill_identifiers_promote_records_or_change_seed_data() -> None:
    before = {path.name: path.read_bytes() for path in SEED_FILES}
    payload = _payload()
    after = {path.name: path.read_bytes() for path in SEED_FILES}
    autofill = payload["provenance_gap_summary"]["identifier_autofill"]

    assert before == after
    assert autofill["performed"] is False
    assert autofill["source_or_accession"] is False
    assert autofill["pmid_doi_database_identifier"] is False
    assert payload["evidence_summary"]["identifier_autofill_performed"] is False
    assert payload["promotion_boundary"]["record_was_promoted"] is False
    assert payload["side_effects"]["seed_data_changed"] is False
    assert payload["side_effects"]["record_promoted"] is False


def test_r163_adds_no_ui_report_export_or_storage_behavior() -> None:
    payload = _payload()
    side_effects = payload["side_effects"]
    blocked = {row["output_key"]: row for row in payload["blocked_outputs"]}

    assert side_effects["ui_added"] is False
    assert side_effects["report_added"] is False
    assert side_effects["export_added"] is False
    assert side_effects["persistence_added"] is False
    assert blocked["ui_report_export_persistence"]["blocked"] is True
    assert blocked["external_lookup"]["blocked"] is True
    assert blocked["identifier_autofill"]["blocked"] is True
    assert blocked["record_promotion"]["blocked"] is True


def test_r163_package_output_and_changed_sources_avoid_blocked_claim_wording() -> None:
    payload = _payload()

    assert payload["copy_safety_findings"] == []
    _copy_scan_value(payload)

    source_text = "\n".join(
        [
            (ROOT / "services" / "plant_goal_review_package_mvp.py").read_text(encoding="utf-8"),
            (ROOT / "tests" / "test_r163_plant_goal_review_package_mvp.py").read_text(encoding="utf-8"),
        ]
    ).casefold()
    for phrase in BLOCKED_OUTPUT_COPY:
        assert phrase not in source_text
    assert "documentation-only" in source_text
