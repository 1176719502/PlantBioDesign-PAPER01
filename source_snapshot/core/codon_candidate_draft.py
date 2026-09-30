# -*- coding: utf-8 -*-
"""Controlled codon candidate draft generation service.

The service creates a deterministic computational synonymous recoding
candidate for review. It does not integrate with the Expression Wizard UI,
saved state, primer design, or downstream assembly.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List

from core.codon_optimizer import (
    AA_TO_CODONS,
    CODON_TABLES,
    CODON_TO_AA,
    DNA_BASES,
    STOP_CODONS,
    calculate_gc_content,
    get_codon_table_metadata,
)


CODON_CANDIDATE_DRAFT_STATUS = "codon_candidate_draft_available_for_review"
CODON_CANDIDATE_REJECTED_STATUS = "codon_candidate_draft_not_created"
CODON_CANDIDATE_DRAFT_SCHEMA_VERSION = "codon_candidate_draft_core_service_v1"
RARE_CODON_THRESHOLD_PER_THOUSAND = 5.0
RARE_CODON_CLUSTER_MIN_SIZE = 2


def _normalize_cds(raw_cds: Any) -> str:
    """Normalize CDS input while dropping FASTA headers."""
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


def _translate_codons(codons: Iterable[str]) -> str:
    protein: list[str] = []
    for codon in codons:
        amino_acid = CODON_TO_AA.get(codon)
        if amino_acid is None:
            return ""
        protein.append(amino_acid)
    return "".join(protein)


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


def _rare_codon_summary(codons: List[str], table_key: str) -> Dict[str, Any]:
    codon_table = CODON_TABLES.get(table_key, {})
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
        "rare_codon_threshold_per_thousand": RARE_CODON_THRESHOLD_PER_THOUSAND,
        "evaluated_codon_count": evaluated_codon_count,
        "rare_codon_count": len(rare_positions),
        "rare_codon_unique_count": len(rare_unique_codons),
        "rare_codon_cluster_count": _count_rare_codon_clusters(rare_positions),
        "rare_codon_cluster_min_size": RARE_CODON_CLUSTER_MIN_SIZE,
    }


def _sequence_metrics(sequence: str, table_key: str) -> Dict[str, Any]:
    codons = _complete_codons(sequence)
    rare_summary = _rare_codon_summary(codons, table_key)
    return {
        "length": len(sequence),
        "gc_percent": round(calculate_gc_content(sequence), 2),
        "rare_codon_count": rare_summary["rare_codon_count"],
        "rare_codon_clusters": rare_summary["rare_codon_cluster_count"],
        "rare_codon_review": rare_summary,
    }


def _ranked_codons_for_amino_acid(amino_acid: str, table_key: str) -> list[str]:
    codon_table = CODON_TABLES[table_key]
    return sorted(
        AA_TO_CODONS.get(amino_acid, []),
        key=lambda codon: (-codon_table.get(codon, 0.0), codon),
    )


def _build_candidate_codons(codons: List[str], table_key: str) -> List[str]:
    terminal_stop_index = len(codons) - 1 if codons and codons[-1] in STOP_CODONS else None
    candidate_codons: list[str] = []

    for index, codon in enumerate(codons):
        if index == terminal_stop_index:
            candidate_codons.append(codon)
            continue
        amino_acid = CODON_TO_AA[codon]
        if index == 0:
            candidate_codons.append(codon)
            continue
        ranked_codons = _ranked_codons_for_amino_acid(amino_acid, table_key)
        candidate_codons.append(ranked_codons[0] if ranked_codons else codon)

    return candidate_codons


def _validation_payload(normalized_cds: str) -> Dict[str, Any]:
    codons = _complete_codons(normalized_cds)
    invalid_or_ambiguous_bases = sorted({base for base in normalized_cds if base not in DNA_BASES})
    length_multiple_of_3 = bool(normalized_cds) and len(normalized_cds) % 3 == 0
    internal_stop_positions: list[int] = []

    if length_multiple_of_3 and not invalid_or_ambiguous_bases:
        terminal_stop_index = len(codons) - 1 if codons and codons[-1] in STOP_CODONS else None
        for index, codon in enumerate(codons):
            if codon in STOP_CODONS and index != terminal_stop_index:
                internal_stop_positions.append(index + 1)

    errors: list[str] = []
    warnings: list[str] = []
    review_flags: list[str] = []

    if not normalized_cds:
        errors.append("CDS input is empty.")
        review_flags.append("empty_input")
    if invalid_or_ambiguous_bases:
        errors.append("CDS contains invalid or ambiguous bases.")
        review_flags.append("invalid_or_ambiguous_bases_detected")
    if normalized_cds and not length_multiple_of_3:
        errors.append("CDS length is not a multiple of 3.")
        review_flags.append("length_not_multiple_of_3")
    if internal_stop_positions:
        errors.append("CDS contains internal stop codons.")
        review_flags.append("internal_stop_codons_detected")
    if length_multiple_of_3 and codons and codons[-1] in STOP_CODONS:
        warnings.append("Terminal stop codon structure is preserved in the candidate draft.")

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "review_flags": review_flags,
        "invalid_or_ambiguous_bases": invalid_or_ambiguous_bases,
        "length_multiple_of_3": length_multiple_of_3,
        "internal_stop_codon_positions": internal_stop_positions,
        "has_terminal_stop_codon": bool(length_multiple_of_3 and codons and codons[-1] in STOP_CODONS),
        "start_codon": codons[0] if codons else "",
    }


def build_codon_candidate_draft(
    raw_cds: Any,
    table_key: str | None = "E.coli",
    table_metadata: dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Build a deterministic codon candidate draft for manual review."""
    normalized_cds = _normalize_cds(raw_cds)
    selected_table_key = _resolve_table_key(table_key)
    metadata = dict(table_metadata or get_codon_table_metadata(selected_table_key))
    validation = _validation_payload(normalized_cds)
    original_codons = _complete_codons(normalized_cds)
    original_metrics = _sequence_metrics(normalized_cds, selected_table_key)

    base_payload: Dict[str, Any] = {
        "schema_version": CODON_CANDIDATE_DRAFT_SCHEMA_VERSION,
        "status": CODON_CANDIDATE_REJECTED_STATUS,
        "candidate_kind": "codon candidate draft",
        "candidate_label": "computational synonymous recoding candidate",
        "selected_table_key": selected_table_key,
        "table_provenance": metadata,
        "input_sequence": normalized_cds,
        "candidate_sequence": "",
        "changed": False,
        "validation": validation,
        "warnings": list(validation["warnings"]),
        "errors": list(validation["errors"]),
        "metrics": {
            "original_length": original_metrics["length"],
            "candidate_length": 0,
            "original_gc_percent": original_metrics["gc_percent"],
            "candidate_gc_percent": 0.0,
            "original_rare_codon_count": original_metrics["rare_codon_count"],
            "candidate_rare_codon_count": 0,
            "original_rare_codon_clusters": original_metrics["rare_codon_clusters"],
            "candidate_rare_codon_clusters": 0,
            "translation_preserved": False,
        },
        "routing": {
            "expression_wizard_step4": "not_routed",
            "downstream_expression_frame_assembly": "not_performed",
            "automatic_handoff": False,
        },
        "boundary": {
            "scope": "documentation-only codon candidate draft review",
            "copy": (
                "Computational synonymous recoding candidate for manual documentation review; "
                "not biological advice, not an experimental validation claim, not proof of "
                "expression behavior, and not a build-readiness judgment."
            ),
            "manual_review_required": True,
        },
    }

    if not validation["valid"]:
        return base_payload

    candidate_codons = _build_candidate_codons(original_codons, selected_table_key)
    candidate_sequence = "".join(candidate_codons)
    original_translation = _translate_codons(original_codons)
    candidate_translation = _translate_codons(candidate_codons)
    translation_preserved = bool(original_translation and original_translation == candidate_translation)

    if not translation_preserved:
        base_payload["errors"] = ["Candidate draft translation did not match the input CDS."]
        base_payload["validation"]["review_flags"] = (
            list(base_payload["validation"]["review_flags"]) + ["translation_mismatch_detected"]
        )
        return base_payload

    candidate_metrics = _sequence_metrics(candidate_sequence, selected_table_key)
    base_payload.update(
        {
            "status": CODON_CANDIDATE_DRAFT_STATUS,
            "candidate_sequence": candidate_sequence,
            "changed": candidate_sequence != normalized_cds,
            "translation": {
                "original": original_translation,
                "candidate": candidate_translation,
                "preserved": True,
            },
            "metrics": {
                "original_length": original_metrics["length"],
                "candidate_length": candidate_metrics["length"],
                "original_gc_percent": original_metrics["gc_percent"],
                "candidate_gc_percent": candidate_metrics["gc_percent"],
                "original_rare_codon_count": original_metrics["rare_codon_count"],
                "candidate_rare_codon_count": candidate_metrics["rare_codon_count"],
                "original_rare_codon_clusters": original_metrics["rare_codon_clusters"],
                "candidate_rare_codon_clusters": candidate_metrics["rare_codon_clusters"],
                "translation_preserved": True,
            },
        }
    )
    return base_payload
