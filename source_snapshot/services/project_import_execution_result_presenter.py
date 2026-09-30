from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SUPPORTED_EXECUTION_STATUSES = {
    "success",
    "completed",
    "failed",
    "partial_failure",
    "blocked_preflight",
    "disabled_in_this_build",
}

DOCUMENTATION_ONLY_BOUNDARY = (
    "documentation-only result display; imported linked artifacts remain computational previews; "
    "imported review records remain review records only; does not provide wet-lab protocols"
)

NO_READINESS_OR_EVIDENCE_BOOST_STATEMENT = (
    "does not certify experimental readiness; does not predict yield; does not optimize pathways; "
    "no readiness boost; no evidence boost; no validation claim"
)

LIMITED_ROLLBACK_NOTE = (
    "limited rollback note: future execution results must describe created counts and any partial state; "
    "this display contract performs no rollback and writes no database state"
)

DISABLED_MESSAGE = "Execution remains disabled in this build."
NO_DATABASE_WRITES_MESSAGE = "No database writes are performed."
NO_PROJECT_CREATED_MESSAGE = "no project created"

STATUS_LABELS = {
    "success": "Created documentation project",
    "completed": "Created documentation project",
    "failed": "Failed",
    "partial_failure": "Partial failure",
    "blocked_preflight": "Blocked by preflight",
    "disabled_in_this_build": "Disabled in this build",
}

REQUIRED_PREFLIGHT_CHECKLIST_ITEMS = [
    "valid package required",
    "validator is_valid=True",
    "dry-run plan available",
    "dry-run plan does not write database",
    "import as new project only",
    "no overwrite",
    "no merge",
    "no raw payload_json restoration",
    "no original id restoration",
    "no executable content restoration",
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
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _normalize_status(value: Any) -> str:
    status = str(value or "").strip()
    if status in SUPPORTED_EXECUTION_STATUSES:
        return status
    return "failed"


def present_import_execution_result(result: Mapping[str, Any] | None) -> dict[str, Any]:
    """Build a pure display model for future import execution results.

    This presenter only maps supplied result data into UI-safe copy. It does not import,
    persist, create projects, call repositories, or modify database state.
    """
    raw_result = result or {}
    status = _normalize_status(raw_result.get("execution_status"))

    is_complete_success = status in {"success", "completed"}
    created_project_id = raw_result.get("created_project_id") if is_complete_success else None
    imported_project_name = raw_result.get("imported_project_name") if is_complete_success else None
    created_counts = _as_dict(raw_result.get("created_counts"))
    warnings = _as_list(raw_result.get("warnings"))
    errors = _as_list(raw_result.get("errors"))
    audit_summary = _as_dict(raw_result.get("audit_summary"))
    blocking_reasons = _as_list(raw_result.get("blocking_reasons"))

    if status == "blocked_preflight" and not blocking_reasons:
        blocking_reasons = ["blocking reasons"]
    if status == "disabled_in_this_build":
        warnings = [*warnings, DISABLED_MESSAGE, NO_DATABASE_WRITES_MESSAGE]
        created_project_id = None
    if status in {"failed", "partial_failure"} and not errors:
        errors = ["Result status requires errors to be reviewed."]

    display_sections: list[dict[str, Any]] = [
        {
            "title": "Status",
            "items": [status, STATUS_LABELS[status]],
        },
        {
            "title": "Safety boundary",
            "items": [DOCUMENTATION_ONLY_BOUNDARY, NO_READINESS_OR_EVIDENCE_BOOST_STATEMENT],
        },
    ]

    if status in {"success", "completed"}:
        display_sections.append(
            {
                "title": "Created documentation project summary",
                "items": [created_project_id, imported_project_name, created_counts, audit_summary],
            }
        )
    elif status == "failed":
        display_sections.append(
            {
                "title": "Failure summary",
                "items": [errors, warnings, created_counts, LIMITED_ROLLBACK_NOTE],
            }
        )
    elif status == "partial_failure":
        display_sections.append(
            {
                "title": "Partial failure summary",
                "items": [errors, warnings, created_counts, LIMITED_ROLLBACK_NOTE, audit_summary],
            }
        )
    elif status == "blocked_preflight":
        display_sections.append(
            {
                "title": "Preflight block summary",
                "items": [blocking_reasons, NO_DATABASE_WRITES_MESSAGE, NO_PROJECT_CREATED_MESSAGE, REQUIRED_PREFLIGHT_CHECKLIST_ITEMS],
            }
        )
    elif status == "disabled_in_this_build":
        display_sections.append(
            {
                "title": "Disabled execution preview",
                "items": [
                    DISABLED_MESSAGE,
                    NO_DATABASE_WRITES_MESSAGE,
                    "This preview does not import or modify any project.",
                    "Create New Documentation Project is a future gated action preview only.",
                ],
            }
        )

    return {
        "execution_status": status,
        "status_label": STATUS_LABELS[status],
        "created_project_id": created_project_id,
        "imported_project_name": imported_project_name,
        "created_counts": created_counts,
        "warnings": warnings,
        "errors": errors,
        "audit_summary": audit_summary,
        "blocking_reasons": blocking_reasons,
        "limited_rollback_note": LIMITED_ROLLBACK_NOTE,
        "documentation_only_boundary": DOCUMENTATION_ONLY_BOUNDARY,
        "no_readiness_or_evidence_boost_statement": NO_READINESS_OR_EVIDENCE_BOOST_STATEMENT,
        "display_sections": display_sections,
    }
