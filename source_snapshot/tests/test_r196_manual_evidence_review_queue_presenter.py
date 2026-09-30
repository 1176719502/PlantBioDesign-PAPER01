from services.plant_manual_evidence_preflight_checker import (
    preflight_manual_evidence_batch,
    preflight_manual_evidence_record,
)
from services.plant_manual_evidence_review_queue_presenter import (
    present_manual_evidence_review_queue,
    present_manual_evidence_review_queue_batch,
    present_manual_evidence_review_queue_record,
)


FORBIDDEN_COPY_FRAGMENTS = [
    "vali" + "dated construct",
    "opti" + "mized pathway",
    "experiment" + "-ready",
    "proto" + "col generation",
    "yield " + "prediction",
    "best biological",
    "wet-lab " + "ready",
    "ready for " + "execution",
    "production" + "-ready",
]

REALISTIC_IDENTIFIER_FRAGMENTS = [
    "1" + "0.",
    "PM" + "ID",
    "NC" + "BI",
    "Gen" + "Bank",
    "Add" + "gene",
    "XP" + "_",
    "NP" + "_",
    "NM" + "_",
]


def _manual_evidence_fixture(**section_overrides):
    fixture = {
        "evidence_entry_metadata": {
            "evidence_entry_id": "R196_MANUAL_ENTRY",
            "created_by_or_imported_by": "CURATOR_ALIAS",
            "created_at": "REVIEW_DATE_PLACEHOLDER",
            "updated_at": "REVIEW_DATE_PLACEHOLDER",
            "import_batch_id": "R196_BATCH",
            "import_mode": "manual_template_entry",
            "notes_for_curator": "CURATOR_NOTE_FOR_REVIEW",
        },
        "source_identity": {
            "source_type": "user_supplied",
            "source_title": "Curator source title",
            "source_url_or_identifier": "CURATOR_ENTERED_SOURCE_TRAIL",
            "doi": "",
            "accession": "",
            "repository_id": "",
            "citation_text": "CURATOR_ENTERED_CITATION_TEXT",
            "source_date_or_version": "CURATOR_ENTERED_SOURCE_DATE",
            "source_quote_or_evidence_note": "CURATOR_ENTERED_EVIDENCE_NOTE",
        },
        "evidence_scope": {
            "route_scope": "plant_protein_expression_review",
            "organism_scope": "PLANT_SCOPE_FOR_REVIEW",
            "host_context": "HOST_CONTEXT_FOR_REVIEW",
            "record_family": "manual_evidence",
            "component_type_or_record_family": "manual_evidence",
            "related_record_id": "RELATED_RECORD_FOR_REVIEW",
            "related_display_name": "Related record for review",
            "claim_type": "evidence_note",
            "claim_summary": "CURATOR_ENTERED_EVIDENCE_NOTE",
            "evidence_quality_level": "user_note",
        },
        "provenance_and_review": {
            "demo_or_real_flag": "user_supplied_unverified",
            "provenance_status": "source_present_needs_review",
            "manual_review_status": "needs_manual_review",
            "allowed_usage_scope": "manual_review_only",
            "conflict_status": "no_known_conflict",
            "deprecated_flag": False,
            "replacement_record_id": "",
            "last_reviewed_at": "",
            "reviewer_note": "CURATOR_NOTE_FOR_REVIEW",
        },
        "admission_gate_preflight": {
            "intended_usage": "manual_review_only",
            "expected_initial_gate_result": "manual_review_required",
            "blocking_reasons_expected": [
                "source_review_required",
                "manual_review_required",
            ],
            "review_required": True,
            "notes_for_gate_operator": "CURATOR_NOTE_FOR_REVIEW",
        },
    }

    for section, overrides in section_overrides.items():
        fixture[section].update(overrides)
    return fixture


def _beginner_preview_fixture():
    return _manual_evidence_fixture(
        provenance_and_review={
            "demo_or_real_flag": "demo_example",
            "provenance_status": "demo_only",
            "allowed_usage_scope": "beginner_preview",
        }
    )


def _assert_plain(value):
    if isinstance(value, dict):
        for key, child in value.items():
            assert isinstance(key, str)
            _assert_plain(child)
        return
    if isinstance(value, list):
        for child in value:
            _assert_plain(child)
        return
    assert value is None or isinstance(value, (str, int, float, bool))


def _all_keys(value):
    if isinstance(value, dict):
        keys = list(value)
        for child in value.values():
            keys.extend(_all_keys(child))
        return keys
    if isinstance(value, list):
        keys = []
        for child in value:
            keys.extend(_all_keys(child))
        return keys
    return []


def test_source_present_manual_evidence_becomes_review_needed_not_source_proof():
    preflight = preflight_manual_evidence_record(_manual_evidence_fixture())
    row = present_manual_evidence_review_queue_record(preflight)

    assert row["queue_state"] == "review_needed"
    assert row["preflight_status"] == "manual_review_ready"
    assert row["manual_review_state"] == "manual_review_required"
    assert row["source_status"]["status"] == "source_present_needs_manual_review"
    assert row["source_readback"]["status"] == "source_present_needs_manual_review"
    assert row["package_export_permission"] is False
    assert row["package_support_readback"]["package_export_permission"] is False
    assert "source_" + "verified" not in _all_keys(row)


def test_missing_source_evidence_becomes_blocked_with_visible_reason():
    preflight = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            source_identity={
                "source_url_or_identifier": "",
                "doi": "",
                "accession": "",
                "repository_id": "",
                "citation_text": "",
            }
        )
    )
    row = present_manual_evidence_review_queue_record(preflight)

    assert row["queue_state"] == "blocked"
    assert row["source_status"]["status"] == "missing_source"
    assert "missing source trail" in row["visible_blocking_reasons"]
    assert row["primary_reason"] == "missing source trail"


def test_placeholder_demo_example_evidence_is_visible_but_blocked_for_package_support():
    preflight = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            source_identity={
                "source_title": "EXAMPLE_SOURCE_TITLE",
                "source_url_or_identifier": "DEMO_SOURCE_TRAIL",
            },
            provenance_and_review={
                "demo_or_real_flag": "demo_example",
                "provenance_status": "demo_only",
                "allowed_usage_scope": "demo_only",
            },
        )
    )
    row = present_manual_evidence_review_queue_record(preflight)

    assert row["queue_state"] == "blocked"
    assert row["evidence_label"] == "EXAMPLE_SOURCE_TITLE"
    assert row["placeholder_demo_example_status"]["has_placeholder_values"] is True
    assert row["package_support_readback"]["supported"] is False
    assert (
        "placeholder/example/demo values require manual review"
        in row["visible_blocking_reasons"]
    )
    assert (
        row["admission_gate_alignment"]["package_draft_support_status"] == "demo_only"
    )


def test_beginner_preview_evidence_becomes_preview_only_not_package_supporting():
    preflight = preflight_manual_evidence_record(_beginner_preview_fixture())
    row = present_manual_evidence_review_queue_record(preflight)

    assert row["queue_state"] == "preview_only"
    assert row["review_priority"] == "preview_context"
    assert row["admission_gate_alignment"]["beginner_preview_allowed"] is True
    assert (
        row["admission_gate_alignment"]["beginner_preview_status"]
        == "allowed_for_beginner_preview"
    )
    assert row["package_draft_support_preview"]["supported"] is False
    assert row["package_support_readback"]["package_export_permission"] is False


def test_conflict_and_deprecated_evidence_become_blocked():
    conflict_row = present_manual_evidence_review_queue_record(
        preflight_manual_evidence_record(
            _manual_evidence_fixture(
                provenance_and_review={"conflict_status": "conflicting_sources"}
            )
        )
    )
    deprecated_row = present_manual_evidence_review_queue_record(
        preflight_manual_evidence_record(
            _manual_evidence_fixture(
                provenance_and_review={
                    "provenance_status": "deprecated_source",
                    "deprecated_flag": True,
                }
            )
        )
    )

    assert conflict_row["queue_state"] == "blocked"
    assert conflict_row["review_priority"] == "blocked_high_attention"
    assert "conflict_status is conflicting_sources" in conflict_row[
        "visible_blocking_reasons"
    ]
    assert deprecated_row["queue_state"] == "blocked"
    assert deprecated_row["review_priority"] == "blocked_high_attention"
    assert "record or source is deprecated" in deprecated_row["visible_blocking_reasons"]


def test_malformed_or_empty_record_returns_fail_closed_queue_output():
    empty_row = present_manual_evidence_review_queue_record({})
    malformed_row = present_manual_evidence_review_queue_record(None)
    empty_preflight_row = present_manual_evidence_review_queue_record(
        preflight_manual_evidence_record({})
    )

    assert empty_row["queue_state"] == "empty"
    assert empty_row["preflight_status"] == "blocked"
    assert empty_row["package_support_readback"]["supported"] is False
    assert malformed_row["queue_state"] == "malformed_blocked"
    assert malformed_row["traceability_readback"]["input_shape"] == "malformed"
    assert empty_preflight_row["queue_state"] == "empty"
    assert empty_preflight_row["package_export_permission"] is False


def test_batch_output_preserves_row_counts_and_summary_counts():
    batch = preflight_manual_evidence_batch(
        [
            _manual_evidence_fixture(),
            _manual_evidence_fixture(
                source_identity={
                    "source_url_or_identifier": "",
                    "doi": "",
                    "accession": "",
                    "repository_id": "",
                    "citation_text": "",
                }
            ),
            _beginner_preview_fixture(),
        ]
    )
    payload = present_manual_evidence_review_queue_batch(batch)

    assert len(payload["rows"]) == 3
    assert payload["summary"]["row_count"] == 3
    assert payload["preflight_summary"] == batch["summary"]
    assert payload["summary"]["preflight_total_records"] == 3
    assert payload["summary"]["preflight_manual_review_records"] == 2
    assert payload["summary"]["preflight_blocked_records"] == 1
    assert payload["summary"]["queue_state_counts"] == {
        "blocked": 1,
        "empty": 0,
        "malformed_blocked": 0,
        "preview_only": 1,
        "review_needed": 1,
    }


def test_warnings_and_blocking_reasons_are_not_dropped():
    preflight = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            source_identity={
                "source_url_or_identifier": "",
                "doi": "",
                "accession": "",
                "repository_id": "",
                "citation_text": "",
            },
            provenance_and_review={
                "demo_or_real_flag": "user_supplied_unverified",
                "provenance_status": "source_verified",
                "manual_review_status": "needs_manual_review",
            },
            admission_gate_preflight={
                "intended_usage": "package_draft_support",
                "expected_initial_gate_result": "allowed_for_package_draft_support",
                "review_required": False,
            },
        )
    )
    row = present_manual_evidence_review_queue_record(preflight)

    assert "missing source trail" in row["visible_blocking_reasons"]
    assert (
        "admission_gate_preflight values are advisory and cannot override R189"
        in row["visible_warnings"]
    )
    assert (
        "user-supplied or unverified evidence cannot become source_verified"
        in row["visible_warnings"]
    )


def test_r189_gate_alignment_is_preserved():
    preflight = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            admission_gate_preflight={
                "intended_usage": "package_draft_support",
                "expected_initial_gate_result": "allowed_for_package_draft_support",
                "review_required": False,
            }
        )
    )
    row = present_manual_evidence_review_queue_record(preflight)

    assert row["admission_gate_alignment"] == preflight["admission_gate_alignment"]
    assert row["traceability"] == preflight["traceability"]
    assert row["r189_admission_gate_is_preserved"] is True
    assert row["r193_preflight_can_override_r189"] is False
    assert (
        row["admission_gate_alignment"]["package_draft_support_status"]
        == "manual_review_only"
    )


def test_output_is_deterministic_plain_dict_list_only_and_copy_safe():
    record = _manual_evidence_fixture(
        provenance_and_review={
            "demo_or_real_flag": "user_supplied_unverified",
            "provenance_status": "source_verified",
        }
    )
    first = present_manual_evidence_review_queue(preflight_manual_evidence_record(record))
    second = present_manual_evidence_review_queue(preflight_manual_evidence_record(record))
    batch = present_manual_evidence_review_queue(
        preflight_manual_evidence_batch([record, _beginner_preview_fixture()])
    )
    list_batch = present_manual_evidence_review_queue(
        [preflight_manual_evidence_record(record)]
    )

    assert first == second
    assert list_batch["summary"]["row_count"] == 1
    _assert_plain(first)
    _assert_plain(batch)
    _assert_plain(list_batch)

    surface = repr([first, batch, list_batch])
    for fragment in REALISTIC_IDENTIFIER_FRAGMENTS:
        assert fragment not in surface
    lowered = surface.lower()
    for fragment in FORBIDDEN_COPY_FRAGMENTS:
        assert fragment not in lowered
