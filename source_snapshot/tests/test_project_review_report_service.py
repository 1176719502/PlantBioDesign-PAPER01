from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_review_report_service import build_project_review_report
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services import expression_construct_presenter as construct_presenter
from tests.helpers.sqlite_test_utils import repo_local_sqlite_db_path


def _empty_construct_report_views(monkeypatch) -> None:
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [],
    )


EXPECTED_DETAILED_REPORT_SECTIONS = [
    "## Project summary",
    "## Research context placeholder",
    "## Local Design Asset Catalog context",
    "## Linked Catalog Assets",
    "## Expression Construct Documentation",
    "## Pathway / Expression Wizard documentation state",
    "## Provenance and source review notes",
    "## Traceability summary",
    "## Data completeness / missing documentation fields",
    "## Human review questions",
    "## Known limitations",
    "## Documentation-only boundary note",
]


def test_minimal_project_generates_report_with_expected_missing_fields(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report({"id": 1, "name": "Minimal"})

    assert report["report_title"] == "Project Review Report"
    assert "# Project Review Report" in report["markdown"]
    gap_ids = {gap["gap_id"] for gap in report["missing_fields"]}
    assert "no_pathway_steps_documented" in gap_ids
    assert "no_linked_documentation_artifacts" in gap_ids
    assert "no_saved_design_snapshot_linked" in gap_ids
    assert "no_import_safety_check_report_attached" in gap_ids


def test_detailed_documentation_report_draft_contains_expected_sections(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {
            "id": 12,
            "name": "Teacher handoff project",
            "target_product": "albumin",
            "description": "Classroom documentation example.",
            "pathway_steps": [
                {
                    "id": 1,
                    "step_order": 1,
                    "step_name": "Context review",
                    "organism_source": "Recorded source context",
                    "enzyme_name": "Recorded enzyme context",
                    "gene_name": "recorded_gene",
                }
            ],
        },
        linked_artifacts=[
            {
                "id": 1,
                "artifact_type": "research_brief",
                "title": "Local research context",
                "source_module": "AI Literature Research",
            }
        ],
        expression_links=[{"id": 2, "design_id": "design-2", "design_name": "Expression design record"}],
        test_records=[{"id": 3, "sample_name": "Observation record"}],
        snapshots=[{"id": 4, "title": "Documentation snapshot"}],
        review_signals=[{"signal_type": "source_review_needed"}],
        completeness_result={"score": 75, "status": "partial"},
    )

    draft = report["detailed_documentation_report_draft"]
    markdown = draft["markdown"]

    assert draft["report_title"] == "Detailed Documentation Report Draft"
    for section in EXPECTED_DETAILED_REPORT_SECTIONS:
        assert section in markdown
    assert "documentation report draft" in markdown
    assert "source review needed" in markdown
    assert "human review required" in markdown
    assert "provenance context" in markdown
    assert "data completeness review" in markdown
    assert "traceability summary" in markdown.lower()
    assert draft["catalog_context"]["record_count"] >= 1
    assert "Linked catalog assets are documentation references only." in markdown
    assert "They do not indicate biological fit, source verification, or downstream use state." in markdown
    assert "Human review is required before downstream use." in markdown
    assert "No linked catalog assets were recorded for this project." in markdown
    assert draft["design_documentation_state"]["linked_expression_design_count"] == 1
    assert draft["traceability_summary"]["test_record_count"] == 1


def test_detailed_documentation_report_draft_empty_state_is_bounded(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report({"id": 13, "name": "Empty"})
    draft = report["detailed_documentation_report_draft"]
    markdown = draft["markdown"]

    assert "Pathway documentation state has no recorded steps." in markdown
    assert "No linked Expression Wizard design records supplied to this report draft." in markdown
    assert "No linked catalog assets were recorded for this project." in markdown
    assert "Unavailable records are marked NOT_AVAILABLE" in markdown
    assert "Human review required" in draft["documentation_only_boundary_note"]
    assert draft["data_completeness_review"]["missing_item_count"] >= 1


def test_detailed_documentation_report_includes_linked_catalog_assets_summary(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 16,
                "asset_id": "asset-001",
                "asset_display_name": "Local promoter documentation record",
                "asset_type": "promoter",
                "linkage_role": "project_reference",
                "documentation_note": "Documentation-only reference for project traceability.",
                "source_context_snapshot": {
                    "source_review_status": "source review needed",
                    "version_context": "seed v1",
                },
                "review_status_snapshot": {
                    "review_status": "human review needed",
                    "human_review_note": "Check source note.",
                },
                "linked_at": "2026-06-15T10:00:00Z",
                "human_review_required": True,
            },
            {
                "project_id": 16,
                "asset_id": "asset-002",
                "asset_display_name": "Local origin metadata record",
                "asset_type": "origin_metadata",
                "linkage_role": "report_context",
                "documentation_note": "Manual reference for report context.",
                "source_context_snapshot": {"source_provenance_status": "review needed"},
                "review_status_snapshot": {"review_status": "complete"},
                "linked_at": "2026-06-15T10:05:00Z",
                "human_review_required": False,
            },
        ],
    )

    report = build_project_review_report({"id": 16, "name": "Linked catalog report"})

    draft = report["detailed_documentation_report_draft"]
    linked = draft["linked_catalog_assets"]

    assert linked["total_linked_assets"] == 2
    assert linked["asset_types_represented"] == ["origin_metadata", "promoter"]
    assert linked["linkage_roles_represented"] == ["project_reference", "report_context"]
    assert linked["records_needing_human_review"] == 1
    assert linked["project_documentation_contexts"] == ["Documentation context not provided"]
    assert "Local promoter documentation record" in draft["markdown"]
    assert "Manual reference for report context." in draft["markdown"]
    assert "| Asset display name | Record identifier | Catalog/source | Catalog/source/review status | Source context readback | Review-needed context | Review gap context | Catalog reference context | Reference origin | Project documentation context | Link state | Snapshot state | Documentation note | Asset snapshot | Source context snapshot | Review status snapshot | Human review required |" in draft["markdown"]
    reference_by_id = {row["record_identifier"]: row for row in linked["linked_references"]}
    first_reference = reference_by_id["asset-001"]
    assert first_reference["catalog_name_source"] == "Local Design Asset Catalog / Source status not recorded"
    assert first_reference["catalog_source_status"] == "Local Design Asset Catalog / Source status not recorded / human review needed"
    assert first_reference["source_context_readback"] == "Source context readback: catalog Local Design Asset Catalog; source/provenance review Source status not recorded"
    assert first_reference["review_needed_context"] == "Review-needed context: curation status human review needed; human review flag yes"
    assert first_reference["metadata_gap_context"] == "Review gap: missing source context for documentation review"
    assert first_reference["catalog_reference_context"] == "Catalog reference context: origin Project documentation reference; link state Linked catalog reference; snapshot state live metadata fallback"
    assert first_reference["reference_origin"] == "Project documentation reference"
    assert first_reference["project_documentation_context"] == "Documentation context not provided"
    assert first_reference["linked_persisted_status"] == "Linked catalog reference"
    assert first_reference["documentation_note"] == "Documentation-only reference for project traceability."


def test_detailed_documentation_report_includes_plant_promoter_reference_summary(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 17,
                "asset_id": "plant-promoter-101",
                "asset_display_name": "Maize promoter profile",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-101",
                    "plant_clade": "monocot",
                    "species": "Zea mays (maize)",
                    "source_labels": "Fixture source: ROOT-101",
                },
                "review_status_snapshot": {
                    "curation_statuses": "source review needed",
                    "missing_metadata_count": 2,
                },
                "linked_at": "2026-06-17T09:00:00Z",
                "human_review_required": True,
            }
        ],
    )

    report = build_project_review_report({"id": 17, "name": "Plant promoter linked catalog report"})

    linked = report["detailed_documentation_report_draft"]["linked_catalog_assets"]
    promoter_summary = linked["plant_promoter_reference_summary"]
    markdown = report["detailed_documentation_report_draft"]["markdown"]

    assert promoter_summary["linked_promoter_count"] == 1
    assert promoter_summary["missing_metadata_count"] == 2
    assert "### Component Library promoter asset references" in markdown
    assert "Linked promoter asset reference count: 1" in markdown
    assert "Missing metadata count: 2" in markdown
    assert "Maize promoter profile" in markdown


def test_project_review_report_promotes_linked_catalog_metadata_gaps_to_missing_fields(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 172,
                "asset_id": "plant-promoter-gap-172",
                "asset_display_name": "Gap-heavy promoter profile",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-gap-172",
                },
                "review_status_snapshot": {
                    "missing_metadata_count": 2,
                },
                "human_review_required": True,
            }
        ],
    )

    report = build_project_review_report({"id": 172, "name": "Catalog review gap report"})

    gap_ids = {gap["gap_id"] for gap in report["missing_fields"]}
    assert "linked_catalog_reference_metadata_review_needed" in gap_ids
    assert "still need source/provenance or record review follow-up" in report["markdown"]
    assert "record missing source/provenance fields or record review status" in "\n".join(report["next_steps"]).lower()


def test_detailed_documentation_report_includes_wizard_catalog_traceability(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 19,
                "asset_id": "plant-promoter-101",
                "asset_display_name": "Maize promoter profile",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "design_record_context",
                "documentation_note": "Documentation-only Expression Wizard catalog context reference for project traceability.",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-101",
                    "plant_clade": "monocot",
                    "species": "Zea mays (maize)",
                    "source_labels": "Fixture source: ROOT-101",
                    "reference_origin": "Expression Wizard catalog context",
                },
                "review_status_snapshot": {
                    "curation_statuses": "source review needed",
                    "missing_metadata_count": 2,
                },
                "linked_at": "2026-06-17T09:00:00Z",
                "human_review_required": True,
            }
        ],
    )

    report = build_project_review_report({"id": 19, "name": "Wizard catalog report"})

    linked = report["detailed_documentation_report_draft"]["linked_catalog_assets"]
    traceability = linked["expression_wizard_catalog_traceability"]
    markdown = report["detailed_documentation_report_draft"]["markdown"]

    assert traceability["reference_count"] == 1
    assert traceability["plant_promoter_reference_count"] == 1
    assert traceability["missing_metadata_count"] == 2
    assert traceability["traceability_rows"][0]["reference_origin"] == "Expression Wizard catalog context"
    assert "### Expression Wizard catalog traceability" in markdown
    assert "| asset_type | asset_id | asset_label | source_label | documentation_status | linked_project_id | reference_origin | limitation_note |" in markdown


def test_detailed_documentation_report_reads_persisted_catalog_references(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_v2_6_r148_project_review_report_service_dbs",
        "review_report_links.db",
    )
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))
    project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": "17",
            "asset_id": "plant-promoter-201",
            "asset_display_name": "Persisted promoter profile",
            "asset_type": "plant_promoter_profile",
            "linkage_role": "source_review_context",
            "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-201",
                "plant_clade": "dicot",
                "species": "Arabidopsis thaliana",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 3,
            },
            "human_review_required": True,
        }
    )

    report = build_project_review_report({"id": 17, "name": "Persisted linked catalog report"})
    linked = report["detailed_documentation_report_draft"]["linked_catalog_assets"]

    assert linked["linked_catalog_asset_count"] == 1
    assert linked["linked_plant_promoter_count"] == 1
    assert linked["missing_source_or_review_metadata_count"] == 3
    assert "Persisted promoter profile" in report["detailed_documentation_report_draft"]["markdown"]
    assert linked["linked_references"][0]["linked_persisted_status"] == "Persisted linked catalog reference"


def test_detailed_documentation_report_ignores_transient_catalog_links_when_persisted_links_exist(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_v2_6_r148_project_review_report_service_dbs",
        "review_report_persisted_only_links.db",
    )
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))
    project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": "22",
            "asset_id": "persisted-only-1",
            "asset_display_name": "Persisted only reference",
            "asset_type": "plant_promoter_profile",
            "linkage_role": "source_review_context",
            "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "profile_id": "persisted-only-1",
                "plant_clade": "dicot",
                "species": "Arabidopsis thaliana",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 1,
            },
            "human_review_required": True,
        }
    )

    report = build_project_review_report(
        {
            "id": 22,
            "name": "Persisted only report",
            "project_asset_links": [
                {
                    "project_id": 22,
                    "asset_id": "transient-1",
                    "asset_display_name": "Transient reference",
                    "asset_type": "promoter",
                    "linkage_role": "project_reference",
                    "documentation_note": "Transient note",
                    "source_context_snapshot": {},
                    "review_status_snapshot": {},
                    "linked_at": "session",
                    "human_review_required": True,
                }
            ],
        }
    )
    linked = report["detailed_documentation_report_draft"]["linked_catalog_assets"]

    assert linked["linked_catalog_asset_count"] == 1
    assert "Persisted only reference" in report["detailed_documentation_report_draft"]["markdown"]
    assert "Transient reference" not in report["detailed_documentation_report_draft"]["markdown"]


def test_detailed_documentation_report_excludes_transient_only_catalog_links(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {
            "id": 122,
            "name": "Transient only report",
            "project_asset_links": [
                {
                    "project_id": 122,
                    "asset_id": "transient-only-1",
                    "asset_display_name": "Transient only reference",
                    "asset_type": "promoter",
                    "linkage_role": "project_reference",
                    "documentation_note": "Transient note",
                    "source_context_snapshot": {"project_documentation_context": "Temporary basket context"},
                    "review_status_snapshot": {},
                    "linked_at": "session",
                    "human_review_required": True,
                }
            ],
        }
    )

    linked = report["detailed_documentation_report_draft"]["linked_catalog_assets"]
    assert linked["linked_catalog_asset_count"] == 0
    assert "Transient only reference" not in report["detailed_documentation_report_draft"]["markdown"]


def test_project_review_report_includes_component_library_asset_readback_snapshot(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 206,
                "asset_id": "generic-promoter-206",
                "asset_display_name": "Generic promoter source record",
                "asset_type": "promoter",
                "linkage_role": "report_context",
                "documentation_note": "Documentation-only source context for report traceability.",
                "source_context_snapshot": {
                    "catalog": "Local Design Asset Catalog",
                    "profile_id": "generic-promoter-206",
                    "host_context": "generic host documentation context",
                    "project_documentation_context": "Project Review Report snapshot",
                },
                "review_status_snapshot": {"review_status": "human review needed"},
                "human_review_required": True,
            }
        ],
    )
    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [
            {
                "construct_profile_rows": [],
                "cassette_rows": [],
                "cassette_part_rows": [],
                "construct_component_rows": [
                    {
                        "component_label": "Documentation-only CDS row",
                        "component_category": "coding sequence",
                        "component_reference_label": "Source note C",
                        "sequence_availability_status": "Sequence not displayed in this documentation review surface",
                        "review_metadata_status": "Source/reference metadata recorded for documentation review",
                        "review_note": "Manual review context recorded.",
                        "cassette_label": "Cassette C",
                    }
                ],
                "linked_gene_rows": [],
                "linked_pathway_step_rows": [],
                "project_link_rows": [],
                "review_gap_rows": [],
                "part_role_counts": {"cds": 1},
                "supported_component_vocabulary": ["coding sequence"],
            }
        ],
    )

    report = build_project_review_report({"id": 206, "name": "R206 readback report"})
    snapshot = report["component_library_asset_readback_snapshot"]
    draft_snapshot = report["detailed_documentation_report_draft"]["component_library_asset_readback_snapshot"]
    followup = report["component_library_followup_queue_report_readback"]
    draft_followup = report["detailed_documentation_report_draft"]["component_library_followup_queue_report_readback"]

    assert snapshot["status"] == "AVAILABLE"
    assert snapshot["summary"]["total_asset_rows"] == 2
    assert snapshot["summary"]["asset_type_counts"] == {
        "construct component reference": 1,
        "promoter": 1,
    }
    assert snapshot["rows"][0]["Asset label"] == "Generic promoter source record"
    assert snapshot["rows"][0]["Documentation context note"] == (
        "Documentation context: Project Review Report snapshot; "
        "origin: Project documentation reference; role: report_context; "
        "link state: Linked catalog reference. "
        "Source/provenance identity remains Local Design Asset Catalog / generic-promoter-206."
    )
    assert snapshot["rows"][1]["Asset label"] == "Documentation-only CDS row"
    assert snapshot["rows"][1]["Documentation context note"] == (
        "Linked catalog documentation context is not recorded for this construct component row."
    )
    assert snapshot["presenter_reuse_note"].startswith("Project Review Report reuses")
    assert "without adding a universal asset database model" in snapshot["presenter_reuse_note"]
    assert "Construct component rows are documentation records only" in " ".join(snapshot["boundary_notes"])
    assert "Type-specific Component Library readback fields are intentionally deferred." in snapshot["boundary_notes"]
    assert draft_snapshot == snapshot
    assert followup["status"] == "AVAILABLE"
    assert followup["summary"]["total_followup_rows"] == 1
    assert followup["summary"]["components_with_followup"] == 1
    assert followup["summary"]["followup_type_counts"] == {"Needs manual review": 1}
    assert followup["columns"] == [
        "Component label",
        "Component ID",
        "Component type",
        "Follow-up type",
        "Follow-up detail",
        "Manual review",
        "Boundary note",
    ]
    assert followup["rows"] == [
        {
            "Component label": "Generic promoter source record",
            "Component ID": "Local Design Asset Catalog; generic-promoter-206; live metadata fallback",
            "Component type": "promoter",
            "Follow-up type": "Needs manual review",
            "Follow-up detail": "Review next: record review status in the existing review surface.",
            "Manual review": "Needs manual review",
            "Boundary note": followup["rows"][0]["Boundary note"],
        }
    ]
    assert "does not create component records" in " ".join(followup["boundary_notes"])
    assert draft_followup == followup
    for markdown in [report["markdown"], report["detailed_documentation_report_draft"]["markdown"]]:
        assert "## Component Library Asset Readback Report Snapshot" in markdown
        assert "Generic promoter source record" in markdown
        assert "Documentation context: Project Review Report snapshot" in markdown
        assert "Documentation-only CDS row" in markdown
        assert "Project Review Report reuses the generic Component Library asset readback presenter" in markdown
        assert "biological proof records" in markdown
        assert "Type-specific fields intentionally deferred" in markdown
        assert "## Component Library Source/Provenance Follow-up Queue Report Readback" in markdown
        assert "Presenter reuse: Project Review Report reuses the existing Component Library source/provenance follow-up queue presenter" in markdown
        assert "Follow-up row type counts" in markdown
        assert "Needs manual review: 1" in markdown
        assert "Review next: record review status in the existing review surface." in markdown


def test_project_review_report_component_library_followup_queue_preserves_empty_state(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report({"id": 207, "name": "R207 empty follow-up report"})
    followup = report["component_library_followup_queue_report_readback"]

    assert followup["status"] == "NOT_AVAILABLE"
    assert followup["rows"] == []
    assert followup["summary"]["total_followup_rows"] == 0
    assert followup["empty_state_message"].startswith(
        "No Component Library source/provenance follow-up rows are currently flagged"
    )
    for markdown in [report["markdown"], report["detailed_documentation_report_draft"]["markdown"]]:
        assert "## Component Library Source/Provenance Follow-up Queue Report Readback" in markdown
        assert "No Component Library source/provenance follow-up rows are currently flagged" in markdown
        assert "does not create component records, select components, validate constructs" in markdown


def test_project_review_report_reuses_component_library_followup_queue_readback(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 363,
                "asset_id": "r363-linked-promoter",
                "asset_display_name": "R363 linked promoter context",
                "asset_type": "promoter",
                "linkage_role": "report_context",
                "source_context_snapshot": {
                    "catalog": "Local Design Asset Catalog",
                    "profile_id": "r363-linked-promoter",
                    "project_documentation_context": "R363 report readback context",
                },
                "review_status_snapshot": {
                    "review_status": "metadata gap",
                    "metadata_gap_context": "Record review status needs manual documentation follow-up.",
                },
                "human_review_required": True,
            }
        ],
    )
    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [
            {
                "construct_profile_rows": [],
                "cassette_rows": [],
                "cassette_part_rows": [],
                "construct_component_rows": [
                    {
                        "component_label": "R363 construct component context",
                        "component_category": "terminator",
                        "component_reference_label": "",
                        "sequence_availability_status": "Sequence availability not recorded",
                        "review_metadata_status": "Review metadata gap",
                        "review_note": "Record source/reference context before report reuse.",
                        "cassette_label": "R363 cassette",
                    }
                ],
                "linked_gene_rows": [],
                "linked_pathway_step_rows": [],
                "project_link_rows": [],
                "review_gap_rows": [],
                "part_role_counts": {},
                "supported_component_vocabulary": ["terminator"],
            }
        ],
    )

    report = build_project_review_report({"id": 363, "name": "R363 queue report"})
    readback = report["component_library_followup_queue_report_readback"]
    draft_readback = report["detailed_documentation_report_draft"]["component_library_followup_queue_report_readback"]

    assert readback["status"] == "AVAILABLE"
    assert readback == draft_readback
    assert readback["presenter_reuse_note"].startswith("Project Review Report reuses the existing Component Library")
    assert readback["summary"]["total_followup_rows"] == 2
    assert readback["summary"]["followup_type_counts"] == {"Needs manual review": 2}
    assert readback["columns"] == [
        "Component label",
        "Component ID",
        "Component type",
        "Follow-up type",
        "Follow-up detail",
        "Manual review",
        "Boundary note",
    ]
    assert {row["Follow-up type"] for row in readback["rows"]} == {"Needs manual review"}
    assert any(row["Component label"] == "R363 linked promoter context" for row in readback["rows"])
    assert any(row["Component label"] == "R363 construct component context" for row in readback["rows"])

    for markdown in [report["markdown"], report["detailed_documentation_report_draft"]["markdown"]]:
        assert "## Component Library Source/Provenance Follow-up Queue Report Readback" in markdown
        assert "Project Review Report reuses the existing Component Library source/provenance follow-up queue presenter" in markdown
        assert "R363 linked promoter context" in markdown
        assert "R363 construct component context" in markdown
        assert "Needs manual review" in markdown
        assert "missing source/provenance, evidence/reference, deferred-field, and boundary notes for manual review" in markdown
        assert "not a biology-use recommendation, validation claim, " + "optimi" + "zation claim, or wet-lab use judgment" in markdown
        assert "does not recommend or select components" in markdown

    combined = f"{readback}\n{report['markdown']}\n{report['detailed_documentation_report_draft']['markdown']}".casefold()
    for phrase in (
        "successful " + "import",
        "project " + "imported",
        "ready for " + "execution",
        "experiment" + "-ready",
        "production" + "-ready",
        "validated " + "construct",
        "optimized " + "pathway",
        "yield " + "prediction",
        "build" + "-ready",
        "wet-lab " + "ready",
    ):
        assert phrase not in combined


def test_project_review_report_followup_queue_readback_preserves_empty_state(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report({"id": 364, "name": "R363 empty queue report"})
    readback = report["component_library_followup_queue_report_readback"]

    assert readback["status"] == "NOT_AVAILABLE"
    assert readback["rows"] == []
    assert readback["summary"]["total_followup_rows"] == 0
    assert readback["empty_state_message"].startswith(
        "No Component Library source/provenance follow-up rows are currently flagged"
    )
    assert readback["empty_state_message"] in report["markdown"]
    assert readback["empty_state_message"] in report["detailed_documentation_report_draft"]["markdown"]


def test_project_review_report_reads_imported_catalog_references(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    db_path = repo_local_sqlite_db_path(
        ".pytest_tmp_v2_6_r148_project_review_report_service_dbs",
        "review_report_imported_links.db",
    )
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))
    project_catalog_link_repo.add_project_catalog_asset_link(
        {
            "project_id": "21",
            "asset_id": "plant-promoter-202",
            "asset_display_name": "Imported promoter profile",
            "asset_type": "plant_promoter_profile",
            "linkage_role": "source_review_context",
            "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
            "source_context_snapshot": {
                "catalog": "Plant Promoter Catalog",
                "profile_id": "plant-promoter-202",
                "plant_clade": "dicot",
                "species": "Arabidopsis thaliana",
            },
            "review_status_snapshot": {
                "curation_statuses": "source review needed",
                "missing_metadata_count": 1,
            },
            "human_review_required": True,
        }
    )

    report = build_project_review_report({"id": 21, "name": "Imported linked catalog report"})
    linked = report["detailed_documentation_report_draft"]["linked_catalog_assets"]

    assert linked["linked_catalog_asset_count"] == 1
    assert linked["linked_plant_promoter_count"] == 1
    assert linked["missing_source_or_review_metadata_count"] == 1
    assert "Imported promoter profile" in report["detailed_documentation_report_draft"]["markdown"]


def test_detailed_documentation_report_uses_seed_backed_promoter_references(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 18,
                "asset_id": "plant-promoter-seed-001",
                "asset_display_name": "Maize ubiquitin promoter source context",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "documentation_note": "Documentation-only Plant Promoter Catalog reference for project traceability.",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-seed-001",
                    "plant_clade": "monocot",
                    "species": "Zea mays (maize)",
                    "source_labels": "Literature source placeholder: ZMU-ROOT",
                },
                "review_status_snapshot": {
                    "curation_statuses": "source review needed",
                    "missing_metadata_count": 1,
                },
                "linked_at": "2026-06-17T09:00:00Z",
                "human_review_required": True,
            }
        ],
    )

    report = build_project_review_report({"id": 18, "name": "Seed backed promoter report"})

    markdown = report["detailed_documentation_report_draft"]["markdown"]
    promoter_summary = report["detailed_documentation_report_draft"]["linked_catalog_assets"]["plant_promoter_reference_summary"]

    assert promoter_summary["references"][0]["asset_display_name"] == "Maize ubiquitin promoter source context"
    assert "documentation-only" in markdown


def test_detailed_documentation_report_catalog_unavailable_does_not_crash(monkeypatch) -> None:
    import services.project_review_report_service as service

    _empty_construct_report_views(monkeypatch)
    monkeypatch.setattr(service, "load_seed_records", lambda: (_ for _ in ()).throw(RuntimeError("missing seed")))

    report = build_project_review_report({"id": 14, "name": "Catalog unavailable"})
    draft = report["detailed_documentation_report_draft"]

    assert draft["catalog_context"]["status"] == "WARNING"
    assert draft["catalog_context"]["record_count"] == 0
    assert "Local Design Asset Catalog context unavailable" in draft["markdown"]
    assert "missing seed" in draft["markdown"]


def test_detailed_documentation_report_research_placeholder_does_not_crash(monkeypatch) -> None:
    import services.project_review_report_service as service

    _empty_construct_report_views(monkeypatch)
    monkeypatch.setattr(
        service,
        "generate_literature_research_brief",
        lambda target: (_ for _ in ()).throw(ValueError("Research target is required.")),
    )

    report = build_project_review_report({"id": 15, "name": "Research unavailable"})
    draft = report["detailed_documentation_report_draft"]

    assert draft["research_context"]["status"] == "WARNING"
    assert "Research target is required." in draft["markdown"]
    assert "documentation-only" in draft["markdown"]


def test_project_with_pathway_steps_counts_and_renders_titles(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {
            "id": 2,
            "name": "Steps",
            "pathway_steps": [
                {"step_order": 1, "step_name": "Precursor activation", "enzyme_name": "EnzA", "gene_name": "geneA"},
                {"step_order": 2, "step_name": "Intermediate conversion", "organism_source": "Host A"},
            ],
        }
    )

    assert report["pathway_steps_summary"]["step_count"] == 2
    assert "Precursor activation" in report["markdown"]
    assert "Intermediate conversion" in report["markdown"]
    gap_ids = {gap["gap_id"] for gap in report["missing_fields"]}
    assert "no_pathway_steps_documented" not in gap_ids


def test_linked_artifacts_are_summarized_without_expanding_raw_payload_json(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {"id": 3, "name": "Artifacts"},
        linked_artifacts=[
            {
                "id": 10,
                "artifact_type": "wizard_snapshot",
                "title": "Design Artifact A",
                "source_module": "Expression Wizard",
                "project_id": 3,
                "payload_json": {"secret_detail": "do not expand"},
            }
        ],
    )

    assert report["linked_artifacts_summary"]["artifact_count"] == 1
    assert "Design Artifact A" in report["markdown"]
    assert "wizard_snapshot" in report["markdown"]
    assert "payload_json" not in report["markdown"]
    assert "do not expand" not in report["markdown"]
    assert "Linked artifacts are documentation records for traceability only." in report["markdown"]
    assert "They do not certify downstream use state or experimental evidence." in report["markdown"]


def test_saved_design_snapshot_summary_available_and_not_available_cases(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {"id": 4, "name": "Saved"},
        saved_designs=[
            {
                "design_id": "design-1",
                "display_name": "Snapshot One",
                "source_saved_design_id": "saved-1",
                "saved_design_version": "v1",
                "identity_source": "linked_artifact",
            }
        ],
    )

    snapshot = report["saved_design_snapshot_summary"]["snapshots"][0]
    assert snapshot["design_id"] == "design-1"
    assert snapshot["display_name"] == "Snapshot One"
    assert snapshot["source_saved_design_id"] == "saved-1"

    missing = build_project_review_report({"id": 5, "name": "No saved"})
    assert missing["saved_design_snapshot_summary"]["status"] == "NOT_AVAILABLE"


def test_import_safety_summary_counts_and_read_only_boundary(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {"id": 6, "name": "Safety"},
        import_safety_summary={
            "overall_status": "WARNING",
            "blocking_issues": ["Issue A"],
            "warnings": ["Warning A", "Warning B"],
            "check_items": [{"status": "NOT_EVALUATED"}, {"status": "PASS"}],
        },
    )

    safety = report["import_safety_summary"]
    assert safety["overall_status"] == "WARNING"
    assert safety["blocking_issue_count"] == 1
    assert safety["warning_count"] == 2
    assert safety["not_evaluated_count"] == 1
    assert "Import package safety checks are read-only." in report["markdown"]
    assert "They do not import or modify any project." in report["markdown"]
    assert "No database writes are performed." in report["markdown"]


def test_package_exchange_review_trail_includes_manifest_context(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {"id": 18, "name": "Package trail"},
        export_summary={
            "status": "AVAILABLE",
            "package_contents_preview_status": "AVAILABLE",
            "last_export_status": "AVAILABLE",
            "documentation_only_boundary": "Export package is documentation-only context.",
        },
        import_safety_summary={
            "status": "AVAILABLE",
            "overall_status": "NEEDS_REVIEW",
            "manifest_summary": {
                "is_manifest_present": True,
                "package_schema_version": "2.6-r28",
                "included_sections": ["project_metadata", "construct_profiles"],
                "record_counts": {"construct_profile_count": 2, "review_gap_count": 1},
                "documentation_boundary": "Manifest review is documentation context.",
                "review_notes": ["Review missing manifest metadata before local documentation use."],
            },
        },
    )

    trail = report["package_exchange_review_trail"]
    manifest = trail["manifest_review"]
    assert trail["section_title"] == "Package Exchange Review Trail"
    assert trail["status"] == "AVAILABLE"
    assert manifest["is_manifest_present"] is True
    assert manifest["package_schema_version"] == "2.6-r28"
    assert manifest["included_section_count"] == 2
    assert manifest["record_counts"]["record_count_total"] == 3
    assert "Package Exchange Review Trail" in report["markdown"]
    assert "Manifest review available: True" in report["markdown"]
    assert "Workflow context: Create or review project documentation." in report["markdown"]
    assert "Workflow context: Export a documentation package with manifest metadata." in report["markdown"]
    assert "Workflow context: Review the package in Import Manifest Review before local documentation use." in report["markdown"]
    assert "Workflow context: Create a new project copy only through explicit create-as-new confirmation." in report["markdown"]
    assert "Workflow context: Review the package exchange review trail in the Project Review Report and Project Quality Dashboard." in report["markdown"]
    assert "Review missing manifest metadata before local documentation use." in report["markdown"]
    assert "Package review does not certify correctness, downstream-use state, biological fit, or biological function." in report["markdown"]


def test_project_review_report_includes_candidate_evidence_human_review_queue_summary(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 26,
                "asset_id": "plant-promoter-301",
                "asset_display_name": "Complete promoter evidence row",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-301",
                },
                "asset_snapshot": {
                    "snapshot_hash": "sha256:complete-301",
                },
                "review_status_snapshot": {
                    "review_status": "source review recorded",
                },
            },
            {
                "project_id": 26,
                "asset_id": "plant-promoter-302",
                "asset_display_name": "Partial promoter evidence row",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {},
                "review_status_snapshot": {},
                "asset_snapshot": {},
            },
        ],
    )

    report = build_project_review_report({"id": 26, "name": "Queue report"})

    queue = report["candidate_evidence_human_review_queue"]
    summary = queue["summary"]

    assert queue["title"] == "Candidate Evidence Human Review Queue"
    assert summary["queue_item_count"] == 4
    assert summary["candidate_count"] == 2
    assert summary["documentation_gap_count"] == 1
    assert summary["provenance_gap_count"] == 1
    assert summary["metadata_gap_count"] == 0
    assert summary["review_follow_up_count"] == 2
    assert queue["rows"][0]["queue_item_id"]
    assert "Candidate Evidence Human Review Queue" in report["markdown"]
    assert "| Queue item id | Candidate label | Category | Severity | Issue | Human follow-up | Source context |" in report["markdown"]
    assert "Partial promoter evidence row" in report["markdown"]
    assert "This section supports manual documentation review only." in report["markdown"]
    assert "It does not rank, recommend, validate, tune, or confirm biological suitability." in report["markdown"]


def test_project_review_report_includes_project_review_follow_up_index(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 126,
                "asset_id": "plant-promoter-401",
                "asset_display_name": "Complete promoter evidence row",
                "asset_type": "plant_promoter_profile",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-401",
                },
                "asset_snapshot": {
                    "snapshot_hash": "sha256:complete-401",
                },
                "review_status_snapshot": {
                    "review_status": "source review recorded",
                },
            },
            {
                "project_id": 126,
                "asset_id": "plant-promoter-402",
                "asset_display_name": "Gap-heavy promoter row",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "source_context_snapshot": {},
                "review_status_snapshot": {
                    "missing_metadata_count": 2,
                },
                "asset_snapshot": {},
                "human_review_required": True,
            },
        ],
    )

    report = build_project_review_report({"id": 126, "name": "Follow-up index report"})

    index = report["project_review_follow_up_index"]
    summary = index["summary"]

    assert index["title"] == "Project Review Follow-up Index"
    assert index["status"] == "AVAILABLE"
    assert summary["total_follow_up_items"] >= 1
    assert summary["source_section_counts"]["candidate_evidence"] >= 1
    assert summary["source_section_counts"]["plant_promoter_catalog"] >= 1
    assert index["rows"][0]["follow_up_id"]
    assert "Project Review Follow-up Index" in report["markdown"]
    assert "| Follow-up id | Source section | Item label | Category | Issue | Review next | Manual review context |" in report["markdown"]
    assert "This index supports manual documentation review and triage only." in report["markdown"]


def test_project_review_report_candidate_evidence_human_review_queue_empty_state_is_safe(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [],
    )

    report = build_project_review_report({"id": 27, "name": "Empty queue report"})

    queue = report["candidate_evidence_human_review_queue"]
    assert queue["status"] == "NOT_AVAILABLE"
    assert queue["summary"]["queue_item_count"] == 0
    assert queue["rows"] == []
    assert "No human review follow-up items are currently queued" in queue["empty_state_message"]
    assert "No human review follow-up items are currently queued" in report["markdown"]


def test_project_review_report_follow_up_index_empty_state_is_safe(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [],
    )

    report = build_project_review_report({"id": 127, "name": "Empty follow-up index report"})

    index = report["project_review_follow_up_index"]
    assert index["status"] == "NOT_AVAILABLE"
    assert index["summary"]["total_follow_up_items"] == 0
    assert index["rows"] == []
    assert "No manual documentation follow-up items are currently aggregated" in index["empty_state_message"]
    assert "No manual documentation follow-up items are currently aggregated" in report["markdown"]


def test_project_review_report_includes_plant_promoter_evidence_gap_review_for_linked_promoters(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 28,
                "asset_id": "plant-promoter-gap-001",
                "asset_display_name": "Linked maize promoter review record",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "documentation_note": "Documentation-only promoter reference.",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-gap-001",
                    "plant_clade": "monocot",
                    "species": "Zea mays (maize)",
                    "tissue_contexts": "No tissue context recorded",
                    "source_labels": "No source database recorded",
                },
                "review_status_snapshot": {
                    "curation_statuses": "source review needed",
                    "review_notes": "Needs review before citation in project documentation.",
                    "missing_metadata_count": 2,
                },
                "human_review_required": True,
            }
        ],
    )

    report = build_project_review_report({"id": 28, "name": "Promoter gap report"})

    promoter_review = report["plant_promoter_evidence_gap_review"]
    summary = promoter_review["summary_counts"]
    categories = promoter_review["category_counts"]

    assert promoter_review["title"] == "Component Library Promoter Asset Evidence Gap Review"
    assert promoter_review["context_scope"] == "project_linked"
    assert promoter_review["status"] == "AVAILABLE"
    assert summary["profile_count"] == 1
    assert summary["queue_item_count"] >= 4
    assert categories["source_provenance_gap"] == 1
    assert categories["tissue_context_gap"] == 1
    assert categories["review_status_gap"] == 0
    assert categories["documentation_follow_up"] == 1
    assert promoter_review["rows"][0]["queue_item_id"]
    assert "Component Library Promoter Asset Evidence Gap Review" in report["markdown"]
    assert "Supports documentation review and human curation only." in report["markdown"]
    assert "| Queue item id | Promoter label | Category | Issue | Human follow-up | Source context |" in report["markdown"]
    assert "Linked maize promoter review record" in report["markdown"]


def test_project_review_report_plant_promoter_evidence_gap_review_empty_state_is_safe(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [],
    )

    report = build_project_review_report({"id": 29, "name": "No promoter context"})

    promoter_review = report["plant_promoter_evidence_gap_review"]
    assert promoter_review["status"] == "NOT_AVAILABLE"
    assert promoter_review["context_scope"] == "catalog_context"
    assert promoter_review["summary_counts"]["queue_item_count"] == 0
    assert promoter_review["rows"] == []
    assert "no promoter evidence gap items are currently queued" in promoter_review["empty_state_message"].lower()
    assert "No Component Library promoter asset context is linked to this project review report" in report["markdown"]


def test_project_review_report_includes_project_review_handoff_center(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 177,
                "asset_id": "plant-promoter-handoff",
                "asset_display_name": "Handoff promoter reference",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "documentation_note": "Documentation-only promoter reference.",
                "source_context_snapshot": {
                    "catalog": "Plant Promoter Catalog",
                    "profile_id": "plant-promoter-handoff",
                    "plant_clade": "monocot",
                    "species": "Zea mays (maize)",
                    "source_labels": "No source database recorded",
                },
                "review_status_snapshot": {
                    "curation_statuses": "source review needed",
                    "missing_metadata_count": 1,
                },
                "human_review_required": True,
            }
        ],
    )

    report = build_project_review_report({"id": 177, "name": "Handoff report", "host": ""})

    handoff = report["project_review_handoff_center"]
    preview = report["project_handoff_package_preview"]
    review_card = preview["snapshot_review_card"]
    qr_payload = preview["qr_verification_payload"]
    action_panel = preview["expression_construct_review_action_panel"]
    summary = handoff["summary"]
    assert handoff["title"] == "Project review handoff center"
    assert preview["title"] == "Project handoff package preview"
    assert review_card["title"] == "Handoff snapshot review card"
    assert review_card["snapshot_checksum"] == preview["snapshot_checksum"]
    assert review_card["snapshot_checksum_algorithm"] == "MD5"
    assert review_card["snapshot_included_surface_count"] == 5
    assert review_card["snapshot_manual_follow_up_count"] == summary["total_follow_up_items"]
    assert qr_payload["snapshot_id"] == preview["snapshot_id"]
    assert qr_payload["checksum_algorithm"] == "MD5"
    assert qr_payload["snapshot_checksum"] == preview["snapshot_checksum"]
    assert qr_payload["included_surfaces_count"] == 5
    assert qr_payload["manual_follow_up_count"] == summary["total_follow_up_items"]
    assert action_panel["title"] == "Expression construct review action panel"
    assert action_panel["source_presenter"] == (
        "services.expression_construct_review_action_panel_presenter."
        "build_expression_construct_review_action_panel"
    )
    assert action_panel["summary"]["row_count"] == 4
    assert report["output_sections_overview"]["title"] == "Output sections overview"
    assert report["output_sections_overview"]["section_count"] == 7
    assert report["detailed_documentation_report_draft"]["output_sections_overview"]["title"] == "Output sections overview"
    assert any(
        row["section_name"] == "Project Review Report"
        for row in report["output_sections_overview"]["rows"]
    )
    assert any(
        row["section_name"] == "Component Library follow-up queue report/readback"
        for row in report["output_sections_overview"]["rows"]
    )
    assert "## Output sections overview" in report["markdown"]
    assert "| Section | Status | Count | Inspect next |" in report["markdown"]
    assert "## Output sections overview" in report["detailed_documentation_report_draft"]["markdown"]
    assert "### Expression construct review action panel" in preview["markdown_handoff_preview"]
    assert "### Expression construct review action panel" in preview["review_sheet_markdown"]
    assert "BioDesign Studio handoff QR verification payload" in preview["qr_verification_payload_text"]
    assert "No export package is created here." in preview["qr_verification_payload_text"]
    assert "No file or download is created here." in preview["qr_verification_payload_text"]
    assert preview["traceability_matrix_summary"]["row_count"] == len(preview["traceability_matrix_rows"])
    assert preview["traceability_matrix_summary"]["included_in_review_sheet_count"] == len(
        preview["traceability_matrix_rows"]
    )
    assert any(
        row["source_surface"] == "Component Library promoter asset source/review"
        for row in preview["traceability_matrix_rows"]
    )
    assert any(
        row["where_to_review_next"] == "Review next: Component Library promoter asset reference summary"
        for row in preview["traceability_matrix_rows"]
    )
    assert "preview matching only" in review_card["boundary_note"]
    assert "not a security signature or certification" in review_card["boundary_note"]
    assert summary["total_follow_up_items"] >= 1
    assert summary["promoter_source_review_follow_up_count"] >= 1
    assert summary["report_markdown_available"] is True
    assert any(item["label"] == "report markdown available for human review" for item in handoff["checklist"])
    assert "Project Review Handoff Center" in report["markdown"]
    assert "Handoff checklist" in report["markdown"]
    assert "Handoff snapshot review card" in report["markdown"]
    assert "Expression construct review action panel" in report["markdown"]
    assert "Handoff QR verification preview" in report["markdown"]
    assert "Use this preview identity to match the same handoff snapshot during human review." in report["markdown"]
    assert "Payload-only fallback is used because the default dependency manifest does not include a QR rendering library." in report["markdown"]
    assert "Read-only QR verification payload for matching the same preview identity during human review." in report["markdown"]
    assert "BioDesign Studio handoff QR verification payload" in report["markdown"]
    assert review_card["snapshot_checksum"] in report["markdown"]
    assert "Checksum algorithm: MD5" in report["markdown"]
    assert "MD5 preview checksum" in report["markdown"]
    assert "No file or download is created here." in report["markdown"]
    assert "Documentation preview only; no export package is created here." in report["markdown"]
    assert "The MD5 code is for preview matching only, not a security signature or certification." in report["markdown"]
    assert "Handoff follow-up queue overview" in report["markdown"]
    assert "Project handoff traceability matrix" in report["markdown"]
    assert "Source/reference context follow-up" in report["markdown"]
    assert "Provenance/review context follow-up" in report["markdown"]
    assert "| Source surface | Item label | Documentation context | Source/reference context | Provenance/review context | Manual follow-up status | Review next | Included in review sheet |" in report["markdown"]
    assert "Included in review sheet" in report["markdown"]
    assert "Component Library promoter asset source/review follow-up" in report["markdown"]
    assert "| Source surface | Item label | Issue type | Manual follow-up note | Review next |" in report["markdown"]
    assert "This handoff center is documentation-only and read-only." in report["markdown"]
    for forbidden in [
        "secure signature",
        "certified",
        "approved package",
        "ready package",
        "recommended handoff",
        "validated construct",
        "optimized pathway",
        "ready for execution",
    ]:
        assert forbidden not in report["markdown"].lower()


def test_project_review_report_normalizes_generated_host_context_wording(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {"id": 187, "name": "Host compatibility report", "host": "host compatibility"},
    )

    text = f"{report['markdown']}\n{report['detailed_documentation_report_draft']['markdown']}".lower()
    assert "host compatibility" not in text
    assert "host/context documentation" in text


def test_project_review_report_guard_rejects_unsafe_generated_claim(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    try:
        build_project_review_report(
            {
                "id": 188,
                "name": "Unsafe report",
                "review_notes": "validated construct",
            }
        )
    except ValueError as exc:
        assert "Misleading report claim detected: validated construct" in str(exc)
    else:
        raise AssertionError("Expected report misleading-claim guard to reject unsafe copy.")


def test_boundary_copy_is_present(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    text = build_project_review_report({"id": 7, "name": "Boundary"})["markdown"]

    assert "documentation-only" in text
    assert "computational previews only" in text
    assert "not a biology-use recommendation, validation claim, " + "optimi" + "zation claim, or wet-lab use judgment" in text
    assert "does not recommend, rank, score, validate, " + "opti" + "mize, predict, or judge downstream-use state" in text
    assert "does not forecast yield" in text
    assert "does not tune pathways" in text
    assert "does not provide wet-lab instructions" in text
    assert "Import execution is documentation-only" in text
    assert "gated by explicit confirmation" in text
    assert "creates a new project" in text
    assert "instead of overwriting or merging existing projects" in text


def test_project_review_report_includes_construct_component_documentation_rows(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [
            {
                "construct_profile_rows": [{"construct_id": "construct-901", "construct_label": "Neutral construct"}],
                "cassette_rows": [],
                "cassette_part_rows": [],
                "construct_component_rows": [
                    {
                        "component_label": "Doc promoter",
                        "component_category": "promoter",
                        "component_reference_label": "Reference A",
                        "sequence_availability_status": "Sequence availability recorded through linked source/reference context",
                        "conservation_review_evidence": (
                            "source organism/source context: maize source context; sequence source: Reference A; "
                            "literature/database evidence: classroom source note; conservation note: manual review note"
                        ),
                        "conservation_follow_up_cue": "Conservation-related source/evidence context recorded for manual documentation review",
                        "review_metadata_status": "Source/reference metadata recorded for documentation review",
                        "review_note": "Recorded for traceability review.",
                        "cassette_label": "Cassette 1",
                    },
                    {
                        "component_label": "crtB CDS",
                        "component_category": "coding sequence",
                        "component_reference_label": "Gene note B",
                        "sequence_availability_status": "Sequence not displayed in this documentation review surface",
                        "conservation_review_evidence": "No conservation review evidence recorded",
                        "conservation_follow_up_cue": "Needs conservation check",
                        "review_metadata_status": "Source/reference metadata recorded for documentation review",
                        "review_note": "Recorded for documentation review.",
                        "cassette_label": "Cassette 1",
                    },
                ],
                "linked_gene_rows": [],
                "linked_pathway_step_rows": [],
                "project_link_rows": [],
                "review_gap_rows": [],
                "part_role_counts": {"promoter": 1, "cds": 1},
                "supported_component_vocabulary": [
                    "promoter",
                    "5' UTR",
                    "RBS",
                    "signal peptide",
                    "coding sequence",
                    "terminator",
                    "other documented component",
                ],
            }
        ],
    )

    report = build_project_review_report({"id": 901, "name": "Construct component report"})
    constructs = report["expression_construct_documentation"]
    main_markdown = report["markdown"]
    markdown = report["detailed_documentation_report_draft"]["markdown"]

    assert len(constructs["construct_component_rows"]) == 2
    assert constructs["construct_component_rows"][0]["component_label"] == "Doc promoter"
    assert constructs["construct_component_rows"][1]["component_category"] == "coding sequence"
    assert constructs["supported_component_vocabulary"] == [
        "promoter",
        "5' UTR",
        "RBS",
        "signal peptide",
        "coding sequence",
        "terminator",
        "other documented component",
    ]
    for text in [
        "### Construct component documentation readback",
        "This section reads back recorded construct documentation from documented component rows only.",
        "It is not validation, selection advice, or a downstream-use state decision.",
        "Construct component readback records recorded construct documentation only. They do not validate, recommend, or decide downstream-use state.",
        "Sequence content is not newly displayed here; sequence availability is read back only through recorded documentation status.",
        "Component conservation review is a documentation-only readback of source/evidence context and missing-review cues.",
        "It does not run BLAST, multiple sequence alignment, conserved-domain analysis, automated conservation-status classification, component selection, expression outcome estimates, guarantees of success, or wet-lab use judgments.",
        "Conservation review context",
        "Conservation follow-up",
        "Conservation review evidence",
        "Conservation follow-up cue",
        "source organism/source context: maize source context",
        "Needs conservation check",
        "Supported documented component vocabulary: promoter; 5' UTR; RBS; signal peptide; coding sequence; terminator; other documented component",
        "Doc promoter",
        "crtB CDS",
    ]:
        assert text in main_markdown
        assert text in markdown
    assert "Sequence availability recorded through linked source/reference context" in main_markdown
    assert "Sequence availability recorded through linked source/reference context" in markdown
    assert "ATGC" not in main_markdown
    assert "ATGC" not in markdown


def test_project_review_report_construct_component_copy_avoids_claims(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [
            {
                "construct_profile_rows": [],
                "cassette_rows": [],
                "cassette_part_rows": [],
                "construct_component_rows": [
                    {
                        "component_label": "Neutral component",
                        "component_category": "other documented component",
                        "component_reference_label": "No component reference recorded",
                        "sequence_availability_status": "Sequence availability not recorded in this documentation view",
                        "conservation_review_evidence": "No conservation review evidence recorded",
                        "conservation_follow_up_cue": "Needs conservation check",
                        "review_metadata_status": "Metadata gap remains visible for documentation review",
                        "review_note": "No provenance note recorded",
                        "cassette_label": "Untitled cassette draft",
                    }
                ],
                "linked_gene_rows": [],
                "linked_pathway_step_rows": [],
                "project_link_rows": [],
                "review_gap_rows": [],
                "part_role_counts": {},
                "supported_component_vocabulary": [
                    "promoter",
                    "5' UTR",
                    "RBS",
                    "coding sequence",
                    "terminator",
                    "other documented component",
                ],
            }
        ],
    )

    report = build_project_review_report({"id": 902, "name": "Construct safety report"})
    text = str(report["expression_construct_documentation"]).lower()
    report_text = f"{report['markdown']}\n{report['detailed_documentation_report_draft']['markdown']}".lower()
    forbidden = [
        "recommended",
        "validated " + "construct",
        "optimized " + "pathway",
        "ready for " + "execution",
        "production" + "-ready",
        "host compatibility proof",
        "automatically conserved",
        "conserved component",
        "component recommendation",
        "expression " + "forecast",
        "success " + "guarantee",
        "replacement of expert review",
    ]
    for phrase in forbidden:
        assert phrase not in text
        assert phrase not in report_text


def test_project_review_report_reuses_documentation_review_summary_in_plant_package_markdown(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [
            {
                "construct_profile_rows": [],
                "cassette_rows": [
                    {
                        "promoter_label": "plant promoter documentation row",
                        "gene_label": "albumin CDS",
                        "terminator_label": "plant terminator documentation row",
                    }
                ],
                "cassette_part_rows": [],
                "linked_gene_rows": [],
                "linked_pathway_step_rows": [],
                "project_link_rows": [],
                "review_gap_rows": [],
                "construct_component_rows": [
                    {"component_label": "Promoter row"},
                    {"component_label": "CDS row"},
                ],
                "construct_component_gap_queue": [],
                "construct_component_review_summary": {
                    "total_component_rows": 2,
                    "rows_with_source_reference_context": 1,
                    "rows_needing_manual_follow_up": 1,
                },
                "construct_component_manual_follow_up_readback": {
                    "total_manual_follow_up_items": 1,
                },
                "part_role_counts": {},
                "supported_component_vocabulary": [],
            }
        ],
    )

    report = build_project_review_report({"id": 905, "name": "Summary reuse report"})
    markdown = report["markdown"]
    package_markdown = report["plant_design_review_package"]["markdown"]

    assert report["documentation_review_summary"] == report["plant_design_review_package"]["documentation_review_summary"]
    assert "### Documentation review summary" in markdown
    assert "### Documentation review summary" in package_markdown
    assert "Review-only documentation handoff review; not a downstream-use assessment." in package_markdown
    assert "not a biology-use recommendation, validation claim, " + "optimi" + "zation claim, or wet-lab use judgment" in package_markdown
    assert "documentation-only" in package_markdown
    assert "sequence: " not in markdown


def test_project_review_report_component_conservation_follow_up_is_manual_documentation_review(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [
            {
                "construct_profile_rows": [
                    {"construct_id": "construct-r221", "construct_label": "R221 conservation construct"}
                ],
                "cassette_rows": [],
                "cassette_part_rows": [],
                "construct_component_rows": [
                    {
                        "component_label": "Signal peptide documentation row",
                        "component_category": "signal peptide",
                        "component_reference_label": "Signal sequence source record",
                        "sequence_availability_status": (
                            "Sequence availability recorded through linked source/reference context"
                        ),
                        "conservation_review_evidence": (
                            "source organism/source context: Nicotiana source context; sequence source: Signal "
                            "sequence source record; literature/database evidence: manual source note; "
                            "conservation note: reviewer note recorded"
                        ),
                        "conservation_follow_up_cue": (
                            "Conservation-related source/evidence context recorded for manual documentation review"
                        ),
                        "review_metadata_status": (
                            "Source/reference and record review status recorded for documentation review"
                        ),
                        "review_note": "Manual reviewer note retained for conservation documentation review.",
                        "cassette_label": "R221 cassette",
                    },
                    {
                        "component_label": "Terminator missing conservation evidence",
                        "component_category": "terminator",
                        "component_reference_label": "No component reference recorded",
                        "sequence_availability_status": "Sequence availability not recorded in this documentation view",
                        "conservation_review_evidence": "No conservation review evidence recorded",
                        "conservation_follow_up_cue": "Needs conservation check",
                        "review_metadata_status": "Review gap remains visible for documentation review",
                        "review_note": "No provenance note recorded",
                        "cassette_label": "R221 cassette",
                    },
                ],
                "construct_component_gap_queue": [
                    {
                        "Construct label": "R221 conservation construct",
                        "Cassette label": "R221 cassette",
                        "Component label": "Terminator missing conservation evidence",
                        "Component category": "terminator",
                        "Issue type": construct_presenter.CONSERVATION_REVIEW_ISSUE_TYPE,
                        "Issue detail": (
                            "No source organism/source context, sequence source, literature or database evidence, "
                            "conservation note, or reviewer note is recorded for conservation review."
                        ),
                        "Manual follow-up note": construct_presenter.CONSERVATION_REVIEW_FOLLOW_UP_NOTE,
                    }
                ],
                "linked_gene_rows": [],
                "linked_pathway_step_rows": [],
                "project_link_rows": [],
                "review_gap_rows": [],
                "part_role_counts": {"signal peptide": 1, "terminator": 1},
                "supported_component_vocabulary": [
                    "promoter",
                    "5' UTR",
                    "RBS",
                    "signal peptide",
                    "coding sequence",
                    "terminator",
                    "other documented component",
                ],
            }
        ],
    )

    report = build_project_review_report({"id": 221, "name": "R221 conservation report"})
    readback = report["expression_construct_documentation"]["construct_component_manual_follow_up_readback"]
    combined = f"{readback}\n{report['markdown']}\n{report['detailed_documentation_report_draft']['markdown']}"

    assert readback["conservation_review_follow_up_count"] == 1
    assert readback["other_documentation_follow_up_count"] == 0
    assert "Signal peptide documentation row" in combined
    assert "Terminator missing conservation evidence" in combined
    assert "source organism/source context: Nicotiana source context" in combined
    assert "literature/database evidence: manual source note" in combined
    assert "Needs conservation check" in combined
    assert "Manual documentation follow-up: record source organism/source context" in combined
    assert "Conservation review rows mean source organism/source context" in combined
    assert "without BLAST, MSA, conserved-domain analysis" in combined

    lowered = combined.lower()
    forbidden = [
        "automatically conserved",
        "conserved component",
        "non-conserved component",
        "component recommendation",
        "best component",
        "expression prediction",
        "yield " + "prediction",
        "guaranteed success",
        "replace expert review",
        "wet-lab " + "readiness",
        "readiness " + "judgment",
    ]
    assert [phrase for phrase in forbidden if phrase in lowered] == []


def test_project_review_report_construct_component_manual_follow_up_readback_polishes_r211_rows(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [
            {
                "construct_profile_rows": [
                    {"construct_id": "construct-r213", "construct_label": "R213 construct"}
                ],
                "cassette_rows": [],
                "cassette_part_rows": [],
                "construct_component_rows": [
                    {
                        "component_label": "Shared manual component",
                        "component_category": "other documented component",
                        "component_reference_label": "Manual component note",
                        "sequence_availability_status": (
                            "Sequence availability recorded through linked source/reference context"
                        ),
                        "review_metadata_status": (
                            "Source/reference metadata recorded for documentation review"
                        ),
                        "review_note": "Manual provenance note.",
                        "cassette_label": "R213 cassette",
                    }
                ],
                "construct_component_gap_queue": [
                    {
                        "Construct label": "R213 construct",
                        "Cassette label": "R213 cassette",
                        "Component label": "Shared manual component",
                        "Component category": "other documented component",
                        "Issue type": construct_presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
                        "Issue detail": (
                            "Component role is missing or recorded as other documented component in this "
                            "documentation view."
                        ),
                        "Manual follow-up note": (
                            "Manual documentation follow-up: review the component role label for traceability clarity."
                        ),
                    },
                    {
                        "Construct label": "R213 construct",
                        "Cassette label": "R213 cassette",
                        "Component label": "Shared manual component",
                        "Component category": "other documented component",
                        "Issue type": construct_presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
                        "Issue detail": (
                            "Component role is missing or recorded as other documented component in this "
                            "documentation view."
                        ),
                        "Manual follow-up note": (
                            "Manual documentation follow-up: review the component role label for traceability clarity."
                        ),
                    },
                    {
                        "Construct label": "R213 construct",
                        "Cassette label": "R213 cassette",
                        "Component label": "Shared manual component",
                        "Component category": "other documented component",
                        "Issue type": construct_presenter.DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE,
                        "Issue detail": (
                            "The same visible component label appears more than once in this construct/cassette "
                            "documentation context."
                        ),
                        "Manual follow-up note": (
                            "Manual documentation follow-up: review duplicate component labels for traceability clarity."
                        ),
                    },
                ],
                "linked_gene_rows": [],
                "linked_pathway_step_rows": [],
                "project_link_rows": [],
                "review_gap_rows": [],
                "part_role_counts": {"other": 2},
                "supported_component_vocabulary": [
                    "promoter",
                    "5' UTR",
                    "RBS",
                    "coding sequence",
                    "terminator",
                    "other documented component",
                ],
            }
        ],
    )

    first = build_project_review_report({"id": 213, "name": "R213 construct component report"})
    second = build_project_review_report({"id": 213, "name": "R213 construct component report"})
    readback = first["expression_construct_documentation"]["construct_component_manual_follow_up_readback"]

    assert readback == second["expression_construct_documentation"]["construct_component_manual_follow_up_readback"]
    assert readback["total_manual_follow_up_items"] == 3
    assert readback["role_label_review_count"] == 2
    assert readback["duplicate_label_review_count"] == 1
    assert readback["other_documentation_follow_up_count"] == 0
    assert readback["manual_review_boundary"] == (
        "Manual documentation review only; preserves existing component-row follow-up detection and ordering."
    )
    assert first["expression_construct_documentation"]["construct_component_gap_queue"] == second[
        "expression_construct_documentation"
    ]["construct_component_gap_queue"]
    assert [row["Issue type"] for row in first["expression_construct_documentation"]["construct_component_gap_queue"]] == [
        construct_presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
        construct_presenter.COMPONENT_ROLE_REVIEW_ISSUE_TYPE,
        construct_presenter.DUPLICATE_COMPONENT_LABEL_REVIEW_ISSUE_TYPE,
    ]

    for markdown in [first["markdown"], first["detailed_documentation_report_draft"]["markdown"]]:
        assert "### Construct component manual follow-up readback" in markdown
        assert "Manual documentation review items in report snapshot: 3" in markdown
        assert "Role-label review items: 2" in markdown
        assert "Duplicate-label review items: 1" in markdown
        assert "Other documentation follow-up items: 0" in markdown
        assert (
            "Role-label review rows mean the component role is missing or recorded as other documented component."
            in markdown
        )
        assert (
            "Duplicate-label review rows mean the same visible component label appears more than once in the "
            "same construct/cassette documentation context."
            in markdown
        )
        assert "This readback does not add gap types, biological scoring, or documentation follow-up status judgments." in markdown
        assert "Manual documentation review only" in markdown
        assert "Review component role documentation" in markdown
        assert "Review duplicate component label" in markdown

    forbidden = [
        "biological recommendation",
        "validated " + "construct",
        "optimized " + "pathway",
        "yield " + "prediction",
        "ready for " + "execution",
        "production" + "-ready",
        "wet-lab " + "ready",
    ]
    combined_text = f"{readback}\n{first['markdown']}\n{first['detailed_documentation_report_draft']['markdown']}".lower()
    assert [phrase for phrase in forbidden if phrase in combined_text] == []


def test_project_review_report_construct_component_markdown_empty_state_is_safe(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [
            {
                "construct_profile_rows": [],
                "cassette_rows": [],
                "cassette_part_rows": [],
                "construct_component_rows": [],
                "linked_gene_rows": [],
                "linked_pathway_step_rows": [],
                "project_link_rows": [],
                "review_gap_rows": [],
                "part_role_counts": {},
                "supported_component_vocabulary": [
                    "promoter",
                    "5' UTR",
                    "RBS",
                    "coding sequence",
                    "terminator",
                    "other documented component",
                ],
            }
        ],
    )

    report = build_project_review_report({"id": 903, "name": "Construct empty state"})
    for markdown in [report["markdown"], report["detailed_documentation_report_draft"]["markdown"]]:
        assert "### Construct component documentation readback" in markdown
        assert "This section reads back recorded construct documentation from documented component rows only." in markdown
        assert "No construct component documentation rows are recorded for this report." in markdown
        assert "No construct component documentation rows are recorded in this report markdown readback." in markdown
        assert "It is not validation, selection advice, or a downstream-use state decision." in markdown
        assert "Construct component readback records recorded construct documentation only. They do not validate, recommend, or decide downstream-use state." in markdown
        assert "Sequence content is not newly displayed here; sequence availability is read back only through recorded documentation status." in markdown


def test_project_review_report_construct_component_markdown_uses_fallbacks_without_new_sequence_exposure(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.expression_construct_presenter,
        "build_expression_construct_report_views",
        lambda **kwargs: [
            {
                "construct_profile_rows": [],
                "cassette_rows": [],
                "cassette_part_rows": [],
                "construct_component_rows": [
                    {
                        "component_label": "",
                        "component_category": "",
                        "component_reference_label": "",
                        "sequence_availability_status": "",
                        "review_metadata_status": "",
                        "review_note": "",
                        "cassette_label": "",
                        "sequence": "ATGCGTATGCGT",
                    }
                ],
                "linked_gene_rows": [],
                "linked_pathway_step_rows": [],
                "project_link_rows": [],
                "review_gap_rows": [],
                "part_role_counts": {},
                "supported_component_vocabulary": [],
            }
        ],
    )

    report = build_project_review_report({"id": 904, "name": "Construct fallback state"})
    for markdown in [report["markdown"], report["detailed_documentation_report_draft"]["markdown"]]:
        assert "NOT_AVAILABLE" in markdown
        assert "ATGCGTATGCGT" not in markdown
        assert "Sequence content is not newly displayed here; sequence availability is read back only through recorded documentation status." in markdown


def test_project_review_report_includes_host_chassis_context_readback(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    import services.project_review_report_service as service

    monkeypatch.setattr(
        service.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 801,
                "asset_id": "host-note-bacterial",
                "asset_display_name": "Bacterial context note",
                "asset_type": "host_chassis_context_note",
                "source_context_snapshot": {
                    "host_context": "E. coli documentation context",
                },
                "review_status_snapshot": {
                    "review_status": "human review needed",
                },
            },
            {
                "project_id": 801,
                "asset_id": "host-note-plant",
                "asset_display_name": "Plant context note",
                "asset_type": "host_chassis_context_note",
                "source_context_snapshot": {
                    "host_context": "Nicotiana benthamiana documentation context",
                },
            },
        ],
    )

    report = build_project_review_report(
        {"id": 801, "name": "Host context report", "host": "CHO cell line"}
    )

    summary = report["host_chassis_context_summary"]
    assert summary["project_context"] == "mammalian"
    assert summary["contexts_present"] == ["bacterial", "mammalian", "plant"]
    assert summary["supported_contexts"] == [
        "bacterial",
        "yeast",
        "mammalian",
        "plant",
        "generic / unspecified",
    ]
    assert summary["plant_is_supported_example_only"] is True
    assert "Host / chassis documentation context" in report["markdown"]
    assert "Supported chassis-neutral contexts: bacterial; yeast; mammalian; +2 more" in report["markdown"]
    assert "Host / chassis context readback is documentation context only." in report["markdown"]
    assert "| Source label | Source value | Normalized context | Record label |" in report["markdown"]
    assert "Active project host field" in report["markdown"]
    assert "Linked host / chassis context reference" in report["markdown"]


def test_project_review_report_unknown_host_falls_back_to_generic_unspecified(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    report = build_project_review_report(
        {"id": 802, "name": "Unknown host report", "host": "amazing custom context token"}
    )

    summary = report["host_chassis_context_summary"]
    assert summary["project_context"] == "generic / unspecified"
    assert summary["project_context_label"] == "Generic / unspecified"
    assert summary["contexts_present"] == ["generic / unspecified"]
    assert "Active project context: Generic / unspecified" in report["markdown"]


def test_project_review_report_treats_plant_as_supported_context_not_default(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    report = build_project_review_report(
        {"id": 803, "name": "Plant context report", "host": "Nicotiana benthamiana"}
    )

    summary = report["host_chassis_context_summary"]
    assert summary["project_context"] == "plant"
    assert summary["plant_is_supported_example_only"] is True
    assert "Plant and Nicotiana examples may appear as examples, not as default or preferred contexts." in report["markdown"]


def test_project_review_report_host_context_copy_avoids_recommendation_validation_and_readiness_claims(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)
    text = str(
        build_project_review_report(
            {"id": 804, "name": "Host context safety report", "host": "Pichia pastoris"}
        )["host_chassis_context_summary"]
    ).lower()

    forbidden = [
        "recommended",
        "validated construct",
        "optimized pathway",
        "readiness score",
        "experiment-ready",
        "production-ready",
        "compatibility proof",
        "host recommendation",
        "synthesis ready",
        "wet-lab ready",
    ]
    for phrase in forbidden:
        assert phrase not in text
    assert "documentation context only" in text


def test_documentation_review_notes_render_in_report_markdown(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {
            "id": 9,
            "name": "Documentation review notes",
            "documentation_review": {
                "review_notes": "Reviewer confirmed the documentation checklist is complete.",
            },
        }
    )

    assert "Reviewer confirmed the documentation checklist is complete." in report["markdown"]


def test_documentation_review_actions_or_unresolved_items_satisfy_review_notes_gap(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {
            "id": 10,
            "name": "Documentation review actions",
            "documentation_review": {
                "follow_up_actions": ["Add source citation to pathway step 2."],
                "unresolved_items": ["Confirm linked artifact title."],
            },
        }
    )

    gap_ids = {gap["gap_id"] for gap in report["missing_fields"]}
    assert "review_notes_missing" not in gap_ids
    assert "Review notes missing" not in report["markdown"]
    assert "Add source citation to pathway step 2." in report["markdown"]
    assert "Confirm linked artifact title." in report["markdown"]


def test_placeholder_documentation_review_values_count_as_missing_review_notes(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {
            "id": 12,
            "name": "Placeholder review notes",
            "documentation_review": {
                "review_notes": "Unknown",
                "reviewer": "TBD",
                "review_date": "N/A",
                "follow_up_actions": ["Not specified", "Record pathway step source context."],
                "unresolved_items": ["None"],
            },
            "review_notes": "No review note recorded",
        }
    )

    gap_ids = {gap["gap_id"] for gap in report["missing_fields"]}
    assert "review_notes_missing" not in gap_ids
    assert "Record pathway step source context." in report["markdown"]
    assert "Reviewer: TBD" not in report["markdown"]
    assert "Review date: N/A" not in report["markdown"]
    assert "- Unknown" not in report["markdown"]
    assert "- Not specified" not in report["markdown"]
    assert "- None" not in report["markdown"]
    assert "No review note recorded" not in report["markdown"]


def test_placeholder_only_documentation_review_keeps_review_notes_gap(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {
            "id": 13,
            "name": "Placeholder-only review notes",
            "documentation_review": {
                "review_notes": "Unknown",
                "reviewer": "TBD",
                "follow_up_actions": ["N/A", ""],
                "unresolved_items": ["Not specified"],
            },
            "notes": "None",
        }
    )

    gap_ids = {gap["gap_id"] for gap in report["missing_fields"]}
    assert "review_notes_missing" in gap_ids
    assert "No review notes are recorded." in report["markdown"]
    assert "Reviewer: TBD" not in report["markdown"]
    assert "- Unknown" not in report["markdown"]


def test_legacy_top_level_review_notes_remain_supported(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {
            "id": 11,
            "name": "Legacy review notes",
            "review_notes": "Legacy top-level review note remains visible.",
        }
    )

    assert "Legacy top-level review note remains visible." in report["markdown"]


def test_no_misleading_claims_in_service_output(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    text = str(build_project_review_report({"id": 8, "name": "Claims"})).lower()

    forbidden = [
        "recommend" + "ed",
        "best",
        "optimal",
        "validation success",
        "successful cloning",
        "successful pcr",
        "successful expression",
        "valid" + "ated construct",
        "approv" + "ed",
        "compatible",
        "suitable",
        "ready for " + "synthesis",
        "ready for " + "wet lab",
        "experimentally " + "confirmed",
        "ready for experiment",
        "experiment-ready",
        "production-ready",
        "yield " + "prediction",
        "optimized pathway",
        "successful import",
        "valid" + "ated import",
    ]
    for phrase in forbidden:
        assert phrase not in text


def _r242_step2_component_context() -> dict[str, object]:
    rows = [
        {
            "key": "host_context",
            "category": "host/context",
            "step2_value": "E. coli review context",
            "context_state": "recorded context",
            "asset_label": "Bacterial host context note",
            "asset_id": "host-context-r242",
            "recorded_context": "Host/context documentation note for source/provenance review.",
            "source_provenance_review": "source review needed",
            "record_review_status": "record review pending",
            "sequence_metadata": "sequence metadata not recorded",
            "manual_follow_up": "Manual follow-up before citing this context in project notes.",
        },
        {
            "key": "promoter",
            "category": "promoter",
            "step2_value": "T7 promoter review label",
            "context_state": "recorded context",
            "asset_label": "T7 promoter documentation record",
            "asset_id": "promoter-r242",
            "recorded_context": "Promoter record for documentation-only review context.",
            "source_provenance_review": "source review needed",
            "record_review_status": "record review pending",
            "sequence_metadata": "sequence metadata recorded",
            "manual_follow_up": "Review source/provenance review before citing in project notes.",
        },
    ]
    return {
        "rows": rows,
        "summary": {
            "total_rows": len(rows),
            "rows_with_recorded_assets": len(rows),
            "manual_follow_up_rows": 0,
        },
        "documentation_boundary_note": (
            "Step 2 recorded Component Library context is a documentation-only read-only review appendix; "
            "not saved as construct evidence and not a biological recommendation."
        ),
    }


def test_project_review_report_includes_r242_step2_component_context_appendix(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report(
        {"id": 242, "name": "R242 appendix report"},
        step2_component_context=_r242_step2_component_context(),
    )
    appendix = report["step2_component_context_appendix"]
    markdown = report["markdown"]
    draft_markdown = report["detailed_documentation_report_draft"]["markdown"]
    handoff = report["project_review_handoff_center"]

    assert appendix["status"] == "AVAILABLE"
    assert appendix["total_rows_available"] == 2
    assert appendix["summary"] == {
        "total_rows": 2,
        "rows_with_recorded_assets": 2,
        "manual_follow_up_rows": 0,
    }
    assert appendix["columns"] == construct_presenter.STEP2_COMPONENT_CONTEXT_COLUMNS
    for text in [
        "Step 2 recorded Component Library context appendix",
        "Read-only review appendix",
        "host/context",
        "promoter",
        "source/provenance review",
        "Record review status",
        "Sequence metadata",
        "Manual follow-up",
        "not saved as construct evidence",
        "not a biological recommendation",
    ]:
        assert text in markdown
        assert text in draft_markdown
    assert handoff["step2_component_context_appendix"]["status"] == "AVAILABLE"
    assert "Step 2 recorded Component Library context appendix" in handoff["markdown"]
    assert "T7 promoter documentation record / promoter-r242" in handoff["markdown"]
    assert not any("step2" in gap["gap_id"].casefold() for gap in report["missing_fields"])

    combined = f"{appendix}\n{markdown}\n{draft_markdown}\n{handoff}".lower()
    for forbidden in [
        "best host",
        "best promoter",
        "optimized",
        "high-expression",
        "validated",
        "wet-lab ready",
        "expression improvement",
    ]:
        assert forbidden not in combined


def test_project_review_report_r242_step2_component_context_empty_state_is_safe(monkeypatch) -> None:
    _empty_construct_report_views(monkeypatch)

    report = build_project_review_report({"id": 243, "name": "R242 empty appendix"})
    appendix = report["step2_component_context_appendix"]

    assert appendix["status"] == "NOT_AVAILABLE"
    assert appendix["rows"] == []
    assert appendix["summary"]["total_rows"] == 0
    assert appendix["empty_state_message"] == (
        "No current Step 2 Component Library context is available for this review appendix."
    )
    assert appendix["empty_state_message"] in report["markdown"]
    assert appendix["empty_state_message"] in report["project_review_handoff_center"]["markdown"]
    assert not any("step2" in gap["gap_id"].casefold() for gap in report["missing_fields"])
