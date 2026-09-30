# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path

from services import plant_seed_review_workflow as dispatcher
from services import rice_albumin_seed_review_workflow as rice_workflow


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
    _term("ready ", "for execution"),
)


ALLOWED_BLOCKED_LABELS = {
    "experimental_validation",
    "experimental_validation_claim",
    "yield_prediction",
    "optimization_output",
    "optimized_sequence",
    "pathway_optimization",
    "codon_optimization_output",
    "expression_success_claim",
}


ROOT = Path(__file__).resolve().parents[1]


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


def _malformed_seed_dir(tmp_path: Path) -> Path:
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
    return seed_dir


def test_r138_generic_dispatcher_preserves_rice_albumin_wrapper_output() -> None:
    generic = dispatcher.build_plant_seed_review_workflow(dataset_key="rice_albumin")
    wrapper = rice_workflow.build_rice_albumin_seed_review_workflow()

    assert generic == wrapper
    assert generic["workflow_status"] == rice_workflow.SEED_REVIEW_WORKFLOW_STATUS_READY
    assert generic["summary"]["seed_record_count"] == 12
    assert generic["summary"]["worksheet_evidence_row_count"] == 2
    assert generic["summary"]["worksheet_component_slot_row_count"] == 7
    assert generic["manual_review_required"] is True
    assert generic["read_only"] is True


def test_r138_unknown_dataset_key_fails_closed_without_loading_seed_records() -> None:
    payload = dispatcher.build_plant_seed_review_workflow(dataset_key="artemisia_annua")

    assert payload["workflow_schema_version"] == dispatcher.PLANT_SEED_REVIEW_DISPATCHER_SCHEMA_VERSION
    assert payload["workflow_status"] == dispatcher.PLANT_SEED_REVIEW_STATUS_UNSUPPORTED_DATASET
    assert payload["read_only"] is True
    assert payload["plant_scope_only"] is True
    assert payload["manual_review_required"] is True
    assert payload["seed_intake"]["records"] == []
    assert payload["seed_intake"]["rejected_rows"] == []
    assert payload["evidence_worksheet"]["evidence_review_section"]["rows"] == []
    assert payload["route_construct_traceability"]["traceability_section"]["rows"] == []
    assert payload["handoff_readback"]["manual_review_required"] is True
    assert "Unsupported plant seed review dataset key" in payload["warnings"][0]


def test_r138_empty_or_malformed_dataset_payload_uses_safe_read_only_outputs(tmp_path: Path) -> None:
    payload = dispatcher.build_plant_seed_review_workflow(
        dataset_key="rice_albumin",
        seed_path=_malformed_seed_dir(tmp_path),
    )
    mount = dispatcher.build_plant_seed_review_visible_mount(payload, dataset_key="rice_albumin")

    assert payload["workflow_status"] == rice_workflow.SEED_REVIEW_WORKFLOW_STATUS_EMPTY
    assert payload["read_only"] is True
    assert payload["manual_review_required"] is True
    assert payload["seed_intake"]["summary"]["total_records"] == 0
    assert payload["seed_intake"]["summary"]["rejected_row_count"] == 2
    assert payload["evidence_worksheet"]["evidence_review_section"]["rows"] == []
    assert payload["evidence_worksheet"]["component_slot_linkage_section"]["rows"] == []
    assert payload["evidence_worksheet"]["manual_review_section"]["rows"]
    assert payload["route_construct_traceability"]["manual_review_required"] is True
    assert mount["visible_mount_status"] == rice_workflow.SEED_REVIEW_WORKFLOW_STATUS_EMPTY
    assert len(mount["rejected_seed_rows"]) == 2
    assert "read-only" in mount["empty_state"]


def test_r138_review_provenance_and_manual_review_fields_survive_dispatcher() -> None:
    payload = dispatcher.build_plant_seed_review_workflow(dataset_key="rice_albumin")
    seed_records = payload["seed_intake"]["records"]
    evidence_rows = payload["evidence_worksheet"]["evidence_review_section"]["rows"]
    component_rows = payload["evidence_worksheet"]["component_slot_linkage_section"]["rows"]
    manual_rows = payload["evidence_worksheet"]["manual_review_section"]["rows"]

    assert {record["review_status"] for record in seed_records} == {"needs_manual_review"}
    assert all(record["needs_manual_review"] is True for record in seed_records)
    assert any(record["provenance_status"] == "missing" for record in seed_records)
    assert any(record["gap_fields"] for record in seed_records)
    assert any(row["source_or_provenance_placeholder"] == "source/provenance placeholder missing" for row in evidence_rows)
    assert any(row["review_status"] == "needs_manual_review" for row in component_rows)
    assert any("provenance_status:missing" in row["gap_reason"] for row in manual_rows)
    assert all(row["manual_review_note"] for row in manual_rows)


def test_r138_traceability_worksheet_and_handoff_outputs_survive_dispatcher() -> None:
    payload = dispatcher.build_plant_seed_review_workflow(dataset_key="rice_albumin")
    worksheet = payload["evidence_worksheet"]
    followup_view = payload["followup_queue_view"]
    traceability = payload["route_construct_traceability"]
    handoff = payload["handoff_readback"]

    assert worksheet["summary"]["evidence_row_count"] == payload["summary"]["worksheet_evidence_row_count"]
    assert followup_view["total_count"] == payload["summary"]["worksheet_followup_queue_count"]
    assert "missing_provenance" in followup_view["followup_type_options"]
    assert traceability["summary"]["trace_row_count"] == payload["summary"]["traceability_row_count"]
    assert any(
        row["linked_evidence_id"] == "r131-evidence-target-identity-placeholder"
        and row["route_or_context_id"] == "plant_protein_expression_evidence_first_route_template"
        for row in traceability["traceability_section"]["rows"]
    )
    assert handoff["handoff_status"] == "manual_review_required"
    assert handoff["evidence_worksheet_handoff_readback"]["summary"]["followup_queue_count"] == (
        payload["summary"]["worksheet_followup_queue_count"]
    )
    assert handoff["route_construct_traceability_readback"]["summary"]["trace_row_count"] == (
        payload["summary"]["traceability_row_count"]
    )


def test_r138_dispatcher_and_thin_wrapper_avoid_forbidden_positive_or_downstream_copy() -> None:
    payload = dispatcher.build_plant_seed_review_workflow(dataset_key="rice_albumin")
    unsupported = dispatcher.build_plant_seed_review_workflow(dataset_key="unknown_plant_seed")
    _copy_scan_value(payload)
    _copy_scan_value(unsupported)

    source_text = "\n".join(
        [
            (ROOT / "services" / "plant_seed_review_workflow.py").read_text(encoding="utf-8"),
            (ROOT / "services" / "rice_albumin_seed_review_workflow.py").read_text(encoding="utf-8"),
        ]
    ).casefold()
    for phrase in FORBIDDEN_OUTPUT_COPY:
        assert phrase not in source_text

    wrapper_source = (ROOT / "services" / "rice_albumin_seed_review_workflow.py").read_text(encoding="utf-8")
    assert "build_plant_seed_review_workflow" in wrapper_source
    assert "load_plant_evidence_seed_intake" not in wrapper_source
    assert "build_plant_evidence_review_worksheet_payload" not in wrapper_source
    assert '"record_id":' not in wrapper_source
