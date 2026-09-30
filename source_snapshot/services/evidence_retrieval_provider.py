from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol, TypedDict


EVIDENCE_RETRIEVAL_BOUNDARY_NOTE = (
    "Evidence retrieval returns source-linked candidates for manual documentation review. "
    "It does not choose components, generate designs, produce protocols, create sequences, "
    "claim experimental validation, or judge wet-lab use state."
)


class EvidenceQuery(TypedDict, total=False):
    query_id: str
    slot_key: str
    slot_label: str
    phrase: str
    keywords: list[str]
    query_text: str
    exact_phrases: list[str]
    manual_review_status: str
    boundary_note: str


class EvidenceQueryBundle(TypedDict, total=False):
    queries: list[EvidenceQuery]
    slot_keys: list[str]
    slot_values: dict[str, str]
    exact_phrases: list[str]
    keywords: list[str]
    manual_review_status: str
    boundary_note: str
    empty_state: str


class EvidenceRecord(TypedDict, total=False):
    record_id: str
    title: str
    abstract: str
    source_type: str
    source_identifier: str
    source_label: str
    source_url: str
    provenance_note: str
    publication_year: int
    year: int
    keywords: list[str]
    design_slots: list[str]
    exact_phrases: list[str]
    manual_review_flags: list[str]


class EvidenceRetrievalProvider(Protocol):
    """Protocol for deterministic or external evidence metadata providers."""

    def retrieve(self, query_bundle: EvidenceQueryBundle) -> list[EvidenceRecord]:
        """Return evidence metadata records for the query bundle."""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _token_key(value: Any) -> str:
    return _text(value).casefold()


def _sequence_texts(value: Any) -> list[str]:
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
        parts.extend(_sequence_texts(record.get(key)))
    return " ".join(parts).casefold()


def _query_matches_record(query: EvidenceQuery, record: Mapping[str, Any]) -> bool:
    blob = _record_blob(record)
    keyword_hits = [
        keyword
        for keyword in query.get("keywords") or []
        if _token_key(keyword) and _token_key(keyword) in blob
    ]
    phrase_hits = [
        phrase
        for phrase in query.get("exact_phrases") or []
        if _token_key(phrase) and _token_key(phrase) in blob
    ]
    slot_key = _token_key(query.get("slot_key"))
    design_slots = {_token_key(slot) for slot in _sequence_texts(record.get("design_slots"))}
    return bool(keyword_hits or phrase_hits or (slot_key and slot_key in design_slots))


def _record_sort_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    return (
        _token_key(record.get("record_id")),
        _token_key(record.get("title")),
        _token_key(record.get("source_identifier")),
    )


class FakeEvidenceRetrievalProvider:
    """Deterministic fake provider for tests and offline wiring."""

    def __init__(self, records: Sequence[Mapping[str, Any]] | None = None) -> None:
        self._records = [dict(record) for record in records or [] if isinstance(record, Mapping)]

    def retrieve(self, query_bundle: EvidenceQueryBundle) -> list[EvidenceRecord]:
        queries = query_bundle.get("queries") or []
        if not queries:
            return []

        matched: dict[str, EvidenceRecord] = {}
        for record in self._records:
            if not any(_query_matches_record(query, record) for query in queries):
                continue
            record_id = _text(record.get("record_id")) or _text(record.get("source_identifier"))
            if not record_id:
                record_id = f"fake-evidence-{len(matched) + 1:03d}"
            normalized = dict(record)
            normalized["record_id"] = record_id
            normalized.setdefault("manual_review_flags", ["manual_review_required"])
            matched[record_id] = normalized

        return sorted(matched.values(), key=_record_sort_key)
