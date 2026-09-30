from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def _app_helper_namespace() -> dict[str, Any]:
    tree = ast.parse(APP_SOURCE)
    wanted = {
        "_CONTROLLED_UI_LABELS",
        "_ui",
        "_localized_rows",
        "_DEFAULT_SINGLE_GENE_PROJECT_NAME",
        "_DEFAULT_MULTI_TU_PROJECT_NAME",
        "_stable_multi_tu_project_name",
        "_stable_single_gene_project_name",
        "_display_multi_tu_project_name",
    }
    nodes = [
        node
        for node in tree.body
        if (isinstance(node, ast.FunctionDef) and node.name in wanted)
        or (
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id in wanted for target in node.targets)
        )
    ]
    namespace: dict[str, Any] = {
        "Any": Any,
        "Mapping": Mapping,
        "_get_language": lambda: "en",
        "_t": lambda key: {"v1.expression.multi_tu_project": "多转录单元项目"}[key],
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py:r5c", "exec"), namespace)
    return namespace


def test_ui_translation_is_exact_only_and_preserves_user_and_source_text() -> None:
    namespace = _app_helper_namespace()
    ui = namespace["_ui"]

    for value in (
        "番茄启动子项目",
        "我的启动子材料",
        "叶片启动子实验",
        "CaMV35S 启动子来源记录",
        "Oryza sativa / accession 启动子",
    ):
        assert ui(value) == value

    assert ui("通过") == "Passed"
    assert ".replace(" not in ast.get_source_segment(APP_SOURCE, next(
        node for node in ast.parse(APP_SOURCE).body
        if isinstance(node, ast.FunctionDef) and node.name == "_ui"
    ))


def test_display_rows_preserve_values_while_localizing_only_controlled_keys() -> None:
    namespace = _app_helper_namespace()
    rows = namespace["_localized_rows"](
        {"来源记录": "番茄启动子项目", "accession": "AF485783.1"}
    )
    assert rows["Source record"] == "番茄启动子项目"
    assert rows["accession"] == "AF485783.1"


def test_multi_tu_default_internal_name_is_locale_independent() -> None:
    namespace = _app_helper_namespace()
    stable_name = namespace["_stable_multi_tu_project_name"]
    display_name = namespace["_display_multi_tu_project_name"]

    assert stable_name("") == "Multi-TU project"
    assert stable_name("") == stable_name("")
    assert display_name(stable_name("")) == "多转录单元项目"
    assert stable_name("用户指定项目") == "用户指定项目"


def test_sidebar_has_one_reachable_label_for_assisted_design_and_gene_editing() -> None:
    sidebar = APP_SOURCE.split("# Sidebar navigation", 1)[1].split("# Page router", 1)[0]
    assert 'PAGE_AGENT_WORKSPACE: "v1.common.assisted_design"' in APP_SOURCE
    assert '"v1.common.assisted_design": "Assisted Design"' in (ROOT / "locales" / "en.py").read_text(encoding="utf-8")
    assert '"v1.common.assisted_design": "辅助设计"' in (ROOT / "locales" / "zh_cn.py").read_text(encoding="utf-8")
    assert 'f"{_t(\'v1.common.ai_assisted_design\')}</div>"' not in sidebar
    assert 'f"{_t(\'v1.common.gene_editing\')}</div>"' not in sidebar
    assert 'key="nav_agent_page"' in sidebar
    assert 'key="nav_agent_toggle"' in sidebar
    assert "PAGE_CRISPR_WORKFLOW" in sidebar


def test_user_source_call_sites_do_not_pass_arbitrary_values_through_ui() -> None:
    assert "_ui(str(st.session_state.get(\"formal_project_name\") or \"\"))" not in APP_SOURCE
    assert "_ui(entry['display_name'])" not in APP_SOURCE
    assert "_ui(entry['accession_version'])" not in APP_SOURCE
    assert "_ui(_t('v1.expression.source_topology_length_bp" not in APP_SOURCE
    assert "message=_ui(message)" not in APP_SOURCE
    assert "_ui(disabled_reason)" not in APP_SOURCE
    assert "_ui(item.get(\"message\")" not in APP_SOURCE
    assert "_display_product_message(message)" in APP_SOURCE
    assert 'st.session_state["formal_project_name"] = stable_single_name("")' in APP_SOURCE
    assert "escape(str(entry['display_name']))" in APP_SOURCE
    assert "escape(str(entry['accession_version']))" in APP_SOURCE
