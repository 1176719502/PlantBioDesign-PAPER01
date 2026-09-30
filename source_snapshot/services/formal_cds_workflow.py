"""Second-step metadata, review, and lifecycle rules for one formal CDS."""
from __future__ import annotations

from typing import Any

from services.mvp_cds_input import analyze_cds_input


SOURCE_TYPES = ("公共数据库记录", "上传的 FASTA 文件", "用户自有序列", "外部公司或工具提供的序列", "其他来源")
MODIFICATION_STATUSES = ("未修改的来源序列", "用户手动编辑", "已由外部工具或公司进行密码子优化", "其他修改", "尚未确定")
_SOURCE_REVIEW_FIELDS = ("source_species", "source_type", "source_reference", "modification_status", "modification_note", "is_partial_cds")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _finding(rule_id: str, message: str) -> dict[str, Any]:
    return {"rule_id": rule_id, "message": message, "blocking": False, "status": "需要人工确认"}


def gene_information_from_values(*, gene_name: Any, gene_symbol: Any = "", source_species: Any = "", source_type: Any = "", source_reference: Any = "", modification_status: Any = "", modification_note: Any = "", is_partial_cds: Any = False, note: Any = "") -> dict[str, Any]:
    return {"gene_name": _text(gene_name), "gene_symbol": _text(gene_symbol), "source_species": _text(source_species), "source_type": _text(source_type), "source_reference": _text(source_reference), "modification_status": _text(modification_status), "modification_note": _text(modification_note), "is_partial_cds": bool(is_partial_cds), "note": _text(note)}


def source_review_basis(gene_information: dict[str, Any] | None) -> dict[str, Any]:
    source = dict(gene_information or {})
    return {field: source.get(field, False if field == "is_partial_cds" else "") for field in _SOURCE_REVIEW_FIELDS}


def sequence_signature(analysis: dict[str, Any] | None) -> dict[str, str]:
    source = dict(analysis or {})
    return {"normalized_cds_sha256": _text(source.get("normalized_cds_sha256")), "reading_frame": "forward:0", "start_terminal_handling": "unchanged", "genetic_code": _text(source.get("genetic_code"))}


def analyze_formal_cds(raw_text: str, *, source_kind: str, source_name: str = "", gene_information: dict[str, Any] | None = None) -> dict[str, Any]:
    """Add formal source and manual-review fields to the strict CDS analysis."""
    info = gene_information_from_values(**dict(gene_information or {}))
    analysis = analyze_cds_input(raw_text, source_kind=source_kind, source_name=source_name)
    findings = list(analysis.get("findings") or [])
    source_type, reference, modification_status = info["source_type"], info["source_reference"], info["modification_status"]
    if not info["source_species"]:
        findings.append(_finding("source_species_missing", "来源物种未记录。"))
    if source_type in {"公共数据库记录", "外部公司或工具提供的序列", "其他来源"} and not reference:
        findings.append(_finding("source_reference_missing", "该来源类型需要 accession 或来源说明。"))
    if source_type == "公共数据库记录" and reference:
        findings.append(_finding("accession_unverified", "accession 未联网核实；请人工确认来源记录。"))
    if modification_status in {"用户手动编辑", "其他修改"} and not info["modification_note"]:
        findings.append(_finding("modification_note_missing", "序列已修改但未记录修改说明。"))
    if modification_status == "已由外部工具或公司进行密码子优化" and not info["modification_note"]:
        findings.append(_finding("external_optimization_source_missing", "声称经过外部密码子优化但未记录来源说明。"))
    if info["is_partial_cds"]:
        findings.append(_finding("partial_cds", "已标记为部分 CDS，需要人工确认。"))
    title, name = _text(analysis.get("record_name")), info["gene_name"]
    if title and name and name.casefold() not in title.casefold() and title.casefold() not in name.casefold():
        findings.append(_finding("gene_name_fasta_title_mismatch", "目标基因名称与 FASTA 标题不一致。"))
    analysis.update(gene_information=info, source_review_basis=source_review_basis(info), sequence_signature=sequence_signature(analysis), findings=findings, manual_review_items=[item for item in findings if item.get("status") == "需要人工确认"])
    return analysis


def lifecycle_change(previous: dict[str, Any] | None, current: dict[str, Any] | None) -> str:
    """Return the downstream action required for an analyzed CDS update."""
    old, new = dict(previous or {}), dict(current or {})
    if not old:
        return "none"
    if sequence_signature(old) != sequence_signature(new):
        return "invalidate"
    if source_review_basis(old.get("gene_information")) != source_review_basis(new.get("gene_information")):
        return "source_review"
    return "none"
