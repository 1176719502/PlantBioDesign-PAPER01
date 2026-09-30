from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from typing import Any

from services.placeholder_review_value import clean_review_value


INDEX_TITLE = "Project Review Follow-up Index"
INDEX_SUBTITLE = (
    "Aggregates documentation and provenance follow-up items from project review queues."
)
INDEX_EMPTY_STATE_MESSAGE = (
    "No manual documentation follow-up items are currently aggregated for this project review context. "
    "Review next: open existing review surfaces for candidate evidence, source/provenance, or Component "
    "Library promoter records when linked documentation context is available."
)
INDEX_BOUNDARY_NOTES = [
    "This index supports manual documentation review and triage only.",
    "It does not recommend, rank, score, validate, optimize, predict, or confirm biological suitability.",
    "It aggregates existing read-only review queue outputs without changing project data.",
]

_SOURCE_TITLES = {
    "candidate_evidence": "Candidate Evidence Human Review Queue",
    "plant_promoter_catalog": "Component Library Promoter Asset Evidence Gap Review",
}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _review_text(value: Any, fallback: str = "") -> str:
    return clean_review_value(value, fallback)


def _rows(queue: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in queue.get("rows") or [] if isinstance(row, Mapping)]


def _summary(queue: Mapping[str, Any]) -> dict[str, Any]:
    value = queue.get("summary")
    if isinstance(value, Mapping):
        return dict(value)
    value = queue.get("summary_counts")
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _queue_count(queue: Mapping[str, Any], summary: Mapping[str, Any]) -> int:
    for key in ("queue_item_count",):
        value = summary.get(key)
        if isinstance(value, int):
            return value
    total = queue.get("total_rows_available")
    if isinstance(total, int):
        return total
    return len(_rows(queue))


def _category_counts(queue: Mapping[str, Any], summary: Mapping[str, Any]) -> dict[str, int]:
    raw_counts = summary.get("category_counts")
    if isinstance(raw_counts, Mapping):
        return {
            _text(key): int(value or 0)
            for key, value in raw_counts.items()
            if _text(key)
        }
    counts: Counter[str] = Counter()
    for row in _rows(queue):
        category = _text(row.get("category_label") or row.get("category"))
        if category:
            counts[category] += 1
    return dict(sorted(counts.items()))


def _normalize_candidate_rows(queue: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _rows(queue):
        queue_item_id = _text(row.get("queue_item_id"))
        if not queue_item_id:
            continue
        rows.append(
            {
                "follow_up_id": f"candidate_evidence::{queue_item_id}",
                "source_section": "candidate_evidence",
                "source_title": _SOURCE_TITLES["candidate_evidence"],
                "item_label": _text(row.get("candidate_label"), "candidate record"),
                "category": _text(row.get("category_label") or row.get("category"), "Documentation review"),
                "issue": _text(row.get("issue"), "Documentation follow-up remains visible."),
                "human_follow_up": _text(
                    row.get("human_follow_up"),
                    "Review next: inspect this row in its existing review surface for documentation review.",
                ),
                "manual_review_context": _text(
                    _review_text(row.get("source_context")),
                    "No source context recorded",
                ),
                "documentation_boundary": _text(
                    row.get("documentation_boundary"),
                    INDEX_BOUNDARY_NOTES[1],
                ),
            }
        )
    return rows


def _normalize_promoter_rows(queue: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _rows(queue):
        queue_item_id = _text(row.get("queue_item_id"))
        if not queue_item_id:
            continue
        rows.append(
            {
                "follow_up_id": f"plant_promoter_catalog::{queue_item_id}",
                "source_section": "plant_promoter_catalog",
                "source_title": _SOURCE_TITLES["plant_promoter_catalog"],
                "item_label": _text(row.get("promoter_label"), "promoter record"),
                "category": _text(row.get("category"), "Documentation review"),
                "issue": _text(row.get("issue"), "Documentation follow-up remains visible."),
                "human_follow_up": _text(
                    row.get("human_follow_up"),
                    "Review next: inspect this row in its existing review surface for documentation review.",
                ),
                "manual_review_context": _text(
                    _review_text(row.get("source_context")),
                    "No source context recorded",
                ),
                "documentation_boundary": _text(
                    row.get("documentation_boundary"),
                    INDEX_BOUNDARY_NOTES[1],
                ),
            }
        )
    return rows


def build_project_review_follow_up_index(
    candidate_queue: Mapping[str, Any] | None = None,
    promoter_queue: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate existing project review queues into a deterministic follow-up index."""
    candidate_queue = candidate_queue if isinstance(candidate_queue, Mapping) else {}
    promoter_queue = promoter_queue if isinstance(promoter_queue, Mapping) else {}

    candidate_summary = _summary(candidate_queue)
    promoter_summary = _summary(promoter_queue)
    candidate_rows = _normalize_candidate_rows(candidate_queue)
    promoter_rows = _normalize_promoter_rows(promoter_queue)

    source_section_counts = {
        "candidate_evidence": _queue_count(candidate_queue, candidate_summary),
        "plant_promoter_catalog": _queue_count(promoter_queue, promoter_summary),
    }
    source_section_counts = dict(sorted(source_section_counts.items()))

    category_counts: Counter[str] = Counter()
    category_counts.update(_category_counts(candidate_queue, candidate_summary))
    category_counts.update(_category_counts(promoter_queue, promoter_summary))

    rows = sorted(
        [*candidate_rows, *promoter_rows],
        key=lambda row: (
            _text(row.get("source_section")).casefold(),
            _text(row.get("item_label")).casefold(),
            _text(row.get("category")).casefold(),
            _text(row.get("follow_up_id")).casefold(),
        ),
    )

    total_follow_up_items = sum(source_section_counts.values())
    total_rows_available = len(rows)

    return {
        "title": INDEX_TITLE,
        "subtitle": INDEX_SUBTITLE,
        "status": "AVAILABLE" if total_follow_up_items else "NOT_AVAILABLE",
        "summary": {
            "total_follow_up_items": total_follow_up_items,
            "source_section_counts": source_section_counts,
            "category_counts": dict(sorted(category_counts.items())),
        },
        "rows": rows,
        "total_rows_available": total_rows_available,
        "empty_state_message": "" if total_follow_up_items else INDEX_EMPTY_STATE_MESSAGE,
        "boundary_notes": INDEX_BOUNDARY_NOTES[:],
    }
