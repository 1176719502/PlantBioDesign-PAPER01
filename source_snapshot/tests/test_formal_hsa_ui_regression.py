from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.canonical_construct_runtime import active_complete_plasmid_snapshot, active_construct_snapshot
from services.rice_hsa_ncbi_mvp10_case import build_rice_hsa_real_case


def _app_source() -> str:
    return (Path(ROOT) / "app.py").read_text(encoding="utf-8")


def _app_function(name: str):
    source = _app_source()
    tree = ast.parse(source)
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace: dict[str, object] = {"Any": object}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "app.py", "exec"), namespace)
    return namespace[name]


def _formal_library_records():
    source = _app_source()
    tree = ast.parse(source)
    wanted = {"_display_element_name", "_plant_library_records", "_formal_library_display_records"}
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]

    class _StreamlitState:
        session_state: dict[str, object] = {}

    namespace: dict[str, object] = {
        "Any": object,
        "_PLANT_HOSTS": ("Rice (O. sativa)", "Tobacco (N. benthamiana)"),
        "st": _StreamlitState(),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "app.py", "exec"), namespace)
    registry_parts = {
        "Promoter": [
            {
                "id": 3,
                "name": "CaMV 35S 启动子片段",
                "host": "Tobacco (N. benthamiana)",
                "sequence": "GTCAACATGGTGGAGCACGACACACTTGTCT",
                "length_bp": 31,
            }
        ],
        "CDS": [],
        "Terminator": [
            {
                "id": 11,
                "name": "NOS 终止子核心片段",
                "host": "Rice (O. sativa)",
                "sequence": "GCATGCACGAGATTTCGATTCCACCGCCGCC",
                "length_bp": 31,
            }
        ],
    }
    with patch("services.parts_service.query_registry_parts", side_effect=lambda *, part_types: registry_parts[part_types]):
        candidates = namespace["_plant_library_records"]()
    return candidates, namespace["_formal_library_display_records"](candidates)


def test_formal_hsa_cassette_lengths_use_the_current_canonical_snapshot() -> None:
    result = build_rice_hsa_real_case()
    cassette = active_construct_snapshot(result["runtime"])
    plasmid = active_complete_plasmid_snapshot(result["runtime"])
    cassette_length = _app_function("_canonical_cassette_length")

    assert cassette["sequence_length"] == 2820
    assert plasmid["sequence_length"] == 11778
    assert cassette_length(result, cassette_input_signature=result["cassette_input_signature"]) == cassette["sequence_length"]
    assert cassette_length(result, cassette_input_signature="changed-input") is None


def test_formal_home_uses_persisted_non_hsa_host_context_before_promoter_inference() -> None:
    infer_host = _app_function("_infer_plant_host")

    assert infer_host(
        {
            "formal_project_context": {"host_key": "Arabidopsis thaliana"},
            "input_records": {"promoter": {"normalized_sequence": "A" * 150}},
        }
    ) == "Arabidopsis (A. thaliana)"
    assert infer_host({"formal_project_context": {"host_key": "Unknown legacy host"}}) == ""


def test_pcambia_cold_restore_backfills_only_missing_review_context() -> None:
    restore_context = _app_function("_restored_formal_project_context")
    result = {
        "exact_insertion_record": {
            "workflow_support_status": "supported_rice_alb_single_gene"
        }
    }

    context, definition = restore_context(
        result,
        "Rice (O. sativa)",
        "Rice ALB exact insertion",
    )

    assert context["host_key"] == "Rice (O. sativa)"
    assert context["project_definition"] == definition
    assert context["construct_review_status"] == "current"
    assert context["cds_source_review_status"] == "current"
    assert context["construct_review_basis"]
    assert result["formal_project_context"] == context

    result["formal_project_context"]["construct_review_status"] = "needs_review"
    restored, _definition = restore_context(
        result,
        "Rice (O. sativa)",
        "Rice ALB exact insertion",
    )
    assert restored["construct_review_status"] == "needs_review"


def test_formal_hsa_ui_uses_chinese_labels_and_real_case_status_dimensions() -> None:
    source = _app_source()

    for expected in (
        "植物生物设计",
        "植物表达载体设计",
        "v1.results_final_report.af234296_1_applied_fixed_xbai_27_28",
        "来源真实性",
        "已确认",
        "序列一致性",
        "通过",
        "精确插入合同",
        "已应用",
        "交付用途",
        "专业审查",
        "编码序列（CDS）",
        "3′端元件",
        "CaMV35S 启动子",
        "ALB 编码序列",
        "CaMV 3′ UTR（polyA 信号）",
    ):
        assert expected in source
    assert '"BioDesign Studio</div>"' not in source
    assert 'authenticity_gate["status"] + "："' not in source


def test_formal_library_reads_all_expanded_registry_records_and_exposes_evidence() -> None:
    catalog_records, visible_records = _formal_library_records()
    direct_records = [
        record
        for record in visible_records
        if record["admission_mode"] == "DIRECT_USE"
    ]
    assisted_records = [
        record
        for record in visible_records
        if record["admission_mode"] == "USER_SEQUENCE_ASSISTED"
    ]

    assert len(catalog_records) == len(visible_records) == 171
    assert len(direct_records) == 17
    assert len(assisted_records) == 24
    assert sum(record["library_tier"] == "REFERENCE" for record in visible_records) == 95
    assert sum(record["library_tier"] == "RETIRED" for record in visible_records) == 35
    assert len({record["catalog_record_id"] for record in visible_records}) == 171
    assert all("source_organism" in record for record in visible_records)
    assert all("target_host_species" in record for record in visible_records)
    assert {
        record["canonical_v2_component_id"]
        for record in visible_records
        if record["formal_selectable"]
    } == {"V2-CMP-138", "V2-CMP-144"}
    assert {
        record["registry_component_id"]
        for record in visible_records
        if record["formal_selectable"]
    } == {"PCLV1-PRO-E8-2164", "PCLV1-TER-HSP18-2-250"}
    assert any(record["component_type"] == "vector_backbone" for record in visible_records)
    assert all(
        record["formal_selectable"] is False
        for record in visible_records
        if record["component_type"] == "vector_backbone"
    )


def test_formal_user_workflow_invalidates_outputs_and_keeps_review_zip_out_of_scope() -> None:
    source = _app_source()

    assert 'def _invalidate_formal_snapshots()' in source
    assert 'on_change=_invalidate_formal_snapshots' in source
    assert '"formal_cassette_result"' in source
    assert 'cassette_runtime=cassette_runtime' in source
    assert "v1.results_final_report.expression_cassette_fasta" in source
    assert "v1.results_final_report.project_backup_json" in source
    result_page = source.split("def _render_results_export_content", 1)[1].split(
        "def _plant_library_records", 1
    )[0]
    assert 'review_assessment = assess_professional_review_package(' not in result_page
    assert 'build_professional_review_package(' not in result_page
    assert '"专业审查包 ZIP"' not in result_page
