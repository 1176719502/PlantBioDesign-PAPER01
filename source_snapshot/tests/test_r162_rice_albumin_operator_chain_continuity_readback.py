# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import rice_albumin_manual_provenance_verification as provenance
from services import rice_albumin_operator_chain_continuity_readback as chain


ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "plant_seed" / "rice_albumin"
SEED_FILES = (
    SEED_DIR / "route_contexts.json",
    SEED_DIR / "component_records.json",
    SEED_DIR / "evidence_records.json",
)


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
        "schema_version": "rice_albumin_manual_verification.record_status.r162.test",
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
    manual_dir.mkdir()
    (manual_dir / provenance.MANUAL_STATUS_FILE).write_text(
        json.dumps(_manual_status_payload()),
        encoding="utf-8",
    )
    return manual_dir


def _payload(tmp_path: Path) -> dict[str, object]:
    return chain.build_rice_albumin_operator_chain_continuity_readback(
        manual_verification_dir=_write_manual_status(tmp_path)
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


def test_r162_payload_is_plain_chain_readback_with_expected_stage_keys(tmp_path: Path) -> None:
    payload = _payload(tmp_path)

    assert payload["operator_chain_schema_version"] == chain.OPERATOR_CHAIN_SCHEMA_VERSION
    assert payload["chain_key"] == chain.CHAIN_KEY
    assert payload["dataset_key"] == "rice_albumin"
    assert payload["dataset_label"]
    assert payload["chain_status"] == chain.CHAIN_STATUS_MANUAL_REVIEW
    assert payload["documentation_boundary"]
    assert payload["fail_closed"] is False
    assert payload["stage_summary"]["stage_keys"] == list(chain.EXPECTED_STAGE_KEYS)
    assert [stage["stage_key"] for stage in payload["stages"]] == list(chain.EXPECTED_STAGE_KEYS)
    assert all(stage["source_service"] for stage in payload["stages"])
    assert all("boundary_note" in stage for stage in payload["stages"])
    _assert_plain_data(payload)


def test_r162_preserves_rice_albumin_counts_and_blocked_states(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    stages = {stage["stage_key"]: stage for stage in payload["stages"]}
    promotion = payload["promotion_status"]

    assert stages["seed_records"]["record_count"] == 12
    assert "12 seed records represented" in stages["seed_records"]["output_summary"]
    assert stages["manual_verification_queue"]["record_count"] == 46
    assert "46 tasks represent 12 records" in stages["manual_verification_queue"]["output_summary"]
    assert stages["promotion_gate"]["gap_count"] == 12
    assert promotion["records_blocked_from_promotion"] == 12
    assert promotion["promotion_allowed"] is False
    assert promotion["promotion_allowed_count"] == 0
    assert promotion["ready_to_promote_count"] == 0
    assert promotion["queue_ready_to_promote_count"] == 0
    assert promotion["gate_ready_to_promote_count"] == 0
    assert any(gap["gap_key"] == "manual_queue_tasks" and gap["gap_count"] == 46 for gap in payload["open_gaps"])
    assert any(gap["gap_key"] == "records_blocked_from_promotion" and gap["gap_count"] == 12 for gap in payload["open_gaps"])
    assert all(stage["manual_review_required"] is True for stage in payload["stages"])
    assert all(stage["promotion_blocked"] is True for stage in payload["stages"])


def test_r162_does_not_fill_identifiers_promote_records_or_change_seed_data(tmp_path: Path) -> None:
    before = {path.name: path.read_bytes() for path in SEED_FILES}
    payload = _payload(tmp_path)
    after = {path.name: path.read_bytes() for path in SEED_FILES}
    identifier_status = payload["identifier_autofill_status"]

    assert before == after
    assert identifier_status["source_or_accession_auto_filled"] is False
    assert identifier_status["pmid_doi_database_id_auto_filled"] is False
    assert identifier_status["record_was_promoted"] is False
    assert payload["promotion_status"]["record_was_promoted"] is False
    assert payload["promotion_status"]["promotion_allowed_count"] == 0
    assert payload["promotion_status"]["ready_to_promote_count"] == 0


def test_r162_construct_task_and_draft_are_safely_marked_unavailable(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    stages = {stage["stage_key"]: stage for stage in payload["stages"]}

    assert stages["construct_task"]["stage_status"] == "unavailable_manual_review_required"
    assert stages["construct_draft"]["stage_status"] == "unavailable_manual_review_required"
    assert stages["construct_task"]["gap_count"] == 1
    assert stages["construct_draft"]["gap_count"] == 1
    assert "no identifiers, records, or status changes were added" in stages["construct_task"]["output_summary"].casefold()
    assert payload["stage_summary"]["unavailable_stage_count"] == 2


def test_r162_fails_closed_for_malformed_upstream_payload(tmp_path: Path) -> None:
    payload = chain.build_rice_albumin_operator_chain_continuity_readback(
        manual_verification_dir=_write_manual_status(tmp_path),
        seed_review_payload="malformed",  # type: ignore[arg-type]
    )

    assert payload["fail_closed"] is True
    assert payload["chain_status"] == chain.CHAIN_STATUS_FAIL_CLOSED
    assert payload["handoff_readiness_status"] == chain.HANDOFF_STATUS_FAIL_CLOSED
    assert any(gap["gap_key"] == "upstream_payload_fail_closed" for gap in payload["open_gaps"])
    assert any("fails closed" in warning for warning in payload["warnings"])
    assert payload["promotion_status"]["promotion_allowed_count"] == 0
    assert payload["promotion_status"]["ready_to_promote_count"] == 0


def test_r162_artemisia_annua_is_not_active_chain(tmp_path: Path) -> None:
    payload = _payload(tmp_path)

    assert payload["active_dataset_keys"] == ["rice_albumin"]
    inactive = payload["inactive_dataset_gates"]
    assert len(inactive) == 1
    assert inactive[0]["dataset_key"] == "artemisia_annua"
    assert inactive[0]["active_dataset_profile"] is False
    assert inactive[0]["conversion_allowed"] is False
    assert inactive[0]["included_in_active_chain"] is False
    assert all(stage["stage_key"] != "artemisia_annua" for stage in payload["stages"])


def test_r162_output_and_changed_sources_avoid_forbidden_claim_wording(tmp_path: Path) -> None:
    payload = _payload(tmp_path)
    rows = chain.build_rice_albumin_operator_chain_continuity_stage_rows(payload)

    assert payload["copy_safety_findings"] == []
    _copy_scan_value(payload)
    _copy_scan_value(rows)

    source_text = "\n".join(
        [
            (ROOT / "services" / "rice_albumin_operator_chain_continuity_readback.py").read_text(
                encoding="utf-8"
            ),
            (
                ROOT
                / "tests"
                / "test_r162_rice_albumin_operator_chain_continuity_readback.py"
            ).read_text(encoding="utf-8"),
        ]
    ).casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text
    assert "documentation-only" in str(payload).casefold()
    assert "manual_review" in str(payload).casefold()
