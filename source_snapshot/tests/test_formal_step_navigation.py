from __future__ import annotations

import ast
from collections.abc import Mapping
from html import escape
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


class _Streamlit:
    def __init__(self, state: dict[str, Any]) -> None:
        self.session_state = state

    def title(self, _value: str) -> None:
        pass

    def caption(self, _value: str) -> None:
        pass

    def info(self, _value: str) -> None:
        pass

    def container(self, **_kwargs: Any):
        class _Container:
            def __enter__(self):
                return self

            def __exit__(self, *_args: Any) -> bool:
                return False

        return _Container()

    def columns(self, spec: list[float]) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                button=lambda _label, **_kwargs: False,
                caption=lambda _value: None,
            )
            for _item in spec
        ]


class _ActionColumn:
    def __init__(self, streamlit: "_ActionStreamlit") -> None:
        self._streamlit = streamlit

    def button(self, label: str, **kwargs: Any) -> bool:
        self._streamlit.button_calls.append({"label": label, **kwargs})
        return kwargs.get("key") == self._streamlit.clicked_key


class _ActionStreamlit:
    def __init__(self, clicked_key: str | None = None) -> None:
        self.session_state: dict[str, Any] = {}
        self.clicked_key = clicked_key
        self.button_calls: list[dict[str, Any]] = []

    def container(self, **_kwargs: Any):
        class _Container:
            def __enter__(self):
                return self

            def __exit__(self, *_args: Any) -> bool:
                return False

        return _Container()

    def columns(self, _spec: list[int]) -> list[_ActionColumn]:
        return [_ActionColumn(self) for _ in range(3)]

    def caption(self, _value: str) -> None:
        pass

    def error(self, _value: str) -> None:
        pass

    def success(self, _value: str) -> None:
        pass


class _StepStripColumn:
    def __enter__(self) -> "_StepStripColumn":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False


class _StepStripStreamlit:
    def __init__(self, clicked_key: str | None = None) -> None:
        self.clicked_key = clicked_key
        self.button_calls: list[dict[str, Any]] = []

    def container(self, **_kwargs: Any) -> _StepStripColumn:
        return _StepStripColumn()

    def columns(self, count: int) -> list[_StepStripColumn]:
        return [_StepStripColumn() for _ in range(count)]

    def button(self, label: str, **kwargs: Any) -> bool:
        self.button_calls.append({"label": label, **kwargs})
        return bool(
            kwargs.get("key") == self.clicked_key
            and not kwargs.get("disabled", False)
        )

    def markdown(self, _value: str, **_kwargs: Any) -> None:
        pass


def _function(name: str, *, state: dict[str, Any]) -> Any:
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    function_names = {name}
    if name == "_formal_step_statuses":
        function_names.add("_formal_step4_strategy_signature")
    nodes = [
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name in function_names
    ]
    namespace = {
        "st": _Streamlit(state),
        "_t": lambda key, **kwargs: key,
        "_ui": lambda value: value,
        "_t": lambda key, **kwargs: key,
        "_ui": lambda value: value,
        "_t": lambda key, **kwargs: key,
        "_ui": lambda value: value,
        "Any": Any,
        "Mapping": Mapping,
        "PROJECT_TYPE_SINGLE_GENE": "single_gene",
        "PROJECT_TYPE_DUAL_TU": "multi_tu",
        "_host_supports_project_type": lambda host, _project_type: bool(host),
        "_formal_project_type": lambda: state.get("formal_project_type", "single_gene"),
        "_is_generic_multi_tu_workflow": lambda: (
            state.get("formal_project_type") == "multi_tu"
            and not state.get("formal_betalain_gate3_case")
        ),
        "_is_multi_tu_expression_assembly": lambda result: (
            isinstance(result, dict)
            and result.get("result_kind") == "MULTI_TU_EXPRESSION_ASSEMBLY"
        ),
        "_is_pathway_multi_tu_project": lambda: bool(state.get("formal_betalain_gate3_case")),
        "_formal_ui_signature": lambda value: json.dumps(value, sort_keys=True, default=str),
        "_t": lambda key, **kwargs: key,
        "_ui": lambda value: value,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace[name]


def _navigation_functions(
    statuses: list[dict[str, bool]],
    *,
    initial_step: int,
) -> tuple[dict[str, Any], SimpleNamespace, dict[str, Any], list[int], list[bool]]:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {
        "_set_formal_step",
        "_normalize_formal_current_step",
        "_formal_step_contract",
    }
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    state: dict[str, Any] = {}
    design_session = SimpleNamespace(step=initial_step)
    saves: list[int] = []
    reruns: list[bool] = []
    controller = SimpleNamespace(
        get=lambda: design_session,
        save=lambda session: saves.append(session.step),
    )
    streamlit = _Streamlit(state)
    streamlit.rerun = lambda: reruns.append(True)
    namespace: dict[str, Any] = {
        "Any": Any,
        "st": streamlit,
        "_t": lambda key, **kwargs: {"v1.expression.return_project_home": "返回项目首页", "v1.common.save_project": "保存项目", "v1.common.save_draft": "保存草稿", "v1.common.next": "下一步", "v1.common.project_saved_can_reopened_project_center": "项目已保存，可从项目中心重新打开。", "v1.common.project_draft_saved_can_reopened_project_center": "项目草稿已保存，可从项目中心重新打开。", "v1.expression.unsaved_changes_session_only_save_draft": "当前更改仅保留在本次会话中；如需稍后继续，请保存草稿。"}.get(key, key),
        "_t": lambda key, **kwargs: key,
        "_controller": lambda: controller,
        "_formal_step_statuses": lambda: statuses,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace, design_session, state, saves, reruns


def test_step_statuses_use_saved_outputs_instead_of_current_step() -> None:
    result = {
        "project_id": "saved-project",
        "input_signature": "construct",
        "runtime": {"sequence_length": 100},
    }
    state = {
        "formal_project_definition": {"project_name": "P", "plant_host": "Rice"},
        "formal_cds_input": {"normalized_cds": "ATG"},
        "formal_cassette_result": {"runtime": {"sequence_length": 10}, "input_signature": "cassette"},
        "formal_cassette_input_signature": "cassette",
        "formal_step3_order_confirmation_recorded": True,
        "formal_backbone_record": {"normalized_sequence": "AAAA"},
        "formal_insertion_settings": {
            "t_dna_confirmation": {"region": {}},
            "t_dna_operation_validation": {"allowed": True},
        },
        "mvp_vector_result": result,
        "mvp_current_input_signature": "construct",
        "formal_project_type": "single_gene",
        "mvp_inputs_stale": False,
        "formal_last_saved_mvp_project_id": "saved-project",
    }
    statuses = _function("_formal_step_statuses", state=state)()

    assert [item["done"] for item in statuses] == [True, True, True, True, True, True]


def test_step_statuses_preserve_upstream_results_when_construct_is_stale() -> None:
    state = {
        "formal_project_definition": {"project_name": "P", "plant_host": "Rice"},
        "formal_cds_input": {"normalized_cds": "ATG"},
        "formal_cassette_result": {"runtime": {"sequence_length": 10}, "input_signature": "cassette"},
        "formal_cassette_input_signature": "cassette",
        "formal_step3_order_confirmation_recorded": True,
        "mvp_vector_result": {"input_signature": "old", "runtime": {"sequence_length": 100}},
        "mvp_current_input_signature": "new",
        "formal_project_type": "single_gene",
        "mvp_inputs_stale": True,
    }
    statuses = _function("_formal_step_statuses", state=state)()

    assert statuses[1]["done"] is True
    assert statuses[2]["done"] is True
    assert statuses[4]["done"] is False
    assert statuses[4]["review"] is True


def test_step3_manual_confirmations_do_not_block_cold_reopen_continuation() -> None:
    state = {
        "formal_project_definition": {"project_name": "P", "plant_host": "Rice"},
        "formal_cds_input": {"normalized_cds": "ATG"},
        "formal_cassette_result": {
            "runtime": {"sequence_length": 10},
            "input_signature": "saved-step3-input",
        },
        "formal_cassette_input_signature": "saved-step3-input",
        "formal_expression_cassette": {
            "findings": [
                {"status": "需要人工确认", "rule_id": "source-review-1"},
                {"status": "需要人工确认", "rule_id": "source-review-2"},
            ],
            "manual_confirmation_items": [
                {"status": "需要人工确认", "rule_id": "source-review-1"},
                {"status": "需要人工确认", "rule_id": "source-review-2"},
            ],
        },
        "formal_step3_order_confirmation_recorded": True,
        "formal_project_type": "single_gene",
    }

    statuses = _function("_formal_step_statuses", state=state)()

    assert statuses[2] == {"done": True, "review": False}


def _fixed_exact_insertion_step4_state() -> dict[str, Any]:
    insertion = {
        "mode": "insertion",
        "start_coordinate": 27,
        "end_coordinate": 28,
        "t_dna_operation_validation": {
            "allowed": True,
            "status": "pcambia1300_exact_insertion_applied",
        },
    }
    backbone = {
        "normalized_sequence": "AAAA",
        "normalized_sequence_sha256": "backbone-sha",
    }
    return {
        "formal_project_definition": {"project_name": "P", "plant_host": "Rice"},
        "formal_cds_input": {"normalized_cds": "ATG"},
        "formal_cassette_result": {"runtime": {"sequence_length": 10}, "input_signature": "cassette-1"},
        "formal_cassette_input_signature": "cassette-1",
        "formal_backbone_record": backbone,
        "formal_insertion_settings": insertion,
        "formal_project_type": "single_gene",
    }


def test_fixed_exact_insertion_rejects_obsolete_ui_only_step4_confirmation() -> None:
    state = _fixed_exact_insertion_step4_state()
    insertion = state["formal_insertion_settings"]
    state["formal_ui_step4_confirmation_signature"] = json.dumps(
        {
            "cassette": "cassette-1",
            "backbone": "backbone-sha",
            "insertion": insertion,
        },
        sort_keys=True,
        default=str,
    )

    statuses = _function("_formal_step_statuses", state=state)()

    assert statuses[3]["done"] is False


def test_fixed_exact_insertion_accepts_current_formal_step4_confirmation() -> None:
    state = _fixed_exact_insertion_step4_state()
    current_signature = _function("_formal_step4_strategy_signature", state=state)()
    state.update(
        formal_step4_strategy_confirmed=True,
        formal_step4_strategy_signature=current_signature,
    )

    statuses = _function("_formal_step_statuses", state=state)()

    assert statuses[3]["done"] is True


def test_gate3_loaded_project_keeps_step1_complete_for_shared_navigation_gate() -> None:
    state = {
        "formal_project_type": "multi_tu",
        "formal_betalain_gate3_case": True,
        "formal_project_name": "Loaded Gate 3 design record",
    }

    statuses = _function("_formal_step_statuses", state=state)()

    assert statuses[0]["done"] is True


def test_step_statuses_treat_none_project_definition_as_an_incomplete_new_project() -> None:
    statuses = _function(
        "_formal_step_statuses",
        state={"formal_project_definition": None},
    )()

    assert statuses[0]["done"] is False


def test_step_statuses_treat_a_missing_project_definition_as_an_incomplete_new_project() -> None:
    statuses = _function("_formal_step_statuses", state={})()

    assert statuses[0]["done"] is False


def test_empty_project_statuses_support_workspace_step_normalization() -> None:
    state = {"formal_project_definition": None}
    statuses = _function("_formal_step_statuses", state=state)()

    assert len(statuses) == 6
    assert statuses[0] == {"done": False, "review": False}


def test_new_empty_project_renders_the_workspace_entry_without_status_errors() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    names = {"_formal_step_statuses", "_is_result_preview_mode", "_render_design_workspace"}
    nodes = [
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name in names
    ]
    state: dict[str, Any] = {"formal_project_definition": None}
    design_session = SimpleNamespace(host="Rice", tag="No tag", step=1)
    controller = SimpleNamespace(get=lambda: design_session, save=lambda _ds: None)
    namespace = {
        "st": _Streamlit(state),
        "Any": Any,
        "Mapping": Mapping,
        "PROJECT_TYPE_SINGLE_GENE": "single_gene",
        "PROJECT_TYPE_DUAL_TU": "multi_tu",
        "PAGE_DESIGN_WORKSPACE": "Expression Design",
        "_controller": lambda: controller,
        "_record_current_project_surface": lambda _destination: None,
        "_PLANT_HOSTS": ("Rice",),
        "_formal_project_type": lambda: "single_gene",
        "_is_generic_multi_tu_workflow": lambda: False,
        "_is_multi_tu_expression_assembly": lambda _result: False,
        "_is_pathway_multi_tu_project": lambda: False,
        "_formal_ui_signature": lambda value: json.dumps(value, sort_keys=True, default=str),
        "_render_step_strip": lambda _step: None,
        "_render_formal_action_feedback": lambda _step: None,
        "_render_step_1_project": lambda _ds: None,
        "_render_step_2_cds": lambda _ds: None,
        "_render_step_3_elements": lambda _ds: None,
        "_render_step_4_backbone": lambda _ds: None,
        "_render_step_5_complete": lambda _ds: None,
        "_render_step_6_review": lambda _ds: None,
        "_t": lambda key, **kwargs: key,
        "_ui": lambda value: value,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    namespace["_normalize_formal_current_step"] = lambda step: (
        1 if not namespace["_formal_step_statuses"]()[0]["done"] else step
    )

    namespace["_render_design_workspace"]()


def test_set_formal_step_only_changes_single_design_session_step() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "_set_formal_step")
    called = {item.func.id for item in ast.walk(node) if isinstance(item, ast.Call) and isinstance(item.func, ast.Name)}

    assert "_invalidate_formal_snapshots" not in called
    assert "_invalidate_complete_plasmid_snapshot" not in called
    assert "_set_formal_step" not in called


def test_workspace_normalizes_an_unreachable_current_step_before_rendering() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "_render_design_workspace"
    )
    called = {
        item.func.id
        for item in ast.walk(node)
        if isinstance(item, ast.Call) and isinstance(item.func, ast.Name)
    }

    assert "_normalize_formal_current_step" in called


def test_step_strip_disables_current_and_blocked_steps_but_keeps_completed_steps_clickable() -> None:
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "_render_step_strip"
    )
    contract = [
        {"state": "COMPLETED", "review": False},
        {"state": "COMPLETED", "review": False},
        {"state": "COMPLETED", "review": False},
        {"state": "CURRENT", "review": False},
        {"state": "BLOCKED", "review": False},
        {"state": "BLOCKED", "review": False},
    ]
    streamlit = _StepStripStreamlit(clicked_key="formal_top_step_1")
    targets: list[int] = []
    namespace = {
        "st": streamlit,
        "_t": lambda key, **kwargs: key,
        "_formal_step_contract": lambda _step: contract,
        "_is_generic_multi_tu_workflow": lambda: False,
        "_set_formal_step": targets.append,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP_PATH), "exec"), namespace)

    namespace["_render_step_strip"](4)

    assert [call["disabled"] for call in streamlit.button_calls] == [
        False,
        False,
        False,
        True,
        True,
        True,
    ]
    assert targets == [1]


def test_step4_block_prevents_direct_navigation_to_step5_without_session_mutation() -> None:
    statuses = [
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
    ]
    namespace, session, state, saves, reruns = _navigation_functions(statuses, initial_step=4)

    namespace["_set_formal_step"](5)

    assert session.step == 4
    assert "formal_step_preview" not in state
    assert saves == []
    assert reruns == []


def test_step5_block_prevents_direct_navigation_to_step6_without_session_mutation() -> None:
    statuses = [
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
    ]
    namespace, session, state, saves, reruns = _navigation_functions(statuses, initial_step=5)

    namespace["_set_formal_step"](6)

    assert session.step == 5
    assert "formal_step_preview" not in state
    assert saves == []
    assert reruns == []


def test_review_block_prevents_direct_navigation_past_steps4_and5() -> None:
    for blocked_step, target_step in ((4, 5), (4, 6), (5, 6)):
        statuses = [
            {"done": True, "review": False}
            for _index in range(6)
        ]
        statuses[blocked_step - 1] = {"done": True, "review": True}
        namespace, session, state, saves, reruns = _navigation_functions(
            statuses,
            initial_step=blocked_step,
        )

        namespace["_set_formal_step"](target_step)

        assert session.step == blocked_step
        assert "formal_step_preview" not in state
        assert saves == []
        assert reruns == []


def test_completed_early_step_remains_available_for_review() -> None:
    statuses = [
        {"done": True, "review": False}
        for _index in range(6)
    ]
    namespace, session, state, saves, reruns = _navigation_functions(statuses, initial_step=6)

    namespace["_set_formal_step"](2)

    assert session.step == 2
    assert state["formal_step_preview"] is True
    assert saves == [2]
    assert reruns == [True]


def test_complete_project_can_navigate_to_step6() -> None:
    statuses = [
        {"done": True, "review": False}
        for _index in range(6)
    ]
    namespace, session, state, saves, reruns = _navigation_functions(statuses, initial_step=5)

    namespace["_set_formal_step"](6)

    assert session.step == 6
    assert state["formal_step_preview"] is True
    assert saves == [6]
    assert reruns == [True]


def test_bottom_action_bar_has_one_consistent_next_step_button() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    block = source.split("def _render_step_navigation", 1)[1].split("def _is_formal_action_widget_key", 1)[0]

    assert 'v1.expression.return_project_home' in block
    assert "_t('v1.common.save_draft')" in block
    assert block.count('v1.common.next') == 1
    assert "if current_step < 6 and next_col.button(" in block
    assert "disabled=not next_enabled" in block


def test_step6_bottom_action_bar_only_has_home_and_draft_actions() -> None:
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    node = next(
        item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "_render_step_navigation"
    )
    streamlit = _ActionStreamlit()
    targets: list[str] = []
    namespace = {
        "Any": Any,
        "st": streamlit,
        "_t": lambda key, **kwargs: {"v1.expression.return_project_home": "返回项目首页", "v1.common.save_project": "保存项目", "v1.common.save_draft": "保存草稿", "v1.common.next": "下一步", "v1.common.project_saved_can_reopened_project_center": "项目已保存，可从项目中心重新打开。", "v1.common.project_draft_saved_can_reopened_project_center": "项目草稿已保存，可从项目中心重新打开。", "v1.expression.unsaved_changes_session_only_save_draft": "当前更改仅保留在本次会话中；如需稍后继续，请保存草稿。"}.get(key, key),
        "_t": lambda key, **kwargs: {"v1.expression.return_project_home": "返回项目首页", "v1.common.save_project": "保存项目", "v1.common.save_draft": "保存草稿", "v1.common.next": "下一步", "v1.common.project_saved_can_reopened_project_center": "项目已保存，可从项目中心重新打开。", "v1.common.project_draft_saved_can_reopened_project_center": "项目草稿已保存，可从项目中心重新打开。", "v1.expression.unsaved_changes_session_only_save_draft": "当前更改仅保留在本次会话中；如需稍后继续，请保存草稿。"}.get(key, key),
        "_normalize_formal_current_step": lambda step: step,
        "_change_page": targets.append,
        "PAGE_PROJECT_HOME": "home",
        "_save_current_formal_draft": lambda **_kwargs: None,
        "_is_pathway_multi_tu_project": lambda: False,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP_PATH), "exec"), namespace)

    namespace["_render_step_navigation"](
        current_step=6,
        next_enabled=False,
    )

    assert [call["label"] for call in streamlit.button_calls] == [
        "返回项目首页",
        "保存项目",
    ]
    assert targets == []

    step6_nodes = [
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name in {"_render_step_6_review", "_render_step_6_complete"}
    ]
    step6_result_actions = [
        item.value
        for node in step6_nodes
        for item in ast.walk(node)
        if isinstance(item, ast.Constant) and item.value == "查看结果与导出"
    ]
    assert step6_result_actions == []

    source = APP_PATH.read_text(encoding="utf-8")
    step6 = source.split("def _render_step_6_review", 1)[1].split("def _render_design_workspace", 1)[0]
    assert step6.count("_render_results_export_content(include_project_actions=False)") == 5
    assert "_change_page(PAGE_RESULTS_EXPORT)" not in step6


def test_workspace_removes_duplicate_generic_save_buttons() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    assert "保存当前步骤" not in source
    assert "保存甜菜红素 Gate 3 CDS 到 TU 映射" not in source
    assert '"保存此步骤"' not in source
    assert '"保存设计"' not in source
    assert '"确认并保存全部 CDS"' not in source
    assert '"应用全部 CDS"' not in source
    assert "next_label=_t('v1.expression.save_tu_plan_continue')" in source
    assert "next_label=_t('v1.expression.confirm_cds_continue')" in source
    assert "_t('v1.expression.applied_pathway_step_configuration')" in source
    preview = source.split("def _render_result_preview_mode", 1)[1].split(
        "def _formal_ui_signature", 1
    )[0]
    assert "show_save=False" in preview


def test_domain_actions_do_not_use_save_or_record_labels() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    assert "_t('v1.expression.confirm_regulatory_component_selection')" in source
    assert "Record reviewed regulatory component choices" not in source
    assert "保存通路酶记录修改" not in source


def test_step_one_next_uses_the_existing_validation_gate_and_save_action() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step_one = source.split("def _render_step_1_project", 1)[1].split(
        "def _render_pathway_mapping_step_2", 1
    )[0]

    assert "next_enabled=ready" in step_one
    assert "next_action=advance_step1" in step_one
    assert 'action_id="step1_save_continue"' in step_one


def test_step_two_uses_automatic_preview_and_one_save_continue_action() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step_two = source.split("def _render_step_2_cds", 1)[1].split(
        "def _plant_element_options", 1
    )[0]

    assert '"分析序列"' not in step_two
    assert '"重新分析"' not in step_two
    assert "next_label=_t('v1.expression.confirm_cds_continue')" in step_two
    assert "preview_matches_saved" in step_two
    assert "next_action=save_cds_and_continue" in step_two
    assert "ds.step = 3" in step_two


def test_step_two_hides_advanced_metadata_and_detailed_checks_by_default() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step_two = source.split("def _render_step_2_cds", 1)[1].split(
        "def _plant_element_options", 1
    )[0]

    assert "st.expander(_t('v1.expression.source_advanced_information'), expanded=False)" in step_two
    assert "st.expander(_t('v1.expression.cds_completeness_checklist'), expanded=False)" in step_two
    assert "blocking_summary = _t('v1.expression.no_blocking_items')" in step_two
    assert "saved_summary = _t('v1.expression.saved_cds_consistent')" in step_two


def test_step_two_automatic_preview_and_summary_follow_cds_input_state() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step_two = source.split("def _render_step_2_cds", 1)[1].split(
        "def _plant_element_options", 1
    )[0]

    assert 'has_cds_input = bool(str(raw or "").strip())' in step_two
    assert "st.info(_t('v1.expression.enter_upload_cds_sequence_view_analysis_preview'))" in step_two
    assert "if not has_cds_input:" in step_two
    assert "else:\n        status_rows = [" in step_two
    assert "saved_summary = _t('v1.expression.saved_cds_consistent') if preview_matches_saved else _t('v1.expression.preview_not_saved')" in step_two
    assert "blocking_messages = [" in step_two


def test_step_five_generates_without_advancing_and_unblocks_next_when_current() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step_five = source.split("def _render_step_5_complete", 1)[1].split(
        "def _render_step_6_review", 1
    )[0]

    assert "_t('v1.expression.full_construct_generated')" in step_five
    assert "_t('v1.expression.generate_full_vector')" in step_five
    assert '"生成载体设计并继续"' not in step_five
    assert "ds.step = 6" not in step_five
    assert "next_enabled=result_is_current" in step_five
    assert 'action=lambda: _generate_complete_plasmid(ds)' in step_five
    assert "st.subheader(_t('v1.expression.step_5_vector_construction_design_computational_check'))" in step_five
    for section_key in (
        'v1.expression.construct_summary',
        'v1.expression.insertion_replacement_strategy',
        'v1.expression.full_construct_preview',
        'v1.expression.computational_check_summary',
    ):
        assert f"_t('{section_key}')" in step_five
    assert "_step5_construct_preview_html(plasmid)" in step_five
    for label_key in (
        'v1.expression.feature_annotation',
        'v1.expression.canonical_hash',
        'v1.expression.canonical_hash_traceability_note',
    ):
        assert f"_t('{label_key}')" in step_five


def test_step_five_preview_exposes_full_component_names_outside_the_track() -> None:
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"))
    node = next(
        item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "_step5_construct_preview_html"
    )
    namespace = {
        "Any": Any,
        "Mapping": Mapping,
        "escape": escape,
        "_component_type_label": lambda value: str(value),
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(APP_PATH), "exec"), namespace)

    rendered = namespace["_step5_construct_preview_html"](
        {
            "sequence_length": 3_000,
            "cassette_coordinates": {"start": 801, "end": 2_791},
            "feature_rows": [
                {"feature_type": "promoter", "name": "CaMV 35S promoter", "start": 801, "end": 1_635},
                {"feature_type": "cds", "name": "R229_SYNTH_CDS", "start": 1_636, "end": 2_535},
                {"feature_type": "terminator", "name": "NOS 3′ regulatory region", "start": 2_536, "end": 2_791},
            ],
        }
    )

    for value in (
        "Promoter",
        "CaMV 35S promoter",
        "835 bp",
        "CDS",
        "R229_SYNTH_CDS",
        "900 bp",
        "3′ regulatory region",
        "NOS 3′ regulatory region",
        "256 bp",
    ):
        assert value in rendered
    assert "NO..." not in rendered


def test_results_route_redirects_to_step_six_and_is_hidden_from_sidebar() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    assert "if target == PAGE_RESULTS_EXPORT:" in source
    assert 'ds.step = 6' in source
    sidebar = source.split("# Sidebar navigation", 1)[1].split("# Page router", 1)[0]
    assert "for _page in _PRIMARY_NAV_PAGES:" in sidebar
    assert "PAGE_CRISPR_WORKFLOW" in sidebar
    primary = source.split("_PRIMARY_NAV_PAGES = (", 1)[1].split(")", 1)[0]
    assert "PAGE_RESULTS_EXPORT" not in primary
