from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any


BOUNDARY_NOTICE = (
    "Documentation-only Plant Design Review Package Markdown readback for manual review. It "
    "formats an existing package snapshot without exporting packages, saving UI state, modifying "
    "databases, choosing components, generating sequences, producing experiment procedures, "
    "scoring outcomes, or judging downstream use."
)
BLOCKED_OUTPUTS_NOTICE = (
    "Blocked output families remain outside this Markdown readback layer: package export, "
    "scannable image generation, final component selection, biological part advice, sequence "
    "generation, outcome scoring, experiment procedure generation, and downstream-use judgments."
)

MARKDOWN_READBACK_KEYS: tuple[str, ...] = (
    "markdown_title",
    "markdown_lines",
    "markdown_text",
    "section_order",
    "identity_payload",
    "identity_md5",
    "boundary_notice",
    "blocked_outputs_notice",
    "empty_state",
)

SECTION_ORDER: tuple[str, ...] = (
    "title",
    "scope",
    "route_summary",
    "design_intent",
    "plant_context",
    "construct_slot_plan",
    "component_candidate_readback",
    "evidence_summary",
    "gap_queue",
    "manual_review_checklist",
    "boundary_notice",
    "identity",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _plain_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, Mapping):
        return [_plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return [_plain_value(value)]


def _json_line(value: Any) -> str:
    return json.dumps(_plain_value(value), sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _heading(lines: list[str], level: int, label: str) -> None:
    lines.append(f"{'#' * level} {label}")


def _kv(lines: list[str], label: str, value: Any) -> None:
    clean = _plain_value(value)
    if isinstance(clean, (dict, list)):
        lines.append(f"- {label}: `{_json_line(clean)}`")
    else:
        lines.append(f"- {label}: {_text(clean) or 'not recorded'}")


def _row_summary(row: Any, fields: Sequence[str]) -> str:
    mapping = _mapping_or_empty(row)
    parts = [f"{field}={_text(mapping.get(field)) or 'not recorded'}" for field in fields]
    return "; ".join(parts)


def _append_rows(lines: list[str], rows: Sequence[Any], fields: Sequence[str], empty_label: str) -> None:
    if not rows:
        lines.append(f"- {empty_label}")
        return
    for index, row in enumerate(rows, start=1):
        lines.append(f"- {index}. {_row_summary(row, fields)}")


def _title_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 1, _text(snapshot.get("package_title")) or "Plant Design Review Package Snapshot")
    _kv(lines, "Package ID", snapshot.get("package_id"))
    _kv(lines, "Package status", snapshot.get("package_status"))


def _scope_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 2, "Scope")
    _kv(lines, "Package scope", snapshot.get("package_scope"))
    lines.append("- Readback mode: documentation-only manual review")


def _route_summary_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 2, "Route Summary")
    summary = _mapping_or_empty(snapshot.get("route_summary"))
    for field in ("route_id", "route_name", "route_type", "draft_status"):
        _kv(lines, field, summary.get(field))
    _kv(lines, "plant_context", summary.get("plant_context") or {})


def _design_intent_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 2, "Design Intent")
    section = _mapping_or_empty(snapshot.get("design_intent_section"))
    _kv(lines, "target_summary", section.get("target_summary") or {})
    _append_rows(
        lines,
        _plain_list(section.get("provided_field_rows") or []),
        ("field", "value"),
        "No provided field rows recorded.",
    )
    missing = _plain_list(section.get("missing_fields") or [])
    lines.append(f"- Missing fields: {', '.join(_text(item) for item in missing) if missing else 'none recorded'}")


def _plant_context_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 2, "Plant Context")
    section = _mapping_or_empty(snapshot.get("plant_context_section"))
    _kv(lines, "plant_context", section.get("plant_context") or {})
    _kv(lines, "route_template", section.get("route_template") or {})
    _append_rows(
        lines,
        _plain_list(section.get("required_modules") or []),
        ("module_id", "module_name", "package_section"),
        "No required module rows recorded.",
    )


def _construct_slot_plan_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 2, "Construct Slot Plan")
    section = _mapping_or_empty(snapshot.get("construct_slot_plan_section"))
    _append_rows(
        lines,
        _plain_list(section.get("construct_slot_rows") or []),
        ("slot_name", "slot_type", "status", "value"),
        "No construct slot rows recorded.",
    )


def _component_candidate_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 2, "Component Candidate Readback")
    section = _mapping_or_empty(snapshot.get("component_candidate_section"))
    _kv(lines, "candidate_match_summary", section.get("candidate_match_summary") or {})
    _append_rows(
        lines,
        _plain_list(section.get("slot_candidate_rows") or []),
        ("slot_type", "component_id", "component_name", "evidence_status", "review_status"),
        "No candidate rows recorded.",
    )
    _append_rows(
        lines,
        _plain_list(section.get("unmatched_slot_rows") or []),
        ("slot_type", "candidate_status", "note"),
        "No unmatched slot rows recorded.",
    )
    lines.append("- Candidate rows are readback records for manual review, not final selections.")


def _evidence_summary_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 2, "Evidence Summary")
    section = _mapping_or_empty(snapshot.get("evidence_summary_section"))
    _append_rows(
        lines,
        _plain_list(section.get("route_evidence_rows") or []),
        ("source_id", "value"),
        "No route evidence rows recorded.",
    )
    _append_rows(
        lines,
        _plain_list(section.get("candidate_evidence_rows") or []),
        ("slot_type", "component_id", "evidence_context_status", "source_id"),
        "No candidate evidence rows recorded.",
    )


def _gap_queue_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 2, "Gap Queue")
    section = _mapping_or_empty(snapshot.get("gap_queue_section"))
    _kv(lines, "queue_summary", section.get("queue_summary") or {})
    _append_rows(
        lines,
        _plain_list(section.get("queue_items") or []),
        ("gap_id", "gap_type", "source_section", "field_name", "status"),
        "No queue items recorded.",
    )


def _manual_review_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 2, "Manual Review Checklist")
    section = _mapping_or_empty(snapshot.get("manual_review_section"))
    _append_rows(
        lines,
        _plain_list(section.get("manual_review_items") or []),
        ("review_type", "gap_type", "source_section", "field", "field_name", "status"),
        "No manual review checklist rows recorded.",
    )


def _boundary_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 2, "Boundary Notice")
    section = _mapping_or_empty(snapshot.get("boundary_section"))
    boundary = _mapping_or_empty(section.get("boundary_notice"))
    blocked = _mapping_or_empty(section.get("blocked_outputs_notice"))
    lines.append(f"- {_text(boundary.get('notice')) or BOUNDARY_NOTICE}")
    lines.append(f"- {_text(blocked.get('notice')) or BLOCKED_OUTPUTS_NOTICE}")


def _identity_section(lines: list[str], snapshot: Mapping[str, Any]) -> None:
    _heading(lines, 2, "Identity")
    _kv(lines, "identity_md5", snapshot.get("identity_md5"))
    _kv(lines, "identity_payload", snapshot.get("identity_payload") or {})


def _empty_readback() -> dict[str, Any]:
    lines = [
        "# Plant Design Review Package Snapshot",
        "## Scope",
        "- Readback mode: documentation-only manual review",
        "## Boundary Notice",
        f"- {BOUNDARY_NOTICE}",
        f"- {BLOCKED_OUTPUTS_NOTICE}",
    ]
    return {
        "markdown_title": "Plant Design Review Package Snapshot",
        "markdown_lines": lines,
        "markdown_text": "\n".join(lines),
        "section_order": list(SECTION_ORDER),
        "identity_payload": {},
        "identity_md5": "",
        "boundary_notice": {"title": "Documentation-only boundary", "notice": BOUNDARY_NOTICE},
        "blocked_outputs_notice": {"title": "Blocked output families", "notice": BLOCKED_OUTPUTS_NOTICE},
        "empty_state": {
            "is_empty": True,
            "title": "No package snapshot available",
            "message": "Provide an R386 package snapshot to build a documentation-only Markdown readback.",
        },
    }


def build_plant_design_review_package_markdown_readback(package_snapshot: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build deterministic Markdown readback data for an existing package snapshot."""
    snapshot = _mapping_or_empty(package_snapshot)
    if not snapshot:
        return _empty_readback()

    lines: list[str] = []
    _title_section(lines, snapshot)
    _scope_section(lines, snapshot)
    _route_summary_section(lines, snapshot)
    _design_intent_section(lines, snapshot)
    _plant_context_section(lines, snapshot)
    _construct_slot_plan_section(lines, snapshot)
    _component_candidate_section(lines, snapshot)
    _evidence_summary_section(lines, snapshot)
    _gap_queue_section(lines, snapshot)
    _manual_review_section(lines, snapshot)
    _boundary_section(lines, snapshot)
    _identity_section(lines, snapshot)

    boundary_section = _mapping_or_empty(snapshot.get("boundary_section"))
    boundary_notice = _mapping_or_empty(boundary_section.get("boundary_notice")) or {
        "title": "Documentation-only boundary",
        "notice": BOUNDARY_NOTICE,
    }
    blocked_outputs_notice = _mapping_or_empty(boundary_section.get("blocked_outputs_notice")) or {
        "title": "Blocked output families",
        "notice": BLOCKED_OUTPUTS_NOTICE,
    }
    result = {
        "markdown_title": _text(snapshot.get("package_title")) or "Plant Design Review Package Snapshot",
        "markdown_lines": lines,
        "markdown_text": "\n".join(lines),
        "section_order": list(SECTION_ORDER),
        "identity_payload": _plain_value(snapshot.get("identity_payload") or {}),
        "identity_md5": _text(snapshot.get("identity_md5")),
        "boundary_notice": _plain_value(boundary_notice),
        "blocked_outputs_notice": _plain_value(blocked_outputs_notice),
        "empty_state": {
            "is_empty": False,
            "title": "",
            "message": "",
        },
    }
    return {key: result[key] for key in MARKDOWN_READBACK_KEYS}
