from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs" / "import_execution_result_contract.md"

REQUIRED_TERMS = [
    "Result contract only",
    "No real import execution in this build",
    "No database writes are performed by this contract",
    "UI execution remains disabled",
    "success",
    "failed",
    "partial_failure",
    "blocked_preflight",
    "disabled_in_this_build",
    "execution_status",
    "created_project_id",
    "imported_project_name",
    "created_counts",
    "warnings",
    "errors",
    "audit_summary",
    "limited_rollback_note",
    "documentation_only_boundary",
    "no_readiness_or_evidence_boost_statement",
    "blocking reasons",
    "no database writes",
    "no project created",
    "documentation-only",
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "does not provide wet-lab protocols",
    "computational previews",
    "review records only",
    "no readiness boost",
    "no evidence boost",
    "no validation claim",
    "no overwrite",
    "no merge",
    "no raw payload_json restoration",
    "no original id restoration",
    "separate approved gated execution branch",
]


def _read_contract() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def test_import_execution_result_contract_document_exists() -> None:
    assert CONTRACT.exists()


def test_import_execution_result_contract_contains_required_terms() -> None:
    source = _read_contract()

    missing = [term for term in REQUIRED_TERMS if term not in source]

    assert missing == []


def test_contract_is_not_an_execution_path() -> None:
    source = _read_contract()

    assert "This contract cannot trigger execution." in source
    assert "This contract cannot call repository write APIs." in source
    assert "This contract cannot modify database state." in source
    assert "no executable import button" in source


def test_contract_keeps_disabled_display_copy() -> None:
    source = _read_contract()

    required = [
        "Execution remains disabled in this build.",
        "No database writes are performed.",
        "This preview does not import or modify any project.",
        "Create New Documentation Project is a future gated action preview only.",
    ]

    assert [term for term in required if term not in source] == []
