# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect

from services import expression_construct_workflow_router as router
from services import expression_construct_workflow_router_presenter as presenter
from tests.helpers.fake_streamlit import FakeStreamlit
import views.pathway_workspace_sections.project_review_report_section as review_report_section
from views import expression_construct_workflow_router_preview_section, tool_typography


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(review_report_section, "st", fake_st)
    return fake_st


def _presenter_payload(intent: str = "plant expression construct vector source review") -> dict[str, object]:
    routed = router.route_expression_construct_workflow(intent)
    routed["matched_intent_text"] = intent
    return presenter.build_expression_construct_workflow_router_presenter(routed)


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


def test_r344_mount_reads_project_scoped_r342_presenter_payload_without_writes(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {"id": 344, "name": "R344 route mount"}
    payload_key = review_report_section._expression_construct_workflow_router_preview_project_key(project)
    fake_st.session_state[payload_key] = _presenter_payload()
    before = dict(fake_st.session_state)

    section = review_report_section._render_expression_construct_workflow_router_preview_mount(project)
    rendered = _rendered_text(fake_st)

    assert section["status"] == "expression_construct_workflow_router_preview_section_available"
    assert section["summary"]["matched_workflow_route"] == router.PLANT_MAINLINE_ROUTE
    assert section["summary"]["manual_review_required"] == "yes"
    assert "Expression Construct Workflow Router Preview" in rendered
    assert "Expression Construct Workflow Route" in rendered
    assert "plant expression construct vector source review" in rendered
    assert "No current expression construct workflow router presenter payload is available" not in rendered
    assert fake_st.session_state == before
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []


def test_r344_mount_can_prepare_local_preview_from_project_intent_payload(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {
        "id": "r344-intent",
        "expression_construct_workflow_intent_payload": {
            "intent_text": "plant expression vector source review for target protein",
            "context": {
                "host_system": "plant",
                "target_identity": "albumin documentation target",
                "source": "manual source/provenance note",
            },
        },
    }
    before_project = dict(project)

    section = review_report_section._render_expression_construct_workflow_router_preview_mount(project)
    rendered = _rendered_text(fake_st)

    assert section["status"] == "expression_construct_workflow_router_preview_section_available"
    assert section["summary"]["matched_workflow_route"] == router.PLANT_MAINLINE_ROUTE
    assert section["route_status"]["active_mainline"] == "yes"
    assert "plant expression vector source review for target protein" in rendered
    assert "plant context review" in rendered
    assert "No current expression construct workflow router presenter payload is available" not in rendered
    assert fake_st.session_state == {}
    assert project == before_project


def test_r344_mount_safe_empty_state_is_read_only_and_does_not_write_session(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.session_state["unrelated"] = {"keep": True}
    before = dict(fake_st.session_state)

    section = review_report_section._render_expression_construct_workflow_router_preview_mount(
        {"id": "r344-empty", "name": "No route payload"}
    )
    rendered = _rendered_text(fake_st)

    assert section["status"] == "expression_construct_workflow_router_preview_section_empty"
    assert section["empty_state"]["is_empty"] is True
    assert "Invalid or empty expression construct workflow router result." in rendered
    assert "No current expression construct workflow router presenter payload is available" in rendered
    assert fake_st.session_state == before
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []


def test_r344_mount_restores_shared_streamlit_bindings(monkeypatch) -> None:
    original_section_st = expression_construct_workflow_router_preview_section.st
    original_typography_st = tool_typography.st
    _install_fake_streamlit(monkeypatch)

    review_report_section._render_expression_construct_workflow_router_preview_mount(
        {"id": "r344-state-isolation", "name": "State isolation"}
    )

    assert expression_construct_workflow_router_preview_section.st is original_section_st
    assert tool_typography.st is original_typography_st


def test_r344_project_review_report_surface_invokes_route_mount_in_plant_review_area(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)
    project = {"id": "r344-surface", "name": "R344 report surface"}
    captured: dict[str, object] = {}

    monkeypatch.setattr(review_report_section, "list_tool_artifacts", lambda project_id: [])
    monkeypatch.setattr(review_report_section, "current_step2_component_context_readback", lambda: None)
    monkeypatch.setattr(
        review_report_section,
        "_render_plant_construct_draft_preview_mount",
        lambda project: fake_st.caption("plant construct draft preview mount called"),
    )
    monkeypatch.setattr(
        review_report_section,
        "_render_plant_user_context_preview",
        lambda project: fake_st.caption("plant context preview called"),
    )

    def _route_mount(project_arg):
        captured["project"] = project_arg
        fake_st.caption("expression construct workflow router preview mount called")
        return {"status": "expression_construct_workflow_router_preview_section_available"}

    monkeypatch.setattr(
        review_report_section,
        "_render_expression_construct_workflow_router_preview_mount",
        _route_mount,
    )

    review_report_section.render_project_review_report_section(
        project=project,
        steps=[],
        linked_catalog_assets=[],
    )
    rendered = _rendered_text(fake_st)

    assert captured["project"] is project
    assert "Plant Design Review Package" in rendered
    assert "expression construct workflow router preview mount called" in rendered
    assert "plant construct draft preview mount called" in rendered
    assert "plant context preview called" in rendered
    assert rendered.index("Documentation-only plant review package skeleton/readback") < rendered.index(
        "expression construct workflow router preview mount called"
    )
    assert rendered.index("expression construct workflow router preview mount called") < rendered.index(
        "plant construct draft preview mount called"
    )


def test_r344_mount_does_not_add_persistence_export_sequence_or_write_controls() -> None:
    source = (
        inspect.getsource(review_report_section._render_expression_construct_workflow_router_preview_mount)
        + inspect.getsource(review_report_section._expression_construct_workflow_router_presenter_payload)
        + inspect.getsource(review_report_section._r342_presenter_from_router_upstream_payload)
    ).casefold()

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
        "vector_sequence",
        "construct_sequence",
        "session_state[",
    ]

    assert [call for call in forbidden_calls if call in source] == []
