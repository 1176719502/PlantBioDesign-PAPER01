import sys, os

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from components.assembly_modules.tab_cloning import (
    _build_fragment_validation_table,
    _build_gibson_fragment_boundary_table,
    _find_duplicate_overhang_warnings,
    _find_internal_site_warnings,
    _format_fragment_summary,
)


@pytest.fixture
def representative_fragments():
    return {
        "names": ["Promoter", "CDS", "Terminator"],
        "seqs": ["ATGC" * 10, "", "GCTA" * 8],
        "enzymes": ["BsaI", "BsmBI"],
    }


def test_format_fragment_summary_counts_and_order(representative_fragments):
    summary = _format_fragment_summary(
        representative_fragments["names"],
        representative_fragments["seqs"],
    )

    assert summary["filled_count"] == 2
    assert summary["empty_count"] == 1
    assert summary["total_bp"] == 72
    assert summary["order_text"] == "Promoter → Terminator"


def test_format_fragment_summary_handles_all_empty_inputs():
    summary = _format_fragment_summary(
        ["Promoter", "CDS"],
        ["", ""],
    )

    assert summary == {
        "filled_count": 0,
        "empty_count": 2,
        "total_bp": 0,
        "order_text": "No fragments entered",
        "length_text": "No valid fragment lengths",
    }


    warnings = _find_internal_site_warnings(
        ["AAAAGGTCTCTTTTCGTCTCAAAA", "ATGC" * 8],
        ["Fragment A", "Fragment B"],
        ["BsaI", "BsmBI"],
    )

    assert len(warnings) == 1
    assert "Fragment A" in warnings[0]
    assert "BsaI" in warnings[0]
    assert "BsmBI" in warnings[0]



def test_find_duplicate_overhang_warnings_detects_duplicate_and_reverse_complement():
    warnings = _find_duplicate_overhang_warnings(["AAAC", "GGTT", "AAAC", "GTTT"])

    assert any("AAAC" in warning and "reused" in warning for warning in warnings)
    assert any("AAAC/GTTT" in warning for warning in warnings)





def test_build_fragment_validation_table_handles_all_empty_rows():
    table = _build_fragment_validation_table(
        ["Promoter", "CDS"],
        ["", ""],
        ["BsaI"],
    )

    assert list(table["Fragment"]) == ["Promoter", "CDS"]
    assert list(table["Length (bp)"]) == [0, 0]
    assert list(table["GC (%)"]) == [0.0, 0.0]
    assert list(table["Internal Site Count"]) == [0, 0]
    assert list(table["Status"]) == ["Empty", "Empty"]



def test_build_gibson_fragment_boundary_table_skips_empty_fragments_and_preserves_coordinates():
    table = _build_gibson_fragment_boundary_table(
        ["Fragment A", "Fragment B", "Fragment C"],
        ["ATGCATGC", "", "GGTTAACC"],
        overlap=20,
    )

    assert list(table["Fragment"]) == ["Fragment A", "Fragment C"]
    assert list(table["Start"]) == [1, 9]
    assert list(table["End"]) == [8, 16]
    assert list(table["5' Boundary"]) == ["ATGCATGC", "GGTTAACC"]
    assert list(table["3' Boundary"]) == ["ATGCATGC", "GGTTAACC"]


