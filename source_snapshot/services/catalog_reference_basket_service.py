from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, MutableMapping
from uuid import uuid4


DEFAULT_PROJECT_DOCUMENTATION_CONTEXT = "Pathway Workspace linked catalog assets"
DEFAULT_REFERENCE_ORIGIN = "Project documentation reference"
BASKET_BOUNDARY_COPY = (
    "This records documentation context only; it is not a recommendation or validation."
)
EMPTY_BASKET_COPY = (
    "No staged documentation references are in the basket yet. "
    "Add a documentation-only context from a catalog record to continue."
)
STAGED_REFERENCE_ADDED_COPY = (
    "Staged documentation reference added to the reference basket."
)
STAGED_REFERENCE_DUPLICATE_COPY = (
    "This documentation reference is already staged in the basket for the active project and selected role."
)
STAGED_REFERENCE_REMOVED_COPY = (
    "Staged documentation reference removed from the basket."
)
STAGED_REFERENCE_NOT_FOUND_COPY = "The staged documentation reference was not found."
STAGED_REFERENCE_CLEARED_COPY = "All staged documentation references were cleared from the basket."


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _catalog_label(link: dict[str, Any], source_snapshot: dict[str, Any]) -> str:
    catalog = _text(source_snapshot.get("catalog"))
    if catalog:
        return catalog
    if _text(link.get("asset_type")) == "plant_promoter_profile":
        return "Plant Promoter Catalog"
    return "Local Design Asset Catalog"


def _source_label(
    link: dict[str, Any],
    source_snapshot: dict[str, Any],
    review_snapshot: dict[str, Any],
    asset_snapshot: dict[str, Any],
) -> str:
    return _text(
        asset_snapshot.get("source_label")
        or link.get("source_label")
        or source_snapshot.get("source_labels")
        or source_snapshot.get("source_label")
        or source_snapshot.get("source_provenance_status"),
        "source review context not recorded",
    )


def _documentation_status(
    link: dict[str, Any],
    review_snapshot: dict[str, Any],
    asset_snapshot: dict[str, Any],
) -> str:
    return _text(
        asset_snapshot.get("documentation_status")
        or link.get("documentation_status")
        or review_snapshot.get("curation_statuses")
        or review_snapshot.get("review_status")
        or review_snapshot.get("human_review_status"),
        "human review needed",
    )


def _basket_storage_key(project_id: Any) -> str:
    return f"catalog_reference_basket_{_text(project_id)}"


def basket_storage_key(project_id: Any) -> str:
    return _basket_storage_key(project_id)


def build_catalog_reference_basket_entry(
    *,
    project_id: Any,
    link_payload: dict[str, Any],
    catalog_name_source: Any = "",
    catalog_source_status: Any = "",
    reference_origin: Any = "",
    project_documentation_context: Any = "",
    documentation_note: Any = "",
) -> dict[str, Any]:
    link = deepcopy(link_payload if isinstance(link_payload, dict) else {})
    source_snapshot = (
        link.get("source_context_snapshot")
        if isinstance(link.get("source_context_snapshot"), dict)
        else {}
    )
    review_snapshot = (
        link.get("review_status_snapshot")
        if isinstance(link.get("review_status_snapshot"), dict)
        else {}
    )
    asset_snapshot = (
        link.get("asset_snapshot") if isinstance(link.get("asset_snapshot"), dict) else {}
    )
    catalog_label = _catalog_label(link, source_snapshot)
    source_label = _source_label(link, source_snapshot, review_snapshot, asset_snapshot)
    documentation_status = _documentation_status(link, review_snapshot, asset_snapshot)
    display_name = _text(
        asset_snapshot.get("asset_label")
        or link.get("asset_display_name")
        or link.get("asset_label")
        or link.get("asset_id")
    )
    link_note = _text(documentation_note or link.get("documentation_note"))
    context_label = _text(
        project_documentation_context
        or source_snapshot.get("project_documentation_context"),
        DEFAULT_PROJECT_DOCUMENTATION_CONTEXT,
    )
    origin = _text(
        reference_origin or source_snapshot.get("reference_origin"),
        DEFAULT_REFERENCE_ORIGIN,
    )
    return {
        "basket_id": f"crb-{uuid4().hex[:12]}",
        "project_id": _text(project_id),
        "asset_id": _text(link.get("asset_id")),
        "asset_type": _text(link.get("asset_type")),
        "asset_display_name": display_name,
        "record_identifier": _text(
            source_snapshot.get("profile_id")
            or asset_snapshot.get("asset_id")
            or link.get("asset_id")
        ),
        "linkage_role": _text(link.get("linkage_role")),
        "catalog_name_source": _text(
            catalog_name_source,
            f"{catalog_label} / {source_label}",
        ),
        "catalog_source_status": _text(
            catalog_source_status,
            f"{catalog_label} / {source_label} / {documentation_status}",
        ),
        "reference_origin": origin,
        "documentation_note": link_note,
        "project_documentation_context": context_label,
        "linked_reference_label": "Linked catalog reference",
        "staged_reference_label": "Staged documentation reference",
        "staged_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "link_payload": link,
    }


def _entry_identity(entry: dict[str, Any]) -> tuple[str, str, str]:
    return (
        _text(entry.get("project_id")).casefold(),
        _text(entry.get("asset_id")).casefold(),
        _text(entry.get("linkage_role")).casefold(),
    )


def basket_entry_identity(entry: dict[str, Any]) -> tuple[str, str, str]:
    return _entry_identity(entry)


def list_catalog_reference_basket(
    session_state: MutableMapping[str, Any],
    *,
    project_id: Any,
) -> list[dict[str, Any]]:
    rows = session_state.get(_basket_storage_key(project_id))
    if not isinstance(rows, list):
        return []
    cleaned = [deepcopy(row) for row in rows if isinstance(row, dict)]
    return sorted(
        cleaned,
        key=lambda row: (
            _text(row.get("asset_display_name")).casefold(),
            _text(row.get("asset_id")).casefold(),
            _text(row.get("linkage_role")).casefold(),
            _text(row.get("basket_id")).casefold(),
        ),
    )


def add_catalog_reference_basket_entry(
    session_state: MutableMapping[str, Any],
    entry: dict[str, Any],
) -> tuple[bool, dict[str, Any]]:
    project_id = _text(entry.get("project_id"))
    if not project_id:
        return False, {}
    rows = list_catalog_reference_basket(session_state, project_id=project_id)
    identity = _entry_identity(entry)
    for row in rows:
        if _entry_identity(row) == identity:
            return False, row
    rows.append(deepcopy(entry))
    session_state[_basket_storage_key(project_id)] = rows
    return True, deepcopy(entry)


def find_catalog_reference_basket_entry(
    session_state: MutableMapping[str, Any],
    *,
    project_id: Any,
    asset_id: Any,
    linkage_role: Any,
) -> dict[str, Any]:
    identity = (
        _text(project_id).casefold(),
        _text(asset_id).casefold(),
        _text(linkage_role).casefold(),
    )
    for row in list_catalog_reference_basket(session_state, project_id=project_id):
        if _entry_identity(row) == identity:
            return deepcopy(row)
    return {}


def remove_catalog_reference_basket_entry(
    session_state: MutableMapping[str, Any],
    *,
    project_id: Any,
    basket_id: Any,
) -> bool:
    rows = list_catalog_reference_basket(session_state, project_id=project_id)
    target = _text(basket_id)
    updated = [row for row in rows if _text(row.get("basket_id")) != target]
    session_state[_basket_storage_key(project_id)] = updated
    return len(updated) != len(rows)


def clear_catalog_reference_basket(
    session_state: MutableMapping[str, Any],
    *,
    project_id: Any,
) -> None:
    session_state[_basket_storage_key(project_id)] = []
