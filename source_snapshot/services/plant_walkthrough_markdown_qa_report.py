from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_walkthrough_chain_runner import run_all_plant_walkthrough_chains
from services.plant_walkthrough_validation_summary import build_plant_walkthrough_validation_summary


REPORT_KEYS: tuple[str, ...] = (
    "markdown_title",
    "markdown_lines",
    "markdown_text",
    "section_order",
    "fixture_summary_table",
    "chain_output_availability",
    "gap_manual_review_summary",
    "boundary_compliance_summary",
    "blocked_claim_scan_summary",
    "boundary_notice",
)

SECTION_ORDER: tuple[str, ...] = (
    "title",
    "not_biological_validation_notice",
    "documentation_only_manual_review_notice",
    "fixture_summary_table",
    "chain_output_availability",
    "gap_manual_review_summary",
    "boundary_compliance_summary",
    "blocked_claim_scan_summary",
)

BOUNDARY_NOTICE = (
    "This QA report is documentation-only/manual-review software evidence. It is not biological "
    "validation and does not choose routes or components, generate sequences, produce experiment "
    "instructions, score outcomes, claim improved pathways, or judge lab-use readiness."
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


def _summary_and_outputs(
    summary: Mapping[str, Any] | None,
    chain_outputs: Sequence[Mapping[str, Any]] | None,
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    outputs = (
        [item for item in chain_outputs if isinstance(item, Mapping)]
        if chain_outputs is not None
        else run_all_plant_walkthrough_chains()
    )
    summary_map = summary if isinstance(summary, Mapping) else build_plant_walkthrough_validation_summary(outputs)
    return summary_map, outputs


def _fixture_summary_table(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _plain_list(summary.get("fixture_level_summary_rows")):
        row_map = _mapping_or_empty(row)
        rows.append(
            {
                "fixture_id": _text(row_map.get("fixture_id")),
                "chain_status": _text(row_map.get("chain_status")),
                "route_id": _text(row_map.get("route_id")),
                "package_status": _text(row_map.get("package_status")),
                "markdown_readback_available": bool(row_map.get("markdown_readback_available")),
                "missing_field_count": int(row_map.get("missing_field_count") or 0),
                "candidate_row_count": int(row_map.get("candidate_row_count") or 0),
                "unresolved_gap_count": int(row_map.get("unresolved_gap_count") or 0),
                "manual_review_item_count": int(row_map.get("manual_review_item_count") or 0),
                "out_of_scope_guard": bool(row_map.get("out_of_scope_guard")),
            }
        )
    return rows


def _chain_output_availability(chain_outputs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    required_keys = (
        "route_draft",
        "presenter_payload",
        "candidate_match_payload",
        "gap_queue_payload",
        "package_snapshot",
        "markdown_readback",
    )
    by_fixture: dict[str, dict[str, bool]] = {}
    totals = {key: 0 for key in required_keys}
    for output in chain_outputs:
        fixture_id = _text(output.get("fixture_id"))
        availability = {key: bool(output.get(key)) for key in required_keys}
        by_fixture[fixture_id] = availability
        for key, available in availability.items():
            totals[key] += 1 if available else 0
    return {
        "required_output_keys": list(required_keys),
        "available_counts": totals,
        "by_fixture": by_fixture,
    }


def _gap_manual_review_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    unresolved = _mapping_or_empty(summary.get("unresolved_gap_counts"))
    manual = _mapping_or_empty(summary.get("manual_review_item_counts"))
    missing = _mapping_or_empty(summary.get("missing_field_counts"))
    return {
        "total_missing_fields": int(missing.get("total_missing_fields") or 0),
        "total_unresolved_gaps": int(unresolved.get("total_unresolved_gaps") or 0),
        "total_manual_review_items": int(manual.get("total_manual_review_items") or 0),
        "unresolved_gaps_by_fixture": _plain_value(unresolved.get("by_fixture") or {}),
        "manual_review_items_by_fixture": _plain_value(manual.get("by_fixture") or {}),
    }


def _append_table(lines: list[str], rows: Sequence[Mapping[str, Any]]) -> None:
    lines.append(
        "| Fixture | Chain status | Route | Package status | Markdown | Missing | Candidates | Gaps | Manual review | Scope guard |"
    )
    lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        lines.append(
            "| {fixture_id} | {chain_status} | {route_id} | {package_status} | {markdown} | {missing} | {candidates} | {gaps} | {manual} | {guard} |".format(
                fixture_id=_text(row.get("fixture_id")),
                chain_status=_text(row.get("chain_status")),
                route_id=_text(row.get("route_id")),
                package_status=_text(row.get("package_status")),
                markdown="yes" if row.get("markdown_readback_available") else "no",
                missing=int(row.get("missing_field_count") or 0),
                candidates=int(row.get("candidate_row_count") or 0),
                gaps=int(row.get("unresolved_gap_count") or 0),
                manual=int(row.get("manual_review_item_count") or 0),
                guard="yes" if row.get("out_of_scope_guard") else "no",
            )
        )


def _build_lines(
    *,
    summary: Mapping[str, Any],
    fixture_table: Sequence[Mapping[str, Any]],
    availability: Mapping[str, Any],
    gap_summary: Mapping[str, Any],
) -> list[str]:
    lines = [
        "# Plant Walkthrough QA Report",
        "## Not Biological Validation Notice",
        "- This report is workflow validation, not biological validation.",
        "## Documentation-Only Manual-Review Notice",
        f"- {BOUNDARY_NOTICE}",
        "## Fixture Summary Table",
    ]
    _append_table(lines, fixture_table)
    lines.extend(
        [
            "## Chain Output Availability",
            f"- Required output keys: {', '.join(_text(key) for key in _plain_list(availability.get('required_output_keys')))}",
            f"- Available counts: {_plain_value(availability.get('available_counts') or {})}",
            "## Gap And Manual Review Summary",
            f"- Total missing fields: {int(gap_summary.get('total_missing_fields') or 0)}",
            f"- Total unresolved gaps: {int(gap_summary.get('total_unresolved_gaps') or 0)}",
            f"- Total manual review items: {int(gap_summary.get('total_manual_review_items') or 0)}",
            "## Boundary Compliance Summary",
            f"- {_plain_value(summary.get('boundary_compliance_summary') or {})}",
            "## Blocked Claim Scan Summary",
            f"- {_plain_value(summary.get('blocked_claim_scan_summary') or {})}",
        ]
    )
    return lines


def build_plant_walkthrough_markdown_qa_report(
    summary: Mapping[str, Any] | None = None,
    chain_outputs: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a stable Markdown QA report as plain data without writing files."""
    summary_map, outputs = _summary_and_outputs(summary, chain_outputs)
    fixture_table = _fixture_summary_table(summary_map)
    availability = _chain_output_availability(outputs)
    gap_summary = _gap_manual_review_summary(summary_map)
    lines = _build_lines(
        summary=summary_map,
        fixture_table=fixture_table,
        availability=availability,
        gap_summary=gap_summary,
    )
    result = {
        "markdown_title": "Plant Walkthrough QA Report",
        "markdown_lines": lines,
        "markdown_text": "\n".join(lines),
        "section_order": list(SECTION_ORDER),
        "fixture_summary_table": fixture_table,
        "chain_output_availability": availability,
        "gap_manual_review_summary": gap_summary,
        "boundary_compliance_summary": _plain_value(summary_map.get("boundary_compliance_summary") or {}),
        "blocked_claim_scan_summary": _plain_value(summary_map.get("blocked_claim_scan_summary") or {}),
        "boundary_notice": {
            "title": "Documentation-only/manual-review notice",
            "notice": BOUNDARY_NOTICE,
        },
    }
    return {key: _plain_value(result[key]) for key in REPORT_KEYS}
