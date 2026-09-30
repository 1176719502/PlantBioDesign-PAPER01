from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from collections.abc import Mapping
from typing import Any

import pytest

from core.i18n import translate


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


def _zh_t(key: str, **kwargs: Any) -> str:
    return translate(key, language="zh-CN", **kwargs)


def _source() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    tree = ast.parse(_source())
    node = next(
        item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(_source(), node) or ""


class _Spinner:
    def __enter__(self) -> "_Spinner":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False


class _Streamlit:
    def __init__(self) -> None:
        self.session_state: dict[str, Any] = {}

    def spinner(self, _message: str) -> _Spinner:
        return _Spinner()


def _action_helpers(streamlit: _Streamlit) -> tuple[Any, Any]:
    tree = ast.parse(_source())
    names = {"_set_formal_action_feedback", "_execute_formal_action"}
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {"Any": Any, "st": streamlit, "_t": _zh_t, "_ui": lambda value: value}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace["_set_formal_action_feedback"], namespace["_execute_formal_action"]


def _feedback_helper(streamlit: _Streamlit) -> Any:
    tree = ast.parse(_source())
    names = {"_current_formal_action_feedback"}
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {"Any": Any, "Mapping": Mapping, "st": streamlit, "_t": _zh_t, "_ui": lambda value: value}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace["_current_formal_action_feedback"]


def _strategy_helpers(streamlit: _Streamlit, *requested: str) -> dict[str, Any]:
    names = {
        "_formal_ui_signature",
        "_clear_formal_step5_strategy_confirmation",
        "_clear_formal_step4_strategy_confirmation",
        "_formal_step4_strategy_signature",
        "_formal_step4_strategy_ready",
        "_record_formal_step4_strategy_confirmation",
        "_formal_step5_strategy_signature",
        "_formal_canonical_result_is_current",
        "_record_formal_step5_strategy_confirmation",
        "_refresh_formal_strategy_confirmation_state",
        *requested,
    }
    tree = ast.parse(_source())
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {
        "Any": Any,
        "Mapping": Mapping,
        "hashlib": hashlib,
        "json": json,
        "st": streamlit,
        "_t": _zh_t,
        "_ui": lambda value: value,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    namespace["_formal_canonical_result_is_current"] = lambda result: bool(
        result.get("runtime") and result.get("construct_status", "current") == "current"
    )
    return {name: namespace[name] for name in names}


def _ready_strategy_state(streamlit: _Streamlit) -> None:
    streamlit.session_state.update(
        {
            "formal_project_definition": {
                "project_name": "Blank Session Project",
                "plant_host": "Rice / Oryza sativa",
            },
            "formal_cassette_input_signature": "cassette-current",
            "formal_backbone_record": {
                "normalized_sequence": "ACGT",
                "normalized_sequence_sha256": "backbone-current",
            },
            "formal_insertion_settings": {
                "mode": "insertion",
                "start_coordinate": 27,
                "end_coordinate": 28,
                "t_dna_operation_validation": {
                    "allowed": True,
                    "status": "pcambia1300_exact_insertion_applied",
                },
            },
        }
    )


def _step_contract(statuses: list[dict[str, bool]], current_step: int) -> list[dict[str, Any]]:
    tree = ast.parse(_source())
    nodes = [
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name in {"_normalize_formal_current_step", "_formal_step_contract"}
    ]
    namespace = {
        "Any": Any,
        "_formal_step_statuses": lambda: statuses,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace["_formal_step_contract"](current_step)


def test_single_gene_steps_expose_the_final_primary_action_labels() -> None:
    step1 = _function_source("_render_step_1_project")
    assert '"保存并继续"' not in step1
    assert "current_step=1" in step1
    assert "next_action=advance_step1" in step1

    expected = {
        "_render_step_2_cds": "v1.expression.confirm_cds_continue",
        "_render_step_3_elements": "v1.expression.generate_expression_cassette_continue",
        "_render_step_4_backbone": "v1.expression.confirm_backbone_continue_action",
        "_render_step_5_complete": "v1.expression.full_construct_generated",
    }

    for function_name, locale_key in expected.items():
        function_source = _function_source(function_name)
        assert locale_key in function_source
        assert translate(locale_key, language="zh-CN")


def test_auto_advance_steps_hide_competing_next_and_step3_has_no_draft_save() -> None:
    step3 = _function_source("_render_step_3_elements")
    assert step3.count("_render_step_navigation(") == 1
    assert '"下一步"' not in step3
    assert "_save_current_formal_draft" not in step3
    assert 'st.button("保存草稿")' not in step3


def test_step6_inlines_existing_result_content_and_keeps_bottom_bar_for_draft_actions() -> None:
    step6 = _function_source("_render_step_6_review")
    navigation = _function_source("_render_step_navigation")

    assert '"查看结果与导出"' not in step6
    assert "_render_results_export_content(include_project_actions=False)" in step6
    assert "current_step=6" in step6

    navigation_tree = ast.parse(navigation)
    assert "_t('v1.expression.return_project_home')" in navigation
    assert "_t('v1.common.save_project')" in navigation
    assert "save_label =" in navigation
    assert '"查看结果与导出"' not in navigation
    assert "PAGE_RESULTS_EXPORT" not in navigation
    assert "_save_current_formal_draft(current_step=current_step)" in navigation
    assert "if current_step < 6 and next_col.button(" in navigation


def test_step6_save_uses_completed_project_persistence_not_draft_overwrite() -> None:
    save_current = _function_source("_save_current_formal_draft")

    assert "if current_step == 6 and isinstance(result, dict):" in save_current
    assert "save_mvp_single_gene_design(result, repository=repository)" in save_current
    assert "save_formal_project_draft" in save_current
    assert save_current.index("save_mvp_single_gene_design") < save_current.index(
        "save_formal_project_draft"
    )


def test_step_contract_blocks_future_steps_and_allows_completed_return() -> None:
    statuses = [
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
    ]

    contract = _step_contract(statuses, current_step=3)

    assert [row["state"] for row in contract] == [
        "COMPLETED",
        "COMPLETED",
        "CURRENT",
        "BLOCKED",
        "BLOCKED",
        "BLOCKED",
    ]
    assert contract[3]["reason"] == "请先完成第 3 步的当前要求。"


def test_step4_and_step5_prerequisites_control_step5_and_step6_availability() -> None:
    step4_pending = [
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
    ]
    contract = _step_contract(step4_pending, current_step=4)
    assert contract[4]["state"] == "BLOCKED"

    step5_pending = [*step4_pending]
    step5_pending[3] = {"done": True, "review": False}
    contract = _step_contract(step5_pending, current_step=5)
    assert contract[4]["state"] == "CURRENT"
    assert contract[5]["state"] == "BLOCKED"


def test_action_orchestration_calls_service_once_for_unchanged_input_and_rerun() -> None:
    streamlit = _Streamlit()
    _set_feedback, execute = _action_helpers(streamlit)
    calls = 0

    def action() -> str:
        nonlocal calls
        calls += 1
        return "generated"

    first = execute(
        step=3,
        action_id="step3_generate_continue",
        input_signature="same-input",
        action=action,
        success_status="已生成",
        success_message="generated",
        failure_status="生成失败",
    )
    rerun = execute(
        step=3,
        action_id="step3_generate_continue",
        input_signature="same-input",
        action=action,
        success_status="已生成",
        success_message="generated",
        failure_status="生成失败",
    )

    assert first == (True, "generated", True)
    assert rerun == (True, None, False)
    assert calls == 1
    assert streamlit.session_state["formal_ui_action_feedback"]["status"] == "已生成"


def test_action_orchestration_blocks_inflight_duplicate_and_recovers_after_failure() -> None:
    streamlit = _Streamlit()
    _set_feedback, execute = _action_helpers(streamlit)
    streamlit.session_state["formal_ui_action_busy"] = "another-action"
    blocked = execute(
        step=3,
        action_id="step3_generate_continue",
        input_signature="input",
        action=lambda: "must not run",
        success_status="已生成",
        success_message="generated",
        failure_status="生成失败",
    )
    assert blocked == (False, None, False)
    assert streamlit.session_state["formal_ui_action_feedback"]["status"] == "处理中"

    streamlit.session_state.pop("formal_ui_action_busy")

    def fail() -> None:
        raise RuntimeError("controlled failure")

    failed = execute(
        step=3,
        action_id="step3_generate_continue",
        input_signature="input",
        action=fail,
        success_status="已生成",
        success_message="generated",
        failure_status="生成失败",
    )
    assert failed[0] is False
    assert isinstance(failed[1], RuntimeError)
    assert "formal_ui_action_busy" not in streamlit.session_state
    assert streamlit.session_state["formal_ui_action_feedback"]["status"] == "生成失败"

    recovered = execute(
        step=3,
        action_id="step3_generate_continue",
        input_signature="input",
        action=lambda: "generated",
        success_status="已生成",
        success_message="generated",
        failure_status="生成失败",
    )
    assert recovered == (True, "generated", True)
    assert streamlit.session_state["formal_ui_action_feedback"]["status"] == "已生成"


def test_current_generated_result_clears_an_old_generation_failure_banner() -> None:
    streamlit = _Streamlit()
    streamlit.session_state["formal_ui_action_feedback"] = {
        "step": 3,
        "status": "生成失败",
        "message": "表达盒存在阻断项，不能生成。",
    }
    current_feedback = _feedback_helper(streamlit)
    statuses = [
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
    ]

    assert current_feedback(3, statuses) is None
    assert "formal_ui_action_feedback" not in streamlit.session_state


def test_transient_generation_failure_does_not_leak_after_step_navigation() -> None:
    streamlit = _Streamlit()
    streamlit.session_state["formal_ui_action_feedback"] = {
        "step": 3,
        "status": "生成失败",
        "message": "表达盒存在阻断项，不能生成。",
    }
    navigation = _function_source("_set_formal_step")

    assert 'feedback = st.session_state.get("formal_ui_action_feedback")' in navigation
    assert 'st.session_state.pop("formal_ui_action_feedback", None)' in navigation


def test_ui_action_state_is_excluded_from_formal_draft_payload() -> None:
    helper = _function_source("_is_formal_action_widget_key")
    assert 'r"ui_.+|"' in helper


def test_deferred_scientific_predicates_and_protected_services_are_unchanged() -> None:
    source = _source()
    for forbidden_name in (
        "wizard_step1_input_ready",
        "construct_character_eligible",
        "canonical_construct_valid",
        "sequence_analysis_valid",
        "documentation_export_available",
    ):
        assert forbidden_name not in source
    assert "save_mvp_single_gene_design(result, repository=repository)" in source


def test_single_gene_cold_reopen_hydrates_persistent_saved_state() -> None:
    restore = _function_source("_restore_mvp_result")

    assert 'globals().get("_verified_formal_saved_project_id")' in restore
    assert "persisted_verifier(result)" in restore
    assert (
        'st.session_state["formal_last_saved_mvp_project_id"] = '
        'str(result.get("project_id") or "")'
    ) not in restore
    assert 'st.session_state.pop("formal_ui_action_feedback", None)' in restore
    assert 'st.session_state["formal_step4_strategy_confirmed"] =' not in restore
    assert 'st.session_state["formal_step5_strategy_confirmed"] =' not in restore


def test_step4_confirmation_records_only_the_current_ready_strategy() -> None:
    streamlit = _Streamlit()
    _ready_strategy_state(streamlit)
    helpers = _strategy_helpers(streamlit)
    signature = helpers["_formal_step4_strategy_signature"]()

    assert "formal_step4_strategy_confirmed" not in streamlit.session_state
    assert helpers["_record_formal_step4_strategy_confirmation"](signature) is True
    assert streamlit.session_state["formal_step4_strategy_confirmed"] is True
    assert streamlit.session_state["formal_step4_strategy_signature"] == signature

    with pytest.raises(RuntimeError, match="changed before confirmation"):
        helpers["_record_formal_step4_strategy_confirmation"]("stale-signature")
    assert "formal_step4_strategy_confirmed" not in streamlit.session_state
    assert "formal_step5_strategy_confirmed" not in streamlit.session_state


def test_step5_confirmation_requires_current_canonical_and_fails_closed_when_stale() -> None:
    streamlit = _Streamlit()
    _ready_strategy_state(streamlit)
    helpers = _strategy_helpers(streamlit)
    helpers["_record_formal_step4_strategy_confirmation"](
        helpers["_formal_step4_strategy_signature"]()
    )
    result = {"input_signature": "canonical-current", "runtime": {"schema": "current"}}
    streamlit.session_state.update(
        {
            "mvp_vector_result": result,
            "mvp_current_input_signature": "canonical-current",
            "mvp_inputs_stale": False,
        }
    )

    assert "formal_step5_strategy_confirmed" not in streamlit.session_state
    assert helpers["_record_formal_step5_strategy_confirmation"](result) is True
    assert streamlit.session_state["formal_step5_strategy_confirmed"] is True

    stale_result = {**result, "construct_status": "stale"}
    with pytest.raises(RuntimeError, match="canonical result is not current"):
        helpers["_record_formal_step5_strategy_confirmation"](stale_result)
    assert "formal_step5_strategy_confirmed" not in streamlit.session_state

    helpers["_record_formal_step5_strategy_confirmation"](result)
    streamlit.session_state["mvp_inputs_stale"] = True
    assert helpers["_refresh_formal_strategy_confirmation_state"](result) == (True, False)
    assert "formal_step5_strategy_confirmed" not in streamlit.session_state


def test_upstream_and_strategy_invalidation_clear_step4_and_step5_markers() -> None:
    streamlit = _Streamlit()
    helpers = _strategy_helpers(
        streamlit,
        "_clear_complete_plasmid_state",
        "_invalidate_formal_snapshots",
        "_invalidate_complete_plasmid_snapshot",
    )
    for invalidate in (
        helpers["_invalidate_formal_snapshots"],
        helpers["_invalidate_complete_plasmid_snapshot"],
    ):
        streamlit.session_state.update(
            {
                "formal_step4_strategy_confirmed": True,
                "formal_step4_strategy_signature": "old-step4",
                "formal_step5_strategy_confirmed": True,
                "formal_step5_strategy_signature": "old-step5",
                "mvp_vector_result": {"input_signature": "old"},
            }
        )
        invalidate()
        assert "formal_step4_strategy_confirmed" not in streamlit.session_state
        assert "formal_step5_strategy_confirmed" not in streamlit.session_state


def test_step4_and_step5_live_actions_bind_durable_state_without_premature_canonical() -> None:
    step4 = _function_source("_render_step_4_backbone")
    generation = _function_source("_generate_complete_plasmid")
    statuses = _function_source("_formal_step_statuses")

    assert '_record_formal_step4_strategy_confirmation(confirmation_signature)' in step4
    assert step4.index('completed_actions.pop("step4_confirm_continue", None)') < step4.index(
        "succeeded, _result, _executed = _execute_formal_action("
    )
    assert generation.index("_refresh_formal_strategy_confirmation_state()") < generation.index(
        "from services.formal_single_gene_runtime import"
    )
    assert generation.index("_record_formal_step5_strategy_confirmation(result)") > generation.index(
        'st.session_state["mvp_inputs_stale"] = False'
    )
    assert 'state.get("formal_step4_strategy_confirmed")' in statuses
    assert '== _formal_step4_strategy_signature()' in statuses
    assert 'state.get("formal_ui_step4_confirmation_signature")' not in statuses
