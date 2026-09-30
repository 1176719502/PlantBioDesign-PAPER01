from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import pathway_repository as repo
from services.pathway_bottleneck_service import analyze_pathway_bottlenecks
from services.pathway_completeness_service import build_pathway_completeness
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


def _pathway_repository_db_path(filename: str) -> Path:
    return repo_local_sqlite_db_path(".pytest_tmp_r81_pathway_repository_dbs", filename)


def _use_temp_db(monkeypatch):
    db_path = _pathway_repository_db_path("pathway_repository.db")
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))
    return db_path


def _create_project(name: str = "Naringenin Pathway") -> int:
    ok, message, project_id = repo.create_pathway_project(
        name=name,
        target_product="Naringenin",
        host="E. coli BL21(DE3)",
        description="Phase 1 repository test project.",
    )
    assert ok is True, message
    assert project_id is not None
    return project_id


def _create_step(project_id: int, step_order: int = 1) -> int:
    ok, message, step_id = repo.create_pathway_step(
        project_id=project_id,
        step_order=step_order,
        step_name="Starter step",
        reaction_name="Starter reaction",
        substrate="p-Coumaroyl-CoA",
        product="Naringenin chalcone",
        enzyme_name="CHS",
        gene_name="chs",
        gene_sequence="atgaaataa",
    )
    assert ok is True, message
    assert step_id is not None
    return step_id


def test_create_list_get_delete_pathway_project(monkeypatch):
    _use_temp_db(monkeypatch)

    project_id = _create_project()

    projects = repo.list_pathway_projects()
    assert len(projects) == 1
    assert projects[0]["id"] == project_id
    assert projects[0]["name"] == "Naringenin Pathway"
    assert projects[0]["documentation_review"] == repo.get_default_documentation_review()

    project = repo.get_pathway_project(project_id)
    assert project["id"] == project_id
    assert project["target_product"] == "Naringenin"
    assert project["documentation_review"] == repo.get_default_documentation_review()

    ok, message = repo.delete_pathway_project(project_id)
    assert ok is True, message
    assert repo.get_pathway_project(project_id) == {}
    assert repo.list_pathway_projects() == []


def test_documentation_review_defaults_and_normalization_are_safe():
    defaults = repo.get_default_documentation_review()

    assert set(defaults["review_items"]) == set(repo.DOCUMENTATION_REVIEW_CHECKLIST_KEYS)
    assert all(value is False for value in defaults["review_items"].values())
    assert defaults["reviewer_name_or_initials"] == ""
    assert defaults["review_date"] == ""
    assert defaults["review_notes"] == ""
    assert defaults["follow_up_actions"] == ""
    assert defaults["unresolved_items"] == ""
    assert defaults["last_updated"] == ""

    normalized = repo.normalize_documentation_review(
        {
            "review_items": {
                "pathway_description_reviewed": True,
                "unknown_review_item": True,
            },
            "reviewer_name_or_initials": " AB ",
            "review_date": "2026-05-22",
            "unknown_field": "ignored",
        }
    )

    assert normalized["review_items"]["pathway_description_reviewed"] is True
    assert normalized["review_items"]["gene_entries_reviewed"] is False
    assert "unknown_review_item" not in normalized["review_items"]
    assert normalized["reviewer_name_or_initials"] == "AB"
    assert "unknown_field" not in normalized


def test_old_project_without_documentation_review_loads_safely(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_pathway_tables()

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO pathway_projects
                (name, target_product, host, description, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "Legacy Pathway",
                "Naringenin",
                "E. coli",
                "Created before documentation review persistence.",
                "draft",
                "2026-05-21T12:00:00",
                "2026-05-21T12:00:00",
            ),
        )
        project_id = conn.execute("SELECT id FROM pathway_projects").fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    project = repo.get_pathway_project(project_id)

    assert project["name"] == "Legacy Pathway"
    assert project["documentation_review"] == repo.get_default_documentation_review()


def test_documentation_review_fields_persist_after_save_load(monkeypatch):
    _use_temp_db(monkeypatch)
    project_id = _create_project()
    review_payload = repo.get_default_documentation_review()
    review_payload["review_items"].update(
        {
            "pathway_description_reviewed": True,
            "gene_entries_reviewed": True,
            "linked_expression_designs_reviewed": True,
            "suggestions_reviewed": True,
            "test_records_reviewed": True,
            "markdown_documentation_report_reviewed": True,
            "unresolved_documentation_items_reviewed": True,
        }
    )
    review_payload.update(
        {
            "reviewer_name_or_initials": "AB",
            "review_date": "2026-05-22",
            "review_notes": "Reviewed documentation language and linked records.",
            "follow_up_actions": "Clarify one enzyme source note.",
            "unresolved_items": "One pathway source citation remains open.",
            "last_updated": "2026-05-22T10:30:00",
            "review_scope": "Local project documentation",
            "review_context": "Phase 5D repository persistence test",
            "unknown_field": "ignored",
        }
    )

    ok, message = repo.update_pathway_documentation_review(project_id, review_payload)
    assert ok is True, message

    loaded = repo.get_pathway_project(project_id)["documentation_review"]
    assert loaded["review_items"] == review_payload["review_items"]
    assert loaded["reviewer_name_or_initials"] == "AB"
    assert loaded["review_date"] == "2026-05-22"
    assert loaded["review_notes"] == "Reviewed documentation language and linked records."
    assert loaded["follow_up_actions"] == "Clarify one enzyme source note."
    assert loaded["unresolved_items"] == "One pathway source citation remains open."
    assert loaded["last_updated"] == "2026-05-22T10:30:00"
    assert loaded["review_scope"] == "Local project documentation"
    assert loaded["review_context"] == "Phase 5D repository persistence test"
    assert "unknown_field" not in loaded


def test_documentation_review_update_validates_project_id(monkeypatch):
    _use_temp_db(monkeypatch)
    repo.init_pathway_tables()

    ok, message = repo.update_pathway_documentation_review("not-an-id", {})
    assert ok is False
    assert message == "Invalid project id."

    ok, message = repo.update_pathway_documentation_review(9999, {})
    assert ok is False
    assert message == "Pathway project was not found."


def test_documentation_review_does_not_change_completeness_or_suggestions(monkeypatch):
    _use_temp_db(monkeypatch)
    project_id = _create_project()
    step_id = _create_step(project_id)
    project_before = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    links = repo.list_expression_design_links(project_id)
    tests = repo.list_pathway_test_records(project_id)

    completeness_before = build_pathway_completeness(project_before, steps, links)
    suggestions_before = analyze_pathway_bottlenecks(
        {
            "pathway_steps": steps,
            "expression_design_links": links,
            "pathway_completeness": completeness_before,
            "pathway_test_records": tests,
        }
    )

    review_payload = {
        "review_items": {"pathway_description_reviewed": True},
        "reviewer_name_or_initials": "AB",
        "review_date": "2026-05-22",
        "review_notes": "Repository-only review note.",
        "follow_up_actions": "Repository-only follow-up action.",
        "unresolved_items": "Repository-only unresolved item.",
        "last_updated": "2026-05-22T10:30:00",
    }
    ok, message = repo.update_pathway_documentation_review(project_id, review_payload)
    assert ok is True, message

    project_after = repo.get_pathway_project(project_id)
    completeness_after = build_pathway_completeness(project_after, steps, links)
    suggestions_after = analyze_pathway_bottlenecks(
        {
            "pathway_steps": steps,
            "expression_design_links": links,
            "pathway_completeness": completeness_after,
            "pathway_test_records": tests,
        }
    )

    assert completeness_after == completeness_before
    assert suggestions_after == suggestions_before


def test_delete_project_removes_steps_and_expression_design_links(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    project_id = _create_project()
    step_id = _create_step(project_id)

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            INSERT INTO pathway_expression_designs
                (project_id, step_id, design_name, design_source, linked_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, step_id, "Expression draft", "manual_test", "2026-05-21T12:00:00"),
        )
        conn.commit()
    finally:
        conn.close()

    assert len(repo.list_pathway_steps(project_id)) == 1
    assert len(repo.list_expression_design_links(project_id)) == 1

    ok, message = repo.delete_pathway_project(project_id)
    assert ok is True, message
    assert repo.list_pathway_steps(project_id) == []
    assert repo.list_expression_design_links(project_id) == []


def test_create_list_update_delete_pathway_step(monkeypatch):
    _use_temp_db(monkeypatch)
    project_id = _create_project()
    step_id = _create_step(project_id)

    steps = repo.list_pathway_steps(project_id)
    assert len(steps) == 1
    assert steps[0]["id"] == step_id
    assert steps[0]["gene_sequence"] == "ATGAAATAA"

    ok, message = repo.update_pathway_step(
        step_id,
        {
            "step_order": 2,
            "step_name": "Updated step",
            "substrate": "Updated substrate",
            "product": "Updated product",
            "enzyme_name": "CHI",
            "gene_name": "chi",
            "gene_sequence": "atgccc",
            "ignored_field": "ignored",
        },
    )
    assert ok is True, message

    updated = repo.list_pathway_steps(project_id)[0]
    assert updated["step_order"] == 2
    assert updated["step_name"] == "Updated step"
    assert updated["gene_sequence"] == "ATGCCC"
    assert "ignored_field" not in updated

    ok, message = repo.delete_pathway_step(step_id)
    assert ok is True, message
    assert repo.list_pathway_steps(project_id) == []


def test_invalid_project_id_does_not_create_orphan_step(monkeypatch):
    db_path = _use_temp_db(monkeypatch)
    repo.init_pathway_tables()

    ok, message, step_id = repo.create_pathway_step(
        project_id=9999,
        step_order=1,
        step_name="Orphan candidate",
    )

    assert ok is False
    assert step_id is None
    assert "not found" in message.lower()
    assert repo.list_pathway_steps(9999) == []

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute("SELECT COUNT(*) FROM pathway_steps").fetchone()[0]
    finally:
        conn.close()
    assert count == 0



def test_link_expression_design_to_step_replaces_current_link(monkeypatch):
    _use_temp_db(monkeypatch)
    project_id = _create_project()
    step_id = _create_step(project_id)

    snapshot_one = json.dumps({"saved_design_name": "Design A", "gene_name": "chs"})
    summary_one = json.dumps({"export_recommendation": "Export with Review Required"})
    ok, message, first_link_id = repo.link_expression_design_to_step(
        project_id=project_id,
        step_id=step_id,
        design_name="Design A",
        design_snapshot_json=snapshot_one,
        validation_summary_json=summary_one,
    )

    assert ok is True, message
    assert first_link_id is not None
    links = repo.list_expression_design_links(project_id)
    assert len(links) == 1
    assert links[0]["project_id"] == project_id
    assert links[0]["step_id"] == step_id
    assert links[0]["design_name"] == "Design A"
    assert links[0]["design_source"] == "expression_wizard"
    assert json.loads(links[0]["design_snapshot_json"])["gene_name"] == "chs"
    assert json.loads(links[0]["validation_summary_json"])["export_recommendation"] == "Export with Review Required"
    assert links[0]["linked_at"]

    snapshot_two = json.dumps({"saved_design_name": "Design B", "gene_name": "chs2"})
    summary_two = json.dumps({"export_recommendation": "Not Recommended for Experimental Use"})
    ok, message, second_link_id = repo.link_expression_design_to_step(
        project_id=project_id,
        step_id=step_id,
        design_name="Design B",
        design_snapshot_json=snapshot_two,
        validation_summary_json=summary_two,
    )

    assert ok is True, message
    assert second_link_id is not None
    links = repo.list_expression_design_links(project_id)
    assert len(links) == 1
    assert links[0]["id"] == second_link_id
    assert links[0]["design_name"] == "Design B"
    assert json.loads(links[0]["design_snapshot_json"])["saved_design_name"] == "Design B"


def test_link_expression_design_to_step_validates_required_inputs(monkeypatch):
    _use_temp_db(monkeypatch)
    project_id = _create_project()
    step_id = _create_step(project_id)
    valid_snapshot = json.dumps({"saved_design_name": "Design A"})
    valid_summary = json.dumps({"export_recommendation": "Documentation Export Available"})

    ok, message, link_id = repo.link_expression_design_to_step(
        project_id=project_id,
        step_id=step_id,
        design_name="",
        design_snapshot_json=valid_snapshot,
        validation_summary_json=valid_summary,
    )
    assert ok is False
    assert link_id is None
    assert message == "Design name is required."

    ok, message, link_id = repo.link_expression_design_to_step(
        project_id=project_id,
        step_id=step_id,
        design_name="Design A",
        design_snapshot_json="not-json",
        validation_summary_json=valid_summary,
    )
    assert ok is False
    assert link_id is None
    assert message == "Design snapshot JSON is invalid."

    ok, message, link_id = repo.link_expression_design_to_step(
        project_id=project_id,
        step_id=step_id,
        design_name="Design A",
        design_snapshot_json=valid_snapshot,
        validation_summary_json="not-json",
    )
    assert ok is False
    assert link_id is None
    assert message == "Validation summary JSON is invalid."
    assert repo.list_expression_design_links(project_id) == []


def test_link_expression_design_to_step_rejects_missing_or_cross_project_records(monkeypatch):
    _use_temp_db(monkeypatch)
    project_a = _create_project("Project A")
    project_b = _create_project("Project B")
    step_b = _create_step(project_b)
    valid_snapshot = json.dumps({"saved_design_name": "Design A"})
    valid_summary = json.dumps({"export_recommendation": "Documentation Export Available"})

    ok, message, link_id = repo.link_expression_design_to_step(
        project_id=9999,
        step_id=step_b,
        design_name="Design A",
        design_snapshot_json=valid_snapshot,
        validation_summary_json=valid_summary,
    )
    assert ok is False
    assert link_id is None
    assert message == "Pathway project was not found."

    ok, message, link_id = repo.link_expression_design_to_step(
        project_id=project_a,
        step_id=9999,
        design_name="Design A",
        design_snapshot_json=valid_snapshot,
        validation_summary_json=valid_summary,
    )
    assert ok is False
    assert link_id is None
    assert message == "Pathway step was not found."

    ok, message, link_id = repo.link_expression_design_to_step(
        project_id=project_a,
        step_id=step_b,
        design_name="Design A",
        design_snapshot_json=valid_snapshot,
        validation_summary_json=valid_summary,
    )
    assert ok is False
    assert link_id is None
    assert message == "Pathway step does not belong to the project."
    assert repo.list_expression_design_links(project_a) == []
    assert repo.list_expression_design_links(project_b) == []
    _use_temp_db(monkeypatch)
    repo.init_pathway_tables()

    ok, message = repo.delete_pathway_project("not-an-id")
    assert ok is False
    assert message == "Invalid project id."

    ok, message = repo.delete_pathway_step("not-an-id")
    assert ok is False
    assert message == "Invalid step id."

    assert repo.get_pathway_project("not-an-id") == {}
    assert repo.list_pathway_steps("not-an-id") == []
    assert repo.list_expression_design_links("not-an-id") == []

    ok, message = repo.update_pathway_step("not-an-id", {"step_name": "No-op"})
    assert ok is False
    assert message == "Invalid step id."

    ok, message, step_id = repo.create_pathway_step(project_id="bad", step_order=1)
    assert ok is False
    assert step_id is None
    assert message == "Project id and step order are required."


def _create_test_record(project_id: int, step_id: int | None = None, sample_name: str = "Sample A") -> int:
    ok, message, test_id = repo.create_pathway_test_record(
        project_id=project_id,
        step_id=step_id,
        sample_name=sample_name,
        measured_product="Naringenin",
        titer="120 mg/L",
        yield_value="0.18 g/g",
        productivity="4.2 mg/L/h",
        intermediate_accumulation="Low chalcone accumulation",
        enzyme_activity="Detected",
        growth_status="Normal growth",
        condition="Shake flask, 30 C, 24 h",
        notes="Documentation-only test record.",
    )
    assert ok is True, message
    assert test_id is not None
    return test_id


def test_create_and_list_project_level_pathway_test_record(monkeypatch):
    _use_temp_db(monkeypatch)
    project_id = _create_project()
    test_id = _create_test_record(project_id)

    records = repo.list_pathway_test_records(project_id)
    assert len(records) == 1
    record = records[0]
    assert record["id"] == test_id
    assert record["project_id"] == project_id
    assert record["step_id"] is None
    assert record["sample_name"] == "Sample A"
    assert record["measured_product"] == "Naringenin"
    assert record["titer"] == "120 mg/L"
    assert record["yield_value"] == "0.18 g/g"
    assert record["productivity"] == "4.2 mg/L/h"
    assert record["intermediate_accumulation"] == "Low chalcone accumulation"
    assert record["enzyme_activity"] == "Detected"
    assert record["growth_status"] == "Normal growth"
    assert record["condition"] == "Shake flask, 30 C, 24 h"
    assert record["notes"] == "Documentation-only test record."
    assert record["created_at"]
    assert record["updated_at"]


def test_create_and_list_step_associated_pathway_test_record(monkeypatch):
    _use_temp_db(monkeypatch)
    project_id = _create_project()
    step_id = _create_step(project_id)
    test_id = _create_test_record(project_id, step_id=step_id, sample_name="Step sample")

    records = repo.list_pathway_test_records(project_id)
    assert len(records) == 1
    assert records[0]["id"] == test_id
    assert records[0]["step_id"] == step_id
    assert records[0]["sample_name"] == "Step sample"
    assert records[0]["step_order"] == 1
    assert records[0]["step_name"] == "Starter step"
    assert records[0]["reaction_name"] == "Starter reaction"


def test_pathway_test_record_validates_required_inputs(monkeypatch):
    _use_temp_db(monkeypatch)
    project_a = _create_project("Project A")
    project_b = _create_project("Project B")
    step_b = _create_step(project_b)

    ok, message, test_id = repo.create_pathway_test_record(project_id=project_a, sample_name="")
    assert ok is False
    assert test_id is None
    assert message == "Sample name is required."

    ok, message, test_id = repo.create_pathway_test_record(project_id=9999, sample_name="Sample A")
    assert ok is False
    assert test_id is None
    assert message == "Pathway project was not found."

    ok, message, test_id = repo.create_pathway_test_record(project_id=project_a, step_id=9999, sample_name="Sample A")
    assert ok is False
    assert test_id is None
    assert message == "Pathway step was not found."

    ok, message, test_id = repo.create_pathway_test_record(project_id=project_a, step_id=step_b, sample_name="Sample A")
    assert ok is False
    assert test_id is None
    assert message == "Pathway step does not belong to the project."
    assert repo.list_pathway_test_records(project_a) == []
    assert repo.list_pathway_test_records(project_b) == []


def test_update_pathway_test_record_and_clear_step_link(monkeypatch):
    _use_temp_db(monkeypatch)
    project_id = _create_project()
    step_id = _create_step(project_id)
    test_id = _create_test_record(project_id, step_id=step_id)

    ok, message = repo.update_pathway_test_record(
        test_id,
        {
            "step_id": "",
            "sample_name": "Updated sample",
            "measured_product": "Updated product",
            "titer": "140 mg/L",
            "yield_value": "0.20 g/g",
            "productivity": "4.8 mg/L/h",
            "intermediate_accumulation": "Moderate intermediate signal",
            "enzyme_activity": "High activity",
            "growth_status": "Slow growth",
            "condition": "Bioreactor screening condition",
            "notes": "Updated documentation note.",
            "ignored_field": "ignored",
        },
    )
    assert ok is True, message

    record = repo.list_pathway_test_records(project_id)[0]
    assert record["step_id"] is None
    assert record["sample_name"] == "Updated sample"
    assert record["measured_product"] == "Updated product"
    assert record["titer"] == "140 mg/L"
    assert record["yield_value"] == "0.20 g/g"
    assert record["productivity"] == "4.8 mg/L/h"
    assert record["intermediate_accumulation"] == "Moderate intermediate signal"
    assert record["enzyme_activity"] == "High activity"
    assert record["growth_status"] == "Slow growth"
    assert record["condition"] == "Bioreactor screening condition"
    assert record["notes"] == "Updated documentation note."
    assert "ignored_field" not in record


def test_update_pathway_test_record_validates_inputs(monkeypatch):
    _use_temp_db(monkeypatch)
    project_a = _create_project("Project A")
    project_b = _create_project("Project B")
    step_b = _create_step(project_b)
    test_id = _create_test_record(project_a)

    ok, message = repo.update_pathway_test_record(test_id, {"sample_name": ""})
    assert ok is False
    assert message == "Sample name is required."

    ok, message = repo.update_pathway_test_record(test_id, {"step_id": 9999})
    assert ok is False
    assert message == "Pathway step was not found."

    ok, message = repo.update_pathway_test_record(test_id, {"step_id": step_b})
    assert ok is False
    assert message == "Pathway step does not belong to the project."

    ok, message = repo.update_pathway_test_record("not-an-id", {"sample_name": "No-op"})
    assert ok is False
    assert message == "Invalid test record id."


def test_delete_pathway_test_record(monkeypatch):
    _use_temp_db(monkeypatch)
    project_id = _create_project()
    test_id = _create_test_record(project_id)

    ok, message = repo.delete_pathway_test_record(test_id)
    assert ok is True, message
    assert repo.list_pathway_test_records(project_id) == []

    ok, message = repo.delete_pathway_test_record(test_id)
    assert ok is False
    assert message == "Pathway test record was not found."

    ok, message = repo.delete_pathway_test_record("not-an-id")
    assert ok is False
    assert message == "Invalid test record id."


def test_delete_project_removes_pathway_test_records(monkeypatch):
    _use_temp_db(monkeypatch)
    project_id = _create_project()
    step_id = _create_step(project_id)
    _create_test_record(project_id, sample_name="Project sample")
    _create_test_record(project_id, step_id=step_id, sample_name="Step sample")

    assert len(repo.list_pathway_test_records(project_id)) == 2

    ok, message = repo.delete_pathway_project(project_id)
    assert ok is True, message
    assert repo.list_pathway_test_records(project_id) == []


def test_delete_step_clears_pathway_test_record_step_id(monkeypatch):
    _use_temp_db(monkeypatch)
    project_id = _create_project()
    step_id = _create_step(project_id)
    test_id = _create_test_record(project_id, step_id=step_id)

    ok, message = repo.delete_pathway_step(step_id)
    assert ok is True, message

    records = repo.list_pathway_test_records(project_id)
    assert len(records) == 1
    assert records[0]["id"] == test_id
    assert records[0]["step_id"] is None
