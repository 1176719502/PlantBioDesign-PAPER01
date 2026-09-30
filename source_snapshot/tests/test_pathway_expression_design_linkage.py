from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services import pathway_repository as repo
from services.pathway_completeness_service import (
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

STEP1_SEQUENCE = "ATGAAATTTGGGCCCTAA"


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "pathway_expression_design_linkage.db"
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
        description="Documentation-only Artemisinin demo project used for expression design linkage regression testing.",
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


def _artemisinin_project() -> dict:
    return repo.get_pathway_project(_ensure_artemisinin_demo_project())


def _step1(steps: list[dict]) -> dict:
    step1 = next((step for step in steps if int(step.get("step_order") or 0) == 1), None)
    assert step1 is not None, "Step 1 was not found."
    return step1


def test_step1_expression_design_link_updates_completeness_signals_matrix_and_report(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)
    _ensure_artemisinin_test_records(project_id)

    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    assert len(steps) == 4

    existing_test_records = repo.list_pathway_test_records(project_id)
    assert existing_test_records, "Baseline Artemisinin test records were not seeded."

    step1 = _step1(steps)
    if step1.get("gene_sequence") != STEP1_SEQUENCE:
        ok, message = repo.update_pathway_step(step1["id"], {"gene_sequence": STEP1_SEQUENCE})
        assert ok, message
        steps = repo.list_pathway_steps(project_id)
        step1 = _step1(steps)

    assert step1.get("gene_sequence") == STEP1_SEQUENCE

    step1_test_record = next((record for record in existing_test_records if int(record.get("step_id") or 0) == int(step1["id"])), None)
    if step1_test_record is None:
        ok, message, _ = repo.create_pathway_test_record(
            project_id=project_id,
            step_id=step1["id"],
            sample_name="Step 1 documentation coverage check",
            measured_product="Mevalonate",
            titer="Not recorded",
            yield_value="Not recorded",
            productivity="Not recorded",
            intermediate_accumulation="Not assessed in this documentation-only record.",
            enzyme_activity="Not assessed in this documentation-only record.",
            growth_status="Not assessed / documentation-only record",
            condition="Documentation review after Step 1 sequence was recorded.",
            notes="Step 1 now has a step-associated documentation record. This is not experimental validation.",
        )
        assert ok, message
        existing_test_records = repo.list_pathway_test_records(project_id)

    steps = repo.list_pathway_steps(project_id)
    test_records = repo.list_pathway_test_records(project_id)
    expression_links_before = repo.list_expression_design_links(project_id)
    completeness_before = build_pathway_completeness(project, steps, expression_links_before)
    review_signals_before = build_pathway_review_signals(project, steps, expression_links_before, test_records)
    summary_before = summarize_review_signals(review_signals_before)

    assert len(completeness_before["missing_items"]) == 7
    assert summary_before["total_review_signals"] == 9
    assert summary_before["medium_review_count"] == 7
    assert summary_before["info_count"] == 2

    step1_signals_before = [signal for signal in review_signals_before if int(signal.get("related_step_id") or 0) == int(step1["id"])]
    assert len(step1_signals_before) == 1
    assert step1_signals_before[0]["signal_type"] == "missing_expression_design"

    from views.PathwayWorkspace import _format_step_reaction
    from views.pathway_workspace_sections.overview_summary_section import _step_evidence_matrix_rows

    matrix_rows_before = _step_evidence_matrix_rows(
        steps,
        expression_links_before,
        test_records,
        review_signals_before,
        completeness_before,
        _format_step_reaction,
    )
    step1_matrix_before = next(row for row in matrix_rows_before if row["Step"] == step1.get("step_name") or row["Step"] == f"Step {step1.get('step_order')}")
    assert step1_matrix_before["Sequence recorded?"] == "Yes"
    assert step1_matrix_before["Expression design linked?"] == "No"
    assert step1_matrix_before["Test record exists?"] == "Yes"
    assert step1_matrix_before["Review signals"] == 1
    assert step1_matrix_before["Missing documentation"].lower() == "no linked expression design"

    design_snapshot = {
        "design_name": "Step 1 linked expression design",
        "step_id": step1["id"],
        "traceability_only": True,
    }
    validation_summary = {
        "traceability_only": True,
        "not_recommended_for_experimental_use": False,
        "primer_risk": "not assessed",
    }
    ok, message, _ = repo.link_expression_design_to_step(
        project_id=project_id,
        step_id=step1["id"],
        design_name="Step 1 linked expression design",
        design_snapshot_json=json.dumps(design_snapshot),
        validation_summary_json=json.dumps(validation_summary),
    )
    assert ok, message

    linked_designs = repo.list_expression_design_links(project_id)
    assert len(linked_designs) == 1
    assert linked_designs[0]["step_id"] == step1["id"]
    assert linked_designs[0]["design_name"] == "Step 1 linked expression design"

    completeness_after = build_pathway_completeness(project, steps, linked_designs)
    review_signals_after = build_pathway_review_signals(project, steps, linked_designs, test_records)
    summary_after = summarize_review_signals(review_signals_after)

    assert len(completeness_after["missing_items"]) == 6
    assert summary_after["total_review_signals"] == 8
    assert summary_after["medium_review_count"] == 6
    assert summary_after["info_count"] == 2

    step1_signals_after = [signal for signal in review_signals_after if int(signal.get("related_step_id") or 0) == int(step1["id"])]
    assert step1_signals_after == []

    matrix_rows_after = _step_evidence_matrix_rows(
        steps,
        linked_designs,
        test_records,
        review_signals_after,
        completeness_after,
        _format_step_reaction,
    )
    step1_matrix_after = next(row for row in matrix_rows_after if row["Step"] == step1.get("step_name") or row["Step"] == f"Step {step1.get('step_order')}")
    assert step1_matrix_after["Sequence recorded?"] == "Yes"
    assert step1_matrix_after["Expression design linked?"] == "Yes"
    assert step1_matrix_after["Test record exists?"] == "Yes"
    assert step1_matrix_after["Review signals"] == 0
    assert step1_matrix_after["Missing documentation"].lower() == "no missing documentation recorded"
    report = generate_pathway_markdown_report(
        project,
        steps,
        linked_designs,
        test_records,
        completeness_after,
        review_signals_after,
        generated_at=None,
    )

    assert "Step 1 linked expression design" in report
    assert "| Total review signals | 8 |" in report
    assert "| Medium review | 6 |" in report
    assert "| Info | 2 |" in report
    assert "linked expression wizard" in report.lower()
    assert "Step 1 missing_expression_design" not in report
    assert "does not certify experimental readiness" in report
    assert "does not predict yield" in report
    assert "does not optimize pathways" in report
    assert "documentation-only" in report.lower()
