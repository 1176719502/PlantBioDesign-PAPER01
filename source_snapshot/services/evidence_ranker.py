from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

from services.evidence_retrieval_provider import (
    EVIDENCE_RETRIEVAL_BOUNDARY_NOTE,
    EvidenceQueryBundle,
    EvidenceRecord,
)


RECENCY_REFERENCE_YEAR = 2026
RANKING_BOUNDARY_NOTE = (
    "Evidence ranking is retrieval triage for manual review. Scores describe metadata and "
    "text alignment to the query context; they do not choose components, validate biology, "
    "predict outcomes, or judge wet-lab use state."
)


class RankedEvidenceCandidate(TypedDict, total=False):
    rank: int
    record_id: str
    title: str
    retrieval_review_score: float
    score_breakdown: dict[str, float]
    matched_keywords: list[str]
    matched_exact_phrases: list[str]
    covered_design_slots: list[str]
    missing_metadata: list[str]
    manual_review_flags: list[str]
    manual_review_status: str
    claim_demoted: bool
    source: dict[str, Any]
    boundary_note: str


_METADATA_FIELDS = (
    "title",
    "source_type",
    "source_identifier",
    "source_label",
    "source_url",
    "provenance_note",
)

_DEMOTION_TERMS = (
    "valid" + "ated",
    "experiment" + "-ready",
    "wet-lab " + "ready",
    "ready " + "for wet lab",
    "production" + "-ready",
    "optim" + "ized",
    "yield " + "pre" + "diction",
    "approved",
    "proven",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return _text(value).casefold()


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_text(item) for item in value if _text(item)]
    return []


def _record_blob(record: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        "record_id",
        "title",
        "abstract",
        "source_type",
        "source_identifier",
        "source_label",
        "source_url",
        "provenance_note",
    ):
        text = _text(record.get(key))
        if text:
            parts.append(text)
    for key in ("keywords", "design_slots", "exact_phrases", "manual_review_flags"):
        parts.extend(_list_texts(record.get(key)))
    return " ".join(parts).casefold()


def _query_keywords(query_bundle: Mapping[str, Any]) -> list[str]:
    keywords: list[str] = []
    for query in query_bundle.get("queries") or []:
        if isinstance(query, Mapping):
            keywords.extend(_list_texts(query.get("keywords")))
    keywords.extend(_list_texts(query_bundle.get("keywords")))
    return _unique_lower(keywords)


def _query_exact_phrases(query_bundle: Mapping[str, Any]) -> list[str]:
    phrases: list[str] = []
    for query in query_bundle.get("queries") or []:
        if isinstance(query, Mapping):
            phrases.extend(_list_texts(query.get("exact_phrases")))
    phrases.extend(_list_texts(query_bundle.get("exact_phrases")))
    return _unique_texts(phrases)


def _query_slot_keys(query_bundle: Mapping[str, Any]) -> list[str]:
    slot_keys: list[str] = []
    for query in query_bundle.get("queries") or []:
        if isinstance(query, Mapping):
            slot_keys.append(_text(query.get("slot_key")))
    slot_keys.extend(_list_texts(query_bundle.get("slot_keys")))
    return _unique_lower(slot_keys)


def _query_slot_values(query_bundle: Mapping[str, Any]) -> dict[str, str]:
    slot_values = query_bundle.get("slot_values")
    if isinstance(slot_values, Mapping):
        return {_key(key): _text(value) for key, value in slot_values.items() if _text(value)}
    values: dict[str, str] = {}
    for query in query_bundle.get("queries") or []:
        if isinstance(query, Mapping):
            slot_key = _key(query.get("slot_key"))
            phrase = _text(query.get("phrase"))
            if slot_key and phrase:
                values[slot_key] = phrase
    return values


def _unique_texts(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            unique_values.append(clean)
    return unique_values


def _unique_lower(values: Sequence[str]) -> list[str]:
    return [value.casefold() for value in _unique_texts(values)]


def _matched_keywords(record: Mapping[str, Any], query_bundle: Mapping[str, Any]) -> list[str]:
    blob = _record_blob(record)
    record_keywords = {_key(keyword) for keyword in _list_texts(record.get("keywords"))}
    matched = [
        keyword
        for keyword in _query_keywords(query_bundle)
        if keyword and (keyword in blob or keyword in record_keywords)
    ]
    return _unique_lower(matched)


def _matched_exact_phrases(record: Mapping[str, Any], query_bundle: Mapping[str, Any]) -> list[str]:
    blob = _record_blob(record)
    return _unique_texts(
        [phrase for phrase in _query_exact_phrases(query_bundle) if _key(phrase) in blob]
    )


def _covered_design_slots(record: Mapping[str, Any], query_bundle: Mapping[str, Any]) -> list[str]:
    blob = _record_blob(record)
    record_slots = {_key(slot) for slot in _list_texts(record.get("design_slots"))}
    slot_values = _query_slot_values(query_bundle)
    covered: list[str] = []
    for slot_key in _query_slot_keys(query_bundle):
        slot_value = _key(slot_values.get(slot_key))
        if slot_key in record_slots or (slot_value and slot_value in blob):
            covered.append(slot_key)
    return _unique_lower(covered)


def _source_completeness(record: Mapping[str, Any]) -> tuple[float, list[str]]:
    missing = [field for field in _METADATA_FIELDS if not _text(record.get(field))]
    present_count = len(_METADATA_FIELDS) - len(missing)
    return present_count / len(_METADATA_FIELDS), missing


def _publication_year(record: Mapping[str, Any]) -> int | None:
    value = record.get("publication_year", record.get("year"))
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    if year < 1800 or year > RECENCY_REFERENCE_YEAR + 1:
        return None
    return year


def _recency_points(record: Mapping[str, Any]) -> float:
    year = _publication_year(record)
    if year is None:
        return 0.0
    age = max(0, RECENCY_REFERENCE_YEAR - year)
    if age <= 2:
        return 3.0
    if age <= 5:
        return 2.0
    if age <= 10:
        return 1.0
    return 0.5


def _manual_review_flags(record: Mapping[str, Any]) -> list[str]:
    flags = _unique_lower(_list_texts(record.get("manual_review_flags")))
    return flags or ["manual_review_required"]


def _claim_demoted(record: Mapping[str, Any]) -> bool:
    blob = _record_blob(record)
    flags = " ".join(_manual_review_flags(record))
    return any(term in blob or term in flags for term in _DEMOTION_TERMS)


def _candidate_score(
    record: Mapping[str, Any],
    query_bundle: Mapping[str, Any],
) -> tuple[float, dict[str, float], list[str], list[str], list[str], list[str], bool]:
    matched_keywords = _matched_keywords(record, query_bundle)
    exact_phrases = _matched_exact_phrases(record, query_bundle)
    covered_slots = _covered_design_slots(record, query_bundle)
    completeness, missing_metadata = _source_completeness(record)
    claim_demoted = _claim_demoted(record)

    keyword_points = min(len(matched_keywords) * 2.0, 12.0)
    slot_points = len(covered_slots) * 4.0
    source_points = completeness * 6.0
    recency_points = _recency_points(record)
    exact_phrase_points = min(len(exact_phrases) * 5.0, 15.0)
    manual_review_penalty = -8.0 if claim_demoted else 0.0
    score = (
        keyword_points
        + slot_points
        + source_points
        + recency_points
        + exact_phrase_points
        + manual_review_penalty
    )
    score = max(0.0, round(score, 3))
    return (
        score,
        {
            "keyword_match": keyword_points,
            "design_slot_coverage": slot_points,
            "source_provenance_completeness": round(source_points, 3),
            "publication_recency": recency_points,
            "exact_phrase_match": exact_phrase_points,
            "manual_review_safety": manual_review_penalty,
        },
        matched_keywords,
        exact_phrases,
        covered_slots,
        missing_metadata,
        claim_demoted,
    )


def _source_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "source_type": _text(record.get("source_type")),
        "source_identifier": _text(record.get("source_identifier")),
        "source_label": _text(record.get("source_label")),
        "source_url": _text(record.get("source_url")),
        "provenance_note": _text(record.get("provenance_note")),
        "publication_year": _publication_year(record),
    }


def rank_evidence_records(
    records: Sequence[Mapping[str, Any]] | None,
    query_bundle: EvidenceQueryBundle | Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Return deterministic evidence retrieval candidates for manual review."""
    if not records or not query_bundle:
        return {
            "candidates": [],
            "summary": {
                "candidate_count": 0,
                "manual_review_required": True,
                "claim_demoted_count": 0,
                "missing_metadata_count": 0,
            },
            "manual_review_status": "manual_review_required",
            "boundary_note": RANKING_BOUNDARY_NOTE,
            "retrieval_boundary_note": EVIDENCE_RETRIEVAL_BOUNDARY_NOTE,
            "empty_state": "No evidence records or query context were available for retrieval review.",
        }

    candidate_rows: list[RankedEvidenceCandidate] = []
    for input_index, record in enumerate(records):
        if not isinstance(record, Mapping):
            continue
        (
            score,
            breakdown,
            matched_keywords,
            exact_phrases,
            covered_slots,
            missing_metadata,
            claim_demoted,
        ) = _candidate_score(record, query_bundle)
        row: RankedEvidenceCandidate = {
            "rank": 0,
            "record_id": _text(record.get("record_id")) or f"evidence-record-{input_index + 1:03d}",
            "title": _text(record.get("title")) or "Untitled evidence record",
            "retrieval_review_score": score,
            "score_breakdown": breakdown,
            "matched_keywords": matched_keywords,
            "matched_exact_phrases": exact_phrases,
            "covered_design_slots": covered_slots,
            "missing_metadata": missing_metadata,
            "manual_review_flags": _manual_review_flags(record),
            "manual_review_status": "manual_review_required",
            "claim_demoted": claim_demoted,
            "source": _source_payload(record),
            "boundary_note": RANKING_BOUNDARY_NOTE,
            "_input_index": input_index,
        }
        candidate_rows.append(row)

    candidate_rows.sort(
        key=lambda row: (
            -float(row["retrieval_review_score"]),
            int(row["_input_index"]),
            _key(row["record_id"]),
        )
    )
    for rank_index, row in enumerate(candidate_rows, start=1):
        row["rank"] = rank_index
        row.pop("_input_index", None)

    missing_metadata_count = sum(1 for row in candidate_rows if row["missing_metadata"])
    claim_demoted_count = sum(1 for row in candidate_rows if row["claim_demoted"])
    return {
        "candidates": candidate_rows,
        "summary": {
            "candidate_count": len(candidate_rows),
            "manual_review_required": True,
            "claim_demoted_count": claim_demoted_count,
            "missing_metadata_count": missing_metadata_count,
        },
        "manual_review_status": "manual_review_required",
        "boundary_note": RANKING_BOUNDARY_NOTE,
        "retrieval_boundary_note": EVIDENCE_RETRIEVAL_BOUNDARY_NOTE,
        "empty_state": "",
    }


def retrieve_and_rank_evidence(
    provider: Any,
    query_bundle: EvidenceQueryBundle,
) -> dict[str, Any]:
    records: list[EvidenceRecord] = provider.retrieve(query_bundle)
    return rank_evidence_records(records, query_bundle)
