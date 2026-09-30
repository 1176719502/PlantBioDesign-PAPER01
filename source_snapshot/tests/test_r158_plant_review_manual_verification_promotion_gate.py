# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_review_manual_verification_promotion_gate as gate
from services import plant_review_manual_verification_status as status
from services import plant_review_manual_verification_status_snapshot as r156
from services import plant_review_manual_verification_transition_guard as r157
from services import plant_review_task_queue_registry as registry
from services import plant_review_task_queue_snapshot_readback as snapshot
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
        "r131-component-vector-backbone_context-placeholder": ["none for current R131 scaffold unless scoped"],
        "r131-evidence-target-identity-placeholder": ["reviewed literature metadata"],
        "r131-evidence-rice-seed-context-placeholder": ["reviewed rice seed context literature metadata"],
    }
    return {
        "schema_version": "rice_albumin_manual_verification.record_status.r158.test",
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


def _rice_snapshot(tmp_path: Path) -> dict[str, object]:
    return r156.build_plant_review_manual_verification_status_snapshot(
        source_kwargs_by_key=_source_kwargs_by_key(tmp_path)
    )


def _summary_status_payload(
    verification_status: str = status.STATUS_PENDING_MANUAL_REVIEW,
) -> dict[str, object]:
    task_id = f"{registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY}-summary-manual-status"
    return status.build_plant_review_manual_verification_status(
        {
            "queue_summaries": [
                {
                    "queue_key": registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY,
                    "dataset_key": "rice_albumin",
                    "manual_review_boundary_text": "Documentation-only summary row for test readback.",
                }
            ]
        },
        status_records=[
            {
                "task_id": task_id,
                "verification_status": verification_status,
                "reviewed_reference_kind": "reviewer-entered literature note",
                "reviewed_reference_value": "reviewer-entered-status-only-note",
            }
        ],
    )


def _seed_texts() -> dict[str, str]:
    return {str(path): path.read_text(encoding="utf-8") for path in SEED_FILES}


def test_r158_rice_albumin_promotion_gate_remains_blocked(tmp_path: Path) -> None:
    snapshot_payload = _rice_snapshot(tmp_path)
    payload = gate.build_plant_review_manual_verification_promotion_gate(snapshot_payload)
    rows = gate.build_plant_review_manual_verification_promotion_gate_readback_rows(payload)

    assert payload["gate_schema_version"] == gate.MANUAL_VERIFICATION_PROMOTION_GATE_SCHEMA_VERSION
    assert payload["promotion_gate_status"] == gate.PROMOTION_GATE_STATUS_BLOCKED
    assert payload["queue_key"] == registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY
    assert payload["total_tasks"] == 46
    assert payload["represented_records"] == 12
    assert payload["promotion_blocked_count"] == 12
    assert payload["ready_to_promote_count"] == 0
    assert payload["promotion_allowed_count"] == 0
    assert payload["promotion_allowed"] is False
    assert rows[0]["promotion_allowed"] is False
    _assert_plain_data(payload)
    _assert_plain_data(rows)


def test_r158_verified_reference_recorded_count_does_not_imply_promotion(tmp_path: Path) -> None:
    task_snapshot = snapshot.build_plant_review_task_queue_snapshot(
        source_kwargs_by_key=_source_kwargs_by_key(tmp_path)
    )
    status_snapshot = r156.build_plant_review_manual_verification_status_snapshot(
        task_snapshot,
        status_payload=_summary_status_payload(status.STATUS_VERIFIED_REFERENCE_RECORDED),
    )
    payload = gate.build_plant_review_manual_verification_promotion_gate(status_snapshot)

    assert payload["verified_reference_recorded_count"] == 1
    assert payload["promotion_allowed"] is False
    assert payload["promotion_allowed_count"] == 0
    assert payload["ready_to_promote_count"] == 0
    assert any("status-only" in reason for reason in payload["blocking_reasons"])


def test_r158_missing_or_malformed_snapshot_fails_closed() -> None:
    for source in ({}, {"task_summary": {}, "verification_status_summary": {}}):
        payload = gate.build_plant_review_manual_verification_promotion_gate(source)

        assert payload["promotion_gate_status"] == gate.PROMOTION_GATE_STATUS_FAIL_CLOSED
        assert payload["fail_closed"] is True
        assert payload["promotion_allowed"] is False
        assert payload["promotion_allowed_count"] == 0
        assert payload["manual_review_required"] is True


def test_r158_identifier_blockers_remain_visible() -> None:
    payload = gate.build_plant_review_manual_verification_promotion_gate(
        {
            "queue_key": "synthetic_queue",
            "dataset_key": "synthetic_dataset",
            "task_summary": {
                "total_tasks": 2,
                "represented_records": 2,
                "records_blocked_from_promotion": 2,
                "promotion_blocked_count": 2,
                "ready_to_promote_count": 0,
                "missing_field_counts": {"source_id": 1, "accession": 2},
            },
            "verification_status_summary": {
                "total_status_records": 2,
                "promotion_allowed_count": 0,
                "verified_reference_recorded_count": 0,
                "status_counts": {status.STATUS_BLOCKED_MISSING_IDENTIFIER: 2},
            },
        }
    )

    assert payload["promotion_allowed"] is False
    assert payload["promotion_allowed_count"] == 0
    assert payload["identifier_blockers"] == [
        {
            "blocked_count": 2,
            "blocking_reason": "Identifier gap remains visible for manual review.",
            "identifier_field": "accession",
            "promotion_allowed": False,
        },
        {
            "blocked_count": 1,
            "blocking_reason": "Identifier gap remains visible for manual review.",
            "identifier_field": "source_id",
            "promotion_allowed": False,
        },
    ]


def test_r158_second_review_requirement_from_r157_transition_remains_visible() -> None:
    transition = r157.build_plant_review_manual_verification_transition_guard(
        {
            "task_id": "task-rejected",
            "verification_status": status.STATUS_REJECTED_BEFORE_PROMOTION,
        },
        {
            "task_id": "task-rejected",
            "verification_status": status.STATUS_VERIFIED_REFERENCE_RECORDED,
        },
    )
    payload = gate.build_plant_review_manual_verification_promotion_gate(
        {
            "queue_key": "synthetic_queue",
            "dataset_key": "synthetic_dataset",
            "task_summary": {
                "total_tasks": 1,
                "represented_records": 1,
                "records_blocked_from_promotion": 1,
                "promotion_blocked_count": 1,
                "ready_to_promote_count": 0,
            },
            "verification_status_summary": {
                "total_status_records": 1,
                "promotion_allowed_count": 0,
                "verified_reference_recorded_count": 0,
                "status_counts": {status.STATUS_REJECTED_BEFORE_PROMOTION: 1},
            },
        },
        transition_readbacks=[transition],
    )

    assert payload["second_review_required_count"] == 1
    assert payload["fail_closed"] is True
    assert payload["transition_blockers"][0]["requires_second_review"] is True
    assert payload["promotion_allowed"] is False


def test_r158_does_not_fill_identifiers_promote_records_or_change_seed_data(tmp_path: Path) -> None:
    before_seed_texts = _seed_texts()
    snapshot_payload = _rice_snapshot(tmp_path)
    payload = gate.build_plant_review_manual_verification_promotion_gate(snapshot_payload)

    assert payload["promotion_allowed"] is False
    assert payload["promotion_allowed_count"] == 0
    assert payload["ready_to_promote_count"] == 0
    assert all(key not in payload for key in FORBIDDEN_FILL_KEYS)
    assert "reviewed_reference_value" not in payload
    assert "PMID:" not in str(payload)
    assert "DOI:" not in str(payload)
    assert _seed_texts() == before_seed_texts


def test_r158_output_and_changed_sources_avoid_forbidden_positive_or_downstream_copy(
    tmp_path: Path,
) -> None:
    payload = gate.build_plant_review_manual_verification_promotion_gate(_rice_snapshot(tmp_path))
    rows = gate.build_plant_review_manual_verification_promotion_gate_readback_rows(payload)
    _copy_scan_value(payload)
    _copy_scan_value(rows)

    source_text = "\n".join(
        [
            (ROOT / "services" / "plant_review_manual_verification_promotion_gate.py").read_text(
                encoding="utf-8"
            ),
            (
                ROOT
                / "tests"
                / "test_r158_plant_review_manual_verification_promotion_gate.py"
            ).read_text(encoding="utf-8"),
        ]
    ).casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text
    assert "documentation-only" in str(payload).casefold()
