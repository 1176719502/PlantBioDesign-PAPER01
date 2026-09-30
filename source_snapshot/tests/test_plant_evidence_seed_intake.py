# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_evidence_review_worksheet_presenter as worksheet_presenter
from services import plant_evidence_seed_intake as intake
from services import plant_route_construct_traceability_readback as traceability_readback


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
    _term("experiment", "-ready"),
    _term("production", "-ready"),
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


def _load() -> dict[str, object]:
    return intake.load_plant_evidence_seed_intake()


def test_r131_rice_albumin_seed_files_load_into_plain_payloads() -> None:
    payload = _load()

    assert payload["seed_intake_schema_version"] == intake.SEED_INTAKE_SCHEMA_VERSION
    assert payload["read_only"] is True
    assert payload["plant_scope_only"] is True
    assert payload["manual_review_required"] is True
    assert payload["summary"]["total_records"] == 12
    assert payload["summary"]["route_context_count"] == 3
    assert payload["summary"]["component_record_count"] == 7
    assert payload["summary"]["evidence_record_count"] == 2
    assert payload["summary"]["rejected_row_count"] == 0
    assert len(payload["records"]) == 12
    _assert_plain_data(payload)


def test_preserved_fields_review_required_state_and_provenance_gaps_remain_visible() -> None:
    payload = _load()
    records = payload["records"]
    first = records[0]

    for field in intake.PRESERVED_FIELDS:
        assert field in first
    assert {record["review_status"] for record in records} == {"needs_manual_review"}
    assert {record["provenance_status"] for record in records} == {"candidate", "missing", "partial"}
    assert all(record["needs_manual_review"] is True for record in records)
    assert all(record["manual_review_note"] for record in records)
    assert payload["summary"]["manual_review_required_count"] == 12
    assert payload["summary"]["provenance_status_counts"] == {
        "candidate": 2,
        "missing": 4,
        "partial": 6,
    }
    assert payload["gap_records"]
    assert any("provenance_status:missing" in row["missing_fields"] for row in payload["gap_records"])
    assert any("provenance_status:partial" in row["missing_fields"] for row in payload["gap_records"])
    assert any("provenance_status:candidate" in row["missing_fields"] for row in payload["gap_records"])


def test_malformed_records_fail_closed_as_rejected_rows(tmp_path: Path) -> None:
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "route_contexts.json").write_text(
        json.dumps({"schema_version": "test", "batch": "test", "records": [{"record_type": "RouteContext"}]}),
        encoding="utf-8",
    )
    (seed_dir / "component_records.json").write_text(
        json.dumps({"schema_version": "test", "batch": "test", "records": ["bad-row"]}),
        encoding="utf-8",
    )
    (seed_dir / "evidence_records.json").write_text(
        json.dumps({"schema_version": "test", "batch": "test", "records": []}),
        encoding="utf-8",
    )

    payload = intake.load_plant_evidence_seed_intake(seed_dir)

    assert payload["records"] == []
    assert payload["summary"]["rejected_row_count"] == 2
    assert payload["summary"]["total_records"] == 0
    assert payload["seed_intake_status"] == intake.SEED_INTAKE_STATUS_EMPTY
    assert {row["rejection_reason"] for row in payload["rejected_rows"]} == {
        "missing_record_id_or_record_type",
        "record_not_object",
    }
    assert all(row["needs_manual_review"] is True for row in payload["rejected_rows"])
    assert all(row["provenance_status"] == "malformed" for row in payload["rejected_rows"])
    assert len(payload["r118_worksheet_input"]["review_items"]) == 2


def test_missing_seed_file_returns_safe_rejected_row(tmp_path: Path) -> None:
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "component_records.json").write_text(
        json.dumps({"schema_version": "test", "batch": "test", "records": []}),
        encoding="utf-8",
    )
    (seed_dir / "evidence_records.json").write_text(
        json.dumps({"schema_version": "test", "batch": "test", "records": []}),
        encoding="utf-8",
    )

    payload = intake.load_plant_evidence_seed_intake(seed_dir)

    assert payload["summary"]["rejected_row_count"] == 1
    assert payload["rejected_rows"][0]["rejection_reason"] == "seed_file_missing"
    assert "route_contexts.json is missing" in payload["warnings"][0]


def test_missing_source_and_provenance_are_visible_to_worksheet_followup_logic() -> None:
    payload = _load()
    worksheet_input = payload["r118_worksheet_input"]
    worksheet = worksheet_presenter.build_plant_evidence_review_worksheet_payload(**worksheet_input)

    assert worksheet["worksheet_status"] == worksheet_presenter.SUPPORTED_WORKSHEET_STATUS
    assert worksheet["summary"]["total_evidence_rows"] == 2
    assert worksheet["summary"]["component_slot_row_count"] == 7
    assert worksheet["summary"]["missing_source_or_provenance_count"] >= 2
    assert worksheet["summary"]["manual_review_required_count"] >= 12
    assert any(
        row["followup_type"] == "missing_provenance"
        for row in worksheet["followup_queue_section"]["rows"]
    )
    assert any(
        row["followup_type"] == "manual_review_required"
        for row in worksheet["followup_queue_section"]["rows"]
    )
    assert all(
        "source/provenance" in row["source_or_provenance_placeholder"]
        or "provenance_status=" in row["source_or_provenance_placeholder"]
        for row in worksheet["evidence_review_section"]["rows"]
    )


def test_r118_worksheet_compatible_input_preserves_record_counts_and_links() -> None:
    payload = _load()
    worksheet_input = intake.build_r118_evidence_worksheet_input(payload)

    assert set(worksheet_input) == {
        "route_context",
        "evidence_placeholders",
        "component_slots",
        "review_items",
        "worksheet_context",
    }
    assert len(worksheet_input["evidence_placeholders"]) == 2
    assert len(worksheet_input["component_slots"]) == 7
    assert len(worksheet_input["review_items"]) == len(payload["gap_records"])
    target_evidence = next(
        row
        for row in worksheet_input["evidence_placeholders"]
        if row["record_id"] == "r131-evidence-target-identity-placeholder"
    )
    assert target_evidence["linked_component_id"] == "r131-component-albumin-like-cds-source-placeholder"
    assert target_evidence["slot_id"] == "gene_or_cds_source"
    assert target_evidence["review_status"] == "needs_manual_review"
    assert target_evidence["source_status"] == "missing"


def test_r128_traceability_input_provides_route_component_evidence_linkage() -> None:
    payload = _load()
    traceability_input = payload["r128_traceability_input"]
    traceability = traceability_readback.build_plant_route_construct_traceability_readback(**traceability_input)

    assert traceability["traceability_status"] == traceability_readback.TRACEABILITY_STATUS_READY
    assert traceability["read_only"] is True
    assert traceability["manual_review_required"] is True
    assert traceability["summary"]["trace_row_count"] >= 2
    assert any(
        row["linked_evidence_id"] == "r131-evidence-target-identity-placeholder"
        and "r131-component-albumin-like-cds-source-placeholder" in row["linked_component"]
        and "gene_or_cds_source" in row["linked_component_slot"]
        for row in traceability["traceability_section"]["rows"]
    )
    assert any(
        row["review_status"] == "manual_review_required"
        for row in traceability["traceability_section"]["rows"]
    )


def test_loader_outputs_avoid_choice_downstream_and_claim_wording() -> None:
    payload = _load()
    text = str(payload).casefold()
    service_text = (Path(__file__).resolve().parents[1] / "services" / "plant_evidence_seed_intake.py").read_text(
        encoding="utf-8"
    ).casefold()

    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in text
        assert phrase not in service_text

    assert "documentation review" in text
    assert "manual_review" in text
