"""Deterministic professional-review ZIP for one canonical single-gene construct.

This adapter packages existing canonical snapshots and export bytes. It does
not assemble, alter, or recommend biological sequences.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from io import BytesIO, StringIO
from pathlib import PurePosixPath
from typing import Any

from Bio import SeqIO
from Bio.Seq import Seq

from services.canonical_construct_runtime import (
    CanonicalConstructRuntimeError,
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
    export_active_construct,
)
from services.formal_t_dna_review import validate_t_dna_operation


PACKAGE_VERSION = "1.0.0"
PACKAGE_MIME = "application/zip"
REVIEW_READY = "ready_for_professional_review"
REVIEW_NEEDS_PROVENANCE = "needs_additional_provenance"
REVIEW_BLOCKED = "blocked"
WET_LAB_READINESS = "not_assessed"
PACKAGE_FILES = (
    "README.md",
    "manifest.json",
    "complete_plasmid.fasta",
    "complete_plasmid.gb",
    "expression_cassette.fasta",
    "construct_summary.json",
    "component_inventory.csv",
    "provenance_review.csv",
    "validation_report.json",
    "checksums.sha256",
)
PAYLOAD_FILES = tuple(
    name for name in PACKAGE_FILES if name not in {"manifest.json", "checksums.sha256"}
)
CHECKSUM_FILES = tuple(name for name in PACKAGE_FILES if name != "checksums.sha256")
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
_ACCESSION_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Z]{1,6}_?\d+(?:\.\d+)?)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_PLACEHOLDERS = {
    "",
    "not provided",
    "not_provided",
    "unknown",
    "未记录",
    "未提供",
    "尚未确定",
    "不适用",
    "n/a",
}
COMPONENT_INVENTORY_COLUMNS = (
    "component_name",
    "biological_role",
    "length_bp",
    "start_1_based",
    "end_1_based",
    "strand",
    "expression_cassette",
    "source_type",
    "source_reference",
    "sequence_sha256",
)
PROVENANCE_REVIEW_COLUMNS = (
    "asset_name",
    "biological_role",
    "sequence_length_bp",
    "sequence_sha256",
    "source_type",
    "source_reference",
    "accession_or_file",
    "user_edited_status",
    "review_status",
    "missing_information",
    "professional_review_items",
)


class ProfessionalReviewPackageError(ValueError):
    """Raised when a professional-review ZIP cannot be built or verified."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bytes(value: Any) -> bytes:
    return value if isinstance(value, bytes) else str(value or "").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sequence_sha256(sequence: str) -> str:
    return _sha256(_text(sequence).upper().encode("ascii"))


def _is_present(value: Any) -> bool:
    return _text(value).casefold() not in _PLACEHOLDERS


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            separators=(",", ": "),
            default=str,
        )
        + "\n"
    ).encode("utf-8")


def _csv_bytes(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _safe_file_stem(value: Any) -> str:
    stem = " ".join(_text(value).split())
    stem = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", stem)
    while ".." in stem:
        stem = stem.replace("..", "_")
    return re.sub(r"_+", "_", stem).strip(" ._-") or "BioDesign_Project"


def project_display_name(result: dict[str, Any], plasmid: dict[str, Any]) -> str:
    """Return the persisted project name, with the historical demo fallback."""
    name = _text(result.get("project_name"))
    if name:
        return name
    records = _mapping(result.get("input_records"))
    cds_name = _text(_mapping(records.get("cds")).get("display_name")).upper()
    if int(plasmid.get("sequence_length") or 0) == 6248 and "ALB" in cds_name:
        return "水稻 ALB 演示项目"
    return "植物表达载体项目"


def _parse_single_sequence(data: bytes, file_format: str, label: str) -> tuple[str, Any]:
    try:
        records = list(SeqIO.parse(StringIO(data.decode("utf-8")), file_format))
    except Exception as exc:
        raise ProfessionalReviewPackageError(f"{label} 无法解析。") from exc
    if len(records) != 1:
        raise ProfessionalReviewPackageError(f"{label} 必须且只能包含一条序列记录。")
    return str(records[0].seq).upper(), records[0]


def _finding_detail(item: dict[str, Any]) -> str:
    return _text(item.get("explanation") or item.get("message") or item.get("rule_id"))


def _blocking_findings(snapshot: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for raw in list(snapshot.get("validation_findings") or []):
        item = _mapping(raw)
        severity = _text(item.get("severity")).lower()
        if bool(item.get("blocking")) or severity == "error":
            rows.append(
                {
                    "rule_id": _text(item.get("rule_id")) or "canonical_runtime_block",
                    "message": _finding_detail(item) or "canonical runtime 返回计算阻断项。",
                }
            )
    declared = int(_mapping(snapshot.get("validation_summary")).get("blocking_count") or 0)
    if declared and not rows:
        rows.append(
            {
                "rule_id": "canonical_runtime_blocking_count",
                "message": f"canonical runtime 记录了 {declared} 个计算阻断项。",
            }
        )
    return rows


def _current_runtime_context(
    result: dict[str, Any], current_input_signature: str | None
) -> dict[str, Any]:
    expected_signature = _text(current_input_signature) or _text(result.get("input_signature"))
    if not expected_signature or _text(result.get("input_signature")) != expected_signature:
        raise ProfessionalReviewPackageError("当前结果已因输入变化而失效。")
    formal_context = _mapping(result.get("formal_project_context"))
    if _text(formal_context.get("construct_review_status")) == "needs_review":
        raise ProfessionalReviewPackageError("第一步项目背景已变化，当前构建需要重新审查。")
    try:
        cassette = active_construct_snapshot(result.get("runtime"))
        plasmid = active_complete_plasmid_snapshot(result.get("runtime"))
    except CanonicalConstructRuntimeError as exc:
        raise ProfessionalReviewPackageError("没有当前完整载体构建设计。") from exc
    if _text(cassette.get("construct_status")) != "current" or _text(plasmid.get("construct_status")) != "current":
        raise ProfessionalReviewPackageError("当前 canonical 构建已失效或存在计算阻断。")
    if not _text(plasmid.get("sequence")):
        raise ProfessionalReviewPackageError("完整构建序列为空。")
    settings = _mapping(result.get("insertion_settings"))
    insertion_site = _mapping(plasmid.get("insertion_site"))
    expected_operation = {
        "mode": _text(settings.get("mode")),
        "start_coordinate": int(settings.get("start_coordinate") or 0),
        "end_coordinate": int(settings.get("end_coordinate") or 0),
        "insertion_orientation": _text(settings.get("insertion_orientation")) or "forward",
    }
    canonical_operation = {
        "mode": _text(insertion_site.get("mode")),
        "start_coordinate": int(insertion_site.get("start_coordinate") or 0),
        "end_coordinate": int(insertion_site.get("end_coordinate") or 0),
        "insertion_orientation": _text(insertion_site.get("insertion_orientation")) or "forward",
    }
    if expected_operation != canonical_operation:
        raise ProfessionalReviewPackageError("插入或替换参数已变化，当前完整构建结果已失效。")
    blocking = [*_blocking_findings(cassette), *_blocking_findings(plasmid)]
    if blocking:
        raise ProfessionalReviewPackageError(
            "当前构建存在计算阻断项：" + "；".join(item["message"] for item in blocking)
        )
    return {"cassette": cassette, "plasmid": plasmid, "formal_context": formal_context}


def _resolve_export_bytes(
    result: dict[str, Any], cassette: dict[str, Any], plasmid: dict[str, Any]
) -> dict[str, Any]:
    exports = _mapping(result.get("exports"))
    fasta = _mapping(exports.get("complete_plasmid_fasta") or exports.get("fasta"))
    genbank = _mapping(exports.get("complete_plasmid_genbank") or exports.get("genbank"))
    fasta_bytes = _bytes(fasta.get("data"))
    genbank_bytes = _bytes(genbank.get("data"))
    if not fasta_bytes or not genbank_bytes:
        raise ProfessionalReviewPackageError("完整质粒 FASTA 或 GenBank 独立导出字节缺失。")
    metadata = _mapping(exports.get("metadata"))
    if metadata:
        if int(metadata.get("sequence_length") or 0) != int(plasmid.get("sequence_length") or 0):
            raise ProfessionalReviewPackageError("完整质粒导出长度不属于当前 canonical snapshot。")
        if _text(metadata.get("sequence_checksum")) != _text(plasmid.get("sequence_checksum")):
            raise ProfessionalReviewPackageError("完整质粒导出 checksum 不属于当前 canonical snapshot。")
    fasta_sequence, fasta_record = _parse_single_sequence(fasta_bytes, "fasta", "完整质粒 FASTA")
    genbank_sequence, genbank_record = _parse_single_sequence(genbank_bytes, "genbank", "完整质粒 GenBank")
    canonical_sequence = _text(plasmid.get("sequence")).upper()
    if fasta_sequence != canonical_sequence or genbank_sequence != canonical_sequence:
        raise ProfessionalReviewPackageError("FASTA、GenBank 和 canonical 完整构建序列不一致。")
    canonical_topology = _text(plasmid.get("topology")).lower() or "circular"
    genbank_topology = _text(genbank_record.annotations.get("topology")).lower() or "circular"
    if genbank_topology != canonical_topology:
        raise ProfessionalReviewPackageError("GenBank 与 canonical 完整构建拓扑不一致。")
    cassette_fasta = _mapping(_mapping(result.get("cassette_exports")).get("fasta"))
    if not cassette_fasta.get("data"):
        try:
            cassette_fasta = _mapping(
                export_active_construct(
                    result.get("runtime"), project_name=_text(result.get("project_name"))
                ).get("fasta")
            )
        except CanonicalConstructRuntimeError as exc:
            raise ProfessionalReviewPackageError(
                "表达盒 FASTA 无法从当前 canonical snapshot 导出。"
            ) from exc
    cassette_fasta_bytes = _bytes(cassette_fasta.get("data"))
    cassette_sequence, cassette_record = _parse_single_sequence(
        cassette_fasta_bytes, "fasta", "表达盒 FASTA"
    )
    if cassette_sequence != _text(cassette.get("sequence")).upper():
        raise ProfessionalReviewPackageError("表达盒 FASTA 与 canonical 表达盒序列不一致。")
    return {
        "fasta_bytes": fasta_bytes,
        "genbank_bytes": genbank_bytes,
        "cassette_fasta_bytes": cassette_fasta_bytes,
        "fasta_record": fasta_record,
        "genbank_record": genbank_record,
        "cassette_record": cassette_record,
        "sequence_consistency": {
            "status": "consistent",
            "canonical_length_bp": len(canonical_sequence),
            "fasta_length_bp": len(fasta_sequence),
            "genbank_length_bp": len(genbank_sequence),
            "canonical_sequence_sha256": _sequence_sha256(canonical_sequence),
        },
    }


def _active_asset_contexts(
    result: dict[str, Any], cassette: dict[str, Any], plasmid: dict[str, Any]
) -> list[dict[str, Any]]:
    runtime = _mapping(cassette.get("runtime"))
    records = _mapping(result.get("input_records"))
    assets = {
        _text(item.get("asset_id")): _mapping(item)
        for item in list(runtime.get("sequence_assets") or [])
    }
    components = {
        _text(item.get("component_type")).lower(): _mapping(item)
        for item in list(runtime.get("components") or [])
    }
    rows: list[dict[str, Any]] = []
    for role in ("promoter", "cds", "terminator"):
        component = components.get(role, {})
        asset = assets.get(_text(component.get("sequence_asset_id")), {})
        record = _mapping(records.get(role))
        sequence = _text(asset.get("nucleotide_sequence")).upper()
        if not sequence:
            raise ProfessionalReviewPackageError(f"活动元件 {role} 缺少实际 DNA 序列。")
        if sequence != _text(record.get("normalized_sequence")).upper():
            raise ProfessionalReviewPackageError(f"活动元件 {role} 与当前输入记录不一致。")
        rows.append({"role": role, "record": record, "asset": asset, "component": component})
    backbone_id = _text(plasmid.get("backbone_asset_id"))
    backbone_asset = assets.get(backbone_id, {})
    backbone_record = _mapping(records.get("backbone"))
    backbone_sequence = _text(backbone_asset.get("nucleotide_sequence")).upper()
    if not backbone_sequence:
        raise ProfessionalReviewPackageError("活动骨架缺少实际 DNA 序列。")
    if backbone_sequence != _text(backbone_record.get("normalized_sequence")).upper():
        raise ProfessionalReviewPackageError("活动骨架与当前输入记录不一致。")
    rows.append(
        {
            "role": "backbone",
            "record": backbone_record,
            "asset": backbone_asset,
            "component": {},
        }
    )
    return rows


def _extract_accession(*values: Any) -> str:
    for value in values:
        match = _ACCESSION_RE.search(_text(value))
        if match:
            return match.group(1).upper()
    return ""


def _source_classification(
    role: str, record: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    kind = _text(record.get("source_kind")).lower()
    name = _text(record.get("source_name"))
    display_name = _text(record.get("display_name")) or role
    cds_basis = _mapping(_mapping(result.get("cds_input")).get("source_review_basis"))
    public_basis = role == "cds" and (
        "公共数据库" in _text(cds_basis.get("source_type"))
        or "public" in _text(cds_basis.get("source_type")).lower()
    )
    demo_asset = (
        kind == "example"
        or "内置" in name
        or "演示" in name
        or "演示" in display_name
        or "测试" in display_name
    )
    accession = _extract_accession(
        record.get("source_accession_version"),
        name,
        record.get("source_reference"),
        record.get("original_text"),
    )
    source_reference = _text(
        record.get("source_reference")
        or record.get("source_accession_version")
        or record.get("source_rationale")
        or record.get("source_definition")
    )
    missing: list[str] = []
    review: list[str] = []
    if demo_asset:
        source_type = "demo_or_test_asset"
        source_reference = f"内置演示或测试资产：{name or display_name}"
        missing.append("缺少可追溯的具体来源引用")
        review.append("确认该演示或测试资产是否应替换为具有明确来源的序列记录")
    elif public_basis or kind in {"public_database", "database", "ncbi"}:
        source_type = "public_database"
        source_reference = accession
        if not accession:
            missing.append("公共数据库 accession 缺失")
        review.append("核对 accession、记录版本和实际使用区段")
    elif kind in {"upload", "uploaded", "user_uploaded"}:
        source_type = "uploaded_file"
        file_name = PurePosixPath(name.replace("\\", "/")).name
        record_id = _text(
            record.get("original_record_identifier")
            or record.get("source_record_name")
            or record.get("record_name")
        )
        source_reference = "#".join(part for part in (file_name, record_id) if part)
        if not file_name:
            missing.append("原始文件名缺失")
        if not record_id:
            missing.append("文件内记录标识缺失")
        review.append("核对上传文件、记录标识和所用序列区段")
    elif kind in {"paste", "pasted", "user_pasted", "user_recorded", "user_provided"}:
        source_type = "user_provided"
        if not _is_present(source_reference):
            missing.append("用户提供序列的来源说明缺失")
        review.append("核对用户提供序列的来源说明和编辑记录")
    else:
        source_type = "local_library"
        source_reference = source_reference or name
        if not _is_present(source_reference):
            missing.append("本地元件库来源引用缺失")
        review.append("核对本地元件库记录标识和来源说明")
    return {
        "source_type": source_type,
        "source_reference": source_reference or "not_provided",
        "accession_or_file": accession or source_reference or name or "not_provided",
        "missing": missing,
        "review": review,
    }


def _existing_manual_review_items(result: dict[str, Any]) -> list[dict[str, str]]:
    raw_items: list[Any] = []
    raw_items.extend(list(_mapping(result.get("cds_input")).get("manual_review_items") or []))
    raw_items.extend(
        list(_mapping(result.get("formal_expression_cassette")).get("manual_confirmation_items") or [])
    )
    settings = _mapping(result.get("insertion_settings"))
    if not bool(settings.get("construction_strategy_confirmed")):
        raw_items.append(
            {
                "rule_id": "construction_strategy_manual_review",
                "message": "构建策略尚未由用户记录确认，需要专业复核。",
            }
        )
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_items:
        item = _mapping(raw)
        rule_id = _text(item.get("rule_id")) or "manual_review_item"
        message = _finding_detail(item)
        if not message:
            continue
        identity = (rule_id, message)
        if identity in seen:
            continue
        seen.add(identity)
        normalized.append({"rule_id": rule_id, "message": message})
    return normalized


def _provenance_rows(
    result: dict[str, Any], assets: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    manual_items = _existing_manual_review_items(result)
    manual_by_rule = {item["rule_id"]: item["message"] for item in manual_items}
    rows: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []
    for context in assets:
        role = _text(context.get("role"))
        record = _mapping(context.get("record"))
        asset = _mapping(context.get("asset"))
        component = _mapping(context.get("component"))
        source = _source_classification(role, record, result)
        missing = list(source["missing"])
        review = list(source["review"])
        if role == "cds" and "accession_unverified" in manual_by_rule:
            missing.append("accession 尚未联网核实")
            review.append(manual_by_rule["accession_unverified"])
        sequence = _text(asset.get("nucleotide_sequence")).upper()
        row = {
            "asset_name": _text(asset.get("display_name")) or _text(record.get("display_name")) or role,
            "biological_role": role,
            "sequence_length_bp": len(sequence),
            "sequence_sha256": _sequence_sha256(sequence),
            "source_type": source["source_type"],
            "source_reference": source["source_reference"],
            "accession_or_file": source["accession_or_file"],
            "user_edited_status": "user_edited" if bool(component.get("user_edited")) else "not_recorded_as_edited",
            "review_status": "pending" if missing else "recorded",
            "missing_information": "；".join(dict.fromkeys(missing)),
            "professional_review_items": "；".join(dict.fromkeys(review)),
        }
        rows.append(row)
        if missing:
            gaps.append(
                {
                    "asset_name": str(row["asset_name"]),
                    "biological_role": role,
                    "missing_information": str(row["missing_information"]),
                }
            )
    return rows, gaps


def _t_dna_gate(result: dict[str, Any]) -> dict[str, Any]:
    settings = _mapping(result.get("insertion_settings"))
    backbone = _mapping(_mapping(result.get("input_records")).get("backbone"))
    confirmation = _mapping(settings.get("t_dna_confirmation"))
    operation = validate_t_dna_operation(
        backbone,
        confirmation=confirmation,
        insertion_settings=settings,
        workflow_id=_text(settings.get("workflow_id")) or "formal_single_gene",
    )
    if not bool(operation.get("allowed")):
        if _text(operation.get("status")) == "needs_manual_confirmation":
            raise ProfessionalReviewPackageError("T-DNA 确认缺失或已过期。")
        raise ProfessionalReviewPackageError(
            "插入或替换操作未通过已确认 T-DNA 区域门禁：" + _text(operation.get("reason"))
        )
    return {
        "status": "passed",
        "operation_status": _text(operation.get("status")),
        "reason": _text(operation.get("reason")),
        "direction": _text(confirmation.get("direction")),
        "lb": _mapping(confirmation.get("lb")),
        "rb": _mapping(confirmation.get("rb")),
        "region": _mapping(confirmation.get("region")),
        "confirmation_signature": _text(confirmation.get("confirmation_signature")),
    }


def _prepared_package_context(
    result: dict[str, Any], current_input_signature: str | None
) -> dict[str, Any]:
    runtime = _current_runtime_context(result, current_input_signature)
    cassette = runtime["cassette"]
    plasmid = runtime["plasmid"]
    exports = _resolve_export_bytes(result, cassette, plasmid)
    assets = _active_asset_contexts(result, cassette, plasmid)
    provenance_rows, provenance_gaps = _provenance_rows(result, assets)
    manual_items = _existing_manual_review_items(result)
    t_dna = _t_dna_gate(result)
    status = REVIEW_NEEDS_PROVENANCE if provenance_gaps or manual_items else REVIEW_READY
    return {
        **runtime,
        **exports,
        "assets": assets,
        "provenance_rows": provenance_rows,
        "provenance_gaps": provenance_gaps,
        "manual_review_items": manual_items,
        "t_dna_gate": t_dna,
        "review_status": status,
    }


def assess_professional_review_package(
    result: dict[str, Any], *, current_input_signature: str | None = None
) -> dict[str, Any]:
    """Assess export gates without creating or persisting ZIP bytes."""
    try:
        prepared = _prepared_package_context(result, current_input_signature)
    except ProfessionalReviewPackageError as exc:
        return {
            "review_status": REVIEW_BLOCKED,
            "wet_lab_readiness": WET_LAB_READINESS,
            "blocking_count": 1,
            "provenance_gap_count": 0,
            "manual_review_count": 0,
            "blocking_reasons": [str(exc)],
            "provenance_gaps": [],
            "manual_review_items": [],
        }
    return {
        "review_status": prepared["review_status"],
        "wet_lab_readiness": WET_LAB_READINESS,
        "blocking_count": 0,
        "provenance_gap_count": len(prepared["provenance_gaps"]),
        "manual_review_count": len(prepared["manual_review_items"]),
        "blocking_reasons": [],
        "provenance_gaps": prepared["provenance_gaps"],
        "manual_review_items": prepared["manual_review_items"],
        "t_dna_gate": prepared["t_dna_gate"],
        "sequence_consistency": prepared["sequence_consistency"],
    }


def _feature_sequence(sequence: str, row: dict[str, Any]) -> str:
    parts = list(row.get("location_parts") or [])
    if not parts:
        parts = [{"start": row.get("start"), "end": row.get("end"), "strand": row.get("strand", 1)}]
    fragments: list[str] = []
    for part in parts:
        start = int(part.get("start") or 0)
        end = int(part.get("end") or 0)
        if start < 1 or end < start or end > len(sequence):
            raise ProfessionalReviewPackageError("活动元件坐标超出 canonical 完整构建序列。")
        fragment = sequence[start - 1 : end]
        if int(part.get("strand") or row.get("strand") or 1) < 0:
            fragment = str(Seq(fragment).reverse_complement())
        fragments.append(fragment)
    if int(row.get("strand") or 1) < 0 and len(parts) > 1:
        fragments.reverse()
    return "".join(fragments)


def _component_inventory_rows(
    prepared: dict[str, Any]
) -> list[dict[str, Any]]:
    plasmid = prepared["plasmid"]
    sequence = _text(plasmid.get("sequence")).upper()
    source_by_role = {
        str(row["biological_role"]): row for row in prepared["provenance_rows"]
    }
    rows: list[dict[str, Any]] = []
    for raw in list(plasmid.get("feature_rows") or []):
        row = _mapping(raw)
        source_scope = _text(row.get("source"))
        role = _text(row.get("feature_type")) or "misc_feature"
        source_role = role.lower() if source_scope == "transcription_unit" else "backbone"
        source = source_by_role.get(source_role, source_by_role.get("backbone", {}))
        feature_sequence = _feature_sequence(sequence, row)
        rows.append(
            {
                "component_name": _text(row.get("name")) or role,
                "biological_role": role,
                "length_bp": len(feature_sequence),
                "start_1_based": int(row.get("start") or 0),
                "end_1_based": int(row.get("end") or 0),
                "strand": int(row.get("strand") or 1),
                "expression_cassette": _text(row.get("unit_id")) or ("TU1" if source_scope == "transcription_unit" else ""),
                "source_type": _text(source.get("source_type")) or "not_provided",
                "source_reference": _text(source.get("source_reference")) or "not_provided",
                "sequence_sha256": _sequence_sha256(feature_sequence),
            }
        )
    if not rows:
        raise ProfessionalReviewPackageError("完整构建缺少可交付的活动元件坐标。")
    return rows


def _construct_summary(result: dict[str, Any], prepared: dict[str, Any]) -> dict[str, Any]:
    records = _mapping(result.get("input_records"))
    settings = _mapping(result.get("insertion_settings"))
    cassette = prepared["cassette"]
    plasmid = prepared["plasmid"]
    context = _mapping(result.get("formal_project_context"))
    definition = _mapping(context.get("project_definition"))
    cds_record = _mapping(records.get("cds"))
    cds_info = _mapping(_mapping(result.get("cds_input")).get("gene_information"))
    t_dna = prepared["t_dna_gate"]
    return {
        "project_definition": definition,
        "target_gene": {
            "name": _text(cds_info.get("gene_name")) or _text(cds_record.get("display_name")),
            "symbol": _text(cds_info.get("gene_symbol")),
            "source_species": _text(cds_info.get("source_species")),
        },
        "cds_summary": {
            "name": _text(cds_record.get("display_name")),
            "length_bp": int(cds_record.get("length") or 0),
            "sequence_sha256": _sequence_sha256(_text(cds_record.get("normalized_sequence"))),
        },
        "expression_cassette_summary": {
            "length_bp": int(cassette.get("sequence_length") or 0),
            "sequence_sha256": _sequence_sha256(_text(cassette.get("sequence"))),
            "components": list(_mapping(result.get("formal_expression_cassette")).get("components") or []),
        },
        "backbone_summary": {
            "name": _text(_mapping(records.get("backbone")).get("display_name")),
            "length_bp": int(_mapping(records.get("backbone")).get("length") or 0),
            "topology": _text(_mapping(records.get("backbone")).get("topology")),
        },
        "t_dna": {
            "lb": t_dna["lb"],
            "rb": t_dna["rb"],
            "region": t_dna["region"],
            "direction": t_dna["direction"],
            "gate_status": t_dna["status"],
        },
        "insertion_operation": {
            "mode": _text(settings.get("mode")),
            "start_1_based": int(settings.get("start_coordinate") or 0),
            "end_1_based": int(settings.get("end_coordinate") or 0),
            "orientation": _text(settings.get("insertion_orientation")) or "forward",
            "expected_removed_sequence": _text(settings.get("expected_removed_sequence")).upper(),
        },
        "complete_construct": {
            "length_bp": int(plasmid.get("sequence_length") or 0),
            "topology": _text(plasmid.get("topology")),
            "canonical_sequence_sha256": _sequence_sha256(_text(plasmid.get("sequence"))),
            "construct_status": _text(plasmid.get("construct_status")),
        },
        "review_status": prepared["review_status"],
        "wet_lab_readiness": WET_LAB_READINESS,
    }


def _validation_report(prepared: dict[str, Any]) -> dict[str, Any]:
    plasmid = prepared["plasmid"]
    findings = [_mapping(item) for item in list(plasmid.get("validation_findings") or [])]
    information = [
        {
            "rule_id": _text(item.get("rule_id")),
            "message": _finding_detail(item),
        }
        for item in findings
        if not bool(item.get("blocking"))
        and _text(item.get("severity")).lower() not in {"warning", "error"}
    ]
    return {
        "review_status": prepared["review_status"],
        "wet_lab_readiness": WET_LAB_READINESS,
        "blocking": [],
        "manual_confirmation_required": prepared["manual_review_items"],
        "passed_software_checks": [
            {
                "check_id": "canonical_construct_current",
                "message": "当前 canonical 完整构建状态有效。",
            },
            {
                "check_id": "sequence_exports_consistent",
                "message": "完整质粒 FASTA、GenBank 与 canonical 序列一致。",
            },
            {
                "check_id": "t_dna_operation_inside_confirmed_region",
                "message": "插入或替换操作位于已确认的 T-DNA 区域内。",
            },
        ],
        "information": information,
        "t_dna_gate": prepared["t_dna_gate"],
        "sequence_consistency": prepared["sequence_consistency"],
        "zip_internal_integrity": {
            "status": "verified_by_builder",
            "checksum_scope": list(CHECKSUM_FILES),
            "checksums_file_self_hash": "not_applicable_due_to_self_reference",
        },
        "boundary": (
            "该报告仅记录软件层面的序列、结构、坐标和文件一致性检查；"
            "不构成实验验证、表达成功判断或湿实验可行性结论。"
        ),
    }


def _readme_bytes(project_name: str, prepared: dict[str, Any]) -> bytes:
    lines = [
        "# BioDesign Studio 专业审查交付包",
        "",
        f"- 项目名称：{project_name}",
        f"- 当前审查状态：`{prepared['review_status']}`",
        f"- wet_lab_readiness: `{WET_LAB_READINESS}`",
        "",
        "## 用途与边界",
        "",
        "当前软件用于植物表达载体的计算设计、计算校验、项目保存和文件导出；尚未经过湿实验验证，不代表实际表达成功或湿实验就绪。",
        "本包为 documentation-only 交付，不代表实验验证、表达成功、构建可行性批准或湿实验就绪判断。",
        "本包不包含实验步骤、培养条件、转化方案或任何虚构的公司要求。",
        "",
        "## 文件导览",
        "",
        "- `manifest.json`：项目、快照、状态、payload 文件大小与 SHA-256。",
        "- `complete_plasmid.fasta`：与结果页独立下载一致的完整质粒 FASTA。",
        "- `complete_plasmid.gb`：与结果页独立下载一致的完整质粒 GenBank。",
        "- `expression_cassette.fasta`：当前 canonical 植物表达盒序列。",
        "- `construct_summary.json`：项目、CDS、表达盒、骨架、T-DNA 与插入参数摘要。",
        "- `component_inventory.csv`：活动 feature 的坐标、方向、来源与序列 SHA-256。",
        "- `provenance_review.csv`：活动序列资产的来源状态、缺口和专业复核事项。",
        "- `validation_report.json`：计算阻断、人工确认、T-DNA 与序列一致性结果。",
        "- `checksums.sha256`：除自身外九个文件的稳定顺序 SHA-256。",
        "",
        "`manifest.json` 校验八个 payload 文件；`checksums.sha256` 另校验 manifest。",
        "manifest 与 checksums 不记录各自的自哈希，以避免不可实现的自引用校验。",
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _build_zip(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
        strict_timestamps=True,
    ) as archive:
        for name in PACKAGE_FILES:
            archive.writestr(
                _zip_info(name),
                files[name],
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return output.getvalue()


def validate_professional_review_package_bytes(data: bytes) -> dict[str, Any]:
    """Verify names, checksums, manifest payload hashes, and sequence agreement."""
    try:
        with zipfile.ZipFile(BytesIO(data), "r") as archive:
            names = archive.namelist()
            if names != list(PACKAGE_FILES) or len(set(names)) != len(names):
                raise ProfessionalReviewPackageError("ZIP 内部文件清单或顺序不正确。")
            files = {name: archive.read(name) for name in names}
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ProfessionalReviewPackageError("ZIP 无法读取或文件不完整。") from exc
    checksum_lines = files["checksums.sha256"].decode("utf-8").splitlines()
    if len(checksum_lines) != len(CHECKSUM_FILES):
        raise ProfessionalReviewPackageError("checksums.sha256 条目数量不正确。")
    checksum_names: list[str] = []
    for line in checksum_lines:
        try:
            expected, name = line.split("  ", 1)
        except ValueError as exc:
            raise ProfessionalReviewPackageError("checksums.sha256 格式不正确。") from exc
        checksum_names.append(name)
        if name not in files or _sha256(files[name]) != expected:
            raise ProfessionalReviewPackageError(f"ZIP 内部文件校验失败：{name}")
    if checksum_names != list(CHECKSUM_FILES):
        raise ProfessionalReviewPackageError("checksums.sha256 文件顺序不正确。")
    try:
        manifest = json.loads(files["manifest.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProfessionalReviewPackageError("manifest.json 无法解析。") from exc
    if manifest.get("package_file_order") != list(PACKAGE_FILES):
        raise ProfessionalReviewPackageError("manifest.json 文件顺序不正确。")
    payload_entries = list(manifest.get("payload_files") or [])
    if [item.get("name") for item in payload_entries] != list(PAYLOAD_FILES):
        raise ProfessionalReviewPackageError("manifest.json payload 文件清单不正确。")
    for item in payload_entries:
        name = str(item["name"])
        if int(item.get("size_bytes") or -1) != len(files[name]):
            raise ProfessionalReviewPackageError(f"manifest.json 文件大小不正确：{name}")
        if str(item.get("sha256") or "") != _sha256(files[name]):
            raise ProfessionalReviewPackageError(f"manifest.json 文件 hash 不正确：{name}")
    fasta_sequence, _ = _parse_single_sequence(
        files["complete_plasmid.fasta"], "fasta", "完整质粒 FASTA"
    )
    genbank_sequence, _ = _parse_single_sequence(
        files["complete_plasmid.gb"], "genbank", "完整质粒 GenBank"
    )
    if fasta_sequence != genbank_sequence:
        raise ProfessionalReviewPackageError("ZIP 内 FASTA 与 GenBank 序列不一致。")
    if _sequence_sha256(fasta_sequence) != str(manifest.get("canonical_sequence_sha256") or ""):
        raise ProfessionalReviewPackageError("ZIP 内序列与 manifest canonical hash 不一致。")
    return {
        "verified": True,
        "files": list(PACKAGE_FILES),
        "manifest": manifest,
        "file_checksums": {name: _sha256(files[name]) for name in CHECKSUM_FILES},
    }


def build_professional_review_package(
    result: dict[str, Any], *, current_input_signature: str | None = None
) -> dict[str, Any]:
    """Build a deterministic, flat ten-file professional-review ZIP."""
    prepared = _prepared_package_context(result, current_input_signature)
    project_name = project_display_name(result, prepared["plasmid"])
    inventory_rows = _component_inventory_rows(prepared)
    files: dict[str, bytes] = {
        "README.md": _readme_bytes(project_name, prepared),
        "complete_plasmid.fasta": prepared["fasta_bytes"],
        "complete_plasmid.gb": prepared["genbank_bytes"],
        "expression_cassette.fasta": prepared["cassette_fasta_bytes"],
        "construct_summary.json": _json_bytes(_construct_summary(result, prepared)),
        "component_inventory.csv": _csv_bytes(inventory_rows, COMPONENT_INVENTORY_COLUMNS),
        "provenance_review.csv": _csv_bytes(prepared["provenance_rows"], PROVENANCE_REVIEW_COLUMNS),
        "validation_report.json": _json_bytes(_validation_report(prepared)),
    }
    manifest = {
        "package_version": PACKAGE_VERSION,
        "project_id": _text(result.get("project_id")),
        "project_name": project_name,
        "construct_status": _text(prepared["plasmid"].get("construct_status")),
        "review_status": prepared["review_status"],
        "wet_lab_readiness": WET_LAB_READINESS,
        "complete_plasmid": {
            "length_bp": int(prepared["plasmid"].get("sequence_length") or 0),
            "topology": _text(prepared["plasmid"].get("topology")),
        },
        "canonical_sequence_sha256": _sequence_sha256(_text(prepared["plasmid"].get("sequence"))),
        "snapshot_version": {
            "complete_plasmid_revision": _text(prepared["plasmid"].get("revision_id")),
            "expression_cassette_revision": _text(prepared["cassette"].get("revision_id")),
            "input_signature": _text(result.get("input_signature")),
        },
        "package_file_order": list(PACKAGE_FILES),
        "payload_files": [
            {"name": name, "size_bytes": len(files[name]), "sha256": _sha256(files[name])}
            for name in PAYLOAD_FILES
        ],
        "integrity_scope": {
            "manifest_payload_hashes": list(PAYLOAD_FILES),
            "checksums_file_hashes": list(CHECKSUM_FILES),
        },
    }
    files["manifest.json"] = _json_bytes(manifest)
    files["checksums.sha256"] = "".join(
        f"{_sha256(files[name])}  {name}\n" for name in CHECKSUM_FILES
    ).encode("utf-8")
    data = _build_zip(files)
    verification = validate_professional_review_package_bytes(data)
    return {
        "data": data,
        "mime": PACKAGE_MIME,
        "file_name": f"{_safe_file_stem(project_name)}_专业审查交付包.zip",
        "project_name": project_name,
        "files": list(PACKAGE_FILES),
        "file_checksums": verification["file_checksums"],
        "sha256": _sha256(data),
        "manifest": manifest,
        "review_status": prepared["review_status"],
        "wet_lab_readiness": WET_LAB_READINESS,
        "blocking_count": 0,
        "provenance_gap_count": len(prepared["provenance_gaps"]),
        "manual_review_count": len(prepared["manual_review_items"]),
        "provenance_gaps": prepared["provenance_gaps"],
        "manual_review_items": prepared["manual_review_items"],
        "verification": verification,
    }
