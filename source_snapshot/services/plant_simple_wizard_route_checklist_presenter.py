from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.plant_simple_wizard_route_schema import (
    HANDOFF_STAGE_ID,
    get_simple_plant_wizard_route,
)


ALLOWED_SLOT_STATUSES: tuple[str, ...] = (
    "missing",
    "filled",
    "missing_provenance",
    "needs_manual_review",
    "optional",
    "not_applicable",
    "blocked",
)

SLOT_LABELS: dict[str, tuple[str, str]] = {
    "target_protein": ("目标蛋白", "Target protein"),
    "gene_or_cds": ("目标基因 / CDS", "Target gene / CDS"),
    "host_plant": ("宿主植物", "Host plant"),
    "expression_context": ("表达场景", "Expression context"),
    "promoter": ("启动子", "Promoter"),
    "signal_or_transit_peptide": ("定位肽 / 转运肽", "Signal or transit peptide"),
    "terminator": ("终止子", "Terminator"),
    "marker_or_reporter": ("标记 / 报告基因", "Marker or reporter"),
    "vector_or_backbone": ("载体 / 骨架", "Vector or backbone"),
    "evidence_records": ("证据来源", "Evidence records"),
    "manual_review_status": ("人工复核状态", "Manual review status"),
    "target_product": ("目标产物", "Target product"),
    "pathway_overview": ("通路概览", "Pathway overview"),
    "pathway_step": ("代谢路线步骤", "Pathway step"),
    "precursor_or_intermediate": ("前体 / 中间体", "Precursor or intermediate"),
    "enzyme_or_gene_candidate": ("酶 / 候选基因", "Enzyme or gene candidate"),
    "subcellular_localization": ("亚细胞定位", "Subcellular localization"),
    "pathway_evidence": ("通路证据来源", "Pathway evidence"),
    "enzyme_evidence": ("酶 / 基因证据来源", "Enzyme evidence"),
    "missing_pathway_steps": ("待补充通路步骤", "Missing pathway steps"),
    "construct_goal": ("构建记录目标", "Construct goal"),
    "gene_list": ("基因列表", "Gene list"),
    "cassette_list": ("表达盒列表", "Cassette list"),
    "cassette_promoters": ("表达盒启动子", "Cassette promoters"),
    "cassette_genes": ("表达盒基因", "Cassette genes"),
    "cassette_terminators": ("表达盒终止子", "Cassette terminators"),
    "cassette_order": ("表达盒顺序", "Cassette order"),
    "module_relationships": ("模块关系", "Module relationships"),
    "regulatory_goal": ("调控目标", "Regulatory goal"),
    "input_signal": ("输入信号", "Input signal"),
    "sensor_or_promoter": ("感应元件 / 启动子", "Sensor or promoter"),
    "transcription_factor_or_regulator": ("TF / 调控因子", "TF or regulator"),
    "cis_element": ("顺式元件", "Cis element"),
    "output_gene": ("输出基因", "Output gene"),
    "expression_pattern": ("表达模式", "Expression pattern"),
    "reporter_or_readout": ("报告读出", "Reporter or readout"),
    "host_context": ("宿主语境", "Host context"),
    "regulatory_evidence": ("调控证据来源", "Regulatory evidence"),
    "uncertainty_or_risk": ("不确定性 / 风险", "Uncertainty or risk"),
}

STATUS_LABELS_ZH: dict[str, str] = {
    "missing": "信息不完整",
    "filled": "草稿已记录",
    "missing_provenance": "需要证据来源",
    "needs_manual_review": "需要人工复核",
    "optional": "可选",
    "not_applicable": "不适用",
    "blocked": "暂时受阻",
}

EVIDENCE_STATUS_LABELS_ZH: dict[str, str] = {
    "not_recorded": "尚未记录来源",
    "recorded": "已有来源记录",
    "needs_provenance": "需要补充来源",
    "not_applicable": "不适用",
}

MANUAL_REVIEW_STATUS_LABELS_ZH: dict[str, str] = {
    "not_started": "尚未复核",
    "not_required": "暂不需要复核",
    "required": "需要人工复核",
    "blocked": "复核暂时受阻",
}

PROVENANCE_SLOT_IDS: tuple[str, ...] = (
    "evidence_records",
    "pathway_evidence",
    "enzyme_evidence",
    "regulatory_evidence",
)

MANUAL_REVIEW_SLOT_IDS: tuple[str, ...] = (
    "manual_review_status",
    "uncertainty_or_risk",
    "missing_pathway_steps",
)

SAFE_BOUNDARY_NOTES_ZH: tuple[str, ...] = (
    "本清单只整理本地项目文档需要补齐的槽位、证据来源和人工复核事项。",
    "下一步动作均为只读模拟标签，不保存数据、不创建项目、不生成交付包。",
    "清单不自动选择生物组件，不判断实验可用性，也不替代人工或公司复核。",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slot_label(slot_id: str) -> tuple[str, str]:
    if slot_id in SLOT_LABELS:
        return SLOT_LABELS[slot_id]
    return slot_id.replace("_", " "), slot_id.replace("_", " ").title()


def _records_by_slot(slot_records: Any) -> dict[str, dict[str, Any]]:
    if isinstance(slot_records, dict):
        rows = [
            {"slot_id": slot_id, **dict(record if isinstance(record, dict) else {"value": record})}
            for slot_id, record in slot_records.items()
        ]
    elif isinstance(slot_records, list):
        rows = [dict(record) for record in slot_records if isinstance(record, dict)]
    else:
        rows = []

    records: dict[str, dict[str, Any]] = {}
    for record in rows:
        slot_id = _text(record.get("slot_id"))
        if slot_id:
            records[slot_id] = deepcopy(record)
    return records


def _normalize_status(slot_id: str, record: dict[str, Any] | None) -> str:
    if record:
        status = _text(record.get("status")).casefold()
        if status in ALLOWED_SLOT_STATUSES:
            return status
        if record.get("blocked") is True:
            return "blocked"
        if record.get("needs_manual_review") is True:
            return "needs_manual_review"
        if record.get("missing_provenance") is True or record.get("has_provenance") is False:
            return "missing_provenance"
        value = _text(record.get("value"))
        if value:
            return "filled"

    if slot_id in MANUAL_REVIEW_SLOT_IDS:
        return "needs_manual_review"
    if slot_id in PROVENANCE_SLOT_IDS:
        return "missing_provenance"
    return "missing"


def _evidence_status(slot_id: str, status: str, record: dict[str, Any] | None) -> str:
    if record:
        explicit = _text(record.get("evidence_status")).casefold()
        if explicit in EVIDENCE_STATUS_LABELS_ZH:
            return explicit
        if record.get("has_provenance") is True:
            return "recorded"
    if status == "filled":
        return "recorded"
    if status == "missing_provenance" or slot_id in PROVENANCE_SLOT_IDS:
        return "needs_provenance"
    return "not_recorded"


def _manual_review_status(slot_id: str, status: str, record: dict[str, Any] | None) -> str:
    if record:
        explicit = _text(record.get("manual_review_status")).casefold()
        if explicit in MANUAL_REVIEW_STATUS_LABELS_ZH:
            return explicit
    if status == "blocked":
        return "blocked"
    if status == "needs_manual_review" or slot_id in MANUAL_REVIEW_SLOT_IDS:
        return "required"
    return "not_started"


def _helper_text(slot_id: str, status: str) -> str:
    label_zh, _label_en = _slot_label(slot_id)
    if status == "filled":
        return f"{label_zh}已有草稿记录，仍建议保留来源和人工复核语境。"
    if status == "missing_provenance":
        return f"{label_zh}需要补充证据来源或出处说明。"
    if status == "needs_manual_review":
        return f"{label_zh}需要人工复核后再进入后续文档整理。"
    if status == "blocked":
        return f"{label_zh}暂时受阻，请先记录原因或缺口。"
    if status == "optional":
        return f"{label_zh}是可选信息，可在资料明确后再补充。"
    if status == "not_applicable":
        return f"{label_zh}当前路线可标记为不适用。"
    return f"{label_zh}尚未记录，请先补齐核心信息。"


def _action_label(slot_id: str, status: str) -> str:
    label_zh, _label_en = _slot_label(slot_id)
    if status == "missing_provenance":
        return f"去补充{label_zh}来源"
    if status == "needs_manual_review":
        return f"查看{label_zh}复核说明"
    if status == "blocked":
        return f"记录{label_zh}受阻原因"
    if status == "filled":
        return f"复查{label_zh}记录"
    if status in {"optional", "not_applicable"}:
        return f"暂时跳过{label_zh}"
    return f"去补充{label_zh}"


def _slot_row(slot_id: str, record: dict[str, Any] | None) -> dict[str, Any]:
    label_zh, label_en = _slot_label(slot_id)
    status = _normalize_status(slot_id, record)
    evidence_status = _evidence_status(slot_id, status, record)
    manual_status = _manual_review_status(slot_id, status, record)
    return {
        "slot_id": slot_id,
        "slot_label_zh": label_zh,
        "slot_label_en": label_en,
        "status": status,
        "status_label_zh": STATUS_LABELS_ZH[status],
        "evidence_status": evidence_status,
        "evidence_status_label_zh": EVIDENCE_STATUS_LABELS_ZH[evidence_status],
        "manual_review_status": manual_status,
        "manual_review_status_label_zh": MANUAL_REVIEW_STATUS_LABELS_ZH[manual_status],
        "helper_text_zh": _helper_text(slot_id, status),
        "next_action_label_zh": _action_label(slot_id, status),
    }


def _completion_summary(slot_rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in ALLOWED_SLOT_STATUSES}
    for row in slot_rows:
        counts[row["status"]] += 1
    manual_count = counts["needs_manual_review"] + sum(
        1 for row in slot_rows if row["manual_review_status"] == "required" and row["status"] != "needs_manual_review"
    )
    blocked_count = counts["blocked"]
    missing_count = counts["missing"]
    provenance_count = counts["missing_provenance"]

    if blocked_count:
        completion_label = "暂时受阻"
    elif missing_count or provenance_count:
        completion_label = "信息不完整"
    elif manual_count:
        completion_label = "需要人工复核"
    else:
        completion_label = "草稿已记录"

    return {
        "total_slots": len(slot_rows),
        "filled_slots": counts["filled"],
        "missing_slots": missing_count,
        "missing_provenance_slots": provenance_count,
        "manual_review_slots": manual_count,
        "blocked_slots": blocked_count,
        "completion_label_zh": completion_label,
        "package_readiness_label_zh": "可继续补充" if missing_count or provenance_count or manual_count else "草稿已记录",
    }


def _gap_group(slot_rows: list[dict[str, Any]], statuses: set[str], explanation: str) -> dict[str, Any]:
    rows = [row for row in slot_rows if row["status"] in statuses]
    return {
        "count": len(rows),
        "slot_ids": [row["slot_id"] for row in rows],
        "explanation_zh": explanation,
    }


def _gap_summary(slot_rows: list[dict[str, Any]]) -> dict[str, Any]:
    optional_rows = [row for row in slot_rows if row["status"] in {"optional", "not_applicable"}]
    return {
        "missing_core_information": _gap_group(
            slot_rows,
            {"missing"},
            "这些核心信息尚未记录，建议先补齐文档草稿。",
        ),
        "missing_evidence_or_provenance": _gap_group(
            slot_rows,
            {"missing_provenance"},
            "这些项目需要补充证据来源、出处或追溯说明。",
        ),
        "needs_manual_review": _gap_group(
            slot_rows,
            {"needs_manual_review"},
            "这些项目需要人工复核，清单不会替代人工判断。",
        ),
        "blocked_items": _gap_group(
            slot_rows,
            {"blocked"},
            "这些项目暂时受阻，请记录缺口原因。",
        ),
        "optional_items": {
            "count": len(optional_rows),
            "slot_ids": [row["slot_id"] for row in optional_rows],
            "explanation_zh": "这些项目可按当前资料情况暂时跳过或标记不适用。",
        },
    }


def _next_step_actions(slot_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actionable_statuses = {"missing", "missing_provenance", "needs_manual_review", "blocked"}
    actions: list[dict[str, Any]] = []
    for row in slot_rows:
        if row["status"] not in actionable_statuses:
            continue
        actions.append(
            {
                "action_id": f"mock_{row['status']}_{row['slot_id']}",
                "slot_id": row["slot_id"],
                "label_zh": row["next_action_label_zh"],
                "action_kind": f"mock_{row['status']}",
                "is_mock": True,
                "does_not_write_data": True,
            }
        )
    return actions


def _unknown_payload(route_id: str | None) -> dict[str, Any]:
    return {
        "page_title_zh": "Simple Plant Wizard 路线清单",
        "page_subtitle_zh": "未识别路线时不生成槽位清单；请先回到路线确认。",
        "route_id": _text(route_id),
        "route_label_zh": "未知路线",
        "route_label_en": "Unknown route",
        "slot_rows": [],
        "completion_summary": _completion_summary([]),
        "gap_summary": _gap_summary([]),
        "next_step_actions": [],
        "safe_boundary_notes_zh": list(SAFE_BOUNDARY_NOTES_ZH),
        "handoff_stage_id": HANDOFF_STAGE_ID,
        "advanced_detail_hint_zh": "高级 Plant Review 细节仍在下方保留；本清单只作为新手入口提示。",
    }


def build_simple_plant_wizard_route_checklist_presenter(
    route_id: str | None = None,
    slot_records: Any = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic read-only route checklist payload for Simple Plant Wizard."""
    selected_route_id = _text(route_id or (options or {}).get("route_id") or "plant_protein_expression_review")
    route = get_simple_plant_wizard_route(selected_route_id)
    if not route or route.get("route_id") == HANDOFF_STAGE_ID:
        return _unknown_payload(selected_route_id)

    records = _records_by_slot(slot_records)
    slot_rows = [_slot_row(slot_id, records.get(slot_id)) for slot_id in route.get("required_slots", [])]
    return {
        "page_title_zh": "Simple Plant Wizard 路线信息清单",
        "page_subtitle_zh": "确认路线后，先查看哪些信息需要补齐、哪些需要来源、哪些需要人工复核。",
        "route_id": route["route_id"],
        "route_label_zh": route["label_zh"],
        "route_label_en": route["label_en"],
        "slot_rows": slot_rows,
        "completion_summary": _completion_summary(slot_rows),
        "gap_summary": _gap_summary(slot_rows),
        "next_step_actions": _next_step_actions(slot_rows),
        "safe_boundary_notes_zh": list(SAFE_BOUNDARY_NOTES_ZH),
        "handoff_stage_id": HANDOFF_STAGE_ID,
        "advanced_detail_hint_zh": "下方仍保留高级 Plant Review 明细；本清单只帮助新手理解当前路线缺口。",
    }
