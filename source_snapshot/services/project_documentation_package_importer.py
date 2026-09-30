from __future__ import annotations

import re
from typing import Any

from services import expression_construct_repository as repo
from services import project_catalog_asset_link_repository as project_catalog_link_repo
from services.project_documentation_package_exporter import (
    LEGACY_PACKAGE_VERSION,
    PACKAGE_KIND,
    PACKAGE_VERSION,
    PACKAGE_SCHEMA_VERSION,
    build_package_integrity_summary,
    build_package_record_counts,
)
from services.catalog_asset_snapshot_builder import sanitize_catalog_asset_snapshot
from services.catalog_asset_snapshot_builder import (
    blank_catalog_asset_snapshot,
    catalog_asset_snapshot_has_content,
)
from services.project_catalog_reference_output_formatter import (
    PERSISTED_LINKED_REFERENCE_STATUS,
    build_linked_catalog_reference_output,
    has_staged_basket_only_markers,
)

R28_PACKAGE_VERSION = "2.6-r28"
R28_PACKAGE_SCHEMA_VERSION = "2.6-r28"
SUPPORTED_PACKAGE_VERSIONS = {LEGACY_PACKAGE_VERSION, R28_PACKAGE_VERSION, PACKAGE_VERSION}
SUPPORTED_PACKAGE_SCHEMA_VERSIONS = {R28_PACKAGE_SCHEMA_VERSION, PACKAGE_SCHEMA_VERSION}
VALIDATION_BOUNDARY = (
    "This package validation is documentation-only. It previews local metadata structure and does not "
    "make downstream-use, biological outcome, ordering, numeric assessment, or external source verification claims."
)
DRY_RUN_BOUNDARY = (
    "Dry-run preview is documentation-only and non-destructive. It summarizes local create-as-new work only and "
    "does not overwrite, merge, delete, restore, or certify downstream use."
)
CREATE_BOUNDARY = (
    "Import creates local documentation records only. It does not overwrite existing rows and does not "
    "treat package metadata as experimental evidence."
)
_LIST_SECTIONS = (
    "project_construct_links",
    "project_catalog_asset_links",
    "construct_profiles",
    "expression_cassettes",
    "cassette_parts",
    "linked_genes",
    "linked_pathway_steps",
    "review_gaps",
)
_UNSAFE_KEYS = {"payload_json", "raw_payload", "executable_payload", "script"}
_PACKAGE_TOP_LEVEL_FIELDS = {
    "manifest",
    "package_metadata",
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
    "integrity_summary",
    "documentation_only_boundary",
    "known_limitations",
}
_OPTIONAL_TOP_LEVEL_FIELDS = {"report_references"}
_MANIFEST_FIELDS = {
    "package_format",
    "package_schema_version",
    "exported_at",
    "exported_by_app",
    "source_commit_or_tag",
    "export_scope",
    "record_counts",
    "included_sections",
    "compatibility_notes",
    "documentation_boundary",
    "limitations",
}
_PACKAGE_METADATA_FIELDS = {
    "package_kind",
    "package_version",
    "package_schema_version",
    "exported_at",
    "documentation_only_boundary",
    "included_sections",
    "counts",
}
_PROJECT_METADATA_FIELDS = {
    "project_id",
    "project_name",
    "target_product",
    "host",
    "status",
    "description",
    "created_at",
    "updated_at",
    "metadata_source_note",
}
_SECTION_FIELD_RULES = {
    "project_construct_links": {
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
    },
    "project_catalog_asset_links": {
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
        "snapshot_schema_version",
        "asset_snapshot",
        "snapshot_captured_at",
        "human_review_required",
        "created_at",
        "updated_at",
        "compact_metadata",
    },
    "construct_profiles": {
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
    },
    "expression_cassettes": {
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
    },
    "cassette_parts": {
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
    },
    "linked_genes": {
        "id",
        "construct_id",
        "gene_label",
        "gene_reference",
        "source_reference",
        "provenance_note",
        "created_at",
    },
    "linked_pathway_steps": {
        "id",
        "construct_id",
        "pathway_step_id",
        "pathway_step_label",
        "source_reference",
        "provenance_note",
        "created_at",
    },
    "review_gaps": {
        "construct_id",
        "Gap type",
        "Label",
        "Review gap note",
    },
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text_list(value: Any) -> list[str]:
    return [_text(item) for item in _as_list(value) if _text(item)]


def _add_message(values: list[str], message: str) -> None:
    if message not in values:
        values.append(message)


def _add_error(errors: list[str], message: str) -> None:
    _add_message(errors, message)


def _contains_unsafe_key(value: Any) -> bool:
    if isinstance(value, dict):
        if any(str(key) in _UNSAFE_KEYS for key in value):
            return True
        return any(_contains_unsafe_key(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_unsafe_key(item) for item in value)
    return False


def _section_rows(package: dict[str, Any], section: str) -> list[dict[str, Any]]:
    rows = package.get(section, [])
    return [row for row in _as_list(rows) if isinstance(row, dict)]


def _promoter_source_link_row_count(package: dict[str, Any]) -> int:
    count = 0
    for row in _section_rows(package, "cassette_parts"):
        if any(
            _text(row.get(key))
            for key in ("source_catalog", "source_record_id", "source_record_label", "evidence_context_note")
        ):
            count += 1
    return count


def _compact_metadata(row: dict[str, Any]) -> dict[str, Any]:
    value = row.get("compact_metadata")
    return value if isinstance(value, dict) else {}


def _catalog_reference_source_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _compact_metadata(row)
    value = metadata.get("source_context_snapshot")
    snapshot = value if isinstance(value, dict) else {}
    if snapshot:
        return dict(snapshot)
    fallback: dict[str, Any] = {}
    if _text(row.get("catalog_label")) and _text(row.get("catalog_label")) != "Not recorded":
        fallback["catalog"] = _text(row.get("catalog_label"))
    if _text(row.get("record_identifier")) and _text(row.get("record_identifier")) != "Not recorded":
        fallback["profile_id"] = _text(row.get("record_identifier"))
    if _text(row.get("reference_origin")):
        fallback["reference_origin"] = _text(row.get("reference_origin"))
    if _text(row.get("project_documentation_context")) and _text(row.get("project_documentation_context")) != "Documentation context not provided":
        fallback["project_documentation_context"] = _text(row.get("project_documentation_context"))
    if _text(row.get("source_label")) and _text(row.get("source_label")) != "Source status not recorded":
        fallback["source_labels"] = _text(row.get("source_label"))
    return fallback


def _catalog_reference_review_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _compact_metadata(row)
    value = metadata.get("review_status_snapshot")
    snapshot = value if isinstance(value, dict) else {}
    if snapshot:
        return dict(snapshot)
    documentation_status = _text(row.get("documentation_status"))
    if documentation_status and documentation_status != "Not recorded":
        return {"review_status": documentation_status}
    return {}


def _catalog_reference_asset_snapshot(row: dict[str, Any], *, preserve_malformed: bool = False) -> dict[str, Any]:
    value = row.get("asset_snapshot")
    if not isinstance(value, dict):
        value = _compact_metadata(row).get("asset_snapshot")
    snapshot = sanitize_catalog_asset_snapshot(value)
    if snapshot:
        return snapshot
    if preserve_malformed and value not in (None, "", {}):
        placeholder = blank_catalog_asset_snapshot()
        placeholder["missing_metadata_note"] = "Malformed snapshot metadata captured with live metadata fallback."
        return placeholder
    return {}


def _is_plant_promoter_catalog_reference(row: dict[str, Any]) -> bool:
    return _text(row.get("asset_type")) == "plant_promoter_profile"


def _reviewable_catalog_reference_rows(package: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in _section_rows(package, "project_catalog_asset_links")
        if not has_staged_basket_only_markers(row)
    ]


def _catalog_reference_missing_metadata_count(package: dict[str, Any]) -> int:
    count = 0
    for row in _reviewable_catalog_reference_rows(package):
        source_snapshot = _catalog_reference_source_snapshot(row)
        review_snapshot = _catalog_reference_review_snapshot(row)
        if _is_plant_promoter_catalog_reference(row):
            explicit = review_snapshot.get("missing_metadata_count")
            if isinstance(explicit, int):
                count += explicit
                continue
        asset_snapshot = _catalog_reference_asset_snapshot(row)
        missing_source = not (
            _text(row.get("source_label"))
            or _text(source_snapshot.get("source_labels"))
            or _text(asset_snapshot.get("source_label"))
        )
        missing_review = not (
            _text(row.get("documentation_status"))
            or _text(review_snapshot.get("curation_statuses"))
            or _text(review_snapshot.get("review_status"))
            or _text(asset_snapshot.get("documentation_status"))
        )
        if missing_source or missing_review:
            count += 1
    return count


def _plant_promoter_catalog_reference_count(package: dict[str, Any]) -> int:
    return sum(1 for row in _reviewable_catalog_reference_rows(package) if _is_plant_promoter_catalog_reference(row))


def _catalog_reference_required_field_warnings(package: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    required_fields = ("project_id", "asset_id", "asset_type")
    for index, row in enumerate(_section_rows(package, "project_catalog_asset_links")):
        if has_staged_basket_only_markers(row):
            warnings.append(
                f"Catalog reference link row {index} uses staged basket markers and will stay out of package import review."
            )
            continue
        missing = [field for field in required_fields if not _text(row.get(field))]
        if missing:
            warnings.append(
                f"Catalog reference link row {index} missing required fields and will be skipped: {', '.join(missing)}."
            )
        if row.get("asset_snapshot") and not catalog_asset_snapshot_has_content(_catalog_reference_asset_snapshot(row)):
            warnings.append(
                f"Catalog reference link row {index} has malformed snapshot metadata and will use live metadata fallback."
            )
    return warnings


def _importable_catalog_reference_rows(package: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        row
        for row in _reviewable_catalog_reference_rows(package)
        if _text(row.get("project_id")) and _text(row.get("asset_id")) and _text(row.get("asset_type"))
    ]


def _catalog_reference_import_review_summary(package: dict[str, Any]) -> dict[str, Any]:
    rows = _section_rows(package, "project_catalog_asset_links")
    review_rows = [row for row in rows if not has_staged_basket_only_markers(row)]
    complete_context_count = 0
    safe_fallback_label_count = 0
    live_metadata_fallback_count = 0
    missing_identifier_or_source_status_count = 0
    persisted_reference_count = 0
    legacy_fallback_count = 0
    source_status_not_recorded_count = 0
    documentation_context_not_provided_count = 0

    for row in review_rows:
        output = build_linked_catalog_reference_output(row)
        source_snapshot = _catalog_reference_source_snapshot(row)
        review_snapshot = _catalog_reference_review_snapshot(row)
        has_record_identifier = bool(_text(output.get("record_identifier")) and _text(output.get("record_identifier")) != "Not recorded")
        has_source_status = _text(output.get("source_label")) != "Source status not recorded"
        has_documentation_status = _text(output.get("documentation_status")) != "Not recorded"
        has_documentation_context = _text(output.get("project_documentation_context")) != "Documentation context not provided"
        has_reference_origin = bool(_text(output.get("reference_origin")))

        if _text(output.get("linked_persisted_status")) == PERSISTED_LINKED_REFERENCE_STATUS:
            persisted_reference_count += 1
        if _text(output.get("snapshot_state")) == "live metadata fallback":
            live_metadata_fallback_count += 1
        if not has_record_identifier or not has_source_status or not has_documentation_status:
            missing_identifier_or_source_status_count += 1
        if not has_source_status or not has_documentation_status or not has_documentation_context:
            safe_fallback_label_count += 1
        if (
            has_record_identifier
            and has_source_status
            and has_documentation_status
            and has_documentation_context
            and has_reference_origin
        ):
            complete_context_count += 1
        if not source_snapshot or not review_snapshot or not _compact_metadata(row):
            legacy_fallback_count += 1
        if _text(output.get("source_label")) == "Source status not recorded":
            source_status_not_recorded_count += 1
        if _text(output.get("project_documentation_context")) == "Documentation context not provided":
            documentation_context_not_provided_count += 1

    return {
        "total_rows_in_package": len(review_rows),
        "staged_rows_excluded_count": len(rows) - len(review_rows),
        "complete_documentation_context_count": complete_context_count,
        "safe_fallback_label_count": safe_fallback_label_count,
        "live_metadata_fallback_count": live_metadata_fallback_count,
        "missing_identifier_or_source_status_count": missing_identifier_or_source_status_count,
        "persisted_reference_count": persisted_reference_count,
        "legacy_package_fallback_count": legacy_fallback_count,
        "source_status_not_recorded_count": source_status_not_recorded_count,
        "documentation_context_not_provided_count": documentation_context_not_provided_count,
        "integrity_messages": [
            f"{persisted_reference_count} persisted linked reference row(s) remain in package import review.",
            f"{complete_context_count} row(s) include imported documentation context with record identifier, source status, review status, and project documentation context.",
            f"{legacy_fallback_count} row(s) rely on legacy package fallback because compact documentation context was not fully provided.",
            f"{source_status_not_recorded_count} row(s) report source status not recorded.",
            f"{documentation_context_not_provided_count} row(s) report documentation context not provided.",
            f"{live_metadata_fallback_count} row(s) use live metadata fallback because pinned snapshot metadata was missing or malformed.",
        ],
    }


def _shape_review_summary(package: dict[str, Any]) -> dict[str, list[str]]:
    missing_optional_fields: list[str] = []
    unknown_extra_fields: list[str] = []

    top_level_keys = set(package)
    for key in sorted(top_level_keys - _PACKAGE_TOP_LEVEL_FIELDS):
        unknown_extra_fields.append(key)
    for key in sorted(_PACKAGE_TOP_LEVEL_FIELDS - top_level_keys):
        if key not in _OPTIONAL_TOP_LEVEL_FIELDS:
            missing_optional_fields.append(key)

    manifest = package.get("manifest")
    if isinstance(manifest, dict):
        for key in sorted(set(manifest) - _MANIFEST_FIELDS):
            unknown_extra_fields.append(f"manifest.{key}")
    elif "manifest" in package:
        missing_optional_fields.append("manifest")

    package_metadata = package.get("package_metadata")
    if isinstance(package_metadata, dict):
        for key in sorted(set(package_metadata) - _PACKAGE_METADATA_FIELDS):
            unknown_extra_fields.append(f"package_metadata.{key}")
    else:
        missing_optional_fields.append("package_metadata")

    project_metadata = package.get("project_metadata")
    if isinstance(project_metadata, dict):
        for key in sorted(_PROJECT_METADATA_FIELDS - set(project_metadata)):
            missing_optional_fields.append(f"project_metadata.{key}")
        for key in sorted(set(project_metadata) - _PROJECT_METADATA_FIELDS):
            unknown_extra_fields.append(f"project_metadata.{key}")
    else:
        missing_optional_fields.append("project_metadata")

    for section, expected_fields in _SECTION_FIELD_RULES.items():
        for index, row in enumerate(_section_rows(package, section)[:5]):
            row_keys = set(row)
            for key in sorted(expected_fields - row_keys):
                missing_optional_fields.append(f"{section}[{index}].{key}")
            for key in sorted(row_keys - expected_fields):
                unknown_extra_fields.append(f"{section}[{index}].{key}")

    return {
        "missing_optional_fields": missing_optional_fields[:40],
        "unknown_extra_fields": unknown_extra_fields[:40],
    }


def build_manifest_review_summary(package: Any) -> dict[str, Any]:
    """Return read-only manifest metadata for UI/report review."""
    safe_package = package if isinstance(package, dict) else {}
    manifest_value = safe_package.get("manifest")
    manifest = manifest_value if isinstance(manifest_value, dict) else {}
    metadata_value = safe_package.get("package_metadata")
    metadata = metadata_value if isinstance(metadata_value, dict) else {}

    export_scope_value = manifest.get("export_scope")
    export_scope = export_scope_value if isinstance(export_scope_value, dict) else {}
    record_counts_value = manifest.get("record_counts")
    record_counts = record_counts_value if isinstance(record_counts_value, dict) else build_package_record_counts(safe_package)
    included_sections = _text_list(manifest.get("included_sections") or metadata.get("included_sections"))
    compatibility_notes = _text_list(manifest.get("compatibility_notes"))
    limitations = _text_list(manifest.get("limitations") or safe_package.get("known_limitations"))
    review_notes: list[str] = []

    if "manifest" not in safe_package:
        review_notes.append("Older package format: manifest metadata was not provided.")
    elif manifest_value is not None and not isinstance(manifest_value, dict):
        review_notes.append("Manifest metadata needs review because the manifest field is not an object.")

    if not _text(manifest.get("package_format")):
        review_notes.append("Package format not provided in manifest metadata.")
    if not _text(manifest.get("exported_by_app")):
        review_notes.append("Exported by app not provided in manifest metadata.")
    if not _text(manifest.get("exported_at") or metadata.get("exported_at")):
        review_notes.append("Exported at not provided in manifest metadata.")
    if not export_scope:
        review_notes.append("Export scope not provided in manifest metadata.")
    if not included_sections:
        review_notes.append("Included sections not provided in manifest metadata.")
    if not compatibility_notes:
        review_notes.append("Compatibility notes not provided in manifest metadata.")
    if not _text(manifest.get("documentation_boundary") or metadata.get("documentation_only_boundary") or safe_package.get("documentation_only_boundary")):
        review_notes.append("Documentation boundary not provided in manifest metadata.")
    if not limitations:
        review_notes.append("Limitations not provided in manifest metadata.")
    if record_counts_value is not None and not isinstance(record_counts_value, dict):
        review_notes.append("Manifest record counts need review because record_counts is not an object.")

    return {
        "is_manifest_present": bool(manifest),
        "package_format": _text(manifest.get("package_format")),
        "package_schema_version": _text(manifest.get("package_schema_version") or metadata.get("package_schema_version")),
        "exported_at": _text(manifest.get("exported_at") or metadata.get("exported_at")),
        "exported_by_app": _text(manifest.get("exported_by_app")),
        "source_commit_or_tag": _text(manifest.get("source_commit_or_tag")),
        "export_scope": dict(export_scope),
        "included_sections": included_sections,
        "compatibility_notes": compatibility_notes,
        "documentation_boundary": _text(
            manifest.get("documentation_boundary")
            or metadata.get("documentation_only_boundary")
            or safe_package.get("documentation_only_boundary")
        ),
        "limitations": limitations,
        "record_counts": dict(record_counts),
        "review_notes": review_notes,
    }


def _normalized_label(value: Any) -> str:
    return _text(value).casefold()


def _existing_construct_labels() -> set[str]:
    return {
        _normalized_label(profile.get("construct_label"))
        for profile in repo.list_construct_profiles()
        if _normalized_label(profile.get("construct_label"))
    }


def _existing_construct_ids() -> set[str]:
    return {
        _text(profile.get("construct_id"))
        for profile in repo.list_construct_profiles()
        if _text(profile.get("construct_id"))
    }


def _existing_project_link_keys() -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for profile in repo.list_construct_profiles():
        construct_id = _text(profile.get("construct_id"))
        if not construct_id:
            continue
        for link in repo.list_construct_project_links(construct_id=construct_id):
            project_id = _text(link.get("project_id"))
            label = _normalized_label(link.get("link_label"))
            if project_id and label:
                keys.add((project_id, label))
    return keys


def _existing_cassette_labels_by_construct() -> dict[str, set[str]]:
    mapping: dict[str, set[str]] = {}
    for profile in repo.list_construct_profiles():
        construct_id = _text(profile.get("construct_id"))
        if not construct_id:
            continue
        labels = {
            _normalized_label(row.get("cassette_label"))
            for row in repo.list_construct_cassettes(construct_id)
            if _normalized_label(row.get("cassette_label"))
        }
        mapping[construct_id] = labels
    return mapping


def _existing_part_source_duplicates() -> set[tuple[str, str]]:
    duplicates: set[tuple[str, str]] = set()
    for profile in repo.list_construct_profiles():
        construct_id = _text(profile.get("construct_id"))
        if not construct_id:
            continue
        for cassette in repo.list_construct_cassettes(construct_id):
            for part in repo.list_construct_cassette_parts(_text(cassette.get("cassette_id"))):
                source_record_id = _text(part.get("source_record_id"))
                source_record_label = _normalized_label(part.get("source_record_label"))
                if source_record_id or source_record_label:
                    duplicates.add((source_record_id, source_record_label))
    return duplicates


def validate_project_documentation_package(package: Any) -> dict[str, Any]:
    report = {
        "is_valid": False,
        "errors": [],
        "warnings": [],
        "package_version": None,
        "package_schema_version": None,
        "project_id": None,
        "project_name": None,
        "counts": {},
        "manifest_summary": {},
        "integrity_summary": {},
        "documentation_only_boundary": VALIDATION_BOUNDARY,
    }
    if not isinstance(package, dict):
        report["errors"].append("Package must be a JSON-compatible object.")
        return report
    if _contains_unsafe_key(package):
        report["errors"].append("Package contains raw or executable payload keys that are not accepted.")

    manifest = package.get("manifest")
    if manifest is not None and not isinstance(manifest, dict):
        report["errors"].append("manifest must be an object when present.")
        manifest = {}
    manifest = manifest if isinstance(manifest, dict) else {}

    metadata = package.get("package_metadata")
    if not isinstance(metadata, dict):
        report["errors"].append("package_metadata must be present as an object.")
        metadata = {}
    project_metadata = package.get("project_metadata")
    if project_metadata is not None and not isinstance(project_metadata, dict):
        report["errors"].append("project_metadata must be an object when present.")
        project_metadata = {}
    project_metadata = project_metadata if isinstance(project_metadata, dict) else {}

    package_kind = metadata.get("package_kind")
    if package_kind != PACKAGE_KIND:
        _add_error(report["errors"], f"Unsupported package_kind: {package_kind}")
    package_version = metadata.get("package_version")
    report["package_version"] = package_version
    if package_version not in SUPPORTED_PACKAGE_VERSIONS:
        _add_error(report["errors"], f"Unsupported package_version: {package_version}")
    package_schema_version = manifest.get("package_schema_version") or metadata.get("package_schema_version")
    report["package_schema_version"] = package_schema_version
    if manifest and not package_schema_version:
        report["warnings"].append("Manifest is present but package_schema_version is missing.")
    elif package_schema_version and package_schema_version not in SUPPORTED_PACKAGE_SCHEMA_VERSIONS:
        report["warnings"].append(f"Unsupported package_schema_version for this build: {package_schema_version}")

    boundary = _text(
        manifest.get("documentation_boundary")
        or metadata.get("documentation_only_boundary")
        or package.get("documentation_only_boundary")
    ).lower()
    if "documentation-only" not in boundary:
        _add_error(report["errors"], "Package boundary must include documentation-only language.")

    for section in _LIST_SECTIONS:
        if section in package and not isinstance(package.get(section), list):
            _add_error(report["errors"], f"{section} must be a list when present.")
    for index, row in enumerate(_as_list(package.get("construct_profiles"))):
        if not isinstance(row, dict):
            _add_error(report["errors"], f"construct_profiles[{index}] must be an object.")
            continue
        if not _text(row.get("construct_label")) and not _text(row.get("construct_id")):
            _add_error(report["errors"], f"construct_profiles[{index}] needs construct_label or construct_id.")
    for index, row in enumerate(_as_list(package.get("expression_cassettes"))):
        if not isinstance(row, dict):
            _add_error(report["errors"], f"expression_cassettes[{index}] must be an object.")
    for index, row in enumerate(_as_list(package.get("cassette_parts"))):
        if not isinstance(row, dict):
            _add_error(report["errors"], f"cassette_parts[{index}] must be an object.")

    report["project_id"] = _text(project_metadata.get("project_id"))
    report["project_name"] = _text(project_metadata.get("project_name"))
    report["counts"] = {
        "project_construct_links": len(_section_rows(package, "project_construct_links")),
        "project_catalog_asset_links": len(_section_rows(package, "project_catalog_asset_links")),
        "construct_profiles": len(_section_rows(package, "construct_profiles")),
        "expression_cassettes": len(_section_rows(package, "expression_cassettes")),
        "cassette_parts": len(_section_rows(package, "cassette_parts")),
        "linked_genes": len(_section_rows(package, "linked_genes")),
        "linked_pathway_steps": len(_section_rows(package, "linked_pathway_steps")),
        "review_gaps": len(_section_rows(package, "review_gaps")),
        "promoter_source_link_rows": _promoter_source_link_row_count(package),
        "linked_plant_promoter_catalog_references": _plant_promoter_catalog_reference_count(package),
        "catalog_reference_missing_metadata_count": _catalog_reference_missing_metadata_count(package),
        "catalog_links_with_pinned_snapshots_count": sum(
            1
            for row in _section_rows(package, "project_catalog_asset_links")
            if catalog_asset_snapshot_has_content(_catalog_reference_asset_snapshot(row))
        ),
        "catalog_links_missing_snapshots_count": sum(
            1
            for row in _section_rows(package, "project_catalog_asset_links")
            if not catalog_asset_snapshot_has_content(_catalog_reference_asset_snapshot(row))
        ),
        "catalog_links_malformed_snapshot_warning_count": sum(
            1
            for row in _reviewable_catalog_reference_rows(package)
            if row.get("asset_snapshot") and not catalog_asset_snapshot_has_content(_catalog_reference_asset_snapshot(row))
        ),
    }
    report["catalog_reference_import_review_summary"] = _catalog_reference_import_review_summary(package)
    for warning in _catalog_reference_required_field_warnings(package):
        _add_message(report["warnings"], warning)
    report["manifest_summary"] = build_manifest_review_summary(package)
    report["manifest_summary"]["package_schema_version"] = _text(package_schema_version)
    integrity_summary = package.get("integrity_summary")
    if isinstance(integrity_summary, dict):
        report["integrity_summary"] = integrity_summary
    else:
        report["integrity_summary"] = build_package_integrity_summary(package, manifest)
    if not _section_rows(package, "construct_profiles"):
        report["warnings"].append("Package contains no construct profile rows.")
    report["is_valid"] = not report["errors"]
    return report


def detect_import_conflicts(
    package: dict[str, Any],
    existing_repository_context: dict[str, Any] | None = None,
    *,
    target_project_id: str | int | None = None,
) -> dict[str, Any]:
    context = existing_repository_context if isinstance(existing_repository_context, dict) else {}
    existing_construct_labels = set(context.get("existing_construct_labels") or _existing_construct_labels())
    existing_construct_ids = set(context.get("existing_construct_ids") or _existing_construct_ids())
    existing_project_link_keys = set(context.get("existing_project_link_keys") or _existing_project_link_keys())
    existing_cassette_labels_by_construct = (
        context.get("existing_cassette_labels_by_construct") or _existing_cassette_labels_by_construct()
    )
    existing_part_source_duplicates = set(
        context.get("existing_part_source_duplicates") or _existing_part_source_duplicates()
    )

    package_construct_ids = {
        _text(row.get("construct_id"))
        for row in _section_rows(package, "construct_profiles")
        if _text(row.get("construct_id"))
    }
    package_cassette_ids = {
        _text(row.get("cassette_id"))
        for row in _section_rows(package, "expression_cassettes")
        if _text(row.get("cassette_id"))
    }

    conflicts: list[dict[str, str]] = []
    structural_errors: list[str] = []
    deferred_checks: list[str] = [
        "Existing cassette-label conflicts are checked only when the package construct_id already exists locally; remapped create-as-new construct IDs are treated as non-conflicting.",
        "Source duplicate checks for promoter source-link rows are limited to source_record_id and source_record_label pairs already present in local cassette part rows.",
    ]

    for row in _section_rows(package, "construct_profiles"):
        construct_id = _text(row.get("construct_id"))
        construct_label = _text(row.get("construct_label"))
        if construct_label and _normalized_label(construct_label) in existing_construct_labels:
            conflicts.append(
                {
                    "conflict_type": "construct_label_exists",
                    "record_type": "construct_profile",
                    "identifier": construct_label,
                    "detail": f"Construct label already exists locally: {construct_label}",
                }
            )
        if construct_id and construct_id in existing_construct_ids:
            conflicts.append(
                {
                    "conflict_type": "construct_id_exists",
                    "record_type": "construct_profile",
                    "identifier": construct_id,
                    "detail": f"Construct ID/reference already exists locally: {construct_id}",
                }
            )

    for row in _section_rows(package, "expression_cassettes"):
        construct_id = _text(row.get("construct_id"))
        cassette_id = _text(row.get("cassette_id"))
        cassette_label = _text(row.get("cassette_label"))
        if construct_id and construct_id not in package_construct_ids:
            _add_message(
                structural_errors,
                f"Expression cassette references unknown package construct_id: {construct_id}",
            )
        if construct_id in existing_cassette_labels_by_construct and cassette_label:
            if _normalized_label(cassette_label) in set(existing_cassette_labels_by_construct.get(construct_id) or set()):
                conflicts.append(
                    {
                        "conflict_type": "cassette_label_exists_under_construct",
                        "record_type": "expression_cassette",
                        "identifier": cassette_label,
                        "detail": f"Cassette label already exists under local construct {construct_id}: {cassette_label}",
                    }
                )
        if cassette_id and cassette_id in package_cassette_ids:
            continue

    for row in _section_rows(package, "cassette_parts"):
        cassette_id = _text(row.get("cassette_id"))
        if cassette_id and cassette_id not in package_cassette_ids:
            _add_message(
                structural_errors,
                f"Cassette part references missing package cassette_id: {cassette_id}",
            )
        source_key = (_text(row.get("source_record_id")), _normalized_label(row.get("source_record_label")))
        if source_key != ("", "") and source_key in existing_part_source_duplicates:
            conflicts.append(
                {
                    "conflict_type": "source_record_duplicate",
                    "record_type": "cassette_part",
                    "identifier": _text(row.get("source_record_id")) or _text(row.get("source_record_label")),
                    "detail": "Promoter source-link row appears to duplicate an existing local source record reference.",
                }
            )

    resolved_target_project_id = _text(target_project_id) or _text(
        (package.get("project_metadata") or {}).get("project_id")
    )
    for row in _section_rows(package, "project_construct_links"):
        construct_id = _text(row.get("construct_id"))
        project_id = _text(row.get("project_id")) or resolved_target_project_id
        link_label = _text(row.get("link_label"))
        if construct_id and construct_id not in package_construct_ids:
            _add_message(
                structural_errors,
                f"Project-level construct link references unknown package construct_id: {construct_id}",
            )
        project_key = (project_id, _normalized_label(link_label))
        if project_id and link_label and project_key in existing_project_link_keys:
            conflicts.append(
                {
                    "conflict_type": "project_construct_link_exists",
                    "record_type": "project_construct_link",
                    "identifier": f"{project_id}:{link_label}",
                    "detail": f"Project-level construct link already exists locally for project {project_id}: {link_label}",
                }
            )

    return {
        "conflicts": conflicts,
        "structural_errors": structural_errors,
        "deferred_checks": deferred_checks,
        "conflict_count": len(conflicts),
        "has_conflicts": bool(conflicts),
    }


def summarize_import_plan(
    package: dict[str, Any],
    *,
    target_project_id: str | int | None = None,
    validation: dict[str, Any] | None = None,
    conflicts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation_report = validation if isinstance(validation, dict) else validate_project_documentation_package(package)
    conflict_report = (
        conflicts
        if isinstance(conflicts, dict)
        else detect_import_conflicts(package, target_project_id=target_project_id)
    )
    shape_summary = _shape_review_summary(package)
    resolved_project_id = _text(target_project_id) or _text(validation_report.get("project_id"))
    would_create = {
        "construct_profiles": len(_section_rows(package, "construct_profiles")),
        "expression_cassettes": len(_section_rows(package, "expression_cassettes")),
        "cassette_parts": len(_section_rows(package, "cassette_parts")),
        "promoter_source_link_rows": _promoter_source_link_row_count(package),
        "linked_genes": len(_section_rows(package, "linked_genes")),
        "linked_pathway_steps": len(_section_rows(package, "linked_pathway_steps")),
        "project_construct_links": len(_section_rows(package, "project_construct_links")),
        "project_catalog_asset_links": len(_importable_catalog_reference_rows(package)),
    }
    return {
        "is_valid": bool(validation_report.get("is_valid")),
        "would_create": would_create,
        "target_project_id": resolved_project_id,
        "package_version": validation_report.get("package_version"),
        "package_schema_version": validation_report.get("package_schema_version"),
        "manifest_summary": dict(validation_report.get("manifest_summary") or {}),
        "integrity_summary": dict(validation_report.get("integrity_summary") or {}),
        "missing_optional_fields": list(shape_summary.get("missing_optional_fields") or []),
        "unknown_extra_fields": list(shape_summary.get("unknown_extra_fields") or []),
        "structural_errors": list(validation_report.get("errors") or []) + list(conflict_report.get("structural_errors") or []),
        "warnings": list(validation_report.get("warnings") or []),
        "possible_conflicts": list(conflict_report.get("conflicts") or []),
        "deferred_conflict_checks": list(conflict_report.get("deferred_checks") or []),
        "documentation_only_boundary": DRY_RUN_BOUNDARY,
        "create_mode": "create_as_new_only",
        "destructive_actions_available": False,
    }


def build_import_dry_run(
    package: Any,
    *,
    target_project_id: str | int | None = None,
    existing_repository_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    validation = validate_project_documentation_package(package)
    if not isinstance(package, dict):
        return {
            "is_valid": False,
            "validation": validation,
            "conflicts": {
                "conflicts": [],
                "structural_errors": list(validation.get("errors") or []),
                "deferred_checks": [],
                "conflict_count": 0,
                "has_conflicts": False,
            },
            "plan": {
                "is_valid": False,
                "would_create": {
                    "construct_profiles": 0,
                    "expression_cassettes": 0,
                    "cassette_parts": 0,
                    "promoter_source_link_rows": 0,
                    "linked_genes": 0,
                    "linked_pathway_steps": 0,
                    "project_construct_links": 0,
                    "project_catalog_asset_links": 0,
                },
                "target_project_id": _text(target_project_id),
                "missing_optional_fields": [],
                "unknown_extra_fields": [],
                "structural_errors": list(validation.get("errors") or []),
                "possible_conflicts": [],
                "deferred_conflict_checks": [],
                "documentation_only_boundary": DRY_RUN_BOUNDARY,
                "create_mode": "create_as_new_only",
                "destructive_actions_available": False,
            },
            "documentation_only_boundary": DRY_RUN_BOUNDARY,
        }
    conflicts = detect_import_conflicts(
        package,
        existing_repository_context,
        target_project_id=target_project_id,
    )
    plan = summarize_import_plan(
        package,
        target_project_id=target_project_id,
        validation=validation,
        conflicts=conflicts,
    )
    return {
        "is_valid": bool(validation.get("is_valid")),
        "validation": validation,
        "conflicts": conflicts,
        "plan": plan,
        "documentation_only_boundary": DRY_RUN_BOUNDARY,
    }


def _slug(value: Any, fallback: str) -> str:
    text = _text(value).lower()
    safe = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return safe[:48] or fallback


def _available_id(prefix: str, source_id: Any, exists) -> str:
    base = f"r24-{prefix}-{_slug(source_id, prefix)}"
    candidate = base
    counter = 2
    while exists(candidate):
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def _create_construct_id(source_id: Any, label: Any) -> str:
    source = _text(source_id) or _text(label)
    return _available_id("construct", source, lambda candidate: bool(repo.get_construct_profile(candidate)))


def _create_cassette_id(source_id: Any, label: Any, cassette_map: dict[str, str]) -> str:
    source = _text(source_id) or _text(label)
    reserved = set(cassette_map.values())
    return _available_id(
        "cassette",
        source,
        lambda candidate: candidate in reserved or any(
            row.get("cassette_id") == candidate
            for profile in repo.list_construct_profiles()
            for row in repo.list_construct_cassettes(profile.get("construct_id", ""))
        ),
    )


def import_project_documentation_package_as_new_records(
    package: dict[str, Any],
    *,
    target_project_id: str | int | None = None,
) -> dict[str, Any]:
    validation = validate_project_documentation_package(package)
    result = {
        "created": False,
        "errors": list(validation["errors"]),
        "warnings": list(validation["warnings"]),
        "construct_id_map": {},
        "cassette_id_map": {},
        "created_counts": {
            "construct_profiles": 0,
            "expression_cassettes": 0,
            "cassette_parts": 0,
            "linked_genes": 0,
            "linked_pathway_steps": 0,
            "project_construct_links": 0,
            "project_catalog_asset_links": 0,
            "project_catalog_asset_link_duplicates": 0,
            "project_catalog_asset_link_skipped": 0,
        },
        "documentation_only_boundary": CREATE_BOUNDARY,
    }
    if not validation["is_valid"]:
        return result

    project_metadata = package.get("project_metadata") if isinstance(package.get("project_metadata"), dict) else {}
    resolved_project_id = _text(target_project_id) or _text(project_metadata.get("project_id"))

    construct_map: dict[str, str] = {}
    cassette_map: dict[str, str] = {}

    for row in _section_rows(package, "construct_profiles"):
        source_construct_id = _text(row.get("construct_id"))
        local_construct_id = _create_construct_id(source_construct_id, row.get("construct_label"))
        created = repo.create_construct_profile(
            construct_id=local_construct_id,
            construct_label=_text(row.get("construct_label")) or source_construct_id or "Imported construct documentation",
            construct_type=_text(row.get("construct_type")),
            plasmid_backbone=_text(row.get("plasmid_backbone")),
            host_context_note=_text(row.get("host_context_note")),
            source_reference=_text(row.get("source_reference")),
            provenance_note=_text(row.get("provenance_note")),
            review_status=_text(row.get("review_status")),
            documentation_scope_note=_text(row.get("documentation_scope_note")),
        )
        if created:
            construct_map[source_construct_id or local_construct_id] = local_construct_id
            result["created_counts"]["construct_profiles"] += 1

    for row in _section_rows(package, "expression_cassettes"):
        source_construct_id = _text(row.get("construct_id"))
        local_construct_id = construct_map.get(source_construct_id)
        if not local_construct_id:
            result["warnings"].append(f"Skipped cassette without imported construct mapping: {row.get('cassette_id')}")
            continue
        source_cassette_id = _text(row.get("cassette_id"))
        local_cassette_id = _create_cassette_id(source_cassette_id, row.get("cassette_label"), cassette_map)
        created = repo.create_construct_cassette(
            local_construct_id,
            cassette_id=local_cassette_id,
            cassette_label=_text(row.get("cassette_label")) or source_cassette_id or "Imported cassette documentation",
            cassette_role=_text(row.get("cassette_role")),
            cassette_order=row.get("cassette_order", 0),
            promoter_label=_text(row.get("promoter_label")),
            gene_label=_text(row.get("gene_label")),
            terminator_label=_text(row.get("terminator_label")),
            source_reference=_text(row.get("source_reference")),
            provenance_note=_text(row.get("provenance_note")),
        )
        if created:
            cassette_map[source_cassette_id or local_cassette_id] = local_cassette_id
            result["created_counts"]["expression_cassettes"] += 1

    for row in _section_rows(package, "cassette_parts"):
        local_cassette_id = cassette_map.get(_text(row.get("cassette_id")))
        if not local_cassette_id:
            result["warnings"].append(f"Skipped cassette part without imported cassette mapping: {row.get('part_label')}")
            continue
        created = repo.add_construct_cassette_part(
            local_cassette_id,
            part_order=row.get("part_order", 0),
            part_role=_text(row.get("part_role")) or "other",
            part_label=_text(row.get("part_label")),
            part_reference=_text(row.get("part_reference")),
            source_reference=_text(row.get("source_reference")),
            source_catalog=_text(row.get("source_catalog")),
            source_record_id=_text(row.get("source_record_id")),
            source_record_label=_text(row.get("source_record_label")),
            evidence_context_note=_text(row.get("evidence_context_note")),
            provenance_note=_text(row.get("provenance_note")),
        )
        if created:
            result["created_counts"]["cassette_parts"] += 1

    for row in _section_rows(package, "linked_genes"):
        local_construct_id = construct_map.get(_text(row.get("construct_id")))
        if not local_construct_id:
            result["warnings"].append(f"Skipped gene link without imported construct mapping: {row.get('gene_label')}")
            continue
        if repo.add_construct_gene_link(
            local_construct_id,
            gene_label=_text(row.get("gene_label")),
            gene_reference=_text(row.get("gene_reference")),
            source_reference=_text(row.get("source_reference")),
            provenance_note=_text(row.get("provenance_note")),
        ):
            result["created_counts"]["linked_genes"] += 1

    for row in _section_rows(package, "linked_pathway_steps"):
        local_construct_id = construct_map.get(_text(row.get("construct_id")))
        if not local_construct_id:
            result["warnings"].append(
                f"Skipped pathway step link without imported construct mapping: {row.get('pathway_step_label')}"
            )
            continue
        if repo.add_construct_pathway_step_link(
            local_construct_id,
            pathway_step_id=_text(row.get("pathway_step_id")),
            pathway_step_label=_text(row.get("pathway_step_label")),
            source_reference=_text(row.get("source_reference")),
            provenance_note=_text(row.get("provenance_note")),
        ):
            result["created_counts"]["linked_pathway_steps"] += 1

    for row in _section_rows(package, "project_construct_links"):
        local_construct_id = construct_map.get(_text(row.get("construct_id")))
        if not local_construct_id:
            result["warnings"].append(f"Skipped project link without imported construct mapping: {row.get('link_label')}")
            continue
        link_project_id = resolved_project_id or _text(row.get("project_id"))
        if repo.create_construct_project_link(
            project_id=link_project_id,
            construct_id=local_construct_id,
            link_label=_text(row.get("link_label")),
            link_note=_text(row.get("link_note")),
            source_context=_text(row.get("source_context")),
            curation_status=_text(row.get("curation_status")),
            review_note=_text(row.get("review_note")),
        ):
            result["created_counts"]["project_construct_links"] += 1

    for index, row in enumerate(_section_rows(package, "project_catalog_asset_links")):
        source_project_id = _text(row.get("project_id"))
        asset_id = _text(row.get("asset_id"))
        asset_type = _text(row.get("asset_type"))
        if not source_project_id or not asset_id or not asset_type:
            result["created_counts"]["project_catalog_asset_link_skipped"] += 1
            result["warnings"].append(
                f"Skipped catalog reference link row {index} because project_id, asset_id, or asset_type was missing."
            )
            continue
        link_project_id = resolved_project_id or source_project_id
        asset_snapshot = _catalog_reference_asset_snapshot(row, preserve_malformed=True)
        if row.get("asset_snapshot") not in (None, "", {}) and not catalog_asset_snapshot_has_content(asset_snapshot):
            result["warnings"].append(
                f"Catalog reference link row {index} has malformed snapshot metadata and will use live metadata fallback."
            )
        added, message, _stored = project_catalog_link_repo.add_project_catalog_asset_link(
            {
                "project_id": link_project_id,
                "asset_id": asset_id,
                "asset_display_name": _text(row.get("asset_label")) or asset_id,
                "asset_type": asset_type,
                "asset_version": _text(row.get("asset_version")),
                "source_label": _text(row.get("source_label")),
                "documentation_status": _text(row.get("documentation_status")),
                "notes": _text(row.get("notes")),
                "linkage_role": _text(row.get("linkage_role")) or "project_reference",
                "source_context_snapshot": _catalog_reference_source_snapshot(row),
                "review_status_snapshot": _catalog_reference_review_snapshot(row),
                "snapshot_schema_version": _text(
                    row.get("snapshot_schema_version")
                    or _compact_metadata(row).get("snapshot_schema_version")
                ),
                "asset_snapshot": asset_snapshot,
                "snapshot_captured_at": _text(
                    row.get("snapshot_captured_at")
                    or _compact_metadata(row).get("snapshot_captured_at")
                ),
                "human_review_required": bool(row.get("human_review_required", True)),
            }
        )
        if added:
            result["created_counts"]["project_catalog_asset_links"] += 1
        else:
            result["created_counts"]["project_catalog_asset_link_duplicates"] += 1
            if message:
                _add_message(result["warnings"], message)

    result["construct_id_map"] = construct_map
    result["cassette_id_map"] = cassette_map
    result["created"] = any(
        result["created_counts"].get(key, 0) > 0
        for key in (
            "construct_profiles",
            "expression_cassettes",
            "cassette_parts",
            "linked_genes",
            "linked_pathway_steps",
            "project_construct_links",
            "project_catalog_asset_links",
        )
    )
    return result


def import_package_create_as_new(
    package: Any,
    *,
    target_project_id: str | int | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    dry_run = build_import_dry_run(package, target_project_id=target_project_id)
    result = {
        "created": False,
        "confirm_required": not confirm,
        "errors": [],
        "warnings": [],
        "dry_run": dry_run,
        "created_counts": {
            "construct_profiles": 0,
            "expression_cassettes": 0,
            "cassette_parts": 0,
            "linked_genes": 0,
            "linked_pathway_steps": 0,
            "project_construct_links": 0,
            "project_catalog_asset_links": 0,
            "project_catalog_asset_link_duplicates": 0,
            "project_catalog_asset_link_skipped": 0,
        },
        "construct_id_map": {},
        "cassette_id_map": {},
        "documentation_only_boundary": CREATE_BOUNDARY,
    }
    if not isinstance(package, dict):
        result["errors"] = list(dry_run["validation"].get("errors") or [])
        return result
    if not dry_run["validation"].get("is_valid"):
        result["errors"] = list(dry_run["validation"].get("errors") or [])
        result["warnings"] = list(dry_run["validation"].get("warnings") or [])
        return result
    if not confirm:
        result["errors"].append(
            "Create-as-new import requires explicit confirmation after the dry-run preview is reviewed."
        )
        result["warnings"] = list(dry_run["validation"].get("warnings") or [])
        return result

    created = import_project_documentation_package_as_new_records(
        package,
        target_project_id=target_project_id,
    )
    result["created"] = bool(created.get("created"))
    result["confirm_required"] = False
    result["errors"] = list(created.get("errors") or [])
    result["warnings"] = list(created.get("warnings") or [])
    result["created_counts"] = dict(created.get("created_counts") or {})
    result["construct_id_map"] = dict(created.get("construct_id_map") or {})
    result["cassette_id_map"] = dict(created.get("cassette_id_map") or {})
    return result
