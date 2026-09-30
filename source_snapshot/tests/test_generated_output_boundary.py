from __future__ import annotations

import pytest

from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    misleading_generated_claim_hits,
    normalize_generated_output_claims,
    normalize_generated_output_text,
)


def test_recursive_normalization_handles_nested_keys_values_and_tuples() -> None:
    source = {
        "host compatibility": [
            "Compatible host summary",
            {
                "compatibility proof": (
                    "Host readiness note",
                    "Ready host review",
                    "Validated host context",
                    "Recommended host row",
                )
            },
        ],
        "design": {
            "wet-lab readiness": "Yield prediction, optimized design, validated design",
        },
    }

    normalized = normalize_generated_output_claims(source)
    text = str(normalized).lower()

    for unsafe in [
        "host compatibility",
        "compatible host",
        "compatibility proof",
        "host readiness",
        "ready host",
        "validated host",
        "recommended host",
        "wet-lab readiness",
        "yield prediction",
        "optimized design",
        "validated design",
    ]:
        assert unsafe not in text
    assert "host/context documentation" in text
    assert "host context record" in text
    assert "documentation context note" in text
    assert isinstance(normalized["host/context documentation"][1]["documentation context note"], tuple)


def test_text_normalization_is_case_insensitive_and_deterministic() -> None:
    text = "HOST COMPATIBILITY and Compatible Host"

    assert normalize_generated_output_text(text) == normalize_generated_output_text(text)
    assert normalize_generated_output_text(text) == "host/context documentation and host context record"


def test_strict_guard_raises_on_unnormalized_generated_claims() -> None:
    with pytest.raises(ValueError, match="Misleading unit-test claim detected: host compatibility"):
        assert_no_misleading_generated_claims(
            {"summary": "Host compatibility summary"},
            context="unit-test",
            strict=True,
        )


def test_default_guard_normalizes_known_phrases_but_rejects_unsafe_claims() -> None:
    assert_no_misleading_generated_claims(
        {"summary": "Host compatibility summary"},
        context="unit-test",
    )

    with pytest.raises(ValueError, match="Misleading unit-test claim detected: validated construct"):
        assert_no_misleading_generated_claims(
            {"summary": "Validated construct summary"},
            context="unit-test",
        )


def test_negative_boundary_copy_is_not_flagged() -> None:
    boundary = (
        "This generated output does not recommend, validate, optimize, predict, "
        "or judge downstream-use state."
    )

    assert misleading_generated_claim_hits(boundary) == []


def test_user_entered_risky_text_is_normalized_only_when_used_as_generated_output() -> None:
    record = {
        "source": "user-entered record text",
        "record_text": "User wrote host compatibility in a note.",
    }

    assert record["record_text"] == "User wrote host compatibility in a note."
    generated_readback = normalize_generated_output_claims(
        {
            "label": "Generated readback",
            "record_text": f"Record text for documentation review: {record['record_text']}",
        }
    )

    assert "host compatibility" not in str(generated_readback).lower()
    assert "record text for documentation review" in str(generated_readback).lower()
