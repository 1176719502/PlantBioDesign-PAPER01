# -*- coding: utf-8 -*-
from __future__ import annotations

from services import evidence_query_builder as builder
from services import evidence_ranker as ranker
from services.evidence_retrieval_provider import FakeEvidenceRetrievalProvider


def _term(*parts: str) -> str:
    return "".join(parts)


def _bundle() -> dict[str, object]:
    return builder.build_evidence_query_bundle(
        {
            "target gene/product": "rice albumin",
            "host/chassis": "Nicotiana benthamiana",
            "promoter": "CaMV 35S",
        },
        extra_keywords=["plant", "expression"],
        exact_phrases=["rice albumin"],
    )


def _complete_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "record_id": "complete",
        "title": "Rice albumin plant expression evidence metadata",
        "abstract": "Source metadata records rice albumin in Nicotiana benthamiana with CaMV 35S.",
        "source_type": "literature metadata",
        "source_identifier": "PMID-LOCAL-001",
        "source_label": "Local citation note",
        "source_url": "https://example.invalid/record/1",
        "provenance_note": "Recorded from local review fixture.",
        "publication_year": 2025,
        "keywords": ["rice", "albumin", "plant", "expression"],
        "design_slots": ["target_gene_product", "host_chassis", "promoter"],
        "manual_review_flags": ["manual_review_required"],
    }
    record.update(overrides)
    return record


def test_ranking_order_uses_keywords_slots_source_recency_and_phrase_match() -> None:
    result = ranker.rank_evidence_records(
        [
            _complete_record(record_id="weak", title="Plant expression metadata", abstract="plant expression"),
            _complete_record(record_id="strong"),
        ],
        _bundle(),
    )

    candidates = result["candidates"]

    assert [candidate["record_id"] for candidate in candidates] == ["strong", "weak"]
    assert candidates[0]["retrieval_review_score"] > candidates[1]["retrieval_review_score"]
    assert candidates[0]["matched_exact_phrases"] == [
        "Nicotiana benthamiana",
        "rice albumin",
        "CaMV 35S",
    ]
    assert candidates[0]["covered_design_slots"] == [
        "host_chassis",
        "promoter",
        "target_gene_product",
    ]
    assert candidates[0]["manual_review_status"] == "manual_review_required"


def test_missing_metadata_is_reported_without_blocking_review_score() -> None:
    result = ranker.rank_evidence_records(
        [
            {
                "record_id": "partial",
                "title": "Rice albumin source note",
                "abstract": "rice albumin plant expression",
                "keywords": ["rice", "albumin"],
                "design_slots": ["target_gene_product"],
            }
        ],
        _bundle(),
    )

    candidate = result["candidates"][0]

    assert candidate["record_id"] == "partial"
    assert candidate["missing_metadata"] == [
        "source_type",
        "source_identifier",
        "source_label",
        "source_url",
        "provenance_note",
    ]
    assert result["summary"]["missing_metadata_count"] == 1
    assert candidate["manual_review_status"] == "manual_review_required"


def test_tie_behavior_preserves_input_order_deterministically() -> None:
    result = ranker.rank_evidence_records(
        [
            _complete_record(record_id="first", publication_year=2024),
            _complete_record(record_id="second", publication_year=2024),
        ],
        _bundle(),
    )

    assert [candidate["record_id"] for candidate in result["candidates"]] == ["first", "second"]
    assert [candidate["rank"] for candidate in result["candidates"]] == [1, 2]


def test_unsafe_claim_like_flags_are_demoted_and_kept_for_manual_review() -> None:
    result = ranker.rank_evidence_records(
        [
            _complete_record(record_id="safe-review", publication_year=2020),
            _complete_record(
                record_id="unsafe-claim",
                title="Rice albumin " + _term("valid", "ated") + " source claim",
                manual_review_flags=[_term("wet-lab ", "ready")],
                publication_year=2025,
            ),
        ],
        _bundle(),
    )

    candidates = result["candidates"]
    demoted = next(candidate for candidate in candidates if candidate["record_id"] == "unsafe-claim")

    assert demoted["claim_demoted"] is True
    assert demoted["score_breakdown"]["manual_review_safety"] < 0
    assert result["summary"]["claim_demoted_count"] == 1
    assert candidates[0]["record_id"] == "safe-review"


def test_empty_inputs_return_manual_review_empty_state() -> None:
    result = ranker.rank_evidence_records([], _bundle())

    assert result["candidates"] == []
    assert result["summary"]["candidate_count"] == 0
    assert result["manual_review_status"] == "manual_review_required"
    assert result["empty_state"]


def test_retrieve_and_rank_uses_provider_interface_without_network() -> None:
    provider = FakeEvidenceRetrievalProvider(
        [
            _complete_record(record_id="provider-strong"),
            {
                "record_id": "provider-unrelated",
                "title": "Unrelated metadata",
                "keywords": ["maize"],
            },
        ]
    )

    result = ranker.retrieve_and_rank_evidence(provider, _bundle())

    assert [candidate["record_id"] for candidate in result["candidates"]] == ["provider-strong"]
    assert result["summary"]["manual_review_required"] is True
