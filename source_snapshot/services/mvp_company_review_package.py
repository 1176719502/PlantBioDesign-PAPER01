"""Deterministic company-review ZIP packaging for the single-gene MVP."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from io import BytesIO, StringIO
from pathlib import PurePosixPath
from typing import Any

from services.canonical_construct_runtime import (
    CanonicalConstructRuntimeError,
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
    export_active_construct,
)
from Bio import SeqIO


PACKAGE_SCHEMA_VERSION = "1.0.0"
PROJECT_SCHEMA_VERSION = "1.0.0"
PROJECT_TYPE = "single_gene"
PACKAGE_MIME = "application/zip"
PACKAGE_FILE_ORDER = (
    "complete_plasmid.gb",
    "complete_plasmid.fasta",
    "expression_cassette.fasta",
    "component_coordinates.csv",
    "validation_summary.json",
    "construct_manifest.json",
    "construct_summary.txt",
    "checksums.sha256",
)
CHECKSUM_FILE_ORDER = PACKAGE_FILE_ORDER[:-1]
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
ALLOWED_SOURCE_KINDS = {
    "example",
    "library",
    "user_pasted",
    "user_uploaded",
    "not_provided",
}
SOURCE_KIND_ALIASES = {
    "paste": "user_pasted",
    "pasted": "user_pasted",
    "upload": "user_uploaded",
    "uploaded": "user_uploaded",
}
BOUNDARY_TEXT = (
    "本交付包用于序列审查、报价和构建可行性评估。实际克隆方法、合成难度、酶切位点、重复序列、GC 含量、"
    "载体来源、生物安全及实验可行性仍需由实验人员或服务公司复核。本软件结果不构成湿实验成功保证。"
)


class MvpCompanyReviewPackageError(ValueError):
    """Raised when a review package cannot be created or restored safely."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _raw_text(value: Any) -> str:
    return str(value or "")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def safe_project_directory_name(project_name: str) -> str:
    """Return one readable ZIP root name with no path semantics."""
    value = " ".join(str(project_name or "").split())
    value = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", value)
    while ".." in value:
        value = value.replace("..", "_")
    value = re.sub(r"_+", "_", value).strip(" ._-")
    return value or "BioDesign_Project"


def _safe_uploaded_name(value: Any) -> str:
    normalized = str(value or "").replace("\\", "/")
    leaf = normalized.rsplit("/", 1)[-1].strip()
    leaf = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", leaf).strip(" .")
    return leaf or "not_provided"


def normalized_source_provenance(record: dict[str, Any] | None) -> dict[str, str]:
    """Normalize legacy MVP source aliases without inventing references."""
    source = _mapping(record)
    raw_kind = _text(source.get("source_kind")).lower()
    kind = SOURCE_KIND_ALIASES.get(raw_kind, raw_kind)
    if kind not in ALLOWED_SOURCE_KINDS:
        return {"source_kind": "not_provided", "source_reference": "not_provided"}

    explicit_reference = _text(source.get("source_reference"))
    source_name = _text(source.get("source_name"))
    if kind == "user_pasted":
        reference = explicit_reference or "not_provided"
    elif kind == "user_uploaded":
        reference = _safe_uploaded_name(explicit_reference or source_name)
    elif kind in {"example", "library"}:
        reference = explicit_reference or source_name or "not_provided"
    else:
        reference = "not_provided"
    return {"source_kind": kind, "source_reference": reference}


def normalized_source_record(record: dict[str, Any] | None) -> dict[str, Any]:
    normalized = _mapping(record)
    normalized.update(normalized_source_provenance(normalized))
    return normalized


def _feature_length(feature: dict[str, Any]) -> int:
    parts = list(feature.get("location_parts") or [])
    if parts:
        return sum(int(part["end"]) - int(part["start"]) + 1 for part in parts)
    return int(feature["end"]) - int(feature["start"]) + 1


def _feature_notes(feature: dict[str, Any]) -> str:
    parts = list(feature.get("location_parts") or [])
    if not parts:
        return ""
    operator = _text(feature.get("location_operator")) or "join"
    spans = "; ".join(
        f"{int(part['start'])}-{int(part['end'])}({int(part.get('strand', feature.get('strand', 1)))})"
        for part in parts
    )
    return f"CompoundLocation {operator}: {spans}"


def _features_from_saved_genbank(result: dict[str, Any]) -> list[dict[str, Any]]:
    exports = _mapping(result.get("exports"))
    genbank_text = _text(_mapping(exports.get("genbank")).get("data"))
    if not genbank_text:
        return []
    try:
        records = list(SeqIO.parse(StringIO(genbank_text), "genbank"))
    except Exception as exc:
        raise MvpCompanyReviewPackageError("已保存的 GenBank 无法恢复元件坐标。") from exc
    if len(records) != 1:
        raise MvpCompanyReviewPackageError("已保存的 GenBank 记录数不正确。")
    input_records = _mapping(result.get("input_records"))
    component_labels = {
        role: _text(_mapping(input_records.get(role)).get("display_name"))
        for role in ("promoter", "cds", "terminator")
    }
    features: list[dict[str, Any]] = []
    for feature in records[0].features:
        qualifiers = feature.qualifiers or {}
        label = _text((qualifiers.get("label") or [""])[0]) or _text(feature.type)
        parts = list(getattr(feature.location, "parts", None) or [feature.location])
        location_parts = [
            {
                "start": int(part.start) + 1,
                "end": int(part.end),
                "strand": int(part.strand or feature.location.strand or 1),
            }
            for part in parts
        ]
        feature_type = _text(feature.type) or "misc_feature"
        role = feature_type.lower()
        source = (
            "transcription_unit"
            if role in component_labels and label == component_labels[role]
            else "backbone"
        )
        payload = {
            "name": label,
            "type": feature_type,
            "start": min(part["start"] for part in location_parts),
            "end": max(part["end"] for part in location_parts),
            "strand": int(feature.location.strand or 1),
            "source": source,
        }
        if len(location_parts) > 1:
            payload["location_parts"] = location_parts
            payload["location_operator"] = _text(
                getattr(feature.location, "operator", "")
            ) or "join"
        features.append(payload)
    return features


def _coordinate_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    records = _mapping(result.get("input_records"))
    exports = _mapping(result.get("exports"))
    metadata = _mapping(exports.get("metadata"))
    rows: list[dict[str, Any]] = []
    features = list(metadata.get("features") or []) or _features_from_saved_genbank(result)
    for feature in features:
        feature_type = _text(feature.get("type")) or "misc_feature"
        source_role = (
            feature_type.lower()
            if _text(feature.get("source")) == "transcription_unit"
            else "backbone"
        )
        provenance = normalized_source_provenance(_mapping(records.get(source_role)))
        rows.append(
            {
                "component_name": _text(feature.get("name")) or feature_type,
                "component_type": feature_type,
                "start_1_based": int(feature.get("start", 0)),
                "end_1_based": int(feature.get("end", 0)),
                "strand": int(feature.get("strand", 1) or 1),
                "length_bp": _feature_length(feature),
                "source_kind": provenance["source_kind"],
                "source_reference": provenance["source_reference"],
                "notes": _feature_notes(feature),
            }
        )
    required = {"promoter", "cds", "terminator"}
    present = {str(row["component_type"]).lower() for row in rows}
    if not required.issubset(present):
        raise MvpCompanyReviewPackageError("元件坐标不完整，无法生成公司审查包。")
    return rows


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    columns = (
        "component_name",
        "component_type",
        "start_1_based",
        "end_1_based",
        "strand",
        "length_bp",
        "source_kind",
        "source_reference",
        "notes",
    )
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _validation_payload(result: dict[str, Any], plasmid: dict[str, Any]) -> dict[str, Any]:
    findings = list(plasmid.get("validation_findings") or [])
    errors = [
        _text(item.get("explanation") or item.get("message"))
        for item in findings
        if bool(item.get("blocking")) or _text(item.get("severity")).lower() == "error"
    ]
    warnings = [
        _text(item.get("explanation") or item.get("message"))
        for item in findings
        if not bool(item.get("blocking")) and _text(item.get("severity")).lower() == "warning"
    ]
    checks = [
        {
            "check_id": "complete_plasmid_sequence",
            "status": "complete",
            "scope": "software",
        },
        {
            "check_id": "feature_coordinates",
            "status": "complete",
            "scope": "software",
        },
        {
            "check_id": "fasta_genbank_export_bytes",
            "status": "complete",
            "scope": "software",
        },
        {
            "check_id": "input_signature_and_snapshot",
            "status": "complete",
            "scope": "software",
        },
    ]
    return {
        "validation_scope": "software_sequence_and_structure_validation",
        "overall_status": "software_checks_complete_with_warnings" if warnings else "software_checks_complete",
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "status_meaning_cn": (
            "“通过”只代表软件层面的输入、序列、坐标、结构、保存和导出检查；"
            "不代表湿实验成功，也不代表表达效果保证。"
        ),
        "accuracy_validation_reference": "v2.7-mvp7-single-gene-accuracy-validation",
        "wet_lab_validated": False,
        "experimental_success_guaranteed": False,
    }


def _primary_components(
    result: dict[str, Any], coordinate_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    records = _mapping(result.get("input_records"))
    row_by_role = {
        str(row["component_type"]).lower(): row
        for row in coordinate_rows
        if str(row["component_type"]).lower() in {"promoter", "cds", "terminator"}
    }
    components: list[dict[str, Any]] = []
    for role in ("promoter", "cds", "terminator"):
        record = _mapping(records.get(role))
        row = row_by_role[role]
        provenance = normalized_source_provenance(record)
        components.append(
            {
                "name": _text(record.get("display_name")) or _text(row["component_name"]),
                "type": role,
                "length_bp": int(record.get("length", row["length_bp"])),
                "strand": int(row["strand"]),
                "start_1_based": int(row["start_1_based"]),
                "end_1_based": int(row["end_1_based"]),
                "source_kind": provenance["source_kind"],
                "source_reference": provenance["source_reference"],
                "coordinate_system": "complete_plasmid",
            }
        )
    backbone = _mapping(records.get("backbone"))
    provenance = normalized_source_provenance(backbone)
    backbone_length = int(backbone.get("length", 0) or 0)
    components.append(
        {
            "name": _text(backbone.get("display_name")) or "Backbone",
            "type": "backbone",
            "length_bp": backbone_length,
            "strand": 1,
            "start_1_based": 1,
            "end_1_based": backbone_length,
            "source_kind": provenance["source_kind"],
            "source_reference": provenance["source_reference"],
            "coordinate_system": "source_backbone",
        }
    )
    return components


def _manifest_payload(
    result: dict[str, Any],
    plasmid: dict[str, Any],
    coordinate_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    settings = _mapping(result.get("insertion_settings"))
    return {
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "project_schema_version": PROJECT_SCHEMA_VERSION,
        "project_type": PROJECT_TYPE,
        "project_name": _text(result.get("project_name")) or "BioDesign Project",
        "generated_by": "BioDesign Studio",
        "construct_topology": _text(plasmid.get("topology")) or "circular",
        "cassette_length_bp": int(result.get("cassette_length", 0) or 0),
        "backbone_length_bp": int(_mapping(result.get("input_lengths")).get("backbone", 0) or 0),
        "complete_plasmid_length_bp": int(plasmid.get("sequence_length", 0) or 0),
        "insertion_mode": _text(settings.get("mode")),
        "insertion_coordinates": {
            "start_1_based": int(settings.get("start_coordinate", 0) or 0),
            "end_1_based": int(settings.get("end_coordinate", 0) or 0),
        },
        "components": _primary_components(result, coordinate_rows),
        "files": [
            {"relative_path": file_name}
            for file_name in PACKAGE_FILE_ORDER
        ],
        "limitations": [
            "Documentation-only software output; company or expert review remains required.",
            "No wet-lab success or expression performance is guaranteed.",
            "No cloning method is automatically selected as the best construction plan.",
        ],
    }


def _summary_bytes(
    result: dict[str, Any], plasmid: dict[str, Any], manifest: dict[str, Any]
) -> bytes:
    records = _mapping(result.get("input_records"))
    settings = _mapping(result.get("insertion_settings"))
    mode_text = (
        f"替换区间 {int(settings.get('start_coordinate', 0))}-{int(settings.get('end_coordinate', 0))}"
        if _text(settings.get("mode")) == "replacement"
        else f"插入位置 {int(settings.get('start_coordinate', 0))}"
    )
    topology_text = "环状" if _text(plasmid.get("topology")).lower() == "circular" else "线性"
    validation = _mapping(result.get("validation_summary"))
    warning_count = int(validation.get("warning_count", 0) or 0)
    backbone_source = normalized_source_provenance(_mapping(records.get("backbone")))
    lines = [
        f"项目名称：{' '.join((_text(result.get('project_name')) or 'BioDesign Project').split())}",
        "设计类型：植物单基因表达载体",
        "表达盒结构：启动子 → CDS → 终止子",
        "各元件长度：",
        f"- 启动子：{int(_mapping(records.get('promoter')).get('length', 0))} bp",
        f"- CDS：{int(_mapping(records.get('cds')).get('length', 0))} bp",
        f"- 终止子：{int(_mapping(records.get('terminator')).get('length', 0))} bp",
        f"骨架：{_text(_mapping(records.get('backbone')).get('display_name')) or 'Backbone'}，{manifest['backbone_length_bp']} bp",
        f"骨架来源：{backbone_source['source_kind']} / {backbone_source['source_reference']}",
        f"插入或替换方式：{mode_text}",
        f"完整质粒长度：{manifest['complete_plasmid_length_bp']} bp",
        f"拓扑状态：{topology_text}",
        f"软件校验结论：软件层面检查完成，警告 {warning_count} 项，阻止错误 0 项。",
        "文件清单：",
        *[f"- {file_name}" for file_name in PACKAGE_FILE_ORDER],
        "边界说明：",
        BOUNDARY_TEXT,
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _zip_info(path: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(path, date_time=FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _build_zip(root_directory: str, files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(
        output,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for file_name in PACKAGE_FILE_ORDER:
            archive.writestr(
                _zip_info(f"{root_directory}/{file_name}"),
                files[file_name],
                compress_type=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            )
    return output.getvalue()


def build_company_review_package(result: dict[str, Any]) -> dict[str, Any]:
    """Build one deterministic ZIP from existing validated runtime exports."""
    runtime = _mapping(result.get("runtime"))
    if not runtime:
        raise MvpCompanyReviewPackageError("尚未生成可用的完整质粒。")
    active_plasmid_id = _text(runtime.get("active_complete_plasmid_id"))
    raw_active_plasmid = next(
        (
            item
            for item in list(runtime.get("complete_plasmid_constructs") or [])
            if _text(item.get("plasmid_id")) == active_plasmid_id
        ),
        {},
    )
    if _text(raw_active_plasmid.get("construct_status")) == "stale":
        raise MvpCompanyReviewPackageError("当前结果已失效，请重新生成后再导出。")
    try:
        plasmid = active_complete_plasmid_snapshot(runtime)
        cassette = active_construct_snapshot(runtime)
    except CanonicalConstructRuntimeError as exc:
        raise MvpCompanyReviewPackageError("尚未生成可用的完整质粒。") from exc
    if _text(plasmid.get("construct_status")) == "stale":
        raise MvpCompanyReviewPackageError("当前结果已失效，请重新生成后再导出。")
    validation = result.get("validation_summary")
    if not isinstance(validation, dict):
        raise MvpCompanyReviewPackageError("软件校验尚未完成。")
    if int(validation.get("blocking_count", 0) or 0):
        raise MvpCompanyReviewPackageError("当前结果存在阻止导出的错误。")
    if not _text(plasmid.get("sequence")) or not _text(cassette.get("sequence")):
        raise MvpCompanyReviewPackageError("当前结果缺少可导出序列。")

    exports = _mapping(result.get("exports"))
    complete_fasta = _raw_text(_mapping(exports.get("fasta")).get("data"))
    complete_genbank = _raw_text(_mapping(exports.get("genbank")).get("data"))
    if not complete_fasta or not complete_genbank:
        raise MvpCompanyReviewPackageError("当前结果缺少 FASTA 或 GenBank 导出字节。")
    try:
        cassette_exports = export_active_construct(
            _mapping(result.get("runtime")),
            project_name=_text(result.get("project_name")) or "BioDesign Project",
        )
    except CanonicalConstructRuntimeError as exc:
        raise MvpCompanyReviewPackageError("表达盒 FASTA 导出字节不可用。") from exc
    cassette_fasta = _raw_text(_mapping(cassette_exports.get("fasta")).get("data"))
    if not cassette_fasta:
        raise MvpCompanyReviewPackageError("表达盒 FASTA 导出字节不可用。")

    coordinate_rows = _coordinate_rows(result)
    validation_payload = _validation_payload(result, plasmid)
    manifest = _manifest_payload(result, plasmid, coordinate_rows)
    files: dict[str, bytes] = {
        "complete_plasmid.gb": complete_genbank.encode("utf-8"),
        "complete_plasmid.fasta": complete_fasta.encode("utf-8"),
        "expression_cassette.fasta": cassette_fasta.encode("utf-8"),
        "component_coordinates.csv": _csv_bytes(coordinate_rows),
        "validation_summary.json": _json_bytes(validation_payload),
        "construct_manifest.json": _json_bytes(manifest),
        "construct_summary.txt": _summary_bytes(result, plasmid, manifest),
    }
    checksum_lines = [
        f"{_sha256_bytes(files[file_name])}  {file_name}"
        for file_name in CHECKSUM_FILE_ORDER
    ]
    files["checksums.sha256"] = ("\n".join(checksum_lines) + "\n").encode("utf-8")
    root_directory = safe_project_directory_name(_text(result.get("project_name")))
    package_bytes = _build_zip(root_directory, files)
    return {
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "project_schema_version": PROJECT_SCHEMA_VERSION,
        "project_type": PROJECT_TYPE,
        "root_directory": root_directory,
        "file_name": f"{root_directory}_company_review_package.zip",
        "mime": PACKAGE_MIME,
        "sha256": _sha256_bytes(package_bytes),
        "data": package_bytes,
    }


def validate_company_review_package_bytes(
    package_bytes: bytes, *, expected_root_directory: str = ""
) -> dict[str, Any]:
    """Validate archive shape and checksums before restoring persisted bytes."""
    if not isinstance(package_bytes, bytes) or not package_bytes:
        raise MvpCompanyReviewPackageError("保存的公司审查包已损坏。")
    try:
        with zipfile.ZipFile(BytesIO(package_bytes), "r") as archive:
            names = archive.namelist()
            if len(names) != len(PACKAGE_FILE_ORDER):
                raise MvpCompanyReviewPackageError("保存的公司审查包文件数不正确。")
            roots: set[str] = set()
            relative_names: list[str] = []
            for name in names:
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or len(path.parts) != 2:
                    raise MvpCompanyReviewPackageError("保存的公司审查包包含不安全路径。")
                roots.add(path.parts[0])
                relative_names.append(path.parts[1])
            if len(roots) != 1 or tuple(relative_names) != PACKAGE_FILE_ORDER:
                raise MvpCompanyReviewPackageError("保存的公司审查包文件清单不正确。")
            root = next(iter(roots))
            if expected_root_directory and root != expected_root_directory:
                raise MvpCompanyReviewPackageError("保存的公司审查包项目目录不一致。")
            checksum_text = archive.read(f"{root}/checksums.sha256").decode("utf-8")
            checksum_lines = checksum_text.splitlines()
            if len(checksum_lines) != len(CHECKSUM_FILE_ORDER):
                raise MvpCompanyReviewPackageError("保存的公司审查包校验清单不正确。")
            for line, relative_name in zip(checksum_lines, CHECKSUM_FILE_ORDER, strict=True):
                expected_line = f"{_sha256_bytes(archive.read(f'{root}/{relative_name}'))}  {relative_name}"
                if line != expected_line:
                    raise MvpCompanyReviewPackageError("保存的公司审查包校验值不一致。")
    except (OSError, UnicodeDecodeError, zipfile.BadZipFile) as exc:
        raise MvpCompanyReviewPackageError("保存的公司审查包无法解析。") from exc
    return {
        "root_directory": root,
        "sha256": _sha256_bytes(package_bytes),
        "file_names": list(PACKAGE_FILE_ORDER),
    }
