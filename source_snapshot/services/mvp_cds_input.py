"""Strict, local CDS intake for the single-page single-gene MVP."""
from __future__ import annotations

import hashlib
from typing import Any


MVP_CDS_INPUT_SCHEMA_VERSION = "v2.8-formal-single-gene-cds"
DNA_ALPHABET = frozenset("ATCG")
TERMINAL_STOP_CODONS = frozenset({"TAA", "TAG", "TGA"})
STANDARD_GENETIC_CODE = "standard_nuclear"

_CODON_TABLE = {
    "TTT": "F", "TTC": "F", "TTA": "L", "TTG": "L", "CTT": "L", "CTC": "L", "CTA": "L", "CTG": "L",
    "ATT": "I", "ATC": "I", "ATA": "I", "ATG": "M", "GTT": "V", "GTC": "V", "GTA": "V", "GTG": "V",
    "TCT": "S", "TCC": "S", "TCA": "S", "TCG": "S", "CCT": "P", "CCC": "P", "CCA": "P", "CCG": "P",
    "ACT": "T", "ACC": "T", "ACA": "T", "ACG": "T", "GCT": "A", "GCC": "A", "GCA": "A", "GCG": "A",
    "TAT": "Y", "TAC": "Y", "TAA": "*", "TAG": "*", "CAT": "H", "CAC": "H", "CAA": "Q", "CAG": "Q",
    "AAT": "N", "AAC": "N", "AAA": "K", "AAG": "K", "GAT": "D", "GAC": "D", "GAA": "E", "GAG": "E",
    "TGT": "C", "TGC": "C", "TGA": "*", "TGG": "W", "CGT": "R", "CGC": "R", "CGA": "R", "CGG": "R",
    "AGT": "S", "AGC": "S", "AGA": "R", "AGG": "R", "GGT": "G", "GGC": "G", "GGA": "G", "GGG": "G",
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _finding(rule_id: str, message: str, *, blocking: bool) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "message": message,
        "blocking": blocking,
        "status": "阻断" if blocking else "需要人工确认",
    }


def _sequence_characters(text: str) -> tuple[str, list[str]]:
    """Build an A/C/G/T-only normalized CDS and record invalid characters separately."""
    normalized = "".join(character.upper() for character in text if character.upper() in DNA_ALPHABET)
    invalid_characters = sorted({
        character
        for character in (character.upper() for character in text if not character.isspace())
        if character not in DNA_ALPHABET
    })
    return normalized, invalid_characters


def _translate_standard_dna(sequence: str) -> str:
    return "".join(_CODON_TABLE[sequence[index : index + 3]] for index in range(0, len(sequence), 3))


def _parse_single_fasta(raw_text: str) -> tuple[str, str, int, list[dict[str, Any]]]:
    lines = raw_text.splitlines()
    nonempty = [line for line in lines if line.strip()]
    header_indexes = [index for index, line in enumerate(lines) if line.lstrip().startswith(">")]
    if not nonempty or not header_indexes:
        return "", "", 0, [_finding("invalid_fasta", "FASTA 文件缺少以 > 开始的标题行。", blocking=True)]
    first_nonempty = next(index for index, line in enumerate(lines) if line.strip())
    if first_nonempty != header_indexes[0]:
        return "", "", 0, [_finding("invalid_fasta", "FASTA 标题行之前不能包含序列内容。", blocking=True)]
    if len(header_indexes) != 1:
        return "", "", len(header_indexes), [
            _finding("multiple_fasta_records", "FASTA 包含多条记录，未选择任何记录。请保留一条 CDS 后再生成。", blocking=True)
        ]

    header = lines[header_indexes[0]].lstrip()[1:].strip()
    if not header:
        return "", "", 1, [_finding("invalid_fasta", "FASTA 标题行缺少记录名称。", blocking=True)]
    sequence_text = "".join(lines[header_indexes[0] + 1 :])
    if not sequence_text.strip():
        return "", "", 1, [_finding("empty_cds", "FASTA 记录不包含 CDS 序列。", blocking=True)]
    return sequence_text, header, 1, []


def analyze_cds_input(
    raw_text: str,
    *,
    source_kind: str,
    source_name: str = "",
) -> dict[str, Any]:
    """Return normalized CDS and R227-aligned findings without changing the input."""
    original_text = str(raw_text or "")
    stripped = original_text.lstrip()
    has_fasta_marker = any(line.lstrip().startswith(">") for line in original_text.splitlines())
    source_format = "fasta" if stripped.startswith(">") or has_fasta_marker else "plain"
    findings: list[dict[str, Any]] = []
    record_name = ""
    record_count = 0
    sequence_text = original_text

    if has_fasta_marker:
        source_format = "fasta"
        sequence_text, record_name, record_count, findings = _parse_single_fasta(original_text)
    elif original_text.strip():
        record_count = 1
    normalized_cds, invalid_characters = _sequence_characters(sequence_text)
    contains_only_acgt = bool(normalized_cds) and not invalid_characters
    if invalid_characters:
        findings.append(
            _finding(
                "invalid_dna_character",
                "CDS 包含 U、N、模糊碱基、数字、连字符或其他非法字符："
                + ", ".join(invalid_characters)
                + "。仅接受 A/C/G/T。",
                blocking=True,
            )
        )
    if not normalized_cds and not any(
        item["rule_id"] in {"empty_cds", "invalid_fasta", "multiple_fasta_records"}
        for item in findings
    ):
        findings.append(_finding("empty_cds", "CDS 输入为空，不能生成完整载体。", blocking=True))

    length_multiple_of_three = bool(normalized_cds) and len(normalized_cds) % 3 == 0
    starts_with_atg = normalized_cds.startswith("ATG") if normalized_cds else False
    terminal_stop_codon = normalized_cds[-3:] if len(normalized_cds) >= 3 else ""
    has_terminal_stop = terminal_stop_codon in TERMINAL_STOP_CODONS
    internal_stop_positions: list[int] = []
    protein_translation = ""
    translation_status = "未分析"

    if normalized_cds and contains_only_acgt:
        if len(normalized_cds) % 3:
            findings.append(
                _finding(
                    "cds_length_not_divisible_by_three",
                    "CDS 长度不是 3 的倍数；按现有 R227 规则阻止生成。",
                    blocking=True,
                )
            )
        if not starts_with_atg:
            findings.append(
                _finding(
                    "cds_missing_start_codon",
                    "CDS 未以标准 ATG 起始；按现有 R227 规则提示。",
                    blocking=False,
                )
            )
        if not has_terminal_stop:
            findings.append(
                _finding(
                    "cds_missing_terminal_stop_codon",
                    "CDS 缺少标准终止密码子；按现有 R227 规则提示。",
                    blocking=False,
                )
            )
        if len(normalized_cds) % 3 == 0:
            internal_stop_positions = [
                (index // 3) + 1
                for index in range(3, len(normalized_cds) - 3, 3)
                if normalized_cds[index : index + 3] in TERMINAL_STOP_CODONS
            ]
            if internal_stop_positions:
                findings.append(
                    _finding(
                        "internal_in_frame_stop_codon",
                        "CDS 存在内部终止密码子。",
                        blocking=True,
                    )
                )
            try:
                protein_translation = _translate_standard_dna(normalized_cds)
                translation_status = "通过"
            except KeyError:
                translation_status = "阻断"
                findings.append(_finding("unable_to_translate", "CDS 无法按标准遗传密码表正常翻译。", blocking=True))
    elif normalized_cds:
        translation_status = "阻断"
        findings.append(_finding("unable_to_translate", "CDS 无法按标准遗传密码表正常翻译。", blocking=True))

    expected_protein_length = len(protein_translation.rstrip("*")) if protein_translation else 0

    return {
        "schema_version": MVP_CDS_INPUT_SCHEMA_VERSION,
        "genetic_code": STANDARD_GENETIC_CODE,
        "source_kind": str(source_kind or "unknown"),
        "source_name": str(source_name or ""),
        "source_format": source_format,
        "original_text": original_text,
        "original_text_sha256": _sha256_text(original_text),
        "record_name": record_name,
        "record_count": record_count,
        "normalized_cds": normalized_cds,
        "normalized_cds_sha256": _sha256_text(normalized_cds),
        "normalized_length": len(normalized_cds),
        "contains_only_acgt": contains_only_acgt,
        "invalid_characters": invalid_characters,
        "length_multiple_of_three": length_multiple_of_three,
        "start_codon": normalized_cds[:3] if len(normalized_cds) >= 3 else "",
        "starts_with_atg": starts_with_atg,
        "terminal_stop_codon": terminal_stop_codon,
        "has_terminal_stop": has_terminal_stop,
        "internal_stop_positions": internal_stop_positions,
        "expected_protein_length": expected_protein_length,
        "protein_translation": protein_translation,
        "translation_summary": (
            f"标准遗传密码表；预计蛋白长度 {expected_protein_length} aa。"
            if translation_status == "通过"
            else "无法生成翻译摘要。"
        ),
        "translation_status": translation_status,
        "findings": findings,
        "blocking": any(bool(item["blocking"]) for item in findings),
    }
