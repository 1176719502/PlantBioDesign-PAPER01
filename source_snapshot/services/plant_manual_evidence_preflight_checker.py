"""Read-only preflight checks for plant manual evidence records.

R193 adds a plain-dict checker for R191/R192-style manual evidence inputs.
It does not import evidence, write files, or change the R189 admission gate.
"""

from __future__ import annotations

from typing import Any

from services.plant_real_data_admission_gate import (
    BEGINNER_PREVIEW,
    PACKAGE_DRAFT_SUPPORT,
    evaluate_real_seed_record_admission,
)


SOURCE_FIELDS = (
    "source_url_or_identifier",
    "doi",
    "accession",
    "repository_id",
    "citation_text",
)

PLACEHOLDER_MARKERS = (
    "todo",
    "placeholder",
    "demo",
    "example",
    "sample",
)

MANUAL_OR_UNVERIFIED_FLAGS = {
    "user_supplied",
    "user_supplied_unverified",
    "unverified",
}

CONFLICT_BLOCKERS = {
    "conflicting_sources",
    "route_scope_mismatch",
    "duplicate_needs_review",
    "unresolved",
}

SAFE_EVIDENCE_TYPES = {
    "evidence_note",
    "source_note",
    "literature_note",
    "manual_review_note",
    "curator_note",
}


def preflight_manual_evidence_record(
    record: dict[str, Any], options: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return a plain dict preflight result for one manual evidence record."""

    if options is not None and not isinstance(options, dict):
        options = {}

    if not isinstance(record, dict):
        return _fail_closed_result(
            record={},
            missing_required_fields=["record"],
            blocking_reasons=["record must be a dict"],
            warnings=[],
            malformed=True,
        )

    extracted = _extract_manual_record(record)
    missing_required_fields = _missing_required_fields(extracted)
    warnings = _preflight_warnings(record)
    blocking_reasons: list[str] = []

    if missing_required_fields:
        blocking_reasons.extend(
            f"missing required field: {field}" for field in missing_required_fields
        )

    source_status = _source_status(extracted)
    placeholder_status = _placeholder_status(record)
    evidence_type_status = _evidence_type_status(extracted)

    if source_status["status"] == "missing_source":
        blocking_reasons.append("missing source trail")
    if evidence_type_status["status"] == "missing_evidence_type":
        blocking_reasons.append("missing evidence type")
    if evidence_type_status["status"] == "unsupported_evidence_type":
        blocking_reasons.append(
            f"unsupported evidence type: {evidence_type_status['evidence_type']}"
        )

    conflict_status = extracted["review"].get("conflict_status") or "unresolved"
    if conflict_status in CONFLICT_BLOCKERS:
        blocking_reasons.append(f"conflict_status is {conflict_status}")

    provenance_status = extracted["review"].get("provenance_status") or "missing_source"
    deprecated_flag = bool(extracted["review"].get("deprecated_flag", False))
    if deprecated_flag or provenance_status == "deprecated_source":
        blocking_reasons.append("record or source is deprecated")

    admission_record = _to_admission_record(extracted)
    package_gate = evaluate_real_seed_record_admission(
        admission_record, intended_usage=PACKAGE_DRAFT_SUPPORT
    )
    beginner_gate = evaluate_real_seed_record_admission(
        admission_record, intended_usage=BEGINNER_PREVIEW
    )

    package_blockers = list(blocking_reasons)
    if placeholder_status["has_placeholder_values"]:
        package_blockers.append("placeholder/example/demo values require manual review")
    if package_gate["blocking_reasons"]:
        package_blockers.extend(
            f"R189 gate: {reason}" for reason in package_gate["blocking_reasons"]
        )
    if package_gate["allowed"] is not True:
        package_blockers.append(
            f"R189 gate status is {package_gate['admission_status']}"
        )

    package_supported = package_gate["allowed"] is True and not package_blockers
    manual_review_state = _manual_review_state(extracted, blocking_reasons, package_supported)
    preflight_status = _preflight_status(
        blocking_reasons=blocking_reasons,
        manual_review_state=manual_review_state,
        package_supported=package_supported,
    )

    if _requested_preflight_override(record):
        warnings.append("admission_gate_preflight values are advisory and cannot override R189")

    result = {
        "preflight_status": preflight_status,
        "manual_review_state": manual_review_state,
        "package_draft_support_preview": {
            "status": "supported" if package_supported else "blocked",
            "supported": package_supported,
            "blocking_reasons": _unique(package_blockers),
        },
        "missing_required_fields": _unique(missing_required_fields),
        "blocking_reasons": _unique(blocking_reasons),
        "warnings": _unique(warnings),
        "source_status": source_status,
        "placeholder_status": placeholder_status,
        "evidence_type_status": evidence_type_status,
        "admission_gate_alignment": {
            "r189_gate_used": True,
            "r189_gate_can_be_overridden": False,
            "package_draft_support_status": package_gate["admission_status"],
            "package_draft_support_allowed": bool(package_gate["allowed"]),
            "beginner_preview_status": beginner_gate["admission_status"],
            "beginner_preview_allowed": bool(beginner_gate["allowed"]),
            "preflight_imports_evidence": False,
            "preflight_writes_files": False,
        },
        "traceability": {
            "record_id": admission_record["record_id"],
            "record_type": admission_record["record_type"],
            "display_name": admission_record["display_name"],
            "route_scope": admission_record["route_scope"],
            "source_fields_present": [
                field for field in SOURCE_FIELDS if _present(admission_record.get(field))
            ],
            "input_shape": extracted["input_shape"],
        },
    }
    return result


def preflight_manual_evidence_batch(
    records: list[dict[str, Any]], options: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Return a plain dict preflight result for a list of manual evidence records."""

    if not isinstance(records, list):
        return {
            "preflight_status": "blocked",
            "records": [],
            "summary": {
                "total_records": 0,
                "ready_records": 0,
                "manual_review_records": 0,
                "blocked_records": 0,
                "package_draft_supported_records": 0,
                "beginner_preview_allowed_records": 0,
                "malformed_records": 1,
            },
            "blocking_reasons": ["records must be a list"],
            "warnings": [],
        }

    record_results = [
        preflight_manual_evidence_record(record, options=options) for record in records
    ]
    summary = {
        "total_records": len(record_results),
        "ready_records": sum(
            1
            for result in record_results
            if result["preflight_status"] == "package_draft_support_preview_ready"
        ),
        "manual_review_records": sum(
            1
            for result in record_results
            if result["manual_review_state"] == "manual_review_required"
        ),
        "blocked_records": sum(
            1 for result in record_results if result["preflight_status"] == "blocked"
        ),
        "package_draft_supported_records": sum(
            1
            for result in record_results
            if result["package_draft_support_preview"]["supported"] is True
        ),
        "beginner_preview_allowed_records": sum(
            1
            for result in record_results
            if result["admission_gate_alignment"]["beginner_preview_allowed"] is True
        ),
        "malformed_records": sum(
            1
            for result in record_results
            if "record" in result["missing_required_fields"]
        ),
    }
    return {
        "preflight_status": "blocked"
        if summary["blocked_records"]
        else "package_draft_support_preview_ready"
        if summary["ready_records"] == summary["total_records"] and summary["total_records"]
        else "manual_review_required",
        "records": record_results,
        "summary": summary,
        "blocking_reasons": _unique(
            reason
            for result in record_results
            for reason in result["blocking_reasons"]
        ),
        "warnings": _unique(
            warning for result in record_results for warning in result["warnings"]
        ),
    }


def _extract_manual_record(record: dict[str, Any]) -> dict[str, Any]:
    metadata = _section(record, "evidence_entry_metadata")
    source = _section(record, "source_identity")
    scope = _section(record, "evidence_scope")
    review = _section(record, "provenance_and_review")

    if not any((metadata, source, scope, review)):
        metadata = record
        source = record
        scope = record
        review = record
        input_shape = "flat_record"
    else:
        input_shape = "manual_evidence_template"

    return {
        "metadata": metadata,
        "source": source,
        "scope": scope,
        "review": review,
        "input_shape": input_shape,
    }


def _to_admission_record(extracted: dict[str, Any]) -> dict[str, Any]:
    metadata = extracted["metadata"]
    source = extracted["source"]
    scope = extracted["scope"]
    review = extracted["review"]
    return {
        "record_id": _text(metadata.get("evidence_entry_id") or metadata.get("record_id")),
        "record_type": _text(metadata.get("record_type") or "manual_evidence_entry"),
        "display_name": _text(source.get("source_title") or source.get("display_name")),
        "route_scope": _text(scope.get("route_scope")),
        "source_url_or_identifier": _text(source.get("source_url_or_identifier")),
        "doi": _text(source.get("doi")),
        "accession": _text(source.get("accession")),
        "repository_id": _text(source.get("repository_id")),
        "citation_text": _text(source.get("citation_text")),
        "source_type": _text(source.get("source_type")),
        "provenance_status": _text(review.get("provenance_status")),
        "manual_review_status": _text(review.get("manual_review_status")),
        "allowed_usage_scope": _text(review.get("allowed_usage_scope")),
        "demo_or_real_flag": _text(review.get("demo_or_real_flag")),
        "conflict_status": _text(review.get("conflict_status")),
        "deprecated_flag": bool(review.get("deprecated_flag", False)),
    }


def _missing_required_fields(extracted: dict[str, Any]) -> list[str]:
    metadata = extracted["metadata"]
    source = extracted["source"]
    scope = extracted["scope"]
    missing = []
    if not _present(metadata.get("evidence_entry_id") or metadata.get("record_id")):
        missing.append("evidence_entry_metadata.evidence_entry_id")
    if not _present(source.get("source_title") or source.get("display_name")):
        missing.append("source_identity.source_title")
    if not _present(scope.get("route_scope")):
        missing.append("evidence_scope.route_scope")
    if not _present(source.get("source_type")):
        missing.append("source_identity.source_type")
    return missing


def _source_status(extracted: dict[str, Any]) -> dict[str, Any]:
    source = extracted["source"]
    review = extracted["review"]
    present_fields = [field for field in SOURCE_FIELDS if _present(source.get(field))]
    source_type = _text(source.get("source_type"))
    demo_or_real_flag = _text(review.get("demo_or_real_flag"))
    provenance_status = _text(review.get("provenance_status")) or "missing_source"

    if not present_fields:
        status = "missing_source"
    elif (
        source_type == "user_supplied"
        or demo_or_real_flag in MANUAL_OR_UNVERIFIED_FLAGS
        or provenance_status == "user_supplied_needs_review"
    ):
        status = "source_present_needs_manual_review"
    elif provenance_status == "source_verified":
        status = "source_present_reviewed_for_documentation"
    else:
        status = "source_present_needs_manual_review"

    return {
        "status": status,
        "source_fields_present": present_fields,
        "source_type": source_type,
        "input_provenance_status": provenance_status,
    }


def _placeholder_status(record: dict[str, Any]) -> dict[str, Any]:
    paths = []
    for path, value in _walk_plain_values(record):
        lowered = _text(value).lower()
        if any(marker in lowered for marker in PLACEHOLDER_MARKERS):
            paths.append(path)
    return {
        "status": "placeholder_or_demo_present" if paths else "no_placeholder_detected",
        "has_placeholder_values": bool(paths),
        "placeholder_fields": sorted(paths),
    }


def _evidence_type_status(extracted: dict[str, Any]) -> dict[str, Any]:
    scope = extracted["scope"]
    evidence_type = _text(
        scope.get("claim_type")
        or scope.get("evidence_type")
        or scope.get("record_family")
        or scope.get("component_type_or_record_family")
    )
    if not evidence_type:
        return {"status": "missing_evidence_type", "evidence_type": ""}
    if evidence_type not in SAFE_EVIDENCE_TYPES:
        return {"status": "unsupported_evidence_type", "evidence_type": evidence_type}
    return {"status": "evidence_type_recorded", "evidence_type": evidence_type}


def _manual_review_state(
    extracted: dict[str, Any],
    blocking_reasons: list[str],
    package_supported: bool,
) -> str:
    if package_supported:
        return "reviewed_for_documentation"
    if any("missing required field" in reason for reason in blocking_reasons):
        return "cannot_review_until_required_fields_are_present"
    if "missing source trail" in blocking_reasons:
        return "cannot_review_until_source_is_recorded"
    manual_review_status = _text(extracted["review"].get("manual_review_status"))
    if manual_review_status == "reviewed_for_documentation":
        return "reviewed_for_documentation_package_blocked"
    return "manual_review_required"


def _preflight_status(
    *,
    blocking_reasons: list[str],
    manual_review_state: str,
    package_supported: bool,
) -> str:
    if package_supported:
        return "package_draft_support_preview_ready"
    if manual_review_state == "manual_review_required" and not blocking_reasons:
        return "manual_review_ready"
    return "blocked"


def _preflight_warnings(record: dict[str, Any]) -> list[str]:
    extracted = _extract_manual_record(record)
    review = extracted["review"]
    source = extracted["source"]
    warnings = []
    source_type = _text(source.get("source_type"))
    demo_or_real_flag = _text(review.get("demo_or_real_flag"))
    provenance_status = _text(review.get("provenance_status"))
    if (
        provenance_status == "source_verified"
        and (source_type == "user_supplied" or demo_or_real_flag in MANUAL_OR_UNVERIFIED_FLAGS)
    ):
        warnings.append("user-supplied or unverified evidence cannot become source_verified")
    return warnings


def _requested_preflight_override(record: dict[str, Any]) -> bool:
    preflight = _section(record, "admission_gate_preflight")
    expected = _text(preflight.get("expected_initial_gate_result"))
    review_required = preflight.get("review_required")
    return expected == "allowed_for_package_draft_support" or review_required is False


def _fail_closed_result(
    *,
    record: dict[str, Any],
    missing_required_fields: list[str],
    blocking_reasons: list[str],
    warnings: list[str],
    malformed: bool,
) -> dict[str, Any]:
    return {
        "preflight_status": "blocked",
        "manual_review_state": "cannot_review_until_required_fields_are_present",
        "package_draft_support_preview": {
            "status": "blocked",
            "supported": False,
            "blocking_reasons": blocking_reasons,
        },
        "missing_required_fields": missing_required_fields,
        "blocking_reasons": blocking_reasons,
        "warnings": warnings,
        "source_status": {
            "status": "missing_source",
            "source_fields_present": [],
            "source_type": "",
            "input_provenance_status": "missing_source",
        },
        "placeholder_status": {
            "status": "no_placeholder_detected",
            "has_placeholder_values": False,
            "placeholder_fields": [],
        },
        "evidence_type_status": {"status": "missing_evidence_type", "evidence_type": ""},
        "admission_gate_alignment": {
            "r189_gate_used": False,
            "r189_gate_can_be_overridden": False,
            "package_draft_support_status": "malformed_record_blocked",
            "package_draft_support_allowed": False,
            "beginner_preview_status": "malformed_record_blocked",
            "beginner_preview_allowed": False,
            "preflight_imports_evidence": False,
            "preflight_writes_files": False,
        },
        "traceability": {
            "record_id": _text(record.get("record_id")),
            "record_type": _text(record.get("record_type")),
            "display_name": _text(record.get("display_name")),
            "route_scope": _text(record.get("route_scope")),
            "source_fields_present": [],
            "input_shape": "malformed" if malformed else "flat_record",
        },
    }


def _section(record: dict[str, Any], key: str) -> dict[str, Any]:
    value = record.get(key)
    return value if isinstance(value, dict) else {}


def _walk_plain_values(value: Any, prefix: str = "") -> list[tuple[str, Any]]:
    if isinstance(value, dict):
        paths = []
        for key in sorted(value):
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_walk_plain_values(value[key], child_prefix))
        return paths
    if isinstance(value, list):
        paths = []
        for index, item in enumerate(value):
            paths.extend(_walk_plain_values(item, f"{prefix}[{index}]"))
        return paths
    return [(prefix, value)]


def _unique(values: Any) -> list[Any]:
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _present(value: Any) -> bool:
    return bool(_text(value))


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
