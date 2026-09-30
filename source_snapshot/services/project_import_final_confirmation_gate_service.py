from __future__ import annotations

FINAL_CONFIRMATION_PREREQUISITES = {
    "package_valid": "valid package",
    "validator_is_valid": "validator is_valid=True",
    "dry_run_available": "dry-run import plan available",
    "preflight_panel_available": "preflight panel available",
    "result_preview_displayed": "import execution result preview displayed",
    "final_confirmation_checked": "explicit final confirmation checked",
    "final_warning_visible": "final warning visible",
    "execution_branch_explicitly_enabled": "execution branch explicitly enabled",
}


def build_project_import_final_confirmation_gate_state(
    *,
    package_valid: bool,
    validator_is_valid: bool,
    dry_run_available: bool,
    preflight_panel_available: bool,
    result_preview_displayed: bool,
    final_confirmation_checked: bool,
    final_warning_visible: bool,
    execution_branch_explicitly_enabled: bool,
) -> dict[str, object]:
    """Return pure contract-preview state for the final import confirmation gate.

    This helper is intentionally read-only. In this build, the future create action
    remains disabled even when every prerequisite is satisfied.
    """
    prerequisite_values = {
        "package_valid": bool(package_valid),
        "validator_is_valid": bool(validator_is_valid),
        "dry_run_available": bool(dry_run_available),
        "preflight_panel_available": bool(preflight_panel_available),
        "result_preview_displayed": bool(result_preview_displayed),
        "final_confirmation_checked": bool(final_confirmation_checked),
        "final_warning_visible": bool(final_warning_visible),
        "execution_branch_explicitly_enabled": bool(execution_branch_explicitly_enabled),
    }
    prerequisites = [
        {"key": key, "label": label, "satisfied": prerequisite_values[key]}
        for key, label in FINAL_CONFIRMATION_PREREQUISITES.items()
    ]
    missing_prerequisites = [item["label"] for item in prerequisites if not item["satisfied"]]

    disabled_reasons: list[str] = []
    if missing_prerequisites:
        disabled_reasons.extend(missing_prerequisites)
    disabled_reasons.append("Execution is unavailable in this build.")
    disabled_reasons.append("Final confirmation does not enable project creation in this build.")

    return {
        "prerequisites": prerequisites,
        "missing_prerequisites": missing_prerequisites,
        "final_confirmation_required": True,
        "final_confirmation_checked": bool(final_confirmation_checked),
        "execution_available_in_this_build": False,
        "can_enable_create_action": False,
        "disabled_reasons": disabled_reasons,
        "contract_preview_only": True,
    }
