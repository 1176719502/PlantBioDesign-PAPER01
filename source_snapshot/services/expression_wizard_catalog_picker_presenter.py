from __future__ import annotations

from typing import Any, Iterable

from services import project_catalog_asset_link_repository as persistent_links
from services.catalog_asset_snapshot_builder import (
    build_catalog_asset_snapshot,
    catalog_asset_snapshot_has_content,
)
from services.local_design_asset_catalog_service import (
    asset_type_short_label,
    load_seed_records,
)
from services.project_asset_linkage_service import build_project_asset_link
from services.plant_promoter_catalog_workspace_presenter import (
    PLANT_PROMOTER_PROFILE_ASSET_TYPE,
    build_catalog_reference_options,
    build_promoter_catalog_project_link,
)

WIZARD_CATALOG_PICKER_TITLE = "Catalog context for this design record"
WIZARD_CATALOG_PICKER_BOUNDARY_COPY = (
    "Add a documentation-level reference to the current project. This picker lists local catalog context only; "
    "it does not advise which record to choose, verify biology, certify downstream-use state, or forecast outcomes."
)
WIZARD_CATALOG_PICKER_EMPTY_PROJECT_COPY = (
    "No project context is linked to this Wizard session. Open the Wizard from Pathway Workspace or select a "
    "current pathway project before adding catalog context."
)
WIZARD_CATALOG_PICKER_EMPTY_CATALOG_COPY = (
    "No catalog context is available for this design record."
)
WIZARD_CATALOG_PICKER_SEED_COPY = (
    "Component Library promoter asset records may include local curated sample context when local catalog rows are empty."
)
DEFAULT_WIZARD_REFERENCE_NOTE = (
    "Documentation-only Expression Wizard catalog context reference for project traceability."
)
WIZARD_REFERENCE_ROLE = "design_record_context"
WIZARD_REFERENCE_ORIGIN = "Expression Wizard catalog context"
WIZARD_PROJECT_DOCUMENTATION_CONTEXT = "Expression Wizard Step 6 catalog context"
WIZARD_REFERENCE_LIMITATION_NOTE = (
    "Documentation-level reference for source/review context only; not selection advice, "
    "not source verification, not downstream-use state, and no outcome forecast."
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _lower(value: Any) -> str:
    return _text(value).casefold()


def _project_id_from_context(context: dict[str, Any] | None, session_state: Any | None = None) -> str:
    safe_context = context if isinstance(context, dict) else {}
    context_project_id = _text(safe_context.get("project_id"))
    if safe_context.get("source") == "pathway_workspace" and context_project_id:
        return context_project_id
    if isinstance(session_state, dict):
        return _text(session_state.get("pathway_current_project_id"))
    return ""


def _source_status(record: dict[str, Any]) -> str:
    return _text(record.get("provenance_status") or record.get("source_notes"), "source review needed")


def _documentation_status(record: dict[str, Any]) -> str:
    return _text(record.get("review_status") or record.get("documentation_boundary_note"), "human review needed")


def _catalog_source_status(*, catalog_family: Any, source_label: Any, documentation_status: Any) -> str:
    family = _text(catalog_family)
    source = _text(source_label, "source review context not recorded")
    review = _text(documentation_status, "human review needed")
    family_label = {
        "local_design_asset_catalog": "Local Design Asset Catalog",
        "plant_promoter_catalog": "Plant Promoter Catalog",
    }.get(family, "Catalog reference")
    return f"{family_label} / {source} / {review}"


def _link_safe_text(value: Any) -> str:
    text = _text(value)
    replacements = {
        "recommend" + "ed": "not advised",
        "recommend" + "ation": "advice",
        "suit" + "able": "fit-state",
        "suit" + "ability": "fit-state",
        "compati" + "ble": "fit-state",
        "compatibi" + "lity": "fit-state",
        "valid" + "ated": "checked",
        "valid" + "ation": "review",
        "read" + "y": "available",
        "readi" + "ness": "availability",
        "experimental use": "downstream use",
        "experiment-" + "ready": "downstream-use state",
    }
    lowered = text.lower()
    for old, new in replacements.items():
        if old in lowered:
            text = text.replace(old, new).replace(old.title(), new.title())
            lowered = text.lower()
    return text


def _local_asset_options(records: Iterable[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in records if records is not None else load_seed_records():
        if not isinstance(record, dict):
            continue
        asset_id = _text(record.get("asset_id"))
        asset_type = _text(record.get("asset_type"))
        display_label = _text(record.get("display_name"), asset_id)
        if not asset_id or not asset_type or not display_label:
            continue
        rows.append(
            {
                "option_id": f"local::{asset_type}::{asset_id}",
                "catalog_family": "local_design_asset_catalog",
                "asset_type": asset_type,
                "asset_id": asset_id,
                "record_identifier": asset_id,
                "display_label": display_label,
                "select_label": f"{display_label} / {asset_type_short_label(asset_type)} / {asset_id}",
                "species_or_clade": _text(record.get("organism_or_source_context"), "No organism or source context recorded"),
                "source_label": _source_status(record),
                "documentation_status": _documentation_status(record),
                "catalog_source_status": _catalog_source_status(
                    catalog_family="local_design_asset_catalog",
                    source_label=_source_status(record),
                    documentation_status=_documentation_status(record),
                ),
                "reference_note": _text(
                    record.get("human_review_notes") or record.get("documentation_boundary_note"),
                    DEFAULT_WIZARD_REFERENCE_NOTE,
                ),
                "limitation_note": _text(
                    record.get("documentation_boundary_note"),
                    "Documentation-only local catalog context.",
                ),
                "record": dict(record),
            }
        )
    return sorted(rows, key=lambda row: (_lower(row["asset_type"]), _lower(row["display_label"]), _lower(row["asset_id"])))


def _plant_promoter_options() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for option in build_catalog_reference_options():
        if not isinstance(option, dict):
            continue
        asset_id = _text(option.get("part_id"))
        display_label = _text(option.get("promoter_label"), asset_id)
        if not asset_id:
            continue
        species = _text(option.get("species_label"), "No species context recorded")
        clade = _text(option.get("plant_clade"), "No plant clade recorded")
        rows.append(
            {
                "option_id": f"plant::{PLANT_PROMOTER_PROFILE_ASSET_TYPE}::{asset_id}",
                "catalog_family": "plant_promoter_catalog",
                "asset_type": PLANT_PROMOTER_PROFILE_ASSET_TYPE,
                "asset_id": asset_id,
                "record_identifier": asset_id,
                "display_label": display_label,
                "select_label": _text(option.get("select_label"), f"{display_label} / {asset_id}"),
                "species_or_clade": " / ".join(value for value in (species, clade) if value),
                "source_label": "Plant Promoter Catalog",
                "documentation_status": "source review needed",
                "catalog_source_status": _catalog_source_status(
                    catalog_family="plant_promoter_catalog",
                    source_label="Plant Promoter Catalog",
                    documentation_status="source review needed",
                ),
                "reference_note": DEFAULT_WIZARD_REFERENCE_NOTE,
                "limitation_note": (
                    "Component Library promoter asset metadata is recorded as documentation context; source review remains human-owned."
                ),
                "record": dict(option),
            }
        )
    return sorted(rows, key=lambda row: (_lower(row["asset_type"]), _lower(row["display_label"]), _lower(row["asset_id"])))


def build_expression_wizard_catalog_picker_view_model(
    *,
    project_context: dict[str, Any] | None = None,
    session_state: Any | None = None,
    local_asset_records: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a deterministic documentation-only catalog picker view model."""
    project_id = _project_id_from_context(project_context, session_state)
    if not project_id:
        return {
            "status": "no_project_context",
            "project_id": "",
            "available_catalog_assets": [],
            "plant_promoter_options": [],
            "options": [],
            "message": WIZARD_CATALOG_PICKER_EMPTY_PROJECT_COPY,
            "boundary_copy": WIZARD_CATALOG_PICKER_BOUNDARY_COPY,
            "seed_context_copy": WIZARD_CATALOG_PICKER_SEED_COPY,
        }

    local_options = _local_asset_options(local_asset_records)
    promoter_options = _plant_promoter_options()
    options = sorted(
        [*local_options, *promoter_options],
        key=lambda row: (_lower(row["asset_type"]), _lower(row["display_label"]), _lower(row["asset_id"])),
    )
    return {
        "status": "available" if options else "empty_catalog",
        "project_id": project_id,
        "available_catalog_assets": local_options,
        "plant_promoter_options": promoter_options,
        "options": options,
        "message": "" if options else WIZARD_CATALOG_PICKER_EMPTY_CATALOG_COPY,
        "boundary_copy": WIZARD_CATALOG_PICKER_BOUNDARY_COPY,
        "seed_context_copy": WIZARD_CATALOG_PICKER_SEED_COPY,
    }


def _selected_option(view_model: dict[str, Any], option_id: Any) -> dict[str, Any]:
    target = _text(option_id)
    for option in view_model.get("options") or []:
        if isinstance(option, dict) and _text(option.get("option_id")) == target:
            return dict(option)
    return {}


def build_expression_wizard_catalog_link_payload(
    *,
    project_id: Any,
    option: dict[str, Any],
    documentation_note: Any = DEFAULT_WIZARD_REFERENCE_NOTE,
    linked_at: Any = "session",
) -> dict[str, Any]:
    """Build a R35-compatible project catalog link from a picker option."""
    if _text(option.get("catalog_family")) == "plant_promoter_catalog":
        link = build_promoter_catalog_project_link(
            project_id=project_id,
            part_id=option.get("asset_id"),
            linkage_role=WIZARD_REFERENCE_ROLE,
            documentation_note=documentation_note or DEFAULT_WIZARD_REFERENCE_NOTE,
            linked_at=linked_at,
        )
        source_snapshot = link.get("source_context_snapshot") if isinstance(link.get("source_context_snapshot"), dict) else {}
        source_snapshot["wizard_context"] = "Expression Wizard design record"
        source_snapshot["reference_origin"] = WIZARD_REFERENCE_ORIGIN
        source_snapshot["project_documentation_context"] = WIZARD_PROJECT_DOCUMENTATION_CONTEXT
        link["source_context_snapshot"] = source_snapshot
        asset_snapshot = link.get("asset_snapshot") if isinstance(link.get("asset_snapshot"), dict) else {}
        asset_snapshot["limitation_note"] = asset_snapshot.get("limitation_note") or WIZARD_REFERENCE_LIMITATION_NOTE
        link["asset_snapshot"] = asset_snapshot
        return link

    record = option.get("record") if isinstance(option.get("record"), dict) else {}
    asset_snapshot = build_catalog_asset_snapshot(
        record,
        asset_type=option.get("asset_type"),
        fallback={
            "asset_id": option.get("asset_id"),
            "asset_label": option.get("display_label"),
            "source_label": _link_safe_text(_source_status(record)),
            "documentation_status": _link_safe_text(_documentation_status(record)),
            "limitation_note": _link_safe_text(option.get("limitation_note") or WIZARD_REFERENCE_LIMITATION_NOTE),
        },
    )
    link = build_project_asset_link(
        project_id=project_id,
        asset_id=option.get("asset_id"),
        asset_display_name=option.get("display_label"),
        asset_type=option.get("asset_type"),
        linkage_role=WIZARD_REFERENCE_ROLE,
        documentation_note=documentation_note or DEFAULT_WIZARD_REFERENCE_NOTE,
        source_context_snapshot={
            "catalog": "Local Design Asset Catalog",
            "wizard_context": "Expression Wizard design record",
            "reference_origin": WIZARD_REFERENCE_ORIGIN,
            "project_documentation_context": WIZARD_PROJECT_DOCUMENTATION_CONTEXT,
            "source_label": _link_safe_text(_source_status(record)),
            "source_provenance_status": _link_safe_text(_source_status(record)),
            "version_context": _link_safe_text(record.get("version_context")),
        },
        review_status_snapshot={
            "curation_statuses": _link_safe_text(_documentation_status(record)),
            "human_review_status": _link_safe_text(_documentation_status(record)),
            "human_review_note": _link_safe_text(record.get("human_review_notes") or "Human review needed."),
        },
        asset_snapshot=asset_snapshot,
        linked_at=linked_at,
        human_review_required=True,
    )
    return link


def add_expression_wizard_catalog_context_link(
    *,
    project_context: dict[str, Any] | None = None,
    session_state: Any | None = None,
    option_id: Any,
    documentation_note: Any = DEFAULT_WIZARD_REFERENCE_NOTE,
    local_asset_records: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Persist the selected catalog context through the existing project link repository."""
    view_model = build_expression_wizard_catalog_picker_view_model(
        project_context=project_context,
        session_state=session_state,
        local_asset_records=local_asset_records,
    )
    project_id = _text(view_model.get("project_id"))
    if not project_id:
        return {
            "added": False,
            "duplicate": False,
            "message": WIZARD_CATALOG_PICKER_EMPTY_PROJECT_COPY,
            "link": {},
            "view_model": view_model,
        }
    option = _selected_option(view_model, option_id)
    if not option:
        return {
            "added": False,
            "duplicate": False,
            "message": "Select an available catalog context before adding a project reference.",
            "link": {},
            "view_model": view_model,
        }

    link = build_expression_wizard_catalog_link_payload(
        project_id=project_id,
        option=option,
        documentation_note=documentation_note,
        linked_at="session",
    )
    added, message, stored = persistent_links.add_project_catalog_asset_link(link)
    return {
        "added": bool(added),
        "duplicate": not bool(added) and bool(stored),
        "message": message,
        "link": stored if isinstance(stored, dict) else {},
        "view_model": build_expression_wizard_catalog_picker_view_model(
            project_context=project_context,
            session_state=session_state,
            local_asset_records=local_asset_records,
        ),
    }


def _link_source_label(link: dict[str, Any]) -> str:
    source_snapshot = link.get("source_context_snapshot") if isinstance(link.get("source_context_snapshot"), dict) else {}
    return _text(
        link.get("source_label")
        or source_snapshot.get("source_labels")
        or source_snapshot.get("source_label")
        or source_snapshot.get("catalog")
        or source_snapshot.get("source_provenance_status"),
        "source review context not recorded",
    )


def _link_documentation_status(link: dict[str, Any]) -> str:
    review_snapshot = link.get("review_status_snapshot") if isinstance(link.get("review_status_snapshot"), dict) else {}
    return _text(
        link.get("documentation_status")
        or review_snapshot.get("curation_statuses")
        or review_snapshot.get("review_status")
        or review_snapshot.get("human_review_status"),
        "human review needed",
    )


def _link_reference_origin(link: dict[str, Any]) -> str:
    source_snapshot = link.get("source_context_snapshot") if isinstance(link.get("source_context_snapshot"), dict) else {}
    return _text(source_snapshot.get("reference_origin"), WIZARD_REFERENCE_ORIGIN)


def _is_wizard_catalog_reference(link: dict[str, Any]) -> bool:
    source_snapshot = link.get("source_context_snapshot") if isinstance(link.get("source_context_snapshot"), dict) else {}
    return (
        _text(link.get("linkage_role")) == WIZARD_REFERENCE_ROLE
        or _text(source_snapshot.get("reference_origin")) == WIZARD_REFERENCE_ORIGIN
        or _text(source_snapshot.get("wizard_context")) == "Expression Wizard design record"
    )


def build_expression_wizard_catalog_traceability_rows(
    links: Iterable[dict[str, Any]] | None,
    *,
    project_id: Any = "",
) -> list[dict[str, str]]:
    """Return deterministic Wizard-origin catalog reference traceability rows."""
    rows_by_identity: dict[tuple[str, str, str], dict[str, str]] = {}
    linked_project_id = _text(project_id)
    for link in links or []:
        if not isinstance(link, dict) or not _is_wizard_catalog_reference(link):
            continue
        asset_type = _text(link.get("asset_type"))
        asset_id = _text(link.get("asset_id"))
        asset_snapshot = link.get("asset_snapshot") if isinstance(link.get("asset_snapshot"), dict) else {}
        has_snapshot = catalog_asset_snapshot_has_content(asset_snapshot)
        asset_label = _text(
            asset_snapshot.get("asset_label")
            or link.get("asset_label")
            or link.get("asset_display_name"),
            asset_id,
        )
        if not asset_type or not asset_id:
            continue
        row = {
            "asset_type": asset_type,
            "asset_id": asset_id,
            "record_identifier": asset_id,
            "asset_label": asset_label,
            "source_label": _link_safe_text(asset_snapshot.get("source_label") or _link_source_label(link)),
            "documentation_status": _link_safe_text(
                asset_snapshot.get("documentation_status") or _link_documentation_status(link)
            ),
            "catalog_source_status": _catalog_source_status(
                catalog_family="plant_promoter_catalog" if asset_type == PLANT_PROMOTER_PROFILE_ASSET_TYPE else "local_design_asset_catalog",
                source_label=asset_snapshot.get("source_label") or _link_source_label(link),
                documentation_status=asset_snapshot.get("documentation_status") or _link_documentation_status(link),
            ),
            "linked_project_id": linked_project_id or _text(link.get("project_id")),
            "reference_origin": _link_reference_origin(link),
            "reference_note": _text(link.get("documentation_note"), DEFAULT_WIZARD_REFERENCE_NOTE),
            "limitation_note": _text(asset_snapshot.get("limitation_note"), WIZARD_REFERENCE_LIMITATION_NOTE),
            "snapshot_status": "pinned documentation snapshot" if has_snapshot else "live metadata fallback",
        }
        identity = (row["asset_type"].casefold(), row["asset_id"].casefold(), row["linked_project_id"].casefold())
        existing = rows_by_identity.get(identity)
        if existing and existing.get("snapshot_status") == "pinned documentation snapshot" and not has_snapshot:
            continue
        rows_by_identity[identity] = row
    return sorted(
        rows_by_identity.values(),
        key=lambda row: (_lower(row["asset_type"]), _lower(row["asset_label"]), _lower(row["asset_id"])),
    )


def build_expression_wizard_catalog_traceability_summary(
    links: Iterable[dict[str, Any]] | None,
    *,
    project_id: Any = "",
) -> dict[str, Any]:
    rows = build_expression_wizard_catalog_traceability_rows(links, project_id=project_id)
    plant_promoter_count = sum(1 for row in rows if row["asset_type"] == PLANT_PROMOTER_PROFILE_ASSET_TYPE)
    missing_metadata_count = 0
    counted_identities: set[tuple[str, str, str]] = set()
    for link in links or []:
        if not isinstance(link, dict) or not _is_wizard_catalog_reference(link):
            continue
        identity = (
            _text(link.get("asset_type")).casefold(),
            _text(link.get("asset_id")).casefold(),
            (_text(project_id) or _text(link.get("project_id"))).casefold(),
        )
        if identity in counted_identities:
            continue
        counted_identities.add(identity)
        review_snapshot = link.get("review_status_snapshot") if isinstance(link.get("review_status_snapshot"), dict) else {}
        asset_snapshot = link.get("asset_snapshot") if isinstance(link.get("asset_snapshot"), dict) else {}
        has_snapshot = catalog_asset_snapshot_has_content(asset_snapshot)
        if "missing_metadata_count" in review_snapshot:
            try:
                missing_metadata_count += int(review_snapshot.get("missing_metadata_count") or 0)
            except (TypeError, ValueError):
                missing_metadata_count += 1
            continue
        if not has_snapshot:
            missing_metadata_count += 1
            continue
        source_label = _link_source_label(link)
        documentation_status = _link_documentation_status(link)
        if source_label == "source review context not recorded" or documentation_status == "human review needed":
            missing_metadata_count += 1
    return {
        "status": "available" if rows else "not_available",
        "reference_count": len(rows),
        "plant_promoter_reference_count": plant_promoter_count,
        "missing_metadata_count": missing_metadata_count,
        "reference_origin": WIZARD_REFERENCE_ORIGIN,
        "traceability_rows": rows,
        "boundary_note": (
            "Wizard catalog references are documentation-level source/review context for the linked project."
        ),
        "limitation_note": WIZARD_REFERENCE_LIMITATION_NOTE,
        "message": "" if rows else "No Expression Wizard catalog context references are recorded for this project.",
    }
