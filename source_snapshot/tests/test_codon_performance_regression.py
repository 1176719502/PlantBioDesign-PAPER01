# -*- coding: utf-8 -*-
"""Codon optimization cache/performance regression checks.

This suite keeps scope intentionally small:
- validate repeated identical requests benefit from cache hits
- validate cached and uncached paths keep identical output semantics
- provide a lightweight timing-oriented guard via cache-hit counters
"""
from __future__ import annotations

import os
import sys
from copy import deepcopy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import codon_optimizer as optimizer_core
from views import CodonOptimizer as codon_view


RARE_CODON_SAMPLE = [
    {"codon": "ATA", "count": 2, "frequency": 3.1, "percentage": 5.0},
    {"codon": "AGG", "count": 1, "frequency": 1.0, "percentage": 2.5},
]


TEST_HOST = "E.coli"
TEST_CDS = (
    "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCCATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA"
)


def _run_uncached_view_path(sequence: str, host: str) -> dict:
    """Execute the same operations as the cached UI path, without cache."""
    validation = optimizer_core.validate_cds_sequence(sequence, host)
    if not validation.get("success"):
        return {
            "success": False,
            "error": "\n".join(validation.get("errors") or ["CDS validation failed."]),
            "validation": validation,
        }

    constraints_before = optimizer_core.analyze_sequence_constraints(sequence, host)
    optimized = optimizer_core.optimize_cds_sequence(sequence, host)
    if not optimized.get("success"):
        errors = optimized.get("errors") or ["Codon optimization failed."]
        return {
            "success": False,
            "error": "\n".join(errors),
            "validation": validation,
            "constraints_before": constraints_before,
            "result": optimized,
        }

    optimized.setdefault("validation", validation)
    optimized.setdefault("constraints_before", constraints_before)
    return optimized


def test_core_sequence_score_cache_hits_increase_on_repeated_optimization():
    """Repeated optimize calls should produce additional LRU cache hits."""
    optimizer_core._sequence_issue_score_cached.cache_clear()

    optimizer_core.optimize_cds_sequence(TEST_CDS, TEST_HOST)
    info_after_first = optimizer_core._sequence_issue_score_cached.cache_info()

    optimizer_core.optimize_cds_sequence(TEST_CDS, TEST_HOST)
    info_after_second = optimizer_core._sequence_issue_score_cached.cache_info()

    assert info_after_first.misses > 0
    assert info_after_second.hits > info_after_first.hits


def test_view_cached_wrapper_matches_uncached_behavior():
    """Cached wrapper must keep output equivalent to uncached logic."""
    if hasattr(codon_view._optimize_cached, "clear"):
        codon_view._optimize_cached.clear()

    cached_result = codon_view._optimize_cached(TEST_CDS, TEST_HOST)
    uncached_result = _run_uncached_view_path(TEST_CDS, TEST_HOST)

    assert cached_result == uncached_result


def test_build_rare_codon_summary_reports_total_unique_and_share():
    """Rare codon summary helper should expose stable aggregate diagnostics."""
    total_hits, unique_hits, total_pct = codon_view._build_rare_codon_summary(RARE_CODON_SAMPLE)

    assert total_hits == 3
    assert unique_hits == 2
    assert total_pct == 7.5


def test_build_hit_dataframe_maps_requested_labels():
    """Diagnostics dataframe helper should keep requested column labels."""
    dataframe = codon_view._build_hit_dataframe(
        [{"motif": "GAATTC", "start": 12, "end": 18}],
        [("motif", "Motif"), ("start", "Start"), ("end", "End")],
    )

    assert list(dataframe.columns) == ["Motif", "Start", "End"]
    assert dataframe.to_dict("records") == [{"Motif": "GAATTC", "Start": 12, "End": 18}]


def test_codon_usage_preview_context_copy_and_report_are_documentation_only():
    report = codon_view._build_optimization_report(
        host=TEST_HOST,
        table_metadata=optimizer_core.get_codon_table_metadata(TEST_HOST),
        input_sequence=TEST_CDS,
        optimized_sequence=TEST_CDS,
        cai_before=0.5,
        cai_after=0.6,
        gc_before=50.0,
        gc_after=51.0,
        codon_changes=0,
        protein_preserved=True,
        rare_before=0,
        rare_after=0,
        forbidden_before=0,
        forbidden_after=0,
        repeat_before=0,
        repeat_after=0,
        gc_outlier_before=0,
        gc_outlier_after=0,
        unresolved_warnings=[],
    )
    combined = "\n".join(
        [
            codon_view.CODON_USAGE_PREVIEW_CONTEXT_COPY,
            codon_view.CODON_USAGE_HANDOFF_COPY,
            report,
        ]
    )

    required = [
        "Codon Usage Preview",
        "candidate sequence documentation review helper",
        "local computational preview",
        "not an expression/yield optimization engine",
        "not prediction",
        "not recommendation",
        "not validation",
        "not readiness approval",
        "not a wet-lab protocol",
        "Candidate Sequence Preview",
    ]
    for phrase in required:
        assert phrase in combined


def test_codon_table_metadata_exists_for_each_supported_host():
    """Each supported table should expose review-oriented provenance metadata."""
    required_fields = {
        "table_id",
        "host_label",
        "organism_or_scope",
        "source_note",
        "version_or_date_note",
        "provenance_status",
        "draft_use_status",
        "limitation_note",
        "documentation_review_note",
        "manual_review_required",
    }

    assert set(optimizer_core.CODON_TABLE_METADATA) == set(optimizer_core.CODON_TABLES)

    for host in optimizer_core.CODON_TABLES:
        metadata = optimizer_core.get_codon_table_metadata(host)

        assert required_fields.issubset(metadata)
        assert metadata["host_label"]
        assert metadata["source_note"]
        assert "not fully documented" in metadata["source_note"]
        assert metadata["provenance_status"] == "local_reference_only"
        assert metadata["draft_use_status"] == "not_enabled_for_rewrite"
        assert metadata["limitation_note"]
        assert "Codon Usage Preview documentation context only" in metadata["limitation_note"]
        assert "biological recommendation" in metadata["limitation_note"]
        assert metadata["documentation_review_note"]
        assert "Provenance review is required" in metadata["documentation_review_note"]
        assert metadata["manual_review_required"] is True


def test_codon_table_metadata_blocks_future_rewrite_until_source_review():
    """R237 source audit keeps local tables preview-only until provenance is reviewed."""
    disallowed_status_terms = {
        "complete",
        "validated",
        "approved",
        "rewrite_enabled",
        "adaptation_enabled",
    }

    for host in optimizer_core.CODON_TABLES:
        metadata = optimizer_core.get_codon_table_metadata(host)
        combined = " ".join(str(value).lower() for value in metadata.values())

        assert metadata["provenance_status"] == "local_reference_only"
        assert metadata["draft_use_status"] == "not_enabled_for_rewrite"
        assert metadata["manual_review_required"] is True
        assert "provenance review is required" in combined
        assert all(term not in combined for term in disallowed_status_terms)


def test_codon_table_metadata_preserves_existing_numeric_tables():
    """R236 metadata should not alter the embedded codon usage table values."""
    expected_table_fingerprints = {
        "E.coli": (64, 991.3, 50.0, 0.3),
        "Yeast": (64, 1000.4, 45.6, 0.5),
        "Human": (64, 1000.2, 39.6, 0.8),
        "Rice": (64, 1057.0, 35.2, 0.6),
        "Maize": (64, 1015.8, 36.8, 0.5),
        "Arabidopsis": (64, 1044.2, 35.2, 0.5),
        "Tobacco": (64, 1003.0, 34.2, 0.5),
        "Agrobacterium": (64, 915.4, 38.5, 0.5),
    }

    observed = {
        host: (
            len(table),
            round(sum(table.values()), 1),
            max(table.values()),
            min(table.values()),
        )
        for host, table in optimizer_core.CODON_TABLES.items()
    }

    assert observed == expected_table_fingerprints


def test_codon_table_provenance_readback_rows_include_manual_review_cue():
    rows = dict(codon_view._codon_table_provenance_rows(TEST_HOST))

    assert rows["Selected codon usage table"] == TEST_HOST
    assert rows["Source/provenance note"]
    assert rows["Provenance status"] == "local_reference_only"
    assert rows["Future rewrite draft status"] == "not_enabled_for_rewrite"
    assert rows["Limitation note"]
    assert "Codon Usage Preview documentation context only" in rows["Limitation note"]
    assert rows["Documentation review note"]
    assert rows["Manual review required"] == "Yes"


def test_codon_usage_report_includes_table_provenance_readback():
    report = codon_view._build_optimization_report(
        host=TEST_HOST,
        table_metadata=optimizer_core.get_codon_table_metadata(TEST_HOST),
        input_sequence=TEST_CDS,
        optimized_sequence=TEST_CDS,
        cai_before=0.5,
        cai_after=0.6,
        gc_before=50.0,
        gc_after=51.0,
        codon_changes=0,
        protein_preserved=True,
        rare_before=0,
        rare_after=0,
        forbidden_before=0,
        forbidden_after=0,
        repeat_before=0,
        repeat_after=0,
        gc_outlier_before=0,
        gc_outlier_after=0,
        unresolved_warnings=[],
    )

    required = [
        "Selected codon usage table",
        "Source/provenance note",
        "Provenance status: local_reference_only",
        "Future rewrite draft status: not_enabled_for_rewrite",
        "Limitation note",
        "Documentation review note",
        "Manual review required: Yes",
        "Codon Usage Preview documentation context only",
    ]
    for phrase in required:
        assert phrase in report


def test_codon_draft_metrics_readback_rows_are_metrics_only_and_show_provenance():
    metrics = codon_view._build_codon_draft_metrics_payload("ATGGCTCTATAA", TEST_HOST)
    rows = dict(codon_view._codon_draft_metrics_rows(metrics, raw_cds="ATGGCTCTATAA", host=TEST_HOST))
    rendered = "\n".join(f"{key}: {value}" for key, value in rows.items())

    assert rows["Metrics-only status"] == "review_metrics_only"
    assert rows["Readback boundary"] == "review metrics only; preview-only; manual review required"
    assert rows["Sequence rewrite output"] == "not a sequence rewrite"
    assert rows["Expression prediction output"] == "not an expression prediction"
    assert rows["Nucleotide length"] == "12"
    assert rows["Codon count"] == "4"
    assert rows["Multiple-of-3 status"] == "multiple_of_3"
    assert rows["Rare codon count"] == "1"
    assert rows["Rare codon cluster count"] == "0"
    assert rows["Selected codon usage table"] == TEST_HOST
    assert rows["Codon table provenance/source status"] == "local_reference_only"
    assert rows["Manual review cue"] == "manual review required"
    assert "ATGGCTCTATAA" not in rendered
    assert "optimized_sequence" not in rendered
    assert "candidate_sequence" not in rendered


def test_codon_draft_metrics_readback_rows_show_safe_empty_and_invalid_states():
    empty_metrics = codon_view._build_codon_draft_metrics_payload("", TEST_HOST)
    empty_rows = dict(codon_view._codon_draft_metrics_rows(empty_metrics, raw_cds="", host=TEST_HOST))

    invalid_metrics = codon_view._build_codon_draft_metrics_payload("ATGNNU", TEST_HOST)
    invalid_rows = dict(codon_view._codon_draft_metrics_rows(invalid_metrics, raw_cds="ATGNNU", host=TEST_HOST))

    unavailable_metrics = {
        "metrics_only_status": "review_metrics_only",
        "cds_length_review": {},
        "start_stop_review": {},
        "base_composition_review": {},
        "codon_usage_review": {},
        "table_provenance": {},
        "review_flags": [],
    }
    unavailable_rows = dict(
        codon_view._codon_draft_metrics_rows(unavailable_metrics, raw_cds="ATGGCT", host="")
    )

    assert empty_rows["CDS entry state"] == "no CDS entered"
    assert empty_rows["Review flags"] == "empty_input, start_codon_manual_review, terminal_stop_codon_manual_review"
    assert invalid_rows["CDS base review"] == "invalid/ambiguous CDS"
    assert invalid_rows["Invalid/ambiguous base count"] == "3"
    assert unavailable_rows["Selected codon usage table"] == "no codon table selected"
    assert unavailable_rows["Codon table provenance/source status"] == "codon table provenance unavailable"


def test_codon_usage_preview_page_does_not_add_artifact_or_project_link_entrypoints():
    from pathlib import Path

    source = Path(codon_view.__file__).read_text(encoding="utf-8")
    forbidden = [
        "create_tool_artifact",
        "Save Documentation Artifact",
        "Optional Pathway Project link",
        "list_pathway_projects",
        "project_id=",
    ]

    for phrase in forbidden:
        assert phrase not in source


def test_build_change_impact_summary_classifies_existing_history_signals():
    """Change-impact helper should classify CAI, constraints, and rare-codon relief."""
    history = [
        {
            "pass": 1,
            "codon_index": 0,
            "from_codon": "ATA",
            "to_codon": "ATC",
            "score_before": 100.0,
            "score_after": 90.0,
        },
        {
            "pass": "cai_sweep",
            "codon_index": 1,
            "from_codon": "GTA",
            "to_codon": "GTG",
            "score_before": 90.0,
            "score_after": 89.0,
        },
        {
            "pass": 2,
            "codon_index": 2,
            "from_codon": "TTA",
            "to_codon": "CTG",
            "score_before": 89.0,
            "score_after": 70.0,
        },
    ]
    before_diag = {
        "rare_codons": [
            {"codon": "ATA", "count": 1, "frequency": 3.1, "percentage": 10.0},
            {"codon": "TTA", "count": 1, "frequency": 4.0, "percentage": 10.0},
        ]
    }
    after_diag = {
        "rare_codons": []
    }

    summary = codon_view._build_change_impact_summary(history, before_diag, after_diag, TEST_HOST)

    assert summary["summary"] == {
        "cai_primary": 1,
        "constraint_driven": 2,
        "rare_codon_relief": 2,
        "total": 3,
    }
    assert summary["by_amino_acid"] == [
        {"Amino Acid": "I", "Edits": 1},
        {"Amino Acid": "L", "Edits": 1},
        {"Amino Acid": "V", "Edits": 1},
    ]
    assert summary["by_frequency_effect"] == [{"Effect": "Higher host-frequency codon", "Edits": 3}]
    assert [row["Primary Driver"] for row in summary["rows"]] == [
        "Constraint-driven",
        "CAI-driven",
        "Constraint-driven",
    ]
    assert [row["Rare Codon Relief"] for row in summary["rows"]] == ["Yes", "No", "Yes"]


def test_view_cached_wrapper_avoids_recomputing_identical_requests(monkeypatch):
    """Second identical request should return from cache, avoiding recompute."""
    if hasattr(codon_view._optimize_cached, "clear"):
        codon_view._optimize_cached.clear()

    counters = {"validate": 0, "analyze": 0, "optimize": 0}

    original_validate = optimizer_core.validate_cds_sequence
    original_analyze = optimizer_core.analyze_sequence_constraints
    original_optimize = optimizer_core.optimize_cds_sequence

    def _validate_wrapper(*args, **kwargs):
        counters["validate"] += 1
        return original_validate(*args, **kwargs)

    def _analyze_wrapper(*args, **kwargs):
        counters["analyze"] += 1
        return original_analyze(*args, **kwargs)

    def _optimize_wrapper(*args, **kwargs):
        counters["optimize"] += 1
        return original_optimize(*args, **kwargs)

    monkeypatch.setattr(optimizer_core, "validate_cds_sequence", _validate_wrapper)
    monkeypatch.setattr(optimizer_core, "analyze_sequence_constraints", _analyze_wrapper)
    monkeypatch.setattr(optimizer_core, "optimize_cds_sequence", _optimize_wrapper)

    first = deepcopy(codon_view._optimize_cached(TEST_CDS, TEST_HOST))
    first_counts = dict(counters)
    second = deepcopy(codon_view._optimize_cached(TEST_CDS, TEST_HOST))

    assert first == second
    assert first_counts["validate"] >= 1
    assert first_counts["analyze"] == 1
    assert first_counts["optimize"] == 1
    assert counters == first_counts
