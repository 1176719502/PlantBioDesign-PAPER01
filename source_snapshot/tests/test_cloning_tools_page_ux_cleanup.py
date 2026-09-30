from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAB_TOOLS_PAGE = ROOT / "views" / "LabTools.py"

FORBIDDEN_COPY = [
    "successful import",
    "project imported",
    "ready for execution",
    "experiment-ready",
    "production-ready",
    "validated construct",
    "optimized pathway",
    "yield prediction",
    "lab-ready",
    "wet-lab ready",
    "proven construct",
    "validated pathway",
]


def _read_page() -> str:
    return LAB_TOOLS_PAGE.read_text(encoding="utf-8-sig")


def _string_literals() -> list[str]:
    tree = ast.parse(_read_page(), filename=str(LAB_TOOLS_PAGE))
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


def test_cloning_tools_page_uses_documentation_record_copy() -> None:
    page = _read_page()

    assert "文档伪影" not in page
    assert "Documentation record / cloning preview record" in page
    assert "Cloning preview records" in page
    assert "保存当前克隆预览记录" in page
    assert "Save current cloning preview record" in page


def test_cloning_tools_page_keeps_documentation_only_boundary() -> None:
    visible_copy = "\n".join(_string_literals())

    required = [
        "documentation-only",
        "not experimental conclusions",
        "not claims of experimental readiness",
        "not a production readiness claim",
        "not yield prediction",
        "not pathway optimization",
        "not wet-lab protocols",
    ]
    assert [phrase for phrase in required if phrase not in visible_copy] == []


def test_cloning_tools_page_forbidden_copy_is_absent() -> None:
    visible_copy = "\n".join(_string_literals()).lower()
    visible_copy = visible_copy.replace("not yield prediction", "")

    assert [phrase for phrase in FORBIDDEN_COPY if phrase in visible_copy] == []


def test_cloning_tools_page_has_one_clear_primary_save_button() -> None:
    page = _read_page()

    assert page.count("CLONING_RECORD_PRIMARY_BUTTON") >= 2
    assert page.count("key='save_current_cloning_preview_record'") == 1
    assert "Save Documentation Artifact" not in page
    assert "save_pcr_documentation_artifact" not in page
    assert "save_gel_documentation_artifact" not in page
    assert "save_export_documentation_artifact" not in page


def test_cloning_tools_raw_record_table_is_advanced_and_friendly() -> None:
    page = _read_page()

    assert "Advanced: view raw documentation record table" in page
    assert "expanded=False" in page
    assert "'Record type'" in page
    assert "'Source module'" in page
    assert "'Created time'" in page
    assert "'Boundary note'" in page
    assert "filter_col1.selectbox('Record type'" in page
    assert "filter_col2.selectbox('Source module'" in page
    assert "st.dataframe" in page
