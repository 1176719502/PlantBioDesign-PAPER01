# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.session_keys import SK
from services import expression_construct_presenter as construct_presenter
from services import expression_construct_repository as construct_repo
from services import project_review_report_service as report_service
from views import ExpressionConstructs
from views.pathway_workspace_sections import project_review_report_section
from views.wizard_steps import step6_export


def test_wizard_save_success_copy_and_navigation_label_are_discoverable() -> None:
    source = open(step6_export.__file__, encoding="utf-8").read()

    assert "Save to Expression Construct" in source
    assert "Open Expression Constructs to review saved cassette documentation." in source
    assert "Open Expression Constructs" in source
    assert f'st.session_state[SK.SELECTED_PAGE] = "Expression Constructs"' in source


def test_expression_constructs_workflow_copy_and_actionable_empty_states() -> None:
    assert construct_presenter.WORKFLOW_COPY == (
        "This page manages construct/plasmid documentation records made of expression cassettes, cassette parts, "
        "linked genes, pathway links, and source-record references."
    )

    view_model = construct_presenter.build_expression_construct_presenter("")
    empty_states = view_model["empty_states"]

    assert "Create a construct draft here or save a Wizard cassette into a construct." in empty_states["constructs"]
    assert "Add cassette rows manually or save from Expression Wizard." in empty_states["cassettes"]
    assert "Add cassette part rows manually or save from Expression Wizard." in empty_states["parts"]
    assert construct_presenter.PROMOTER_SOURCE_LINK_EMPTY_COPY == (
        "Manual promoter rows can be documented without Component Library promoter asset references."
    )


def test_expression_constructs_page_source_keeps_important_labels() -> None:
    source = open(ExpressionConstructs.__file__, encoding="utf-8").read()

    assert "Create construct draft" in source
    assert "Current Construct Preview" in source
    assert "Review gaps" in source
    assert "WORKFLOW_COPY" in source
    assert "PROMOTER_SOURCE_LINK_EMPTY_COPY" in source
    assert construct_presenter.PROMOTER_SOURCE_LINK_EMPTY_COPY == (
        "Manual promoter rows can be documented without Component Library promoter asset references."
    )


def test_project_review_report_construct_section_copy_exists(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "product_workflow_polish_report.db"
    monkeypatch.setattr(construct_repo, "DB_PATH", str(db_path))

    report = report_service.build_project_review_report({"id": 26022, "name": "R22 report copy"})
    section = report["expression_construct_documentation"]

    assert report_service.EXPRESSION_CONSTRUCT_SECTION_COPY == (
        "Expression Construct Documentation summarizes saved construct records and source/provenance context."
    )
    assert report_service.EXPRESSION_CONSTRUCT_SECTION_COPY in section["boundary_notes"]
    assert report_service.EXPRESSION_CONSTRUCT_SECTION_COPY in report["markdown"]

    ui_source = open(project_review_report_section.__file__, encoding="utf-8").read()
    assert "EXPRESSION_CONSTRUCT_SECTION_COPY" in ui_source
    assert "Expression construct documentation" in ui_source


def test_product_workflow_polish_copy_avoids_unsafe_claims() -> None:
    combined = "\n".join(
        [
            construct_presenter.WORKFLOW_COPY,
            construct_presenter.NO_SOURCE_RECORD_LABEL,
            construct_presenter.BOUNDARY_COPY,
            *construct_presenter.build_expression_construct_presenter("")["empty_states"].values(),
            report_service.EXPRESSION_CONSTRUCT_SECTION_COPY,
            "\n".join(report_service._EXPRESSION_CONSTRUCT_BOUNDARY_NOTES),
            "Open Expression Constructs to review saved cassette documentation.",
            "This page manages construct/plasmid documentation records made of expression cassettes, cassette parts, linked genes, pathway links, and source-record references.",
            "Manual promoter rows can be documented without Component Library promoter asset references.",
            "Expression Construct Documentation summarizes saved construct records and source/provenance context.",
        ]
    ).lower()
    allowed_negative_context = {
        "does not recommend",
        "review recommended",
        "manual review recommended",
        "recommended action",
        "not recommended for experimental use",
        "not recommended",
        "validation status",
        "validation issues",
        "validation has not been run",
        "validation is running",
        "validation failed or is unavailable",
        "validation result is stale",
        "validation complete",
        "validation completed",
        "final validation",
        "current validation",
        "validation state",
        "validation_state",
    }
    forbidden = [
        "best promoter",
        "scoring",
        "ranking",
        "optimization",
        "optimized",
        "validated",
        "host compatibility",
        "ready for synthesis",
        "ready for wet lab",
        "transformation protocol",
        "experimentally confirmed",
        "expression prediction",
        "yield improvement",
    ]

    for allowed in allowed_negative_context:
        combined = combined.replace(allowed, "")

    assert [phrase for phrase in forbidden if phrase in combined] == []


def test_wizard_construct_success_button_sets_expression_construct_page(monkeypatch) -> None:
    class _FakeState:
        gene_name = "crtI"
        elements = {}
        frame = {}
        validation_results = []
        primers = []
        optimized_seq = "ATGAAATTTTAA"
        original_seq = "ATGAAATTTTAA"
        host = "E.coli"

    class _FakeForm:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _FakeSt:
        def __init__(self):
            self.session_state = {}
            self.captions: list[str] = []
            self.success_messages: list[str] = []
            self.markdown_messages: list[str] = []
            self.button_calls: list[str] = []
            self.rerun_count = 0

        def form(self, *args, **kwargs):
            return _FakeForm()

        def caption(self, body, **kwargs):
            self.captions.append(str(body))

        def radio(self, *args, **kwargs):
            return "New construct draft"

        def selectbox(self, label, options, **kwargs):
            return list(options)[0]

        def text_input(self, label, value="", **kwargs):
            return value

        def form_submit_button(self, label, **kwargs):
            return True

        def success(self, body, **kwargs):
            self.success_messages.append(str(body))

        def markdown(self, body, **kwargs):
            self.markdown_messages.append(str(body))

        def info(self, body, **kwargs):
            self.captions.append(str(body))

        def error(self, body, **kwargs):
            raise AssertionError(body)

        def button(self, label, **kwargs):
            self.button_calls.append(str(label))
            return label == "Open Expression Constructs"

        def rerun(self):
            self.rerun_count += 1

    fake_st = _FakeSt()

    class _Result:
        construct = {"construct_label": "Wizard construct", "construct_id": "construct-1"}
        cassette = {"cassette_label": "Wizard cassette", "cassette_id": "cassette-1"}
        cassette_parts = [{"part_id": "part-1"}]
        gene_link = {"gene_label": "crtI"}
        pathway_link_deferred = False
        pathway_link_note = ""

    monkeypatch.setattr(step6_export, "st", fake_st)
    monkeypatch.setattr(
        "services.expression_construct_repository.list_construct_profiles",
        lambda: [],
    )
    monkeypatch.setattr(
        "services.expression_wizard_construct_bridge.save_wizard_draft_to_construct",
        lambda *args, **kwargs: _Result(),
    )
    monkeypatch.setattr(
        "services.pathway_wizard_context.get_pathway_wizard_context",
        lambda: {},
    )

    step6_export._render_save_to_construct_bridge(_FakeState())

    assert "Cassette documentation saved to the local construct workspace." in fake_st.success_messages
    assert "Open Expression Constructs to review saved cassette documentation." in fake_st.captions
    assert "Open Expression Constructs" in fake_st.button_calls
    assert fake_st.session_state[SK.SELECTED_PAGE] == "Expression Constructs"
    assert fake_st.rerun_count == 1
