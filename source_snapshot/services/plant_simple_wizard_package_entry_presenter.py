from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.plant_simple_wizard_route_schema import (
    HANDOFF_STAGE_ID,
    get_simple_plant_wizard_handoff_stage,
    get_simple_plant_wizard_route,
)


SAFE_PACKAGE_STATUSES: tuple[str, ...] = (
    "draft",
    "incomplete",
    "needs_manual_review",
    "not_started",
)

PACKAGE_STATUS_LABELS_ZH: dict[str, str] = {
    "draft": "审查包草稿预览",
    "incomplete": "信息不完整",
    "needs_manual_review": "需要人工复核",
    "not_started": "尚未开始",
}

PACKAGE_ENTRY_ACTIONS: tuple[dict[str, Any], ...] = (
    {
        "action_id": "view_package_draft_preview",
        "label_zh": "查看审查包草稿预览",
        "action_kind": "mock_view_preview",
        "is_mock": True,
        "does_not_write_data": True,
    },
    {
        "action_id": "copy_gap_summary",
        "label_zh": "复制缺口摘要",
        "action_kind": "mock_copy_summary",
        "is_mock": True,
        "does_not_write_data": True,
    },
    {
        "action_id": "view_manual_review_note",
        "label_zh": "查看人工复核说明",
        "action_kind": "mock_view_manual_review",
        "is_mock": True,
        "does_not_write_data": True,
    },
    {
        "action_id": "continue_filling_missing_information",
        "label_zh": "继续补充缺失信息",
        "action_kind": "mock_continue_documentation",
        "is_mock": True,
        "does_not_write_data": True,
    },
)

SAFE_BOUNDARY_NOTES_ZH: tuple[str, ...] = (
    "本入口只展示文档化审查包草稿预览，不保存项目、不写入数据库，也不生成真实导出包。",
    "草稿预览用于回读目标、路线、缺口、证据来源和人工复核状态，不代表生物学推荐或实验判断。",
    "后续交接仍需人工或公司复核；本界面不选择最终组件、不改写序列、不给出湿实验可用性结论。",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _count_group(gap_summary: dict[str, Any], group_id: str) -> int:
    group = _mapping(gap_summary.get(group_id))
    try:
        return int(group.get("count") or 0)
    except (TypeError, ValueError):
        return 0


def _slot_ids(gap_summary: dict[str, Any], group_id: str) -> list[str]:
    group = _mapping(gap_summary.get(group_id))
    return [_text(slot_id) for slot_id in _list(group.get("slot_ids")) if _text(slot_id)]


def _summary_from_checklist(checklist_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    completion = _mapping(checklist_payload.get("completion_summary"))
    gaps = _mapping(checklist_payload.get("gap_summary"))

    missing_count = _count_group(gaps, "missing_core_information")
    provenance_count = _count_group(gaps, "missing_evidence_or_provenance")
    manual_count = _count_group(gaps, "needs_manual_review")
    blocked_count = _count_group(gaps, "blocked_items")

    input_summary = {
        "total_slots": int(completion.get("total_slots") or 0),
        "filled_slots": int(completion.get("filled_slots") or 0),
        "route_completion_label_zh": _text(completion.get("completion_label_zh")) or "尚未开始",
    }
    gap_summary = {
        "missing_field_count": missing_count,
        "missing_evidence_or_provenance_count": provenance_count,
        "blocked_item_count": blocked_count,
        "missing_field_slot_ids": _slot_ids(gaps, "missing_core_information"),
        "missing_evidence_or_provenance_slot_ids": _slot_ids(gaps, "missing_evidence_or_provenance"),
        "blocked_item_slot_ids": _slot_ids(gaps, "blocked_items"),
        "summary_zh": (
            f"缺失信息 {missing_count} 项；证据或来源缺口 {provenance_count} 项；"
            f"受阻项目 {blocked_count} 项。"
        ),
    }
    manual_review_summary = {
        "manual_review_item_count": manual_count,
        "manual_review_slot_ids": _slot_ids(gaps, "needs_manual_review"),
        "summary_zh": f"需要人工复核 {manual_count} 项；草稿预览不会替代人工判断。",
    }
    return input_summary, gap_summary, manual_review_summary


def _empty_summaries() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    return (
        {
            "total_slots": 0,
            "filled_slots": 0,
            "route_completion_label_zh": "尚未开始",
        },
        {
            "missing_field_count": 0,
            "missing_evidence_or_provenance_count": 0,
            "blocked_item_count": 0,
            "missing_field_slot_ids": [],
            "missing_evidence_or_provenance_slot_ids": [],
            "blocked_item_slot_ids": [],
            "summary_zh": "尚未收到路线清单；请先查看缺口摘要。",
        },
        {
            "manual_review_item_count": 0,
            "manual_review_slot_ids": [],
            "summary_zh": "尚未收到人工复核条目；正式草稿前仍需人工复核。",
        },
    )


def _package_status(
    input_summary: dict[str, Any],
    gap_summary: dict[str, Any],
    manual_review_summary: dict[str, Any],
) -> str:
    if int(input_summary.get("total_slots") or 0) <= 0:
        return "not_started"
    if int(gap_summary.get("blocked_item_count") or 0) or int(manual_review_summary.get("manual_review_item_count") or 0):
        return "needs_manual_review"
    if int(gap_summary.get("missing_field_count") or 0) or int(gap_summary.get("missing_evidence_or_provenance_count") or 0):
        return "incomplete"
    return "draft"


def _preview_section(
    section_id: str,
    title_zh: str,
    summary_zh: str,
    status_label_zh: str,
) -> dict[str, str]:
    return {
        "section_id": section_id,
        "title_zh": title_zh,
        "summary_zh": summary_zh,
        "status_label_zh": status_label_zh,
    }


def _package_preview_sections(
    *,
    route_label_zh: str,
    package_status_label_zh: str,
    input_summary: dict[str, Any],
    gap_summary: dict[str, Any],
    manual_review_summary: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        _preview_section(
            "project_goal_readback",
            "项目目标回读",
            "从用户目标和路线确认中回读文档化目标；不扩展为实验任务。",
            package_status_label_zh,
        ),
        _preview_section(
            "route_type",
            "路线类型",
            f"当前路线：{route_label_zh}。",
            package_status_label_zh,
        ),
        _preview_section(
            "required_information_completion",
            "必填信息完成情况",
            f"已记录 {input_summary.get('filled_slots', 0)} / {input_summary.get('total_slots', 0)} 个路线槽位。",
            _text(input_summary.get("route_completion_label_zh")) or package_status_label_zh,
        ),
        _preview_section(
            "gap_summary",
            "缺口摘要",
            _text(gap_summary.get("summary_zh")),
            "信息不完整" if int(gap_summary.get("missing_field_count") or 0) else package_status_label_zh,
        ),
        _preview_section(
            "evidence_source_status",
            "证据来源状态",
            f"证据或来源缺口 {gap_summary.get('missing_evidence_or_provenance_count', 0)} 项。",
            "需要补充来源" if int(gap_summary.get("missing_evidence_or_provenance_count") or 0) else package_status_label_zh,
        ),
        _preview_section(
            "manual_review_status",
            "人工复核状态",
            _text(manual_review_summary.get("summary_zh")),
            "需要人工复核" if int(manual_review_summary.get("manual_review_item_count") or 0) else package_status_label_zh,
        ),
        _preview_section(
            "handoff_readback",
            "文档化交接说明",
            "交接内容保持为审查包草稿预览和人工复核材料。",
            package_status_label_zh,
        ),
    ]


def _identity_preview() -> dict[str, Any]:
    return {
        "enabled": False,
        "label_zh": "包身份信息将在正式草稿生成时显示",
        "qr_status_zh": "未生成",
        "md5_status_zh": "未生成",
        "snapshot_status_zh": "未生成",
        "does_not_require_new_dependency": True,
    }


def _intent_summary(intent_payload: dict[str, Any] | None) -> dict[str, Any]:
    source = _mapping(intent_payload)
    input_summary = _mapping(source.get("input_summary"))
    return {
        "interpreted_goal_zh": _text(source.get("interpreted_goal_zh")),
        "user_goal_text": _text(input_summary.get("user_goal_text")),
        "confidence": _text(source.get("confidence")),
    }


def build_simple_plant_wizard_package_entry_presenter(
    route_id: str | None = None,
    checklist_payload: dict[str, Any] | None = None,
    intent_payload: dict[str, Any] | None = None,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic read-only Design Review Package Draft entry payload."""
    selected_route_id = _text(route_id or (options or {}).get("route_id") or "plant_protein_expression_review")
    route = get_simple_plant_wizard_route(selected_route_id)
    if not route or route.get("route_id") == HANDOFF_STAGE_ID:
        route = {}

    route_label_zh = _text(route.get("label_zh")) or "未知路线"
    if isinstance(checklist_payload, dict) and checklist_payload:
        input_summary, gap_summary, manual_review_summary = _summary_from_checklist(deepcopy(checklist_payload))
    else:
        input_summary, gap_summary, manual_review_summary = _empty_summaries()

    package_status = _package_status(input_summary, gap_summary, manual_review_summary)
    package_status_label_zh = PACKAGE_STATUS_LABELS_ZH[package_status]
    handoff_stage = get_simple_plant_wizard_handoff_stage()

    return {
        "page_title_zh": "Simple Plant Wizard 设计审查包草稿入口",
        "page_subtitle_zh": "在路线、确认和缺口摘要之后，查看只读的 Design Review Package Draft 预览入口。",
        "route_id": _text(route.get("route_id")) or selected_route_id,
        "route_label_zh": route_label_zh,
        "package_stage_id": HANDOFF_STAGE_ID,
        "package_stage_label_zh": _text(handoff_stage.get("label_zh")) or "植物交接包复核阶段",
        "package_status": package_status,
        "package_status_label_zh": package_status_label_zh,
        "package_readiness_summary_zh": (
            "这是文档化审查包草稿预览入口；当前状态仍需按缺口和人工复核项继续整理。"
        ),
        "input_summary": {
            **input_summary,
            **_intent_summary(intent_payload),
        },
        "gap_summary": gap_summary,
        "manual_review_summary": manual_review_summary,
        "package_entry_actions": deepcopy(list(PACKAGE_ENTRY_ACTIONS)),
        "package_preview_sections": _package_preview_sections(
            route_label_zh=route_label_zh,
            package_status_label_zh=package_status_label_zh,
            input_summary=input_summary,
            gap_summary=gap_summary,
            manual_review_summary=manual_review_summary,
        ),
        "identity_preview": _identity_preview(),
        "safe_boundary_notes_zh": list(SAFE_BOUNDARY_NOTES_ZH),
        "advanced_detail_hint_zh": "下方仍保留高级 Plant Review 明细；本入口只作为新手路线到审查包草稿预览的只读对齐。",
    }
