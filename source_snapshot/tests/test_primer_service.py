from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.primer_service import design_and_evaluate_primers, design_outer_primers_for_cassette
import services.primer_service as primer_service
from core.primer_utils import Primer3BackendStatus, design_outer_primers


def _balanced_cassette() -> str:
    promoter = "TAATACGACTCACTATAGGGAGA"
    rbs = "AAAGAGGAGAAA"
    spacer = "AACCGGT"
    cds = "ATG" + "GCCGAACTGATC" * 36 + "TAA"
    terminator = "TGCCTGGCGGCAGTAGCGCGGTGGTCCCACCTGACCCCAT"
    return promoter + rbs + spacer + cds + terminator


def _result_signature(result_payload: dict) -> tuple[str, str]:
    primers = result_payload.get("primers") or []
    return primers[0].get("sequence", ""), primers[1].get("sequence", "")


def _assert_full_cassette_candidate(candidate: dict, sequence: str) -> None:
    reverse_sequence = candidate["primers"][1]["sequence"]
    assert candidate["product_size"] == len(sequence)
    assert candidate["product_start"] == 0
    assert candidate["product_end"] == len(sequence)
    assert candidate["forward_start"] == 0
    assert candidate["reverse_start"] == len(sequence) - len(reverse_sequence)


def test_design_outer_primers_for_cassette_returns_full_length_product():
    sequence = _balanced_cassette()

    result = design_outer_primers_for_cassette(sequence, num_designs=3)

    assert result["success"] is True
    assert result["results"]

    for candidate in result["results"]:
        _assert_full_cassette_candidate(candidate, sequence)
        assert candidate["quality_grade"] in {"Recommended", "Usable with Risk", "Not Recommended"}
        assert any(primer["role"] == "forward" and primer["sequence"] for primer in candidate["primers"])
        assert any(primer["role"] == "reverse" and primer["sequence"] for primer in candidate["primers"])


def test_design_outer_primers_for_cassette_rejects_short_templates():
    result = design_outer_primers_for_cassette("ATGCATGCATGC")

    assert result["success"] is False
    assert "Template too short" in result["error"]
    assert result["results"] == []


def test_generic_primer_design_remains_generic_without_full_length_assertion():
    sequence = ("ATGGCCATGGCCATTA" * 10)[:160]

    result = design_and_evaluate_primers(sequence, num_designs=2)

    assert result["success"] is True
    assert result["results"]
    assert "design_scope" not in result["results"][0]


def test_design_and_evaluate_primers_returns_ranked_candidates():
    sequence = ("ATGGCCATGGCCATTA" * 10)[:160]

    result = design_and_evaluate_primers(sequence, num_designs=4)

    assert result["success"] is True
    assert len(result["results"]) >= 2

    ranking_keys = [
        (
            -item["quality_score"],
            item["max_tm_deviation"],
            item["tm_gap"],
            item["gc_balance_gap"],
            item["issue_count"],
            abs(item["target_tm"] - 60.0),
        )
        for item in result["results"]
    ]
    assert ranking_keys == sorted(ranking_keys)


def test_outer_primer_results_keep_ranking_invariant():
    sequence = _balanced_cassette()

    result = design_outer_primers_for_cassette(sequence, target_tm=60.0, num_designs=5)

    assert result["success"] is True
    assert result["results"]
    ranking_keys = [
        (
            -item["quality_score"],
            item["max_tm_deviation"],
            item["tm_gap"],
            item["gc_balance_gap"],
            item["issue_count"],
            abs(item["target_tm"] - 60.0),
        )
        for item in result["results"]
    ]
    assert ranking_keys == sorted(ranking_keys)


def test_design_and_evaluate_primers_returns_structured_quality_fields():
    sequence = ("ATGGCCATGGCCATTA" * 8)[:128]

    result = design_and_evaluate_primers(sequence)

    assert result["success"] is True
    assert result["results"]

    pair = result["results"][0]
    assert pair["quality_grade"] in {"Recommended", "Usable with Risk", "Not Recommended"}
    assert pair["hetero_dimer_risk"] in {"Low", "Moderate", "High", "Unknown"}
    assert isinstance(pair["quality_score"], int)
    assert len(pair["primers"]) == 2

    for primer in pair["primers"]:
        assert primer["sequence"]
        assert isinstance(primer["tm"], float)
        assert isinstance(primer["tm_deviation"], float)
        assert isinstance(primer["gc_content"], float)
        assert isinstance(primer["gc_in_range"], bool)
        assert isinstance(primer["length"], int)
        assert primer["hairpin_risk"] in {"Low", "Moderate", "High", "Unknown"}
        assert primer["self_dimer_risk"] in {"Low", "Moderate", "High", "Unknown"}


def test_design_and_evaluate_primers_rejects_short_templates():
    result = design_and_evaluate_primers("ATGCATGCATGC")

    assert result["success"] is False
    assert "Template too short" in result["error"]
    assert result["results"] == []


def test_design_and_evaluate_primers_handles_full_expression_cassette():
    promoter = "TAATACGACTCACTATA"
    rbs = "AAAGAGGAGAAA"
    spacer = "AAAAAAA"
    cds = "ATG" + "GCC" * 40 + "TAA"
    terminator = "TGCCTGGCGGCAGTAGCGCGGTGGTCCCACCTGACCCCAT"
    sequence = promoter + rbs + spacer + cds + terminator

    result = design_and_evaluate_primers(sequence, num_designs=3)

    assert result["success"] is True
    assert result["results"]

    top_result = result["results"][0]
    assert top_result["quality_grade"] in {"Recommended", "Usable with Risk", "Not Recommended"}
    assert len(top_result["primers"]) == 2
    assert any(primer["role"] == "forward" and primer["sequence"] for primer in top_result["primers"])
    assert any(primer["role"] == "reverse" and primer["sequence"] for primer in top_result["primers"])


def test_outer_primer_design_returns_unique_candidate_signatures_when_available():
    sequence = _balanced_cassette()

    result = design_outer_primers_for_cassette(sequence, num_designs=5)

    assert result["success"] is True
    assert result["results"]
    signatures = [_result_signature(item) for item in result["results"]]
    assert len(signatures) == len(set(signatures))
    assert len(signatures) >= 2


def test_outer_primer_design_does_not_force_high_risk_repetitive_cassette_to_recommended():
    promoter = "ATATATATATATATATATAT"
    cds = "ATG" + "GCGTACGCGTAC" * 24 + "TAA"
    terminator = "ATATATATATATATATATAT"
    sequence = promoter + cds + terminator

    result = design_outer_primers_for_cassette(sequence, num_designs=5)

    assert result["success"] is True
    assert result["results"]
    assert any(
        item["quality_grade"] in {"Usable with Risk", "Not Recommended"}
        for item in result["results"]
    )
    if all(item["quality_score"] < 85 for item in result["results"]):
        assert all(item["quality_grade"] != "Recommended" for item in result["results"])


def test_manual_outer_fallback_generates_multiple_ranked_candidates_for_short_cassette():
    sequence = ("ATGGCCGAACTGATC" * 4)[:64]

    result = design_outer_primers_for_cassette(sequence, num_designs=5)

    assert result["success"] is True
    assert len(result["results"]) >= 3
    for candidate in result["results"]:
        _assert_full_cassette_candidate(candidate, sequence)
        assert candidate["rank_metrics"]
        assert candidate["max_tm_deviation"] >= 0
        assert candidate["gc_balance_gap"] >= 0
    assert len({_result_signature(item) for item in result["results"]}) == len(result["results"])


def test_manual_outer_fallback_keeps_full_cassette_coordinates():
    sequence = ("ATGGCCGAACTGATC" * 4)[:64]

    pair = design_outer_primers(sequence, target_tm=60.0, min_len=16, max_len=22)

    assert "error" not in pair
    assert pair["product_size"] == len(sequence)
    assert pair["product_start"] == 0
    assert pair["product_end"] == len(sequence)
    assert pair["forward_start"] == 0
    assert pair["reverse_start"] == len(sequence) - len(pair["reverse"]["seq"])
    assert sequence.startswith(pair["forward"]["seq"])


def test_low_high_gc_and_tm_gap_are_explainable_reasons():
    sequence = "ATG" + "A" * 34 + "GCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGCGC" + "TAA"

    result = design_outer_primers_for_cassette(sequence, target_tm=60.0, num_designs=5)

    assert result["success"] is True
    assert result["results"]
    joined_reasons = " | ".join(
        reason
        for candidate in result["results"]
        for reason in candidate.get("quality_reasons", []) + candidate.get("pair_warnings", [])
    )
    assert "GC" in joined_reasons
    assert any(
        term in joined_reasons
        for term in ("Tm gap", "Tm deviation", "Tm deviates", "Forward/reverse Tm gap")
    )


def test_quality_thresholds_do_not_relabel_not_recommended_as_recommended():
    sequence = "ATG" + "A" * 46 + "TAA"

    result = design_outer_primers_for_cassette(sequence, target_tm=60.0, num_designs=5)

    assert result["success"] is True
    assert result["results"]
    for candidate in result["results"]:
        if candidate["quality_score"] < 60:
            assert candidate["quality_grade"] == "Not Recommended"
        if candidate["quality_grade"] == "Recommended":
            assert candidate["quality_score"] >= 85


def test_short_cassette_keeps_safety_result_without_crashing():
    sequence = "ATG" + "A" * 37 + "TAA"

    result = design_outer_primers_for_cassette(sequence, num_designs=5)

    assert result["success"] is True
    assert result["results"]
    assert all(
        candidate["quality_grade"] in {"Recommended", "Usable with Risk", "Not Recommended"}
        for candidate in result["results"]
    )
    assert any(candidate["quality_reasons"] for candidate in result["results"])


def test_design_primers_if_available_returns_unavailable_without_backend_probe(monkeypatch):
    calls = {"design": 0}

    monkeypatch.setattr(
        primer_service,
        "get_primer3_backend_status",
        lambda *, probe=False: Primer3BackendStatus(
            False,
            primer_service.PRIMER_BACKEND_UNAVAILABLE_MESSAGE,
        ),
    )

    def _unexpected_design(*args, **kwargs):
        calls["design"] += 1
        raise AssertionError("primer design should not run when backend is unavailable")

    monkeypatch.setattr(primer_service, "design_outer_primers_for_cassette", _unexpected_design)

    result = primer_service.design_primers_if_available("ATG" + "GCC" * 20 + "TAA")

    assert result["success"] is False
    assert result["unavailable"] is True
    assert result["results"] == []
    assert "Primer design engine is unavailable" in result["error"]
    assert calls["design"] == 0
