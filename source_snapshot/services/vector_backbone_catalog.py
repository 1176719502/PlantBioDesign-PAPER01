"""Read-only Step 4 catalog backed by reviewed vector-asset contracts."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from core.vector_asset_contracts_v1 import (
    classify_vector_asset,
    load_vector_asset_contracts,
    vector_asset_contract,
)
from services.vector_asset_admission import assess_vector_workflow, normalize_workflow_id


CATALOG_SOURCE_LABEL = "现有正式载体合同和本地 GenBank 记录"

_OPERATION_LABELS = {
    "exact_insertion": "精确插入",
    "exact_replacement": "精确替换",
    "none": "暂无正式操作合同",
}
_WORKFLOW_LABELS = {
    "single_gene_rice_alb": "水稻单基因完整载体",
    "single_gene": "单基因完整载体",
    "generic_multi_tu": "通用 Multi-TU 组装",
    "gate3_pathway": "代谢通路 Multi-TU 载体",
    "betalain_gate3": "Betalain Gate 3",
}


def _workflow_reason(contract: Mapping[str, Any], workflow_id: str) -> str:
    workflow = normalize_workflow_id(workflow_id)
    if workflow in set(contract.get("supported_workflows") or []):
        return "现有精确操作合同适用于当前路线。"
    if str(contract.get("asset_kind")) == "reference_vector":
        return "仅供参考：尚无正式插入或替换操作合同。"
    if str(contract.get("asset_kind")) == "hold_unverified_asset":
        return "未验证，只读；不可保存为正式骨架或用于 canonical。"
    if str(contract.get("asset_id")) == "pbi121_af485783_1":
        return "仅限已授权的代谢通路 Multi-TU 或 Betalain Gate 3 固定精确替换路线。"
    return "仅限已审查的 Rice 单基因完整载体路线。"


def catalog_entries(workflow_id: str, *, step3_ready: bool = True) -> list[dict[str, Any]]:
    """Return compact catalog metadata without reading DNA into the UI module."""
    workflow = normalize_workflow_id(workflow_id)
    entries: list[dict[str, Any]] = []
    for contract in load_vector_asset_contracts():
        compatible = (
            bool(contract.get("formal_selection_allowed"))
            and workflow in set(contract.get("supported_workflows") or [])
        )
        selectable = compatible and step3_ready
        action_label = "选择" if selectable else "请先完成第三步" if compatible else "不可选"
        entries.append(
            {
                "asset_id": str(contract["asset_id"]),
                "display_name": str(contract["display_name"]),
                "accession_version": str(contract.get("accession_version") or "本地示例"),
                "length": int(contract["full_sequence_length"]),
                "operation_label": _OPERATION_LABELS[str(contract["operation_kind"])],
                "asset_kind": str(contract["asset_kind"]),
                "applicable_workflows": [
                    _WORKFLOW_LABELS[str(value)]
                    for value in list(contract.get("supported_workflows") or [])
                ],
                "selectable": selectable,
                "compatible": compatible,
                "action_label": action_label,
                "status": "正式可用" if compatible else "受限/只读",
                "reason": _workflow_reason(contract, workflow),
                "source": CATALOG_SOURCE_LABEL,
            }
        )
    return entries


def catalog_backbone_record(asset_id: str, *, project_id: str) -> dict[str, Any]:
    """Parse the reviewed local record through the existing GenBank adapter."""
    contract = vector_asset_contract(asset_id)
    evidence = next(
        (item for item in contract.get("source_evidence") or [] if item.get("local_record_path")),
        None,
    )
    if not evidence:
        raise ValueError(f"Catalog asset {asset_id} has no local source record.")
    source_path = Path(__file__).resolve().parents[1] / str(evidence["local_record_path"])
    try:
        raw_text = source_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Catalog asset {asset_id} source record cannot be read.") from exc
    from services.mvp_sequence_input import analyze_genbank_backbone_input

    record = analyze_genbank_backbone_input(
        raw_text,
        project_id=project_id,
        display_name=str(contract["display_name"]),
        source_kind="formal_catalog",
        source_name=str(source_path.name),
    )
    identity = classify_vector_asset(record)
    if identity.get("asset_id") != asset_id or identity.get("identity_status") != "EXACT_KNOWN_ASSET":
        raise ValueError(f"Catalog asset {asset_id} does not match its reviewed local record.")
    record["formal_catalog_asset_id"] = asset_id
    return record


def persisted_backbone_assessment(record: Mapping[str, Any] | None, *, workflow_id: str) -> dict[str, Any]:
    """Assess restored state without trusting a stored asset ID or display label."""
    if not isinstance(record, Mapping) or not record.get("normalized_sequence"):
        return {"allowed": False, "reason": "尚未选择正式骨架。", "asset_id": None}
    assessment = assess_vector_workflow(record, workflow_id=workflow_id)
    return {
        "allowed": bool(assessment.get("allowed")),
        "reason": str(assessment.get("reason") or "已保存骨架不适用于当前路线。"),
        "asset_id": (assessment.get("identity") or {}).get("asset_id"),
    }
