from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
import re
from typing import Any

from services.plant_expression_route_template_registry import (
    get_plant_expression_route_template_by_id,
)
from services.plant_review_module_card_registry import get_plant_review_module_card_by_id
from services.plant_review_module_card_schema import CURRENT_ACTIVE_PLANT_ROUTE_TYPE


MATCHER_BOUNDARY_NOTE = (
    "Documentation-only plant component candidate matcher for manual review. It links "
    "route slots, slot evidence ids, and local component records as review candidates "
    "without selecting a final component, generating sequences, predicting outcomes, "
    "or judging downstream use."
)

SUPPORTED_MATCHER_STATUS = "plant_component_candidates_for_manual_review"
FAIL_SAFE_MATCHER_STATUS = "fail_safe_manual_review_required"
UNSUPPORTED_MATCHER_STATUS = "unsupported_plant_component_candidate_matching"

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

_NON_PLANT_COMPONENT_TERMS: tuple[str, ...] = (
    "bacterial",
    "bacteria",
    "e. coli",
    "ecoli",
    "escherichia",
    "yeast",
    "saccharomyces",
    "pichia",
    "mammalian",
    "human cell",
    "cho cell",
    "hek293",
    "mouse",
)

_PLANT_TERMS: tuple[str, ...] = (
    "plant",
    "rice",
    "oryza",
    "oryza sativa",
    "nicotiana",
    "benthamiana",
    "arabidopsis",
    "maize",
    "corn",
    "wheat",
    "soybean",
    "tobacco",
    "chloroplast",
    "plastid",
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

_SLOT_COMPONENT_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "target": ("target", "target_product", "protein", "gene_product"),
    "host": ("host", "plant_host", "plant_species", "host_chassis", "host_context"),
    "context": ("context", "plant_context", "expression_context", "documentation_goal"),
    "cds": ("cds", "coding_sequence", "coding_sequence_slot", "gene", "source", "cds_source"),
    "promoter": ("promoter", "promoter_slot", "leader", "regulatory_element", "regulatory"),
    "terminator": ("terminator", "terminator_slot", "polyadenylation", "3_utr"),
    "backbone": ("backbone", "vector_backbone", "plasmid_backbone", "binary_vector", "vector"),
    "signal": ("signal", "signal_peptide", "signal_peptide_slot", "localization", "targeting_peptide"),
    "marker": ("marker", "selectable_marker", "selection_marker"),
    "reporter": ("reporter", "gfp", "luciferase"),
    "source": ("source", "source_reference", "literature_source_note", "component_source"),
    "generic": ("component", "component_asset", "part"),
}

_COMPONENT_ID_FIELDS: tuple[str, ...] = (
    "component_id",
    "asset_id",
    "part_id",
    "profile_id",
    "record_identifier",
    "source_record_id",
)

_COMPONENT_NAME_FIELDS: tuple[str, ...] = (
    "component_name",
    "component_label",
    "asset_label",
    "asset_display_name",
    "display_name",
    "promoter_label",
    "part_label",
    "source_record_label",
    "name",
    "title",
)

_COMPONENT_TYPE_FIELDS: tuple[str, ...] = (
    "component_type",
    "asset_type",
    "part_type",
    "component_category",
    "slot_type",
    "Asset type",
)

_SOURCE_FIELDS: tuple[str, ...] = (
    "source_label",
    "source_type",
    "source_database",
    "source_accession",
    "accession",
    "source_reference",
    "publication_reference",
    "source_id",
    "source_record_id",
    "provenance_status",
    "provenance_note",
    "source_notes",
    "citation",
)

_ZERO_SCORE_BREAKDOWN: dict[str, float] = {
    "slot_id_or_label_match": 0.0,
    "component_type_match": 0.0,
    "component_name_or_alias_match": 0.0,
    "design_slot_tag_match": 0.0,
    "host_or_context_term_match": 0.0,
    "matched_evidence_id_match": 0.0,
    "source_completeness": 0.0,
    "duplicate_or_alias_review_signal": 0.0,
}

_GENERIC_REVIEW_TOKENS: set[str] = {
    "component",
    "context",
    "curated",
    "documentation",
    "expression",
    "local",
    "manual",
    "metadata",
    "note",
    "plant",
    "record",
    "review",
    "source",
}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _key(value: Any) -> str:
    clean = _text(value).casefold().replace("-", "_").replace("/", "_").replace(" ", "_")
    return re.sub(r"_+", "_", clean).strip("_")


def _searchable(value: Any) -> str:
    return " ".join(_text(value).casefold().replace("-", " ").replace("_", " ").split())


def _list_texts(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = re.split(r"[;\n|,]+", value)
    elif isinstance(value, Mapping):
        raw_values = sorted(value.keys(), key=lambda item: str(item))
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        raw_values = list(value)
    else:
        raw_values = [value] if _text(value) else []
    return [_text(item) for item in raw_values if _text(item)]


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


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _first_text(record: Mapping[str, Any], fields: Sequence[str]) -> str:
    for field in fields:
        if field in record and _text(record.get(field)):
            return _text(record.get(field))
    return ""


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


def _slot_label(slot_id: str) -> str:
    return _SLOT_LABEL_OVERRIDES.get(slot_id, slot_id.replace("_", " ").title())


def _slot_group(slot_id: str) -> str:
    key = _key(slot_id)
    if key in {"cds_label", "coding_sequence_slot", "sequence_source_note"}:
        return "cds"
    if key in {"target_name"}:
        return "target"
    if key == "reporter_slot":
        return "reporter"
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
    if "marker" in key:
        return "marker"
    return "generic"


def _slot_component_type(slot_id: str) -> str:
    return _slot_group(slot_id)


def _component_type_group(value: Any) -> str:
    key = _key(value)
    for group, aliases in _SLOT_COMPONENT_TYPE_ALIASES.items():
        if key == group or key in {_key(alias) for alias in aliases}:
            return group
    if "promoter" in key or "leader" in key:
        return "promoter"
    if "terminator" in key or "polyadenylation" in key:
        return "terminator"
    if key in {"cds_source", "coding_sequence_source"} or "coding_sequence" in key:
        return "cds"
    if "backbone" in key or "vector" in key:
        return "backbone"
    if "signal" in key or "localization" in key or "localisation" in key:
        return "signal"
    if "marker" in key:
        return "marker"
    if "reporter" in key:
        return "reporter"
    if "source" in key or "literature" in key:
        return "source"
    if "host" in key or "species" in key:
        return "host"
    return key or "generic"


def _compatible_component_type(slot_component_type: str, record_component_type: str) -> bool:
    slot_group = _component_type_group(slot_component_type)
    record_group = _component_type_group(record_component_type)
    if slot_group == record_group:
        return True
    return slot_group == "cds" and record_group == "source"


def _add_slot(
    slots: list[dict[str, Any]],
    by_id: dict[str, dict[str, Any]],
    slot_id: str,
    *,
    slot_label: str = "",
    value: str = "",
    source: str = "",
    matched_evidence_ids: Sequence[str] | None = None,
    evidence_slot_status: str = "",
) -> None:
    key = _key(slot_id)
    if not key:
        return
    if key not in by_id:
        by_id[key] = {
            "slot_id": key,
            "slot_label": _text(slot_label) or _slot_label(key),
            "slot_value": _text(value),
            "slot_sources": [],
            "matched_evidence_ids": [],
            "evidence_slot_status": "",
            "component_type": _slot_component_type(key),
        }
        slots.append(by_id[key])
    slot = by_id[key]
    if source and source not in slot["slot_sources"]:
        slot["slot_sources"].append(source)
    if value and not slot["slot_value"]:
        slot["slot_value"] = _text(value)
    if slot_label and not slot["slot_label"]:
        slot["slot_label"] = _text(slot_label)
    for evidence_id in matched_evidence_ids or []:
        clean = _text(evidence_id)
        if clean and clean not in slot["matched_evidence_ids"]:
            slot["matched_evidence_ids"].append(clean)
    if evidence_slot_status and not slot["evidence_slot_status"]:
        slot["evidence_slot_status"] = _text(evidence_slot_status)


def _evidence_ids_from_slot_match(slot_match: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    ids.extend(_list_texts(slot_match.get("matched_evidence_ids")))
    for candidate_key in ("candidate_evidence", "candidate_records", "candidates"):
        for candidate in slot_match.get(candidate_key) or []:
            if isinstance(candidate, Mapping):
                ids.append(_text(candidate.get("record_id") or candidate.get("evidence_id") or candidate.get("source_id")))
    return _unique_texts(ids)


def _extract_slots(
    route_draft: Mapping[str, Any],
    evidence_slot_match_result: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    slots: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}

    for source_field in ("required_construct_slots", "required_slots"):
        for slot in route_draft.get(source_field) or []:
            if not isinstance(slot, Mapping):
                continue
            slot_id = _text(slot.get("slot_id") or slot.get("slot_name") or slot.get("id") or slot.get("name"))
            _add_slot(
                slots,
                by_id,
                slot_id,
                slot_label=_text(slot.get("slot_label") or slot.get("label")),
                value=_text(slot.get("value") or slot.get("slot_value")),
                source=source_field,
            )

    template = route_draft.get("selected_template")
    if isinstance(template, Mapping):
        for slot_id in template.get("required_slots") or []:
            _add_slot(slots, by_id, _text(slot_id), source="selected_template.required_slots")
        for module_id in template.get("required_module_ids") or template.get("required_module_cards") or []:
            card = get_plant_review_module_card_by_id(_text(module_id))
            if not card:
                continue
            for slot_id in card.get("required_slots") or []:
                _add_slot(slots, by_id, _text(slot_id), source=f"module_card:{module_id}")

    for summary in route_draft.get("module_card_summaries") or route_draft.get("required_modules") or []:
        if not isinstance(summary, Mapping):
            continue
        module_id = _text(summary.get("module_id"))
        for slot_id in summary.get("required_slots") or []:
            _add_slot(slots, by_id, _text(slot_id), source=f"module_card:{module_id}")

    if isinstance(evidence_slot_match_result, Mapping):
        for source_field in ("slots", "slot_matches"):
            for slot_match in evidence_slot_match_result.get(source_field) or []:
                if not isinstance(slot_match, Mapping):
                    continue
                slot_id = _text(slot_match.get("slot_id") or slot_match.get("slot_name"))
                _add_slot(
                    slots,
                    by_id,
                    slot_id,
                    slot_label=_text(slot_match.get("slot_label")),
                    source=f"evidence_match_result.{source_field}",
                    matched_evidence_ids=_evidence_ids_from_slot_match(slot_match),
                    evidence_slot_status=_text(slot_match.get("slot_status")),
                )

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


def _target_terms(route_draft: Mapping[str, Any], user_context_terms: Mapping[str, Any] | Sequence[Any] | str | None) -> list[str]:
    terms: list[str] = []
    for field in ("target_summary", "intent_summary"):
        value = route_draft.get(field)
        if isinstance(value, Mapping):
            for key in ("target_name", "known_cds_source", "target_or_product_terms", "expression_purpose"):
                terms.append(_text(value.get(key)))
    if isinstance(user_context_terms, Mapping):
        for key in ("target", "target_name", "product", "query", "user_query"):
            terms.append(_text(user_context_terms.get(key)))
    elif isinstance(user_context_terms, str):
        terms.append(user_context_terms)
    elif isinstance(user_context_terms, Sequence):
        terms.extend(_text(item) for item in user_context_terms)
    return _unique_texts(terms)


def _host_context_terms(
    route_draft: Mapping[str, Any],
    user_context_terms: Mapping[str, Any] | Sequence[Any] | str | None,
) -> list[str]:
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
    if isinstance(user_context_terms, Mapping):
        for key in ("host", "plant_host", "context", "plant_context", "tissue_context"):
            terms.append(_text(user_context_terms.get(key)))
    return _unique_texts(terms)


def _record_blob(record: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for key in (
        *_COMPONENT_ID_FIELDS,
        *_COMPONENT_NAME_FIELDS,
        *_COMPONENT_TYPE_FIELDS,
        "short_description",
        "description",
        "domain_or_source_context",
        "organism_or_source_context",
        "species_label",
        "species",
        "plant_context",
        "host_context",
        "notes",
        "review_note",
        "provenance_note",
        "evidence_summary",
    ):
        parts.append(_text(record.get(key)))
    for key in ("aliases", "alias", "tags", "design_slot_tags", "design_slots", "matched_evidence_ids"):
        parts.extend(_list_texts(record.get(key)))
    return _searchable(" ".join(part for part in parts if part))


def _record_id(record: Mapping[str, Any], index: int) -> str:
    return _first_text(record, _COMPONENT_ID_FIELDS) or f"component-record-{index + 1:03d}"


def _component_name(record: Mapping[str, Any]) -> str:
    return _first_text(record, _COMPONENT_NAME_FIELDS) or "Unnamed component record"


def _component_type(record: Mapping[str, Any]) -> str:
    return _first_text(record, _COMPONENT_TYPE_FIELDS) or "component"


def _record_aliases(record: Mapping[str, Any]) -> list[str]:
    aliases = _list_texts(record.get("aliases"))
    aliases.extend(_list_texts(record.get("alias")))
    aliases.extend(_list_texts(record.get("native_gene_or_locus")))
    return _unique_texts(aliases)


def _record_design_slot_tags(record: Mapping[str, Any]) -> set[str]:
    tags = {_key(value) for value in _list_texts(record.get("design_slot_tags"))}
    tags.update(_key(value) for value in _list_texts(record.get("design_slots")))
    values = record.get("design_slot_values")
    if isinstance(values, Mapping):
        tags.update(_key(key) for key in values)
    return {tag for tag in tags if tag}


def _record_context_terms(record: Mapping[str, Any]) -> list[str]:
    terms: list[str] = []
    for key in (
        "plant_context",
        "host_context",
        "domain_or_source_context",
        "organism_or_source_context",
        "species_label",
        "species",
        "plant_clade",
        "clade",
    ):
        terms.append(_text(record.get(key)))
    return _unique_texts(terms)


def _record_evidence_ids(record: Mapping[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("matched_evidence_ids", "evidence_ids", "evidence_record_ids", "evidence_id"):
        ids.extend(_list_texts(record.get(key)))
    for key in ("source_id", "source_record_id", "record_identifier"):
        ids.append(_text(record.get(key)))
    return _unique_texts(ids)


def _is_component_plant_scope(record: Mapping[str, Any]) -> bool:
    blob = " ".join(
        [
            _record_blob(record),
            _searchable(" ".join(_record_context_terms(record))),
        ]
    )
    if not blob:
        return True
    return not (
        any(_searchable(term) in blob for term in _NON_PLANT_COMPONENT_TERMS)
        and not any(_searchable(term) in blob for term in _PLANT_TERMS)
    )


def _source_completeness(record: Mapping[str, Any]) -> dict[str, Any]:
    field_values = {
        "component_id": _record_id(record, -1),
        "component_name": _component_name(record),
        "component_type": _component_type(record),
        "source": _first_text(record, _SOURCE_FIELDS),
        "provenance": _text(record.get("provenance_status")) or _text(record.get("provenance_note")),
        "evidence_link": bool(_record_evidence_ids(record)) or bool(_text(record.get("evidence_summary"))),
    }
    present = {
        "has_component_id": bool(field_values["component_id"]),
        "has_component_name": field_values["component_name"] != "Unnamed component record",
        "has_component_type": field_values["component_type"] != "component",
        "has_source": bool(field_values["source"]),
        "has_provenance": bool(field_values["provenance"]),
        "has_evidence_link": bool(field_values["evidence_link"]),
    }
    missing_fields = [field.replace("has_", "") for field, is_present in present.items() if not is_present]
    return {
        "completeness_score": round(sum(1 for is_present in present.values() if is_present) / len(present), 3),
        "missing_fields": missing_fields,
        **present,
    }


def _provenance_status(record: Mapping[str, Any], completeness: Mapping[str, Any]) -> str:
    explicit = _text(record.get("provenance_status") or record.get("source_provenance_display_status"))
    if explicit:
        return explicit
    if completeness.get("has_source") and completeness.get("has_provenance"):
        return "source_provenance_recorded"
    if completeness.get("has_source"):
        return "source_recorded_provenance_missing"
    return "source_provenance_missing"


def _duplicate_or_alias_flags(records: Sequence[Mapping[str, Any]]) -> dict[str, bool]:
    labels: Counter[str] = Counter()
    aliases: Counter[str] = Counter()
    ids: Counter[str] = Counter()
    for index, record in enumerate(records):
        ids[_key(_record_id(record, index))] += 1
        labels[_key(f"{_component_type(record)} {_component_name(record)}")] += 1
        for alias in _record_aliases(record):
            aliases[_key(alias)] += 1

    flags: dict[str, bool] = {}
    for index, record in enumerate(records):
        record_key = _record_id(record, index)
        explicit = any(
            bool(record.get(key))
            for key in (
                "duplicate",
                "duplicate_flag",
                "duplicate_candidate",
                "alias_duplicate",
                "duplicate_or_alias_flag",
            )
        )
        duplicate_ref = any(_text(record.get(key)) for key in ("duplicate_of", "alias_of", "same_as_component_id"))
        alias_values = _record_aliases(record)
        id_duplicate = ids[_key(record_key)] > 1
        label_duplicate = labels[_key(f"{_component_type(record)} {_component_name(record)}")] > 1
        alias_overlap = any(aliases[_key(alias)] > 1 for alias in alias_values)
        flags[record_key] = bool(explicit or duplicate_ref or alias_values or id_duplicate or label_duplicate or alias_overlap)
    return flags


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


def _term_hits(blob: str, terms: Sequence[str]) -> list[str]:
    hits: list[str] = []
    for term in terms:
        clean = _searchable(term)
        if clean and clean in blob:
            hits.append(_text(term))
    return _unique_texts(hits)


def _name_or_alias_hits(record: Mapping[str, Any], terms: Sequence[str]) -> list[str]:
    name_blob = _searchable(" ".join([_component_name(record), *_record_aliases(record)]))
    exact_hits = [
        term
        for term in terms
        if any(token not in _GENERIC_REVIEW_TOKENS for token in _tokens(term))
        and _searchable(term)
        and _searchable(term) in name_blob
    ]
    token_terms = _unique_texts(
        token
        for term in terms
        for token in _tokens(term)
        if token not in _GENERIC_REVIEW_TOKENS
    )
    return exact_hits + [
        token for token in token_terms if token and token in name_blob
    ]


def _context_hits(record: Mapping[str, Any], host_context_terms: Sequence[str]) -> list[str]:
    return _term_hits(_searchable(" ".join(_record_context_terms(record))), host_context_terms)


def _slot_tag_hits(record: Mapping[str, Any], slot: Mapping[str, Any]) -> list[str]:
    tags = _record_design_slot_tags(record)
    slot_id = _text(slot.get("slot_id"))
    slot_group = _slot_group(slot_id)
    aliases = {_key(slot_id), _key(slot_group)}
    aliases.update(_key(alias) for alias in _SLOT_ALIASES.get(slot_id, ()))
    aliases.update(_key(alias) for alias in _SLOT_COMPONENT_TYPE_ALIASES.get(slot_group, ()))
    return sorted(tag for tag in tags if tag in aliases)


def _candidate_for_slot(
    *,
    slot: Mapping[str, Any],
    record: Mapping[str, Any],
    record_index: int,
    target_terms: Sequence[str],
    host_context_terms: Sequence[str],
    duplicate_or_alias_flag: bool,
) -> dict[str, Any] | None:
    slot_id = _text(slot.get("slot_id"))
    slot_component_type = _text(slot.get("component_type")) or _slot_component_type(slot_id)
    record_component_type = _component_type(record)
    type_match = _compatible_component_type(slot_component_type, record_component_type)
    slot_terms = _slot_terms(slot, target_terms, host_context_terms)
    blob = _record_blob(record)
    slot_term_hits = _term_hits(blob, slot_terms)
    name_alias_hits = _unique_texts(_name_or_alias_hits(record, slot_terms))
    design_slot_hits = _slot_tag_hits(record, slot)
    context_hits = _context_hits(record, host_context_terms)
    record_evidence_ids = _record_evidence_ids(record)
    matched_evidence_ids = sorted(
        set(_list_texts(slot.get("matched_evidence_ids"))).intersection(record_evidence_ids),
        key=str.casefold,
    )
    completeness = _source_completeness(record)
    provenance_status = _provenance_status(record, completeness)

    slot_group = _slot_group(slot_id)
    record_group = _component_type_group(record_component_type)
    base_relevant = bool(type_match or slot_term_hits or name_alias_hits or design_slot_hits)
    evidence_relevant = bool(matched_evidence_ids and (base_relevant or slot_group == "source" or record_group == "source"))
    relevant = bool(base_relevant or evidence_relevant)
    if slot_group in {"host", "context"} and context_hits:
        relevant = True
    if not relevant:
        return None

    breakdown = {
        "slot_id_or_label_match": min(float(len(slot_term_hits) * 4), 20.0),
        "component_type_match": 28.0 if type_match else 0.0,
        "component_name_or_alias_match": min(float(len(name_alias_hits) * 4), 16.0),
        "design_slot_tag_match": 24.0 if design_slot_hits else 0.0,
        "host_or_context_term_match": min(float(len(context_hits) * 3), 12.0),
        "matched_evidence_id_match": 20.0 if matched_evidence_ids else 0.0,
        "source_completeness": round(float(completeness["completeness_score"]) * 10.0, 3),
        "duplicate_or_alias_review_signal": 0.0,
    }
    score = round(max(0.0, sum(breakdown.values())), 3)
    if score <= 0:
        return None

    manual_reasons = ["manual_review_required", "review_candidate_requires_human_review"]
    if not completeness["has_source"] or not completeness["has_provenance"]:
        manual_reasons.append("missing_provenance_or_source")
    if not completeness["has_evidence_link"]:
        manual_reasons.append("missing_evidence_link")
    if duplicate_or_alias_flag:
        manual_reasons.append("duplicate_or_alias_review")

    return {
        "component_id": _record_id(record, record_index),
        "component_name": _component_name(record),
        "component_type": record_component_type,
        "candidate_score": score,
        "score_breakdown": breakdown,
        "matched_slot_terms": slot_term_hits,
        "matched_component_name_or_alias_terms": name_alias_hits,
        "matched_design_slot_tags": design_slot_hits,
        "matched_host_or_context_terms": context_hits,
        "matched_evidence_ids": matched_evidence_ids,
        "record_evidence_ids": record_evidence_ids,
        "provenance_status": provenance_status,
        "source_completeness": completeness,
        "duplicate_or_alias_flag": bool(duplicate_or_alias_flag),
        "manual_review_required": True,
        "manual_review_reasons": _unique_texts(manual_reasons),
        "traceability": {
            "source_label": _text(record.get("source_label")),
            "source_reference": _text(record.get("source_reference") or record.get("publication_reference")),
            "source_database": _text(record.get("source_database")),
            "source_accession": _text(record.get("source_accession") or record.get("accession")),
            "source_record_id": _text(record.get("source_record_id")),
        },
    }


def _missing_context(
    route_draft: Mapping[str, Any] | None,
    slots: Sequence[Mapping[str, Any]],
    evidence_slot_match_result: Mapping[str, Any] | None,
    records: Sequence[Mapping[str, Any]],
) -> list[str]:
    missing: list[str] = []
    if not isinstance(route_draft, Mapping) or not route_draft or not _text(route_draft.get("route_id")):
        missing.append("route_context")
    elif not _is_supported_plant_route_draft(route_draft):
        missing.append("supported_plant_route_context")
    if not slots:
        missing.append("slot_context")
    if not isinstance(evidence_slot_match_result, Mapping) or not evidence_slot_match_result:
        missing.append("evidence_slot_context")
    if not records:
        missing.append("component_context")
    return missing


def _slot_result(
    *,
    slot: Mapping[str, Any],
    component_records: Sequence[Mapping[str, Any]],
    target_terms: Sequence[str],
    host_context_terms: Sequence[str],
    duplicate_or_alias_flags: Mapping[str, bool],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for index, record in enumerate(component_records):
        candidate = _candidate_for_slot(
            slot=slot,
            record=record,
            record_index=index,
            target_terms=target_terms,
            host_context_terms=host_context_terms,
            duplicate_or_alias_flag=bool(duplicate_or_alias_flags.get(_record_id(record, index))),
        )
        if candidate:
            candidates.append(candidate)

    candidates.sort(
        key=lambda item: (
            -float(item["candidate_score"]),
            _text(item["component_id"]).casefold(),
            _text(item["component_name"]).casefold(),
        )
    )
    best_score = float(candidates[0]["candidate_score"]) if candidates else 0.0
    score_breakdown = candidates[0]["score_breakdown"] if candidates else dict(_ZERO_SCORE_BREAKDOWN)
    source_completeness = candidates[0]["source_completeness"] if candidates else {
        "completeness_score": 0.0,
        "missing_fields": [],
        "has_component_id": False,
        "has_component_name": False,
        "has_component_type": False,
        "has_source": False,
        "has_provenance": False,
        "has_evidence_link": False,
    }
    provenance_status = candidates[0]["provenance_status"] if candidates else "source_provenance_missing"
    duplicate_flag = any(candidate["duplicate_or_alias_flag"] for candidate in candidates)
    manual_reasons = ["manual_review_required"]
    missing_reason = ""
    if not component_records:
        manual_reasons.append("missing_component_context")
        missing_reason = "no_component_records_provided"
    elif not candidates:
        manual_reasons.append("missing_component_candidate")
        missing_reason = "no_component_record_matched_slot"
    for candidate in candidates:
        manual_reasons.extend(candidate["manual_review_reasons"])

    return {
        "slot_id": _text(slot.get("slot_id")),
        "slot_label": _text(slot.get("slot_label")),
        "slot_status": "component_candidates_for_manual_review" if candidates else "missing_component_candidate",
        "candidate_components": candidates,
        "best_candidate_score": best_score,
        "score_breakdown": _plain_value(score_breakdown),
        "matched_evidence_ids": _list_texts(slot.get("matched_evidence_ids")),
        "component_type": _text(slot.get("component_type")) or _slot_component_type(_text(slot.get("slot_id"))),
        "provenance_status": provenance_status,
        "source_completeness": _plain_value(source_completeness),
        "duplicate_or_alias_flag": bool(duplicate_flag),
        "manual_review_required": True,
        "manual_review_reasons": _unique_texts(manual_reasons),
        "missing_component_reason": missing_reason,
    }


def _fail_safe_result(
    *,
    route_draft: Mapping[str, Any] | None,
    slots: Sequence[Mapping[str, Any]],
    evidence_slot_match_result: Mapping[str, Any] | None,
    records: Sequence[Mapping[str, Any]],
    status: str,
) -> dict[str, Any]:
    missing = _missing_context(route_draft, slots, evidence_slot_match_result, records)
    route_id = _text(route_draft.get("route_id")) if isinstance(route_draft, Mapping) else ""
    route_type = _text(route_draft.get("route_type")) if isinstance(route_draft, Mapping) else ""
    return {
        "matcher_status": status,
        "plant_scope_supported": False,
        "final_design_present": False,
        "active_component_candidate_selection": False,
        "candidate_component_matches_present": False,
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
            "slots_with_candidate_components": 0,
            "slots_missing_component_candidates": 0,
            "candidate_component_count": 0,
            "duplicate_or_alias_candidate_count": 0,
            "out_of_scope_component_count": 0,
        },
        "boundary_note": MATCHER_BOUNDARY_NOTE,
    }


def match_plant_component_candidates(
    route_draft: Mapping[str, Any] | None,
    evidence_slot_match_result: Mapping[str, Any] | None,
    component_records: Sequence[Mapping[str, Any]] | None,
    user_context_terms: Mapping[str, Any] | Sequence[Any] | str | None = None,
) -> dict[str, Any]:
    """Match local plant component records to route slots as manual review candidates."""
    records = [record for record in component_records or [] if isinstance(record, Mapping)]
    if not isinstance(route_draft, Mapping) or not route_draft:
        return _fail_safe_result(
            route_draft=None,
            slots=[],
            evidence_slot_match_result=evidence_slot_match_result if isinstance(evidence_slot_match_result, Mapping) else None,
            records=records,
            status=FAIL_SAFE_MATCHER_STATUS,
        )

    route_copy = dict(route_draft)
    template = route_copy.get("selected_template")
    if isinstance(template, Mapping) and _text(template.get("route_id")):
        route_copy["selected_template"] = get_plant_expression_route_template_by_id(_text(template.get("route_id"))) or template

    evidence_result = evidence_slot_match_result if isinstance(evidence_slot_match_result, Mapping) else None
    slots = _extract_slots(route_copy, evidence_result)
    if not _is_supported_plant_route_draft(route_copy):
        return _fail_safe_result(
            route_draft=route_copy,
            slots=slots,
            evidence_slot_match_result=evidence_result,
            records=records,
            status=UNSUPPORTED_MATCHER_STATUS,
        )

    plant_records = [record for record in records if _is_component_plant_scope(record)]
    out_of_scope_count = len(records) - len(plant_records)
    duplicate_or_alias_flags = _duplicate_or_alias_flags(plant_records)
    target_terms = _target_terms(route_copy, user_context_terms)
    host_context_terms = _host_context_terms(route_copy, user_context_terms)
    slot_matches = [
        _slot_result(
            slot=slot,
            component_records=plant_records,
            target_terms=target_terms,
            host_context_terms=host_context_terms,
            duplicate_or_alias_flags=duplicate_or_alias_flags,
        )
        for slot in slots
    ]

    slots_with_candidates = sum(1 for slot in slot_matches if slot["candidate_components"])
    candidate_count = sum(len(slot["candidate_components"]) for slot in slot_matches)
    duplicate_or_alias_count = sum(
        1
        for slot in slot_matches
        for candidate in slot["candidate_components"]
        if candidate["duplicate_or_alias_flag"]
    )
    missing_context = _missing_context(route_copy, slots, evidence_result, plant_records)
    manual_reasons = ["manual_review_required", *missing_context]
    if out_of_scope_count:
        manual_reasons.append("out_of_scope_component_records")

    return {
        "matcher_status": SUPPORTED_MATCHER_STATUS,
        "plant_scope_supported": True,
        "final_design_present": False,
        "active_component_candidate_selection": False,
        "candidate_component_matches_present": bool(candidate_count),
        "manual_review_required": True,
        "manual_review_reasons": _unique_texts(manual_reasons),
        "missing_context": missing_context,
        "route_context": {
            "route_id": _text(route_copy.get("route_id")),
            "route_type": _text(route_copy.get("route_type")),
            "route_status": _text(route_copy.get("draft_status")),
        },
        "slots": slot_matches,
        "slot_matches": slot_matches,
        "summary": {
            "slot_count": len(slot_matches),
            "slots_with_candidate_components": slots_with_candidates,
            "slots_missing_component_candidates": len(slot_matches) - slots_with_candidates,
            "candidate_component_count": candidate_count,
            "duplicate_or_alias_candidate_count": duplicate_or_alias_count,
            "out_of_scope_component_count": out_of_scope_count,
        },
        "boundary_note": MATCHER_BOUNDARY_NOTE,
    }
