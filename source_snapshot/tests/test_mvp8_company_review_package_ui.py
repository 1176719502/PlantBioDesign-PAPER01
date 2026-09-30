from __future__ import annotations

from copy import deepcopy

import pytest

import mvp_app
from tests.helpers.fake_streamlit import FakeStreamlit


def _result(*, project_id: str = "mvp8-ui", project_name: str = "MVP8 UI 项目") -> dict:
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
    signature = mvp_app.generation_input_signature(records, settings, project_name=project_name)
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
def fake_st(monkeypatch: pytest.MonkeyPatch) -> FakeStreamlit:
    fake = FakeStreamlit()
    monkeypatch.setattr(mvp_app, "st", fake)
    return fake


def _render(fake_st: FakeStreamlit, result: dict, *, stale: bool = False) -> None:
    mvp_app._restore_reopened_state(deepcopy(result))
    if stale:
        fake_st.session_state["mvp_inputs_stale"] = True
        fake_st.session_state["mvp_current_input_signature"] = "f" * 64
    mvp_app._render_results()


def test_company_review_package_button_is_enabled_only_for_complete_current_result(
    fake_st: FakeStreamlit,
) -> None:
    result = _result()
    _render(fake_st, result)
    package_call = next(
        call
        for call in fake_st.download_button_calls
        if call["label"] == "导出公司审查包 ZIP"
    )
    save_call = next(call for call in fake_st.button_calls if call["label"] == "保存项目")

    assert package_call["disabled"] is False
    assert package_call["data"] == result["company_review_package"]["data"]
    assert package_call["file_name"] == result["company_review_package"]["file_name"]
    assert package_call["mime"] == "application/zip"
    assert package_call["on_click"] == "ignore"
    assert save_call["disabled"] is False
    assert any("序列审查、报价和构建评估" in message for message in fake_st.caption_messages)
    assert any("仍需人工确认实际施工方案" in message for message in fake_st.caption_messages)


def test_stale_result_disables_company_package_and_all_existing_downloads(
    fake_st: FakeStreamlit,
) -> None:
    _render(fake_st, _result(project_id="mvp8-ui-stale"), stale=True)

    assert [call["label"] for call in fake_st.download_button_calls] == [
        "下载表达盒 FASTA",
        "下载完整质粒 FASTA",
        "下载完整质粒 GenBank",
        "导出公司审查包 ZIP",
    ]
    assert all(call["disabled"] is True for call in fake_st.download_button_calls)


def test_missing_package_bytes_disables_package_and_save_without_page_exception(
    fake_st: FakeStreamlit,
) -> None:
    result = _result(project_id="mvp8-ui-missing-package")
    result["company_review_package"]["data"] = b""
    _render(fake_st, result)
    package_call = next(
        call
        for call in fake_st.download_button_calls
        if call["label"] == "导出公司审查包 ZIP"
    )
    save_call = next(call for call in fake_st.button_calls if call["label"] == "保存项目")

    assert package_call["disabled"] is True
    assert save_call["disabled"] is True
    assert any("缺少完整的公司审查包字节" in message for message in fake_st.warning_messages)


def test_missing_genbank_export_disables_genbank_and_package_without_traceback(
    fake_st: FakeStreamlit,
) -> None:
    result = _result(project_id="mvp8-ui-missing-genbank")
    result["exports"]["genbank"]["data"] = ""
    _render(fake_st, result)
    calls = {call["label"]: call for call in fake_st.download_button_calls}

    assert calls["下载完整质粒 FASTA"]["disabled"] is False
    assert calls["下载完整质粒 GenBank"]["disabled"] is True
    assert calls["导出公司审查包 ZIP"]["disabled"] is True
    assert any("缺少完整的公司审查包字节" in message for message in fake_st.warning_messages)


def test_no_complete_plasmid_result_shows_safe_empty_state(fake_st: FakeStreamlit) -> None:
    fake_st.session_state["mvp_page"] = mvp_app.PAGE_RESULTS

    mvp_app._render_results()

    assert fake_st.download_button_calls == []
    assert any("还没有完整质粒结果" in message for message in fake_st.warning_messages)


def test_rebuilt_core_input_produces_a_new_valid_package() -> None:
    original = _result(project_id="mvp8-ui-rebuild", project_name="MVP8 重建项目")
    rebuilt_settings = dict(original["insertion_settings"], start_coordinate=2101, end_coordinate=2102)
    rebuilt_signature = mvp_app.generation_input_signature(
        original["input_records"],
        rebuilt_settings,
        project_name=original["project_name"],
    )
    rebuilt = mvp_app.generate_complete_vector(
        cds_input=original["cds_input"],
        input_records=original["input_records"],
        insertion_settings=rebuilt_settings,
        project_id=original["project_id"],
        project_name=original["project_name"],
        input_signature=rebuilt_signature,
    )

    assert rebuilt["input_signature"] != original["input_signature"]
    assert rebuilt["company_review_package"]["data"] != original["company_review_package"]["data"]
    assert rebuilt["company_review_package"]["sha256"] != original["company_review_package"]["sha256"]
