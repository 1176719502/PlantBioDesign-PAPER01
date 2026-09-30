from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Any

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.codon_candidate_draft import (  # noqa: E402
    CODON_CANDIDATE_DRAFT_SCHEMA_VERSION,
    CODON_CANDIDATE_DRAFT_STATUS,
    CODON_CANDIDATE_REJECTED_STATUS,
    build_codon_candidate_draft,
)
from core.codon_optimizer import CODON_TO_AA  # noqa: E402
from core.codon_draft_metrics import build_codon_draft_metrics  # noqa: E402


SERVICE_SOURCE = Path(ROOT) / "core" / "codon_candidate_draft.py"
STEP2_SOURCE = Path(ROOT) / "views" / "wizard_steps" / "step2_host_elements.py"


def _translate(sequence: str) -> str:
    return "".join(CODON_TO_AA[sequence[index:index + 3]] for index in range(0, len(sequence), 3))


def _flatten_values(payload: Any) -> list[str]:
    if isinstance(payload, dict):
        values: list[str] = []
        for key, value in payload.items():
            values.append(str(key))
            values.extend(_flatten_values(value))
        return values
    if isinstance(payload, list):
        values = []
        for value in payload:
            values.extend(_flatten_values(value))
        return values
    return [str(payload)]


def test_valid_cds_produces_deterministic_synonymous_candidate() -> None:
    first = build_codon_candidate_draft("ATGGCTCTATAA", "E.coli")
    second = build_codon_candidate_draft("ATGGCTCTATAA", "E.coli")

    assert first == second
    assert first["schema_version"] == CODON_CANDIDATE_DRAFT_SCHEMA_VERSION
    assert first["status"] == CODON_CANDIDATE_DRAFT_STATUS
    assert first["candidate_label"] == "computational synonymous recoding candidate"
    assert first["candidate_kind"] == "codon candidate draft"
    assert first["input_sequence"] == "ATGGCTCTATAA"
    assert first["candidate_sequence"] == "ATGGCGCTGTAA"
    assert first["candidate_sequence"].startswith("ATG")
    assert first["candidate_sequence"].endswith("TAA")
    assert first["changed"] is True


def test_translation_is_preserved_and_metrics_are_reported() -> None:
    result = build_codon_candidate_draft("ATGGCTCTATAA", "E.coli")
    metrics = result["metrics"]

    assert _translate(result["input_sequence"]) == _translate(result["candidate_sequence"])
    assert result["translation"]["preserved"] is True
    assert metrics["translation_preserved"] is True
    assert metrics["original_length"] == 12
    assert metrics["candidate_length"] == 12
    assert metrics["original_gc_percent"] == 33.33
    assert metrics["candidate_gc_percent"] == 50.0
    assert metrics["original_rare_codon_count"] == 1
    assert metrics["candidate_rare_codon_count"] == 0
    assert metrics["original_rare_codon_clusters"] == 0
    assert metrics["candidate_rare_codon_clusters"] == 0


def test_first_codon_is_preserved_as_start_boundary() -> None:
    result = build_codon_candidate_draft("TTAGCTTAA", "E.coli")

    assert result["status"] == CODON_CANDIDATE_DRAFT_STATUS
    assert result["input_sequence"].startswith("TTA")
    assert result["candidate_sequence"].startswith("TTA")
    assert _translate(result["input_sequence"]) == _translate(result["candidate_sequence"])


def test_invalid_bases_do_not_silently_generate_candidate() -> None:
    result = build_codon_candidate_draft("ATGBCTTAA", "E.coli")

    assert result["status"] == CODON_CANDIDATE_REJECTED_STATUS
    assert result["candidate_sequence"] == ""
    assert result["errors"] == ["CDS contains invalid or ambiguous bases."]
    assert "invalid_or_ambiguous_bases_detected" in result["validation"]["review_flags"]
    assert result["validation"]["invalid_or_ambiguous_bases"] == ["B"]
    assert result["metrics"]["translation_preserved"] is False


def test_ambiguous_bases_are_flagged_without_candidate_output() -> None:
    result = build_codon_candidate_draft("ATGNNTTAA", "E.coli")

    assert result["status"] == CODON_CANDIDATE_REJECTED_STATUS
    assert result["candidate_sequence"] == ""
    assert "invalid_or_ambiguous_bases_detected" in result["validation"]["review_flags"]
    assert result["validation"]["invalid_or_ambiguous_bases"] == ["N"]


def test_internal_stop_codons_are_flagged_without_candidate_output() -> None:
    result = build_codon_candidate_draft("ATGTAAGCTTAA", "E.coli")

    assert result["status"] == CODON_CANDIDATE_REJECTED_STATUS
    assert result["candidate_sequence"] == ""
    assert result["errors"] == ["CDS contains internal stop codons."]
    assert result["validation"]["internal_stop_codon_positions"] == [2]
    assert "internal_stop_codons_detected" in result["validation"]["review_flags"]


def test_cds_length_not_multiple_of_three_is_flagged() -> None:
    result = build_codon_candidate_draft("ATGGCTTA", "E.coli")

    assert result["status"] == CODON_CANDIDATE_REJECTED_STATUS
    assert result["candidate_sequence"] == ""
    assert result["errors"] == ["CDS length is not a multiple of 3."]
    assert result["validation"]["length_multiple_of_3"] is False
    assert "length_not_multiple_of_3" in result["validation"]["review_flags"]


def test_existing_codon_usage_preview_metrics_remain_available() -> None:
    metrics = build_codon_draft_metrics("ATGGCTCTATAA", "E.coli")

    assert metrics["metrics_only_status"] == "review_metrics_only"
    assert metrics["codon_usage_review"]["rare_codon_count"] == 1
    assert metrics["codon_usage_review"]["rare_codon_cluster_count"] == 0
    assert "candidate_sequence" not in metrics


def test_candidate_output_wording_avoids_claim_labels() -> None:
    result = build_codon_candidate_draft("ATGGCTCTATAA", "E.coli")
    combined = "\n".join(_flatten_values({
        "status": result["status"],
        "candidate_kind": result["candidate_kind"],
        "candidate_label": result["candidate_label"],
        "boundary": result["boundary"],
        "routing": result["routing"],
    })).lower()

    forbidden = [
        "valid" + "ated",
        "recommended",
        "optim" + "ized",
        "build-ready",
        "experiment" + "-ready",
        "yield " + "prediction",
        "wet-lab " + "ready",
    ]

    assert [phrase for phrase in forbidden if phrase in combined] == []
    assert "manual documentation review" in combined
    assert "computational synonymous recoding candidate" in combined


def test_candidate_is_not_routed_to_step4_or_downstream_assembly() -> None:
    result = build_codon_candidate_draft("ATGGCTCTATAA", "E.coli")

    assert result["routing"] == {
        "expression_wizard_step4": "not_routed",
        "downstream_expression_frame_assembly": "not_performed",
        "automatic_handoff": False,
    }

    tree = ast.parse(SERVICE_SOURCE.read_text(encoding="utf-8"), filename=str(SERVICE_SOURCE))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_modules.update(
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )

    forbidden_import_prefixes = (
        "streamlit",
        "core.session_keys",
        "views.wizard_steps",
        "services.primer",
        "services.assembly",
        "core.assembly",
    )
    assert [
        module
        for module in imported_modules
        if module.startswith(forbidden_import_prefixes)
    ] == []


def test_step2_source_is_not_modified_for_candidate_service() -> None:
    source = STEP2_SOURCE.read_text(encoding="utf-8-sig")

    assert "build_codon_candidate_draft" not in source
    assert "codon_candidate_draft" not in source
