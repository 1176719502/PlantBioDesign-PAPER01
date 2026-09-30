# -*- coding: utf-8 -*-
"""Regression tests for low-risk registry read-path optimizations."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services import parts_service


def test_normalize_part_type_handles_supported_aliases_and_unknown_values():
    assert parts_service.normalize_part_type(" cds ") == "CDS"
    assert parts_service.normalize_part_type("Coding Sequence") == "CDS"
    assert parts_service.normalize_part_type("promoter_sequence") == "Promoter"
    assert parts_service.normalize_part_type("ribosome-binding-site") == "RBS"
    assert parts_service.normalize_part_type("Kozak sequence") == "RBS"
    assert parts_service.normalize_part_type("transcription terminator") == "Terminator"
    assert parts_service.normalize_part_type("Enhancer") == "Enhancer"
    assert parts_service.normalize_part_type(" enhancer ") == "enhancer"


def test_canonical_part_record_maps_database_row_with_compatibility_fields():
    row = {
        "id": 7,
        "name": "T7 Promoter",
        "part_type": "promoter sequence",
        "organism": "E.coli",
        "sequence": "TAATACGACTCACTATA",
        "length_bp": 17,
        "gc_content": 35.3,
        "description": "Strong bacterial promoter.",
        "source_type": "Seed library",
        "function_summary": "Drives transcription.",
    }

    record = parts_service.canonical_part_record(row)

    assert record["id"] == 7
    assert record["name"] == "T7 Promoter"
    assert record["canonical_type"] == "Promoter"
    assert record["raw_type"] == "promoter sequence"
    assert record["sequence"] == "TAATACGACTCACTATA"
    assert record["host"] == "E.coli"
    assert record["source"] == "Seed library"
    assert record["description"] == "Strong bacterial promoter."
    assert record["metadata"]["gc_content"] == 35.3
    assert record["metadata"]["function_summary"] == "Drives transcription."
    assert record["part_type"] == "Promoter"
    assert record["organism"] == "E.coli"
    assert record["length_bp"] == 17


def test_canonical_part_record_maps_display_table_row():
    row = {
        "ID": 11,
        "Name": "eGFP CDS Fragment",
        "Type": "coding sequence",
        "Organism": "Universal",
        "Sequence": "ATGGTG",
        "Length (bp)": 6,
        "Description": "Reporter fragment.",
        "Source Type": "Seed library",
        "Notes": "Starter entry.",
    }

    record = parts_service.canonical_part_record(row)

    assert record["id"] == 11
    assert record["name"] == "eGFP CDS Fragment"
    assert record["canonical_type"] == "CDS"
    assert record["raw_type"] == "coding sequence"
    assert record["sequence"] == "ATGGTG"
    assert record["host"] == "Universal"
    assert record["source"] == "Seed library"
    assert record["description"] == "Reporter fragment."
    assert record["metadata"]["notes"] == "Starter entry."
    assert record["part_type"] == "CDS"
    assert record["length_bp"] == 6


def test_query_registry_parts_filters_global_records_to_canonical_contract(monkeypatch):
    sample_df = parts_service.pd.DataFrame(
        [
            {"name": "C1", "part_type": "coding sequence", "sequence": "ATGAAA", "source_type": "Seed library"},
            {"name": "P1", "part_type": "promoter", "sequence": "TTGACA", "source_type": "Seed library"},
        ]
    )
    calls = []

    def _fake_get_all_parts_cached(filter_type=None):
        calls.append(filter_type)
        return sample_df

    monkeypatch.setattr(parts_service, "get_all_parts_cached", _fake_get_all_parts_cached)

    records = parts_service.query_registry_parts(part_types=["CDS"], source_scope="Seed library")

    assert calls == ["CDS"]
    assert [row["name"] for row in records] == ["C1"]
    assert records[0]["canonical_type"] == "CDS"
    assert records[0]["source"] == "Seed library"


def test_query_registry_parts_groups_host_records(monkeypatch):
    sample_rows = [
        {"name": "P1", "part_type": "promoter", "sequence": "ATGC"},
        {"name": "R1", "part_type": "ribosome binding site", "sequence": "AGGA"},
        {"name": "P2", "part_type": "Promoter ", "sequence": "ATGG"},
    ]

    monkeypatch.setattr(parts_service, "get_parts_by_organism_all_cached", lambda organism: sample_rows)
    monkeypatch.setattr(parts_service, "host_to_organism", lambda host: "E.coli")

    grouped = parts_service.query_registry_parts(
        host="E.coli BL21(DE3)",
        part_types=["Promoter", "RBS"],
        group_by_type=True,
    )

    assert list(grouped.keys()) == ["Promoter", "RBS"]
    assert [row["name"] for row in grouped["Promoter"]] == ["P1", "P2"]
    assert [row["name"] for row in grouped["RBS"]] == ["R1"]
    assert all(row["canonical_type"] == "Promoter" for row in grouped["Promoter"])


def test_parts_map_for_host_filters_requested_types(monkeypatch):
    """Requested part types should be filtered from one host-scoped payload."""
    sample_rows = [
        {"name": "P1", "part_type": "promoter", "sequence": "ATGC"},
        {"name": "R1", "part_type": "ribosome binding site", "sequence": "AGGA"},
        {"name": "T1", "part_type": "Terminator", "sequence": "TTTT"},
        {"name": "P2", "part_type": "Promoter ", "sequence": "ATGG"},
    ]

    monkeypatch.setattr(parts_service, "get_parts_by_organism_all_cached", lambda organism: sample_rows)
    monkeypatch.setattr(parts_service, "host_to_organism", lambda host: "E.coli")

    grouped = parts_service.parts_map_for_host("E.coli BL21(DE3)", ["Promoter", "RBS"])

    assert list(grouped.keys()) == ["Promoter", "RBS"]
    assert [row["name"] for row in grouped["Promoter"]] == ["P1", "P2"]
    assert [row["name"] for row in grouped["RBS"]] == ["R1"]
    assert all(row["canonical_type"] == "Promoter" for row in grouped["Promoter"])
    assert grouped["Promoter"][0]["raw_type"] == "promoter"


def test_parts_map_for_host_groups_all_types_when_no_filter(monkeypatch):
    """Without filter types, rows should be grouped by normalized part_type."""
    sample_rows = [
        {"name": "P1", "part_type": "promoter"},
        {"name": "R1", "part_type": "RBS"},
        {"name": "P2", "part_type": "Promoter"},
        {"name": "C1", "part_type": "coding sequence"},
    ]

    monkeypatch.setattr(parts_service, "get_parts_by_organism_all_cached", lambda organism: sample_rows)
    monkeypatch.setattr(parts_service, "host_to_organism", lambda host: "Rice")

    grouped = parts_service.parts_map_for_host("Rice (O. sativa)")

    assert set(grouped.keys()) == {"Promoter", "RBS", "CDS"}
    assert [row["name"] for row in grouped["Promoter"]] == ["P1", "P2"]
    assert [row["name"] for row in grouped["RBS"]] == ["R1"]
    assert [row["name"] for row in grouped["CDS"]] == ["C1"]
    assert grouped["CDS"][0]["canonical_type"] == "CDS"
    assert grouped["CDS"][0]["raw_type"] == "coding sequence"


def test_get_all_parts_cached_normalizes_filter_type(monkeypatch):
    calls = []

    def _fake_get_all_parts(filter_type=None):
        calls.append(filter_type)
        return None

    monkeypatch.setattr(parts_service, "get_all_parts", _fake_get_all_parts)

    parts_service.get_all_parts_cached.__wrapped__(filter_type=" coding-sequence ")

    assert calls == ["CDS"]


def test_parts_for_host_normalizes_filter_type(monkeypatch):
    calls = []

    def _fake_get_parts_by_organism_all_cached(organism):
        calls.append(organism)
        return [
            {"name": "P1", "part_type": "promoter", "organism": organism, "sequence": "ATGC"},
            {"name": "R1", "part_type": "RBS", "organism": organism, "sequence": "AGGA"},
        ]

    monkeypatch.setattr(parts_service, "host_to_organism", lambda host: "E.coli")
    monkeypatch.setattr(parts_service, "get_parts_by_organism_all_cached", _fake_get_parts_by_organism_all_cached)

    records = parts_service.parts_for_host("E.coli BL21(DE3)", " promoter sequence ")

    assert calls == ["E.coli"]
    assert [row["name"] for row in records] == ["P1"]
    assert records[0]["canonical_type"] == "Promoter"
    assert records[0]["raw_type"] == "promoter"
