# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_review_manual_verification_consistency_audit as audit
from services import plant_review_manual_verification_status as status
from services import plant_review_task_queue as queue
from services import plant_review_task_queue_registry as registry
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
    _term("pro", "duction", "-ready"),
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
        "schema_version": "rice_albumin_manual_verification.record_status.r159.test",
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


def test_r159_rice_albumin_consistency_audit_remains_read_only_and_blocked(tmp_path: Path) -> None:
    payload = audit.build_plant_review_manual_verification_consistency_audit(
        _rice_queue(tmp_path),
        queue_key=registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY,
        dataset_key="rice_albumin",
    )
    rows = audit.build_plant_review_manual_verification_consistency_audit_rows(payload)

    assert payload["audit_schema_version"] == audit.MANUAL_VERIFICATION_CONSISTENCY_AUDIT_SCHEMA_VERSION
    assert payload["audit_status"] == audit.AUDIT_STATUS_READY
    assert payload["queue_key"] == registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY
    assert payload["dataset_key"] == "rice_albumin"
    assert payload["total_tasks"] == 46
    assert payload["status_record_count"] == 46
    assert payload["tasks_without_status_count"] == 0
    assert payload["unknown_task_status_count"] == 0
    assert payload["dataset_mismatch_count"] == 0
    assert payload["promotion_conflict_count"] == 0
    assert payload["ready_to_promote_count"] == 0
    assert payload["promotion_allowed_count"] == 0
    assert payload["promotion_allowed"] is False
    assert payload["blocking_findings"] == []
    assert rows[0]["promotion_allowed"] is False
    _assert_plain_data(payload)
    _assert_plain_data(rows)


def test_r159_missing_status_payload_defaults_to_pending_manual_review(tmp_path: Path) -> None:
    payload = audit.build_plant_review_manual_verification_consistency_audit(_rice_queue(tmp_path))

    assert payload["status_record_count"] == 46
    assert payload["tasks_without_status_count"] == 0
    assert payload["manual_review_required"] is True
    assert payload["fail_closed"] is False
    assert payload["promotion_allowed"] is False


def test_r159_partial_status_payload_counts_tasks_without_status(tmp_path: Path) -> None:
    queue_payload = queue.build_plant_review_task_queue(
        [
            {"task_id": "task-a", "record_id": "record-a", "dataset_key": "rice_albumin"},
            {"task_id": "task-b", "record_id": "record-b", "dataset_key": "rice_albumin"},
        ],
        queue_key="synthetic_queue",
        queue_label="Synthetic queue",
        task_source="synthetic_source",
        dataset_key="rice_albumin",
    )
    status_payload = {
        "summary": {"total_status_records": 1, "promotion_allowed_count": 0},
        "status_records": [
            {
                "status_record_id": "status-a",
                "task_id": "task-a",
                "dataset_key": "rice_albumin",
                "verification_status": status.STATUS_PENDING_MANUAL_REVIEW,
                "promotion_allowed": False,
            }
        ],
    }

    payload = audit.build_plant_review_manual_verification_consistency_audit(
        queue_payload,
        status_payload=status_payload,
        dataset_key="rice_albumin",
    )

    assert payload["tasks_without_status_count"] == 1
    assert payload["unknown_task_status_count"] == 0
    assert payload["fail_closed"] is False
    assert any(row["finding_type"] == "task_without_status" for row in payload["warning_findings"])


def test_r159_unknown_task_status_record_is_counted(tmp_path: Path) -> None:
    queue_payload = _rice_queue(tmp_path)
    status_payload = {
        "summary": {"total_status_records": 1, "promotion_allowed_count": 0},
        "status_records": [
            {
                "status_record_id": "unknown-status",
                "task_id": "unknown-task-id",
                "dataset_key": "rice_albumin",
                "verification_status": status.STATUS_PENDING_MANUAL_REVIEW,
                "promotion_allowed": False,
            }
        ],
    }

    payload = audit.build_plant_review_manual_verification_consistency_audit(
        queue_payload,
        status_payload=status_payload,
        dataset_key="rice_albumin",
    )

    assert payload["unknown_task_status_count"] == 1
    assert payload["fail_closed"] is True
    assert payload["blocking_findings"][0]["finding_type"] == "unknown_task_status_record"


def test_r159_dataset_mismatch_is_counted_and_fails_closed(tmp_path: Path) -> None:
    queue_payload = _rice_queue(tmp_path)
    first_task = queue_payload["tasks"][0]
    status_payload = {
        "summary": {"total_status_records": 1, "promotion_allowed_count": 0},
        "status_records": [
            {
                "status_record_id": "mismatch-status",
                "task_id": first_task["task_id"],
                "dataset_key": "different_dataset",
                "verification_status": status.STATUS_PENDING_MANUAL_REVIEW,
                "promotion_allowed": False,
            }
        ],
    }

    payload = audit.build_plant_review_manual_verification_consistency_audit(
        queue_payload,
        status_payload=status_payload,
        dataset_key="rice_albumin",
    )

    assert payload["dataset_mismatch_count"] == 1
    assert payload["fail_closed"] is True
    assert any(row["finding_type"] == "status_dataset_mismatch" for row in payload["blocking_findings"])


def test_r159_status_promotion_conflict_is_counted(tmp_path: Path) -> None:
    queue_payload = _rice_queue(tmp_path)
    first_task = queue_payload["tasks"][0]
    status_payload = {
        "summary": {"total_status_records": 1, "promotion_allowed_count": 1},
        "status_records": [
            {
                "status_record_id": "conflict-status",
                "task_id": first_task["task_id"],
                "dataset_key": "rice_albumin",
                "verification_status": status.STATUS_REVIEWED_BUT_NOT_PROMOTABLE,
                "promotion_allowed": True,
            }
        ],
    }
    gate_payload = {
        "promotion_allowed": False,
        "promotion_allowed_count": 0,
        "fail_closed": False,
    }

    payload = audit.build_plant_review_manual_verification_consistency_audit(
        queue_payload,
        status_payload=status_payload,
        promotion_gate_payload=gate_payload,
        dataset_key="rice_albumin",
    )

    assert payload["promotion_conflict_count"] == 2
    assert payload["fail_closed"] is True
    assert payload["promotion_allowed"] is False


def test_r159_verified_reference_recorded_without_promotion_is_allowed(tmp_path: Path) -> None:
    queue_payload = _rice_queue(tmp_path)
    first_task = queue_payload["tasks"][0]
    status_payload = status.build_plant_review_manual_verification_status(
        queue_payload,
        status_records=[
            {
                "task_id": first_task["task_id"],
                "verification_status": status.STATUS_VERIFIED_REFERENCE_RECORDED,
                "reviewed_reference_kind": "reviewer-entered literature note",
                "reviewed_reference_value": "reviewer-entered-status-only-note",
            }
        ],
    )

    payload = audit.build_plant_review_manual_verification_consistency_audit(
        queue_payload,
        status_payload=status_payload,
        dataset_key="rice_albumin",
    )

    assert payload["verified_reference_without_promotion_count"] == 1
    assert payload["promotion_conflict_count"] == 0
    assert payload["promotion_allowed"] is False
    assert payload["fail_closed"] is False


def test_r159_does_not_fill_identifiers_promote_records_or_change_seed_data(tmp_path: Path) -> None:
    before_seed_texts = _seed_texts()
    payload = audit.build_plant_review_manual_verification_consistency_audit(_rice_queue(tmp_path))

    assert payload["promotion_allowed"] is False
    assert payload["promotion_allowed_count"] == 0
    assert payload["ready_to_promote_count"] == 0
    assert all(key not in payload for key in FORBIDDEN_FILL_KEYS)
    assert "PMID:" not in str(payload)
    assert "DOI:" not in str(payload)
    assert _seed_texts() == before_seed_texts


def test_r159_output_and_changed_sources_avoid_forbidden_positive_or_downstream_copy(
    tmp_path: Path,
) -> None:
    payload = audit.build_plant_review_manual_verification_consistency_audit(_rice_queue(tmp_path))
    rows = audit.build_plant_review_manual_verification_consistency_audit_rows(payload)
    _copy_scan_value(payload)
    _copy_scan_value(rows)

    source_text = "\n".join(
        [
            (
                ROOT
                / "services"
                / "plant_review_manual_verification_consistency_audit.py"
            ).read_text(encoding="utf-8"),
            (
                ROOT
                / "tests"
                / "test_r159_plant_review_manual_verification_consistency_audit.py"
            ).read_text(encoding="utf-8"),
        ]
    ).casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text
    assert "documentation-only" in str(payload).casefold()
