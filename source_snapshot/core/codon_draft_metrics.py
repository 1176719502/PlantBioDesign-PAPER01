# -*- coding: utf-8 -*-
"""Metrics-only codon draft review helper.

This module intentionally reports review metrics for the provided CDS and
selected codon usage table without returning rewritten or generated CDS output.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from core.codon_optimizer import (
    CODON_TABLES,
    DNA_BASES,
    STOP_CODONS,
    calculate_gc_content,
    get_codon_table_metadata,
)


METRICS_ONLY_STATUS = "review_metrics_only"
RARE_CODON_THRESHOLD_PER_THOUSAND = 5.0
RARE_CODON_CLUSTER_MIN_SIZE = 2


def _normalize_cds_for_review(raw_cds: Any) -> str:
    """Normalize CDS input for metrics review while dropping FASTA headers."""
    if raw_cds is None:
        return ""
    if not isinstance(raw_cds, str):
        raw_cds = str(raw_cds)
    lines = [
        line.strip()
        for line in raw_cds.strip().splitlines()
        if not line.strip().startswith(">")
    ]
    return "".join(lines).replace(" ", "").replace("\t", "").replace("\r", "").upper()


def _resolve_table_key(table_key: str | None) -> str:
    return table_key if table_key in CODON_TABLES else "E.coli"


def _complete_codons(normalized_cds: str) -> List[str]:
    return [
        normalized_cds[index:index + 3]
        for index in range(0, len(normalized_cds), 3)
        if len(normalized_cds[index:index + 3]) == 3
    ]


def _terminal_stop_status(normalized_cds: str, codons: List[str]) -> tuple[str, bool]:
    if not normalized_cds:
        return "not_assessed_empty_input", False
    if len(normalized_cds) % 3 != 0:
        return "not_assessed_length_not_multiple_of_3", False
    if codons and codons[-1] in STOP_CODONS:
        return "present", True
    return "absent", False


def _start_codon_status(normalized_cds: str) -> tuple[str, bool]:
    if not normalized_cds:
        return "not_assessed_empty_input", False
    if len(normalized_cds) < 3:
        return "not_assessed_short_input", False
    if normalized_cds.startswith("ATG"):
        return "present_atg", True
    return "absent_at_first_codon", False


def _count_rare_codon_clusters(rare_positions: Iterable[int]) -> int:
    clusters = 0
    run_length = 0
    previous_position = None

    for position in sorted(rare_positions):
        if previous_position is None or position == previous_position + 1:
            run_length += 1
        else:
            if run_length >= RARE_CODON_CLUSTER_MIN_SIZE:
                clusters += 1
            run_length = 1
        previous_position = position

    if run_length >= RARE_CODON_CLUSTER_MIN_SIZE:
        clusters += 1
    return clusters


def _rare_codon_metrics(codons: List[str], selected_table_key: str) -> Dict[str, Any]:
    codon_table = CODON_TABLES.get(selected_table_key, {})
    rare_positions: list[int] = []
    rare_unique_codons: set[str] = set()
    evaluated_codon_count = 0

    for index, codon in enumerate(codons):
        if codon in STOP_CODONS or codon not in codon_table:
            continue
        evaluated_codon_count += 1
        if codon_table[codon] < RARE_CODON_THRESHOLD_PER_THOUSAND:
            rare_positions.append(index)
            rare_unique_codons.add(codon)

    return {
        "selected_table_key": selected_table_key,
        "rare_codon_threshold_per_thousand": RARE_CODON_THRESHOLD_PER_THOUSAND,
        "evaluated_codon_count": evaluated_codon_count,
        "rare_codon_count": len(rare_positions),
        "rare_codon_unique_count": len(rare_unique_codons),
        "rare_codon_cluster_count": _count_rare_codon_clusters(rare_positions),
        "rare_codon_cluster_min_size": RARE_CODON_CLUSTER_MIN_SIZE,
    }


def build_codon_draft_metrics(
    raw_cds: Any,
    table_key: str | None = "E.coli",
    table_metadata: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a metrics-only codon usage review payload.

    The returned payload reports measurements and provenance readback only. It
    does not include any rewritten CDS, generated CDS, replacement codons, or
    biological readiness judgment.
    """
    normalized_cds = _normalize_cds_for_review(raw_cds)
    selected_table_key = _resolve_table_key(table_key)
    metadata = dict(table_metadata or get_codon_table_metadata(selected_table_key))
    codons = _complete_codons(normalized_cds)
    invalid_bases = sorted({base for base in normalized_cds if base not in DNA_BASES})
    invalid_base_count = sum(1 for base in normalized_cds if base not in DNA_BASES)
    length_multiple_of_3 = bool(normalized_cds) and len(normalized_cds) % 3 == 0
    start_status, start_present = _start_codon_status(normalized_cds)
    stop_status, terminal_stop_present = _terminal_stop_status(normalized_cds, codons)

    internal_codons = codons[:-1] if length_multiple_of_3 and codons else codons
    internal_stop_count = sum(1 for codon in internal_codons if codon in STOP_CODONS)
    review_flags: list[str] = []
    if not normalized_cds:
        review_flags.append("empty_input")
    if invalid_base_count:
        review_flags.append("ambiguous_or_invalid_bases_detected")
    if normalized_cds and not length_multiple_of_3:
        review_flags.append("length_not_multiple_of_3")
    if start_status != "present_atg":
        review_flags.append("start_codon_manual_review")
    if stop_status != "present":
        review_flags.append("terminal_stop_codon_manual_review")
    if internal_stop_count:
        review_flags.append("internal_stop_codons_detected")

    return {
        "status": METRICS_ONLY_STATUS,
        "metrics_only_status": METRICS_ONLY_STATUS,
        "cds_length_review": {
            "normalized_input_length": len(normalized_cds),
            "nucleotide_length": len(normalized_cds),
            "codon_count": len(codons),
            "length_multiple_of_3": length_multiple_of_3,
            "length_status": "multiple_of_3" if length_multiple_of_3 else "manual_review_required",
        },
        "start_stop_review": {
            "start_codon_status": start_status,
            "start_codon_present": start_present,
            "terminal_stop_codon_status": stop_status,
            "terminal_stop_codon_present": terminal_stop_present,
            "internal_stop_codon_count": internal_stop_count,
        },
        "base_composition_review": {
            "ambiguous_or_invalid_base_count": invalid_base_count,
            "ambiguous_or_invalid_bases": invalid_bases,
            "gc_percentage": round(calculate_gc_content(normalized_cds), 2),
        },
        "codon_usage_review": _rare_codon_metrics(codons, selected_table_key),
        "table_provenance": metadata,
        "review_flags": review_flags,
        "boundary": {
            "scope": "codon_draft_metrics",
            "copy": "Review metrics only; no rewritten or generated CDS is returned.",
            "manual_review_required": True,
        },
    }
