# -*- coding: utf-8 -*-
from __future__ import annotations

from services.plant_ai_guided_domain_chain import build_rice_albumin_like_domain_chain
from services.plant_ai_intake_mock_parser import RICE_ALBUMIN_LIKE_REQUEST
from services.plant_company_handoff_draft_assembler import assemble_company_handoff_draft


def _term(*parts: str) -> str:
    return "".join(parts)


EXPECTED_BUNDLE_KEYS = [
    "chain_version",
    "batch",
    "input_request",
    "scope_decision",
    "design_intent",
    "plant_context",
    "evidence_placeholders",
    "component_placeholders",
    "construct_draft",
    "construct_slots",
    "review_gap_items",
    "report_block_placeholders",
    "handoff_package_skeleton",
    "boundary_statements",
    "status",
]

EXPECTED_PACKAGE_KEYS = [
    "assembler_version",
    "batch",
    "package_label",
    "boundary_labels",
    "source_chain_version",
    "source_request",
    "sections",
    "manual_review_required",
    "package_status",
]

EXPECTED_SECTION_IDS = [
    "cover_title",
    "project_summary",
    "original_user_request",
    "parsed_design_intent",
    "plant_design_context",
    "evidence_source_placeholder_matrix",
    "component_candidate_slot_table",
    "construct_draft_slot_scaffold",
    "review_gap_items",
    "manual_review_checklist",
    "boundary_statement",
    "version_identity_placeholder",
]

EXPECTED_MISSING_FIELDS = [
    "CDS/source/version",
    "exact tissue/development context if needed",
    "subcellular localization",
    "evidence references",
    "component provenance",
    "vector/backbone context",
]

FORBIDDEN_OUTPUT_PHRASES = (
    _term("wet", "-lab protocol"),
    _term("experimental ", "protocol"),
    _term("primer ", "design"),
    _term("primer ", "sequence"),
    _term("final ", "sequence"),
    _term("synthesis", "-ready"),
    _term("transformation ", "efficiency"),
    _term("yield ", "prediction"),
    _term("guaran", "teed"),
    _term("valid", "ated"),
    _term("wet lab ", "ready"),
    _term("culture ", "conditions"),
    _term("cloning ", "steps"),
)

ALLOWED_NEGATIVE_BOUNDARY_PHRASES = (
    "not an experimental protocol",
)


def _sections_by_id(package: dict[str, object]) -> dict[str, dict[str, object]]:
    return {section["section_id"]: section for section in package["sections"]}  # type: ignore[index]


def _current_snapshot() -> tuple[dict[str, object], dict[str, object]]:
    bundle = build_rice_albumin_like_domain_chain(RICE_ALBUMIN_LIKE_REQUEST)
    package = assemble_company_handoff_draft(bundle)
    return bundle, package


def _output_text_without_allowed_negative_boundaries(value: object) -> str:
    text = str(value).casefold()
    for allowed in ALLOWED_NEGATIVE_BOUNDARY_PHRASES:
        text = text.replace(allowed, "")
    return text


def test_r103_snapshot_calls_r99_to_r102_chain_for_fixed_example() -> None:
    bundle, package = _current_snapshot()

    assert list(bundle) == EXPECTED_BUNDLE_KEYS
    assert list(package) == EXPECTED_PACKAGE_KEYS
    assert bundle["input_request"] == RICE_ALBUMIN_LIKE_REQUEST
    assert package["source_request"] == RICE_ALBUMIN_LIKE_REQUEST
    assert bundle["scope_decision"]["raw_user_request"] == RICE_ALBUMIN_LIKE_REQUEST  # type: ignore[index]
    assert package["source_chain_version"] == bundle["chain_version"]


def test_r103_snapshot_preserves_safety_router_scope_allowed_and_blocked_outputs() -> None:
    bundle, _package = _current_snapshot()
    scope_decision = bundle["scope_decision"]

    assert scope_decision["scope_category"] == "company_handoff_request"  # type: ignore[index]
    assert scope_decision["manual_review_required"] is True  # type: ignore[index]
    assert scope_decision["allowed_outputs"] == [  # type: ignore[index]
        "design_intent",
        "plant_design_context",
        "evidence_placeholders",
        "component_slots",
        "construct_draft_slots",
        "review_items",
        "report_blocks",
        "company_handoff_draft",
    ]
    assert set(scope_decision["blocked_outputs"]) >= {  # type: ignore[index]
        "wet_lab_protocol",
        "cloning_steps",
        "transformation_steps",
        "culture_conditions",
        "primer_design",
        "synthesis_ready_sequence",
        "final_construct_recommendation",
        "component_ranking",
        "yield_prediction",
        "success_guarantee",
        "wet_lab_readiness_claim",
    }


def test_r103_snapshot_package_contains_expected_handoff_sections() -> None:
    _bundle, package = _current_snapshot()

    assert [section["section_id"] for section in package["sections"]] == EXPECTED_SECTION_IDS  # type: ignore[index]
    assert package["package_label"] == "company-facing design evaluation draft"
    assert package["boundary_labels"] == [
        "not an experimental protocol",
        "not a final construct design",
        "manual expert review required",
    ]


def test_r103_snapshot_contains_rice_seed_albumin_company_context() -> None:
    bundle, package = _current_snapshot()
    sections = _sections_by_id(package)
    readable = str([bundle["design_intent"], bundle["plant_context"], sections["project_summary"]]).casefold()

    assert "rice" in readable
    assert "seed" in readable
    assert "albumin-like" in readable
    assert "company-facing design evaluation package" in readable
    assert bundle["design_intent"]["target_name"] == "albumin-like protein"  # type: ignore[index]
    assert bundle["plant_context"]["plant_species"] == "rice"  # type: ignore[index]
    assert bundle["plant_context"]["tissue_or_organ"] == "seed"  # type: ignore[index]


def test_r103_snapshot_preserves_placeholders_slots_reports_and_missing_fields() -> None:
    bundle, package = _current_snapshot()
    sections = _sections_by_id(package)

    assert len(bundle["evidence_placeholders"]) == 3  # type: ignore[arg-type]
    assert len(bundle["component_placeholders"]) == 3  # type: ignore[arg-type]
    assert len(bundle["construct_slots"]) == 6  # type: ignore[arg-type]
    assert len(bundle["report_block_placeholders"]) == 3  # type: ignore[arg-type]
    assert bundle["design_intent"]["missing_fields"] == EXPECTED_MISSING_FIELDS  # type: ignore[index]
    assert len(sections["evidence_source_placeholder_matrix"]["rows"]) == 3
    assert len(sections["component_candidate_slot_table"]["rows"]) == 6
    assert len(sections["construct_draft_slot_scaffold"]["rows"]) == 6
    assert sections["review_gap_items"]["rows"]


def test_r103_snapshot_requires_manual_review_across_bundle_and_package() -> None:
    bundle, package = _current_snapshot()
    sections = _sections_by_id(package)

    assert bundle["status"]["manual_review_required"] is True  # type: ignore[index]
    assert bundle["construct_draft"]["draft_status"] == "manual_review_required"  # type: ignore[index]
    assert package["manual_review_required"] is True
    assert package["package_status"] == "manual_review_required"
    assert all(section["manual_review_required"] is True for section in package["sections"])  # type: ignore[index]
    assert all(row["status"] == "manual_review_required" for row in sections["manual_review_checklist"]["rows"])


def test_r103_snapshot_boundary_statements_are_visible_and_negative_only() -> None:
    bundle, package = _current_snapshot()
    sections = _sections_by_id(package)
    boundary_text = str([bundle["boundary_statements"], sections["boundary_statement"]["rows"]]).casefold()

    assert "documentation-only" in boundary_text
    assert "manual review" in boundary_text
    assert "not an experimental protocol" in boundary_text
    assert "not a final construct design" in boundary_text
    assert "manual expert review required" in boundary_text


def test_r103_snapshot_does_not_contain_forbidden_positive_or_operational_content() -> None:
    bundle, package = _current_snapshot()
    output_text = _output_text_without_allowed_negative_boundaries([bundle, package])

    for phrase in FORBIDDEN_OUTPUT_PHRASES:
        assert phrase not in output_text
