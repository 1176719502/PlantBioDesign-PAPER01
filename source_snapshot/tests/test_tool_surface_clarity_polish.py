from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TOOL_PAGE_FILES = {
    "Parts Registry": ROOT / "views" / "Data.py",
    "Sequence Tools": ROOT / "views" / "SequenceTools.py",
    "Codon Usage Preview": ROOT / "views" / "CodonOptimizer.py",
    "Structure Analysis": ROOT / "views" / "StructureAnalysis.py",
    "Lab Tools": ROOT / "views" / "LabTools.py",
}

EXTRA_COPY_FILES = [ROOT / "locales" / "en.py"]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _string_literals(path: Path) -> str:
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
    return "\n".join(values)


def _page_copy(page: str) -> str:
    paths = [TOOL_PAGE_FILES[page], *EXTRA_COPY_FILES]
    return "\n".join(_string_literals(path) for path in paths if path.exists())


def test_each_target_tool_page_explains_input_output_and_next_step() -> None:
    for page in TOOL_PAGE_FILES:
        copy = _page_copy(page).lower()
        assert "input:" in copy, page
        assert "output:" in copy, page
        assert "next step:" in copy, page


def test_each_target_tool_page_keeps_preview_or_documentation_boundary() -> None:
    for page in TOOL_PAGE_FILES:
        copy = _page_copy(page).lower()
        assert "does not certify experimental readiness" in copy, page
        assert "does not predict yield" in copy, page
        assert "does not optimize pathways" in copy or "not expression optimization" in copy, page
        assert "does not provide wet-lab protocols" in copy or "not a wet-lab protocol" in copy, page
        assert "documentation-only" in copy or "computational preview" in copy, page


def test_disabled_button_copy_explains_why_controls_are_unavailable() -> None:
    sequence_copy = _page_copy("Sequence Tools")
    assert "Use in Wizard is unavailable until the current input has been analyzed" in sequence_copy

    codon_copy = _page_copy("Codon Usage Preview")
    assert "Paste a DNA coding sequence of at least 30 bp before generating a computational preview." in codon_copy

    structure_copy = _page_copy("Structure Analysis")
    assert "Enter a protein sequence or select a valid PDB source before saving a documentation-only artifact." in structure_copy

    lab_copy = _page_copy("Lab Tools")
    assert "requires a current cloning preview with usable input" in lab_copy.lower()
    assert "save_pcr_documentation_artifact" not in lab_copy
    assert "save_gel_documentation_artifact" not in lab_copy
    assert "save_export_documentation_artifact" not in lab_copy

    registry_copy = _page_copy("Parts Registry")
    assert "Only promoter, RBS/Kozak, and terminator parts can be sent to Wizard Step 2." in registry_copy


def test_empty_states_tell_user_what_to_do_next() -> None:
    required_by_page = {
        "Parts Registry": "Adjust the search/filter controls, switch tabs, or add a reference record",
        "Sequence Tools": "Use <strong>Generate Preview</strong> to submit your DNA sequence",
        "Codon Usage Preview": "Enter a DNA coding sequence of at least 30 bp to generate a computational preview.",
        "Structure Analysis": "Save a Documentation Artifact after entering a protein sequence or selecting a PDB source",
        "Lab Tools": "Generate or review a cloning preview, then use Save current cloning preview record",
    }
    for page, required in required_by_page.items():
        assert required in _page_copy(page), page


def test_target_tool_clarity_copy_avoids_positive_readiness_claims() -> None:
    combined = "\n".join(_page_copy(page) for page in TOOL_PAGE_FILES).lower()
    disallowed_positive_claims = [
        "certifies experimental readiness",
        "predicts yield",
        "provides wet-lab protocols",
        "expression optimization result",
        "validated construct",
        "validated expression",
        "successful expression",
        "ready for experiments",
    ]
    assert [phrase for phrase in disallowed_positive_claims if phrase in combined] == []
