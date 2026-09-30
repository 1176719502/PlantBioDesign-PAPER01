# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from services import plant_design_domain_schema as schema


def _term(*parts: str) -> str:
    return "".join(parts)


RICE_FORBIDDEN_CONTENT = (
    _term("proto", "col"),
    _term("pri", "mer"),
    _term("synthesis", "-ready"),
    _term("wet lab ", "ready"),
    _term("yield ", "prediction"),
    _term("transformation ", "efficiency"),
    _term("guaran", "teed"),
    _term("vali", "dated"),
)

FORBIDDEN_FIELD_FRAGMENTS = (
    "final_component",
    "best_component",
    "recommended_component",
)


def _assert_plain_data(value: object) -> None:
    assert not hasattr(value, "__dataclass_fields__")
    if isinstance(value, dict):
        for key, nested in value.items():
            assert isinstance(key, str)
            _assert_plain_data(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_plain_data(nested)
    else:
        assert value is None or isinstance(value, (str, int, float, bool))


def _assert_no_field_fragment(value: object, fragment: str) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            assert fragment not in key.casefold()
            _assert_no_field_fragment(nested, fragment)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_field_fragment(nested, fragment)


def _stable_keys() -> dict[str, list[str]]:
    return {
        "project": [
            "project_id",
            "project_name",
            "raw_user_request",
            "project_status",
            "source_status",
            "notes",
        ],
        "intent": [
            "intent_id",
            "project_id",
            "raw_user_request",
            "target_name",
            "target_type",
            "plant_host",
            "tissue_or_context",
            "design_purpose",
            "handoff_goal",
            "scope_status",
            "missing_fields",
            "ai_output_status",
            "manual_review_required",
        ],
        "context": [
            "context_id",
            "project_id",
            "plant_species",
            "cultivar_or_variety",
            "tissue_or_organ",
            "expression_context",
            "subcellular_localization",
            "target_product_type",
            "uncertainty_flags",
            "review_status",
        ],
        "evidence": [
            "evidence_id",
            "project_id",
            "source_type",
            "title",
            "source_reference",
            "related_species",
            "related_component_ids",
            "related_context_ids",
            "summary",
            "source_status",
            "review_status",
        ],
        "component": [
            "component_id",
            "component_name",
            "component_type",
            "source_species",
            "sequence_status",
            "source_reference",
            "compatible_contexts",
            "evidence_ids",
            "review_status",
            "manual_notes",
        ],
        "knowledge": [
            "knowledge_id",
            "knowledge_type",
            "title",
            "plant_scope",
            "component_scope",
            "design_context_scope",
            "summary",
            "source_evidence_ids",
            "review_status",
        ],
        "draft": [
            "draft_id",
            "project_id",
            "context_id",
            "intent_id",
            "route_template_id",
            "draft_status",
            "slot_ids",
            "review_item_ids",
            "manual_review_required",
        ],
        "slot": [
            "slot_id",
            "draft_id",
            "slot_type",
            "label",
            "required",
            "selected_component_id",
            "candidate_component_ids",
            "evidence_ids",
            "slot_status",
            "missing_reason",
            "manual_review_required",
        ],
        "review": [
            "review_item_id",
            "project_id",
            "draft_id",
            "review_type",
            "severity",
            "message",
            "related_object_ids",
            "status",
            "manual_review_required",
        ],
        "report": [
            "report_block_id",
            "project_id",
            "block_type",
            "title",
            "summary",
            "rows",
            "source_object_ids",
            "ai_output_status",
            "review_status",
        ],
        "handoff": [
            "package_id",
            "project_id",
            "package_version",
            "design_intent_id",
            "context_id",
            "evidence_ids",
            "component_ids",
            "construct_draft_id",
            "review_item_ids",
            "report_block_ids",
            "package_status",
            "boundary_statements",
            "identity",
        ],
    }


def test_builders_return_plain_dicts_with_stable_keys() -> None:
    records = {
        "project": schema.build_project_record(project_id="p1"),
        "intent": schema.build_design_intent_record(intent_id="i1", project_id="p1"),
        "context": schema.build_plant_design_context_record(context_id="c1", project_id="p1"),
        "evidence": schema.build_evidence_record(evidence_id="e1", project_id="p1"),
        "component": schema.build_component_asset_record(component_id="cmp1"),
        "knowledge": schema.build_knowledge_record(knowledge_id="k1"),
        "draft": schema.build_construct_draft_record(draft_id="d1"),
        "slot": schema.build_construct_slot_record(slot_id="s1", draft_id="d1"),
        "review": schema.build_review_item_record(review_item_id="r1"),
        "report": schema.build_report_block_record(report_block_id="b1"),
        "handoff": schema.build_handoff_package_record(package_id="pkg1"),
    }

    for name, record in records.items():
        assert isinstance(record, dict)
        assert list(record) == _stable_keys()[name]
        _assert_plain_data(record)


def test_missing_optional_fields_get_safe_defaults() -> None:
    intent = schema.build_design_intent_record()
    context = schema.build_plant_design_context_record()
    evidence = schema.build_evidence_record()
    package = schema.build_handoff_package_record()

    assert intent["intent_id"] == ""
    assert intent["missing_fields"] == []
    assert intent["ai_output_status"] == "draft"
    assert intent["manual_review_required"] is True
    assert context["uncertainty_flags"] == []
    assert evidence["related_component_ids"] == []
    assert package["boundary_statements"] == list(schema.DEFAULT_BOUNDARY_STATEMENTS)


def test_ai_output_status_accepts_r97_values() -> None:
    for status in schema.AI_OUTPUT_STATUSES:
        report = schema.build_report_block_record(ai_output_status=status)
        intent = schema.build_design_intent_record(ai_output_status=status)
        assert report["ai_output_status"] == status
        assert intent["ai_output_status"] == status


def test_blocked_and_safety_status_values_do_not_generate_wet_lab_content() -> None:
    intent = schema.build_design_intent_record(
        scope_status="blocked_wet_lab_execution",
        ai_output_status="blocked_claim",
    )
    slot = schema.build_construct_slot_record(slot_status="blocked")
    package = schema.build_handoff_package_record(package_status="not_eligible_boundary_review")

    text = f"{intent} {slot} {package}".casefold()
    assert intent["scope_status"] == "blocked_wet_lab_execution"
    assert slot["slot_status"] == "blocked"
    assert package["package_status"] == "not_eligible_boundary_review"
    for phrase in RICE_FORBIDDEN_CONTENT:
        assert phrase not in text


def test_construct_draft_references_slots_without_final_component_selection() -> None:
    slots = [
        schema.build_construct_slot_record(
            slot_id="slot-cds",
            draft_id="draft-1",
            candidate_component_ids=["component-placeholder-cds"],
            slot_status="candidate_recorded",
        ),
        schema.build_construct_slot_record(slot_id="slot-vector", draft_id="draft-1"),
    ]
    draft = schema.build_construct_draft_record(
        draft_id="draft-1",
        slot_ids=[slot["slot_id"] for slot in slots],
    )

    assert draft["slot_ids"] == ["slot-cds", "slot-vector"]
    assert slots[0]["candidate_component_ids"] == ["component-placeholder-cds"]
    assert all(slot["selected_component_id"] == "" for slot in slots)


def test_handoff_package_references_report_blocks_and_review_items() -> None:
    package = schema.build_handoff_package_record(
        package_id="pkg-r98",
        project_id="project-r98",
        review_item_ids=["review-1", "review-2"],
        report_block_ids=["report-1"],
        package_status="eligible_for_company_review_draft",
    )

    assert package["review_item_ids"] == ["review-1", "review-2"]
    assert package["report_block_ids"] == ["report-1"]
    assert package["package_status"] == "eligible_for_company_review_draft"


def test_rice_albumin_like_seed_bundle_has_expected_review_structure() -> None:
    bundle = schema.build_rice_albumin_like_domain_seed()

    assert bundle["schema_version"] == schema.DOMAIN_SCHEMA_VERSION
    assert bundle["project"]["project_id"] == "r98-rice-albumin-like-project"
    assert bundle["design_intent"]["plant_host"] == "Oryza sativa rice"
    assert bundle["design_intent"]["tissue_or_context"] == "seed"
    assert bundle["design_intent"]["target_name"] == "albumin-like protein"
    assert bundle["design_intent"]["handoff_goal"] == "company-facing design evaluation package"
    assert bundle["plant_design_context"]["plant_species"] == "Oryza sativa rice"
    assert bundle["plant_design_context"]["tissue_or_organ"] == "seed"
    assert bundle["construct_draft"]["slot_ids"] == [slot["slot_id"] for slot in bundle["construct_slots"]]
    assert bundle["handoff_package"]["report_block_ids"] == [
        block["report_block_id"] for block in bundle["report_blocks"]
    ]
    assert bundle["handoff_package"]["review_item_ids"] == [
        item["review_item_id"] for item in bundle["review_items"]
    ]
    assert bundle["component_assets"]
    assert bundle["evidence_records"]
    assert bundle["review_items"]
    _assert_plain_data(bundle)


def test_rice_albumin_like_seed_bundle_is_manual_review_or_draft_status() -> None:
    bundle = schema.build_rice_albumin_like_domain_seed()

    assert bundle["project"]["project_status"] == "manual_review_required"
    assert bundle["design_intent"]["ai_output_status"] == "needs_manual_review"
    assert bundle["construct_draft"]["draft_status"] == "manual_review_required"
    assert bundle["handoff_package"]["package_status"] == "manual_review_required"
    assert bundle["design_intent"]["manual_review_required"] is True
    assert bundle["construct_draft"]["manual_review_required"] is True


def test_rice_albumin_like_seed_bundle_does_not_contain_forbidden_content() -> None:
    bundle = schema.build_rice_albumin_like_domain_seed()
    text = str(bundle).casefold()

    for phrase in RICE_FORBIDDEN_CONTENT:
        assert phrase not in text

    for fragment in FORBIDDEN_FIELD_FRAGMENTS:
        _assert_no_field_fragment(bundle, fragment)

    assert "documentation-only" in text
    assert all(slot["selected_component_id"] == "" for slot in bundle["construct_slots"])


def test_unknown_status_values_fall_back_to_safe_defaults() -> None:
    values: dict[str, Any] = {
        "project": schema.build_project_record(project_status="unknown")["project_status"],
        "intent_scope": schema.build_design_intent_record(scope_status="unknown")["scope_status"],
        "context": schema.build_plant_design_context_record(review_status="unknown")["review_status"],
        "source": schema.build_evidence_record(source_status="unknown")["source_status"],
        "slot": schema.build_construct_slot_record(slot_status="unknown")["slot_status"],
        "handoff": schema.build_handoff_package_record(package_status="unknown")["package_status"],
    }

    assert values == {
        "project": "draft",
        "intent_scope": "plant_supported_design_review",
        "context": "manual_review_required",
        "source": "placeholder",
        "slot": "missing",
        "handoff": "manual_review_required",
    }
