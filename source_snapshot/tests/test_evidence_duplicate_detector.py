# -*- coding: utf-8 -*-
from __future__ import annotations

from services.evidence_duplicate_detector import detect_evidence_duplicates, normalized_title_key


def test_duplicate_detector_groups_exact_doi_pmid_and_normalized_title() -> None:
    result = detect_evidence_duplicates(
        [
            {"record_id": "A", "doi": "10.1000/abc", "title": "Plant Expression Evidence"},
            {"record_id": "B", "doi": "https://doi.org/10.1000/ABC", "title": "Other title"},
            {"record_id": "C", "pmid": "PMID: 98765", "title": "Distinct"},
            {"record_id": "D", "pmid": "98765", "title": "Plant expression evidence!"},
            {"record_id": "E", "title": "The plant expression evidence"},
        ]
    )

    reasons = [group["reason"] for group in result["duplicate_groups"]]

    assert "exact_doi" in reasons
    assert "exact_pmid" in reasons
    assert "normalized_title" in reasons
    assert result["summary"]["record_count"] == 5
    assert result["summary"]["duplicate_group_count"] == 3
    assert result["summary"]["manual_review_required"] is True
    assert sorted(result["duplicate_record_ids"]) == ["A", "B", "C", "D", "E"]


def test_duplicate_detector_flags_high_similarity_title_pairs() -> None:
    result = detect_evidence_duplicates(
        [
            {"record_id": "A", "title": "Rice albumin plant expression metadata"},
            {"record_id": "B", "title": "Rice albumin plant expression meta data"},
            {"record_id": "C", "title": "Unrelated source note"},
        ],
        title_similarity_threshold=0.9,
    )

    similar_groups = [
        group for group in result["duplicate_groups"] if group["reason"] == "similar_title"
    ]

    assert len(similar_groups) == 1
    assert similar_groups[0]["record_ids"] == ["A", "B"]
    assert similar_groups[0]["similarity"] >= 0.9
    assert result["duplicate_record_ids"] == ["A", "B"]


def test_normalized_title_key_removes_punctuation_case_and_small_stopwords() -> None:
    assert normalized_title_key(" The Plant-Expression Evidence, in Rice! ") == (
        "plant expression evidence rice"
    )
