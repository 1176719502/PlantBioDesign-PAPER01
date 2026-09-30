# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_review_manual_verification_status as status
from services import plant_review_manual_verification_transition_guard as guard
from services import plant_review_task_queue as queue
from services import rice_albumin_manual_provenance_verification as provenance


ROOT = Path(__file__).resolve().parents[1]
SEED_FILES = tuple(sorted((ROOT / "data" / "plant_seed" / "rice_albumin").glob("*.json")))


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_OUTPUT_COPY = (
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
    _term("source-backed ", "recom", "mendation"),
)

FORBIDDEN_FILL_KEYS = {
    "source_id",
    "source_identifier",
    "accession",
    "database_id",
    "pmid",
    "doi",
}


def _assert_plain_data(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            _assert_plain_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_data(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def _copy_scan_value(value: object) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _copy_scan_value(nested)
        return
    if isinstance(value, list):
        for nested in value:
            _copy_scan_value(nested)
        return
    if not isinstance(value, str):
        return

    text = value.casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in text


def _manual_status_payload() -> dict[str, object]:
    record_ids = [
        "r131-rice-albumin-project-intent",
        "r131-rice-seed-design-context",
        "r131-route-plant-protein-expression-evidence-first",
        "r131-slot-target-product",
        "r131-slot-gene-or-cds-source",
        "r131-slot-plant-context",
        "r131-slot-tissue-context",
        "r131-slot-evidence-context",
        "r131-component-albumin-like-cds-source-placeholder",
        "r131-component-vector-backbone-context-placeholder",
        "r131-evidence-target-identity-placeholder",
        "r131-evidence-rice-seed-context-placeholder",
    ]
    missing_source_ids = {
        "r131-rice-albumin-project-intent",
        "r131-rice-seed-design-context",
        "r131-component-albumin-like-cds-source-placeholder",
        "r131-component-vector-backbone-context-placeholder",
        "r131-evidence-target-identity-placeholder",
        "r131-evidence-rice-seed-context-placeholder",
    }
    candidate_categories = {
        "r131-rice-albumin-project-intent": ["curated literature metadata for target identity"],
        "r131-rice-seed-design-context": ["curated rice seed context metadata"],
        "r131-component-albumin-like-cds-source-placeholder": ["curated protein database metadata"],
        "r131-component-vector-backbone-context-placeholder": ["none for current R131 scaffold unless scoped"],
        "r131-evidence-target-identity-placeholder": ["reviewed literature metadata"],
        "r131-evidence-rice-seed-context-placeholder": ["reviewed rice seed context literature metadata"],
    }
    return {
        "schema_version": "rice_albumin_manual_verification.record_status.r157.test",
        "record_count": len(record_ids),
        "records": [
            {
                "record_id": record_id,
                "missing_source_id": record_id in missing_source_ids,
                "missing_accession": True,
                "candidate_external_source_category": candidate_categories.get(record_id, []),
                "requires_human_lookup": record_id in missing_source_ids,
                "status": [
                    "candidate",
                    provenance.REVIEW_REQUIRED_STATUS,
                    provenance.DO_NOT_PROMOTE_STATUS,
                ],
                "must_not_be_promoted": True,
                "verified_by_local_repo_only": record_id not in missing_source_ids,
            }
            for record_id in record_ids
        ],
    }


def _write_manual_status(tmp_path: Path) -> Path:
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir(parents=True)
    (manual_dir / provenance.MANUAL_STATUS_FILE).write_text(
        json.dumps(_manual_status_payload()),
        encoding="utf-8",
    )
    return manual_dir


def _rice_queue(tmp_path: Path) -> dict[str, object]:
    return queue.build_rice_albumin_manual_provenance_task_queue(
        manual_verification_dir=_write_manual_status(tmp_path)
    )


def _seed_texts() -> dict[str, str]:
    return {str(path): path.read_text(encoding="utf-8") for path in SEED_FILES}


def test_r157_known_status_transition_returns_deterministic_readback() -> None:
    payload = guard.build_plant_review_manual_verification_transition_guard(
        {
            "task_id": "task-1",
            "verification_status": status.STATUS_PENDING_MANUAL_REVIEW,
        },
        {
            "task_id": "task-1",
            "verification_status": status.STATUS_MANUAL_REVIEW_IN_PROGRESS,
        },
    )
    rows = guard.build_plant_review_manual_verification_transition_readback_rows([payload])

    assert payload["transition_schema_version"] == guard.MANUAL_VERIFICATION_TRANSITION_GUARD_SCHEMA_VERSION
    assert payload["transition_status"] == guard.TRANSITION_STATUS_ALLOWED
    assert payload["transition_allowed"] is True
    assert payload["from_status"] == status.STATUS_PENDING_MANUAL_REVIEW
    assert payload["to_status"] == status.STATUS_MANUAL_REVIEW_IN_PROGRESS
    assert payload["promotion_allowed"] is False
    assert payload["manual_review_required"] is True
    assert rows[0]["transition_allowed"] is True
    _assert_plain_data(payload)
    _assert_plain_data(rows)


def test_r157_unknown_status_fails_closed() -> None:
    payload = guard.build_plant_review_manual_verification_transition_guard(
        {"task_id": "task-unknown", "verification_status": "unlisted_status"},
        {"task_id": "task-unknown", "verification_status": status.STATUS_MANUAL_REVIEW_IN_PROGRESS},
    )

    assert payload["transition_allowed"] is False
    assert payload["transition_status"] == guard.TRANSITION_STATUS_FAIL_CLOSED
    assert payload["fail_closed"] is True
    assert payload["from_status"] == "unknown_status"
    assert payload["promotion_allowed"] is False
    assert payload["blocking_reasons"]


def test_r157_missing_or_malformed_input_fails_closed() -> None:
    malformed_inputs = (
        (None, status.STATUS_MANUAL_REVIEW_IN_PROGRESS),
        (status.STATUS_PENDING_MANUAL_REVIEW, None),
        ({"task_id": "task-a"}, {"task_id": "task-a", "verification_status": status.STATUS_REVIEWED_BUT_NOT_PROMOTABLE}),
        ({"verification_status": status.STATUS_PENDING_MANUAL_REVIEW}, {"verification_status": status.STATUS_REVIEWED_BUT_NOT_PROMOTABLE}),
    )
    for current_status, next_status in malformed_inputs:
        payload = guard.build_plant_review_manual_verification_transition_guard(
            current_status,
            next_status,
        )

        assert payload["transition_allowed"] is False
        assert payload["fail_closed"] is True
        assert payload["promotion_allowed"] is False
        assert payload["manual_review_required"] is True


def test_r157_verified_reference_recorded_does_not_allow_promotion(tmp_path: Path) -> None:
    rice_payload = _rice_queue(tmp_path)
    target_task = rice_payload["tasks"][0]
    payload = guard.build_plant_review_manual_verification_transition_guard(
        {
            "task_id": target_task["task_id"],
            "verification_status": status.STATUS_MANUAL_REVIEW_IN_PROGRESS,
        },
        {
            "task_id": target_task["task_id"],
            "verification_status": status.STATUS_VERIFIED_REFERENCE_RECORDED,
            "reviewed_reference_kind": "reviewer-entered literature note",
            "reviewed_reference_value": "reviewer-entered-status-only-note",
        },
    )

    assert payload["transition_allowed"] is True
    assert payload["to_status"] == status.STATUS_VERIFIED_REFERENCE_RECORDED
    assert payload["promotion_allowed"] is False
    assert payload["manual_review_required"] is True
    assert "reviewed_reference_value" not in payload


def test_r157_rejected_to_reference_recorded_requires_second_review_and_fails_closed() -> None:
    payload = guard.build_plant_review_manual_verification_transition_guard(
        {
            "task_id": "task-rejected",
            "verification_status": status.STATUS_REJECTED_BEFORE_PROMOTION,
        },
        {
            "task_id": "task-rejected",
            "verification_status": status.STATUS_VERIFIED_REFERENCE_RECORDED,
        },
    )

    assert payload["transition_allowed"] is False
    assert payload["requires_second_review"] is True
    assert payload["fail_closed"] is True
    assert payload["promotion_allowed"] is False
    assert any("second review" in reason for reason in payload["blocking_reasons"])


def test_r157_blocked_statuses_preserve_blocking_reasons() -> None:
    payload = guard.build_plant_review_manual_verification_transition_guard(
        {
            "task_id": "task-blocked",
            "verification_status": status.STATUS_MANUAL_REVIEW_IN_PROGRESS,
            "blocking_reason": "Identifier context still needs manual review.",
        },
        {
            "task_id": "task-blocked",
            "verification_status": status.STATUS_BLOCKED_MISSING_IDENTIFIER,
            "promotion_blocked_reason": "Reviewer confirmed identifier context is still missing.",
        },
    )

    assert payload["transition_allowed"] is True
    assert payload["transition_status"] == guard.TRANSITION_STATUS_BLOCKED
    assert payload["promotion_allowed"] is False
    assert "Identifier context still needs manual review." in payload["blocking_reasons"]
    assert "Reviewer confirmed identifier context is still missing." in payload["blocking_reasons"]


def test_r157_promotion_allowed_remains_false_for_current_rice_albumin_path(tmp_path: Path) -> None:
    rice_payload = _rice_queue(tmp_path)
    transitions = [
        guard.build_plant_review_manual_verification_transition_guard(
            {
                "task_id": task["task_id"],
                "verification_status": status.STATUS_PENDING_MANUAL_REVIEW,
            },
            {
                "task_id": task["task_id"],
                "verification_status": status.STATUS_REVIEWED_BUT_NOT_PROMOTABLE,
            },
        )
        for task in rice_payload["tasks"]
    ]

    assert rice_payload["summary"]["total_tasks"] == 46
    assert rice_payload["summary"]["represented_records"] == 12
    assert rice_payload["summary"]["ready_to_promote_count"] == 0
    assert all(row["promotion_allowed"] is False for row in transitions)
    assert all(row["transition_allowed"] is True for row in transitions)


def test_r157_does_not_fill_identifiers_promote_records_or_change_seed_data(tmp_path: Path) -> None:
    before_seed_texts = _seed_texts()
    rice_payload = _rice_queue(tmp_path)
    before_tasks = json.loads(json.dumps(rice_payload["tasks"]))
    target_task = rice_payload["tasks"][0]
    payload = guard.build_plant_review_manual_verification_transition_guard(
        {
            "task_id": target_task["task_id"],
            "verification_status": status.STATUS_PENDING_MANUAL_REVIEW,
        },
        {
            "task_id": target_task["task_id"],
            "verification_status": status.STATUS_VERIFIED_REFERENCE_RECORDED,
            "reviewed_reference_kind": "reviewer-entered database note",
            "reviewed_reference_value": "reviewer-entered-status-only-note",
        },
    )

    assert payload["promotion_allowed"] is False
    assert all(key not in payload for key in FORBIDDEN_FILL_KEYS)
    assert "PMID:" not in str(payload)
    assert "DOI:" not in str(payload)
    assert rice_payload["tasks"] == before_tasks
    assert _seed_texts() == before_seed_texts


def test_r157_output_and_changed_sources_avoid_forbidden_positive_or_downstream_copy(
    tmp_path: Path,
) -> None:
    rice_payload = _rice_queue(tmp_path)
    payload = guard.build_plant_review_manual_verification_transition_guard(
        {
            "task_id": rice_payload["tasks"][0]["task_id"],
            "verification_status": status.STATUS_PENDING_MANUAL_REVIEW,
        },
        {
            "task_id": rice_payload["tasks"][0]["task_id"],
            "verification_status": status.STATUS_REVIEWED_BUT_NOT_PROMOTABLE,
        },
    )
    rows = guard.build_plant_review_manual_verification_transition_readback_rows([payload])
    _copy_scan_value(payload)
    _copy_scan_value(rows)

    source_text = "\n".join(
        [
            (ROOT / "services" / "plant_review_manual_verification_transition_guard.py").read_text(
                encoding="utf-8"
            ),
            (
                ROOT
                / "tests"
                / "test_r157_plant_review_manual_verification_transition_guard.py"
            ).read_text(encoding="utf-8"),
        ]
    ).casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text
    assert "documentation-only" in str(payload).casefold()
