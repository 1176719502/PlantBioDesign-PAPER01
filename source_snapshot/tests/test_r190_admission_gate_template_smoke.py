from services.plant_real_data_admission_gate import evaluate_real_seed_record_admission


TEMPLATE_FIELDS = [
    "record_id",
    "record_type",
    "display_name",
    "canonical_name",
    "aliases",
    "route_scope",
    "organism_scope",
    "host_context",
    "component_type_or_record_family",
    "source_type",
    "source_title",
    "source_url_or_identifier",
    "doi",
    "accession",
    "repository_id",
    "citation_text",
    "source_quote_or_evidence_note",
    "curator_note",
    "created_by_or_imported_by",
    "created_at",
    "updated_at",
    "last_reviewed_at",
    "provenance_status",
    "manual_review_status",
    "allowed_usage_scope",
    "demo_or_real_flag",
    "conflict_status",
    "deprecated_flag",
    "replacement_record_id",
    "notes_for_user",
]

FORBIDDEN_COPY_FRAGMENTS = [
    "vali" + "dated",
    "opti" + "mized",
    "experiment" + "-ready",
    "proto" + "col",
    "yield " + "prediction",
    "best " + "component",
    "wet-lab " + "ready",
    "final " + "package",
    "exported " + "package",
]


def _template_record(**overrides):
    record = {
        "record_id": "TODO_RECORD_ID",
        "record_type": "plant_component_record",
        "display_name": "TODO_RECORD_LABEL",
        "canonical_name": "TODO_CANONICAL_NAME",
        "aliases": ["TODO_ALIAS"],
        "route_scope": "plant_protein_expression_review",
        "organism_scope": "TODO_ORGANISM_SCOPE",
        "host_context": "TODO_HOST_CONTEXT",
        "component_type_or_record_family": "TODO_COMPONENT_TYPE",
        "source_type": "TODO_SOURCE_TYPE",
        "source_title": "TODO_SOURCE_TITLE",
        "source_url_or_identifier": "TODO_SOURCE_URL_OR_IDENTIFIER",
        "doi": "TODO_DOI_IF_APPLICABLE",
        "accession": "",
        "repository_id": "",
        "citation_text": "TODO_CITATION_TEXT",
        "source_quote_or_evidence_note": "TODO_SOURCE_QUOTE_OR_EVIDENCE_NOTE",
        "curator_note": "TODO_CURATOR_NOTE",
        "created_by_or_imported_by": "TODO_CREATED_BY_OR_IMPORTED_BY",
        "created_at": "TODO_CREATED_AT",
        "updated_at": "TODO_UPDATED_AT",
        "last_reviewed_at": "TODO_LAST_REVIEWED_AT",
        "provenance_status": "source_verified",
        "manual_review_status": "reviewed_for_documentation",
        "allowed_usage_scope": "package_draft_support",
        "demo_or_real_flag": "literature_derived",
        "conflict_status": "no_known_conflict",
        "deprecated_flag": False,
        "replacement_record_id": "",
        "notes_for_user": "TODO_NOTES_FOR_USER",
    }
    record.update(overrides)
    return record


def _copy_surface(result):
    return f"{result['user_visible_label']}\n{result['safety_notes']}".lower()


def _assert_safe_copy(result):
    copy_surface = _copy_surface(result)
    for fragment in FORBIDDEN_COPY_FRAGMENTS:
        assert fragment not in copy_surface


def test_eligible_package_draft_support_template_record_is_allowed():
    result = evaluate_real_seed_record_admission(_template_record())

    assert result["admission_status"] == "allowed_for_package_draft_support"
    assert result["allowed"] is True
    assert result["review_required"] is False
    _assert_safe_copy(result)


def test_missing_source_template_record_is_blocked():
    result = evaluate_real_seed_record_admission(
        _template_record(
            source_url_or_identifier="",
            doi="",
            accession="",
            repository_id="",
            citation_text="",
        )
    )

    assert result["admission_status"] == "missing_source_blocked"
    assert result["allowed"] is False


def test_demo_example_is_blocked_for_package_support_and_labeled_for_preview():
    package_result = evaluate_real_seed_record_admission(
        _template_record(
            demo_or_real_flag="demo_example",
            provenance_status="demo_only",
            allowed_usage_scope="demo_only",
        )
    )
    preview_result = evaluate_real_seed_record_admission(
        _template_record(
            demo_or_real_flag="demo_example",
            provenance_status="demo_only",
            allowed_usage_scope="beginner_preview",
        ),
        intended_usage="beginner_preview",
    )

    assert package_result["admission_status"] == "demo_only"
    assert package_result["allowed"] is False
    assert preview_result["admission_status"] == "allowed_for_beginner_preview"
    assert preview_result["allowed"] is True
    assert preview_result["demo_or_real_flag"] == "demo_example"
    assert "source-backed real data" in preview_result["safety_notes"]
    _assert_safe_copy(preview_result)


def test_user_supplied_unverified_template_record_is_manual_review_only():
    result = evaluate_real_seed_record_admission(
        _template_record(
            demo_or_real_flag="user_supplied_unverified",
            provenance_status="user_supplied_needs_review",
            manual_review_status="needs_manual_review",
            allowed_usage_scope="manual_review_only",
        )
    )

    assert result["admission_status"] == "manual_review_only"
    assert result["allowed"] is False


def test_source_present_but_needs_review_is_not_package_support():
    result = evaluate_real_seed_record_admission(
        _template_record(
            provenance_status="source_present_needs_review",
            manual_review_status="needs_manual_review",
        )
    )

    assert result["admission_status"] == "manual_review_only"
    assert result["allowed"] is False
    assert result["review_required"] is True


def test_conflict_template_record_is_blocked():
    result = evaluate_real_seed_record_admission(
        _template_record(conflict_status="conflicting_sources")
    )

    assert result["admission_status"] == "conflict_needs_review_blocked"
    assert result["allowed"] is False


def test_deprecated_template_records_are_blocked():
    deprecated_flag = evaluate_real_seed_record_admission(
        _template_record(deprecated_flag=True)
    )
    deprecated_source = evaluate_real_seed_record_admission(
        _template_record(provenance_status="deprecated_source")
    )

    assert deprecated_flag["admission_status"] == "deprecated_blocked"
    assert deprecated_flag["allowed"] is False
    assert deprecated_source["admission_status"] == "deprecated_blocked"
    assert deprecated_source["allowed"] is False


def test_unknown_route_scope_is_blocked():
    result = evaluate_real_seed_record_admission(
        _template_record(route_scope="non_plant_or_unknown_route")
    )

    assert result["admission_status"] == "out_of_scope_blocked"
    assert result["allowed"] is False


def test_template_field_vocabulary_alignment():
    record = _template_record()

    assert list(record.keys()) == TEMPLATE_FIELDS


def test_returned_labels_and_notes_avoid_forbidden_claims():
    scenarios = [
        _template_record(),
        _template_record(
            source_url_or_identifier="",
            doi="",
            accession="",
            repository_id="",
            citation_text="",
        ),
        _template_record(demo_or_real_flag="demo_example", provenance_status="demo_only"),
        _template_record(
            demo_or_real_flag="user_supplied_unverified",
            provenance_status="user_supplied_needs_review",
            manual_review_status="needs_manual_review",
        ),
        _template_record(
            provenance_status="source_present_needs_review",
            manual_review_status="needs_manual_review",
        ),
        _template_record(conflict_status="conflicting_sources"),
        _template_record(deprecated_flag=True),
        _template_record(route_scope="non_plant_or_unknown_route"),
    ]

    for record in scenarios:
        _assert_safe_copy(evaluate_real_seed_record_admission(record))
