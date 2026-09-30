# -*- coding: utf-8 -*-
from __future__ import annotations

import builtins
import importlib

from services import evidence_record_normalizer as normalizer


def test_normalize_evidence_record_trims_identifiers_and_preserves_traceability() -> None:
    record = normalizer.normalize_evidence_record(
        {
            "id": " LOCAL-1 ",
            "DOI": " https://doi.org/10.1000/ABC.123. ",
            "PMID": " PMID: 123456 ",
            "paper_title": "  Rice albumin   expression metadata  ",
            "summary": "  Local abstract note for plant expression evidence. ",
            "publication_year": "2025",
            "journal": " Local citation list ",
            "authors": " A. Curator ; B. Reviewer ",
            "tags": " Plant, Expression, plant ",
            "design_context": {"host": "Nicotiana benthamiana", "target_product": "rice albumin"},
        }
    )

    assert record["record_id"] == "LOCAL-1"
    assert record["doi"] == "10.1000/abc.123"
    assert record["pmid"] == "123456"
    assert record["title"] == "Rice albumin expression metadata"
    assert record["year"] == 2025
    assert record["publication_year"] == 2025
    assert record["source_label"] == "Local citation list"
    assert record["authors"] == ["A. Curator", "B. Reviewer"]
    assert record["keywords"] == ["plant", "expression"]
    assert record["design_slots"] == ["host_chassis", "target_gene_product"]
    assert record["design_slot_values"] == {
        "host_chassis": "Nicotiana benthamiana",
        "target_gene_product": "rice albumin",
    }
    assert record["has_title"] is True
    assert record["has_abstract"] is True
    assert record["has_year"] is True
    assert record["has_source"] is True
    assert record["has_doi_or_pmid"] is True
    assert record["completeness_score"] == 1.0
    assert record["manual_review_required"] is True
    assert record["manual_review_reasons"] == ["multiple_source_identifiers"]
    assert record["raw_fields"]["paper_title"] == "  Rice albumin   expression metadata  "


def test_incomplete_record_reports_completeness_and_review_reasons() -> None:
    record = normalizer.normalize_evidence_record(
        {
            "title": "  Source note without citation fields ",
            "abstract": "",
        }
    )

    assert record["title"] == "Source note without citation fields"
    assert record["has_title"] is True
    assert record["has_abstract"] is False
    assert record["has_year"] is False
    assert record["has_source"] is False
    assert record["has_doi_or_pmid"] is False
    assert record["completeness_score"] == 0.2
    assert record["manual_review_required"] is True
    assert record["manual_review_reasons"] == [
        "missing_abstract",
        "missing_year",
        "missing_source",
        "missing_doi_or_pmid",
    ]
    assert record["source_type"] == "local evidence metadata"
    assert record["source_label"] == "Local evidence metadata"


def test_normalizer_stays_offline_and_ui_free(monkeypatch) -> None:
    original_import = builtins.__import__
    blocked_roots = {"streamlit", "requests", "httpx", "urllib"}

    def _block_import(name, globals=None, locals=None, fromlist=(), level=0):
        root = name.split(".", 1)[0]
        if root in blocked_roots:
            raise AssertionError("evidence normalizer must stay offline and UI-free")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", _block_import)

    record = normalizer.normalize_evidence_record({"title": "Local source note"})
    assert record["record_id"] == "local-evidence-001"
    importlib.reload(normalizer)
