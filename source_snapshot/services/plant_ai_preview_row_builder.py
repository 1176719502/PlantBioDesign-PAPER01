from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from services.plant_ai_mock_preview_contracts import (
    BLOCKED_OUTPUT_BOUNDARY,
    allowed_output_boundary,
    boundary_statement_rows,
    normalize_boundary_statements,
    output_rows,
    preview_status,
    sequence,
    status_label,
    text,
)


def _join_values(value: Any) -> str:
    items = [text(item) for item in sequence(value)]
    items = [item for item in items if item]
    return ", ".join(items) if items else status_label(value)


def field_rows(pairs: Sequence[tuple[str, Any]]) -> list[dict[str, str]]:
    return [{"Field": label, "Readback": _join_values(value)} for label, value in pairs]


def _boundary_groups(value: Any) -> list[Any]:
    items = sequence(value)
    return items if items else [value]


def build_preview_contract_rows(
    *,
    scope_category: Any,
    allowed_outputs: Any,
    blocked_outputs: Any,
    boundary_statements: Any,
    parsed_intent_pairs: Sequence[tuple[str, Any]] = (),
    persistent: bool = False,
    allowed_output_boundary_label: str | None = None,
) -> dict[str, Any]:
    clean_scope_category = text(scope_category, "safe_conceptual_explanation")
    clean_allowed_outputs = [text(value) for value in sequence(allowed_outputs) if text(value)]
    clean_blocked_outputs = [text(value) for value in sequence(blocked_outputs) if text(value)]
    clean_boundary_statements = normalize_boundary_statements(*_boundary_groups(boundary_statements))
    allowed_boundary = text(allowed_output_boundary_label) or allowed_output_boundary(clean_scope_category)

    return {
        "persistent": bool(persistent),
        "preview_status": preview_status(clean_scope_category),
        "allowed_outputs": clean_allowed_outputs,
        "blocked_outputs": clean_blocked_outputs,
        "boundary_statements": clean_boundary_statements,
        "parsed_intent_rows": field_rows(parsed_intent_pairs),
        "allowed_output_rows": output_rows(clean_allowed_outputs, allowed_boundary),
        "blocked_output_rows": output_rows(clean_blocked_outputs, BLOCKED_OUTPUT_BOUNDARY),
        "boundary_statement_rows": boundary_statement_rows(clean_boundary_statements),
    }
