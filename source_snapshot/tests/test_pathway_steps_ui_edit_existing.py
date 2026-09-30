from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import streamlit as streamlit_module

from services import pathway_repository as repo
from services.pathway_completeness_service import (
    build_pathway_completeness,
    build_pathway_review_signals,
    summarize_review_signals,
)
from services.pathway_report_service import generate_pathway_markdown_report
from tests.helpers.fake_streamlit import FakeStreamlit
import views.PathwayWorkspace as pathway_workspace


ARTEMISININ_PROJECT_NAME = "Artemisinin Demo Project"
ARTEMISININ_TARGET_PRODUCT = "Artemisinin"
ARTEMISININ_HOST = "Saccharomyces cerevisiae"
ARTEMISININ_STATUS = "draft"


ARTEMISININ_STEPS_FOR_EDIT_TEST = [
    {
        "step_order": 1,
        "step_name": "Acetyl-CoA-derived intermediates",
        "substrate": "Central carbon precursors",
        "product": "Isoprenoid precursors",
        "enzyme_name": "Documented pathway enzymes",
        "gene_name": "precursor_genes",
    },
    {
        "step_order": 2,
        "step_name": "Farnesyl diphosphate formation",
        "substrate": "Isoprenoid precursors",
        "product": "Farnesyl diphosphate",
        "enzyme_name": "Documented pathway enzymes",
        "gene_name": "fpp_genes",
    },
    {
        "step_order": 3,
        "step_name": "Amorpha-4,11-diene synthase reaction",
        "substrate": "Farnesyl diphosphate",
        "product": "Amorpha-4,11-diene",
        "enzyme_name": "ADS",
        "gene_name": "ads",
    },
    {
        "step_order": 4,
        "step_name": "Artemisinin intermediate documentation step",
        "substrate": "Amorpha-4,11-diene",
        "product": "Amorphadiene / Amorpha-4,11-diene",
        "enzyme_name": "Documented pathway enzyme",
        "gene_name": "cyp71av1_like",
    },
]


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "pathway_steps_ui_edit_existing.db"
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    return db_path


def _ensure_artemisinin_demo_project() -> int:
    projects = repo.list_pathway_projects()
    for project in projects:
        if project.get("name") == ARTEMISININ_PROJECT_NAME:
            return int(project["id"])

    ok, message, project_id = repo.create_pathway_project(
        name=ARTEMISININ_PROJECT_NAME,
        target_product=ARTEMISININ_TARGET_PRODUCT,
        host=ARTEMISININ_HOST,
        description="Documentation-only Artemisinin demo project used for UI regression tests.",
        status=ARTEMISININ_STATUS,
    )
    assert ok, message
    assert project_id is not None
    return int(project_id)


def _ensure_artemisinin_steps(project_id: int) -> None:
    existing_steps = repo.list_pathway_steps(project_id)
    if len(existing_steps) == 4:
        return

    for step in existing_steps:
        repo.delete_pathway_step(step["id"])

    for step in ARTEMISININ_STEPS_FOR_EDIT_TEST:
        ok, message, step_id = repo.create_pathway_step(
            project_id=project_id,
            step_order=step["step_order"],
            step_name=step["step_name"],
            substrate=step["substrate"],
            product=step["product"],
            enzyme_name=step["enzyme_name"],
            gene_name=step["gene_name"],
            gene_sequence="",
        )
        assert ok, message
        assert step_id is not None


def _ensure_artemisinin_test_records(project_id: int) -> None:
    records = repo.list_pathway_test_records(project_id)
    if len(records) == 2:
        return

    for record in records:
        repo.delete_pathway_test_record(record["id"])

    steps = repo.list_pathway_steps(project_id)
    step4 = next(step for step in steps if int(step["step_order"]) == 4)

    ok, message, project_record_id = repo.create_pathway_test_record(
        project_id=project_id,
        sample_name="Project-level documentation-only observation",
        measured_product="Documentation only",
        notes="Project-level test record.",
    )
    assert ok, message
    assert project_record_id is not None

    ok, message, step_record_id = repo.create_pathway_test_record(
        project_id=project_id,
        step_id=step4["id"],
        sample_name="Step 4 documentation-only observation",
        measured_product="Artemisinin intermediate documentation",
        notes="Step 4-associated test record.",
    )
    assert ok, message
    assert step_record_id is not None


def _install_fake_streamlit(monkeypatch) -> FakeStreamlit:
    fake_st = FakeStreamlit()
    monkeypatch.setattr(pathway_workspace, "st", fake_st)
    monkeypatch.setattr(streamlit_module, "session_state", fake_st.session_state, raising=False)
    return fake_st


def _step_by_order(steps: list[dict[str, object]], order: int) -> dict[str, object]:
    return next(step for step in steps if int(step["step_order"]) == order)


def test_edit_existing_step_from_steps_tab_updates_only_that_step(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)
    _ensure_artemisinin_test_records(project_id)

    original_steps = repo.list_pathway_steps(project_id)
    original_step1 = _step_by_order(original_steps, 1)
    original_step_names = {step["step_order"]: step["step_name"] for step in original_steps}

    fake_st = _install_fake_streamlit(monkeypatch)
    fake_st.session_state[pathway_workspace.CURRENT_PROJECT_KEY] = project_id
    fake_st.text_area_values.update(
        {
            "gene_sequence_1": "ATGAAATTTGGGCCCTAA",
        }
    )

    def _form_submit_button(label: str, **kwargs):
        fake_st.form_submit_button_calls.append({"label": label, "key": kwargs.get("key"), **kwargs})
        return label == "Save changes"

    monkeypatch.setattr(fake_st, "form_submit_button", _form_submit_button)

    pathway_workspace.render(lambda page_name: None)

    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    expression_links = repo.list_expression_design_links(project_id)
    test_records = repo.list_pathway_test_records(project_id)
    completeness = build_pathway_completeness(project, steps, expression_links)
    review_signals = build_pathway_review_signals(project, steps, expression_links, test_records)
    review_counts = summarize_review_signals(review_signals)
    report = generate_pathway_markdown_report(project, steps, expression_links, test_records, completeness, review_signals)

    assert len(steps) == 4
    assert [step["step_order"] for step in steps] == [1, 2, 3, 4]
    assert not any(int(step["step_order"]) == 5 for step in steps)
    assert not any(step["step_name"] == "Step 5" for step in steps)
    assert any(call["label"] == "Save changes" for call in fake_st.form_submit_button_calls)
    assert fake_st.rerun_calls >= 1

    step1 = _step_by_order(steps, 1)
    step2 = _step_by_order(steps, 2)
    step3 = _step_by_order(steps, 3)
    step4 = _step_by_order(steps, 4)

    assert step1["step_name"] == original_step_names[1]
    assert step2["step_name"] == original_step_names[2]
    assert step3["step_name"] == original_step_names[3]
    assert step4["step_name"] == original_step_names[4]
    assert step1["gene_sequence"] == "ATGAAATTTGGGCCCTAA"
    assert len(str(step1["gene_sequence"])) == 18
    assert len(completeness["missing_items"]) == 7
    assert review_counts["total_review_signals"] == 10
    assert review_counts["medium_review_count"] == 7
    assert not any(signal["signal_type"] == "incomplete_step_documentation" and signal.get("related_step_id") == step1["id"] for signal in review_signals)
    assert any(signal["signal_type"] == "missing_expression_design" and signal.get("related_step_id") == step1["id"] for signal in review_signals)
    assert any("Recorded (18 nt)" in line for line in report.splitlines())
