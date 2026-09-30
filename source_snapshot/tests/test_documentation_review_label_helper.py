from __future__ import annotations

from services.documentation_review_label_helper import (
    NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL,
    REVIEW_NEXT_COLUMN_LABEL,
    WHERE_TO_REVIEW_NEXT_KEY,
    format_review_next_label,
    review_next_body,
    review_next_table_value,
)


def test_format_review_next_label_adds_prefix_once() -> None:
    assert format_review_next_label("Expression Constructs") == "Review next: Expression Constructs"
    assert (
        format_review_next_label("Review next: Candidate Evidence Review Matrix")
        == "Review next: Candidate Evidence Review Matrix"
    )
    assert format_review_next_label("  review next: Project Review Report  ") == "review next: Project Review Report"


def test_format_review_next_label_uses_fallback_without_visible_claims() -> None:
    assert format_review_next_label("", "Project review handoff center") == (
        "Review next: Project review handoff center"
    )
    assert format_review_next_label(None) == ""


def test_review_next_body_removes_prefix_for_plain_text_labels() -> None:
    assert review_next_body("Review next: Project handoff review sheet") == "Project handoff review sheet"
    assert review_next_body("Project Review Follow-up Index") == "Project Review Follow-up Index"


def test_review_next_table_value_preserves_compatible_key_contract() -> None:
    row = {WHERE_TO_REVIEW_NEXT_KEY: "Host / Chassis Context Summary"}

    assert review_next_table_value(row) == "Review next: Host / Chassis Context Summary"
    assert REVIEW_NEXT_COLUMN_LABEL == "Review next"
    assert NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL == "Next documentation review action"
