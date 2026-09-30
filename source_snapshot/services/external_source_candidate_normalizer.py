from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ExternalSourceCandidateNormalizerError(ValueError):
    """Raised when a candidate snapshot cannot be loaded safely."""


REQUIRED_TOP_LEVEL_FIELDS = {
    "spike_id",
    "source_route",
    "retrieved_at",
    "not_runtime_seed",
    "seed_expansion_status",
    "candidate_results",
}

REQUIRED_CANDIDATE_FIELDS = {
    "query_target",
    "candidate_id",
    "source_review_status",
    "source_database",
    "source_url",
    "source_accession",
    "curation_status",
    "not_runtime_seed",
}

REQUIRED_ROW_EXPORT_FIELDS = (
    "query_target",
    "candidate_id",
    "source_database",
    "source_accession",
    "source_url",
    "source_review_status",
    "curation_status",
    "not_runtime_seed",
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _warning_row(
    *,
    message: str,
    warning_code: str,
    field: str,
    query_target: Any = "",
    candidate_id: Any = "",
    level: str = "warning",
) -> dict[str, str]:
    return {
        "level": level,
        "warning_code": warning_code,
        "field": field,
        "query_target": _text(query_target),
        "candidate_id": _text(candidate_id),
        "message": message,
    }


def _build_warning_rows(
    payload: dict[str, Any],
    candidate_results: list[Any],
) -> tuple[list[dict[str, str]], list[dict[str, str]], int]:
    warning_rows: list[dict[str, str]] = []
    review_required_rows: list[dict[str, str]] = []
    records_missing_trace_count = 0

    if payload.get("not_runtime_seed") is not True:
        warning_rows.append(
            _warning_row(
                message="Top-level not_runtime_seed must remain true for documentation-only candidate snapshots.",
                warning_code="top_level_not_runtime_seed_not_true",
                field="not_runtime_seed",
                level="error",
            )
        )
    if _text(payload.get("seed_expansion_status")) != "blocked":
        warning_rows.append(
            _warning_row(
                message="Seed expansion must remain blocked for external source candidate snapshots.",
                warning_code="seed_expansion_status_not_blocked",
                field="seed_expansion_status",
                level="error",
            )
        )

    for index, row in enumerate(candidate_results, start=1):
        if not isinstance(row, dict):
            warning_rows.append(
                _warning_row(
                    message=f"candidate_results row {index} is not an object and requires manual review.",
                    warning_code="candidate_result_not_object",
                    field="candidate_results",
                    candidate_id=f"row-{index}",
                    level="error",
                )
            )
            review_required_rows.append(
                {
                    "query_target": "",
                    "candidate_id": f"row-{index}",
                    "reason": "candidate_results row is not an object",
                }
            )
            records_missing_trace_count += 1
            continue

        query_target = row.get("query_target")
        candidate_id = row.get("candidate_id") or f"row-{index}"

        for field in sorted(REQUIRED_CANDIDATE_FIELDS):
            if field not in row or row.get(field) in (None, ""):
                warning_rows.append(
                    _warning_row(
                        message=f"Candidate row is missing required field: {field}.",
                        warning_code="missing_required_field",
                        field=field,
                        query_target=query_target,
                        candidate_id=candidate_id,
                        level="error",
                    )
                )

        source_review_status = _text(row.get("source_review_status"))
        source_url = _text(row.get("source_url"))
        source_accession = _text(row.get("source_accession"))
        stable_identifier = source_accession or _text(row.get("stable_source_identifier"))

        missing_trace = False
        if source_review_status == "source_candidate_identified":
            if not source_url:
                warning_rows.append(
                    _warning_row(
                        message="source_candidate_identified rows must include a source_url.",
                        warning_code="identified_candidate_missing_source_url",
                        field="source_url",
                        query_target=query_target,
                        candidate_id=candidate_id,
                        level="error",
                    )
                )
                missing_trace = True
            if not stable_identifier:
                warning_rows.append(
                    _warning_row(
                        message="source_candidate_identified rows must include a source_accession or stable source identifier.",
                        warning_code="identified_candidate_missing_stable_identifier",
                        field="source_accession",
                        query_target=query_target,
                        candidate_id=candidate_id,
                        level="error",
                    )
                )
                missing_trace = True

        if missing_trace:
            records_missing_trace_count += 1

        if row.get("not_runtime_seed") is not True:
            warning_rows.append(
                _warning_row(
                    message="Candidate rows must keep not_runtime_seed set to true.",
                    warning_code="candidate_not_runtime_seed_not_true",
                    field="not_runtime_seed",
                    query_target=query_target,
                    candidate_id=candidate_id,
                    level="error",
                )
            )

        runtime_seed_ready = bool(row.get("runtime_seed_ready"))
        curated_for_runtime_seed = bool(row.get("curated_for_runtime_seed"))

        if runtime_seed_ready:
            warning_rows.append(
                _warning_row(
                    message="runtime_seed_ready must not appear in external source candidate snapshots.",
                    warning_code="runtime_seed_ready_present",
                    field="runtime_seed_ready",
                    query_target=query_target,
                    candidate_id=candidate_id,
                    level="error",
                )
            )
        if curated_for_runtime_seed:
            warning_rows.append(
                _warning_row(
                    message="curated_for_runtime_seed must not appear in external source candidate snapshots.",
                    warning_code="curated_for_runtime_seed_present",
                    field="curated_for_runtime_seed",
                    query_target=query_target,
                    candidate_id=candidate_id,
                    level="error",
                )
            )

        needs_review = (
            source_review_status != "no_acceptable_candidate_selected"
            and (
                source_review_status != "source_candidate_identified"
                or _text(row.get("metadata_completeness_status")) in {"source_review_required", "not_curated_yet"}
                or _text(row.get("curation_status")) != "curated"
                or missing_trace
                or row.get("not_runtime_seed") is not True
                or runtime_seed_ready
                or curated_for_runtime_seed
            )
        )
        if needs_review:
            review_required_rows.append(
                {
                    "query_target": _text(query_target),
                    "candidate_id": _text(candidate_id),
                    "reason": "Candidate remains documentation-only and requires manual source review.",
                }
            )

    return warning_rows, review_required_rows, records_missing_trace_count


def load_external_source_candidate_snapshot(path: str | Path) -> dict[str, Any]:
    snapshot_path = Path(path)
    try:
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExternalSourceCandidateNormalizerError(
            f"Unable to read external source candidate snapshot: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ExternalSourceCandidateNormalizerError(
            f"Invalid external source candidate snapshot JSON: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise ExternalSourceCandidateNormalizerError(
            "External source candidate snapshot payload must be a JSON object."
        )
    return payload


def list_external_source_candidate_rows(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    candidate_results = snapshot.get("candidate_results")
    if not isinstance(candidate_results, list):
        return []

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(candidate_results, start=1):
        row = item if isinstance(item, dict) else {}
        export_row = {field: row.get(field) for field in REQUIRED_ROW_EXPORT_FIELDS}
        export_row["stable_source_identifier"] = _text(row.get("source_accession")) or _text(
            row.get("stable_source_identifier")
        )
        export_row["row_index"] = index
        rows.append(export_row)
    return rows


def build_external_source_candidate_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    missing_top_level = sorted(
        field for field in REQUIRED_TOP_LEVEL_FIELDS if field not in snapshot
    )
    candidate_results = snapshot.get("candidate_results")
    if candidate_results is None:
        candidate_results = []
    if not isinstance(candidate_results, list):
        candidate_results = []

    warning_rows, review_required_rows, records_missing_trace_count = _build_warning_rows(
        snapshot,
        candidate_results,
    )

    candidate_rows = list_external_source_candidate_rows(
        {**snapshot, "candidate_results": candidate_results}
    )
    source_candidate_identified_count = sum(
        1
        for row in candidate_results
        if isinstance(row, dict)
        and _text(row.get("source_review_status")) == "source_candidate_identified"
    )
    no_acceptable_candidate_selected_count = sum(
        1
        for row in candidate_results
        if isinstance(row, dict)
        and _text(row.get("source_review_status")) == "no_acceptable_candidate_selected"
    )
    not_runtime_seed_count = sum(
        1
        for row in candidate_results
        if isinstance(row, dict) and row.get("not_runtime_seed") is True
    )
    runtime_seed_ready_count = sum(
        1 for row in candidate_results if isinstance(row, dict) and bool(row.get("runtime_seed_ready"))
    )
    curated_for_runtime_seed_count = sum(
        1
        for row in candidate_results
        if isinstance(row, dict) and bool(row.get("curated_for_runtime_seed"))
    )

    if missing_top_level:
        warning_rows = [
            _warning_row(
                message=f"Snapshot is missing required top-level field: {field}.",
                warning_code="missing_top_level_field",
                field=field,
                level="error",
            )
            for field in missing_top_level
        ] + warning_rows

    if "candidate_results" not in snapshot:
        warning_rows.append(
            _warning_row(
                message="Snapshot is missing candidate_results.",
                warning_code="missing_candidate_results",
                field="candidate_results",
                level="error",
            )
        )
    elif not isinstance(snapshot.get("candidate_results"), list):
        warning_rows.append(
            _warning_row(
                message="candidate_results must be a list.",
                warning_code="candidate_results_not_list",
                field="candidate_results",
                level="error",
            )
        )

    return {
        "spike_id": _text(snapshot.get("spike_id")),
        "source_route": _text(snapshot.get("source_route")),
        "retrieved_at": _text(snapshot.get("retrieved_at")),
        "candidate_count": len(candidate_results),
        "query_target_count": len(snapshot.get("query_targets"))
        if isinstance(snapshot.get("query_targets"), list)
        else 0,
        "source_candidate_identified_count": source_candidate_identified_count,
        "no_acceptable_candidate_selected_count": no_acceptable_candidate_selected_count,
        "not_runtime_seed_count": not_runtime_seed_count,
        "runtime_seed_ready_count": runtime_seed_ready_count,
        "curated_for_runtime_seed_count": curated_for_runtime_seed_count,
        "records_missing_trace_count": records_missing_trace_count,
        "seed_expansion_status": _text(snapshot.get("seed_expansion_status")),
        "review_required_count": len(review_required_rows),
        "warning_rows": warning_rows,
        "review_required_rows": review_required_rows,
        "candidate_rows": candidate_rows,
    }


def normalize_external_source_candidate_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    return build_external_source_candidate_summary(snapshot)
