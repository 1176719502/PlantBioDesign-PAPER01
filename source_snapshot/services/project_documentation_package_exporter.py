from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from services import expression_construct_presenter as presenter
from services import expression_construct_repository as repo
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services.catalog_asset_snapshot_builder import (
    SNAPSHOT_SCHEMA_VERSION,
    catalog_asset_snapshot_has_content,
    sanitize_catalog_asset_snapshot,
)
from services.expression_wizard_catalog_picker_presenter import build_expression_wizard_catalog_traceability_summary
from services.plant_promoter_catalog_workspace_presenter import summarize_linked_plant_promoter_references
from services.project_catalog_reference_output_formatter import build_linked_catalog_reference_output
from services.project_catalog_reference_output_formatter import has_staged_basket_only_markers

PACKAGE_KIND = "BioDesign Studio project documentation package"
LEGACY_PACKAGE_VERSION = "2.6-r24"
PACKAGE_VERSION = "2.6-r39"
PACKAGE_FORMAT = "biodesign-studio-project-documentation-package"
PACKAGE_SCHEMA_VERSION = "2.6-r39"
EXPORTED_BY_APP = "BioDesign Studio"
DOCUMENTATION_ONLY_BOUNDARY = (
    "This documentation-only local project package preserves metadata for review and traceability only. "
    "It does not make downstream-use claims or biological outcome claims for any project, construct, "
    "cassette, promoter, gene, pathway step, report, or export."
)
CSV_DEFERRED_NOTE = (
    "CSV import/export is deferred for this foundation slice; the supported package shape is a "
    "deterministic JSON-compatible metadata dictionary."
)

_PROFILE_FIELDS = (
    "construct_id",
    "construct_label",
    "construct_type",
    "plasmid_backbone",
    "host_context_note",
    "source_reference",
    "provenance_note",
    "review_status",
    "documentation_scope_note",
    "created_at",
    "updated_at",
)
_CASSETTE_FIELDS = (
    "cassette_id",
    "construct_id",
    "cassette_label",
    "cassette_role",
    "cassette_order",
    "promoter_label",
    "gene_label",
    "terminator_label",
    "source_reference",
    "provenance_note",
    "created_at",
    "updated_at",
)
_PART_FIELDS = (
    "id",
    "cassette_id",
    "part_order",
    "part_role",
    "part_label",
    "part_reference",
    "source_reference",
    "source_catalog",
    "source_record_id",
    "source_record_label",
    "evidence_context_note",
    "provenance_note",
    "created_at",
    "updated_at",
)
_GENE_LINK_FIELDS = (
    "id",
    "construct_id",
    "gene_label",
    "gene_reference",
    "source_reference",
    "provenance_note",
    "created_at",
)
_PATHWAY_LINK_FIELDS = (
    "id",
    "construct_id",
    "pathway_step_id",
    "pathway_step_label",
    "source_reference",
    "provenance_note",
    "created_at",
)
_PROJECT_LINK_FIELDS = (
    "id",
    "project_id",
    "construct_id",
    "construct_label",
    "construct_type",
    "construct_review_status",
    "link_label",
    "link_note",
    "source_context",
    "curation_status",
    "review_note",
    "created_at",
    "updated_at",
)
_CATALOG_REFERENCE_LINK_FIELDS = (
    "link_id",
    "project_id",
    "asset_type",
    "asset_id",
    "asset_label",
    "asset_version",
    "source_label",
    "documentation_status",
    "notes",
    "linkage_role",
    "human_review_required",
    "snapshot_schema_version",
    "asset_snapshot",
    "snapshot_captured_at",
    "created_at",
    "updated_at",
)
_CATALOG_REFERENCE_OUTPUT_FIELDS = (
    "record_identifier",
    "catalog_label",
    "catalog_name_source",
    "catalog_source_status",
    "reference_origin",
    "project_documentation_context",
    "documentation_note",
    "linked_reference_label",
    "linked_persisted_status",
    "snapshot_state",
)
INCLUDED_SECTIONS = (
    "project_metadata",
    "project_construct_links",
    "project_catalog_asset_links",
    "construct_profiles",
    "expression_cassettes",
    "cassette_parts",
    "linked_genes",
    "linked_pathway_steps",
    "review_gaps",
    "report_references",
)
COUNT_FIELD_BY_SECTION = (
    ("construct_profiles", "construct_profile_count"),
    ("project_construct_links", "project_construct_link_count"),
    ("project_catalog_asset_links", "project_catalog_asset_link_count"),
    ("expression_cassettes", "cassette_count"),
    ("cassette_parts", "cassette_part_count"),
    ("linked_genes", "linked_gene_count"),
    ("linked_pathway_steps", "linked_pathway_step_count"),
    ("review_gaps", "review_gap_count"),
)
COMPATIBILITY_NOTES = (
    "Older documentation packages without the R28 manifest remain readable when package_metadata and documentation-only boundary fields are present.",
    "Unknown future manifest fields are ignored during documentation package review when the package structure remains readable.",
    "Catalog reference link rows are restored as documentation-level project references when the local repository accepts their project, asset, and role identity.",
)
KNOWN_LIMITATIONS = (
    "External database and API imports are deferred.",
    "Complex sequence parsing is deferred.",
    CSV_DEFERRED_NOTE,
    "Imported package metadata remains documentation-only and requires human review.",
    "Lightweight integrity summary is for package comparison only and is not a tamper-proof or readiness signal.",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _pick(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: row.get(field, "") for field in fields}


def _section_rows(package: dict[str, Any], section: str) -> list[dict[str, Any]]:
    rows = package.get(section)
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _compact_metadata(row: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("source_context_snapshot", "review_status_snapshot", "asset_snapshot"):
        value = row.get(key)
        if isinstance(value, dict) and value:
            metadata[key] = dict(value)
    if _text(row.get("snapshot_schema_version")):
        metadata["snapshot_schema_version"] = _text(row.get("snapshot_schema_version"))
    if _text(row.get("snapshot_captured_at")):
        metadata["snapshot_captured_at"] = _text(row.get("snapshot_captured_at"))
    return metadata


def _dedupe_profiles(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_construct_ids: set[str] = set()
    for row in rows:
        construct_id = _text(row.get("construct_id"))
        if construct_id:
            if construct_id in seen_construct_ids:
                continue
            seen_construct_ids.add(construct_id)
        deduped.append(row)
    return deduped


def _project_metadata(project: dict[str, Any] | None, project_id: str) -> dict[str, Any]:
    safe_project = project if isinstance(project, dict) else {}
    return {
        "project_id": _text(
            safe_project.get("project_id")
            or safe_project.get("id")
            or safe_project.get("linked_project_id")
            or project_id
        ),
        "project_name": _text(
            safe_project.get("project_name")
            or safe_project.get("name")
            or safe_project.get("target_product")
        ),
        "target_product": _text(safe_project.get("target_product")),
        "host": _text(safe_project.get("host") or safe_project.get("chassis")),
        "status": _text(safe_project.get("status") or safe_project.get("active_project_status")),
        "description": _text(safe_project.get("description") or safe_project.get("project_description")),
        "created_at": _text(safe_project.get("created_at")),
        "updated_at": _text(safe_project.get("updated_at")),
        "metadata_source_note": (
            "Project metadata is caller-provided when available; construct-scoped records come from "
            "local Expression Constructs documentation tables."
        ),
    }


def _selected_profiles(
    *,
    project_id: str,
    construct_ids: list[str] | None,
) -> list[dict[str, Any]]:
    requested_ids = {_text(value) for value in (construct_ids or []) if _text(value)}
    if requested_ids:
        profiles = [repo.get_construct_profile(construct_id) for construct_id in sorted(requested_ids, key=str.casefold)]
        return [profile for profile in profiles if profile]
    if project_id:
        return _dedupe_profiles(repo.list_construct_profiles_for_project(project_id))
    return repo.list_construct_profiles()


def _collect_review_gaps(construct_ids: list[str], project_id: str) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    for construct_id in construct_ids:
        try:
            view = presenter.build_expression_construct_presenter(construct_id, project_id=project_id or None)
        except Exception:
            continue
        for gap in view.get("review_gap_rows") or []:
            if isinstance(gap, dict):
                gaps.append({"construct_id": construct_id, **gap})
    return gaps


def _promoter_source_link_row_count_from_rows(rows: list[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        if any(
            _text(row.get(key))
            for key in ("source_catalog", "source_record_id", "source_record_label", "evidence_context_note")
        ):
            count += 1
    return count


def _catalog_reference_summary_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    summary_rows: list[dict[str, Any]] = []
    for row in rows:
        compact_metadata = row.get("compact_metadata") if isinstance(row.get("compact_metadata"), dict) else {}
        source_snapshot = compact_metadata.get("source_context_snapshot")
        review_snapshot = compact_metadata.get("review_status_snapshot")
        asset_snapshot = compact_metadata.get("asset_snapshot")
        summary_rows.append(
            {
                **row,
                "asset_display_name": (
                    asset_snapshot.get("asset_label")
                    if isinstance(asset_snapshot, dict)
                    else ""
                )
                or row.get("asset_label")
                or row.get("asset_display_name"),
                "source_context_snapshot": source_snapshot if isinstance(source_snapshot, dict) else {},
                "review_status_snapshot": review_snapshot if isinstance(review_snapshot, dict) else {},
                "asset_snapshot": asset_snapshot if isinstance(asset_snapshot, dict) else {},
            }
        )
    promoter_summary = summarize_linked_plant_promoter_references(summary_rows)
    wizard_summary = build_expression_wizard_catalog_traceability_summary(summary_rows)
    return {
        "linked_plant_promoter_count": int(promoter_summary.get("linked_promoter_count", 0) or 0),
        "catalog_reference_missing_metadata_count": int(promoter_summary.get("missing_metadata_count", 0) or 0),
        "expression_wizard_catalog_reference_count": int(wizard_summary.get("reference_count", 0) or 0),
        "expression_wizard_plant_promoter_reference_count": int(wizard_summary.get("plant_promoter_reference_count", 0) or 0),
        "expression_wizard_catalog_missing_metadata_count": int(wizard_summary.get("missing_metadata_count", 0) or 0),
        "catalog_links_with_pinned_snapshots_count": sum(
            1
            for row in summary_rows
            if catalog_asset_snapshot_has_content(row.get("asset_snapshot"))
        ),
        "catalog_links_missing_snapshots_count": sum(
            1
            for row in summary_rows
            if not catalog_asset_snapshot_has_content(row.get("asset_snapshot"))
        ),
        "catalog_links_malformed_snapshot_warning_count": sum(
            1
            for row in summary_rows
            if row.get("asset_snapshot_warning")
        ),
    }


def build_package_record_counts(package: dict[str, Any]) -> dict[str, int]:
    counts = {
        count_field: len(_section_rows(package, section))
        for section, count_field in COUNT_FIELD_BY_SECTION
    }
    counts["promoter_source_link_row_count"] = _promoter_source_link_row_count_from_rows(
        _section_rows(package, "cassette_parts")
    )
    counts.update(_catalog_reference_summary_counts(_section_rows(package, "project_catalog_asset_links")))
    return counts


def _record_counts_from_rows(
    *,
    project_links: list[dict[str, Any]],
    catalog_reference_links: list[dict[str, Any]],
    profiles: list[dict[str, Any]],
    cassettes: list[dict[str, Any]],
    cassette_parts: list[dict[str, Any]],
    linked_genes: list[dict[str, Any]],
    linked_pathway_steps: list[dict[str, Any]],
    review_gaps: list[dict[str, Any]],
) -> dict[str, int]:
    return build_package_record_counts(
        {
            "project_construct_links": project_links,
            "project_catalog_asset_links": catalog_reference_links,
            "construct_profiles": profiles,
            "expression_cassettes": cassettes,
            "cassette_parts": cassette_parts,
            "linked_genes": linked_genes,
            "linked_pathway_steps": linked_pathway_steps,
            "review_gaps": review_gaps,
        }
    )


def _catalog_reference_link_row(link: dict[str, Any]) -> dict[str, Any]:
    row = _pick(link, _CATALOG_REFERENCE_LINK_FIELDS)
    output_row = build_linked_catalog_reference_output(link)
    asset_snapshot = sanitize_catalog_asset_snapshot(link.get("asset_snapshot"))
    row["snapshot_schema_version"] = row.get("snapshot_schema_version") or (
        SNAPSHOT_SCHEMA_VERSION if asset_snapshot else ""
    )
    row["asset_snapshot"] = asset_snapshot
    row["snapshot_captured_at"] = _text(link.get("snapshot_captured_at"))
    row["compact_metadata"] = _compact_metadata(link)
    for field in _CATALOG_REFERENCE_OUTPUT_FIELDS:
        row[field] = output_row.get(field, "")
    return row


def _project_catalog_reference_links(project_id: str) -> list[dict[str, Any]]:
    if not project_id:
        return []
    try:
        links = project_catalog_link_repo.list_project_catalog_asset_links(project_id)
    except Exception:
        return []
    rows = [
        _catalog_reference_link_row(link)
        for link in links
        if isinstance(link, dict) and not has_staged_basket_only_markers(link)
    ]
    return sorted(
        rows,
        key=lambda row: (
            _text(row.get("asset_label")).casefold(),
            _text(row.get("asset_id")).casefold(),
            _text(row.get("linkage_role")).casefold(),
            _text(row.get("link_id")).casefold(),
        ),
    )


def _export_scope(project_id: str, construct_ids: list[str], selected_construct_ids: list[str]) -> dict[str, Any]:
    if construct_ids:
        selection_mode = "explicit_construct_ids"
    elif project_id:
        selection_mode = "project_scoped"
    else:
        selection_mode = "all_construct_profiles"
    return {
        "selection_mode": selection_mode,
        "project_id": project_id,
        "selected_construct_ids": selected_construct_ids,
    }


def _stable_package_id(manifest: dict[str, Any], counts: dict[str, int]) -> str:
    fingerprint_source = {
        "package_format": manifest.get("package_format"),
        "package_schema_version": manifest.get("package_schema_version"),
        "export_scope": manifest.get("export_scope"),
        "included_sections": manifest.get("included_sections"),
        "record_counts": counts,
    }
    digest = hashlib.sha256(
        json.dumps(fingerprint_source, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:16]
    return f"bdspkg-{digest}"


def build_package_integrity_summary(package: dict[str, Any], manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    counts = build_package_record_counts(package)
    manifest_data = manifest if isinstance(manifest, dict) else {}
    return {
        "package_id": _stable_package_id(manifest_data, counts),
        "section_row_counts": counts,
        "integrity_note": (
            "Lightweight package comparison summary only. It does not claim tamper-proof validation, security review, or readiness."
        ),
    }


def build_project_documentation_export_package(
    *,
    project: dict[str, Any] | None = None,
    project_id: str | int | None = None,
    construct_ids: list[str] | None = None,
    report_reference: dict[str, Any] | None = None,
    exported_at: str | None = None,
    source_commit_or_tag: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic JSON-compatible documentation metadata package."""
    clean_project_id = _text(
        project_id
        if project_id is not None
        else (project or {}).get("project_id")
        or (project or {}).get("id")
    )
    profiles = [_pick(profile, _PROFILE_FIELDS) for profile in _selected_profiles(project_id=clean_project_id, construct_ids=construct_ids)]
    construct_id_list: list[str] = []
    seen_construct_ids: set[str] = set()
    for profile in profiles:
        construct_id = _text(profile.get("construct_id"))
        if construct_id and construct_id not in seen_construct_ids:
            seen_construct_ids.add(construct_id)
            construct_id_list.append(construct_id)
    construct_id_set = set(construct_id_list)

    cassettes: list[dict[str, Any]] = []
    cassette_parts: list[dict[str, Any]] = []
    linked_genes: list[dict[str, Any]] = []
    linked_pathway_steps: list[dict[str, Any]] = []
    project_links: list[dict[str, Any]] = []
    catalog_reference_links = _project_catalog_reference_links(clean_project_id)

    for construct_id in construct_id_list:
        construct_cassettes = [_pick(row, _CASSETTE_FIELDS) for row in repo.list_construct_cassettes(construct_id)]
        cassettes.extend(construct_cassettes)
        for cassette in construct_cassettes:
            cassette_parts.extend(
                _pick(row, _PART_FIELDS)
                for row in repo.list_construct_cassette_parts(_text(cassette.get("cassette_id")))
            )
        linked_genes.extend(_pick(row, _GENE_LINK_FIELDS) for row in repo.list_construct_gene_links(construct_id))
        linked_pathway_steps.extend(
            _pick(row, _PATHWAY_LINK_FIELDS) for row in repo.list_construct_pathway_step_links(construct_id)
        )
        project_links.extend(
            _pick(row, _PROJECT_LINK_FIELDS) for row in repo.list_construct_project_links(construct_id=construct_id)
        )

    if clean_project_id:
        project_links = [
            row for row in project_links if _text(row.get("project_id")) == clean_project_id
        ]
    else:
        project_links = [
            row for row in project_links if _text(row.get("construct_id")) in construct_id_set
        ]

    review_gaps = _collect_review_gaps(construct_id_list, clean_project_id)
    counts = _record_counts_from_rows(
        project_links=project_links,
        catalog_reference_links=catalog_reference_links,
        profiles=profiles,
        cassettes=cassettes,
        cassette_parts=cassette_parts,
        linked_genes=linked_genes,
        linked_pathway_steps=linked_pathway_steps,
        review_gaps=review_gaps,
    )
    manifest = {
        "package_format": PACKAGE_FORMAT,
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "exported_at": exported_at or _now_iso(),
        "exported_by_app": EXPORTED_BY_APP,
        "export_scope": _export_scope(clean_project_id, construct_ids or [], construct_id_list),
        "record_counts": counts,
        "included_sections": list(INCLUDED_SECTIONS),
        "compatibility_notes": list(COMPATIBILITY_NOTES),
        "documentation_boundary": DOCUMENTATION_ONLY_BOUNDARY,
        "limitations": list(KNOWN_LIMITATIONS),
    }
    if _text(source_commit_or_tag):
        manifest["source_commit_or_tag"] = _text(source_commit_or_tag)

    package = {
        "manifest": manifest,
        "package_metadata": {
            "package_kind": PACKAGE_KIND,
            "package_version": PACKAGE_VERSION,
            "package_schema_version": PACKAGE_SCHEMA_VERSION,
            "exported_at": manifest["exported_at"],
            "documentation_only_boundary": DOCUMENTATION_ONLY_BOUNDARY,
            "included_sections": list(INCLUDED_SECTIONS),
            "counts": counts,
        },
        "project_metadata": _project_metadata(project, clean_project_id),
        "project_construct_links": project_links,
        "project_catalog_asset_links": catalog_reference_links,
        "construct_profiles": profiles,
        "expression_cassettes": cassettes,
        "cassette_parts": cassette_parts,
        "linked_genes": linked_genes,
        "linked_pathway_steps": linked_pathway_steps,
        "review_gaps": review_gaps,
        "report_references": report_reference if isinstance(report_reference, dict) else {},
        "documentation_only_boundary": DOCUMENTATION_ONLY_BOUNDARY,
        "known_limitations": list(KNOWN_LIMITATIONS),
    }
    package["integrity_summary"] = build_package_integrity_summary(package, manifest)
    return package
