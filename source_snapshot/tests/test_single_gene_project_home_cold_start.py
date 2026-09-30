from __future__ import annotations

import ast
from copy import deepcopy
from html import escape
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from typing import Any

from core.i18n import translate
from mvp_app import generate_complete_vector, generation_input_signature
from services.canonical_construct_runtime import active_complete_plasmid_snapshot, active_construct_snapshot
from services.mvp_single_gene_persistence import list_mvp_single_gene_designs, open_mvp_single_gene_design, save_mvp_single_gene_design
from services.plant_project_draft_repository import PlantProjectDraftRepository
from tests.test_company_delivery_package import _alb_demo_result


def _zh_t(key: str, **kwargs: Any) -> str:
    return translate(key, language="zh-CN", **kwargs)


def _function_source(name: str) -> str:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == name)
    return ast.get_source_segment(source, node) or ""


def test_saved_alb_single_gene_record_survives_cold_start_and_is_home_listable(tmp_path: Path) -> None:
    seed = deepcopy(_alb_demo_result())
    settings = dict(
        seed["insertion_settings"],
        start_coordinate=2000,
        end_coordinate=2001,
        t_dna_confirmation={"region": {"start": 11, "end": 4190}, "direction": "lb_to_rb"},
    )
    project_id = "rice-alb-cold-start-acceptance"
    project_name = "水稻 ALB 单基因载体闭环验收"
    result = generate_complete_vector(
        cds_input=seed["cds_input"],
        input_records=seed["input_records"],
        insertion_settings=settings,
        project_id=project_id,
        project_name=project_name,
        input_signature=generation_input_signature(seed["input_records"], settings, project_name=project_name),
    )
    result["formal_project_context"] = {
        "host_key": "",
        "project_definition": {"plant_host": "水稻（Oryza sativa）"},
        "current_step": 6,
    }
    repository = PlantProjectDraftRepository(tmp_path / "plant_drafts")

    saved = save_mvp_single_gene_design(result, repository=repository)
    cold_repository = PlantProjectDraftRepository(repository.storage_dir)
    listed = list_mvp_single_gene_designs(repository=cold_repository)
    reopened = open_mvp_single_gene_design(saved.project_id, repository=cold_repository)
    cassette = active_construct_snapshot(reopened["runtime"])
    plasmid = active_complete_plasmid_snapshot(reopened["runtime"])

    assert any(summary.project_id == saved.project_id for summary in listed)
    assert reopened["project_name"] == "水稻 ALB 单基因载体闭环验收"
    assert cassette["sequence_length"] == 2048
    assert plasmid["sequence_length"] == 6248
    assert reopened["insertion_settings"]["start_coordinate"] == 2000
    assert reopened["insertion_settings"]["end_coordinate"] == 2001
    assert reopened["insertion_settings"]["insertion_orientation"] == "forward"
    assert reopened["insertion_settings"]["t_dna_confirmation"] == {
        "region": {"start": 11, "end": 4190},
        "direction": "lb_to_rb",
    }
    assert plasmid["validation_summary"]["blocking_count"] == 0
    assert plasmid["validation_summary"]["warning_count"] == 0
    assert reopened["exports"] == result["exports"]


def test_home_host_inference_uses_the_persisted_project_definition() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "_infer_plant_host")
    namespace: dict[str, object] = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)

    infer_host = namespace["_infer_plant_host"]
    assert infer_host(
        {"formal_project_context": {"project_definition": {"plant_host": "Rice (O. sativa)"}}}
    ) == "Rice (O. sativa)"
    expected_legacy_labels = {
        "水稻（Oryza sativa）": "Rice (O. sativa)",
        "烟草（Nicotiana benthamiana）": "Tobacco (N. benthamiana)",
        "玉米（Zea mays）": "Maize (Corn)",
        "拟南芥（Arabidopsis thaliana）": "Arabidopsis (A. thaliana)",
        "番茄（Solanum lycopersicum）": "Tomato (S. lycopersicum)",
        "大豆（Glycine max）": "Soybean (G. max)",
    }
    for label, canonical_host in expected_legacy_labels.items():
        assert infer_host(
            {"formal_project_context": {"project_definition": {"plant_host": label}}}
        ) == canonical_host
    assert infer_host(
        {
            "formal_project_context": {
                "host_key": "Rice (O. sativa)",
                "project_definition": {"plant_host": "Tobacco (N. benthamiana)"},
            }
        }
    ) == "Tobacco (N. benthamiana)"
    assert infer_host(
        {"formal_project_context": {"project_definition": {"plant_host": "Unknown plant host"}}}
    ) == ""


def test_project_home_uses_the_persisted_project_name_without_runtime_relabeling() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")

    assert 'display_name = str(summary.project_name or "未命名项目")' in source
    assert 'result.get("project_name")' in source


def test_project_home_display_helpers_format_supported_hosts_and_project_statuses() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    helper_nodes = [
        item
        for item in tree.body
        if (
            isinstance(item, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "_PROJECT_HOME_STANDARD_HOST_LABELS" for target in item.targets)
        )
        or (
            isinstance(item, ast.FunctionDef)
            and item.name in {"_project_home_host_label", "_project_home_type_status_label"}
        )
    ]
    namespace: dict[str, object] = {
        "Any": object,
        "_t": _zh_t,
        "PROJECT_TYPE_GATE3_PATHWAY_DRAFT": "gate3_pathway_draft",
        "PROJECT_TYPE_DUAL_TU": "dual_tu",
    }
    exec(compile(ast.Module(body=helper_nodes, type_ignores=[]), "app.py", "exec"), namespace)

    host_label = namespace["_project_home_host_label"]
    type_status_label = namespace["_project_home_type_status_label"]
    assert host_label("Rice (O. sativa)") == "水稻（Oryza sativa）"
    assert host_label("Custom host") == "Custom host"
    assert host_label("") == _zh_t("design_library.not_recorded")
    assert type_status_label("single_gene", "draft") == "{} · {}".format(
        _zh_t("runtime.project_type_single_gene"), _zh_t("runtime.project_status_draft")
    )
    assert type_status_label("dual_tu", "draft") == "{} · {}".format(
        _zh_t("runtime.project_type_multi_tu"), _zh_t("runtime.project_status_draft")
    )
    assert type_status_label("single_gene", "completed") == "{} · {}".format(
        _zh_t("runtime.project_type_single_gene"), _zh_t("runtime.project_status_completed")
    )


def test_public_project_home_keeps_project_management_and_omits_internal_case_entries() -> None:
    homepage = _function_source("_render_project_home")

    for expected in (
        'v1.project_center.title',
        'v1.project_center.subtitle',
        'v1.project_center.new_single_gene_project',
        'v1.project_center.new_multi_tu_project',
        'v1.project_center.new_project_heading',
        'v1.project_center.recent_projects',
        'pc("v1.common.type") + " / " + pc("v1.common.status")',
        'pc("runtime.last_modified")',
        'pc("v1.common.open")',
    ):
        assert expected in homepage

    for internal_entry in (
        "已验证真实案例",
        "MT-01",
        "MT-02",
        "file_uploader",
        "GenBank 来源文件",
        "验证来源并载入",
        "加载水稻 ALB 示例",
        "加载 HSA/ALB 真实数据案例",
        "加载甜菜红素三酶真实来源案例",
        "重开已保存的甜菜红素 Gate 3 映射",
        "_render_mt01_case_entry",
        "_render_mt02_case_entry",
        "local_registry_verification_adapter",
    ):
        assert internal_entry not in homepage


def test_project_home_keeps_openable_record_when_host_context_is_not_recorded() -> None:
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    node = next(item for item in tree.body if isinstance(item, ast.FunctionDef) and item.name == "_render_project_home")

    class _Column:
        def __init__(self, parent) -> None:
            self.parent = parent

        def button(self, *args, **kwargs) -> bool:
            return False

        def markdown(self, body, **kwargs) -> None:
            self.parent.markdown_calls.append(str(body))

        def caption(self, body, **kwargs) -> None:
            self.parent.caption_calls.append(str(body))

    class _Container:
        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

        def markdown(self, *_args, **_kwargs) -> None:
            return None

        def empty(self) -> None:
            return None

    class _Streamlit:
        def __init__(self) -> None:
            self.markdown_calls: list[str] = []
            self.caption_calls: list[str] = []
            self.warning_calls: list[str] = []
            self.session_state: dict[str, object] = {}

        def markdown(self, body, **kwargs) -> None:
            self.markdown_calls.append(str(body))

        def title(self, *args, **kwargs) -> None:
            return None

        def subheader(self, *args, **kwargs) -> None:
            return None

        def caption(self, body, **kwargs) -> None:
            self.caption_calls.append(str(body))

        def warning(self, body, **kwargs) -> None:
            self.warning_calls.append(str(body))

        def selectbox(self, _label, options, **_kwargs):
            return list(options)[0]

        def radio(self, _label, options, **_kwargs):
            return list(options)[0]

        def button(self, *args, **kwargs) -> bool:
            return False

        def columns(self, spec):
            return [_Column(self) for _ in spec]

        def container(self, **kwargs):
            return _Container()

        def empty(self):
            return _Container()

    fake_st = _Streamlit()
    namespace: dict[str, object] = {
        "Any": object,
        "st": fake_st,
        "_t": _zh_t,
        "_PLANT_HOSTS": ("Rice (O. sativa)", "Tobacco (N. benthamiana)"),
        "_PLANT_HOST_LABELS": {
            "Rice (O. sativa)": "水稻（Oryza sativa）",
            "Tobacco (N. benthamiana)": "烟草（Nicotiana benthamiana）",
        },
        "PROJECT_TYPE_SINGLE_GENE": "single_gene",
        "PROJECT_TYPE_DUAL_TU": "dual_tu",
        "escape": escape,
        "_infer_plant_host": lambda _result: "",
        "_project_home_host_label": lambda host: "未记录" if not host else str(host),
            "_project_home_type_status_label": lambda _project_type, _project_status: "单基因 · 已完成",
            "_project_center_search_input": lambda: "",
            "_start_blank_design": lambda *_args: None,
        "_load_rice_alb_example": lambda: None,
        "_load_rice_hsa_real_case": lambda: None,
        "_open_saved_mvp_project": lambda *_args: None,
    }
    exec(compile(ast.Module(body=[node], type_ignores=[]), "app.py", "exec"), namespace)
    summary = SimpleNamespace(project_id="missing-host", project_name="Persisted project name", updated_at="2026-07-16T21:47:00Z")

    with patch("services.mvp_single_gene_persistence.list_mvp_single_gene_designs", return_value=[summary]), patch(
        "services.mvp_single_gene_persistence.open_mvp_single_gene_design", return_value={"project_id": summary.project_id}
    ), patch("services.mvp_multi_tu_persistence.list_mvp_multi_tu_designs", return_value=[]):
        namespace["_render_project_home"]()

    assert any("Persisted project name" in body for body in fake_st.markdown_calls)
    assert any("未记录" in body for body in fake_st.markdown_calls)
    assert fake_st.warning_calls == []
