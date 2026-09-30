"""Deterministic professional-review ZIP for generic multi-TU constructs.

This service packages existing canonical snapshots and export bytes. It does not
assemble, alter, optimize, or reinterpret biological sequences.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from io import BytesIO, StringIO
from typing import Any

from Bio import SeqIO
from Bio.Seq import Seq

from services.canonical_construct_runtime import (
    CanonicalConstructRuntimeError,
    active_complete_plasmid_snapshot,
    active_construct_snapshot,
)
from services.mvp_multi_tu_runtime import export_multi_tu_outputs
from services.professional_review_delivery_package import (
    REVIEW_BLOCKED,
    REVIEW_NEEDS_PROVENANCE,
    REVIEW_READY,
    WET_LAB_READINESS,
)


PACKAGE_VERSION = "multi-tu-professional-review-v1"
PACKAGE_MIME = "application/zip"
PACKAGE_FILES = (
    "README.md",
    "manifest.json",
    "complete_plasmid.fasta",
    "complete_plasmid.gb",
    "multi_tu_region.fasta",
    "unit_fastas.json",
    "construct_summary.json",
    "component_inventory.csv",
    "provenance_review.csv",
    "manual_review_items.csv",
    "validation_report.json",
    "checksums.sha256",
)
PAYLOAD_FILES = tuple(name for name in PACKAGE_FILES if name not in {"manifest.json", "checksums.sha256"})
CHECKSUM_FILES = tuple(name for name in PACKAGE_FILES if name != "checksums.sha256")
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

COMPONENT_INVENTORY_COLUMNS = (
    "item_order",
    "unit_id",
    "unit_order",
    "unit_display_name",
    "component_name",
    "biological_role",
    "component_type",
    "length_bp",
    "complete_start_1_based",
    "complete_end_1_based",
    "multi_tu_start_1_based",
    "multi_tu_end_1_based",
    "strand",
    "source_type",
    "source_name",
    "provenance_reference",
    "sequence_sha256",
)
PROVENANCE_REVIEW_COLUMNS = (
    "asset_name",
    "unit_id",
    "biological_role",
    "source_type",
    "source_name",
    "source_description",
    "provenance_reference",
    "sequence_length_bp",
    "sequence_sha256",
    "review_status",
    "missing_information",
    "professional_review_items",
)
MANUAL_REVIEW_COLUMNS = (
    "item_order",
    "review_item",
    "status",
    "notes",
)


class MultiTuProfessionalReviewPackageError(ValueError):
    """Raised when a multi-TU review ZIP cannot be built or verified."""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bytes(value: Any) -> bytes:
    return value if isinstance(value, bytes) else str(value or "").encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sequence_sha256(sequence: str) -> str:
    return _sha256(_text(sequence).upper().encode("ascii"))


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, separators=(",", ": "), default=str)
        + "\n"
    ).encode("utf-8")


def _csv_bytes(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _safe_file_stem(value: Any) -> str:
    stem = " ".join(_text(value).split())
    stem = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", stem)
    while ".." in stem:
        stem = stem.replace("..", "_")
    return re.sub(r"_+", "_", stem).strip(" ._-") or "BioDesign_Project"


def _parse_single_sequence(data: bytes, file_format: str, label: str) -> tuple[str, Any]:
    try:
        records = list(SeqIO.parse(StringIO(data.decode("utf-8")), file_format))
    except Exception as exc:  # pragma: no cover - parser exception context
        raise MultiTuProfessionalReviewPackageError(f"{label} cannot be parsed.") from exc
    if len(records) != 1:
        raise MultiTuProfessionalReviewPackageError(f"{label} must contain exactly one sequence record.")
    return str(records[0].seq).upper(), records[0]


def _feature_sequence(sequence: str, row: dict[str, Any]) -> str:
    parts = list(row.get("location_parts") or [])
    if not parts:
        parts = [{"start": row.get("start"), "end": row.get("end"), "strand": row.get("strand", 1)}]
    fragments: list[str] = []
    for part in parts:
        start = int(part.get("start") or 0)
        end = int(part.get("end") or 0)
        if start < 1 or end < start or end > len(sequence):
            raise MultiTuProfessionalReviewPackageError("Feature coordinates are outside the canonical sequence.")
        fragment = sequence[start - 1 : end]
        if int(part.get("strand") or row.get("strand") or 1) < 0:
            fragment = str(Seq(fragment).reverse_complement())
        fragments.append(fragment)
    if int(row.get("strand") or 1) < 0 and len(parts) > 1:
        fragments.reverse()
    return "".join(fragments)


def _finding_detail(item: dict[str, Any]) -> str:
    return _text(item.get("message") or item.get("explanation") or item.get("rule_id"))


def _blocking_findings(snapshot: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    for raw in list(snapshot.get("validation_findings") or []):
        item = _mapping(raw)
        severity = _text(item.get("severity")).lower()
        if bool(item.get("blocking")) or severity == "error":
            messages.append(_finding_detail(item) or "Canonical runtime returned a blocking finding.")
    declared = int(_mapping(snapshot.get("validation_summary")).get("blocking_count") or 0)
    if declared and not messages:
        messages.append(f"Canonical runtime records {declared} blocking finding(s).")
    return messages


def _unit_lookup(units: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {_text(unit.get("unit_id")): _mapping(unit) for unit in units}


def _asset_lookup(runtime: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _text(asset.get("asset_id")): _mapping(asset)
        for asset in list(runtime.get("sequence_assets") or [])
    }


def _component_lookup(runtime: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        _text(component.get("component_id")): _mapping(component)
        for component in list(runtime.get("components") or [])
    }


def _prepared_context(result: dict[str, Any], current_input_signature: str | None) -> dict[str, Any]:
    expected_signature = _text(current_input_signature) or _text(result.get("input_signature"))
    if expected_signature and _text(result.get("input_signature")) != expected_signature:
        raise MultiTuProfessionalReviewPackageError("The current multi-TU result signature has changed.")
    context = _mapping(result.get("formal_project_context"))
    if _text(context.get("construct_review_status")) == "needs_review":
        raise MultiTuProfessionalReviewPackageError("The project definition changed; regenerate or review the construct before packaging.")
    units = [_mapping(unit) for unit in list(result.get("expression_units") or [])]
    if len(units) < 2:
        raise MultiTuProfessionalReviewPackageError("The generic multi-TU review package requires at least two transcription units.")
    try:
        cassette = active_construct_snapshot(result.get("runtime"))
        plasmid = active_complete_plasmid_snapshot(result.get("runtime"))
    except CanonicalConstructRuntimeError as exc:
        raise MultiTuProfessionalReviewPackageError("No current canonical multi-TU construct is available.") from exc
    if _text(cassette.get("construct_status")) != "current" or _text(plasmid.get("construct_status")) != "current":
        raise MultiTuProfessionalReviewPackageError("The canonical multi-TU construct is stale or computationally blocked.")
    blocking = [*_blocking_findings(cassette), *_blocking_findings(plasmid)]
    if blocking:
        raise MultiTuProfessionalReviewPackageError("; ".join(blocking))
    combined = _mapping(result.get("combined_construct"))
    complete = _mapping(result.get("complete_plasmid"))
    combined_sequence = _text(combined.get("dna") or combined.get("sequence") or cassette.get("sequence")).upper()
    complete_sequence = _text(complete.get("dna") or complete.get("sequence") or plasmid.get("sequence")).upper()
    if not combined_sequence or not complete_sequence:
        raise MultiTuProfessionalReviewPackageError("The canonical multi-TU or complete-plasmid sequence is empty.")
    if combined_sequence != _text(cassette.get("sequence")).upper():
        raise MultiTuProfessionalReviewPackageError("The result multi-TU sequence does not match the canonical runtime.")
    if complete_sequence != _text(plasmid.get("sequence")).upper():
        raise MultiTuProfessionalReviewPackageError("The result complete-plasmid sequence does not match the canonical runtime.")
    exports = _mapping(result.get("exports"))
    if not exports:
        try:
            exports = export_multi_tu_outputs(result.get("runtime"), project_name=_text(result.get("project_name")))
        except Exception as exc:  # pragma: no cover - defensive fallback
            raise MultiTuProfessionalReviewPackageError("The current multi-TU exports are unavailable.") from exc
    fasta_bytes = _bytes(_mapping(exports.get("complete_plasmid_fasta")).get("data"))
    genbank_bytes = _bytes(_mapping(exports.get("complete_plasmid_genbank")).get("data"))
    multi_tu_bytes = _bytes(_mapping(exports.get("combined_construct_fasta")).get("data"))
    if not fasta_bytes or not genbank_bytes or not multi_tu_bytes:
        raise MultiTuProfessionalReviewPackageError("The multi-TU result is missing FASTA or GenBank export bytes.")
    fasta_sequence, fasta_record = _parse_single_sequence(fasta_bytes, "fasta", "complete plasmid FASTA")
    genbank_sequence, genbank_record = _parse_single_sequence(genbank_bytes, "genbank", "complete plasmid GenBank")
    multi_tu_sequence, multi_tu_record = _parse_single_sequence(multi_tu_bytes, "fasta", "multi-TU FASTA")
    if fasta_sequence != complete_sequence or genbank_sequence != complete_sequence:
        raise MultiTuProfessionalReviewPackageError("Complete-plasmid FASTA, GenBank, and canonical sequence differ.")
    if multi_tu_sequence != combined_sequence:
        raise MultiTuProfessionalReviewPackageError("Multi-TU FASTA and canonical multi-TU sequence differ.")
    unit_fasta_records: dict[str, dict[str, Any]] = {}
    unit_fastas = _mapping(exports.get("unit_fastas"))
    for unit in sorted(units, key=lambda item: int(item.get("order") or 0)):
        unit_id = _text(unit.get("unit_id"))
        export_record = _mapping(unit_fastas.get(unit_id))
        data = _bytes(export_record.get("data"))
        if not data:
            raise MultiTuProfessionalReviewPackageError(f"The {unit_id} canonical FASTA export is missing.")
        sequence, _record = _parse_single_sequence(data, "fasta", f"{unit_id} FASTA")
        if sequence != _text(unit.get("dna") or unit.get("sequence")).upper():
            raise MultiTuProfessionalReviewPackageError(f"The {unit_id} FASTA and canonical unit sequence differ.")
        unit_fasta_records[unit_id] = {
            "file_name": _text(export_record.get("file_name")) or f"{unit_id}.fasta",
            "mime": _text(export_record.get("mime")) or "text/plain",
            "data": data,
            "sequence_sha256": _sequence_sha256(sequence),
            "length_bp": len(sequence),
        }
    return {
        "result": result,
        "context": context,
        "units": units,
        "cassette": cassette,
        "plasmid": plasmid,
        "combined": combined,
        "complete": complete,
        "exports": exports,
        "fasta_bytes": fasta_bytes,
        "genbank_bytes": genbank_bytes,
        "multi_tu_bytes": multi_tu_bytes,
        "fasta_record": fasta_record,
        "genbank_record": genbank_record,
        "multi_tu_record": multi_tu_record,
        "unit_fasta_records": unit_fasta_records,
        "combined_sequence": combined_sequence,
        "complete_sequence": complete_sequence,
        "sequence_consistency": {
            "status": "consistent",
            "complete_plasmid_length_bp": len(complete_sequence),
            "multi_tu_length_bp": len(combined_sequence),
            "complete_plasmid_sha256": _sequence_sha256(complete_sequence),
            "multi_tu_sha256": _sequence_sha256(combined_sequence),
            "unit_count": len(units),
        },
    }


def _source_review_for_asset(asset: dict[str, Any]) -> tuple[str, str, str]:
    source_type = _text(asset.get("source_type")) or "not_provided"
    source_name = _text(asset.get("source_name"))
    source_description = _text(asset.get("source_description"))
    provenance = _text(asset.get("provenance_reference"))
    missing: list[str] = []
    review: list[str] = []
    if source_type in {"test_fixture", "example", "demo"}:
        missing.append("Replace fixture or example source with a traceable source record before external review.")
        review.append("Confirm whether this fixture source is acceptable for the review record.")
    elif not source_name and not provenance and not source_description:
        missing.append("Source reference is not recorded.")
        review.append("Record source file, accession, or local library reference.")
    else:
        review.append("Check source/provenance record against the sequence used in the canonical construct.")
    status = "pending" if missing else "recorded"
    return status, "; ".join(dict.fromkeys(missing)), "; ".join(dict.fromkeys(review))


def _provenance_rows(prepared: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    runtime = _mapping(prepared["cassette"].get("runtime"))
    assets = _asset_lookup(runtime)
    components = _component_lookup(runtime)
    unit_by_id = _unit_lookup(prepared["units"])
    rows: list[dict[str, Any]] = []
    gaps: list[dict[str, str]] = []
    seen_assets: set[str] = set()
    for raw in list(runtime.get("expression_units") or []):
        runtime_unit = _mapping(raw)
        unit_id = _text(runtime_unit.get("unit_id"))
        source_unit = unit_by_id.get(unit_id, {})
        for role in ("promoter", "targeting_sequence", "cds", "linker", "fusion_tag", "3_prime_regulatory_region"):
            ref = _mapping(runtime_unit.get(role))
            component = components.get(_text(ref.get("component_id")), {})
            asset = assets.get(_text(ref.get("sequence_asset_id") or component.get("sequence_asset_id")), {})
            asset_id = _text(asset.get("asset_id"))
            if not asset_id or asset_id in seen_assets:
                continue
            seen_assets.add(asset_id)
            sequence = _text(asset.get("nucleotide_sequence")).upper()
            status, missing, review = _source_review_for_asset(asset)
            role_input = _mapping(source_unit.get(role))
            row = {
                "asset_name": _text(asset.get("display_name")) or _text(role_input.get("display_name")) or role,
                "unit_id": unit_id,
                "biological_role": role,
                "source_type": _text(asset.get("source_type")) or _text(role_input.get("source_type")) or "not_provided",
                "source_name": _text(asset.get("source_name")) or _text(role_input.get("source_name")),
                "source_description": _text(asset.get("source_description")) or _text(role_input.get("source_description")),
                "provenance_reference": _text(asset.get("provenance_reference")) or _text(role_input.get("provenance_reference")),
                "sequence_length_bp": len(sequence),
                "sequence_sha256": _sequence_sha256(sequence),
                "review_status": status,
                "missing_information": missing,
                "professional_review_items": review,
            }
            rows.append(row)
            if missing:
                gaps.append({"asset_name": row["asset_name"], "unit_id": unit_id, "missing_information": missing})
    backbone_id = _text(prepared["plasmid"].get("backbone_asset_id"))
    backbone = assets.get(backbone_id, {})
    if backbone:
        sequence = _text(backbone.get("nucleotide_sequence")).upper()
        status, missing, review = _source_review_for_asset(backbone)
        row = {
            "asset_name": _text(backbone.get("display_name")) or "Backbone",
            "unit_id": "",
            "biological_role": "backbone",
            "source_type": _text(backbone.get("source_type")) or "not_provided",
            "source_name": _text(backbone.get("source_name")),
            "source_description": _text(backbone.get("source_description")),
            "provenance_reference": _text(backbone.get("provenance_reference")),
            "sequence_length_bp": len(sequence),
            "sequence_sha256": _sequence_sha256(sequence),
            "review_status": status,
            "missing_information": missing,
            "professional_review_items": review,
        }
        rows.append(row)
        if missing:
            gaps.append({"asset_name": row["asset_name"], "unit_id": "", "missing_information": missing})
    return rows, gaps


def _component_inventory_rows(prepared: dict[str, Any], provenance_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plasmid = prepared["plasmid"]
    complete_sequence = _text(plasmid.get("sequence")).upper()
    cassette_start = int(_mapping(prepared["complete"].get("cassette_coordinates") or plasmid.get("cassette_coordinates")).get("start") or 0)
    unit_by_id = _unit_lookup(prepared["units"])
    source_by_unit_role = {
        (_text(row.get("unit_id")), _text(row.get("biological_role"))): row
        for row in provenance_rows
    }
    source_by_role = {_text(row.get("biological_role")): row for row in provenance_rows if not _text(row.get("unit_id"))}
    rows: list[dict[str, Any]] = []
    for raw in list(plasmid.get("feature_rows") or []):
        row = _mapping(raw)
        source_scope = _text(row.get("source"))
        component_type = _text(row.get("component_type"))
        role = _text(row.get("biological_role") or row.get("feature_type") or component_type) or "misc_feature"
        unit_id = _text(row.get("unit_id"))
        if source_scope != "transcription_unit" and component_type == "transcription_unit":
            continue
        source = source_by_unit_role.get((unit_id, role), source_by_role.get("backbone", {}))
        feature_sequence = _feature_sequence(complete_sequence, row)
        complete_start = int(row.get("start") or 0)
        complete_end = int(row.get("end") or 0)
        multi_start = complete_start - cassette_start + 1 if source_scope == "transcription_unit" and cassette_start else 0
        multi_end = complete_end - cassette_start + 1 if source_scope == "transcription_unit" and cassette_start else 0
        unit = unit_by_id.get(unit_id, {})
        rows.append(
            {
                "item_order": len(rows) + 1,
                "unit_id": unit_id,
                "unit_order": int(unit.get("order") or 0),
                "unit_display_name": _text(unit.get("display_name") or unit.get("unit_name")),
                "component_name": _text(row.get("name")) or role,
                "biological_role": role,
                "component_type": component_type,
                "length_bp": len(feature_sequence),
                "complete_start_1_based": complete_start,
                "complete_end_1_based": complete_end,
                "multi_tu_start_1_based": multi_start,
                "multi_tu_end_1_based": multi_end,
                "strand": int(row.get("strand") or 1),
                "source_type": _text(source.get("source_type")) or "not_provided",
                "source_name": _text(source.get("source_name")),
                "provenance_reference": _text(source.get("provenance_reference")),
                "sequence_sha256": _sequence_sha256(feature_sequence),
            }
        )
    if not rows:
        raise MultiTuProfessionalReviewPackageError("Feature coordinates are unavailable for the multi-TU review package.")
    return rows


def _manual_review_rows(prepared: dict[str, Any], provenance_gaps: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for unit in sorted(prepared["units"], key=lambda item: int(item.get("order") or 0)):
        if _text(unit.get("provenance_state")) != "current":
            rows.append(
                {
                    "review_item": f"{_text(unit.get('unit_id'))} source/provenance review",
                    "status": _text(unit.get("provenance_state")) or "review_required",
                    "notes": "Review source records for this transcription unit before external handoff.",
                }
            )
    repeated_roles: dict[str, int] = {}
    for row in _component_inventory_rows_for_repeats(prepared):
        key = f"{row['biological_role']}:{row['sequence_sha256']}"
        repeated_roles[key] = repeated_roles.get(key, 0) + 1
    if any(count > 1 for count in repeated_roles.values()):
        rows.append(
            {
                "review_item": "Repeated sequence use across transcription units",
                "status": "manual_review_required",
                "notes": "Repeated component sequences across transcription units should remain visible for professional review.",
            }
        )
    for gap in provenance_gaps:
        rows.append(
            {
                "review_item": f"Missing provenance: {_text(gap.get('asset_name'))}",
                "status": "source_review_needed",
                "notes": _text(gap.get("missing_information")),
            }
        )
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        identity = (_text(row.get("review_item")), _text(row.get("notes")))
        if identity in seen:
            continue
        seen.add(identity)
        row = dict(row)
        row["item_order"] = len(unique) + 1
        unique.append(row)
    return unique


def _component_inventory_rows_for_repeats(prepared: dict[str, Any]) -> list[dict[str, Any]]:
    runtime = _mapping(prepared["cassette"].get("runtime"))
    assets = _asset_lookup(runtime)
    rows: list[dict[str, Any]] = []
    for raw in list(runtime.get("expression_units") or []):
        unit = _mapping(raw)
        for role in ("promoter", "targeting_sequence", "cds", "linker", "fusion_tag", "3_prime_regulatory_region"):
            ref = _mapping(unit.get(role))
            asset = assets.get(_text(ref.get("sequence_asset_id")), {})
            sequence = _text(asset.get("nucleotide_sequence")).upper()
            if sequence:
                rows.append({"biological_role": role, "sequence_sha256": _sequence_sha256(sequence)})
    return rows


def _review_status(provenance_gaps: list[dict[str, str]], manual_rows: list[dict[str, Any]]) -> str:
    return REVIEW_NEEDS_PROVENANCE if provenance_gaps or manual_rows else REVIEW_READY


def _construct_summary(prepared: dict[str, Any], review_status: str) -> dict[str, Any]:
    result = prepared["result"]
    complete = prepared["complete"]
    combined = prepared["combined"]
    return {
        "project_type": _text(result.get("project_type")),
        "project_id": _text(result.get("project_id")),
        "project_name": _text(result.get("project_name")),
        "unit_order": list(result.get("unit_order") or [_text(unit.get("unit_id")) for unit in prepared["units"]]),
        "transcription_units": [
            {
                "unit_id": _text(unit.get("unit_id")),
                "order": int(unit.get("order") or 0),
                "display_name": _text(unit.get("display_name") or unit.get("unit_name")),
                "orientation": _text(unit.get("orientation")),
                "length_bp": int(unit.get("length") or 0),
                "sequence_sha256": _text(unit.get("sequence_sha256")),
                "range": _mapping(unit.get("range")),
                "provenance_state": _text(unit.get("provenance_state")),
            }
            for unit in sorted(prepared["units"], key=lambda item: int(item.get("order") or 0))
        ],
        "multi_tu_region": {
            "length_bp": int(combined.get("total_length") or len(prepared["combined_sequence"])),
            "sequence_sha256": _text(combined.get("sequence_sha256")) or _sequence_sha256(prepared["combined_sequence"]),
        },
        "complete_plasmid": {
            "length_bp": int(complete.get("total_length") or len(prepared["complete_sequence"])),
            "topology": _text(prepared["plasmid"].get("topology")),
            "sequence_sha256": _text(complete.get("sequence_sha256")) or _sequence_sha256(prepared["complete_sequence"]),
            "cassette_coordinates": _mapping(complete.get("cassette_coordinates") or prepared["plasmid"].get("cassette_coordinates")),
        },
        "review_status": review_status,
        "wet_lab_readiness": WET_LAB_READINESS,
    }


def _validation_report(prepared: dict[str, Any], review_status: str, manual_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "package_version": PACKAGE_VERSION,
        "review_status": review_status,
        "wet_lab_readiness": WET_LAB_READINESS,
        "blocking": [],
        "manual_review_items": manual_rows,
        "passed_software_checks": [
            {"check_id": "canonical_multi_tu_current", "message": "Current canonical multi-TU region is available."},
            {"check_id": "complete_plasmid_current", "message": "Current canonical complete plasmid is available."},
            {"check_id": "sequence_exports_consistent", "message": "FASTA, GenBank, unit FASTA, and canonical sequences are consistent."},
        ],
        "sequence_consistency": prepared["sequence_consistency"],
        "boundary": (
            "This package is a computational design and review record for plant expression vector review. "
            "It is not an experimental validation record, expression success claim, or wet-lab readiness conclusion."
        ),
    }


def _unit_fastas_payload(prepared: dict[str, Any]) -> dict[str, Any]:
    records = {}
    for unit in sorted(prepared["units"], key=lambda item: int(item.get("order") or 0)):
        unit_id = _text(unit.get("unit_id"))
        export_record = prepared["unit_fasta_records"][unit_id]
        data = export_record["data"]
        records[unit_id] = {
            "file_name": export_record["file_name"],
            "mime": export_record["mime"],
            "length_bp": export_record["length_bp"],
            "sequence_sha256": export_record["sequence_sha256"],
            "fasta": data.decode("utf-8"),
        }
    return {"unit_count": len(records), "records": records}


def _readme_bytes(project_name: str, review_status: str, manual_count: int) -> bytes:
    lines = [
        "# BioDesign Studio Multi-TU Professional Review Package",
        "",
        f"- Project name: {project_name}",
        f"- Review status: `{review_status}`",
        f"- wet_lab_readiness: `{WET_LAB_READINESS}`",
        f"- Manual review items: {manual_count}",
        "",
        "## Boundary",
        "",
        "This ZIP is a documentation-only design and review record for plant expression vector review.",
        "It records canonical sequence exports, component coordinates, source/provenance notes, and software consistency checks.",
        "It does not provide experimental validation, expression success claims, wet-lab readiness conclusions, or automatic biological recommendations.",
        "",
        "## Files",
        "",
        *[f"- `{name}`" for name in PACKAGE_FILES],
        "",
    ]
    return "\n".join(lines).encode("utf-8")


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    return info


def _build_zip(files: dict[str, bytes]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9, strict_timestamps=True) as archive:
        for name in PACKAGE_FILES:
            archive.writestr(_zip_info(name), files[name], compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    return output.getvalue()


def validate_multi_tu_professional_review_package_bytes(data: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(BytesIO(data), "r") as archive:
            names = archive.namelist()
            if names != list(PACKAGE_FILES) or len(set(names)) != len(names):
                raise MultiTuProfessionalReviewPackageError("The ZIP file list or order is incorrect.")
            files = {name: archive.read(name) for name in names}
    except (zipfile.BadZipFile, KeyError) as exc:
        raise MultiTuProfessionalReviewPackageError("The ZIP archive cannot be read.") from exc
    checksum_lines = files["checksums.sha256"].decode("utf-8").splitlines()
    if len(checksum_lines) != len(CHECKSUM_FILES):
        raise MultiTuProfessionalReviewPackageError("The checksum file has the wrong number of entries.")
    checksum_names: list[str] = []
    for line in checksum_lines:
        expected, name = line.split("  ", 1)
        checksum_names.append(name)
        if name not in files or _sha256(files[name]) != expected:
            raise MultiTuProfessionalReviewPackageError(f"Checksum verification failed for {name}.")
    if checksum_names != list(CHECKSUM_FILES):
        raise MultiTuProfessionalReviewPackageError("The checksum file order is incorrect.")
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    if list(manifest.get("package_file_order") or []) != list(PACKAGE_FILES):
        raise MultiTuProfessionalReviewPackageError("The manifest file order is incorrect.")
    payload_entries = list(manifest.get("payload_files") or [])
    if [entry.get("name") for entry in payload_entries] != list(PAYLOAD_FILES):
        raise MultiTuProfessionalReviewPackageError("The manifest payload list is incorrect.")
    for entry in payload_entries:
        name = _text(entry.get("name"))
        if int(entry.get("size_bytes") or -1) != len(files[name]):
            raise MultiTuProfessionalReviewPackageError(f"The manifest size is incorrect for {name}.")
        if _text(entry.get("sha256")) != _sha256(files[name]):
            raise MultiTuProfessionalReviewPackageError(f"The manifest checksum is incorrect for {name}.")
    fasta_sequence, _ = _parse_single_sequence(files["complete_plasmid.fasta"], "fasta", "complete plasmid FASTA")
    genbank_sequence, _ = _parse_single_sequence(files["complete_plasmid.gb"], "genbank", "complete plasmid GenBank")
    multi_tu_sequence, _ = _parse_single_sequence(files["multi_tu_region.fasta"], "fasta", "multi-TU FASTA")
    if fasta_sequence != genbank_sequence:
        raise MultiTuProfessionalReviewPackageError("Complete-plasmid FASTA and GenBank sequences differ.")
    if _sequence_sha256(fasta_sequence) != _text(manifest.get("complete_plasmid", {}).get("sequence_sha256")):
        raise MultiTuProfessionalReviewPackageError("The complete plasmid sequence does not match the manifest hash.")
    if _sequence_sha256(multi_tu_sequence) != _text(manifest.get("multi_tu_region", {}).get("sequence_sha256")):
        raise MultiTuProfessionalReviewPackageError("The multi-TU sequence does not match the manifest hash.")
    try:
        unit_fastas = json.loads(files["unit_fastas.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise MultiTuProfessionalReviewPackageError("unit_fastas.json cannot be parsed.") from exc
    unit_records = _mapping(unit_fastas.get("records"))
    if int(unit_fastas.get("unit_count") or -1) != len(unit_records):
        raise MultiTuProfessionalReviewPackageError("unit_fastas.json unit count is inconsistent.")
    if int(manifest.get("unit_count") or -1) != len(unit_records):
        raise MultiTuProfessionalReviewPackageError("unit_fastas.json does not match the manifest unit count.")
    for unit_id, raw_record in sorted(unit_records.items()):
        unit_record = _mapping(raw_record)
        unit_sequence, _ = _parse_single_sequence(
            _text(unit_record.get("fasta")).encode("utf-8"), "fasta", f"{unit_id} FASTA"
        )
        if int(unit_record.get("length_bp") or -1) != len(unit_sequence):
            raise MultiTuProfessionalReviewPackageError(
                f"The {unit_id} FASTA length does not match unit_fastas.json."
            )
        if _sequence_sha256(unit_sequence) != _text(unit_record.get("sequence_sha256")):
            raise MultiTuProfessionalReviewPackageError(
                f"The {unit_id} FASTA sequence hash does not match unit_fastas.json."
            )
    return {
        "verified": True,
        "files": list(PACKAGE_FILES),
        "manifest": manifest,
        "file_checksums": {name: _sha256(files[name]) for name in CHECKSUM_FILES},
    }


def _package_context(result: dict[str, Any], current_input_signature: str | None) -> dict[str, Any]:
    prepared = _prepared_context(result, current_input_signature)
    provenance_rows, provenance_gaps = _provenance_rows(prepared)
    manual_rows = _manual_review_rows(prepared, provenance_gaps)
    review_status = _review_status(provenance_gaps, manual_rows)
    inventory_rows = _component_inventory_rows(prepared, provenance_rows)
    return {
        **prepared,
        "provenance_rows": provenance_rows,
        "provenance_gaps": provenance_gaps,
        "manual_review_items": manual_rows,
        "review_status": review_status,
        "inventory_rows": inventory_rows,
    }


def assess_multi_tu_professional_review_package(
    result: dict[str, Any], *, current_input_signature: str | None = None
) -> dict[str, Any]:
    """Assess gates without creating ZIP bytes."""
    try:
        prepared = _package_context(result, current_input_signature)
    except MultiTuProfessionalReviewPackageError as exc:
        return {
            "review_status": REVIEW_BLOCKED,
            "wet_lab_readiness": WET_LAB_READINESS,
            "blocking_count": 1,
            "blocker_count": 1,
            "provenance_gap_count": 0,
            "manual_review_count": 0,
            "blocking_reasons": [str(exc)],
            "blockers": [str(exc)],
            "provenance_gaps": [],
            "manual_review_items": [],
        }
    return {
        "review_status": prepared["review_status"],
        "wet_lab_readiness": WET_LAB_READINESS,
        "blocking_count": 0,
        "blocker_count": 0,
        "provenance_gap_count": len(prepared["provenance_gaps"]),
        "manual_review_count": len(prepared["manual_review_items"]),
        "blocking_reasons": [],
        "blockers": [],
        "provenance_gaps": prepared["provenance_gaps"],
        "manual_review_items": prepared["manual_review_items"],
        "sequence_consistency": prepared["sequence_consistency"],
        "file_count": len(PACKAGE_FILES),
    }


def build_multi_tu_professional_review_package(
    result: dict[str, Any], *, current_input_signature: str | None = None
) -> dict[str, Any]:
    """Build a deterministic, flat multi-TU professional-review ZIP."""
    prepared = _package_context(result, current_input_signature)
    project_name = _text(result.get("project_name")) or "BioDesign Multi-TU Project"
    review_status = prepared["review_status"]
    validation_report = _validation_report(prepared, review_status, prepared["manual_review_items"])
    files: dict[str, bytes] = {
        "README.md": _readme_bytes(project_name, review_status, len(prepared["manual_review_items"])),
        "complete_plasmid.fasta": prepared["fasta_bytes"],
        "complete_plasmid.gb": prepared["genbank_bytes"],
        "multi_tu_region.fasta": prepared["multi_tu_bytes"],
        "unit_fastas.json": _json_bytes(_unit_fastas_payload(prepared)),
        "construct_summary.json": _json_bytes(_construct_summary(prepared, review_status)),
        "component_inventory.csv": _csv_bytes(prepared["inventory_rows"], COMPONENT_INVENTORY_COLUMNS),
        "provenance_review.csv": _csv_bytes(prepared["provenance_rows"], PROVENANCE_REVIEW_COLUMNS),
        "manual_review_items.csv": _csv_bytes(prepared["manual_review_items"], MANUAL_REVIEW_COLUMNS),
        "validation_report.json": _json_bytes(validation_report),
    }
    manifest = {
        "package_version": PACKAGE_VERSION,
        "project_id": _text(result.get("project_id")),
        "project_name": project_name,
        "project_type": _text(result.get("project_type")),
        "review_status": review_status,
        "wet_lab_readiness": WET_LAB_READINESS,
        "unit_count": len(prepared["units"]),
        "complete_plasmid": {
            "length_bp": len(prepared["complete_sequence"]),
            "topology": _text(prepared["plasmid"].get("topology")),
            "sequence_sha256": _sequence_sha256(prepared["complete_sequence"]),
        },
        "multi_tu_region": {
            "length_bp": len(prepared["combined_sequence"]),
            "sequence_sha256": _sequence_sha256(prepared["combined_sequence"]),
        },
        "snapshot_version": {
            "complete_plasmid_revision": _text(prepared["plasmid"].get("revision_id")),
            "multi_tu_revision": _text(prepared["cassette"].get("revision_id")),
            "input_signature": _text(result.get("input_signature")),
        },
        "package_file_order": list(PACKAGE_FILES),
        "payload_files": [
            {"name": name, "size_bytes": len(files[name]), "sha256": _sha256(files[name])}
            for name in PAYLOAD_FILES
        ],
        "summary": {
            "blocking_count": 0,
            "provenance_gap_count": len(prepared["provenance_gaps"]),
            "manual_review_count": len(prepared["manual_review_items"]),
            "wet_lab_readiness": WET_LAB_READINESS,
        },
    }
    files["manifest.json"] = _json_bytes(manifest)
    files["checksums.sha256"] = "".join(
        f"{_sha256(files[name])}  {name}\n" for name in CHECKSUM_FILES
    ).encode("utf-8")
    data = _build_zip(files)
    verification = validate_multi_tu_professional_review_package_bytes(data)
    return {
        "data": data,
        "mime": PACKAGE_MIME,
        "file_name": f"{_safe_file_stem(project_name)}_multi_tu_professional_review_package.zip",
        "project_name": project_name,
        "files": list(PACKAGE_FILES),
        "file_checksums": verification["file_checksums"],
        "sha256": _sha256(data),
        "manifest": manifest,
        "review_status": review_status,
        "wet_lab_readiness": WET_LAB_READINESS,
        "blocking_count": 0,
        "blocker_count": 0,
        "provenance_gap_count": len(prepared["provenance_gaps"]),
        "manual_review_count": len(prepared["manual_review_items"]),
        "provenance_gaps": prepared["provenance_gaps"],
        "manual_review_items": prepared["manual_review_items"],
        "validation_report": validation_report,
        "verification": verification,
    }
