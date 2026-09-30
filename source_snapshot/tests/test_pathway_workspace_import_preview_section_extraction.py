from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
SECTIONS_DIR = ROOT / "views" / "pathway_workspace_sections"
IMPORT_PREVIEW_SECTION = SECTIONS_DIR / "import_preview_section.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_import_preview_section_exists() -> None:
    assert IMPORT_PREVIEW_SECTION.exists()


def test_pathway_workspace_imports_and_calls_import_preview_renderer() -> None:
    source = _read(PATHWAY_WORKSPACE)
    assert "from views.pathway_workspace_sections.import_preview_section import render_import_preview_section" in source
    assert "render_import_preview_section()" in source


def test_project_import_package_preview_copy_preserved() -> None:
    source = _read(IMPORT_PREVIEW_SECTION)
    required = [
        "Project Import Package Preview",
        "import package preview",
        "dry-run",
        "read-only",
        "preview only",
        "no database writes",
        "no project creation",
        "No database writes are performed.",
        "This preview does not import or modify any project.",
        "A separate gated action below may create a local documentation-only project only after package validation, safety review, dry-run planning, and explicit final confirmation.",
        "If a blocked state is shown below, it applies only to the separate gated create-as-new action",
        "Final confirmation is required before creating a new documentation project.",
    ]
    for text in required:
        assert text in source


def test_import_preview_has_only_gated_documentation_project_execution_entry_point() -> None:
    source = "\n".join([_read(PATHWAY_WORKSPACE), _read(IMPORT_PREVIEW_SECTION)])

    required = [
        "execute_project_import_as_new_project",
        "enable_database_write=True",
        "project_import_create_new_documentation_project_confirmation",
        "can_enable_create_action",
        "Create New Documentation Project",
        "Documentation project creation summary only",
        "Documentation project created.",
        "imported_project_name",
        "created_project_id",
        "created_counts",
        "project_import_create_result",
        "pathway_current_project_id",
    ]
    forbidden = [
        "Import" + " Project",
        "Execute" + " Import",
        "Confirm" + " Import",
        "Import" + " now",
        "Ready" + " to import",
        "Ready" + " for execution",
        "successful" + " import",
        "import" + " succeeded",
        "project" + " imported",
        "allow overwrite",
        "allow merge",
        "certifies experimental readiness",
        "predicts yield",
        "optimizes pathways",
        "provides wet-lab protocols",
    ]

    assert [text for text in required if text not in source] == []
    assert [text for text in forbidden if text in source.lower()] == []


def test_import_preview_persists_creation_result_and_sets_active_project() -> None:
    source = _read(IMPORT_PREVIEW_SECTION)
    required = [
        'st.session_state["project_import_create_result"] = result',
        'st.session_state["pathway_current_project_id"] = created_project_id',
        'st.session_state["project_import_execution_created_project_id"] = created_project_id',
        'st.session_state["project_import_execution_imported_project_name"] = result.get("imported_project_name")',
        'st.success("Documentation project created.")',
        'st.info("The new documentation-only project is now available in Pathway Projects / Pathway Workspace.")',
    ]
    assert [text for text in required if text not in source] == []


def test_import_preview_prevents_same_session_duplicate_creation() -> None:
    source = _read(IMPORT_PREVIEW_SECTION)
    required = [
        "hashlib.sha256(zip_bytes).hexdigest()",
        'project_import_create_created_by_package',
        'project_import_create_last_package_fingerprint',
        'disabled=not creation_state["can_create"]',
        "A documentation project was already created from this package in this session.",
    ]
    assert [text for text in required if text not in source] == []


def test_import_preview_warns_and_gates_existing_source_package_copy() -> None:
    source = _read(IMPORT_PREVIEW_SECTION)
    required = [
        "_find_existing_documentation_project_from_same_package",
        "list_pathway_documentation_snapshots",
        "source_project_name",
        "source_project_id",
        "package_fingerprint",
        "A documentation-only project from this package appears to already exist.",
        "Existing project name:",
        "Existing project ID:",
        "Existing package match:",
        "Review note: open the existing documentation-only project instead of creating another copy.",
        "Create another documentation-only copy anyway.",
        "project_import_create_another_documentation_copy_confirmation",
        "existing_documentation_project and not duplicate_copy_confirmed",
        "confirm another documentation-only copy before creation",
        "disabled=not creation_state[\"can_create\"]",
        "if st.button(\n            \"Create New Documentation Project\"",
        "result = execute_project_import_as_new_project(zip_bytes, enable_database_write=True)",
    ]
    assert [text for text in required if text not in source] == []


def test_import_preview_state_model_reconciles_copy_button_and_runtime_behavior() -> None:
    source = _read(IMPORT_PREVIEW_SECTION)
    required = [
        "def _build_import_preview_creation_state_model",
        "Preview/review blocked: safety review is blocked, so no local documentation project will be created.",
        "Preview/review blocked for local documentation project creation.",
        "Local documentation project creation allowed after explicit confirmation.",
        "This action can create a local documentation-only project from the reviewed package.",
        "if not creation_state[\"can_create\"]:",
        'st.error("Local documentation project creation is blocked in the current state. No database write was performed.")',
    ]
    assert [text for text in required if text not in source] == []


def test_import_preview_duplicate_detection_has_cross_session_fallbacks() -> None:
    source = _read(IMPORT_PREVIEW_SECTION)
    required = [
        "def _source_identity_matches",
        'for key in ("package_fingerprint", "source_project_id"):',
        "expected.get(key) and candidate.get(key) and expected[key] == candidate[key]",
        "def _snapshot_payload_source_identity",
        'payload.get("source_project_id") or project_id_summary.get("source_id")',
        'payload.get("package_fingerprint")',
        "def _existing_documentation_project_result",
        'match_reason: str = "source identity"',
        '"import audit payload"',
        "return None",
    ]
    forbidden = [
        'match_reason="project name"',
        "return name_matched_project",
        "if _project_name_matches_source_package",
    ]
    assert [text for text in required if text not in source] == []
    assert [text for text in forbidden if text in source] == []


def test_import_preview_duplicate_detection_does_not_use_source_project_name_as_match_key() -> None:
    source = _read(IMPORT_PREVIEW_SECTION)
    source_identity_matches_start = source.index("def _source_identity_matches")
    source_identity_matches_end = source.index("def _project_name_matches_source_package", source_identity_matches_start)
    source_identity_matches_body = source[source_identity_matches_start:source_identity_matches_end]

    assert 'for key in ("package_fingerprint", "source_project_id"):' in source_identity_matches_body
    assert "source_project_name" not in source_identity_matches_body


def test_import_preview_duplicate_copy_override_allows_create_gate() -> None:
    source = _read(IMPORT_PREVIEW_SECTION)
    assert "duplicate_copy_confirmed = st.checkbox" in source
    assert "confirmation_checked=confirmation_checked and not safety_blocked" in source
    assert "if existing_documentation_project and not duplicate_copy_confirmed" in source
    assert "if existing_documentation_project and duplicate_copy_confirmed" not in source


def test_import_preview_denylist_copy_absent() -> None:
    source = _read(IMPORT_PREVIEW_SECTION).lower()
    forbidden = [
        "successful import",
        "project imported",
        "ready to import",
        "ready for execution",
        "experiment-ready",
        "production-ready",
        "validated construct",
        "optimized pathway",
        "yield prediction",
    ]
    assert [text for text in forbidden if text in source] == []


def test_import_plan_and_audit_snapshot_preserve_source_identity_for_duplicate_detection() -> None:
    planner_source = _read(ROOT / "services" / "project_import_dry_run_planner.py")
    service_source = _read(ROOT / "services" / "project_import_service.py")
    required_planner = [
        "hashlib.sha256(zip_bytes).hexdigest()",
        '"source_project_id": None',
        '"package_fingerprint": None',
        'plan["source_project_id"] = manifest.get("project_id")',
    ]
    required_service = [
        '"source_project_id": manifest.get("project_id")',
        '"package_fingerprint": dry_run_plan.get("package_fingerprint")',
        '"raw_payload_restored": False',
    ]
    assert [text for text in required_planner if text not in planner_source] == []
    assert [text for text in required_service if text not in service_source] == []
