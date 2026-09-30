from __future__ import annotations

import ast
import os
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


def _python_files() -> list[Path]:
    files: list[Path] = []
    for target in TARGETS:
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(path for path in target.rglob("*.py") if "__pycache__" not in path.parts)
    return sorted(files)


def _read(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8-sig")


def _string_literals(path: Path) -> list[str]:
    tree = ast.parse(_read(path), filename=str(path))
    values: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            values.append(node.value)
        elif isinstance(node, ast.JoinedStr):
            parts = []
            for value in node.values:
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    parts.append(value.value)
            if parts:
                values.append("".join(parts))
    return values


def test_user_visible_tool_labels_do_not_use_ampersand_symbol() -> None:
    string_nodes = [
        value
        for path in [ROOT / "app.py", ROOT / "views" / "LabTools.py"]
        for value in _string_literals(path)
        if not value.lstrip().startswith("<style>")
    ]

    labels_with_ampersands = [value for value in string_nodes if "&" in value]
    assert labels_with_ampersands == []


def test_lab_tools_copy_uses_review_and_documentation_framing() -> None:
    page = _read(ROOT / "views" / "LabTools.py")
    service = _read(ROOT / "services" / "lab_tools_service.py")
    combined = page + "\n" + service

    assert "Assembly and Cloning" in combined
    assert "Review Checks" in combined
    assert "Construct review summary" in combined
    assert "Rule-based documentation review" in combined
    assert "Preview summary" in combined
    assert "Review notes" in combined
    assert "Documentation artifact" in combined
    assert ("Rule check passed" in combined) or ("Review check passed" in combined)

    assert "Test & Validation" not in combined
    assert "Construct Design Validation" not in combined
    assert "Automated quality assessment" not in combined
    assert "Fragment validation: Pass" not in combined


def test_tool_boundary_copy_exists_for_main_tool_pages() -> None:
    combined = "\n".join(_read(path) for path in [
        ROOT / "views" / "CodonOptimizer.py",
        ROOT / "views" / "LabTools.py",
        ROOT / "views" / "StructureAnalysis.py",
        ROOT / "services" / "lab_tools_service.py",
        ROOT / "services" / "protein_structure_analysis_service.py",
    ])

    assert "computational previews" in combined
    assert "documentation artifacts" in combined
    assert "does not certify experimental readiness" in combined
    assert "predict yield" in combined
    assert "optimize pathways" in combined
    assert "provide wet-lab protocols" in combined


def test_structure_analysis_boundary_copy_is_explicit() -> None:
    combined = _read(ROOT / "views" / "StructureAnalysis.py") + _read(ROOT / "services" / "protein_structure_analysis_service.py")

    assert "does not validate folding" in combined
    assert "function" in combined
    assert "expression" in combined
    assert "experimental readiness" in combined


def test_lab_tools_boundary_copy_is_explicit() -> None:
    combined = _read(ROOT / "views" / "LabTools.py") + _read(ROOT / "services" / "lab_tools_service.py")

    assert "They do not certify cloning" in combined
    assert "PCR" in combined
    assert "gel" in combined
    assert "expression success" in combined
    assert "They do not provide wet-lab protocols" in combined


def test_codon_usage_preview_safety_copy_exists() -> None:
    page = _read(ROOT / "views" / "CodonOptimizer.py")
    app = _read(ROOT / "app.py")
    combined = page + "\n" + app

    assert "Codon Usage Preview" in combined
    assert "codon usage preview" in combined.lower()
    assert "candidate sequence documentation review helper" in combined
    assert "local computational preview" in combined
    assert "documentation-only review context" in combined
    assert "not an expression/yield optimization engine" in combined
    assert "not prediction" in combined
    assert "not recommendation" in combined
    assert "not validation" in combined
    assert "not readiness approval" in combined
    assert "not a wet-lab protocol" in combined
    assert "Review outputs before using them as design support" in combined


def test_documentation_artifact_copy_is_standardized() -> None:
    combined = "\n".join(_read(path) for path in [
        ROOT / "views" / "LabTools.py",
        ROOT / "views" / "StructureAnalysis.py",
    ])

    assert "Cloning preview records" in combined
    assert "Save current cloning preview record" in combined
    assert "Documentation Artifacts" in combined
    for required_phrase in [
        "documentation-only",
        "documentation records",
        "review records",
        "not experimental conclusions",
        "not yield prediction",
        "not pathway optimization",
        "not wet-lab protocols",
    ]:
        assert required_phrase in combined
    assert "This removes the saved documentation record only." in combined
    assert "This removes the saved documentation artifact only." in combined
    assert "Save Documentation Artifact" not in _read(ROOT / "views" / "LabTools.py")
    assert "文档伪影" not in _read(ROOT / "views" / "LabTools.py")


def test_no_disallowed_positive_readiness_yield_or_success_claims() -> None:
    combined = "\n".join(_read(path) for path in _python_files())
    allowed_negative_boundary = "Do not treat the package as experiment-ready or production-ready."
    combined = combined.replace(allowed_negative_boundary, "")
    disallowed = [
        "production-ready",
        "validated pathway",
        "optimized pathway",
        "yield prediction result",
        "successful cloning",
        "successful PCR",
        "successful expression",
    ]

    lower = combined.lower()
    offenders = [phrase for phrase in disallowed if phrase.lower() in lower]
    assert offenders == []


def test_standalone_pass_fail_success_labels_are_not_visible_copy() -> None:
    combined = "\n".join(_read(path) for path in [
        ROOT / "views" / "LabTools.py",
        ROOT / "views" / "CodonOptimizer.py",
    ])

    assert re.search(r'["\']Pass["\']', combined) is None
    assert re.search(r'["\']Fail["\']', combined) is None
    assert re.search(r'["\']Success["\']', combined) is None
    assert "Optimization Status" not in combined
