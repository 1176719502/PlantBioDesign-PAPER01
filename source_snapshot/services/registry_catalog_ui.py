from __future__ import annotations

from typing import Any, Mapping

from services.plant_component_workflow_registry import (
    CATALOG_CANDIDATE_STATE,
    GENERIC_MULTI_TU_WORKFLOW,
    LEGACY_CATALOG_STATE,
    build_registry_selection,
    build_user_provided_selection,
    validate_saved_selection,
)


_ROLE_BY_COMPONENT_TYPE = {
    "promoter": "promoter",
    "five_prime_utr": "five_prime_region",
    "cds": "cds",
    "terminator": "3_prime_regulatory_region",
    "three_prime_regulatory_region": "3_prime_regulatory_region",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def component_role_for_catalog_record(record: Mapping[str, Any]) -> str:
    """Return the existing Multi-TU role for a catalog component type."""
    return _ROLE_BY_COMPONENT_TYPE.get(_text(record.get("component_type")), "")


def catalog_row_ui_state(record: Mapping[str, Any]) -> dict[str, Any]:
    """Translate authoritative Registry facts into concise display-only labels."""
    governance_state = record.get("catalog_governance_state")
    formal_selectable = bool(record.get("formal_selectable"))
    identity_status = _text(record.get("identity_review_status"))
    boundary_status = _text(record.get("boundary_review_status"))
    unresolved_badges = []
    if identity_status in {"human_review", "not_resolved"}:
        unresolved_badges.append("身份待人工复核")
    if boundary_status == "human_review":
        unresolved_badges.append("边界待人工复核")
    participation_mode = _text(record.get("participation_mode"))
    library_tier = _text(record.get("library_tier"))
    if library_tier == "RETIRED":
        return {
            "state_key": "retired",
            "state_label": "已退役",
            "distribution_label": "已退役（保留历史身份映射）",
            "sequence_label": "不向新设计提供序列入口",
            "workflow_label": "不可进入新设计；历史保存记录仍可解析",
            "badges": ["已退役", "新设计不可用", *unresolved_badges],
            "can_offer_user_sequence": False,
            "can_offer_assisted_sequence": False,
            "formal_selectable": False,
        }
    if participation_mode == "REFERENCE_ONLY":
        return {
            "state_key": "reference_only",
            "state_label": "仅供参考",
            "distribution_label": "V2 参考身份（reference-only）",
            "sequence_label": "仅保留身份、来源与限制信息",
            "workflow_label": "不可作为正式序列选择；可供 Agent/人工检索参考",
            "badges": ["仅供参考", "正式选择不可用", *unresolved_badges],
            "can_offer_user_sequence": False,
            "can_offer_assisted_sequence": False,
            "formal_selectable": False,
        }
    if participation_mode == "USER_SEQUENCE_ASSISTED":
        return {
            "state_key": "user_sequence_assisted",
            "state_label": "需用户序列",
            "distribution_label": "需用户提供序列（USER_SEQUENCE_ASSISTED）",
            "sequence_label": "需提供用户 DNA 并按现有证据确认项目使用",
            "workflow_label": "完成项目绑定与双重确认后可作为 USER_PROVIDED 使用",
            "badges": ["需用户序列", "项目内确认后可用", *unresolved_badges],
            "can_offer_user_sequence": True,
            "can_offer_assisted_sequence": True,
            "formal_selectable": False,
        }
    if participation_mode == "DIRECT_USE" and not formal_selectable:
        return {
            "state_key": "qualified_direct_not_admitted",
            "state_label": "资产合格，尚未正式准入",
            "distribution_label": "V2 DIRECT_USE 资产已记录",
            "sequence_label": "序列与来源已记录；当前主机/角色准入未建立",
            "workflow_label": "不可直接使用；需现有 Registry 与主机适用性证据",
            "badges": ["DIRECT_USE 合格", "当前正式选择不可用", *unresolved_badges],
            "can_offer_user_sequence": False,
            "can_offer_assisted_sequence": False,
            "formal_selectable": False,
        }
    if governance_state == CATALOG_CANDIDATE_STATE:
        return {
            "state_key": "catalog_candidate",
            "state_label": "目录候选",
            "distribution_label": "经复核的目录候选（CATALOG_CANDIDATE）",
            "sequence_label": "精确 intake 序列仅供目录身份与来源复核",
            "workflow_label": "未正式准入；不可选择或用于构建设计",
            "badges": ["目录候选", "正式选择不可用", *unresolved_badges],
            "can_offer_user_sequence": False,
            "can_offer_assisted_sequence": False,
            "formal_selectable": False,
        }
    if governance_state == LEGACY_CATALOG_STATE:
        return {
            "state_key": "legacy",
            "state_label": "旧版未分类",
            "distribution_label": "未分类（旧版记录）",
            "sequence_label": "本地序列已记录；不构成正式准入",
            "workflow_label": "正式选择不可用",
            "badges": ["旧版未分类", "正式选择不可用", *unresolved_badges],
            "can_offer_user_sequence": False,
            "can_offer_assisted_sequence": False,
            "formal_selectable": False,
        }

    state = tuple(governance_state) if isinstance(governance_state, tuple) else ()
    if state == ("bundled", "local_verified", "eligible"):
        return {
            "state_key": "bundled",
            "state_label": "本地内置",
            "distribution_label": "本地内置（bundled）",
            "sequence_label": "本地序列已记录",
            "workflow_label": "可按服务准入用于正式工作流" if formal_selectable else "当前角色不可直接使用",
            "badges": ["本地序列", "服务准入可用" if formal_selectable else "当前角色不可用", *unresolved_badges],
            "can_offer_user_sequence": False,
            "can_offer_assisted_sequence": False,
            "formal_selectable": formal_selectable,
        }
    if state == ("reference_only", "unavailable", "requires_sequence"):
        can_offer = bool(component_role_for_catalog_record(record))
        return {
            "state_key": "reference_only",
            "state_label": "仅元数据",
            "distribution_label": "仅参考身份（reference-only）",
            "sequence_label": "当前版本未内置序列",
            "workflow_label": "不能作为 Registry 序列直接使用；可自行提供序列" if can_offer else "不能直接用于正式工作流",
            "badges": ["仅元数据", "可自备序列" if can_offer else "正式选择不可用", *unresolved_badges],
            "can_offer_user_sequence": can_offer,
            "can_offer_assisted_sequence": False,
            "formal_selectable": False,
        }
    if state == ("deferred", "unavailable", "blocked"):
        return {
            "state_key": "deferred",
            "state_label": "暂缓",
            "distribution_label": "暂缓（deferred）",
            "sequence_label": "当前版本未内置序列",
            "workflow_label": "正式选择不可用",
            "badges": ["暂缓", "正式选择不可用", *unresolved_badges],
            "can_offer_user_sequence": False,
            "can_offer_assisted_sequence": False,
            "formal_selectable": False,
        }
    return {
        "state_key": "blocked",
        "state_label": "状态不可用",
        "distribution_label": "治理状态不可用",
        "sequence_label": "本地序列状态不可用",
        "workflow_label": "正式选择不可用",
        "badges": ["状态不可用", "正式选择不可用", *unresolved_badges],
        "can_offer_user_sequence": False,
        "can_offer_assisted_sequence": False,
        "formal_selectable": False,
    }


def catalog_state_counts(records: list[Mapping[str, Any]]) -> dict[str, int]:
    counts = {
        "bundled": 0,
        "reference_only": 0,
        "deferred": 0,
        "legacy": 0,
        "catalog_candidate": 0,
        "formal_selectable": 0,
    }
    for record in records:
        state = catalog_row_ui_state(record)
        key = str(state["state_key"])
        if key in counts:
            counts[key] += 1
        elif key in {
            "user_sequence_assisted",
            "qualified_direct_not_admitted",
            "retired",
        }:
            counts[key] = counts.get(key, 0) + 1
        counts["formal_selectable"] += int(bool(state["formal_selectable"]))
    return counts


def build_direct_registry_component(
    record: Mapping[str, Any], *, requested_host: str
) -> dict[str, Any]:
    """Build a direct component only through the frozen Registry admission service."""
    role = component_role_for_catalog_record(record)
    if not role:
        raise ValueError("该元件类型未接入当前 Multi-TU 角色。")
    selection = build_registry_selection(
        _text(record.get("registry_component_id")),
        role=role,
        workflow_id=GENERIC_MULTI_TU_WORKFLOW,
        requested_host=_text(requested_host),
    )
    return {
        "role": role,
        "display_name": _text(record.get("name")) or role,
        "raw_text": _text(record.get("sequence")),
        "source_type": "REGISTRY",
        "source_format": "plain",
        "source_name": _text(record.get("accession")) or "Plant Component Registry V1",
        "provenance_reference": _text(record.get("provenance_origin")) or _text(record.get("source")),
        "component_reference": selection,
    }


def build_reference_user_provided_component(
    record: Mapping[str, Any],
    *,
    raw_sequence: str,
    display_name: str,
    project_id: str,
) -> dict[str, Any]:
    """Validate a user sequence and retain only a non-authoritative catalog identity link."""
    state = catalog_row_ui_state(record)
    if state["state_key"] != "reference_only" or not state["can_offer_user_sequence"]:
        raise ValueError("当前目录记录不提供用户序列入口。")
    role = component_role_for_catalog_record(record)
    from services.mvp_sequence_input import analyze_dna_component_input

    name = _text(display_name) or _text(record.get("name")) or role
    analyzed = analyze_dna_component_input(
        raw_sequence,
        project_id=_text(project_id),
        component_type={"3_prime_regulatory_region": "terminator"}.get(role, role),
        display_name=name,
        source_kind="paste",
        source_name="用户提供",
    )
    normalized = _text(analyzed.get("normalized_sequence"))
    selection = build_user_provided_selection(
        role=role,
        display_name=name,
        sequence=normalized,
        workflow_id=GENERIC_MULTI_TU_WORKFLOW,
        reference_component_id=_text(record.get("registry_component_id")),
        reference_registry_version=_text(record.get("registry_version")),
    )
    return {
        "role": role,
        "display_name": name,
        "raw_text": normalized,
        "source_type": "paste",
        "source_format": "fasta" if raw_sequence.lstrip().startswith(">") else "plain",
        "source_name": "用户提供",
        "provenance_reference": (
            f"参考目录身份：{_text(record.get('registry_component_id'))}；"
            "未核对为该 accession 的官方序列"
        ),
        "component_reference": selection,
        "sequence_sha256": _text(selection.get("sequence_sha256")),
    }


def build_v2_user_provided_component(
    record: Mapping[str, Any],
    *,
    raw_sequence: str,
    display_name: str,
    project_id: str,
    project_repository: Any,
    user_sequence_source: str,
    identity_and_boundaries_confirmed: bool = False,
    project_intent_confirmed: bool = False,
    explicit_user_confirmation: bool,
) -> dict[str, Any]:
    """Resolve one V2 assisted identity into a USER_PROVIDED snapshot."""
    from services.component_library_v2_adoption import (
        resolve_v2_user_sequence_for_project,
    )
    from services.mvp_sequence_input import analyze_dna_component_input

    state = catalog_row_ui_state(record)
    role = component_role_for_catalog_record(record)
    if state["state_key"] != "user_sequence_assisted" or not role:
        raise ValueError("当前 V2 记录不提供用户序列入口。")
    name = _text(display_name) or _text(record.get("name")) or role
    analyzed = analyze_dna_component_input(
        raw_sequence,
        project_id=_text(project_id),
        component_type={"3_prime_regulatory_region": "terminator"}.get(role, role),
        display_name=name,
        source_kind="paste",
        source_name=_text(user_sequence_source) or "用户提供",
    )
    normalized = _text(analyzed.get("normalized_sequence"))
    resolution = resolve_v2_user_sequence_for_project(
        record,
        normalized,
        project_id=_text(project_id),
        repository=project_repository,
        identity_and_boundaries_confirmed=identity_and_boundaries_confirmed,
        project_intent_confirmed=project_intent_confirmed,
        explicit_user_confirmation=explicit_user_confirmation,
        user_sequence_source=user_sequence_source,
    )
    selection = build_user_provided_selection(
        role=role,
        display_name=name,
        sequence=normalized,
        workflow_id=GENERIC_MULTI_TU_WORKFLOW,
        assisted_resolution=resolution,
    )
    return {
        "role": role,
        "display_name": name,
        "raw_text": normalized,
        "source_type": "paste",
        "source_format": "fasta" if raw_sequence.lstrip().startswith(">") else "plain",
        "source_name": _text(user_sequence_source),
        "provenance_reference": (
            f"V2 canonical identity: {_text(record.get('canonical_v2_component_id'))}; "
            f"user-supplied sequence source: {_text(user_sequence_source)}"
        ),
        "component_reference": selection,
        "sequence_sha256": _text(selection.get("sequence_sha256")),
        "component_identity_source": "V2_CORE",
        "sequence_source": "USER_SUPPLIED_CONFIRMED",
        "catalog_component_id": _text(record.get("canonical_v2_component_id")),
        "catalog_name": _text(record.get("name")),
        "governance_status": "USER_SEQUENCE_ASSISTED",
        "admission_mode": "USER_SEQUENCE_ASSISTED",
        "project_id": _text(project_id),
        "resolved_component_id": _text(resolution.get("resolution_id")),
        "resolved_component_evidence": resolution,
    }


def preserved_user_component_reference(
    selection: Mapping[str, Any] | None,
    *,
    role: str,
    sequence: str,
    current_project_id: str | None = None,
) -> dict[str, Any]:
    """Preserve a saved USER_PROVIDED link only while the frozen snapshot still validates."""
    candidate = dict(selection) if isinstance(selection, Mapping) else {}
    if not candidate:
        return {}
    try:
        validated = validate_saved_selection(
            candidate,
            role=role,
            sequence=sequence,
            current_project_id=current_project_id,
        )
    except ValueError:
        return {}
    return validated if _text(validated.get("source_type")) == "USER_PROVIDED" else {}
