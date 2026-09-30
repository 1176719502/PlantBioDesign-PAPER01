from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from core.i18n import translate


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


def _zh_t(key: str, **kwargs: Any) -> str:
    return translate(key, language="zh-CN", **kwargs)


class _Spinner:
    def __enter__(self) -> "_Spinner":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False


class _Streamlit:
    def __init__(self, state: dict[str, Any] | None = None) -> None:
        self.session_state = state if state is not None else {}

    def spinner(self, _message: str) -> _Spinner:
        return _Spinner()


def _functions(names: set[str], streamlit: _Streamlit) -> dict[str, Any]:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace = {
        "Any": Any,
        "hashlib": hashlib,
        "json": json,
        "st": streamlit,
        "_t": _zh_t,
        "_ui": lambda value: value,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace


def _step3_orchestrator(state: dict[str, Any]) -> Any:
    names = {
        "_set_formal_action_feedback",
        "_execute_formal_action",
        "_matching_formal_step3_result",
        "_orchestrate_formal_step3_generation",
    }
    return _functions(names, _Streamlit(state))["_orchestrate_formal_step3_generation"]


def _step6_orchestrator(state: dict[str, Any]) -> Any:
    names = {
        "_formal_ui_signature",
        "_set_formal_action_feedback",
        "_execute_formal_action",
        "_orchestrate_formal_step6_save",
    }
    return _functions(names, _Streamlit(state))["_orchestrate_formal_step6_save"]


def _generated_action(state: dict[str, Any], calls: list[str], signature: str) -> Any:
    def generate() -> dict[str, Any]:
        calls.append(signature)
        result = {
            "runtime": {"sequence_length": 12},
            "cassette_input_signature": signature,
            "input_signature": signature,
        }
        state["formal_expression_cassette"] = result
        state["formal_cassette_result"] = result
        state["formal_cassette_input_signature"] = signature
        return result

    return generate


def test_step3_first_click_calls_generation_once() -> None:
    state: dict[str, Any] = {}
    calls: list[str] = []
    orchestrate = _step3_orchestrator(state)

    outcome = orchestrate(
        input_signature="input-a",
        generate_action=_generated_action(state, calls, "input-a"),
    )

    assert outcome[0] is True and outcome[2] is True
    assert calls == ["input-a"]


def test_step3_rerun_and_unchanged_return_reuse_the_generated_runtime() -> None:
    state: dict[str, Any] = {}
    calls: list[str] = []
    orchestrate = _step3_orchestrator(state)
    orchestrate(
        input_signature="input-a",
        generate_action=_generated_action(state, calls, "input-a"),
    )
    state.pop("formal_cassette_result")
    state.pop("formal_cassette_input_signature")

    repeated = orchestrate(
        input_signature="input-a",
        generate_action=_generated_action(state, calls, "input-a"),
    )

    assert repeated[0] is True and repeated[2] is False
    assert calls == ["input-a"]
    assert state["formal_cassette_input_signature"] == "input-a"


def test_step3_material_input_change_calls_generation_once_more() -> None:
    state: dict[str, Any] = {}
    calls: list[str] = []
    orchestrate = _step3_orchestrator(state)
    orchestrate(
        input_signature="input-a",
        generate_action=_generated_action(state, calls, "input-a"),
    )

    changed = orchestrate(
        input_signature="input-b",
        generate_action=_generated_action(state, calls, "input-b"),
    )

    assert changed[0] is True and changed[2] is True
    assert calls == ["input-a", "input-b"]


def test_step3_failure_does_not_cache_a_successful_fingerprint() -> None:
    state: dict[str, Any] = {}
    orchestrate = _step3_orchestrator(state)

    def fail() -> None:
        raise RuntimeError("controlled generation failure")

    failed = orchestrate(input_signature="input-a", generate_action=fail)

    assert failed[0] is False
    assert state.get("formal_ui_completed_actions", {}).get("step3_generate_continue") is None
    assert state["formal_ui_action_feedback"]["status"] == "生成失败"


def test_step3_busy_state_blocks_a_duplicate_service_call() -> None:
    state: dict[str, Any] = {"formal_ui_action_busy": "step3_generate_continue"}
    calls: list[str] = []
    orchestrate = _step3_orchestrator(state)

    blocked = orchestrate(
        input_signature="input-a",
        generate_action=_generated_action(state, calls, "input-a"),
    )

    assert blocked == (False, None, False)
    assert calls == []
    assert state["formal_ui_action_feedback"]["status"] == "处理中"


def test_step3_order_confirmation_survives_widget_cleanup_and_can_be_revoked() -> None:
    state = {"formal_step3_order_confirmation_recorded": True}
    streamlit = _Streamlit(state)
    namespace = _functions(
        {
            "_formal_step3_order_confirmation",
            "_record_formal_step3_order_confirmation",
        },
        streamlit,
    )
    invalidations: list[bool] = []
    namespace["_invalidate_formal_snapshots"] = lambda: invalidations.append(True)

    assert namespace["_formal_step3_order_confirmation"]() is True
    assert state["formal_step3_order_confirmed"] is True

    state["formal_step3_order_confirmed"] = False
    namespace["_record_formal_step3_order_confirmation"]()
    state.pop("formal_step3_order_confirmed")

    assert namespace["_formal_step3_order_confirmation"]() is False
    assert invalidations == [True]


def test_step6_success_calls_the_formal_save_service_once_and_then_reuses_it() -> None:
    state: dict[str, Any] = {}
    calls: list[str] = []
    orchestrate = _step6_orchestrator(state)
    result = {"project_id": "project-1", "input_signature": "construct-1"}

    def save_service(payload: dict[str, Any]) -> Any:
        calls.append(payload["project_id"])
        return SimpleNamespace(project_id=payload["project_id"])

    first = orchestrate(result, save_service)
    repeated = orchestrate(result, save_service)

    assert first[0] is True and first[2] is True
    assert repeated[0] is True and repeated[2] is False
    assert calls == ["project-1"]
    assert state["formal_last_saved_mvp_project_id"] == "project-1"


def test_step6_save_exception_reports_failure_without_saved_state() -> None:
    state: dict[str, Any] = {}
    orchestrate = _step6_orchestrator(state)

    def fail(_payload: dict[str, Any]) -> Any:
        raise RuntimeError("controlled save failure")

    failed = orchestrate(
        {"project_id": "project-1", "input_signature": "construct-1"},
        fail,
    )

    assert failed[0] is False
    assert "formal_last_saved_mvp_project_id" not in state
    assert state["formal_ui_action_feedback"]["status"] == "保存失败"


def test_step6_rejects_a_save_result_without_the_current_project_id() -> None:
    state: dict[str, Any] = {}
    orchestrate = _step6_orchestrator(state)

    failed = orchestrate(
        {"project_id": "project-1", "input_signature": "construct-1"},
        lambda _payload: SimpleNamespace(project_id="different-project"),
    )

    assert failed[0] is False
    assert "formal_last_saved_mvp_project_id" not in state
    assert state["formal_ui_action_feedback"]["status"] == "保存失败"


def test_project_reopen_verification_reads_without_triggering_save() -> None:
    namespace = _functions(
        {"_verified_formal_saved_project_id"},
        _Streamlit(),
    )
    verify = namespace["_verified_formal_saved_project_id"]
    opens: list[str] = []
    saves: list[str] = []
    result = {
        "project_id": "project-1",
        "project_name": "P",
        "input_signature": "construct-1",
        "runtime": {"sequence_length": 100},
    }

    def open_service(project_id: str) -> dict[str, Any]:
        opens.append(project_id)
        return dict(result)

    assert verify(result, open_service) == "project-1"
    assert opens == ["project-1"]
    assert saves == []


def test_unsaved_or_mismatched_result_is_not_marked_as_persisted() -> None:
    verify = _functions(
        {"_verified_formal_saved_project_id"},
        _Streamlit(),
    )["_verified_formal_saved_project_id"]
    result = {
        "project_id": "project-1",
        "input_signature": "construct-1",
        "runtime": {"sequence_length": 100},
    }

    def missing(_project_id: str) -> dict[str, Any]:
        raise RuntimeError("not found")

    mismatched = {**result, "input_signature": "other"}
    assert verify(result, missing) == ""
    assert verify(result, lambda _project_id: mismatched) == ""


def _step_contract(statuses: list[dict[str, bool]], current_step: int) -> list[dict[str, Any]]:
    namespace = _functions(
        {"_normalize_formal_current_step", "_formal_step_contract"},
        _Streamlit(),
    )
    namespace["_formal_step_statuses"] = lambda: statuses
    return namespace["_formal_step_contract"](current_step)


def test_step4_blocked_normalizes_manual_step5_and_blocks_later_steps() -> None:
    statuses = [
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": False, "review": False},
        {"done": True, "review": False},
        {"done": False, "review": False},
    ]
    contract = _step_contract(statuses, current_step=5)

    assert [row["state"] for row in contract] == [
        "COMPLETED",
        "COMPLETED",
        "COMPLETED",
        "CURRENT",
        "BLOCKED",
        "BLOCKED",
    ]

    statuses[3] = {"done": True, "review": True}
    review_contract = _step_contract(statuses, current_step=6)
    assert review_contract[3]["state"] == "CURRENT"
    assert [row["state"] for row in review_contract[4:]] == ["BLOCKED", "BLOCKED"]
    assert sum(row["state"] == "CURRENT" for row in review_contract) == 1


def test_completed_prerequisites_unlock_steps_five_and_six_in_order() -> None:
    step5_pending = [
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": True, "review": False},
        {"done": False, "review": False},
        {"done": False, "review": False},
    ]
    contract = _step_contract(step5_pending, current_step=6)
    assert [row["state"] for row in contract] == [
        "COMPLETED",
        "COMPLETED",
        "COMPLETED",
        "COMPLETED",
        "CURRENT",
        "BLOCKED",
    ]
    assert sum(row["state"] == "CURRENT" for row in contract) == 1

    step6_available = [*step5_pending]
    step6_available[4] = {"done": True, "review": False}
    contract = _step_contract(step6_available, current_step=6)
    assert contract[5]["state"] == "CURRENT"
    assert sum(row["state"] == "CURRENT" for row in contract) == 1


def test_material_input_invalidation_preserves_upstream_inputs_and_drops_dependents() -> None:
    state = {
        "formal_project_definition": {"project_name": "P"},
        "formal_cds_input": {"normalized_cds": "ATG"},
        "formal_cassette_result": {"runtime": {}},
        "formal_cassette_input_signature": "old",
        "formal_backbone_record": {"normalized_sequence": "AAAA"},
        "formal_insertion_settings": {"mode": "insertion"},
        "mvp_vector_result": {"runtime": {}},
    }
    namespace = _functions(
        {"_clear_complete_plasmid_state", "_invalidate_formal_snapshots"},
        _Streamlit(state),
    )

    namespace["_invalidate_formal_snapshots"]()

    assert "formal_project_definition" in state
    assert "formal_cds_input" in state
    for key in (
        "formal_cassette_result",
        "formal_cassette_input_signature",
        "formal_backbone_record",
        "formal_insertion_settings",
        "mvp_vector_result",
    ):
        assert key not in state
    assert state["mvp_inputs_stale"] is True
