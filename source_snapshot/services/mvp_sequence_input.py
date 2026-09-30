"""Thin user-input adapters for the single-gene MVP runtime."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from services.canonical_construct_runtime import (
    CanonicalConstructRuntimeError,
    create_sequence_asset,
)


DNA_FILE_SUFFIXES = {".fa", ".fasta", ".fas", ".txt"}
GENBANK_FILE_SUFFIXES = {".gb", ".gbk", ".genbank"}


class MvpSequenceInputError(ValueError):
    """Raised when a user input cannot become a canonical sequence asset."""


def decode_uploaded_text(data: bytes, *, file_name: str, allowed_suffixes: set[str]) -> str:
    suffix = Path(str(file_name or "")).suffix.lower()
    if suffix not in allowed_suffixes:
        raise MvpSequenceInputError("文件类型不支持。")
    if not data:
        raise MvpSequenceInputError("上传文件为空。")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MvpSequenceInputError("上传文件无法按 UTF-8 解码。") from exc


def _safe_runtime_error(exc: CanonicalConstructRuntimeError, *, role: str) -> MvpSequenceInputError:
    message = str(exc).casefold()
    if "exactly one" in message or "multiple" in message:
        safe = "FASTA 或 GenBank 包含多条记录；单基因项目一次只能使用一条记录。"
    elif "no valid fasta" in message or "no fasta" in message or "record" in message and "not" in message:
        safe = "FASTA 中没有可用记录。"
    elif "unsupported nucleotide" in message or "invalid" in message and role != "backbone":
        safe = "DNA 包含非法字符。"
    elif role == "backbone":
        safe = "GenBank 文件无法解析。"
    else:
        safe = "序列输入无法解析。"
    return MvpSequenceInputError(safe)


def analyze_dna_component_input(
    raw_text: str,
    *,
    project_id: str,
    component_type: str,
    display_name: str,
    source_kind: str,
    source_name: str,
) -> dict[str, Any]:
    """Delegate promoter/terminator DNA or FASTA parsing to R227."""
    original_text = str(raw_text or "")
    if not original_text.strip():
        raise MvpSequenceInputError("输入为空。")
    source_format = "fasta" if original_text.lstrip().startswith(">") else "plain"
    try:
        asset = create_sequence_asset(
            project_id=project_id,
            display_name=display_name,
            raw_text=original_text,
            molecule_type="dna",
            source_type=source_kind,
            source_format=source_format,
            source_name=source_name,
            asset_role="construct_component",
        )
    except CanonicalConstructRuntimeError as exc:
        raise _safe_runtime_error(exc, role=component_type) from exc
    if int(asset.get("length", 0)) <= 0:
        raise MvpSequenceInputError("输入为空。")
    return {
        "role": component_type,
        "source_kind": source_kind,
        "source_name": source_name,
        "source_format": source_format,
        "display_name": display_name,
        "original_text": original_text,
        "normalized_sequence": str(asset.get("nucleotide_sequence") or ""),
        "length": int(asset.get("length", 0)),
        "asset": asset,
    }


def analyze_genbank_backbone_input(
    raw_text: str,
    *,
    project_id: str,
    display_name: str,
    source_kind: str,
    source_name: str,
) -> dict[str, Any]:
    """Delegate single-record GenBank parsing and feature import to R227."""
    original_text = str(raw_text or "")
    if not original_text.strip():
        raise MvpSequenceInputError("骨架为空。")
    try:
        asset = create_sequence_asset(
            project_id=project_id,
            display_name=display_name,
            raw_text=original_text,
            molecule_type="dna",
            source_type=source_kind,
            source_format="genbank",
            source_name=source_name,
            asset_role="backbone",
        )
    except CanonicalConstructRuntimeError as exc:
        raise _safe_runtime_error(exc, role="backbone") from exc
    if int(asset.get("length", 0)) <= 0:
        raise MvpSequenceInputError("GenBank 骨架没有序列。")
    record = {
        "role": "backbone",
        "source_kind": source_kind,
        "source_name": source_name,
        "source_format": "genbank",
        "display_name": display_name,
        "original_text": original_text,
        "normalized_sequence": str(asset.get("nucleotide_sequence") or ""),
        "length": int(asset.get("length", 0)),
        "topology": str(asset.get("topology") or ""),
        "original_record_identifier": str(asset.get("original_record_identifier") or ""),
        "imported_feature_records": list(asset.get("imported_feature_records") or []),
        "asset": asset,
    }
    from services.vector_asset_admission import annotate_vector_record

    return annotate_vector_record(record)
