from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path
import sys
import types
from typing import Any, Mapping
from unittest.mock import patch

import pytest

from core.design_session import DesignSession
from services.formal_project_persistence import formal_draft_snapshot, save_formal_project_draft
from services.plant_project_draft_repository import PlantProjectDraftRepository


ROOT = Path(__file__).resolve().parents[1]


def _step1_project_type_resolver():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "_resolve_formal_step1_project_type"
    )
    namespace = {
        "Any": Any,
        "Mapping": Mapping,
        "PROJECT_TYPE_SINGLE_GENE": "single_gene",
        "PROJECT_TYPE_DUAL_TU": "dual_tu",
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace["_resolve_formal_step1_project_type"]


def test_step1_standard_scenario_preserves_explicit_multi_tu_selection() -> None:
    resolve = _step1_project_type_resolver()
    labels = {"single_gene": "单基因", "dual_tu": "多转录单元（可增减与排序）"}
    assert resolve(
        selected_scenario="standard_plant_expression_vector",
        selected_mode_label=labels["dual_tu"],
        mode_labels=labels,
        current_project_type="single_gene",
    ) == "dual_tu"


def test_step1_pathway_scenario_forces_multi_tu_when_disabled_widget_is_none() -> None:
    resolve = _step1_project_type_resolver()
    labels = {"single_gene": "单基因", "dual_tu": "多转录单元（可增减与排序）"}
    assert resolve(
        selected_scenario="metabolic_pathway_multi_tu_vector",
        selected_mode_label=None,
        mode_labels=labels,
        current_project_type="single_gene",
    ) == "dual_tu"


def test_step1_pathway_scenario_forced_mode_is_stable_across_current_state() -> None:
    resolve = _step1_project_type_resolver()
    labels = {"single_gene": "单基因", "dual_tu": "多转录单元（可增减与排序）"}
    for current in ("single_gene", "dual_tu", None, "stale"):
        assert resolve(
            selected_scenario="metabolic_pathway_multi_tu_vector",
            selected_mode_label=None,
            mode_labels=labels,
            current_project_type=current,
        ) == "dual_tu"


def test_step1_switching_back_to_standard_restores_selectable_mode_behavior() -> None:
    resolve = _step1_project_type_resolver()
    labels = {"single_gene": "单基因", "dual_tu": "多转录单元（可增减与排序）"}
    assert resolve(
        selected_scenario="standard_plant_expression_vector",
        selected_mode_label=labels["single_gene"],
        mode_labels=labels,
        current_project_type="dual_tu",
    ) == "single_gene"


@pytest.mark.parametrize("selected_mode_label", ["未知模式", "", 123])
def test_step1_invalid_mode_state_fails_closed_without_guessing(selected_mode_label: Any) -> None:
    resolve = _step1_project_type_resolver()
    labels = {"single_gene": "单基因", "dual_tu": "多转录单元（可增减与排序）"}
    assert resolve(
        selected_scenario="standard_plant_expression_vector",
        selected_mode_label=selected_mode_label,
        mode_labels=labels,
        current_project_type="not-a-project-type",
    ) is None


class _Streamlit:
    def __init__(self, state: dict[str, Any]) -> None:
        self.session_state = state


class _OptionalInputStreamlit(_Streamlit):
    def checkbox(self, _label: str, *, value: bool, key: str, on_change: Any) -> bool:
        del on_change
        return bool(self.session_state.setdefault(key, value))

    def text_input(self, _label: str, *, value: str, key: str, on_change: Any) -> str:
        del on_change
        return str(self.session_state.setdefault(key, value))

    def text_area(
        self,
        _label: str,
        *,
        value: str,
        height: int,
        key: str,
        on_change: Any,
    ) -> str:
        del height, on_change
        return str(self.session_state.setdefault(key, value))


def _is_result_preview_mode(state: dict[str, Any]) -> bool:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "_is_result_preview_mode"
    )
    namespace = {
        "Mapping": Mapping,
        "st": _Streamlit(state),
        "_formal_step_statuses": lambda: [{"done": True, "review": False}] * 3
        + [{"done": False, "review": False}] * 3,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace["_is_result_preview_mode"]()


def _hydrate_current_editor(state: dict[str, Any]) -> bool:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    names = {
        "_new_transcription_unit",
        "_default_transcription_unit_display_name",
        "_normalize_transcription_units",
        "_store_transcription_units",
        "_multi_tu_editor_has_complete_inputs",
        "_is_explicit_five_prime_absence",
        "_hydrate_current_multi_tu_editor_from_result",
    }
    nodes = [
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name in names
    ]
    namespace = {
        "Any": Any,
        "Mapping": Mapping,
        "st": _Streamlit(state),
        "uuid4": lambda: None,
        "_MULTI_TU_EDITOR_REQUIRED_ROLES": (
            "promoter",
            "five_prime_region",
            "cds",
            "3_prime_regulatory_region",
        ),
        "_MULTI_TU_EDITOR_OPTIONAL_ROLES": (
            "targeting_sequence",
            "linker",
            "fusion_tag",
        ),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return namespace["_hydrate_current_multi_tu_editor_from_result"]()


def _prepare_editor_widgets(state: dict[str, Any]) -> None:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    names = {
        "_new_transcription_unit",
        "_default_transcription_unit_display_name",
        "_normalize_transcription_units",
        "_transcription_units",
        "_formal_ui_signature",
        "_multi_tu_editor_widget_state_is_present",
        "_prepare_multi_tu_editor_widget_state",
        "_invalidate_multi_tu_editor_widget_state",
        "_is_explicit_five_prime_absence",
    }
    nodes = [
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name in names
    ]
    namespace = {
        "Any": Any,
        "Mapping": Mapping,
        "json": __import__("json"),
        "hashlib": __import__("hashlib"),
        "uuid4": lambda: None,
        "st": _Streamlit(state),
        "_MULTI_TU_EDITOR_REQUIRED_ROLES": (
            "promoter",
            "five_prime_region",
            "cds",
            "3_prime_regulatory_region",
        ),
        "_MULTI_TU_EDITOR_OPTIONAL_ROLES": (
            "targeting_sequence",
            "linker",
            "fusion_tag",
        ),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    namespace["_prepare_multi_tu_editor_widget_state"]()


def _render_optional_editor(
    state: dict[str, Any],
    unit: dict[str, Any],
    role: str,
    label: str,
) -> dict[str, Any]:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    step_three = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "_render_dual_tu_step_3"
    )
    node = next(
        item
        for item in step_three.body
        if isinstance(item, ast.FunctionDef) and item.name == "_optional_input"
    )
    namespace = {
        "Any": Any,
        "st": _OptionalInputStreamlit(state),
        "_transcription_unit": lambda _unit_id: unit,
        "_invalidate_dual_tu_unit": lambda _unit_id: None,
        "analyze_dna_component_input": lambda *_args, **_kwargs: {},
        "new_project_id": lambda: "test-project",
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace["_optional_input"](str(unit["unit_id"]), "TU1", role, label)


def _invalidate_editor_unit(state: dict[str, Any], unit_id: str) -> None:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    nodes = [
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name in {"_invalidate_dual_tu_outputs", "_invalidate_dual_tu_unit"}
    ]
    namespace = {
        "st": _Streamlit(state),
        "globals": globals,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    namespace["_invalidate_dual_tu_unit"](unit_id)


def _reopen_dual_tu_result(state: dict[str, Any], result: dict[str, Any]) -> None:
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    nodes = [
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef)
        and item.name in {
            "_new_transcription_unit",
            "_default_transcription_unit_display_name",
            "_normalize_transcription_units",
            "_restore_dual_tu_result",
            "_invalidate_multi_tu_editor_widget_state",
        }
    ]

    class _Controller:
        def save(self, _design_session: Any) -> None:
            return None

    namespace = {
        "Any": Any,
        "Mapping": Mapping,
        "uuid4": lambda: None,
        "st": _Streamlit(state),
        "PROJECT_TYPE_DUAL_TU": "dual_tu",
        "_MULTI_TU_EDITOR_REQUIRED_ROLES": (
            "promoter",
            "five_prime_region",
            "cds",
            "3_prime_regulatory_region",
        ),
        "PAGE_RESULTS_EXPORT": "Results and Export",
        "_restore_completed_formal_state": lambda _context: None,
        "_controller": lambda: _Controller(),
        "_change_page": lambda _page: None,
        "_normalize_design_scenario": lambda value: value or "standard_plant_expression_vector",
        "_is_pathway_multi_tu_project": lambda: False,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    design_session = types.ModuleType("core.design_session")
    design_session.DesignSession = type(
        "DesignSession",
        (),
        {"__init__": lambda self, **kwargs: self.__dict__.update(kwargs)},
    )
    pathway_mapping = types.ModuleType("services.gate3_pathway_mapping")
    pathway_mapping.normalize_design_scenario = lambda value: value or "standard_plant_expression_vector"
    pathway_mapping.normalize_pathway_steps = lambda value: list(value or [])
    mt01 = types.ModuleType("services.mt01_formal_runtime")
    mt01.is_mt01_claim = lambda _result: False
    mt02 = types.ModuleType("services.mt02_formal_runtime")
    mt02.is_mt02_claim = lambda _result: False
    with patch.dict(
        sys.modules,
        {
            "core.design_session": design_session,
            "services.gate3_pathway_mapping": pathway_mapping,
            "services.mt01_formal_runtime": mt01,
            "services.mt02_formal_runtime": mt02,
        },
    ):
        namespace["_restore_dual_tu_result"](result)


def _saved_multi_tu_result() -> dict[str, Any]:
    return {
        "project_id": "multi-tu-current",
        "input_signature": "same-input",
        "exports": {
            "combined_construct_fasta": {"data": ">multi-tu\nAAAA"},
            "combined_construct_genbank": {"data": "LOCUS       multi-tu"},
        },
    }


def _four_role_unit(unit_id: str, orientation: str) -> dict[str, Any]:
    suffix = "A" if unit_id == "TU1" else "B"
    return {
        "unit_id": unit_id,
        "display_name": unit_id,
        "order": 1 if unit_id == "TU1" else 2,
        "orientation": orientation,
        "promoter": {"display_name": f"UI_PROMOTER_{suffix}", "raw_text": "AAAA"},
        "five_prime_region": {"display_name": f"UI_5PRIME_{suffix}", "raw_text": "CCCC"},
        "cds": {"display_name": f"UI_TEST_CDS_{suffix}", "raw_text": "ATGAAATAA"},
        "3_prime_regulatory_region": {"display_name": f"UI_3REG_{suffix}", "raw_text": "TTTT"},
    }


def _current_result_with_four_roles() -> dict[str, Any]:
    units = [_four_role_unit("TU1", "forward"), _four_role_unit("TU2", "reverse")]
    return {
        "project_id": "multi-tu-current",
        "unit_order": ["TU1", "TU2"],
        "original_input": {"expression_units": units},
    }


def _persisted_widget_units(suffix: str) -> list[dict[str, Any]]:
    roles = (
        "promoter",
        "five_prime_region",
        "cds",
        "3_prime_regulatory_region",
    )
    units = []
    for unit_id in ("TU1", "TU2"):
        unit = {"unit_id": unit_id, "display_name": unit_id, "orientation": "forward"}
        for role in roles:
            unit[role] = {
                "display_name": f"{role}-{unit_id}-{suffix}",
                "raw_text": f"{suffix}{unit_id}{role}",
                "source_type": "paste",
            }
        units.append(unit)
    return units


def _widget_values(state: dict[str, Any], units: list[dict[str, Any]]) -> dict[str, str]:
    return {
        f"formal_{unit['unit_id'].lower()}_{role}_{field}": str(state.get(
            f"formal_{unit['unit_id'].lower()}_{role}_{field}", ""
        ))
        for unit in units
        for role in ("promoter", "five_prime_region", "cds", "3_prime_regulatory_region")
        for field in ("name", "text")
    }


def test_current_multi_tu_result_never_enters_history_without_explicit_open() -> None:
    result = _saved_multi_tu_result()

    assert not _is_result_preview_mode(
        {
            "mvp_vector_result": result,
            "mvp_current_input_signature": result["input_signature"],
            "mvp_inputs_stale": False,
        }
    )


def test_explicit_saved_result_open_is_the_only_history_preview_trigger() -> None:
    result = _saved_multi_tu_result()

    assert _is_result_preview_mode(
        {
            "formal_explicit_historical_open": True,
            "mvp_vector_result": result,
            "mvp_current_input_signature": result["input_signature"],
            "mvp_inputs_stale": False,
        }
    )


def test_multi_tu_generation_and_project_open_classify_history_from_record_contract() -> None:
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    step_three = source.split("def _render_dual_tu_step_3", 1)[1].split(
        "def _render_step_3_elements", 1
    )[0]
    open_saved = source.split("def _open_saved_mvp_project", 1)[1].split(
        "def _render_mt01_case_entry", 1
    )[0]

    assert 'st.session_state.pop("formal_explicit_historical_open", None)' in step_three
    assert "_prepare_saved_multi_tu_open(result)" in open_saved
    assert open_saved.index("_prepare_saved_multi_tu_open(result)") < open_saved.index(
        "_restore_dual_tu_result(result)"
    )


def test_current_result_hydrates_only_missing_editor_inputs_with_four_roles() -> None:
    result = _current_result_with_four_roles()
    state = {
        "mvp_project_id": result["project_id"],
        "mvp_vector_result": result,
        "mvp_inputs_stale": False,
        "formal_transcription_units": [
            {"unit_id": "TU1", "orientation": "forward"},
            {"unit_id": "TU2", "orientation": "forward"},
        ],
    }

    assert _hydrate_current_editor(state) is True
    units = state["formal_transcription_units"]
    assert [unit["unit_id"] for unit in units] == ["TU1", "TU2"]
    assert [unit["orientation"] for unit in units] == ["forward", "reverse"]
    assert [unit["five_prime_region"]["display_name"] for unit in units] == [
        "UI_5PRIME_A",
        "UI_5PRIME_B",
    ]
    assert [unit["cds"]["raw_text"] for unit in units] == ["ATGAAATAA", "ATGAAATAA"]


def test_current_result_hydration_never_overwrites_stale_or_historical_editor_state() -> None:
    result = _current_result_with_four_roles()
    for state_update in (
        {"mvp_inputs_stale": True},
        {"formal_explicit_historical_open": True},
    ):
        existing = [{"unit_id": "TU1", "orientation": "forward"}]
        state = {
            "mvp_project_id": result["project_id"],
            "mvp_vector_result": result,
            "formal_transcription_units": existing,
            **state_update,
        }
        before = deepcopy(existing)
        assert _hydrate_current_editor(state) is False
        assert state["formal_transcription_units"] == before


def test_current_result_hydration_leaves_complete_editor_inputs_unchanged() -> None:
    result = _current_result_with_four_roles()
    existing = deepcopy(result["original_input"]["expression_units"])
    existing[0]["promoter"]["display_name"] = "CURRENT_EDITOR_PROMOTER"
    state = {
        "mvp_project_id": result["project_id"],
        "mvp_vector_result": result,
        "mvp_inputs_stale": False,
        "formal_transcription_units": existing,
    }

    assert _hydrate_current_editor(state) is False
    assert state["formal_transcription_units"][0]["promoter"]["display_name"] == "CURRENT_EDITOR_PROMOTER"


def test_multi_tu_widget_hydration_first_run_populates_all_four_roles() -> None:
    persisted = _persisted_widget_units("saved-a")
    state = {"mvp_project_id": "same-project", "formal_transcription_units": persisted}

    _prepare_editor_widgets(state)

    values = _widget_values(state, persisted)
    assert all(values.values())
    assert values["formal_tu1_five_prime_region_text"] == "saved-aTU1five_prime_region"
    assert values["formal_tu2_3_prime_regulatory_region_name"] == (
        "3_prime_regulatory_region-TU2-saved-a"
    )
    assert state["_formal_multi_tu_widget_state_marker"].startswith("same-project:")


def test_multi_tu_widget_hydration_is_idempotent_for_unsaved_widget_edits() -> None:
    persisted = _persisted_widget_units("saved-a")
    state = {"mvp_project_id": "same-project", "formal_transcription_units": persisted}

    _prepare_editor_widgets(state)
    marker = state["_formal_multi_tu_widget_state_marker"]
    state["formal_tu1_cds_text"] = "unsaved-edit"
    _prepare_editor_widgets(state)

    assert state["_formal_multi_tu_widget_state_marker"] == marker
    assert state["formal_tu1_cds_text"] == "unsaved-edit"


def test_step3_step4_step3_rehydrates_removed_widgets_without_staling_current_result() -> None:
    units = [
        {
            "unit_id": "TU1",
            "display_name": "植物选择标记表达单元",
            "order": 1,
            "orientation": "forward",
            "promoter": {"display_name": "PROMOTER_BETA", "raw_text": "GGTTAACC", "source_type": "paste"},
            "five_prime_region": {"display_name": "FIVE_PRIME_BETA", "raw_text": "GCTA", "source_type": "paste"},
            "cds": {"display_name": "CDS_BETA", "raw_text": "ATGAAACCCGGGTAG", "source_type": "paste"},
            "3_prime_regulatory_region": {"display_name": "THREE_PRIME_BETA", "raw_text": "CCGGTTAA", "source_type": "paste"},
        },
        {
            "unit_id": "TU2",
            "display_name": "目标基因表达单元",
            "order": 2,
            "orientation": "reverse",
            "promoter": {"display_name": "PROMOTER_ALPHA", "raw_text": "AACCGGTT", "source_type": "paste"},
            "five_prime_region": {"display_name": "FIVE_PRIME_ALPHA", "raw_text": "ATGC", "source_type": "paste"},
            "cds": {"display_name": "CDS_ALPHA", "raw_text": "ATGGCTGCTTAA", "source_type": "paste"},
            "3_prime_regulatory_region": {"display_name": "THREE_PRIME_ALPHA", "raw_text": "TTGCAACC", "source_type": "paste"},
        },
    ]
    state = {
        "mvp_project_id": "human-multi-tu-fixture",
        "formal_transcription_units": deepcopy(units),
        "mvp_vector_result": {"input_signature": "current-signature"},
        "formal_dual_tu_combined_result": {"input_signature": "current-signature"},
        "mvp_current_input_signature": "current-signature",
        "mvp_inputs_stale": False,
    }
    _prepare_editor_widgets(state)
    expected_widgets = _widget_values(state, units)
    marker = state["_formal_multi_tu_widget_state_marker"]

    for _navigation_cycle in range(2):
        for key in list(state):
            if key.startswith("formal_tu") and key != "formal_transcription_units":
                state.pop(key)
        assert state["_formal_multi_tu_widget_state_marker"] == marker

        _prepare_editor_widgets(state)

        assert _widget_values(state, units) == expected_widgets
        hydrated = state["formal_transcription_units"]
        assert [unit["unit_id"] for unit in hydrated] == ["TU1", "TU2"]
        assert [unit["orientation"] for unit in hydrated] == ["forward", "reverse"]
        assert [unit["cds"]["raw_text"] for unit in hydrated] == [
            "ATGAAACCCGGGTAG",
            "ATGGCTGCTTAA",
        ]
        assert state["mvp_vector_result"]["input_signature"] == "current-signature"
        assert state["mvp_current_input_signature"] == "current-signature"
        assert state["mvp_inputs_stale"] is False


def test_widget_hydration_preserves_explicit_none_and_does_not_overwrite_a_real_mode_edit() -> None:
    units = _persisted_widget_units("saved")
    units[0]["five_prime_region"] = {
        "absence_state": "explicit_none",
        "display_name": "不使用独立 5′ region",
        "raw_text": "",
        "source_type": "EXPLICIT_ABSENCE",
    }
    state = {"mvp_project_id": "same-project", "formal_transcription_units": units}
    _prepare_editor_widgets(state)
    assert state["formal_tu1_five_prime_region_mode"] == "不使用独立 5′ region"

    state["formal_tu1_promoter_mode"] = "元件库"
    state.pop("formal_tu1_promoter_name")
    state.pop("formal_tu1_promoter_text")
    _prepare_editor_widgets(state)

    assert state["formal_tu1_promoter_mode"] == "元件库"


def test_widget_hydration_preserves_optional_component_state_after_navigation() -> None:
    units = _persisted_widget_units("saved")
    units[0]["targeting_sequence"] = {
        "display_name": "Targeting",
        "raw_text": "GGCC",
        "source_type": "paste",
    }
    state = {"mvp_project_id": "same-project", "formal_transcription_units": units}

    _prepare_editor_widgets(state)
    for key in list(state):
        if key.startswith("formal_tu") and key != "formal_transcription_units":
            state.pop(key)
    _prepare_editor_widgets(state)

    assert state["formal_tu1_targeting_sequence_enabled"] is True
    assert state["formal_tu1_targeting_sequence_name"] == "Targeting"
    assert state["formal_tu1_targeting_sequence_text"] == "GGCC"
    assert state["formal_tu2_targeting_sequence_enabled"] is False


def test_real_multi_tu_widget_edit_invalidates_the_previous_canonical_result() -> None:
    state = {
        "formal_dual_tu_unit_snapshots": {"TU2": {"input_signature": "old-unit"}},
        "formal_dual_tu_combined_result": {"input_signature": "old-canonical"},
        "formal_cassette_result": {"input_signature": "old-canonical"},
        "formal_cassette_exports": {"fasta": "old"},
        "mvp_vector_result": {"input_signature": "old-canonical"},
        "mvp_current_input_signature": "old-canonical",
        "mvp_inputs_stale": False,
    }

    _invalidate_editor_unit(state, "TU2")

    assert "TU2" not in state["formal_dual_tu_unit_snapshots"]
    assert state["mvp_inputs_stale"] is True
    for key in (
        "formal_dual_tu_combined_result",
        "formal_cassette_result",
        "formal_cassette_exports",
        "mvp_vector_result",
        "mvp_current_input_signature",
    ):
        assert key not in state


@pytest.mark.parametrize(
    ("role", "label"),
    (
        ("targeting_sequence", "靶向序列"),
        ("linker", "linker"),
        ("fusion_tag", "融合标签"),
    ),
)
def test_newly_enabled_optional_component_survives_pre_child_widget_hydration(
    role: str,
    label: str,
) -> None:
    units = _persisted_widget_units("saved")
    units[0]["unit_id"] = "tu1"
    state = {"mvp_project_id": "same-project", "formal_transcription_units": units}
    _prepare_editor_widgets(state)

    enabled_key = f"formal_tu1_{role}_enabled"
    name_key = f"formal_tu1_{role}_name"
    text_key = f"formal_tu1_{role}_text"
    assert state[enabled_key] is False
    assert name_key not in state
    assert text_key not in state

    # Streamlit applies the checkbox transition before the newly conditional
    # name/text widgets render on the following rerun.
    state[enabled_key] = True
    _prepare_editor_widgets(state)

    assert state[enabled_key] is True
    rendered = _render_optional_editor(state, units[0], role, label)
    assert rendered == {"display_name": label, "raw_text": ""}
    assert state[name_key] == label
    assert state[text_key] == ""


@pytest.mark.parametrize("role", ("targeting_sequence", "linker", "fusion_tag"))
def test_newly_disabled_optional_component_remains_user_owned_during_hydration(role: str) -> None:
    units = _persisted_widget_units("saved")
    units[0][role] = {
        "display_name": role,
        "raw_text": "GGCC",
        "source_type": "paste",
    }
    state = {"mvp_project_id": "same-project", "formal_transcription_units": units}
    _prepare_editor_widgets(state)

    enabled_key = f"formal_tu1_{role}_enabled"
    assert state[enabled_key] is True
    state[enabled_key] = False
    _prepare_editor_widgets(state)

    assert state[enabled_key] is False


def test_multi_tu_widget_hydration_refreshes_when_saved_state_marker_changes() -> None:
    first = _persisted_widget_units("saved-a")
    second = _persisted_widget_units("saved-b")
    state = {"mvp_project_id": "same-project", "formal_transcription_units": first}

    _prepare_editor_widgets(state)
    old_marker = state["_formal_multi_tu_widget_state_marker"]
    state["formal_transcription_units"] = second
    state["formal_tu1_cds_text"] = "stale-edit"
    _prepare_editor_widgets(state)

    assert state["_formal_multi_tu_widget_state_marker"] != old_marker
    assert state["formal_tu1_cds_text"] == "saved-bTU1cds"
    assert state["formal_tu2_five_prime_region_text"] == "saved-bTU2five_prime_region"
    assert all(_widget_values(state, second).values())


def test_same_project_identical_payload_reopen_rehydrates_stale_widgets_through_real_restore() -> None:
    reopened = _persisted_widget_units("reopened")
    state = {"mvp_project_id": "same-project", "formal_transcription_units": deepcopy(reopened)}
    _prepare_editor_widgets(state)
    state["formal_tu1_promoter_text"] = "unsaved-before-reopen"
    state["formal_tu1_five_prime_region_text"] = "STALE_UNSAVED_5PRIME"
    state["formal_tu1_cds_text"] = "STALE_UNSAVED_CDS"
    state["formal_tu1_3_prime_regulatory_region_text"] = "STALE_UNSAVED_3REG"
    marker_before_reopen = state["_formal_multi_tu_widget_state_marker"]

    result = {
        "project_id": "same-project",
        "project_name": "Same project reopen",
        "unit_order": ["TU1", "TU2"],
        "input_signature": "same-persisted-signature",
        "formal_project_context": {"host_key": "Rice", "current_step": 3},
        "original_input": {"expression_units": reopened},
    }
    _reopen_dual_tu_result(state, result)
    assert [unit["unit_id"] for unit in state["formal_transcription_units"]] == ["TU1", "TU2"]
    assert [unit["promoter"]["raw_text"] for unit in state["formal_transcription_units"]] == [
        "reopenedTU1promoter",
        "reopenedTU2promoter",
    ]
    assert [unit["five_prime_region"]["raw_text"] for unit in state["formal_transcription_units"]] == [
        "reopenedTU1five_prime_region",
        "reopenedTU2five_prime_region",
    ]
    assert [unit["cds"]["raw_text"] for unit in state["formal_transcription_units"]] == [
        "reopenedTU1cds",
        "reopenedTU2cds",
    ]
    assert [unit["3_prime_regulatory_region"]["raw_text"] for unit in state["formal_transcription_units"]] == [
        "reopenedTU13_prime_regulatory_region",
        "reopenedTU23_prime_regulatory_region",
    ]
    assert state.get("_formal_multi_tu_widget_state_marker") is None
    assert marker_before_reopen.startswith("same-project:")
    _prepare_editor_widgets(state)

    assert state["mvp_project_id"] == "same-project"
    values = _widget_values(state, reopened)
    assert all(values.values())
    assert values["formal_tu1_promoter_text"] == "reopenedTU1promoter"
    assert values["formal_tu1_five_prime_region_text"] == "reopenedTU1five_prime_region"
    assert values["formal_tu1_cds_text"] == "reopenedTU1cds"
    assert values["formal_tu1_3_prime_regulatory_region_text"] == (
        "reopenedTU13_prime_regulatory_region"
    )
    assert values["formal_tu1_promoter_text"] != "unsaved-before-reopen"
    assert values["formal_tu1_five_prime_region_text"] != "STALE_UNSAVED_5PRIME"
    assert values["formal_tu1_cds_text"] != "STALE_UNSAVED_CDS"
    assert values["formal_tu1_3_prime_regulatory_region_text"] != "STALE_UNSAVED_3REG"
    assert values["formal_tu2_3_prime_regulatory_region_text"] == (
        "reopenedTU23_prime_regulatory_region"
    )


def test_completed_editor_reopen_preserves_hydrated_multi_tu_assembly() -> None:
    units = _persisted_widget_units("completed")
    assembly = {
        "project_id": "completed-editor",
        "project_type": "dual_tu",
        "result_kind": "MULTI_TU_EXPRESSION_ASSEMBLY",
        "input_signature": "assembly-signature",
        "combined_construct": {"sequence_sha256": "assembly-sha"},
    }
    state = {"formal_dual_tu_combined_result": deepcopy(assembly)}
    result = {
        "project_id": "completed-editor",
        "project_name": "Completed editor",
        "unit_order": ["TU1", "TU2"],
        "input_signature": "complete-plasmid-signature",
        "formal_editor_restoration_eligible": True,
        "formal_project_context": {"host_key": "Tobacco", "current_step": 6},
        "original_input": {"expression_units": units},
    }

    _reopen_dual_tu_result(state, result)

    assert state["formal_dual_tu_combined_result"] == assembly
    assert state["formal_cassette_result"] == assembly
    assert state["mvp_vector_result"] is result


def test_generated_multi_tu_editor_inputs_save_and_reopen_through_existing_draft_state(
    tmp_path: Path,
) -> None:
    result = _current_result_with_four_roles()
    repository = PlantProjectDraftRepository(tmp_path / "drafts")
    saved = save_formal_project_draft(
        project_name="Current Multi-TU",
        project_id=result["project_id"],
        workflow_type="multi_tu",
        current_step=4,
        design_session=DesignSession(step=4, host="Rice"),
        formal_state={"formal_transcription_units": result["original_input"]["expression_units"]},
        project_definition={"project_name": "Current Multi-TU", "plant_host": "Rice"},
        repository=repository,
    )

    reopened = formal_draft_snapshot(repository.load(saved.project_id))
    assert reopened["current_step"] == 4
    assert reopened["design_session"]["step"] == 4
    reopened_units = reopened["formal_state"]["formal_transcription_units"]
    expected_units = result["original_input"]["expression_units"]
    assert [unit["unit_id"] for unit in reopened_units] == ["TU1", "TU2"]
    assert [unit["orientation"] for unit in reopened_units] == ["forward", "reverse"]
    for role in (
        "promoter",
        "five_prime_region",
        "cds",
        "3_prime_regulatory_region",
    ):
        assert [unit[role] for unit in reopened_units] == [
            unit[role] for unit in expected_units
        ]

    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    step_three = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == "_render_dual_tu_step_3"
    )
    persistence_calls = [
        node
        for node in ast.walk(step_three)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_persist_generated_multi_tu_step_four"
    ]
    assert len(persistence_calls) == 1
    assert len(persistence_calls[0].args) == 1
    assert isinstance(persistence_calls[0].args[0], ast.Name)
    assert persistence_calls[0].args[0].id == "ds"
