from __future__ import annotations

import ast
from pathlib import Path


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


def _step3_source() -> str:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "_render_step_3_elements"
    )
    return ast.get_source_segment(source, node) or ""


def test_step3_low_frequency_sections_are_default_collapsed_with_counts() -> None:
    step3 = _step3_source()

    assert "st.expander" in step3
    assert "optional_selected_count" in step3
    assert "blocking_count" in step3
    assert "manual_confirmation_count" in step3
    assert "warning_count" in step3
    assert step3.count("expanded=False") >= 3


def test_step3_disclosure_keeps_existing_controls_tables_and_state_contracts() -> None:
    step3 = _step3_source()

    for token in (
        '"formal_step3_order_confirmed"',
        "biological_role_field = _t('v1.expression.biological_role_label')",
        '"source_reference"',
        "_invalidate_formal_snapshots",
        "assess_expression_cassette",
        "generate_expression_cassette",
    ):
        assert token in step3


def test_step3_generation_stays_on_step_and_only_bottom_next_is_rendered() -> None:
    step3 = _step3_source()

    assert "_t('v1.expression.generate_expression_cassette_continue')" in step3
    assert "\u751f\u6210\u8868\u8fbe\u76d2\u5e76\u7ee7\u7eed" not in step3
    assert "step3_can_continue_to_backbone" in step3
    assert "next_enabled=step3_ready_for_backbone" in step3
    assert "next_action=advance_step3" in step3
    assert step3.count("step3_can_continue_to_backbone") >= 2
    assert "show_next=False" not in step3
