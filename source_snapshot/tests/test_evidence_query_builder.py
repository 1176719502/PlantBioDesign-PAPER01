# -*- coding: utf-8 -*-
from __future__ import annotations

from services import evidence_query_builder as builder


def test_query_builder_creates_slot_aware_manual_review_queries() -> None:
    bundle = builder.build_evidence_query_bundle(
        {
            "target gene/product": "rice albumin",
            "host": "Nicotiana benthamiana",
            "promoter": "CaMV 35S",
            "terminator": "NOS terminator",
            "selectable marker": "kanamycin marker",
            "vector/backbone": "binary vector",
            "expression context": "leaf transient expression",
        },
        extra_keywords=["plant", "expression"],
        exact_phrases=["rice albumin"],
    )

    assert bundle["slot_keys"] == [
        "expression_context",
        "host_chassis",
        "promoter",
        "selectable_marker",
        "target_gene_product",
        "terminator",
        "vector_backbone",
    ]
    assert len(bundle["queries"]) == 7
    assert bundle["manual_review_status"] == "manual_review_required"
    assert "manual documentation review" in bundle["boundary_note"]
    assert all(query["manual_review_status"] == "manual_review_required" for query in bundle["queries"])


def test_query_builder_normalizes_aliases_and_deduplicates_terms() -> None:
    bundle = builder.build_evidence_query_bundle(
        {
            "target_product": {"label": "Alpha enzyme alpha enzyme"},
            "backbone": ["binary vector", "binary vector"],
        },
        extra_keywords=["Plant", "plant", "Review"],
        exact_phrases=["Alpha enzyme", "alpha enzyme"],
    )

    target_query = next(query for query in bundle["queries"] if query["slot_key"] == "target_gene_product")
    backbone_query = next(query for query in bundle["queries"] if query["slot_key"] == "vector_backbone")

    assert target_query["phrase"] == "Alpha enzyme alpha enzyme"
    assert target_query["keywords"] == ["alpha", "enzyme", "plant", "review"]
    assert target_query["exact_phrases"] == ["Alpha enzyme alpha enzyme", "Alpha enzyme"]
    assert backbone_query["phrase"] == "binary vector binary vector"


def test_query_builder_empty_inputs_return_safe_empty_state() -> None:
    bundle = builder.build_evidence_query_bundle({})

    assert bundle["queries"] == []
    assert bundle["slot_keys"] == []
    assert bundle["empty_state"]
    assert bundle["manual_review_status"] == "manual_review_required"


def test_query_builder_skips_blank_slot_values() -> None:
    bundle = builder.build_evidence_query_bundle(
        {
            "promoter": "",
            "terminator": None,
            "host": "Rice",
        }
    )

    assert bundle["slot_keys"] == ["host_chassis"]
    assert bundle["slot_values"] == {"host_chassis": "Rice"}
