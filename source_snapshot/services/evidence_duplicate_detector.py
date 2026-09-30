from __future__ import annotations

import difflib
import re
from collections.abc import Mapping, Sequence
from typing import Any

from services.evidence_record_normalizer import normalize_doi, normalize_pmid


_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalized_title_key(value: Any) -> str:
    tokens = re.findall(r"[a-z0-9]+", _text(value).casefold())
    useful_tokens = [token for token in tokens if token not in _STOPWORDS]
    return " ".join(useful_tokens)


def _record_key(record: Mapping[str, Any], index: int) -> str:
    return _text(record.get("record_id")) or f"input-{index:03d}"


def _add_group(
    groups: list[dict[str, Any]],
    *,
    reason: str,
    record_indices: Sequence[int],
    records: Sequence[Mapping[str, Any]],
    similarity: float | None = None,
) -> None:
    unique_indices = sorted(set(record_indices))
    if len(unique_indices) < 2:
        return
    group: dict[str, Any] = {
        "reason": reason,
        "record_indices": unique_indices,
        "record_ids": [_record_key(records[index], index + 1) for index in unique_indices],
    }
    if similarity is not None:
        group["similarity"] = round(similarity, 3)
    groups.append(group)


def detect_evidence_duplicates(
    records: Sequence[Mapping[str, Any]] | None,
    *,
    title_similarity_threshold: float = 0.92,
) -> dict[str, Any]:
    """Detect duplicate local evidence metadata records using deterministic metadata keys."""
    normalized_records = [dict(record) for record in records or [] if isinstance(record, Mapping)]
    groups: list[dict[str, Any]] = []
    doi_to_indices: dict[str, list[int]] = {}
    pmid_to_indices: dict[str, list[int]] = {}
    title_to_indices: dict[str, list[int]] = {}

    for index, record in enumerate(normalized_records):
        doi = normalize_doi(record.get("doi"))
        pmid = normalize_pmid(record.get("pmid"))
        title_key = normalized_title_key(record.get("title"))
        if doi:
            doi_to_indices.setdefault(doi, []).append(index)
        if pmid:
            pmid_to_indices.setdefault(pmid, []).append(index)
        if title_key:
            title_to_indices.setdefault(title_key, []).append(index)

    for indices in doi_to_indices.values():
        _add_group(groups, reason="exact_doi", record_indices=indices, records=normalized_records)
    for indices in pmid_to_indices.values():
        _add_group(groups, reason="exact_pmid", record_indices=indices, records=normalized_records)
    for indices in title_to_indices.values():
        _add_group(groups, reason="normalized_title", record_indices=indices, records=normalized_records)

    title_items = [
        (index, normalized_title_key(record.get("title")))
        for index, record in enumerate(normalized_records)
        if normalized_title_key(record.get("title"))
    ]
    for left_position, (left_index, left_title) in enumerate(title_items):
        for right_index, right_title in title_items[left_position + 1 :]:
            if left_title == right_title:
                continue
            similarity = difflib.SequenceMatcher(None, left_title, right_title).ratio()
            if similarity >= title_similarity_threshold:
                _add_group(
                    groups,
                    reason="similar_title",
                    record_indices=[left_index, right_index],
                    records=normalized_records,
                    similarity=similarity,
                )

    seen: set[tuple[str, tuple[int, ...]]] = set()
    unique_groups: list[dict[str, Any]] = []
    for group in groups:
        key = (str(group["reason"]), tuple(group["record_indices"]))
        if key in seen:
            continue
        seen.add(key)
        unique_groups.append(group)

    duplicate_indices = sorted(
        {
            index
            for group in unique_groups
            for index in group["record_indices"]
        }
    )
    return {
        "duplicate_groups": unique_groups,
        "duplicate_record_indices": duplicate_indices,
        "duplicate_record_ids": [_record_key(normalized_records[index], index + 1) for index in duplicate_indices],
        "summary": {
            "record_count": len(normalized_records),
            "duplicate_group_count": len(unique_groups),
            "duplicate_record_count": len(duplicate_indices),
            "manual_review_required": bool(unique_groups),
        },
    }
