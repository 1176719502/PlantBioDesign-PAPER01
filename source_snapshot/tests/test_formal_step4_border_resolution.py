from __future__ import annotations

import ast
from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _step4_source() -> str:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_render_step_4_backbone"
    )
    return ast.get_source_segment(source, function) or ""


def test_formal_step4_removes_generic_manual_border_resolution_helper() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step4 = _step4_source()

    assert "def _resolve_step4_border_confirmations" not in source
    assert "formal_step4_border_method" not in step4
    assert "formal_step4_border_direction_note" not in step4


def test_formal_step4_has_no_arbitrary_coordinate_widgets() -> None:
    source = _step4_source()

    assert "number_input" not in source
    assert '"手动坐标"' not in source
    assert '"操作起始坐标（1-based）"' not in source
    assert '"操作结束坐标（1-based）"' not in source


def test_formal_step4_uses_classification_and_contract_validation() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    assert "classify_vector_asset(backbone)" in source
    assert "validate_t_dna_operation(" in source
    assert "v1.expression.asset_type_full_binary_vector_bp_circular" in source
    assert "v1.expression.full_binary_vector_summary" in source
