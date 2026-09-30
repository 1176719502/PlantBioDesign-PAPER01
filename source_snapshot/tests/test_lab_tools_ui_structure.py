from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAB_TOOL_FILES = [
    ROOT / "views" / "LabTools.py",
    ROOT / "components" / "assembly_modules" / "tab_cloning.py",
    ROOT / "components" / "assembly_modules" / "tab_pcr.py",
    ROOT / "components" / "assembly_modules" / "tab_gel.py",
    ROOT / "components" / "assembly_modules" / "tab_export.py",
    ROOT / "services" / "lab_tools_service.py",
    ROOT / "services" / "tool_artifact_service.py",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _combined_lab_tools_source() -> str:
    return "\n".join(_read(path) for path in LAB_TOOL_FILES if path.exists())


def test_lab_tools_boundary_copy_exists() -> None:
    combined = _combined_lab_tools_source()

    required = [
        "computational previews",
        "documentation artifacts",
        "does not certify experimental readiness",
        "does not predict yield",
        "does not optimize pathways",
        "does not provide wet-lab protocols",
        "does not certify cloning, PCR, gel, or expression success",
    ]

    missing = [phrase for phrase in required if phrase not in combined]
    assert missing == []


def test_lab_tools_result_section_labels_exist() -> None:
    combined = _combined_lab_tools_source()

    required = [
        "Preview summary",
        "Review notes",
        "Documentation artifact",
        "Construct review summary",
        "Rule-based documentation review",
        "Primer review notes",
        "Fragment review notes",
        "Export review notes",
    ]

    missing = [phrase for phrase in required if phrase not in combined]
    assert missing == []


def test_old_unsafe_lab_tools_wording_absent() -> None:
    combined = _combined_lab_tools_source()
    disallowed = [
        "Test & Validation",
        "Automated quality assessment",
        "Construct Design Validation",
        "Validation passed",
        "Cloning success",
        "PCR success",
        "experiment-ready",
        "wet-lab protocol generated",
        "Save Validation",
        "Save Protocol",
    ]

    offenders = [phrase for phrase in disallowed if phrase.lower() in combined.lower()]
    assert offenders == []


def test_lab_tools_artifact_copy_consistency() -> None:
    combined = _combined_lab_tools_source()

    required = [
        "Cloning preview records",
        "Save current cloning preview record",
        "保存当前克隆预览记录",
        "Saved documentation records are documentation-only review records.",
        "This removes the saved documentation record only.",
        "Advanced: view raw documentation record table",
    ]

    missing = [phrase for phrase in required if phrase not in combined]
    assert missing == []
    assert "Save Documentation Artifact" not in combined
    assert "文档伪影" not in combined


def test_lab_tools_empty_states_are_safe() -> None:
    combined = _combined_lab_tools_source()

    assert "No saved documentation artifacts yet." in combined
    assert "Generate or review a cloning preview, then use Save current cloning preview record" in combined
    assert "No validation results" not in combined
    assert "No experiment results" not in combined
