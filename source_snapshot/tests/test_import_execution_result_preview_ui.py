from __future__ import annotations

from pathlib import Path

from services.project_import_execution_result_presenter import present_import_execution_result

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
PRESENTER = ROOT / "services" / "project_import_execution_result_presenter.py"

REQUIRED_RESULT_PREVIEW_COPY = [
    "Import Execution Result Preview",
    "Result preview only.",
    "Documentation project creation requires all explicit gates.",
    "Execution only creates a documentation project after final confirmation.",
    "No database writes are performed.",
    "This preview does not import or modify any project.",
    "Create New Documentation Project is available only after package validation, safety review, dry-run planning, and explicit final confirmation.",
]

FORBIDDEN_FAKE_SUCCESS_UI = [
    "Created successfully",
    "Successful import",
    "success result preview",
    "created_project_id = ",
    "fake_project_id",
    "mock_created_project",
]

FORBIDDEN_EXECUTION_PATH_TERMS = [
    "enable_database_write=True",
    "execute_project_import_as_new_project",
    "create_project(",
    "insert_project",
    "update_project",
    "delete_project",
    "repository.write",
    "repo.write",
    "ProjectRepository",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _flatten(value: object) -> str:
    return str(value)


def test_result_preview_copy_exists() -> None:
    source = _read(PATHWAY_WORKSPACE)

    assert [term for term in REQUIRED_RESULT_PREVIEW_COPY if term not in source] == []


def test_presenter_is_used_safely() -> None:
    source = _read(PATHWAY_WORKSPACE)

    assert "present_import_execution_result" in source
    assert "extracted import preview section owns the gated execution path" in source
    assert "validation, safety," in source
    assert "dry-run planning, and final confirmation" in source


def test_disabled_result_model_behavior() -> None:
    model = present_import_execution_result({"execution_status": "disabled_in_this_build"})
    flattened = _flatten(model)

    assert model["execution_status"] == "disabled_in_this_build"
    assert "Execution remains disabled in this build." in flattened
    assert "documentation-only" in model["documentation_only_boundary"]
    assert "no readiness boost" in model["no_readiness_or_evidence_boost_statement"]
    assert "no evidence boost" in model["no_readiness_or_evidence_boost_statement"]


def test_blocked_preflight_model_behavior() -> None:
    model = present_import_execution_result(
        {
            "execution_status": "blocked_preflight",
            "blocking_reasons": ["valid package required", "dry-run plan available"],
        }
    )
    flattened = _flatten(model)

    assert model["execution_status"] == "blocked_preflight"
    assert "valid package required" in model["blocking_reasons"]
    assert "dry-run plan available" in model["blocking_reasons"]
    assert "No database writes are performed." in flattened
    assert "no project created" in flattened
    assert "documentation-only" in model["documentation_only_boundary"]


def test_no_fake_success_ui() -> None:
    source = _read(PATHWAY_WORKSPACE)

    assert [term for term in FORBIDDEN_FAKE_SUCCESS_UI if term in source] == []


def test_execution_path_remains_gated_documentation_only() -> None:
    source = _read(PATHWAY_WORKSPACE)
    presenter_source = _read(PRESENTER)

    required_contract_terms = [
        "read-only preview",
        "No database writes are performed by preview and safety checks.",
        "This preview does not import or modify any project.",
        "No project creation during preview",
        "no overwrite",
        "no merge",
        "validation, safety,",
        "dry-run planning, and final confirmation",
        "Documentation project creation requires all explicit gates.",
        "documentation-only",
        "no readiness boost",
        "no validation claim",
        "predict yield",
        "optimize pathways",
        "does not provide wet-lab instructions",
    ]
    assert [term for term in required_contract_terms if term not in source] == []

    forbidden_execution_boundary_terms = [
        "execute_project_import_as_new_project",
        "enable_database_write=True",
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Import now",
        "Ready to import",
        "Ready for execution",
    ]
    assert [term for term in forbidden_execution_boundary_terms if term in source] == []

    forbidden_direct_repository_terms = [
        "create_project(",
        "insert_project",
        "update_project",
        "delete_project",
        "repository.write",
        "repo.write",
        "ProjectRepository",
    ]
    violations: list[str] = []
    for term in forbidden_direct_repository_terms:
        if term in source or term in presenter_source:
            violations.append(term)

    assert violations == []


def test_required_boundary_copy_remains_visible_in_ui_source() -> None:
    source = _read(PATHWAY_WORKSPACE)
    required = [
        "disabled_in_this_build",
        "blocked_preflight",
        "documentation-only",
        "no readiness boost",
        "no evidence boost",
        "no validation claim",
        "limited rollback note",
        "audit summary required before future execution",
        "computational previews",
        "review records only",
    ]

    assert [term for term in required if term not in source] == []
