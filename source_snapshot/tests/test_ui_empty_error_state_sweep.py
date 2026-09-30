from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_TARGETS = [
    ROOT / "app.py",
    ROOT / "views",
    ROOT / "components",
    ROOT / "locales" / "en.py",
    ROOT / "services" / "ui_empty_state_presenter.py",
    ROOT / "services" / "tool_artifact_library_presenter.py",
    ROOT / "services" / "lab_tools_service.py",
    ROOT / "services" / "protein_structure_analysis_service.py",
]
CHANGED_UI_FILES = [
    ROOT / "services" / "ui_empty_state_presenter.py",
]
IMPORT_SAFETY_TARGETS = [
    ROOT / "views" / "PathwayWorkspace.py",
    ROOT / "views" / "pathway_workspace_sections" / "project_outputs_section.py",
    *CHANGED_UI_FILES,
]


def _python_files(targets: list[Path]) -> list[Path]:
    files: list[Path] = []
    for target in targets:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(path for path in target.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(set(files))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _combined_source(targets: list[Path] = UI_TARGETS) -> str:
    return "\n".join(_read(path) for path in _python_files(targets))


def _literal_values(path: Path) -> list[str]:
    tree = ast.parse(_read(path), filename=str(path))
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            static_parts = [
                value.value
                for value in node.values
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            ]
            if static_parts:
                values.append("".join(static_parts))
    return values


def _combined_literals(targets: list[Path] = UI_TARGETS) -> str:
    return "\n".join(value for path in _python_files(targets) for value in _literal_values(path))


def _missing(haystack: str, phrases: list[str]) -> list[str]:
    lower = haystack.lower()
    return [phrase for phrase in phrases if phrase.lower() not in lower]


def _offenders(haystack: str, phrases: list[str]) -> list[str]:
    lower = haystack.lower()
    return [phrase for phrase in phrases if phrase.lower() in lower]


def test_global_empty_error_copy_exists() -> None:
    combined = _combined_source()
    required = [
        "Enter input to generate a documentation preview.",
        "No saved documentation artifacts yet.",
        "No matching documentation records found.",
        "No linked documentation artifacts for this project yet.",
        "No active pathway project selected.",
        "No saved design snapshots found.",
        "No reference records found.",
        "This page creates documentation records only.",
        "This preview does not certify experimental readiness.",
        "Review the input and try again.",
    ]
    assert _missing(combined, required) == []


def test_tool_boundary_copy_exists() -> None:
    combined = _combined_source()
    required = [
        "computational preview only",
        "documentation-only",
        "review records only",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
        "does not validate folding",
        "does not validate function",
        "does not validate expression",
        "does not certify cloning success",
        "does not certify PCR success",
        "does not certify gel success",
        "does not certify expression success",
    ]
    assert _missing(combined, required) == []


def test_page_specific_empty_states_exist() -> None:
    combined = _combined_source()
    required = [
        "Enter a sequence to generate a preview.",
        "No reference records found.",
        "No saved design snapshots found.",
        "No pathway documentation projects found.",
        "No saved documentation artifacts yet.",
        "No linked documentation artifacts for this project yet.",
    ]
    assert _missing(combined, required) == []


def test_saved_design_pathway_relationship_copy_still_present() -> None:
    combined = _combined_source()
    required = [
        "Saved design = wizard snapshot",
        "Pathway project = documentation workspace",
        "Active project = currently selected pathway documentation workspace",
        "Loading a saved design does not automatically create or select a pathway project",
    ]
    assert _missing(combined, required) == []


def test_artifact_library_empty_search_states_still_present() -> None:
    combined = _combined_source()
    required = [
        "Search saved documentation artifacts",
        "Filter by artifact type",
        "Filter by linked project",
        "Documentation artifacts are saved review records only.",
    ]
    assert _missing(combined, required) == []


def test_import_safety_still_locked() -> None:
    combined = _combined_source(IMPORT_SAFETY_TARGETS)
    forbidden = [
        "enable_database_write=True",
        "execute_project_import_as_new_project",
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Import now",
        "Ready to import",
        "Ready for execution",
    ]
    assert _offenders(combined, forbidden) == []


def test_forbidden_misleading_copy_absent_in_changed_ui_files() -> None:
    combined = _combined_literals(CHANGED_UI_FILES)
    allowed_negative_fragments = [
        "does not certify experimental readiness",
        "does not certify cloning success",
        "does not certify PCR success",
        "does not certify expression success",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
    ]
    normalized = combined
    for allowed in allowed_negative_fragments:
        normalized = normalized.replace(allowed, "")
    forbidden = [
        "experiment-ready",
        "production-ready",
        "validated project",
        "validated import",
        "successful cloning",
        "successful PCR",
        "successful expression",
        "optimized pathway",
        "yield prediction result",
        "wet-lab protocol generated",
        "Save Validation",
        "Save Protocol",
        "Save Experiment",
        "Save Result",
    ]
    assert _offenders(normalized, forbidden) == []
