from __future__ import annotations

from typing import Any, Iterable

from services.local_design_asset_catalog_service import list_assets, load_seed_records


DOCUMENTATION_BOUNDARY_NOTE = (
    "Component Library context is read-only recorded context for source/provenance review and manual follow-up. "
    "It is not a biological recommendation, not validation, not optimization, and not a wet-lab readiness judgment."
)

EMPTY_STATE = (
    "No Component Library context is recorded for the current Step 2 review surface. "
    "Manual follow-up is required in the existing Component Library or review surfaces before citing context in project notes."
)

GENERIC_TERMS = {
    "a",
    "and",
    "backbone",
    "context",
    "default",
    "display",
    "element",
    "family",
    "host",
    "kozak",
    "note",
    "plasmid",
    "promoter",
    "record",
    "regulatory",
    "rbs",
    "review",
    "sequence",
    "shine",
    "signal",
    "source",
    "tag",
    "terminator",
    "translation",
    "utr",
    "vector",
}

HOST_KINGDOM_CONTEXT_TERMS = {
    "prokaryote": ("bacterial", "microbial"),
    "plant_delivery": ("plant",),
    "plant_dicot": ("plant",),
    "plant_monocot": ("plant",),
    "yeast": ("yeast", "fungal"),
    "mammalian": ("mammalian", "cell"),
    "insect": ("insect",),
    "cell_free": ("cell-free", "cell free"),
}

CONTEXT_CATEGORIES = [
    {
        "key": "host_context",
        "category": "host/context",
        "asset_types": ("host_chassis_context_note",),
        "value_key": "host",
    },
    {
        "key": "promoter",
        "category": "promoter",
        "asset_types": ("promoter",),
        "value_key": "promoter",
    },
    {
        "key": "translation_initiation_context",
        "category": "RBS / Shine-Dalgarno / Kozak / translation initiation context",
        "asset_types": ("rbs_5utr",),
        "value_key": "rbs",
    },
    {
        "key": "terminator",
        "category": "terminator",
        "asset_types": ("terminator",),
        "value_key": "terminator",
    },
    {
        "key": "tag",
        "category": "tag",
        "asset_types": ("tag",),
        "value_key": "tag",
    },
    {
        "key": "signal_peptide",
        "category": "signal peptide",
        "asset_types": ("signal_peptide",),
        "value_key": "",
    },
    {
        "key": "selectable_marker",
        "category": "selectable marker",
        "asset_types": ("marker_metadata",),
        "value_key": "",
    },
    {
        "key": "reporter",
        "category": "reporter",
        "asset_types": ("marker_metadata", "cds_target"),
        "value_key": "",
        "preferred_terms": ("reporter",),
    },
    {
        "key": "vector_backbone",
        "category": "vector/backbone",
        "asset_types": ("plasmid_backbone",),
        "value_key": "vector_suggestion",
    },
]


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _text_values(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    if _text(value):
        return [_text(value)]
    return []


def _record_haystack(record: dict[str, Any]) -> str:
    values = [
        record.get("asset_id"),
        record.get("display_name"),
        record.get("asset_type"),
        record.get("short_description"),
        record.get("organism_or_source_context"),
        record.get("source_notes"),
        record.get("version_context"),
        *_text_values(record.get("aliases")),
        *_text_values(record.get("tags")),
    ]
    return " ".join(_text(value) for value in values if _text(value)).casefold()


def _tokens(value: Any) -> list[str]:
    normalized = "".join(ch.casefold() if ch.isalnum() else " " for ch in _text(value))
    return [token for token in normalized.split() if token and (token not in GENERIC_TERMS or any(ch.isdigit() for ch in token))]


def _distinctive_tokens(value: Any) -> list[str]:
    return [token for token in _tokens(value) if len(token) > 3 or any(ch.isdigit() for ch in token)]


def _record_matches_value(record: dict[str, Any], value: Any) -> bool:
    haystack = _record_haystack(record)
    normalized_value = " ".join(_tokens(value))
    if normalized_value and len(normalized_value) >= 4 and normalized_value in haystack:
        return True
    return any(token in haystack for token in _distinctive_tokens(value))


def _context_terms_for_category(category: dict[str, Any], rules: dict[str, Any]) -> tuple[str, ...]:
    if category["key"] == "host_context":
        kingdom = _text(rules.get("kingdom"))
        return HOST_KINGDOM_CONTEXT_TERMS.get(kingdom, ())
    return tuple(_text_values(category.get("preferred_terms")))


def _records_for_asset_types(records: Iterable[dict[str, Any]], asset_types: tuple[str, ...]) -> list[dict[str, Any]]:
    wanted = set(asset_types)
    return [dict(record) for record in records if _text(record.get("asset_type")) in wanted]


def _find_record(
    records: list[dict[str, Any]],
    *,
    selected_value: str,
    context_terms: tuple[str, ...],
) -> tuple[dict[str, Any] | None, str]:
    for record in records:
        if selected_value and _record_matches_value(record, selected_value):
            return record, "recorded context"
    for term in context_terms:
        for record in records:
            if term.casefold() in _record_haystack(record):
                return record, "recorded context"
    if records:
        return records[0], "manual follow-up"
    return None, "manual follow-up"


def _selected_value(category: dict[str, Any], *, host: str, tag: str, rules: dict[str, Any], elements: dict[str, Any]) -> str:
    key = category.get("value_key")
    if key == "host":
        return _text(host)
    if key == "tag":
        return "" if _text(tag).casefold() == "no tag" else _text(tag)
    if key == "promoter":
        return _text(elements.get("promoter_name") or rules.get("promoter"))
    if key == "rbs":
        return _text(elements.get("rbs_name") or rules.get("rbs"))
    if key == "terminator":
        return _text(elements.get("terminator_name") or rules.get("terminator"))
    if key == "vector_suggestion":
        return _text(rules.get("vector_suggestion"))
    return ""


def _row_for_category(
    category: dict[str, Any],
    *,
    host: str,
    tag: str,
    rules: dict[str, Any],
    elements: dict[str, Any],
    records: list[dict[str, Any]],
) -> dict[str, str]:
    selected_value = _selected_value(category, host=host, tag=tag, rules=rules, elements=elements)
    category_records = _records_for_asset_types(records, tuple(category["asset_types"]))
    record, context_state = _find_record(
        category_records,
        selected_value=selected_value,
        context_terms=_context_terms_for_category(category, rules),
    )

    if not record:
        return {
            "key": category["key"],
            "category": category["category"],
            "step2_value": selected_value or "No Step 2 value recorded",
            "context_state": "manual follow-up",
            "asset_label": "No recorded Component Library context",
            "asset_id": "",
            "recorded_context": "Component Library context is missing for this Step 2 field.",
            "source_provenance_review": "manual follow-up",
            "record_review_status": "manual follow-up",
            "sequence_metadata": "metadata not recorded",
            "manual_follow_up": "Record or link source/provenance review in the existing Component Library review surface.",
        }

    exact = context_state == "recorded context"
    return {
        "key": category["key"],
        "category": category["category"],
        "step2_value": selected_value or "No Step 2 value recorded",
        "context_state": context_state,
        "asset_label": _text(record.get("display_name"), "Unnamed Component Library asset"),
        "asset_id": _text(record.get("asset_id")),
        "recorded_context": _text(record.get("organism_or_source_context"), "recorded context not provided"),
        "source_provenance_review": _text(record.get("provenance_status"), "manual follow-up"),
        "record_review_status": _text(record.get("review_status"), "manual follow-up"),
        "sequence_metadata": "sequence metadata recorded" if record.get("sequence_available") else "sequence metadata not recorded",
        "manual_follow_up": (
            "Review the recorded source/provenance status before citing this context in project notes."
            if exact
            else "Catalog family context is available; manual follow-up is required before citing it in project notes."
        ),
    }


def _needs_source_review(row: dict[str, Any]) -> bool:
    text = _text(row.get("source_provenance_review")).casefold()
    return not text or any(
        marker in text
        for marker in (
            "manual follow-up",
            "source review needed",
            "source status not recorded",
            "source not recorded",
            "missing source",
            "not recorded",
        )
    )


def _has_incomplete_sequence_metadata(row: dict[str, Any]) -> bool:
    return "not recorded" in _text(row.get("sequence_metadata")).casefold()


def build_step2_component_library_context(
    *,
    host: str = "",
    tag: str = "",
    rules: dict[str, Any] | None = None,
    elements: dict[str, Any] | None = None,
    records: Iterable[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build read-only Component Library context rows for Expression Wizard Step 2."""
    rules = dict(rules or {})
    elements = dict(elements or {})
    try:
        catalog_records = list_assets(list(records) if records is not None else load_seed_records())
    except Exception:
        catalog_records = []

    rows = [
        _row_for_category(
            category,
            host=host,
            tag=tag,
            rules=rules,
            elements=elements,
            records=catalog_records,
        )
        for category in CONTEXT_CATEGORIES
    ]
    rows_with_assets = [row for row in rows if row.get("asset_id")]
    source_review_rows = sum(1 for row in rows if _needs_source_review(row))
    manual_follow_up_rows = sum(1 for row in rows if row.get("context_state") == "manual follow-up")
    incomplete_sequence_metadata_rows = sum(1 for row in rows if _has_incomplete_sequence_metadata(row))
    return {
        "title": "Component Library context",
        "subtitle": "Read-only recorded context for source/provenance review and manual follow-up.",
        "rows": rows,
        "rows_with_assets": rows_with_assets,
        "summary": {
            "total_rows": len(rows),
            "rows_with_recorded_assets": len(rows_with_assets),
            "source_provenance_review_rows": source_review_rows,
            "manual_follow_up_rows": manual_follow_up_rows,
            "incomplete_sequence_metadata_rows": incomplete_sequence_metadata_rows,
        },
        "empty_state": EMPTY_STATE,
        "documentation_boundary_note": DOCUMENTATION_BOUNDARY_NOTE,
    }
