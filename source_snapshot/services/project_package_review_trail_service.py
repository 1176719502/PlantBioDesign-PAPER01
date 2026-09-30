from __future__ import annotations

from typing import Any

STATUS_AVAILABLE = "AVAILABLE"
STATUS_NOT_AVAILABLE = "NOT_AVAILABLE"
STATUS_NEEDS_REVIEW = "NEEDS_REVIEW"

PACKAGE_EXCHANGE_BOUNDARY_NOTES = [
    "Package exchange review trail is documentation-only.",
    "Manifest review is documentation context for local project review.",
    "Package review does not certify correctness, downstream-use state, biological fit, or biological function.",
    "Older package formats may show limited metadata and review notes.",
]

PACKAGE_WORKFLOW_CONTEXT = [
    "Create or review project documentation.",
    "Export a documentation package with manifest metadata.",
    "Review the package in Import Manifest Review before local documentation use.",
    "Create a new project copy only through explicit create-as-new confirmation.",
    "Review the package exchange review trail in the Project Review Report and Project Quality Dashboard.",
]


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _first_present(source: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = source.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _manifest_summary_from(source: dict[str, Any]) -> dict[str, Any]:
    manifest_summary = _as_dict(source.get("manifest_summary"))
    if manifest_summary:
        return manifest_summary
    manifest = _as_dict(source.get("manifest"))
    if manifest:
        return {
            "is_manifest_present": True,
            "package_format": manifest.get("package_format"),
            "package_schema_version": manifest.get("package_schema_version"),
            "exported_at": manifest.get("exported_at"),
            "exported_by_app": manifest.get("exported_by_app"),
            "included_sections": manifest.get("included_sections"),
            "record_counts": manifest.get("record_counts"),
            "documentation_boundary": manifest.get("documentation_boundary"),
            "review_notes": manifest.get("review_notes"),
        }
    return {}


def _record_count_summary(manifest_summary: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    counts = _as_dict(
        _first_present(
            manifest_summary,
            ("record_counts", "counts"),
        )
    ) or _as_dict(source.get("record_counts") or source.get("counts"))
    return {
        "is_available": bool(counts),
        "record_count_keys": sorted(str(key) for key in counts),
        "record_count_total": sum(value for value in counts.values() if isinstance(value, int)),
        "record_counts": dict(counts),
    }


def _manifest_review(manifest_summary: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    included_sections = _as_list(
        _first_present(manifest_summary, ("included_sections",))
        or source.get("included_sections")
    )
    review_notes = [
        _text(note)
        for note in _as_list(manifest_summary.get("review_notes") or source.get("review_notes"))
        if _text(note)
    ]
    is_present = bool(manifest_summary.get("is_manifest_present") or manifest_summary)
    if not is_present and not review_notes:
        review_notes.append("Manifest metadata is not available for this package review trail.")
    record_counts = _record_count_summary(manifest_summary, source)
    return {
        "status": STATUS_AVAILABLE if is_present else STATUS_NEEDS_REVIEW,
        "is_manifest_present": is_present,
        "package_format": _text(manifest_summary.get("package_format")),
        "package_schema_version": _text(
            manifest_summary.get("package_schema_version") or source.get("package_schema_version")
        ),
        "exported_at": _text(manifest_summary.get("exported_at")),
        "exported_by_app": _text(manifest_summary.get("exported_by_app")),
        "included_sections": [str(item) for item in included_sections if _text(item)],
        "included_section_count": len([item for item in included_sections if _text(item)]),
        "record_counts": record_counts,
        "documentation_boundary": _text(
            manifest_summary.get("documentation_boundary")
            or source.get("documentation_boundary")
            or source.get("documentation_only_boundary")
        ),
        "review_notes": review_notes,
    }


def build_package_exchange_review_trail(
    export_summary: dict[str, Any] | None = None,
    import_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a read-only package exchange review trail from existing summary data."""
    export_data = _as_dict(export_summary)
    import_data = _as_dict(import_summary)
    manifest_source = import_data or export_data
    manifest_summary = _manifest_summary_from(import_data) or _manifest_summary_from(export_data)
    manifest_review = _manifest_review(manifest_summary, manifest_source)

    export_status = export_data.get("status") or STATUS_NOT_AVAILABLE
    import_status = (
        import_data.get("overall_status")
        or import_data.get("status")
        or STATUS_NOT_AVAILABLE
    )
    has_context = export_status != STATUS_NOT_AVAILABLE or import_status != STATUS_NOT_AVAILABLE
    review_notes = list(manifest_review.get("review_notes") or [])
    if export_status == STATUS_NOT_AVAILABLE:
        review_notes.append("Export package review context is not recorded.")
    if import_status == STATUS_NOT_AVAILABLE:
        review_notes.append("Import package review context is not recorded.")

    return {
        "section_title": "Package Exchange Review Trail",
        "status": STATUS_AVAILABLE if has_context else STATUS_NOT_AVAILABLE,
        "export_context": {
            "status": export_status,
            "package_contents_preview_status": (
                export_data.get("package_contents_preview_status")
                or export_data.get("contents_preview_availability")
                or export_data.get("contents_preview_status")
                or STATUS_NOT_AVAILABLE
            ),
            "last_export_status": export_data.get("last_export_status") or STATUS_NOT_AVAILABLE,
        },
        "import_context": {
            "status": import_status,
            "blocking_issue_count": len(_as_list(import_data.get("blocking_issues"))),
            "warning_count": len(_as_list(import_data.get("warnings"))),
            "not_evaluated_count": import_data.get("not_evaluated_count", 0),
        },
        "manifest_review": manifest_review,
        "review_notes": review_notes,
        "package_workflow_context": PACKAGE_WORKFLOW_CONTEXT,
        "demo_workflow_context": PACKAGE_WORKFLOW_CONTEXT,
        "documentation_boundary": (
            manifest_review.get("documentation_boundary")
            or export_data.get("documentation_only_boundary")
            or export_data.get("documentation_only_package_note")
            or "Package exchange review trail is documentation-only context."
        ),
        "boundary_notes": PACKAGE_EXCHANGE_BOUNDARY_NOTES,
    }
