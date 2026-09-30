from __future__ import annotations

import ast
from pathlib import Path

import pytest

from services.dna_sequence_analysis import (
    SequenceTransformError,
    transform_dna_rna,
)
from services import sequence_service


def test_dna_to_rna_normalizes_without_mutating_input() -> None:
    raw = " aT\nGcN "
    assert transform_dna_rna(raw, "DNA-to-RNA") == "AUGCN"
    assert raw == " aT\nGcN "


def test_rna_to_dna_normalizes() -> None:
    assert transform_dna_rna(" aU\nGcN ", "RNA-to-DNA") == "ATGCN"


@pytest.mark.parametrize(
    ("raw", "mode", "character", "position"),
    [("ACU", "DNA-to-RNA", "U", 2), ("ACT", "RNA-to-DNA", "T", 2), ("ATUG", "DNA-to-RNA", "T", 1)],
)
def test_transform_rejects_forbidden_or_mixed_symbols_with_position(raw: str, mode: str, character: str, position: int) -> None:
    with pytest.raises(SequenceTransformError) as exc_info:
        transform_dna_rna(raw, mode)
    error = exc_info.value
    assert error.character == character
    assert error.position == position
    assert f"position {position}" in str(error)


def test_translation_uses_selected_strand_frame_ambiguity_and_stop_rule() -> None:
    assert sequence_service.translate_frame("ATGAAATAA", "+", 1) == "MK*"
    assert sequence_service.translate_frame("ATGAAATAA", "+", 1, "trim_terminal") == "MK"
    assert sequence_service.translate_frame("CAT", "-", 1) == "M"
    assert sequence_service.translate_frame("ATN", "+", 1) == "X"


def test_orf_adapter_exposes_self_consistent_existing_service_fields() -> None:
    records = sequence_service.normalized_orfs("ATGAAATAA", min_len=3).to_dict("records")
    assert records == [{
        "strand": "+",
        "frame": 1,
        "nucleotide_start": 1,
        "nucleotide_end": 9,
        "nucleotide_length": 9,
        "amino_acid_length": 2,
    }]


def test_sequence_toolbox_exposes_both_new_groups_without_project_imports() -> None:
    source = Path(__file__).parents[1].joinpath("views", "SequenceToolbox.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert "services.sequence_service" in imported
    assert "v1.sequence_tools.dna_rna_conversion" in source
    assert "v1.sequence_tools.translation_orf_analysis" in source
    assert "v1.sequence_tools.no_orf_matching_rules_detected" in source
    assert "ORFs from the existing service" not in source
    assert "Convert sequence" not in source
    assert "Translate selected frame" not in source
    assert "services.project" not in source
    assert "core.database" not in source
    assert "views.SequenceTools" not in source
