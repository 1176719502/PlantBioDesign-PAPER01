from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_project_draft_r223_adapter import plant_project_draft_to_r223_chain_output
from services.plant_walkthrough_chain_runner import run_plant_walkthrough_chain_by_fixture_id


DEFAULT_FIXTURE_ID = "rice_albumin_expression_review"

PAGE_TITLE = "Plant Expression Workspace"
PAGE_BADGE = "Prototype"
PAGE_SUBTITLE = (
    "Read-only plant expression design review workspace for goal, construct, gap, "
    "and traceability review."
)
BOUNDARY_NOTICE = (
    "Documentation-only workspace. It summarizes existing review records for manual review; "
    "it does not choose components, generate sequences, create construct tasks, or evaluate lab use."
)
EMPTY_STATE_MESSAGE = (
    "No plant expression design record is available for this prototype. Select or prepare a "
    "plant design record before reviewing the workspace summary."
)

SECTION_ORDER: tuple[str, ...] = (
    "Workspace Header",
    "Expression Construct Overview",
    "Current Gaps and Next Action",
    "Detailed Review",
)
ADVANCED_DETAIL_GROUPS: tuple[str, ...] = (
    "Evidence details",
    "Provenance",
    "Traceability",
    "Readback",
    "Audit / Snapshot",
    "Raw status and detailed records",
)

BLOCKED_COPY_FAMILIES: tuple[str, ...] = (
    "automatic design",
    "automatic component choice",
    "construct content generation",
    "sequence generation",
    "biological outcome claim",
    "lab-use judgment",
)

COMPONENT_LAYOUT: tuple[dict[str, Any], ...] = (
    {
        "component_id": "promoter",
        "label": "Promoter",
        "slot_keys": ("promoter_slot",),
        "source_keys": ("promoter_source_reference",),
        "missing_note": "Promoter source record is not shown in the current readback.",
    },
    {
        "component_id": "five_prime_utr",
        "label": "5' UTR",
        "slot_keys": ("five_prime_utr", "leader_sequence", "leader_source_reference"),
        "source_keys": ("leader_source_reference",),
        "missing_note": "5' UTR or leader source note is not recorded in this readback.",
    },
    {
        "component_id": "cds",
        "label": "CDS",
        "slot_keys": ("cds_label", "coding_sequence_slot"),
        "source_keys": ("source_reference",),
        "missing_note": "CDS source label is not recorded in this readback.",
    },
    {
        "component_id": "tag_signal",
        "label": "Tag / Signal",
        "slot_keys": ("tag_signal", "signal_peptide", "localization_context"),
        "source_keys": (),
        "missing_note": "Tag or signal note is not recorded in this readback.",
    },
    {
        "component_id": "terminator",
        "label": "Terminator",
        "slot_keys": ("terminator_slot",),
        "source_keys": ("terminator_source_reference",),
        "missing_note": "Terminator source record is not shown in the current readback.",
    },
    {
        "component_id": "vector_backbone",
        "label": "Vector / Backbone",
        "slot_keys": ("backbone_label", "vector_backbone"),
        "source_keys": ("source_reference",),
        "missing_note": "Vector or backbone source label is not recorded in this readback.",
    },
)

GAP_PRIORITY: dict[str, int] = {
    "terminator_source_reference": 10,
    "promoter_source_reference": 20,
    "backbone_label": 30,
    "cds_label": 40,
    "five_prime_utr": 50,
    "tag_signal": 60,
}


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _section(output: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    package = _as_mapping(output.get("package_snapshot"))
    return _as_mapping(package.get(key))


def _route(output: Mapping[str, Any]) -> Mapping[str, Any]:
    return _as_mapping(output.get("route_draft"))


def _summary(output: Mapping[str, Any]) -> Mapping[str, Any]:
    return _as_mapping(output.get("chain_summary"))


def _slot_rows(output: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _mapping_list(_section(output, "construct_slot_plan_section").get("construct_slot_rows"))


def _candidate_rows(output: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _mapping_list(_section(output, "component_candidate_section").get("slot_candidate_rows"))


def _unmatched_rows(output: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _mapping_list(_section(output, "component_candidate_section").get("unmatched_slot_rows"))


def _gap_rows(output: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return _mapping_list(_section(output, "gap_queue_section").get("queue_items"))


def _slot_index(output: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        _text(row.get("slot_name")): row
        for row in _slot_rows(output)
        if _text(row.get("slot_name"))
    }


def _candidate_index(output: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    return {
        _text(row.get("slot_type")): row
        for row in _candidate_rows(output)
        if _text(row.get("slot_type"))
    }


def _provided_slot(slot_index: Mapping[str, Mapping[str, Any]], keys: Sequence[str]) -> Mapping[str, Any]:
    for key in keys:
        row = slot_index.get(key)
        if row and _text(row.get("value")):
            return row
    return {}


def _source_is_recorded(slot_index: Mapping[str, Mapping[str, Any]], keys: Sequence[str]) -> bool:
    return any(bool(_text(_as_mapping(slot_index.get(key)).get("value"))) for key in keys)


def _component_status(
    *,
    component: Mapping[str, Any],
    slot_index: Mapping[str, Mapping[str, Any]],
    candidate_index: Mapping[str, Mapping[str, Any]],
) -> tuple[str, str, str]:
    slot = _provided_slot(slot_index, component.get("slot_keys", ()))
    candidate = candidate_index.get(_text(slot.get("slot_name")))
    source_recorded = _source_is_recorded(slot_index, component.get("source_keys", ()))

    if not slot:
        return (
            "Needs documentation",
            _text(component.get("missing_note"), "Component source note is not recorded."),
            "",
        )

    value = _text(slot.get("value"))
    if candidate:
        review_status = _text(candidate.get("review_status"), "manual review pending")
        return (
            "Manual review needed",
            f"{value}; source context is present and remains marked for manual confirmation.",
            review_status,
        )

    if source_recorded or _text(slot.get("slot_name")) in {"cds_label", "backbone_label"}:
        return (
            "Recorded",
            f"{value}; no component choice is made by this prototype.",
            "source label recorded",
        )

    return (
        "Needs documentation",
        _text(component.get("missing_note"), "Component source note is not recorded."),
        "",
    )


def _construct_components(output: Mapping[str, Any]) -> list[dict[str, str]]:
    slot_index = _slot_index(output)
    candidates = _candidate_index(output)
    rows: list[dict[str, str]] = []
    for component in COMPONENT_LAYOUT:
        status, note, review_note = _component_status(
            component=component,
            slot_index=slot_index,
            candidate_index=candidates,
        )
        slot = _provided_slot(slot_index, component.get("slot_keys", ()))
        rows.append(
            {
                "component_id": _text(component.get("component_id")),
                "label": _text(component.get("label")),
                "name": _text(slot.get("value"), "Not recorded"),
                "status": status,
                "note": note,
                "review_note": review_note,
            }
        )
    return rows


def _status_counts(component_rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {"Recorded": 0, "Needs documentation": 0, "Manual review needed": 0}
    for row in component_rows:
        status = _text(row.get("status"))
        if status in counts:
            counts[status] += 1
    return counts


def _component_gap_rows(component_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(component_rows, start=1):
        status = _text(row.get("status"))
        if status == "Recorded":
            continue
        component_id = _text(row.get("component_id"))
        rows.append(
            {
                "gap_id": f"component-gap-{index:02d}",
                "field_name": component_id,
                "title": f"{row.get('label')} needs documentation review",
                "description": _text(row.get("note"), "Manual documentation review is still open."),
                "priority": GAP_PRIORITY.get(component_id, 80),
                "source": "construct overview",
            }
        )
    return rows


def _source_gap_rows(output: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _gap_rows(output):
        field_name = _text(row.get("field_name"), "documentation field")
        rows.append(
            {
                "gap_id": _text(row.get("gap_id"), field_name),
                "field_name": field_name,
                "title": _friendly_gap_title(field_name),
                "description": _text(row.get("message"), "Manual documentation review is still open."),
                "priority": GAP_PRIORITY.get(field_name, 70),
                "source": _text(row.get("source_section"), "review queue"),
            }
        )
    return rows


def _friendly_gap_title(field_name: str) -> str:
    labels = {
        "terminator_source_reference": "Terminator source needs documentation review",
        "promoter_source_reference": "Promoter evidence needs manual confirmation",
        "backbone_label": "Vector / backbone information needs documentation review",
        "cds_label": "CDS source needs documentation review",
    }
    return labels.get(field_name, f"{field_name.replace('_', ' ').title()} needs documentation review")


def _highest_priority_gaps(
    output: Mapping[str, Any],
    component_rows: Sequence[Mapping[str, Any]],
    limit: int = 3,
) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for row in [*_source_gap_rows(output), *_component_gap_rows(component_rows)]:
        key = _text(row.get("field_name")) or _text(row.get("title"))
        if not key:
            continue
        current = deduped.get(key)
        if current is None or int(row.get("priority", 99)) < int(current.get("priority", 99)):
            deduped[key] = dict(row)
    return sorted(deduped.values(), key=lambda item: (int(item.get("priority", 99)), _text(item.get("title"))))[:limit]


def _workspace_summary(output: Mapping[str, Any], component_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    route = _route(output)
    summary = _summary(output)
    package = _as_mapping(output.get("package_snapshot"))
    intent = _as_mapping(route.get("intent_summary"))
    counts = _status_counts(component_rows)
    recorded = counts["Recorded"] + counts["Manual review needed"]
    total = len(component_rows)
    is_user_draft = _text(output.get("record_origin")) == "user"
    return {
        "project_name": _text(package.get("package_title"), "Untitled plant design draft")
        if is_user_draft
        else "Rice albumin expression review",
        "case_name": _text(output.get("project_id"), "user draft") if is_user_draft else _text(output.get("fixture_id"), DEFAULT_FIXTURE_ID),
        "target_product": _text(intent.get("target_or_product_terms"), "rice albumin source record"),
        "plant_host": _text(intent.get("host_plant_terms"), "Oryza sativa rice"),
        "design_purpose": (
            "Review the persisted user plant design draft and keep source gaps visible for manual review."
            if is_user_draft
            else "Review a plant expression design record and keep source gaps visible for manual review."
        ),
        "current_stage": "Plant project draft review" if is_user_draft else "Construct draft review",
        "overall_status": "Documentation review in progress",
        "completion_label": f"{recorded}/{total} construct elements recorded or awaiting manual confirmation",
        "progress_percent": int(round((recorded / total) * 100)) if total else 0,
        "route_label": _text(summary.get("route_id"), "plant expression route review"),
        "read_only": True,
        "record_origin": _text(output.get("record_origin"), "example"),
    }


def _advanced_details(output: Mapping[str, Any]) -> list[dict[str, Any]]:
    route = _route(output)
    package = _as_mapping(output.get("package_snapshot"))
    markdown = _as_mapping(output.get("markdown_readback"))
    return [
        {
            "label": "Evidence details",
            "rows": _mapping_list(route.get("evidence_summary")),
            "empty_message": "No evidence detail rows are available.",
        },
        {
            "label": "Provenance",
            "rows": _candidate_rows(output),
            "empty_message": "No component provenance rows are available.",
        },
        {
            "label": "Traceability",
            "rows": _slot_rows(output),
            "empty_message": "No construct traceability rows are available.",
        },
        {
            "label": "Readback",
            "rows": [{"field": "Markdown readback characters", "value": str(len(_text(markdown.get("markdown_text"))))}],
            "empty_message": "No readback summary is available.",
        },
        {
            "label": "Audit / Snapshot",
            "rows": [
                {"field": "Package title", "value": _text(package.get("package_title"), "not recorded")},
                {"field": "Package status", "value": _text(package.get("package_status"), "not recorded")},
                {"field": "Package scope", "value": _text(package.get("package_scope"), "not recorded")},
            ],
            "empty_message": "No package snapshot rows are available.",
        },
        {
            "label": "Raw status and detailed records",
            "rows": [
                {"field": "Route status", "value": _text(route.get("draft_status"), "manual review")},
                {"field": "Candidate rows", "value": str(len(_candidate_rows(output)))},
                {"field": "Unmatched rows", "value": str(len(_unmatched_rows(output)))},
                {"field": "Gap rows", "value": str(len(_gap_rows(output)))},
            ],
            "empty_message": "No raw status rows are available.",
        },
    ]


def _empty_presenter() -> dict[str, Any]:
    return {
        "page_title": PAGE_TITLE,
        "page_badge": PAGE_BADGE,
        "subtitle": PAGE_SUBTITLE,
        "boundary_notice": BOUNDARY_NOTICE,
        "section_order": list(SECTION_ORDER),
        "advanced_detail_groups": list(ADVANCED_DETAIL_GROUPS),
        "workspace_summary": {},
        "construct_components": [],
        "status_counts": {"Recorded": 0, "Needs documentation": 0, "Manual review needed": 0},
        "gaps": [],
        "next_action": "Select or prepare a plant design record, then reopen this read-only workspace.",
        "advanced_details": [],
        "empty_state": {"is_empty": True, "message": EMPTY_STATE_MESSAGE},
        "blocked_copy_families": list(BLOCKED_COPY_FAMILIES),
        "read_only": True,
    }


def build_plant_expression_workspace_prototype_presenter(
    chain_output: Mapping[str, Any] | None = None,
    *,
    project_draft: Mapping[str, Any] | None = None,
    use_default_fixture: bool = True,
) -> dict[str, Any]:
    """Build the R223 read-only Plant Expression Workspace prototype presenter."""
    if isinstance(project_draft, Mapping) and project_draft:
        output = plant_project_draft_to_r223_chain_output(dict(project_draft))
    elif isinstance(chain_output, Mapping):
        output = chain_output
    elif use_default_fixture:
        output = run_plant_walkthrough_chain_by_fixture_id(DEFAULT_FIXTURE_ID)
    else:
        output = {}
    if not isinstance(output, Mapping) or not output:
        return _empty_presenter()

    component_rows = _construct_components(output)
    gaps = _highest_priority_gaps(output, component_rows)
    next_action = (
        "Review the listed source/provenance gaps manually before treating this design record as complete documentation."
        if gaps
        else "Review the advanced details and add a manual review note if the documentation record is complete."
    )
    presenter = _empty_presenter()
    if _text(output.get("record_origin")) == "user":
        presenter["page_badge"] = "User draft"
    presenter.update(
        {
            "workspace_summary": _workspace_summary(output, component_rows),
            "construct_components": component_rows,
            "status_counts": _status_counts(component_rows),
            "gaps": gaps,
            "next_action": next_action,
            "advanced_details": _advanced_details(output),
            "empty_state": {"is_empty": False, "message": ""},
        }
    )
    return presenter
