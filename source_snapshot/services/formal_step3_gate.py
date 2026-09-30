"""Shared Step 3 continuation gate for the formal vector workflow."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _has_blocking_finding(findings: Iterable[Mapping[str, Any]] | None) -> bool:
    return any(
        bool(finding.get("blocking"))
        or str(finding.get("status") or "").casefold() in {"blocking", "阻断"}
        for finding in (findings or [])
    )


def step3_can_continue_to_backbone(
    *,
    cassette_result: Mapping[str, Any] | None,
    current_input_signature: str,
    findings: Iterable[Mapping[str, Any]] | None,
    order_confirmed: bool,
) -> bool:
    """Return the formal Step 3 gate used by navigation and backbone selection.

    Manual-review findings remain visible but are not blocking prerequisites for
    selecting a reviewed backbone.
    """
    if not isinstance(cassette_result, Mapping) or not cassette_result.get("runtime"):
        return False
    generated_signature = str(
        cassette_result.get("cassette_input_signature")
        or cassette_result.get("input_signature")
        or ""
    )
    return bool(
        current_input_signature
        and generated_signature == str(current_input_signature)
        and not _has_blocking_finding(findings)
        and order_confirmed
    )
