from __future__ import annotations

import ast
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from services.plant_host_registry import (
    GENERIC_MULTI_TU_ASSEMBLY,
    SINGLE_GENE_COMPLETE_VECTOR,
)


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "app.py"


def _host_helpers() -> dict[str, Any]:
    source = APP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {
        "_plant_host_records",
        "_plant_host_storage_value",
        "_plant_host_record",
        "_plant_host_values",
        "_plant_host_label",
        "_plant_host_value_for_id",
        "_host_supports_project_type",
        "_host_workflow_summary",
    }
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    namespace: dict[str, Any] = {
        "Any": Any,
        "Mapping": Mapping,
        "PROJECT_TYPE_SINGLE_GENE": "single_gene",
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace


def test_step_one_uses_the_public_plant_host_registry_loader_only() -> None:
    source = APP_PATH.read_text(encoding="utf-8")

    assert "from services.plant_host_registry import list_hosts" in source
    assert "hosts.json" not in source
    assert "_PLANT_HOSTS" not in source
    assert "_PLANT_HOST_LABELS" not in source


def test_step_one_exposes_exactly_the_six_registered_plants() -> None:
    helpers = _host_helpers()
    labels = [helpers["_plant_host_label"](value) for value in helpers["_plant_host_values"]()]

    assert labels == [
        "Rice / Oryza sativa",
        "Tobacco / Nicotiana benthamiana",
        "Maize / Zea mays",
        "Arabidopsis / Arabidopsis thaliana",
        "Tomato / Solanum lycopersicum",
        "Soybean / Glycine max",
    ]
    forbidden = ("Agrobacterium", "E. coli", "Yeast", "Human")
    assert not any(term in " ".join(labels) for term in forbidden)


def test_workflow_contracts_are_enforced_without_a_hidden_route_change() -> None:
    helpers = _host_helpers()
    records = helpers["_plant_host_records"]()
    rice = helpers["_plant_host_value_for_id"]("rice")

    assert helpers["_host_supports_project_type"](rice, "single_gene") is True
    assert helpers["_host_supports_project_type"](rice, "multi_tu") is True
    assert SINGLE_GENE_COMPLETE_VECTOR in records[0]["workflow_levels"]
    tomato = helpers["_plant_host_value_for_id"]("tomato")
    assert helpers["_host_supports_project_type"](tomato, "single_gene") is True
    assert helpers["_host_supports_project_type"](tomato, "multi_tu") is True
    for record in records:
        host = helpers["_plant_host_storage_value"](record)
        assert record["workflow_contracts"][GENERIC_MULTI_TU_ASSEMBLY]["contains_vector"] is False
        if record["host_id"] not in {"rice", "tomato"}:
            assert helpers["_host_supports_project_type"](host, "single_gene") is False
            assert helpers["_host_supports_project_type"](host, "multi_tu") is True
    assert "通用 Multi-TU 组装（不包含载体骨架）" in helpers["_host_workflow_summary"](rice)


def test_unknown_saved_host_is_not_matched_or_allowed_to_continue() -> None:
    helpers = _host_helpers()
    source = APP_PATH.read_text(encoding="utf-8")

    assert helpers["_plant_host_record"]("Unknown legacy host") is None
    assert helpers["_host_supports_project_type"]("Unknown legacy host", "single_gene") is False
    assert "v1.expression.saved_host_not_official_registry_reselect_plant" in source
    assert "and not unknown_host" in source


def test_step_one_navigation_retains_the_existing_save_and_next_gate() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step_one = source.split("def _render_step_1_project", 1)[1].split(
        "def _render_pathway_mapping_step_2", 1
    )[0]

    assert "next_enabled=ready" in step_one
    assert "next_action=advance_step1" in step_one
    assert 'action_id="step1_save_continue"' in step_one


def test_generic_multi_tu_surface_uses_assembly_wording_without_vector_claims() -> None:
    source = APP_PATH.read_text(encoding="utf-8")
    step_strip = source.split("def _render_step_strip", 1)[1].split(
        "def _render_step_navigation", 1
    )[0]
    generic_step4 = source.split("def _render_generic_multi_tu_step_4", 1)[1].split(
        "def _render_dual_tu_step_4", 1
    )[0]
    generic_step5 = source.split("def _render_generic_multi_tu_step_5", 1)[1].split(
        "def _step5_construct_preview_html", 1
    )[0]
    step6_review = source.split("def _render_step_6_review", 1)[1].split(
        "def _render_step_6_complete", 1
    )[0]
    generic_step6 = step6_review.split("if _is_generic_multi_tu_workflow():", 1)[1].split(
        "from services.formal_t_dna_review", 1
    )[0]

    assert "v1.expression.step_short_assembly_settings" in step_strip
    assert "v1.expression.step_4_assembly_setup_canonical_assembly" in generic_step4
    assert "v1.expression.canonical_assembly_summary" in generic_step4
    assert "v1.expression.step_5_canonical_assembly_check" in generic_step5
    assert "v1.expression.result_type_multi_tu_expression_cassette_assembly" in generic_step6
    assert "v1.expression.includes_vector" in generic_step4
    assert "完整构建" not in generic_step4
    assert "载体骨架" not in generic_step4
