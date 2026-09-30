from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from services.candidate_evidence_review_matrix import build_candidate_evidence_review_matrix
from services.placeholder_review_value import clean_review_value

QUEUE_TITLE = "Human Review Queue"
QUEUE_SUBTITLE = "Read-only documentation triage queue derived from candidate evidence review rows."
QUEUE_BOUNDARY_NOTE = (
    "This queue supports manual review only. It does not rank, recommend, validate, "
    "or confirm biological use suitability."
)
QUEUE_TRIAGE_NOTE = (
    "Use this queue to track documentation gaps, source/provenance gaps, metadata follow-up, "
    "and manual review reminders."
)
QUEUE_EMPTY_STATE_MESSAGE = (
    "No human review follow-up items are currently queued from the candidate evidence review rows."
)
QUEUE_CONFIRMATION_ISSUE = "Documentation review remains available for confirmation."
QUEUE_CONFIRMATION_ACTION = "Confirm the recorded documentation context during manual review if needed."
QUEUE_BOUNDARY_REMINDER = "Documentation-only manual review support; no biological decision is made here."

_CATEGORY_LABELS = {
    "documentation_gap": "Documentation gap",
    "provenance_gap": "Source/provenance gap",
    "metadata_gap": "Metadata needs review",
    "review_follow_up": "Human review follow-up",
}
_SEVERITY_LABELS = {
    "low": "low priority",
    "medium": "medium priority",
    "high": "high priority",
}
_FIELD_ISSUE_MAP = {
    "candidate_label": (
        "documentation_gap",
        "high",
        "Missing candidate identifier",
        "Record a candidate label or stable display name for documentation traceability.",
    ),
    "source_category": (
        "provenance_gap",
        "high",
        "Missing source/provenance details",
        "Record the source category or source family used for this documentation row.",
    ),
    "source_identifier": (
        "provenance_gap",
        "high",
        "Missing source/provenance details",
        "Record the source identifier, accession, profile id, URL, or local reference id.",
    ),
    "source_hash": (
        "provenance_gap",
        "medium",
        "Missing source/provenance details",
        "Record the available source hash or equivalent trace value for manual provenance review.",
    ),
    "review_status": (
        "review_follow_up",
        "medium",
        "Missing review status",
        "Record the current manual review state for this documentation row.",
    ),
}


def _as_matrix(matrix_or_rows: Any) -> dict[str, Any]:
    if isinstance(matrix_or_rows, Mapping) and isinstance(matrix_or_rows.get("rows"), list):
        return dict(matrix_or_rows)
    return build_candidate_evidence_review_matrix(matrix_or_rows)


def _rows(matrix: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in matrix.get("rows") or [] if isinstance(row, Mapping)]


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _context_text(value: Any, fallback: str) -> str:
    return clean_review_value(value, fallback)


def _sort_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _text(row.get("candidate_label"), "candidate record").casefold(),
        _text(row.get("source_category"), "source not recorded").casefold(),
        _text(row.get("source_identifier"), "identifier not recorded").casefold(),
    )


def _queue_item(
    *,
    queue_item_id: str,
    candidate_label: str,
    category: str,
    severity: str,
    issue: str,
    human_follow_up: str,
    source_context: str,
) -> dict[str, str]:
    return {
        "queue_item_id": queue_item_id,
        "candidate_label": candidate_label,
        "category": category,
        "category_label": _CATEGORY_LABELS[category],
        "severity": severity,
        "severity_label": _SEVERITY_LABELS[severity],
        "issue": issue,
        "human_follow_up": human_follow_up,
        "source_context": source_context,
        "documentation_boundary": QUEUE_BOUNDARY_REMINDER,
    }


def build_candidate_evidence_human_review_queue(matrix_or_rows: Any) -> dict[str, Any]:
    """Build a deterministic read-only human review queue from candidate evidence rows."""
    matrix = _as_matrix(matrix_or_rows)
    matrix_rows = sorted(_rows(matrix), key=_sort_key)
    queue_rows: list[dict[str, str]] = []

    for row_index, row in enumerate(matrix_rows, start=1):
        candidate_label = _text(row.get("candidate_label"), "candidate record")
        source_context = (
            f"{_context_text(row.get('source_category'), 'source not recorded')} / "
            f"{_context_text(row.get('source_identifier'), 'identifier not recorded')}"
        )
        missing_fields = [str(field) for field in row.get("missing_fields") or []]

        for field_index, field_name in enumerate(missing_fields, start=1):
            mapping = _FIELD_ISSUE_MAP.get(field_name)
            if mapping is None:
                continue
            category, severity, issue, follow_up = mapping
            queue_rows.append(
                _queue_item(
                    queue_item_id=f"candidate-review-{row_index:03d}-{field_index:02d}",
                    candidate_label=candidate_label,
                    category=category,
                    severity=severity,
                    issue=issue,
                    human_follow_up=follow_up,
                    source_context=source_context,
                )
            )

        if _text(row.get("review_status")).casefold() == "manual review needed":
            queue_rows.append(
                _queue_item(
                    queue_item_id=f"candidate-review-{row_index:03d}-review",
                    candidate_label=candidate_label,
                    category="review_follow_up",
                    severity="medium",
                    issue="Records needing manual follow-up",
                    human_follow_up=(
                        "Review the current documentation context and record a human review note "
                        "before downstream discussion."
                    ),
                    source_context=source_context,
                )
            )

        if row.get("metadata_status") == "documentation-complete" and not missing_fields:
            queue_rows.append(
                _queue_item(
                    queue_item_id=f"candidate-review-{row_index:03d}-confirm",
                    candidate_label=candidate_label,
                    category="documentation_gap",
                    severity="low",
                    issue=QUEUE_CONFIRMATION_ISSUE,
                    human_follow_up=QUEUE_CONFIRMATION_ACTION,
                    source_context=source_context,
                )
            )

    queue_rows = sorted(
        queue_rows,
        key=lambda item: (
            _text(item.get("candidate_label")).casefold(),
            _text(item.get("category")).casefold(),
            _text(item.get("issue")).casefold(),
            _text(item.get("queue_item_id")).casefold(),
        ),
    )
    category_counts = Counter(item["category"] for item in queue_rows)
    severity_counts = Counter(item["severity"] for item in queue_rows)

    return {
        "title": QUEUE_TITLE,
        "subtitle": QUEUE_SUBTITLE,
        "summary": {
            "queue_item_count": len(queue_rows),
            "candidate_count": len(matrix_rows),
            "documentation_gap_count": category_counts.get("documentation_gap", 0),
            "provenance_gap_count": category_counts.get("provenance_gap", 0),
            "metadata_gap_count": category_counts.get("metadata_gap", 0),
            "review_follow_up_count": category_counts.get("review_follow_up", 0),
            "low_priority_count": severity_counts.get("low", 0),
            "medium_priority_count": severity_counts.get("medium", 0),
            "high_priority_count": severity_counts.get("high", 0),
            "category_counts": dict(sorted(category_counts.items())),
            "severity_counts": dict(sorted(severity_counts.items())),
        },
        "rows": queue_rows,
        "empty_state_message": QUEUE_EMPTY_STATE_MESSAGE if not queue_rows else "",
        "boundary_notes": [
            QUEUE_BOUNDARY_NOTE,
            QUEUE_TRIAGE_NOTE,
            QUEUE_BOUNDARY_REMINDER,
        ],
    }
