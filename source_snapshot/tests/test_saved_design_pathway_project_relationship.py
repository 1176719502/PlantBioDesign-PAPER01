from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "views" / "Dashboard.py"
DESIGN_LIBRARY = ROOT / "views" / "DesignLibrary.py"
PATHWAY_PROJECTS = ROOT / "views" / "PathwayProjects.py"
PROJECT_MANAGER = ROOT / "components" / "project_manager.py"
PATHWAY_WORKSPACE = ROOT / "views" / "PathwayWorkspace.py"
LOCALES_EN = ROOT / "locales" / "en.py"

CONCEPT_FILES = [DASHBOARD, DESIGN_LIBRARY, PATHWAY_PROJECTS, PROJECT_MANAGER, PATHWAY_WORKSPACE, LOCALES_EN]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _combined(paths: list[Path]) -> str:
    return "\n".join(_read(path) for path in paths)


def test_core_concept_copy_exists() -> None:
    source = _combined(CONCEPT_FILES)

    required_copy = [
        "Saved design = wizard snapshot",
        "Pathway project = documentation project for pathway context",
        "Active project = currently selected pathway project for Pathway Workspace",
        "Linked artifact = documentation record connected to a pathway project",
    ]

    missing = [item for item in required_copy if item not in source]
    assert not missing


def test_saved_design_boundary_copy_exists() -> None:
    source = _combined(CONCEPT_FILES)

    required_copy = [
        "Saved design records library.",
        "Saved design records are local documentation records",
        "Expression Wizard design record subflow",
        "linked Pathway Project context",
        "This saved design record can be reviewed in linked Pathway Project context",
        "linked records should support documentation traceability",
        "Expression Wizard is the design record subflow.",
        "Documentation artifacts and saved design records are review records only.",
    ]

    missing = [item for item in required_copy if item not in source]
    assert not missing

    old_copy = [
        "Loading a saved design restores wizard inputs and outputs.",
        "Loading a saved design does not automatically create or select a pathway project.",
        "loading restores wizard inputs and outputs",
    ]
    present = [item for item in old_copy if item in source]
    assert not present


def test_design_library_language_uses_snapshot_not_project_boundary_confusion() -> None:
    source = _combined([DESIGN_LIBRARY, LOCALES_EN])

    assert "saved design snapshot" in source or "wizard snapshot" in source

    misleading_copy = [
        "saved design project",
        "saved project is active project",
        "loading a saved design creates a pathway project",
    ]
    present = [item for item in misleading_copy if item in source.lower()]
    assert not present


def test_pathway_projects_and_project_manager_language_exists() -> None:
    source = _combined([PATHWAY_PROJECTS, PROJECT_MANAGER])

    required_copy = [
        "Use Pathway Projects when expression vector design records need optional project grouping",
        "or documentation traceability.",
        "Selecting a pathway project makes it the active project for Pathway Workspace.",
        "does not certify experimental readiness",
    ]

    missing = [item for item in required_copy if item not in source]
    assert not missing


def test_import_safety_still_locked_in_ui_path() -> None:
    source = _read(PATHWAY_WORKSPACE)

    forbidden_copy = [
        "enable_database_write=True",
        "execute_project_import_as_new_project",
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Import now",
        "Ready to import",
        "Ready for execution",
    ]

    present = [item for item in forbidden_copy if item in source]
    assert not present


def test_existing_navigation_polish_still_present() -> None:
    source = _read(PATHWAY_WORKSPACE)

    required_copy = [
        "No active pathway project selected",
        "Pathway Workspace shows one documentation project at a time.",
        "Go to Pathway Projects",
        "Design Library",
        "traceability",
    ]

    missing = [item for item in required_copy if item not in source]
    assert not missing
