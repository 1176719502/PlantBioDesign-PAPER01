import os
import sys
from copy import deepcopy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.legacy_snapshot_adapter import (  # noqa: E402
    FORBIDDEN_READINESS_TERMS,
    HISTORICAL_VALIDATION_WARNING,
    PRIMER_SNAPSHOT_WARNING,
    SEQUENCE_ONLY_FALLBACK_WARNING,
    normalize_legacy_snapshot,
)


def _assert_no_forbidden_terms(value):
    combined = str(value)
    for forbidden_term in FORBIDDEN_READINESS_TERMS:
        assert forbidden_term not in combined


def test_full_design_data_snapshot_normalize():
    record = {
        "load_key": "legacy-001",
        "name": "Rice GFP snapshot",
        "source": "project_history",
        "design_data": {
            "sequence": "ATGGCTTAA",
            "host": "Rice",
            "gene_name": "GFP",
            "created_at": "2026-05-01T10:00:00",
        },
    }

    normalized = normalize_legacy_snapshot(record)

    assert normalized["legacy_snapshot_id"] == "legacy-001"
    assert normalized["display_name"] == "Rice GFP snapshot"
    assert normalized["sequence"] == "ATGGCTTAA"
    assert normalized["host"] == "Rice"
    assert normalized["gene_name"] == "GFP"
    assert normalized["source"] == "project_history"
    assert normalized["snapshot_created_at"] == "2026-05-01T10:00:00"
    assert normalized["readiness_authority"] is False
    assert normalized["revision_candidate"] is False


def test_validation_results_marked_historical():
    record = {
        "name": "Historical validation snapshot",
        "design_data": {
            "sequence": "ATGAAATAA",
            "validation_results": [
                {"severity": "warning", "message": "Legacy warning"},
                {"severity": "error", "message": "Legacy error"},
            ],
        },
    }

    normalized = normalize_legacy_snapshot(record)

    assert normalized["has_historical_validation"] is True
    assert normalized["historical_validation_issue_count"] == 2
    assert HISTORICAL_VALIDATION_WARNING in normalized["load_warnings"]
    assert normalized["readiness_authority"] is False
    _assert_no_forbidden_terms(normalized)


def test_primers_marked_snapshot():
    record = {
        "name": "Primer snapshot",
        "design_data": {"sequence": "ATGAAATAA"},
        "primers": [
            {"name": "forward", "sequence": "ATGAAA"},
            {"name": "reverse", "sequence": "TTATTTCAT"},
        ],
    }

    normalized = normalize_legacy_snapshot(record)

    assert normalized["has_primer_snapshot"] is True
    assert normalized["primer_snapshot_count"] == 2
    assert PRIMER_SNAPSHOT_WARNING in normalized["load_warnings"]
    assert normalized["readiness_authority"] is False
    _assert_no_forbidden_terms(normalized)


def test_sequence_only_fallback_warning():
    record = {
        "name": "Sequence row",
        "sequence": "ATGCGTTAA",
    }

    normalized = normalize_legacy_snapshot(record)

    assert normalized["display_name"] == "Sequence row"
    assert normalized["sequence"] == "ATGCGTTAA"
    assert normalized["source"] == "sequence-only"
    assert SEQUENCE_ONLY_FALLBACK_WARNING in normalized["load_warnings"]
    assert normalized["readiness_authority"] is False


def test_sequence_only_preserves_existing_source():
    record = {
        "name": "Imported sequence",
        "source": "sequences",
        "sequence": "ATGCGTTAA",
    }

    normalized = normalize_legacy_snapshot(record)

    assert normalized["source"] == "sequences"
    assert SEQUENCE_ONLY_FALLBACK_WARNING in normalized["load_warnings"]
    assert normalized["readiness_authority"] is False


def test_missing_fields_handled_safely():
    normalized = normalize_legacy_snapshot({})

    assert normalized["legacy_snapshot_id"] == ""
    assert normalized["display_name"] == "Legacy Snapshot"
    assert normalized["sequence"] == ""
    assert normalized["host"] == ""
    assert normalized["gene_name"] == ""
    assert normalized["snapshot_created_at"] == ""
    assert normalized["has_historical_validation"] is False
    assert normalized["has_primer_snapshot"] is False
    assert normalized["historical_validation_issue_count"] == 0
    assert normalized["primer_snapshot_count"] == 0
    assert normalized["readiness_authority"] is False


def test_input_record_is_not_mutated():
    record = {
        "name": "Immutable input",
        "design_data": {
            "sequence": "ATGAAATAA",
            "validation_results": [{"severity": "warning"}],
        },
        "primers": [{"name": "forward"}],
    }
    original = deepcopy(record)

    normalize_legacy_snapshot(record)

    assert record == original


def test_no_forbidden_readiness_or_certification_terms_emitted():
    record = {
        "name": "Unsafe legacy wording stays out of adapter wording",
        "design_data": {
            "sequence": "ATGAAATAA",
            "validation_results": [{"message": "Historical issue"}],
        },
        "primers": [{"name": "forward"}],
    }

    normalized = normalize_legacy_snapshot(record)

    _assert_no_forbidden_terms(normalized)


def test_readiness_authority_always_false_for_common_inputs():
    records = [
        {},
        {"sequence": "ATGTAA"},
        {"design_data": {"sequence": "ATGTAA"}},
        {"validation_results": [{"severity": "info"}]},
        {"primers": [{"name": "forward"}]},
    ]

    for record in records:
        normalized = normalize_legacy_snapshot(record)
        assert normalized["readiness_authority"] is False
