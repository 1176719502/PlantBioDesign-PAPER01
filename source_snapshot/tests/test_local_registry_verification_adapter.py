# -*- coding: utf-8 -*-
"""Tests for local Parts Registry sequence verification adapter."""
from __future__ import annotations

import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.local_registry_verification_adapter import LocalRegistryVerificationAdapter
from services.sequence_verification_service import DISCLAIMER, run_sequence_verification

PART_SEQ = "ATGGCCGCTGCTTAA"
STALE_SEQ = "ATGTTTTTTTTTTAA"


def _records():
    return [
        {
            "id": "part-001",
            "name": "Demo CDS",
            "sequence": PART_SEQ,
            "host": "E.coli",
            "part_type": "CDS",
            "description": "Local demo coding sequence",
        }
    ]


def _warning_codes(result: dict) -> set[str]:
    return {item.get("code") for item in result.get("warnings", []) if isinstance(item, dict)}


def _local_result(sequence: str) -> dict:
    adapter = LocalRegistryVerificationAdapter(registry_loader=_records)
    return run_sequence_verification(sequence, adapter=adapter, database_label="Local Parts Registry")


def test_exact_local_registry_match_returns_completed_top_hit():
    result = _local_result(PART_SEQ)

    assert result["status"] == "completed"
    assert result["top_hit"]["accession"] == "part-001"
    assert result["top_hit"]["match_type"] == "exact_match"
    assert result["top_hit"]["part_type"] == "CDS"
    assert result["top_hit"]["source"] == "Local Parts Registry"
    assert result["top_hit"]["percent_identity"] == 100.0
    assert result["top_hit"]["coverage"] == 100.0
    assert result["top_hit"]["e_value"] == "local_exact"
    assert result["database"]["source"] == "Local Parts Registry"
    assert "LOCAL_REGISTRY_ONLY" in _warning_codes(result)


def test_query_contains_registry_part_returns_hit():
    result = _local_result("GGG" + PART_SEQ + "CCC")

    assert result["status"] == "completed"
    assert result["top_hit"]["match_type"] == "query_contains_part"
    assert result["top_hit"]["alignment_length"] == len(PART_SEQ)


def test_registry_part_contains_query_returns_hit():
    result = _local_result(PART_SEQ[3:12])

    assert result["status"] == "completed"
    assert result["top_hit"]["match_type"] == "part_contains_query"
    assert result["top_hit"]["alignment_length"] == len(PART_SEQ[3:12])


def test_reverse_complement_exact_match_returns_hit():
    result = _local_result("TTAAGCAGCGGCCAT")

    assert result["status"] == "completed"
    assert result["top_hit"]["match_type"] == "reverse_complement_exact_match"


def test_no_hit_returns_no_hits():
    result = _local_result("ATGTTTTTTTTTTAA")

    assert result["status"] == "no_hits"
    assert result["top_hit"] is None
    assert result["hits"] == []
    assert "NO_HITS" in _warning_codes(result)


def test_completed_current_sequence_reports_completed_with_stale_record_present():
    def records():
        return [
            {
                "id": "stale-001",
                "name": "Stale CDS",
                "sequence": STALE_SEQ,
                "host": "E.coli",
                "part_type": "CDS",
            },
            {
                "id": "part-001",
                "name": "Current CDS",
                "sequence": PART_SEQ,
                "host": "E.coli",
                "part_type": "CDS",
            },
        ]

    adapter = LocalRegistryVerificationAdapter(registry_loader=records)
    result = run_sequence_verification(PART_SEQ, adapter=adapter, database_label="Local Parts Registry")

    assert result["status"] == "completed"
    assert result["top_hit"]["accession"] == "part-001"
    assert result["top_hit"]["match_type"] == "exact_match"


def test_stale_completed_record_does_not_override_missing_current_sequence():
    def records():
        return [
            {
                "id": "stale-001",
                "name": "Stale CDS",
                "sequence": STALE_SEQ,
                "host": "E.coli",
                "part_type": "CDS",
            }
        ]

    adapter = LocalRegistryVerificationAdapter(registry_loader=records)
    result = run_sequence_verification(PART_SEQ, adapter=adapter, database_label="Local Parts Registry")

    assert result["status"] == "no_hits"
    assert result["top_hit"] is None
    assert result["hits"] == []


def test_missing_current_sequence_evidence_reports_no_hits():
    adapter = LocalRegistryVerificationAdapter(registry_loader=lambda: [])
    result = run_sequence_verification(PART_SEQ, adapter=adapter, database_label="Local Parts Registry")

    assert result["status"] == "no_hits"
    assert result["top_hit"] is None
    assert "NO_HITS" in _warning_codes(result)


def test_default_registry_lookup_initializes_isolated_tmp_database(tmp_path, monkeypatch):
    from core import database
    from services import parts_service

    db_path = tmp_path / "isolated_registry.db"
    monkeypatch.setattr(database, "DB_PATH", str(db_path))
    parts_service.get_all_parts_cached.clear()
    parts_service.get_parts_by_organism_cached.clear()
    parts_service.get_parts_by_organism_all_cached.clear()

    result = run_sequence_verification(
        (
            "ATGGTGAGCAAGGGCGAGGAGCTGTTCACCGGGGTGGTGCCC"
            "ATCCTGGTCGAGCTGGACGGCGACGTAAACGGCCACAAGTAA"
        ),
        adapter=LocalRegistryVerificationAdapter(),
        database_label="Local Parts Registry",
    )

    assert result["status"] == "completed"
    assert result["top_hit"]["accession"]


def test_empty_query_returns_no_query():
    result = _local_result("  >empty\n")

    assert result["status"] == "no_query"
    assert result["top_hit"] is None
    assert "NO_QUERY" in _warning_codes(result)


def test_ambiguous_bases_emit_ambiguous_warning():
    result = _local_result("ATGNNNTAA")

    assert "AMBIGUOUS_BASES" in _warning_codes(result)


def test_registry_unavailable_returns_unavailable():
    def broken_loader():
        raise RuntimeError("registry unavailable")

    adapter = LocalRegistryVerificationAdapter(registry_loader=broken_loader)
    result = run_sequence_verification(PART_SEQ, adapter=adapter, database_label="Local Parts Registry")

    assert result["status"] == "unavailable"
    assert result["top_hit"] is None
    assert "REGISTRY_UNAVAILABLE" in _warning_codes(result)


def test_payload_includes_disclaimer():
    result = _local_result(PART_SEQ)

    assert result["disclaimer"] == DISCLAIMER
    assert "informational only" in result["disclaimer"]


@pytest.mark.parametrize("blocked_word", ["ready for", "approved", "certified"])
def test_local_hit_does_not_include_readiness_wording(blocked_word: str):
    result = _local_result(PART_SEQ)

    assert blocked_word not in str(result).lower()
