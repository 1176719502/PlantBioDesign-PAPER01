from __future__ import annotations

from typing import Any

from services.catalog_asset_snapshot_builder import catalog_asset_snapshot_has_content
from services.host_chassis_context_presenter import summarize_asset_host_chassis_context

NOT_RECORDED = "Not recorded"
DOCUMENTATION_CONTEXT_NOT_PROVIDED = "Documentation context not provided"
SOURCE_STATUS_NOT_RECORDED = "Source status not recorded"
DEFAULT_REFERENCE_ORIGIN = "Project documentation reference"
LINKED_REFERENCE_LABEL = "Linked catalog reference"
PERSISTED_LINKED_REFERENCE_STATUS = "Persisted linked catalog reference"


def text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _meaningful(value: Any, *empty_labels: str) -> str:
    clean = text(value)
    if not clean or clean in empty_labels:
        return ""
    return clean


def source_snapshot(link: dict[str, Any]) -> dict[str, Any]:
    value = link.get("source_context_snapshot")
    snapshot = dict(value) if isinstance(value, dict) else {}
    if not text(snapshot.get("profile_id")):
        snapshot["profile_id"] = _meaningful(link.get("record_identifier"), NOT_RECORDED)
    if not text(snapshot.get("catalog")):
        snapshot["catalog"] = _meaningful(link.get("catalog_label"), NOT_RECORDED)
    if not text(snapshot.get("reference_origin")):
        snapshot["reference_origin"] = _meaningful(link.get("reference_origin"))
    if not text(snapshot.get("project_documentation_context")):
        snapshot["project_documentation_context"] = _meaningful(
            link.get("project_documentation_context"),
            DOCUMENTATION_CONTEXT_NOT_PROVIDED,
        )
    if not text(snapshot.get("source_labels")) and not text(snapshot.get("source_label")):
        fallback_source = _meaningful(link.get("source_label"), SOURCE_STATUS_NOT_RECORDED)
        if fallback_source:
            snapshot["source_labels"] = fallback_source
    return snapshot


def review_snapshot(link: dict[str, Any]) -> dict[str, Any]:
    value = link.get("review_status_snapshot")
    snapshot = dict(value) if isinstance(value, dict) else {}
    documentation_value = _meaningful(link.get("documentation_status"), NOT_RECORDED)
    if documentation_value and not (
        text(snapshot.get("curation_statuses"))
        or text(snapshot.get("review_status"))
        or text(snapshot.get("human_review_status"))
    ):
        snapshot["review_status"] = documentation_value
    return snapshot


def asset_snapshot(link: dict[str, Any]) -> dict[str, Any]:
    value = link.get("asset_snapshot")
    return dict(value) if isinstance(value, dict) else {}


def catalog_label(link: dict[str, Any]) -> str:
    source = source_snapshot(link)
    catalog = text(source.get("catalog"))
    if catalog:
        return catalog
    asset_type = text(link.get("asset_type") or asset_snapshot(link).get("asset_type"))
    if asset_type == "plant_promoter_profile":
        return "Plant Promoter Catalog"
    return "Local Design Asset Catalog"


def asset_display_name(link: dict[str, Any]) -> str:
    snapshot = asset_snapshot(link)
    return text(
        snapshot.get("asset_label")
        or link.get("asset_display_name")
        or link.get("asset_label")
        or link.get("asset_id"),
        NOT_RECORDED,
    )


def record_identifier(link: dict[str, Any]) -> str:
    snapshot = asset_snapshot(link)
    source = source_snapshot(link)
    return text(
        source.get("profile_id")
        or snapshot.get("asset_id")
        or link.get("asset_id"),
        NOT_RECORDED,
    )


def source_label(link: dict[str, Any]) -> str:
    snapshot = asset_snapshot(link)
    source = source_snapshot(link)
    return text(
        snapshot.get("source_label")
        or link.get("source_label")
        or source.get("source_labels")
        or source.get("source_label")
        or source.get("source_provenance_status"),
        SOURCE_STATUS_NOT_RECORDED,
    )


def documentation_status(link: dict[str, Any]) -> str:
    snapshot = asset_snapshot(link)
    review = review_snapshot(link)
    return text(
        snapshot.get("documentation_status")
        or link.get("documentation_status")
        or review.get("curation_statuses")
        or review.get("review_status")
        or review.get("human_review_status"),
        NOT_RECORDED,
    )


def reference_origin(link: dict[str, Any]) -> str:
    return text(source_snapshot(link).get("reference_origin"), DEFAULT_REFERENCE_ORIGIN)


def project_documentation_context(link: dict[str, Any]) -> str:
    return text(
        source_snapshot(link).get("project_documentation_context"),
        DOCUMENTATION_CONTEXT_NOT_PROVIDED,
    )


def documentation_note(link: dict[str, Any]) -> str:
    return text(link.get("documentation_note") or link.get("notes"), NOT_RECORDED)


def catalog_name_source(link: dict[str, Any]) -> str:
    return f"{catalog_label(link)} / {source_label(link)}"


def catalog_source_status(link: dict[str, Any]) -> str:
    return f"{catalog_label(link)} / {source_label(link)} / {documentation_status(link)}"


def source_context_readback(link: dict[str, Any]) -> str:
    return f"Source context readback: catalog {catalog_label(link)}; source/provenance review {source_label(link)}"


def host_chassis_context_readback(link: dict[str, Any]) -> str:
    source = source_snapshot(link)
    host_context_record = {
        "organism_or_source_context": (
            source.get("host_context")
            or source.get("chassis_context")
            or source.get("organism_or_source_context")
            or source.get("species")
            or source.get("plant_clade")
            or ""
        )
    }
    summary = summarize_asset_host_chassis_context(host_context_record)
    return summary["readback"]


def review_needed_context(link: dict[str, Any]) -> str:
    review_value = documentation_status(link)
    human_review = "yes" if bool(link.get("human_review_required")) else "not recorded"
    return f"Review-needed context: curation status {review_value}; human review flag {human_review}"


def metadata_gap_context(link: dict[str, Any]) -> str:
    missing = []
    if source_label(link) == SOURCE_STATUS_NOT_RECORDED:
        missing.append("source context")
    if documentation_status(link) == NOT_RECORDED:
        missing.append("record review status")
    if missing:
        return f"Review gap: missing {' and '.join(missing)} for documentation review"
    return "Source/provenance and record review status recorded for documentation review"


def catalog_reference_context(link: dict[str, Any]) -> str:
    return (
        f"Catalog reference context: origin {reference_origin(link)}; "
        f"link state {linked_persisted_status(link)}; snapshot state {snapshot_status(link)}"
    )


def has_persisted_identity(link: dict[str, Any]) -> bool:
    return bool(
        text(link.get("link_id"))
        or text(link.get("created_at"))
        or text(link.get("updated_at"))
        or text(link.get("linked_persisted_status")) == PERSISTED_LINKED_REFERENCE_STATUS
    )


def linked_persisted_status(link: dict[str, Any]) -> str:
    return PERSISTED_LINKED_REFERENCE_STATUS if has_persisted_identity(link) else LINKED_REFERENCE_LABEL


def has_staged_basket_only_markers(link: dict[str, Any]) -> bool:
    staged_label = text(link.get("staged_reference_label"))
    basket_id = text(link.get("basket_id"))
    origin = reference_origin(link).casefold()
    documentation_context = project_documentation_context(link).casefold()
    return bool(
        staged_label
        or basket_id
        or "staged basket" in origin
        or "staged basket" in documentation_context
    )


def snapshot_status(link: dict[str, Any]) -> str:
    return (
        "pinned documentation snapshot"
        if catalog_asset_snapshot_has_content(asset_snapshot(link))
        else "live metadata fallback"
    )


def snapshot_state(link: dict[str, Any]) -> str:
    return (
        "pinned snapshot"
        if catalog_asset_snapshot_has_content(asset_snapshot(link))
        else "live metadata fallback"
    )


def build_linked_catalog_reference_output(link: dict[str, Any]) -> dict[str, Any]:
    snapshot = asset_snapshot(link)
    source = source_snapshot(link)
    review = review_snapshot(link)
    source_value = source_label(link)
    documentation_value = documentation_status(link)
    return {
        "asset_display_name": asset_display_name(link),
        "asset_label": text(snapshot.get("asset_label") or link.get("asset_label") or link.get("asset_display_name"), NOT_RECORDED),
        "asset_type": text(link.get("asset_type") or snapshot.get("asset_type"), NOT_RECORDED),
        "asset_id": text(link.get("asset_id"), NOT_RECORDED),
        "record_identifier": record_identifier(link),
        "linkage_role": text(link.get("linkage_role"), NOT_RECORDED),
        "catalog_label": catalog_label(link),
        "source_label": source_value,
        "documentation_status": documentation_value,
        "catalog_name_source": catalog_name_source(link),
        "catalog_source_status": catalog_source_status(link),
        "source_context_readback": source_context_readback(link),
        "host_chassis_context_readback": host_chassis_context_readback(link),
        "review_needed_context": review_needed_context(link),
        "metadata_gap_context": metadata_gap_context(link),
        "catalog_reference_context": catalog_reference_context(link),
        "reference_origin": reference_origin(link),
        "project_documentation_context": project_documentation_context(link),
        "documentation_note": documentation_note(link),
        "linked_reference_label": text(link.get("linked_reference_label"), LINKED_REFERENCE_LABEL),
        "linked_persisted_status": linked_persisted_status(link),
        "snapshot_status": snapshot_status(link),
        "snapshot_state": snapshot_state(link),
        "has_pinned_snapshot": catalog_asset_snapshot_has_content(snapshot),
        "snapshot_schema_version": text(link.get("snapshot_schema_version"), NOT_RECORDED),
        "snapshot_captured_at": text(link.get("snapshot_captured_at"), NOT_RECORDED),
        "source_review_note": text(link.get("notes"), NOT_RECORDED),
        "human_review_required": bool(link.get("human_review_required")),
        "missing_metadata": source_value == SOURCE_STATUS_NOT_RECORDED or documentation_value == NOT_RECORDED,
        "asset_snapshot": snapshot,
        "source_context_snapshot": source,
        "review_status_snapshot": review,
    }
