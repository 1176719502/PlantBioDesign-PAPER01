from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = (ROOT / "app.py").read_text(encoding="utf-8")


def _helper_namespace() -> dict[str, Any]:
    tree = ast.parse(APP_SOURCE)
    wanted = {
        "_DEFAULT_SINGLE_GENE_PROJECT_NAME",
        "_DEFAULT_MULTI_TU_PROJECT_NAME",
        "_DEFAULT_PATHWAY_PROJECT_NAME",
        "_stable_single_gene_project_name",
        "_stable_multi_tu_project_name",
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
    namespace: dict[str, Any] = {"Any": Any}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py:r5d", "exec"), namespace)
    return namespace


def _function_source(name: str) -> str:
    tree = ast.parse(APP_SOURCE)
    node = next(
        item
        for item in tree.body
        if isinstance(item, ast.FunctionDef) and item.name == name
    )
    return ast.get_source_segment(APP_SOURCE, node) or ""


def test_internal_defaults_are_identical_for_en_and_zh_cn() -> None:
    namespace = _helper_namespace()
    stable_single = namespace["_stable_single_gene_project_name"]
    stable_multi = namespace["_stable_multi_tu_project_name"]

    for locale in ("en", "zh-CN"):
        assert stable_single("") == "Plant expression vector project", locale
        assert stable_multi("") == "Multi-TU project", locale
        assert stable_single("", "ALB") == "ALB", locale
        assert stable_multi("") == "Multi-TU project", locale


def test_user_entered_project_names_are_not_translated_or_replaced() -> None:
    namespace = _helper_namespace()
    stable_single = namespace["_stable_single_gene_project_name"]
    stable_multi = namespace["_stable_multi_tu_project_name"]

    for value in ("中文项目", "English project", "Plant expression vector project"):
        assert stable_single(value) == value
        assert stable_multi(value) == value


def test_all_internal_default_name_paths_use_stable_helpers_or_constants() -> None:
    expected = {
        "_start_blank_design": (
            "_stable_single_gene_project_name",
            "_stable_multi_tu_project_name",
        ),
        "_restore_mvp_result": ("_stable_single_gene_project_name",),
        "_restore_dual_tu_result": ("_stable_multi_tu_project_name",),
        "_render_dual_tu_step_3": ("_stable_multi_tu_project_name",),
        "_render_dual_tu_step_4": ("_stable_multi_tu_project_name",),
        "_render_step_4_cassette": ("_stable_single_gene_project_name",),
        "_generate_complete_plasmid": ("_stable_single_gene_project_name",),
    }
    for function_name, required_tokens in expected.items():
        source = _function_source(function_name)
        assert source, function_name
        for token in required_tokens:
            assert token in source, (function_name, token)

    pathway_source = _function_source("_render_step_5_complete")
    assert "_DEFAULT_PATHWAY_PROJECT_NAME" in pathway_source


def test_no_locale_translation_call_can_assign_project_name_internal_state() -> None:
    tree = ast.parse(APP_SOURCE)
    violations: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        targets = [target for target in node.targets if isinstance(target, ast.Subscript)]
        if not any(
            isinstance(target.slice, ast.Constant)
            and target.slice.value == "formal_project_name"
            for target in targets
        ):
            continue
        if any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "_t" for call in ast.walk(node.value)):
            violations.append(node.lineno)
    assert not violations


def test_project_name_fallback_does_not_change_canonical_payload() -> None:
    namespace = _helper_namespace()
    stable_single = namespace["_stable_single_gene_project_name"]
    stable_multi = namespace["_stable_multi_tu_project_name"]
    canonical = {
        "sequence": "ATGAAATAA",
        "feature_rows": [{"type": "CDS", "start": 1, "end": 9}],
    }
    en_metadata = {
        "project_name": stable_single(""),
        "canonical": canonical,
    }
    zh_metadata = {
        "project_name": stable_single(""),
        "canonical": canonical,
    }
    assert en_metadata == zh_metadata
    assert stable_multi("") == stable_multi("")
