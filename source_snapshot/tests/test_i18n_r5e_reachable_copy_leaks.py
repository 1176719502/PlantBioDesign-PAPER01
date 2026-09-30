from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.i18n import translate
from services.registry_catalog_ui import catalog_row_ui_state


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def _app_copy_helpers() -> dict[str, Any]:
    tree = ast.parse(APP_SOURCE)
    wanted = {
        "_COMPONENT_LIBRARY_CONTROLLED_LABEL_KEYS",
        "_COMPONENT_LIBRARY_HOST_ALL_VALUE",
        "_component_library_label",
        "_component_library_host_filter_value",
    }
    nodes = [
        node
        for node in tree.body
        if (
            isinstance(node, ast.FunctionDef) and node.name in wanted
        )
        or (
            isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id in wanted
                for target in node.targets
            )
        )
    ]
    namespace: dict[str, Any] = {
        "Any": Any,
        "_t": lambda key: translate(key, language="en"),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py:r5e", "exec"), namespace)
    return namespace


def test_multi_tu_results_count_label_is_bilingual() -> None:
    assert translate("v1.results_final_report.tu_count", language="en") == "TU Count"
    assert translate("v1.results_final_report.tu_count", language="zh-CN") == "TU 数量"
    assert "v1.results_final_report.tu_count" in APP_SOURCE
    assert 'summary_cards.append((_t("v1.results_final_report.tu_count")' in APP_SOURCE
    assert "_t('v1.expression.tu_count')" not in APP_SOURCE[APP_SOURCE.index("def _render_results_export_content"):]


def test_component_library_controlled_copy_is_locale_only() -> None:
    helpers = _app_copy_helpers()
    label = helpers["_component_library_label"]
    assert label("身份待人工复核") == "Identity requires manual review"
    assert label("边界待人工复核") == "Boundary requires manual review"
    assert label("本地内置") == "Bundled locally"
    assert translate("v1.component_library.search_placeholder", language="en") == "Name, exact variant, record ID, or accession"
    assert translate("v1.component_library.search_placeholder", language="zh-CN") == "名称、精确变体、记录 ID 或 accession"
    assert translate("v1.component_library.all_sources_host_contexts", language="en") == "All sources / host contexts"
    assert translate("v1.component_library.all_sources_host_contexts", language="zh-CN") == "全部来源/宿主上下文"
    assert translate("v1.component_library.identity_review_required_badge", language="zh-CN") == "身份待人工复核"


def test_component_library_host_filter_uses_stable_internal_sentinel() -> None:
    helpers = _app_copy_helpers()
    normalize = helpers["_component_library_host_filter_value"]
    sentinel = helpers["_COMPONENT_LIBRARY_HOST_ALL_VALUE"]
    assert sentinel == "__all_sources_host_contexts__"
    assert normalize("全部来源/宿主上下文") == sentinel
    assert normalize(sentinel) == sentinel
    assert normalize("Solanum lycopersicum") == "Solanum lycopersicum"
    assert 'placeholder=_t("v1.component_library.search_placeholder")' in APP_SOURCE
    assert 'v1.component_library.all_sources_host_contexts' in APP_SOURCE


def test_catalog_internal_state_is_unchanged_while_display_is_localized() -> None:
    record: Mapping[str, Any] = {
        "catalog_governance_state": "reviewed/catalog_candidate",
        "formal_selectable": False,
        "identity_review_status": "human_review",
        "boundary_review_status": "human_review",
    }
    state = catalog_row_ui_state(record)
    assert "身份待人工复核" in state["badges"]
    assert state["state_key"] == "catalog_candidate"
    assert _app_copy_helpers()["_component_library_label"](state["badges"][0]) == "Catalog candidate"


def test_pathway_help_and_disabled_reasons_use_locale_keys() -> None:
    for key in (
        "v1.expression.pathway_cds_source_help",
        "v1.expression.pathway_contract_incomplete_help",
        "v1.expression.pathway_mapping_incomplete_help",
        "v1.expression.tu_plan_incomplete_help",
        "v1.expression.tu_plan_save_help",
        "v1.expression.multi_tu_components_incomplete_help",
        "v1.expression.canonical_blocking_items_help",
        "v1.expression.full_plasmid_record_required_help",
        "v1.expression.canonical_record_required_help",
        "v1.expression.full_vector_required_help",
        "v1.expression.full_plasmid_required_for_results_help",
        "v1.expression.current_inputs_must_be_unchanged_help",
    ):
        english = translate(key, language="en")
        chinese = translate(key, language="zh-CN")
        assert english
        assert chinese
        assert not any("\u3400" <= char <= "\u9fff" for char in english)
    assert 'help=_t("v1.expression.pathway_cds_source_help")' in APP_SOURCE
    assert 'disabled_reason=_t("v1.expression.pathway_mapping_incomplete_help")' in APP_SOURCE
