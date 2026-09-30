import os
import sys
from copy import deepcopy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.legacy_snapshot_adapter import FORBIDDEN_READINESS_TERMS  # noqa: E402
from services.legacy_snapshot_inventory import (  # noqa: E402
    DUPLICATE_DISPLAY_NAME_WARNING,
    HISTORICAL_VALIDATION_WITHOUT_CONTEXT_WARNING,
    MISSING_GENE_WARNING,
    MISSING_HOST_WARNING,
    MISSING_SEQUENCE_WARNING,
    MISSING_TIMESTAMP_WARNING,
    PRIMER_PROVENANCE_WARNING,
    build_legacy_snapshot_inventory,
)


def _assert_no_forbidden_terms(value):
    combined = str(value)
    for forbidden_term in FORBIDDEN_READINESS_TERMS:
        assert forbidden_term not in combined


def test_empty_records_summary():
    summary = build_legacy_snapshot_inventory([])

    assert summary == {
        "total_records": 0,
        "expression_design_count": 0,
        "sequence_only_count": 0,
        "missing_sequence_count": 0,
        "historical_validation_count": 0,
        "primer_snapshot_count": 0,
        "missing_metadata_count": 0,
        "high_risk_record_count": 0,
        "warnings_by_type": {},
        "example_records": [],
    }
    _assert_no_forbidden_terms(summary)


def test_mixed_full_design_and_sequence_only_records():
    records = [
        {
            "id": "design-1",
            "name": "Expression Design",
            "source": "project_history",
            "design_data": {
                "sequence": "ATGAAATAA",
                "host": "Rice",
                "gene_name": "GFP",
                "created_at": "2026-05-01T10:00:00",
                "metadata": {"description": "Expression design snapshot"},
            },
        },
        {
            "id": "sequence-1",
            "name": "Sequence Only",
            "sequence": "ATGCCCTAA",
            "source": "sequences",
        },
    ]

    summary = build_legacy_snapshot_inventory(records)

    assert summary["total_records"] == 2
    assert summary["expression_design_count"] == 1
    assert summary["sequence_only_count"] == 1
    assert summary["missing_sequence_count"] == 0
    assert summary["high_risk_record_count"] == 0
    _assert_no_forbidden_terms(summary)


def test_historical_validation_count():
    records = [
        {
            "name": "Historical Validation",
            "design_data": {
                "sequence": "ATGAAATAA",
                "host": "Maize",
                "gene_name": "ABC1",
                "created_at": "2026-05-02T10:00:00",
                "validation_results": [{"severity": "warning"}],
            },
        }
    ]

    summary = build_legacy_snapshot_inventory(records)

    assert summary["historical_validation_count"] == 1
    assert summary["high_risk_record_count"] == 0
    assert HISTORICAL_VALIDATION_WITHOUT_CONTEXT_WARNING not in summary["warnings_by_type"]
    _assert_no_forbidden_terms(summary)


def test_primer_snapshot_count_and_missing_provenance_warning():
    records = [
        {
            "name": "Primer Snapshot",
            "design_data": {
                "sequence": "ATGAAATAA",
                "host": "E. coli",
                "gene_name": "lacZ",
                "created_at": "2026-05-03T10:00:00",
            },
            "primers": [{"name": "forward"}, {"name": "reverse"}],
        }
    ]

    summary = build_legacy_snapshot_inventory(records)

    assert summary["primer_snapshot_count"] == 1
    assert summary["warnings_by_type"][PRIMER_PROVENANCE_WARNING] == 1
    assert summary["high_risk_record_count"] == 0
    _assert_no_forbidden_terms(summary)


def test_missing_sequence_is_high_risk():
    records = [
        {
            "name": "Missing Sequence",
            "design_data": {
                "host": "Rice",
                "gene_name": "GFP",
                "created_at": "2026-05-04T10:00:00",
            },
        }
    ]

    summary = build_legacy_snapshot_inventory(records)

    assert summary["missing_sequence_count"] == 1
    assert summary["high_risk_record_count"] == 1
    assert summary["warnings_by_type"][MISSING_SEQUENCE_WARNING] == 1
    _assert_no_forbidden_terms(summary)


def test_missing_host_gene_timestamp_metadata_count():
    records = [
        {
            "name": "Missing Metadata",
            "design_data": {
                "sequence": "ATGAAATAA",
            },
        }
    ]

    summary = build_legacy_snapshot_inventory(records)

    assert summary["missing_metadata_count"] == 1
    assert summary["warnings_by_type"][MISSING_HOST_WARNING] == 1
    assert summary["warnings_by_type"][MISSING_GENE_WARNING] == 1
    assert summary["warnings_by_type"][MISSING_TIMESTAMP_WARNING] == 1
    _assert_no_forbidden_terms(summary)


def test_duplicate_name_warning():
    records = [
        {
            "id": "a",
            "name": "Duplicate Name",
            "design_data": {
                "sequence": "ATGAAATAA",
                "host": "Rice",
                "gene_name": "GFP",
                "created_at": "2026-05-05T10:00:00",
            },
        },
        {
            "id": "b",
            "name": "Duplicate Name",
            "design_data": {
                "sequence": "ATGCCCTAA",
                "host": "Rice",
                "gene_name": "RFP",
                "created_at": "2026-05-05T11:00:00",
            },
        },
    ]

    summary = build_legacy_snapshot_inventory(records)

    assert summary["warnings_by_type"][DUPLICATE_DISPLAY_NAME_WARNING] == 1
    assert any(
        DUPLICATE_DISPLAY_NAME_WARNING in example["warnings"]
        for example in summary["example_records"]
    )
    _assert_no_forbidden_terms(summary)


def test_input_records_are_not_mutated():
    records = [
        {
            "name": "Immutable",
            "design_data": {
                "sequence": "ATGAAATAA",
                "host": "Rice",
                "gene_name": "GFP",
                "created_at": "2026-05-06T10:00:00",
                "validation_results": [{"severity": "warning"}],
            },
            "primers": [{"name": "forward"}],
        }
    ]
    original = deepcopy(records)

    build_legacy_snapshot_inventory(records)

    assert records == original


def test_forbidden_readiness_and_certification_terms_not_emitted():
    records = [
        {
            "name": "Safe Legacy Snapshot",
            "design_data": {
                "sequence": "ATGAAATAA",
                "host": "Rice",
                "gene_name": "GFP",
                "created_at": "2026-05-06T10:00:00",
                "validation_results": [{"severity": "warning"}],
            },
            "primers": [{"name": "forward"}],
        },
        {"name": "Sequence Only", "sequence": "ATGCCCTAA"},
        {"name": "Missing Sequence", "design_data": {"host": "Rice"}},
    ]

    summary = build_legacy_snapshot_inventory(records)

    _assert_no_forbidden_terms(summary)
