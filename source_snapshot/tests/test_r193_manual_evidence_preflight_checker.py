from services.plant_manual_evidence_preflight_checker import (
    preflight_manual_evidence_batch,
    preflight_manual_evidence_record,
)


FORBIDDEN_COPY_FRAGMENTS = [
    "vali" + "dated",
    "opti" + "mized",
    "experiment" + "-ready",
    "proto" + "col",
    "yield " + "prediction",
    "best " + "component",
    "wet-lab " + "ready",
]


def _manual_evidence_fixture(**section_overrides):
    fixture = {
        "evidence_entry_metadata": {
            "evidence_entry_id": "R193_MANUAL_ENTRY",
            "created_by_or_imported_by": "CURATOR_ALIAS",
            "created_at": "REVIEW_DATE_PLACEHOLDER",
            "updated_at": "REVIEW_DATE_PLACEHOLDER",
            "import_batch_id": "R193_BATCH",
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


def _reviewed_package_support_fixture():
    fixture = _manual_evidence_fixture(
        evidence_entry_metadata={
            "created_at": "CURATOR_REVIEW_DATE",
            "updated_at": "CURATOR_REVIEW_DATE",
        },
        source_identity={
            "source_type": "curated_source",
            "source_title": "Reviewed source title",
        },
        provenance_and_review={
            "demo_or_real_flag": "manually_curated",
            "provenance_status": "source_verified",
            "manual_review_status": "reviewed_for_documentation",
            "allowed_usage_scope": "package_draft_support",
        },
    )
    return fixture


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


def test_source_present_manual_evidence_remains_manual_review_only():
    result = preflight_manual_evidence_record(_manual_evidence_fixture())

    assert result["preflight_status"] == "manual_review_ready"
    assert result["manual_review_state"] == "manual_review_required"
    assert result["package_draft_support_preview"]["supported"] is False
    assert result["source_status"]["status"] == "source_present_needs_manual_review"
    assert (
        result["admission_gate_alignment"]["package_draft_support_status"]
        == "manual_review_only"
    )
    assert result["admission_gate_alignment"]["package_draft_support_allowed"] is False


def test_missing_source_is_blocked():
    result = preflight_manual_evidence_record(
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

    assert result["preflight_status"] == "blocked"
    assert result["source_status"]["status"] == "missing_source"
    assert "missing source trail" in result["blocking_reasons"]
    assert result["package_draft_support_preview"]["supported"] is False


def test_placeholder_example_demo_evidence_blocks_package_draft_support():
    result = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            source_identity={
                "source_title": "TODO_SOURCE_TITLE",
                "source_url_or_identifier": "TODO_SOURCE_TRAIL",
            },
            provenance_and_review={
                "demo_or_real_flag": "demo_example",
                "provenance_status": "demo_only",
                "allowed_usage_scope": "demo_only",
            },
        )
    )

    assert result["placeholder_status"]["has_placeholder_values"] is True
    assert result["package_draft_support_preview"]["supported"] is False
    assert (
        "placeholder/example/demo values require manual review"
        in result["package_draft_support_preview"]["blocking_reasons"]
    )
    assert (
        result["admission_gate_alignment"]["package_draft_support_status"]
        == "demo_only"
    )


def test_beginner_preview_label_is_preview_only_not_package_support():
    result = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            provenance_and_review={
                "demo_or_real_flag": "demo_example",
                "provenance_status": "demo_only",
                "allowed_usage_scope": "beginner_preview",
            }
        )
    )

    assert result["package_draft_support_preview"]["supported"] is False
    assert (
        result["admission_gate_alignment"]["package_draft_support_status"]
        == "demo_only"
    )
    assert result["admission_gate_alignment"]["beginner_preview_allowed"] is True
    assert (
        result["admission_gate_alignment"]["beginner_preview_status"]
        == "allowed_for_beginner_preview"
    )


def test_conflict_and_deprecated_evidence_are_blocked():
    conflict = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            provenance_and_review={"conflict_status": "conflicting_sources"}
        )
    )
    deprecated = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            provenance_and_review={
                "provenance_status": "deprecated_source",
                "deprecated_flag": True,
            }
        )
    )

    assert conflict["preflight_status"] == "blocked"
    assert "conflict_status is conflicting_sources" in conflict["blocking_reasons"]
    assert (
        conflict["admission_gate_alignment"]["package_draft_support_status"]
        == "conflict_needs_review_blocked"
    )
    assert deprecated["preflight_status"] == "blocked"
    assert "record or source is deprecated" in deprecated["blocking_reasons"]
    assert (
        deprecated["admission_gate_alignment"]["package_draft_support_status"]
        == "deprecated_blocked"
    )


def test_user_supplied_unverified_evidence_cannot_become_source_verified():
    result = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            provenance_and_review={
                "demo_or_real_flag": "user_supplied_unverified",
                "provenance_status": "source_verified",
                "manual_review_status": "needs_manual_review",
            }
        )
    )

    assert result["source_status"]["status"] == "source_present_needs_manual_review"
    assert (
        "user-supplied or unverified evidence cannot become source_verified"
        in result["warnings"]
    )
    assert result["package_draft_support_preview"]["supported"] is False
    assert (
        result["admission_gate_alignment"]["package_draft_support_status"]
        == "manual_review_only"
    )


def test_batch_summary_counts_ready_manual_review_and_blocked_records():
    result = preflight_manual_evidence_batch(
        [
            _reviewed_package_support_fixture(),
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
        ]
    )

    assert result["summary"]["total_records"] == 3
    assert result["summary"]["ready_records"] == 1
    assert result["summary"]["manual_review_records"] == 1
    assert result["summary"]["blocked_records"] == 1
    assert result["summary"]["package_draft_supported_records"] == 1


def test_empty_or_malformed_records_fail_closed():
    empty = preflight_manual_evidence_record({})
    malformed = preflight_manual_evidence_record(None)
    malformed_batch = preflight_manual_evidence_batch({})

    assert empty["preflight_status"] == "blocked"
    assert "evidence_entry_metadata.evidence_entry_id" in empty["missing_required_fields"]
    assert malformed["preflight_status"] == "blocked"
    assert malformed["missing_required_fields"] == ["record"]
    assert malformed_batch["preflight_status"] == "blocked"
    assert malformed_batch["summary"]["malformed_records"] == 1


def test_preflight_result_cannot_override_r189_gate():
    result = preflight_manual_evidence_record(
        _manual_evidence_fixture(
            admission_gate_preflight={
                "intended_usage": "package_draft_support",
                "expected_initial_gate_result": "allowed_for_package_draft_support",
                "review_required": False,
            }
        )
    )

    assert result["admission_gate_alignment"]["r189_gate_used"] is True
    assert result["admission_gate_alignment"]["r189_gate_can_be_overridden"] is False
    assert result["package_draft_support_preview"]["supported"] is False
    assert (
        result["admission_gate_alignment"]["package_draft_support_status"]
        == "manual_review_only"
    )
    assert (
        "admission_gate_preflight values are advisory and cannot override R189"
        in result["warnings"]
    )


def test_output_is_deterministic_and_plain_dict_list_only():
    record = _manual_evidence_fixture()
    first = preflight_manual_evidence_record(record)
    second = preflight_manual_evidence_record(record)
    batch = preflight_manual_evidence_batch([record, _reviewed_package_support_fixture()])

    assert first == second
    _assert_plain(first)
    _assert_plain(batch)

    copy_surface = repr([first, batch]).lower()
    for fragment in FORBIDDEN_COPY_FRAGMENTS:
        assert fragment not in copy_surface
