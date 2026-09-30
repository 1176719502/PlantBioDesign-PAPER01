from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import pathway_repository as repo
from services.pathway_completeness_service import (
    build_dbt_step_evidence_matrix_rows,
    build_pathway_completeness,
    build_pathway_review_signals,
    summarize_review_signals,
)
from services.pathway_report_service import generate_pathway_markdown_report


ARTEMISININ_PROJECT_NAME = "Artemisinin Demo Project"
ARTEMISININ_TARGET_PRODUCT = "Artemisinin"
ARTEMISININ_HOST = "Saccharomyces cerevisiae"
ARTEMISININ_STATUS = "draft"

ARTEMISININ_STEPS = [
    {
        "step_order": 1,
        "step_name": "IPP/DMAPP precursor supply",
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

STEP1_GENE_SEQUENCE = "ATGAAATTTGGGCCCTAA"


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "pathway_steps_crud_linkage.db"
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
        description="Documentation-only Artemisinin demo project used for linkage tests.",
        status=ARTEMISININ_STATUS,
    )
    assert ok, message
    assert project_id is not None
    return int(project_id)


def _step_by_order(steps: list[dict[str, object]], order: int) -> dict[str, object]:
    return next(step for step in steps if int(step["step_order"]) == order)


def _ensure_artemisinin_steps(project_id: int) -> None:
    existing_steps = repo.list_pathway_steps(project_id)
    if len(existing_steps) == 4:
        return

    for step in existing_steps:
        repo.delete_pathway_step(step["id"])

    for step in ARTEMISININ_STEPS:
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
    step4 = _step_by_order(steps, 4)

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


def _baseline_state(project_id: int) -> dict[str, object]:
    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    expression_links = repo.list_expression_design_links(project_id)
    test_records = repo.list_pathway_test_records(project_id)
    completeness = build_pathway_completeness(project, steps, expression_links)
    signals = build_pathway_review_signals(project, steps, expression_links, test_records)
    summary = summarize_review_signals(signals)
    evidence_rows = build_dbt_step_evidence_matrix_rows(project, steps, expression_links, test_records, signals)
    report = generate_pathway_markdown_report(project, steps, expression_links, test_records, completeness, [])
    return {
        "project": project,
        "steps": steps,
        "expression_links": expression_links,
        "test_records": test_records,
        "completeness": completeness,
        "signals": signals,
        "summary": summary,
        "evidence_rows": evidence_rows,
        "report": report,
    }


def test_pathway_steps_crud_linkage_updates_completeness_review_and_report(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)
    _ensure_artemisinin_test_records(project_id)

    baseline = _baseline_state(project_id)
    assert len(baseline["steps"]) == 4
    assert len(baseline["test_records"]) == 2
    assert baseline["summary"]["total_review_signals"] == 11
    assert baseline["summary"]["medium_review_count"] == 8
    assert baseline["summary"]["info_count"] == 3
    assert len(baseline["completeness"]["missing_items"]) == 8
    assert len(baseline["evidence_rows"]) == 4

    step1 = _step_by_order(baseline["steps"], 1)
    ok, message = repo.update_pathway_step(step1["id"], {"gene_sequence": STEP1_GENE_SEQUENCE})
    assert ok, message

    after_sequence = _baseline_state(project_id)
    step1 = _step_by_order(after_sequence["steps"], 1)
    assert step1["gene_sequence"] == STEP1_GENE_SEQUENCE
    assert len(after_sequence["completeness"]["missing_items"]) == 7
    assert after_sequence["summary"]["total_review_signals"] == 10
    assert after_sequence["summary"]["medium_review_count"] == 7
    assert after_sequence["summary"]["info_count"] == 3
    assert after_sequence["summary"]["documentation_gap_count"] == 7
    assert any(signal["signal_type"] == "missing_expression_design" and signal["related_step_id"] == step1["id"] for signal in after_sequence["signals"])
    assert any(signal["signal_type"] == "missing_test_records" and signal["related_step_id"] == step1["id"] for signal in after_sequence["signals"])
    assert not any(signal["signal_type"] == "incomplete_step_documentation" and signal["related_step_id"] == step1["id"] for signal in after_sequence["signals"])
    assert after_sequence["evidence_rows"][0]["sequence_recorded"] is True
    assert after_sequence["evidence_rows"][0]["expression_design_linked"] is False
    assert after_sequence["evidence_rows"][0]["test_record_exists"] is False
    assert "Recorded (18 nt)" in after_sequence["report"]
    assert "Not recorded" in after_sequence["report"]

    ok, message = repo.update_pathway_step(
        step1["id"],
        {
            "reaction_name": "IPP/DMAPP condensation",
            "substrate": "IPP and DMAPP",
            "product": "Geranyl diphosphate",
            "enzyme_name": "Condensing enzyme",
            "gene_name": "ipi1",
            "notes": "Updated documentation for the first step.",
        },
    )
    assert ok, message

    after_reaction = _baseline_state(project_id)
    step1 = _step_by_order(after_reaction["steps"], 1)
    assert step1["reaction_name"] == "IPP/DMAPP condensation"
    assert step1["substrate"] == "IPP and DMAPP"
    assert step1["product"] == "Geranyl diphosphate"
    assert step1["enzyme_name"] == "Condensing enzyme"
    assert step1["gene_name"] == "ipi1"
    assert step1["notes"] == "Updated documentation for the first step."
    assert after_reaction["evidence_rows"][0]["reaction"] == "IPP/DMAPP condensation"
    assert after_reaction["summary"] == after_sequence["summary"]
    assert len(after_reaction["completeness"]["missing_items"]) == len(after_sequence["completeness"]["missing_items"])
    assert after_reaction["report"] != ""
    assert "IPP/DMAPP condensation" in after_reaction["report"]
    assert "Geranyl diphosphate" in after_reaction["report"]

    ok, message, step5_id = repo.create_pathway_step(
        project_id=project_id,
        step_order=5,
        step_name="Late documentation step",
        reaction_name="Documentation reaction",
        substrate="Intermediate X",
        product="Intermediate Y",
        enzyme_name="Documentation enzyme",
        gene_name="doc5",
        gene_sequence="",
        notes="New incomplete documentation step.",
    )
    assert ok, message
    assert step5_id is not None

    after_create = _baseline_state(project_id)
    assert len(after_create["steps"]) == 5
    assert len(after_create["evidence_rows"]) == 5
    step5 = _step_by_order(after_create["steps"], 5)
    assert step5["gene_sequence"] in (None, "")
    assert after_create["evidence_rows"][-1]["sequence_recorded"] is False
    assert after_create["evidence_rows"][-1]["expression_design_linked"] is False
    assert after_create["evidence_rows"][-1]["test_record_exists"] is False
    assert len(after_create["completeness"]["missing_items"]) == 9
    assert after_create["summary"]["medium_review_count"] == 9
    assert after_create["summary"]["info_count"] == 4
    assert after_create["summary"]["total_review_signals"] == 13
    assert "Late documentation step" in after_create["report"]

    ok, message = repo.delete_pathway_step(step5_id)
    assert ok, message

    after_delete = _baseline_state(project_id)
    assert len(after_delete["steps"]) == 4
    assert len(after_delete["evidence_rows"]) == 4
    assert len(after_delete["completeness"]["missing_items"]) == 7
    assert after_delete["summary"]["total_review_signals"] == 10
    assert after_delete["summary"]["medium_review_count"] == 7
    assert after_delete["summary"]["info_count"] == 3
    assert after_delete["summary"]["documentation_gap_count"] == 7
    step1 = _step_by_order(after_delete["steps"], 1)
    assert step1["gene_sequence"] == STEP1_GENE_SEQUENCE
    assert after_delete["evidence_rows"][0]["sequence_recorded"] is True
    assert "Late documentation step" not in after_delete["report"]
    assert len(after_delete["test_records"]) == 2
