from __future__ import annotations

from typing import Any

from services.catalog_asset_snapshot_builder import catalog_asset_snapshot_has_content
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services.plant_promoter_catalog_workspace_presenter import summarize_linked_plant_promoter_references
from services.project_catalog_reference_output_formatter import (
    build_linked_catalog_reference_output,
    has_staged_basket_only_markers,
)
from services.project_quality_dashboard_service import build_project_quality_dashboard
from services.project_review_report_service import build_project_review_report
from services.project_documentation_package_exporter import build_project_documentation_export_package
from services.project_documentation_package_importer import build_manifest_review_summary

OVERVIEW_TITLE = "Catalog Reference Overview"
OVERVIEW_VERSION = "1.0"


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _first_present(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _project_identity(project: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": _first_present(project, ("project_id", "id")),
        "project_name": _first_present(project, ("project_name", "name", "target_product")),
        "description": _first_present(project, ("description", "project_description")),
    }


def _build_coverage_note(*, project: dict[str, Any], linked_count: int, pinned_count: int, missing_snapshot_count: int, missing_metadata_count: int) -> str:
    project_id = _first_present(project, ("project_id", "id"))
    if linked_count == 0:
        return "No catalog references are recorded for this project yet."
    note = f"{linked_count} catalog references"
    if pinned_count:
        note += f"; {pinned_count} pinned snapshot(s)"
    if missing_snapshot_count:
        note += f"; {missing_snapshot_count} without pinned snapshot metadata"
    if missing_metadata_count:
        note += f"; {missing_metadata_count} with missing source/provenance or record review status"
    if project_id not in (None, ""):
        note += f"; project {project_id}"
    return note + "."


def _row_view(link: dict[str, Any]) -> dict[str, Any]:
    row = build_linked_catalog_reference_output(link)
    row["asset_label"] = row.get("asset_display_name", "")
    row["staged_reference_label"] = "Staged documentation reference"
    return row


def _link_missing_source_or_review_metadata(link: dict[str, Any]) -> bool:
    snapshot = link.get("asset_snapshot") if isinstance(link.get("asset_snapshot"), dict) else {}
    source_snapshot = link.get("source_context_snapshot") if isinstance(link.get("source_context_snapshot"), dict) else {}
    review_snapshot = link.get("review_status_snapshot") if isinstance(link.get("review_status_snapshot"), dict) else {}
    source_label = _text(
        snapshot.get("source_label")
        or link.get("source_label")
        or source_snapshot.get("source_label")
        or source_snapshot.get("source_labels")
        or source_snapshot.get("source_provenance_status")
    )
    review_status = _text(
        snapshot.get("documentation_status")
        or link.get("documentation_status")
        or review_snapshot.get("review_status")
        or review_snapshot.get("curation_statuses")
        or review_snapshot.get("human_review_status")
    )
    return not (source_label and review_status)


def build_project_catalog_reference_overview(
    project: dict[str, Any] | None,
    *,
    linked_catalog_assets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    project_data = project if isinstance(project, dict) else {}
    project_id = _first_present(project_data, ("project_id", "id"))
    linked_catalog_asset_list: list[dict[str, Any]] = []
    if project_id not in (None, ""):
        try:
            linked_catalog_asset_list = project_catalog_link_repo.list_project_catalog_asset_links(project_id)
        except Exception:
            linked_catalog_asset_list = []
    linked_catalog_asset_list = [
        link for link in linked_catalog_asset_list if not has_staged_basket_only_markers(link)
    ]

    summary = summarize_linked_plant_promoter_references(linked_catalog_asset_list)
    pinned_snapshot_count = sum(1 for link in linked_catalog_asset_list if catalog_asset_snapshot_has_content(link.get("asset_snapshot")))
    missing_snapshot_count = len(linked_catalog_asset_list) - pinned_snapshot_count
    missing_metadata_count = sum(1 for link in linked_catalog_asset_list if _link_missing_source_or_review_metadata(link))
    rows = sorted(
        (_row_view(link) for link in linked_catalog_asset_list),
        key=lambda row: (
            _text(row.get("asset_type")).casefold(),
            _text(row.get("asset_label")).casefold(),
            _text(row.get("asset_id")).casefold(),
            _text(row.get("linkage_role")).casefold(),
        ),
    )

    export_package = (
        build_project_documentation_export_package(project=project_data, project_id=project_id)
        if project_id not in (None, "")
        else {}
    )
    manifest_review = build_manifest_review_summary(export_package)
    report_project = {**project_data, "project_id": project_id, "project_asset_links": linked_catalog_asset_list}
    quality_dashboard = build_project_quality_dashboard(
        report_project,
        linked_catalog_assets=linked_catalog_asset_list,
    )
    review_report = build_project_review_report(report_project)

    linked_count = len(rows)
    overview = {
        "overview_title": OVERVIEW_TITLE,
        "overview_version": OVERVIEW_VERSION,
        "project_identity": _project_identity(project_data),
        "total_catalog_links": linked_count,
        "plant_promoter_link_count": int(summary.get("linked_promoter_count", 0) or 0),
        "pinned_snapshot_count": pinned_snapshot_count,
        "missing_snapshot_count": missing_snapshot_count,
        "missing_source_or_review_metadata_count": missing_metadata_count,
        "coverage_note": _build_coverage_note(
            project=project_data,
            linked_count=linked_count,
            pinned_count=pinned_snapshot_count,
            missing_snapshot_count=missing_snapshot_count,
            missing_metadata_count=missing_metadata_count,
        ),
        "package_export_context": {
            "package_kind": export_package.get("package_metadata", {}).get("package_kind", ""),
            "package_version": export_package.get("package_metadata", {}).get("package_version", ""),
            "record_count": int(
                export_package.get("package_metadata", {}).get("counts", {}).get("project_catalog_asset_link_count", 0) or 0
            ),
            "documentation_only_boundary": export_package.get("documentation_only_boundary", ""),
            "included_sections": list(export_package.get("package_metadata", {}).get("included_sections", []) or []),
        },
        "package_import_context": {
            "review_note_count": len(manifest_review.get("review_notes") or []),
            "documentation_boundary": manifest_review.get("documentation_boundary", ""),
            "compatibility_note_count": len(manifest_review.get("compatibility_notes") or []),
        },
        "manifest_review_note": f"{len(manifest_review.get('review_notes') or [])} manifest review note(s) recorded.",
        "review_report_note": review_report.get("overall_summary", "Documentation-only review report context."),
        "quality_dashboard_note": quality_dashboard.get("overall_documentation_status", "NOT_AVAILABLE"),
        "linked_catalog_assets": rows,
        "summary": summary,
    }
    return overview
