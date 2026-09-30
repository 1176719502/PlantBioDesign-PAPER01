from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from services.local_design_asset_catalog_service import (
    asset_type_short_label,
    list_assets,
    load_seed_records,
)
from services.project_asset_linkage_service import (
    append_project_asset_link,
    build_project_asset_link,
    list_project_asset_links,
)

CATALOG_REFERENCE_BOUNDARY_COPY = (
    "Catalog references are documentation context only. "
    "Adding a reference does not indicate suitability, compatibility, validation, or readiness. "
    "Human review is required before downstream use."
)
CATALOG_REFERENCE_EMPTY_COPY = "No catalog documentation reference matched this Wizard selection."
CATALOG_REFERENCE_STORAGE_KEY_TEMPLATE = "project_asset_links_{project_id}"

WIZARD_SELECTION_ASSET_TYPES = {
    "host": "host_chassis_context_note",
    "promoter": "promoter",
    "rbs_or_kozak": "rbs_5utr",
    "terminator": "terminator",
    "tag": "tag",
    "cds_target": "cds_target",
}

WIZARD_SELECTION_LABELS = {
    "host": "host / chassis",
    "promoter": "promoter",
    "rbs_or_kozak": "RBS / 5' UTR / Kozak",
    "terminator": "terminator",
    "tag": "tag",
    "cds_target": "CDS / target gene",
}

WIZARD_SELECTION_LINKAGE_ROLES = {
    "host": "source_review_context",
    "promoter": "design_record_context",
    "rbs_or_kozak": "design_record_context",
    "terminator": "design_record_context",
    "tag": "design_record_context",
    "cds_target": "project_reference",
}


def project_catalog_reference_storage_key(project_id: Any) -> str:
    return CATALOG_REFERENCE_STORAGE_KEY_TEMPLATE.format(project_id=project_id)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _lower_text(value: Any) -> str:
    return _clean_text(value).lower()


def _resolve_element_name(ds: Any, part_type: str, name_key: str) -> str:
    elements = getattr(ds, "elements", None)
    elements = elements if isinstance(elements, dict) else {}
    frame = getattr(ds, "frame", None)
    frame = frame if isinstance(frame, dict) else {}
    name = elements.get(name_key) or frame.get(name_key)
    if name:
        return _clean_text(name)

    parts = frame.get("parts") if isinstance(frame.get("parts"), list) else []
    part_type_norm = part_type.lower()
    for part in parts:
        if not isinstance(part, dict):
            continue
        current_type = _lower_text(part.get("type"))
        if current_type == part_type_norm or (part_type_norm == "rbs" and current_type == "kozak"):
            return _clean_text(part.get("name"))
    return ""


def wizard_catalog_reference_selections(ds: Any) -> list[dict[str, str]]:
    selections = [
        ("host", _clean_text(getattr(ds, "host", ""))),
        ("promoter", _resolve_element_name(ds, "promoter", "promoter_name")),
        ("rbs_or_kozak", _resolve_element_name(ds, "rbs", "rbs_name")),
        ("terminator", _resolve_element_name(ds, "terminator", "terminator_name")),
        ("tag", _clean_text(getattr(ds, "tag", ""))),
        ("cds_target", _clean_text(getattr(ds, "gene_name", ""))),
    ]

    rows: list[dict[str, str]] = []
    for key, value in selections:
        if not value:
            continue
        if key == "tag" and value.lower() == "no tag":
            continue
        asset_type = WIZARD_SELECTION_ASSET_TYPES[key]
        rows.append(
            {
                "selection_key": key,
                "selection_label": WIZARD_SELECTION_LABELS[key],
                "selection_value": value,
                "asset_type": asset_type,
                "linkage_role": WIZARD_SELECTION_LINKAGE_ROLES[key],
            }
        )
    return rows


def _record_haystack(record: dict[str, Any]) -> str:
    values = [
        record.get("display_name"),
        record.get("asset_type"),
        asset_type_short_label(record.get("asset_type")),
        " ".join(str(alias) for alias in record.get("aliases", []) if alias),
        " ".join(str(tag) for tag in record.get("tags", []) if tag),
    ]
    return " ".join(_clean_text(value) for value in values if _clean_text(value)).lower()


def _selection_needles(selection: dict[str, str]) -> list[str]:
    values = [
        selection.get("selection_value"),
        selection.get("selection_label"),
        selection.get("asset_type"),
        asset_type_short_label(selection.get("asset_type")),
    ]
    needles: list[str] = []
    for value in values:
        text = _lower_text(value)
        if text and text not in needles:
            needles.append(text)
    return needles


def _match_context(record: dict[str, Any], selection: dict[str, str]) -> str:
    haystack = _record_haystack(record)
    value = _lower_text(selection.get("selection_value"))
    label = _lower_text(selection.get("selection_label"))
    asset_type = _lower_text(selection.get("asset_type"))
    short_label = _lower_text(asset_type_short_label(selection.get("asset_type")))
    if value and value in haystack:
        return "wizard_selection_text"
    if label and label in haystack:
        return "wizard_selection_label"
    if asset_type and asset_type in haystack:
        return "asset_type"
    if short_label and short_label in haystack:
        return "asset_type"
    return "catalog_metadata"


def _record_matches_selection(record: dict[str, Any], selection: dict[str, str]) -> bool:
    if _clean_text(record.get("asset_type")) != _clean_text(selection.get("asset_type")):
        return False
    haystack = _record_haystack(record)
    return any(needle in haystack for needle in _selection_needles(selection))


def build_wizard_catalog_reference_candidates(
    ds: Any,
    records: Iterable[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    catalog_records = list_assets(list(records) if records is not None else load_seed_records())
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for selection in wizard_catalog_reference_selections(ds):
        for record in catalog_records:
            if not _record_matches_selection(record, selection):
                continue
            identity = (
                selection["selection_key"],
                _clean_text(record.get("asset_id")),
                selection["linkage_role"],
            )
            if identity in seen:
                continue
            seen.add(identity)
            candidates.append(
                {
                    **selection,
                    "asset_id": _clean_text(record.get("asset_id")),
                    "asset_display_name": _clean_text(record.get("display_name")),
                    "asset_type": _clean_text(record.get("asset_type")),
                    "source_context_snapshot": {
                        "wizard_field": selection["selection_label"],
                        "wizard_value": selection["selection_value"],
                        "source_provenance_status": _clean_text(record.get("provenance_status")),
                        "version_context": _clean_text(record.get("version_context")),
                    },
                    "review_status_snapshot": {
                        "review_status": _clean_text(record.get("review_status")),
                        "human_review_note": _clean_text(record.get("human_review_notes")),
                    },
                    "documentation_note": (
                        f"Documentation-only Wizard reference for {selection['selection_label']} context."
                    ),
                    "human_review_required": True,
                    "match_context": _match_context(record, selection),
                }
            )

    return sorted(
        candidates,
        key=lambda row: (
            list(WIZARD_SELECTION_ASSET_TYPES).index(row["selection_key"]),
            _lower_text(row.get("asset_display_name")),
            _lower_text(row.get("asset_id")),
        ),
    )


def build_wizard_catalog_project_link(
    *,
    project_id: Any,
    candidate: dict[str, Any],
    linked_at: Any = "",
) -> dict[str, Any]:
    return build_project_asset_link(
        project_id=project_id,
        asset_id=candidate.get("asset_id"),
        asset_display_name=candidate.get("asset_display_name"),
        asset_type=candidate.get("asset_type"),
        linkage_role=candidate.get("linkage_role"),
        documentation_note=candidate.get("documentation_note") or "Documentation-only Wizard reference.",
        source_context_snapshot=candidate.get("source_context_snapshot") if isinstance(candidate.get("source_context_snapshot"), dict) else {},
        review_status_snapshot=candidate.get("review_status_snapshot") if isinstance(candidate.get("review_status_snapshot"), dict) else {},
        linked_at=linked_at or datetime.now().isoformat(timespec="seconds"),
        human_review_required=True,
    )


def append_wizard_catalog_project_links(
    existing_links: Iterable[dict[str, Any]],
    *,
    project_id: Any,
    candidates: Iterable[dict[str, Any]],
    linked_at: Any = "session",
) -> tuple[list[dict[str, Any]], int, int]:
    updated_links = list_project_asset_links(existing_links, project_id=project_id)
    added_count = 0
    duplicate_count = 0
    for candidate in candidates:
        link = build_wizard_catalog_project_link(
            project_id=project_id,
            candidate=candidate,
            linked_at=linked_at,
        )
        updated_links, added = append_project_asset_link(updated_links, link)
        if added:
            added_count += 1
        else:
            duplicate_count += 1
    return updated_links, added_count, duplicate_count
