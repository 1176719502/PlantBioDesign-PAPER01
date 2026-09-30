from __future__ import annotations

from typing import Any


PLACEHOLDER_REVIEW_VALUES = frozenset(
    {
        "",
        "-",
        "--",
        "n/a",
        "na",
        "none",
        "not applicable",
        "not recorded",
        "not set",
        "not specified",
        "null",
        "tbd",
        "to be determined",
        "unknown",
        "unspecified",
        "no component reference recorded",
        "no curation status recorded",
        "no provenance note recorded",
        "no recorded host / chassis context",
        "no review note recorded",
        "no review status recorded",
        "no source context recorded",
        "no source record linked",
        "no source reference recorded",
        "no source status recorded",
        "no source/provenance identity recorded",
        "no source/reference context recorded",
        "source status not recorded",
        "identifier not recorded",
    }
)


def review_value_text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def is_placeholder_review_value(value: Any) -> bool:
    return review_value_text(value).casefold() in PLACEHOLDER_REVIEW_VALUES


def has_recorded_review_value(value: Any) -> bool:
    return not is_placeholder_review_value(value)


def clean_review_value(value: Any, fallback: str = "") -> str:
    text = review_value_text(value)
    return text if text and not is_placeholder_review_value(text) else fallback
