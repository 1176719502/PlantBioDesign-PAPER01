# -*- coding: utf-8 -*-
"""Tests for the read-only sequence verification service."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.sequence_verification_service import DISCLAIMER, run_sequence_verification


VALID_SEQ = "ATG" + "GCC" * 20 + "TAA"


def _warning_codes(result: dict) -> set[str]:
    return {item.get("code") for item in result.get("warnings", []) if isinstance(item, dict)}


def _payload_text(result: dict) -> str:
    return str(result).lower()


def test_empty_input_returns_no_query_payload():
    result = run_sequence_verification("   \n>header\n")

    assert result["status"] == "no_query"
    assert result["query"]["length"] == 0
    assert result["query"]["hash"] == ""
    assert result["top_hit"] is None
    assert result["hits"] == []
    assert "NO_QUERY" in _warning_codes(result)
    assert result["disclaimer"] == DISCLAIMER


def test_no_adapter_returns_stable_placeholder_unavailable_payload():
    result = run_sequence_verification(VALID_SEQ, source_label="Unit test sequence")

    assert result["status"] == "unavailable"
    assert result["query"]["length"] == len(VALID_SEQ)
    assert result["query"]["source_label"] == "Unit test sequence"
    assert result["query"]["hash"]
    assert result["database"]["source"] == "Placeholder verification adapter"
    assert result["adapter_name"] == "placeholder"
    assert result["top_hit"] is None
    assert result["hits"] == []
    assert "REMOTE_UNAVAILABLE" in _warning_codes(result)
    assert "NO_HITS" in _warning_codes(result)
    assert result["timestamp"].endswith("Z")
    assert result["disclaimer"] == DISCLAIMER


class _HighIdentityAdapter:
    name = "fake-high-identity"

    def verify(self, sequence: str, database_label: str) -> dict:
        return {
            "hits": [
                {
                    "accession": "FAKE123",
                    "organism": "Example organism",
                    "description": "High identity fixture hit",
                    "percent_identity": 99.2,
                    "coverage": 96.5,
                    "e_value": "1e-80",
                    "alignment_length": len(sequence) - 3,
                    "alignment_summary": "Query 1-60 aligned to subject 10-69.",
                }
            ]
        }


def test_fake_adapter_high_identity_hit_returns_top_hit():
    result = run_sequence_verification(VALID_SEQ, adapter=_HighIdentityAdapter())

    assert result["status"] == "completed"
    assert result["adapter_name"] == "fake-high-identity"
    assert result["top_hit"]["accession"] == "FAKE123"
    assert result["top_hit"]["organism"] == "Example organism"
    assert result["top_hit"]["percent_identity"] == 99.2
    assert result["top_hit"]["coverage"] == 96.5
    assert result["top_hit"]["e_value"] == "1e-80"
    assert result["top_hit"]["alignment_summary"] == "Query 1-60 aligned to subject 10-69."


class _LowCoverageAdapter:
    def __call__(self, sequence: str, database_label: str) -> dict:
        return {
            "hits": [
                {
                    "accession": "LOWCOV1",
                    "organism": "Example organism",
                    "description": "Low coverage fixture hit",
                    "percent_identity": 91.0,
                    "coverage": 42.0,
                    "e_value": "2e-10",
                    "alignment_length": 30,
                    "alignment_summary": "Short partial alignment.",
                }
            ]
        }


def test_fake_adapter_low_coverage_emits_low_coverage_warning():
    result = run_sequence_verification(VALID_SEQ, adapter=_LowCoverageAdapter())

    assert result["status"] == "completed"
    assert result["top_hit"]["accession"] == "LOWCOV1"
    assert "LOW_COVERAGE" in _warning_codes(result)


class _ErrorAdapter:
    name = "fake-error"

    def verify(self, sequence: str, database_label: str) -> dict:
        raise RuntimeError("fixture adapter failure")


def test_adapter_error_returns_unavailable_payload():
    result = run_sequence_verification(VALID_SEQ, adapter=_ErrorAdapter())

    assert result["status"] == "unavailable"
    assert result["top_hit"] is None
    assert result["hits"] == []
    assert "REMOTE_UNAVAILABLE" in _warning_codes(result)
    assert "fixture adapter failure" in _payload_text(result)


def test_payload_includes_disclaimer_and_no_readiness_certification_wording():
    result = run_sequence_verification(VALID_SEQ, adapter=_HighIdentityAdapter())
    text = _payload_text(result)

    assert result["disclaimer"] == DISCLAIMER
    assert "informational only" in result["disclaimer"]
    assert "ready for" not in text
    assert "approved" not in text
    assert "certified" not in text
    assert "certify experimental readiness" in result["disclaimer"].lower()


def test_ambiguous_bases_emit_warning():
    result = run_sequence_verification("ATGNNNTAA")

    assert result["query"]["length"] == 9
    assert "AMBIGUOUS_BASES" in _warning_codes(result)
