from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


CURATION_BOUNDARY = (
    "Plant evidence case curation creates documentation-only case drafts from manually annotated "
    "evidence metadata. It does not invent missing biological fields, recommend components, "
    "validate experiments, optimize routes, or judge wet-lab readiness."
)
CASE_ALLOWED_CLASSIFICATIONS = {"direct", "adjacent"}
CORE_CASE_FIELDS = (
    "source_id",
    "title",
    "year",
    "doi",
    "plant_species",
    "target_trait_or_product",
    "pathway",
    "gene",
    "enzyme",
    "promoter",
    "cds",
    "vector",
    "tissue_context",
    "evidence_summary",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _lower(value: Any) -> str:
    return _text(value).casefold()


def _as_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_text(item) for item in value if _text(item)]
    return []


def _missing_fields(record: Mapping[str, Any]) -> list[str]:
    explicit_missing = _as_list(record.get("missing_fields"))
    missing = list(explicit_missing)
    for field in CORE_CASE_FIELDS:
        if not _text(record.get(field)) and field not in missing:
            missing.append(field)
    return missing


def classify_plant_evidence_candidate(record: Mapping[str, Any]) -> str:
    """Classify manually annotated evidence as direct, adjacent, or irrelevant."""
    explicit = _lower(record.get("evidence_classification") or record.get("classification"))
    if explicit in {"direct", "adjacent", "irrelevant"}:
        return explicit

    relevance = _lower(record.get("relevance"))
    plant_species = _lower(record.get("plant_species"))
    goal_species = _lower(record.get("goal_plant_species") or record.get("goal_context"))
    trait = _lower(record.get("target_trait_or_product") or record.get("target_trait"))
    goal_trait = _lower(record.get("goal_target") or record.get("goal_trait"))

    if "irrelevant" in relevance or "not relevant" in relevance:
        return "irrelevant"
    if plant_species and goal_species and plant_species == goal_species and trait and goal_trait and trait == goal_trait:
        return "direct"
    if "plant" in relevance or plant_species or record.get("adjacent_reason"):
        return "adjacent"
    return "irrelevant"


def _source_reference(record: Mapping[str, Any]) -> dict[str, str]:
    return {
        "source_id": _text(record.get("source_id")),
        "doi": _text(record.get("doi")),
        "title": _text(record.get("title")),
        "year": _text(record.get("year")),
    }


def _case_draft(record: Mapping[str, Any], classification: str, missing: Sequence[str], index: int) -> dict[str, Any]:
    source_reference = _source_reference(record)
    stable_id = _text(record.get("case_id")) or _text(record.get("source_id")) or f"case-draft-{index:03d}"
    return {
        "case_id": stable_id,
        "classification": classification,
        "case_draft_allowed": classification in CASE_ALLOWED_CLASSIFICATIONS,
        "source_reference": source_reference,
        "plant_context": {
            "plant_species": _text(record.get("plant_species")),
            "tissue_context": _text(record.get("tissue_context")),
        },
        "target_context": {
            "target_trait_or_product": _text(record.get("target_trait_or_product")),
            "pathway": _text(record.get("pathway")),
        },
        "component_context": {
            "gene": _text(record.get("gene")),
            "enzyme": _text(record.get("enzyme")),
            "promoter": _text(record.get("promoter")),
            "cds": _text(record.get("cds")),
            "vector": _text(record.get("vector")),
        },
        "evidence_summary": _text(record.get("evidence_summary")),
        "missing_fields": list(missing),
        "manual_review_required": True,
        "documentation_boundary": CURATION_BOUNDARY,
    }


def curate_plant_evidence_case_candidates(
    evidence_candidates: Sequence[Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Create case drafts only from direct or adjacent manually annotated evidence metadata."""
    records = [dict(record) for record in evidence_candidates or [] if isinstance(record, Mapping)]
    case_drafts: list[dict[str, Any]] = []
    skipped_records: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        classification = classify_plant_evidence_candidate(record)
        missing = _missing_fields(record)
        source_reference = _source_reference(record)
        if classification in CASE_ALLOWED_CLASSIFICATIONS:
            case_drafts.append(_case_draft(record, classification, missing, index))
        else:
            skipped_records.append(
                {
                    "source_reference": source_reference,
                    "classification": classification,
                    "case_draft_allowed": False,
                    "reason": "Evidence candidate is not direct or adjacent plant evidence.",
                    "missing_fields": missing,
                    "manual_review_required": True,
                }
            )

    classification_counts = {
        "direct": 0,
        "adjacent": 0,
        "irrelevant": 0,
    }
    for draft in case_drafts:
        classification_counts[draft["classification"]] += 1
    for skipped in skipped_records:
        classification_counts[skipped["classification"]] = classification_counts.get(skipped["classification"], 0) + 1

    return {
        "case_drafts": case_drafts,
        "skipped_records": skipped_records,
        "summary": {
            "input_count": len(records),
            "case_draft_count": len(case_drafts),
            "skipped_count": len(skipped_records),
            "classification_counts": classification_counts,
            "manual_review_required": True,
        },
        "documentation_boundary": CURATION_BOUNDARY,
    }
