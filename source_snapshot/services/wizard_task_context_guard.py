# -*- coding: utf-8 -*-
"""Pure guards for Expression Wizard async task context signatures."""
from __future__ import annotations


STALE_PRIMER_TASK_MESSAGE = (
    "This primer task result was ignored because the design context changed. "
    "Re-run the primer preview for the current design context. "
    "This is a computational preview only and does not certify experimental readiness."
)

STALE_VALIDATION_TASK_MESSAGE = (
    "This review task result was ignored because the design context changed. "
    "Re-run the review preview for the current design context. "
    "This is a computational preview only and does not certify experimental readiness."
)


def is_task_context_current(task_signature: str | None, current_signature: str | None) -> bool:
    """Return True only when both task and current signatures are present and equal."""
    task_value = str(task_signature or "").strip()
    current_value = str(current_signature or "").strip()
    return bool(task_value and current_value and task_value == current_value)


def should_apply_task_result(task_signature: str | None, current_signature: str | None) -> bool:
    """Alias used by wizard steps before applying async task results."""
    return is_task_context_current(task_signature, current_signature)


def build_stale_primer_task_message() -> str:
    """Return the stale primer-task warning copy."""
    return STALE_PRIMER_TASK_MESSAGE


def build_stale_validation_task_message() -> str:
    """Return the stale validation/review-task warning copy."""
    return STALE_VALIDATION_TASK_MESSAGE
