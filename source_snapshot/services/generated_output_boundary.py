from __future__ import annotations

import re
from typing import Any


GENERATED_OUTPUT_SAFE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("host compatibility", "host/context documentation"),
    ("compatible host", "host context record"),
    ("compatibility proof", "documentation context note"),
    ("host readiness", "host context documentation status"),
    ("ready host", "documented host context"),
    ("validated host", "reviewed host context note"),
    ("recommended host", "host context note"),
    ("wet-lab readiness", "documentation follow-up status"),
    ("yield prediction", "documentation note"),
    ("optimized design", "documentation review item"),
    ("validated design", "documentation review item"),
)

MISLEADING_GENERATED_CLAIMS: tuple[str, ...] = (
    "validation success",
    "successful cloning",
    "successful PCR",
    "successful expression",
    "validated construct",
    "ready for experiment",
    "experiment-ready",
    "production-ready",
    "optimized pathway",
    "evidence score",
    "readiness score",
    "successful import",
    "validated import",
    "host recommendation",
    "ready for synthesis",
    "ready for wet lab",
    "ready for execution",
    "experimentally confirmed",
)


def normalize_generated_output_text(text: Any) -> str:
    """Normalize generated-output wording without changing caller-owned records."""
    clean = str(text)
    for unsafe, replacement in GENERATED_OUTPUT_SAFE_REPLACEMENTS:
        clean = re.sub(re.escape(unsafe), replacement, clean, flags=re.IGNORECASE)
    return clean


def normalize_generated_output_claims(value: Any) -> Any:
    """Recursively normalize generated-output keys and values."""
    if isinstance(value, str):
        return normalize_generated_output_text(value)
    if isinstance(value, list):
        return [normalize_generated_output_claims(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_generated_output_claims(item) for item in value)
    if isinstance(value, dict):
        return {
            normalize_generated_output_claims(key): normalize_generated_output_claims(item)
            for key, item in value.items()
        }
    return value


def misleading_generated_claim_hits(value: Any, *, strict: bool = False) -> list[str]:
    """Return unsafe generated-claim phrases still visible in output."""
    scan_value = value if strict else normalize_generated_output_claims(value)
    lower_output = str(scan_value).lower()
    claim_terms = MISLEADING_GENERATED_CLAIMS
    if strict:
        claim_terms = claim_terms + tuple(unsafe for unsafe, _replacement in GENERATED_OUTPUT_SAFE_REPLACEMENTS)
    return [claim for claim in claim_terms if claim.lower() in lower_output]


def assert_no_misleading_generated_claims(
    value: Any,
    *,
    context: str,
    strict: bool = False,
) -> None:
    """Raise when generated output still contains unsafe claim wording."""
    hits = misleading_generated_claim_hits(value, strict=strict)
    if hits:
        raise ValueError(f"Misleading {context} claim detected: {hits[0]}")
