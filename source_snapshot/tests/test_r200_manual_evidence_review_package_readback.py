# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from services import plant_goal_review_package_mvp as r163
from services.plant_manual_evidence_package_readback import (
    build_manual_evidence_package_readback,
)
from services.plant_manual_evidence_preflight_checker import (
    preflight_manual_evidence_batch,
    preflight_manual_evidence_record,
)
from services.plant_review_handoff_data_adapter import build_plant_review_handoff_payload
from services.plant_review_package_readback_presenter import (
    build_plant_review_package_readback_presenter,
)


ROOT = Path(__file__).resolve().parents[1]
RICE_ALBUMIN_GOAL = "Review a rice albumin-like protein expression design in a plant system."
CHANGED_FILES = [
    ROOT / "services" / "plant_manual_evidence_package_readback.py",
    ROOT / "services" / "plant_goal_review_package_mvp.py",
    ROOT / "services" / "plant_review_package_readback_presenter.py",
    ROOT / "services" / "plant_review_handoff_data_adapter.py",
    ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py",
    ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py",
    ROOT / "tests" / "test_r200_manual_evidence_review_package_readback.py",
    ROOT / "docs" / "qa" / "V2_7_R200_MANUAL_EVIDENCE_REVIEW_PACKAGE_READBACK_QA.md",
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
    _term("source ", "verification workflow"),
    _term("approval ", "workflow"),
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


def _manual_evidence_record(record_id: str, title: str, **section_overrides: Any) -> dict[str, Any]:
    record = {
        "evidence_entry_metadata": {
            "evidence_entry_id": record_id,
            "created_by_or_imported_by": "R200_CURATOR_ALIAS",
            "created_at": "R200_REVIEW_DATE_PLACEHOLDER",
            "updated_at": "R200_REVIEW_DATE_PLACEHOLDER",
            "import_batch_id": "R200_PLACEHOLDER_BATCH",
            "import_mode": "manual_template_entry",
            "notes_for_curator": "R200_PLACEHOLDER_CURATOR_NOTE",
        },
        "source_identity": {
            "source_type": "user_supplied",
            "source_title": title,
            "source_url_or_identifier": f"{record_id}_SOURCE_TRAIL_PLACEHOLDER",
            "doi": "",
            "accession": "",
            "repository_id": "",
            "citation_text": f"{record_id}_CITATION_PLACEHOLDER",
            "source_date_or_version": "R200_SOURCE_DATE_PLACEHOLDER",
            "source_quote_or_evidence_note": f"{record_id}_EVIDENCE_NOTE_PLACEHOLDER",
        },
        "evidence_scope": {
            "route_scope": "plant_protein_expression_review",
            "organism_scope": "R200_PLANT_SCOPE_PLACEHOLDER",
            "host_context": "R200_HOST_CONTEXT_PLACEHOLDER",
            "record_family": "manual_evidence",
            "component_type_or_record_family": "manual_evidence",
            "related_record_id": f"{record_id}_RELATED_PLACEHOLDER",
            "related_display_name": f"{record_id} related placeholder",
            "claim_type": "evidence_note",
            "claim_summary": f"{record_id}_NOTE_FOR_REVIEW_PLACEHOLDER",
            "evidence_quality_level": "user_note",
        },
        "provenance_and_review": {
            "demo_or_real_flag": "user_supplied_unverified",
            "provenance_status": "source_present_needs_review",
            "manual_review_status": "needs_manual_review",
            "allowed_usage_scope": "manual_review_only",
            "conflict_status": "no_known_conflict",
            "deprecated_flag": False,
            "replacement_record_id": "",
            "last_reviewed_at": "",
            "reviewer_note": f"{record_id}_REVIEW_NOTE_PLACEHOLDER",
        },
        "admission_gate_preflight": {
            "intended_usage": "manual_review_only",
            "expected_initial_gate_result": "manual_review_required",
            "blocking_reasons_expected": [
                "source_review_required",
                "manual_review_required",
            ],
            "review_required": True,
            "notes_for_gate_operator": "R200_GATE_NOTE_PLACEHOLDER",
        },
    }
    for section_name, overrides in section_overrides.items():
        record[section_name].update(overrides)
    return record


def _placeholder_preflight_batch() -> dict[str, Any]:
    records = [
        _manual_evidence_record(
            "R200_ENTRY_ALPHA",
            "R200_PLACEHOLDER_SOURCE_ALPHA",
            admission_gate_preflight={
                "intended_usage": "package_draft_support",
                "expected_initial_gate_result": "allowed_for_package_draft_support",
                "review_required": False,
            },
        ),
        _manual_evidence_record(
            "R200_ENTRY_BETA",
            "R200_PLACEHOLDER_SOURCE_BETA",
            source_identity={
                "source_url_or_identifier": "",
                "doi": "",
                "accession": "",
                "repository_id": "",
                "citation_text": "",
            },
        ),
        _manual_evidence_record(
            "R200_ENTRY_GAMMA",
            "R200_PLACEHOLDER_SOURCE_GAMMA",
            provenance_and_review={
                "demo_or_real_flag": "demo_example",
                "provenance_status": "demo_only",
                "allowed_usage_scope": "beginner_preview",
            },
        ),
    ]
    batch = preflight_manual_evidence_batch(records)
    batch["blocking_reasons"] = ["R200_BATCH_BLOCKER_PLACEHOLDER"]
    batch["warnings"] = ["R200_BATCH_WARNING_PLACEHOLDER"]
    return batch


def _package(manual_payload: Any = None) -> dict[str, Any]:
    return {
        "package_id": "R200_PACKAGE_PLACEHOLDER",
        "package_schema_version": "plant_review_package.r200.test",
        "package_type": "plant_review_package",
        "package_status": "manual_review_required",
        "manual_review_required": True,
        "route_summary": {
            "route_id": "R200_ROUTE_PLACEHOLDER",
            "route_label": "R200 plant route placeholder",
            "route_status": "manual_review_required",
            "route_template_id": "R200_TEMPLATE_PLACEHOLDER",
        },
        "design_intent_summary": {
            "target_terms": ["R200_TARGET_PLACEHOLDER"],
            "product_terms": ["R200_PRODUCT_PLACEHOLDER"],
            "host_terms": ["R200_HOST_PLACEHOLDER"],
            "context_terms": ["R200_CONTEXT_PLACEHOLDER"],
        },
        "module_card_summary": {"modules": []},
        "construct_slot_summary": {"slots": []},
        "evidence_summary": {"slots": []},
        "component_candidate_summary": {"slots": []},
        "gap_manual_review_summary": {
            "blocker_count": 0,
            "review_required_count": 1,
            "informational_count": 0,
        },
        "review_queue": [
            {
                "item_id": "R200_REVIEW_ITEM_PLACEHOLDER",
                "category": "evidence_gap",
                "severity": "review_required",
                "priority": 40,
                "reason": "R200 package readback keeps existing review item visible.",
            }
        ],
        "traceability": {
            "route_ids": ["R200_ROUTE_PLACEHOLDER"],
            "evidence_ids": ["R200_EVIDENCE_PLACEHOLDER"],
            "component_ids": ["R200_COMPONENT_PLACEHOLDER"],
            "upstream_result_versions": {"r200": "placeholder"},
            "package_builder_version": "v2.7-r200-test",
        },
        "blocked_output_boundaries": ["export_action"],
        "manual_evidence_preflight_payload": manual_payload,
    }


def _surface_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        values = [str(key) for key in value]
        for child in value.values():
            values.extend(_surface_values(child))
        return values
    if isinstance(value, list):
        values: list[str] = []
        for child in value:
            values.extend(_surface_values(child))
        return values
    return [str(value)]


def test_empty_manual_evidence_status_renders_safe_empty_package_readback() -> None:
    readback = build_manual_evidence_package_readback()
    package = r163.build_plant_goal_review_package_mvp(RICE_ALBUMIN_GOAL)
    package_readback = package["manual_evidence_review_queue_readback"]

    for payload in (readback, package_readback):
        assert payload["section_status"] == "empty_manual_evidence_queue_readback"
        assert payload["summary"]["row_count"] == 0
        assert payload["summary"]["review_needed_count"] == 0
        assert payload["summary"]["blocked_count"] == 0
        assert payload["summary"]["preview_only_count"] == 0
        assert payload["summary"]["malformed_or_empty_count"] == 0
        assert payload["empty_state"]["is_empty"] is True
        assert "preflight/readback only" in payload["boundary_note"]
        assert payload["permissions"]["imports_evidence"] is False
        assert payload["permissions"]["package_export_permission"] is False
        assert payload["permissions"]["package_draft_completion_permission"] is False


def test_populated_placeholder_queue_summary_appears_in_package_readback_payload() -> None:
    package = r163.build_plant_goal_review_package_mvp(
        RICE_ALBUMIN_GOAL,
        manual_evidence_preflight_payload=_placeholder_preflight_batch(),
    )
    readback = package["manual_evidence_review_queue_readback"]

    assert package["package_status"] == r163.PACKAGE_STATUS_READY
    assert package["intent_summary"]
    assert package["manual_review_task_summary"]["manual_provenance_queue_task_count"] == 46
    assert readback["section_status"] == "manual_evidence_queue_readback_present"
    assert readback["summary"]["row_count"] == 3
    assert readback["summary"]["review_needed_count"] == 1
    assert readback["summary"]["blocked_count"] == 1
    assert readback["summary"]["preview_only_count"] == 1
    assert readback["summary"]["malformed_or_empty_count"] == 0
    assert readback["batch_blocking_reasons"] == ["R200_BATCH_BLOCKER_PLACEHOLDER"]
    assert readback["batch_warnings"] == ["R200_BATCH_WARNING_PLACEHOLDER"]


def test_malformed_and_empty_counts_are_preserved_when_present() -> None:
    payload = build_manual_evidence_package_readback(
        [preflight_manual_evidence_record({}), None]
    )

    assert payload["summary"]["row_count"] == 2
    assert payload["summary"]["empty_count"] == 1
    assert payload["summary"]["malformed_count"] == 1
    assert payload["summary"]["malformed_or_empty_count"] == 2
    assert payload["queue_state_counts"]["empty"] == 1
    assert payload["queue_state_counts"]["malformed_blocked"] == 1


def test_r75_readback_preserves_queue_blockers_warnings_gate_and_traceability() -> None:
    presenter = build_plant_review_package_readback_presenter(
        _package(_placeholder_preflight_batch())
    )
    manual = presenter["manual_evidence_review_queue_section"]
    rows_by_id = {
        row["traceability"]["record_id"]: row
        for row in manual["rows"]
    }

    assert presenter["package_header"]["package_id"] == "R200_PACKAGE_PLACEHOLDER"
    assert presenter["review_queue_section"]["rows"][0]["item_id"] == "R200_REVIEW_ITEM_PLACEHOLDER"
    assert manual["summary"]["review_needed_count"] == 1
    assert manual["summary"]["blocked_count"] == 1
    assert manual["summary"]["preview_only_count"] == 1
    assert "missing source trail" in rows_by_id["R200_ENTRY_BETA"]["visible_blocking_reasons"]
    assert rows_by_id["R200_ENTRY_ALPHA"]["visible_warnings"]
    assert rows_by_id["R200_ENTRY_ALPHA"]["package_draft_support_preview"]["readback_only"] is True
    assert rows_by_id["R200_ENTRY_ALPHA"]["package_draft_support_preview"][
        "package_export_permission"
    ] is False
    assert rows_by_id["R200_ENTRY_ALPHA"]["package_draft_completion_permission"] is False
    assert rows_by_id["R200_ENTRY_ALPHA"]["admission_gate_alignment"]["r189_gate_used"] is True
    assert rows_by_id["R200_ENTRY_ALPHA"]["admission_gate_alignment"][
        "r189_gate_can_be_overridden"
    ] is False
    assert rows_by_id["R200_ENTRY_GAMMA"]["traceability_readback"]["record_id"] == "R200_ENTRY_GAMMA"
    assert rows_by_id["R200_ENTRY_GAMMA"]["traceability"]["route_scope"] == (
        "plant_protein_expression_review"
    )
    assert manual["permissions"]["approval_allowed"] is False
    assert manual["permissions"]["biological_decision_advice"] is False


def test_handoff_payload_carries_manual_evidence_readback_from_presenter() -> None:
    presenter = build_plant_review_package_readback_presenter(
        _package(_placeholder_preflight_batch())
    )
    handoff = build_plant_review_handoff_payload(presenter)
    manual = handoff["manual_evidence_review_queue_readback"]

    assert handoff["package_header"]["package_id"] == "R200_PACKAGE_PLACEHOLDER"
    assert handoff["required_review_items"]
    assert handoff["source_traceability"]["source_kind"] == "readback_presenter"
    assert handoff["source_traceability"]["manual_evidence_queue_row_count"] == 3
    assert manual["summary"]["row_count"] == 3
    assert manual["summary"]["review_needed_count"] == 1
    assert manual["summary"]["blocked_count"] == 1
    assert manual["summary"]["preview_only_count"] == 1
    assert manual["permissions"]["imports_evidence"] is False
    assert manual["permissions"]["package_export_permission"] is False


def test_output_and_changed_copy_keep_r200_boundaries() -> None:
    readback = build_manual_evidence_package_readback(_placeholder_preflight_batch())
    presenter = build_plant_review_package_readback_presenter(
        _package(_placeholder_preflight_batch())
    )
    handoff = build_plant_review_handoff_payload(presenter)
    combined_output = repr([readback, presenter, handoff])
    changed_text = "\n".join(
        path.read_text(encoding="utf-8") for path in CHANGED_FILES if path.exists()
    )

    for fragment in REALISTIC_IDENTIFIER_FRAGMENTS:
        assert fragment not in combined_output
        assert fragment not in changed_text
    lowered = f"{combined_output}\n{changed_text}".casefold()
    for fragment in FORBIDDEN_COPY_FRAGMENTS:
        assert fragment not in lowered
    assert _term("source_", "verified") not in combined_output
    assert _term("source_", "verified") not in changed_text
    assert "documentation-only" in changed_text
    assert "preflight/readback only" in changed_text
    assert readback["permissions"]["route_improvement_claim"] is False
    assert handoff["manual_evidence_review_queue_readback"]["permissions"][
        "downstream_use_judgment"
    ] is False
