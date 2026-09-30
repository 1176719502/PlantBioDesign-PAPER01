# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import rice_albumin_manual_provenance_verification as provenance
from services import rice_albumin_manual_provenance_verification_queue as queue


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


TASK_KEYS = {
    "task_id",
    "record_id",
    "record_type",
    "task_type",
    "task_label",
    "current_review_status",
    "current_provenance_status",
    "missing_fields",
    "verification_question",
    "blocking_reason",
    "required_manual_action",
    "promotion_blocked",
    "do_not_promote_until_verified",
    "documentation_boundary",
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
        "schema_version": "rice_albumin_manual_verification.record_status.r146.test",
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


def _write_manual_status(tmp_path: Path, payload: dict[str, object] | None = None) -> Path:
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    source = payload if payload is not None else _manual_status_payload()
    (manual_dir / provenance.MANUAL_STATUS_FILE).write_text(json.dumps(source), encoding="utf-8")
    return manual_dir


def _queue_payload(tmp_path: Path) -> dict[str, object]:
    return queue.build_rice_albumin_manual_provenance_verification_queue(
        manual_verification_dir=_write_manual_status(tmp_path)
    )


def test_r146_queue_represents_all_r131_seed_records_with_task_rows(tmp_path: Path) -> None:
    payload = _queue_payload(tmp_path)
    tasks = payload["tasks"]
    summary = payload["summary"]

    assert payload["workflow_schema_version"] == queue.MANUAL_PROVENANCE_QUEUE_SCHEMA_VERSION
    assert payload["workflow_status"] == queue.MANUAL_PROVENANCE_QUEUE_STATUS_READY
    assert payload["read_only"] is True
    assert payload["manual_review_required"] is True
    assert summary["represented_record_count"] == 12
    assert summary["total_tasks"] == 46
    assert summary["records_requiring_manual_lookup"] == 12
    assert summary["records_blocked_from_promotion"] == 12
    assert {task["record_id"] for task in tasks} == set(summary["record_ids_blocked_from_promotion"])
    assert all(set(task) == TASK_KEYS for task in tasks)
    assert tasks == sorted(tasks, key=lambda item: (item["record_id"], item["task_type"]))
    _assert_plain_data(payload)


def test_r146_missing_source_ids_and_accessions_generate_manual_tasks(tmp_path: Path) -> None:
    payload = _queue_payload(tmp_path)
    summary = payload["summary"]
    tasks = payload["tasks"]
    target_tasks = [
        task
        for task in tasks
        if task["record_id"] == "r131-evidence-target-identity-placeholder"
    ]
    route_tasks = [
        task
        for task in tasks
        if task["record_id"] == "r131-route-plant-protein-expression-evidence-first"
    ]

    assert summary["missing_source_id_count"] == 6
    assert summary["missing_accession_count"] == 12
    assert summary["ready_to_promote_count"] == 0
    assert summary["task_type_counts"]["verify_source_id"] == 6
    assert summary["task_type_counts"]["verify_accession"] == 12
    assert any(task["task_type"] == "verify_source_id" for task in target_tasks)
    assert any(task["task_type"] == "verify_accession" for task in target_tasks)
    assert not any(task["task_type"] == "verify_source_id" for task in route_tasks)
    assert any(task["task_type"] == "verify_accession" for task in route_tasks)
    assert all(task["promotion_blocked"] is True for task in tasks)
    assert all(task["do_not_promote_until_verified"] is True for task in tasks)


def test_r146_queue_preserves_source_scope_component_evidence_and_guard_tasks(tmp_path: Path) -> None:
    payload = _queue_payload(tmp_path)
    counts = payload["summary"]["task_type_counts"]
    tasks = payload["tasks"]

    assert counts == {
        "verify_source_id": 6,
        "verify_accession": 12,
        "confirm_source_scope": 12,
        "confirm_component_linkage": 2,
        "confirm_evidence_record": 2,
        "do_not_promote_guard": 12,
    }
    assert any(
        task["record_id"] == "r131-component-albumin-like-cds-source-placeholder"
        and task["task_type"] == "confirm_component_linkage"
        and "component_linkage" in task["missing_fields"]
        for task in tasks
    )
    assert any(
        task["record_id"] == "r131-evidence-rice-seed-context-placeholder"
        and task["task_type"] == "confirm_evidence_record"
        and "evidence_record" in task["missing_fields"]
        for task in tasks
    )
    assert all(
        any(
            task["record_id"] == record_id and task["task_type"] == "do_not_promote_guard"
            for task in tasks
        )
        for record_id in payload["summary"]["record_ids_blocked_from_promotion"]
    )


def test_r146_queue_does_not_fill_identifiers_or_promote_records(tmp_path: Path) -> None:
    payload = _queue_payload(tmp_path)
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


def test_r146_readback_rows_are_compact_plain_rows(tmp_path: Path) -> None:
    payload = _queue_payload(tmp_path)
    rows = queue.build_rice_albumin_manual_provenance_queue_readback_rows(payload)

    assert isinstance(rows, list)
    assert len(rows) == payload["summary"]["total_tasks"]
    assert set(rows[0]) == {
        "task_id",
        "record_id",
        "record_type",
        "task_type",
        "task_label",
        "current_review_status",
        "current_provenance_status",
        "missing_fields",
        "promotion_blocked",
        "do_not_promote_until_verified",
        "documentation_boundary",
    }
    assert all(row["promotion_blocked"] is True for row in rows)
    assert all(row["do_not_promote_until_verified"] is True for row in rows)
    _assert_plain_data(rows)


def test_r146_missing_external_status_materials_fail_closed_with_blocked_tasks(tmp_path: Path) -> None:
    payload = queue.build_rice_albumin_manual_provenance_verification_queue(
        manual_verification_dir=tmp_path / "missing"
    )

    assert payload["workflow_status"] == queue.MANUAL_PROVENANCE_QUEUE_STATUS_FAIL_CLOSED
    assert payload["source_workflow_status"] == provenance.MANUAL_PROVENANCE_STATUS_FAIL_CLOSED
    assert payload["summary"]["represented_record_count"] == 12
    assert payload["summary"]["records_blocked_from_promotion"] == 12
    assert payload["summary"]["ready_to_promote_count"] == 0
    assert payload["summary"]["task_type_counts"]["do_not_promote_guard"] == 12
    assert all(task["promotion_blocked"] is True for task in payload["tasks"])


def test_r146_malformed_or_missing_provenance_payload_fails_closed() -> None:
    payload = queue.build_rice_albumin_manual_provenance_verification_queue(
        {
            "workflow_status": provenance.MANUAL_PROVENANCE_STATUS_READY,
            "records": "malformed",
            "warnings": ["malformed fixture"],
        }
    )
    task = payload["tasks"][0]

    assert payload["workflow_status"] == queue.MANUAL_PROVENANCE_QUEUE_STATUS_FAIL_CLOSED
    assert payload["summary"]["total_tasks"] == 1
    assert payload["summary"]["records_blocked_from_promotion"] == 1
    assert payload["summary"]["ready_to_promote_count"] == 0
    assert task["task_type"] == "do_not_promote_guard"
    assert task["record_id"] == "unknown_rice_albumin_seed_records"
    assert task["promotion_blocked"] is True
    assert "queue fails closed" in task["blocking_reason"]
    assert any("queue fails closed" in warning for warning in payload["warnings"])


def test_r146_output_and_changed_sources_avoid_forbidden_positive_or_downstream_copy(
    tmp_path: Path,
) -> None:
    payload = _queue_payload(tmp_path)
    rows = queue.build_rice_albumin_manual_provenance_queue_readback_rows(payload)
    _copy_scan_value(payload)
    _copy_scan_value(rows)

    source_text = "\n".join(
        [
            (ROOT / "services" / "rice_albumin_manual_provenance_verification_queue.py").read_text(
                encoding="utf-8"
            ),
            (
                ROOT
                / "tests"
                / "test_r146_rice_albumin_manual_provenance_verification_queue.py"
            ).read_text(encoding="utf-8"),
        ]
    ).casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text
    assert "documentation-only" in str(payload).casefold()
    assert "needs_manual_review" in str(payload).casefold()
