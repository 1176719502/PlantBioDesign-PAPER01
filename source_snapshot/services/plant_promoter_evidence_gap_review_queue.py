from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from services import plant_promoter_catalog_presenter as presenter


CATEGORY_ORDER = [
    "source_provenance_gap",
    "tissue_context_gap",
    "species_or_clade_context_gap",
    "review_status_gap",
    "metadata_gap",
    "documentation_follow_up",
]

BOUNDARY_NOTES = [
    "Supports documentation review and human curation only.",
    "Does not recommend, rank, validate, optimize, or confirm promoter suitability.",
    "Queue rows keep evidence and provenance gaps visible without making biological forecasts or wet-lab readiness judgments.",
]


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _row_list(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    return [row for row in raw if isinstance(row, dict)]


def _is_missing_label(value: str, missing_labels: set[str]) -> bool:
    clean = _text(value)
    return not clean or clean in missing_labels


def _queue_item(
    *,
    part_id: str,
    promoter_label: str,
    category: str,
    issue: str,
    human_follow_up: str,
    source_context: str,
) -> dict[str, str]:
    stable_part = part_id or promoter_label.lower().replace(" ", "-")
    return {
        "queue_item_id": f"{stable_part}::{category}",
        "promoter_label": promoter_label or "Unknown promoter record",
        "category": category,
        "issue": issue,
        "human_follow_up": human_follow_up,
        "source_context": source_context or "No source context recorded",
        "documentation_boundary": BOUNDARY_NOTES[1],
    }


def build_plant_promoter_evidence_gap_review_queue(
    data: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a deterministic read-only review queue for promoter evidence gaps."""
    if isinstance(data, dict):
        profile_rows = _row_list(data.get("profile_rows"))
        evidence_rows = _row_list(data.get("evidence_rows"))
        review_rows = _row_list(data.get("rows_needing_review"))
        context_rows = _row_list(data.get("context_readback_rows"))
    else:
        profile_rows = _row_list(data)
        evidence_rows = []
        review_rows = []
        context_rows = []

    evidence_by_part: dict[str, list[dict[str, Any]]] = defaultdict(list)
    review_by_part: dict[str, list[dict[str, Any]]] = defaultdict(list)
    context_by_label: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in evidence_rows:
        evidence_by_part[_text(row.get("part_id"))].append(row)
    for row in review_rows:
        review_by_part[_text(row.get("part_id"))].append(row)
    for row in context_rows:
        context_by_label[_text(row.get("promoter_label")) or _text(row.get("catalog_context"))].append(row)

    queue_items: list[dict[str, str]] = []
    category_counts: Counter[str] = Counter()
    missing_species_labels = {presenter.NO_SPECIES_LABEL}
    missing_clade_labels = {presenter.NO_CLADE_LABEL, presenter.OTHER_CLADE_LABEL}
    missing_tissue_labels = {presenter.NO_TISSUE_LABEL}
    missing_source_labels = {presenter.NO_SOURCE_LABEL}
    missing_review_labels = {presenter.NO_CURATION_STATUS_LABEL}

    for profile in sorted(
        profile_rows,
        key=lambda row: (
            _text(row.get("display_name"), _text(row.get("part_id"))).casefold(),
            _text(row.get("part_id")).casefold(),
        ),
    ):
        part_id = _text(profile.get("part_id"))
        promoter_label = _text(profile.get("display_name"), part_id or "Unknown promoter record")
        species_label = _text(profile.get("species_label"), presenter.NO_SPECIES_LABEL)
        clade_label = _text(profile.get("plant_clade"), presenter.NO_CLADE_LABEL)
        source_context = "No source context recorded"
        rows = evidence_by_part.get(part_id, [])
        if rows:
            first_source = _text(rows[0].get("source_database"), presenter.NO_SOURCE_LABEL)
            source_context = first_source

        categories_for_profile: list[dict[str, str]] = []

        if not rows or all(_is_missing_label(_text(row.get("source_database")), missing_source_labels) for row in rows):
            categories_for_profile.append(
                _queue_item(
                    part_id=part_id,
                    promoter_label=promoter_label,
                    category="source_provenance_gap",
                    issue="Source/provenance gap remains visible for this promoter record.",
                    human_follow_up="Add or confirm source database or accession context for documentation review.",
                    source_context=source_context,
                )
            )

        if not rows or all(_is_missing_label(_text(row.get("tissue_context")), missing_tissue_labels) for row in rows):
            categories_for_profile.append(
                _queue_item(
                    part_id=part_id,
                    promoter_label=promoter_label,
                    category="tissue_context_gap",
                    issue="Tissue context needs review because no tissue evidence context is recorded.",
                    human_follow_up="Capture tissue context from documentation sources before citing this record.",
                    source_context=source_context,
                )
            )

        if _is_missing_label(species_label, missing_species_labels) or _is_missing_label(clade_label, missing_clade_labels):
            categories_for_profile.append(
                _queue_item(
                    part_id=part_id,
                    promoter_label=promoter_label,
                    category="species_or_clade_context_gap",
                    issue="Species/clade context needs review for this promoter record.",
                    human_follow_up="Add species or clade documentation context so the catalog record remains traceable.",
                    source_context=source_context,
                )
            )

        if not rows or all(_is_missing_label(_text(row.get("curation_status")), missing_review_labels) for row in rows):
            categories_for_profile.append(
                _queue_item(
                    part_id=part_id,
                    promoter_label=promoter_label,
                    category="review_status_gap",
                    issue="Review status gap remains visible because curation status is not recorded.",
                    human_follow_up="Record a human curation status before using this row in project documentation.",
                    source_context=source_context,
                )
            )

        metadata_gaps: list[str] = []
        if not _text(profile.get("promoter_type")):
            metadata_gaps.append("promoter type")
        if not _text(profile.get("sequence_availability")):
            metadata_gaps.append("sequence availability note")
        if rows and all(not _text(row.get("review_note")) for row in rows):
            metadata_gaps.append("review note")
        if metadata_gaps:
            categories_for_profile.append(
                _queue_item(
                    part_id=part_id,
                    promoter_label=promoter_label,
                    category="metadata_gap",
                    issue="Metadata gap remains visible for: " + ", ".join(metadata_gaps) + ".",
                    human_follow_up="Complete the recorded metadata fields for documentation review clarity.",
                    source_context=source_context,
                )
            )

        follow_up_rows = review_by_part.get(part_id, [])
        if follow_up_rows or any(
            (
                "metadata gap" in _text(row.get("metadata_gap")).lower()
                and "no metadata gap recorded" not in _text(row.get("metadata_gap")).lower()
            )
            for row in context_by_label.get(promoter_label, [])
        ):
            categories_for_profile.append(
                _queue_item(
                    part_id=part_id,
                    promoter_label=promoter_label,
                    category="documentation_follow_up",
                    issue="Documentation follow-up remains open for source or metadata review.",
                    human_follow_up="Use the queue as a human curation checklist only; do not treat it as promoter validation.",
                    source_context=source_context,
                )
            )

        seen_categories: set[str] = set()
        for item in categories_for_profile:
            if item["category"] in seen_categories:
                continue
            seen_categories.add(item["category"])
            queue_items.append(item)
            category_counts[item["category"]] += 1

    queue_items.sort(
        key=lambda row: (
            CATEGORY_ORDER.index(row["category"]) if row["category"] in CATEGORY_ORDER else len(CATEGORY_ORDER),
            row["promoter_label"].casefold(),
            row["queue_item_id"].casefold(),
        )
    )

    ordered_category_counts = {
        category: int(category_counts.get(category, 0))
        for category in CATEGORY_ORDER
    }

    return {
        "summary_counts": {
            "profile_count": len(profile_rows),
            "queue_item_count": len(queue_items),
            "category_count": sum(1 for count in ordered_category_counts.values() if count > 0),
        },
        "queue_item_rows": queue_items,
        "category_counts": ordered_category_counts,
        "boundary_notes": BOUNDARY_NOTES[:],
    }
