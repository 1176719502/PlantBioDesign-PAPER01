# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_manual_evidence_input_adapter import (
    build_manual_evidence_input_adapter_payload,
    manual_evidence_queue_payload_from_project_input,
)
from services.plant_manual_evidence_package_readback import (
    build_manual_evidence_package_readback,
)
from services.plant_review_handoff_data_adapter import build_plant_review_handoff_payload
from services.plant_review_package_readback_presenter import (
    build_plant_review_package_readback_presenter,
)
from views.pathway_workspace_sections import plant_review_workflow_section as section


ROOT = Path(__file__).resolve().parents[1]
CHANGED_FILES = [
    ROOT / "services" / "plant_manual_evidence_input_adapter.py",
    ROOT / "services" / "plant_manual_evidence_package_readback.py",
    ROOT / "services" / "plant_review_package_readback_presenter.py",
    ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py",
    ROOT / "tests" / "test_r202_manual_evidence_input_adapter.py",
    ROOT / "docs" / "qa" / "V2_7_R202_MANUAL_EVIDENCE_INPUT_ADAPTER_QA.md",
]


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY_FRAGMENTS = (
    _term("successful ", "import"),
    _term("project ", "imported"),
    _term("ready ", "for execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("yield ", "prediction"),
    _term("wet-lab ", "ready"),
)

REALISTIC_IDENTIFIER_FRAGMENTS = (
    _term("1", "0."),
    _term("PM", "ID"),
    _term("NC", "BI"),
    _term("Gen", "Bank"),
    _term("Add", "gene"),
    _term("XP", "_"),
    _term("NP", "_"),
    _term("NM", "_"),
)


def _project_payload(records: list[Any] | None = None, **extra: Any) -> dict[str, Any]:
    payload = {
        "project_id": "R202_PROJECT_PLACEHOLDER",
        "workflow_id": "R202_WORKFLOW_PLACEHOLDER",
        "manual_evidence_records": records if records is not None else [_manual_record()],
    }
    payload.update(extra)
    return payload


def _manual_record(record_id: str = "R202_ENTRY_ALPHA", **overrides: Any) -> dict[str, Any]:
    record = {
        "record_id": record_id,
        "evidence_label": f"{record_id}_CURATOR_LABEL",
        "source_reference": f"{record_id}_CURATOR_SOURCE_TRAIL",
        "citation_text": f"{record_id}_CURATOR_CITATION",
        "route_scope": "plant_protein_expression_review",
        "claim_type": "evidence_note",
        "manual_review_status": "needs_manual_review",
        "allowed_usage_scope": "manual_review_only",
        "conflict_status": "no_known_conflict",
        "review_notes": f"{record_id}_REVIEW_NOTE",
        "manual_evidence": True,
    }
    record.update(overrides)
    return record


def _package(manual_payload: Any = None, **extra: Any) -> dict[str, Any]:
    package = {
        "package_id": "R202_PACKAGE_PLACEHOLDER",
        "package_schema_version": "plant_review_package.r202.test",
        "package_type": "plant_review_package",
        "package_status": "manual_review_required",
        "manual_review_required": True,
        "route_summary": {
            "route_id": "R202_ROUTE_PLACEHOLDER",
            "route_label": "R202 plant route placeholder",
            "route_status": "manual_review_required",
        },
        "design_intent_summary": {
            "target_terms": ["R202_TARGET_PLACEHOLDER"],
            "product_terms": ["R202_PRODUCT_PLACEHOLDER"],
            "host_terms": ["R202_HOST_PLACEHOLDER"],
            "context_terms": ["R202_CONTEXT_PLACEHOLDER"],
        },
        "module_card_summary": {"modules": []},
        "construct_slot_summary": {"slots": []},
        "evidence_summary": {"slots": []},
        "component_candidate_summary": {"slots": []},
        "gap_manual_review_summary": {"review_required_count": 1},
        "review_queue": [
            {
                "item_id": "R202_REVIEW_ITEM_PLACEHOLDER",
                "category": "evidence_gap",
                "severity": "review_required",
                "reason": "R202 package readback keeps manual review visible.",
            }
        ],
        "traceability": {
            "route_ids": ["R202_ROUTE_PLACEHOLDER"],
            "evidence_ids": ["R202_EVIDENCE_PLACEHOLDER"],
            "component_ids": ["R202_COMPONENT_PLACEHOLDER"],
        },
        "blocked_output_boundaries": ["export_action"],
        "manual_evidence_review_queue_payload": manual_payload,
    }
    package.update(extra)
    return package


def _rows_by_id(queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row["traceability"]["record_id"]: row
        for row in queue["rows"]
    }


def _assert_plain(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            assert isinstance(key, str)
            _assert_plain(child)
        return
    if isinstance(value, list):
        for child in value:
            _assert_plain(child)
        return
    assert value is None or isinstance(value, (str, int, float, bool))


def test_project_payload_manual_evidence_records_produce_populated_review_queue_rows() -> None:
    adapted = build_manual_evidence_input_adapter_payload(
        _project_payload(
                [
                    _manual_record("R202_ENTRY_ALPHA"),
                    _manual_record("R202_ENTRY_BETA", source_reference="", citation_text=""),
                ]
            )
        )
    queue = adapted["manual_evidence_review_queue_payload"]
    rows = _rows_by_id(queue)

    assert adapted["input_summary"]["records_extracted"] == 2
    assert queue["summary"]["row_count"] == 2
    assert rows["R202_ENTRY_ALPHA"]["queue_state"] == "review_needed"
    assert rows["R202_ENTRY_ALPHA"]["evidence_label"] == "R202_ENTRY_ALPHA_CURATOR_LABEL"
    assert rows["R202_ENTRY_ALPHA"]["source_status"]["status"] == "source_present_needs_manual_review"
    assert rows["R202_ENTRY_ALPHA"]["package_draft_support_preview"]["supported"] is False
    assert rows["R202_ENTRY_BETA"]["queue_state"] == "blocked"


def test_project_payload_with_no_manual_evidence_produces_safe_empty_state() -> None:
    adapted = build_manual_evidence_input_adapter_payload(
        {"project_id": "R202_EMPTY_PROJECT", "evidence_records": [{"record_id": "NOT_MANUAL"}]}
    )
    queue = adapted["manual_evidence_review_queue_payload"]
    package_readback = build_manual_evidence_package_readback(adapted)

    assert adapted["input_summary"]["empty_input"] is True
    assert queue["summary"]["row_count"] == 0
    assert package_readback["section_status"] == "empty_manual_evidence_queue_readback"
    assert package_readback["empty_state"]["is_empty"] is True
    assert package_readback["permissions"]["imports_evidence"] is False


def test_missing_source_record_from_project_payload_produces_blocked_readback() -> None:
    adapted = build_manual_evidence_input_adapter_payload(
        _project_payload([_manual_record("R202_ENTRY_MISSING_SOURCE", source_reference="", citation_text="")])
    )
    row = adapted["manual_evidence_review_queue_payload"]["rows"][0]
    package_readback = build_manual_evidence_package_readback(adapted)

    assert row["queue_state"] == "blocked"
    assert row["source_status"]["status"] == "missing_source"
    assert "missing source trail" in row["visible_blocking_reasons"]
    assert package_readback["summary"]["blocked_count"] == 1


def test_beginner_preview_record_from_project_payload_produces_preview_only_readback() -> None:
    adapted = build_manual_evidence_input_adapter_payload(
        _project_payload(
            [
                _manual_record(
                    "R202_ENTRY_PREVIEW",
                    allowed_usage_scope="beginner_preview",
                    readback_state="preview_only",
                )
            ]
        )
    )
    row = adapted["manual_evidence_review_queue_payload"]["rows"][0]

    assert row["queue_state"] == "preview_only"
    assert row["admission_gate_alignment"]["beginner_preview_allowed"] is True
    assert row["package_draft_support_preview"]["supported"] is False
    assert "beginner preview only" in row["visible_blocking_reasons"][-1]


def test_demo_example_record_remains_blocked_for_package_support() -> None:
    adapted = build_manual_evidence_input_adapter_payload(
        _project_payload(
            [
                _manual_record(
                    "R202_ENTRY_DEMO",
                    evidence_label="R202_DEMO_LABEL",
                    demo_or_real_flag="demo_example",
                    allowed_usage_scope="demo_only",
                )
            ]
        )
    )
    row = adapted["manual_evidence_review_queue_payload"]["rows"][0]

    assert row["queue_state"] == "blocked"
    assert row["package_support_readback"]["supported"] is False
    assert row["placeholder_demo_example_status"]["has_placeholder_values"] is True
    assert "placeholder/example/demo values require manual review" in row["visible_blocking_reasons"]


def test_malformed_manual_evidence_entries_fail_closed() -> None:
    adapted = build_manual_evidence_input_adapter_payload(_project_payload(["R202_BAD_ENTRY"]))
    row = adapted["manual_evidence_review_queue_payload"]["rows"][0]

    assert adapted["input_summary"]["normalized_record_count"] == 1
    assert row["queue_state"] == "blocked"
    assert row["package_draft_support_preview"]["supported"] is False
    assert row["r193_preflight_can_override_r189"] is False
    assert row["imports_evidence"] is False


def test_traceability_from_project_payload_is_preserved() -> None:
    adapted = build_manual_evidence_input_adapter_payload(
        _project_payload([_manual_record("R202_ENTRY_TRACE")])
    )
    normalized = adapted["normalized_manual_evidence_records"][0]
    row = adapted["manual_evidence_review_queue_payload"]["rows"][0]

    assert normalized["adapter_traceability"]["project_id"] == "R202_PROJECT_PLACEHOLDER"
    assert normalized["adapter_traceability"]["workflow_id"] == "R202_WORKFLOW_PLACEHOLDER"
    assert normalized["adapter_traceability"]["adapter_source_field"] == "manual_evidence_records"
    assert row["traceability"]["record_id"] == "R202_ENTRY_TRACE"
    assert row["traceability"]["route_scope"] == "plant_protein_expression_review"


def test_r200_package_and_handoff_readback_consume_adapter_output() -> None:
    adapted = build_manual_evidence_input_adapter_payload(
        _project_payload([_manual_record("R202_ENTRY_HANDOFF")])
    )
    package_readback = build_manual_evidence_package_readback(adapted)
    presenter = build_plant_review_package_readback_presenter(_package(adapted))
    handoff = build_plant_review_handoff_payload(presenter)

    assert package_readback["summary"]["row_count"] == 1
    assert package_readback["summary"]["review_needed_count"] == 1
    assert presenter["manual_evidence_review_queue_section"]["summary"]["row_count"] == 1
    assert handoff["manual_evidence_review_queue_readback"]["summary"]["row_count"] == 1
    assert handoff["source_traceability"]["manual_evidence_queue_row_count"] == 1
    assert handoff["manual_evidence_review_queue_readback"]["permissions"][
        "package_export_permission"
    ] is False


def test_r197_project_payload_entry_consumes_manual_evidence_records() -> None:
    queue = section._find_manual_evidence_preflight_payload(
        _project_payload([_manual_record("R202_ENTRY_UI")]),
        {},
    )

    assert queue["summary"]["row_count"] == 1
    assert queue["rows"][0]["traceability"]["record_id"] == "R202_ENTRY_UI"


def test_existing_r199_r200_populated_flow_remains_unchanged() -> None:
    raw_preflight = {
        "preflight_status": "manual_review_required",
        "records": [
            {
                "preflight_status": "manual_review_ready",
                "manual_review_state": "manual_review_required",
                "package_draft_support_preview": {
                    "status": "blocked",
                    "supported": False,
                    "blocking_reasons": [],
                },
                "missing_required_fields": [],
                "blocking_reasons": [],
                "warnings": [],
                "source_status": {
                    "status": "source_present_needs_manual_review",
                    "source_fields_present": ["source_url_or_identifier"],
                    "source_type": "user_supplied",
                    "input_provenance_status": "source_present_needs_review",
                },
                "placeholder_status": {
                    "status": "no_placeholder_detected",
                    "has_placeholder_values": False,
                    "placeholder_fields": [],
                },
                "admission_gate_alignment": {
                    "r189_gate_used": True,
                    "r189_gate_can_be_overridden": False,
                    "package_draft_support_allowed": False,
                    "beginner_preview_allowed": False,
                },
                "traceability": {
                    "record_id": "R202_EXISTING_PREFLIGHT",
                    "record_type": "manual_evidence_entry",
                    "display_name": "R202 existing preflight label",
                    "route_scope": "plant_protein_expression_review",
                    "source_fields_present": ["source_url_or_identifier"],
                    "input_shape": "manual_evidence_template",
                },
            }
        ],
        "summary": {
            "total_records": 1,
            "ready_records": 0,
            "manual_review_records": 1,
            "blocked_records": 0,
            "package_draft_supported_records": 0,
            "beginner_preview_allowed_records": 0,
            "malformed_records": 0,
        },
        "blocking_reasons": [],
        "warnings": [],
    }

    direct = build_manual_evidence_package_readback(raw_preflight)
    via_presenter = build_plant_review_package_readback_presenter(
        _package(raw_preflight)
    )["manual_evidence_review_queue_section"]

    assert direct == via_presenter
    assert direct["summary"]["row_count"] == 1
    assert direct["rows"][0]["traceability"]["record_id"] == "R202_EXISTING_PREFLIGHT"


def test_output_is_deterministic_plain_and_safe_for_changed_files() -> None:
    project = {
        "project_id": "R202_PROJECT_PLACEHOLDER",
        "manual_evidence": {"records": [_manual_record("R202_ENTRY_NESTED")]},
        "evidence_records": [
            _manual_record("R202_ENTRY_EXPLICIT", record_family="manual_evidence"),
            {"record_id": "R202_ENTRY_NON_MANUAL", "record_family": "other_record"},
        ],
    }
    first = build_manual_evidence_input_adapter_payload(project)
    second = build_manual_evidence_input_adapter_payload(project)
    queue_only = manual_evidence_queue_payload_from_project_input(project)

    assert first == second
    assert queue_only == first["manual_evidence_review_queue_payload"]
    assert first["input_summary"]["records_extracted"] == 2
    _assert_plain(first)

    combined_output = repr(first)
    changed_text = "\n".join(
        path.read_text(encoding="utf-8") for path in CHANGED_FILES if path.exists()
    )
    lowered = f"{combined_output}\n{changed_text}".casefold()
    for fragment in FORBIDDEN_COPY_FRAGMENTS:
        assert fragment not in lowered
    for fragment in REALISTIC_IDENTIFIER_FRAGMENTS:
        assert fragment not in combined_output
        assert fragment not in changed_text
    assert _term("source", "_", "verified") not in combined_output
    assert _term("source", "_", "verified") not in changed_text
    assert first["permissions"]["imports_evidence"] is False
    assert first["permissions"]["database_write_allowed"] is False
