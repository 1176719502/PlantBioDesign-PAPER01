from __future__ import annotations

import pytest

from services.ai_literature_research_service import (
    BOUNDARY_NOTE,
    SECTION_TITLES,
    empty_input_state,
    generate_literature_research_brief,
    unavailable_state,
)

FORBIDDEN_OUTPUT_PHRASES = [
    "recommended",
    "optimal",
    "validated",
    "approved",
    "compatible",
    "ready for synthesis",
    "ready for wet lab",
    "experimentally confirmed",
]


def test_empty_input_state_is_bounded_and_does_not_generate_brief() -> None:
    state = empty_input_state()

    assert "Enter a research target" in state["title"]
    assert "albumin" in state["body"]
    with pytest.raises(ValueError):
        generate_literature_research_brief("   ")


def test_albumin_example_generates_safe_draft_brief() -> None:
    brief = generate_literature_research_brief("albumin / 白蛋白")
    markdown = brief.as_markdown()

    assert brief.target == "albumin / 白蛋白"
    assert brief.requires_source_review is True
    assert "Draft research brief" in markdown
    assert "source review needed" in markdown.lower()
    assert "human review" in markdown.lower()
    assert "albumin" in markdown.lower()
    assert "白蛋白" in markdown
    assert "No external source lookup was performed" in markdown
    assert "host, promoter, construct, protocol, or wet-lab setup guidance" in markdown


def test_generated_brief_contains_expected_sections() -> None:
    brief = generate_literature_research_brief("human serum albumin")
    markdown = brief.as_markdown()

    for title in SECTION_TITLES:
        assert f"## {title}" in markdown
        assert brief.sections[title], title


def test_generic_target_uses_same_documentation_only_structure() -> None:
    brief = generate_literature_research_brief("example protein family")
    markdown = brief.as_markdown()

    assert "example protein family" in markdown
    assert "local deterministic stub" in markdown
    assert BOUNDARY_NOTE in markdown
    for title in SECTION_TITLES:
        assert title in brief.sections


def test_no_forbidden_wording_outside_explicit_policy_text() -> None:
    rendered = "\n".join(
        [
            generate_literature_research_brief("albumin").as_markdown(),
            generate_literature_research_brief("example topic").as_markdown(),
            empty_input_state()["title"],
            empty_input_state()["body"],
        ]
    ).lower()

    for phrase in FORBIDDEN_OUTPUT_PHRASES:
        assert phrase not in rendered


def test_unavailable_state_is_bounded() -> None:
    state = unavailable_state()

    assert "unavailable" in state["title"].lower()
    assert "External AI" in state["body"]
    assert "documentation-only" in state["boundary"]
    for phrase in FORBIDDEN_OUTPUT_PHRASES:
        assert phrase not in "\n".join(state.values()).lower()
