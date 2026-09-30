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


def _construct_draft() -> dict[str, object]:
    return {
        "construct_draft_status": "construct_draft_created",
        "draft_id": "construct-draft-r336-review-chain",
        "source_route_id": "r336-route-candidate",
        "route_label": "case-supported option",
        "plant_host_or_context": "rice seed documentation context",
        "goal_type": "plant_molecular_farming_protein_expression",
        "route_type": "case-supported option",
        "draft_status": "incomplete",
        "manual_review_required": True,
        "required_slots_explicitly_confirmed": False,
        "missing_required_slots": ["promoter"],
        "safety_boundary": "Construct draft readback is a read-only summary for source and manual review.",
        "construct_slots": [
            {
                "slot_name": "promoter",
                "role": "regulatory slot",
                "required": True,
                "status": "needs_source",
                "value": "",
                "source_ids": ["SRC-PROMOTER-R336"],
                "evidence_ids": ["EVID-PROMOTER-R336"],
                "missing_reason": "promoter source evidence not provided",
                "manual_review_required": True,
            },
            {
                "slot_name": "vector_backbone",
                "role": "vector backbone slot",
                "required": True,
                "status": "needs_confirmation",
                "value": "recorded vector documentation context",
                "source_ids": ["SRC-VECTOR-R336"],
                "evidence_ids": ["EVID-VECTOR-R336"],
                "missing_reason": "",
                "manual_review_required": True,
            },
        ],
    }


def _candidate_route_result() -> dict[str, object]:
    return {
        "plant_goal": "Plant protein expression review",
        "matched_goal_type_id": "plant_molecular_farming_protein_expression",
        "route_generation_status": "allowed",
        "manual_review_required": True,
        "candidate_route": {
            "route_id": "r336-route-candidate",
            "route_framing": "case-supported option",
            "supporting_source_ids": ["SRC-CASE-R336"],
            "required_component_slots": [
                "plant_context",
                "target_product",
                "promoter",
                "terminator",
                "marker",
                "vector",
            ],
            "slot_source_ids": {
                "plant_species": ["SRC-PLANT-R336"],
                "cds": ["SRC-CDS-R336"],
                "promoter": ["SRC-PROMOTER-R336"],
                "vector": ["SRC-VECTOR-R336"],
            },
            "missing_fields": ["terminator_need"],
            "manual_review_required": True,
        },
    }


def test_r336_project_review_mount_populates_r333_payload_from_upstream_construct_draft(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {
        "id": 336,
        "name": "R336 payload bridge",
        "plant_construct_draft": _construct_draft(),
    }
    before_project = dict(project)

    section = review_report_section._render_plant_construct_draft_preview_mount(project)
    rendered = _rendered_text(fake_st)
    project_payload_key = review_report_section._plant_construct_draft_preview_project_key(project)
    stored_payload = fake_st.session_state[project_payload_key]
    slot_rows = section["slot_table"].to_dict("records")
    rows_by_key = {row["Slot key"]: row for row in slot_rows}

    assert section["status"] == "plant_construct_draft_preview_section_available"
    assert stored_payload["status"] == "construct_draft_preview_presenter_available"
    assert section["summary"]["draft_id"] == "construct-draft-r336-review-chain"
    assert section["summary"]["draft_status"] == "incomplete"
    assert section["summary"]["manual_review_required"] == "yes"
    assert rows_by_key["promoter"]["Missing reason"] == "promoter source evidence not provided"
    assert rows_by_key["promoter"]["Source IDs"] == "SRC-PROMOTER-R336"
    assert rows_by_key["promoter"]["Evidence IDs"] == "EVID-PROMOTER-R336"
    assert rows_by_key["vector_backbone"]["Source IDs"] == "SRC-VECTOR-R336"
    assert rows_by_key["vector_backbone"]["Evidence IDs"] == "EVID-VECTOR-R336"
    assert "Promoter: missing source." in rendered
    assert "One or more draft slots have missing source records." in rendered
    assert "No current construct draft presenter payload is available" not in rendered
    assert project == before_project


def test_r336_bridge_accepts_session_upstream_candidate_route_and_remains_project_scoped(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {"id": "r336-session", "name": "R336 session route"}
    upstream_key = review_report_section._plant_construct_draft_preview_upstream_project_key(project)
    fake_st.session_state[upstream_key] = _candidate_route_result()

    section = review_report_section._render_plant_construct_draft_preview_mount(project)
    project_payload_key = review_report_section._plant_construct_draft_preview_project_key(project)
    stored_payload = fake_st.session_state[project_payload_key]
    slot_rows = section["slot_table"].to_dict("records")
    rows_by_key = {row["Slot key"]: row for row in slot_rows}

    assert section["status"] == "plant_construct_draft_preview_section_available"
    assert stored_payload["draft_summary_card"]["draft_id"] == "construct-draft-r336-route-candidate"
    assert rows_by_key["promoter"]["Evidence IDs"] == "SRC-PROMOTER-R336"
    assert rows_by_key["cds_payload_gene_or_enzyme"]["Evidence IDs"] == "SRC-CDS-R336"
    assert rows_by_key["terminator"]["Missing reason"] == "upstream task has no source for this slot"
    assert set(fake_st.session_state) == {upstream_key, project_payload_key}


def test_r336_no_upstream_payload_keeps_r334_safe_empty_state_without_session_write(monkeypatch) -> None:
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


def test_r336_bridge_ignores_blocked_or_empty_upstream_payload(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {
        "id": "r336-empty",
        "plant_construct_draft": {
            "construct_draft_status": "route_generation_blocked",
            "reason": "route not allowed / route generation blocked",
            "construct_slots": [],
            "manual_review_required": True,
        },
    }

    section = review_report_section._render_plant_construct_draft_preview_mount(project)

    assert section["status"] == "plant_construct_draft_preview_section_empty"
    assert review_report_section._plant_construct_draft_preview_project_key(project) not in fake_st.session_state


def test_r336_bridge_does_not_add_persistence_export_sequence_or_write_controls() -> None:
    bridge_source = inspect.getsource(
        review_report_section._populate_plant_construct_draft_preview_payload_bridge
    ) + inspect.getsource(review_report_section._r333_presenter_from_upstream_payload)

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

    assert [call for call in forbidden_calls if call in bridge_source.casefold()] == []
