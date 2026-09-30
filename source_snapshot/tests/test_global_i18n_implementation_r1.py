from __future__ import annotations

from pathlib import Path

from core.i18n import get_language, normalize_language, set_language, translate
from locales import LOCALES


ROOT = Path(__file__).resolve().parents[1]


def test_language_aliases_normalize_to_one_internal_state() -> None:
    assert normalize_language("en") == "en"
    assert normalize_language("EN-US") == "en"
    assert normalize_language("zh") == "zh-CN"
    assert normalize_language("zh_CN") == "zh-CN"
    assert normalize_language("中文") == "zh-CN"
    assert normalize_language("unsupported") == "en"


def test_frozen_locale_keys_are_bilingual_and_nonempty() -> None:
    assert len(LOCALES["en"]) >= 937
    assert len(LOCALES["zh-CN"]) >= 937
    assert set(LOCALES["en"]).issubset(LOCALES["zh-CN"])
    assert all(str(value).strip() for value in LOCALES["en"].values())
    assert all(str(value).strip() for value in LOCALES["zh-CN"].values())


def test_multi_tu_step5_confirmation_action_has_semantic_bilingual_copy() -> None:
    assert translate(
        "v1.expression.confirm_and_view_results", language="en"
    ) == "Confirm and view results"
    assert translate(
        "v1.expression.confirm_and_view_results", language="zh-CN"
    ) == "确认并查看结果"
    assert "v1.expression.save_and_view_results" not in LOCALES["en"]
    assert "v1.expression.save_and_view_results" not in LOCALES["zh-CN"]


def test_session_language_uses_ui_language_key() -> None:
    state: dict[str, str] = {}
    assert get_language(state) == "en"
    assert set_language("中文", state) == "zh-CN"
    assert state["ui_language"] == "zh-CN"
    assert get_language(state) == "zh-CN"


def test_inventory_placeholders_can_be_rendered_without_changing_key_contract() -> None:
    assert translate(
        "v1.crispr.associated_project",
        language="en",
        project_name="Demo",
        project_id="project-1",
    ) == "Associated project: Demo · project-1"
    assert translate(
        "v1.crispr.associated_project",
        language="zh-CN",
        project_name="示例",
        project_id="project-1",
    ) == "关联项目：示例 · project-1"


def test_agent_entry_surface_resolves_copy_through_the_shared_locale() -> None:
    source = (ROOT / "views" / "AgentWorkspace.py").read_text(encoding="utf-8")

    assert '_t("v1.common.ai_assisted_design")' in source
    assert '"generate_reviewable_candidate_project_confirmed_design_information"' in source
    assert '"select_project_generate_candidate_confirm_manually"' in source
    assert '_t("v1.ai_assisted_design.start_new_project")' in source
    assert '_t("v1.ai_assisted_design.start_existing_project")' in source
    assert "actions = st.columns((1.5, 1.5, 4))" in source


def test_project_center_table_headers_do_not_render_inventory_placeholders() -> None:
    assert translate("runtime.project", language="en") == "Project"
    assert translate("runtime.last_modified", language="en") == "Last modified"
    assert translate("runtime.actions", language="en") == "Actions"
    assert translate("runtime.project", language="zh-CN") == "项目"
    assert translate("runtime.last_modified", language="zh-CN") == "最近修改"
    assert translate("runtime.actions", language="zh-CN") == "操作"
    assert "{...}" not in translate(
        "v1.project_center.last_modified",
        language="en",
        updated="2026-09-21 12:19",
    )


def test_project_center_supported_host_labels_are_bilingual() -> None:
    assert translate("runtime.host_rice", language="en") == "Rice (Oryza sativa)"
    assert translate("runtime.host_rice", language="zh-CN") == "水稻（Oryza sativa）"
    assert translate("runtime.host_tobacco", language="en") == (
        "Tobacco (Nicotiana benthamiana)"
    )
    assert translate("runtime.host_tobacco", language="zh-CN") == (
        "烟草（Nicotiana benthamiana）"
    )
