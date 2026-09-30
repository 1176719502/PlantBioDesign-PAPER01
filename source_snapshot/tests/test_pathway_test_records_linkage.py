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


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "pathway_test_records_linkage.db"
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    return db_path


def _ensure_artemisinin_demo_project() -> int:
    projects = repo.list_pathway_projects()
    for project in projects:
        if project.get("name") == ARTEMISININ_PROJECT_NAME:
            return int(project["id"])

    ok, message, project_id = repo.create_pathway_project(
        name=ARTEMISININ_PROJECT_NAME,
        target_product="Artemisinin",
        host="Saccharomyces cerevisiae",
        description="Documentation-only Artemisinin demo project used for pathway test record linkage regression testing.",
        status="draft",
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

    steps = [
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

    for step in steps:
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
    test_records = repo.list_pathway_test_records(project_id)
    step4_record_exists = any(int(record.get("step_id") or 0) == 4 for record in test_records)
    if step4_record_exists:
        return

    steps = repo.list_pathway_steps(project_id)
    step4 = _step_by_order(steps, 4)
    ok, message, test_record_id = repo.create_pathway_test_record(
        project_id=project_id,
        step_id=step4["id"],
        sample_name="Step 4 baseline documentation record",
        measured_product="Documentation only",
        titer="Not recorded",
        yield_value="Not recorded",
        productivity="Not recorded",
        notes="Baseline step-associated test record to preserve the expected review signal state.",
    )
    assert ok, message
    assert test_record_id is not None


def _step_by_order(steps: list[dict[str, object]], order: int) -> dict[str, object]:
    return next(step for step in steps if int(step["step_order"]) == order)


def _review_state(project: dict[str, object], steps: list[dict[str, object]], expression_links: list[dict[str, object]], test_records: list[dict[str, object]]) -> dict[str, object]:
    signals = build_pathway_review_signals(project, steps, expression_links, test_records)
    return {
        "completeness": build_pathway_completeness(project, steps, expression_links),
        "signals": signals,
        "summary": summarize_review_signals(signals),
        "evidence_matrix_rows": build_dbt_step_evidence_matrix_rows(project, steps, expression_links, test_records, signals),
    }


def test_step1_test_record_updates_coverage_signals_matrix_and_report(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)
    _ensure_artemisinin_test_records(project_id)

    steps = repo.list_pathway_steps(project_id)
    step1 = _step_by_order(steps, 1)
    step4 = _step_by_order(steps, 4)
    ok, message = repo.update_pathway_step(step1["id"], {"gene_sequence": "ATGAAATTTGGGCCCTAA"})
    assert ok, message

    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    expression_links = repo.list_expression_design_links(project_id)
    test_records = repo.list_pathway_test_records(project_id)
    pre_state = _review_state(project, steps, expression_links, test_records)

    assert any(record.get("step_id") == step4["id"] for record in test_records)
    assert any(
        row["step_order"] == 4 and row["test_record_exists"] is True
        for row in pre_state["evidence_matrix_rows"]
    )
    assert pre_state["summary"]["total_review_signals"] == 10
    assert pre_state["summary"]["medium_review_count"] == 7
    assert pre_state["summary"]["info_count"] == 3
    assert not any(record.get("step_id") == step1["id"] for record in test_records)
    assert any(signal["signal_type"] == "missing_test_records" and signal.get("related_step_id") == step1["id"] for signal in pre_state["signals"])

    ok, message, test_record_id = repo.create_pathway_test_record(
        project_id=project_id,
        step_id=step1["id"],
        sample_name="Step 1 documentation-only observation",
        measured_product="Documentation only",
        titer="Not recorded",
        yield_value="Not recorded",
        productivity="Not recorded",
        notes="Documentation-only test record for Step 1. This is a user-entered observation, not experimental validation.",
    )
    assert ok, message
    assert test_record_id is not None

    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    expression_links = repo.list_expression_design_links(project_id)
    test_records = repo.list_pathway_test_records(project_id)
    post_state = _review_state(project, steps, expression_links, test_records)
    report = generate_pathway_markdown_report(
        project,
        steps,
        expression_links,
        test_records,
        post_state["completeness"],
        post_state["signals"],
    )

    step1_row = next(row for row in post_state["evidence_matrix_rows"] if row["step_order"] == 1)

    assert post_state["summary"]["total_review_signals"] == 9
    assert post_state["summary"]["medium_review_count"] == 7
    assert post_state["summary"]["info_count"] == 2
    assert any(record.get("step_id") == step1["id"] for record in test_records)
    assert step1_row["test_record_exists"] is True
    assert step1_row["review_signal_count"] == 1
    assert step1_row["missing_documentation_summary"] == "No linked expression design"
    assert not any(signal["signal_type"] == "missing_test_records" and signal.get("related_step_id") == step1["id"] for signal in post_state["signals"])
    assert "Step 1 documentation-only observation" in report
    assert "| Total review signals | 9 |" in report
    assert "| Medium review | 7 |" in report
    assert "| Info | 2 |" in report
