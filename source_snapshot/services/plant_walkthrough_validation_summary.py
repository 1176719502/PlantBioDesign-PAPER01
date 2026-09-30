from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from services.plant_walkthrough_chain_runner import run_all_plant_walkthrough_chains


VALIDATION_SUMMARY_KEYS: tuple[str, ...] = (
    "total_fixtures",
    "completed_chain_count",
    "out_of_scope_count",
    "route_draft_status_summary",
    "package_snapshot_status_summary",
    "markdown_readback_availability",
    "missing_field_counts",
    "candidate_match_counts",
    "unresolved_gap_counts",
    "manual_review_item_counts",
    "boundary_compliance_summary",
    "blocked_claim_scan_summary",
    "fixture_level_summary_rows",
    "boundary_notice",
)

BOUNDARY_NOTICE = (
    "Documentation-only plant walkthrough workflow summary. It summarizes software chain "
    "completion, readback availability, gaps, candidate readback counts, manual review counts, "
    "and blocked claim checks; it is not biological validation, outcome review, route-choice "
    "guidance, experiment instruction generation, or lab-use readiness judgment."
)

BLOCKED_SCAN_TERMS: tuple[str, ...] = (
    "validated",
    "optimized",
    "best",
    "ready to build",
    "experiment-ready",
    "guaranteed expression",
    "high-yield",
    "successful production",
    "protocol",
    "wet-lab ready",
    "feasible",
    "yield prediction",
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


def _counter(values: Sequence[str]) -> dict[str, int]:
    counts = Counter(_text(value) or "not_recorded" for value in values)
    return {key: counts[key] for key in sorted(counts, key=lambda item: item.casefold())}


def _chain_outputs(chain_outputs: Sequence[Mapping[str, Any]] | None) -> list[Mapping[str, Any]]:
    if chain_outputs is None:
        return run_all_plant_walkthrough_chains()
    return [item for item in chain_outputs if isinstance(item, Mapping)]


def _scan_text(value: Any) -> str:
    if isinstance(value, Mapping):
        allowed_keys = {
            "blocked_outputs",
            "blocked_outputs_notice",
            "blocked_output_families",
            "expected_blocked_claims",
            "blocked_claims",
            "source_blocked_outputs_notices",
        }
        parts = [
            _scan_text(nested)
            for key, nested in value.items()
            if str(key) not in allowed_keys
        ]
        return " ".join(part for part in parts if part)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return " ".join(_scan_text(item) for item in value)
    return _text(value)


def _blocked_claim_scan_summary(chain_outputs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    combined_text = "\n".join(_scan_text(output) for output in chain_outputs).casefold()
    hits = {
        term: combined_text.count(term.casefold())
        for term in BLOCKED_SCAN_TERMS
        if term.casefold() in combined_text
    }
    return {
        "scan_terms": list(BLOCKED_SCAN_TERMS),
        "non_blocked_context_hits": hits,
        "scan_status": "review_passed" if not hits else "manual_review_required",
        "allowed_context_note": "Terms may appear in explicit blocked-output metadata or negative-test scan term lists.",
    }


def _fixture_row(output: Mapping[str, Any]) -> dict[str, Any]:
    route_draft = _mapping_or_empty(output.get("route_draft"))
    chain_summary = _mapping_or_empty(output.get("chain_summary"))
    candidate_summary = _mapping_or_empty(
        _mapping_or_empty(output.get("candidate_match_payload")).get("candidate_match_summary")
    )
    queue_summary = _mapping_or_empty(
        _mapping_or_empty(output.get("gap_queue_payload")).get("queue_summary")
    )
    package_snapshot = _mapping_or_empty(output.get("package_snapshot"))
    markdown_readback = _mapping_or_empty(output.get("markdown_readback"))
    return {
        "fixture_id": _text(output.get("fixture_id")),
        "chain_status": _text(chain_summary.get("chain_status")),
        "route_id": _text(route_draft.get("route_id")),
        "draft_status": _text(route_draft.get("draft_status")),
        "package_status": _text(package_snapshot.get("package_status")),
        "markdown_readback_available": bool(_text(markdown_readback.get("markdown_text"))),
        "missing_field_count": len(_plain_list(route_draft.get("missing_fields"))),
        "candidate_row_count": int(candidate_summary.get("total_candidate_rows") or 0),
        "unresolved_gap_count": len(_plain_list(_mapping_or_empty(output.get("gap_queue_payload")).get("unresolved_items"))),
        "manual_review_item_count": len(_plain_list(_mapping_or_empty(output.get("gap_queue_payload")).get("manual_review_items"))),
        "queue_item_count": int(queue_summary.get("total_items") or 0),
        "out_of_scope_guard": bool(chain_summary.get("out_of_scope_guard")),
        "boundary_status": _text(chain_summary.get("boundary_status")),
    }


def build_plant_walkthrough_validation_summary(
    chain_outputs: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Summarize R390 chain outputs as workflow validation, not biological validation."""
    outputs = _chain_outputs(chain_outputs)
    rows = [_fixture_row(output) for output in outputs]
    total = len(rows)
    completed = sum(1 for row in rows if row["chain_status"] == "workflow_chain_completed")
    out_of_scope = sum(1 for row in rows if row["out_of_scope_guard"] is True)
    markdown_available = sum(1 for row in rows if row["markdown_readback_available"] is True)
    boundary_rows = sum(1 for row in rows if row["boundary_status"] == "documentation_only_manual_review")

    result = {
        "total_fixtures": total,
        "completed_chain_count": completed,
        "out_of_scope_count": out_of_scope,
        "route_draft_status_summary": _counter([str(row["draft_status"]) for row in rows]),
        "package_snapshot_status_summary": _counter([str(row["package_status"]) for row in rows]),
        "markdown_readback_availability": {
            "available_count": markdown_available,
            "missing_count": total - markdown_available,
        },
        "missing_field_counts": {
            "total_missing_fields": sum(int(row["missing_field_count"]) for row in rows),
            "by_fixture": {str(row["fixture_id"]): int(row["missing_field_count"]) for row in rows},
        },
        "candidate_match_counts": {
            "total_candidate_rows": sum(int(row["candidate_row_count"]) for row in rows),
            "by_fixture": {str(row["fixture_id"]): int(row["candidate_row_count"]) for row in rows},
        },
        "unresolved_gap_counts": {
            "total_unresolved_gaps": sum(int(row["unresolved_gap_count"]) for row in rows),
            "by_fixture": {str(row["fixture_id"]): int(row["unresolved_gap_count"]) for row in rows},
        },
        "manual_review_item_counts": {
            "total_manual_review_items": sum(int(row["manual_review_item_count"]) for row in rows),
            "by_fixture": {str(row["fixture_id"]): int(row["manual_review_item_count"]) for row in rows},
        },
        "boundary_compliance_summary": {
            "documentation_only_rows": boundary_rows,
            "manual_review_rows": boundary_rows,
            "non_compliant_rows": total - boundary_rows,
            "summary_status": "review_passed" if boundary_rows == total else "manual_review_required",
        },
        "blocked_claim_scan_summary": _blocked_claim_scan_summary(outputs),
        "fixture_level_summary_rows": rows,
        "boundary_notice": {
            "title": "Workflow validation boundary",
            "notice": BOUNDARY_NOTICE,
        },
    }
    return {key: _plain_value(result[key]) for key in VALIDATION_SUMMARY_KEYS}
