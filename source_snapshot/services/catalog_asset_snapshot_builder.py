from __future__ import annotations

from typing import Any, Iterable


SNAPSHOT_SCHEMA_VERSION = "2.6-r39-catalog-reference-snapshot"
SNAPSHOT_MISSING_METADATA_NOTE = "Captured reference context has missing optional metadata."
SNAPSHOT_LIMITATION_NOTE = (
    "Pinned documentation snapshot for reference context only; human review remains required."
)

SNAPSHOT_FIELDS = (
    "asset_type",
    "asset_id",
    "asset_label",
    "asset_version",
    "source_label",
    "documentation_status",
    "species",
    "clade",
    "aliases",
    "tissue_contexts",
    "motif_labels",
    "limitation_note",
)

_SNAPSHOT_MEANINGFUL_FIELDS = (
    "asset_type",
    "asset_id",
    "asset_label",
    "asset_version",
    "source_label",
    "documentation_status",
    "species",
    "clade",
    "aliases",
    "tissue_contexts",
    "motif_labels",
    "limitation_note",
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _first_text(source: dict[str, Any], keys: Iterable[str], fallback: str = "") -> str:
    for key in keys:
        value = _text(source.get(key))
        if value:
            return value
    return fallback


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = [item.strip() for item in value.replace("|", ";").split(";")]
    elif isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    else:
        raw_values = []
    return sorted({_text(item) for item in raw_values if _text(item)}, key=str.casefold)


def _source_label(source: dict[str, Any]) -> str:
    source_database = _first_text(source, ("source_database", "source_label", "source_labels"))
    source_accession = _first_text(source, ("source_accession", "accession"))
    if source_database and source_accession and source_accession not in source_database:
        return f"{source_database}: {source_accession}"
    return _first_text(
        source,
        (
            "source_labels",
            "source_label",
            "source_database",
            "catalog_record_source",
            "seed_source",
            "source_notes",
            "provenance_status",
            "catalog",
        ),
    )


def _documentation_status(source: dict[str, Any]) -> str:
    return _first_text(
        source,
        (
            "documentation_status",
            "curation_status",
            "review_status",
            "human_review_status",
            "source_provenance_status",
            "documentation_boundary_note",
        ),
    )


def _species(source: dict[str, Any]) -> str:
    scientific = _first_text(source, ("species_scientific_name",))
    common = _first_text(source, ("species_common_name",))
    if scientific and common:
        return f"{scientific} ({common})"
    return _first_text(
        source,
        ("species", "species_label", "organism_or_source_context", "organism"),
        scientific or common,
    )


def _clade(source: dict[str, Any]) -> str:
    return _first_text(source, ("clade", "plant_clade"))


def _asset_label(source: dict[str, Any]) -> str:
    return _first_text(
        source,
        (
            "asset_label",
            "asset_display_name",
            "display_label",
            "display_name",
            "promoter_label",
            "part_label",
            "name",
        ),
        _first_text(source, ("asset_id", "part_id")),
    )


def _asset_id(source: dict[str, Any]) -> str:
    return _first_text(source, ("asset_id", "part_id", "profile_id", "record_id"))


def _asset_version(source: dict[str, Any]) -> str:
    return _first_text(source, ("asset_version", "version_context", "seed_version"))


def _aliases(source: dict[str, Any]) -> list[str]:
    values = _text_list(source.get("aliases"))
    locus = _first_text(source, ("native_gene_or_locus", "alias"))
    if locus:
        values.append(locus)
    return sorted(set(values), key=str.casefold)


def _tissue_contexts(source: dict[str, Any], evidence_rows: Iterable[dict[str, Any]] | None) -> list[str]:
    values = _text_list(source.get("tissue_contexts") or source.get("tissue_context"))
    for row in evidence_rows or []:
        if isinstance(row, dict):
            value = _first_text(row, ("tissue_context", "expression_context_label"))
            if value:
                values.append(value)
    return sorted(set(values), key=str.casefold)


def _motif_labels(source: dict[str, Any], motif_rows: Iterable[dict[str, Any]] | None) -> list[str]:
    values = _text_list(source.get("motif_labels") or source.get("motif_names"))
    for row in motif_rows or []:
        if isinstance(row, dict):
            value = _first_text(row, ("motif_name", "motif_label"))
            if value:
                values.append(value)
    return sorted(set(values), key=str.casefold)


def _limitation_note(source: dict[str, Any]) -> str:
    notes = _text_list(source.get("limitation_notes"))
    if notes:
        return "; ".join(notes)
    return _first_text(
        source,
        ("limitation_note", "documentation_boundary_note", "documentation_note"),
        SNAPSHOT_LIMITATION_NOTE,
    )


def build_catalog_asset_snapshot(
    record: dict[str, Any] | None,
    *,
    asset_type: Any = "",
    evidence_rows: Iterable[dict[str, Any]] | None = None,
    motif_rows: Iterable[dict[str, Any]] | None = None,
    fallback: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic compact metadata snapshot for documentation links."""
    source: dict[str, Any] = {}
    if isinstance(fallback, dict):
        source.update(fallback)
    if isinstance(record, dict):
        source.update(record)

    snapshot = {
        "asset_type": _text(asset_type) or _first_text(source, ("asset_type",)),
        "asset_id": _asset_id(source),
        "asset_label": _asset_label(source),
        "asset_version": _asset_version(source),
        "source_label": _source_label(source),
        "documentation_status": _documentation_status(source),
        "species": _species(source),
        "clade": _clade(source),
        "aliases": _aliases(source),
        "tissue_contexts": _tissue_contexts(source, evidence_rows),
        "motif_labels": _motif_labels(source, motif_rows),
        "limitation_note": _limitation_note(source),
    }
    missing_fields = [
        field
        for field in ("asset_type", "asset_id", "asset_label", "source_label", "documentation_status")
        if not snapshot[field]
    ]
    if missing_fields:
        snapshot["missing_metadata_note"] = SNAPSHOT_MISSING_METADATA_NOTE
        snapshot["missing_metadata_fields"] = missing_fields
    return snapshot


def sanitize_catalog_asset_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    cleaned = {field: value.get(field, [] if field in {"aliases", "tissue_contexts", "motif_labels"} else "") for field in SNAPSHOT_FIELDS}
    for field in ("aliases", "tissue_contexts", "motif_labels"):
        cleaned[field] = _text_list(cleaned.get(field))
    for field in ("asset_type", "asset_id", "asset_label", "asset_version", "source_label", "documentation_status", "species", "clade", "limitation_note"):
        cleaned[field] = _text(cleaned.get(field))
    if isinstance(value.get("missing_metadata_fields"), list):
        cleaned["missing_metadata_fields"] = _text_list(value.get("missing_metadata_fields"))
    if _text(value.get("missing_metadata_note")):
        cleaned["missing_metadata_note"] = _text(value.get("missing_metadata_note"))
    if not any(
        cleaned.get(field)
        for field in (*_SNAPSHOT_MEANINGFUL_FIELDS, "missing_metadata_fields", "missing_metadata_note")
    ):
        return {}
    return cleaned


def blank_catalog_asset_snapshot() -> dict[str, Any]:
    return {
        field: [] if field in {"aliases", "tissue_contexts", "motif_labels"} else ""
        for field in SNAPSHOT_FIELDS
    }


def catalog_asset_snapshot_has_content(value: Any) -> bool:
    snapshot = sanitize_catalog_asset_snapshot(value)
    if not snapshot:
        return False
    if any(_text(snapshot.get(field)) for field in _SNAPSHOT_MEANINGFUL_FIELDS if field not in {"aliases", "tissue_contexts", "motif_labels"}):
        return True
    return any(_text_list(snapshot.get(field)) for field in ("aliases", "tissue_contexts", "motif_labels"))
