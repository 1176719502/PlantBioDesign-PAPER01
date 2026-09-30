# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_review_task_queue as queue
from services import rice_albumin_manual_provenance_verification as provenance
from services import rice_albumin_manual_provenance_verification_queue as r146_queue


ROOT = Path(__file__).resolve().parents[1]


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
        "schema_version": "rice_albumin_manual_verification.record_status.r151.test",
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


def _r151_rice_queue(tmp_path: Path) -> dict[str, object]:
    return queue.build_rice_albumin_manual_provenance_task_queue(
        manual_verification_dir=_write_manual_status(tmp_path)
    )


def test_r151_generic_builder_returns_plain_dict_list_payload() -> None:
    payload = queue.build_plant_review_task_queue(
        [
            {
                "task_id": "task-b",
                "record_id": "record-b",
                "record_type": "EvidenceRecord",
                "task_type": "verify_accession",
                "task_label": "Verify accession",
                "current_review_status": provenance.REVIEW_REQUIRED_STATUS,
                "current_provenance_status": "missing",
                "missing_fields": ["accession"],
                "verification_question": "Which accession should a human review?",
                "blocking_reason": "The local record has no accession.",
                "required_manual_action": "Complete manual source review in a separate update.",
                "promotion_blocked": True,
                "do_not_promote_until_verified": True,
            },
            {
                "task_id": "task-a",
                "record_id": "record-a",
                "record_type": "ComponentRecord",
                "task_type": "verify_source_id",
                "task_label": "Verify source identifier",
                "current_review_status": provenance.REVIEW_REQUIRED_STATUS,
                "current_provenance_status": "missing",
                "missing_fields": ["source_id"],
                "verification_question": "Which source identifier should a human review?",
                "blocking_reason": "The local record has no source identifier.",
                "required_manual_action": "Complete manual source review in a separate update.",
                "promotion_blocked": True,
                "do_not_promote_until_verified": True,
            },
        ],
        queue_key="test_queue",
        queue_label="Test queue",
        task_source="test_source",
        dataset_key="test_dataset",
    )

    assert payload["workflow_schema_version"] == queue.PLANT_REVIEW_TASK_QUEUE_SCHEMA_VERSION
    assert payload["workflow_status"] == queue.PLANT_REVIEW_TASK_QUEUE_STATUS_READY
    assert payload["queue_metadata"]["read_only"] is True
    assert payload["summary"]["total_tasks"] == 2
    assert payload["summary"]["represented_records"] == 2
    assert payload["summary"]["records_requiring_manual_review"] == 2
    assert payload["summary"]["records_blocked_from_promotion"] == 2
    assert payload["summary"]["ready_to_promote_count"] == 0
    assert payload["summary"]["task_type_counts"] == {
        "verify_accession": 1,
        "verify_source_id": 1,
    }
    assert payload["summary"]["missing_field_counts"] == {
        "accession": 1,
        "source_id": 1,
    }
    assert [task["record_id"] for task in payload["tasks"]] == ["record-a", "record-b"]
    assert all(set(task) == set(queue.TASK_ROW_FIELDS) for task in payload["tasks"])
    _assert_plain_data(payload)


def test_r151_empty_and_malformed_input_fails_closed() -> None:
    empty_payload = queue.build_plant_review_task_queue(
        [],
        queue_key="empty_queue",
        queue_label="Empty queue",
        task_source="empty_source",
        dataset_key="empty_dataset",
    )
    malformed_payload = queue.build_plant_review_task_queue(
        ["not-a-row"],
        queue_key="malformed_queue",
        queue_label="Malformed queue",
        task_source="malformed_source",
        dataset_key="malformed_dataset",
    )

    for payload in (empty_payload, malformed_payload):
        assert payload["workflow_status"] == queue.PLANT_REVIEW_TASK_QUEUE_STATUS_FAIL_CLOSED
        assert payload["summary"]["fail_closed"] is True
        assert payload["summary"]["total_tasks"] == 1
        assert payload["summary"]["records_blocked_from_promotion"] == 1
        assert payload["summary"]["ready_to_promote_count"] == 0
        assert payload["tasks"][0]["promotion_blocked"] is True
        assert payload["tasks"][0]["do_not_promote_until_verified"] is True


def test_r151_rice_albumin_adapter_preserves_r146_counts(tmp_path: Path) -> None:
    generic_payload = _r151_rice_queue(tmp_path)
    r146_payload = r146_queue.build_rice_albumin_manual_provenance_verification_queue(
        manual_verification_dir=_write_manual_status(tmp_path / "r146")
    )
    summary = generic_payload["summary"]

    assert summary["total_tasks"] == 46
    assert summary["represented_records"] == 12
    assert summary["records_requiring_manual_review"] == 12
    assert summary["records_blocked_from_promotion"] == 12
    assert summary["ready_to_promote_count"] == 0
    assert generic_payload["queue_metadata"]["source_summary"]["total_tasks"] == 46
    assert generic_payload["queue_metadata"]["source_summary"]["represented_record_count"] == 12
    assert r146_payload["summary"]["total_tasks"] == summary["total_tasks"]
    assert r146_payload["summary"]["records_blocked_from_promotion"] == summary[
        "records_blocked_from_promotion"
    ]


def test_r151_rice_albumin_counts_are_deterministic(tmp_path: Path) -> None:
    payload = _r151_rice_queue(tmp_path)
    summary = payload["summary"]

    assert summary["task_type_counts"] == {
        "confirm_component_linkage": 2,
        "confirm_evidence_record": 2,
        "confirm_source_scope": 12,
        "do_not_promote_guard": 12,
        "verify_accession": 12,
        "verify_source_id": 6,
    }
    assert summary["missing_field_counts"]["source_id"] == 28
    assert summary["missing_field_counts"]["accession"] == 46
    assert summary["missing_field_counts"]["component_linkage"] == 2
    assert summary["missing_field_counts"]["evidence_record"] == 2


def test_r151_rice_albumin_manual_questions_actions_and_blocks_are_preserved(tmp_path: Path) -> None:
    payload = _r151_rice_queue(tmp_path)
    tasks = payload["tasks"]
    target_task = next(
        task
        for task in tasks
        if task["record_id"] == "r131-evidence-target-identity-placeholder"
        and task["task_type"] == "verify_source_id"
    )

    assert target_task["verification_question"] == (
        "Which external source identifier should a human review for this record?"
    )
    assert "Manually inspect" in target_task["required_manual_action"]
    assert all(task["promotion_blocked"] is True for task in tasks)
    assert all(task["do_not_promote_until_verified"] is True for task in tasks)
    assert all(task["task_source"] == "r146_rice_albumin_manual_provenance_queue" for task in tasks)
    assert all(task["dataset_key"] == "rice_albumin" for task in tasks)


def test_r151_does_not_fill_identifiers_or_promote_records(tmp_path: Path) -> None:
    payload = _r151_rice_queue(tmp_path)
    tasks = payload["tasks"]
    forbidden_fill_keys = {
        "source_id",
        "source_identifier",
        "accession",
        "database_id",
        "pmid",
        "doi",
    }

    assert payload["summary"]["ready_to_promote_count"] == 0
    assert all(task["current_review_status"] == provenance.REVIEW_REQUIRED_STATUS for task in tasks)
    assert all(task["promotion_blocked"] is True for task in tasks)
    assert all(forbidden_fill_keys.isdisjoint(task) for task in tasks)
    assert not any("PMID:" in str(task) or "DOI:" in str(task) for task in tasks)
    assert "source_id" in str(tasks)
    assert "accession" in str(tasks)


def test_r151_output_and_changed_sources_avoid_forbidden_positive_or_downstream_copy(
    tmp_path: Path,
) -> None:
    payload = _r151_rice_queue(tmp_path)
    _copy_scan_value(payload)

    source_text = "\n".join(
        [
            (ROOT / "services" / "plant_review_task_queue.py").read_text(encoding="utf-8"),
            (ROOT / "tests" / "test_r151_plant_review_task_queue.py").read_text(encoding="utf-8"),
        ]
    ).casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text
    assert "documentation-only" in str(payload).casefold()
    assert "needs_manual_review" in str(payload).casefold()
