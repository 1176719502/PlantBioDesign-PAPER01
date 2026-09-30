from __future__ import annotations

import ast
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from mvp_app import generate_complete_vector, load_real_case
from core.design_session import DesignSession
from core.i18n import translate
from locales import LOCALES
from services.formal_project_definition_lifecycle import (
    active_project_definition_summary,
    APPLICATION_MODES,
    INDUCIBILITY_REQUIREMENTS,
    PROJECT_DEFINITION_SOURCE,
    TISSUE_SPECIFICITY_REQUIREMENTS,
    TRANSIENT_EXPRESSION_SYSTEMS,
    construct_review_basis,
    is_induction_notes_active,
    is_tissue_target_active,
    is_transient_system_active,
    normalize_project_definition,
    project_definition_from_context,
    requires_construct_review,
)
from services.formal_project_persistence import (
    FORMAL_PRODUCT_NAVIGATION_STATE_KEY,
    PRODUCT_SURFACE_AGENT,
    PRODUCT_SURFACE_EXPRESSION,
    formal_project_last_active_surface,
    record_formal_project_active_surface,
)
from services.mvp_single_gene_persistence import (
    MvpSingleGenePersistenceError,
    open_mvp_single_gene_design,
    save_mvp_single_gene_design,
)
from services.plant_project_draft_repository import PlantProjectDraftRepository
from services.plant_project_draft_schema import PlantProjectDraftError
from tests.helpers.fake_streamlit import FakeStreamlit, FakeStreamlitContext


ROOT = Path(__file__).resolve().parents[1]


def _zh_t(key: str, **kwargs: Any) -> str:
    return translate(key, language="zh-CN", **kwargs)


def _app_functions(*names: str, namespace: dict[str, Any]) -> dict[str, Any]:
    namespace.setdefault("_t", _zh_t)
    namespace.setdefault("_get_language", lambda: "zh-CN")
    namespace.setdefault("_LOCALES", LOCALES)
    namespace.setdefault("_ui", lambda value: value)
    namespace.setdefault("_DESIGN_SCENARIO_LABELS", {
        "standard_plant_expression_vector": "v1.expression.standard_plant_expression_vector",
        "metabolic_pathway_multi_tu_vector": "v1.expression.metabolic_pathway_multi_tu_vector",
    })
    namespace.setdefault("_PROJECT_MODE_LABELS", {
        "稳定遗传转化": "v1.expression.stable_genetic_transformation",
        "瞬时表达": "v1.expression.transient_expression",
        "尚未确定": "v1.expression.not_yet_determined",
    })
    namespace.setdefault("_APPLICATION_MODE_VALUES", ("稳定遗传转化", "瞬时表达", "尚未确定"))
    namespace.setdefault("_TRANSIENT_SYSTEM_VALUES", ("农杆菌介导的植物组织瞬时表达", "植物原生质体瞬时转染", "其他瞬时表达体系", "尚未确定"))
    namespace.setdefault("_TISSUE_REQUIREMENT_VALUES", ("无特定组织或器官限制", "组织或器官特异性表达", "尚未确定"))
    namespace.setdefault("_INDUCIBILITY_VALUES", ("无特定诱导要求", "需要诱导型表达", "尚未确定"))
    namespace.setdefault("_APPLICATION_MODE_LABELS", {
        "稳定遗传转化": "v1.expression.application_mode_stable",
        "瞬时表达": "v1.expression.application_mode_transient",
        "尚未确定": "v1.expression.application_mode_undetermined",
    })
    namespace.setdefault("_TRANSIENT_SYSTEM_LABELS", {
        "农杆菌介导的植物组织瞬时表达": "v1.expression.transient_agrobacterium",
        "植物原生质体瞬时转染": "v1.expression.transient_protoplast",
        "其他瞬时表达体系": "v1.expression.transient_other",
        "尚未确定": "v1.expression.application_mode_undetermined",
    })
    namespace.setdefault("_TISSUE_REQUIREMENT_LABELS", {
        "无特定组织或器官限制": "v1.expression.no_specific_tissue_organ_restrictions",
        "组织或器官特异性表达": "v1.expression.tissue_or_organ_specific_expression",
        "尚未确定": "v1.expression.not_yet_determined",
    })
    namespace.setdefault("_INDUCIBILITY_LABELS", {
        "无特定诱导要求": "v1.expression.no_specific_induction_requirements",
        "需要诱导型表达": "v1.expression.inducible_expression_required",
        "尚未确定": "v1.expression.not_yet_determined",
    })
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    ]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    return {name: namespace[name] for name in names}


def _definition(**updates: str) -> dict[str, str]:
    value = {
        "project_name": "第一步状态生命周期项目",
        "plant_host": "Rice (O. sativa)",
        "material": "Kitaake",
        "application_mode": "瞬时表达",
        "transient_expression_system": "农杆菌介导的植物组织瞬时表达",
        "tissue_specificity_requirement": "组织或器官特异性表达",
        "tissue_target": "种子",
        "inducibility_requirement": "无特定诱导要求",
        "induction_notes": "",
        "localization_target": "叶绿体",
        "data_source": PROJECT_DEFINITION_SOURCE,
    }
    value.update(updates)
    return value


def _context(definition: dict[str, str], *, status: str = "current") -> dict[str, Any]:
    return {
        "host_key": definition["plant_host"],
        "expression_target": "项目定义摘要",
        "project_definition": deepcopy(definition),
        "construct_review_basis": construct_review_basis(definition),
        "construct_review_status": status,
        "current_step": 6,
    }


def test_project_resume_surface_is_bounded_project_metadata(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "resume-projects")
    draft = repository.create_blank(project_name="Resume project")
    draft.project_id = "resume-project"
    draft = repository.save(draft)
    original_updated_at = draft.updated_at

    assert formal_project_last_active_surface(
        draft.project_id, repository=repository
    ) == PRODUCT_SURFACE_EXPRESSION
    assert record_formal_project_active_surface(
        draft.project_id, PRODUCT_SURFACE_AGENT, repository=repository
    ) is True
    assert record_formal_project_active_surface(
        draft.project_id, PRODUCT_SURFACE_AGENT, repository=repository
    ) is False
    assert formal_project_last_active_surface(
        draft.project_id, repository=repository
    ) == PRODUCT_SURFACE_AGENT

    saved = repository.load(draft.project_id)
    assert saved.updated_at == original_updated_at
    assert saved.manual_review_state[FORMAL_PRODUCT_NAVIGATION_STATE_KEY] == {
        "schema_version": "1.0.0",
        "project_id": draft.project_id,
        "last_active_surface": PRODUCT_SURFACE_AGENT,
    }
    assert saved.workflow_type == draft.workflow_type
    assert saved.canonical_construct_runtime == draft.canonical_construct_runtime


@pytest.mark.parametrize(
    "payload",
    (
        {"schema_version": "1.0.0", "project_id": "other-project", "last_active_surface": PRODUCT_SURFACE_AGENT},
        {"schema_version": "1.0.0", "project_id": "resume-project", "last_active_surface": "arbitrary-route"},
        {"schema_version": "future", "project_id": "resume-project", "last_active_surface": PRODUCT_SURFACE_AGENT},
        "malformed",
    ),
)
def test_project_resume_surface_fails_closed_for_stale_or_malformed_metadata(
    tmp_path: Path, payload: object
) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "resume-projects")
    draft = repository.create_blank(project_name="Resume project")
    draft.project_id = "resume-project"
    draft.manual_review_state[FORMAL_PRODUCT_NAVIGATION_STATE_KEY] = payload
    repository.save(draft)

    assert formal_project_last_active_surface(
        draft.project_id, repository=repository
    ) == PRODUCT_SURFACE_EXPRESSION


def test_project_resume_surface_rejects_arbitrary_destination(tmp_path: Path) -> None:
    repository = PlantProjectDraftRepository(tmp_path / "resume-projects")
    draft = repository.create_blank(project_name="Resume project")
    draft.project_id = "resume-project"
    repository.save(draft)

    with pytest.raises(PlantProjectDraftError, match="Unsupported product navigation"):
        record_formal_project_active_surface(
            draft.project_id, "../../Injected Route", repository=repository
        )


def test_current_field_options_and_conditional_summary_are_independent() -> None:
    assert APPLICATION_MODES == ("稳定遗传转化", "瞬时表达", "尚未确定")
    assert TRANSIENT_EXPRESSION_SYSTEMS[-1] == "尚未确定"
    assert TISSUE_SPECIFICITY_REQUIREMENTS == ("无特定组织或器官限制", "组织或器官特异性表达", "尚未确定")
    assert INDUCIBILITY_REQUIREMENTS == ("无特定诱导要求", "需要诱导型表达", "尚未确定")

    inducible_only = _definition(
        tissue_specificity_requirement="无特定组织或器官限制",
        inducibility_requirement="需要诱导型表达",
        induction_notes="用户记录的诱导系统",
        tissue_target="种子",
    )
    assert not is_tissue_target_active(inducible_only)
    assert is_induction_notes_active(inducible_only)
    assert "种子" not in active_project_definition_summary(inducible_only)
    assert "用户记录的诱导系统" in active_project_definition_summary(inducible_only)

    tissue_and_inducible = _definition(inducibility_requirement="需要诱导型表达")
    assert is_tissue_target_active(tissue_and_inducible)
    assert is_induction_notes_active(tissue_and_inducible)
    assert is_transient_system_active(tissue_and_inducible)


@pytest.mark.parametrize(
    ("legacy", "expected"),
    [
        (
            {"application_mode": "稳定转化", "expression_mode": "组成型表达"},
            {
                "application_mode": "稳定遗传转化",
                "tissue_specificity_requirement": "无特定组织或器官限制",
                "inducibility_requirement": "无特定诱导要求",
                "compatibility_review_required": "false",
            },
        ),
        (
            {"application_mode": "瞬时", "expression_mode": "组织或器官特异表达"},
            {
                "application_mode": "瞬时表达",
                "tissue_specificity_requirement": "组织或器官特异性表达",
                "inducibility_requirement": "尚未确定",
                "compatibility_review_required": "false",
            },
        ),
        (
            {"application_mode": "原生质体", "expression_mode": "诱导型表达"},
            {
                "application_mode": "瞬时表达",
                "transient_expression_system": "植物原生质体瞬时转染",
                "tissue_specificity_requirement": "尚未确定",
                "inducibility_requirement": "需要诱导型表达",
                "compatibility_review_required": "false",
            },
        ),
    ],
)
def test_legacy_application_and_expression_modes_map_without_data_loss(
    legacy: dict[str, str], expected: dict[str, str]
) -> None:
    normalized = normalize_project_definition(legacy)
    assert {key: normalized[key] for key in expected} == expected
    assert normalized["legacy_application_mode"] == legacy["application_mode"]
    assert normalized["legacy_expression_mode"] == legacy["expression_mode"]


def test_ambiguous_legacy_values_require_compatibility_review() -> None:
    normalized = normalize_project_definition(
        {"application_mode": "其他植物表达记录", "expression_mode": "其他表达模式"}
    )
    assert normalized["application_mode"] == "尚未确定"
    assert normalized["tissue_specificity_requirement"] == "尚未确定"
    assert normalized["inducibility_requirement"] == "尚未确定"
    assert normalized["compatibility_review_required"] == "true"
    assert requires_construct_review(normalized, construct_review_basis(normalized))


def test_first_step_conditional_fields_do_not_mix_tissue_and_induction_requirements() -> None:
    class _Step1Streamlit(FakeStreamlit):
        def selectbox(self, label: str, options: Any, **kwargs: Any) -> Any:
            key = kwargs.get("key")
            option_list = list(options)
            if key in self.session_state and self.session_state[key] in option_list:
                self.selectbox_calls.append({"label": label, "options": option_list, **kwargs})
                return self.session_state[key]
            return super().selectbox(label, option_list, **kwargs)

        def columns(self, spec: int | list[Any] | tuple[Any, ...], **_kwargs: Any) -> list[FakeStreamlitContext]:
            count = spec if isinstance(spec, int) else len(spec)

            class _Column(FakeStreamlitContext):
                def text_input(self, label: str, value: str = "", **kwargs: Any) -> str:
                    assert self.fake_st is not None
                    return self.fake_st.text_input(label, value=value, **kwargs)

                def selectbox(self, label: str, options: Any, **kwargs: Any) -> Any:
                    assert self.fake_st is not None
                    return self.fake_st.selectbox(label, options, **kwargs)

            return [_Column(self) for _ in range(count)]

    streamlit = _Step1Streamlit()
    streamlit.segmented_control = lambda _label, options, **_kwargs: list(options)[0]
    navigation_calls: list[dict[str, Any]] = []
    session = DesignSession(host="Rice (O. sativa)")
    render = _app_functions(
        "_plant_host_records",
        "_plant_host_storage_value",
        "_plant_host_record",
        "_plant_host_values",
        "_plant_host_label",
        "_host_supports_project_type",
        "_host_workflow_summary",
        "_formal_widget_initial_kwargs",
        "_render_step_1_project",
        namespace={
            "Any": Any,
            "escape": lambda value: str(value),
            "st": streamlit,
            "PROJECT_TYPE_SINGLE_GENE": "single_gene",
            "PROJECT_TYPE_DUAL_TU": "dual_tu",
            "_formal_project_type": lambda: "single_gene",
            "_formal_design_scenario": lambda: "standard_plant_expression_vector",
            "_render_step_navigation": lambda **kwargs: navigation_calls.append(kwargs),
        },
    )["_render_step_1_project"]

    def render_labels(**values: str) -> tuple[set[str], list[dict[str, Any]]]:
        streamlit.selectbox_calls.clear()
        streamlit.text_input_calls.clear()
        streamlit.button_calls.clear()
        navigation_calls.clear()
        streamlit.session_state.update(
            {
                "formal_step1_project_name": "第一步条件显示",
                "formal_step1_host": "Rice (O. sativa)",
                "formal_step1_tissue_target": "种子",
                "formal_step1_induction_notes": "用户记录的诱导系统",
                **values,
            }
        )
        render(session)
        return (
            {call["label"] for call in streamlit.selectbox_calls + streamlit.text_input_calls},
            list(navigation_calls),
        )

    stable_labels, stable_navigation = render_labels(
        formal_step1_application_mode="稳定遗传转化",
        formal_step1_tissue_specificity_requirement="无特定组织或器官限制",
        formal_step1_inducibility_requirement="无特定诱导要求",
    )
    assert "瞬时表达体系（可选）" not in stable_labels
    assert "目标组织或器官 *" not in stable_labels
    assert "诱导条件或系统说明（可选）" not in stable_labels
    assert stable_navigation[-1]["next_enabled"]

    transient_labels, _ = render_labels(
        formal_step1_application_mode="瞬时表达",
        formal_step1_transient_expression_system="植物原生质体瞬时转染",
        formal_step1_tissue_specificity_requirement="无特定组织或器官限制",
        formal_step1_inducibility_requirement="无特定诱导要求",
    )
    assert "瞬时表达体系（可选）" in transient_labels

    tissue_labels, _ = render_labels(
        formal_step1_application_mode="稳定遗传转化",
        formal_step1_tissue_specificity_requirement="组织或器官特异性表达",
        formal_step1_inducibility_requirement="无特定诱导要求",
    )
    assert "目标组织或器官 *" in tissue_labels
    assert "诱导条件或系统说明（可选）" not in tissue_labels

    inducible_labels, _ = render_labels(
        formal_step1_application_mode="稳定遗传转化",
        formal_step1_tissue_specificity_requirement="无特定组织或器官限制",
        formal_step1_inducibility_requirement="需要诱导型表达",
    )
    assert "诱导条件或系统说明（可选）" in inducible_labels
    assert "目标组织或器官 *" not in inducible_labels

    combined_labels, _ = render_labels(
        formal_step1_application_mode="瞬时表达",
        formal_step1_tissue_specificity_requirement="组织或器官特异性表达",
        formal_step1_inducibility_requirement="需要诱导型表达",
    )
    assert {
        "瞬时表达体系（可选）",
        "目标组织或器官 *",
        "诱导条件或系统说明（可选）",
    }.issubset(combined_labels)


def test_first_step_definition_restores_all_widget_values_before_render() -> None:
    definition = _definition()
    result = generate_complete_vector(load_real_case())
    result["formal_project_context"] = _context(definition)
    streamlit = FakeStreamlit()
    saved_sessions: list[Any] = []
    functions = _app_functions(
        "_project_definition_expression_target",
        "_formal_step3_custom_input_label",
        "_restored_formal_project_context",
        "_restore_mvp_result",
        namespace={
            "Any": Any,
            "Mapping": Mapping,
            "st": streamlit,
            "_FORMAL_STEP3_CUSTOM_INPUT_LABELS": {
                "paste": "粘贴 DNA/FASTA",
                "upload": "上传 FASTA",
            },
            "_FORMAL_STEP3_CUSTOM_INPUT_REVIEW_LABEL": "需要核对输入来源",
            "PROJECT_TYPE_SINGLE_GENE": "single_gene",
            "PAGE_RESULTS_EXPORT": "results",
            "_controller": lambda: type("Controller", (), {"save": saved_sessions.append})(),
            "_change_page": lambda _page: None,
        },
    )

    functions["_restore_mvp_result"](result, definition["plant_host"])

    assert saved_sessions
    assert streamlit.session_state["formal_step1_project_name"] == definition["project_name"]
    assert streamlit.session_state["formal_step1_host"] == definition["plant_host"]
    assert streamlit.session_state["formal_step1_material"] == definition["material"]
    assert streamlit.session_state["formal_step1_application_mode"] == definition["application_mode"]
    assert streamlit.session_state["formal_step1_transient_expression_system"] == definition["transient_expression_system"]
    assert streamlit.session_state["formal_step1_tissue_specificity_requirement"] == definition["tissue_specificity_requirement"]
    assert streamlit.session_state["formal_step1_tissue_target"] == definition["tissue_target"]
    assert streamlit.session_state["formal_step1_inducibility_requirement"] == definition["inducibility_requirement"]
    assert streamlit.session_state["formal_step1_induction_notes"] == definition["induction_notes"]
    assert streamlit.session_state["formal_step1_localization_target"] == definition["localization_target"]


def test_only_biological_design_background_fields_require_construct_review() -> None:
    baseline = _definition()

    assert not requires_construct_review(_definition(project_name="重命名项目"), construct_review_basis(baseline))
    assert not requires_construct_review(_definition(material="另一实验材料"), construct_review_basis(baseline))
    assert requires_construct_review(_definition(plant_host="Tobacco (N. benthamiana)"), construct_review_basis(baseline))
    assert requires_construct_review(_definition(application_mode="稳定遗传转化"), construct_review_basis(baseline))
    assert requires_construct_review(_definition(transient_expression_system="植物原生质体瞬时转染"), construct_review_basis(baseline))
    assert requires_construct_review(_definition(tissue_specificity_requirement="无特定组织或器官限制"), construct_review_basis(baseline))
    assert requires_construct_review(_definition(tissue_target="叶片"), construct_review_basis(baseline))
    assert requires_construct_review(_definition(inducibility_requirement="需要诱导型表达"), construct_review_basis(baseline))
    assert requires_construct_review(_definition(induction_notes="用户记录的条件"), construct_review_basis(baseline))
    assert requires_construct_review(_definition(localization_target="内质网"), construct_review_basis(baseline))
    assert not requires_construct_review(baseline, construct_review_basis(baseline))


def test_background_change_retains_canonical_result_and_restoring_basis_clears_review() -> None:
    baseline = _definition()
    runtime = {"canonical": "unchanged"}
    result = {
        "project_name": baseline["project_name"],
        "runtime": runtime,
        "input_signature": "signature",
        "formal_project_context": _context(baseline),
    }
    streamlit = FakeStreamlit()
    streamlit.session_state["mvp_vector_result"] = result
    streamlit.session_state["formal_project_name"] = baseline["project_name"]
    streamlit.session_state["formal_project_host"] = baseline["plant_host"]
    streamlit.session_state["formal_step1_host"] = baseline["plant_host"]
    streamlit.session_state["formal_step1_material"] = baseline["material"]
    streamlit.session_state["formal_step1_application_mode"] = baseline["application_mode"]
    streamlit.session_state["formal_step1_transient_expression_system"] = baseline["transient_expression_system"]
    streamlit.session_state["formal_step1_tissue_specificity_requirement"] = baseline["tissue_specificity_requirement"]
    streamlit.session_state["formal_step1_tissue_target"] = baseline["tissue_target"]
    streamlit.session_state["formal_step1_inducibility_requirement"] = baseline["inducibility_requirement"]
    streamlit.session_state["formal_step1_induction_notes"] = baseline["induction_notes"]
    streamlit.session_state["formal_step1_localization_target"] = baseline["localization_target"]
    functions = _app_functions(
        "_formal_project_definition",
        "_project_definition_expression_target",
        "_formal_result_needs_review",
        "_apply_formal_project_definition",
        namespace={
            "Any": Any,
            "st": streamlit,
            "PROJECT_TYPE_DUAL_TU": "dual_tu",
        },
    )

    changed = _definition(inducibility_requirement="需要诱导型表达", induction_notes="用户记录的条件")
    assert functions["_apply_formal_project_definition"](changed) is True
    assert result["runtime"] is runtime
    assert result["input_signature"] == "signature"
    assert result["formal_project_context"]["construct_review_status"] == "needs_review"
    assert functions["_formal_result_needs_review"](result) is True

    assert functions["_apply_formal_project_definition"](baseline) is False
    assert result["runtime"] is runtime
    assert result["formal_project_context"]["construct_review_status"] == "current"
    assert functions["_formal_result_needs_review"](result) is False

    renamed = _definition(project_name="重命名项目", material="另一实验材料")
    assert functions["_apply_formal_project_definition"](renamed) is False
    assert result["runtime"] is runtime
    assert result["project_name"] == "重命名项目"
    assert result["formal_project_context"]["construct_review_status"] == "current"


def test_first_step_confirmation_persists_normalized_definition_without_rewriting_widget_state() -> None:
    definition = _definition(project_name="confirmed formal name")
    streamlit = FakeStreamlit()
    widget_values = {
        "formal_step1_project_name": "current user entry",
        "formal_step1_host": "Rice (O. sativa)",
        "formal_step1_material": "current material",
        "formal_step1_application_mode": definition["application_mode"],
    }
    streamlit.session_state.update(widget_values)
    functions = _app_functions(
        "_project_definition_expression_target",
        "_apply_formal_project_definition",
        namespace={"Any": Any, "st": streamlit},
    )

    assert functions["_apply_formal_project_definition"](definition) is False
    assert {key: streamlit.session_state[key] for key in widget_values} == widget_values
    assert streamlit.session_state["formal_project_definition"]["project_name"] == definition["project_name"]
    assert streamlit.session_state["formal_project_name"] == definition["project_name"]
    assert streamlit.session_state["formal_construct_review_basis"] == construct_review_basis(
        definition
    )


def test_single_gene_snapshot_persists_definition_and_blocks_unreviewed_context(tmp_path: Path) -> None:
    definition = _definition()
    result = generate_complete_vector(load_real_case())
    result["formal_project_context"] = _context(definition)
    repository = PlantProjectDraftRepository(tmp_path / "projects")

    saved = save_mvp_single_gene_design(result, repository=repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=repository)

    assert reopened["formal_project_context"] == result["formal_project_context"]
    assert project_definition_from_context(reopened["formal_project_context"]) == normalize_project_definition(definition)

    stale_context = deepcopy(result)
    stale_context["formal_project_context"]["construct_review_status"] = "needs_review"
    with pytest.raises(MvpSingleGenePersistenceError, match="需要重新审查"):
        save_mvp_single_gene_design(stale_context, repository=repository)
