from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.project_catalog_reference_overview_presenter import build_project_catalog_reference_overview


def test_new_overview_user_visible_copy_avoids_claim_terms() -> None:
    checked_files = [
        os.path.join(ROOT, "services", "project_catalog_reference_overview_presenter.py"),
        os.path.join(ROOT, "views", "PathwayProjects.py"),
        os.path.join(ROOT, "views", "PathwayWorkspace.py"),
    ]
    forbidden_terms = [
        "best",
        "optimal",
        "approved",
        "safe for use",
        "ready for synthesis",
        "ready for wet lab",
        "experimentally confirmed",
        "host compatible",
        "ranking",
    ]
    combined = "\n".join(open(path, encoding="utf-8").read().lower() for path in checked_files)

    for term in forbidden_terms:
        assert term not in combined

    for allowed_negated_boundary in [
        "not recommendation",
        "not validation",
        "not readiness",
        "not prediction",
    ]:
        assert allowed_negated_boundary in combined


def test_empty_project_overview_uses_safe_empty_state(monkeypatch) -> None:
    import services.project_catalog_reference_overview_presenter as presenter

    monkeypatch.setattr(presenter.project_catalog_link_repo, "list_project_catalog_asset_links", lambda project_id: [])
    monkeypatch.setattr(
        presenter,
        "build_project_documentation_export_package",
        lambda **kwargs: {
            "package_metadata": {
                "package_kind": "BioDesign Studio project documentation package",
                "package_version": "2.6-r39",
                "counts": {"project_catalog_asset_link_count": 0},
                "included_sections": ["project_catalog_asset_links"],
            },
            "documentation_only_boundary": "documentation-only",
        },
    )
    monkeypatch.setattr(
        presenter,
        "build_manifest_review_summary",
        lambda package: {"review_notes": [], "documentation_boundary": "documentation-only", "compatibility_notes": []},
    )
    monkeypatch.setattr(
        presenter,
        "build_project_quality_dashboard",
        lambda project, linked_catalog_assets=None: {"overall_documentation_status": "NOT_AVAILABLE"},
    )
    monkeypatch.setattr(
        presenter,
        "build_project_review_report",
        lambda project: {"overall_summary": "Documentation-only review report for the active pathway documentation project."},
    )

    overview = build_project_catalog_reference_overview({"id": 1, "name": "Empty"})

    assert overview["total_catalog_links"] == 0
    assert overview["plant_promoter_link_count"] == 0
    assert overview["pinned_snapshot_count"] == 0
    assert overview["missing_snapshot_count"] == 0
    assert overview["missing_source_or_review_metadata_count"] == 0
    assert overview["linked_catalog_assets"] == []
    assert "No catalog references are recorded" in overview["coverage_note"]


def test_overview_counts_links_and_orders_rows_deterministically(monkeypatch) -> None:
    import services.project_catalog_reference_overview_presenter as presenter

    monkeypatch.setattr(
        presenter.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 2,
                "asset_id": "b-2",
                "asset_label": "Beta asset",
                "asset_type": "other_reference",
                "linkage_role": "report_context",
                "asset_snapshot": {},
                "source_label": "",
                "documentation_status": "",
                "notes": "beta note",
                "source_context_snapshot": {},
                "review_status_snapshot": {},
            },
            {
                "project_id": 2,
                "asset_id": "a-1",
                "asset_label": "Alpha promoter",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "asset_snapshot": {
                    "asset_label": "Alpha promoter",
                    "asset_type": "plant_promoter_profile",
                    "source_label": "Source A",
                    "documentation_status": "Reviewed",
                },
                "source_label": "Source A",
                "documentation_status": "Reviewed",
                "notes": "alpha note",
                "source_context_snapshot": {"source_label": "Source A"},
                "review_status_snapshot": {"review_status": "Reviewed"},
            },
        ],
    )
    monkeypatch.setattr(
        presenter,
        "build_project_documentation_export_package",
        lambda **kwargs: {
            "package_metadata": {
                "package_kind": "BioDesign Studio project documentation package",
                "package_version": "2.6-r39",
                "counts": {"project_catalog_asset_link_count": 2},
                "included_sections": ["project_catalog_asset_links"],
            },
            "documentation_only_boundary": "documentation-only",
        },
    )
    monkeypatch.setattr(
        presenter,
        "build_manifest_review_summary",
        lambda package: {
            "review_notes": ["note one"],
            "documentation_boundary": "documentation-only",
            "compatibility_notes": ["compat one"],
        },
    )
    monkeypatch.setattr(
        presenter,
        "build_project_quality_dashboard",
        lambda project, linked_catalog_assets=None: {"overall_documentation_status": "NEEDS_REVIEW"},
    )
    monkeypatch.setattr(
        presenter,
        "build_project_review_report",
        lambda project: {"overall_summary": "Documentation-only review report for the active pathway documentation project."},
    )

    overview = build_project_catalog_reference_overview({"id": 2, "name": "Project"})

    assert overview["total_catalog_links"] == 2
    assert overview["plant_promoter_link_count"] == 1
    assert overview["pinned_snapshot_count"] == 1
    assert overview["missing_snapshot_count"] == 1
    assert overview["missing_source_or_review_metadata_count"] == 1
    assert [row["asset_id"] for row in overview["linked_catalog_assets"]] == ["b-2", "a-1"]
    assert overview["linked_catalog_assets"][0]["record_identifier"] == "b-2"
    assert overview["linked_catalog_assets"][0]["catalog_label"] == "Local Design Asset Catalog"
    assert overview["linked_catalog_assets"][0]["catalog_source_status"] == "Local Design Asset Catalog / Source status not recorded / Not recorded"
    assert overview["linked_catalog_assets"][0]["source_context_readback"] == "Source context readback: catalog Local Design Asset Catalog; source/provenance review Source status not recorded"
    assert overview["linked_catalog_assets"][0]["host_chassis_context_readback"] == "Recorded host / chassis context only: Not recorded; normalized review context: Generic / unspecified. This is source/readback context, not compatibility evidence."
    assert overview["linked_catalog_assets"][0]["review_needed_context"] == "Review-needed context: curation status Not recorded; human review flag not recorded"
    assert overview["linked_catalog_assets"][0]["metadata_gap_context"] == "Review gap: missing source context and record review status for documentation review"
    assert overview["linked_catalog_assets"][0]["catalog_reference_context"] == "Catalog reference context: origin Project documentation reference; link state Linked catalog reference; snapshot state live metadata fallback"
    assert overview["linked_catalog_assets"][0]["reference_origin"] == "Project documentation reference"
    assert overview["linked_catalog_assets"][0]["project_documentation_context"] == "Documentation context not provided"
    assert overview["linked_catalog_assets"][0]["snapshot_state"] == "live metadata fallback"
    assert overview["linked_catalog_assets"][1]["snapshot_state"] == "pinned snapshot"
    assert overview["linked_catalog_assets"][1]["record_identifier"] == "a-1"
    assert overview["linked_catalog_assets"][1]["catalog_label"] == "Plant Promoter Catalog"
    assert overview["linked_catalog_assets"][1]["catalog_source_status"] == "Plant Promoter Catalog / Source A / Reviewed"
    assert overview["linked_catalog_assets"][1]["source_context_readback"] == "Source context readback: catalog Plant Promoter Catalog; source/provenance review Source A"
    assert overview["linked_catalog_assets"][1]["host_chassis_context_readback"] == "Recorded host / chassis context only: Not recorded; normalized review context: Generic / unspecified. This is source/readback context, not compatibility evidence."
    assert overview["linked_catalog_assets"][1]["review_needed_context"] == "Review-needed context: curation status Reviewed; human review flag not recorded"
    assert overview["linked_catalog_assets"][1]["metadata_gap_context"] == "Source/provenance and record review status recorded for documentation review"
    assert overview["linked_catalog_assets"][1]["catalog_reference_context"] == "Catalog reference context: origin Project documentation reference; link state Linked catalog reference; snapshot state pinned documentation snapshot"
    assert overview["linked_catalog_assets"][1]["project_documentation_context"] == "Documentation context not provided"
    assert overview["package_export_context"]["record_count"] == 2
    assert overview["package_import_context"]["review_note_count"] == 1


def test_overview_prefers_pinned_snapshot_metadata_over_live_fallback(monkeypatch) -> None:
    import services.project_catalog_reference_overview_presenter as presenter

    monkeypatch.setattr(
        presenter.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 3,
                "asset_id": "prom-1",
                "asset_label": "Pinned promoter",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "asset_snapshot": {
                    "asset_label": "Pinned promoter",
                    "asset_type": "plant_promoter_profile",
                    "source_label": "Pinned source",
                    "documentation_status": "Pinned review",
                },
                "source_label": "Live source",
                "documentation_status": "Live review",
                "notes": "pinned note",
                "source_context_snapshot": {"source_label": "Live source"},
                "review_status_snapshot": {"review_status": "Live review"},
            }
        ],
    )
    monkeypatch.setattr(
        presenter,
        "build_project_documentation_export_package",
        lambda **kwargs: {
            "package_metadata": {
                "package_kind": "BioDesign Studio project documentation package",
                "package_version": "2.6-r39",
                "counts": {"project_catalog_asset_link_count": 1},
                "included_sections": ["project_catalog_asset_links"],
            },
            "documentation_only_boundary": "documentation-only",
        },
    )
    monkeypatch.setattr(
        presenter,
        "build_manifest_review_summary",
        lambda package: {"review_notes": [], "documentation_boundary": "documentation-only", "compatibility_notes": []},
    )
    monkeypatch.setattr(
        presenter,
        "build_project_quality_dashboard",
        lambda project, linked_catalog_assets=None: {"overall_documentation_status": "AVAILABLE"},
    )
    monkeypatch.setattr(
        presenter,
        "build_project_review_report",
        lambda project: {"overall_summary": "Documentation-only review report for the active pathway documentation project."},
    )

    overview = build_project_catalog_reference_overview({"id": 3, "name": "Pinned"})

    row = overview["linked_catalog_assets"][0]
    assert row["snapshot_state"] == "pinned snapshot"
    assert row["source_label"] == "Pinned source"
    assert row["documentation_status"] == "Pinned review"
    assert row["catalog_source_status"] == "Plant Promoter Catalog / Pinned source / Pinned review"
    assert row["project_documentation_context"] == "Documentation context not provided"
    assert overview["pinned_snapshot_count"] == 1


def test_overview_uses_persisted_links_when_transient_links_are_passed(monkeypatch) -> None:
    import services.project_catalog_reference_overview_presenter as presenter

    monkeypatch.setattr(
        presenter.project_catalog_link_repo,
        "list_project_catalog_asset_links",
        lambda project_id: [
            {
                "project_id": 4,
                "asset_id": "persisted-1",
                "asset_label": "Persisted reference",
                "asset_type": "plant_promoter_profile",
                "linkage_role": "source_review_context",
                "asset_snapshot": {
                    "asset_label": "Persisted reference",
                    "asset_type": "plant_promoter_profile",
                    "source_label": "Persisted source",
                    "documentation_status": "Reviewed",
                },
                "source_label": "Persisted source",
                "documentation_status": "Reviewed",
                "notes": "persisted note",
                "source_context_snapshot": {"source_label": "Persisted source"},
                "review_status_snapshot": {"review_status": "Reviewed"},
            }
        ],
    )
    monkeypatch.setattr(
        presenter,
        "build_project_documentation_export_package",
        lambda **kwargs: {
            "package_metadata": {
                "package_kind": "BioDesign Studio project documentation package",
                "package_version": "2.6-r39",
                "counts": {"project_catalog_asset_link_count": 1},
                "included_sections": ["project_catalog_asset_links"],
            },
            "documentation_only_boundary": "documentation-only",
        },
    )
    monkeypatch.setattr(
        presenter,
        "build_manifest_review_summary",
        lambda package: {"review_notes": [], "documentation_boundary": "documentation-only", "compatibility_notes": []},
    )
    monkeypatch.setattr(
        presenter,
        "build_project_quality_dashboard",
        lambda project, linked_catalog_assets=None: {"overall_documentation_status": "AVAILABLE"},
    )
    monkeypatch.setattr(
        presenter,
        "build_project_review_report",
        lambda project: {"overall_summary": "Documentation-only review report for the active pathway documentation project."},
    )

    overview = build_project_catalog_reference_overview(
        {"id": 4, "name": "Project"},
        linked_catalog_assets=[
            {
                "project_id": 4,
                "asset_id": "transient-1",
                "asset_label": "Transient reference",
                "asset_type": "promoter",
                "linkage_role": "project_reference",
            }
        ],
    )

    assert overview["total_catalog_links"] == 1
    assert [row["asset_id"] for row in overview["linked_catalog_assets"]] == ["persisted-1"]
