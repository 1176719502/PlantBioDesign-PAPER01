from services.plant_real_data_admission_gate import evaluate_real_seed_record_admission


TEMPLATE_SECTIONS = [
    "evidence_entry_metadata",
    "source_identity",
    "evidence_scope",
    "provenance_and_review",
    "admission_gate_preflight",
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


def _manual_evidence_fixture(**section_overrides):
    fixture = {
        "evidence_entry_metadata": {
            "evidence_entry_id": "TODO_EVIDENCE_ENTRY_ID",
            "created_by_or_imported_by": "TODO_CREATED_BY",
            "created_at": "TODO_CREATED_AT",
            "updated_at": "TODO_UPDATED_AT",
            "import_batch_id": "TODO_IMPORT_BATCH_ID",
            "import_mode": "manual_template_entry",
            "notes_for_curator": "TODO_CURATOR_NOTE",
        },
        "source_identity": {
            "source_type": "user_supplied",
            "source_title": "TODO_SOURCE_TITLE",
            "source_url_or_identifier": "TODO_SOURCE_URL_OR_IDENTIFIER",
            "doi": "",
            "accession": "",
            "repository_id": "",
            "citation_text": "TODO_CITATION_TEXT",
            "source_date_or_version": "TODO_SOURCE_DATE_OR_VERSION",
            "source_quote_or_evidence_note": "TODO_EVIDENCE_NOTE",
        },
        "evidence_scope": {
            "route_scope": "plant_protein_expression_review",
            "organism_scope": "TODO_ORGANISM_SCOPE",
            "host_context": "TODO_HOST_CONTEXT",
            "record_family": "TODO_RECORD_FAMILY",
            "component_type_or_record_family": "TODO_COMPONENT_TYPE",
            "related_record_id": "TODO_RELATED_RECORD_ID",
            "related_display_name": "TODO_RELATED_LABEL",
            "claim_type": "evidence_note",
            "claim_summary": "TODO_EVIDENCE_NOTE",
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
            "reviewer_note": "TODO_CURATOR_NOTE",
        },
        "admission_gate_preflight": {
            "intended_usage": "manual_review_only",
            "expected_initial_gate_result": "manual_review_required",
            "blocking_reasons_expected": [
                "source_review_required",
                "manual_review_required",
            ],
            "review_required": True,
            "notes_for_gate_operator": "TODO_CURATOR_NOTE",
        },
    }

    for section, overrides in section_overrides.items():
        fixture[section].update(overrides)
    return fixture


def convert_manual_evidence_fixture_to_admission_record(fixture):
    metadata = fixture["evidence_entry_metadata"]
    source = fixture["source_identity"]
    scope = fixture["evidence_scope"]
    review = fixture["provenance_and_review"]

    return {
        "record_id": metadata["evidence_entry_id"],
        "record_type": "manual_evidence_entry",
        "display_name": source["source_title"],
        "route_scope": scope["route_scope"],
        "source_url_or_identifier": source["source_url_or_identifier"],
        "doi": source["doi"],
        "accession": source["accession"],
        "repository_id": source["repository_id"],
        "citation_text": source["citation_text"],
        "source_type": source["source_type"],
        "provenance_status": review["provenance_status"],
        "manual_review_status": review["manual_review_status"],
        "allowed_usage_scope": review["allowed_usage_scope"],
        "demo_or_real_flag": review["demo_or_real_flag"],
        "conflict_status": review["conflict_status"],
        "deprecated_flag": review["deprecated_flag"],
    }


def _evaluate(fixture, *, intended_usage="package_draft_support"):
    record = convert_manual_evidence_fixture_to_admission_record(fixture)
    return evaluate_real_seed_record_admission(record, intended_usage=intended_usage)


def _assert_copy_safe(result):
    copy_surface = f"{result['user_visible_label']}\n{result['safety_notes']}".lower()
    for fragment in FORBIDDEN_COPY_FRAGMENTS:
        assert fragment not in copy_surface


def test_template_section_vocabulary_alignment():
    fixture = _manual_evidence_fixture()

    assert list(fixture.keys()) == TEMPLATE_SECTIONS


def test_source_present_manual_evidence_defaults_to_review_required():
    fixture = _manual_evidence_fixture(
        source_identity={
            "source_url_or_identifier": "TODO_SOURCE_URL_OR_IDENTIFIER",
            "citation_text": "TODO_CITATION_TEXT",
        },
        provenance_and_review={
            "provenance_status": "source_present_needs_review",
            "manual_review_status": "needs_manual_review",
            "allowed_usage_scope": "manual_review_only",
            "demo_or_real_flag": "user_supplied_unverified",
        },
    )
    record = convert_manual_evidence_fixture_to_admission_record(fixture)
    result = evaluate_real_seed_record_admission(record)

    assert record["provenance_status"] != "source_verified"
    assert record["manual_review_status"] != "reviewed_for_documentation"
    assert record["allowed_usage_scope"] != "package_draft_support"
    assert result["admission_status"] == "manual_review_only"
    assert result["allowed"] is False
    assert result["review_required"] is True
    assert result["admission_status"] != "allowed_for_package_draft_support"


def test_missing_source_manual_evidence_fails_closed():
    fixture = _manual_evidence_fixture(
        source_identity={
            "source_url_or_identifier": "",
            "doi": "",
            "accession": "",
            "repository_id": "",
            "citation_text": "",
        },
        provenance_and_review={
            "provenance_status": "missing_source",
            "manual_review_status": "needs_manual_review",
            "allowed_usage_scope": "manual_review_only",
            "demo_or_real_flag": "unverified",
        },
    )

    result = _evaluate(fixture)

    assert result["admission_status"] == "missing_source_blocked"
    assert result["allowed"] is False


def test_user_supplied_evidence_cannot_become_verified_automatically():
    fixture = _manual_evidence_fixture(
        source_identity={"source_type": "user_supplied"},
        provenance_and_review={
            "demo_or_real_flag": "user_supplied_unverified",
            "provenance_status": "user_supplied_needs_review",
            "manual_review_status": "needs_manual_review",
        },
    )

    result = _evaluate(fixture)

    assert result["admission_status"] == "manual_review_only"
    assert result["allowed"] is False
    assert result["review_required"] is True
    assert result["provenance_status"] != "source_verified"
    assert result["manual_review_status"] == "needs_manual_review"


def test_demo_example_evidence_remains_demo_only():
    package_fixture = _manual_evidence_fixture(
        provenance_and_review={
            "demo_or_real_flag": "demo_example",
            "provenance_status": "demo_only",
            "allowed_usage_scope": "demo_only",
        },
    )
    preview_fixture = _manual_evidence_fixture(
        provenance_and_review={
            "demo_or_real_flag": "demo_example",
            "provenance_status": "demo_only",
            "allowed_usage_scope": "beginner_preview",
        },
    )

    package_result = _evaluate(package_fixture)
    preview_result = _evaluate(preview_fixture, intended_usage="beginner_preview")

    assert package_result["admission_status"] == "demo_only"
    assert package_result["allowed"] is False
    assert preview_result["admission_status"] == "allowed_for_beginner_preview"
    assert preview_result["allowed"] is True
    assert preview_result["demo_or_real_flag"] == "demo_example"
    assert "source-backed real data" in preview_result["safety_notes"]


def test_conflict_evidence_blocks_package_draft():
    conflicting_sources = _evaluate(
        _manual_evidence_fixture(
            provenance_and_review={"conflict_status": "conflicting_sources"}
        )
    )
    route_scope_mismatch = _evaluate(
        _manual_evidence_fixture(
            provenance_and_review={"conflict_status": "route_scope_mismatch"}
        )
    )

    assert conflicting_sources["admission_status"] == "conflict_needs_review_blocked"
    assert conflicting_sources["allowed"] is False
    assert route_scope_mismatch["admission_status"] == "conflict_needs_review_blocked"
    assert route_scope_mismatch["allowed"] is False


def test_deprecated_evidence_blocks_package_draft():
    deprecated_flag = _evaluate(
        _manual_evidence_fixture(provenance_and_review={"deprecated_flag": True})
    )
    deprecated_source = _evaluate(
        _manual_evidence_fixture(
            provenance_and_review={"provenance_status": "deprecated_source"}
        )
    )

    assert deprecated_flag["admission_status"] == "deprecated_blocked"
    assert deprecated_flag["allowed"] is False
    assert deprecated_source["admission_status"] == "deprecated_blocked"
    assert deprecated_source["allowed"] is False


def test_preflight_section_cannot_override_the_admission_gate():
    fixture = _manual_evidence_fixture(
        provenance_and_review={
            "provenance_status": "source_present_needs_review",
            "manual_review_status": "needs_manual_review",
            "allowed_usage_scope": "manual_review_only",
            "demo_or_real_flag": "user_supplied_unverified",
        },
        admission_gate_preflight={
            "intended_usage": "package_draft_support",
            "expected_initial_gate_result": "allowed_for_package_draft_support",
            "review_required": False,
        },
    )

    result = _evaluate(fixture)

    assert result["admission_status"] == "manual_review_only"
    assert result["allowed"] is False
    assert result["review_required"] is True


def test_placeholder_safety_for_manual_evidence_fixtures():
    fixture_text = repr(
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
        ]
    )
    blocked_fragments = [
        "1" + "0.",
        "PM" + "ID",
        "NC" + "BI",
        "Gen" + "Bank",
        "Add" + "gene",
        "XP" + "_",
        "NP" + "_",
        "NM" + "_",
    ]

    for placeholder in [
        "TODO_SOURCE_TITLE",
        "TODO_SOURCE_URL_OR_IDENTIFIER",
        "TODO_CITATION_TEXT",
        "TODO_EVIDENCE_NOTE",
        "TODO_CURATOR_NOTE",
    ]:
        assert placeholder in fixture_text
    for fragment in blocked_fragments:
        assert fragment not in fixture_text


def test_returned_labels_and_safety_notes_avoid_forbidden_claims():
    fixtures = [
        _manual_evidence_fixture(),
        _manual_evidence_fixture(
            source_identity={
                "source_url_or_identifier": "",
                "doi": "",
                "accession": "",
                "repository_id": "",
                "citation_text": "",
            },
            provenance_and_review={"provenance_status": "missing_source"},
        ),
        _manual_evidence_fixture(
            provenance_and_review={
                "demo_or_real_flag": "demo_example",
                "provenance_status": "demo_only",
                "allowed_usage_scope": "demo_only",
            }
        ),
        _manual_evidence_fixture(
            provenance_and_review={"conflict_status": "conflicting_sources"}
        ),
        _manual_evidence_fixture(provenance_and_review={"deprecated_flag": True}),
    ]

    for fixture in fixtures:
        _assert_copy_safe(_evaluate(fixture))
