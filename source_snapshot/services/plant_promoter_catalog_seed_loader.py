from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "plant_promoter_catalog_seed.json"
SEED_TIMESTAMP = "2026-06-17T00:00:00"

REQUIRED_RECORD_FIELDS = {
    "promoter_id",
    "promoter_name",
    "species",
    "clade",
    "tissue_contexts",
    "evidence_labels",
    "motif_annotations",
    "source_labels",
    "review_status",
    "documentation_status",
    "limitation_notes",
}
KNOWN_RECORD_FIELDS = REQUIRED_RECORD_FIELDS | {
    "aliases",
    "promoter_type",
    "sequence_availability",
    "sequence_scope_note",
    "tss_reference_note",
}
KNOWN_SPECIES_FIELDS = {
    "scientific_name",
    "common_name",
    "taxonomy_id",
    "cultivar_or_ecotype",
}


class PlantPromoterCatalogSeedError(ValueError):
    """Raised when local Plant Promoter Catalog seed data cannot be loaded safely."""


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _string_list(value: Any) -> list[str]:
    return [_text(item) for item in _as_list(value) if _text(item)]


def _record_required_errors(record: Any, index: int) -> list[str]:
    if not isinstance(record, dict):
        return [f"record {index} is not an object"]
    errors: list[str] = []
    for field in sorted(REQUIRED_RECORD_FIELDS):
        if field not in record:
            errors.append(f"record {index} missing required field: {field}")
            continue
        value = record.get(field)
        if field not in {"tissue_contexts", "motif_annotations", "evidence_labels", "source_labels", "limitation_notes"} and value in (None, "", {}):
            errors.append(f"record {index} missing required field: {field}")
    species = record.get("species")
    if not isinstance(species, dict):
        errors.append(f"record {index} species must be an object")
    elif not _text(species.get("scientific_name")):
        errors.append(f"record {index} missing required field: species.scientific_name")
    if not isinstance(record.get("tissue_contexts"), list):
        errors.append(f"record {index} tissue_contexts must be a list")
    if not isinstance(record.get("motif_annotations"), list):
        errors.append(f"record {index} motif_annotations must be a list")
    return errors


def _unknown_field_warnings(record: dict[str, Any], index: int) -> list[str]:
    warnings = [
        f"record {index} unknown field ignored: {field}"
        for field in sorted(set(record) - KNOWN_RECORD_FIELDS)
    ]
    species = record.get("species")
    if isinstance(species, dict):
        warnings.extend(
            f"record {index} species unknown field ignored: {field}"
            for field in sorted(set(species) - KNOWN_SPECIES_FIELDS)
        )
    return warnings


def _profile_row(record: dict[str, Any]) -> dict[str, Any]:
    species = record.get("species") if isinstance(record.get("species"), dict) else {}
    aliases = _string_list(record.get("aliases"))
    limitation_notes = _string_list(record.get("limitation_notes"))
    description_parts = [
        "Local curated sample record for documentation-level Plant Promoter Catalog context.",
        f"Documentation status: {_text(record.get('documentation_status'), 'source review needed')}.",
    ]
    if limitation_notes:
        description_parts.append(f"Limitation notes: {'; '.join(limitation_notes)}.")
    return {
        "part_id": _text(record.get("promoter_id")),
        "part_type": "Promoter",
        "display_name": _text(record.get("promoter_name")),
        "description": " ".join(description_parts),
        "plant_clade": _text(record.get("clade"), "other / not specified"),
        "species_scientific_name": _text(species.get("scientific_name")),
        "species_common_name": _text(species.get("common_name")),
        "taxonomy_id": _text(species.get("taxonomy_id")),
        "cultivar_or_ecotype": _text(species.get("cultivar_or_ecotype")),
        "native_gene_or_locus": "; ".join(aliases),
        "promoter_type": _text(record.get("promoter_type"), "source-recorded promoter context"),
        "sequence_availability": _text(record.get("sequence_availability"), "metadata-only sequence context"),
        "sequence_scope_note": _text(record.get("sequence_scope_note"), "Sequence scope is recorded as documentation context."),
        "tss_reference_note": _text(record.get("tss_reference_note"), "TSS reference note is source context."),
        "seed_source": "local curated sample records",
        "evidence_labels": _string_list(record.get("evidence_labels")),
        "source_labels": _string_list(record.get("source_labels")),
        "documentation_status": _text(record.get("documentation_status"), "source review needed"),
        "limitation_notes": limitation_notes,
        "created_at": SEED_TIMESTAMP,
        "updated_at": SEED_TIMESTAMP,
    }


def _evidence_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    part_id = _text(record.get("promoter_id"))
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(_as_list(record.get("tissue_contexts")), start=1):
        row = item if isinstance(item, dict) else {}
        evidence_label = _text(row.get("evidence_label"), "source review needed")
        source_label = _text(row.get("source_label"))
        rows.append(
            {
                "id": index,
                "part_id": part_id,
                "tissue_context": _text(row.get("tissue_context")),
                "plant_ontology_id": _text(row.get("plant_ontology_id")),
                "development_stage": _text(row.get("development_stage")),
                "expression_context_label": _text(row.get("expression_context_label")),
                "evidence_type": evidence_label,
                "evidence_summary": _text(row.get("evidence_summary"), "No evidence summary recorded"),
                "source_label": source_label,
                "source_database": _text(row.get("source_database"), source_label),
                "source_accession": _text(row.get("source_accession")),
                "publication_reference": _text(row.get("publication_reference"), "Reviewer-selected citation needed"),
                "curation_status": _text(row.get("review_status"), _text(record.get("review_status"), "source review needed")),
                "review_note": _text(row.get("review_note"), "Source review needed before citation."),
                "created_at": SEED_TIMESTAMP,
                "updated_at": SEED_TIMESTAMP,
            }
        )
    return rows


def _motif_rows(record: dict[str, Any]) -> list[dict[str, Any]]:
    part_id = _text(record.get("promoter_id"))
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(_as_list(record.get("motif_annotations")), start=1):
        row = item if isinstance(item, dict) else {}
        rows.append(
            {
                "id": index,
                "part_id": part_id,
                "motif_name": _text(row.get("motif_name"), "Unnamed motif note"),
                "motif_source": _text(row.get("motif_source"), "No source database recorded"),
                "motif_accession": _text(row.get("motif_accession")),
                "motif_sequence_or_consensus": _text(row.get("motif_sequence_or_consensus")),
                "motif_position_note": _text(row.get("motif_position_note")),
                "associated_function_note": _text(row.get("associated_function_note"), "Function note is documentation context only."),
                "evidence_note": _text(row.get("evidence_note"), "No motif evidence note recorded"),
                "created_at": SEED_TIMESTAMP,
                "updated_at": SEED_TIMESTAMP,
            }
        )
    return rows


def _build_catalog(payload: dict[str, Any]) -> dict[str, Any]:
    records = payload.get("records")
    if not isinstance(records, list):
        raise PlantPromoterCatalogSeedError("Plant promoter seed payload must contain a records list.")

    errors: list[str] = []
    warnings: list[str] = []
    seen_ids: set[str] = set()
    profiles: list[dict[str, Any]] = []
    tissue_by_part_id: dict[str, list[dict[str, Any]]] = {}
    motifs_by_part_id: dict[str, list[dict[str, Any]]] = {}

    for index, record in enumerate(records, start=1):
        errors.extend(_record_required_errors(record, index))
        if not isinstance(record, dict):
            continue
        warnings.extend(_unknown_field_warnings(record, index))
        promoter_id = _text(record.get("promoter_id"))
        if promoter_id in seen_ids:
            errors.append(f"duplicate promoter_id: {promoter_id}")
            continue
        seen_ids.add(promoter_id)
        if any(error.startswith(f"record {index} ") for error in errors):
            continue
        evidence_rows = _evidence_rows(record)
        if not evidence_rows:
            warnings.append(f"record {index} has no tissue evidence rows after normalization")
        profiles.append(_profile_row(record))
        tissue_by_part_id[promoter_id] = sorted(
            evidence_rows,
            key=lambda row: (_text(row.get("tissue_context")).casefold(), _text(row.get("source_accession")).casefold()),
        )
        motifs_by_part_id[promoter_id] = sorted(
            _motif_rows(record),
            key=lambda row: (_text(row.get("motif_name")).casefold(), _text(row.get("motif_accession")).casefold()),
        )

    if errors:
        raise PlantPromoterCatalogSeedError("; ".join(sorted(errors, key=str.casefold)))

    return {
        "metadata": {
            "seed_name": _text(payload.get("seed_name")),
            "seed_version": _text(payload.get("seed_version")),
            "seed_scope": _text(payload.get("seed_scope")),
            "documentation_boundary_note": _text(payload.get("documentation_boundary_note")),
        },
        "warnings": warnings,
        "profiles": sorted(profiles, key=lambda row: (_text(row.get("display_name")).casefold(), _text(row.get("part_id")).casefold())),
        "tissue_evidence_by_part_id": tissue_by_part_id,
        "motif_annotations_by_part_id": motifs_by_part_id,
    }


def load_seed_catalog(seed_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(seed_path) if seed_path is not None else DEFAULT_SEED_PATH
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PlantPromoterCatalogSeedError(f"Unable to read plant promoter seed data: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise PlantPromoterCatalogSeedError(f"Invalid plant promoter seed JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise PlantPromoterCatalogSeedError("Plant promoter seed payload must be a JSON object.")
    return _build_catalog(payload)


def list_seed_profiles(seed_path: str | Path | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in load_seed_catalog(seed_path).get("profiles", [])]


def get_seed_profile_by_part_id(part_id: Any, seed_path: str | Path | None = None) -> dict[str, Any]:
    clean = _text(part_id)
    if not clean:
        return {}
    for row in list_seed_profiles(seed_path):
        if _text(row.get("part_id")) == clean:
            return row
    return {}


def list_seed_tissue_evidence(part_id: Any, seed_path: str | Path | None = None) -> list[dict[str, Any]]:
    clean = _text(part_id)
    catalog = load_seed_catalog(seed_path)
    rows = catalog.get("tissue_evidence_by_part_id", {}).get(clean, [])
    return [dict(row) for row in rows if isinstance(row, dict)]


def list_seed_motif_annotations(part_id: Any, seed_path: str | Path | None = None) -> list[dict[str, Any]]:
    clean = _text(part_id)
    catalog = load_seed_catalog(seed_path)
    rows = catalog.get("motif_annotations_by_part_id", {}).get(clean, [])
    return [dict(row) for row in rows if isinstance(row, dict)]
