from __future__ import annotations

from typing import Any


def _dict_items(items: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [item for item in (items or []) if isinstance(item, dict)]


def _has_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _has_project_context(project: dict[str, Any] | None, steps: list[dict[str, Any]]) -> bool:
    if steps:
        return True
    if not isinstance(project, dict):
        return False
    return any(_has_text(project.get(field)) for field in ("name", "target_product", "host", "description", "status"))


def _row(
    label: str,
    status: str,
    detail: str,
    related_count: int,
    source_area: str,
) -> dict[str, Any]:
    return {
        "label": label,
        "status": status,
        "detail": detail,
        "related_count": related_count,
        "source_area": source_area,
    }


def build_documentation_risk_summary(
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None,
    expression_links: list[dict[str, Any]] | None,
    test_records: list[dict[str, Any]] | None,
    review_signals: list[dict[str, Any]] | None,
    snapshots: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build documentation-only risk summary rows for recorded project context."""
    step_rows = _dict_items(steps)
    link_rows = _dict_items(expression_links)
    test_rows = _dict_items(test_records)
    signal_rows = _dict_items(review_signals)
    snapshot_rows = _dict_items(snapshots)
    has_context = _has_project_context(project, step_rows)
    recorded_area_count = sum(1 for items in (step_rows, link_rows, test_rows, signal_rows, snapshot_rows) if items)

    if step_rows:
        steps_row = _row(
            "Pathway steps documentation",
            "available_for_review",
            f"{len(step_rows)} pathway step record(s) are documented for project review.",
            len(step_rows),
            "Pathway Steps",
        )
    else:
        steps_row = _row(
            "Pathway steps documentation",
            "needs_documentation" if has_context else "no_records",
            "No pathway step records are available for documentation review.",
            0,
            "Pathway Steps",
        )

    if link_rows:
        links_row = _row(
            "Linked expression designs",
            "available_for_review",
            f"{len(link_rows)} linked expression design record(s) are available for traceability review.",
            len(link_rows),
            "Linked Designs",
        )
    elif step_rows:
        links_row = _row(
            "Linked expression designs",
            "needs_review",
            "No linked expression design records are attached to the documented pathway steps.",
            0,
            "Linked Designs",
        )
    else:
        links_row = _row(
            "Linked expression designs",
            "no_records",
            "No linked expression design records are available for traceability review.",
            0,
            "Linked Designs",
        )

    if test_rows:
        tests_row = _row(
            "Test records / observations",
            "available_for_review",
            f"{len(test_rows)} observation or test record(s) are available as documentation records.",
            len(test_rows),
            "Test Records",
        )
    elif step_rows:
        tests_row = _row(
            "Test records / observations",
            "needs_documentation",
            "No observation or test records are attached to the current pathway documentation.",
            0,
            "Test Records",
        )
    else:
        tests_row = _row(
            "Test records / observations",
            "no_records",
            "No observation or test records are available for documentation review.",
            0,
            "Test Records",
        )

    if signal_rows:
        signals_row = _row(
            "Review signals",
            "needs_review",
            f"{len(signal_rows)} documentation review signal(s) are recorded for human review.",
            len(signal_rows),
            "Review Signals",
        )
    else:
        signals_row = _row(
            "Review signals",
            "no_records",
            "No documentation review signals are recorded in the current project summary.",
            0,
            "Review Signals",
        )

    if snapshot_rows:
        snapshots_row = _row(
            "Documentation snapshots",
            "available_for_review",
            f"{len(snapshot_rows)} documentation snapshot(s) are saved for local review history.",
            len(snapshot_rows),
            "Documentation Snapshots",
        )
    elif has_context:
        snapshots_row = _row(
            "Documentation snapshots",
            "needs_documentation",
            "No documentation snapshots are saved for the current project context.",
            0,
            "Documentation Snapshots",
        )
    else:
        snapshots_row = _row(
            "Documentation snapshots",
            "no_records",
            "No documentation snapshots are available because project context is not recorded.",
            0,
            "Documentation Snapshots",
        )

    if recorded_area_count:
        outputs_row = _row(
            "Project outputs traceability",
            "available_for_review" if recorded_area_count >= 2 else "needs_review",
            f"{recorded_area_count} project documentation area(s) have records for output traceability review.",
            recorded_area_count,
            "Project Outputs",
        )
    else:
        outputs_row = _row(
            "Project outputs traceability",
            "no_records",
            "No project documentation records are available for output traceability review.",
            0,
            "Project Outputs",
        )

    return [steps_row, links_row, tests_row, signals_row, snapshots_row, outputs_row]
