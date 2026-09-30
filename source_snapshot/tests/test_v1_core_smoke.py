from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import module_registry
from services import pathway_repository as repo
from services.pathway_completeness_service import (
    build_dbt_step_evidence_matrix_rows,
    build_pathway_completeness,
    build_pathway_review_signals,
    filter_documentation_gap_signals,
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


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "v1_core_smoke.db"
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
        description="Documentation-only Artemisinin demo project used for V1 Core smoke tests.",
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


def _step_by_order(steps: list[dict[str, object]], order: int) -> dict[str, object]:
    return next(step for step in steps if int(step["step_order"]) == order)


def _build_review_signal_set(project: dict[str, object], steps: list[dict[str, object]], expression_links: list[dict[str, object]], test_records: list[dict[str, object]]) -> dict[str, object]:
    completeness = build_pathway_completeness(project, steps, expression_links)
    signals = build_pathway_review_signals(project, steps, expression_links, test_records)
    return {
        "completeness": completeness,
        "signals": signals,
        "summary": summarize_review_signals(signals),
        "documentation_gaps": filter_documentation_gap_signals(signals),
        "evidence_matrix_rows": build_dbt_step_evidence_matrix_rows(project, steps, expression_links, test_records, signals),
    }


def test_artemisinin_demo_seed_is_idempotent(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)
    _ensure_artemisinin_test_records(project_id)

    first_project = repo.get_pathway_project(project_id)
    first_steps = repo.list_pathway_steps(project_id)
    assert first_project["name"] == ARTEMISININ_PROJECT_NAME
    assert first_project["target_product"] == ARTEMISININ_TARGET_PRODUCT
    assert first_project["host"] == ARTEMISININ_HOST
    assert first_project["status"] == ARTEMISININ_STATUS
    assert len(first_steps) == 4

    project_id_again = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id_again)

    second_steps = repo.list_pathway_steps(project_id_again)
    assert project_id_again == project_id
    assert len(second_steps) == 4
    assert repo.list_pathway_steps(project_id) == second_steps


def test_artemisinin_demo_pathway_steps_are_complete_and_ordered(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)
    _ensure_artemisinin_test_records(project_id)

    steps = repo.list_pathway_steps(project_id)
    assert [step["step_order"] for step in steps] == [1, 2, 3, 4]
    assert [step["step_name"] for step in steps] == [item["step_name"] for item in ARTEMISININ_STEPS]
    for step in steps:
        assert step["substrate"]
        assert step["product"]
        assert step["enzyme_name"]
        assert step["gene_name"]

    assert steps[-1]["product"] in {"Amorphadiene / Amorpha-4,11-diene", "Amorpha-4,11-diene", "Amorphadiene"}
    assert repo.list_pathway_steps(project_id)[3]["product"] == "Amorphadiene / Amorpha-4,11-diene"


def test_pathway_completeness_reads_four_demo_steps(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)
    _ensure_artemisinin_test_records(project_id)

    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    completeness = build_pathway_completeness(project, steps, [])

    assert completeness["step_summaries"]
    assert len(completeness["step_summaries"]) == 4
    assert completeness["score"] is not None
    assert isinstance(completeness["score"], int)


def test_pathway_test_records_project_and_step_association(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)
    _ensure_artemisinin_test_records(project_id)
    steps = repo.list_pathway_steps(project_id)
    step4 = _step_by_order(steps, 4)
    records = repo.list_pathway_test_records(project_id)
    assert len(records) == 2
    assert any(record["step_id"] is None for record in records)
    assert any(record["step_id"] == step4["id"] for record in records)
    linked = next(record for record in records if record["step_id"] == step4["id"])
    assert linked["step_name"] == step4["step_name"]
    assert linked.get("step_id") == step4["id"]


def test_documentation_review_notes_and_snapshots_round_trip(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)

    review_payload = repo.get_default_documentation_review()
    review_payload["review_notes"] = "Documentation review notes for the demo project."
    review_payload["follow_up_actions"] = "Confirm wording only."
    review_payload["reviewer_name_or_initials"] = "AB"
    ok, message = repo.update_pathway_documentation_review(project_id, review_payload)
    assert ok, message

    project = repo.get_pathway_project(project_id)
    assert project["documentation_review"]["review_notes"] == "Documentation review notes for the demo project."

    ok, message, snapshot_id = repo.create_pathway_documentation_snapshot(
        project_id=project_id,
        snapshot_title="Artemisinin demo snapshot",
        snapshot_note="Round-trip smoke test.",
        snapshot_payload={"project_id": project_id, "kind": "smoke"},
        report_config={"include_project_metadata": True},
    )
    assert ok, message
    assert snapshot_id is not None

    snapshots = repo.list_pathway_documentation_snapshots(project_id)
    assert len(snapshots) == 1
    assert snapshots[0]["snapshot_title"] == "Artemisinin demo snapshot"
    assert snapshots[0]["snapshot_note"] == "Round-trip smoke test."


def test_pathway_report_service_generates_safe_markdown_for_demo_project(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)
    _ensure_artemisinin_test_records(project_id)
    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    completeness = build_pathway_completeness(project, steps, [])
    test_records = repo.list_pathway_test_records(project_id)

    report = generate_pathway_markdown_report(
        project,
        steps,
        [],
        test_records,
        completeness,
        [],
        generated_at="2026-05-27 10:00:00",
    )

    assert "Artemisinin Demo Project" in report
    assert "Artemisinin" in report
    assert "4" in report
    forbidden_phrases = [
        "Potential bottleneck signal",
        "confirmed bottleneck",
        "bottleneck",
        "yield prediction",
        "optimized pathway",
        "ready for experiment",
    ]
    assert "documentation-only" in report.lower()
    assert "boundary" in report.lower()
    for phrase in forbidden_phrases:
        assert phrase.lower() not in report.lower()


def test_pathway_workspace_data_linkage_initial_demo_state(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)
    _ensure_artemisinin_test_records(project_id)

    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    expression_links = repo.list_expression_design_links(project_id)
    test_records = repo.list_pathway_test_records(project_id)
    completeness = build_pathway_completeness(project, steps, expression_links)
    review_state = _build_review_signal_set(project, steps, expression_links, test_records)
    counts = review_state["summary"]

    step1 = _step_by_order(steps, 1)
    step4 = _step_by_order(steps, 4)

    assert len(steps) == 4
    assert completeness["score"] == 50
    assert len(completeness["missing_items"]) == 8
    assert counts["total_review_signals"] == 11
    assert counts["high_review_count"] == 0
    assert counts["medium_review_count"] == 8
    assert counts["info_count"] == 3
    assert counts["documentation_gap_count"] == 8
    assert counts["missing_test_record_prompt_count"] == 3
    assert len(expression_links) == 0
    assert len([record for record in test_records if record.get("step_id") is not None]) == 1
    assert len(test_records) == 2
    assert any(record.get("step_id") == step4["id"] for record in test_records)
    assert len([summary for summary in completeness["step_summaries"] if summary["has_expression_design"]]) == 0
    assert len([summary for summary in completeness["step_summaries"] if summary["step_order"] == 1]) == 1
    assert len([summary for summary in completeness["step_summaries"] if summary["step_order"] == 4]) == 1
    assert step1["gene_sequence"] in (None, "")
    assert step4["gene_sequence"] in (None, "") or str(step4["gene_sequence"]).strip() == ""
    assert step1["id"] is not None
    assert step1.get("step_order") == 1
    assert step4.get("step_order") == 4
    assert step1.get("gene_sequence", "") == ""
    assert step4.get("gene_sequence", "") == ""
    assert len([record for record in test_records if record.get("step_id") == step4["id"]]) == 1
    assert len([record for record in test_records if record.get("step_id") == step1["id"]]) == 0
    assert len(review_state["documentation_gaps"]) == 8
    assert any(record.get("step_id") == step4["id"] for record in test_records)
    assert len(review_state["evidence_matrix_rows"]) == 4
    assert review_state["evidence_matrix_rows"][0]["sequence_recorded"] is False
    assert review_state["evidence_matrix_rows"][3]["test_record_exists"] is True
    assert len([item for item in completeness["step_summaries"][0]["missing_items"] if "gene sequence" in item.lower()]) == 1
    assert len([item for item in completeness["step_summaries"][0]["missing_items"] if "linked expression design" in item.lower()]) == 1
    assert len([item for item in completeness["step_summaries"][0]["missing_items"] if "test record" in item.lower()]) == 0
    assert len([item for item in completeness["step_summaries"][3]["missing_items"] if "test record" in item.lower()]) == 0
    assert len([record for record in test_records if record.get("step_id") is None]) == 1
    assert len([record for record in test_records if record.get("step_id") == step4["id"]]) == 1
    assert any(signal["signal_type"] == "missing_test_records" for signal in review_state["signals"])


def test_pathway_workspace_data_linkage_sequence_link_and_test_record_progression(tmp_path, monkeypatch):
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
    completeness = build_pathway_completeness(project, steps, expression_links)
    review_state = _build_review_signal_set(project, steps, expression_links, test_records)
    report = generate_pathway_markdown_report(project, steps, expression_links, test_records, completeness, review_state["signals"])
    counts = review_state["summary"]

    step1 = _step_by_order(steps, 1)
    assert step1["gene_sequence"] == "ATGAAATTTGGGCCCTAA"
    assert step1["gene_sequence"].strip()
    assert len(completeness["missing_items"]) == 7
    assert len(expression_links) == 0
    assert len([record for record in test_records if record.get("step_id") == step1["id"]]) == 0
    assert any(record.get("step_id") == step4["id"] for record in test_records)
    assert counts["total_review_signals"] == 10
    assert counts["medium_review_count"] == 7
    assert counts["info_count"] == 3
    assert counts["documentation_gap_count"] == 7
    assert len([item for item in completeness["step_summaries"][0]["missing_items"] if "gene sequence" in item.lower()]) == 0
    assert len([item for item in completeness["step_summaries"][0]["missing_items"] if "linked expression design" in item.lower()]) == 1
    assert any("Recorded (18 nt)" in line for line in report.splitlines())
    assert "| Score | 56% |" in report or "56%" in report
    assert "Missing Items" in report
    assert "Step 1 | incomplete_step_documentation" not in report
    assert "Step Acetyl-CoA-derived intermediates to Mevalonate is missing sequence documentation" not in report
    assert "missing_expression_design" in report
    assert step1["step_name"] in report
    assert "No linked Expression Wizard design is recorded for this step." in report
    assert "missing_test_records" in report
    assert step1["step_name"] in report
    assert "No step-associated test record" in report
    assert "Not recorded" in report
    assert any(
        signal["signal_type"] == "missing_test_records"
        and signal["related_step_id"] == step1["id"]
        for signal in review_state["signals"]
    )
    assert any(signal["signal_type"] == "missing_expression_design" and signal["related_step_id"] == step1["id"] for signal in review_state["signals"])
    assert "Documentation review prompt" not in report
    assert "Recorded pattern suggests" not in report
    assert "Review priority" not in report
    assert "Suggested next check" not in report
    assert "No linked expression design" in report or any("No linked expression design" in str(row) for row in review_state["evidence_matrix_rows"])
    assert "No step-associated test record" in report or any("No step-associated test record" in str(row) for row in review_state["evidence_matrix_rows"])

    ok, message, test_id = repo.create_pathway_test_record(
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
    assert test_id is not None

    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    expression_links = repo.list_expression_design_links(project_id)
    test_records = repo.list_pathway_test_records(project_id)
    completeness = build_pathway_completeness(project, steps, expression_links)
    review_state = _build_review_signal_set(project, steps, expression_links, test_records)
    counts = review_state["summary"]

    assert len([record for record in test_records if record.get("step_id") == step1["id"]]) == 1
    assert len(test_records) == 3
    assert any(record.get("step_id") == step1["id"] for record in test_records)
    assert len(completeness["step_summaries"]) == 4
    assert len([record for record in test_records if record.get("step_id") is None]) == 1
    assert counts["total_review_signals"] == 9
    assert counts["medium_review_count"] == 7
    assert counts["info_count"] == 2
    assert counts["documentation_gap_count"] == 7
    assert counts["missing_test_record_prompt_count"] == 2
    assert any(row["test_record_exists"] is True for row in review_state["evidence_matrix_rows"] if row["step_name"] == step1["step_name"])
    report = generate_pathway_markdown_report(project, steps, expression_links, test_records, completeness, review_state["signals"])
    assert step1["step_name"] in report
    assert "Review Signals Summary" in report
    assert "| Total review signals | 9 |" in report
    assert "| Medium review | 7 |" in report
    assert "| Info | 2 |" in report
    assert "| Missing test record prompts | 2 |" in report
    assert "Step 1 documentation-only record" in report or "Step 1 documentation coverage check" in report
    assert "| Step 1: IPP/DMAPP precursor supply |" in report or "Step 1 documentation-only record" in report


def test_pathway_workspace_report_keeps_sequence_status_as_recorded(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _ensure_artemisinin_demo_project()
    _ensure_artemisinin_steps(project_id)

    steps = repo.list_pathway_steps(project_id)
    step1 = _step_by_order(steps, 1)
    repo.update_pathway_step(step1["id"], {"gene_sequence": "ATGAAATTTGGGCCCTAA"})
    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    report = generate_pathway_markdown_report(project, steps, [], repo.list_pathway_test_records(project_id), build_pathway_completeness(project, steps, []), [])

    assert "Step 1" in report
    assert "Recorded (18 nt)" in report
    assert "Not recorded" in report


def test_module_registry_core_visibility_and_hidden_modules(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    core_ids = {module["id"] for module in module_registry.list_by_layer("core")}
    hidden_ids = {module["id"] for module in module_registry.list_by_layer("hidden")}

    assert "homepage" in core_ids
    assert "dashboard" in core_ids
    assert "pathway_projects" in core_ids
    assert "pathway_workspace" in core_ids
    assert "expression_wizard" in core_ids
    assert "module_center" in hidden_ids
    assert "ai_literature_research" in hidden_ids
    assert "assembly_cloning" in hidden_ids
    assert "module_center" not in core_ids
    assert "ai_literature_research" not in core_ids
    assert module_registry.get_by_route_key("Module Overview")["layer"] == "hidden"
    assert module_registry.get_by_route_key("AI Literature Research")["layer"] == "hidden"
    assert module_registry.get_by_route_key("Homepage")["layer"] == "core"
    assert module_registry.get_by_route_key("Dashboard")["name"] == "Saved Designs"
    assert module_registry.get_by_route_key("Pathway Projects")["layer"] == "core"
    assert module_registry.get_by_route_key("Pathway Workspace")["layer"] == "core"
