from __future__ import annotations

from typing import Any

EXECUTION_DISABLED_REASON = "Execution requires a valid package, safety checks, dry-run plan, and explicit final confirmation."

GATED_IMPORT_EXECUTION_BOUNDARY = (
    "documentation-only, import as new project only, no overwrite, "
    "no merge, no raw payload_json restoration; does not certify experimental readiness, "
    "does not predict yield, does not optimize pathways, and does not provide wet-lab protocols. "
    "Linked artifacts remain computational previews / review records only."
)

IMPORT_EXECUTION_PREFLIGHT_INTRO_COPY = [
    "This preflight review must pass before the final Create New Documentation Project action can run.",
    "Execution creates a new documentation project only after explicit final confirmation.",
    "The import does not overwrite, merge, restore raw payload_json, or modify existing projects.",
    "This workflow does not certify experimental readiness, predict yield, optimize pathways, or provide wet-lab protocols.",
]

IMPORT_EXECUTION_PREFLIGHT_ITEMS = [
    ("Package validation", ["valid package required", "validator is_valid=True"]),
    ("Dry-run import plan", ["dry-run plan available", "dry-run plan does not write database"]),
    ("Project creation boundary", ["import as new project only", "no overwrite", "no merge", "no existing project restore"]),
    (
        "Payload boundary",
        ["no raw payload_json restoration", "no original id restoration", "no executable content restoration"],
    ),
    (
        "Safety boundary",
        [
            "documentation-only",
            "does not certify experimental readiness",
            "does not predict yield",
            "does not optimize pathways",
            "does not provide wet-lab protocols",
        ],
    ),
    (
        "Artifact boundary",
        ["imported linked artifacts remain computational previews", "imported review records remain review records only"],
    ),
    ("Failure/audit boundary", ["limited rollback note", "audit summary required before future execution"]),
    (
        "Final confirmation requirement",
        [
            "explicit confirmation checkbox required before execution branch",
            "creation is enabled only when validation, dry-run, safety, and final confirmation gates pass",
        ],
    ),
]


def build_project_import_execution_gate_state(
    *,
    validation_report: dict[str, Any] | None,
    dry_run_plan: dict[str, Any] | None,
    confirmation_checked: bool,
) -> dict[str, Any]:
    """Return UI gate state for controlled documentation-only import execution.

    This helper is intentionally pure. It never imports, creates, persists, merges,
    overwrites, restores raw payload_json, or writes to the database. It only decides
    whether the caller may show the final execution action after all visible gates pass.
    """
    package_valid = bool((validation_report or {}).get("is_valid"))
    dry_run_available = bool((dry_run_plan or {}).get("is_plan_available"))
    disabled_reasons: list[str] = []

    if not package_valid:
        disabled_reasons.append("A valid package is required before any gated create action can be considered.")
    if not dry_run_available:
        disabled_reasons.append("A dry-run import plan is required before any gated create action can be considered.")
    if not confirmation_checked:
        disabled_reasons.append("The documentation-only confirmation checkbox must be checked.")

    preflight_blocking_reasons: list[str] = []
    if not package_valid:
        preflight_blocking_reasons.append("valid package required")
    if not dry_run_available:
        preflight_blocking_reasons.append("dry-run plan available")

    can_enable_create_action = package_valid and dry_run_available and bool(confirmation_checked)
    if not can_enable_create_action:
        disabled_reasons.append(EXECUTION_DISABLED_REASON)

    return {
        "package_valid": package_valid,
        "dry_run_available": dry_run_available,
        "confirmation_checked": bool(confirmation_checked),
        "execution_available_in_this_build": True,
        "can_show_gated_block": package_valid and dry_run_available,
        "can_enable_create_action": can_enable_create_action,
        "preflight_panel_available": package_valid and dry_run_available,
        "preflight_items": IMPORT_EXECUTION_PREFLIGHT_ITEMS,
        "preflight_intro_copy": IMPORT_EXECUTION_PREFLIGHT_INTRO_COPY,
        "preflight_blocking_reasons": preflight_blocking_reasons,
        "final_confirmation_required": True,
        "disabled_reasons": disabled_reasons,
        "boundary": GATED_IMPORT_EXECUTION_BOUNDARY,
    }
