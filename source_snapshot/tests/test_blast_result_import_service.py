# -*- coding: utf-8 -*-
"""Tests for imported BLAST TSV verification payloads."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.blast_result_import_service import build_blast_import_payload, parse_blast_tsv_hits
from services.sequence_verification_service import DISCLAIMER, run_sequence_verification


STANDARD_TSV = "query1\tNC_000913.3\t99.5\t120\t0\t0\t1\t120\t100\t219\t1e-40\t200\n"
HEADER_TSV = (
    "query id\tsubject id\tpercent identity\talignment length\tquery coverage\te-value\tbitscore\t"
    "subject title\torganism\n"
    "query1\tABC123\t97.2\t90\t75\t2e-20\t150\tExample enzyme\tExample organism\n"
)


def _codes(payload: dict) -> set[str]:
    return {item.get("code") for item in payload.get("warnings", []) if isinstance(item, dict)}


def test_parse_standard_blast_tsv_with_one_hit():
    hits = parse_blast_tsv_hits(STANDARD_TSV, query_length=120)

    assert len(hits) == 1
    assert hits[0]["accession"] == "NC_000913.3"
    assert hits[0]["percent_identity"] == 99.5
    assert hits[0]["alignment_length"] == 120
    assert hits[0]["coverage"] == 100.0
    assert hits[0]["e_value"] == "1e-40"
    assert hits[0]["bitscore"] == 200.0
    assert hits[0]["source"] == "Imported BLAST result"
    assert hits[0]["match_type"] == "blast_hit"


def test_parse_multiple_hits_and_sort_by_evalue_then_bitscore():
    tsv = "\n".join(
        [
            "query1\tB_HIT\t99\t100\t0\t0\t1\t100\t1\t100\t1e-20\t100",
            "query1\tA_HIT\t95\t100\t0\t0\t1\t100\t1\t100\t1e-50\t80",
            "query1\tC_HIT\t96\t100\t0\t0\t1\t100\t1\t100\t1e-20\t180",
        ]
    )

    hits = parse_blast_tsv_hits(tsv, query_length=100)

    assert [hit["accession"] for hit in hits] == ["A_HIT", "C_HIT", "B_HIT"]
    assert [hit["rank"] for hit in hits] == [1, 2, 3]


def test_missing_optional_organism_does_not_crash():
    payload = build_blast_import_payload(
        "query id\tsubject id\tpercent identity\talignment length\te-value\tbitscore\tsubject title\n"
        "query1\tABC123\t98\t120\t1e-30\t210\tExample title\n",
        query_length=120,
    )

    assert payload["status"] == "completed"
    assert payload["top_hit"]["organism"] == ""
    assert payload["top_hit"]["description"] == "Example title"


def test_missing_coverage_can_be_estimated_from_query_length():
    payload = build_blast_import_payload(STANDARD_TSV, query_length=240)

    assert payload["status"] == "completed"
    assert payload["top_hit"]["coverage"] == 50.0


def test_missing_coverage_without_query_length_remains_none():
    payload = build_blast_import_payload(STANDARD_TSV)

    assert payload["status"] == "completed"
    assert payload["top_hit"]["coverage"] is None


def test_low_coverage_emits_low_coverage_warning():
    payload = build_blast_import_payload(HEADER_TSV, query_length=120)

    assert payload["status"] == "completed"
    assert "LOW_COVERAGE" in _codes(payload)


def test_low_identity_emits_low_identity_warning():
    payload = build_blast_import_payload(
        "query id\tsubject id\tpercent identity\talignment length\tquery coverage\te-value\tbitscore\n"
        "query1\tLOWID\t55\t120\t100\t1e-10\t120\n",
        query_length=120,
    )

    assert payload["status"] == "completed"
    assert "LOW_IDENTITY" in _codes(payload)


def test_empty_tsv_returns_no_hits():
    payload = build_blast_import_payload("  \n\t")

    assert payload["status"] == "no_hits"
    assert payload["hits"] == []
    assert payload["top_hit"] is None
    assert "NO_HITS" in _codes(payload)


def test_header_only_tsv_returns_no_hits():
    payload = build_blast_import_payload(
        "qseqid\tsseqid\tpident\tlength\tmismatch\tgapopen\tqstart\tqend\tsstart\tsend\tevalue\tbitscore\n"
    )

    assert payload["status"] == "no_hits"
    assert payload["hits"] == []
    assert payload["top_hit"] is None
    assert "NO_HITS" in _codes(payload)


def test_malformed_tsv_returns_safe_unavailable_payload():
    payload = build_blast_import_payload("this is not\ta valid\tblast result")

    assert payload["status"] == "unavailable"
    assert payload["hits"] == []
    assert payload["top_hit"] is None
    assert "REMOTE_UNAVAILABLE" in _codes(payload)


def test_payload_includes_disclaimer():
    payload = build_blast_import_payload(STANDARD_TSV, query_length=120)

    assert payload["disclaimer"] == DISCLAIMER
    assert "INFORMATIONAL_ONLY" in _codes(payload)


def test_result_does_not_include_ready_approved_certified_wording():
    payload = build_blast_import_payload(STANDARD_TSV, query_length=120)
    text = str(payload).lower()

    assert "ready for" not in text
    assert "approved" not in text
    assert "certified" not in text


def test_imported_hits_integrate_with_sequence_verification_payload():
    hits = parse_blast_tsv_hits(STANDARD_TSV, query_length=120)
    payload = run_sequence_verification(
        "ATG" * 40,
        adapter={"hits": hits},
        database_label="Imported BLAST TSV",
    )

    assert payload["status"] == "completed"
    assert payload["database"]["source"] == "Imported BLAST TSV"
    assert payload["top_hit"]["source"] == "Imported BLAST result"
    assert payload["top_hit"]["match_type"] == "blast_hit"
    assert payload["disclaimer"] == DISCLAIMER
