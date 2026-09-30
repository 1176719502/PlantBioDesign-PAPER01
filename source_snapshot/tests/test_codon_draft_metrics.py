from __future__ import annotations

import os
import sys
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.codon_draft_metrics import (  # noqa: E402
    METRICS_ONLY_STATUS,
    build_codon_draft_metrics,
)
from core.codon_optimizer import get_codon_table_metadata  # noqa: E402


UNSAFE_OUTPUT_KEY_TERMS = [
    "rewritten",
    "generated",
    "optimized_sequence",
    "optimized_dna",
    "replacement",
    "recommended_sequence",
    "best_codon",
    "expression_prediction",
    "wet_lab_readiness",
]


def _flatten_keys(payload: Any, prefix: str = "") -> list[str]:
    if isinstance(payload, dict):
        keys: list[str] = []
        for key, value in payload.items():
            key_path = f"{prefix}.{key}" if prefix else str(key)
            keys.append(key_path)
            keys.extend(_flatten_keys(value, key_path))
        return keys
    if isinstance(payload, list):
        keys = []
        for index, value in enumerate(payload):
            keys.extend(_flatten_keys(value, f"{prefix}[{index}]"))
        return keys
    return []


def test_valid_cds_returns_expected_review_metrics() -> None:
    metrics = build_codon_draft_metrics("atg gct cta taa", "E.coli")

    assert metrics["status"] == METRICS_ONLY_STATUS
    assert metrics["metrics_only_status"] == "review_metrics_only"
    assert metrics["cds_length_review"] == {
        "normalized_input_length": 12,
        "nucleotide_length": 12,
        "codon_count": 4,
        "length_multiple_of_3": True,
        "length_status": "multiple_of_3",
    }
    assert metrics["start_stop_review"] == {
        "start_codon_status": "present_atg",
        "start_codon_present": True,
        "terminal_stop_codon_status": "present",
        "terminal_stop_codon_present": True,
        "internal_stop_codon_count": 0,
    }
    assert metrics["base_composition_review"]["ambiguous_or_invalid_base_count"] == 0
    assert metrics["base_composition_review"]["gc_percentage"] == 33.33
    assert metrics["codon_usage_review"]["rare_codon_count"] == 1
    assert metrics["codon_usage_review"]["rare_codon_unique_count"] == 1
    assert metrics["codon_usage_review"]["rare_codon_cluster_count"] == 0
    assert metrics["review_flags"] == []


def test_invalid_or_ambiguous_sequence_returns_safe_review_flags() -> None:
    metrics = build_codon_draft_metrics(">demo\nATGNNU", "Yeast")

    assert metrics["cds_length_review"]["normalized_input_length"] == 6
    assert metrics["cds_length_review"]["length_multiple_of_3"] is True
    assert metrics["start_stop_review"]["start_codon_status"] == "present_atg"
    assert metrics["start_stop_review"]["terminal_stop_codon_status"] == "absent"
    assert metrics["base_composition_review"]["ambiguous_or_invalid_base_count"] == 3
    assert metrics["base_composition_review"]["ambiguous_or_invalid_bases"] == ["N", "U"]
    assert "ambiguous_or_invalid_bases_detected" in metrics["review_flags"]
    assert "terminal_stop_codon_manual_review" in metrics["review_flags"]


def test_internal_stop_codons_are_counted_not_corrected() -> None:
    metrics = build_codon_draft_metrics("ATGTAAGCTTAA", "E.coli")

    assert metrics["cds_length_review"]["codon_count"] == 4
    assert metrics["start_stop_review"]["terminal_stop_codon_present"] is True
    assert metrics["start_stop_review"]["internal_stop_codon_count"] == 1
    assert "internal_stop_codons_detected" in metrics["review_flags"]


def test_rare_codon_clusters_are_deterministic_table_relative_metrics() -> None:
    metrics = build_codon_draft_metrics("ATGCTACTACGATAA", "E.coli")
    usage = metrics["codon_usage_review"]

    assert usage["selected_table_key"] == "E.coli"
    assert usage["rare_codon_threshold_per_thousand"] == 5.0
    assert usage["rare_codon_count"] == 3
    assert usage["rare_codon_unique_count"] == 2
    assert usage["rare_codon_cluster_count"] == 1
    assert usage["rare_codon_cluster_min_size"] == 2


def test_table_provenance_is_included_and_keeps_rewrite_boundary() -> None:
    metadata = get_codon_table_metadata("Rice")
    metrics = build_codon_draft_metrics("ATGGCTTAA", "Rice")

    assert metrics["table_provenance"] == metadata
    assert metrics["table_provenance"]["provenance_status"] == "local_reference_only"
    assert metrics["table_provenance"]["draft_use_status"] == "not_enabled_for_rewrite"
    assert metrics["table_provenance"]["manual_review_required"] is True
    assert metrics["boundary"]["manual_review_required"] is True


def test_unknown_table_key_falls_back_to_local_reference_default() -> None:
    metrics = build_codon_draft_metrics("ATGGCTTAA", "Unknown host")

    assert metrics["codon_usage_review"]["selected_table_key"] == "E.coli"
    assert metrics["table_provenance"]["host_label"] == "E.coli"


def test_metrics_payload_contains_no_sequence_rewrite_output_fields() -> None:
    metrics = build_codon_draft_metrics("ATGGCTTAA", "E.coli")
    flat_keys = [key.lower() for key in _flatten_keys(metrics)]

    offenders = [
        key
        for key in flat_keys
        for term in UNSAFE_OUTPUT_KEY_TERMS
        if term in key
    ]

    assert offenders == []
    assert "sequence" not in metrics
    assert "input_sequence" not in metrics
    assert "candidate_sequence" not in metrics
