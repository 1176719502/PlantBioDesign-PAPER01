from __future__ import annotations

import ast
import json
import re
import sys
import types
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.i18n import translate


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


def _zh_t(key: str, **kwargs: Any) -> str:
    return translate(key, language="zh-CN", **kwargs)


def _app_source() -> str:
    return APP_PATH.read_text(encoding="utf-8")


def _runtime(
    names: set[str],
    state: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    tree = ast.parse(_app_source())
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    namespace: dict[str, Any] = {
        "Any": Any,
        "Mapping": Mapping,
        "json": json,
        "re": re,
        "st": SimpleNamespace(session_state=state),
        "_t": _zh_t,
        "_ui": lambda value: value,
        "_DESIGN_SCENARIO_LABELS": {
            "standard_plant_expression_vector": "v1.expression.standard_plant_expression_vector",
            "metabolic_pathway_multi_tu_vector": "v1.expression.metabolic_pathway_multi_tu_vector",
        },
        "_PROJECT_MODE_LABELS": {
            "稳定遗传转化": "v1.expression.stable_genetic_transformation",
            "瞬时表达": "v1.expression.transient_expression",
            "尚未确定": "v1.expression.not_yet_determined",
        },
        **extra,
    }
    exec(
        compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"),
        namespace,
    )
    return namespace


def _state_helpers(state: dict[str, Any]) -> dict[str, Any]:
    return _runtime(
        {
            "_mark_workflow_dirty",
            "_establish_workflow_baseline",
            "_workflow_has_unsaved_changes",
        },
        state,
    )


def test_session_only_keys_never_enter_formal_state_snapshot() -> None:
    state = {
        "formal_project_name": "Snapshot project",
        "mvp_inputs_stale": True,
        "formal_workflow_dirty": True,
        "formal_durable_save_state": "saved",
        "ui_workflow_dirty": True,
        "ui_has_durable_save": False,
    }
    runtime = _runtime(
        {
            "_is_formal_action_widget_key",
            "_formal_state_snapshot",
        },
        state,
    )

    snapshot = runtime["_formal_state_snapshot"]()

    assert snapshot == {
        "formal_project_name": "Snapshot project",
        "mvp_inputs_stale": True,
    }


def test_new_project_edit_is_dirty_and_warning_eligible() -> None:
    state: dict[str, Any] = {}
    runtime = _state_helpers(state)

    runtime["_establish_workflow_baseline"](has_durable_save=False)
    runtime["_mark_workflow_dirty"]()

    assert state["ui_workflow_dirty"] is True
    assert state["ui_has_durable_save"] is False
    assert runtime["_workflow_has_unsaved_changes"]() is True


def test_successful_draft_save_sets_clean_durable_baseline_while_stale_can_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {
        "formal_project_name": "Draft project",
        "mvp_project_id": "",
        "mvp_inputs_stale": True,
        "ui_workflow_dirty": True,
        "ui_has_durable_save": False,
    }
    captured: dict[str, Any] = {}

    def save_formal_project_draft(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return SimpleNamespace(project_id="draft-1")

    persistence = types.ModuleType("services.formal_project_persistence")
    persistence.save_formal_project_draft = save_formal_project_draft
    repository_module = types.ModuleType("services.plant_project_draft_repository")
    repository_module.PlantProjectDraftRepository = type(
        "PlantProjectDraftRepository",
        (),
        {},
    )
    monkeypatch.setitem(sys.modules, persistence.__name__, persistence)
    monkeypatch.setitem(sys.modules, repository_module.__name__, repository_module)

    runtime = _runtime(
        {
            "_mark_workflow_dirty",
            "_establish_workflow_baseline",
            "_record_formal_step1_design_edit",
            "_is_formal_action_widget_key",
            "_formal_state_snapshot",
            "_save_current_formal_draft",
        },
        state,
        _formal_project_definition=lambda: {"project_name": "Draft project"},
        _project_definition_expression_target=lambda _definition: "",
        _formal_workflow_type=lambda: "single_gene",
        _controller=lambda: SimpleNamespace(get=lambda: SimpleNamespace(step=2)),
        _is_dual_tu_project=lambda: False,
        _formal_design_scenario=lambda: "standard_plant_expression_vector",
        _formal_project_type=lambda: "single_gene",
        PROJECT_TYPE_SINGLE_GENE="single_gene",
        PROJECT_TYPE_DUAL_TU="dual_tu",
    )

    saved = runtime["_save_current_formal_draft"](current_step=2)

    assert saved.project_id == "draft-1"
    assert state["ui_workflow_dirty"] is False
    assert state["ui_has_durable_save"] is True
    assert state["mvp_inputs_stale"] is True
    assert state["formal_last_saved_draft_id"] == "draft-1"
    assert "ui_workflow_dirty" not in captured["formal_state"]
    assert "ui_has_durable_save" not in captured["formal_state"]
    assert "formal_workflow_dirty" not in captured["formal_state"]
    assert "formal_durable_save_state" not in captured["formal_state"]

    state["formal_step1_project_name"] = "Draft project edited after save"
    state["formal_step1_design_scenario"] = "常规植物表达载体"
    state["formal_step1_project_type"] = "单基因"
    runtime["_record_formal_step1_design_edit"]()
    assert state["ui_workflow_dirty"] is True


def test_failed_draft_save_keeps_dirty_and_does_not_claim_durable_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {
        "formal_project_name": "Failing draft",
        "mvp_project_id": "",
        "ui_workflow_dirty": True,
        "ui_has_durable_save": False,
    }

    def fail_save(**_kwargs: Any) -> Any:
        raise RuntimeError("storage unavailable")

    persistence = types.ModuleType("services.formal_project_persistence")
    persistence.save_formal_project_draft = fail_save
    repository_module = types.ModuleType("services.plant_project_draft_repository")
    repository_module.PlantProjectDraftRepository = type(
        "PlantProjectDraftRepository",
        (),
        {},
    )
    monkeypatch.setitem(sys.modules, persistence.__name__, persistence)
    monkeypatch.setitem(sys.modules, repository_module.__name__, repository_module)
    runtime = _runtime(
        {
            "_establish_workflow_baseline",
            "_is_formal_action_widget_key",
            "_formal_state_snapshot",
            "_save_current_formal_draft",
        },
        state,
        _formal_project_definition=lambda: {"project_name": "Failing draft"},
        _project_definition_expression_target=lambda _definition: "",
        _formal_workflow_type=lambda: "single_gene",
        _controller=lambda: SimpleNamespace(get=lambda: SimpleNamespace(step=2)),
    )

    with pytest.raises(RuntimeError, match="storage unavailable"):
        runtime["_save_current_formal_draft"](current_step=2)

    assert state["ui_workflow_dirty"] is True
    assert state["ui_has_durable_save"] is False
    assert "formal_last_saved_draft_id" not in state


def test_post_save_step1_edit_marks_workflow_dirty() -> None:
    state = {
        "ui_workflow_dirty": False,
        "ui_has_durable_save": True,
        "formal_project_definition": {"project_name": "Saved project"},
        "formal_step1_project_name": "Edited project",
        "formal_step1_design_scenario": "常规植物表达载体",
        "formal_step1_project_type": "单基因",
    }
    runtime = _runtime(
        {"_mark_workflow_dirty", "_record_formal_step1_design_edit"},
        state,
        _formal_design_scenario=lambda: "standard_plant_expression_vector",
        _formal_project_type=lambda: "single_gene",
        PROJECT_TYPE_SINGLE_GENE="single_gene",
        PROJECT_TYPE_DUAL_TU="dual_tu",
    )

    runtime["_record_formal_step1_design_edit"]()

    assert state["formal_step1_design_dirty"] is True
    assert state["ui_workflow_dirty"] is True


def test_post_save_step2_edit_marks_workflow_dirty() -> None:
    state = {
        "ui_workflow_dirty": False,
        "ui_has_durable_save": True,
        "formal_cds_input": {
            "original_text": "ATGAAATAA",
            "source_kind": "paste",
            "gene_information": {"gene_name": "SAVED_CDS"},
        },
        "formal_step2_mode": "粘贴核酸序列",
        "formal_step2_gene_name": "EDITED_CDS",
        "formal_step2_cds_text": "ATGAAATAA",
    }
    runtime = _runtime(
        {"_mark_workflow_dirty", "_record_formal_step2_design_edit"},
        state,
    )

    runtime["_record_formal_step2_design_edit"]()

    assert state["formal_step2_design_dirty"] is True
    assert state["ui_workflow_dirty"] is True


@pytest.mark.parametrize(
    ("function_name", "extra"),
    [
        (
            "_invalidate_formal_snapshots",
            {"_clear_complete_plasmid_state": lambda: None},
        ),
        (
            "_invalidate_complete_plasmid_snapshot",
            {"_is_multi_tu_expression_assembly": lambda _value: False},
        ),
    ],
)
def test_post_save_step3_and_step4_edits_mark_workflow_dirty(
    function_name: str,
    extra: dict[str, Any],
) -> None:
    state = {
        "ui_workflow_dirty": False,
        "ui_has_durable_save": True,
        "mvp_vector_result": {"project_id": "saved"},
    }
    runtime = _runtime(
        {"_mark_workflow_dirty", function_name},
        state,
        **extra,
    )

    runtime[function_name]()

    assert state["ui_workflow_dirty"] is True


def test_post_save_step5_generation_marks_workflow_dirty() -> None:
    state = {
        "ui_workflow_dirty": False,
        "ui_has_durable_save": True,
    }
    runtime = _runtime(
        {"_mark_workflow_dirty", "_generate_complete_plasmid"},
        state,
        _is_dual_tu_project=lambda: True,
        _generate_dual_tu_complete_plasmid=lambda _ds: {"project_id": "saved"},
    )

    runtime["_generate_complete_plasmid"](SimpleNamespace())

    assert state["ui_workflow_dirty"] is True


def test_draft_reopen_discards_persisted_legacy_markers_and_starts_clean(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {
        "ui_workflow_dirty": True,
        "ui_has_durable_save": False,
        "formal_project_name": "Previous project",
    }
    draft = SimpleNamespace(project_id="draft-2", project_name="Reopened draft")
    snapshot = {
        "formal_state": {
            "formal_project_name": "Reopened draft",
            "formal_workflow_dirty": True,
            "formal_durable_save_state": "saved",
        },
        "project_definition": {"plant_host": "rice"},
        "workflow_type": "single_gene",
        "design_session": {"step": 2},
    }
    persistence = types.ModuleType("services.formal_project_persistence")
    persistence.formal_draft_snapshot = lambda _draft: snapshot
    persistence.restore_design_session = lambda _payload: SimpleNamespace(
        step=2,
        gene_name="",
        original_seq="",
        host="",
    )
    repository_module = types.ModuleType("services.plant_project_draft_repository")
    repository_module.PlantProjectDraftRepository = type(
        "PlantProjectDraftRepository",
        (),
        {"load": lambda _self, _project_id: draft},
    )
    repository_module.require_active_project = lambda _draft: None
    monkeypatch.setitem(sys.modules, persistence.__name__, persistence)
    monkeypatch.setitem(sys.modules, repository_module.__name__, repository_module)
    runtime = _runtime(
        {
            "_mark_workflow_dirty",
            "_establish_workflow_baseline",
            "_is_formal_action_widget_key",
            "_restore_formal_workflow_draft",
        },
        state,
        _restore_formal_step3_generated_result=lambda: None,
        _controller=lambda: SimpleNamespace(save=lambda _session: None),
        _change_page=lambda _page: None,
        PAGE_DESIGN_WORKSPACE="Design Workspace",
        PROJECT_TYPE_SINGLE_GENE="single_gene",
        PROJECT_TYPE_DUAL_TU="dual_tu",
    )

    runtime["_restore_formal_workflow_draft"]("draft-2")

    assert state["ui_workflow_dirty"] is False
    assert state["ui_has_durable_save"] is True
    assert state["formal_last_saved_draft_id"] == "draft-2"
    assert "formal_workflow_dirty" not in state
    assert "formal_durable_save_state" not in state


def test_compatibility_draft_reopen_seeds_step1_baseline_before_first_edit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definition = {
        "project_name": "Compatibility draft",
        "plant_host": "rice",
        "material": "albumin",
        "application_mode": "stable",
    }
    state: dict[str, Any] = {
        "ui_workflow_dirty": True,
        "ui_has_durable_save": False,
        "formal_step1_project_name": definition["project_name"],
        "formal_step1_host": definition["plant_host"],
        "formal_step1_material": definition["material"],
        "formal_step1_application_mode": definition["application_mode"],
    }
    draft = SimpleNamespace(project_id="compat-draft", project_name=definition["project_name"])
    snapshot = {
        "formal_state": {
            "formal_step1_project_name": definition["project_name"],
            "formal_step1_host": definition["plant_host"],
            "formal_step1_material": definition["material"],
            "formal_step1_application_mode": definition["application_mode"],
        },
        "project_definition": definition,
        "workflow_type": "single_gene",
        "design_session": {"step": 1},
    }
    persistence = types.ModuleType("services.formal_project_persistence")
    persistence.formal_draft_snapshot = lambda _draft: snapshot
    persistence.restore_design_session = lambda _payload: SimpleNamespace(
        step=1, gene_name="", original_seq="", host=""
    )
    repository_module = types.ModuleType("services.plant_project_draft_repository")
    repository_module.PlantProjectDraftRepository = type(
        "PlantProjectDraftRepository", (), {"load": lambda _self, _project_id: draft}
    )
    repository_module.require_active_project = lambda _draft: None
    monkeypatch.setitem(sys.modules, persistence.__name__, persistence)
    monkeypatch.setitem(sys.modules, repository_module.__name__, repository_module)
    runtime = _runtime(
        {
            "_mark_workflow_dirty",
            "_establish_workflow_baseline",
            "_is_formal_action_widget_key",
            "_restore_formal_workflow_draft",
            "_record_formal_step1_design_edit",
        },
        state,
        _restore_formal_step3_generated_result=lambda: None,
        _controller=lambda: SimpleNamespace(save=lambda _session: None),
        _change_page=lambda _page: None,
        _formal_project_type=lambda: "single_gene",
        _formal_design_scenario=lambda: "standard_plant_expression_vector",
        PAGE_DESIGN_WORKSPACE="Design Workspace",
        PROJECT_TYPE_SINGLE_GENE="single_gene",
        PROJECT_TYPE_DUAL_TU="dual_tu",
    )

    runtime["_restore_formal_workflow_draft"]("compat-draft")

    assert state["ui_workflow_dirty"] is False
    assert state["ui_has_durable_save"] is True
    assert state["ui_step1_baseline"] == definition
    assert state["formal_project_definition"] == definition

    runtime["_record_formal_step1_design_edit"]()
    assert state["ui_workflow_dirty"] is False

    state["formal_step1_material"] = "edited albumin"
    runtime["_record_formal_step1_design_edit"]()
    assert state["ui_workflow_dirty"] is True
    assert state["formal_step1_design_dirty"] is True

    state["formal_step1_material"] = "edited albumin again"
    runtime["_record_formal_step1_design_edit"]()
    assert state["ui_workflow_dirty"] is True


def test_completed_project_restore_replaces_prior_project_session_markers() -> None:
    state = {
        "ui_workflow_dirty": True,
        "ui_has_durable_save": False,
        "formal_workflow_dirty": True,
        "formal_durable_save_state": "saved",
    }
    runtime = _runtime(
        {
            "_mark_workflow_dirty",
            "_establish_workflow_baseline",
            "_is_formal_action_widget_key",
            "_restore_completed_formal_state",
        },
        state,
    )

    runtime["_restore_completed_formal_state"](
        {
            "formal_state": {
                "formal_project_name": "Completed project",
                "formal_workflow_dirty": True,
                "formal_durable_save_state": "saved",
            }
        }
    )

    assert state["formal_project_name"] == "Completed project"
    assert state["ui_workflow_dirty"] is False
    assert state["ui_has_durable_save"] is True
    assert "formal_workflow_dirty" not in state
    assert "formal_durable_save_state" not in state


def test_new_project_after_saved_project_cannot_inherit_save_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {
        "ui_workflow_dirty": True,
        "ui_has_durable_save": True,
        "formal_last_saved_draft_id": "old-project",
        "mvp_project_id": "old-project",
    }
    controller = SimpleNamespace(
        save=lambda _session: None,
        clear_global_context=lambda: None,
    )
    design_module = types.ModuleType("core.design_session")
    design_module.DesignSession = lambda **kwargs: SimpleNamespace(**kwargs)
    design_module.SessionController = lambda: controller
    wizard_module = types.ModuleType("services.wizard_state_service")
    wizard_module.reset_wizard_for_new_design = lambda _state: None
    monkeypatch.setitem(sys.modules, design_module.__name__, design_module)
    monkeypatch.setitem(sys.modules, wizard_module.__name__, wizard_module)
    runtime = _runtime(
        {
            "_mark_workflow_dirty",
            "_establish_workflow_baseline",
            "_start_blank_design",
        },
        state,
        _bump_reset_token=lambda: None,
        _change_page=lambda _page: None,
        _formal_project_definition=lambda: {
            "project_name": state.get("formal_project_name", ""),
        },
        PAGE_DESIGN_WORKSPACE="Design Workspace",
        PROJECT_TYPE_SINGLE_GENE="single_gene",
        PROJECT_TYPE_DUAL_TU="dual_tu",
    )

    runtime["_start_blank_design"]()

    assert state["ui_workflow_dirty"] is False
    assert state["ui_has_durable_save"] is False
    assert "formal_last_saved_draft_id" not in state
    assert "mvp_project_id" not in state


class _ActionColumn:
    def __init__(self, streamlit: "_ActionStreamlit") -> None:
        self.streamlit = streamlit

    def button(self, label: str, **kwargs: Any) -> bool:
        return bool(
            kwargs.get("key") == self.streamlit.clicked_key
            and not kwargs.get("disabled", False)
        )


class _Context:
    def __enter__(self) -> "_Context":
        return self

    def __exit__(self, *_args: Any) -> bool:
        return False


class _ActionStreamlit:
    def __init__(self, state: dict[str, Any], clicked_key: str) -> None:
        self.session_state = state
        self.clicked_key = clicked_key
        self.captions: list[str] = []
        self.successes: list[str] = []
        self.errors: list[str] = []

    def container(self, **_kwargs: Any) -> Any:
        return _Context()

    def columns(self, spec: list[int]) -> list[_ActionColumn]:
        return [_ActionColumn(self) for _item in spec]

    def caption(self, message: str) -> None:
        self.captions.append(message)

    def success(self, message: str) -> None:
        self.successes.append(message)

    def error(self, message: str) -> None:
        self.errors.append(message)


@pytest.mark.parametrize(
    ("current_step", "expected"),
    [
        (1, "项目草稿已保存，可从项目中心重新打开。"),
        (6, "项目已保存，可从项目中心重新打开。"),
    ],
)
def test_save_feedback_uses_step_specific_wording_without_unsaved_warning(
    current_step: int,
    expected: str,
) -> None:
    state = {
        "ui_workflow_dirty": True,
        "ui_has_durable_save": False,
    }
    streamlit = _ActionStreamlit(
        state,
        clicked_key=f"formal_step_{current_step}_save_draft",
    )
    runtime = _runtime(
        {
            "_mark_workflow_dirty",
            "_establish_workflow_baseline",
            "_workflow_has_unsaved_changes",
            "_render_step_navigation",
        },
        state,
        _is_pathway_multi_tu_project=lambda: False,
        _normalize_formal_current_step=lambda step: step,
        _save_current_formal_draft=lambda **_kwargs: runtime[
            "_establish_workflow_baseline"
        ](has_durable_save=True),
        _change_page=lambda _page: None,
        PAGE_PROJECT_HOME="Project Home",
    )
    runtime["st"] = streamlit

    runtime["_render_step_navigation"](
        current_step=current_step,
        next_enabled=False,
    )

    assert streamlit.successes == [expected]
    assert "当前更改仅保留在本次会话中；如需稍后继续，请保存草稿。" not in streamlit.captions
    assert state["ui_workflow_dirty"] is False
    assert state["ui_has_durable_save"] is True


def test_failed_save_shows_no_success_and_keeps_unsaved_warning() -> None:
    state = {
        "ui_workflow_dirty": True,
        "ui_has_durable_save": False,
    }
    streamlit = _ActionStreamlit(
        state,
        clicked_key="formal_step_1_save_draft",
    )

    def fail_save(**_kwargs: Any) -> None:
        raise RuntimeError("storage unavailable")

    runtime = _runtime(
        {
            "_workflow_has_unsaved_changes",
            "_render_step_navigation",
        },
        state,
        _is_pathway_multi_tu_project=lambda: False,
        _normalize_formal_current_step=lambda step: step,
        _save_current_formal_draft=fail_save,
        _change_page=lambda _page: None,
        PAGE_PROJECT_HOME="Project Home",
    )
    runtime["st"] = streamlit

    runtime["_render_step_navigation"](current_step=1, next_enabled=False)

    assert streamlit.successes == []
    assert streamlit.errors == ["storage unavailable"]
    assert "当前更改仅保留在本次会话中；如需稍后继续，请保存草稿。" in streamlit.captions
    assert state["ui_workflow_dirty"] is True
    assert state["ui_has_durable_save"] is False


def test_r1_step1_and_step2_copy_remains_unchanged() -> None:
    source = _app_source()

    assert "v1.expression.step_1_applied_continue_step_2" in source
    assert "v1.expression.cds_applied_continue_step_3" in source
    assert "next_label=_t('v1.expression.confirm_cds_continue')" in source
