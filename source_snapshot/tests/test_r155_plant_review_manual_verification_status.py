# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_review_manual_verification_status as status
from services import plant_review_task_queue as queue
from services import plant_review_task_queue_registry as registry
from services import plant_review_task_queue_snapshot_readback as snapshot
from services import rice_albumin_manual_provenance_verification as provenance
from services import rice_albumin_manual_provenance_verification_queue as r146_queue


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
        "schema_version": "rice_albumin_manual_verification.record_status.r155.test",
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


def _rice_snapshot(tmp_path: Path) -> dict[str, object]:
    return snapshot.build_plant_review_task_queue_snapshot(
        source_kwargs_by_key={
            registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY: {
                "manual_verification_dir": _write_manual_status(tmp_path)
            }
        }
    )


def _seed_texts() -> dict[str, str]:
    return {str(path): path.read_text(encoding="utf-8") for path in SEED_FILES}


def test_r155_status_payloads_are_plain_dict_list() -> None:
    payload = status.build_plant_review_manual_verification_status(
        [
            {
                "task_id": "task-1",
                "queue_key": "synthetic_queue",
                "dataset_key": "synthetic_dataset",
                "record_id": "record-1",
                "record_type": "EvidenceRecord",
                "blocking_reason": "Manual reviewer has not entered a status yet.",
                "promotion_blocked": True,
                "do_not_promote_until_verified": True,
            }
        ],
        status_records=[
            {
                "task_id": "task-1",
                "verification_status": status.STATUS_MANUAL_REVIEW_IN_PROGRESS,
                "reviewer_note": "Reviewer is checking local documentation context.",
            }
        ],
    )
    rows = status.build_plant_review_manual_verification_status_readback_rows(payload)

    assert payload["workflow_schema_version"] == status.MANUAL_VERIFICATION_STATUS_SCHEMA_VERSION
    assert payload["workflow_status"] == status.MANUAL_VERIFICATION_STATUS_READY
    assert payload["plain_dict_list_contract"] is True
    assert payload["summary"]["total_status_records"] == 1
    assert payload["summary"]["manual_review_in_progress_count"] == 1
    assert payload["summary"]["promotion_allowed_count"] == 0
    assert set(payload["status_records"][0]) == set(status.STATUS_RECORD_FIELDS)
    assert rows[0]["verification_status"] == status.STATUS_MANUAL_REVIEW_IN_PROGRESS
    _assert_plain_data(payload)
    _assert_plain_data(rows)


def test_r155_missing_or_malformed_task_input_fails_closed() -> None:
    for source in (None, [], ["not-a-row"], {"tasks": "not-a-list"}):
        payload = status.build_plant_review_manual_verification_status(source)
        row = payload["status_records"][0]

        assert payload["workflow_status"] == status.MANUAL_VERIFICATION_STATUS_FAIL_CLOSED
        assert payload["summary"]["fail_closed"] is True
        assert payload["summary"]["blocked_count"] == 1
        assert payload["summary"]["promotion_allowed_count"] == 0
        assert row["verification_status"] == status.STATUS_BLOCKED_SCOPE_UNCLEAR
        assert row["promotion_allowed"] is False
        assert row["do_not_promote_until_verified"] is True


def test_r155_default_rice_albumin_queue_status_remains_pending_or_blocked(tmp_path: Path) -> None:
    queue_payload = _rice_queue(tmp_path)
    payload = status.build_plant_review_manual_verification_status(queue_payload)
    summary = payload["summary"]
    allowed_defaults = {
        status.STATUS_PENDING_MANUAL_REVIEW,
        status.STATUS_BLOCKED_MISSING_IDENTIFIER,
        status.STATUS_BLOCKED_SCOPE_UNCLEAR,
    }

    assert summary["total_status_records"] == queue_payload["summary"]["total_tasks"] == 46
    assert summary["pending_count"] == 46
    assert summary["promotion_allowed_count"] == 0
    assert set(summary["status_counts"]) <= allowed_defaults
    assert all(row["promotion_allowed"] is False for row in payload["status_records"])
    assert all(row["do_not_promote_until_verified"] is True for row in payload["status_records"])


def test_r155_snapshot_readback_stays_closed_for_rice_albumin(tmp_path: Path) -> None:
    snapshot_payload = _rice_snapshot(tmp_path)
    payload = status.build_plant_review_manual_verification_status(snapshot_payload)
    row = payload["status_records"][0]

    assert snapshot_payload["summary"]["total_tasks"] == 46
    assert snapshot_payload["summary"]["ready_to_promote_count"] == 0
    assert payload["summary"]["total_status_records"] == 1
    assert payload["summary"]["promotion_allowed_count"] == 0
    assert row["queue_key"] == registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY
    assert row["verification_status"] == status.STATUS_PENDING_MANUAL_REVIEW
    assert row["promotion_allowed"] is False


def test_r155_verified_reference_recorded_does_not_allow_promotion_or_mutate_tasks(tmp_path: Path) -> None:
    queue_payload = _rice_queue(tmp_path)
    original_tasks = json.loads(json.dumps(queue_payload["tasks"]))
    target_task = queue_payload["tasks"][0]
    payload = status.build_plant_review_manual_verification_status(
        queue_payload,
        status_records=[
            {
                "task_id": target_task["task_id"],
                "verification_status": status.STATUS_VERIFIED_REFERENCE_RECORDED,
                "reviewed_reference_kind": "reviewer-entered literature identifier",
                "reviewed_reference_value": "reviewer-entered-placeholder-001",
                "reviewer_note": "Synthetic reviewer-entered status data for test readback.",
                "requires_second_review": True,
            }
        ],
    )
    row = next(item for item in payload["status_records"] if item["task_id"] == target_task["task_id"])

    assert row["verification_status"] == status.STATUS_VERIFIED_REFERENCE_RECORDED
    assert row["identifier_recorded"] is True
    assert row["promotion_allowed"] is False
    assert row["do_not_promote_until_verified"] is True
    assert row["requires_second_review"] is True
    assert payload["summary"]["verified_reference_recorded_count"] == 1
    assert payload["summary"]["promotion_allowed_count"] == 0
    assert queue_payload["tasks"] == original_tasks


def test_r155_reviewed_references_are_status_data_only_not_task_fill_values(tmp_path: Path) -> None:
    queue_payload = _rice_queue(tmp_path)
    before_seed_texts = _seed_texts()
    target_task = queue_payload["tasks"][0]
    payload = status.build_plant_review_manual_verification_status(
        queue_payload,
        status_records=[
            {
                "task_id": target_task["task_id"],
                "verification_status": status.STATUS_REVIEWED_BUT_NOT_PROMOTABLE,
                "reviewed_reference_kind": "reviewer-entered database note",
                "reviewed_reference_value": "synthetic-review-note-not-a-seed-value",
                "promotion_blocked_reason": "Human status note is present, but record promotion remains blocked.",
            }
        ],
    )
    row = next(item for item in payload["status_records"] if item["task_id"] == target_task["task_id"])
    forbidden_fill_keys = {
        "source_id",
        "source_identifier",
        "accession",
        "database_id",
        "pmid",
        "doi",
    }

    assert row["reviewed_reference_value"] == "synthetic-review-note-not-a-seed-value"
    assert row["identifier_recorded"] is False
    assert row["promotion_allowed"] is False
    assert all(forbidden_fill_keys.isdisjoint(task) for task in queue_payload["tasks"])
    assert _seed_texts() == before_seed_texts


def test_r155_blocked_statuses_preserve_reasons_and_do_not_promote_state() -> None:
    payload = status.build_plant_review_manual_verification_status(
        [
            {
                "task_id": "blocked-task",
                "queue_key": "synthetic_queue",
                "dataset_key": "synthetic_dataset",
                "record_id": "blocked-record",
                "record_type": "ComponentRecord",
                "missing_fields": ["source_id"],
                "blocking_reason": "Identifier context is missing from the local task row.",
                "promotion_blocked": True,
                "do_not_promote_until_verified": True,
            }
        ],
        status_records=[
            {
                "task_id": "blocked-task",
                "verification_status": status.STATUS_BLOCKED_MISSING_IDENTIFIER,
                "promotion_blocked_reason": "Reviewer confirmed identifier context is still missing.",
            }
        ],
    )
    row = payload["status_records"][0]

    assert payload["summary"]["blocked_count"] == 1
    assert row["verification_status"] == status.STATUS_BLOCKED_MISSING_IDENTIFIER
    assert row["promotion_blocked_reason"] == "Reviewer confirmed identifier context is still missing."
    assert row["promotion_allowed"] is False
    assert row["do_not_promote_until_verified"] is True


def test_r155_preserves_r146_r151_r153_counts_and_no_records_are_promoted(tmp_path: Path) -> None:
    manual_dir = _write_manual_status(tmp_path)
    r146_payload = r146_queue.build_rice_albumin_manual_provenance_verification_queue(
        manual_verification_dir=manual_dir
    )
    r151_payload = queue.build_rice_albumin_manual_provenance_task_queue(
        manual_verification_dir=manual_dir
    )
    r153_payload = snapshot.build_plant_review_task_queue_snapshot(
        source_kwargs_by_key={
            registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY: {
                "manual_verification_dir": manual_dir
            }
        }
    )
    status_payload = status.build_plant_review_manual_verification_status(r151_payload)

    assert r146_payload["summary"]["total_tasks"] == 46
    assert r146_payload["summary"]["records_blocked_from_promotion"] == 12
    assert r146_payload["summary"]["ready_to_promote_count"] == 0
    assert r151_payload["summary"]["total_tasks"] == 46
    assert r151_payload["summary"]["records_blocked_from_promotion"] == 12
    assert r151_payload["summary"]["ready_to_promote_count"] == 0
    assert r153_payload["summary"]["total_tasks"] == 46
    assert r153_payload["summary"]["records_blocked_from_promotion"] == 12
    assert r153_payload["summary"]["ready_to_promote_count"] == 0
    assert status_payload["summary"]["total_status_records"] == 46
    assert status_payload["summary"]["promotion_allowed_count"] == 0
    assert all(row["promotion_allowed"] is False for row in status_payload["status_records"])


def test_r155_output_and_changed_sources_avoid_forbidden_positive_or_downstream_copy(
    tmp_path: Path,
) -> None:
    queue_payload = _rice_queue(tmp_path)
    status_payload = status.build_plant_review_manual_verification_status(queue_payload)
    rows = status.build_plant_review_manual_verification_status_readback_rows(status_payload)
    _copy_scan_value(status_payload)
    _copy_scan_value(rows)

    source_text = "\n".join(
        [
            (ROOT / "services" / "plant_review_manual_verification_status.py").read_text(
                encoding="utf-8"
            ),
            (ROOT / "tests" / "test_r155_plant_review_manual_verification_status.py").read_text(
                encoding="utf-8"
            ),
        ]
    ).casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text
    assert "documentation-only" in str(status_payload).casefold()
    assert status.STATUS_VERIFIED_REFERENCE_RECORDED in status_payload["supported_verification_statuses"]
