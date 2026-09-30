from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.expression_vector_sample_walkthrough_helper import (
    SAMPLE_PACKAGE_TITLE,
    SAMPLE_WALKTHROUGH_TITLE,
    build_single_gene_expression_vector_sample_walkthrough,
)


def test_sample_walkthrough_returns_read_only_preview_and_markdown() -> None:
    sample = build_single_gene_expression_vector_sample_walkthrough()
    preview = sample["preview"]

    assert sample["title"] == SAMPLE_WALKTHROUGH_TITLE
    assert sample["start_here"] == "Start in Expression Wizard with one target gene / CDS / protein record."
    assert preview["package_identity"]["package_title"] == SAMPLE_PACKAGE_TITLE
    assert preview["package_identity"]["package_status"] == "sample / needs review"
    assert len(preview["package_identity"]["md5"]) == 32
    assert "## Package Identity" in sample["markdown"]
    assert "## Source / Provenance Summary" in sample["markdown"]
    assert "## Gap / Manual Follow-up Review" in sample["markdown"]


def test_sample_walkthrough_makes_recorded_context_gaps_and_follow_up_visible() -> None:
    sample = build_single_gene_expression_vector_sample_walkthrough()
    preview = sample["preview"]
    combined = " ".join(
        [
            sample["start_here"],
            *sample["recorded_context"],
            *sample["source_provenance_gaps"],
            *sample["manual_follow_up"],
            sample["markdown"],
        ]
    )

    assert "single-gene / single-protein / single-enzyme" in combined
    assert "Host, promoter, insert, and vector/backbone labels" in combined
    assert "Target sequence source/provenance is not recorded." in combined
    assert "Manual follow-up" in combined
    assert any(row["review_status"] == "needs source" for row in preview["gap_follow_up_summary"])
    assert any(row["section"] == "Sample walkthrough source/provenance gap" for row in preview["gap_follow_up_summary"])
    assert preview["sequence_basic_checks"][0]["review_status"] == "not assessed"


def test_sample_walkthrough_stays_inside_documentation_only_boundaries() -> None:
    sample = build_single_gene_expression_vector_sample_walkthrough()
    combined = str(sample).casefold()

    assert "read-only" in combined
    assert "not saved, exported, imported" in combined
    assert "does not choose a host" in combined
    assert "does not choose a backbone" in combined
    assert "no final vector sequence is assembled" in combined
    forbidden = [
        "recommended promoter",
        "recommended host",
        "recommended vector",
        "best promoter",
        "best host",
        "best vector",
        "build-ready",
        "ready-to-clone",
        "validated construct",
        "cloning protocol",
        "wet-lab protocol",
        "yield prediction",
        "experimentally validated",
        "experiment-ready",
        "production-ready",
        "final vector generated",
        "generated final vector",
        "codon-optimized sequence",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
