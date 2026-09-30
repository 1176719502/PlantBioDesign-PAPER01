from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.documentation_consistency_provenance_view_model import (
    STATUS_AVAILABLE,
    STATUS_COMPLETE,
    STATUS_HUMAN_REVIEW_NEEDED,
    STATUS_NOT_AVAILABLE,
    build_documentation_consistency_provenance_panel,
)


def _section(panel: dict, key: str) -> dict:
    return panel["sections"][key]


def _all_output_text(panel: dict) -> str:
    return str(panel).lower()


def test_minimal_project_builds_panel_without_package_or_duplicate_context() -> None:
    panel = build_documentation_consistency_provenance_panel(project={"id": 1, "name": "Minimal"})

    assert panel["panel_title"] == "Documentation Consistency / Provenance"
    assert panel["summary"]["section_count"] == 6
    assert "duplicate_guard_context" not in panel["sections"]
    assert _section(panel, "metadata_completeness")["status"] == STATUS_HUMAN_REVIEW_NEEDED
    assert _section(panel, "snapshot_coverage")["status"] == STATUS_HUMAN_REVIEW_NEEDED
    assert _section(panel, "package_review_context")["status"] == STATUS_NOT_AVAILABLE


def test_project_with_missing_sequences_and_metadata_marks_human_review_needed() -> None:
    panel = build_documentation_consistency_provenance_panel(
        project={"id": 2, "name": "Pathway", "target_product": "", "host": "", "status": "draft"},
        steps=[
            {
                "id": 10,
                "step_order": 1,
                "step_name": "Step A",
                "substrate": "Input",
                "product": "Output",
                "enzyme_name": "",
                "gene_name": "geneA",
                "gene_sequence": "",
            }
        ],
    )

    metadata = _section(panel, "metadata_completeness")
    assert metadata["status"] == STATUS_HUMAN_REVIEW_NEEDED
    assert "metadata completeness" in panel["boundary_note"]
    assert any("gene sequence" in item["detail"] for item in metadata["items"])


def test_missing_linked_design_coverage_is_summarized_by_step() -> None:
    panel = build_documentation_consistency_provenance_panel(
        project={"id": 3, "name": "Links", "target_product": "Product", "host": "Host", "description": "Doc", "status": "draft"},
        steps=[
            {"id": 10, "step_order": 1, "step_name": "Step A", "substrate": "A", "product": "B", "enzyme_name": "E", "gene_name": "g", "gene_sequence": "ATG", "organism_source": "Source"},
            {"id": 11, "step_order": 2, "step_name": "Step B", "substrate": "B", "product": "C", "enzyme_name": "E", "gene_name": "g", "gene_sequence": "ATG", "organism_source": "Source"},
        ],
        expression_links=[{"id": 20, "step_id": 10, "design_name": "Design A"}],
    )

    coverage = _section(panel, "linked_record_coverage")
    assert coverage["status"] == STATUS_HUMAN_REVIEW_NEEDED
    assert any("1 pathway step(s) have no linked design record" in item["detail"] for item in coverage["items"])


def test_snapshot_coverage_handles_present_and_absent_snapshots() -> None:
    absent = build_documentation_consistency_provenance_panel(project={"id": 4, "name": "No snapshots"})
    present = build_documentation_consistency_provenance_panel(
        project={"id": 5, "name": "Snapshots"},
        snapshots=[
            {"id": 1, "snapshot_title": "One", "include_generated_markdown": False},
            {"id": 2, "snapshot_title": "Two", "include_generated_markdown": True},
        ],
    )

    assert _section(absent, "snapshot_coverage")["status"] == STATUS_HUMAN_REVIEW_NEEDED
    assert _section(present, "snapshot_coverage")["status"] == STATUS_AVAILABLE
    assert any("2 documentation snapshot(s)" in item["detail"] for item in _section(present, "snapshot_coverage")["items"])
    assert any("1 documentation snapshot(s) include generated Markdown" in item["detail"] for item in _section(present, "snapshot_coverage")["items"])


def test_unresolved_review_notes_and_follow_up_actions_are_human_review_needed() -> None:
    panel = build_documentation_consistency_provenance_panel(
        project={
            "id": 6,
            "name": "Review",
            "documentation_review": {
                "review_items": {"pathway_description_reviewed": True, "gene_entries_reviewed": False},
                "review_notes": "Reviewer note.",
                "unresolved_items": "Missing source note.",
                "follow_up_actions": "Check linked design context.",
            },
        },
    )

    review = _section(panel, "review_notes_follow_up")
    assert review["status"] == STATUS_HUMAN_REVIEW_NEEDED
    assert any("1 checklist item(s) remain unchecked" in item["detail"] for item in review["items"])
    assert any("1 unresolved review note field(s)" in item["detail"] for item in review["items"])
    assert any("1 follow-up action field(s)" in item["detail"] for item in review["items"])


def test_optional_package_and_duplicate_context_are_read_only_and_optional() -> None:
    no_context = build_documentation_consistency_provenance_panel(project={"id": 7, "name": "Optional"})
    with_context = build_documentation_consistency_provenance_panel(
        project={"id": 8, "name": "Optional"},
        export_summary={"status": "AVAILABLE"},
        import_summary={"overall_status": "WARNING"},
        duplicate_guard_context={"matches": [{"project_id": 1, "project_name": "Existing"}]},
    )

    assert _section(no_context, "package_review_context")["status"] == STATUS_NOT_AVAILABLE
    assert "duplicate_guard_context" not in no_context["sections"]
    assert _section(with_context, "package_review_context")["status"] == STATUS_AVAILABLE
    assert _section(with_context, "duplicate_guard_context")["status"] == STATUS_HUMAN_REVIEW_NEEDED


def test_summary_human_review_count_matches_listed_sections() -> None:
    panel = build_documentation_consistency_provenance_panel(
        project={"id": 11, "name": "Summary", "status": "draft"},
        steps=[{"id": 10, "step_order": 1, "step_name": "Step A"}],
        expression_links=[{"id": 20, "step_id": 999, "design_name": "Stale design"}],
        review_signals=[{"id": 30, "related_step_id": 999, "signal_type": "stale_signal"}],
        duplicate_guard_context={"matches": [{"project_id": 1, "project_name": "Existing"}]},
    )
    summary = panel["summary"]
    listed = summary["human_review_needed_sections"]

    assert summary["human_review_needed_count"] == len(listed)
    assert set(listed) == {
        key
        for key, section in panel["sections"].items()
        if section["status"] == STATUS_HUMAN_REVIEW_NEEDED
    }
    assert "metadata_completeness" in listed
    assert "traceability_gaps" in listed
    assert "duplicate_guard_context" in listed


def test_complete_local_records_can_report_complete_core_sections() -> None:
    review = {"review_items": {"one": True}, "review_notes": "Reviewed for documentation consistency."}
    panel = build_documentation_consistency_provenance_panel(
        project={
            "id": 9,
            "name": "Complete",
            "target_product": "Product",
            "host": "Host",
            "description": "Documentation project.",
            "status": "draft",
            "documentation_review": review,
        },
        steps=[
            {"id": 10, "step_order": 1, "step_name": "Step", "substrate": "A", "product": "B", "enzyme_name": "E", "gene_name": "g", "gene_sequence": "ATG", "organism_source": "Source"}
        ],
        expression_links=[{"id": 20, "step_id": 10, "design_name": "Design"}],
        snapshots=[{"id": 30, "snapshot_title": "Snapshot"}],
        documentation_review=review,
    )

    assert _section(panel, "metadata_completeness")["status"] == STATUS_COMPLETE
    assert _section(panel, "linked_record_coverage")["status"] == STATUS_COMPLETE
    assert _section(panel, "review_notes_follow_up")["status"] == STATUS_COMPLETE


def test_view_model_copy_avoids_forbidden_claims() -> None:
    panel = build_documentation_consistency_provenance_panel(project={"id": 10, "name": "Copy"})
    text = _all_output_text(panel)

    for phrase in [
        "approval",
        "validated",
        "ready",
        "certified",
        "experimentally confirmed",
        "successful import",
        "production-ready",
        "optimized pathway",
        "yield prediction",
        "wet-lab",
    ]:
        assert phrase not in text
