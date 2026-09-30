"""Read-only BLAST tabular result import utilities.

This module parses user-provided BLAST tabular text that was generated
outside BioDesign Studio. It does not contact NCBI, does not run BLAST,
and does not infer experimental suitability from similarity evidence.
"""
from __future__ import annotations

import csv
import math
import re
from typing import Any

from services.sequence_verification_service import DISCLAIMER

SOURCE_LABEL = "Imported BLAST result"
MATCH_TYPE = "blast_hit"

_STANDARD_OUTFMT6_COLUMNS = [
    "query_id",
    "subject_id",
    "percent_identity",
    "alignment_length",
    "mismatches",
    "gap_opens",
    "query_start",
    "query_end",
    "subject_start",
    "subject_end",
    "e_value",
    "bitscore",
]

_COLUMN_ALIASES = {
    "query id": "query_id",
    "query_id": "query_id",
    "qseqid": "query_id",
    "query acc.ver": "query_id",
    "subject id": "subject_id",
    "subject_id": "subject_id",
    "subject accession": "subject_id",
    "subject acc.ver": "subject_id",
    "accession": "subject_id",
    "sseqid": "subject_id",
    "sacc": "subject_id",
    "pident": "percent_identity",
    "percent identity": "percent_identity",
    "% identity": "percent_identity",
    "identity": "percent_identity",
    "alignment length": "alignment_length",
    "alignment_length": "alignment_length",
    "length": "alignment_length",
    "qcovs": "coverage",
    "qcovhsp": "coverage",
    "query coverage": "coverage",
    "query cover": "coverage",
    "coverage": "coverage",
    "evalue": "e_value",
    "e-value": "e_value",
    "e value": "e_value",
    "bitscore": "bitscore",
    "bit score": "bitscore",
    "score": "bitscore",
    "stitle": "description",
    "subject title": "description",
    "description": "description",
    "title": "description",
    "organism": "organism",
    "scientific name": "organism",
    "sscinames": "organism",
    "subject sci names": "organism",
}

_REQUIRED_FIELDS = {"query_id", "subject_id", "percent_identity", "alignment_length", "e_value", "bitscore"}
_LOW_COVERAGE_THRESHOLD = 80.0
_LOW_IDENTITY_THRESHOLD = 70.0


def _safe_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def _safe_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _sort_key(hit: dict[str, Any]) -> tuple[float, float]:
    e_value = _safe_float(hit.get("e_value"))
    bitscore = _safe_float(hit.get("bitscore"))
    return (e_value if e_value is not None else math.inf, -(bitscore if bitscore is not None else -math.inf))


def _normalize_column_name(name: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(name or "").strip().lower())
    return _COLUMN_ALIASES.get(cleaned, cleaned.replace(" ", "_"))


def _split_data_line(line: str) -> list[str]:
    return next(csv.reader([line], delimiter="\t"))


def _extract_blast_fields_comment(line: str) -> list[str]:
    fields_text = line.split(":", 1)[1] if ":" in line else ""
    names = [item.strip() for item in fields_text.split(",") if item.strip()]
    return [_normalize_column_name(name) for name in names]


def _detect_header(first_values: list[str]) -> list[str] | None:
    normalized = [_normalize_column_name(value) for value in first_values]
    known_count = sum(1 for value in normalized if value in set(_COLUMN_ALIASES.values()) | _REQUIRED_FIELDS)
    if known_count >= 2:
        return normalized
    return None


def _coverage_from_alignment(alignment_length: int | None, query_length: int | None) -> float | None:
    if not alignment_length or not query_length or query_length <= 0:
        return None
    return round(min(100.0, alignment_length / query_length * 100.0), 2)


def _hit_from_row(row: dict[str, str], rank: int, query_length: int | None) -> dict[str, Any] | None:
    accession = (row.get("subject_id") or "").strip()
    percent_identity = _safe_float(row.get("percent_identity"))
    alignment_length = _safe_int(row.get("alignment_length"))
    e_value = (row.get("e_value") or "").strip()
    bitscore = _safe_float(row.get("bitscore"))

    if not accession or percent_identity is None or alignment_length is None or not e_value:
        return None

    coverage = _safe_float(row.get("coverage"))
    if coverage is None:
        coverage = _coverage_from_alignment(alignment_length, query_length)

    query_id = (row.get("query_id") or "").strip()
    description = (row.get("description") or "").strip()
    organism = (row.get("organism") or "").strip()
    alignment_summary_parts = []
    if query_id:
        alignment_summary_parts.append(f"Query {query_id}")
    alignment_summary_parts.append(f"aligned to {accession}")
    alignment_summary_parts.append(f"over {alignment_length} bp")

    return {
        "rank": rank,
        "accession": accession,
        "organism": organism,
        "description": description,
        "percent_identity": percent_identity,
        "coverage": coverage,
        "e_value": e_value,
        "bitscore": bitscore,
        "alignment_length": alignment_length,
        "alignment_summary": " ".join(alignment_summary_parts) + ".",
        "source": SOURCE_LABEL,
        "match_type": MATCH_TYPE,
    }


def parse_blast_tsv_hits(blast_text: str, query_length: int | None = None) -> list[dict[str, Any]]:
    """Parse BLAST tabular text into normalized verification hits."""
    text = str(blast_text or "")
    if not text.strip():
        return []

    columns: list[str] | None = None
    rows: list[dict[str, str]] = []
    saw_data_line = False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.lower().startswith("# fields"):
                columns = _extract_blast_fields_comment(line)
            continue

        values = _split_data_line(line)
        if not saw_data_line:
            detected_header = _detect_header(values)
            if detected_header:
                columns = detected_header
                saw_data_line = True
                continue
            saw_data_line = True

        active_columns = columns or _STANDARD_OUTFMT6_COLUMNS
        if len(values) < min(len(active_columns), len(_STANDARD_OUTFMT6_COLUMNS)):
            continue
        row = {name: values[index].strip() for index, name in enumerate(active_columns) if index < len(values)}
        rows.append(row)

    hits = [
        hit
        for index, row in enumerate(rows)
        if (hit := _hit_from_row(row, index + 1, query_length)) is not None
    ]
    hits.sort(key=_sort_key)
    for index, hit in enumerate(hits, start=1):
        hit["rank"] = index
    return hits


def _is_header_only_blast_tsv(blast_text: str) -> bool:
    data_lines = [
        line.strip()
        for line in str(blast_text or "").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return len(data_lines) == 1 and _detect_header(_split_data_line(data_lines[0])) is not None


def build_blast_import_payload(blast_text: str, query_length: int | None = None) -> dict[str, Any]:
    """Return a safe import payload for BLAST tabular text."""
    payload: dict[str, Any] = {
        "status": "no_hits",
        "hits": [],
        "top_hit": None,
        "warnings": [
            {
                "code": "INFORMATIONAL_ONLY",
                "message": DISCLAIMER,
                "severity": "info",
            }
        ],
        "disclaimer": DISCLAIMER,
    }

    try:
        hits = parse_blast_tsv_hits(blast_text, query_length=query_length)
    except Exception as exc:  # noqa: BLE001 - import boundary must be defensive
        payload["status"] = "unavailable"
        payload["warnings"].append(
            {
                "code": "REMOTE_UNAVAILABLE",
                "message": f"The imported BLAST TSV could not be parsed safely: {exc}",
                "severity": "warning",
            }
        )
        return payload

    if not hits:
        if not str(blast_text or "").strip() or _is_header_only_blast_tsv(blast_text):
            payload["warnings"].append(
                {
                    "code": "NO_HITS",
                    "message": "No BLAST tabular hits were provided for import.",
                    "severity": "info",
                }
            )
        else:
            payload["status"] = "unavailable"
            payload["warnings"].append(
                {
                    "code": "REMOTE_UNAVAILABLE",
                    "message": "The imported BLAST TSV did not contain valid tabular hit rows.",
                    "severity": "warning",
                }
            )
        return payload

    payload["status"] = "completed"
    payload["hits"] = hits
    payload["top_hit"] = hits[0]
    top_hit = hits[0]
    coverage = top_hit.get("coverage")
    identity = top_hit.get("percent_identity")
    if coverage is not None and coverage < _LOW_COVERAGE_THRESHOLD:
        payload["warnings"].append(
            {
                "code": "LOW_COVERAGE",
                "message": f"Top imported BLAST hit covers less than {_LOW_COVERAGE_THRESHOLD:.0f}% of the query sequence.",
                "severity": "warning",
            }
        )
    if identity is not None and identity < _LOW_IDENTITY_THRESHOLD:
        payload["warnings"].append(
            {
                "code": "LOW_IDENTITY",
                "message": f"Top imported BLAST hit identity is below {_LOW_IDENTITY_THRESHOLD:.0f}%.",
                "severity": "warning",
            }
        )
    return payload
