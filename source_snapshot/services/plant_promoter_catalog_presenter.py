from __future__ import annotations

from collections import Counter
from typing import Any

from services import parts_registry_repository as repo
from services import plant_promoter_catalog_seed_loader as seed_loader


ALL_FILTER_VALUE = "all"
OTHER_FILTER_VALUE = "other"
UNKNOWN_FILTER_VALUE = "unknown"
OTHER_CLADE_LABEL = "other / not specified"

NO_CLADE_LABEL = "No plant clade recorded"
NO_SPECIES_LABEL = "No species context recorded"
NO_TISSUE_LABEL = "No tissue context recorded"
NO_SOURCE_LABEL = "No source database recorded"
NO_EVIDENCE_TYPE_LABEL = "No evidence type recorded"
NO_CURATION_STATUS_LABEL = "No curation status recorded"
NO_REVIEW_NOTE_LABEL = "No manual review note recorded"

BOUNDARY_NOTE = "Read-only catalog context for documentation and source review."
SEED_CONTEXT_NOTE = (
    "Local curated sample records are shown as documentation-level catalog context; "
    "they are not selection advice, source verification, biological forecasts, or wet-lab use guidance."
)
READBACK_BOUNDARY_NOTE = (
    "Documentation-only context readback for catalog/source review. "
    "This readback does not recommend promoters, rank records, verify host compatibility, "
    "predict expression, validate use, or judge wet-lab readiness."
)
PERSISTENT_RECORD_LABEL = "persistent records"
SEEDED_RECORD_LABEL = "bundled seed records"
DOCUMENTATION_REFERENCE_LABEL = "documentation-only reference records"


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _normalize_filter(value: Any) -> str:
    return _text(value).lower()


def _species_label(profile: dict[str, Any]) -> str:
    scientific = _text(profile.get("species_scientific_name"))
    common = _text(profile.get("species_common_name"))
    if scientific and common:
        return f"{scientific} ({common})"
    return scientific or common or NO_SPECIES_LABEL


def _source_label(evidence: dict[str, Any]) -> str:
    source = _text(evidence.get("source_database"))
    accession = _text(evidence.get("source_accession"))
    if source and accession:
        return f"{source}: {accession}"
    return source or accession or NO_SOURCE_LABEL


def _missing_metadata_labels(profile: dict[str, Any], evidence: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    if not _text(profile.get("plant_clade")):
        gaps.append("plant clade metadata gap")
    if not _text(profile.get("species_scientific_name")) and not _text(profile.get("species_common_name")):
        gaps.append("species context metadata gap")
    if not _text(evidence.get("tissue_context")):
        gaps.append("tissue evidence context metadata gap")
    if not _text(evidence.get("source_database")) and not _text(evidence.get("source_accession")):
        gaps.append("source context metadata gap")
    if not _text(evidence.get("curation_status")):
        gaps.append("review metadata gap")
    if not _text(evidence.get("review_note")):
        gaps.append("manual review note metadata gap")
    return gaps


def _needs_review(evidence: dict[str, Any]) -> bool:
    combined = " ".join(
        [
            _text(evidence.get("curation_status")),
            _text(evidence.get("review_note")),
        ]
    ).lower()
    return "need" in combined or "follow-up" in combined or not combined.strip()


def _normalize_clade_label(profile: dict[str, Any]) -> str:
    return _text(profile.get("plant_clade"), NO_CLADE_LABEL)


def _normalize_tissue_label(evidence: dict[str, Any]) -> str:
    return _text(evidence.get("tissue_context"), NO_TISSUE_LABEL)


def _normalize_source_database_label(evidence: dict[str, Any]) -> str:
    return _text(evidence.get("source_database"), NO_SOURCE_LABEL)


def _normalize_evidence_type_label(evidence: dict[str, Any]) -> str:
    return _text(evidence.get("evidence_type"), NO_EVIDENCE_TYPE_LABEL)


def _normalize_curation_status_label(evidence: dict[str, Any]) -> str:
    return _text(evidence.get("curation_status"), NO_CURATION_STATUS_LABEL)


def _matches_named_filter(selected: str, actual: str, *, other_label: str | None = None) -> bool:
    token = _normalize_filter(selected)
    if not token or token == ALL_FILTER_VALUE:
        return True

    actual_token = _normalize_filter(actual)
    if token == UNKNOWN_FILTER_VALUE:
        return actual in {
            NO_CLADE_LABEL,
            NO_SPECIES_LABEL,
            NO_TISSUE_LABEL,
            NO_SOURCE_LABEL,
            NO_EVIDENCE_TYPE_LABEL,
            NO_CURATION_STATUS_LABEL,
        }
    if token == OTHER_FILTER_VALUE and other_label:
        return actual_token == _normalize_filter(other_label)
    return actual_token == token


def _matches_species_filter(selected: str, actual: str) -> bool:
    token = _normalize_filter(selected)
    if not token or token == ALL_FILTER_VALUE:
        return True
    if token == UNKNOWN_FILTER_VALUE:
        return actual == NO_SPECIES_LABEL
    return _normalize_filter(actual) == token


def build_plant_promoter_catalog_view_model(
    *,
    plant_clade: str | None = None,
    species: str | None = None,
    tissue_context: str | None = None,
    evidence_type: str | None = None,
    curation_status: str | None = None,
) -> dict[str, Any]:
    """Build a read-only view model for the plant promoter catalog browse UI."""
    profiles = repo.list_plant_promoter_profiles()
    use_seed_records = not profiles
    seed_catalog: dict[str, Any] = {}
    if use_seed_records:
        seed_catalog = seed_loader.load_seed_catalog()
        profiles = seed_catalog.get("profiles") or []

    clades: set[str] = set()
    species_labels: set[str] = set()
    tissue_labels: set[str] = set()
    evidence_type_labels: set[str] = set()
    curation_status_labels: set[str] = set()
    source_database_labels: set[str] = set()
    source_evidence_labels: set[str] = set()

    tissue_counts: Counter[str] = Counter()
    rows_needing_review: list[dict[str, Any]] = []
    profile_rows: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    context_readback_rows: list[dict[str, Any]] = []
    motif_preview_rows: list[dict[str, Any]] = []

    filtered_profile_count = 0
    tissue_total = 0
    motif_total = 0
    linked_catalog_reference_ids: set[str] = set()
    represented_part_ids: set[str] = set()

    for profile in profiles:
        clade_label = _normalize_clade_label(profile)
        species_label = _species_label(profile)
        clades.add(clade_label)
        species_labels.add(species_label)

        if not _matches_named_filter(plant_clade or "", clade_label, other_label=OTHER_CLADE_LABEL):
            continue
        if not _matches_species_filter(species or "", species_label):
            continue

        part_id = _text(profile.get("part_id"))
        if part_id:
            represented_part_ids.add(part_id)
        if use_seed_records:
            tissue_rows = seed_loader.list_seed_tissue_evidence(part_id)
            motif_rows = seed_loader.list_seed_motif_annotations(part_id)
        else:
            tissue_rows = repo.list_plant_promoter_tissue_evidence(part_id)
            motif_rows = repo.list_plant_promoter_motif_annotations(part_id)

        filtered_tissue_rows: list[dict[str, Any]] = []
        for evidence in tissue_rows:
            tissue_label = _normalize_tissue_label(evidence)
            evidence_label = _normalize_evidence_type_label(evidence)
            curation_label = _normalize_curation_status_label(evidence)
            source_database_label = _normalize_source_database_label(evidence)

            tissue_labels.add(tissue_label)
            evidence_type_labels.add(evidence_label)
            curation_status_labels.add(curation_label)
            source_database_labels.add(source_database_label)
            source_evidence_labels.add(_source_label(evidence))
            if source_database_label != NO_SOURCE_LABEL:
                linked_catalog_reference_ids.add(source_database_label)

            if not _matches_named_filter(tissue_context or "", tissue_label):
                continue
            if not _matches_named_filter(evidence_type or "", evidence_label):
                continue
            if not _matches_named_filter(curation_status or "", curation_label):
                continue

            filtered_tissue_rows.append(evidence)
            tissue_counts[tissue_label] += 1
            tissue_total += 1

            review_row = {
                "part_id": part_id,
                "display_name": _text(profile.get("display_name")),
                "tissue_context": tissue_label,
                "curation_status": curation_label,
                "review_note": _text(evidence.get("review_note")),
            }
            if _needs_review(evidence):
                rows_needing_review.append(review_row)

            evidence_rows.append(
                {
                    "part_id": part_id,
                    "display_name": _text(profile.get("display_name")),
                    "promoter_label": _text(profile.get("display_name")) or part_id,
                    "plant_clade": clade_label,
                    "species_label": species_label,
                    "tissue_context": tissue_label,
                    "evidence_type": evidence_label,
                    "source_database": source_database_label,
                    "curation_status": curation_label,
                    "review_note": _text(evidence.get("review_note")),
                }
            )
            missing_metadata = _missing_metadata_labels(profile, evidence)
            context_readback_rows.append(
                {
                    "part_id": part_id,
                    "promoter_label": _text(profile.get("display_name")) or part_id,
                    "catalog_context": _text(profile.get("display_name")) or part_id,
                    "species_or_clade_context": "; ".join(
                        [
                            label
                            for label in (
                                species_label if species_label != NO_SPECIES_LABEL else "",
                                clade_label if clade_label != NO_CLADE_LABEL else "",
                            )
                            if label
                        ]
                    )
                    or f"{NO_SPECIES_LABEL}; {NO_CLADE_LABEL}",
                    "tissue_evidence_context": "; ".join(
                        [
                            _text(evidence.get("tissue_context"), NO_TISSUE_LABEL),
                            _text(evidence.get("evidence_type"), NO_EVIDENCE_TYPE_LABEL),
                        ]
                    ),
                    "source_review_metadata": "; ".join(
                        [
                            f"source context: {_source_label(evidence)}",
                            f"review metadata: {_text(evidence.get('curation_status'), NO_CURATION_STATUS_LABEL)}",
                            f"manual review note: {_text(evidence.get('review_note'), NO_REVIEW_NOTE_LABEL)}",
                        ]
                    ),
                    "metadata_gap": "; ".join(missing_metadata) if missing_metadata else "No metadata gap recorded",
                    "documentation_boundary": READBACK_BOUNDARY_NOTE,
                }
            )

        if tissue_rows and not filtered_tissue_rows and any(
            _normalize_filter(value)
            not in {"", ALL_FILTER_VALUE}
            for value in (tissue_context, evidence_type, curation_status)
        ):
            continue

        filtered_profile_count += 1
        motif_total += len(motif_rows)

        profile_rows.append(
            {
                "part_id": part_id,
                "display_name": _text(profile.get("display_name")),
                "plant_clade": clade_label,
                "species_label": species_label,
                "promoter_type": _text(profile.get("promoter_type")),
                "sequence_availability": _text(profile.get("sequence_availability")),
                "tissue_evidence_count": len(filtered_tissue_rows),
                "motif_annotation_count": len(motif_rows),
                "catalog_record_source": _text(profile.get("seed_source"), "local Parts Registry"),
                "documentation_status": _text(profile.get("documentation_status")),
                "limitation_notes": "; ".join(profile.get("limitation_notes") or []),
            }
        )

        for motif in motif_rows:
            motif_preview_rows.append(
                {
                    "promoter_label": _text(profile.get("display_name")) or part_id,
                    "motif_name": _text(motif.get("motif_name"), "Unnamed motif note"),
                    "motif_source": _text(motif.get("motif_source"), NO_SOURCE_LABEL),
                    "motif_accession": _text(motif.get("motif_accession"), "No source accession recorded"),
                    "evidence_note": _text(motif.get("evidence_note"), "No motif evidence note recorded"),
                }
            )

    return {
        "summary_counts": {
            "profile_count": filtered_profile_count,
            "tissue_evidence_count": tissue_total,
            "motif_annotation_count": motif_total,
            "rows_needing_review_count": len(rows_needing_review),
            "source_database_count": len(source_database_labels),
            "linked_catalog_reference_count": len(linked_catalog_reference_ids),
        },
        "available_plant_clades": sorted(clades, key=str.casefold),
        "available_species": sorted(species_labels, key=str.casefold),
        "available_tissue_contexts": sorted(tissue_labels, key=str.casefold),
        "available_evidence_types": sorted(evidence_type_labels, key=str.casefold),
        "available_curation_statuses": sorted(curation_status_labels, key=str.casefold),
        "tissue_context_evidence_summary": dict(sorted(tissue_counts.items())),
        "rows_needing_review": rows_needing_review,
        "source_evidence_labels": sorted(source_evidence_labels, key=str.casefold),
        "source_database_labels": sorted(source_database_labels, key=str.casefold),
        "profile_rows": profile_rows,
        "evidence_rows": evidence_rows,
        "context_readback_rows": context_readback_rows,
        "motif_preview_rows": motif_preview_rows,
        "boundary_note": SEED_CONTEXT_NOTE if use_seed_records else BOUNDARY_NOTE,
        "documentation_only_context_note": READBACK_BOUNDARY_NOTE,
        "catalog_source": "local curated sample records" if use_seed_records else "local Parts Registry",
        "catalog_status_label": SEEDED_RECORD_LABEL if use_seed_records else PERSISTENT_RECORD_LABEL,
        "documentation_status_label": DOCUMENTATION_REFERENCE_LABEL,
        "persistent_profile_count": 0 if use_seed_records else len(profiles),
        "seed_profile_count": len(profiles) if use_seed_records else 0,
        "represented_source_database_labels": sorted(source_database_labels, key=str.casefold),
        "linked_catalog_reference_labels": sorted(linked_catalog_reference_ids, key=str.casefold),
        "represented_profile_ids": sorted(represented_part_ids, key=str.casefold),
        "seed_metadata": seed_catalog.get("metadata", {}) if use_seed_records else {},
        "seed_warnings": seed_catalog.get("warnings", []) if use_seed_records else [],
    }
