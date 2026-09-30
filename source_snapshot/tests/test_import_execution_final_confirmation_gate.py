from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "import_execution_final_confirmation_gate.md"

REQUIRED_TERMS = [
    "Final confirmation gate contract only",
    "No real import execution in this build",
    "No database writes are performed by this contract",
    "UI execution remains disabled",
    "valid package",
    "validator is_valid=True",
    "dry-run import plan available",
    "preflight panel available",
    "import execution result preview displayed",
    "explicit final confirmation checked",
    "final warning visible",
    "execution branch explicitly enabled",
    "execution_available_in_this_build = False",
    "can_enable_create_action = False",
    "final confirmation does not enable project creation",
    "no import occurs during preview",
    "no import occurs during checkbox toggle",
    "This final confirmation is a contract preview only.",
    "It does not enable project creation in this build.",
    "Create New Documentation Project",
    "documentation-only",
    "no overwrite",
    "no merge",
    "no raw payload_json restoration",
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "does not provide wet-lab protocols",
    "computational previews",
    "review records only",
    "no readiness boost",
    "no evidence boost",
    "no validation claim",
    "enable_database_write=False",
    "enable_database_write=True",
    "execute_project_import_as_new_project",
    "UI must not call repository write APIs directly",
    "Current decision: NO-GO",
    "separate explicitly approved gated execution branch",
]

FORBIDDEN_SUPPORTIVE_COPY = [
    "real import execution enabled",
    "production-ready",
    "experiment-ready",
    "validated project",
    "successful import",
    "optimized pathway",
    "yield prediction result",
    "wet-lab protocol generated",
]


def _read_contract() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def test_final_confirmation_gate_contract_document_exists() -> None:
    assert CONTRACT.exists()


def test_final_confirmation_gate_contract_contains_required_terms() -> None:
    source = _read_contract()

    missing = [term for term in REQUIRED_TERMS if term not in source]

    assert missing == []


def test_current_build_invariants_remain_no_go() -> None:
    source = _read_contract()

    required = [
        "execution_available_in_this_build = False",
        "can_enable_create_action = False",
        "checkbox does not enable database writes",
        "Execution remains disabled in this build.",
        "No database writes are performed.",
        "Current decision: NO-GO for real import execution UI in this build.",
    ]

    assert [term for term in required if term not in source] == []


def test_future_execution_rules_remain_explicitly_gated() -> None:
    source = _read_contract()

    required = [
        "UI may call only execute_project_import_as_new_project",
        "enable_database_write=True may appear only inside the final explicitly confirmed execution branch",
        "default service behavior must remain enable_database_write=False",
        "no execution should happen during page render",
        "no execution should happen during validator run",
        "no execution should happen during dry-run planning",
        "no execution should happen during preflight review",
        "no execution should happen during result preview",
        "no execution should happen during checkbox toggle",
    ]

    assert [term for term in required if term not in source] == []


def test_forbidden_copy_is_not_used_as_supportive_status() -> None:
    source = _read_contract().lower()

    assert [term for term in FORBIDDEN_SUPPORTIVE_COPY if term in source] == []
