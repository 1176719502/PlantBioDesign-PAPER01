# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_review_task_queue_registry as registry
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
        "schema_version": "rice_albumin_manual_verification.record_status.r152.test",
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


def _source_kwargs(tmp_path: Path) -> dict[str, object]:
    return {"manual_verification_dir": _write_manual_status(tmp_path)}


def test_r152_rice_albumin_queue_is_registered_available_readonly(tmp_path: Path) -> None:
    source = registry.get_plant_review_task_queue_source(
        registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY,
        source_kwargs=_source_kwargs(tmp_path),
    )

    assert source["queue_key"] == registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY
    assert source["dataset_key"] == "rice_albumin"
    assert source["queue_status"] == registry.QUEUE_STATUS_AVAILABLE_READONLY
    assert source["active"] is True
    assert source["read_only"] is True
    assert source["manual_review_required"] is True
    assert source["promotion_allowed"] is False
    assert source["summary"]["total_tasks"] == 46
    assert source["summary"]["represented_records"] == 12
    _assert_plain_data(source)


def test_r152_registry_source_returns_r151_queue_payload_safely(tmp_path: Path) -> None:
    payload = registry.get_plant_review_task_queue_payload(
        registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY,
        source_kwargs=_source_kwargs(tmp_path),
    )

    assert payload["queue_metadata"]["queue_key"] == "rice_albumin_manual_provenance_verification"
    assert payload["queue_metadata"]["dataset_key"] == "rice_albumin"
    assert payload["queue_metadata"]["promotion_allowed"] is False
    assert payload["summary"]["total_tasks"] == 46
    assert payload["summary"]["records_blocked_from_promotion"] == 12
    assert payload["summary"]["ready_to_promote_count"] == 0
    assert all(task["promotion_blocked"] is True for task in payload["tasks"])
    assert all(task["do_not_promote_until_verified"] is True for task in payload["tasks"])
    _assert_plain_data(payload)


def test_r152_unknown_queue_lookup_fails_closed() -> None:
    source = registry.get_plant_review_task_queue_source("unknown_queue")
    payload = registry.get_plant_review_task_queue_payload("unknown_queue")

    assert source["queue_status"] == registry.QUEUE_STATUS_UNKNOWN_FAIL_CLOSED
    assert source["active"] is False
    assert source["promotion_allowed"] is False
    assert source["summary"]["fail_closed"] is True
    assert payload["workflow_status"].endswith("fail_closed")
    assert payload["summary"]["fail_closed"] is True
    assert payload["summary"]["ready_to_promote_count"] == 0


def test_r152_list_sources_contains_only_active_rice_albumin_queue(tmp_path: Path) -> None:
    sources = registry.list_plant_review_task_queue_sources(
        source_kwargs_by_key={
            registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY: _source_kwargs(tmp_path)
        }
    )

    assert [source["queue_key"] for source in sources] == [
        registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY
    ]
    assert all(source["promotion_allowed"] is False for source in sources)
    assert "artemisia_annua" not in {source["dataset_key"] for source in sources if source["active"]}


def test_r152_does_not_fill_identifiers_or_promote_records(tmp_path: Path) -> None:
    payload = registry.get_plant_review_task_queue_payload(
        registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY,
        source_kwargs=_source_kwargs(tmp_path),
    )
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


def test_r152_output_and_changed_sources_avoid_forbidden_positive_or_downstream_copy(
    tmp_path: Path,
) -> None:
    source = registry.get_plant_review_task_queue_source(
        registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY,
        source_kwargs=_source_kwargs(tmp_path),
    )
    payload = registry.get_plant_review_task_queue_payload(
        registry.RICE_ALBUMIN_MANUAL_PROVENANCE_QUEUE_KEY,
        source_kwargs=_source_kwargs(tmp_path / "payload"),
    )
    unknown = registry.get_plant_review_task_queue_source("unknown_queue")
    _copy_scan_value(source)
    _copy_scan_value(payload)
    _copy_scan_value(unknown)

    source_text = "\n".join(
        [
            (ROOT / "services" / "plant_review_task_queue_registry.py").read_text(encoding="utf-8"),
            (ROOT / "tests" / "test_r152_plant_review_task_queue_registry.py").read_text(
                encoding="utf-8"
            ),
        ]
    ).casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text
    assert "documentation-only" in str(payload).casefold()
    assert "needs_manual_review" in str(payload).casefold()
