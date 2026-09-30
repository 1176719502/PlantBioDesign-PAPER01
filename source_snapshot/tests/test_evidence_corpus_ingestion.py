# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib

from services import evidence_corpus_ingestion as ingestion
from services import evidence_query_builder as builder
from services import evidence_ranker as ranker


def test_ingest_local_evidence_corpus_accepts_dict_lists_and_marks_duplicates() -> None:
    result = ingestion.ingest_local_evidence_corpus(
        [
            {
                "title": "Rice albumin plant expression evidence",
                "abstract": "Evidence metadata mentions rice albumin in a plant expression context.",
                "doi": "10.1000/rice.1",
                "year": "2025",
                "source": "Local citation list",
                "keywords": ["rice", "albumin", "plant"],
                "design_slots": ["target_product", "host"],
            },
            {
                "title": "Rice albumin plant expression evidence",
                "abstract": "Duplicate local citation note.",
                "doi": "https://doi.org/10.1000/RICE.1",
                "year": 2025,
                "source": "Local citation list",
            },
        ]
    )

    records = result["records"]

    assert result["summary"]["input_count"] == 2
    assert result["summary"]["record_count"] == 2
    assert result["summary"]["duplicate_group_count"] >= 1
    assert records[0]["doi"] == "10.1000/rice.1"
    assert records[0]["design_slots"] == ["target_gene_product", "host_chassis"]
    assert "duplicate_candidate" in records[0]["manual_review_reasons"]
    assert "duplicate_candidate" in records[1]["manual_review_reasons"]
    assert result["boundary_note"].startswith("Local evidence corpus ingestion")


def test_ingest_pasted_note_blocks_when_feasible() -> None:
    pasted = """
    Title: Nicotiana rice albumin source metadata
    DOI: 10.2000/example.42
    Year: 2024
    Source: Local literature notes
    Keywords: rice, albumin, plant
    Design slots: target gene/product; host
    Abstract: Metadata note links rice albumin and Nicotiana context for documentation review.

    PMID: 7654321
    Title: Incomplete citation note
    Source: Local pasted note
    """

    result = ingestion.ingest_local_evidence_corpus(pasted)
    records = result["records"]

    assert len(records) == 2
    assert records[0]["title"] == "Nicotiana rice albumin source metadata"
    assert records[0]["doi"] == "10.2000/example.42"
    assert records[0]["year"] == 2024
    assert records[0]["keywords"] == ["rice", "albumin", "plant"]
    assert records[0]["design_slots"] == ["target_gene_product", "host_chassis"]
    assert records[1]["pmid"] == "7654321"
    assert "missing_abstract" in records[1]["manual_review_reasons"]


def test_ingested_records_are_compatible_with_r64_ranker() -> None:
    records = ingestion.ingest_evidence_records(
        [
            {
                "title": "Rice albumin plant expression evidence metadata",
                "abstract": "Source metadata records rice albumin in Nicotiana benthamiana.",
                "doi": "10.3000/ranker.1",
                "year": 2025,
                "source": "Local evidence notes",
                "keywords": "rice, albumin, plant, expression",
                "design_slots": {"target_product": "rice albumin", "host": "Nicotiana benthamiana"},
            }
        ]
    )
    query_bundle = builder.build_evidence_query_bundle(
        {"target_product": "rice albumin", "host": "Nicotiana benthamiana"},
        extra_keywords=["plant", "expression"],
        exact_phrases=["rice albumin"],
    )

    ranked = ranker.rank_evidence_records(records, query_bundle)

    assert ranked["summary"]["candidate_count"] == 1
    assert ranked["candidates"][0]["record_id"] == "DOI:10.3000/ranker.1"
    assert ranked["candidates"][0]["covered_design_slots"] == [
        "host_chassis",
        "target_gene_product",
    ]
    assert "rice albumin" in ranked["candidates"][0]["matched_exact_phrases"]


def test_ingestion_stays_offline_and_ui_free(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("local evidence ingestion must stay offline and UI-free")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    result = ingestion.ingest_local_evidence_corpus("Title: Local source note")
    assert result["records"][0]["title"] == "Local source note"
    importlib.reload(ingestion)
