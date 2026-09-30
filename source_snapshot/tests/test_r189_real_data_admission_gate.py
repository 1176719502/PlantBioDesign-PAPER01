from services.plant_real_data_admission_gate import evaluate_real_seed_record_admission


def _eligible_record(**overrides):
    record = {
        "record_id": "R189_TEST_RECORD",
        "record_type": "plant_component_record",
        "display_name": "R189 test plant component",
        "route_scope": "plant_protein_expression_review",
        "source_url_or_identifier": "https://example.invalid/source-record",
        "doi": "",
        "accession": "",
        "repository_id": "",
        "citation_text": "",
        "provenance_status": "source_verified",
        "manual_review_status": "reviewed_for_documentation",
        "allowed_usage_scope": "package_draft_support",
        "demo_or_real_flag": "literature_derived",
        "conflict_status": "no_known_conflict",
        "deprecated_flag": False,
    }
    record.update(overrides)
    return record


def test_fully_eligible_package_support_record_is_allowed():
    result = evaluate_real_seed_record_admission(_eligible_record())

    assert result["admission_status"] == "allowed_for_package_draft_support"
    assert result["allowed"] is True
    assert result["user_visible_label"] == "已人工审查，仅限文档整理"
    assert result["review_required"] is False


def test_missing_all_source_identifiers_is_blocked():
    result = evaluate_real_seed_record_admission(
        _eligible_record(
            source_url_or_identifier="",
            doi="",
            accession="",
            repository_id="",
            citation_text="",
        )
    )

    assert result["admission_status"] == "missing_source_blocked"
    assert result["allowed"] is False
    assert result["provenance_status"] == "missing_source"
    assert result["user_visible_label"] == "来源待补充"


def test_demo_example_is_demo_only_for_package_support():
    result = evaluate_real_seed_record_admission(
        _eligible_record(
            demo_or_real_flag="demo_example",
            provenance_status="demo_only",
            allowed_usage_scope="demo_only",
        )
    )

    assert result["admission_status"] == "demo_only"
    assert result["allowed"] is False
    assert result["user_visible_label"] == "示例 / 演示"


def test_user_supplied_unverified_is_manual_review_only():
    result = evaluate_real_seed_record_admission(
        _eligible_record(
            demo_or_real_flag="user_supplied_unverified",
            provenance_status="user_supplied_needs_review",
            allowed_usage_scope="manual_review_only",
        )
    )

    assert result["admission_status"] == "manual_review_only"
    assert result["allowed"] is False
    assert result["user_visible_label"] == "用户提供，待复核"


def test_source_present_needs_review_is_not_package_support():
    result = evaluate_real_seed_record_admission(
        _eligible_record(
            provenance_status="source_present_needs_review",
            allowed_usage_scope="manual_review_only",
        )
    )

    assert result["admission_status"] == "manual_review_only"
    assert result["allowed"] is False
    assert result["user_visible_label"] == "已记录来源，待人工确认"


def test_not_reviewed_or_needs_manual_review_is_not_package_support():
    not_reviewed = evaluate_real_seed_record_admission(
        _eligible_record(manual_review_status="not_reviewed")
    )
    needs_review = evaluate_real_seed_record_admission(
        _eligible_record(manual_review_status="needs_manual_review")
    )

    assert not_reviewed["admission_status"] == "manual_review_only"
    assert not_reviewed["allowed"] is False
    assert needs_review["admission_status"] == "manual_review_only"
    assert needs_review["allowed"] is False


def test_conflicting_sources_are_blocked():
    result = evaluate_real_seed_record_admission(
        _eligible_record(conflict_status="conflicting_sources")
    )

    assert result["admission_status"] == "conflict_needs_review_blocked"
    assert result["allowed"] is False
    assert result["user_visible_label"] == "冲突待复核"


def test_deprecated_flag_is_blocked():
    result = evaluate_real_seed_record_admission(_eligible_record(deprecated_flag=True))

    assert result["admission_status"] == "deprecated_blocked"
    assert result["allowed"] is False
    assert result["user_visible_label"] == "已弃用"


def test_unknown_route_scope_is_out_of_scope_blocked():
    result = evaluate_real_seed_record_admission(_eligible_record(route_scope="microbial_review"))

    assert result["admission_status"] == "out_of_scope_blocked"
    assert result["allowed"] is False


def test_malformed_input_is_blocked():
    result = evaluate_real_seed_record_admission(None)
    missing_identity = evaluate_real_seed_record_admission(_eligible_record(record_id=""))

    assert result["admission_status"] == "malformed_record_blocked"
    assert result["allowed"] is False
    assert missing_identity["admission_status"] == "malformed_record_blocked"
    assert missing_identity["allowed"] is False


def test_beginner_preview_can_allow_labeled_demo_only():
    result = evaluate_real_seed_record_admission(
        _eligible_record(
            demo_or_real_flag="demo_example",
            provenance_status="demo_only",
            allowed_usage_scope="beginner_preview",
        ),
        intended_usage="beginner_preview",
    )

    assert result["admission_status"] == "allowed_for_beginner_preview"
    assert result["allowed"] is True
    assert result["demo_or_real_flag"] == "demo_example"
    assert result["user_visible_label"] == "示例 / 演示"
    assert "source-backed real data" in result["safety_notes"]


def test_safety_notes_avoid_forbidden_claims():
    forbidden_claims = [
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
    scenarios = [
        _eligible_record(),
        _eligible_record(
            source_url_or_identifier="",
            doi="",
            accession="",
            repository_id="",
            citation_text="",
        ),
        _eligible_record(demo_or_real_flag="demo_example", provenance_status="demo_only"),
        _eligible_record(conflict_status="conflicting_sources"),
        _eligible_record(deprecated_flag=True),
        _eligible_record(route_scope="unknown"),
    ]

    notes = "\n".join(
        evaluate_real_seed_record_admission(record)["safety_notes"] for record in scenarios
    ).lower()

    for claim in forbidden_claims:
        assert claim not in notes
