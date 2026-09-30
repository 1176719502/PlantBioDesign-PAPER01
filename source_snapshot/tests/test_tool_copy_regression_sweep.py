from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "app.py",
    ROOT / "views",
    ROOT / "components",
    ROOT / "services" / "lab_tools_service.py",
    ROOT / "services" / "protein_structure_analysis_service.py",
    ROOT / "services" / "tool_artifact_service.py",
]

# Route keys and compatibility aliases may still use legacy identifiers internally.
# These tests focus on user-visible copy, so internal route keys are allowed when
# they map to normalized labels before rendering.
_ALLOWED_INTERNAL_ROUTE_LABELS = {
    "Assembly & Cloning",
}


def _python_files() -> list[Path]:
    files: list[Path] = []
    for target in TARGETS:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(path for path in target.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _combined_source() -> str:
    return "\n".join(_read(path) for path in _python_files())


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


def _combined_literals() -> str:
    return "\n".join(value for path in _python_files() for value in _literal_values(path))


def _visible_literals() -> list[str]:
    return [
        value
        for path in _python_files()
        for value in _literal_values(path)
        if value.strip() not in _ALLOWED_INTERNAL_ROUTE_LABELS
    ]


def _offenders(haystack: str, phrases: list[str]) -> list[str]:
    lower = haystack.lower()
    return [phrase for phrase in phrases if phrase.lower() in lower]


def test_tool_user_visible_copy_has_no_legacy_ampersand_labels() -> None:
    combined = _combined_source()
    disallowed = [
        "Test & Validation",
        "Test & Review",
        "Import & Export",
        "Tools & Analysis",
    ]

    assert _offenders(combined, disallowed) == []
    assert "Assembly & Cloning ·" not in combined
    assert "Assembly & Cloning</" not in combined
    assert "Assembly & Cloning" not in "\n".join(_visible_literals())


def test_old_lab_tools_copy_does_not_return() -> None:
    disallowed = [
        "Construct Design Validation",
        "Automated quality assessment",
        "Fragment validation: Pass",
        "Cloning preview completed",
        "PCR success",
        "successful cloning",
        "successful PCR",
        "successful expression",
    ]

    assert _offenders("\n".join(_visible_literals()), disallowed) == []


def test_required_lab_tools_review_framing_is_present() -> None:
    combined = _combined_source()

    required = [
        "Assembly and Cloning",
        "Review Checks",
        "Construct review summary",
        "Rule-based documentation review",
        "Preview summary",
        "Preview generated",
        "Documentation Artifacts",
    ]
    missing = [phrase for phrase in required if phrase not in combined]

    assert missing == []
    assert ("Rule check passed" in combined) or ("Review check passed" in combined)


def test_codon_usage_preview_safety_framing_is_present_without_positive_optimization_claims() -> None:
    combined = _combined_source()

    required = [
        "Codon Usage Preview",
        "does not predict expression",
        "does not optimize yield",
    ]
    disallowed = [
        "optimized construct",
        "optimized sequence",
        "expression optimized",
        "yield optimized",
    ]

    assert [phrase for phrase in required if phrase not in combined] == []
    assert "codon usage preview" in combined.lower()
    visible_literals = "\n".join(_visible_literals())
    for allowed_boundary in [
        "not a generated optimized sequence",
        "no generated optimized sequence",
    ]:
        visible_literals = visible_literals.replace(
            allowed_boundary,
            "not a generated recoding output",
        )
    assert _offenders(visible_literals, disallowed) == []


def test_structure_analysis_boundary_copy_stays_review_only() -> None:
    combined = _combined_source()

    required = [
        "Documentation-only inspection and structure review helper",
        "local documentation review context",
        "computational previews",
        "documentation artifacts",
        "does not validate folding",
        "function",
        "expression",
        "experimental readiness",
        "not validation",
        "not prediction",
        "not recommendation",
        "not readiness approval",
        "not wet-lab protocol",
    ]

    assert [phrase for phrase in required if phrase not in combined] == []


def test_tool_artifact_copy_uses_documentation_artifact_language_only() -> None:
    combined = _combined_source()
    required = [
        "Cloning preview records",
        "Save current cloning preview record",
        "Documentation Artifacts",
        "This removes the saved documentation artifact only.",
        "documentation-only",
        "documentation records",
        "review records",
        "not experimental conclusions",
        "not yield prediction",
        "not pathway optimization",
        "not wet-lab protocols",
    ]
    disallowed = [
        "Save Result",
        "Save Validation",
        "Save Experiment",
        "Save Protocol",
    ]

    assert [phrase for phrase in required if phrase not in combined] == []
    assert _offenders(combined, disallowed) == []
    assert "Save Documentation Artifact" not in _read(ROOT / "views" / "LabTools.py")
    assert "文档伪影" not in _read(ROOT / "views" / "LabTools.py")


def test_lab_tools_dormant_boundary_copy_stays_frozen_preview_only() -> None:
    combined = _combined_source()
    required = [
        "Lab Tools is a dormant / V1 frozen / documentation artifact preview surface.",
        "not the current mainline tool path",
        "not a wet-lab execution workflow",
        "Artifact saved as a documentation artifact.",
        "can be reviewed in linked project context",
        "visible from Pathway Workspace linked documentation artifacts",
        "not validation",
        "not prediction",
        "not recommendation",
        "not readiness approval",
        "not wet-lab protocol",
    ]

    assert [phrase for phrase in required if phrase not in combined] == []


def test_positive_readiness_validation_yield_protocol_claims_do_not_return() -> None:
    combined = _combined_source()
    allowed_negative_boundary = "Do not treat the package as experiment-ready or production-ready."
    visible_literals = "\n".join(_visible_literals()).replace(allowed_negative_boundary, "")
    disallowed = [
        "experiment-ready certification",
        "experiment-ready certificate",
        "experiment-ready output",
        "production-ready",
        "validated pathway",
        "validated construct",
        "validated cloning",
        "validated PCR",
        "validated expression",
        "yield prediction result",
        "optimized pathway",
        "wet-lab protocol provided",
        "protocol generated",
    ]

    assert _offenders(visible_literals, disallowed) == []


def test_warning_and_suggestion_copy_uses_review_framing() -> None:
    combined = _combined_source()
    encouraged = [
        "Review note",
        "Rule check note",
        "Suggested review",
        "Flagged for review",
        "No flagged issue",
    ]
    disallowed = [
        "experimental failure",
        "experiment failed",
        "biological failure",
        "guaranteed success",
        "guaranteed amplification",
    ]

    assert any(phrase in combined for phrase in encouraged)
    assert _offenders(combined, disallowed) == []


def test_import_export_boundary_negations_are_allowed_copy() -> None:
    combined = _combined_source()

    allowed_boundary_copy = [
        "does not import or modify any project",
        "does not certify experimental readiness",
    ]

    for phrase in allowed_boundary_copy:
        assert re.search(re.escape(phrase), combined, flags=re.IGNORECASE)

    # These import/export boundary terms should not be treated as positive claims
    # if they are added to user-visible safety copy in the future.
    assert _offenders("no overwrite\nno merge", ["validated import", "protocol generated"]) == []
