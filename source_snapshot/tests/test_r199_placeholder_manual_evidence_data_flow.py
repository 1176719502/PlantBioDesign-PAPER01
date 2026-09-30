# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from services.plant_manual_evidence_preflight_checker import (
    preflight_manual_evidence_batch,
)
from services.plant_manual_evidence_review_queue_presenter import (
    present_manual_evidence_review_queue,
)
from tests.helpers.fake_streamlit import FakeStreamlit
from views.pathway_workspace_sections import plant_review_workflow_section as section


ROOT = Path(__file__).resolve().parents[1]
CHANGED_FILES = [
    ROOT / "tests" / "test_r199_placeholder_manual_evidence_data_flow.py",
    ROOT / "docs" / "qa" / "V2_7_R199_PLACEHOLDER_MANUAL_EVIDENCE_DATA_FLOW_QA.md",
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


def _manual_evidence_record(record_id: str, title: str, **section_overrides: Any) -> dict[str, Any]:
    record = {
        "evidence_entry_metadata": {
            "evidence_entry_id": record_id,
            "created_by_or_imported_by": "R199_CURATOR_ALIAS",
            "created_at": "R199_REVIEW_DATE_PLACEHOLDER",
            "updated_at": "R199_REVIEW_DATE_PLACEHOLDER",
            "import_batch_id": "R199_PLACEHOLDER_BATCH",
            "import_mode": "manual_template_entry",
            "notes_for_curator": "R199_PLACEHOLDER_CURATOR_NOTE",
        },
        "source_identity": {
            "source_type": "user_supplied",
            "source_title": title,
            "source_url_or_identifier": f"{record_id}_PLACEHOLDER_SOURCE_TRAIL",
            "doi": "",
            "accession": "",
            "repository_id": "",
            "citation_text": f"{record_id}_PLACEHOLDER_CITATION_TEXT",
            "source_date_or_version": "R199_SOURCE_DATE_PLACEHOLDER",
            "source_quote_or_evidence_note": f"{record_id}_PLACEHOLDER_EVIDENCE_NOTE",
        },
        "evidence_scope": {
            "route_scope": "plant_protein_expression_review",
            "organism_scope": "R199_PLANT_SCOPE_PLACEHOLDER",
            "host_context": "R199_HOST_CONTEXT_PLACEHOLDER",
            "record_family": "manual_evidence",
            "component_type_or_record_family": "manual_evidence",
            "related_record_id": f"{record_id}_RELATED_PLACEHOLDER",
            "related_display_name": f"{record_id} related placeholder",
            "claim_type": "evidence_note",
            "claim_summary": f"{record_id}_PLACEHOLDER_NOTE_FOR_REVIEW",
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
            "reviewer_note": f"{record_id}_PLACEHOLDER_REVIEW_NOTE",
        },
        "admission_gate_preflight": {
            "intended_usage": "manual_review_only",
            "expected_initial_gate_result": "manual_review_required",
            "blocking_reasons_expected": [
                "source_review_required",
                "manual_review_required",
            ],
            "review_required": True,
            "notes_for_gate_operator": "R199_PLACEHOLDER_GATE_NOTE",
        },
    }

    for section_name, overrides in section_overrides.items():
        record[section_name].update(overrides)
    return record


def _placeholder_records() -> list[dict[str, Any]]:
    return [
        _manual_evidence_record(
            "R199_ENTRY_ALPHA",
            "R199_PLACEHOLDER_SOURCE_ALPHA",
            admission_gate_preflight={
                "intended_usage": "package_draft_support",
                "expected_initial_gate_result": "allowed_for_package_draft_support",
                "review_required": False,
            },
        ),
        _manual_evidence_record(
            "R199_ENTRY_BETA",
            "R199_PLACEHOLDER_SOURCE_BETA",
            source_identity={
                "source_url_or_identifier": "",
                "doi": "",
                "accession": "",
                "repository_id": "",
                "citation_text": "",
            },
        ),
        _manual_evidence_record(
            "R199_ENTRY_GAMMA",
            "R199_PLACEHOLDER_SOURCE_GAMMA",
            provenance_and_review={
                "demo_or_real_flag": "demo_example",
                "provenance_status": "demo_only",
                "allowed_usage_scope": "beginner_preview",
            },
        ),
        _manual_evidence_record(
            "R199_ENTRY_DELTA",
            "R199_EXAMPLE_SOURCE_DELTA",
            provenance_and_review={
                "demo_or_real_flag": "demo_example",
                "provenance_status": "demo_only",
                "allowed_usage_scope": "demo_only",
            },
        ),
        _manual_evidence_record(
            "R199_ENTRY_EPSILON",
            "R199_PLACEHOLDER_SOURCE_EPSILON",
            provenance_and_review={
                "provenance_status": "deprecated_source",
                "conflict_status": "conflicting_sources",
                "deprecated_flag": True,
            },
        ),
    ]


def _preflight_batch() -> dict[str, Any]:
    return preflight_manual_evidence_batch(_placeholder_records())


def _queue_payload() -> dict[str, Any]:
    return present_manual_evidence_review_queue(_preflight_batch())


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


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.subheaders
        + fake_st.info_messages
        + fake_st.caption_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [frame.to_string(index=False) for frame in fake_st.dataframes]
    )


def _manual_queue_frame(fake_st: FakeStreamlit):
    expected = [
        "Queue state",
        "Evidence label",
        "Manual review state",
        "Source readback/status",
        "Package support readback",
        "Primary reason",
        "Blocking reasons",
        "Warnings",
        "Traceability readback",
    ]
    for frame in fake_st.dataframes:
        if list(frame.columns) == expected:
            return frame
    raise AssertionError("Manual Evidence Review Queue dataframe was not rendered")


def _minimal_workflow() -> dict[str, Any]:
    return {
        "workflow_status": "manual_review_required",
        "manual_review_required": True,
        "warnings": [],
        "adapter_input": {"evidence_records": [], "component_records": []},
        "chain_result": {
            "plant_review_package": {
                "package_status": "manual_review_required",
                "route_summary": {
                    "route_id": "plant_protein_expression_review",
                    "route_label": "Plant protein expression review",
                    "route_type": "plant_expression_vector",
                },
                "construct_slot_summary": {"slots": []},
            },
            "route_draft": {"draft_status": "manual_review_required"},
        },
        "handoff_preview_payload": {
            "handoff_status": "manual_review_required",
            "missing_information_items": [],
        },
        "traceability": {"upstream_statuses": {}},
    }


def test_placeholder_records_flow_from_preflight_to_populated_queue_rows() -> None:
    preflight = _preflight_batch()
    queue = present_manual_evidence_review_queue(preflight)
    rows_by_id = {
        row["traceability"]["record_id"]: row
        for row in queue["rows"]
    }

    assert preflight["summary"] == {
        "total_records": 5,
        "ready_records": 0,
        "manual_review_records": 4,
        "blocked_records": 2,
        "package_draft_supported_records": 0,
        "beginner_preview_allowed_records": 1,
        "malformed_records": 0,
    }
    assert queue["summary"]["row_count"] == 5
    assert queue["summary"]["queue_state_counts"] == {
        "blocked": 3,
        "empty": 0,
        "malformed_blocked": 0,
        "preview_only": 1,
        "review_needed": 1,
    }

    assert rows_by_id["R199_ENTRY_ALPHA"]["queue_state"] == "review_needed"
    assert rows_by_id["R199_ENTRY_ALPHA"]["source_status"]["status"] == (
        "source_present_needs_manual_review"
    )
    assert rows_by_id["R199_ENTRY_ALPHA"]["manual_review_state"] == "manual_review_required"
    assert rows_by_id["R199_ENTRY_ALPHA"]["package_draft_support_preview"]["supported"] is False

    assert rows_by_id["R199_ENTRY_BETA"]["queue_state"] == "blocked"
    assert rows_by_id["R199_ENTRY_BETA"]["source_status"]["status"] == "missing_source"
    assert "missing source trail" in rows_by_id["R199_ENTRY_BETA"]["visible_blocking_reasons"]

    assert rows_by_id["R199_ENTRY_GAMMA"]["queue_state"] == "preview_only"
    assert rows_by_id["R199_ENTRY_GAMMA"]["admission_gate_alignment"]["beginner_preview_allowed"] is True
    assert rows_by_id["R199_ENTRY_GAMMA"]["package_draft_support_preview"]["supported"] is False

    assert rows_by_id["R199_ENTRY_DELTA"]["queue_state"] == "blocked"
    assert rows_by_id["R199_ENTRY_DELTA"]["placeholder_demo_example_status"][
        "has_placeholder_values"
    ] is True
    assert rows_by_id["R199_ENTRY_DELTA"]["package_support_readback"]["supported"] is False

    assert rows_by_id["R199_ENTRY_EPSILON"]["queue_state"] == "blocked"
    assert rows_by_id["R199_ENTRY_EPSILON"]["review_priority"] == "blocked_high_attention"
    assert "conflict_status is conflicting_sources" in rows_by_id["R199_ENTRY_EPSILON"][
        "visible_blocking_reasons"
    ]
    assert "record or source is deprecated" in rows_by_id["R199_ENTRY_EPSILON"][
        "visible_blocking_reasons"
    ]


def test_queue_rows_preserve_r193_readback_fields_without_new_permissions() -> None:
    preflight = _preflight_batch()
    queue = present_manual_evidence_review_queue(preflight)

    for preflight_record, row in zip(preflight["records"], queue["rows"]):
        assert row["manual_review_state"] == preflight_record["manual_review_state"]
        assert row["source_status"] == preflight_record["source_status"]
        assert row["package_draft_support_preview"] == preflight_record[
            "package_draft_support_preview"
        ]
        assert row["blocking_reasons"] == preflight_record["blocking_reasons"]
        assert row["warnings"] == preflight_record["warnings"]
        assert row["traceability"] == preflight_record["traceability"]
        assert row["admission_gate_alignment"] == preflight_record["admission_gate_alignment"]
        assert row["display_readback_only"] is True
        assert row["imports_evidence"] is False
        assert row["approval_allowed"] is False
        assert row["package_export_permission"] is False
        assert row["package_draft_completion_permission"] is False
        assert row["biological_recommendation"] is False
        assert row["experiment_validation_claim"] is False
        assert row["optimization_claim"] is False
        assert row["wet_lab_readiness_judgment"] is False

    alpha = queue["rows"][0]
    beta = queue["rows"][1]
    assert (
        "admission_gate_preflight values are advisory and cannot override R189"
        in alpha["visible_warnings"]
    )
    assert "missing source trail" in beta["visible_blocking_reasons"]
    assert "R199_ENTRY_ALPHA" in alpha["traceability_readback"]["record_id"]


def test_plant_review_mount_renders_populated_placeholder_queue_rows(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    queue = section.render_manual_evidence_review_queue_preview(
        project={"manual_evidence_preflight_payload": _preflight_batch()},
        workflow={},
    )
    rendered = _rendered_text(fake_st)
    frame = _manual_queue_frame(fake_st)
    rows = frame.to_dict("records")

    assert queue["summary"]["row_count"] == 5
    assert len(rows) == 5
    assert rows[0]["Queue state"] == "review needed"
    assert rows[0]["Evidence label"] == "R199_PLACEHOLDER_SOURCE_ALPHA"
    assert "source_present_needs_manual_review" in rows[0]["Source readback/status"]
    assert "package output action: no" in rows[0]["Package support readback"]
    assert "admission_gate_preflight values are advisory" in rows[0]["Warnings"]
    assert rows[1]["Queue state"] == "blocked"
    assert "missing source trail" in rows[1]["Blocking reasons"]
    assert rows[2]["Queue state"] == "preview only"
    assert rows[3]["Queue state"] == "blocked"
    assert "placeholder/example/demo values require manual review" in rows[3][
        "Blocking reasons"
    ]
    assert "R199_ENTRY_EPSILON" in rows[4]["Traceability readback"]
    assert "Manual Evidence Review Queue" in rendered
    assert "preflight/readback only" in rendered
    assert fake_st.download_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_full_plant_review_section_mount_consumes_populated_queue_payload(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.checkbox_values[section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(section, "st", fake_st)
    monkeypatch.setattr(section, "render_plant_goal_review_package_draft_visible_mvp", lambda: {})
    monkeypatch.setattr(section, "render_plant_review_handoff_preview_section", lambda _payload: None)
    monkeypatch.setattr(section, "render_rice_albumin_seed_review_visible_mount", lambda: None)

    workflow = section.render_plant_review_workflow_section(
        project={
            "id": "R199_PROJECT_PLACEHOLDER",
            "manual_evidence_preflight_payload": _preflight_batch(),
        },
        steps=[],
        expression_links=[],
        test_records=[],
        review_signals=[],
        build_workflow=lambda _state: _minimal_workflow(),
    )
    rendered = _rendered_text(fake_st)
    frame = _manual_queue_frame(fake_st)

    assert workflow["advanced_details_visible"] is True
    assert "Plant Review Workflow" in rendered
    assert "Manual Evidence Review Queue" in rendered
    assert len(frame.to_dict("records")) == 5
    assert any(call["label"] == "Full Manual Evidence Review Queue table" for call in fake_st.expander_calls)


def test_output_is_deterministic_plain_and_boundary_safe() -> None:
    first_preflight = _preflight_batch()
    second_preflight = _preflight_batch()
    first_queue = present_manual_evidence_review_queue(first_preflight)
    second_queue = present_manual_evidence_review_queue(second_preflight)

    assert first_preflight == second_preflight
    assert first_queue == second_queue
    _assert_plain(first_preflight)
    _assert_plain(first_queue)

    combined_surface = repr([first_preflight, first_queue])
    for fragment in REALISTIC_IDENTIFIER_FRAGMENTS:
        assert fragment not in combined_surface
    lowered = combined_surface.casefold()
    for fragment in FORBIDDEN_COPY_FRAGMENTS:
        assert fragment not in lowered
    assert _term("source_", "verified") not in _surface_values(first_preflight)
    assert _term("source_", "verified") not in _surface_values(first_queue)
    assert first_queue["automatic_import_allowed"] is False
    assert first_queue["automatic_approval_allowed"] is False
    assert first_queue["automatic_package_export_allowed"] is False


def test_r199_changed_files_keep_copy_and_identifier_boundaries() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in CHANGED_FILES if path.exists())
    lowered = combined.casefold()

    for fragment in FORBIDDEN_COPY_FRAGMENTS:
        assert fragment not in lowered
    for fragment in REALISTIC_IDENTIFIER_FRAGMENTS:
        assert fragment not in combined
    assert _term("source_", "verified") not in combined
    assert "documentation-only" in combined
    assert "read-only" in combined
    assert "Manual Evidence Review Queue" in combined
