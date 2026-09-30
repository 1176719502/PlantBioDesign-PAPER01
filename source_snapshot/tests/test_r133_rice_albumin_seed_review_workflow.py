# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_evidence_review_worksheet_presenter as worksheet_presenter
from services import plant_evidence_seed_intake as intake
from services import plant_review_handoff_data_adapter as handoff_adapter
from services import plant_route_construct_traceability_readback as traceability_readback
from services import rice_albumin_seed_review_workflow as workflow


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
)

ALLOWED_BLOCKED_LABELS = (
    "experimental_validation",
    "experimental_validation_claim",
    "yield_prediction",
    "optimization_output",
    "optimized_sequence",
    "pathway_optimization",
    "codon_optimization_output",
    "expression_success_claim",
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
    return workflow.build_rice_albumin_seed_review_workflow()


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

    text = value.casefold()
    if key_path and key_path[-1] in {
        "blocked_output_categories",
        "blocked_output_boundaries",
        "blocked_output_boundary_categories",
        "source_references",
    }:
        assert text in ALLOWED_BLOCKED_LABELS or not any(phrase in text for phrase in FORBIDDEN_OUTPUT_COPY)
        return

    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in text


def test_r133_loads_rice_albumin_seed_into_existing_review_chain() -> None:
    payload = _load()

    assert payload["workflow_schema_version"] == workflow.SEED_REVIEW_WORKFLOW_SCHEMA_VERSION
    assert payload["workflow_status"] == workflow.SEED_REVIEW_WORKFLOW_STATUS_READY
    assert payload["read_only"] is True
    assert payload["plant_scope_only"] is True
    assert payload["manual_review_required"] is True
    assert payload["seed_intake"]["seed_intake_schema_version"] == intake.SEED_INTAKE_SCHEMA_VERSION
    assert payload["evidence_worksheet"]["worksheet_schema_version"] == worksheet_presenter.WORKSHEET_SCHEMA_VERSION
    assert payload["route_construct_traceability"]["traceability_schema_version"] == (
        traceability_readback.TRACEABILITY_SCHEMA_VERSION
    )
    assert payload["handoff_readback"]["handoff_schema_version"] == handoff_adapter.HANDOFF_SCHEMA_VERSION
    assert payload["summary"]["seed_record_count"] == 12
    assert payload["summary"]["worksheet_evidence_row_count"] == 2
    assert payload["summary"]["worksheet_component_slot_row_count"] == 7
    assert payload["summary"]["traceability_row_count"] >= 2
    _assert_plain_data(payload)


def test_evidence_worksheet_rows_preserve_review_required_and_provenance_gap_fields() -> None:
    worksheet = _load()["evidence_worksheet"]
    evidence_rows = worksheet["evidence_review_section"]["rows"]
    component_rows = worksheet["component_slot_linkage_section"]["rows"]
    manual_rows = worksheet["manual_review_section"]["rows"]

    target_row = next(
        row
        for row in evidence_rows
        if row["evidence_item_id"] == "r131-evidence-target-identity-placeholder"
    )

    assert worksheet["worksheet_status"] == worksheet_presenter.SUPPORTED_WORKSHEET_STATUS
    assert worksheet["summary"]["overall_review_state"] == worksheet_presenter.OVERALL_STATE_REQUIRES_MANUAL_REVIEW
    assert target_row["review_status"] == "needs_manual_review"
    assert target_row["evidence_status"] == "needs_manual_review"
    assert target_row["source_or_provenance_placeholder"] == "source/provenance placeholder missing"
    assert target_row["gap_reason"]
    assert target_row["manual_review_note"].startswith("Target identity evidence still needs manual curation")
    assert any(row["review_status"] == "needs_manual_review" for row in component_rows)
    assert any("provenance_status:missing" in row["gap_reason"] for row in manual_rows)


def test_followup_and_gap_information_remains_visible() -> None:
    payload = _load()
    worksheet = payload["evidence_worksheet"]
    followup_view = payload["followup_queue_view"]
    followups = worksheet["followup_queue_section"]["rows"]

    assert payload["seed_intake"]["gap_records"]
    assert worksheet["summary"]["followup_queue_count"] == len(followups)
    assert followup_view["total_count"] == len(followups)
    assert "missing_provenance" in followup_view["followup_type_options"]
    assert "manual_review_required" in followup_view["followup_type_options"]
    assert any(row["followup_type"] == "missing_provenance" for row in followups)
    assert any(row["followup_type"] == "manual_review_required" for row in followups)
    assert followup_view["group_counts"]["manual_review_required"] > 0


def test_route_context_evidence_ids_and_component_slot_links_survive_traceability() -> None:
    traceability = _load()["route_construct_traceability"]
    rows = traceability["traceability_section"]["rows"]

    assert traceability["traceability_status"] == traceability_readback.TRACEABILITY_STATUS_READY
    assert traceability["summary"]["trace_row_count"] == len(rows)
    assert traceability["intent_section"]["rows"][1]["value"] == "plant_protein_expression_evidence_first_route_template"
    assert any(
        row["linked_evidence_id"] == "r131-evidence-target-identity-placeholder"
        and "r131-component-albumin-like-cds-source-placeholder" in row["linked_component"]
        and "gene_or_cds_source" in row["linked_component_slot"]
        and row["route_or_context_id"] == "plant_protein_expression_evidence_first_route_template"
        and row["review_status"] == "manual_review_required"
        for row in rows
    )
    assert any(row["manual_review_note"] for row in rows)


def test_handoff_readback_preserves_worksheet_followup_and_traceability_payloads() -> None:
    payload = _load()
    handoff = payload["handoff_readback"]
    worksheet_readback = handoff["evidence_worksheet_handoff_readback"]
    traceability = handoff["route_construct_traceability_readback"]

    assert handoff["handoff_status"] == "manual_review_required"
    assert handoff["manual_review_required"] is True
    assert handoff["required_review_items"]
    assert worksheet_readback["readback_batch"] == handoff_adapter.WORKSHEET_HANDOFF_READBACK_BATCH
    assert worksheet_readback["summary"]["total_evidence_rows"] == payload["summary"]["worksheet_evidence_row_count"]
    assert worksheet_readback["summary"]["followup_queue_count"] == payload["summary"]["worksheet_followup_queue_count"]
    assert traceability["readback_context"]["mount_batch"] == handoff_adapter.ROUTE_CONSTRUCT_TRACEABILITY_MOUNT_BATCH
    assert traceability["summary"]["trace_row_count"] == payload["summary"]["traceability_row_count"]
    assert any(
        item["evidence_id"] == "r131-evidence-target-identity-placeholder"
        for item in handoff["evidence_traceability_items"]
    )
    assert any(
        item["component_id"] == "r131-component-albumin-like-cds-source-placeholder"
        for item in handoff["component_traceability_items"]
    )


def test_empty_or_malformed_seed_payload_renders_safe_read_only_state(tmp_path: Path) -> None:
    seed_dir = tmp_path / "seed"
    seed_dir.mkdir()
    (seed_dir / "route_contexts.json").write_text(
        json.dumps({"schema_version": "test", "batch": "test", "records": [{"record_type": "RouteContext"}]}),
        encoding="utf-8",
    )
    (seed_dir / "component_records.json").write_text(
        json.dumps({"schema_version": "test", "batch": "test", "records": []}),
        encoding="utf-8",
    )
    (seed_dir / "evidence_records.json").write_text(
        json.dumps({"schema_version": "test", "batch": "test", "records": ["bad-row"]}),
        encoding="utf-8",
    )

    payload = workflow.build_rice_albumin_seed_review_workflow(seed_dir)

    assert payload["workflow_status"] == workflow.SEED_REVIEW_WORKFLOW_STATUS_EMPTY
    assert payload["read_only"] is True
    assert payload["manual_review_required"] is True
    assert payload["seed_intake"]["summary"]["total_records"] == 0
    assert payload["seed_intake"]["summary"]["rejected_row_count"] == 2
    assert payload["evidence_worksheet"]["evidence_review_section"]["rows"] == []
    assert payload["evidence_worksheet"]["component_slot_linkage_section"]["rows"] == []
    assert payload["evidence_worksheet"]["manual_review_section"]["rows"]
    assert payload["handoff_readback"]["manual_review_required"] is True
    assert all(item["severity"] == "review_required" for item in payload["handoff_readback"]["required_review_items"])


def test_r133_output_avoids_forbidden_positive_or_downstream_claim_wording() -> None:
    payload = _load()
    _copy_scan_value(payload)

    source_text = Path("services/rice_albumin_seed_review_workflow.py").read_text(encoding="utf-8").casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text

    assert "documentation-only" in str(payload).casefold()
    assert "manual_review" in str(payload).casefold()
