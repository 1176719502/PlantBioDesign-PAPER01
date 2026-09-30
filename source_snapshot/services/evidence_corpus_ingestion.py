from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from services.evidence_duplicate_detector import detect_evidence_duplicates
from services.evidence_record_normalizer import (
    EVIDENCE_NORMALIZATION_BOUNDARY_NOTE,
    normalize_evidence_record,
)


EVIDENCE_CORPUS_INGESTION_BOUNDARY_NOTE = (
    "Local evidence corpus ingestion prepares pasted or structured source metadata for manual "
    "documentation review and ranking. It does not call the network, generate designs, validate "
    "experiments, optimize routes, or judge wet-lab use state."
)

_KEY_ALIASES = {
    "doi": "doi",
    "pmid": "pmid",
    "title": "title",
    "abstract": "abstract",
    "summary": "abstract",
    "year": "year",
    "publication year": "year",
    "source": "source",
    "journal": "source",
    "authors": "authors",
    "keywords": "keywords",
    "design slots": "design_slots",
    "design_slots": "design_slots",
    "source url": "source_url",
    "url": "source_url",
    "note": "abstract",
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _as_sequence(value: Any) -> list[Any]:
    if isinstance(value, Mapping):
        return [value]
    if isinstance(value, str):
        return _parse_note_blocks(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items: list[Any] = []
        for item in value:
            if isinstance(item, str):
                items.extend(_parse_note_blocks(item))
            elif isinstance(item, Mapping):
                items.append(item)
        return items
    return []


def _canonical_key(raw_key: str) -> str:
    key = raw_key.strip().casefold().replace("_", " ")
    key = re.sub(r"\s+", " ", key)
    return _KEY_ALIASES.get(key, key.replace(" ", "_"))


def _parse_note_block(block: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    free_text: list[str] = []
    for line in block.splitlines():
        clean = line.strip().strip("-* ")
        if not clean:
            continue
        match = re.match(r"^([A-Za-z][A-Za-z0-9 _/-]{1,32})\s*:\s*(.+)$", clean)
        if match:
            parsed[_canonical_key(match.group(1))] = match.group(2).strip()
        else:
            free_text.append(clean)

    if free_text:
        if "title" not in parsed:
            parsed["title"] = free_text[0]
        if len(free_text) > 1 and "abstract" not in parsed:
            parsed["abstract"] = " ".join(free_text[1:])
    parsed["raw_note_text"] = block.strip()
    return parsed


def _parse_note_blocks(text: str) -> list[dict[str, Any]]:
    clean = str(text or "").strip()
    if not clean:
        return []
    blocks = [block.strip() for block in re.split(r"\n\s*\n+", clean) if block.strip()]
    return [_parse_note_block(block) for block in blocks]


def ingest_local_evidence_corpus(corpus: Any) -> dict[str, Any]:
    """Ingest local evidence metadata into normalized R64 ranker-compatible records."""
    raw_items = _as_sequence(corpus)
    records = [
        normalize_evidence_record(raw_item, input_index=index)
        for index, raw_item in enumerate(raw_items, start=1)
    ]
    duplicate_report = detect_evidence_duplicates(records)
    duplicate_indices = set(duplicate_report["duplicate_record_indices"])

    for index, record in enumerate(records):
        if index in duplicate_indices:
            if "duplicate_candidate" not in record["manual_review_reasons"]:
                record["manual_review_reasons"].append("duplicate_candidate")
            if "duplicate_candidate" not in record["manual_review_flags"]:
                record["manual_review_flags"].append("duplicate_candidate")
            record["manual_review_required"] = True

    return {
        "records": records,
        "duplicate_report": duplicate_report,
        "summary": {
            "input_count": len(raw_items),
            "record_count": len(records),
            "duplicate_group_count": duplicate_report["summary"]["duplicate_group_count"],
            "manual_review_required": True,
            "records_requiring_manual_review": sum(
                1 for record in records if record["manual_review_required"]
            ),
        },
        "boundary_note": EVIDENCE_CORPUS_INGESTION_BOUNDARY_NOTE,
        "normalization_boundary_note": EVIDENCE_NORMALIZATION_BOUNDARY_NOTE,
    }


def ingest_evidence_records(corpus: Any) -> list[dict[str, Any]]:
    """Return only normalized evidence records for callers that need ranker input."""
    return ingest_local_evidence_corpus(corpus)["records"]
