# -*- coding: utf-8 -*-
from __future__ import annotations

from services.plant_ai_guided_domain_chain import build_rice_albumin_like_domain_chain
from services.plant_ai_mock_preview_contracts import HANDOFF_BOUNDARY_LABELS
from services.plant_company_handoff_draft_assembler import assemble_company_handoff_draft


def _term(*parts: str) -> str:
    return "".join(parts)


FORBIDDEN_CONTENT = (
    _term("wet-lab ", "steps"),
    _term("primer ", "design"),
    _term("final ", "sequence"),
    _term("operational ", "parameters"),
    _term("yield ", "claim"),
    _term("success ", "claim"),
    _term("readiness ", "claim"),
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


def _sections_by_id(package: dict[str, object]) -> dict[str, dict[str, object]]:
    return {section["section_id"]: section for section in package["sections"]}  # type: ignore[index]


def test_assembler_returns_required_package_labels() -> None:
    package = assemble_company_handoff_draft()

    assert package["package_label"] == "company-facing design evaluation draft"
    assert package["boundary_labels"] == list(HANDOFF_BOUNDARY_LABELS)
    assert package["manual_review_required"] is True


def test_assembler_contains_required_sections() -> None:
    package = assemble_company_handoff_draft()

    assert [section["section_id"] for section in package["sections"]] == [
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


def test_assembler_preserves_original_request_and_design_intent() -> None:
    package = assemble_company_handoff_draft()
    sections = _sections_by_id(package)

    original_rows = sections["original_user_request"]["rows"]
    summary_rows = sections["project_summary"]["rows"]

    assert "albumin-like protein" in str(original_rows)
    assert {"field": "target", "value": "albumin-like protein"} in summary_rows
    assert {"field": "plant_host", "value": "rice"} in summary_rows
    assert {"field": "tissue_or_context", "value": "seed"} in summary_rows


def test_assembler_builds_evidence_and_slot_tables_from_domain_chain() -> None:
    bundle = build_rice_albumin_like_domain_chain()
    package = assemble_company_handoff_draft(bundle)
    sections = _sections_by_id(package)

    assert len(sections["evidence_source_placeholder_matrix"]["rows"]) == len(bundle["evidence_placeholders"])
    assert len(sections["component_candidate_slot_table"]["rows"]) == len(bundle["construct_slots"])
    assert len(sections["construct_draft_slot_scaffold"]["rows"]) == len(bundle["construct_slots"])
    assert all(row["selected_component_id"] == "" for row in sections["component_candidate_slot_table"]["rows"])


def test_assembler_includes_review_items_and_manual_checklist() -> None:
    package = assemble_company_handoff_draft()
    sections = _sections_by_id(package)

    assert sections["review_gap_items"]["rows"]
    assert len(sections["manual_review_checklist"]["rows"]) >= 5
    assert all(row["status"] == "manual_review_required" for row in sections["manual_review_checklist"]["rows"])


def test_assembler_boundary_statement_is_explicit() -> None:
    package = assemble_company_handoff_draft()
    boundary_text = str(_sections_by_id(package)["boundary_statement"]["rows"]).casefold()

    assert "documentation-only" in boundary_text
    assert "not an experimental protocol" in boundary_text
    assert "not a final construct design" in boundary_text
    assert "manual expert review required" in boundary_text


def test_assembler_identity_placeholder_is_safely_available() -> None:
    package = assemble_company_handoff_draft()
    identity_rows = _sections_by_id(package)["version_identity_placeholder"]["rows"]

    assert {"field": "batch", "value": "v2.7-r102"} in identity_rows
    assert {"field": "documentation_only", "value": True} in identity_rows
    assert {"field": "company_review_draft", "value": True} in identity_rows


def test_assembler_returns_plain_data_only() -> None:
    package = assemble_company_handoff_draft()

    _assert_plain_data(package)


def test_assembler_does_not_output_blocked_operational_content() -> None:
    package = assemble_company_handoff_draft()
    text = str(package).casefold()

    for phrase in FORBIDDEN_CONTENT:
        assert phrase not in text
