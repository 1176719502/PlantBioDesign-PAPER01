from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from services.evidence_query_builder import DESIGN_SLOT_ALIASES
from services.evidence_retrieval_provider import EVIDENCE_RETRIEVAL_BOUNDARY_NOTE


EVIDENCE_NORMALIZATION_BOUNDARY_NOTE = (
    "Local evidence normalization prepares source metadata for manual documentation review. "
    "It does not recommend components, generate designs, validate experiments, optimize routes, "
    "or judge wet-lab use state."
)

_DOI_RE = re.compile(r"\b10\.\d{4,9}/[^\s]+", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b(18\d{2}|19\d{2}|20\d{2})\b")

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "record_id": ("record_id", "id", "local_id", "evidence_id", "source_id"),
    "doi": ("doi", "DOI", "digital_object_identifier"),
    "pmid": ("pmid", "PMID", "pubmed_id", "pubmed"),
    "title": ("title", "paper_title", "article_title", "name"),
    "abstract": ("abstract", "summary", "evidence_summary", "notes", "note"),
    "year": ("year", "publication_year", "published_year", "date"),
    "source": ("source", "journal", "venue", "source_label", "publication"),
    "source_type": ("source_type", "source_category", "type"),
    "source_identifier": ("source_identifier", "identifier", "citation_id", "accession"),
    "source_url": ("source_url", "url", "link"),
    "provenance_note": ("provenance_note", "provenance", "local_note"),
    "authors": ("authors", "author", "creators", "creator"),
    "keywords": ("keywords", "keyword", "tags"),
    "design_slots": ("design_slots", "design_slot", "slots", "design_context"),
    "exact_phrases": ("exact_phrases", "exact_phrase", "phrases"),
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _field(record: Mapping[str, Any], canonical_key: str) -> Any:
    for alias in _FIELD_ALIASES[canonical_key]:
        if alias in record:
            return record.get(alias)
    return ""


def normalize_doi(value: Any) -> str:
    """Return a deterministic lower-case DOI value without resolver prefixes."""
    clean = _text(value)
    if not clean:
        return ""
    clean = re.sub(r"^(doi:\s*|https?://(dx\.)?doi\.org/)", "", clean, flags=re.IGNORECASE)
    match = _DOI_RE.search(clean)
    doi = match.group(0) if match else clean
    return doi.strip().rstrip(".,;)").casefold()


def normalize_pmid(value: Any) -> str:
    clean = _text(value)
    if not clean:
        return ""
    clean = re.sub(r"^pmid:\s*", "", clean, flags=re.IGNORECASE)
    digits = re.sub(r"\D+", "", clean)
    return digits


def normalize_year(value: Any) -> int | None:
    if isinstance(value, int):
        year = value
    else:
        match = _YEAR_RE.search(_text(value))
        if not match:
            return None
        year = int(match.group(1))
    if 1800 <= year <= 2027:
        return year
    return None


def _split_values(value: Any, *, lower: bool = False) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        raw_values = [_text(item) for item in value]
    else:
        raw_values = re.split(r"[;\n|,]+", _text(value))

    seen: set[str] = set()
    values: list[str] = []
    for raw in raw_values:
        clean = _text(raw)
        if lower:
            clean = clean.casefold()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            values.append(clean)
    return values


def _slot_key(value: Any) -> str:
    clean = _text(value).casefold().replace("/", "_").replace("-", "_").replace(" ", "_")
    clean = re.sub(r"_+", "_", clean).strip("_")
    return DESIGN_SLOT_ALIASES.get(clean, clean)


def _normalize_design_slots(record: Mapping[str, Any]) -> tuple[list[str], dict[str, str]]:
    raw_slots = _field(record, "design_slots")
    slot_values: dict[str, str] = {}
    slots: list[str] = []

    if isinstance(raw_slots, Mapping):
        for raw_key, raw_value in raw_slots.items():
            slot_key = _slot_key(raw_key)
            slot_value = _text(raw_value)
            if slot_key:
                slots.append(slot_key)
                if slot_value:
                    slot_values[slot_key] = slot_value
    else:
        slots.extend(_slot_key(value) for value in _split_values(raw_slots, lower=True))

    for raw_key, raw_value in record.items():
        slot_key = _slot_key(raw_key)
        if slot_key in DESIGN_SLOT_ALIASES.values() and _text(raw_value):
            slots.append(slot_key)
            slot_values.setdefault(slot_key, _text(raw_value))

    seen: set[str] = set()
    unique_slots: list[str] = []
    for slot in slots:
        if slot and slot not in seen:
            seen.add(slot)
            unique_slots.append(slot)
    return unique_slots, slot_values


def _source_identifier(doi: str, pmid: str, explicit_identifier: Any) -> str:
    explicit = _text(explicit_identifier)
    if explicit:
        return explicit
    if doi:
        return f"DOI:{doi}"
    if pmid:
        return f"PMID:{pmid}"
    return ""


def _completeness(record: Mapping[str, Any]) -> dict[str, Any]:
    has_title = bool(_text(record.get("title")))
    has_abstract = bool(_text(record.get("abstract")))
    has_year = record.get("year") is not None
    source_label = _text(record.get("source_label"))
    source_type = _text(record.get("source_type"))
    has_source = bool(
        _text(record.get("source"))
        or _text(record.get("source_identifier"))
        or (source_label and source_label != "Local evidence metadata")
        or (source_type and source_type != "local evidence metadata")
    )
    has_doi_or_pmid = bool(_text(record.get("doi")) or _text(record.get("pmid")))
    flags = {
        "has_title": has_title,
        "has_abstract": has_abstract,
        "has_year": has_year,
        "has_source": has_source,
        "has_doi_or_pmid": has_doi_or_pmid,
    }
    score = round(sum(1 for present in flags.values() if present) / len(flags), 3)
    return {**flags, "completeness_score": score}


def _manual_review_reasons(record: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    completeness = _completeness(record)
    if not completeness["has_title"]:
        reasons.append("missing_title")
    if not completeness["has_abstract"]:
        reasons.append("missing_abstract")
    if not completeness["has_year"]:
        reasons.append("missing_year")
    if not completeness["has_source"]:
        reasons.append("missing_source")
    if not completeness["has_doi_or_pmid"]:
        reasons.append("missing_doi_or_pmid")
    if _text(record.get("doi")) and _text(record.get("pmid")):
        reasons.append("multiple_source_identifiers")
    return reasons


def normalize_evidence_record(raw_record: Mapping[str, Any] | str, *, input_index: int = 1) -> dict[str, Any]:
    """Normalize one local evidence metadata record into the R64 ranker-compatible shape."""
    if isinstance(raw_record, Mapping):
        raw_fields: dict[str, Any] = dict(raw_record)
        raw_input: Any = dict(raw_record)
    else:
        raw_fields = {"note_text": _text(raw_record)}
        raw_input = _text(raw_record)

    doi = normalize_doi(_field(raw_fields, "doi"))
    pmid = normalize_pmid(_field(raw_fields, "pmid"))
    year = normalize_year(_field(raw_fields, "year"))
    title = _text(_field(raw_fields, "title"))
    abstract = _text(_field(raw_fields, "abstract"))
    source_label = _text(_field(raw_fields, "source"))
    source_type = _text(_field(raw_fields, "source_type")) or "local evidence metadata"
    source_identifier = _source_identifier(doi, pmid, _field(raw_fields, "source_identifier"))
    design_slots, design_slot_values = _normalize_design_slots(raw_fields)
    record_id = _text(_field(raw_fields, "record_id")) or source_identifier or f"local-evidence-{input_index:03d}"

    normalized: dict[str, Any] = {
        "record_id": record_id,
        "title": title,
        "abstract": abstract,
        "doi": doi,
        "pmid": pmid,
        "year": year,
        "publication_year": year,
        "source": source_label,
        "source_type": source_type,
        "source_identifier": source_identifier,
        "source_label": source_label or source_identifier or "Local evidence metadata",
        "source_url": _text(_field(raw_fields, "source_url")),
        "provenance_note": _text(_field(raw_fields, "provenance_note")) or "Normalized from local input.",
        "authors": _split_values(_field(raw_fields, "authors")),
        "keywords": _split_values(_field(raw_fields, "keywords"), lower=True),
        "design_slots": design_slots,
        "design_slot_values": design_slot_values,
        "exact_phrases": _split_values(_field(raw_fields, "exact_phrases")),
        "raw_input": raw_input,
        "raw_fields": raw_fields,
        "boundary_note": EVIDENCE_NORMALIZATION_BOUNDARY_NOTE,
        "retrieval_boundary_note": EVIDENCE_RETRIEVAL_BOUNDARY_NOTE,
    }
    normalized.update(_completeness(normalized))
    reasons = _manual_review_reasons(normalized)
    normalized["manual_review_required"] = True
    normalized["manual_review_reasons"] = reasons
    normalized["manual_review_flags"] = ["manual_review_required", *reasons]
    return normalized


def normalize_evidence_records(records: Sequence[Mapping[str, Any] | str] | None) -> list[dict[str, Any]]:
    return [
        normalize_evidence_record(record, input_index=index)
        for index, record in enumerate(records or [], start=1)
        if isinstance(record, (Mapping, str))
    ]
