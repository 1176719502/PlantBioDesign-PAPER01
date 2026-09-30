# -*- coding: utf-8 -*-
"""V2.6-R21 construct documentation report integration tests."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import expression_construct_repository as construct_repo
from services import expression_construct_presenter as presenter
from services.project_review_report_service import build_project_review_report
import views.ExpressionConstructs as expression_constructs_view
import views.pathway_workspace_sections.project_quality_dashboard_section as dashboard_view


def _use_temp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "expression_construct_report.db"
    monkeypatch.setattr(construct_repo, "DB_PATH", str(db_path))
    return db_path


def _seed_construct(*, pathway_step_id: str = "step-1", with_parts: bool = True) -> dict:
    profile = construct_repo.create_construct_profile(
        construct_id="construct-r21",
        construct_label="R21 documentation construct",
        construct_type="multi-cassette documentation record",
        plasmid_backbone="pDOC-R21",
        host_context_note="Host context retained as documentation only.",
        source_reference="Construct notebook",
        provenance_note="Construct provenance note.",
        review_status="documentation review pending",
        documentation_scope_note="Documentation-only construct record.",
    )
    cassette = construct_repo.create_construct_cassette(
        profile["construct_id"],
        cassette_id="cassette-r21",
        cassette_label="Expression cassette R21",
        cassette_role="expression cassette record",
        cassette_order=1,
        promoter_label="Manual promoter label",
        gene_label="geneR",
        terminator_label="terminatorR",
        source_reference="Cassette notebook",
        provenance_note="Cassette provenance note.",
    )
    if with_parts:
        construct_repo.add_construct_cassette_part(
            cassette["cassette_id"],
            part_order=1,
            part_role="promoter",
            part_label="Plant promoter context row",
            part_reference="promoter-ref",
            source_reference="Manual source note",
            source_catalog="Plant Promoter Catalog",
            source_record_id="plant-promoter-r21",
            source_record_label="Plant promoter source record R21",
            evidence_context_note="source context retained for documentation review",
            provenance_note="Promoter provenance note.",
        )
        construct_repo.add_construct_cassette_part(
            cassette["cassette_id"],
            part_order=2,
            part_role="cds",
            part_label="geneR CDS",
            part_reference="geneR-ref",
            source_reference="CDS source note",
            provenance_note="CDS provenance note.",
        )
    construct_repo.add_construct_gene_link(
        profile["construct_id"],
        gene_label="geneR",
        gene_reference="geneR-reference",
        source_reference="Gene source note",
        provenance_note="Gene provenance note.",
    )
    construct_repo.add_construct_pathway_step_link(
        profile["construct_id"],
        pathway_step_id=pathway_step_id,
        pathway_step_label="Pathway step R21",
        source_reference="Pathway map",
        provenance_note="Pathway provenance note.",
    )
    return profile


def test_report_includes_construct_section_with_rows_and_boundary_copy(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _seed_construct()

    report = build_project_review_report(
        {
            "id": 21,
            "name": "R21 report project",
            "pathway_steps": [{"id": "step-1", "step_name": "Pathway step R21"}],
        }
    )
    section = report["expression_construct_documentation"]
    draft_markdown = report["detailed_documentation_report_draft"]["markdown"]

    assert section["status"] == "AVAILABLE"
    assert section["project_scoped_filtering"] == "pathway_step_id links"
    assert section["summary_counts"] == {
        "construct_profile_count": 1,
        "cassette_count": 1,
        "cassette_part_count": 2,
        "gene_link_count": 1,
        "pathway_step_link_count": 1,
        "project_link_count": 0,
        "review_gap_count": 0,
    }
    assert section["construct_component_review_summary"] == {
        "total_component_rows": 2,
        "rows_with_source_reference_context": 2,
        "rows_missing_source_reference_context": 0,
        "rows_with_sequence_availability_note": 2,
        "rows_with_conservation_review_context": 2,
        "rows_needing_conservation_follow_up": 0,
        "rows_with_review_metadata_status": 2,
        "rows_with_review_note": 2,
        "rows_needing_manual_follow_up": 0,
    }
    assert section["construct_component_gap_queue"] == []
    assert "## Expression Construct Documentation" in report["markdown"]
    assert "### Construct review summary" in report["markdown"]
    assert "### Manual follow-up queue" in report["markdown"]
    assert "| Review concept | Count |" in report["markdown"]
    assert "Component rows reviewed" in report["markdown"]
    assert "Source/reference context" in report["markdown"]
    assert "Missing source/reference context" in report["markdown"]
    assert "Sequence availability note" in report["markdown"]
    assert "Record review status" in report["markdown"]
    assert "Documentation follow-up" in report["markdown"]
    assert (
        "| Component label | Component category | Source/reference context | Sequence availability note | "
        "Conservation review evidence | Conservation follow-up cue | Record review status | Review note | Cassette label |"
        in report["markdown"]
    )
    assert "R21 documentation construct" in report["markdown"]
    assert "Expression cassette R21" in draft_markdown
    assert "Plant promoter source record R21" in draft_markdown
    assert "source context retained for documentation review" in draft_markdown
    assert "geneR-reference" in draft_markdown
    assert "Pathway step R21" in draft_markdown
    assert "Documentation-only construct, cassette, part" not in report["markdown"]
    assert "Promoter source links are evidence and provenance context, not selection advice." in draft_markdown
    assert "does not choose, rate, order, tune, forecast, verify, or certify downstream-use state" in draft_markdown


def test_report_handles_no_construct_data(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)

    report = build_project_review_report({"id": 22, "name": "No construct data"})
    section = report["expression_construct_documentation"]

    assert section["status"] == "NOT_AVAILABLE"
    assert section["summary_counts"]["construct_profile_count"] == 0
    assert "No expression construct documentation records are available for this report." in report["markdown"]
    assert "Expression construct documentation is documentation-only context for review and traceability." in report["markdown"]


def test_report_includes_review_gaps_for_incomplete_construct_rows(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    profile = construct_repo.create_construct_profile(construct_label="Incomplete construct report row")
    cassette = construct_repo.create_construct_cassette(profile["construct_id"], cassette_label="Cassette with incomplete part")
    construct_repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="terminator",
        part_label="Incomplete terminator context",
        part_reference="",
        source_reference="",
        source_record_id="",
        source_record_label="",
        provenance_note="",
    )

    report = build_project_review_report({"id": 23, "name": "Incomplete construct"})
    section = report["expression_construct_documentation"]

    gap_types = {row["Gap type"] for row in section["review_gap_rows"]}
    assert "part provenance" in gap_types
    assert "gene links" in gap_types
    assert "pathway step links" in gap_types
    assert section["construct_component_review_summary"]["rows_missing_source_reference_context"] == 1
    assert section["construct_component_review_summary"]["rows_needing_manual_follow_up"] == 1
    assert [row["Issue type"] for row in section["construct_component_gap_queue"]] == [
        "Missing source/reference context",
        "Missing provenance context",
        "Missing sequence availability note",
        "Needs conservation check",
    ]
    assert section["summary_counts"]["review_gap_count"] >= 3
    assert "Construct review gap" in report["markdown"]
    assert "Manual follow-up queue" in report["markdown"]
    assert "Incomplete terminator context" in report["markdown"]
    assert "Missing source/reference context" in report["markdown"]
    assert "| Construct label | Cassette label | Component label | Component category | Issue type | Issue detail | Manual follow-up note |" in report["markdown"]
    assert "manual documentation follow-up" in report["markdown"]


def test_construct_review_queue_language_aligns_across_read_only_surfaces(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    profile = construct_repo.create_construct_profile(construct_label="Cross-surface construct")
    cassette = construct_repo.create_construct_cassette(profile["construct_id"], cassette_label="Cross-surface cassette")
    construct_repo.add_construct_cassette_part(
        cassette["cassette_id"],
        part_order=1,
        part_role="terminator",
        part_label="Cross-surface terminator",
        part_reference="",
        source_reference="",
        source_record_id="",
        source_record_label="",
        provenance_note="",
    )

    report = build_project_review_report({"id": 175, "name": "Cross-surface report"})
    queue_rows = report["expression_construct_documentation"]["construct_component_gap_queue"]
    dashboard_rows = dashboard_view._expression_construct_follow_up_table_rows({"rows": queue_rows})

    assert expression_constructs_view.COMPONENT_GAP_QUEUE_COLUMNS == presenter.COMPONENT_GAP_QUEUE_COLUMNS
    assert list(dashboard_rows[0]) == presenter.COMPONENT_GAP_QUEUE_COLUMNS
    for shared_label in presenter.COMPONENT_GAP_QUEUE_COLUMNS:
        assert shared_label in report["markdown"]
    for shared_label in presenter.COMPONENT_REVIEW_SUMMARY_LABELS.values():
        assert shared_label in report["markdown"]

    assert dashboard_rows[0]["Issue type"] == "Missing source/reference context"
    assert "Missing source/reference context" in report["markdown"]
    assert "Manual follow-up note" in expression_constructs_view.COMPONENT_GAP_QUEUE_COLUMNS
    assert "Manual follow-up note" in dashboard_rows[0]
    assert "Manual follow-up note" in report["markdown"]


def test_component_ambiguity_follow_up_reaches_report_and_dashboard_rows(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    profile = construct_repo.create_construct_profile(
        construct_label="Ambiguity follow-up construct",
        source_reference="Construct source",
        provenance_note="Construct provenance.",
    )
    cassette = construct_repo.create_construct_cassette(
        profile["construct_id"],
        cassette_label="Ambiguity cassette",
        source_reference="Cassette source",
        provenance_note="Cassette provenance.",
    )
    for order in (1, 2):
        construct_repo.add_construct_cassette_part(
            cassette["cassette_id"],
            part_order=order,
            part_role="other",
            part_label="Repeated manual component",
            part_reference="manual-component-ref",
            source_reference="Manual source note",
            source_record_id="",
            source_record_label="",
            provenance_note="Manual provenance note.",
        )

    report = build_project_review_report({"id": 211, "name": "R211 ambiguity report"})
    queue_rows = report["expression_construct_documentation"]["construct_component_gap_queue"]
    dashboard_rows = dashboard_view._expression_construct_follow_up_table_rows({"rows": queue_rows})

    assert [row["Issue type"] for row in queue_rows] == [
        presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
        presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
        presenter.DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE,
    ]
    assert [row["Issue type"] for row in dashboard_rows] == [
        presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
        presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
        presenter.DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE,
    ]
    assert "Review component role documentation" in report["markdown"]
    assert "Review duplicate component label" in report["markdown"]
    assert "Manual documentation follow-up" in report["markdown"]
    assert "Repeated manual component" in report["markdown"]
    assert report["expression_construct_documentation"]["construct_component_review_summary"][
        "rows_needing_manual_follow_up"
    ] == 1


def test_report_filters_constructs_by_existing_pathway_step_links(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _seed_construct(pathway_step_id="step-in-scope")
    other = construct_repo.create_construct_profile(
        construct_id="construct-other",
        construct_label="Out of scope construct",
    )
    construct_repo.add_construct_pathway_step_link(
        other["construct_id"],
        pathway_step_id="step-out-of-scope",
        pathway_step_label="Other pathway step",
    )

    report = build_project_review_report(
        {
            "id": 24,
            "name": "Scoped construct project",
            "pathway_steps": [{"id": "step-in-scope", "step_name": "Scoped step"}],
        }
    )

    assert report["expression_construct_documentation"]["summary_counts"]["construct_profile_count"] == 1
    assert "R21 documentation construct" in report["markdown"]
    assert "Out of scope construct" not in report["markdown"]


def test_report_construct_section_avoids_unsafe_copy(tmp_path, monkeypatch):
    _use_temp_db(tmp_path, monkeypatch)
    _seed_construct()

    text = str(build_project_review_report({"id": 25, "name": "Unsafe copy scan"})).lower()
    forbidden = [
        "best promoter",
        "host compatibility",
        "ready for synthesis",
        "ready for wet lab",
        "transformation protocol",
        "experimentally confirmed",
        "expression prediction",
        "yield improvement",
        "validated construct",
        "optimized pathway",
    ]

    assert [phrase for phrase in forbidden if phrase in text] == []
