from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
import re
from typing import Any

from services.evidence_ranker import RANKING_BOUNDARY_NOTE, rank_evidence_records
from services.plant_expression_route_template_registry import (
    get_plant_expression_route_template_by_id,
)
from services.plant_review_module_card_registry import get_plant_review_module_card_by_id
from services.plant_review_module_card_schema import CURRENT_ACTIVE_PLANT_ROUTE_TYPE


MATCHER_BOUNDARY_NOTE = (
    "Documentation-only plant slot evidence matcher for manual review. It links source "
    "metadata candidates to route draft slots without selecting components, producing a "
    "final design, predicting outcomes, generating sequences, or judging lab-use state."
)

SUPPORTED_MATCHER_STATUS = "plant_slot_evidence_candidates_for_manual_review"
FAIL_SAFE_MATCHER_STATUS = "fail_safe_manual_review_required"
UNSUPPORTED_MATCHER_STATUS = "unsupported_plant_slot_evidence_matching"

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

_NON_PLANT_ROUTE_MARKERS: tuple[str, ...] = (
    "unsupported_non_plant",
    "bacterial",
    "bacteria",
    "e_coli",
    "ecoli",
    "escherichia",
    "yeast",
    "mammalian",
    "cho",
    "hek293",
)

_UNSUPPORTED_ROUTE_STATUSES: tuple[str, ...] = (
    "unsupported_non_plant_scope",
    "mixed_scope_manual_review",
    "unknown_or_ambiguous",
)

_SLOT_LABEL_OVERRIDES: dict[str, str] = {
    "cds_label": "CDS source",
    "coding_sequence_slot": "CDS source",
    "promoter_slot": "Promoter and leader",
    "promoter_source_reference": "Promoter source reference",
    "terminator_slot": "Terminator",
    "terminator_source_reference": "Terminator source reference",
    "plant_species": "Plant host species",
    "plant_context": "Plant expression context",
    "host_context_note": "Host context note",
    "backbone_label": "Vector backbone",
    "source_reference": "Source reference",
}

_SLOT_ALIASES: dict[str, tuple[str, ...]] = {
    "target_name": ("target", "product", "protein", "gene product"),
    "documentation_goal": ("documentation goal", "review goal", "expression purpose"),
    "plant_context": ("plant context", "plant expression", "expression context", "plant"),
    "plant_species": ("plant species", "plant host", "host plant", "rice", "oryza"),
    "host_context_note": ("host context", "tissue context", "seed", "leaf", "plant host"),
    "cds_label": ("cds", "coding sequence", "gene source", "protein source", "albumin"),
    "coding_sequence_slot": ("cds", "coding sequence", "gene", "open reading frame", "albumin"),
    "sequence_source_note": ("sequence source", "cds source", "gene source", "accession"),
    "promoter_slot": ("promoter", "leader", "regulatory", "seed promoter"),
    "promoter_source_reference": ("promoter", "leader", "promoter source", "regulatory"),
    "terminator_slot": ("terminator", "polyadenylation", "3 utr", "nos terminator"),
    "terminator_source_reference": ("terminator", "terminator source", "polyadenylation"),
    "backbone_label": ("vector", "backbone", "binary vector", "expression vector"),
    "localization_note": ("localization", "localisation", "subcellular", "signal peptide"),
    "signal_peptide_slot": ("signal peptide", "secretion", "localization", "targeting peptide"),
    "reporter_slot": ("reporter", "gfp", "luciferase", "fluorescent"),
    "source_reference": ("source reference", "citation", "evidence", "provenance"),
    "manual_review_note": ("manual review", "review note", "curation note"),
    "component_name": ("component", "part", "element"),
    "component_type": ("component type", "part type", "element type"),
}

_R64_SLOT_ALIASES: dict[str, str] = {
    "target_name": "target_gene_product",
    "cds_label": "target_gene_product",
    "coding_sequence_slot": "target_gene_product",
    "sequence_source_note": "target_gene_product",
    "plant_species": "host_chassis",
    "plant_context": "expression_context",
    "host_context_note": "host_chassis",
    "promoter_slot": "promoter",
    "promoter_source_reference": "promoter",
    "terminator_slot": "terminator",
    "terminator_source_reference": "terminator",
    "backbone_label": "vector_backbone",
    "reporter_slot": "target_gene_product",
}

_COMPONENT_GROUP_TERMS: dict[str, tuple[str, ...]] = {
    "promoter": ("promoter", "leader", "regulatory"),
    "terminator": ("terminator", "polyadenylation", "3 utr"),
    "cds": ("cds", "coding sequence", "gene source", "open reading frame"),
    "backbone": ("vector backbone", "binary vector", "backbone"),
    "signal": ("signal peptide", "secretion", "targeting peptide"),
    "marker": ("selectable marker", "marker"),
    "reporter": ("reporter", "gfp", "luciferase"),
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    return re.sub(r"_+", "_", _text(value).casefold().replace("-", "_").replace("/", "_").replace(" ", "_")).strip("_")


def _searchable(value: Any) -> str:
    return " ".join(_text(value).casefold().replace("-", " ").replace("_", " ").split())


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        clean = _text(value)
        return [clean] if clean else []
    if isinstance(value, Mapping):
        return [_text(key) for key in sorted(value, key=lambda item: str(item)) if _text(key)]
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [_text(item) for item in value if _text(item)]
    clean = _text(value)
    return [clean] if clean else []


def _unique_texts(values: Iterable[Any]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            unique.append(clean)
            seen.add(key)
    return unique


def _tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_RE.findall(_text(value)):
        token = match.casefold()
        if len(token) < 3 or token in seen:
            continue
        tokens.append(token)
        seen.add(token)
    return tokens


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _slot_label(slot_id: str) -> str:
    return _SLOT_LABEL_OVERRIDES.get(slot_id, slot_id.replace("_", " ").title())


def _add_slot(slots: list[dict[str, Any]], seen: set[str], slot_id: str, *, value: str = "", source: str = "") -> None:
    slot_id = _key(slot_id)
    if not slot_id or slot_id in seen:
        return
    slots.append(
        {
            "slot_id": slot_id,
            "slot_label": _slot_label(slot_id),
            "slot_value": _text(value),
            "slot_sources": [source] if source else [],
        }
    )
    seen.add(slot_id)


def _merge_slot_source(slots: list[dict[str, Any]], slot_id: str, source: str) -> None:
    slot_key = _key(slot_id)
    for slot in slots:
        if slot["slot_id"] == slot_key and source and source not in slot["slot_sources"]:
            slot["slot_sources"].append(source)
            return


def _extract_slots_from_route_draft(route_draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    seen: set[str] = set()

    for source_field in ("required_construct_slots", "required_slots"):
        for slot in route_draft.get(source_field) or []:
            if not isinstance(slot, Mapping):
                continue
            slot_id = _text(slot.get("slot_id") or slot.get("slot_name") or slot.get("id") or slot.get("name"))
            value = _text(slot.get("value") or slot.get("slot_value"))
            _add_slot(slots, seen, slot_id, value=value, source=source_field)

    template = route_draft.get("selected_template")
    if isinstance(template, Mapping):
        for slot_id in template.get("required_slots") or []:
            _add_slot(slots, seen, _text(slot_id), source="selected_template.required_slots")
            _merge_slot_source(slots, _text(slot_id), "selected_template.required_slots")
        for module_id in template.get("required_module_ids") or template.get("required_module_cards") or []:
            card = get_plant_review_module_card_by_id(_text(module_id))
            if not card:
                continue
            for slot_id in card.get("required_slots") or []:
                _add_slot(slots, seen, _text(slot_id), source=f"module_card:{module_id}")
                _merge_slot_source(slots, _text(slot_id), f"module_card:{module_id}")

    for summary in route_draft.get("module_card_summaries") or route_draft.get("required_modules") or []:
        if not isinstance(summary, Mapping):
            continue
        module_id = _text(summary.get("module_id"))
        for slot_id in summary.get("required_slots") or []:
            _add_slot(slots, seen, _text(slot_id), source=f"module_card:{module_id}")
            _merge_slot_source(slots, _text(slot_id), f"module_card:{module_id}")

    return slots


def _route_context_blob(route_draft: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for field in ("route_id", "route_name", "route_type", "draft_status", "boundary_note"):
        parts.append(_text(route_draft.get(field)))
    for field in ("plant_context", "target_summary", "intent_summary", "route_match"):
        value = route_draft.get(field)
        if isinstance(value, Mapping):
            parts.extend(_text(item) for item in value.values())
    template = route_draft.get("selected_template")
    if isinstance(template, Mapping):
        for field in ("route_id", "route_type", "display_name", "plant_context"):
            parts.append(_text(template.get(field)))
        for field in ("trigger_terms", "supported_host_contexts"):
            parts.extend(_list_texts(template.get(field)))
    return _searchable(" ".join(part for part in parts if part))


def _is_supported_plant_route_draft(route_draft: Mapping[str, Any]) -> bool:
    route_id = _key(route_draft.get("route_id"))
    route_type = _text(route_draft.get("route_type"))
    template = route_draft.get("selected_template")
    route_match = route_draft.get("route_match")
    route_match_status = _text(route_match.get("route_match_status")) if isinstance(route_match, Mapping) else ""
    context = route_draft.get("plant_context")
    scope_status = _text(context.get("scope_status")) if isinstance(context, Mapping) else ""
    blob = _route_context_blob(route_draft)

    if not isinstance(template, Mapping) or not template:
        return False
    if route_type != CURRENT_ACTIVE_PLANT_ROUTE_TYPE:
        return False
    if not route_id or route_id.startswith("unknown") or route_id.startswith("unsupported"):
        return False
    if route_match_status in _UNSUPPORTED_ROUTE_STATUSES:
        return False
    if scope_status and scope_status != "plant_scope_review":
        return False
    return not any(marker in blob for marker in _NON_PLANT_ROUTE_MARKERS)


def _missing_context(route_draft: Mapping[str, Any] | None, slots: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]]) -> list[str]:
    missing: list[str] = []
    if not isinstance(route_draft, Mapping) or not route_draft or not _text(route_draft.get("route_id")):
        missing.append("route_context")
    elif not _is_supported_plant_route_draft(route_draft):
        missing.append("supported_plant_route_context")
    if not slots:
        missing.append("slot_context")
    if not records:
        missing.append("evidence_context")
    return missing


def _target_terms(route_draft: Mapping[str, Any], user_context: Mapping[str, Any] | str | None) -> list[str]:
    terms: list[str] = []
    for field in ("target_summary", "intent_summary"):
        value = route_draft.get(field)
        if isinstance(value, Mapping):
            for key in ("target_name", "known_cds_source", "target_or_product_terms", "expression_purpose"):
                terms.append(_text(value.get(key)))
    if isinstance(user_context, Mapping):
        for key in ("target", "target_name", "product", "query", "user_query"):
            terms.append(_text(user_context.get(key)))
    elif isinstance(user_context, str):
        terms.append(user_context)
    return _unique_texts(terms)


def _host_context_terms(route_draft: Mapping[str, Any], user_context: Mapping[str, Any] | str | None) -> list[str]:
    terms: list[str] = []
    for field in ("plant_context", "intent_summary"):
        value = route_draft.get(field)
        if isinstance(value, Mapping):
            for key in (
                "provided_host",
                "provided_context",
                "selected_context",
                "host_plant_terms",
                "tissue_context_terms",
                "expression_context_terms",
            ):
                terms.append(_text(value.get(key)))
    template = route_draft.get("selected_template")
    if isinstance(template, Mapping):
        terms.append(_text(template.get("plant_context")))
        terms.extend(_list_texts(template.get("supported_host_contexts")))
    if isinstance(user_context, Mapping):
        for key in ("host", "plant_host", "context", "plant_context", "tissue_context"):
            terms.append(_text(user_context.get(key)))
    return _unique_texts(terms)


def _record_text(record: Mapping[str, Any]) -> str:
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
        "source",
    ):
        parts.append(_text(record.get(key)))
    for key in ("keywords", "design_slots", "exact_phrases", "manual_review_flags", "manual_review_reasons"):
        parts.extend(_list_texts(record.get(key)))
    values = record.get("design_slot_values")
    if isinstance(values, Mapping):
        parts.extend(_text(key) for key in values)
        parts.extend(_text(value) for value in values.values())
    return _searchable(" ".join(part for part in parts if part))


def _record_design_slots(record: Mapping[str, Any]) -> set[str]:
    slots = {_key(slot) for slot in _list_texts(record.get("design_slots"))}
    values = record.get("design_slot_values")
    if isinstance(values, Mapping):
        slots.update(_key(key) for key in values)
    return {slot for slot in slots if slot}


def _slot_terms(slot: Mapping[str, Any], target_terms: Sequence[str], host_context_terms: Sequence[str]) -> list[str]:
    slot_id = _text(slot.get("slot_id"))
    terms: list[str] = [
        slot_id,
        _text(slot.get("slot_label")),
        _text(slot.get("slot_value")),
        *_SLOT_ALIASES.get(slot_id, ()),
    ]
    group = _slot_group(slot_id)
    if group in {"target", "cds", "reporter"}:
        terms.extend(target_terms)
    if group in {"host", "context"}:
        terms.extend(host_context_terms)
    return _unique_texts(terms)


def _slot_group(slot_id: str) -> str:
    key = _key(slot_id)
    if key in {"cds_label", "coding_sequence_slot", "sequence_source_note"}:
        return "cds"
    if key in {"target_name", "reporter_slot"}:
        return "target" if key == "target_name" else "reporter"
    if key in {"plant_species", "host_context_note"}:
        return "host"
    if key in {"plant_context", "documentation_goal"}:
        return "context"
    if "promoter" in key or "leader" in key:
        return "promoter"
    if "terminator" in key:
        return "terminator"
    if "backbone" in key or "vector" in key:
        return "backbone"
    if "signal" in key or "localization" in key or "localisation" in key:
        return "signal"
    if "source_reference" in key:
        return "source"
    return "generic"


def _slot_design_aliases(slot_id: str) -> set[str]:
    aliases = {_key(slot_id)}
    r64_alias = _R64_SLOT_ALIASES.get(_key(slot_id))
    if r64_alias:
        aliases.add(_key(r64_alias))
    for alias in _SLOT_ALIASES.get(_key(slot_id), ()):
        aliases.add(_key(alias))
    group = _slot_group(slot_id)
    if group in _COMPONENT_GROUP_TERMS:
        aliases.add(group)
    return aliases


def _term_hits(blob: str, terms: Sequence[str]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        clean = _searchable(term)
        if clean and clean in blob:
            hits.append(_text(term))
    return _unique_texts(hits)


def _keyword_hits(record: Mapping[str, Any], terms: Sequence[str]) -> list[str]:
    keywords = {_searchable(keyword) for keyword in _list_texts(record.get("keywords"))}
    hits: list[str] = []
    for term in terms:
        for token in _tokens(term):
            if token in keywords:
                hits.append(token)
    return _unique_texts(hits)


def _source_completeness(record: Mapping[str, Any]) -> dict[str, Any]:
    score = record.get("completeness_score")
    if not isinstance(score, (int, float)):
        fields = ("title", "abstract", "publication_year", "source_label", "source_identifier")
        score = sum(1 for field in fields if _text(record.get(field))) / len(fields)
    missing = _list_texts(record.get("missing_metadata"))
    if not missing:
        missing = [
            reason.replace("missing_", "")
            for reason in _list_texts(record.get("manual_review_reasons"))
            if reason.startswith("missing_")
        ]
    return {
        "completeness_score": round(float(score), 3),
        "missing_metadata": _unique_texts(missing),
        "has_title": bool(record.get("has_title", bool(_text(record.get("title"))))),
        "has_source": bool(record.get("has_source", bool(_text(record.get("source_label")) or _text(record.get("source_identifier"))))),
    }


def _component_groups_for_record(record: Mapping[str, Any]) -> set[str]:
    blob = _record_text(record)
    design_slots = _record_design_slots(record)
    groups: set[str] = set()
    for group, terms in _COMPONENT_GROUP_TERMS.items():
        term_keys = {_key(term) for term in terms}
        if group in design_slots or design_slots.intersection(term_keys):
            groups.add(group)
            continue
        if any(_searchable(term) in blob for term in terms):
            groups.add(group)
    return groups


def _is_ambiguous_record(record: Mapping[str, Any]) -> bool:
    flags_blob = _record_text({"manual_review_flags": record.get("manual_review_flags"), "manual_review_reasons": record.get("manual_review_reasons")})
    if any(term in flags_blob for term in ("ambiguous", "unclear", "mixed slot", "multiple slot")):
        return True
    return len(_component_groups_for_record(record)) > 1


def _record_id(record: Mapping[str, Any], index: int) -> str:
    return _text(record.get("record_id")) or f"evidence-record-{index + 1:03d}"


def _ranker_scores_for_slot(
    slot: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    terms: Sequence[str],
) -> dict[str, dict[str, Any]]:
    slot_id = _text(slot.get("slot_id"))
    slot_key = _R64_SLOT_ALIASES.get(slot_id, slot_id)
    query_bundle = {
        "queries": [
            {
                "query_id": f"slot-query-{slot_id}",
                "slot_key": slot_key,
                "slot_label": _text(slot.get("slot_label")),
                "phrase": _text(slot.get("slot_value")) or _text(slot.get("slot_label")),
                "keywords": _unique_texts([token for term in terms for token in _tokens(term)]),
                "exact_phrases": _unique_texts(terms),
            }
        ],
        "slot_keys": [slot_key],
        "slot_values": {slot_key: _text(slot.get("slot_value")) or _text(slot.get("slot_label"))},
        "keywords": _unique_texts([token for term in terms for token in _tokens(term)]),
        "exact_phrases": _unique_texts(terms),
    }
    ranked = rank_evidence_records(records, query_bundle)
    scores: dict[str, dict[str, Any]] = {}
    for candidate in ranked.get("candidates") or []:
        if not isinstance(candidate, Mapping):
            continue
        record_id = _text(candidate.get("record_id"))
        if record_id:
            scores[record_id] = {
                "retrieval_review_score": float(candidate.get("retrieval_review_score") or 0.0),
                "rank": int(candidate.get("rank") or 0),
                "claim_demoted": bool(candidate.get("claim_demoted")),
                "score_breakdown": _plain_value(candidate.get("score_breakdown") or {}),
                "matched_keywords": _plain_value(candidate.get("matched_keywords") or []),
                "matched_exact_phrases": _plain_value(candidate.get("matched_exact_phrases") or []),
            }
    return scores


def _candidate_for_slot(
    *,
    slot: Mapping[str, Any],
    record: Mapping[str, Any],
    record_index: int,
    terms: Sequence[str],
    target_terms: Sequence[str],
    host_context_terms: Sequence[str],
    ranker_score: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    blob = _record_text(record)
    design_slots = _record_design_slots(record)
    slot_id = _text(slot.get("slot_id"))
    slot_group = _slot_group(slot_id)
    slot_aliases = _slot_design_aliases(slot_id)

    slot_tag_hits = sorted(design_slots.intersection(slot_aliases))
    slot_term_hits = _term_hits(blob, terms)
    keyword_hits = _keyword_hits(record, terms)
    target_hits = _term_hits(blob, target_terms)
    context_hits = _term_hits(blob, host_context_terms)
    completeness = _source_completeness(record)
    ranker_value = float((ranker_score or {}).get("retrieval_review_score") or 0.0)
    claim_demoted = bool((ranker_score or {}).get("claim_demoted"))

    relevant = bool(slot_tag_hits or slot_term_hits or keyword_hits)
    if slot_group in {"target", "cds", "reporter"} and target_hits:
        relevant = True
    if slot_group in {"host", "context"} and context_hits:
        relevant = True
    if slot_group == "source" and (slot_term_hits or _text(record.get("source_identifier"))):
        relevant = True
    if not relevant:
        return None

    breakdown = {
        "slot_id_or_label_match": min(float(len(slot_term_hits) * 4), 20.0),
        "design_slot_tag_match": 30.0 if slot_tag_hits else 0.0,
        "keyword_match": min(float(len(keyword_hits) * 3), 15.0),
        "target_or_product_term_match": min(float(len(target_hits) * 3), 12.0),
        "host_or_context_term_match": min(float(len(context_hits) * 2), 10.0),
        "source_completeness": round(float(completeness["completeness_score"]) * 10.0, 3),
        "r64_ranker_score": round(min(ranker_value / 4.0, 10.0), 3),
        "manual_review_safety": -8.0 if claim_demoted else 0.0,
    }
    score = round(max(0.0, sum(breakdown.values())), 3)
    if score <= 0:
        return None

    ambiguous = _is_ambiguous_record(record)
    reasons = ["manual_review_required", "candidate_evidence_requires_human_review"]
    if ambiguous:
        reasons.append("ambiguous_evidence_context")
    if completeness["missing_metadata"]:
        reasons.append("missing_source_metadata")
    if claim_demoted:
        reasons.append("source_claim_needs_boundary_review")

    return {
        "record_id": _record_id(record, record_index),
        "title": _text(record.get("title")) or "Untitled evidence record",
        "candidate_score": score,
        "score_breakdown": breakdown,
        "matched_slot_terms": slot_term_hits,
        "matched_design_slot_tags": slot_tag_hits,
        "matched_keywords": keyword_hits,
        "matched_target_or_product_terms": target_hits,
        "matched_host_or_context_terms": context_hits,
        "source_completeness": completeness,
        "manual_review_required": True,
        "manual_review_reasons": _unique_texts(reasons),
        "source": {
            "source_type": _text(record.get("source_type")),
            "source_identifier": _text(record.get("source_identifier")),
            "source_label": _text(record.get("source_label")),
            "source_url": _text(record.get("source_url")),
            "publication_year": record.get("publication_year") if isinstance(record.get("publication_year"), int) else None,
        },
        "r64_ranker": _plain_value(ranker_score or {}),
    }


def _slot_result(
    *,
    slot: Mapping[str, Any],
    records: Sequence[Mapping[str, Any]],
    target_terms: Sequence[str],
    host_context_terms: Sequence[str],
) -> dict[str, Any]:
    terms = _slot_terms(slot, target_terms, host_context_terms)
    ranker_scores = _ranker_scores_for_slot(slot, records, terms) if records else {}
    candidates: list[dict[str, Any]] = []
    for index, record in enumerate(records):
        candidate = _candidate_for_slot(
            slot=slot,
            record=record,
            record_index=index,
            terms=terms,
            target_terms=target_terms,
            host_context_terms=host_context_terms,
            ranker_score=ranker_scores.get(_record_id(record, index)),
        )
        if candidate:
            candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            -float(item["candidate_score"]),
            _text(item["record_id"]).casefold(),
            _text(item["title"]).casefold(),
        )
    )

    best_score = float(candidates[0]["candidate_score"]) if candidates else 0.0
    best_breakdown = candidates[0]["score_breakdown"] if candidates else {
        "slot_id_or_label_match": 0.0,
        "design_slot_tag_match": 0.0,
        "keyword_match": 0.0,
        "target_or_product_term_match": 0.0,
        "host_or_context_term_match": 0.0,
        "source_completeness": 0.0,
        "r64_ranker_score": 0.0,
        "manual_review_safety": 0.0,
    }
    ambiguous = any("ambiguous_evidence_context" in candidate["manual_review_reasons"] for candidate in candidates)
    manual_reasons = ["manual_review_required"]
    missing_reason = ""
    if not records:
        manual_reasons.append("missing_evidence_context")
        missing_reason = "no_evidence_records_provided"
    elif not candidates:
        manual_reasons.append("missing_slot_evidence")
        missing_reason = "no_candidate_evidence_for_slot"
    if ambiguous:
        manual_reasons.append("ambiguous_evidence_context")

    return {
        "slot_id": _text(slot.get("slot_id")),
        "slot_label": _text(slot.get("slot_label")),
        "slot_status": "candidate_evidence_manual_review" if candidates else "missing_evidence",
        "candidate_evidence": candidates,
        "best_candidate_score": best_score,
        "score_breakdown": _plain_value(best_breakdown),
        "source_completeness": candidates[0]["source_completeness"] if candidates else {
            "completeness_score": 0.0,
            "missing_metadata": [],
            "has_title": False,
            "has_source": False,
        },
        "manual_review_required": True,
        "manual_review_reasons": _unique_texts(manual_reasons),
        "missing_evidence_reason": missing_reason,
    }


def _fail_safe_result(
    *,
    route_draft: Mapping[str, Any] | None,
    slots: Sequence[Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    status: str,
) -> dict[str, Any]:
    missing = _missing_context(route_draft, slots, records)
    route_id = _text(route_draft.get("route_id")) if isinstance(route_draft, Mapping) else ""
    route_type = _text(route_draft.get("route_type")) if isinstance(route_draft, Mapping) else ""
    return {
        "matcher_status": status,
        "plant_scope_supported": False,
        "final_design_present": False,
        "active_plant_design_evidence_matches": False,
        "candidate_slot_evidence_present": False,
        "manual_review_required": True,
        "manual_review_reasons": _unique_texts(["manual_review_required", *missing]),
        "missing_context": missing,
        "route_context": {
            "route_id": route_id,
            "route_type": route_type,
            "route_status": _text(route_draft.get("draft_status")) if isinstance(route_draft, Mapping) else "",
        },
        "slots": [],
        "slot_matches": [],
        "summary": {
            "slot_count": 0,
            "slots_with_candidate_evidence": 0,
            "slots_missing_evidence": 0,
            "ambiguous_candidate_count": 0,
        },
        "boundary_note": MATCHER_BOUNDARY_NOTE,
        "ranker_boundary_note": RANKING_BOUNDARY_NOTE,
    }


def match_plant_evidence_to_slots(
    route_draft: Mapping[str, Any] | None,
    evidence_records: Sequence[Mapping[str, Any]] | None,
    user_context: Mapping[str, Any] | str | None = None,
) -> dict[str, Any]:
    """Match normalized local evidence records to plant route draft slots for manual review."""
    records = [record for record in evidence_records or [] if isinstance(record, Mapping)]
    if not isinstance(route_draft, Mapping) or not route_draft:
        return _fail_safe_result(
            route_draft=None,
            slots=[],
            records=records,
            status=FAIL_SAFE_MATCHER_STATUS,
        )

    route_draft = dict(route_draft)
    template = route_draft.get("selected_template")
    if isinstance(template, Mapping) and _text(template.get("route_id")):
        route_draft["selected_template"] = get_plant_expression_route_template_by_id(
            _text(template.get("route_id"))
        ) or template

    slots = _extract_slots_from_route_draft(route_draft)
    if not _is_supported_plant_route_draft(route_draft):
        return _fail_safe_result(
            route_draft=route_draft,
            slots=slots,
            records=records,
            status=UNSUPPORTED_MATCHER_STATUS,
        )

    target_terms = _target_terms(route_draft, user_context)
    host_context_terms = _host_context_terms(route_draft, user_context)
    slot_matches = [
        _slot_result(
            slot=slot,
            records=records,
            target_terms=target_terms,
            host_context_terms=host_context_terms,
        )
        for slot in slots
    ]

    slots_with_candidates = sum(1 for slot in slot_matches if slot["candidate_evidence"])
    ambiguous_count = sum(
        1
        for slot in slot_matches
        for candidate in slot["candidate_evidence"]
        if "ambiguous_evidence_context" in candidate["manual_review_reasons"]
    )
    missing_context = _missing_context(route_draft, slots, records)
    return {
        "matcher_status": SUPPORTED_MATCHER_STATUS,
        "plant_scope_supported": True,
        "final_design_present": False,
        "active_plant_design_evidence_matches": False,
        "candidate_slot_evidence_present": bool(slots_with_candidates),
        "manual_review_required": True,
        "manual_review_reasons": _unique_texts(["manual_review_required", *missing_context]),
        "missing_context": missing_context,
        "route_context": {
            "route_id": _text(route_draft.get("route_id")),
            "route_type": _text(route_draft.get("route_type")),
            "route_status": _text(route_draft.get("draft_status")),
        },
        "slots": slot_matches,
        "slot_matches": slot_matches,
        "summary": {
            "slot_count": len(slot_matches),
            "slots_with_candidate_evidence": slots_with_candidates,
            "slots_missing_evidence": len(slot_matches) - slots_with_candidates,
            "ambiguous_candidate_count": ambiguous_count,
        },
        "boundary_note": MATCHER_BOUNDARY_NOTE,
        "ranker_boundary_note": RANKING_BOUNDARY_NOTE,
    }
