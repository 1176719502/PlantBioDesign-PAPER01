from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from services.host_chassis_context_presenter import summarize_asset_host_chassis_context

ASSET_TYPES = (
    "plasmid_backbone",
    "promoter",
    "rbs_5utr",
    "terminator",
    "signal_peptide",
    "tag",
    "cds_target",
    "origin_metadata",
    "marker_metadata",
    "host_chassis_context_note",
    "literature_source_note",
)

REQUIRED_FIELDS = (
    "asset_id",
    "asset_type",
    "display_name",
    "aliases",
    "short_description",
    "organism_or_source_context",
    "sequence_available",
    "sequence_hash",
    "sequence_hash_algorithm",
    "source_notes",
    "provenance_status",
    "version_context",
    "review_status",
    "human_review_notes",
    "tags",
    "documentation_boundary_note",
)
REQUIRED_NONEMPTY_FIELDS = (
    "asset_id",
    "asset_type",
    "display_name",
    "short_description",
    "organism_or_source_context",
    "source_notes",
    "provenance_status",
    "version_context",
    "review_status",
    "human_review_notes",
    "documentation_boundary_note",
)

FORBIDDEN_BOUNDARY_TERMS = (
    "recommended",
    "best",
    "optimal",
    "validated",
    "approved",
    "compatible",
    "suitable",
    "ready for synthesis",
    "ready for wet lab",
    "experimentally confirmed",
    "prediction",
    "ranked",
    "ranking",
    "score",
    "scored",
    "optimization",
    "optimized",
    "readiness",
)

DEFAULT_SEED_PATH = Path(__file__).resolve().parents[1] / "data" / "local_design_asset_seed.json"
BUNDLED_SEED_RECORD_LABEL = "bundled seed records"
DOCUMENTATION_ONLY_REFERENCE_LABEL = "documentation-only reference records"


def load_seed_records(seed_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(seed_path) if seed_path is not None else DEFAULT_SEED_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError("seed payload must contain a records list")
    return [dict(record) for record in records]


def load_seed_catalog(seed_path: str | Path | None = None) -> dict[str, Any]:
    path = Path(seed_path) if seed_path is not None else DEFAULT_SEED_PATH
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    if not isinstance(records, list):
        raise ValueError("seed payload must contain a records list")
    metadata = {
        "seed_name": str(payload.get("seed_name") or "").strip(),
        "seed_version": str(payload.get("seed_version") or "").strip(),
        "seed_scope": str(payload.get("seed_scope") or "").strip(),
        "documentation_boundary_note": str(payload.get("documentation_boundary_note") or "").strip(),
    }
    return {
        "metadata": metadata,
        "records": [dict(record) for record in records],
    }


def validate_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in record:
            errors.append(f"missing field: {field}")
    asset_type = str(record.get("asset_type") or "")
    if asset_type not in ASSET_TYPES:
        errors.append(f"unrecognized asset_type: {asset_type}")
    if not isinstance(record.get("aliases"), list):
        errors.append("aliases must be a list")
    if not isinstance(record.get("tags"), list):
        errors.append("tags must be a list")
    if not isinstance(record.get("sequence_available"), bool):
        errors.append("sequence_available must be boolean")
    for field in REQUIRED_NONEMPTY_FIELDS:
        if not str(record.get(field) or "").strip():
            errors.append(f"{field} must not be empty")
    if str(record.get("provenance_status") or "").strip().lower() not in {"source review needed", "reviewed", "source reviewed"}:
        errors.append("provenance_status must use a recognized review status")
    if str(record.get("review_status") or "").strip().lower() not in {"human review needed", "reviewed", "human reviewed"}:
        errors.append("review_status must use a recognized review status")
    if record.get("sequence_available") is False:
        if record.get("sequence_hash") not in {"", None}:
            errors.append("sequence_hash must be empty when sequence_available is false")
        if record.get("sequence_hash_algorithm") not in {"", None}:
            errors.append("sequence_hash_algorithm must be empty when sequence_available is false")
    return errors


def validate_seed_records(records: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, record in enumerate(records):
        for error in validate_record(record):
            errors.append(f"record {index}: {error}")
    return errors


def list_assets(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted((dict(record) for record in records), key=lambda record: (str(record.get("display_name") or "").lower(), str(record.get("asset_id") or "")))


def filter_by_asset_type(records: list[dict[str, Any]], asset_type: str) -> list[dict[str, Any]]:
    expected = str(asset_type or "").strip()
    return [dict(record) for record in records if str(record.get("asset_type") or "") == expected]


def search_assets(records: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    needle = str(query or "").strip().lower()
    if not needle:
        return list_assets(records)
    matches: list[dict[str, Any]] = []
    for record in records:
        haystack = " ".join(
            [
                str(record.get("display_name") or ""),
                " ".join(str(alias) for alias in record.get("aliases", []) if alias),
                " ".join(str(tag) for tag in record.get("tags", []) if tag),
            ]
        ).lower()
        if needle in haystack:
            matches.append(dict(record))
    return sorted(matches, key=lambda record: (str(record.get("display_name") or "").lower(), str(record.get("asset_id") or "")))


ASSET_TYPE_SHORT_LABELS = {
    "plasmid_backbone": "plasmid backbone",
    "promoter": "promoter",
    "rbs_5utr": "RBS / 5' UTR",
    "terminator": "terminator",
    "signal_peptide": "signal peptide",
    "tag": "tag",
    "cds_target": "CDS target",
    "origin_metadata": "origin / replication metadata",
    "marker_metadata": "marker metadata",
    "host_chassis_context_note": "host / chassis context",
    "literature_source_note": "literature / source note",
}


def asset_type_short_label(asset_type: Any) -> str:
    key = str(asset_type or "").strip()
    return ASSET_TYPE_SHORT_LABELS.get(key, key or "asset")


def asset_selector_label(record: dict[str, Any]) -> str:
    display_name = str(record.get("display_name") or record.get("asset_id") or "Unnamed asset").strip()
    return f"{display_name} - {asset_type_short_label(record.get('asset_type'))}"


def asset_preview(record: dict[str, Any]) -> dict[str, str]:
    host_context = summarize_asset_host_chassis_context(record)
    return {
        "display_name": str(record.get("display_name") or "").strip() or "Not recorded",
        "asset_type": asset_type_short_label(record.get("asset_type")),
        "source_or_provenance_status": str(record.get("provenance_status") or "").strip() or "Not recorded",
        "review_status": str(record.get("review_status") or "").strip() or "Not recorded",
        "human_review_note": str(record.get("human_review_notes") or "").strip() or "Not recorded",
        "host_chassis_context": host_context["source_value"],
        "host_chassis_context_label": host_context["normalized_context_label"],
        "host_chassis_context_readback": host_context["readback"],
    }


def summarize_counts_by_asset_type(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(str(record.get("asset_type") or "") for record in records)
    return {asset_type: counts.get(asset_type, 0) for asset_type in ASSET_TYPES}


def summarize_review_status(records: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "source_review_needed": sum(
            1 for record in records if str(record.get("provenance_status") or "").strip().lower() == "source review needed"
        ),
        "human_review_needed": sum(
            1 for record in records if str(record.get("review_status") or "").strip().lower() == "human review needed"
        ),
    }


def report_records_missing_review(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(record)
        for record in records
        if str(record.get("provenance_status") or "").strip().lower() == "source review needed"
        or str(record.get("review_status") or "").strip().lower() == "human review needed"
    ]


def summarize_missing_review(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "source_review_needed": [
            str(record.get("asset_id") or "")
            for record in records
            if str(record.get("provenance_status") or "").strip().lower() == "source review needed"
        ],
        "human_review_needed": [
            str(record.get("asset_id") or "")
            for record in records
            if str(record.get("review_status") or "").strip().lower() == "human review needed"
        ],
    }


def summarize_catalog_inventory(records: list[dict[str, Any]]) -> dict[str, Any]:
    counts_by_type = summarize_counts_by_asset_type(records)
    review_counts = summarize_review_status(records)
    represented_source_contexts = sorted(
        {
            str(record.get("organism_or_source_context") or "").strip()
            for record in records
            if str(record.get("organism_or_source_context") or "").strip()
        },
        key=str.casefold,
    )
    version_contexts = sorted(
        {
            str(record.get("version_context") or "").strip()
            for record in records
            if str(record.get("version_context") or "").strip()
        },
        key=str.casefold,
    )
    return {
        "record_source_label": BUNDLED_SEED_RECORD_LABEL,
        "documentation_status_label": DOCUMENTATION_ONLY_REFERENCE_LABEL,
        "total_record_count": len(records),
        "asset_type_count": sum(1 for value in counts_by_type.values() if value),
        "counts_by_asset_type": counts_by_type,
        "source_review_needed_count": review_counts["source_review_needed"],
        "human_review_needed_count": review_counts["human_review_needed"],
        "represented_source_context_count": len(represented_source_contexts),
        "represented_source_contexts": represented_source_contexts,
        "version_context_count": len(version_contexts),
        "version_contexts": version_contexts,
    }


def find_forbidden_boundary_terms(records: list[dict[str, Any]]) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for record in records:
        blob = " ".join(str(record.get(field) or "") for field in REQUIRED_FIELDS).lower()
        for term in FORBIDDEN_BOUNDARY_TERMS:
            if term in blob:
                matches.append((str(record.get("asset_id") or ""), term))
    return matches
