"""R5 regression tests for structured report coordinate suffix localization."""

from __future__ import annotations

from tests.test_r3_ui_corrections import _load_app_helpers


def test_zh_feature_coordinates_accept_label_and_optional_list_marker() -> None:
    preview = _load_app_helpers(
        "_localized_formal_report_preview", language="zh-CN"
    )["_localized_formal_report_preview"]
    report = "\n".join([
        "## Map and Feature Summary",
        "来源：1..11778 (1-based inclusive), strand 1",
        "- 正向：28..808 (1-based inclusive), strand -1",
        "- forward inclusive strand Project: 809..900 (1-based inclusive), strand 1",
        "## Technical Identities, Hashes and Manifest",
        "Project: forward inclusive strand Project",
        "Project: 1..11778 (1-based inclusive), strand 1",
        "- Project: 1..11778 (1-based inclusive), strand 1",
        "Source accession: AF234296.1",
        "ReportSnapshot ID: report-project-forward-001",
        "Canonical SHA-256: " + "ab" * 32,
        "Sequence: ATGCCCTAA",
    ])

    localized = preview(report)
    assert "来源：1..11778（1-based 闭区间），链 1" in localized
    assert "- 正向：28..808（1-based 闭区间），链 -1" in localized
    assert "- forward inclusive strand Project: 809..900（1-based 闭区间），链 1" in localized
    assert "(1-based inclusive), strand" not in localized.split("## 技术标识、哈希与清单")[0]
    assert "项目：forward inclusive strand Project" in localized
    assert "项目：1..11778 (1-based inclusive), strand 1" in localized
    assert "- 项目：1..11778 (1-based inclusive), strand 1" in localized
    assert "来源 accession：AF234296.1" in localized
    assert "ReportSnapshot ID：report-project-forward-001" in localized
    assert "ab" * 32 in localized and "ATGCCCTAA" in localized


def test_en_zh_en_feature_coordinates_preserve_names_and_numbers() -> None:
    namespace = _load_app_helpers(
        "_localized_formal_report_preview", language="en"
    )
    preview = namespace["_localized_formal_report_preview"]
    report = "\n".join([
        "## Map and Feature Summary",
        "Source: 1..11778（1-based 闭区间），链 1",
        "- forward: 28..808（1-based 闭区间），链 -1",
        "- strand inclusive Project forward: 809..900 (1-based inclusive), strand 1",
        "## Project and Design Summary",
        "Project: strand inclusive Project forward",
    ])

    english = preview(report)
    assert "Source: 1..11778 (1-based inclusive), strand 1" in english
    assert "- forward: 28..808 (1-based inclusive), strand -1" in english
    assert "- strand inclusive Project forward: 809..900 (1-based inclusive), strand 1" in english
    assert "Project: strand inclusive Project forward" in english

    namespace["_get_language"] = lambda: "zh-CN"
    chinese = preview(english)
    assert "Source: 1..11778（1-based 闭区间），链 1" in chinese
    assert "- forward: 28..808（1-based 闭区间），链 -1" in chinese
    assert "- strand inclusive Project forward: 809..900（1-based 闭区间），链 1" in chinese
    assert "项目：strand inclusive Project forward" in chinese

    namespace["_get_language"] = lambda: "en"
    assert preview(report) == english
