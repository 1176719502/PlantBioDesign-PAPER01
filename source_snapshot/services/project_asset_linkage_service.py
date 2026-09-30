from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any, Iterable

ALLOWED_LINKAGE_ROLES = (
    "project_reference",
    "design_record_context",
    "source_review_context",
    "report_context",
    "candidate_context",
)

REQUIRED_FIELDS = (
    "project_id",
    "asset_id",
    "asset_display_name",
    "asset_type",
    "linkage_role",
    "documentation_note",
    "source_context_snapshot",
    "review_status_snapshot",
    "linked_at",
    "human_review_required",
)

FORBIDDEN_COPY_TERMS = (
    "recommended",
    "recommendation",
    "suitable",
    "suitability",
    "compatible",
    "compatibility",
    "validated",
    "validation",
    "ready",
    "readiness",
    "experimental use",
    "experiment-ready",
)


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _snapshot_copy(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return deepcopy(value)
    raise ValueError("snapshot fields must be dictionaries")


def _contains_forbidden_copy(value: Any) -> str | None:
    text = _normalize_text(value).lower()
    if not text:
        return None
    for term in FORBIDDEN_COPY_TERMS:
        if term in text:
            return term
    return None


def _validate_snapshot_text(snapshot: Any) -> str | None:
    if not isinstance(snapshot, dict):
        return None
    for key, value in snapshot.items():
        term = _contains_forbidden_copy(key)
        if term:
            return term
        term = _contains_forbidden_copy(value)
        if term:
            return term
    return None


def validate_project_asset_link(link: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in link:
            errors.append(f"missing field: {field}")

    for field in ("project_id", "asset_id", "asset_display_name", "asset_type", "linkage_role"):
        if not _normalize_text(link.get(field)):
            errors.append(f"{field} must not be empty")

    linkage_role = _normalize_text(link.get("linkage_role"))
    if linkage_role and linkage_role not in ALLOWED_LINKAGE_ROLES:
        errors.append(f"unrecognized linkage_role: {linkage_role}")

    if not isinstance(link.get("human_review_required"), bool):
        errors.append("human_review_required must be boolean")

    if not isinstance(link.get("source_context_snapshot"), dict):
        errors.append("source_context_snapshot must be a dictionary")
    if not isinstance(link.get("review_status_snapshot"), dict):
        errors.append("review_status_snapshot must be a dictionary")
    if "asset_snapshot" in link and not isinstance(link.get("asset_snapshot"), dict):
        errors.append("asset_snapshot must be a dictionary")

    for field in ("asset_display_name", "asset_type", "documentation_note", "linked_at"):
        term = _contains_forbidden_copy(link.get(field))
        if term:
            errors.append(f"{field} contains forbidden wording: {term}")

    for field in ("source_context_snapshot", "review_status_snapshot"):
        term = _validate_snapshot_text(link.get(field))
        if term:
            errors.append(f"{field} contains forbidden wording: {term}")

    return errors


def build_project_asset_link(
    *,
    project_id: Any,
    asset_id: Any,
    asset_display_name: Any,
    asset_type: Any,
    linkage_role: Any,
    documentation_note: Any = "Documentation-only reference.",
    source_context_snapshot: dict[str, Any] | None = None,
    review_status_snapshot: dict[str, Any] | None = None,
    asset_snapshot: dict[str, Any] | None = None,
    linked_at: Any = "",
    human_review_required: bool = True,
) -> dict[str, Any]:
    link = {
        "project_id": _normalize_text(project_id),
        "asset_id": _normalize_text(asset_id),
        "asset_display_name": _normalize_text(asset_display_name),
        "asset_type": _normalize_text(asset_type),
        "linkage_role": _normalize_text(linkage_role),
        "documentation_note": _normalize_text(documentation_note),
        "source_context_snapshot": _snapshot_copy(source_context_snapshot),
        "review_status_snapshot": _snapshot_copy(review_status_snapshot),
        "asset_snapshot": _snapshot_copy(asset_snapshot),
        "linked_at": _normalize_text(linked_at),
        "human_review_required": human_review_required,
    }

    errors = validate_project_asset_link(link)
    if errors:
        raise ValueError("; ".join(errors))
    return link


def list_project_asset_links(
    links: Iterable[dict[str, Any]],
    *,
    project_id: Any | None = None,
) -> list[dict[str, Any]]:
    rows = [deepcopy(dict(link)) for link in links]
    if project_id is not None:
        rows = [row for row in rows if _normalize_text(row.get("project_id")) == _normalize_text(project_id)]
    return sorted(
        rows,
        key=lambda row: (
            _normalize_text(row.get("project_id")).lower(),
            _normalize_text(row.get("asset_display_name")).lower(),
            _normalize_text(row.get("asset_id")).lower(),
            _normalize_text(row.get("linkage_role")).lower(),
        ),
    )


def _link_identity(link: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _normalize_text(link.get("project_id")).lower(),
        _normalize_text(link.get("asset_id")).lower(),
        _normalize_text(link.get("linkage_role")).lower(),
    )


def merge_project_asset_links(*link_groups: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, str, str], dict[str, Any]] = {}
    for link_group in link_groups:
        for raw_link in link_group:
            if not isinstance(raw_link, dict):
                continue
            link = deepcopy(dict(raw_link))
            identity = _link_identity(link)
            if not any(identity):
                continue
            merged[identity] = link
    return list_project_asset_links(merged.values())


def append_project_asset_link(
    links: Iterable[dict[str, Any]],
    link: dict[str, Any],
) -> tuple[list[dict[str, Any]], bool]:
    rows = list_project_asset_links(links)
    candidate = deepcopy(dict(link))
    candidate_identity = _link_identity(candidate)
    if any(_link_identity(row) == candidate_identity for row in rows):
        return rows, False
    rows.append(candidate)
    return list_project_asset_links(rows), True


def filter_links_by_project(links: Iterable[dict[str, Any]], project_id: Any) -> list[dict[str, Any]]:
    return list_project_asset_links(links, project_id=project_id)


def summarize_project_asset_links(links: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list_project_asset_links(links)
    asset_type_counts = Counter(_normalize_text(row.get("asset_type")) for row in rows)
    role_counts = Counter(_normalize_text(row.get("linkage_role")) for row in rows)
    review_needed = report_links_needing_review(rows)
    return {
        "total_links": len(rows),
        "by_asset_type": dict(sorted(asset_type_counts.items())),
        "by_linkage_role": dict(sorted(role_counts.items())),
        "human_review_required": len(review_needed),
    }


def report_links_needing_review(links: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for link in list_project_asset_links(links):
        snapshot_blob = " ".join(
            [
                _normalize_text(key)
                for key in link.get("review_status_snapshot", {}).keys()
            ]
            + [
                _normalize_text(value)
                for value in link.get("review_status_snapshot", {}).values()
            ]
        ).lower()
        needs_review = bool(link.get("human_review_required")) or "review needed" in snapshot_blob or "needs review" in snapshot_blob
        if needs_review:
            rows.append(link)
    return rows
