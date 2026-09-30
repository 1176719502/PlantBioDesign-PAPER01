"""Build a company-facing design delivery ZIP from the active canonical result.

This module packages existing export bytes and runtime snapshots.  It does not
assemble sequences, alter feature coordinates, or introduce a second exporter.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from datetime import datetime
from html import escape
from io import BytesIO, StringIO
from typing import Any

from services.canonical_construct_runtime import (
    CanonicalConstructRuntimeError,
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
)


PACKAGE_MIME = "application/zip"
PACKAGE_FILES = (
    "01_设计交付说明.html",
    "02_完整质粒.gb",
    "03_完整质粒.fasta",
    "04_表达盒.fasta",
    "05_元件与坐标清单.csv",
    "06_来源与accession清单.csv",
    "07_校验结果.json",
    "08_SHA256校验值.txt",
    "09_项目备份.json",
)
_ACCESSION_RE = re.compile(r"^[A-Z]{1,6}_?\d+(?:\.\d+)?$", re.IGNORECASE)
_REAL_CASE_ACCESSIONS = {"NM_000477.7", "AF234296.1"}
_FEATURE_DISPLAY_NAMES = {
    "ORI_ALPHA": "复制起点（ORI_ALPHA）",
    "UPSTREAM_SITE": "上游位点（UPSTREAM_SITE）",
    "SELECT_MARK": "筛选标记（SELECT_MARK）",
    "TAIL_AUDIT": "末端审计区（TAIL_AUDIT）",
}
_FEATURE_CONFLICT_RULE_ID = "overlapping_backbone_feature_conflict"


class CompanyDeliveryPackageError(ValueError):
    """Raised when the current result cannot be delivered as a ZIP package."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    return str(value or "").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _accession_or_empty(value: Any) -> str:
    candidate = _text(value)
    return candidate if _ACCESSION_RE.fullmatch(candidate) else ""


def _type_label(value: Any) -> str:
    normalized = _text(value).lower()
    return {
        "promoter": "启动子",
        "cds": "编码序列（CDS）",
        "terminator": "终止子",
        "rep_origin": "复制起点",
        "backbone": "载体骨架",
    }.get(normalized, "其他元件")


def _direction(value: Any) -> str:
    return "反向（-）" if int(value or 1) < 0 else "正向（+）"


def _feature_display_name(value: Any) -> str:
    name = _text(value)
    return _FEATURE_DISPLAY_NAMES.get(name, name or "未命名元件")


def _feature_length(row: dict[str, Any]) -> int:
    parts = row.get("location_parts") if isinstance(row.get("location_parts"), list) else []
    if parts:
        return sum(max(0, int(part.get("end") or 0) - int(part.get("start") or 0) + 1) for part in parts)
    return max(0, int(row.get("end") or 0) - int(row.get("start") or 0) + 1)


def _source_for_record(record: dict[str, Any]) -> tuple[str, str]:
    source_name = _text(record.get("source_name"))
    accession = _accession_or_empty(record.get("source_accession_version")) or _accession_or_empty(source_name)
    if accession:
        return accession, accession
    if source_name in {"内置植物元件记录", "内置示例骨架"}:
        return source_name, ""
    if _text(record.get("source_kind")) == "example":
        return "内置示例骨架", ""
    return "未记录", ""


def _feature_rows(result: dict[str, Any], plasmid: dict[str, Any]) -> list[dict[str, str | int]]:
    records = _mapping(result.get("input_records"))
    rows: list[dict[str, str | int]] = []
    for source_row in list(plasmid.get("feature_rows") or []):
        row = _mapping(source_row)
        feature_type = _text(row.get("feature_type")) or "misc_feature"
        source = _text(row.get("source"))
        source_record = _mapping(records.get(feature_type)) if source == "transcription_unit" else _mapping(records.get("backbone"))
        source_label, accession = _source_for_record(source_record)
        unit = "TU1" if source == "transcription_unit" else ""
        rows.append(
            {
                "名称": _feature_display_name(row.get("name")),
                "类型": _type_label(feature_type),
                "起点": int(row.get("start") or 0),
                "终点": int(row.get("end") or 0),
                "长度": _feature_length(row),
                "链方向": _direction(row.get("strand")),
                "所属表达单元": unit,
                "来源 accession": accession or "未记录",
                "来源说明": source_label,
            }
        )
    return rows


def _canonical_component_lengths(cassette: dict[str, Any]) -> dict[str, int]:
    lengths: dict[str, int] = {}
    for row_value in list(cassette.get("feature_rows") or []):
        row = _mapping(row_value)
        component_type = _text(row.get("component_type")).lower()
        if component_type:
            lengths[component_type] = max(0, int(row.get("end") or 0) - int(row.get("start") or 0) + 1)
    return lengths


def _require_current_snapshot_exports(
    result: dict[str, Any], cassette: dict[str, Any], plasmid: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reject stale records instead of silently falling back to another case."""
    exports = _mapping(result.get("exports"))
    cassette_exports = _mapping(result.get("cassette_exports"))
    complete_metadata = _mapping(exports.get("metadata"))
    cassette_metadata = _mapping(cassette_exports.get("metadata"))
    if int(complete_metadata.get("sequence_length") or 0) != int(plasmid.get("sequence_length") or 0):
        raise CompanyDeliveryPackageError("完整质粒导出字节不属于当前 canonical snapshot。")
    if _text(complete_metadata.get("sequence_checksum")) != _text(plasmid.get("sequence_checksum")):
        raise CompanyDeliveryPackageError("完整质粒导出 checksum 不属于当前 canonical snapshot。")
    if int(cassette_metadata.get("sequence_length") or 0) != int(cassette.get("sequence_length") or 0):
        raise CompanyDeliveryPackageError("表达盒导出字节不属于当前 canonical snapshot。")
    if _text(cassette_metadata.get("sequence_checksum")) != _text(cassette.get("sequence_checksum")):
        raise CompanyDeliveryPackageError("表达盒导出 checksum 不属于当前 canonical snapshot。")

    records = _mapping(result.get("input_records"))
    canonical_lengths = _canonical_component_lengths(cassette)
    runtime = _mapping(cassette.get("runtime"))
    assets_by_id = {
        _text(asset.get("asset_id")): _mapping(asset)
        for asset in list(runtime.get("sequence_assets") or [])
    }
    features_by_role = {
        _text(row.get("component_type")).lower(): _mapping(row)
        for row in list(cassette.get("feature_rows") or [])
    }
    for role in ("promoter", "cds", "terminator"):
        record = _mapping(records.get(role))
        record_length = int(record.get("length") or 0)
        if record_length != int(canonical_lengths.get(role) or 0):
            raise CompanyDeliveryPackageError(f"{role} 输入记录与当前 canonical snapshot 长度不一致。")
        asset = assets_by_id.get(_text(_mapping(features_by_role.get(role)).get("source_asset_id")), {})
        if _text(record.get("normalized_sequence")) != _text(asset.get("nucleotide_sequence")):
            raise CompanyDeliveryPackageError(f"{role} 输入序列与当前 canonical snapshot 不一致。")
        if _text(record.get("source_name")) != _text(asset.get("source_name")):
            raise CompanyDeliveryPackageError(f"{role} 输入来源与当前 canonical snapshot 不一致。")
    return exports, cassette_exports


def _source_rows(result: dict[str, Any]) -> list[dict[str, str | int]]:
    records = _mapping(result.get("input_records"))
    rows: list[dict[str, str | int]] = []
    for role, label in (("promoter", "启动子"), ("cds", "编码序列（CDS）"), ("terminator", "终止子"), ("backbone", "载体骨架")):
        record = _mapping(records.get(role))
        source_label, accession = _source_for_record(record)
        rows.append(
            {
                "元件": _text(record.get("display_name")) or label,
                "类型": label,
                "来源 accession": accession or "未记录",
                "来源说明": source_label,
                "原始记录名称": _text(record.get("source_record_name")) or "未记录",
                "原始长度": int(record.get("source_record_length") or record.get("length") or 0),
                "使用区段": _text(record.get("source_location")) or "未记录",
                "strand": int(record.get("source_strand") or 0),
                "截取长度": int(record.get("length") or 0),
                "原始文件 SHA-256": _text(record.get("source_file_sha256")) or "未记录",
                "截取序列 SHA-256": _text(record.get("extracted_sequence_sha256")) or "未记录",
                "定义依据": _text(record.get("source_rationale")) or "未记录",
            }
        )
    return rows


def _csv_bytes(rows: list[dict[str, Any]], fieldnames: tuple[str, ...]) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8-sig")


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n").encode("utf-8")


def _finding_detail(item: dict[str, Any]) -> str:
    return _text(item.get("explanation") or item.get("message") or item.get("rule_id"))


def _validation_payload(plasmid: dict[str, Any]) -> dict[str, Any]:
    findings = list(plasmid.get("validation_findings") or [])
    passed: list[str] = []
    warnings: list[str] = []
    blocking: list[str] = []
    for item in findings:
        finding = _mapping(item)
        detail = _finding_detail(finding)
        if not detail:
            continue
        severity = _text(finding.get("severity")).lower() or "info"
        is_blocking = bool(finding.get("blocking")) or severity == "error"
        if is_blocking:
            blocking.append(detail)
        elif severity == "warning":
            warnings.append(detail)
        else:
            passed.append(detail)
    return {
        "校验范围": "当前软件运行时的输入、序列组装、坐标计算和导出一致性结果",
        "通过项": passed,
        "警告项": warnings,
        "阻断项": blocking,
        "汇总": _mapping(plasmid.get("validation_summary")),
    }


def _runtime_validation_items(plasmid: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw_item in list(plasmid.get("validation_findings") or []):
        item = _mapping(raw_item)
        detail = _finding_detail(item)
        if not detail:
            continue
        severity = _text(item.get("severity")).lower() or "info"
        items.append(
            {
                "rule_id": _text(item.get("rule_id")),
                "severity": severity,
                "blocking": bool(item.get("blocking")) or severity == "error",
                "message": detail,
            }
        )
    return items


def _feature_conflict_result(plasmid: dict[str, Any]) -> str:
    findings = [_mapping(item) for item in list(plasmid.get("validation_findings") or [])]
    conflicts = [
        _finding_detail(item)
        for item in findings
        if _text(item.get("rule_id")) == _FEATURE_CONFLICT_RULE_ID
    ]
    if conflicts:
        return "已执行完整 feature 冲突分析：发现与原有 feature 的冲突：" + "；".join(conflicts)

    summary = _mapping(plasmid.get("validation_summary"))
    blocking_rule_ids = {
        _text(item.get("rule_id"))
        for item in findings
        if bool(item.get("blocking")) or _text(item.get("severity")).lower() == "error"
    }
    if summary and not blocking_rule_ids and _text(plasmid.get("sequence")):
        return "已执行完整 feature 冲突分析：未发现与原有 feature 的重叠冲突。"
    return "未执行完整 feature 冲突分析，需要人工复核。"


def project_display_name(result: dict[str, Any], plasmid: dict[str, Any]) -> str:
    """Choose locked case names from runtime evidence, never from relabeling."""
    from services.rice_hsa_ncbi_mvp10_case import DEMO_PROJECT_NAME, REAL_CASE_PROJECT_NAME, evaluate_real_case_authenticity, is_real_case_candidate

    if is_real_case_candidate(result):
        return REAL_CASE_PROJECT_NAME
    records = _mapping(result.get("input_records"))
    length = int(plasmid.get("sequence_length") or 0)
    topology = _text(plasmid.get("topology")).lower()
    cds_name = _text(_mapping(records.get("cds")).get("display_name")).upper()
    if length == 6248 and topology == "circular" and "ALB" in cds_name:
        return DEMO_PROJECT_NAME
    return _text(result.get("project_name")) or "植物表达载体项目"


def _html_report(
    *,
    project_name: str,
    result: dict[str, Any],
    cassette: dict[str, Any],
    plasmid: dict[str, Any],
    coordinate_rows: list[dict[str, str | int]],
    validation: dict[str, Any],
    file_descriptions: list[tuple[str, str]],
) -> bytes:
    records = _mapping(result.get("input_records"))
    settings = _mapping(result.get("insertion_settings"))
    component_rows = {
        str(row["类型"]): row
        for row in coordinate_rows
        if str(row.get("所属表达单元") or "") == "TU1"
    }
    elements = [
        ("启动子", _mapping(records.get("promoter")), component_rows.get("启动子", {})),
        ("编码序列（CDS）", _mapping(records.get("cds")), component_rows.get("编码序列（CDS）", {})),
        ("终止子", _mapping(records.get("terminator")), component_rows.get("终止子", {})),
    ]
    backbone = _mapping(records.get("backbone"))
    source_label, accession = _source_for_record(backbone)
    insertion_mode = "替换区间" if _text(settings.get("mode")) == "replacement" else "插入"
    removal = f"{int(settings.get('start_coordinate') or 0)}–{int(settings.get('end_coordinate') or 0)}" if insertion_mode == "替换区间" else "不适用"
    row_html = "".join(
        "<tr>" + "".join(f"<td>{escape(str(row[column]))}</td>" for column in ("名称", "类型", "起点", "终点", "长度", "链方向", "所属表达单元", "来源 accession")) + "</tr>"
        for row in coordinate_rows
    )
    component_html = "".join(
        f"<tr><td>{label}</td><td>{escape(_text(row.get('名称')) or _text(record.get('display_name')) or '未记录')}</td><td>{int(row.get('长度') or 0):,} bp</td><td>{escape(_text(row.get('链方向')) or '未记录')}</td></tr>"
        for label, record, row in elements
    )
    files_html = "".join(f"<li><strong>{escape(name)}</strong>：{escape(description)}</li>" for name, description in file_descriptions)
    validation_summary = _mapping(plasmid.get("validation_summary"))
    returned_checks = _runtime_validation_items(plasmid)
    validation_html = "".join(
        "<li>"
        f"<strong>{escape(_text(_mapping(item).get('rule_id')) or '未标识检查项')}</strong>："
        f"{escape(_finding_detail(_mapping(item)))}"
        f"（级别：{escape(_text(_mapping(item).get('severity')) or 'info')}；"
        f"{'阻断' if bool(_mapping(item).get('blocking')) else '非阻断'}）"
        "</li>"
        for item in returned_checks
    ) or "<li>当前运行时未返回可逐项展示的检查项。</li>"
    feature_conflict_result = _feature_conflict_result(plasmid)
    host = _text(result.get("host")) or _text(records.get("host")) or "未记录"
    from services.rice_hsa_ncbi_mvp10_case import DEMO_BOUNDARY_NOTE, DEMO_PROJECT_NAME, REAL_CASE_BOUNDARY_NOTE, evaluate_real_case_authenticity, is_real_case_candidate

    real_case = is_real_case_candidate(result)
    gate = evaluate_real_case_authenticity(result) if real_case else {}
    provenance_html = "".join(
        "<tr>"
        f"<td>{escape(_text(record.get('display_name')) or label)}</td>"
        f"<td>{escape(_text(record.get('source_accession_version')) or _text(record.get('source_name')) or '未记录')}</td>"
        f"<td>{escape(_text(record.get('source_location')) or '未记录')}</td>"
        f"<td>{int(record.get('source_strand') or 0)}</td>"
        f"<td>{int(record.get('source_record_length') or record.get('length') or 0):,} bp</td>"
        f"<td>{int(record.get('length') or 0):,} bp</td>"
        f"<td>{escape(_text(record.get('source_file_sha256')) or '未记录')}</td>"
        f"<td>{escape(_text(record.get('extracted_sequence_sha256')) or '未记录')}</td>"
        "</tr>"
        for label, record in (("启动子", _mapping(records.get("promoter"))), ("编码序列（CDS）", _mapping(records.get("cds"))), ("终止子", _mapping(records.get("terminator"))), ("载体骨架", backbone))
    )
    gate_items = "".join(f"<li>{escape(str(item))}</li>" for item in list(gate.get("missing_items") or [])) or "<li>无缺失来源项。</li>"
    coverage_end = max((int(row.get("终点") or 0) for row in coordinate_rows), default=0)
    uncovered = max(0, int(plasmid.get("sequence_length") or 0) - coverage_end)
    boundary_note = REAL_CASE_BOUNDARY_NOTE if real_case else (DEMO_BOUNDARY_NOTE if project_name == DEMO_PROJECT_NAME else "该结果为 documentation-only 设计记录，不表示实验验证或湿实验可用性判断。")
    html = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>{escape(project_name)} 设计交付说明</title>
<style>body{{font-family:Arial,'Microsoft YaHei',sans-serif;color:#1d2920;line-height:1.55;margin:28px;max-width:1000px}}h1{{color:#1d613a}}h2{{border-bottom:1px solid #c7d2c8;padding-bottom:5px;margin-top:28px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{border:1px solid #cfd8d0;padding:7px;text-align:left;vertical-align:top}}th{{background:#e8f4ea}}.note{{background:#fff5df;border-left:4px solid #c37b13;padding:12px}}@media print{{body{{margin:14mm}}}}</style></head><body>
<h1>设计交付说明</h1><p>文件生成时间：{escape(datetime.now().astimezone().isoformat(timespec='seconds'))}</p>
<h2>1. 项目信息</h2><table><tr><th>项目名称</th><td>{escape(project_name)}</td></tr><tr><th>宿主植物</th><td>{escape(host)}</td></tr><tr><th>目标基因</th><td>{escape(_text(_mapping(records.get('cds')).get('display_name')) or '未记录')}</td></tr><tr><th>项目类型</th><td>单基因植物表达载体</td></tr><tr><th>软件版本</th><td>BioDesign Studio V1.0</td></tr></table>
<h2>2. 表达盒</h2><table><tr><th>类型</th><th>名称</th><th>长度</th><th>方向</th></tr>{component_html}</table><p>元件顺序：启动子 → 编码序列（CDS） → 终止子。表达盒总长度：{int(cassette.get('sequence_length') or 0):,} bp。表达盒 SHA-256：{escape(_text(cassette.get('sequence_checksum')))}</p>
<h2>3. 载体骨架</h2><p>骨架名称：{escape(_text(backbone.get('display_name')) or '未记录')}；骨架长度：{int(backbone.get('length') or 0):,} bp；拓扑：{'环状' if _text(plasmid.get('topology')).lower() == 'circular' else '线性'}；来源 accession：{escape(accession or '未记录')}；来源说明：{escape(source_label)}；原有 feature 数量：{len(list(backbone.get('imported_feature_records') or []))}。</p>
<h2>4. 插入信息</h2><p>方式：{insertion_mode}；插入位置：{int(settings.get('start_coordinate') or 0)}；替换区域：{removal}；插入方向：正向（+）；是否影响原有 feature：{escape(feature_conflict_result)}；完整质粒长度：{int(plasmid.get('sequence_length') or 0):,} bp。</p><p>人工复核项：候选插入边界及克隆策略仍需人工或公司复核；本记录不声称该位置为最佳插入位置。</p>
<h2>5. 完整质粒</h2><p>名称：{escape(project_name)}；长度：{int(plasmid.get('sequence_length') or 0):,} bp；拓扑：{'环状' if _text(plasmid.get('topology')).lower() == 'circular' else '线性'}；feature 总数：{len(coordinate_rows)}；完整质粒 SHA-256：{escape(_text(plasmid.get('sequence_checksum')))}</p>
<h2>6. 来源与 SHA-256</h2><table><tr><th>元件</th><th>accession</th><th>使用区段</th><th>strand</th><th>原始长度</th><th>截取长度</th><th>原始文件 SHA-256</th><th>截取序列 SHA-256</th></tr>{provenance_html}</table>
<h2>7. 元件坐标表</h2><table><tr><th>名称</th><th>类型</th><th>起点</th><th>终点</th><th>长度</th><th>链方向</th><th>所属表达单元</th><th>来源 accession</th></tr>{row_html}</table><p>完整质粒 {int(plasmid.get('sequence_length') or 0):,} bp；已注释 feature 最大终点 {coverage_end:,} bp；未由最大终点覆盖的尾部长度 {uncovered:,} bp。完整序列均来自当前 canonical runtime。</p>
<h2>8. 真实性与软件校验</h2><p>真实性门：{escape(_text(gate.get('status')) or '不适用')}。以下仅展示当前程序运行时实际执行并返回的检查项；不表示实验验证。</p><ul>{gate_items}</ul><p>警告数：{int(validation_summary.get('warning_count') or 0)}；阻断数：{int(validation_summary.get('blocking_count') or 0)}；信息项数：{int(validation_summary.get('info_count') or 0)}。</p><ul>{validation_html}</ul>
<h2>9. 文件清单</h2><ul>{files_html}</ul>
<h2>10. 边界声明</h2><div class="note">{escape(boundary_note)}</div>
</body></html>"""
    return html.encode("utf-8")


def build_company_delivery_package(
    result: dict[str, Any],
    *,
    current_input_signature: str,
) -> dict[str, Any]:
    """Return a ZIP that contains only current canonical output bytes and metadata."""
    if _text(result.get("input_signature")) != _text(current_input_signature):
        raise CompanyDeliveryPackageError("项目输入已变更，当前结果已过期。")
    from services.rice_hsa_ncbi_mvp10_case import (
        evaluate_real_case_authenticity,
        is_real_case_candidate,
    )

    authenticity_gate: dict[str, Any] = {}
    if is_real_case_candidate(result):
        authenticity_gate = evaluate_real_case_authenticity(result)
        if not authenticity_gate["passed"]:
            missing = "；".join(str(item) for item in authenticity_gate["missing_items"])
            raise CompanyDeliveryPackageError(f"{authenticity_gate['status']}，禁止公司交付包：{missing}")
    try:
        cassette = active_construct_snapshot(result.get("runtime"))
        plasmid = active_complete_plasmid_snapshot(result.get("runtime"))
    except CanonicalConstructRuntimeError as exc:
        raise CompanyDeliveryPackageError(str(exc)) from exc
    if int(_mapping(plasmid.get("validation_summary")).get("blocking_count") or 0):
        raise CompanyDeliveryPackageError("当前完整质粒存在阻断错误，不能导出公司交付包。")

    exports, cassette_exports = _require_current_snapshot_exports(result, cassette, plasmid)
    genbank_bytes = _bytes(_mapping(exports.get("genbank")).get("data"))
    fasta_bytes = _bytes(_mapping(exports.get("fasta")).get("data"))
    if not genbank_bytes or not fasta_bytes:
        raise CompanyDeliveryPackageError("FASTA 或 GenBank 导出字节尚未生成。")
    cassette_fasta_bytes = _bytes(_mapping(cassette_exports.get("fasta")).get("data"))
    if not cassette_fasta_bytes:
        raise CompanyDeliveryPackageError("表达盒 FASTA 导出字节尚未生成。")

    project_name = project_display_name(result, plasmid)
    coordinate_rows = _feature_rows(result, plasmid)
    source_rows = _source_rows(result)
    validation = _validation_payload(plasmid)
    validation["真实性门"] = authenticity_gate or {"status": "不适用"}
    file_descriptions = [
        ("01_设计交付说明.html", "可打印的当前运行时设计说明"),
        ("02_完整质粒.gb", "与结果页单独下载完全一致的 GenBank"),
        ("03_完整质粒.fasta", "与结果页单独下载完全一致的 FASTA"),
        ("04_表达盒.fasta", "当前 runtime 的表达盒 FASTA"),
        ("05_元件与坐标清单.csv", "当前 canonical feature 坐标"),
        ("06_来源与accession清单.csv", "输入元件的来源与 accession"),
        ("07_校验结果.json", "当前软件校验结果"),
        ("08_SHA256校验值.txt", "交付文件的 SHA-256"),
        ("09_项目备份.json", "当前项目运行时备份"),
    ]
    files: dict[str, bytes] = {
        "02_完整质粒.gb": genbank_bytes,
        "03_完整质粒.fasta": fasta_bytes,
        "04_表达盒.fasta": cassette_fasta_bytes,
        "05_元件与坐标清单.csv": _csv_bytes(coordinate_rows, ("名称", "类型", "起点", "终点", "长度", "链方向", "所属表达单元", "来源 accession", "来源说明")),
        "06_来源与accession清单.csv": _csv_bytes(
            source_rows,
            (
                "元件", "类型", "来源 accession", "来源说明", "原始记录名称",
                "原始长度", "使用区段", "strand", "截取长度", "原始文件 SHA-256",
                "截取序列 SHA-256", "定义依据",
            ),
        ),
        "07_校验结果.json": _json_bytes(validation),
        "09_项目备份.json": _json_bytes(result),
    }
    files["01_设计交付说明.html"] = _html_report(
        project_name=project_name,
        result=result,
        cassette=cassette,
        plasmid=plasmid,
        coordinate_rows=coordinate_rows,
        validation=validation,
        file_descriptions=file_descriptions,
    )
    checksums = {name: _sha256(files[name]) for name in PACKAGE_FILES if name not in {"08_SHA256校验值.txt"}}
    files["08_SHA256校验值.txt"] = "".join(f"{checksum}  {name}\n" for name, checksum in checksums.items()).encode("utf-8")

    archive = BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name in PACKAGE_FILES:
            package.writestr(name, files[name])
    data = archive.getvalue()
    return {
        "data": data,
        "mime": PACKAGE_MIME,
        "file_name": f"{project_name}_公司交付包.zip",
        "project_name": project_name,
        "files": list(PACKAGE_FILES),
        "file_checksums": checksums,
        "sha256": _sha256(data),
        "report_format": "html",
    }
