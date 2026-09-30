# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_review_task_queue_registry as registry
from services import plant_review_task_queue_snapshot_readback as snapshot
from services import rice_albumin_manual_provenance_verification as provenance


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
        "schema_version": "rice_albumin_manual_verification.record_status.r153.test",
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


def _source_kwargs_by_key(tmp_path: Path) -> dict[str, dict[str, object]]:
    return {
        registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY: {
            "manual_verification_dir": _write_manual_status(tmp_path)
        }
    }


def _snapshot(tmp_path: Path) -> dict[str, object]:
    return snapshot.build_plant_review_task_queue_snapshot(
        source_kwargs_by_key=_source_kwargs_by_key(tmp_path)
    )


def test_r153_snapshot_includes_rice_albumin_queue_summary(tmp_path: Path) -> None:
    payload = _snapshot(tmp_path)
    queue_summary = payload["queue_summaries"][0]

    assert payload["snapshot_metadata"]["snapshot_schema_version"] == (
        snapshot.PLANT_REVIEW_TASK_QUEUE_SNAPSHOT_SCHEMA_VERSION
    )
    assert queue_summary["queue_key"] == registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY
    assert queue_summary["dataset_key"] == "rice_albumin"
    assert queue_summary["queue_status"] == registry.QUEUE_STATUS_AVAILABLE_READONLY
    assert queue_summary["manual_review_required"] is True
    assert queue_summary["promotion_allowed"] is False
    _assert_plain_data(payload)


def test_r153_snapshot_preserves_r146_counts(tmp_path: Path) -> None:
    payload = _snapshot(tmp_path)
    summary = payload["summary"]
    queue_summary = payload["queue_summaries"][0]

    assert queue_summary["total_tasks"] == 46
    assert queue_summary["represented_records"] == 12
    assert queue_summary["records_blocked_from_promotion"] == 12
    assert queue_summary["ready_to_promote_count"] == 0
    assert summary["total_tasks"] == 46
    assert summary["represented_records"] == 12
    assert summary["records_blocked_from_promotion"] == 12
    assert summary["promotion_blocked_count"] == 12
    assert summary["ready_to_promote_count"] == 0


def test_r153_snapshot_exposes_missing_source_and_accession_counts(tmp_path: Path) -> None:
    payload = _snapshot(tmp_path)
    queue_summary = payload["queue_summaries"][0]

    assert queue_summary["missing_source_id_count"] == 6
    assert queue_summary["missing_accession_count"] == 12
    assert queue_summary["missing_field_counts"]["source_id"] == 28
    assert queue_summary["missing_field_counts"]["accession"] == 46
    assert payload["summary"]["missing_field_counts"]["source_id"] == 28
    assert payload["summary"]["missing_field_counts"]["accession"] == 46


def test_r153_unknown_queue_snapshot_fails_closed() -> None:
    payload = snapshot.build_plant_review_task_queue_snapshot(["unknown_queue"])
    row = payload["queue_summaries"][0]
    readback_rows = snapshot.build_plant_review_task_queue_readback_rows(payload)

    assert row["queue_key"] == "unknown_queue"
    assert row["queue_status"] == registry.QUEUE_STATUS_UNKNOWN_FAIL_CLOSED
    assert row["fail_closed"] is True
    assert row["promotion_allowed"] is False
    assert row["ready_to_promote_count"] == 0
    assert payload["summary"]["fail_closed"] is True
    assert readback_rows[0]["fail_closed"] is True


def test_r153_readback_rows_are_plain_dict_list(tmp_path: Path) -> None:
    payload = _snapshot(tmp_path)
    rows = snapshot.build_plant_review_task_queue_readback_rows(payload)

    assert isinstance(rows, list)
    assert len(rows) == 1
    assert rows[0]["queue_key"] == registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY
    assert rows[0]["total_tasks"] == 46
    assert rows[0]["records_blocked_from_promotion"] == 12
    assert rows[0]["missing_source_id_count"] == 6
    assert rows[0]["missing_accession_count"] == 12
    assert rows[0]["promotion_allowed"] is False
    _assert_plain_data(rows)


def test_r153_does_not_fill_identifiers_or_promote_records(tmp_path: Path) -> None:
    payload = _snapshot(tmp_path)
    queue_summary = payload["queue_summaries"][0]
    forbidden_fill_keys = {
        "source_id",
        "source_identifier",
        "accession",
        "database_id",
        "pmid",
        "doi",
    }

    assert queue_summary["ready_to_promote_count"] == 0
    assert queue_summary["promotion_allowed"] is False
    assert forbidden_fill_keys.isdisjoint(queue_summary)
    assert not any("PMID:" in str(row) or "DOI:" in str(row) for row in payload["queue_summaries"])


def test_r153_output_and_changed_sources_avoid_forbidden_positive_or_downstream_copy(
    tmp_path: Path,
) -> None:
    payload = _snapshot(tmp_path)
    rows = snapshot.build_plant_review_task_queue_readback_rows(payload)
    unknown = snapshot.build_plant_review_task_queue_snapshot(["unknown_queue"])
    _copy_scan_value(payload)
    _copy_scan_value(rows)
    _copy_scan_value(unknown)

    source_text = "\n".join(
        [
            (ROOT / "services" / "plant_review_task_queue_snapshot_readback.py").read_text(
                encoding="utf-8"
            ),
            (ROOT / "tests" / "test_r153_plant_review_task_queue_snapshot_readback.py").read_text(
                encoding="utf-8"
            ),
        ]
    ).casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text
    assert "documentation-only" in str(payload).casefold()
    assert "needs_manual_review" in str(payload).casefold()
