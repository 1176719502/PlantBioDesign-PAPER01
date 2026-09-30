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
TYPOGRAPHY_HELPER = ROOT / "views" / "tool_typography.py"
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


def test_target_tool_pages_keep_input_output_next_step_copy() -> None:
    for page in TOOL_PAGE_FILES:
        copy = _page_copy(page).lower()
        assert "input:" in copy, page
        assert "output:" in copy, page
        assert "next step:" in copy, page


def test_target_tool_pages_keep_documentation_or_preview_boundary() -> None:
    for page in TOOL_PAGE_FILES:
        copy = _page_copy(page).lower()
        assert "does not certify experimental readiness" in copy, page
        assert "documentation-only" in copy or "computational preview" in copy, page


def test_target_tool_pages_use_shared_typography_surface_helpers() -> None:
    helper_source = _read(TYPOGRAPHY_HELPER)
    required_helpers = [
        "render_tool_header",
        "render_tool_intro",
        "render_boundary_note",
        "render_help_text",
        "render_section_heading",
        "render_subsection_heading",
        "render_compact_summary_cards",
    ]
    assert [name for name in required_helpers if name not in helper_source] == []

    for page, path in TOOL_PAGE_FILES.items():
        source = _read(path)
        if page == "Codon Usage Preview":
            assert "st.metric" not in source, page
            assert "inject_tool_typography_css" not in source, page
            continue
        assert "inject_tool_typography_css" in source, page
        assert "render_tool_intro" in source, page
        assert "render_boundary_note" in source, page


def test_lab_tools_construct_review_summary_uses_compact_cards_not_st_metric() -> None:
    source = _read(TOOL_PAGE_FILES["Lab Tools"])
    validation_section = source.split("def _render_validation", 1)[1].split("# ===========================================================================\n# Documentation artifact helpers", 1)[0]
    assert "render_compact_summary_cards" in validation_section
    assert ".metric(" not in validation_section


def test_shared_typography_helper_defines_compact_visual_hierarchy_classes() -> None:
    source = _read(TYPOGRAPHY_HELPER)
    required_classes = [
        "tool-title",
        "tool-subtitle",
        "tool-intro-card",
        "tool-boundary-note",
        "tool-help-text",
        "tool-section-heading",
        "tool-subsection-heading",
        "tool-summary-card",
    ]
    assert [klass for klass in required_classes if klass not in source] == []
