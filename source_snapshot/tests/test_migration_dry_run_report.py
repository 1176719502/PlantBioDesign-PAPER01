import os
import sys
from copy import deepcopy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.legacy_snapshot_adapter import FORBIDDEN_READINESS_TERMS  # noqa: E402
from services.migration_dry_run_report import (  # noqa: E402
    DO_NOT_MIGRATE_AUTOMATICALLY,
    MISSING_REQUIRED_DATA,
    NEEDS_REVIEW,
    READ_ONLY_COMPATIBLE,
    build_migration_dry_run_report,
)

FORBIDDEN_ACTION_TERMS = ("migrate", "auto_migrate", "ready", "validated", "certified")


def _assert_no_forbidden_terms(value):
    combined = str(value)
    for forbidden_term in FORBIDDEN_READINESS_TERMS:
        assert forbidden_term not in combined


def _assert_allowed_action_values(report):
    allowed = {
        READ_ONLY_COMPATIBLE,
        NEEDS_REVIEW,
        DO_NOT_MIGRATE_AUTOMATICALLY,
        MISSING_REQUIRED_DATA,
    }
    assert set(report["recommended_actions_summary"]) == allowed
    for action in report["recommended_actions_summary"]:
        assert action in allowed
        for forbidden_term in FORBIDDEN_ACTION_TERMS:
            if forbidden_term == "migrate":
                assert action not in {"migrate", "auto_migrate"}
            else:
                assert forbidden_term not in action
    for row in report["example_records"]:
        assert row["recommended_action"] in allowed


def test_empty_records_report():
    report = build_migration_dry_run_report([])

    assert report["report_type"] == "read_only_migration_dry_run"
    assert report["total_records"] == 0
    assert report["migration_candidate_count"] == 0
    assert report["read_only_compatible_count"] == 0
    assert report["needs_review_count"] == 0
    assert report["do_not_migrate_automatically_count"] == 0
    assert report["missing_required_data_count"] == 0
    assert report["high_risk_record_count"] == 0
    assert report["medium_risk_record_count"] == 0
    assert report["low_risk_record_count"] == 0
    assert report["duplicate_groups"] == {"display_name": [], "legacy_snapshot_id": []}
    assert report["warnings_by_type"] == {}
    assert report["example_records"] == []
    _assert_allowed_action_values(report)
    _assert_no_forbidden_terms(report)


def test_mixed_records_report_counts():
    records = [
        {
            "id": "full-1",
            "name": "Complete Snapshot",
            "source": "project_history",
            "design_data": {
                "sequence": "ATGAAATAA",
                "host": "Rice",
                "gene_name": "GFP",
                "created_at": "2026-05-01T10:00:00",
                "metadata": {"description": "Complete legacy snapshot"},
            },
        },
        {
            "id": "review-1",
            "name": "Historical Snapshot",
            "design_data": {
                "sequence": "ATGCCCTAA",
                "host": "Rice",
                "gene_name": "RFP",
                "created_at": "2026-05-01T11:00:00",
                "metadata": {"description": "Historical validation snapshot"},
                "validation_results": [{"severity": "warning"}],
            },
        },
        {
            "id": "missing-sequence",
            "name": "Missing Sequence",
            "design_data": {
                "host": "Rice",
                "gene_name": "ABC1",
                "created_at": "2026-05-01T12:00:00",
            },
        },
    ]

    report = build_migration_dry_run_report(records)

    assert report["total_records"] == 3
    assert report["read_only_compatible_count"] == 1
    assert report["needs_review_count"] == 1
    assert report["missing_required_data_count"] == 1
    assert report["do_not_migrate_automatically_count"] == 0
    assert report["migration_candidate_count"] == 2
    assert report["high_risk_record_count"] == 1
    assert report["medium_risk_record_count"] == 1
    assert report["low_risk_record_count"] == 1
    _assert_allowed_action_values(report)
    _assert_no_forbidden_terms(report)


def test_action_summary_counts_for_review_and_missing_data():
    records = [
        {
            "name": "Primer Review",
            "design_data": {
                "sequence": "ATGAAATAA",
                "host": "E. coli",
                "gene_name": "lacZ",
                "created_at": "2026-05-03T10:00:00",
                "metadata": {"description": "Primer snapshot"},
            },
            "primers": [{"name": "forward"}],
        },
        {
            "name": "Missing Sequence",
            "design_data": {
                "host": "Rice",
                "gene_name": "GFP",
                "created_at": "2026-05-04T10:00:00",
            },
        },
    ]

    report = build_migration_dry_run_report(records)

    assert report["recommended_actions_summary"][NEEDS_REVIEW] == 1
    assert report["recommended_actions_summary"][MISSING_REQUIRED_DATA] == 1
    assert report["needs_review_count"] == 1
    assert report["missing_required_data_count"] == 1
    _assert_no_forbidden_terms(report)


def test_missing_sequence_becomes_missing_required_data():
    report = build_migration_dry_run_report(
        [
            {
                "name": "Missing Sequence",
                "design_data": {
                    "host": "Rice",
                    "gene_name": "GFP",
                    "created_at": "2026-05-04T10:00:00",
                },
            }
        ]
    )

    assert report["missing_required_data_count"] == 1
    assert report["do_not_migrate_automatically_count"] == 0
    assert report["example_records"][0]["recommended_action"] == MISSING_REQUIRED_DATA
    assert report["example_records"][0]["risk_level"] == "high"


def test_corrupted_design_data_does_not_migrate_automatically():
    report = build_migration_dry_run_report(
        [
            {
                "name": "Corrupted Payload",
                "sequence": "ATGAAATAA",
                "design_data": "not-json-dict",
            }
        ]
    )

    assert report["do_not_migrate_automatically_count"] == 1
    assert report["example_records"][0]["recommended_action"] == DO_NOT_MIGRATE_AUTOMATICALLY
    assert report["example_records"][0]["risk_level"] == "high"


def test_historical_validation_creates_needs_review_not_ready():
    report = build_migration_dry_run_report(
        [
            {
                "name": "Historical Validation",
                "design_data": {
                    "sequence": "ATGAAATAA",
                    "host": "Maize",
                    "gene_name": "ABC1",
                    "created_at": "2026-05-02T10:00:00",
                    "metadata": {"description": "Historical validation"},
                    "validation_results": [{"severity": "warning"}],
                },
            }
        ]
    )

    assert report["needs_review_count"] == 1
    assert report["read_only_compatible_count"] == 0
    assert report["example_records"][0]["recommended_action"] == NEEDS_REVIEW
    _assert_no_forbidden_terms(report)


def test_duplicate_names_appear_in_duplicate_groups():
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

    report = build_migration_dry_run_report(records)

    assert report["duplicate_groups"]["display_name"] == ["Duplicate Name"]
    assert report["needs_review_count"] == 2
    assert report["medium_risk_record_count"] == 2
    _assert_no_forbidden_terms(report)


def test_no_forbidden_readiness_or_certification_terms_emitted():
    records = [
        {
            "name": "Safe Snapshot",
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

    report = build_migration_dry_run_report(records)

    _assert_no_forbidden_terms(report)
    _assert_allowed_action_values(report)


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

    build_migration_dry_run_report(records)

    assert records == original
