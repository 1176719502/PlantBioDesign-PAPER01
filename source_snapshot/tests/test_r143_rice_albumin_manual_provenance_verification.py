# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

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
    _term("ready ", "for execution"),
)


ALLOWED_KEYS_WITH_BLOCKED_TERMS = {
    "blocked_output_categories",
    "blocked_output_boundaries",
    "blocked_output_boundary_categories",
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


def _copy_scan_value(value: object, *, key_path: tuple[str, ...] = ()) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            _copy_scan_value(nested, key_path=(*key_path, key))
        return
    if isinstance(value, list):
        for nested in value:
            _copy_scan_value(nested, key_path=key_path)
        return
    if not isinstance(value, str):
        return

    if key_path and key_path[-1] in ALLOWED_KEYS_WITH_BLOCKED_TERMS:
        return
    text = value.casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in text


def _manual_status_payload() -> dict[str, object]:
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
    return {
        "schema_version": "rice_albumin_manual_verification.record_status.test",
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
                    "needs_manual_review",
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


def test_r143_payload_includes_all_r131_rice_albumin_seed_records(tmp_path: Path) -> None:
    payload = provenance.build_rice_albumin_manual_provenance_verification_payload(
        manual_verification_dir=_write_manual_status(tmp_path)
    )
    rows = payload["records"]

    assert payload["workflow_schema_version"] == provenance.MANUAL_PROVENANCE_SCHEMA_VERSION
    assert payload["workflow_status"] == provenance.MANUAL_PROVENANCE_STATUS_READY
    assert payload["read_only"] is True
    assert payload["manual_review_required"] is True
    assert payload["summary"]["total_records"] == 12
    assert payload["summary"]["all_expected_records_present"] is True
    assert len(rows) == 12
    assert {row["record_id"] for row in rows} == set(payload["summary"]["records_missing_accession"])
    _assert_plain_data(payload)


def test_r143_missing_source_ids_and_accessions_remain_visible(tmp_path: Path) -> None:
    payload = provenance.build_rice_albumin_manual_provenance_verification_payload(
        manual_verification_dir=_write_manual_status(tmp_path)
    )
    rows = {row["record_id"]: row for row in payload["records"]}

    target = rows["r131-evidence-target-identity-placeholder"]
    route = rows["r131-route-plant-protein-expression-evidence-first"]

    assert payload["summary"]["missing_source_id_count"] == 6
    assert payload["summary"]["missing_accession_count"] == 12
    assert target["missing_source_id"] is True
    assert target["missing_accession"] is True
    assert "missing_source_id" in target["safe_review_categories"]
    assert "missing_accession" in target["safe_review_categories"]
    assert route["missing_source_id"] is False
    assert route["missing_accession"] is True
    assert route["source_id"].startswith("data/plant_synbio_knowledge/")


def test_r143_records_remain_review_required_and_not_promoted(tmp_path: Path) -> None:
    payload = provenance.build_rice_albumin_manual_provenance_verification_payload(
        manual_verification_dir=_write_manual_status(tmp_path)
    )

    assert payload["summary"]["all_records_need_manual_review"] is True
    assert payload["summary"]["all_records_do_not_promote"] is True
    assert payload["summary"]["any_record_promoted"] is False
    assert payload["summary"]["any_source_or_accession_auto_filled"] is False
    assert payload["summary"]["do_not_promote_count"] == 12
    assert all(row["review_status"] == "needs_manual_review" for row in payload["records"])
    assert all(row["record_was_promoted"] is False for row in payload["records"])
    assert all(row["auto_filled_source_or_accession"] is False for row in payload["records"])
    assert all(row["do_not_promote_status"] == provenance.DO_NOT_PROMOTE_STATUS for row in payload["records"])


def test_r143_safe_categories_and_readback_rows_are_plain(tmp_path: Path) -> None:
    payload = provenance.build_rice_albumin_manual_provenance_verification_payload(
        manual_verification_dir=_write_manual_status(tmp_path)
    )
    rows = provenance.build_rice_albumin_manual_provenance_readback_rows(payload)
    target = next(row for row in rows if row["record_id"] == "r131-component-albumin-like-cds-source-placeholder")

    assert isinstance(rows, list)
    assert len(rows) == 12
    assert set(target) == {
        "record_id",
        "record_type",
        "review_status",
        "provenance_status",
        "source_type",
        "source_id",
        "missing_source_id",
        "missing_accession",
        "review_categories",
        "manual_action",
        "do_not_promote_status",
        "manual_review_note",
    }
    assert "candidate_source_category_only" in target["review_categories"]
    assert "requires_manual_lookup" in target["review_categories"]
    assert target["manual_action"] == "manual lookup required"
    _assert_plain_data(rows)


def test_r143_missing_external_materials_fail_closed_without_promoting_records(tmp_path: Path) -> None:
    missing_dir = tmp_path / "missing"
    payload = provenance.build_rice_albumin_manual_provenance_verification_payload(
        manual_verification_dir=missing_dir
    )

    assert payload["workflow_status"] == provenance.MANUAL_PROVENANCE_STATUS_FAIL_CLOSED
    assert payload["summary"]["manual_material_status"] == provenance.MANUAL_PROVENANCE_STATUS_FAIL_CLOSED
    assert payload["summary"]["total_records"] == 12
    assert payload["summary"]["all_records_need_manual_review"] is True
    assert payload["summary"]["all_records_do_not_promote"] is True
    assert payload["summary"]["manual_lookup_required_count"] == 12
    assert any("missing" in warning for warning in payload["warnings"])
    assert all(row["must_not_be_promoted"] is True for row in payload["records"])
    assert all("requires_manual_lookup" in row["safe_review_categories"] for row in payload["records"])


def test_r143_malformed_external_materials_fail_closed_without_promoting_records(tmp_path: Path) -> None:
    manual_dir = tmp_path / "manual"
    manual_dir.mkdir()
    (manual_dir / provenance.MANUAL_STATUS_FILE).write_text("{not-json", encoding="utf-8")

    payload = provenance.build_rice_albumin_manual_provenance_verification_payload(
        manual_verification_dir=manual_dir
    )

    assert payload["workflow_status"] == provenance.MANUAL_PROVENANCE_STATUS_FAIL_CLOSED
    assert payload["summary"]["all_records_need_manual_review"] is True
    assert payload["summary"]["all_records_do_not_promote"] is True
    assert payload["summary"]["any_record_promoted"] is False
    assert any("could not be read" in warning for warning in payload["warnings"])


def test_r143_partial_external_materials_fail_closed(tmp_path: Path) -> None:
    payload = _manual_status_payload()
    payload["records"] = payload["records"][:-1]
    manual_dir = _write_manual_status(tmp_path, payload)

    result = provenance.build_rice_albumin_manual_provenance_verification_payload(
        manual_verification_dir=manual_dir
    )

    assert result["workflow_status"] == provenance.MANUAL_PROVENANCE_STATUS_FAIL_CLOSED
    assert result["summary"]["total_records"] == 12
    assert result["manual_materials"]["missing_manual_record_ids"] == [
        "r131-evidence-rice-seed-context-placeholder"
    ]
    assert result["summary"]["all_records_do_not_promote"] is True


def test_r143_output_and_changed_sources_avoid_forbidden_positive_or_downstream_copy(tmp_path: Path) -> None:
    payload = provenance.build_rice_albumin_manual_provenance_verification_payload(
        manual_verification_dir=_write_manual_status(tmp_path)
    )
    rows = provenance.build_rice_albumin_manual_provenance_readback_rows(payload)
    _copy_scan_value(payload)
    _copy_scan_value(rows)

    source_text = "\n".join(
        [
            (ROOT / "services" / "rice_albumin_manual_provenance_verification.py").read_text(encoding="utf-8"),
            (ROOT / "tests" / "test_r143_rice_albumin_manual_provenance_verification.py").read_text(
                encoding="utf-8"
            ),
        ]
    ).casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text
    assert "documentation-only" in str(payload).casefold()
    assert "needs_manual_review" in str(payload).casefold()
