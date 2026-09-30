from __future__ import annotations

from typing import Any


PANEL_TITLE = "Documentation Consistency / Provenance"
PANEL_BOUNDARY_NOTE = (
    "Documentation-only consistency and provenance context for metadata completeness, "
    "traceability review, and human review needed signals."
)

STATUS_COMPLETE = "complete"
STATUS_HUMAN_REVIEW_NEEDED = "human_review_needed"
STATUS_NOT_AVAILABLE = "not_available"
STATUS_AVAILABLE = "available"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in _as_list(value) if isinstance(item, dict)]


def _has_text(value: Any) -> bool:
    return bool(str(value or "").strip())


def _safe_int(value: Any) -> int | None:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def _section(
    title: str,
    status: str,
    summary: str,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "title": title,
        "status": status,
        "summary": summary,
        "items": items or [],
    }


def _item(label: str, status: str, detail: str, source: str) -> dict[str, str]:
    return {
        "label": label,
        "status": status,
        "detail": detail,
        "source": source,
    }


def _metadata_completeness(project: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    project_fields = {
        "Project name": project.get("name") or project.get("project_name"),
        "Target product": project.get("target_product"),
        "Host": project.get("host"),
        "Description": project.get("description"),
        "Status": project.get("status"),
    }
    missing_project = [label for label, value in project_fields.items() if not _has_text(value)]
    items = [
        _item(
            "Project metadata",
            STATUS_COMPLETE if not missing_project else STATUS_HUMAN_REVIEW_NEEDED,
            "Missing fields: " + ", ".join(missing_project) if missing_project else "Project metadata fields are recorded.",
            "Pathway project",
        )
    ]

    step_missing_count = 0
    for index, step in enumerate(steps, start=1):
        label = step.get("step_name") or f"Step {step.get('step_order') or index}"
        missing = [
            field_label
            for field_label, field_name in (
                ("step name", "step_name"),
                ("substrate", "substrate"),
                ("product", "product"),
                ("enzyme", "enzyme_name"),
                ("gene", "gene_name"),
                ("gene sequence", "gene_sequence"),
                ("organism source", "organism_source"),
            )
            if not _has_text(step.get(field_name))
        ]
        if missing:
            step_missing_count += len(missing)
        items.append(
            _item(
                str(label),
                STATUS_COMPLETE if not missing else STATUS_HUMAN_REVIEW_NEEDED,
                "Missing fields: " + ", ".join(missing) if missing else "Step metadata fields are recorded.",
                "Pathway steps",
            )
        )

    if not steps:
        items.append(
            _item(
                "Pathway steps",
                STATUS_HUMAN_REVIEW_NEEDED,
                "No pathway step records are available for metadata completeness review.",
                "Pathway steps",
            )
        )

    missing_count = len(missing_project) + step_missing_count + (1 if not steps else 0)
    return _section(
        "metadata_completeness",
        STATUS_COMPLETE if missing_count == 0 else STATUS_HUMAN_REVIEW_NEEDED,
        f"{missing_count} metadata completeness item(s) need human review.",
        items,
    )


def _linked_record_coverage(steps: list[dict[str, Any]], expression_links: list[dict[str, Any]]) -> dict[str, Any]:
    step_ids = {_safe_int(step.get("id")) for step in steps}
    step_ids.discard(None)
    linked_step_ids = {_safe_int(link.get("step_id")) for link in expression_links}
    linked_step_ids.discard(None)
    missing_link_steps = [
        step
        for step in steps
        if _safe_int(step.get("id")) not in linked_step_ids
    ]
    stale_links = [
        link
        for link in expression_links
        if _safe_int(link.get("step_id")) not in step_ids
    ]

    items = [
        _item(
            "Linked Expression Wizard design records",
            STATUS_AVAILABLE if expression_links else STATUS_NOT_AVAILABLE,
            f"{len(expression_links)} linked design record(s) are available for traceability review.",
            "Linked design records",
        ),
        _item(
            "Pathway steps without linked design records",
            STATUS_COMPLETE if not missing_link_steps else STATUS_HUMAN_REVIEW_NEEDED,
            f"{len(missing_link_steps)} pathway step(s) have no linked design record.",
            "Pathway steps / linked designs",
        ),
        _item(
            "Linked records with missing step reference",
            STATUS_COMPLETE if not stale_links else STATUS_HUMAN_REVIEW_NEEDED,
            f"{len(stale_links)} linked record(s) reference a pathway step that is not present.",
            "Linked design records",
        ),
    ]
    needs_review = bool(missing_link_steps or stale_links or (steps and not expression_links))
    return _section(
        "linked_record_coverage",
        STATUS_HUMAN_REVIEW_NEEDED if needs_review else STATUS_COMPLETE,
        "Linked record coverage is summarized from existing local records.",
        items,
    )


def _snapshot_coverage(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    markdown_count = sum(1 for snapshot in snapshots if snapshot.get("include_generated_markdown"))
    items = [
        _item(
            "Documentation snapshots",
            STATUS_AVAILABLE if snapshots else STATUS_NOT_AVAILABLE,
            f"{len(snapshots)} documentation snapshot(s) are available for provenance context.",
            "Documentation snapshots",
        ),
        _item(
            "Snapshots with captured Markdown",
            STATUS_AVAILABLE if markdown_count else STATUS_NOT_AVAILABLE,
            f"{markdown_count} documentation snapshot(s) include generated Markdown text.",
            "Documentation snapshots",
        ),
    ]
    return _section(
        "snapshot_coverage",
        STATUS_AVAILABLE if snapshots else STATUS_HUMAN_REVIEW_NEEDED,
        "Snapshot coverage shows whether saved documentation state exists for local review history.",
        items,
    )


def _text_list_count(value: Any) -> int:
    if isinstance(value, str):
        return 1 if _has_text(value) else 0
    return sum(1 for item in _as_list(value) if _has_text(item))


def _review_notes_follow_up(documentation_review: dict[str, Any]) -> dict[str, Any]:
    review_items = _as_dict(documentation_review.get("review_items"))
    unchecked = [key for key, value in sorted(review_items.items()) if not bool(value)]
    unresolved_count = _text_list_count(documentation_review.get("unresolved_items"))
    follow_up_count = _text_list_count(documentation_review.get("follow_up_actions"))
    notes_present = _has_text(documentation_review.get("review_notes"))
    items = [
        _item(
            "Checklist items needing human review",
            STATUS_COMPLETE if not unchecked else STATUS_HUMAN_REVIEW_NEEDED,
            f"{len(unchecked)} checklist item(s) remain unchecked.",
            "Review notes",
        ),
        _item(
            "Unresolved review notes",
            STATUS_COMPLETE if unresolved_count == 0 else STATUS_HUMAN_REVIEW_NEEDED,
            f"{unresolved_count} unresolved review note field(s) are recorded.",
            "Review notes",
        ),
        _item(
            "Follow-up actions",
            STATUS_COMPLETE if follow_up_count == 0 else STATUS_HUMAN_REVIEW_NEEDED,
            f"{follow_up_count} follow-up action field(s) are recorded.",
            "Review notes",
        ),
        _item(
            "Review note text",
            STATUS_AVAILABLE if notes_present else STATUS_NOT_AVAILABLE,
            "Review note text is recorded." if notes_present else "No review note text is recorded.",
            "Review notes",
        ),
    ]
    needs_review = bool(unchecked or unresolved_count or follow_up_count or not notes_present)
    return _section(
        "review_notes_follow_up",
        STATUS_HUMAN_REVIEW_NEEDED if needs_review else STATUS_COMPLETE,
        "Review notes and follow-up fields are summarized as human review needed context.",
        items,
    )


def _traceability_gaps(
    steps: list[dict[str, Any]],
    expression_links: list[dict[str, Any]],
    review_signals: list[dict[str, Any]],
    linked_tool_artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    step_ids = {_safe_int(step.get("id")) for step in steps}
    step_ids.discard(None)
    stale_link_count = sum(1 for link in expression_links if _safe_int(link.get("step_id")) not in step_ids)
    stale_signal_count = sum(
        1
        for signal in review_signals
        if _safe_int(signal.get("related_step_id")) is not None and _safe_int(signal.get("related_step_id")) not in step_ids
    )
    items = [
        _item(
            "Review signals",
            STATUS_AVAILABLE if review_signals else STATUS_NOT_AVAILABLE,
            f"{len(review_signals)} review signal(s) are available for traceability review.",
            "Review signals",
        ),
        _item(
            "Missing local references",
            STATUS_COMPLETE if stale_link_count + stale_signal_count == 0 else STATUS_HUMAN_REVIEW_NEEDED,
            f"{stale_link_count + stale_signal_count} local reference gap(s) need human review.",
            "Traceability",
        ),
        _item(
            "Linked documentation artifacts",
            STATUS_AVAILABLE if linked_tool_artifacts else STATUS_NOT_AVAILABLE,
            f"{len(linked_tool_artifacts)} linked documentation artifact(s) are available as provenance context.",
            "Linked documentation artifacts",
        ),
    ]
    return _section(
        "traceability_gaps",
        STATUS_HUMAN_REVIEW_NEEDED if stale_link_count or stale_signal_count else STATUS_AVAILABLE,
        "Traceability gaps are computed from local record references only.",
        items,
    )


def _package_review_context(export_summary: dict[str, Any], import_summary: dict[str, Any]) -> dict[str, Any]:
    export_available = bool(export_summary)
    import_available = bool(import_summary)
    items = [
        _item(
            "Export package context",
            STATUS_AVAILABLE if export_available else STATUS_NOT_AVAILABLE,
            "Export package summary context is available." if export_available else "No export package summary context was supplied.",
            "Project Outputs",
        ),
        _item(
            "Import preview context",
            STATUS_AVAILABLE if import_available else STATUS_NOT_AVAILABLE,
            "Import preview or safety summary context is available." if import_available else "No import preview context was supplied.",
            "Project Outputs",
        ),
    ]
    return _section(
        "package_review_context",
        STATUS_AVAILABLE if export_available or import_available else STATUS_NOT_AVAILABLE,
        "Package review context is optional and uses only supplied read-only summaries.",
        items,
    )


def _duplicate_guard_context(context: dict[str, Any]) -> dict[str, Any]:
    has_context = bool(context)
    duplicate_count = len(_records(context.get("matches") or context.get("duplicates") or context.get("duplicate_matches")))
    status = STATUS_HUMAN_REVIEW_NEEDED if duplicate_count else (STATUS_AVAILABLE if has_context else STATUS_NOT_AVAILABLE)
    return _section(
        "duplicate_guard_context",
        status,
        f"{duplicate_count} duplicate guard item(s) need human review.",
        [
            _item(
                "Duplicate guard context",
                status,
                "Duplicate guard context was supplied." if has_context else "No duplicate guard context was supplied.",
                "Duplicate guard",
            )
        ],
    )


def build_documentation_consistency_provenance_panel(
    *,
    project: dict[str, Any] | None,
    steps: list[dict[str, Any]] | None = None,
    expression_links: list[dict[str, Any]] | None = None,
    snapshots: list[dict[str, Any]] | None = None,
    documentation_review: dict[str, Any] | None = None,
    review_signals: list[dict[str, Any]] | None = None,
    linked_tool_artifacts: list[dict[str, Any]] | None = None,
    export_summary: dict[str, Any] | None = None,
    import_summary: dict[str, Any] | None = None,
    duplicate_guard_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic read-only documentation consistency panel model."""
    project_data = _as_dict(project)
    step_rows = _records(steps)
    link_rows = _records(expression_links)
    snapshot_rows = _records(snapshots)
    review_data = _as_dict(documentation_review) or _as_dict(project_data.get("documentation_review"))
    signal_rows = _records(review_signals)
    artifact_rows = _records(linked_tool_artifacts)

    sections: dict[str, Any] = {
        "metadata_completeness": _metadata_completeness(project_data, step_rows),
        "linked_record_coverage": _linked_record_coverage(step_rows, link_rows),
        "snapshot_coverage": _snapshot_coverage(snapshot_rows),
        "review_notes_follow_up": _review_notes_follow_up(review_data),
        "traceability_gaps": _traceability_gaps(step_rows, link_rows, signal_rows, artifact_rows),
        "package_review_context": _package_review_context(_as_dict(export_summary), _as_dict(import_summary)),
    }
    if duplicate_guard_context is not None:
        sections["duplicate_guard_context"] = _duplicate_guard_context(_as_dict(duplicate_guard_context))

    human_review_sections = [
        key
        for key, section in sections.items()
        if section.get("status") == STATUS_HUMAN_REVIEW_NEEDED
    ]
    return {
        "panel_title": PANEL_TITLE,
        "boundary_note": PANEL_BOUNDARY_NOTE,
        "summary": {
            "section_count": len(sections),
            "human_review_needed_count": len(human_review_sections),
            "human_review_needed_sections": human_review_sections,
        },
        "sections": sections,
    }
