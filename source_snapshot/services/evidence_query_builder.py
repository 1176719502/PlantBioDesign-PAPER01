from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from services.evidence_retrieval_provider import (
    EVIDENCE_RETRIEVAL_BOUNDARY_NOTE,
    EvidenceQuery,
    EvidenceQueryBundle,
)


DESIGN_SLOT_LABELS: dict[str, str] = {
    "target_gene_product": "target gene/product",
    "host_chassis": "host/chassis",
    "promoter": "promoter",
    "terminator": "terminator",
    "selectable_marker": "selectable marker",
    "vector_backbone": "vector/backbone",
    "expression_context": "expression context",
}

DESIGN_SLOT_ALIASES: dict[str, str] = {
    "target_gene": "target_gene_product",
    "target_product": "target_gene_product",
    "target_gene_product": "target_gene_product",
    "gene_product": "target_gene_product",
    "host": "host_chassis",
    "chassis": "host_chassis",
    "host_chassis": "host_chassis",
    "promoter": "promoter",
    "terminator": "terminator",
    "selectable_marker": "selectable_marker",
    "marker": "selectable_marker",
    "vector": "vector_backbone",
    "backbone": "vector_backbone",
    "vector_backbone": "vector_backbone",
    "expression_context": "expression_context",
    "context": "expression_context",
}

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _slot_key(value: Any) -> str:
    clean = _text(value).casefold().replace("/", "_").replace("-", "_").replace(" ", "_")
    clean = re.sub(r"_+", "_", clean).strip("_")
    return DESIGN_SLOT_ALIASES.get(clean, clean)


def _slot_value(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("value", "label", "name", "text", "display_name", "provided_context"):
            clean = _text(value.get(key))
            if clean:
                return clean
        return ""
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return " ".join(_text(item) for item in value if _text(item))
    return _text(value)


def _tokens(value: str) -> list[str]:
    seen: set[str] = set()
    tokens: list[str] = []
    for match in _TOKEN_RE.findall(value):
        token = match.casefold()
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens


def _unique(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    unique_values: list[str] = []
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            unique_values.append(clean)
    return unique_values


def _query_text(slot_label: str, phrase: str, keywords: Sequence[str]) -> str:
    keyword_text = " ".join(keywords)
    parts = [part for part in (slot_label, phrase, keyword_text, "plant evidence") if part]
    return " ".join(parts)


def build_evidence_query_bundle(
    design_slots: Mapping[str, Any] | None,
    *,
    extra_keywords: Sequence[str] | None = None,
    exact_phrases: Sequence[str] | None = None,
) -> EvidenceQueryBundle:
    """Build deterministic slot-aware evidence metadata queries."""
    if not isinstance(design_slots, Mapping) or not design_slots:
        return {
            "queries": [],
            "slot_keys": [],
            "slot_values": {},
            "exact_phrases": _unique(list(exact_phrases or [])),
            "keywords": _unique([_text(value).casefold() for value in extra_keywords or []]),
            "manual_review_status": "manual_review_required",
            "boundary_note": EVIDENCE_RETRIEVAL_BOUNDARY_NOTE,
            "empty_state": "No design slot context was provided for evidence retrieval review.",
        }

    global_exact_phrases = _unique(list(exact_phrases or []))
    global_keywords = _unique([_text(value).casefold() for value in extra_keywords or []])
    normalized_slots: dict[str, str] = {}
    queries: list[EvidenceQuery] = []

    for raw_key, raw_value in design_slots.items():
        slot_key = _slot_key(raw_key)
        phrase = _slot_value(raw_value)
        if not slot_key or not phrase:
            continue
        normalized_slots[slot_key] = phrase

    for index, slot_key in enumerate(sorted(normalized_slots), start=1):
        phrase = normalized_slots[slot_key]
        slot_label = DESIGN_SLOT_LABELS.get(slot_key, slot_key.replace("_", " "))
        keywords = _unique([*_tokens(phrase), *global_keywords])
        query_exact_phrases = _unique([phrase, *global_exact_phrases])
        queries.append(
            {
                "query_id": f"evidence-query-{index:03d}",
                "slot_key": slot_key,
                "slot_label": slot_label,
                "phrase": phrase,
                "keywords": keywords,
                "query_text": _query_text(slot_label, phrase, keywords),
                "exact_phrases": query_exact_phrases,
                "manual_review_status": "manual_review_required",
                "boundary_note": EVIDENCE_RETRIEVAL_BOUNDARY_NOTE,
            }
        )

    return {
        "queries": queries,
        "slot_keys": [query["slot_key"] for query in queries],
        "slot_values": {query["slot_key"]: query["phrase"] for query in queries},
        "exact_phrases": global_exact_phrases,
        "keywords": global_keywords,
        "manual_review_status": "manual_review_required",
        "boundary_note": EVIDENCE_RETRIEVAL_BOUNDARY_NOTE,
        "empty_state": "" if queries else "No usable design slot values were provided.",
    }


def build_evidence_queries(
    design_slots: Mapping[str, Any] | None,
    *,
    extra_keywords: Sequence[str] | None = None,
    exact_phrases: Sequence[str] | None = None,
) -> list[EvidenceQuery]:
    return build_evidence_query_bundle(
        design_slots,
        extra_keywords=extra_keywords,
        exact_phrases=exact_phrases,
    )["queries"]
