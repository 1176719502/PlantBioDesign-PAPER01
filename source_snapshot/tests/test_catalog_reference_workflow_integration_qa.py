from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import catalog_reference_basket_service as basket_service
from services import expression_construct_repository as construct_repo
from services import project_asset_linkage_service as linkage_service
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services.project_catalog_reference_overview_presenter import (
    build_project_catalog_reference_overview,
)
from services.project_documentation_package_exporter import (
    build_project_documentation_export_package,
)
from services.project_documentation_package_importer import (
    validate_project_documentation_package,
)
from services.project_review_report_service import build_project_review_report
import views.pathway_workspace_sections.project_documentation_package_section as package_section


def _use_temp_db(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "catalog_reference_workflow_integration.db"
    monkeypatch.setattr(construct_repo, "DB_PATH", str(db_path))
    monkeypatch.setattr(project_catalog_link_repo, "DB_PATH", str(db_path))


def _project() -> dict[str, str]:
    return {"id": "project-r50", "name": "R50 workflow QA"}


def _link_payload(
    *,
    asset_id: str,
    asset_display_name: str,
    context: str = "Pathway Workspace linked catalog assets",
    reference_origin: str = "Project documentation reference",
    include_snapshot: bool = True,
) -> dict[str, object]:
    asset_snapshot = {
        "asset_type": "plant_promoter_profile",
        "asset_id": asset_id,
        "asset_label": asset_display_name,
        "asset_version": "catalog-v1",
        "source_label": "Fixture source: QA",
        "documentation_status": "source review needed",
        "species": "Zea mays (maize)",
        "clade": "monocot",
        "aliases": [],
        "tissue_contexts": ["root"],
        "motif_labels": [],
        "limitation_note": "Pinned documentation snapshot for QA review only.",
    } if include_snapshot else {}
    return linkage_service.build_project_asset_link(
        project_id="project-r50",
        asset_id=asset_id,
        asset_display_name=asset_display_name,
        asset_type="plant_promoter_profile",
        linkage_role="source_review_context",
        documentation_note="Documentation-only Plant Promoter Catalog reference for project traceability.",
        source_context_snapshot={
            "catalog": "Plant Promoter Catalog",
            "profile_id": asset_id,
            "plant_clade": "monocot",
            "species": "Zea mays (maize)",
            "source_labels": "Fixture source: QA",
            "project_documentation_context": context,
            "reference_origin": reference_origin,
        },
        review_status_snapshot={
            "curation_statuses": "source review needed",
            "missing_metadata_count": 1,
        },
        asset_snapshot=asset_snapshot,
        linked_at="2026-06-18T09:00:00Z",
        human_review_required=True,
    )


def test_catalog_reference_workflow_filters_staged_rows_until_persisted_across_surfaces(
    tmp_path,
    monkeypatch,
) -> None:
    _use_temp_db(tmp_path, monkeypatch)
    project = _project()
    session_state: dict[str, object] = {}

    staged_entry = basket_service.build_catalog_reference_basket_entry(
        project_id=project["id"],
        link_payload=_link_payload(
            asset_id="plant-promoter-staged",
            asset_display_name="Staged promoter profile",
            include_snapshot=False,
        ),
        project_documentation_context="Pathway Workspace linked catalog assets",
        documentation_note="Documentation-only Plant Promoter Catalog reference for project traceability.",
    )
    added_to_basket, _stored_entry = basket_service.add_catalog_reference_basket_entry(session_state, staged_entry)
    assert added_to_basket is True
    assert len(
        basket_service.list_catalog_reference_basket(session_state, project_id=project["id"])
    ) == 1

    empty_package = build_project_documentation_export_package(project=project, project_id=project["id"])
    empty_overview = build_project_catalog_reference_overview(project)
    empty_report = build_project_review_report(project)
    empty_package_summary = package_section._project_catalog_reference_summary(project)

    assert empty_package["project_catalog_asset_links"] == []
    assert empty_overview["total_catalog_links"] == 0
    assert (
        empty_report["detailed_documentation_report_draft"]["linked_catalog_assets"]["linked_catalog_asset_count"]
        == 0
    )
    assert empty_package_summary["linked_catalog_asset_count"] == 0

    staged_marker_added, _message, _staged_marker_row = project_catalog_link_repo.add_project_catalog_asset_link(
        {
            **_link_payload(
                asset_id="plant-promoter-staged-marker",
                asset_display_name="Staged marker profile",
                context="Staged basket context",
                reference_origin="Staged basket",
                include_snapshot=False,
            ),
            "project_documentation_context": "Staged basket context",
        }
    )
    assert staged_marker_added is True

    filtered_package = build_project_documentation_export_package(project=project, project_id=project["id"])
    filtered_overview = build_project_catalog_reference_overview(project)
    filtered_report = build_project_review_report(project)
    filtered_package_summary = package_section._project_catalog_reference_summary(project)

    assert filtered_package["project_catalog_asset_links"] == []
    assert filtered_overview["total_catalog_links"] == 0
    assert (
        filtered_report["detailed_documentation_report_draft"]["linked_catalog_assets"]["linked_catalog_asset_count"]
        == 0
    )
    assert filtered_package_summary["linked_catalog_asset_count"] == 0

    persisted_added, _message, _persisted_row = project_catalog_link_repo.add_project_catalog_asset_link(
        _link_payload(
            asset_id="plant-promoter-persisted",
            asset_display_name="Persisted promoter profile",
            include_snapshot=True,
        )
    )
    assert persisted_added is True

    package = build_project_documentation_export_package(project=project, project_id=project["id"])
    overview = build_project_catalog_reference_overview(project)
    report = build_project_review_report(project)
    package_summary = package_section._project_catalog_reference_summary(project)
    validation = validate_project_documentation_package(package)

    assert package["package_metadata"]["counts"]["project_catalog_asset_link_count"] == 1
    assert [row["asset_id"] for row in package["project_catalog_asset_links"]] == [
        "plant-promoter-persisted"
    ]
    assert overview["total_catalog_links"] == 1
    assert [row["record_identifier"] for row in overview["linked_catalog_assets"]] == [
        "plant-promoter-persisted"
    ]
    assert (
        report["detailed_documentation_report_draft"]["linked_catalog_assets"]["linked_catalog_asset_count"]
        == 1
    )
    assert (
        report["detailed_documentation_report_draft"]["linked_catalog_assets"]["linked_references"][0][
            "linked_persisted_status"
        ]
        == "Persisted linked catalog reference"
    )
    assert package_summary["linked_catalog_asset_count"] == 1
    assert package_summary["project_documentation_contexts"] == [
        "Pathway Workspace linked catalog assets"
    ]
    assert validation["catalog_reference_import_review_summary"]["total_rows_in_package"] == 1
    assert (
        validation["catalog_reference_import_review_summary"]["complete_documentation_context_count"]
        == 1
    )
    assert (
        validation["catalog_reference_import_review_summary"]["staged_rows_excluded_count"]
        == 0
    )


def test_catalog_reference_workflow_duplicate_persisted_link_does_not_duplicate_outputs(
    tmp_path,
    monkeypatch,
) -> None:
    _use_temp_db(tmp_path, monkeypatch)
    project = _project()
    link_payload = _link_payload(
        asset_id="plant-promoter-duplicate",
        asset_display_name="Duplicate-guard promoter profile",
        include_snapshot=True,
    )

    first_added, _message, first_row = project_catalog_link_repo.add_project_catalog_asset_link(link_payload)
    second_added, second_message, second_row = project_catalog_link_repo.add_project_catalog_asset_link(link_payload)

    package = build_project_documentation_export_package(project=project, project_id=project["id"])
    overview = build_project_catalog_reference_overview(project)
    report = build_project_review_report(project)
    package_summary = package_section._project_catalog_reference_summary(project)

    assert first_added is True
    assert second_added is False
    assert "already exists" in second_message.lower()
    assert second_row["link_id"] == first_row["link_id"]
    assert package["package_metadata"]["counts"]["project_catalog_asset_link_count"] == 1
    assert len(package["project_catalog_asset_links"]) == 1
    assert overview["total_catalog_links"] == 1
    assert (
        report["detailed_documentation_report_draft"]["linked_catalog_assets"]["linked_catalog_asset_count"]
        == 1
    )
    assert package_summary["linked_catalog_asset_count"] == 1
