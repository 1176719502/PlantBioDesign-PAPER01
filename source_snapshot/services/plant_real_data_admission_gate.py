"""Fail-closed admission checks for future plant real seed records.

R189 adds a read-only skeleton for evaluating plain dict records. It does not
load seed data, connect to import/export, or make biological design decisions.
"""

from __future__ import annotations

from typing import Any


PACKAGE_DRAFT_SUPPORT = "package_draft_support"
BEGINNER_PREVIEW = "beginner_preview"

ALLOWED_ROUTE_SCOPES = {
    "plant_protein_expression_review",
    "plant_metabolic_pathway_review",
    "plant_multigene_construct_review",
    "plant_regulatory_module_review",
    "plant_handoff_package_review",
}

SOURCE_FIELDS = (
    "source_url_or_identifier",
    "doi",
    "accession",
    "repository_id",
    "citation_text",
)

SOURCE_BACKED_FLAGS = {
    "literature_derived",
    "database_derived",
    "repository_derived",
    "manually_curated",
}

MANUAL_REVIEW_FLAGS = {
    "user_supplied",
    "user_supplied_unverified",
    "unverified",
}

USER_VISIBLE_LABELS = {
    "source_recorded_review_needed": "已记录来源，待人工确认",
    "reviewed_documentation_only": "已人工审查，仅限文档整理",
    "user_supplied_review_needed": "用户提供，待复核",
    "missing_source": "来源待补充",
    "demo_only": "示例 / 演示",
    "conflict_review_needed": "冲突待复核",
    "deprecated": "已弃用",
    "not_available_for_package_draft": "暂不可用于审查包草稿",
}

SAFETY_NOTES = {
    "allowed_for_package_draft_support": (
        "Source-backed documentation context only; reviewed_for_documentation "
        "does not confirm experimental outcome or downstream use."
    ),
    "allowed_for_beginner_preview": (
        "Beginner preview only; this remains a labeled demo/example record and "
        "is not displayed as source-backed real data."
    ),
    "manual_review_only": (
        "Manual documentation review is required before this record can support "
        "package draft content."
    ),
    "demo_only": (
        "Demo/example record only; it cannot support package draft content as "
        "source-backed data."
    ),
    "missing_source_blocked": (
        "No source trail is recorded; add a source identifier, DOI, accession, "
        "repository ID, or citation before review."
    ),
    "conflict_needs_review_blocked": (
        "A source, duplicate, host, route, or unresolved conflict needs human "
        "documentation review."
    ),
    "deprecated_blocked": (
        "Deprecated records remain excluded from active documentation support."
    ),
    "out_of_scope_blocked": (
        "The route scope or allowed usage does not match this admission request."
    ),
    "malformed_record_blocked": (
        "The record is missing required identity fields or is not a dict."
    ),
}


def evaluate_real_seed_record_admission(
    record: dict[str, Any], *, intended_usage: str = PACKAGE_DRAFT_SUPPORT
) -> dict[str, Any]:
    """Return a plain dict admission decision for a future plant seed record."""

    if not isinstance(record, dict):
        return _result(
            record={},
            intended_usage=intended_usage,
            admission_status="malformed_record_blocked",
            label_key="not_available_for_package_draft",
            blocking_reasons=["record must be a dict"],
            review_required=True,
            provenance_status="missing_source",
        )

    normalized = dict(record)
    missing_identity = [
        field for field in ("record_id", "record_type", "display_name") if not _present(normalized.get(field))
    ]
    if missing_identity:
        return _result(
            record=normalized,
            intended_usage=intended_usage,
            admission_status="malformed_record_blocked",
            label_key="not_available_for_package_draft",
            blocking_reasons=[f"missing required field: {field}" for field in missing_identity],
            review_required=True,
        )

    route_scope = _as_text(normalized.get("route_scope"))
    if route_scope not in ALLOWED_ROUTE_SCOPES:
        return _result(
            record=normalized,
            intended_usage=intended_usage,
            admission_status="out_of_scope_blocked",
            label_key="not_available_for_package_draft",
            blocking_reasons=["route_scope is not allowed for plant review admission"],
            review_required=True,
        )

    deprecated_flag = bool(normalized.get("deprecated_flag", False))
    provenance_status = _as_text(normalized.get("provenance_status")) or "missing_source"
    if deprecated_flag or provenance_status == "deprecated_source":
        return _result(
            record=normalized,
            intended_usage=intended_usage,
            admission_status="deprecated_blocked",
            label_key="deprecated",
            blocking_reasons=["record or source is deprecated"],
            review_required=True,
            provenance_status=provenance_status,
        )

    conflict_status = _as_text(normalized.get("conflict_status")) or "unresolved"
    if conflict_status != "no_known_conflict":
        return _result(
            record=normalized,
            intended_usage=intended_usage,
            admission_status="conflict_needs_review_blocked",
            label_key="conflict_review_needed",
            blocking_reasons=[f"conflict_status is {conflict_status}"],
            review_required=True,
        )

    demo_or_real_flag = _as_text(normalized.get("demo_or_real_flag")) or "unverified"
    allowed_usage_scope = _as_text(normalized.get("allowed_usage_scope")) or "manual_review_only"
    if demo_or_real_flag == "demo_example":
        if intended_usage == BEGINNER_PREVIEW and allowed_usage_scope == BEGINNER_PREVIEW:
            return _result(
                record=normalized,
                intended_usage=intended_usage,
                admission_status="allowed_for_beginner_preview",
                label_key="demo_only",
                blocking_reasons=[],
                review_required=False,
                allowed=True,
            )
        return _result(
            record=normalized,
            intended_usage=intended_usage,
            admission_status="demo_only",
            label_key="demo_only",
            blocking_reasons=["demo/example records cannot support package draft content"],
            review_required=True,
        )

    source_present = any(_present(normalized.get(field)) for field in SOURCE_FIELDS)
    if not source_present:
        return _result(
            record=normalized,
            intended_usage=intended_usage,
            admission_status="missing_source_blocked",
            label_key="missing_source",
            blocking_reasons=["missing source trail"],
            review_required=True,
            provenance_status="missing_source",
        )

    manual_review_status = _as_text(normalized.get("manual_review_status")) or "not_reviewed"
    if demo_or_real_flag in MANUAL_REVIEW_FLAGS:
        return _result(
            record=normalized,
            intended_usage=intended_usage,
            admission_status="manual_review_only",
            label_key="user_supplied_review_needed",
            blocking_reasons=[f"demo_or_real_flag is {demo_or_real_flag}"],
            review_required=True,
        )

    if intended_usage == PACKAGE_DRAFT_SUPPORT:
        blockers = []
        if provenance_status != "source_verified":
            blockers.append(f"provenance_status is {provenance_status}")
        if manual_review_status != "reviewed_for_documentation":
            blockers.append(f"manual_review_status is {manual_review_status}")
        if allowed_usage_scope != PACKAGE_DRAFT_SUPPORT:
            blockers.append(f"allowed_usage_scope is {allowed_usage_scope}")
        if demo_or_real_flag not in SOURCE_BACKED_FLAGS:
            blockers.append(f"demo_or_real_flag is {demo_or_real_flag}")

        if blockers:
            label_key = (
                "source_recorded_review_needed"
                if provenance_status == "source_present_needs_review"
                else "not_available_for_package_draft"
            )
            return _result(
                record=normalized,
                intended_usage=intended_usage,
                admission_status="manual_review_only",
                label_key=label_key,
                blocking_reasons=blockers,
                review_required=True,
            )

        return _result(
            record=normalized,
            intended_usage=intended_usage,
            admission_status="allowed_for_package_draft_support",
            label_key="reviewed_documentation_only",
            blocking_reasons=[],
            review_required=False,
            allowed=True,
        )

    if intended_usage == BEGINNER_PREVIEW and allowed_usage_scope == BEGINNER_PREVIEW:
        return _result(
            record=normalized,
            intended_usage=intended_usage,
            admission_status="allowed_for_beginner_preview",
            label_key="reviewed_documentation_only",
            blocking_reasons=[],
            review_required=False,
            allowed=True,
        )

    return _result(
        record=normalized,
        intended_usage=intended_usage,
        admission_status="out_of_scope_blocked",
        label_key="not_available_for_package_draft",
        blocking_reasons=[f"allowed_usage_scope is {allowed_usage_scope}"],
        review_required=True,
    )


def _result(
    *,
    record: dict[str, Any],
    intended_usage: str,
    admission_status: str,
    label_key: str,
    blocking_reasons: list[str],
    review_required: bool,
    allowed: bool = False,
    provenance_status: str | None = None,
) -> dict[str, Any]:
    return {
        "record_id": _as_text(record.get("record_id")),
        "record_type": _as_text(record.get("record_type")),
        "display_name": _as_text(record.get("display_name")),
        "intended_usage": intended_usage,
        "admission_status": admission_status,
        "allowed": allowed,
        "allowed_usage_scope": _as_text(record.get("allowed_usage_scope")) or "manual_review_only",
        "demo_or_real_flag": _as_text(record.get("demo_or_real_flag")) or "unverified",
        "provenance_status": provenance_status
        if provenance_status is not None
        else (_as_text(record.get("provenance_status")) or "missing_source"),
        "manual_review_status": _as_text(record.get("manual_review_status")) or "not_reviewed",
        "conflict_status": _as_text(record.get("conflict_status")) or "unresolved",
        "deprecated_flag": bool(record.get("deprecated_flag", False)),
        "blocking_reasons": blocking_reasons,
        "review_required": review_required,
        "user_visible_label": USER_VISIBLE_LABELS[label_key],
        "safety_notes": SAFETY_NOTES[admission_status],
    }


def _present(value: Any) -> bool:
    return bool(_as_text(value))


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
