from __future__ import annotations

from collections.abc import Mapping
from typing import Any


REVIEW_NEXT_PREFIX = "Review next:"
REVIEW_NEXT_COLUMN_LABEL = "Review next"
NEXT_DOCUMENTATION_REVIEW_ACTION_LABEL = "Next documentation review action"
WHERE_TO_REVIEW_NEXT_KEY = "where_to_review_next"


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def format_review_next_label(value: Any, fallback: str = "") -> str:
    text = _text(value, fallback)
    if not text:
        return ""
    if text.casefold().startswith(REVIEW_NEXT_PREFIX.casefold()):
        return text
    return f"{REVIEW_NEXT_PREFIX} {text}"


def review_next_body(value: Any, fallback: str = "") -> str:
    text = format_review_next_label(value, fallback)
    if text.casefold().startswith(REVIEW_NEXT_PREFIX.casefold()):
        return text[len(REVIEW_NEXT_PREFIX):].strip()
    return text


def review_next_table_value(
    row: Mapping[str, Any],
    *,
    key: str = WHERE_TO_REVIEW_NEXT_KEY,
    fallback: str = "",
) -> str:
    return format_review_next_label(row.get(key), fallback)
