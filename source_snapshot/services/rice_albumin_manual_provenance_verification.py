from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from services.plant_evidence_seed_intake import (
    DEFAULT_RICE_ALBUMIN_SEED_DIR,
    load_plant_evidence_seed_intake,
)


MANUAL_PROVENANCE_SCHEMA_VERSION = "rice_albumin_manual_provenance_verification.v2.7.r143"
MANUAL_PROVENANCE_BATCH = "v2.7-r143"
MANUAL_PROVENANCE_STATUS_READY = "manual_provenance_review_ready"
MANUAL_PROVENANCE_STATUS_FAIL_CLOSED = "manual_provenance_review_fail_closed"

DEFAULT_MANUAL_VERIFICATION_DIR = Path("E:/UBD-data-drafts/rice_albumin_manual_verification")
DEFAULT_SOURCE_REVIEW_DIR = Path("E:/UBD-data-drafts/rice_albumin_source_review")
MANUAL_STATUS_FILE = "record_by_record_verification_status.json"
EXPECTED_RICE_ALBUMIN_RECORD_COUNT = 12

DO_NOT_PROMOTE_STATUS = "do_not_promote_until_verified"
REVIEW_REQUIRED_STATUS = "needs_manual_review"

SAFE_REVIEW_CATEGORIES = (
    "local_placeholder_only",
    "missing_source_id",
    "missing_accession",
    "candidate_source_category_only",
    "requires_manual_lookup",
    "do_not_promote_until_verified",
)

ACCESSION_FIELDS = (
    "accession",
    "accession_id",
    "accession_version",
    "gene_accession",
    "protein_accession",
    "database_accession",
)

BOUNDARY_NOTE = (
    "Read-only documentation-only rice albumin manual provenance review. It preserves "
    "local seed record status, shows source and accession gaps, and keeps each record "
    "in manual review without filling identifiers or changing record standing."
)


def _text(value: Any, fallback: str = "") -> str:
    clean = str(value or "").strip()
    return clean if clean else fallback


def _missing_text(value: Any) -> bool:
    return _text(value).casefold() in {"", "missing", "not recorded", "none", "null"}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return list(value)
    return []


def _plain_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain_value(value[key]) for key in sorted(value, key=lambda item: str(item))}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [_plain_value(item) for item in value]
    return _text(value)


def _unique_texts(values: Sequence[Any]) -> list[str]:
    rows: list[str] = []
    seen: set[str] = set()
    for value in values:
        clean = _text(value)
        key = clean.casefold()
        if clean and key not in seen:
            rows.append(clean)
            seen.add(key)
    return rows


def _manual_status_path(manual_verification_dir: str | Path | None) -> Path:
    base_dir = Path(manual_verification_dir) if manual_verification_dir is not None else DEFAULT_MANUAL_VERIFICATION_DIR
    return base_dir / MANUAL_STATUS_FILE


def _load_manual_status_index(manual_verification_dir: str | Path | None) -> dict[str, Any]:
    path = _manual_status_path(manual_verification_dir)
    if not path.exists():
        return {
            "status": MANUAL_PROVENANCE_STATUS_FAIL_CLOSED,
            "path": str(path),
            "records": {},
            "warnings": [f"{MANUAL_STATUS_FILE} is missing; manual provenance review fails closed."],
        }

    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": MANUAL_PROVENANCE_STATUS_FAIL_CLOSED,
            "path": str(path),
            "records": {},
            "warnings": [
                f"{MANUAL_STATUS_FILE} could not be read as local JSON: {exc.__class__.__name__}."
            ],
        }

    payload = _mapping(raw_payload)
    raw_records = payload.get("records")
    if not isinstance(raw_records, Sequence) or isinstance(raw_records, (bytes, bytearray, str)):
        return {
            "status": MANUAL_PROVENANCE_STATUS_FAIL_CLOSED,
            "path": str(path),
            "records": {},
            "warnings": [f"{MANUAL_STATUS_FILE} has no records list; manual provenance review fails closed."],
        }

    records: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for index, raw_record in enumerate(raw_records, start=1):
        record = _mapping(raw_record)
        record_id = _text(record.get("record_id"))
        if not record_id:
            warnings.append(f"{MANUAL_STATUS_FILE} row {index} has no record_id; row ignored.")
            continue
        if record_id in records:
            warnings.append(f"{MANUAL_STATUS_FILE} repeats record_id {record_id}; later row ignored.")
            continue
        records[record_id] = record

    status = MANUAL_PROVENANCE_STATUS_READY if not warnings else MANUAL_PROVENANCE_STATUS_FAIL_CLOSED
    return {
        "status": status,
        "path": str(path),
        "records": records,
        "warnings": warnings,
    }


def _source_review_inventory(source_review_dir: str | Path | None) -> dict[str, Any]:
    base_dir = Path(source_review_dir) if source_review_dir is not None else DEFAULT_SOURCE_REVIEW_DIR
    expected_files = (
        "r131_record_source_gap_review.md",
        "manual_review_questions.md",
        "source_id_candidates.json",
        "accession_candidates.json",
    )
    existing_files = [file_name for file_name in expected_files if (base_dir / file_name).exists()]
    missing_files = [file_name for file_name in expected_files if file_name not in existing_files]
    return {
        "source_review_dir": str(base_dir),
        "available_reference_files": existing_files,
        "missing_reference_files": missing_files,
        "reference_policy": (
            "Reference files are listed only as manual review material; candidate identifiers "
            "are not copied into product seed records or this readback."
        ),
    }


def _has_accession(record: Mapping[str, Any]) -> bool:
    return any(not _missing_text(record.get(field)) for field in ACCESSION_FIELDS)


def _local_placeholder_only(record: Mapping[str, Any], manual_record: Mapping[str, Any]) -> bool:
    if manual_record.get("verified_by_local_repo_only") is True:
        return True
    source_type = _text(record.get("source_type")).casefold()
    source_id = _text(record.get("source_id")).casefold()
    return (
        source_type.startswith("local_")
        or source_type == "placeholder"
        or "services/" in source_id
        or "data/plant_synbio_knowledge/" in source_id
    )


def _missing_source_id(record: Mapping[str, Any], manual_record: Mapping[str, Any]) -> bool:
    if manual_record.get("missing_source_id") is True:
        return True
    return _missing_text(record.get("source_id"))


def _missing_accession(record: Mapping[str, Any], manual_record: Mapping[str, Any]) -> bool:
    if manual_record.get("missing_accession") is True:
        return True
    return not _has_accession(record)


def _candidate_categories(manual_record: Mapping[str, Any]) -> list[str]:
    return _unique_texts(_sequence(manual_record.get("candidate_external_source_category")))


def _requires_manual_lookup(
    record: Mapping[str, Any],
    manual_record: Mapping[str, Any],
    *,
    manual_status_available: bool,
) -> bool:
    if manual_record.get("requires_human_lookup") is True:
        return True
    if not manual_status_available:
        return True
    if _missing_source_id(record, manual_record):
        return True
    record_type = _text(record.get("record_type"))
    return record_type in {"ComponentRecord", "EvidenceRecord"} and _missing_accession(record, manual_record)


def _review_categories(
    record: Mapping[str, Any],
    manual_record: Mapping[str, Any],
    *,
    manual_status_available: bool,
) -> list[str]:
    categories: list[str] = []
    if _local_placeholder_only(record, manual_record):
        categories.append("local_placeholder_only")
    if _missing_source_id(record, manual_record):
        categories.append("missing_source_id")
    if _missing_accession(record, manual_record):
        categories.append("missing_accession")
    if _candidate_categories(manual_record):
        categories.append("candidate_source_category_only")
    if _requires_manual_lookup(record, manual_record, manual_status_available=manual_status_available):
        categories.append("requires_manual_lookup")
    categories.append(DO_NOT_PROMOTE_STATUS)
    return [category for category in SAFE_REVIEW_CATEGORIES if category in categories]


def _gap_fields(record: Mapping[str, Any], manual_record: Mapping[str, Any]) -> list[str]:
    gaps = [_text(field) for field in _sequence(record.get("gap_fields")) if _text(field)]
    if _missing_source_id(record, manual_record):
        gaps.append("source_id")
    if _missing_accession(record, manual_record):
        gaps.append("accession")
    return _unique_texts(gaps)


def _do_not_promote(manual_record: Mapping[str, Any], manual_status_available: bool) -> bool:
    if not manual_status_available:
        return True
    if not manual_record:
        return True
    if manual_record.get("must_not_be_promoted") is True:
        return True
    status_values = [_text(value).casefold() for value in _sequence(manual_record.get("status"))]
    return DO_NOT_PROMOTE_STATUS in status_values


def _review_row(
    record: Mapping[str, Any],
    manual_record: Mapping[str, Any],
    *,
    manual_status_available: bool,
) -> dict[str, Any]:
    status_values = _unique_texts(_sequence(manual_record.get("status")))
    candidate_categories = _candidate_categories(manual_record)
    missing_source_id = _missing_source_id(record, manual_record)
    missing_accession = _missing_accession(record, manual_record)
    do_not_promote = _do_not_promote(manual_record, manual_status_available)
    return _plain_value(
        {
            "record_id": _text(record.get("record_id")),
            "record_type": _text(record.get("record_type")),
            "source_file": _text(record.get("source_file")),
            "review_status": _text(record.get("review_status"), REVIEW_REQUIRED_STATUS),
            "provenance_status": _text(record.get("provenance_status"), "missing"),
            "source_type": _text(record.get("source_type"), "missing"),
            "source_id": _text(record.get("source_id"), "missing"),
            "manual_review_note": _text(record.get("manual_review_note"), "manual review required"),
            "missing_source_id": missing_source_id,
            "missing_accession": missing_accession,
            "gap_fields": _gap_fields(record, manual_record),
            "safe_review_categories": _review_categories(
                record,
                manual_record,
                manual_status_available=manual_status_available,
            ),
            "candidate_source_categories": candidate_categories,
            "requires_manual_lookup": _requires_manual_lookup(
                record,
                manual_record,
                manual_status_available=manual_status_available,
            ),
            "manual_status_values": status_values or [REVIEW_REQUIRED_STATUS, DO_NOT_PROMOTE_STATUS],
            "do_not_promote_status": DO_NOT_PROMOTE_STATUS if do_not_promote else "manual_review_required",
            "must_not_be_promoted": do_not_promote,
            "record_remains_review_required": _text(record.get("review_status")) == REVIEW_REQUIRED_STATUS,
            "record_was_promoted": False,
            "auto_filled_source_or_accession": False,
        }
    )


def _summary(rows: Sequence[Mapping[str, Any]], manual_status: Mapping[str, Any]) -> dict[str, Any]:
    record_ids = [_text(row.get("record_id")) for row in rows if _text(row.get("record_id"))]
    missing_source_ids = [_text(row.get("record_id")) for row in rows if row.get("missing_source_id") is True]
    missing_accessions = [_text(row.get("record_id")) for row in rows if row.get("missing_accession") is True]
    manual_lookup = [_text(row.get("record_id")) for row in rows if row.get("requires_manual_lookup") is True]
    do_not_promote = [_text(row.get("record_id")) for row in rows if row.get("must_not_be_promoted") is True]
    return {
        "total_records": len(record_ids),
        "expected_record_count": EXPECTED_RICE_ALBUMIN_RECORD_COUNT,
        "all_expected_records_present": len(record_ids) == EXPECTED_RICE_ALBUMIN_RECORD_COUNT,
        "all_records_need_manual_review": all(row.get("review_status") == REVIEW_REQUIRED_STATUS for row in rows),
        "all_records_do_not_promote": len(do_not_promote) == len(record_ids),
        "any_record_promoted": any(row.get("record_was_promoted") is True for row in rows),
        "any_source_or_accession_auto_filled": any(
            row.get("auto_filled_source_or_accession") is True for row in rows
        ),
        "missing_source_id_count": len(missing_source_ids),
        "missing_accession_count": len(missing_accessions),
        "manual_lookup_required_count": len(manual_lookup),
        "do_not_promote_count": len(do_not_promote),
        "records_missing_source_id": missing_source_ids,
        "records_missing_accession": missing_accessions,
        "records_requiring_manual_lookup": manual_lookup,
        "records_do_not_promote": do_not_promote,
        "manual_material_status": _text(manual_status.get("status"), MANUAL_PROVENANCE_STATUS_FAIL_CLOSED),
    }


def build_rice_albumin_manual_provenance_verification_payload(
    *,
    seed_dir: str | Path = DEFAULT_RICE_ALBUMIN_SEED_DIR,
    manual_verification_dir: str | Path | None = None,
    source_review_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Return a read-only manual provenance review payload for R131 rice albumin seed records."""
    seed_payload = load_plant_evidence_seed_intake(seed_dir)
    seed_records = [_mapping(record) for record in _sequence(seed_payload.get("records"))]
    manual_status = _load_manual_status_index(manual_verification_dir)
    manual_records = _mapping(manual_status.get("records"))
    manual_status_available = _text(manual_status.get("status")) == MANUAL_PROVENANCE_STATUS_READY

    rows = [
        _review_row(
            record,
            _mapping(manual_records.get(_text(record.get("record_id")))),
            manual_status_available=manual_status_available,
        )
        for record in seed_records
    ]

    missing_manual_rows = sorted(
        set(_text(record.get("record_id")) for record in seed_records)
        - set(str(record_id) for record_id in manual_records),
        key=str.casefold,
    )
    unknown_manual_rows = sorted(
        set(str(record_id) for record_id in manual_records)
        - set(_text(record.get("record_id")) for record in seed_records),
        key=str.casefold,
    )
    warnings = _sequence(manual_status.get("warnings"))
    if missing_manual_rows:
        warnings.append("Manual provenance status does not cover every seed record; uncovered rows fail closed.")
    if unknown_manual_rows:
        warnings.append("Manual provenance status contains records that are not in the R131 seed payload.")
    if len(seed_records) != EXPECTED_RICE_ALBUMIN_RECORD_COUNT:
        warnings.append("Seed record count differs from the R131 rice albumin expected count; review remains closed.")

    payload_status = (
        MANUAL_PROVENANCE_STATUS_READY
        if not warnings and len(seed_records) == EXPECTED_RICE_ALBUMIN_RECORD_COUNT
        else MANUAL_PROVENANCE_STATUS_FAIL_CLOSED
    )
    return _plain_value(
        {
            "workflow_schema_version": MANUAL_PROVENANCE_SCHEMA_VERSION,
            "workflow_batch": MANUAL_PROVENANCE_BATCH,
            "workflow_status": payload_status,
            "read_only": True,
            "plant_scope_only": True,
            "manual_review_required": True,
            "documentation_only_boundary": BOUNDARY_NOTE,
            "safe_review_categories": list(SAFE_REVIEW_CATEGORIES),
            "source_policy": (
                "No source IDs, literature IDs, database IDs, or accessions are filled by this workflow. "
                "Rows remain review-required until a human updates seed data in a separately scoped batch."
            ),
            "seed_source": _mapping(seed_payload.get("seed_source")),
            "manual_materials": {
                "status_file": _text(manual_status.get("path")),
                "status": _text(manual_status.get("status")),
                "missing_manual_record_ids": missing_manual_rows,
                "unknown_manual_record_ids": unknown_manual_rows,
                "source_review_inventory": _source_review_inventory(source_review_dir),
            },
            "summary": _summary(rows, manual_status),
            "records": rows,
            "warnings": warnings + _sequence(seed_payload.get("warnings")),
        }
    )


def build_rice_albumin_manual_provenance_readback_rows(
    payload: Mapping[str, Any] | None = None,
    *,
    seed_dir: str | Path = DEFAULT_RICE_ALBUMIN_SEED_DIR,
    manual_verification_dir: str | Path | None = None,
    source_review_dir: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Return UI/report-safe row dicts for the R143 manual provenance review."""
    source = _mapping(payload) or build_rice_albumin_manual_provenance_verification_payload(
        seed_dir=seed_dir,
        manual_verification_dir=manual_verification_dir,
        source_review_dir=source_review_dir,
    )
    rows: list[dict[str, Any]] = []
    for record in _sequence(source.get("records")):
        row = _mapping(record)
        rows.append(
            {
                "record_id": _text(row.get("record_id")),
                "record_type": _text(row.get("record_type")),
                "review_status": _text(row.get("review_status"), REVIEW_REQUIRED_STATUS),
                "provenance_status": _text(row.get("provenance_status"), "missing"),
                "source_type": _text(row.get("source_type"), "missing"),
                "source_id": _text(row.get("source_id"), "missing"),
                "missing_source_id": row.get("missing_source_id") is True,
                "missing_accession": row.get("missing_accession") is True,
                "review_categories": _sequence(row.get("safe_review_categories")),
                "manual_action": (
                    "manual lookup required"
                    if row.get("requires_manual_lookup") is True
                    else "manual record check required"
                ),
                "do_not_promote_status": _text(row.get("do_not_promote_status"), DO_NOT_PROMOTE_STATUS),
                "manual_review_note": _text(row.get("manual_review_note"), "manual review required"),
            }
        )
    return _plain_value(rows)
