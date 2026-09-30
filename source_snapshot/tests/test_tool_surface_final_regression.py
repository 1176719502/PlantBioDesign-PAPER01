from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SURFACE_TARGETS = [
    ROOT / "app.py",
    ROOT / "locales" / "en.py",
    ROOT / "views",
    ROOT / "components",
    ROOT / "services" / "lab_tools_service.py",
    ROOT / "services" / "protein_structure_analysis_service.py",
    ROOT / "services" / "tool_artifact_service.py",
]

VISIBLE_COPY_FILES = [
    ROOT / "app.py",
    ROOT / "locales" / "en.py",
    ROOT / "views" / "Data.py",
    ROOT / "views" / "DesignLibrary.py",
    ROOT / "views" / "LabTools.py",
    ROOT / "views" / "SequenceTools.py",
    ROOT / "views" / "CodonOptimizer.py",
    ROOT / "views" / "StructureAnalysis.py",
    ROOT / "views" / "PathwayWorkspace.py",
    ROOT / "components" / "assembly_modules" / "tab_export.py",
    ROOT / "services" / "lab_tools_service.py",
    ROOT / "services" / "protein_structure_analysis_service.py",
    ROOT / "services" / "tool_artifact_service.py",
]

MODULE_COVERAGE = {
    "Lab Tools": [ROOT / "views" / "LabTools.py", ROOT / "services" / "lab_tools_service.py"],
    "Structure Analysis": [ROOT / "views" / "StructureAnalysis.py", ROOT / "services" / "protein_structure_analysis_service.py"],
    "Sequence Tools": [ROOT / "views" / "SequenceTools.py"],
    "Codon Usage Preview": [ROOT / "views" / "CodonOptimizer.py", ROOT / "app.py"],
    "Parts Registry": [ROOT / "views" / "Data.py", ROOT / "app.py", ROOT / "locales" / "en.py"],
    "Design Library": [ROOT / "views" / "DesignLibrary.py", ROOT / "app.py", ROOT / "locales" / "en.py"],
    "Data / Project Manager": [ROOT / "views" / "Data.py", ROOT / "app.py"],
}

ALLOWED_NEGATIVE_BOUNDARY_PHRASES = {
    "does not certify experimental readiness",
    "does not predict yield",
    "does not optimize pathways",
    "does not provide wet-lab protocols",
    "does not validate folding, function, expression",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _python_files() -> list[Path]:
    files: list[Path] = []
    for target in SURFACE_TARGETS:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(path for path in target.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(dict.fromkeys(files))


def _string_literals(path: Path) -> list[str]:
    tree = ast.parse(_read(path), filename=str(path))
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            text = "".join(
                value.value
                for value in node.values
                if isinstance(value, ast.Constant) and isinstance(value.value, str)
            )
            if text:
                values.append(text)
    return values


def _visible_literals(paths: list[Path] | None = None) -> str:
    selected = paths or VISIBLE_COPY_FILES
    return "\n".join(
        literal
        for path in selected
        if path.exists()
        for literal in _string_literals(path)
    )


def _surface_literals() -> str:
    return "\n".join(literal for path in _python_files() for literal in _string_literals(path))


def test_main_tool_pages_are_covered_by_visible_copy_regression_targets() -> None:
    missing = {
        module: [str(path.relative_to(ROOT)) for path in paths if not path.exists()]
        for module, paths in MODULE_COVERAGE.items()
    }
    assert {module: paths for module, paths in missing.items() if paths} == {}

    combined = _visible_literals()
    expected_labels = [
        "Lab Tools",
        "Structure Analysis",
        "Sequence Tools",
        "Codon Usage Preview",
        "Parts Registry",
        "Design Library",
    ]
    assert [label for label in expected_labels if label not in combined] == []


def test_global_user_visible_tool_labels_do_not_use_retired_copy() -> None:
    visible_copy = _visible_literals()
    disallowed = [
        "Assembly & Cloning ·",
        "Test & Validation",
        "Construct Design Validation",
        "Automated quality assessment",
        "Fragment validation: Pass",
    ]
    assert [phrase for phrase in disallowed if phrase in visible_copy] == []
    assert "Assembly and Cloning" in visible_copy


def test_tool_pages_do_not_make_positive_readiness_success_or_optimization_claims() -> None:
    visible_copy = _visible_literals().lower()
    disallowed = [
        "experiment-ready",
        "production-ready",
        "validated pathway",
        "validated construct",
        "validated cloning",
        "validated pcr",
        "validated expression",
        "successful cloning",
        "successful pcr",
        "successful expression",
        "optimized pathway",
        "optimized construct",
        "optimized sequence",
        "yield prediction result",
        "wet-lab protocol provided",
        "protocol generated",
    ]
    allowed_negative_boundary = "Do not treat the package as experiment-ready or production-ready.".lower()
    visible_copy_for_scan = visible_copy.replace(allowed_negative_boundary, "")
    offenders = [phrase for phrase in disallowed if phrase in visible_copy_for_scan]
    assert offenders == []

    for allowed in ALLOWED_NEGATIVE_BOUNDARY_PHRASES:
        # Guard the allowlist itself so future tests do not treat these negative boundaries as regressions.
        assert allowed in ALLOWED_NEGATIVE_BOUNDARY_PHRASES


def test_unified_tool_boundary_phrases_are_present() -> None:
    combined = _visible_literals().lower()
    required_any = [
        ("computational preview", "computational previews"),
        ("documentation artifacts", "documentation records"),
        ("review-only", "review records only", "documentation records only"),
    ]
    required_exact = [
        "documentation-only",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
    ]
    assert [phrase for phrase in required_exact if phrase not in combined] == []
    assert [options for options in required_any if not any(option in combined for option in options)] == []


def test_documentation_artifact_copy_is_consistent() -> None:
    combined = _visible_literals()
    required = [
        "Cloning preview records",
        "Save current cloning preview record",
        "Saved documentation records are documentation-only review records.",
        "Documentation Artifacts",
        "This removes the saved documentation artifact only.",
    ]
    disallowed = ["Save Validation", "Save Protocol", "Save Experiment", "Save Result", "文档伪影"]
    assert [phrase for phrase in required if phrase not in combined] == []
    assert [phrase for phrase in disallowed if phrase in combined] == []
    assert "Save Documentation Artifact" not in _read(ROOT / "views" / "LabTools.py")


def test_lab_tools_dormant_documentation_artifact_boundary_is_visible() -> None:
    combined = _visible_literals()
    required = [
        "Lab Tools is a dormant / V1 frozen / documentation artifact preview surface.",
        "It is not the current mainline tool path and not a wet-lab execution workflow.",
        "Artifact saved as a documentation artifact.",
        "Linked records are visible from Pathway Workspace linked documentation artifacts.",
        "not validation",
        "not prediction",
        "not recommendation",
        "not readiness approval",
        "not wet-lab protocol",
    ]
    assert [phrase for phrase in required if phrase not in combined] == []


def test_empty_state_copy_is_consistent() -> None:
    combined = _visible_literals()
    required = [
        "No saved documentation artifacts yet.",
        "No reference records found.",
        "No saved design records yet.",
        "Enter a sequence to generate a preview.",
    ]
    disallowed = [
        "No validation results",
        "No experiment results",
        "No validated parts",
        "No successful designs",
        "No ready projects",
    ]
    assert [phrase for phrase in required if phrase not in combined] == []
    assert [phrase for phrase in disallowed if phrase in combined] == []


def test_import_export_safety_copy_and_controls_remain_preview_only() -> None:
    combined = _visible_literals()
    required = [
        "read-only preview",
        "no database writes",
        "does not import or modify any project",
        "import as new project only",
    ]
    disallowed_controls = [
        "Import Project",
        "Execute Import",
        "Confirm Import",
        "Merge Project",
        "Overwrite Project",
    ]
    assert [phrase for phrase in required if phrase not in combined] == []
    assert [phrase for phrase in disallowed_controls if phrase in combined] == []
