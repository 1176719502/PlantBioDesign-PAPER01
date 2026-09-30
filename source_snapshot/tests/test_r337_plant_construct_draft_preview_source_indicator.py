# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect

from tests.helpers.fake_streamlit import FakeStreamlit
import views.pathway_workspace_sections.project_review_report_section as review_report_section


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    return fake_st


def _rendered_text(fake_st: FakeStreamlit) -> str:
    dataframe_text = "\n".join(
        frame.to_string(index=False) if hasattr(frame, "to_string") else str(frame)
        for frame in fake_st.dataframes
    )
    return "\n".join(
        fake_st.caption_messages
        + fake_st.info_messages
        + [call["label"] for call in fake_st.expander_calls]
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + dataframe_text.splitlines()
    )


def _presenter_payload() -> dict[str, object]:
    return {
        "status": "construct_draft_preview_presenter_available",
        "page_title": "Plant Construct Draft Preview",
        "subtitle": "UI-safe presenter for read-only construct draft review.",
        "draft_summary_card": {
            "draft_id": "construct-draft-r337-source-indicator",
            "draft_status": "needs_manual_review",
            "manual_review_required": True,
            "safety_boundary": (
                "Read-only construct draft preview for source and manual review. It preserves "
                "draft slots, source identifiers, evidence identifiers, missing reasons, review "
                "counts, and warnings without creating final construct content or downstream-use "
                "judgments."
            ),
            "summary_lines": ["Manual review required."],
            "review_counts": {
                "slot_count": 1,
                "present_slot_count": 0,
                "missing_slot_count": 1,
                "needs_source_count": 1,
                "needs_confirmation_count": 0,
                "warning_count": 1,
                "review_item_count": 1,
            },
        },
        "status_badges": [
            {"label": "Preview status", "value": "construct_draft_preview_presenter_available", "tone": "neutral"},
            {"label": "Draft status", "value": "needs_manual_review", "tone": "neutral"},
            {"label": "Manual review", "value": "yes", "tone": "attention"},
        ],
        "slot_table": {
            "columns": [
                "display_label",
                "slot_name",
                "role",
                "status",
                "safe_status_text",
                "value",
                "source_ids",
                "evidence_ids",
                "missing_reason",
                "manual_review_required",
            ],
            "rows": [
                {
                    "display_label": "Promoter",
                    "slot_name": "promoter",
                    "role": "regulatory slot",
                    "status": "needs_source",
                    "safe_status_text": "missing source; manual review required",
                    "value": "",
                    "source_ids": ["SRC-PROMOTER-R337"],
                    "evidence_ids": ["EVID-PROMOTER-R337"],
                    "missing_reason": "promoter source evidence not provided",
                    "manual_review_required": True,
                }
            ],
            "row_count": 1,
        },
        "evidence_summary": {
            "source_ids": ["SRC-PROMOTER-R337"],
            "evidence_ids": ["EVID-PROMOTER-R337"],
            "source_count": 1,
            "evidence_count": 1,
            "note": "Identifiers are displayed as supplied; no evidence is inferred.",
        },
        "missing_fields_section": {
            "rows": [
                {
                    "display_label": "Promoter",
                    "slot_name": "promoter",
                    "status": "needs_source",
                    "missing_reason": "promoter source evidence not provided",
                    "manual_review_required": True,
                }
            ],
            "manual_review_required": True,
        },
        "review_items_section": {
            "items": ["Promoter: source evidence requires manual review."],
            "review_item_count": 1,
            "manual_review_required": True,
        },
        "warnings_section": {
            "warnings": ["Construct draft remains a documentation-only review preview."],
            "warning_count": 1,
        },
        "empty_state": {"is_empty": False, "reason": "", "manual_review_required": True},
    }


def _construct_draft() -> dict[str, object]:
    return {
        "construct_draft_status": "construct_draft_created",
        "draft_id": "construct-draft-r337-upstream",
        "route_label": "case-supported option",
        "plant_host_or_context": "plant documentation context",
        "goal_type": "plant_molecular_farming_protein_expression",
        "route_type": "case-supported option",
        "draft_status": "incomplete",
        "manual_review_required": True,
        "construct_slots": [
            {
                "slot_name": "promoter",
                "role": "regulatory slot",
                "required": True,
                "status": "needs_source",
                "value": "",
                "source_ids": ["SRC-PROMOTER-R337"],
                "evidence_ids": ["EVID-PROMOTER-R337"],
                "missing_reason": "promoter source evidence not provided",
                "manual_review_required": True,
            }
        ],
    }


def test_r337_source_indicator_appears_when_project_presenter_payload_exists(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {"id": "r337-presenter", "name": "R337 presenter"}
    fake_st.session_state[
        review_report_section._plant_construct_draft_preview_project_key(project)
    ] = _presenter_payload()

    section = review_report_section._render_plant_construct_draft_preview_mount(project)
    rendered = _rendered_text(fake_st)

    assert section["status"] == "plant_construct_draft_preview_section_available"
    assert "Preview source: R333 presenter payload" in rendered
    assert "Draft ID: construct-draft-r337-source-indicator" in rendered
    assert "Draft status: needs_manual_review" in rendered
    assert "Manual review required: yes" in rendered
    assert "Upstream bridge status: project-scoped R333 presenter payload available" in rendered


def test_r337_source_indicator_uses_safe_fallback_when_source_type_unknown(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {"id": "r337-unknown", "name": "R337 unknown source"}
    payload = _presenter_payload()
    payload["source_type"] = "external_runtime_shape_without_local_mapping"
    fake_st.session_state[
        review_report_section._plant_construct_draft_preview_project_key(project)
    ] = payload

    section = review_report_section._render_plant_construct_draft_preview_mount(project)
    rendered = _rendered_text(fake_st)

    assert section["status"] == "plant_construct_draft_preview_section_available"
    assert "Preview source: normalized in-memory construct draft preview" in rendered
    assert "source type not recorded" in rendered


def test_r337_empty_state_remains_when_no_payload_exists(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    before = dict(fake_st.session_state)

    section = review_report_section._render_plant_construct_draft_preview_mount({"id": "r337-empty"})
    rendered = _rendered_text(fake_st)

    assert section["status"] == "plant_construct_draft_preview_section_empty"
    assert "No current construct draft presenter payload is available" in rendered
    assert "Preview source:" not in rendered
    assert fake_st.session_state == before


def test_r337_manual_review_required_is_displayed_safely_for_upstream_construct_draft(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {
        "id": "r337-upstream-draft",
        "name": "R337 upstream construct draft",
        "plant_construct_draft": _construct_draft(),
    }

    section = review_report_section._render_plant_construct_draft_preview_mount(project)
    rendered = _rendered_text(fake_st)

    assert section["status"] == "plant_construct_draft_preview_section_available"
    assert "Preview source: construct draft payload" in rendered
    assert "Draft ID: construct-draft-r337-upstream" in rendered
    assert "Draft status: incomplete" in rendered
    assert "Manual review required: yes" in rendered
    assert "Upstream bridge status: normalized from in-memory upstream payload" in rendered


def test_r337_source_indicator_does_not_introduce_write_controls() -> None:
    source = (
        inspect.getsource(review_report_section._plant_construct_draft_preview_source_indicator_model)
        + inspect.getsource(review_report_section._render_plant_construct_draft_preview_source_indicator)
        + inspect.getsource(review_report_section._render_plant_construct_draft_preview_mount)
    )
    forbidden_calls = [
        "download_button",
        "form_submit_button",
        "st.button",
        "repo.",
        "create_",
        "update_",
        "delete_",
        "fasta",
        "genbank",
        "codon",
    ]

    assert [call for call in forbidden_calls if call in source.casefold()] == []
