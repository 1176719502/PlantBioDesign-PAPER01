from __future__ import annotations

import inspect

from tests.helpers.fake_streamlit import FakeStreamlit
import views.pathway_workspace_sections.project_review_report_section as review_report_section


def _presenter_payload() -> dict[str, object]:
    return {
        "status": "construct_draft_preview_presenter_available",
        "page_title": "Plant Construct Draft Preview",
        "subtitle": "UI-safe presenter for read-only construct draft review.",
        "draft_summary_card": {
            "draft_id": "construct-draft-r335-ui-mount",
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
                "slot_count": 2,
                "present_slot_count": 0,
                "missing_slot_count": 1,
                "needs_source_count": 1,
                "needs_confirmation_count": 1,
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
                    "source_ids": ["SRC-PROMOTER-R335"],
                    "evidence_ids": ["EVID-PROMOTER-R335"],
                    "missing_reason": "promoter source evidence not provided",
                    "manual_review_required": True,
                },
                {
                    "display_label": "Vector backbone",
                    "slot_name": "vector_backbone",
                    "role": "vector backbone slot",
                    "status": "needs_confirmation",
                    "safe_status_text": "needs confirmation; manual review required",
                    "value": "recorded vector documentation context",
                    "source_ids": ["SRC-VECTOR-R335"],
                    "evidence_ids": ["EVID-VECTOR-R335"],
                    "missing_reason": "",
                    "manual_review_required": True,
                },
            ],
            "row_count": 2,
        },
        "evidence_summary": {
            "source_ids": ["SRC-PROMOTER-R335", "SRC-VECTOR-R335"],
            "evidence_ids": ["EVID-PROMOTER-R335", "EVID-VECTOR-R335"],
            "source_count": 2,
            "evidence_count": 2,
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


def test_r335_mount_reads_project_specific_r333_payload_and_preserves_preview_fields(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {"id": 335, "name": "R335 mount project"}
    fake_st.session_state[
        review_report_section._plant_construct_draft_preview_project_key(project)
    ] = _presenter_payload()

    section = review_report_section._render_plant_construct_draft_preview_mount(project)
    rendered = _rendered_text(fake_st)
    slot_rows = section["slot_table"].to_dict("records")
    rows_by_key = {row["Slot key"]: row for row in slot_rows}

    assert section["status"] == "plant_construct_draft_preview_section_available"
    assert section["summary"]["draft_id"] == "construct-draft-r335-ui-mount"
    assert section["summary"]["draft_status"] == "needs_manual_review"
    assert section["summary"]["manual_review_required"] == "yes"
    assert rows_by_key["promoter"]["Missing reason"] == "promoter source evidence not provided"
    assert rows_by_key["promoter"]["Source IDs"] == "SRC-PROMOTER-R335"
    assert rows_by_key["promoter"]["Evidence IDs"] == "EVID-PROMOTER-R335"
    assert rows_by_key["vector_backbone"]["Source IDs"] == "SRC-VECTOR-R335"
    assert rows_by_key["vector_backbone"]["Evidence IDs"] == "EVID-VECTOR-R335"
    assert "Plant Construct Draft Preview" in rendered
    assert "Read-only construct draft preview mount" in rendered
    assert "Promoter: source evidence requires manual review." in rendered


def test_r335_mount_can_read_shared_r333_payload_without_project_payload(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.session_state[review_report_section.PLANT_CONSTRUCT_DRAFT_PREVIEW_SESSION_KEY] = _presenter_payload()

    section = review_report_section._render_plant_construct_draft_preview_mount({"id": 336})

    assert section["status"] == "plant_construct_draft_preview_section_available"
    assert section["summary"]["draft_id"] == "construct-draft-r335-ui-mount"
    assert "No current construct draft presenter payload is available" not in _rendered_text(fake_st)


def test_r335_mount_safe_empty_state_is_read_only_and_does_not_write_session(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.session_state["unrelated"] = {"keep": True}
    before = dict(fake_st.session_state)

    section = review_report_section._render_plant_construct_draft_preview_mount({"id": 337})
    rendered = _rendered_text(fake_st)

    assert section["status"] == "plant_construct_draft_preview_section_empty"
    assert section["empty_state"]["is_empty"] is True
    assert "Invalid or empty construct draft preview payload." in rendered
    assert "No current construct draft presenter payload is available" in rendered
    assert fake_st.session_state == before
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []


def test_r335_project_review_report_surface_invokes_mount_in_plant_review_area(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {"id": 338, "name": "R335 report mount"}
    captured: dict[str, object] = {}

    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    monkeypatch.setattr(review_report_section, "current_step2_component_context_readback", lambda: None)
    monkeypatch.setattr(
        review_report_section,
        "_render_plant_user_context_preview",
        lambda project: fake_st.caption("plant context preview called"),
    )

    def _mount(project_arg):
        captured["project"] = project_arg
        fake_st.caption("plant construct draft preview mount called")
        return {"status": "plant_construct_draft_preview_section_available"}

    monkeypatch.setattr(review_report_section, "_render_plant_construct_draft_preview_mount", _mount)

    review_report_section.render_project_review_report_section(
        project=project,
        steps=[],
        linked_catalog_assets=[],
    )

    rendered = _rendered_text(fake_st)

    assert captured["project"] is project
    assert "Plant Design Review Package" in rendered
    assert "plant construct draft preview mount called" in rendered
    assert "plant context preview called" in rendered


def test_r335_mount_does_not_add_persistence_export_or_sequence_generation_paths() -> None:
    source = inspect.getsource(review_report_section._render_plant_construct_draft_preview_mount)

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
