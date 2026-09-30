from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import mvp_app
from services.mvp_single_gene_persistence import (
    list_mvp_single_gene_designs,
    open_mvp_single_gene_design,
)
from services.plant_project_draft_repository import PlantProjectDraftSummary
from tests.helpers.fake_streamlit import FakeStreamlit


def _summary(project_id: str = "mvp6-project") -> PlantProjectDraftSummary:
    return PlantProjectDraftSummary(
        project_id=project_id,
        project_name="MVP6 测试项目",
        updated_at="2026-07-13T15:00:00Z",
        created_at="2026-07-13T14:00:00Z",
        draft_status="draft",
    )


def _example_result(*, project_id: str = "mvp6-project", project_name: str = "MVP6 测试项目"):
    case = mvp_app.load_real_case()
    cds_input = mvp_app.real_case_cds_input(case)
    records = {
        "promoter": mvp_app._component_record_from_example(
            "promoter", project_id=project_id, case=case
        ),
        "cds": mvp_app._cds_record(cds_input, display_name=mvp_app.COMPONENT_NAMES["cds"]),
        "terminator": mvp_app._component_record_from_example(
            "terminator", project_id=project_id, case=case
        ),
        "backbone": mvp_app._backbone_record_from_example(project_id=project_id, case=case),
    }
    settings = {
        "mode": "insertion",
        "start_coordinate": 2100,
        "end_coordinate": 2101,
        "expected_removed_sequence": "",
        "topology_confirmation": False,
    }
    signature = mvp_app.generation_input_signature(
        records, settings, project_name=project_name
    )
    return mvp_app.generate_complete_vector(
        case,
        cds_input=cds_input,
        input_records=records,
        insertion_settings=settings,
        project_id=project_id,
        project_name=project_name,
        input_signature=signature,
    )


@pytest.fixture
def fake_st(monkeypatch) -> FakeStreamlit:
    fake = FakeStreamlit()
    monkeypatch.setattr(mvp_app, "st", fake)
    return fake


def test_project_home_renders_and_page_config_is_called_once(fake_st, monkeypatch) -> None:
    monkeypatch.setattr(mvp_app, "list_mvp_single_gene_designs", lambda: [])

    mvp_app.main()

    assert fake_st.titles == ["项目首页"]
    assert fake_st.page_config_calls == [{"page_title": "BioDesign Studio", "layout": "wide"}]
    assert "BioDesign Studio 植物表达载体设计" in fake_st.caption_messages


def test_home_new_blank_project_clears_previous_inputs_and_results(fake_st, monkeypatch) -> None:
    monkeypatch.setattr(mvp_app, "list_mvp_single_gene_designs", lambda: [])
    fake_st.session_state.update(
        {
            "mvp_project_id": "old-project",
            "mvp_promoter_text": "AAAA",
            "mvp_vector_result": {"old": True},
            "mvp_inputs_stale": True,
        }
    )
    fake_st.button_values["新建空白单基因项目"] = True

    mvp_app._render_home()

    assert fake_st.session_state["mvp_page"] == mvp_app.PAGE_DESIGN
    assert fake_st.session_state["mvp_project_id"] != "old-project"
    assert fake_st.session_state["mvp_project_name"] == "未命名单基因项目"
    assert "mvp_promoter_text" not in fake_st.session_state
    assert "mvp_vector_result" not in fake_st.session_state
    assert "mvp_inputs_stale" not in fake_st.session_state


def test_home_load_example_project_sets_all_example_inputs(fake_st, monkeypatch) -> None:
    monkeypatch.setattr(mvp_app, "list_mvp_single_gene_designs", lambda: [])
    fake_st.button_values["加载示例项目"] = True

    mvp_app._render_home()

    assert fake_st.session_state["mvp_page"] == mvp_app.PAGE_DESIGN
    assert fake_st.session_state["mvp_promoter_mode"] == "使用示例"
    assert fake_st.session_state["mvp_cds_mode"] == "使用示例"
    assert fake_st.session_state["mvp_terminator_mode"] == "使用示例"
    assert fake_st.session_state["mvp_backbone_mode"] == "使用示例骨架"
    assert fake_st.session_state["mvp_start_coordinate"] == 2100


def test_home_lists_recent_project_and_opens_saved_result(fake_st, monkeypatch) -> None:
    result = _example_result()
    summary = _summary(result["project_id"])
    monkeypatch.setattr(mvp_app, "list_mvp_single_gene_designs", lambda: [summary])
    monkeypatch.setattr(mvp_app, "open_mvp_single_gene_design", lambda _project_id: result)
    fake_st.button_values[f"mvp_open_{summary.project_id}"] = True

    mvp_app._render_home()

    assert any(summary.project_name in str(call["body"]) for call in fake_st.markdown_calls)
    assert fake_st.session_state["mvp_page"] == mvp_app.PAGE_RESULTS
    assert fake_st.session_state["mvp_vector_result"]["input_signature"] == result["input_signature"]
    assert fake_st.session_state["mvp_inputs_stale"] is False


def test_home_delete_requires_confirmation(fake_st, monkeypatch) -> None:
    summary = _summary()
    deleted: list[str] = []
    monkeypatch.setattr(mvp_app, "list_mvp_single_gene_designs", lambda: [summary])
    monkeypatch.setattr(mvp_app, "delete_mvp_single_gene_design", deleted.append)
    fake_st.button_values[f"mvp_delete_{summary.project_id}"] = True

    mvp_app._render_home()

    assert fake_st.session_state["mvp_delete_confirm_project_id"] == summary.project_id
    assert deleted == []
    assert any("确认删除项目" in message for message in fake_st.warning_messages)


def test_home_confirm_delete_removes_only_selected_project(fake_st, monkeypatch) -> None:
    selected = _summary("selected-project")
    other = _summary("other-project")
    deleted: list[str] = []
    monkeypatch.setattr(mvp_app, "list_mvp_single_gene_designs", lambda: [selected, other])
    monkeypatch.setattr(mvp_app, "delete_mvp_single_gene_design", deleted.append)
    fake_st.session_state["mvp_delete_confirm_project_id"] = selected.project_id
    fake_st.button_values["确认删除项目"] = True

    mvp_app._render_home()

    assert deleted == [selected.project_id]
    assert fake_st.session_state["mvp_page"] == mvp_app.PAGE_HOME
    assert other.project_id not in deleted


def test_home_enters_existing_design_workspace(fake_st, monkeypatch) -> None:
    monkeypatch.setattr(mvp_app, "list_mvp_single_gene_designs", lambda: [])
    fake_st.session_state["mvp_project_id"] = "existing-project"
    fake_st.button_values["进入设计工作区"] = True

    mvp_app._render_home()

    assert fake_st.session_state["mvp_page"] == mvp_app.PAGE_DESIGN


def test_design_generates_cassette_then_complete_plasmid_and_routes_to_results(fake_st) -> None:
    mvp_app._reset_to_blank()
    mvp_app._load_all_examples()
    fake_st.session_state["mvp_project_id"] = "mvp6-generation"
    fake_st.session_state["mvp_project_name"] = "MVP6 生成测试"
    fake_st.button_values["生成表达盒"] = True

    mvp_app._render_design()

    cassette = fake_st.session_state["mvp_cassette_result"]
    assert cassette["cassette_length"] == 1750
    fake_st.button_values["生成表达盒"] = False
    fake_st.button_values["生成完整质粒"] = True

    mvp_app._render_design()

    result = fake_st.session_state["mvp_vector_result"]
    assert result["plasmid_length"] == 5950
    assert fake_st.session_state["mvp_page"] == mvp_app.PAGE_RESULTS


def test_results_return_to_design_preserves_all_reopened_inputs(fake_st) -> None:
    result = _example_result()
    mvp_app._restore_reopened_state(deepcopy(result))
    records_before = deepcopy(fake_st.session_state["mvp_loaded_input_records"])
    fake_st.session_state["mvp_design_input_state"]["insertion_settings"][
        "start_coordinate"
    ] = 2101
    for key in (
        "mvp_promoter_mode",
        "mvp_cds_mode",
        "mvp_terminator_mode",
        "mvp_backbone_mode",
        "mvp_start_coordinate",
        "mvp_end_coordinate",
    ):
        fake_st.session_state.pop(key, None)
    fake_st.button_values["返回修改设计"] = True

    mvp_app._render_results()

    assert fake_st.session_state["mvp_page"] == mvp_app.PAGE_DESIGN
    assert fake_st.session_state["mvp_loaded_input_records"] == records_before
    assert fake_st.session_state["mvp_promoter_mode"] == "使用示例"
    assert fake_st.session_state["mvp_cds_mode"] == "使用示例"
    assert fake_st.session_state["mvp_terminator_mode"] == "使用示例"
    assert fake_st.session_state["mvp_backbone_mode"] == "使用示例骨架"
    assert fake_st.session_state["mvp_start_coordinate"] == 2101


@pytest.mark.parametrize("mutation", ["promoter", "cds", "terminator", "backbone", "coordinate"])
def test_core_input_change_marks_existing_result_stale(fake_st, mutation: str) -> None:
    result = _example_result(project_id=f"mvp6-stale-{mutation}")
    mvp_app._restore_reopened_state(deepcopy(result))
    if mutation == "promoter":
        fake_st.session_state["mvp_promoter_mode"] = "粘贴 DNA/FASTA"
        fake_st.session_state["mvp_promoter_text"] = "AACCGGTTAACC"
    elif mutation == "cds":
        fake_st.session_state["mvp_cds_mode"] = "粘贴 DNA/FASTA"
        fake_st.session_state["mvp_cds_text"] = "ATG" + ("GCT" * 24) + "TAA"
    elif mutation == "terminator":
        fake_st.session_state["mvp_terminator_mode"] = "粘贴 DNA/FASTA"
        fake_st.session_state["mvp_terminator_text"] = "TTGGAATTCC"
    elif mutation == "backbone":
        loaded = fake_st.session_state["mvp_loaded_input_records"]
        loaded["backbone"] = dict(
            loaded["backbone"],
            source_kind="upload",
            source_name="changed.gb",
            original_text=str(loaded["backbone"].get("original_text") or "") + "\nCOMMENT changed backbone content",
        )
        fake_st.session_state["mvp_backbone_mode"] = "上传 GenBank"
    else:
        fake_st.session_state["mvp_start_coordinate"] = 2101

    mvp_app._render_design()

    assert fake_st.session_state["mvp_inputs_stale"] is True
    assert fake_st.session_state["mvp_vector_result"]["exports"] == result["exports"]


def test_stale_result_disables_every_old_download(fake_st) -> None:
    result = _example_result(project_id="mvp6-stale-downloads")
    mvp_app._restore_reopened_state(deepcopy(result))
    fake_st.session_state["mvp_inputs_stale"] = True
    fake_st.session_state["mvp_current_input_signature"] = "f" * 64

    mvp_app._render_results()

    assert [call["label"] for call in fake_st.download_button_calls] == [
        "下载表达盒 FASTA",
        "下载完整质粒 FASTA",
        "下载完整质粒 GenBank",
        "导出公司审查包 ZIP",
    ]
    assert all(call["disabled"] is True for call in fake_st.download_button_calls)
    assert all(call["on_click"] == "ignore" for call in fake_st.download_button_calls)


def test_save_return_home_restart_reopen_uses_persisted_runtime_and_bytes(
    fake_st, monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BIODESIGN_PLANT_PROJECT_DRAFT_DIR", str(tmp_path / "drafts"))
    result = _example_result(project_id="mvp6-save-reopen")
    mvp_app._restore_reopened_state(deepcopy(result))
    fake_st.button_values["保存项目"] = True

    mvp_app._render_results()

    assert [item.project_id for item in list_mvp_single_gene_designs()] == [result["project_id"]]
    fake_st.button_values.clear()
    fake_st.session_state["mvp_page"] = mvp_app.PAGE_HOME
    fake_st.button_values[f"mvp_open_{result['project_id']}"] = True
    monkeypatch.setattr(
        mvp_app,
        "generate_complete_vector",
        lambda *args, **kwargs: pytest.fail("reopen must not regenerate the complete plasmid"),
    )
    monkeypatch.setattr(
        mvp_app,
        "generate_expression_cassette",
        lambda *args, **kwargs: pytest.fail("reopen must not regenerate the cassette"),
    )

    mvp_app._render_home()

    reopened = open_mvp_single_gene_design(result["project_id"])
    assert fake_st.session_state["mvp_page"] == mvp_app.PAGE_RESULTS
    assert reopened["exports"]["fasta"]["data"] == result["exports"]["fasta"]["data"]
    assert reopened["exports"]["genbank"]["data"] == result["exports"]["genbank"]["data"]
    assert reopened["runtime"] == result["runtime"]


def test_three_page_chinese_copy_and_legacy_entries_are_absent() -> None:
    source = Path(mvp_app.__file__).read_text(encoding="utf-8")

    for expected in (
        'st.title("项目首页")',
        'st.title("设计工作区")',
        'st.title("结果与导出")',
        'st.subheader("软件校验结果")',
        '"生成表达盒"',
        '"生成完整质粒"',
        '"返回修改设计"',
    ):
        assert expected in source
    for forbidden in ("Readback", "Preview", "Promotion Gate"):
        assert forbidden not in source
    assert source.count("st.set_page_config(") == 1


def test_fake_number_input_matches_session_state_widget_behavior() -> None:
    fake = FakeStreamlit()
    fake.session_state["coordinate"] = 2100

    assert fake.number_input("坐标", key="coordinate", min_value=1) == 2100
    fake.number_input_values["coordinate"] = 2200
    assert fake.number_input("坐标", key="coordinate", min_value=1) == 2200
    assert fake.session_state["coordinate"] == 2200
