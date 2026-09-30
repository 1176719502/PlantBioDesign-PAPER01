from services.plant_manual_evidence_preflight_checker import (
    preflight_manual_evidence_batch,
    preflight_manual_evidence_record,
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
            "evidence_entry_id": "R195_MANUAL_ENTRY",
            "created_by_or_imported_by": "CURATOR_ALIAS",
            "created_at": "REVIEW_DATE_PLACEHOLDER",
            "updated_at": "REVIEW_DATE_PLACEHOLDER",
            "import_batch_id": "R195_BATCH",
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


def _reviewed_documentation_fixture():
    return _manual_evidence_fixture(
        evidence_entry_metadata={
            "created_at": "CURATOR_REVIEW_DATE",
            "updated_at": "CURATOR_REVIEW_DATE",
        },
        source_identity={
            "source_type": "curated_source",
            "source_title": "Reviewed source title",
            "source_url_or_identifier": "CURATOR_REVIEWED_SOURCE_TRAIL",
            "citation_text": "CURATOR_REVIEWED_CITATION_TEXT",
        },
        provenance_and_review={
            "demo_or_real_flag": "manually_curated",
            "provenance_status": "source_verified",
            "manual_review_status": "reviewed_for_documentation",
            "allowed_usage_scope": "package_draft_support",
        },
    )


def _beginner_preview_fixture():
    return _manual_evidence_fixture(
        provenance_and_review={
            "demo_or_real_flag": "demo_example",
            "provenance_status": "demo_only",
            "allowed_usage_scope": "beginner_preview",
        }
    )


def _queue_item_state(preflight_result):
    alignment = preflight_result["admission_gate_alignment"]
    if preflight_result["preflight_status"] == "blocked":
        return "blocked"
    if (
        alignment["beginner_preview_allowed"] is True
        and preflight_result["package_draft_support_preview"]["supported"] is False
    ):
        return "preview_only"
    if alignment["package_draft_support_status"] == "demo_only":
        return "blocked"
    return "review_needed"


def _review_queue_payload(preflight_result):
    boundary = {
        "display_readback_only": True,
        "imports_evidence": False,
        "approval_allowed": False,
        "source_verified": False,
        "package_export_permission": False,
        "package_draft_completion_permission": False,
        "biological_recommendation": False,
        "experiment_validation_claim": False,
        "optimization_claim": False,
        "wet_lab_readiness_judgment": False,
        "r189_admission_gate_is_preserved": True,
        "r193_preflight_can_override_r189": False,
    }

    if "records" in preflight_result:
        records = [_review_queue_payload(record) for record in preflight_result["records"]]
        queue_state_counts = {
            "blocked": sum(1 for record in records if record["queue_item_state"] == "blocked"),
            "review_needed": sum(
                1 for record in records if record["queue_item_state"] == "review_needed"
            ),
            "preview_only": sum(
                1 for record in records if record["queue_item_state"] == "preview_only"
            ),
        }
        return {
            "payload_kind": "manual_evidence_review_queue_batch",
            "preflight_status": preflight_result["preflight_status"],
            "records": records,
            "summary": dict(preflight_result["summary"]),
            "queue_state_counts": queue_state_counts,
            "batch_summary_usage": "display_readback_only",
            "automatic_import_allowed": False,
            "automatic_approval_allowed": False,
            "automatic_package_export_allowed": False,
            "blocking_reasons": list(preflight_result["blocking_reasons"]),
            "warnings": list(preflight_result["warnings"]),
            "consumer_boundary": boundary,
        }

    return {
        "payload_kind": "manual_evidence_review_queue_item",
        "queue_item_state": _queue_item_state(preflight_result),
        "preflight_status": preflight_result["preflight_status"],
        "manual_review_state": preflight_result["manual_review_state"],
        "blocking_reasons": list(preflight_result["blocking_reasons"]),
        "warnings": list(preflight_result["warnings"]),
        "package_draft_support_preview": dict(
            preflight_result["package_draft_support_preview"]
        ),
        "source_status": dict(preflight_result["source_status"]),
        "placeholder_status": dict(preflight_result["placeholder_status"]),
        "admission_gate_alignment": dict(preflight_result["admission_gate_alignment"]),
        "traceability": dict(preflight_result["traceability"]),
        "consumer_boundary": boundary,
    }


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


def test_source_present_manual_evidence_is_review_needed_manual_review_only():
    preflight = preflight_manual_evidence_record(_manual_evidence_fixture())
    payload = _review_queue_payload(preflight)

    assert payload["queue_item_state"] == "review_needed"
    assert payload["preflight_status"] == "manual_review_ready"
    assert payload["manual_review_state"] == "manual_review_required"
    assert payload["blocking_reasons"] == []
    assert payload["warnings"] == []
    assert payload["package_draft_support_preview"]["supported"] is False
    assert (
        payload["admission_gate_alignment"]["package_draft_support_status"]
        == "manual_review_only"
    )
    assert payload["traceability"]["record_id"] == "R195_MANUAL_ENTRY"
    assert payload["consumer_boundary"]["imports_evidence"] is False
    assert payload["consumer_boundary"]["approval_allowed"] is False


def test_missing_source_evidence_is_blocked_and_reason_is_preserved():
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
    payload = _review_queue_payload(preflight)

    assert payload["queue_item_state"] == "blocked"
    assert payload["preflight_status"] == "blocked"
    assert payload["source_status"]["status"] == "missing_source"
    assert "missing source trail" in payload["blocking_reasons"]
    assert (
        "missing source trail"
        in payload["package_draft_support_preview"]["blocking_reasons"]
    )


def test_placeholder_demo_example_evidence_is_blocked_for_package_draft_support():
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
    payload = _review_queue_payload(preflight)

    assert payload["queue_item_state"] == "blocked"
    assert payload["placeholder_status"]["has_placeholder_values"] is True
    assert payload["package_draft_support_preview"]["supported"] is False
    assert (
        "placeholder/example/demo values require manual review"
        in payload["package_draft_support_preview"]["blocking_reasons"]
    )
    assert (
        payload["admission_gate_alignment"]["package_draft_support_status"]
        == "demo_only"
    )


def test_beginner_preview_evidence_remains_preview_only_not_package_supporting():
    preflight = preflight_manual_evidence_record(_beginner_preview_fixture())
    payload = _review_queue_payload(preflight)

    assert payload["queue_item_state"] == "preview_only"
    assert (
        payload["admission_gate_alignment"]["beginner_preview_status"]
        == "allowed_for_beginner_preview"
    )
    assert payload["admission_gate_alignment"]["beginner_preview_allowed"] is True
    assert payload["package_draft_support_preview"]["supported"] is False
    assert (
        payload["admission_gate_alignment"]["package_draft_support_status"]
        == "demo_only"
    )


def test_conflict_and_deprecated_evidence_appear_blocked():
    conflict_payload = _review_queue_payload(
        preflight_manual_evidence_record(
            _manual_evidence_fixture(
                provenance_and_review={"conflict_status": "conflicting_sources"}
            )
        )
    )
    deprecated_payload = _review_queue_payload(
        preflight_manual_evidence_record(
            _manual_evidence_fixture(
                provenance_and_review={
                    "provenance_status": "deprecated_source",
                    "deprecated_flag": True,
                }
            )
        )
    )

    assert conflict_payload["queue_item_state"] == "blocked"
    assert "conflict_status is conflicting_sources" in conflict_payload["blocking_reasons"]
    assert (
        conflict_payload["admission_gate_alignment"]["package_draft_support_status"]
        == "conflict_needs_review_blocked"
    )
    assert deprecated_payload["queue_item_state"] == "blocked"
    assert "record or source is deprecated" in deprecated_payload["blocking_reasons"]
    assert (
        deprecated_payload["admission_gate_alignment"]["package_draft_support_status"]
        == "deprecated_blocked"
    )


def test_queue_consumer_cannot_reinterpret_manual_review_state_as_source_verified():
    preflight = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            provenance_and_review={
                "demo_or_real_flag": "user_supplied_unverified",
                "provenance_status": "source_verified",
                "manual_review_status": "needs_manual_review",
            }
        )
    )
    payload = _review_queue_payload(preflight)

    assert payload["queue_item_state"] == "review_needed"
    assert payload["queue_item_state"] != "source_verified"
    assert payload["manual_review_state"] == "manual_review_required"
    assert payload["source_status"]["status"] == "source_present_needs_manual_review"
    assert (
        "user-supplied or unverified evidence cannot become source_verified"
        in payload["warnings"]
    )
    assert payload["consumer_boundary"]["source_verified"] is False


def test_queue_consumer_cannot_reinterpret_preview_as_package_export_permission():
    preflight = preflight_manual_evidence_record(_reviewed_documentation_fixture())
    payload = _review_queue_payload(preflight)

    assert payload["queue_item_state"] == "review_needed"
    assert payload["package_draft_support_preview"]["supported"] is True
    assert (
        payload["admission_gate_alignment"]["package_draft_support_status"]
        == "allowed_for_package_draft_support"
    )
    assert payload["consumer_boundary"]["package_export_permission"] is False
    assert payload["consumer_boundary"]["package_draft_completion_permission"] is False
    assert payload["consumer_boundary"]["biological_recommendation"] is False
    assert payload["consumer_boundary"]["wet_lab_readiness_judgment"] is False


def test_empty_or_malformed_records_fail_closed_for_queue_payload():
    empty_payload = _review_queue_payload(preflight_manual_evidence_record({}))
    malformed_payload = _review_queue_payload(preflight_manual_evidence_record(None))
    malformed_batch_payload = _review_queue_payload(preflight_manual_evidence_batch({}))

    assert empty_payload["queue_item_state"] == "blocked"
    assert empty_payload["preflight_status"] == "blocked"
    assert empty_payload["manual_review_state"] == (
        "cannot_review_until_required_fields_are_present"
    )
    assert malformed_payload["queue_item_state"] == "blocked"
    assert malformed_payload["traceability"]["input_shape"] == "malformed"
    assert malformed_batch_payload["preflight_status"] == "blocked"
    assert malformed_batch_payload["summary"]["malformed_records"] == 1
    assert malformed_batch_payload["records"] == []


def test_batch_summary_preserves_queue_counts_as_display_readback_only():
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
    payload = _review_queue_payload(batch)

    assert payload["summary"]["total_records"] == 3
    assert payload["summary"]["manual_review_records"] == 2
    assert payload["summary"]["blocked_records"] == 1
    assert payload["queue_state_counts"] == {
        "blocked": 1,
        "review_needed": 1,
        "preview_only": 1,
    }
    assert payload["batch_summary_usage"] == "display_readback_only"
    assert payload["automatic_import_allowed"] is False
    assert payload["automatic_approval_allowed"] is False
    assert payload["automatic_package_export_allowed"] is False


def test_review_queue_payload_preserves_r189_alignment_and_r193_traceability():
    preflight = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            admission_gate_preflight={
                "intended_usage": "package_draft_support",
                "expected_initial_gate_result": "allowed_for_package_draft_support",
                "review_required": False,
            }
        )
    )
    payload = _review_queue_payload(preflight)

    assert payload["admission_gate_alignment"]["r189_gate_used"] is True
    assert payload["admission_gate_alignment"]["r189_gate_can_be_overridden"] is False
    assert payload["consumer_boundary"]["r189_admission_gate_is_preserved"] is True
    assert payload["consumer_boundary"]["r193_preflight_can_override_r189"] is False
    assert payload["traceability"] == preflight["traceability"]
    assert (
        "admission_gate_preflight values are advisory and cannot override R189"
        in payload["warnings"]
    )


def test_review_queue_output_is_deterministic_plain_and_copy_safe():
    record = _manual_evidence_fixture(
        provenance_and_review={
            "demo_or_real_flag": "user_supplied_unverified",
            "provenance_status": "source_verified",
        }
    )
    first = _review_queue_payload(preflight_manual_evidence_record(record))
    second = _review_queue_payload(preflight_manual_evidence_record(record))
    batch = _review_queue_payload(
        preflight_manual_evidence_batch([record, _beginner_preview_fixture()])
    )

    assert first == second
    _assert_plain(first)
    _assert_plain(batch)

    contract_surface = repr([first, batch])
    for fragment in REALISTIC_IDENTIFIER_FRAGMENTS:
        assert fragment not in contract_surface
    lowered = contract_surface.lower()
    for fragment in FORBIDDEN_COPY_FRAGMENTS:
        assert fragment not in lowered
