"""Formal Step 3 plant expression-cassette assembly.

This adapter records the user's selected components and delegates sequence and
coordinate generation to the existing canonical construct runtime.  It does
not select, alter, or optimize any biological sequence.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from services.canonical_construct_runtime import (
    active_construct_snapshot,
    create_component,
    create_sequence_asset,
    generate_active_construct,
    set_active_component_order,
    upsert_component,
    upsert_sequence_asset,
)
from services.mvp_cds_input import TERMINAL_STOP_CODONS


CASSETTE_SCHEMA_VERSION = "formal-plant-expression-cassette.v1"
DNA_ALPHABET = frozenset("ATCG")
ROLE_COMPONENT_TYPES = {
    "promoter": "promoter",
    "five_prime_utr": "five_prime_utr",
    "five_prime_regulatory_region": "five_prime_utr",
    "translation_enhancer_sequence": "five_prime_utr",
    "signal_peptide_coding_sequence": "signal_targeting_coding_sequence",
    "chloroplast_transit_peptide_coding_sequence": "signal_targeting_coding_sequence",
    "mitochondrial_targeting_peptide_coding_sequence": "signal_targeting_coding_sequence",
    "nuclear_localization_signal_coding_sequence": "signal_targeting_coding_sequence",
    "n_terminal_fusion_tag_coding_sequence": "n_terminal_tag",
    "linker_coding_sequence": "linker",
    "c_terminal_fusion_tag_coding_sequence": "c_terminal_tag",
    "cds": "cds",
    "three_prime_utr": "terminator",
    "terminator": "terminator",
    "three_prime_regulatory_region": "terminator",
    "three_prime_processing_termination_region": "terminator",
}
MANDATORY_ROLES = {"promoter", "cds", "three_prime_utr", "terminator", "three_prime_regulatory_region", "three_prime_processing_termination_region"}
CODING_COMPONENT_TYPES = {
    "n_terminal_tag",
    "signal_targeting_coding_sequence",
    "cds",
    "linker",
    "c_terminal_tag",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _sequence(value: Any) -> str:
    return "".join(char.upper() for char in str(value or "") if not char.isspace())


def _finding(rule_id: str, status: str, message: str) -> dict[str, str]:
    return {"rule_id": rule_id, "status": status, "message": message}


def _signature(components: list[dict[str, Any]], cds_signature: str) -> str:
    payload = {
        "schema_version": CASSETTE_SCHEMA_VERSION,
        "cds_signature": cds_signature,
        "components": [
            {
                "biological_role": item["biological_role"],
                "display_name": item["display_name"],
                "sequence": item["sequence"],
                "strand": item["strand"],
                "source_kind": item["source_kind"],
                "source_reference": item["source_reference"],
                "user_edited": item["user_edited"],
                "order": item["order"],
                **({"component_reference": item["component_reference"],
                    "assisted_project_host": item.get("assisted_project_host", "")}
                   if item.get("component_reference") else {}),
            }
            for item in components
        ],
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def normalize_component(value: dict[str, Any], *, order: int) -> dict[str, Any]:
    """Keep precise source role while mapping it to one canonical runtime type."""
    source = dict(value or {})
    role = _text(source.get("biological_role") or source.get("role")).lower()
    if role not in ROLE_COMPONENT_TYPES:
        raise ValueError("组件缺少可识别的 biological role。")
    sequence = _sequence(source.get("sequence") or source.get("normalized_sequence"))
    strand = _text(source.get("strand") or source.get("orientation") or "forward").lower()
    if strand in {"+", "1", "forward", "正向"}:
        strand = "forward"
    elif strand in {"-", "-1", "reverse", "反向"}:
        strand = "reverse"
    else:
        raise ValueError("组件方向必须为正向或反向。")
    return {
        "display_name": _text(source.get("display_name") or source.get("name")) or "未命名组件",
        "biological_role": role,
        "component_type": ROLE_COMPONENT_TYPES[role],
        "sequence": sequence,
        "length": len(sequence),
        "strand": strand,
        "source_kind": _text(source.get("source_kind") or source.get("source_type")) or "user_recorded",
        "source_reference": _text(source.get("source_reference") or source.get("accession") or source.get("source_name")),
        "source_file": _text(source.get("source_file") or source.get("source_name")),
        "user_edited": bool(source.get("user_edited", False)),
        "order": int(order),
        **({"component_reference": deepcopy(source["component_reference"]),
            "assisted_project_host": _text(source.get("assisted_project_host"))}
           if source.get("component_reference") else {}),
    }


def assess_expression_cassette(
    components: list[dict[str, Any]],
    *,
    cds_sequence: str,
    cds_signature: str,
    project_definition: dict[str, Any] | None = None,
    order_confirmed: bool = False,
) -> dict[str, Any]:
    """Validate declared Step 3 components without mutating sequence content."""
    normalized = [normalize_component(item, order=index + 1) for index, item in enumerate(components)]
    findings: list[dict[str, str]] = []
    roles = [item["biological_role"] for item in normalized]
    types = [item["component_type"] for item in normalized]
    expected_cds = _sequence(cds_sequence)
    cds_items = [item for item in normalized if item["component_type"] == "cds"]
    if not any(item["component_type"] == "promoter" for item in normalized):
        findings.append(_finding("missing_promoter", "阻断", "缺少启动子。"))
    if len(cds_items) != 1 or not expected_cds:
        findings.append(_finding("missing_cds", "阻断", "缺少第二步已确认的 CDS。"))
    if not any(item["component_type"] == "terminator" for item in normalized):
        findings.append(_finding("missing_three_prime_regulatory_element", "阻断", "缺少 3′端调控元件。"))
    if cds_items and cds_items[0]["sequence"] != expected_cds:
        findings.append(_finding("cds_signature_mismatch", "阻断", "CDS 必须保持第二步已确认的规范化序列；请返回第二步修改。"))
    if not order_confirmed:
        findings.append(_finding("component_order_not_confirmed", "阻断", "需要确认当前组件排列和方向。"))
    for item in normalized:
        if not item["sequence"]:
            findings.append(_finding("empty_component_sequence", "阻断", f"{item['display_name']} 的 DNA 序列为空。"))
        invalid = sorted(set(item["sequence"]) - DNA_ALPHABET)
        if invalid:
            findings.append(_finding("illegal_dna_character", "阻断", f"{item['display_name']} 含非法 DNA 字符：{', '.join(invalid)}。"))
        if not item["source_reference"]:
            findings.append(_finding("incomplete_component_provenance", "需要人工确认", f"{item['display_name']} 的来源信息尚不完整。"))
        if item["source_kind"] in {"paste", "upload", "user_recorded"} and not item["source_reference"]:
            findings.append(_finding("custom_component_annotation", "需要人工确认", f"自定义组件 {item['display_name']} 缺少专业注释或来源。"))
    if types.count("promoter") == 1 and types.count("cds") == 1 and types.count("terminator") == 1:
        canonical_order = ["promoter", "five_prime_utr", "n_terminal_tag", "signal_targeting_coding_sequence", "cds", "linker", "c_terminal_tag", "terminator"]
        ranks = [canonical_order.index(component_type) for component_type in types]
        if ranks != sorted(ranks):
            findings.append(_finding("unsupported_component_order", "阻断", "组件顺序不符合已确认的植物表达盒结构。"))
    coding = [item for item in normalized if item["component_type"] in CODING_COMPONENT_TYPES]
    for item in coding:
        if item["length"] % 3:
            findings.append(_finding("coding_component_frameshift", "阻断", f"{item['display_name']} 的编码长度不是 3 的倍数。"))
    has_c_terminal = any(item["component_type"] in {"linker", "c_terminal_tag"} for item in normalized)
    if cds_items:
        cds = cds_items[0]["sequence"]
        has_stop = len(cds) >= 3 and cds[-3:] in TERMINAL_STOP_CODONS
        if has_c_terminal and has_stop:
            findings.append(_finding("c_terminal_fusion_terminal_stop_conflict", "阻断", "C 端融合元件与 CDS 末端终止密码子冲突；请返回第二步处理 CDS。"))
        if not has_c_terminal and not has_stop:
            findings.append(_finding("cds_missing_terminal_stop", "需要人工确认", "未选择 C 端融合元件且 CDS 缺少末端终止密码子。"))
        if any(item["component_type"] in {"n_terminal_tag", "signal_targeting_coding_sequence"} for item in normalized):
            findings.append(_finding("n_terminal_start_relationship", "需要人工确认", "N 端编码融合的起始密码子关系需要人工确认。"))
        fused = "".join(item["sequence"] for item in coding)
        if len(fused) % 3 == 0:
            stops = [index for index in range(0, max(0, len(fused) - 3), 3) if fused[index:index + 3] in TERMINAL_STOP_CODONS]
            if stops:
                findings.append(_finding("unexpected_internal_stop", "阻断", "编码融合后出现非预期内部终止密码子。"))
    definition = dict(project_definition or {})
    if _text(definition.get("tissue_target")):
        findings.append(_finding("promoter_context_not_confirmed", "需要人工确认", "第一步记录了组织或器官目标；启动子适用背景尚未确认。"))
    localization = _text(definition.get("localization_target"))
    if localization and not any(item["component_type"] == "signal_targeting_coding_sequence" for item in normalized):
        findings.append(_finding("localization_component_not_confirmed", "需要人工确认", "第一步记录了定位目标；第三步未记录相应靶向编码元件。"))
    if any(item["biological_role"] == "three_prime_regulatory_region" for item in normalized):
        findings.append(_finding("broad_three_prime_role", "需要人工确认", "3′端元件当前仅记录为宽泛的 3′端调控区。"))
    return {
        "schema_version": CASSETTE_SCHEMA_VERSION,
        "components": normalized,
        "findings": findings,
        "input_signature": _signature(normalized, cds_signature),
        "cds_signature": cds_signature,
        "blocking": any(item["status"] == "阻断" for item in findings),
    }


def generate_expression_cassette(
    assessment: dict[str, Any],
    *,
    project_id: str,
) -> dict[str, Any]:
    """Generate one canonical transcription unit from approved component records."""
    if bool(assessment.get("blocking")):
        raise ValueError("表达盒存在阻断项，不能生成。")
    runtime: dict[str, Any] = {"project_id": project_id}
    component_ids: list[str] = []
    components = [dict(item) for item in assessment.get("components") or []]
    for item in components:
        if item.get("component_reference"):
            from services.single_gene_assisted_components import validate_single_gene_assisted_reference

            validate_single_gene_assisted_reference(
                item["component_reference"], sequence=item["sequence"],
                role=item["biological_role"], project_id=project_id,
                host=item.get("assisted_project_host", ""),
            )
        asset = create_sequence_asset(
            project_id=project_id,
            display_name=item["display_name"],
            raw_text=item["sequence"],
            molecule_type="dna",
            source_type=item["source_kind"],
            source_format="plain",
            source_name=item["source_file"],
            provenance_reference=item["source_reference"],
            asset_role="construct_component",
        )
        runtime = upsert_sequence_asset(runtime, asset)
        component = create_component(
            project_id=project_id,
            component_type=item["component_type"],
            display_name=item["display_name"],
            sequence_asset_id=asset["asset_id"],
            orientation=item["strand"],
            provenance_reference=item["source_reference"],
            user_confirmation_state="confirmed",
        )
        component["biological_role"] = item["biological_role"]
        component["source_kind"] = item["source_kind"]
        component["source_file"] = item["source_file"]
        component["user_edited"] = item["user_edited"]
        if item.get("component_reference"):
            component["component_reference"] = deepcopy(item["component_reference"])
            component["assisted_project_host"] = item["assisted_project_host"]
        runtime = upsert_component(runtime, component)
        component_ids.append(component["component_id"])
    runtime = set_active_component_order(runtime, component_ids)
    runtime = generate_active_construct(runtime)
    cassette = active_construct_snapshot(runtime)
    if int((cassette.get("validation_summary") or {}).get("blocking_count") or 0):
        raise ValueError("canonical 表达盒存在阻断项，不能生成。")
    feature_by_name = {str(row.get("name") or ""): dict(row) for row in cassette.get("feature_rows") or []}
    component_records = []
    for item in components:
        feature = feature_by_name.get(item["display_name"], {})
        component_records.append({
            **item,
            "transcription_unit_id": str(cassette.get("construct_id") or ""),
            "start": int(feature.get("start") or 0),
            "end": int(feature.get("end") or 0),
        })
    total_length = sum(item["length"] for item in component_records)
    if total_length != int(cassette.get("sequence_length") or 0):
        raise ValueError("表达盒总长度与活动元件长度之和不一致。")
    return {
        "schema_version": CASSETTE_SCHEMA_VERSION,
        "runtime": runtime,
        "cassette": cassette,
        "components": component_records,
        "findings": list(assessment.get("findings") or []),
        "manual_confirmation_items": [item for item in assessment.get("findings") or [] if item.get("status") == "需要人工确认"],
        "input_signature": str(assessment.get("input_signature") or ""),
        "cds_signature": str(assessment.get("cds_signature") or ""),
        "total_length": total_length,
    }
