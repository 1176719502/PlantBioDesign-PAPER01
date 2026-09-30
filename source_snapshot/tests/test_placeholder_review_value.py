from __future__ import annotations

from services.placeholder_review_value import (
    clean_review_value,
    has_recorded_review_value,
    is_placeholder_review_value,
    review_value_text,
)


def test_placeholder_review_values_are_not_recorded_metadata() -> None:
    placeholders = [
        None,
        "",
        "Unknown",
        "TBD",
        "N/A",
        "Not specified",
        "None",
        "No review note recorded",
        "No component reference recorded",
    ]

    for value in placeholders:
        assert is_placeholder_review_value(value)
        assert not has_recorded_review_value(value)
        assert clean_review_value(value, "missing review information") == "missing review information"


def test_recorded_review_value_is_trimmed_and_preserved() -> None:
    value = "  Curator added source context.  "

    assert review_value_text(value) == "Curator added source context."
    assert not is_placeholder_review_value(value)
    assert has_recorded_review_value(value)
    assert clean_review_value(value, "missing review information") == "Curator added source context."
