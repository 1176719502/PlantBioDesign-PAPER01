from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

from services.candidate_evidence_review_matrix import build_candidate_evidence_review_matrix
from services.generated_output_boundary import (
    assert_no_misleading_generated_claims,
    normalize_generated_output_text,
)

SNAPSHOT_TITLE = "Candidate Evidence Review Snapshot"
SNAPSHOT_BOUNDARY_LINE = (
    "Documentation-only evidence review snapshot for manual review planning; it does not "
    "choose candidates or make biological use decisions."
)
SNAPSHOT_MANUAL_REVIEW_NOTE = (
    "This snapshot supports manual review planning only and does not change project records, "
    "package data, or runtime seed intake."
)
SNAPSHOT_TRIAGE_NOTE = (
    "Use this read-only snapshot to explain what is documented, what is missing, and what "
    "still needs human follow-up during documentation triage."
)
SNAPSHOT_DEMO_NOTE = (
    "This is a review aid for human discussion only; it does not order candidates, assign "
    "numeric review values, suggest a preferred option, certify biological evidence, tune "
    "design behavior, assess host fit, or judge wet-lab use state."
)
EMPTY_SNAPSHOT_NOTE = (
    "No candidate evidence records are currently available for review. Record source trace "
    "and record review status in the existing Component Library, Candidate Evidence, or Project "
    "Review Report surfaces before documentation review planning."
)

SUMMARY_COUNT_KEYS = (
    ("candidate_count", "candidate records"),
    ("documentation_complete_count", "record review complete"),
    ("metadata_incomplete_count", "record review gaps"),
    ("source_trace_missing_count", "source trace missing"),
    ("source_trace_incomplete_count", "source trace incomplete"),
    ("external_candidate_count", "external candidate records"),
    ("runtime_seed_intake_blocked_count", "runtime seed intake blocked"),
)
MISSING_FIELD_ORDER = (
    "candidate_label",
    "source_category",
    "source_identifier",
    "source_hash",
    "review_status",
)


def _as_matrix(matrix_or_rows: Any) -> dict[str, Any]:
    if isinstance(matrix_or_rows, Mapping) and isinstance(matrix_or_rows.get("rows"), list):
        return dict(matrix_or_rows)
    return build_candidate_evidence_review_matrix(matrix_or_rows)


def _summary(matrix: Mapping[str, Any]) -> dict[str, Any]:
    return dict(matrix.get("summary")) if isinstance(matrix.get("summary"), Mapping) else {}


def _rows(matrix: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [dict(row) for row in matrix.get("rows") or [] if isinstance(row, Mapping)]


def _text(value: Any, fallback: str = "not recorded") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _count_lines(counts: Mapping[str, Any]) -> list[str]:
    if not counts:
        return ["- none recorded"]
    return [f"- {_text(key)}: {counts[key]}" for key in sorted(counts)]


def _field_gap_groups(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        label = _text(row.get("candidate_label"), "candidate record")
        for field_name in row.get("missing_fields") or []:
            grouped[str(field_name)].append(label)
    return {field: sorted(labels, key=str.casefold) for field, labels in grouped.items()}


def _field_gap_lines(grouped_fields: Mapping[str, list[str]]) -> list[str]:
    if not grouped_fields:
        return ["- No source/provenance or record review fields are missing in the current matrix."]

    ordered_fields = [field for field in MISSING_FIELD_ORDER if field in grouped_fields]
    ordered_fields.extend(sorted(field for field in grouped_fields if field not in ordered_fields))

    lines: list[str] = []
    for field_name in ordered_fields:
        labels = grouped_fields.get(field_name) or []
        lines.append(f"- {field_name}: {len(labels)} record(s)")
        for label in labels:
            lines.append(f"  - {label}")
    return lines


def _manual_action_lines(rows: list[dict[str, Any]]) -> list[str]:
    action_counts = Counter(
        _text(row.get("next_manual_action"), "Review source trace and record review status manually.")
        for row in rows
    )
    if not action_counts:
        return ["- Add candidate evidence records with source trace and record review status before documentation review planning."]
    return [f"- {action}: {action_counts[action]} record(s)" for action in sorted(action_counts)]


def format_candidate_evidence_review_snapshot(matrix_or_rows: Any) -> str:
    """Return a deterministic Markdown snapshot for read-only evidence review."""
    matrix = _as_matrix(matrix_or_rows)
    rows = _rows(matrix)
    summary = _summary(matrix)
    metadata_counts = summary.get("metadata_status_counts")
    provenance_counts = summary.get("provenance_status_counts")
    grouped_fields = _field_gap_groups(rows)

    lines: list[str] = [
        f"# {SNAPSHOT_TITLE}",
        "",
        SNAPSHOT_BOUNDARY_LINE,
        SNAPSHOT_MANUAL_REVIEW_NOTE,
        SNAPSHOT_TRIAGE_NOTE,
        SNAPSHOT_DEMO_NOTE,
        "",
        "## Summary counts",
    ]
    for key, label in SUMMARY_COUNT_KEYS:
        lines.append(f"- {label}: {summary.get(key, 0)}")

    lines.extend(["", "## Record review status summary"])
    lines.extend(_count_lines(metadata_counts if isinstance(metadata_counts, Mapping) else {}))

    lines.extend(["", "## Source trace gap summary"])
    lines.extend(_count_lines(provenance_counts if isinstance(provenance_counts, Mapping) else {}))

    lines.extend(["", "## Missing fields grouped by field name"])
    lines.extend(_field_gap_lines(grouped_fields))

    lines.extend(["", "## Next documentation review actions"])
    lines.extend(_manual_action_lines(rows))

    if not rows:
        lines.extend(["", "## Empty state", f"- {matrix.get('empty_state_message') or EMPTY_SNAPSHOT_NOTE}"])

    lines.extend(
        [
            "",
            "## Manual review planning note",
            f"- {SNAPSHOT_MANUAL_REVIEW_NOTE}",
            f"- {SNAPSHOT_TRIAGE_NOTE}",
            f"- {SNAPSHOT_DEMO_NOTE}",
            "",
        ]
    )
    snapshot = normalize_generated_output_text("\n".join(lines))
    assert_no_misleading_generated_claims(snapshot, context="candidate evidence review snapshot")
    return snapshot
