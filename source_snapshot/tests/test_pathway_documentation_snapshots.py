from __future__ import annotations

import copy
import json
import os
import sqlite3
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import pathway_repository as repo
from services.pathway_bottleneck_service import analyze_pathway_bottlenecks
from services.pathway_completeness_service import build_pathway_completeness
from services.pathway_snapshot_service import (
    DOCUMENTATION_SNAPSHOT_BOUNDARY_STATEMENT,
    DOCUMENTATION_SNAPSHOT_SCHEMA_VERSION,
    build_documentation_snapshot_payload,
    create_documentation_snapshot,
    get_documentation_snapshot,
    list_documentation_snapshots,
)


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "pathway_documentation_snapshots.db"
    monkeypatch.setattr(repo, "DB_PATH", str(db_path))


def _project() -> int:
    ok, message, project_id = repo.create_pathway_project(
        name="Naringenin Pathway",
        target_product="Naringenin",
        host="E. coli BL21(DE3)",
        description="Documentation snapshot test project.",
    )
    assert ok, message
    assert project_id is not None
    return project_id


def _step(project_id: int) -> int:
    ok, message, step_id = repo.create_pathway_step(
        project_id=project_id,
        step_order=1,
        step_name="Chalcone synthesis",
        reaction_name="Condensation",
        substrate="p-Coumaroyl-CoA",
        product="Naringenin chalcone",
        enzyme_name="CHS",
        gene_name="chs",
        gene_sequence="ATGAAATAA",
        notes="Original step note.",
    )
    assert ok, message
    assert step_id is not None
    return step_id


def _design(project_id: int, step_id: int) -> None:
    ok, message, link_id = repo.link_expression_design_to_step(
        project_id=project_id,
        step_id=step_id,
        design_name="chs expression design",
        design_snapshot_json=json.dumps({"design": "snapshot"}),
        validation_summary_json=json.dumps({"primer_risk": "not recommended"}),
    )
    assert ok, message
    assert link_id is not None


def _test_record(project_id: int, step_id: int) -> int:
    ok, message, test_id = repo.create_pathway_test_record(
        project_id=project_id,
        step_id=step_id,
        sample_name="Sample 1",
        measured_product="Naringenin",
        titer="120 mg/L",
        yield_value="0.18 g/g",
        productivity="4.2 mg/L/h",
        intermediate_accumulation="Moderate",
        enzyme_activity="Recorded",
        growth_status="Normal",
        condition="Shake flask",
        notes="User observation.",
    )
    assert ok, message
    assert test_id is not None
    return test_id


def test_snapshot_round_trip_and_payload(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _project()
    step_id = _step(project_id)
    _design(project_id, step_id)
    _test_record(project_id, step_id)

    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    links = repo.list_expression_design_links(project_id)
    tests = repo.list_pathway_test_records(project_id)
    completeness = build_pathway_completeness(project, steps, links)
    suggestions = analyze_pathway_bottlenecks(
        {
            "pathway_steps": steps,
            "expression_design_links": links,
            "pathway_test_records": tests,
            "pathway_completeness": completeness,
        }
    )

    ok, message, snapshot_id = create_documentation_snapshot(
        project_id=project_id,
        snapshot_title="Local documentation snapshot",
        snapshot_note="Captured before review.",
        report_config={"include_full_gene_sequences": False, "include_project_metadata": True},
        suggestions=suggestions,
        review_notes=project.get("documentation_review", {}),
    )
    assert ok, message
    assert snapshot_id is not None

    snapshots = list_documentation_snapshots(project_id)
    assert len(snapshots) == 1
    assert snapshots[0]["id"] == snapshot_id
    assert snapshots[0]["snapshot_title"] == "Local documentation snapshot"
    assert snapshots[0]["include_generated_markdown"] is False
    assert snapshots[0]["generated_markdown_text"] is None
    assert snapshots[0]["schema_version"] == DOCUMENTATION_SNAPSHOT_SCHEMA_VERSION

    loaded = get_documentation_snapshot(snapshot_id)
    payload = loaded["snapshot_payload"]
    assert payload["boundary_statement"] == DOCUMENTATION_SNAPSHOT_BOUNDARY_STATEMENT
    assert payload["project"]["id"] == project_id
    assert payload["pathway_steps"]
    assert payload["linked_expression_designs"]
    assert payload["test_records"]
    assert payload["suggestions"] == suggestions
    assert payload["review_notes"] == project.get("documentation_review", {})
    assert payload["report_configuration"]["include_full_gene_sequences"] is False
    assert payload["generated_markdown"] == {"included": False, "text": None}


def test_snapshot_preserves_original_json_after_source_changes(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _project()
    step_id = _step(project_id)
    _design(project_id, step_id)
    _test_record(project_id, step_id)

    ok, message, snapshot_id = create_documentation_snapshot(project_id=project_id, snapshot_title="Initial snapshot")
    assert ok, message
    assert snapshot_id is not None

    before = copy.deepcopy(get_documentation_snapshot(snapshot_id)["snapshot_payload"])
    ok, message = repo.update_pathway_step(step_id, {"step_name": "Updated step name", "gene_sequence": "ATGCCCCCC"})
    assert ok, message
    ok, message = repo.update_pathway_test_record(repo.list_pathway_test_records(project_id)[0]["id"], {"notes": "Changed"})
    assert ok, message

    after = get_documentation_snapshot(snapshot_id)["snapshot_payload"]
    assert after == before
    assert after["pathway_steps"][0]["step_name"] == "Chalcone synthesis"
    assert after["test_records"][0]["notes"] == "User observation."


def test_minimal_title_defaults_and_markdown_optional(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _project()

    ok, message, snapshot_id = create_documentation_snapshot(project_id=project_id, snapshot_title="   ")
    assert ok, message
    assert snapshot_id is not None

    snapshot = get_documentation_snapshot(snapshot_id)
    assert snapshot["snapshot_title"] == "Untitled Documentation Snapshot"
    assert snapshot["snapshot_note"] == ""
    assert snapshot["generated_markdown_text"] is None
    assert snapshot["include_generated_markdown"] is False

    ok, message, markdown_snapshot_id = create_documentation_snapshot(
        project_id=project_id,
        snapshot_title="Markdown snapshot",
        generated_markdown_text="# Snapshot report\nDocumentation only.",
        include_generated_markdown=True,
    )
    assert ok, message
    assert markdown_snapshot_id is not None
    markdown_snapshot = get_documentation_snapshot(markdown_snapshot_id)
    assert markdown_snapshot["include_generated_markdown"] is True
    assert markdown_snapshot["generated_markdown_text"] == "# Snapshot report\nDocumentation only."
    assert markdown_snapshot["snapshot_payload"]["generated_markdown"] == {
        "included": True,
        "text": "# Snapshot report\nDocumentation only.",
    }


def test_snapshot_build_payload_and_non_destructive_semantics(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _project()
    step_id = _step(project_id)
    _design(project_id, step_id)
    _test_record(project_id, step_id)

    project = repo.get_pathway_project(project_id)
    steps = repo.list_pathway_steps(project_id)
    links = repo.list_expression_design_links(project_id)
    tests = repo.list_pathway_test_records(project_id)
    completeness_before = build_pathway_completeness(project, steps, links)
    suggestions_before = analyze_pathway_bottlenecks(
        {
            "pathway_steps": steps,
            "expression_design_links": links,
            "pathway_test_records": tests,
            "pathway_completeness": completeness_before,
        }
    )
    review_before = project.get("documentation_review", {})

    ok, message, payload = build_documentation_snapshot_payload(
        project_id=project_id,
        snapshot_title="Payload only",
        snapshot_note="Structure check.",
        report_config={"include_full_gene_sequences": True},
        review_notes=review_before,
        suggestions=[{"signal_type": "review_only"}],
    )
    assert ok, message
    assert payload["schema_version"] == DOCUMENTATION_SNAPSHOT_SCHEMA_VERSION
    assert payload["boundary_statement"] == DOCUMENTATION_SNAPSHOT_BOUNDARY_STATEMENT
    assert payload["snapshot_metadata"]["snapshot_title"] == "Payload only"
    assert payload["report_configuration"]["include_full_gene_sequences"] is True
    assert payload["generated_markdown"] == {"included": False, "text": None}
    assert payload["review_notes"] == review_before
    assert payload["suggestions"] == [{"signal_type": "review_only"}]

    ok, message, _ = create_documentation_snapshot(
        project_id=project_id,
        snapshot_title="Non-destructive snapshot",
        review_notes=review_before,
        suggestions=suggestions_before,
    )
    assert ok, message
    assert build_pathway_completeness(project, steps, links) == completeness_before
    assert analyze_pathway_bottlenecks(
        {
            "pathway_steps": steps,
            "expression_design_links": links,
            "pathway_test_records": tests,
            "pathway_completeness": completeness_before,
        }
    ) == suggestions_before
    assert repo.get_pathway_project(project_id)["documentation_review"] == review_before


def test_snapshot_persistence_is_local_and_additive(tmp_path, monkeypatch):
    db_path = tmp_path / "pathway_documentation_snapshots.db"
    _use_temp_db(tmp_path, monkeypatch)
    project_id = _project()
    step_id = _step(project_id)
    _design(project_id, step_id)
    _test_record(project_id, step_id)

    before_steps = repo.list_pathway_steps(project_id)
    before_links = repo.list_expression_design_links(project_id)
    before_tests = repo.list_pathway_test_records(project_id)

    ok, message, snapshot_id = create_documentation_snapshot(project_id=project_id, snapshot_title="Local snapshot")
    assert ok, message
    assert snapshot_id is not None

    assert repo.list_pathway_steps(project_id) == before_steps
    assert repo.list_expression_design_links(project_id) == before_links
    assert repo.list_pathway_test_records(project_id) == before_tests

    conn = sqlite3.connect(str(db_path))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM pathway_documentation_snapshots WHERE project_id = ?",
            (project_id,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == 1
