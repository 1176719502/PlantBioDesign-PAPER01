from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from services import parts_registry_repository as repo
from services import plant_promoter_catalog_presenter as catalog_presenter
from services import plant_promoter_catalog_seed_loader as seed_loader
from services.catalog_asset_snapshot_builder import (
    build_catalog_asset_snapshot,
    catalog_asset_snapshot_has_content,
)
from services.project_asset_linkage_service import build_project_asset_link, list_project_asset_links


PLANT_PROMOTER_PROFILE_ASSET_TYPE = "plant_promoter_profile"
PLANT_PROMOTER_CATALOG_LABEL = "Plant Promoter Catalog"
DEFAULT_REFERENCE_NOTE = "Documentation-only Component Library promoter asset reference for project traceability."
CATALOG_REFERENCE_BOUNDARY_NOTE = (
    "Read-only Component Library promoter asset reference. Documentation-level context only; "
    "not selection advice, behavior forecast, source verification, or wet-lab use guidance."
)
CATALOG_REFERENCE_LIMITATION_NOTE = (
    "Linked Component Library promoter assets preserve catalog metadata snapshots only. "
    "They do not choose records, rate records, order records, alter records, or assert source verification."
)
EMPTY_CATALOG_REFERENCE_MESSAGE = (
    "No Component Library promoter asset profiles are available for project reference linking."
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _unique(values: Iterable[Any]) -> list[str]:
    return sorted({_text(value) for value in values if _text(value)}, key=str.casefold)


def _species_label(profile: dict[str, Any]) -> str:
    scientific = _text(profile.get("species_scientific_name"))
    common = _text(profile.get("species_common_name"))
    if scientific and common:
        return f"{scientific} ({common})"
    return scientific or common or catalog_presenter.NO_SPECIES_LABEL


def _source_label(row: dict[str, Any]) -> str:
    source = _text(row.get("source_database"))
    accession = _text(row.get("source_accession"))
    if source and accession:
        return f"{source}: {accession}"
    return source or accession or catalog_presenter.NO_SOURCE_LABEL


def _get_profile(clean_part_id: str) -> dict[str, Any]:
    profile = repo.get_plant_promoter_profile_by_part_id(clean_part_id)
    if profile:
        return profile
    return seed_loader.get_seed_profile_by_part_id(clean_part_id)


def _list_evidence_rows(clean_part_id: str, *, use_seed: bool) -> list[dict[str, Any]]:
    if use_seed:
        return seed_loader.list_seed_tissue_evidence(clean_part_id)
    return repo.list_plant_promoter_tissue_evidence(clean_part_id)


def _list_motif_rows(clean_part_id: str, *, use_seed: bool) -> list[dict[str, Any]]:
    if use_seed:
        return seed_loader.list_seed_motif_annotations(clean_part_id)
    return repo.list_plant_promoter_motif_annotations(clean_part_id)


def _profile_summary_row(profile: dict[str, Any], evidence_rows: list[dict[str, Any]], motif_rows: list[dict[str, Any]]) -> dict[str, Any]:
    part_id = _text(profile.get("part_id"))
    return {
        "part_id": part_id,
        "promoter_label": _text(profile.get("display_name"), part_id),
        "alias": _text(profile.get("native_gene_or_locus"), "No alias or locus recorded"),
        "plant_clade": _text(profile.get("plant_clade"), catalog_presenter.NO_CLADE_LABEL),
        "species_label": _species_label(profile),
        "promoter_type": _text(profile.get("promoter_type"), "No promoter type recorded"),
        "sequence_availability": _text(profile.get("sequence_availability"), "No sequence availability note recorded"),
        "catalog_record_source": _text(profile.get("seed_source"), "local Parts Registry"),
        "documentation_status": _text(profile.get("documentation_status"), "No documentation status recorded"),
        "limitation_notes": "; ".join(profile.get("limitation_notes") or []),
        "tissue_context_count": len(_unique(row.get("tissue_context") for row in evidence_rows)),
        "evidence_row_count": len(evidence_rows),
        "motif_annotation_count": len(motif_rows),
    }


def _evidence_view_rows(profile: dict[str, Any], evidence_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    part_id = _text(profile.get("part_id"))
    label = _text(profile.get("display_name"), part_id)
    clade = _text(profile.get("plant_clade"), catalog_presenter.NO_CLADE_LABEL)
    species = _species_label(profile)
    return [
        {
            "part_id": part_id,
            "promoter_label": label,
            "plant_clade": clade,
            "species_label": species,
            "tissue_context": _text(row.get("tissue_context"), catalog_presenter.NO_TISSUE_LABEL),
            "plant_ontology_id": _text(row.get("plant_ontology_id"), "No plant ontology id recorded"),
            "development_stage": _text(row.get("development_stage"), "No development stage recorded"),
            "expression_context_label": _text(row.get("expression_context_label"), "No expression context label recorded"),
            "evidence_type": _text(row.get("evidence_type"), catalog_presenter.NO_EVIDENCE_TYPE_LABEL),
            "evidence_summary": _text(row.get("evidence_summary"), "No evidence summary recorded"),
            "source_label": _source_label(row),
            "source_database": _text(row.get("source_database"), catalog_presenter.NO_SOURCE_LABEL),
            "source_accession": _text(row.get("source_accession"), "No source accession recorded"),
            "publication_reference": _text(row.get("publication_reference"), "No publication reference recorded"),
            "curation_status": _text(row.get("curation_status"), catalog_presenter.NO_CURATION_STATUS_LABEL),
            "review_note": _text(row.get("review_note"), "No review note recorded"),
        }
        for row in evidence_rows
    ]


def _motif_view_rows(profile: dict[str, Any], motif_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    label = _text(profile.get("display_name"), _text(profile.get("part_id")))
    return [
        {
            "promoter_label": label,
            "motif_name": _text(row.get("motif_name"), "Unnamed motif note"),
            "motif_source": _text(row.get("motif_source"), catalog_presenter.NO_SOURCE_LABEL),
            "motif_accession": _text(row.get("motif_accession"), "No motif accession recorded"),
            "motif_sequence_or_consensus": _text(row.get("motif_sequence_or_consensus"), "No motif sequence note recorded"),
            "motif_position_note": _text(row.get("motif_position_note"), "No motif position note recorded"),
            "associated_function_note": _text(row.get("associated_function_note"), "No associated function note recorded"),
            "evidence_note": _text(row.get("evidence_note"), "No motif evidence note recorded"),
        }
        for row in motif_rows
    ]


def _source_review_rows(profile: dict[str, Any], evidence_rows: list[dict[str, Any]], motif_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    source_labels = _unique(_source_label(row) for row in evidence_rows)
    motif_sources = _unique(row.get("motif_source") for row in motif_rows)
    curation_statuses = _unique(row.get("curation_status") for row in evidence_rows)
    review_notes = _unique(row.get("review_note") for row in evidence_rows)
    metadata_gaps = missing_metadata_count(profile, evidence_rows, motif_rows)
    return [
        {"metadata_group": "Catalog identity", "metadata_value": _text(profile.get("part_id"), "No profile id recorded")},
        {"metadata_group": "Source labels", "metadata_value": "; ".join(source_labels) if source_labels else catalog_presenter.NO_SOURCE_LABEL},
        {"metadata_group": "Motif sources", "metadata_value": "; ".join(motif_sources) if motif_sources else catalog_presenter.NO_SOURCE_LABEL},
        {"metadata_group": "Review status labels", "metadata_value": "; ".join(curation_statuses) if curation_statuses else catalog_presenter.NO_CURATION_STATUS_LABEL},
        {"metadata_group": "Review notes", "metadata_value": "; ".join(review_notes) if review_notes else "No review note recorded"},
        {"metadata_group": "Missing metadata count", "metadata_value": str(metadata_gaps)},
    ]


def missing_metadata_count(profile: dict[str, Any], evidence_rows: list[dict[str, Any]], motif_rows: list[dict[str, Any]]) -> int:
    count = 0
    for key in ("display_name", "plant_clade", "species_scientific_name", "promoter_type"):
        if not _text(profile.get(key)):
            count += 1
    if not evidence_rows:
        count += 1
    for row in evidence_rows:
        for key in ("tissue_context", "evidence_type", "source_database", "curation_status"):
            if not _text(row.get(key)):
                count += 1
    for row in motif_rows:
        if not _text(row.get("motif_source")):
            count += 1
    return count


def build_profile_detail_view_model(part_id: Any) -> dict[str, Any]:
    """Return deterministic profile detail, evidence, motif, and source-review rows."""
    clean_part_id = _text(part_id)
    profile = _get_profile(clean_part_id) if clean_part_id else {}
    if not profile:
        return {
            "status": "empty",
            "profile": {},
            "profile_summary": {},
            "evidence_rows": [],
            "motif_annotation_rows": [],
            "source_review_metadata_rows": [],
            "missing_metadata_count": 0,
            "message": "No Component Library promoter asset profile matched the selected catalog record.",
            "boundary_note": CATALOG_REFERENCE_BOUNDARY_NOTE,
            "limitation_note": CATALOG_REFERENCE_LIMITATION_NOTE,
        }

    use_seed = _text(profile.get("seed_source")) == "local curated sample records"
    evidence_rows = _list_evidence_rows(clean_part_id, use_seed=use_seed)
    motif_rows = _list_motif_rows(clean_part_id, use_seed=use_seed)
    return {
        "status": "available",
        "profile": dict(profile),
        "profile_summary": _profile_summary_row(profile, evidence_rows, motif_rows),
        "evidence_rows": _evidence_view_rows(profile, evidence_rows),
        "motif_annotation_rows": _motif_view_rows(profile, motif_rows),
        "source_review_metadata_rows": _source_review_rows(profile, evidence_rows, motif_rows),
        "missing_metadata_count": missing_metadata_count(profile, evidence_rows, motif_rows),
        "message": "",
        "boundary_note": CATALOG_REFERENCE_BOUNDARY_NOTE,
        "limitation_note": CATALOG_REFERENCE_LIMITATION_NOTE,
    }


def build_catalog_reference_options(
    *,
    plant_clade: str | None = None,
    species: str | None = None,
    tissue_context: str | None = None,
) -> list[dict[str, Any]]:
    """Return deterministic select options for project-level documentation references."""
    view_model = catalog_presenter.build_plant_promoter_catalog_view_model(
        plant_clade=plant_clade,
        species=species,
        tissue_context=tissue_context,
    )
    rows: list[dict[str, Any]] = []
    for row in view_model.get("profile_rows") or []:
        if not isinstance(row, dict):
            continue
        part_id = _text(row.get("part_id"))
        if not part_id:
            continue
        detail = build_profile_detail_view_model(part_id)
        summary = detail.get("profile_summary") if isinstance(detail.get("profile_summary"), dict) else {}
        rows.append(
            {
                "part_id": part_id,
                "select_label": f"{_text(summary.get('promoter_label'), part_id)} / {part_id}",
                "promoter_label": _text(summary.get("promoter_label"), part_id),
                "plant_clade": _text(summary.get("plant_clade"), catalog_presenter.NO_CLADE_LABEL),
                "species_label": _text(summary.get("species_label"), catalog_presenter.NO_SPECIES_LABEL),
                "tissue_context_count": int(summary.get("tissue_context_count") or 0),
                "evidence_row_count": int(summary.get("evidence_row_count") or 0),
                "motif_annotation_count": int(summary.get("motif_annotation_count") or 0),
                "missing_metadata_count": int(detail.get("missing_metadata_count") or 0),
            }
        )
    return sorted(rows, key=lambda item: (item["promoter_label"].casefold(), item["part_id"].casefold()))


def build_promoter_catalog_project_link(
    *,
    project_id: Any,
    part_id: Any,
    linkage_role: Any = "source_review_context",
    documentation_note: Any = DEFAULT_REFERENCE_NOTE,
    linked_at: Any = "session",
) -> dict[str, Any]:
    detail = build_profile_detail_view_model(part_id)
    if detail.get("status") != "available":
        raise ValueError("Component Library promoter asset profile is not available for documentation reference linking.")

    summary = detail["profile_summary"]
    evidence_rows = detail["evidence_rows"]
    motif_rows = detail["motif_annotation_rows"]
    source_rows = detail["source_review_metadata_rows"]
    source_values = {row["metadata_group"]: row["metadata_value"] for row in source_rows}
    tissue_contexts = _unique(row.get("tissue_context") for row in evidence_rows)
    curation_statuses = _unique(row.get("curation_status") for row in evidence_rows)
    asset_snapshot = build_catalog_asset_snapshot(
        detail["profile"],
        asset_type=PLANT_PROMOTER_PROFILE_ASSET_TYPE,
        evidence_rows=evidence_rows,
        motif_rows=motif_rows,
        fallback={
            "asset_id": summary["part_id"],
            "asset_label": summary["promoter_label"],
            "source_label": source_values.get("Source labels", catalog_presenter.NO_SOURCE_LABEL),
            "documentation_status": "; ".join(curation_statuses) if curation_statuses else catalog_presenter.NO_CURATION_STATUS_LABEL,
            "species": summary["species_label"],
            "clade": summary["plant_clade"],
            "limitation_note": CATALOG_REFERENCE_LIMITATION_NOTE,
        },
    )

    link = build_project_asset_link(
        project_id=project_id,
        asset_id=summary["part_id"],
        asset_display_name=summary["promoter_label"],
        asset_type=PLANT_PROMOTER_PROFILE_ASSET_TYPE,
        linkage_role=linkage_role,
        documentation_note=_text(documentation_note, DEFAULT_REFERENCE_NOTE),
        source_context_snapshot={
            "catalog": PLANT_PROMOTER_CATALOG_LABEL,
            "profile_id": summary["part_id"],
            "plant_clade": summary["plant_clade"],
            "species": summary["species_label"],
            "project_documentation_context": "Pathway Workspace linked catalog assets",
            "tissue_contexts": "; ".join(tissue_contexts) if tissue_contexts else catalog_presenter.NO_TISSUE_LABEL,
            "source_labels": source_values.get("Source labels", catalog_presenter.NO_SOURCE_LABEL),
            "motif_sources": source_values.get("Motif sources", catalog_presenter.NO_SOURCE_LABEL),
            "motif_rows": len(motif_rows),
        },
        review_status_snapshot={
            "curation_statuses": "; ".join(curation_statuses) if curation_statuses else catalog_presenter.NO_CURATION_STATUS_LABEL,
            "review_notes": source_values.get("Review notes", "No review note recorded"),
            "missing_metadata_count": detail.get("missing_metadata_count", 0),
        },
        asset_snapshot=asset_snapshot,
        linked_at=linked_at,
        human_review_required=True,
    )
    return link


def summarize_linked_plant_promoter_references(links: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = [
        row
        for row in list_project_asset_links(links)
        if _text(row.get("asset_type")) == PLANT_PROMOTER_PROFILE_ASSET_TYPE
    ]
    missing_metadata_count = 0
    source_statuses: Counter[str] = Counter()
    review_statuses: Counter[str] = Counter()
    references: list[dict[str, Any]] = []

    for row in rows:
        source_snapshot = row.get("source_context_snapshot") if isinstance(row.get("source_context_snapshot"), dict) else {}
        review_snapshot = row.get("review_status_snapshot") if isinstance(row.get("review_status_snapshot"), dict) else {}
        asset_snapshot = row.get("asset_snapshot") if isinstance(row.get("asset_snapshot"), dict) else {}
        has_snapshot = catalog_asset_snapshot_has_content(asset_snapshot)
        source_label = _text(
            asset_snapshot.get("source_label") or source_snapshot.get("source_labels"),
            catalog_presenter.NO_SOURCE_LABEL,
        )
        review_status = _text(
            asset_snapshot.get("documentation_status") or review_snapshot.get("curation_statuses"),
            catalog_presenter.NO_CURATION_STATUS_LABEL,
        )
        try:
            missing_metadata_count += int(review_snapshot.get("missing_metadata_count") or 0)
        except (TypeError, ValueError):
            missing_metadata_count += 1
        if "missing_metadata_count" in review_snapshot:
            pass
        elif not has_snapshot:
            missing_metadata_count += 1
        source_statuses[source_label] += 1
        review_statuses[review_status] += 1
        references.append(
            {
                "asset_id": _text(row.get("asset_id")),
                "asset_display_name": _text(
                    asset_snapshot.get("asset_label")
                    or row.get("asset_display_name")
                    or row.get("asset_label")
                    or row.get("asset_id")
                ),
                "linkage_role": _text(row.get("linkage_role")),
                "species": _text(asset_snapshot.get("species") or source_snapshot.get("species"), catalog_presenter.NO_SPECIES_LABEL),
                "plant_clade": _text(asset_snapshot.get("clade") or source_snapshot.get("plant_clade"), catalog_presenter.NO_CLADE_LABEL),
                "source_labels": source_label,
                "review_status": review_status,
                "missing_metadata_count": review_snapshot.get("missing_metadata_count", 0),
                "snapshot_status": "pinned documentation snapshot" if has_snapshot else "live metadata fallback",
                "limitation_note": _text(asset_snapshot.get("limitation_note"), CATALOG_REFERENCE_LIMITATION_NOTE),
            }
        )

    return {
        "linked_promoter_count": len(rows),
        "missing_metadata_count": missing_metadata_count,
        "source_status_summary": dict(sorted(source_statuses.items())),
        "review_status_summary": dict(sorted(review_statuses.items())),
        "references": references,
        "pinned_snapshot_count": sum(
            1
            for row in rows
            if catalog_asset_snapshot_has_content(row.get("asset_snapshot"))
        ),
        "missing_snapshot_count": sum(
            1
            for row in rows
            if not catalog_asset_snapshot_has_content(row.get("asset_snapshot"))
        ),
        "malformed_snapshot_warning_count": sum(
            1
            for row in rows
            if row.get("asset_snapshot_warning")
        ),
        "message": EMPTY_CATALOG_REFERENCE_MESSAGE if not rows else "",
        "boundary_note": CATALOG_REFERENCE_BOUNDARY_NOTE,
        "limitation_note": CATALOG_REFERENCE_LIMITATION_NOTE,
    }
