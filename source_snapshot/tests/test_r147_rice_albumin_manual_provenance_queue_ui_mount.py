# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from services import rice_albumin_manual_provenance_verification_queue as queue
from tests.helpers.fake_streamlit import FakeStreamlit
from views.pathway_workspace_sections import plant_review_handoff_preview_section as section


ROOT = Path(__file__).resolve().parents[1]


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_COPY = (
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
)


def _queue_payload() -> dict[str, object]:
    return {
        "workflow_schema_version": queue.MANUAL_PROVENANCE_QUEUE_SCHEMA_VERSION,
        "workflow_batch": queue.MANUAL_PROVENANCE_QUEUE_BATCH,
        "workflow_status": queue.MANUAL_PROVENANCE_QUEUE_STATUS_READY,
        "read_only": True,
        "manual_review_required": True,
        "queue_boundary": (
            "Documentation-only manual provenance task. Manual review required; "
            "source/accession gaps visible."
        ),
        "source_policy": (
            "The queue performs no source lookup, external API calls, identifier filling, "
            "seed record changes, evidence acceptance, component selection, or record promotion."
        ),
        "summary": {
            "total_tasks": 46,
            "represented_record_count": 12,
            "records_requiring_manual_lookup": 12,
            "records_blocked_from_promotion": 12,
            "missing_source_id_count": 6,
            "missing_accession_count": 12,
            "ready_to_promote_count": 0,
            "task_type_counts": {
                "verify_source_id": 1,
                "verify_accession": 1,
                "confirm_source_scope": 0,
                "confirm_component_linkage": 0,
                "confirm_evidence_record": 0,
                "do_not_promote_guard": 0,
            },
        },
        "task_types": [
            "verify_source_id",
            "verify_accession",
            "confirm_source_scope",
            "confirm_component_linkage",
            "confirm_evidence_record",
            "do_not_promote_guard",
        ],
        "tasks": [
            {
                "task_id": "r146-r131-evidence-target-identity-placeholder-verify_source_id",
                "record_id": "r131-evidence-target-identity-placeholder",
                "record_type": "EvidenceRecord",
                "task_type": "verify_source_id",
                "missing_fields": ["source_id", "accession"],
                "verification_question": "Which external source identifier should a human review for this record?",
                "blocking_reason": "The record has no source identifier in the local seed payload.",
                "required_manual_action": "Manually inspect source material and record notes in a later scoped update.",
                "promotion_blocked": True,
                "do_not_promote_until_verified": True,
            },
            {
                "task_id": "r146-r131-route-plant-protein-expression-evidence-first-verify_accession",
                "record_id": "r131-route-plant-protein-expression-evidence-first",
                "record_type": "RouteRecord",
                "task_type": "verify_accession",
                "missing_fields": ["accession"],
                "verification_question": "Which accession or versioned accession should a human review for this record?",
                "blocking_reason": "The record has no accession captured in the local seed payload.",
                "required_manual_action": "Manually inspect source material before any later scoped metadata update.",
                "promotion_blocked": True,
                "do_not_promote_until_verified": True,
            },
        ],
        "warnings": [],
    }


def _rendered_text(fake_st: FakeStreamlit) -> str:
    return "\n".join(
        fake_st.caption_messages
        + fake_st.info_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + [frame.to_string(index=False) for frame in fake_st.dataframes]
        + [f"{call['label']}: {call['value']}" for call in fake_st.metric_calls]
    )


def test_r147_handoff_preview_surface_mounts_manual_provenance_queue(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)
    calls: list[str] = []

    def _render_readback() -> dict[str, object]:
        fake_st.markdown("**Rice albumin manual provenance verification**")
        return {"read_only": True}

    def _render_queue() -> dict[str, object]:
        calls.append("mounted")
        fake_st.markdown("**Rice albumin manual provenance verification queue**")
        return {"read_only": True}

    monkeypatch.setattr(section, "render_rice_albumin_manual_provenance_verification_readback", _render_readback)
    monkeypatch.setattr(section, "render_rice_albumin_manual_provenance_verification_queue", _render_queue)

    section.render_plant_review_handoff_preview_section({})
    rendered = _rendered_text(fake_st)

    assert calls == ["mounted"]
    assert "Handoff preview" in rendered
    assert "Rice albumin manual provenance verification queue" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.file_uploader_calls == []


def test_r147_queue_ui_renders_r146_summary_and_manual_task_rows(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    mount = section.render_rice_albumin_manual_provenance_verification_queue(_queue_payload())
    rendered = _rendered_text(fake_st)

    assert mount["read_only"] is True
    assert len(mount["manual_provenance_queue_tasks"]) == 2
    assert "Rice albumin manual provenance verification queue" in rendered
    assert "documentation-only" in rendered
    assert "manual review required" in rendered
    assert "source/accession gaps visible" in rendered
    assert "no automatic identifier fill" in rendered
    assert "not promoted" in rendered
    assert "Manual provenance verification queue summary" in rendered
    assert "Total tasks" in rendered
    assert "Total tasks: 46" in rendered
    assert "Represented records" in rendered
    assert "Represented records: 12" in rendered
    assert "Records requiring manual lookup" in rendered
    assert "Records blocked from promotion" in rendered
    assert "Missing source ID tasks" in rendered
    assert "Missing source ID tasks: 6" in rendered
    assert "Missing accession tasks" in rendered
    assert "ready_to_promote_count" in rendered
    assert "ready_to_promote_count: 0" in rendered
    assert "Manual verification task rows are summarized by task type first" in rendered
    assert "Manual provenance verification task type summary" in rendered
    assert "verify_source_id" in rendered
    assert "verify_accession" in rendered
    assert "Manual provenance verification tasks" in rendered
    assert fake_st.expander_calls == [
        {"label": "Show all 2 manual provenance task rows", "expanded": False}
    ]
    assert "task_id" in rendered
    assert "record_id" in rendered
    assert "record_type" in rendered
    assert "task_type" in rendered
    assert "missing_fields" in rendered
    assert "verification_question" in rendered
    assert "blocking_reason" in rendered
    assert "required_manual_action" in rendered
    assert "promotion_blocked" in rendered
    assert "do_not_promote_until_verified" in rendered
    assert "Which external source identifier should a human review" in rendered
    assert "Manually inspect source material" in rendered
    assert "True" in rendered


def test_r147_ui_consumes_r146_queue_output_without_local_task_logic(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)
    sentinel = _queue_payload()
    sentinel["tasks"][0]["task_id"] = "r147-sentinel-r146-queue-task"

    def _build_queue() -> dict[str, object]:
        return sentinel

    monkeypatch.setattr(section, "build_rice_albumin_manual_provenance_verification_queue", _build_queue)

    mount = section.render_rice_albumin_manual_provenance_verification_queue()
    rendered = _rendered_text(fake_st)
    source = (
        ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py"
    ).read_text(encoding="utf-8")

    assert mount["manual_provenance_queue_payload"] == sentinel
    assert "r147-sentinel-r146-queue-task" in rendered
    assert "build_rice_albumin_manual_provenance_verification_queue" in source
    assert "_record_task_types" not in source
    assert "TASK_TYPES" not in source
    assert "TASK_TEXT" not in source


def test_r147_empty_or_malformed_queue_payload_renders_safe_read_only_state(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    mount = section.render_rice_albumin_manual_provenance_verification_queue(
        {
            "workflow_status": "unexpected_external_status",
            "summary": "malformed",
            "tasks": "malformed",
            "warnings": ["malformed queue fixture"],
        }
    )
    rendered = _rendered_text(fake_st)

    assert mount["read_only"] is True
    assert mount["manual_provenance_queue_payload"]["workflow_status"] == queue.MANUAL_PROVENANCE_QUEUE_STATUS_FAIL_CLOSED
    assert "read-only fail-closed state" in rendered
    assert "manual provenance records are missing or malformed" in rendered.casefold()
    assert "Manual provenance verification tasks" in rendered
    assert "promotion_blocked" in rendered
    assert "do_not_promote_until_verified" in rendered
    assert "ready_to_promote_count" in rendered
    assert "ready_to_promote_count: 0" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []


def test_r147_queue_ui_does_not_fill_identifiers_or_promote_records(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)
    payload = _queue_payload()

    mount = section.render_rice_albumin_manual_provenance_verification_queue(payload)
    tasks = mount["manual_provenance_queue_tasks"]
    rendered = _rendered_text(fake_st)
    forbidden_fill_keys = {
        "source_identifier",
        "accession",
        "database_id",
        "pmid",
        "doi",
    }

    assert mount["manual_provenance_queue_payload"]["summary"]["ready_to_promote_count"] == 0
    assert all(task["promotion_blocked"] is True for task in tasks)
    assert all(task["do_not_promote_until_verified"] is True for task in tasks)
    assert all(forbidden_fill_keys.isdisjoint(task) for task in tasks)
    assert "PMID:" not in rendered
    assert "DOI:" not in rendered
    assert "Records blocked from promotion" in rendered


def test_r147_changed_ui_copy_has_no_positive_or_downstream_wording(monkeypatch) -> None:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section, "st", fake_st)

    section.render_rice_albumin_manual_provenance_verification_queue(_queue_payload())
    rendered = _rendered_text(fake_st).casefold()
    source_text = "\n".join(
        [
            (
                ROOT / "views" / "pathway_workspace_sections" / "plant_review_handoff_preview_section.py"
            ).read_text(encoding="utf-8"),
            (
                ROOT / "tests" / "test_r147_rice_albumin_manual_provenance_queue_ui_mount.py"
            ).read_text(encoding="utf-8"),
        ]
    ).casefold()

    for phrase in FORBIDDEN_COPY:
        assert phrase.casefold() not in rendered
        assert phrase.casefold() not in source_text
    assert "documentation-only" in rendered
    assert "manual review required" in rendered
    assert "not promoted" in rendered
