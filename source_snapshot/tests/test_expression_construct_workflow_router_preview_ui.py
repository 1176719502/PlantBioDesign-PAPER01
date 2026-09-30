# -*- coding: utf-8 -*-
from __future__ import annotations

import inspect
from pathlib import Path

from services import expression_construct_workflow_router as router
from services import expression_construct_workflow_router_presenter as presenter
from tests.helpers.fake_streamlit import FakeStreamlit
import views.expression_construct_workflow_router_preview_section as section_view
import views.tool_typography as tool_typography


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_WORDING = (
    _term("successful ", "import"),
    _term("project ", "imported"),
    _term("ready for ", "execution"),
    _term("experiment", "-ready"),
    _term("production", "-ready"),
    _term("validated ", "construct"),
    _term("optimized ", "pathway"),
    _term("yield ", "prediction"),
    _term("build", "-ready"),
    _term("component ", "recommendation"),
    _term("protocol ", "generation"),
    _term("biological ", "feasibility"),
    _term("experimental ", "validation"),
    _term("wet-lab", "-ready"),
)


def _payload(intent: str) -> dict[str, object]:
    routed = router.route_expression_construct_workflow(intent)
    routed["matched_intent_text"] = intent
    return presenter.build_expression_construct_workflow_router_presenter(routed)


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(section_view, "st", fake_st)
    monkeypatch.setattr(tool_typography, "st", fake_st)
    return fake_st


def _rendered_text(fake_st: FakeStreamlit) -> str:
    dataframe_text = "\n".join(frame.to_string(index=False) for frame in fake_st.dataframes)
    return "\n".join(
        fake_st.titles
        + fake_st.subheaders
        + fake_st.caption_messages
        + fake_st.info_messages
        + fake_st.warning_messages
        + fake_st.error_messages
        + fake_st.success_messages
        + fake_st.write_messages
        + [str(call["body"]) for call in fake_st.markdown_calls]
        + dataframe_text.splitlines()
    )


def test_ui_section_consumes_r342_presenter_payload_and_preserves_route_summary() -> None:
    section = section_view.build_expression_construct_workflow_router_preview_section(
        _payload("expression construct vector source review for target protein")
    )

    assert section["status"] == section_view.SECTION_STATUS_AVAILABLE
    assert section["title"] == "Expression Construct Workflow Route"
    assert section["subtitle"] == "UI-safe readback for documentation-only expression construct route review."
    assert section["read_only"] is True
    assert section["summary"]["matched_workflow_route"] == router.ACTIVE_MAINLINE_ROUTE
    assert section["summary"]["route_status_label"] == "Active expression construct review mainline"
    assert section["summary"]["manual_review_required"] == "yes"
    assert section["route_status"]["active_mainline"] == "yes"
    assert section["route_status"]["future_candidate"] == "no"
    assert section["route_status"]["fallback"] == "no"
    assert section["matched_intent_text"] == "expression construct vector source review for target protein"


def test_review_stages_required_slots_missing_slots_and_next_action_are_visible() -> None:
    section = section_view.build_expression_construct_workflow_router_preview_section(
        _payload("plant expression vector review")
    )

    assert "intent review" in section["review_stages"]["Review stage"].tolist()
    assert "plant context review" in section["review_stages"]["Review stage"].tolist()
    assert "target_identity" in section["required_information_slots"]["Required information slot"].tolist()
    assert "host_system" in section["required_information_slots"]["Required information slot"].tolist()
    assert "target_identity" in section["missing_or_unknown_slots"]["Missing or unknown slot"].tolist()
    assert "source_or_provenance" in section["missing_or_unknown_slots"]["Missing or unknown slot"].tolist()
    assert section["safe_next_review_action"]
    assert "documentation-only route readback" in section["boundary_notes"]["Boundary note"].tolist()


def test_future_route_candidate_and_fallback_messages_render_when_present(monkeypatch) -> None:
    future_fake = _install_fake_streamlit(monkeypatch)
    future_section = section_view.render_expression_construct_workflow_router_preview_section(
        _payload("metabolic pathway product biosynthesis review")
    )
    future_rendered = _rendered_text(future_fake)

    assert future_section["route_status"]["future_candidate"] == "yes"
    assert "Future route candidate for manual triage" in future_rendered
    assert "future route review" in future_rendered

    fallback_fake = _install_fake_streamlit(monkeypatch)
    fallback_section = section_view.render_expression_construct_workflow_router_preview_section(_payload("help"))
    fallback_rendered = _rendered_text(fallback_fake)

    assert fallback_section["route_status"]["fallback"] == "yes"
    assert "Fallback clarification route" in fallback_rendered
    assert "Router result used the fallback clarification route." in fallback_rendered


def test_invalid_or_empty_payload_returns_safe_empty_state_without_crashing(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)

    invalid_section = section_view.build_expression_construct_workflow_router_preview_section({"unexpected": "shape"})
    rendered_section = section_view.render_expression_construct_workflow_router_preview_section(None)
    rendered = _rendered_text(fake_st)

    assert invalid_section["status"] == section_view.SECTION_STATUS_EMPTY
    assert rendered_section["status"] == section_view.SECTION_STATUS_EMPTY
    assert rendered_section["empty_state"] == {
        "is_empty": True,
        "message": "Invalid or empty expression construct workflow router result.",
        "manual_review_required": True,
    }
    assert rendered_section["review_stages"].empty
    assert rendered_section["required_information_slots"].empty
    assert "Invalid or empty expression construct workflow router result." in rendered
    assert "No suggested review stages supplied." in rendered
    assert "No required information slots supplied." in rendered


def test_rendered_read_only_ui_contains_expected_sections_without_write_controls(monkeypatch) -> None:
    fake_st = _install_fake_streamlit(monkeypatch)

    section_view.render_expression_construct_workflow_router_preview_section(
        _payload("expression construct vector source review for target protein")
    )
    rendered = _rendered_text(fake_st)

    assert "Expression Construct Workflow Route" in rendered
    assert "documentation-only expression construct route review" in rendered
    assert "Route status" in rendered
    assert "Matched intent" in rendered
    assert "Suggested review stages" in rendered
    assert "Required information slots" in rendered
    assert "Missing or unknown slots" in rendered
    assert "Safe next review action" in rendered
    assert "Documentation-only boundary notes" in rendered
    assert "Warnings" in rendered
    assert fake_st.button_calls == []
    assert fake_st.download_button_calls == []
    assert fake_st.form_submit_button_calls == []
    assert fake_st.text_input_calls == []
    assert fake_st.text_area_calls == []


def test_ui_copy_avoids_unsafe_claims() -> None:
    section = section_view.build_expression_construct_workflow_router_preview_section(
        _payload("expression construct vector source review for target protein")
    )
    service_text = (
        Path(__file__).resolve().parents[1]
        / "views"
        / "expression_construct_workflow_router_preview_section.py"
    ).read_text(encoding="utf-8")
    output_text = str(section)

    for text in [output_text, service_text]:
        lowered = text.casefold()
        assert [phrase for phrase in FORBIDDEN_WORDING if phrase in lowered] == []


def test_ui_section_does_not_add_write_export_or_sequence_generation_paths() -> None:
    source = inspect.getsource(section_view).casefold()
    forbidden_calls = [
        "download_button",
        "form_submit_button",
        "st.button",
        "text_input",
        "text_area",
        "session_state",
        "sqlite",
        "export_package",
        "fasta",
        "genbank",
        "codon",
        "vector_sequence",
        "construct_sequence",
    ]

    assert [call for call in forbidden_calls if call in source] == []
