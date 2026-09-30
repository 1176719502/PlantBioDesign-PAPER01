from __future__ import annotations

from typing import Any


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def safe_step_id(step_or_value: Any) -> int:
    """Return a positive integer step id, or 0 for missing/invalid values."""
    value = step_or_value.get("id") if isinstance(step_or_value, dict) else step_or_value
    try:
        step_id = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return step_id if step_id > 0 else 0


def expression_links_by_step(expression_links: list[dict[str, Any]] | None) -> dict[int, list[dict[str, Any]]]:
    """Group linked Expression Wizard records by safe positive pathway step id."""
    links_by_step: dict[int, list[dict[str, Any]]] = {}
    for link in expression_links or []:
        if not isinstance(link, dict):
            continue
        step_id = safe_step_id(link.get("step_id"))
        if step_id <= 0:
            continue
        links_by_step.setdefault(step_id, []).append(dict(link))
    return links_by_step


def expression_link_counts_by_step(expression_links: list[dict[str, Any]] | None) -> dict[int, int]:
    """Return linked design counts keyed by positive pathway step id."""
    return {step_id: len(links) for step_id, links in expression_links_by_step(expression_links).items()}


def _linked_design_display_name(link: dict[str, Any]) -> str:
    for field in ("design_name", "design_title", "snapshot_title", "name", "title"):
        value = _clean_text(link.get(field))
        if value:
            return value
    design_id = _clean_text(link.get("design_id") or link.get("id"))
    return f"Linked design {design_id}" if design_id else "Linked design"


def _linked_design_timestamp(link: dict[str, Any]) -> str:
    for field in ("linked_at", "saved_at", "created_at", "updated_at"):
        value = _clean_text(link.get(field))
        if value:
            return value
    return "Not recorded"


def _linked_design_source(link: dict[str, Any]) -> str:
    for field in ("design_source", "source", "linked_source", "context", "source_context"):
        value = _clean_text(link.get(field))
        if value:
            return value
    return "Not recorded"


def _step_title(step: dict[str, Any], step_order: Any) -> str:
    for field in ("step_title", "step_name"):
        value = _clean_text(step.get(field))
        if value:
            return value
    order = _clean_text(step_order)
    return f"Step {order}" if order else "Step"


def _steps_table_step_label(step: dict[str, Any]) -> Any:
    return step.get("step_name") or step.get("name") or f"Step {step.get('step_order')}"


def build_pathway_steps_table_rows(
    steps: list[dict[str, Any]] | None,
    linked_design_counts: dict[int, int] | None,
) -> list[dict[str, Any]]:
    """Build Pathway Workspace steps table rows without mutating source steps."""
    counts = linked_design_counts or {}
    rows: list[dict[str, Any]] = []
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        step_id = safe_step_id(step)
        step_order = step.get("step_order")
        rows.append(
            {
                "Order": step_order,
                "Step": _steps_table_step_label(step),
                "Reaction": step.get("reaction_name") or "",
                "Substrate": step.get("substrate") or "",
                "Product": step.get("product") or "",
                "Enzyme": step.get("enzyme_name") or "",
                "Gene": step.get("gene_name") or "",
                "Sequence Length": len(str(step.get("gene_sequence") or "")),
                "Linked designs": counts.get(step_id, 0),
            }
        )
    return rows


def build_linked_design_evidence_rows(
    steps: list[dict[str, Any]] | None,
    expression_links: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Build documentation-only linked design evidence rows for pathway steps."""
    links_by_step = expression_links_by_step(expression_links)
    rows: list[dict[str, Any]] = []
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        step_id = safe_step_id(step)
        step_order = step.get("step_order")
        step_links = links_by_step.get(step_id, []) if step_id > 0 else []
        linked_design_rows = [
            {
                "linked_design_name": _linked_design_display_name(link),
                "linked_timestamp": _linked_design_timestamp(link),
                "source_context": _linked_design_source(link),
            }
            for link in step_links
        ]
        rows.append(
            {
                "step_id": step_id,
                "step_order": step_order,
                "step_title": _step_title(step, step_order),
                "step_name": _clean_text(step.get("step_name")),
                "linked_design_count": len(linked_design_rows),
                "linked_design_rows": linked_design_rows,
            }
        )
    return rows
