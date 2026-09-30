# -*- coding: utf-8 -*-
"""
services/parts_service.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Parts-registry query helpers for the wizard UI.

This module isolates all database access for bio parts so that wizard
step files remain pure UI — they call this service instead of querying
the database directly.

Public API
----------
query_registry_parts(part_types=None, host=None, source_scope=None, group_by_type=False)
    Unified registry query contract. Returns canonical part records by
    default, optionally grouped by canonical part type.

parts_for_host(host, part_type)  -> list[dict]
    Compatibility wrapper for a host-scoped part-type query.

parts_map_for_host(host, part_types) -> dict[str, list[dict]]
    Compatibility wrapper for a grouped host-scoped query.

get_all_parts_cached(filter_type=None) -> pandas.DataFrame
    Cached view-model table used by UI pages.

canonical_parts_from_registry(filter_type=None) -> list[dict]
    Compatibility wrapper returning canonical registry records.

host_to_organism(host)           -> str
    Map a wizard host string to the organism key used in the database.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, List, Mapping, Optional

import pandas as pd
import streamlit as st

from core.database import get_all_parts, get_parts_by_organism

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Part type normalization
# ---------------------------------------------------------------------------

_PART_TYPE_ALIASES = {
    "cds": "CDS",
    "coding sequence": "CDS",
    "coding_sequence": "CDS",
    "coding-sequence": "CDS",
    "gene": "CDS",
    "gene cds": "CDS",
    "promoter": "Promoter",
    "promoter sequence": "Promoter",
    "promoter_sequence": "Promoter",
    "promoter-sequence": "Promoter",
    "rbs": "RBS",
    "ribosome binding site": "RBS",
    "ribosome-binding-site": "RBS",
    "ribosome_binding_site": "RBS",
    "shine dalgarno": "RBS",
    "shine-dalgarno": "RBS",
    "shine_dalgarno": "RBS",
    "sd sequence": "RBS",
    "sd_sequence": "RBS",
    "kozak": "RBS",
    "kozak sequence": "RBS",
    "kozak_sequence": "RBS",
    "terminator": "Terminator",
    "terminator sequence": "Terminator",
    "terminator_sequence": "Terminator",
    "terminator-sequence": "Terminator",
    "transcription terminator": "Terminator",
    "transcription_terminator": "Terminator",
    "transcription-terminator": "Terminator",
}


def normalize_part_type(part_type: Optional[str]) -> str:
    """Return the canonical part type, or a trimmed original value for unknown types."""
    text = str(part_type or "").strip()
    if not text:
        return ""
    normalized = " ".join(text.replace("_", " ").replace("-", " ").split()).lower()
    return _PART_TYPE_ALIASES.get(normalized, text)


# ---------------------------------------------------------------------------
# Host -> organism key mapping
# ---------------------------------------------------------------------------

def host_to_organism(host: str) -> str:
    """Map a wizard host display string to the organism key used in the DB.

    Parameters
    ----------
    host : str
        The host string selected in Step 2 of the Expression Wizard
        (e.g. "Rice (O. sativa)", "E.coli BL21(DE3)").

    Returns
    -------
    str
        Organism key recognised by ``get_parts_by_organism``, or the
        original *host* string when no mapping is found.
    """
    host_lower = host.lower()
    if "rice" in host_lower or "oryza" in host_lower:
        return "Rice"
    if "arabidopsis" in host_lower or "thaliana" in host_lower:
        return "Arabidopsis"
    if "coli" in host_lower or "bl21" in host_lower or "dh5" in host_lower:
        return "E.coli"
    if "tobacco" in host_lower or "nicotiana" in host_lower or "benthamiana" in host_lower:
        return "Tobacco"
    if "yeast" in host_lower or "cerevisiae" in host_lower or "pichia" in host_lower:
        return "Yeast"
    return host


def _normalise_filter_values(filter_values: Optional[Iterable[str] | str]) -> tuple[str, ...]:
    """Return a stable cache key tuple for optional part-type filters."""
    if not filter_values:
        return tuple()
    if isinstance(filter_values, str):
        return (normalize_part_type(filter_values),)
    return tuple(normalize_part_type(v) for v in filter_values)


def _first_present(row: Mapping[str, Any], *keys: str, default: Any = "") -> Any:
    """Return the first non-empty value found for any key."""
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return default


def canonical_part_record(row: Mapping[str, Any]) -> dict:
    """Convert a registry row or display record to a canonical part record."""
    raw_type = _first_present(row, "part_type", "Type", "raw_type", "canonical_type")
    sequence = str(_first_present(row, "sequence", "Sequence", "Sequence Preview"))
    name = str(_first_present(row, "name", "Name"))
    host = str(_first_present(row, "organism", "Organism", "host"))
    source = str(_first_present(row, "source", "source_type", "Source Type"))
    description = str(_first_present(row, "description", "Description"))
    length_bp = _first_present(row, "length_bp", "Length (bp)", default=len(sequence))

    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {} 
    metadata = {
        **metadata,
        "gc_content": _first_present(row, "gc_content", "GC Content (%)"),
        "function_summary": _first_present(row, "function_summary", "Function Summary"),
        "common_usage": _first_present(row, "common_usage", "Common Usage"),
        "key_features": _first_present(row, "key_features", "Key Features"),
        "recommended_pairing": _first_present(row, "recommended_pairing", "Recommended Pairing"),
        "notes": _first_present(row, "notes", "Notes"),
        "created_at": _first_present(row, "created_at", "Created At"),
    }

    record = dict(row)
    record.update(
        {
            "id": _first_present(row, "id", "ID"),
            "name": name,
            "canonical_type": normalize_part_type(raw_type),
            "raw_type": str(raw_type or ""),
            "sequence": sequence,
            "host": host,
            "source": source,
            "description": description,
            "metadata": metadata,
            "part_type": normalize_part_type(raw_type),
            "organism": host,
            "length_bp": length_bp,
        }
    )
    return record


def canonical_part_records(rows: Iterable[Mapping[str, Any]]) -> list[dict]:
    """Convert registry rows to canonical part records."""
    return [canonical_part_record(row) for row in rows]


@st.cache_data(ttl=30, show_spinner=False)
def get_all_parts_cached(filter_type: Optional[str] = None) -> pd.DataFrame:
    """Cached table query for UI pages; delegates to core.database."""
    normalized_type = normalize_part_type(filter_type) if filter_type is not None else None
    return get_all_parts(filter_type=normalized_type)



@st.cache_data(ttl=30, show_spinner=False)
def get_parts_by_organism_cached(
    organism: str,
    part_type: Optional[str] = None,
) -> list[dict]:
    """Cached host-scoped parts query for wizard flows."""
    normalized_type = normalize_part_type(part_type) if part_type is not None else None
    return get_parts_by_organism(organism, part_type=normalized_type)


@st.cache_data(ttl=30, show_spinner=False)
def get_parts_by_organism_all_cached(organism: str) -> list[dict]:
    """Cached full host-scoped parts list (all part types)."""
    return get_parts_by_organism(organism, part_type=None)


# ---------------------------------------------------------------------------
# Unified registry query
# ---------------------------------------------------------------------------

def _filter_records_by_part_types(
    records: Iterable[Mapping[str, Any]],
    part_types: Optional[Iterable[str] | str],
) -> list[dict]:
    """Filter canonical records by normalized part type values."""
    requested_types = _normalise_filter_values(part_types)
    if not requested_types:
        return [dict(record) for record in records]
    return [
        dict(record)
        for record in records
        if str(record.get("canonical_type") or "") in requested_types
    ]


def _filter_records_by_source_scope(
    records: Iterable[Mapping[str, Any]],
    source_scope: Optional[str],
) -> list[dict]:
    """Filter canonical records by existing source/source_type fields."""
    if not source_scope:
        return [dict(record) for record in records]
    expected_scope = str(source_scope).strip().lower()
    if not expected_scope:
        return [dict(record) for record in records]
    return [
        dict(record)
        for record in records
        if str(_first_present(record, "source", "source_type", "Source Type")).strip().lower()
        == expected_scope
    ]


def _group_records_by_type(records: Iterable[Mapping[str, Any]]) -> dict[str, list[dict]]:
    """Group records by canonical part type."""
    grouped: dict[str, list[dict]] = {}
    for record in records:
        pt = str(record.get("canonical_type") or record.get("part_type") or "")
        grouped.setdefault(pt, []).append(dict(record))
    return grouped


def query_registry_parts(
    part_types: Optional[Iterable[str] | str] = None,
    host: Optional[str] = None,
    source_scope: Optional[str] = None,
    group_by_type: bool = False,
    canonical: bool = True,
) -> list[dict] | dict[str, list[dict]]:
    """Query registry parts through the shared canonical query contract.

    Parameters
    ----------
    part_types : iterable[str] | str | None
        Optional part-type filter values. Values are normalized before matching.
    host : str | None
        Optional wizard host display string. When provided, the query uses the
        host-scoped registry read path.
    source_scope : str | None
        Optional filter over existing source fields.
    group_by_type : bool
        Return a mapping keyed by canonical part type when true.
    canonical : bool
        Return canonical part records by default. The false branch is retained
        only for compatibility with legacy callers.
    """
    try:
        if host:
            organism = host_to_organism(host)
            rows = get_parts_by_organism_all_cached(organism)
        else:
            requested_types = _normalise_filter_values(part_types)
            filter_type = requested_types[0] if len(requested_types) == 1 else None
            df = get_all_parts_cached(filter_type=filter_type)
            rows = [] if df.empty else df.to_dict(orient="records")

        records = canonical_part_records(rows) if canonical else [dict(row) for row in rows]
        records = _filter_records_by_part_types(records, part_types)
        records = _filter_records_by_source_scope(records, source_scope)

        if group_by_type:
            grouped = _group_records_by_type(records)
            for part_type in _normalise_filter_values(part_types):
                grouped.setdefault(part_type, [])
            return grouped
        return records
    except Exception as exc:
        logger.debug(
            "[parts_service] query_registry_parts(part_types=%r, host=%r, source_scope=%r, group_by_type=%r) failed: %s",
            part_types,
            host,
            source_scope,
            group_by_type,
            exc,
        )
        return {} if group_by_type else []


# ---------------------------------------------------------------------------
# Compatibility wrappers
# ---------------------------------------------------------------------------

def canonical_parts_from_registry(filter_type: Optional[str] = None) -> list[dict]:
    """Return registry records using the canonical part-record contract."""
    records = query_registry_parts(part_types=filter_type)
    return records if isinstance(records, list) else []


def parts_map_for_host(host: str, part_types: Optional[Iterable[str]] = None) -> dict[str, list[dict]]:
    """Return host-scoped parts grouped by part type."""
    records = query_registry_parts(host=host, part_types=part_types, group_by_type=True)
    return records if isinstance(records, dict) else {}


def parts_for_host(host: str, part_type: str) -> List[dict]:
    """Return canonical parts for a host and part type."""
    records = query_registry_parts(host=host, part_types=part_type)
    return records if isinstance(records, list) else []

