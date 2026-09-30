from __future__ import annotations

import ast
from pathlib import Path


APP_SOURCE = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")


def _function(name: str):
    tree = ast.parse(APP_SOURCE)
    function = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    )
    namespace: dict[str, object] = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace[name]


def test_plant_library_header_and_records_share_the_five_column_grid() -> None:
    columns = "minmax(180px,2fr) 100px 90px minmax(150px,1.2fr) 180px"

    assert f".library-head {{ display:grid; grid-template-columns:{columns}" in APP_SOURCE
    assert (
        f'[class*="st-key-formal_library_row_"] [data-testid="stHorizontalBlock"] '
        f'{{ display:grid !important; grid-template-columns:{columns} !important' in APP_SOURCE
    )
    assert 'with st.container(key=f"formal_library_row_{record_key}", border=False):' in APP_SOURCE
    assert "name_col, type_col, length_col, accession_col, action_col = st.columns(" in APP_SOURCE
    assert '[class*="st-key-formal_library_row_"] { min-height:56px;' in APP_SOURCE


def test_plant_library_uses_stable_catalog_keys_and_fixed_detail_container() -> None:
    assert 'for record in page_records:' in APP_SOURCE
    assert 'record_key = str(record["catalog_record_id"])' in APP_SOURCE
    assert "enumerate(page_records)" not in APP_SOURCE
    assert 'key=f"formal_library_detail_{record_key}"' in APP_SOURCE
    assert 'key=f"formal_library_use_{record_key}"' in APP_SOURCE
    assert 'with st.container(key="formal_library_selected_detail", border=False):' in APP_SOURCE
    assert "st.popover(" not in APP_SOURCE
    assert "st.expander(" in APP_SOURCE  # The unrelated development resources remain collapsed.


def test_plant_library_pagination_clamps_before_slicing_across_page_sizes() -> None:
    window = _function("_formal_library_page_window")

    assert window(13, 10, 1) == (1, 2, 0, 10)
    assert window(13, 50, 2) == (1, 1, 0, 13)
    assert window(13, 10, 99) == (2, 2, 10, 13)
    assert "[10, 20, 50]," in APP_SOURCE
    assert 'key="formal_library_page_size"' in APP_SOURCE
    assert "page_records = filtered[start:end]" in APP_SOURCE
    assert APP_SOURCE.index('st.session_state["formal_library_page"] = page') < APP_SOURCE.index(
        "page_records = filtered[start:end]"
    )


def test_plant_library_filters_reset_page_and_clear_hidden_detail_selection() -> None:
    selected_record_id = _function("_formal_library_selected_record_id")
    records = [{"registry_component_id": "PCRV1-001"}, {"registry_component_id": "PCRV1-002"}]

    assert selected_record_id(records, "PCRV1-002") == "PCRV1-002"
    assert selected_record_id(records, "PCRV1-003") is None
    assert selected_record_id([], "PCRV1-001") is None
    assert selected_record_id(records, None) is None
    assert APP_SOURCE.count("on_change=_reset_formal_library_page") >= 4
    assert "on_change=_change_formal_library_type_filter" in APP_SOURCE
    assert 'st.session_state.pop("formal_library_selected_registry_id", None)' in APP_SOURCE


def test_plant_library_type_filter_uses_a_stable_horizontal_radio() -> None:
    type_filter_value = _function("_formal_library_type_filter_value")

    assert type_filter_value(None) == "all"
    assert type_filter_value("全部") == "all"
    assert type_filter_value("CDS") == "cds"
    assert type_filter_value("unexpected") == "all"
    assert "st.segmented_control(\n        \"元件类型\"" not in APP_SOURCE
    assert "type_filter = st.radio(" in APP_SOURCE
    assert 'key="formal_library_type_radio_v2"' in APP_SOURCE
    assert "horizontal=True" in APP_SOURCE
    assert "on_change=_change_formal_library_type_filter" in APP_SOURCE
    assert 'row.get("component_type") != type_filter' in APP_SOURCE


def test_plant_library_type_filter_changes_reset_page_and_clear_detail_only_when_changed() -> None:
    callback_source = APP_SOURCE[
        APP_SOURCE.index("def _change_formal_library_type_filter") : APP_SOURCE.index(
            "def _render_plant_component_library"
        )
    ]

    assert 'st.session_state.get("formal_library_type_radio_v2")' in callback_source
    assert 'st.session_state.get("formal_library_type_filter")' in callback_source
    assert "if selected_type != current_type:" in callback_source
    assert 'st.session_state["formal_library_type_filter"] = selected_type' in callback_source
    assert "_reset_formal_library_page()" in callback_source
    assert 'st.session_state["formal_library_type_radio_v2"]' not in callback_source


def test_plant_library_detail_requires_a_known_nonempty_registry_id() -> None:
    assert "records_by_registry_id =" in APP_SOURCE
    assert "if selected_registry_id and selected_registry_id in records_by_registry_id:" in APP_SOURCE
    assert "selected_record = records_by_registry_id[selected_registry_id]" in APP_SOURCE


def test_plant_library_close_detail_clears_the_selected_registry_id() -> None:
    assert "v1.component_library.collapse_details" in APP_SOURCE
    assert 'key="formal_library_close_detail"' in APP_SOURCE
    assert "on_click=_clear_formal_library_selected_record" in APP_SOURCE
    assert 'def _clear_formal_library_selected_record() -> None:' in APP_SOURCE
    assert 'st.session_state.pop("formal_library_selected_registry_id", None)' in APP_SOURCE


def test_plant_library_close_detail_does_not_reset_filter_or_pagination_state() -> None:
    clear_function = APP_SOURCE[
        APP_SOURCE.index("def _clear_formal_library_selected_record") : APP_SOURCE.index(
            "def _formal_library_page_window"
        )
    ]

    assert "formal_library_page" not in clear_function
    assert "formal_library_search" not in clear_function
    assert "formal_library_host" not in clear_function
    assert "formal_library_workflow" not in clear_function
    assert "formal_library_type" not in clear_function


def test_plant_library_filtered_detail_selection_remains_safe_to_clear() -> None:
    selected_record_id = _function("_formal_library_selected_record_id")
    visible_records = [{"registry_component_id": "PCRV1-001"}]

    assert selected_record_id(visible_records, "PCRV1-002") is None
    assert "if selected_registry_id and selected_registry_id in records_by_registry_id:" in APP_SOURCE


def test_plant_library_keeps_bound_actions_and_registry_display_fields() -> None:
    assert 'if ui_state["formal_selectable"]' in APP_SOURCE
    assert 'if ui_state["state_key"] == "catalog_candidate"' in APP_SOURCE
    assert "v1.component_library.browse_only" in APP_SOURCE
    assert 'disabled=not ui_state["formal_selectable"]' in APP_SOURCE
    assert 'disabled=record.get("formal_selectable") is False' not in APP_SOURCE
    assert "_use_plant_library_record(record)" in APP_SOURCE
    assert "records = _formal_library_display_records(_plant_library_records())" in APP_SOURCE
    assert "registry_component_id" in APP_SOURCE
    assert "library-accession" in APP_SOURCE
