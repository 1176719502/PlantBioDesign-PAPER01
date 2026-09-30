import os
import sys
from copy import deepcopy

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from services.status_derivation import (  # noqa: E402
    BLOCKED_NON_AUTHORITATIVE_TERMS,
    derive_loaded_snapshot_label,
    derive_safe_status_notes,
    has_historical_validation_data,
    normalize_snapshot_status,
)


def _assert_no_blocked_terms(values):
    combined = "\n".join(str(value) for value in values)
    for blocked_term in BLOCKED_NON_AUTHORITATIVE_TERMS:
        assert blocked_term not in combined


def test_saved_maps_to_snapshot_saved():
    assert normalize_snapshot_status("saved") == "Snapshot Saved"
    assert normalize_snapshot_status(" SAVED ") == "Snapshot Saved"


def test_empty_status_values_map_to_snapshot_saved():
    assert normalize_snapshot_status(None) == "Snapshot Saved"
    assert normalize_snapshot_status("") == "Snapshot Saved"
    assert normalize_snapshot_status("   ") == "Snapshot Saved"


def test_missing_status_maps_to_snapshot_saved():
    record = {}

    assert normalize_snapshot_status(record.get("status")) == "Snapshot Saved"


def test_unknown_status_maps_to_safe_snapshot_record_wording():
    assert normalize_snapshot_status("Validated") == "Snapshot Record"
    assert normalize_snapshot_status("Ready for Export") == "Snapshot Record"


def test_loaded_snapshot_label_is_display_only():
    assert derive_loaded_snapshot_label(True) == "Loaded Snapshot"
    assert derive_loaded_snapshot_label(False) is None


def test_validation_results_do_not_produce_authoritative_terms():
    record = {
        "status": "saved",
        "validation_results": [
            {"severity": "info", "message": "Legacy validation data"},
        ],
    }

    values = [normalize_snapshot_status(record.get("status")), *derive_safe_status_notes(record)]

    _assert_no_blocked_terms(values)
    assert "Prior validation data may be historical." in values


def test_issue_count_does_not_produce_authoritative_terms():
    record = {
        "status": "saved",
        "metadata": {"n_issues": 0},
    }

    values = [normalize_snapshot_status(record.get("status")), *derive_safe_status_notes(record)]

    _assert_no_blocked_terms(values)
    assert "Snapshot Saved" in values


def test_historical_validation_note_is_labeled_historical():
    record = {
        "summary": {
            "validation_results": [{"severity": "warning"}],
        }
    }

    notes = derive_safe_status_notes(record)

    assert "Prior validation data may be historical." in notes
    assert any("historical" in note.lower() for note in notes)


def test_validation_like_snapshot_data_detection_is_limited_to_presence():
    assert has_historical_validation_data({"validation_results": []}) is False
    assert has_historical_validation_data({"validation_results": [{"message": "Prior issue"}]}) is True
    assert has_historical_validation_data({"metadata": {"n_issues": 2}}) is True
    assert has_historical_validation_data({"metadata": {"n_issues": 0}}) is False


def test_safe_status_notes_include_step_6_review_guidance():
    notes = derive_safe_status_notes({})

    assert "Saved snapshot only; not validation or readiness." in notes
    assert "Use Expression Wizard Step 6 for current documentation export review." in notes
    _assert_no_blocked_terms(notes)


def test_helper_functions_do_not_mutate_input_records():
    record = {
        "status": "saved",
        "summary": {"validation_results": [{"severity": "warning"}]},
        "metadata": {"n_issues": 1},
    }
    original = deepcopy(record)

    normalize_snapshot_status(record.get("status"))
    has_historical_validation_data(record)
    derive_safe_status_notes(record)

    assert record == original
