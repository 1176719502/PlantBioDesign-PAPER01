from __future__ import annotations

import ast
from pathlib import Path

from core.vector_asset_contracts_v1 import classify_vector_asset, load_vector_asset_contracts
from services.vector_backbone_catalog import (
    catalog_backbone_record,
    catalog_entries,
    persisted_backbone_assessment,
)
from services.formal_step3_gate import step3_can_continue_to_backbone


def _by_id(workflow: str) -> dict[str, dict]:
    return {row["asset_id"]: row for row in catalog_entries(workflow)}


def test_catalog_uses_existing_contract_sources_and_no_dna_is_embedded() -> None:
    contracts = load_vector_asset_contracts()
    assert {row["asset_id"] for row in contracts} == {
        "pcambia1300_af234296_1", "pbi121_af485783_1", "pbin19_u09365_1", "r229_local_example"
    }
    assert all((Path(__file__).parents[1] / row["source_evidence"][0]["local_record_path"]).is_file() for row in contracts)


def test_pcambia_is_only_selectable_for_rice_single_gene_contract() -> None:
    assert _by_id("rice_alb_single_gene")["pcambia1300_af234296_1"]["selectable"]
    assert not _by_id("formal_single_gene")["pcambia1300_af234296_1"]["selectable"]
    assert not _by_id("generic_multi_tu")["pcambia1300_af234296_1"]["selectable"]


def test_pbi121_is_only_selectable_for_existing_gate3_contract() -> None:
    assert _by_id("gate3")["pbi121_af485783_1"]["selectable"]
    assert not _by_id("formal_single_gene")["pbi121_af485783_1"]["selectable"]
    assert not _by_id("generic_multi_tu")["pbi121_af485783_1"]["selectable"]


def test_pbin19_and_r229_are_never_constructible() -> None:
    for workflow in ("rice_alb_single_gene", "formal_single_gene", "generic_multi_tu", "gate3"):
        rows = _by_id(workflow)
        assert not rows["pbin19_u09365_1"]["selectable"]
        assert not rows["r229_local_example"]["selectable"]


def test_step3_prerequisite_and_contract_incompatibility_have_distinct_actions() -> None:
    awaiting_step3 = {row["asset_id"]: row for row in catalog_entries("rice_alb_single_gene", step3_ready=False)}
    assert awaiting_step3["pcambia1300_af234296_1"]["action_label"] == "请先完成第三步"
    assert awaiting_step3["pbi121_af485783_1"]["action_label"] == "不可选"
    assert "Betalain Gate 3" in awaiting_step3["pbi121_af485783_1"]["reason"]


def _step3_gate(*, current: bool = True, blocking: bool = False, confirmed: bool = True, manual_review: bool = False) -> bool:
    return step3_can_continue_to_backbone(
        cassette_result={"runtime": {"construct": "current"}, "input_signature": "step3-current"},
        current_input_signature="step3-current" if current else "step3-changed",
        findings=(
            [{"status": "需要人工确认", "rule_id": "manual_review"}]
            if manual_review
            else [{"status": "阻断", "rule_id": "blocking"}]
            if blocking
            else []
        ),
        order_confirmed=confirmed,
    )


def test_pcambia_uses_the_same_step3_continue_gate_as_navigation() -> None:
    assert _step3_gate()
    assert _by_id("rice_alb_single_gene")["pcambia1300_af234296_1"]["selectable"] is True
    assert catalog_entries("rice_alb_single_gene", step3_ready=_step3_gate())[0]["selectable"] is True


def test_nonblocking_manual_confirmation_does_not_lock_pcambia() -> None:
    assert _step3_gate(manual_review=True)
    rows = {row["asset_id"]: row for row in catalog_entries("rice_alb_single_gene", step3_ready=_step3_gate(manual_review=True))}
    assert rows["pcambia1300_af234296_1"]["selectable"] is True
    assert rows["pcambia1300_af234296_1"]["status"] == "正式可用"
    assert rows["pcambia1300_af234296_1"]["action_label"] == "选择"


def test_stale_step3_result_or_unconfirmed_order_locks_pcambia() -> None:
    assert not _step3_gate(current=False)
    assert not _step3_gate(confirmed=False)
    for ready in (_step3_gate(current=False), _step3_gate(confirmed=False), _step3_gate(blocking=True)):
        row = {item["asset_id"]: item for item in catalog_entries("rice_alb_single_gene", step3_ready=ready)}[
            "pcambia1300_af234296_1"
        ]
        assert row["selectable"] is False
        assert row["action_label"] == "请先完成第三步"


def test_step3_navigation_and_step4_catalog_call_the_shared_gate() -> None:
    source = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = {
        node.name: ast.get_source_segment(source, node) or ""
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_render_step_3_elements", "_render_step_4_backbone"}
    }
    assert "step3_can_continue_to_backbone" in functions["_render_step_3_elements"]
    assert "step3_can_continue_to_backbone" in functions["_render_step_4_backbone"]


def test_catalog_uses_chinese_operation_and_workflow_labels() -> None:
    rows = _by_id("rice_alb_single_gene")
    assert rows["pcambia1300_af234296_1"]["operation_label"] == "精确插入"
    assert rows["pbin19_u09365_1"]["operation_label"] == "暂无正式操作合同"
    assert rows["pcambia1300_af234296_1"]["applicable_workflows"] == ["水稻单基因完整载体"]


def test_catalog_selection_uses_existing_stable_asset_id_and_exact_record() -> None:
    record = catalog_backbone_record("pcambia1300_af234296_1", project_id="vector01a-test")
    assert record["formal_catalog_asset_id"] == "pcambia1300_af234296_1"
    assert classify_vector_asset(record)["asset_id"] == "pcambia1300_af234296_1"


def test_unknown_or_incompatible_restored_backbone_fails_closed() -> None:
    pcambia = catalog_backbone_record("pcambia1300_af234296_1", project_id="vector01a-test")
    assert not persisted_backbone_assessment(pcambia, workflow_id="generic_multi_tu")["allowed"]
    assert not persisted_backbone_assessment({"normalized_sequence": "ACGT"}, workflow_id="formal_single_gene")["allowed"]
