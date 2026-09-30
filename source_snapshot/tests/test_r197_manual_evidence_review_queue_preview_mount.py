# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.helpers.fake_streamlit import FakeStreamlit
from views.pathway_workspace_sections import plant_review_workflow_section as section


ROOT = Path(__file__).resolve().parents[1]
CHANGED_FILES = [
    ROOT / "views" / "pathway_workspace_sections" / "plant_review_workflow_section.py",
    ROOT / "services" / "plant_goal_review_package_mvp.py",
    ROOT / "tests" / "test_r165_plant_goal_review_package_visible_mvp.py",
    ROOT / "tests" / "test_r197_manual_evidence_review_queue_preview_mount.py",
    ROOT / "docs" / "qa" / "V2_7_R197_MANUAL_EVIDENCE_REVIEW_QUEUE_PREVIEW_MOUNT_QA.md",
]


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_CLAIM_FRAGMENTS = (
    _term("source ", "verification"),
    _term("approval ", "workflow"),
    _term("package ", "export allowed"),
    _term("export ", "permission: yes"),
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("experiment", "-ready"),
    _term("wet-lab ", "ready"),
    _term("yield ", "prediction"),
    _term("ready ", "for execution"),
)

REALISTIC_IDENTIFIER_FRAGMENTS = (
    _term("PM", "ID"),
    _term("NC", "BI"),
    _term("Gen", "Bank"),
    _term("Add", "gene"),
    _term("XP", "_"),
    _term("NP", "_"),
    _term("NM", "_"),
)


def _preflight_record(
    *,
    record_id: str,
    display_name: str,
    queue_status: str,
    manual_review_state: str,
    source_status: str,
    source_type: str = "user_supplied",
    package_status: str = "blocked",
    package_supported: bool = False,
    blocking_reasons: list[str] | None = None,
    warnings: list[str] | None = None,
    beginner_preview_allowed: bool = False,
) -> dict[str, Any]:
    return {
        "preflight_status": queue_status,
        "manual_review_state": manual_review_state,
        "package_draft_support_preview": {
            "status": package_status,
            "supported": package_supported,
            "blocking_reasons": blocking_reasons or [],
        },
        "missing_required_fields": [],
        "blocking_reasons": blocking_reasons or [],
        "warnings": warnings or [],
        "source_status": {
            "status": source_status,
            "source_fields_present": ["citation_text"] if source_status != "missing_source" else [],
            "source_type": source_type,
            "input_provenance_status": source_status,
        },
        "placeholder_status": {
            "status": "placeholder_or_demo_present",
            "has_placeholder_values": True,
            "placeholder_fields": ["source_identity.source_title"],
        },
        "admission_gate_alignment": {
            "r189_gate_used": True,
            "r189_gate_can_be_overridden": False,
            "package_draft_support_status": "manual_review_only",
            "package_draft_support_allowed": False,
            "beginner_preview_status": "allowed_for_beginner_preview"
            if beginner_preview_allowed
            else "manual_review_only",
            "beginner_preview_allowed": beginner_preview_allowed,
        },
        "traceability": {
            "record_id": record_id,
            "record_type": "manual_evidence_entry",
            "display_name": display_name,
            "route_scope": "plant_protein_expression_review",
            "source_fields_present": ["citation_text"] if source_status != "missing_source" else [],
            "input_shape": "manual_evidence_template",
        },
    }


def _preflight_batch() -> dict[str, Any]:
    records = [
        _preflight_record(
            record_id="R197_ENTRY_ALPHA",
            display_name="PLACEHOLDER_SOURCE_ALPHA",
            queue_status="manual_review_ready",
            manual_review_state="manual_review_required",
            source_status="source_present_needs_manual_review",
            blocking_reasons=[],
            warnings=["CURATOR_WARNING_PLACEHOLDER"],
        ),
        _preflight_record(
            record_id="R197_ENTRY_BETA",
            display_name="PLACEHOLDER_SOURCE_BETA",
            queue_status="blocked",
            manual_review_state="cannot_review_until_source_is_recorded",
            source_status="missing_source",
            blocking_reasons=["missing source trail"],
        ),
        _preflight_record(
            record_id="R197_ENTRY_GAMMA",
            display_name="PLACEHOLDER_SOURCE_GAMMA",
            queue_status="blocked",
            manual_review_state="manual_review_required",
            source_status="source_present_needs_manual_review",
            blocking_reasons=["beginner preview only; package draft support remains blocked"],
            beginner_preview_allowed=True,
        ),
    ]
    return {
        "preflight_status": "blocked",
        "records": records,
        "summary": {
            "total_records": 3,
            "ready_records": 0,
            "manual_review_records": 2,
            "blocked_records": 1,
            "package_draft_supported_records": 0,
            "beginner_preview_allowed_records": 1,
            "malformed_records": 0,
        },
        "blocking_reasons": ["BATCH_BLOCKER_PLACEHOLDER"],
        "warnings": ["BATCH_WARNING_PLACEHOLDER"],
    }


def _workflow() -> dict[str, Any]:
    return {
        "workflow_status": "manual_review_required",
        "manual_review_required": True,
        "warnings": ["workflow warning placeholder"],
        "adapter_input": {
            "evidence_records": [{"id": "EV_PLACEHOLDER", "paper_title": "Placeholder evidence"}],
            "component_records": [{"component_id": "COMP_PLACEHOLDER", "component_name": "Placeholder component"}],
        },
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
            "missing_information_items": [
                {
                    "item_id": "GAP_PLACEHOLDER",
                    "category": "evidence_gap",
                    "slot_id": "manual_evidence_slot",
                    "reason": "Placeholder source review remains open.",
                }
            ],
        },
        "traceability": {
            "upstream_statuses": {
                "extractor": "ready_for_adapter",
                "adapter": "manual_review_required",
                "chain": "manual_review_required",
                "handoff": "manual_review_required",
            }
        },
    }


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


def test_manual_evidence_review_queue_empty_state_is_safe(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    payload = section.render_manual_evidence_review_queue_preview(project={}, workflow={})
    rendered = _rendered_text(fake_st)

    assert payload["summary"]["row_count"] == 0
    assert "Manual Evidence Review Queue" in rendered
    assert "preflight/readback only" in rendered
    assert "No manual evidence preflight payload is available yet" in rendered
    assert fake_st.dataframes == []
    assert fake_st.download_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_placeholder_manual_evidence_renders_read_only_queue_rows(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    first = section.render_manual_evidence_review_queue_preview(
        project={"manual_evidence_preflight_payload": _preflight_batch()},
        workflow={},
    )
    first_render = _rendered_text(fake_st)
    frame = _manual_queue_frame(fake_st)
    rows = frame.to_dict("records")

    fake_st_second = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st_second)
    second = section.render_manual_evidence_review_queue_preview(
        project={"manual_evidence_preflight_payload": _preflight_batch()},
        workflow={},
    )

    assert first == second
    assert first["summary"]["row_count"] == 3
    assert len(rows) == 3
    assert rows[0]["Queue state"] == "review needed"
    assert rows[0]["Evidence label"] == "PLACEHOLDER_SOURCE_ALPHA"
    assert rows[0]["Manual review state"] == "manual review required"
    assert "source_present_needs_manual_review" in rows[0]["Source readback/status"]
    assert "supported: no" in rows[0]["Package support readback"]
    assert "package output action: no" in rows[0]["Package support readback"]
    assert "CURATOR_WARNING_PLACEHOLDER" in rows[0]["Warnings"]
    assert "missing source trail" in rows[1]["Blocking reasons"]
    assert rows[1]["Queue state"] == "blocked"
    assert "missing_source" in rows[1]["Source readback/status"]
    assert rows[2]["Queue state"] == "preview only"
    assert "beginner preview only" in rows[2]["Primary reason"]
    assert "R197_ENTRY_GAMMA" in rows[2]["Traceability readback"]
    assert "BATCH_BLOCKER_PLACEHOLDER" in first_render
    assert "BATCH_WARNING_PLACEHOLDER" in first_render
    assert "bds-manual-evidence-review-queue" in first_render
    assert fake_st.download_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_plant_review_section_mounts_manual_queue_and_keeps_existing_sections(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    fake_st.checkbox_values[section.SIMPLE_PLANT_WIZARD_ADVANCED_MODE_KEY] = True
    monkeypatch.setattr(section, "st", fake_st)
    monkeypatch.setattr(section, "render_plant_goal_review_package_draft_visible_mvp", lambda: {})
    monkeypatch.setattr(section, "render_plant_review_handoff_preview_section", lambda _payload: None)
    monkeypatch.setattr(section, "render_rice_albumin_seed_review_visible_mount", lambda: None)

    workflow = section.render_plant_review_workflow_section(
        project={"id": "R197_PROJECT", "manual_evidence_preflight_payload": _preflight_batch()},
        steps=[],
        expression_links=[],
        test_records=[],
        review_signals=[],
        build_workflow=lambda _state: _workflow(),
    )
    rendered = _rendered_text(fake_st)

    assert workflow["advanced_details_visible"] is True
    assert "Plant Review Workflow" in rendered
    assert "Route summary" in rendered
    assert "Construct slot summary" in rendered
    assert "Evidence summary" in rendered
    assert "Component candidate summary" in rendered
    assert "Gap / manual review queue" in rendered
    assert "Manual Evidence Review Queue" in rendered
    assert "Traceability" in rendered
    assert any(call["label"] == "Full Manual Evidence Review Queue table" for call in fake_st.expander_calls)


def test_r197_changed_files_keep_copy_and_identifier_boundaries() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in CHANGED_FILES if path.exists())
    lowered = combined.casefold()

    for fragment in FORBIDDEN_CLAIM_FRAGMENTS:
        assert fragment not in lowered
    for fragment in REALISTIC_IDENTIFIER_FRAGMENTS:
        assert fragment not in combined
    assert "source_" + "verified" not in combined
    assert "documentation-only" in combined
    assert "read-only" in combined
    assert "Manual Evidence Review Queue" in combined
