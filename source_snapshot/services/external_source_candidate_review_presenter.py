from __future__ import annotations

from pathlib import Path
from typing import Any

from services import external_source_candidate_normalizer as normalizer


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _bool_label(value: bool, *, true_label: str, false_label: str) -> str:
    return true_label if value else false_label


def build_candidate_review_cards(summary: dict[str, Any]) -> list[dict[str, str]]:
    seed_expansion_status = _text(summary.get("seed_expansion_status"), "unknown")
    return [
        {"label": "Candidate records", "value": str(summary.get("candidate_count", 0))},
        {
            "label": "Source candidates identified",
            "value": str(summary.get("source_candidate_identified_count", 0)),
        },
        {
            "label": "Missing trace records",
            "value": str(summary.get("records_missing_trace_count", 0)),
        },
        {"label": "Review required", "value": str(summary.get("review_required_count", 0))},
        {
            "label": "Runtime seed ready",
            "value": str(summary.get("runtime_seed_ready_count", 0)),
        },
        {"label": "Seed expansion status", "value": seed_expansion_status or "unknown"},
    ]


def build_candidate_review_rows(candidate_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    review_rows: list[dict[str, Any]] = []

    for index, row in enumerate(candidate_rows, start=1):
        current = row if isinstance(row, dict) else {}
        query_target = _text(current.get("query_target"), "Unknown query target")
        candidate_id = _text(current.get("candidate_id"), f"candidate-row-{index}")
        source_database = _text(current.get("source_database"), "Unknown source database")
        source_accession = _text(current.get("source_accession"), "missing-accession")
        source_url = _text(current.get("source_url"))
        source_review_status = _text(current.get("source_review_status"), "review_required")
        curation_status = _text(current.get("curation_status"), "not_curated_yet")
        not_runtime_seed = current.get("not_runtime_seed") is True
        runtime_seed_ready = bool(current.get("runtime_seed_ready"))
        curated_for_runtime_seed = bool(current.get("curated_for_runtime_seed"))

        row_status = "review_required"
        if runtime_seed_ready or curated_for_runtime_seed:
            row_status = "boundary_warning"
        elif source_review_status == "no_acceptable_candidate_selected":
            row_status = "no_candidate_selected"
        elif source_review_status == "source_candidate_identified":
            row_status = "trace_only_candidate"

        review_rows.append(
            {
                "query_target": query_target,
                "candidate_id": candidate_id,
                "source_database": source_database,
                "source_accession": source_accession,
                "source_url": source_url,
                "source_review_status": source_review_status,
                "curation_status": curation_status,
                "not_runtime_seed": not_runtime_seed,
                "display_label": f"{query_target} -> {source_accession}",
                "trace_label": f"Trace-only candidate source: {source_database} accession {source_accession}",
                "review_status_label": _build_review_status_label(
                    source_review_status=source_review_status,
                    curation_status=curation_status,
                    not_runtime_seed=not_runtime_seed,
                    runtime_seed_ready=runtime_seed_ready,
                    curated_for_runtime_seed=curated_for_runtime_seed,
                ),
                "row_status": row_status,
            }
        )

    return review_rows


def _build_review_status_label(
    *,
    source_review_status: str,
    curation_status: str,
    not_runtime_seed: bool,
    runtime_seed_ready: bool,
    curated_for_runtime_seed: bool,
) -> str:
    if runtime_seed_ready or curated_for_runtime_seed:
        return "Boundary warning: runtime-seed-positive status must not appear in this review presenter."
    if source_review_status == "no_acceptable_candidate_selected":
        return "No acceptable candidate selected; review remains documentation-only."
    trace_label = _bool_label(
        not_runtime_seed,
        true_label="documentation-only trace",
        false_label="boundary flag mismatch",
    )
    return (
        "Source candidate identified for manual review; "
        f"{trace_label}; curation status: {curation_status}."
    )


def build_candidate_warning_rows(summary: dict[str, Any]) -> list[dict[str, str]]:
    warning_rows = summary.get("warning_rows")
    if not isinstance(warning_rows, list):
        warning_rows = []

    rows: list[dict[str, str]] = []
    for row in warning_rows:
        current = row if isinstance(row, dict) else {}
        rows.append(
            {
                "level": _text(current.get("level"), "warning"),
                "warning_code": _text(current.get("warning_code"), "review_warning"),
                "field": _text(current.get("field")),
                "query_target": _text(current.get("query_target")),
                "candidate_id": _text(current.get("candidate_id")),
                "message": _text(current.get("message"), "Review warning."),
            }
        )

    if _text(summary.get("seed_expansion_status")) != "blocked":
        rows.append(
            {
                "level": "error",
                "warning_code": "presenter_seed_expansion_not_blocked",
                "field": "seed_expansion_status",
                "query_target": "",
                "candidate_id": "",
                "message": "Seed expansion status must remain blocked in this documentation-only review presenter.",
            }
        )

    if int(summary.get("runtime_seed_ready_count", 0) or 0) > 0:
        rows.append(
            {
                "level": "error",
                "warning_code": "presenter_runtime_seed_ready_present",
                "field": "runtime_seed_ready_count",
                "query_target": "",
                "candidate_id": "",
                "message": "Runtime seed ready signals must not appear in external source candidate review presentation.",
            }
        )

    if int(summary.get("curated_for_runtime_seed_count", 0) or 0) > 0:
        rows.append(
            {
                "level": "error",
                "warning_code": "presenter_curated_for_runtime_seed_present",
                "field": "curated_for_runtime_seed_count",
                "query_target": "",
                "candidate_id": "",
                "message": "Curated-for-runtime-seed signals must not appear in external source candidate review presentation.",
            }
        )

    if int(summary.get("records_missing_trace_count", 0) or 0) > 0:
        rows.append(
            {
                "level": "warning",
                "warning_code": "presenter_missing_trace_records",
                "field": "records_missing_trace_count",
                "query_target": "",
                "candidate_id": "",
                "message": "One or more candidate records are missing trace fields and still require manual repair.",
            }
        )

    return rows


def _build_blocked_messages(summary: dict[str, Any]) -> list[str]:
    messages = [
        "Seed expansion remains blocked. Candidate traces cannot enter the runtime seed.",
        "External source candidates cannot enter the curated manifest from this presenter.",
    ]
    if _text(summary.get("seed_expansion_status")) != "blocked":
        messages.append(
            "Boundary mismatch detected: seed expansion status is not blocked and requires manual review."
        )
    return messages


def _build_next_action_messages(summary: dict[str, Any]) -> list[str]:
    messages = [
        "Review candidate trace records manually before any curated intake decision.",
        "Confirm publication, motif, and route-specific usage fields outside this presenter.",
        "Keep S51061.1 and JX947345.1 as trace-only candidate sources until later human review is completed.",
    ]
    if int(summary.get("records_missing_trace_count", 0) or 0) > 0:
        messages.append(
            "Repair missing trace fields before using this snapshot in any downstream documentation review."
        )
    return messages


def build_external_source_candidate_review_view(snapshot: dict[str, Any]) -> dict[str, Any]:
    summary = normalizer.build_external_source_candidate_summary(snapshot)
    raw_candidate_rows = snapshot.get("candidate_results")
    if not isinstance(raw_candidate_rows, list):
        raw_candidate_rows = summary.get("candidate_rows", [])
    candidate_rows = build_candidate_review_rows(raw_candidate_rows)
    warning_rows = build_candidate_warning_rows(summary)

    empty_state_message = ""
    if not candidate_rows:
        empty_state_message = (
            "No candidate review rows are available. This snapshot remains documentation-only and requires manual source review."
        )

    return {
        "title": "External Source Candidate Review",
        "subtitle": "Documentation-only candidate trace presentation for manual review.",
        "boundary_message": (
            "Documentation-only review view. Candidate traces remain not runtime seed and cannot be treated as curated manifest or runtime seed content."
        ),
        "source_route": _text(summary.get("source_route"), "Unknown source route"),
        "retrieved_at": _text(summary.get("retrieved_at")),
        "seed_expansion_status": _text(summary.get("seed_expansion_status"), "unknown"),
        "summary_cards": build_candidate_review_cards(summary),
        "candidate_rows": candidate_rows,
        "warning_rows": warning_rows,
        "blocked_messages": _build_blocked_messages(summary),
        "next_action_messages": _build_next_action_messages(summary),
        "empty_state_message": empty_state_message,
    }


def build_external_source_candidate_review_view_from_path(path: str | Path) -> dict[str, Any]:
    snapshot = normalizer.load_external_source_candidate_snapshot(path)
    return build_external_source_candidate_review_view(snapshot)
