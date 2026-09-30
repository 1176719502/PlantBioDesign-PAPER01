from __future__ import annotations

from pathlib import Path

from services.project_import_final_confirmation_gate_service import (
    build_project_import_final_confirmation_gate_state,
)

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "services" / "project_import_final_confirmation_gate_service.py"


def _state(**overrides: bool) -> dict[str, object]:
    values = {
        "package_valid": False,
        "validator_is_valid": False,
        "dry_run_available": False,
        "preflight_panel_available": False,
        "result_preview_displayed": False,
        "final_confirmation_checked": False,
        "final_warning_visible": False,
        "execution_branch_explicitly_enabled": False,
    }
    values.update(overrides)
    return build_project_import_final_confirmation_gate_state(**values)


def test_all_prerequisites_false_cannot_enable_create_action() -> None:
    state = _state()

    assert state["can_enable_create_action"] is False


def test_valid_package_only_cannot_enable_create_action() -> None:
    state = _state(package_valid=True)

    assert state["can_enable_create_action"] is False


def test_no_confirmation_cannot_enable_create_action() -> None:
    state = _state(
        package_valid=True,
        validator_is_valid=True,
        dry_run_available=True,
        preflight_panel_available=True,
        result_preview_displayed=True,
        final_warning_visible=True,
    )

    assert state["can_enable_create_action"] is False
    assert "explicit final confirmation checked" in state["missing_prerequisites"]


def test_all_prerequisites_true_but_execution_branch_not_enabled_is_disabled() -> None:
    state = _state(
        package_valid=True,
        validator_is_valid=True,
        dry_run_available=True,
        preflight_panel_available=True,
        result_preview_displayed=True,
        final_confirmation_checked=True,
        final_warning_visible=True,
        execution_branch_explicitly_enabled=False,
    )

    assert state["can_enable_create_action"] is False
    assert "execution branch explicitly enabled" in state["missing_prerequisites"]


def test_all_prerequisites_true_and_branch_enabled_still_disabled_in_current_build() -> None:
    state = _state(
        package_valid=True,
        validator_is_valid=True,
        dry_run_available=True,
        preflight_panel_available=True,
        result_preview_displayed=True,
        final_confirmation_checked=True,
        final_warning_visible=True,
        execution_branch_explicitly_enabled=True,
    )

    assert state["missing_prerequisites"] == []
    assert state["can_enable_create_action"] is False


def test_final_confirmation_checked_does_not_enable_creation() -> None:
    state = _state(final_confirmation_checked=True)

    assert state["final_confirmation_checked"] is True
    assert state["can_enable_create_action"] is False


def test_execution_available_in_this_build_is_false() -> None:
    assert _state()["execution_available_in_this_build"] is False


def test_contract_preview_only_is_true() -> None:
    assert _state()["contract_preview_only"] is True


def test_missing_prerequisites_lists_missing_items() -> None:
    state = _state(package_valid=True, validator_is_valid=True)

    assert "valid package" not in state["missing_prerequisites"]
    assert "validator is_valid=True" not in state["missing_prerequisites"]
    assert "dry-run import plan available" in state["missing_prerequisites"]
    assert "preflight panel available" in state["missing_prerequisites"]


def test_helper_source_does_not_contain_database_write_enablement() -> None:
    source = HELPER.read_text(encoding="utf-8")

    assert "enable_database_write=True" not in source


def test_helper_source_does_not_call_execution_service() -> None:
    source = HELPER.read_text(encoding="utf-8")

    assert "execute_project_import_as_new_project" not in source


def test_helper_source_does_not_import_repository_or_database() -> None:
    source = HELPER.read_text(encoding="utf-8")

    assert "import repository" not in source
    assert "from repository" not in source
    assert "import database" not in source
    assert "from database" not in source
