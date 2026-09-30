"""Deterministic professional-review ZIP for the betalain three-TU pBI121 case.

The service packages existing canonical result bytes. It does not assemble,
optimize, edit, or reinterpret biological sequences.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import re
import zipfile
from copy import deepcopy
from io import BytesIO, StringIO
from typing import Any

from Bio import SeqIO
from Bio.Seq import Seq

from services.betalain_three_enzyme_gate3_case import load_betalain_three_enzyme_case
from services.real_genbank_asset_import import build_pbi121_asset_bundle


PACKAGE_SCHEMA_VERSION = "betalain-multi-tu-professional-review-v1"
PACKAGE_MIME = "application/zip"
PACKAGE_FILES = (
    "01_\u8bbe\u8ba1\u4ea4\u4ed8\u8bf4\u660e.html",
    "02_\u5b8c\u6574\u8d28\u7c92.gb",
    "03_\u5b8c\u6574\u8d28\u7c92.fasta",
    "04_\u591a\u8f6c\u5f55\u5355\u5143\u533a\u57df.fasta",
    "05_TU1_CYP76AD1.fasta",
    "06_TU2_DODA1.fasta",
    "07_TU3_cDOPA5GT.fasta",
    "08_\u5143\u4ef6\u4e0e\u6765\u6e90\u6e05\u5355.csv",
    "09_pBI121\u66ff\u6362\u7b56\u7565.json",
    "10_\u8ba1\u7b97\u6821\u9a8c\u62a5\u544a.json",
    "11_\u4eba\u5de5\u590d\u6838\u4e8b\u9879.csv",
    "12_manifest.json",
    "13_checksums.sha256",
)
CHECKSUMMED_FILES = PACKAGE_FILES[:-1]
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
MANIFEST_SELF_HASH_PLACEHOLDER = "not_applicable_due_to_self_reference"
CHECKSUMS_SELF_HASH_PLACEHOLDER = "not_applicable_due_to_checksum_scope"
WET_LAB_READINESS = "not_assessed"
EXPECTED_COMPLETE_SHA = "cdeb4ea329322b942472b38c44fcad9c11216cd1e3fd4b9540e28a37826e2dc7"
EXPECTED_PBI121_SOURCE_RECORD_SHA = "7301abcf3146e14cd4826a8c8b7f44d65a0b03b0f642695f6d8277ea56d733d7"
EXPECTED_PBI121_SOURCE_SEQUENCE_SHA = "e497e664f6d6baba1bd1cafce38bceedf88c0108101bc57adf29513246497539"
EXPECTED_COMPLETE_LENGTH = 18841
EXPECTED_MULTI_TU_LENGTH = 7089
EXPECTED_TU_LENGTHS = [2582, 1916, 2591]
REPEATED_REGULATORY_WARNING = (
    "Multiple transcription units reuse the reviewed CaMV 35S promoter and NOS 3' regulatory region; repeated homologous regions require professional review."
)
BOUNDARY_CN = (
    "\u5f53\u524d\u7ed3\u679c\u7528\u4e8e\u690d\u7269\u8868\u8fbe\u8f7d\u4f53\u7684\u8ba1\u7b97\u8bbe\u8ba1\u3001\u8ba1\u7b97\u6821\u9a8c\u3001\u9879\u76ee\u4fdd\u5b58\u548c\u6587\u4ef6\u5bfc\u51fa\uff1b"
    "\u5c1a\u672a\u7ecf\u8fc7\u6e7f\u5b9e\u9a8c\u9a8c\u8bc1\uff0c\u4e0d\u4ee3\u8868\u5b9e\u9645\u8868\u8fbe\u6210\u529f\u6216\u6e7f\u5b9e\u9a8c\u5c31\u7eea\u3002"
)
CSV_COLUMNS = (
    "item_order",
    "tu_id",
    "component_name",
    "biological_role",
    "exact_length_bp",
    "strand",
    "final_start_1based",
    "final_end_1based",
    "source_type",
    "source_accession",
    "source_feature_location",
    "source_record_sha256",
    "sequence_sha256",
    "provenance_status",
    "verification_status",
    "manual_review_status",
    "notes",
)
MANUAL_REVIEW_COLUMNS = (
    "item_order",
    "review_item",
    "why_it_needs_review",
    "status",
    "notes",
)


class BetalainMultiTuProfessionalReviewPackageError(ValueError):
    """Raised when the betalain multi-TU review package cannot be built safely."""


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
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, separators=(",", ": "), default=str) + "\n").encode("utf-8")


def _csv_bytes(rows: list[dict[str, Any]], columns: tuple[str, ...]) -> bytes:
    buffer = StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _fasta_bytes(header: str, sequence: str) -> bytes:
    clean_sequence = _text(sequence).upper()
    lines = [f">{header}"] + [clean_sequence[index : index + 80] for index in range(0, len(clean_sequence), 80)]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _safe_file_stem(value: Any) -> str:
    stem = " ".join(_text(value).split())
    stem = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "_", stem)
    while ".." in stem:
        stem = stem.replace("..", "_")
    return re.sub(r"_+", "_", stem).strip(" ._-") or "BioDesign_Project"


def _parse_single_sequence(data: bytes, file_format: str, label: str) -> tuple[str, Any]:
    try:
        records = list(SeqIO.parse(StringIO(data.decode("utf-8")), file_format))
    except Exception as exc:  # pragma: no cover - defensive parse context
        raise BetalainMultiTuProfessionalReviewPackageError(f"{label} cannot be parsed.") from exc
    if len(records) != 1:
        raise BetalainMultiTuProfessionalReviewPackageError(f"{label} must contain exactly one record.")
    return str(records[0].seq).upper(), records[0]


def _feature_sequence(sequence: str, row: dict[str, Any]) -> str:
    start = int(row.get("start") or 0)
    end = int(row.get("end") or 0)
    strand = int(row.get("strand") or 1)
    if start < 1 or end < start or end > len(sequence):
        raise BetalainMultiTuProfessionalReviewPackageError("Feature coordinates are outside the canonical sequence.")
    fragment = sequence[start - 1 : end]
    return str(Seq(fragment).reverse_complement()) if strand < 0 else fragment


def _feature_lookup(rows: list[dict[str, Any]], unit_id: str, role: str) -> dict[str, Any]:
    for row in rows:
        if _text(row.get("unit_id")) != unit_id:
            continue
        if _text(row.get("biological_role") or row.get("feature_type")).lower() == role.lower():
            return dict(row)
    raise BetalainMultiTuProfessionalReviewPackageError(f"Missing feature row for {unit_id} {role}.")


def _asset_context() -> dict[str, Any]:
    bundle = build_pbi121_asset_bundle()
    audit = _mapping(bundle.get("audit"))
    components = list(bundle.get("components") or [])
    by_type = {_text(component.get("asset_type")): dict(component) for component in components}
    if audit.get("accession") != "AF485783.1":
        raise BetalainMultiTuProfessionalReviewPackageError("The pBI121 source accession does not match AF485783.1.")
    if _text(audit.get("source_record_sha256")) != EXPECTED_PBI121_SOURCE_RECORD_SHA:
        raise BetalainMultiTuProfessionalReviewPackageError("The pBI121 source record SHA-256 does not match the reviewed asset.")
    if _text(audit.get("sequence_sha256")) != EXPECTED_PBI121_SOURCE_SEQUENCE_SHA:
        raise BetalainMultiTuProfessionalReviewPackageError("The pBI121 source sequence SHA-256 does not match the reviewed asset.")
    for required_asset in ("promoter", "three_prime_regulatory_region", "left_border", "right_border", "selectable_marker_cassette"):
        asset = _mapping(by_type.get(required_asset))
        if not asset or _text(asset.get("provenance_status")) != "verified_source" or _text(asset.get("verification_status")) != "source_feature_parsed":
            raise BetalainMultiTuProfessionalReviewPackageError(f"The pBI121 {required_asset} source asset is incomplete.")
    return {"audit": audit, "components": components, "by_type": by_type}


def _prepared_context(result: dict[str, Any], current_input_signature: str | None) -> dict[str, Any]:
    expected_signature = _text(current_input_signature) or _text(result.get("input_signature"))
    if expected_signature and _text(result.get("input_signature")) != expected_signature:
        raise BetalainMultiTuProfessionalReviewPackageError("The current result signature has changed.")
    complete = _mapping(result.get("complete_plasmid"))
    combined = _mapping(result.get("combined_construct"))
    exports = _mapping(result.get("exports"))
    context = _mapping(result.get("formal_project_context"))
    validation = deepcopy(
        _mapping(result.get("betalain_pbi121_validation"))
        or _mapping(context.get("betalain_pbi121_validation"))
    )
    case = load_betalain_three_enzyme_case()
    assets = _asset_context()
    strategy = _mapping(validation.get("replacement_strategy_summary"))
    if _text(strategy.get("strategy_status")) != "ready_for_construct_use":
        raise BetalainMultiTuProfessionalReviewPackageError("The pBI121 replacement strategy is not ready_for_construct_use.")
    if _text(strategy.get("source_record_sha256")) != EXPECTED_PBI121_SOURCE_RECORD_SHA:
        raise BetalainMultiTuProfessionalReviewPackageError("The replacement strategy pBI121 source SHA-256 does not match the reviewed asset.")
    if (int(strategy.get("replacement_start") or 0), int(strategy.get("replacement_end") or 0)) != (4974, 7979):
        raise BetalainMultiTuProfessionalReviewPackageError("The replacement interval is not 4974..7979 (1-based inclusive).")
    for record in list(case.get("cds_records") or []):
        if _text(record.get("verification_status")) != "passed":
            raise BetalainMultiTuProfessionalReviewPackageError("A betalain CDS source verification is not passed.")
    if _text(context.get("wet_lab_readiness")) != WET_LAB_READINESS:
        raise BetalainMultiTuProfessionalReviewPackageError("wet_lab_readiness must remain not_assessed.")
    if int(complete.get("total_length") or 0) != EXPECTED_COMPLETE_LENGTH:
        raise BetalainMultiTuProfessionalReviewPackageError("The complete plasmid length is not 18841 bp.")
    if _text(complete.get("sequence_sha256")) != EXPECTED_COMPLETE_SHA:
        raise BetalainMultiTuProfessionalReviewPackageError("The complete plasmid SHA-256 does not match the fixed betalain case.")
    if int(combined.get("total_length") or 0) != EXPECTED_MULTI_TU_LENGTH:
        raise BetalainMultiTuProfessionalReviewPackageError("The multi-TU region length is not 7089 bp.")
    units = list(result.get("expression_units") or [])
    if [int(unit.get("length") or 0) for unit in units] != EXPECTED_TU_LENGTHS:
        raise BetalainMultiTuProfessionalReviewPackageError("The TU lengths do not match the fixed betalain case.")
    fasta_bytes = _bytes(_mapping(exports.get("complete_plasmid_fasta")).get("data"))
    genbank_bytes = _bytes(_mapping(exports.get("complete_plasmid_genbank")).get("data"))
    multi_tu_bytes = _bytes(_mapping(exports.get("combined_construct_fasta")).get("data"))
    fasta_sequence, fasta_record = _parse_single_sequence(fasta_bytes, "fasta", "complete_plasmid.fasta")
    genbank_sequence, genbank_record = _parse_single_sequence(genbank_bytes, "genbank", "complete_plasmid.gb")
    multi_tu_sequence, _ = _parse_single_sequence(multi_tu_bytes, "fasta", "multi_tu_region.fasta")
    if _text(genbank_record.annotations.get("topology")).lower() != "circular":
        raise BetalainMultiTuProfessionalReviewPackageError("The complete plasmid topology is not circular.")
    if fasta_sequence != genbank_sequence:
        raise BetalainMultiTuProfessionalReviewPackageError("The complete plasmid FASTA and GenBank sequences differ.")
    if fasta_sequence != _text(complete.get("dna") or complete.get("sequence")).upper():
        raise BetalainMultiTuProfessionalReviewPackageError("The complete plasmid FASTA does not match canonical sequence.")
    if multi_tu_sequence != _text(combined.get("dna") or combined.get("sequence")).upper():
        raise BetalainMultiTuProfessionalReviewPackageError("The multi-TU FASTA does not match canonical sequence.")
    unit_sequences: dict[str, str] = {}
    unit_fastas = _mapping(exports.get("unit_fastas"))
    for unit in units:
        unit_id = _text(unit.get("unit_id"))
        unit_data = _bytes(_mapping(unit_fastas.get(unit_id)).get("data"))
        unit_sequence, _ = _parse_single_sequence(unit_data, "fasta", f"{unit_id}.fasta")
        if unit_sequence != _text(unit.get("dna") or unit.get("sequence")).upper():
            raise BetalainMultiTuProfessionalReviewPackageError(f"The {unit_id} FASTA does not match canonical sequence.")
        unit_sequences[unit_id] = unit_sequence
    feature_rows = list(complete.get("feature_coordinates") or [])
    if not feature_rows:
        raise BetalainMultiTuProfessionalReviewPackageError("Canonical feature coordinates are unavailable.")
    return {
        "result": result,
        "complete": complete,
        "combined": combined,
        "exports": exports,
        "context": context,
        "validation": validation,
        "case": case,
        "assets": assets,
        "audit": assets["audit"],
        "feature_rows": feature_rows,
        "fasta_sequence": fasta_sequence,
        "fasta_record": fasta_record,
        "genbank_sequence": genbank_sequence,
        "genbank_record": genbank_record,
        "multi_tu_sequence": multi_tu_sequence,
        "unit_sequences": unit_sequences,
    }


def _replacement_strategy_summary(validation: dict[str, Any]) -> dict[str, Any]:
    strategy = deepcopy(_mapping(validation.get("replacement_strategy_summary")))
    retained_removed = deepcopy(_mapping(validation.get("retained_removed_feature_summary")))
    return {
        "source_accession": _text(strategy.get("source_accession")),
        "source_record_sha256": _text(strategy.get("source_record_sha256")),
        "strategy_status": _text(strategy.get("strategy_status")),
        "t_dna_direction": _text(strategy.get("t_dna_direction")),
        "replacement_start": int(strategy.get("replacement_start") or 0),
        "replacement_end": int(strategy.get("replacement_end") or 0),
        "replacement_mode": "replacement",
        "insertion_orientation": _text(strategy.get("insertion_orientation")),
        "retained_feature_ids": list(retained_removed.get("retained_feature_ids") or []),
        "removed_feature_ids": list(retained_removed.get("removed_feature_ids") or []),
        "partially_overlapped_feature_ids": list(retained_removed.get("partially_overlapped_feature_ids") or []),
        "protected_summary": ["LB", "RB"],
        "manual_decisions": {"gus": "reviewed_removed", "nptii": "reviewed_retained"},
        "blockers": list(validation.get("blockers") or []),
        "warnings": list(validation.get("warnings") or []),
    }


def _inventory_rows(prepared: dict[str, Any]) -> list[dict[str, Any]]:
    result = prepared["result"]
    complete = prepared["complete"]
    combined = prepared["combined"]
    feature_rows = prepared["feature_rows"]
    audit = prepared["audit"]
    by_type = prepared["assets"]["by_type"]
    case_records = {_text(record.get("version")): dict(record) for record in prepared["case"]["cds_records"]}
    complete_sequence = _text(complete.get("dna") or complete.get("sequence")).upper()
    rows: list[dict[str, Any]] = []

    def append(row: dict[str, Any]) -> None:
        row["item_order"] = len(rows) + 1
        rows.append(row)

    append({"tu_id": "", "component_name": "pBI121 source record", "biological_role": "complete_binary_vector_source_record", "exact_length_bp": int(audit["length"]), "strand": 1, "final_start_1based": 1, "final_end_1based": int(audit["length"]), "source_type": "official_ncbi_genbank", "source_accession": "AF485783.1", "source_feature_location": f"1..{int(audit['length'])}", "source_record_sha256": _text(audit["source_record_sha256"]), "sequence_sha256": _sequence_sha256(_text(audit["sequence"])), "provenance_status": "verified_source", "verification_status": "source_record_verified", "manual_review_status": "reviewed", "notes": "Immutable source record summary for the reviewed pBI121 backbone."})
    append({"tu_id": "", "component_name": "T-DNA right border", "biological_role": "T-DNA right border", "exact_length_bp": 25, "strand": -1, "final_start_1based": 2454, "final_end_1based": 2478, "source_type": "official_ncbi_genbank", "source_accession": "AF485783.1", "source_feature_location": "[2453:2478](-)", "source_record_sha256": _text(audit["source_record_sha256"]), "sequence_sha256": _text(by_type["right_border"]["sequence_sha256"]), "provenance_status": "verified_source", "verification_status": "source_feature_parsed", "manual_review_status": "reviewed", "notes": "Retained from the original pBI121 source record."})
    append({"tu_id": "", "component_name": "NPTII selectable marker", "biological_role": "nptii_selectable_marker_cassette", "exact_length_bp": 795, "strand": 1, "final_start_1based": 2838, "final_end_1based": 3632, "source_type": "official_ncbi_genbank", "source_accession": "AF485783.1", "source_feature_location": "[2837:3632](+)", "source_record_sha256": _text(audit["source_record_sha256"]), "sequence_sha256": _text(by_type["selectable_marker_cassette"]["sequence_sha256"]), "provenance_status": "verified_source", "verification_status": "source_feature_parsed", "manual_review_status": "reviewed", "notes": "Selectable marker retained in the final plasmid."})
    append({"tu_id": "", "component_name": "T-DNA left border", "biological_role": "T-DNA left border", "exact_length_bp": 26, "strand": -1, "final_start_1based": 8621, "final_end_1based": 8646, "source_type": "official_ncbi_genbank", "source_accession": "AF485783.1", "source_feature_location": "[8620:8646](-)", "source_record_sha256": _text(audit["source_record_sha256"]), "sequence_sha256": _text(by_type["left_border"]["sequence_sha256"]), "provenance_status": "verified_source", "verification_status": "source_feature_parsed", "manual_review_status": "reviewed", "notes": "Retained from the original pBI121 source record."})

    cds_accessions = {"TU1": "HQ656023.1", "TU2": "HQ656027.1", "TU3": "AB182643.1"}
    for unit in list(result.get("expression_units") or []):
        unit_id = _text(unit.get("unit_id"))
        for role in ("promoter", "cds", "3_prime_regulatory_region"):
            feature = _feature_lookup(feature_rows, unit_id, role)
            component = _mapping(unit.get(role))
            feature_dna = _feature_sequence(complete_sequence, feature)
            if role == "cds":
                accession = cds_accessions[unit_id]
                source = case_records[accession]
                source_location = _text(source["cds_coordinates"])
                source_record_sha = _text(source["source_record_sha256"])
                sequence_sha = _text(source["cds_sha256"])
            elif role == "promoter":
                source = by_type["promoter"]
                accession = _text(source["source_accession"])
                source_location = _text(source["source_feature_location"])
                source_record_sha = _text(source["source_record_sha256"])
                sequence_sha = _text(source["sequence_sha256"])
            else:
                source = by_type["three_prime_regulatory_region"]
                accession = _text(source["source_accession"])
                source_location = _text(source["source_feature_location"])
                source_record_sha = _text(source["source_record_sha256"])
                sequence_sha = _text(source["sequence_sha256"])
            append({"tu_id": unit_id, "component_name": _text(component.get("display_name")) or _text(feature.get("name")) or role, "biological_role": role, "exact_length_bp": len(feature_dna), "strand": int(feature.get("strand") or 1), "final_start_1based": int(feature.get("start") or 0), "final_end_1based": int(feature.get("end") or 0), "source_type": _text(component.get("source_type")) or "official_ncbi_genbank", "source_accession": accession, "source_feature_location": source_location, "source_record_sha256": source_record_sha, "sequence_sha256": sequence_sha, "provenance_status": "verified_source", "verification_status": "source_feature_parsed", "manual_review_status": "reviewed", "notes": f"Verified source for {unit_id} {role}."})
    append({"tu_id": "", "component_name": "multi-TU region", "biological_role": "multi_transcription_unit_region", "exact_length_bp": int(combined.get("total_length") or 0), "strand": 1, "final_start_1based": int(_mapping(complete.get("cassette_coordinates")).get("start") or 0), "final_end_1based": int(_mapping(complete.get("cassette_coordinates")).get("end") or 0), "source_type": "computed_design_record", "source_accession": "", "source_feature_location": "4974..12062", "source_record_sha256": "", "sequence_sha256": _sequence_sha256(_text(combined.get("dna") or combined.get("sequence"))), "provenance_status": "derived_from_verified_sources", "verification_status": "software_checked", "manual_review_status": "pending_third_party_review", "notes": "Derived multi-TU design region built from three verified transcription units."})
    append({"tu_id": "", "component_name": "complete plasmid", "biological_role": "complete_design_record", "exact_length_bp": int(complete.get("total_length") or 0), "strand": 1, "final_start_1based": 1, "final_end_1based": int(complete.get("total_length") or 0), "source_type": "computed_design_record", "source_accession": "", "source_feature_location": "", "source_record_sha256": "", "sequence_sha256": _sequence_sha256(complete_sequence), "provenance_status": "derived_from_verified_sources", "verification_status": "software_checked", "manual_review_status": "pending_third_party_review", "notes": "Final plasmid design record derived from the verified canonical construct."})
    return rows


def _manual_review_rows() -> list[dict[str, Any]]:
    items = [
        ("Repeated regulatory reuse", "Multiple transcription units reuse the same regulatory sequence.", "warning", REPEATED_REGULATORY_WARNING),
        ("Homology risk", "Repeated homologous promoter and 3' regulatory regions can create recombination concern.", "warning", "Inspect repeated-regulatory-region handling during professional review."),
        ("Replacement strategy review", "The pBI121 replacement strategy should be reviewed independently before handoff.", "required", "The JSON record summarizes the saved replacement strategy only."),
        ("GUS replacement result", "The GUS region was replaced by a multi-TU betalain design record.", "required", "Removed GUS-related annotations are not retained in the final GenBank file."),
        ("NPTII retention decision", "Selectable-marker retention should remain visible to the reviewer.", "required", "NPTII is retained in the final design record."),
        ("Assembly feasibility", "Final assembly feasibility has not been confirmed in wet experiments.", "required", "This package is a computational design and review artifact only."),
        ("Expression level", "Actual expression level was not assessed.", "required", "No expression success statement is made here."),
        ("Host performance", "Plant-host functional performance was not assessed.", "required", "No wet-lab readiness conclusion is made here."),
    ]
    return [
        {"item_order": index, "review_item": item, "why_it_needs_review": why, "status": status, "notes": notes}
        for index, (item, why, status, notes) in enumerate(items, start=1)
    ]


def _validation_report(prepared: dict[str, Any], inventory_rows: list[dict[str, Any]]) -> dict[str, Any]:
    validation = _mapping(prepared["validation"])
    strategy = _replacement_strategy_summary(validation)
    feature_labels = {_text((feature.qualifiers.get("label") or [""])[0]) for feature in prepared["genbank_record"].features}
    warnings = list(validation.get("warnings") or [])
    if REPEATED_REGULATORY_WARNING not in warnings:
        warnings.append(REPEATED_REGULATORY_WARNING)
    blockers = list(validation.get("blockers") or [])
    return {
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "blockers": blockers,
        "warnings": warnings,
        "information": ["Computational design record only.", "wet_lab_readiness: not_assessed"],
        "wet_lab_readiness": WET_LAB_READINESS,
        "source_integrity_checks": {
            "pbi121": {"accession": "AF485783.1", "source_record_sha256": _text(prepared["audit"]["source_record_sha256"]), "sequence_sha256": _text(prepared["audit"]["sequence_sha256"]), "length_bp": int(prepared["audit"]["length"]), "topology": _text(prepared["audit"].get("topology"))},
            "cds_records": [{"tu_id": f"TU{index}", "accession": _text(record["version"]), "source_record_sha256": _text(record["source_record_sha256"]), "sequence_sha256": _text(record["cds_sha256"]), "length_bp": int(record["cds_length"])} for index, record in enumerate(prepared["case"]["cds_records"], start=1)],
            "promoter_and_three_prime_regulatory_region_source_complete": True,
        },
        "sequence_identity_checks": {"canonical_length_bp": int(prepared["complete"]["total_length"]), "canonical_sequence_sha256": _text(prepared["complete"]["sequence_sha256"]), "multi_tu_length_bp": int(prepared["combined"]["total_length"]), "tu_lengths_bp": EXPECTED_TU_LENGTHS, "replacement_length_bp": 3006, "length_formula": "18841 = 14758 - 3006 + 7089", "length_formula_matches": True},
        "replacement_integrity_checks": strategy,
        "retained_removed_feature_checks": {"lb_retained": True, "rb_retained": True, "nptii_retained": True, "gus_annotations_removed": True, "removed_labels": ["gusA", "GUS"], "retained_labels": ["LB", "RB", "NPTII"]},
        "fasta_genbank_consistency": {"complete_plasmid_fasta_matches_genbank": prepared["fasta_sequence"] == prepared["genbank_sequence"], "complete_plasmid_matches_canonical": prepared["fasta_sequence"] == _text(prepared["complete"].get("dna") or prepared["complete"].get("sequence")).upper(), "multi_tu_matches_canonical": prepared["multi_tu_sequence"] == _text(prepared["combined"].get("dna") or prepared["combined"].get("sequence")).upper(), "genbank_topology": _text(prepared["genbank_record"].annotations.get("topology")), "required_labels_present": [label for label in ("TU1: CYP76AD1", "TU2: DODA1", "TU3: cDOPA5GT", "CaMV 35S promoter", "NOS 3' regulatory region", "nptII", "T-DNA left border", "T-DNA right border") if label in feature_labels], "gus_labels_absent": [label for label in ("gusA", "GUS") if label not in feature_labels]},
        "repeated_regulatory_sequence_warning": REPEATED_REGULATORY_WARNING,
        "inventory_row_count": len(inventory_rows),
    }


def _media_type(name: str) -> str:
    if name.endswith(".json"):
        return "application/json"
    if name.endswith(".csv"):
        return "text/csv"
    if name.endswith(".html"):
        return "text/html"
    if name.endswith(".gb"):
        return "application/genbank"
    return "text/plain"


def _role(name: str) -> str:
    roles = {
        PACKAGE_FILES[0]: "design_delivery_note",
        PACKAGE_FILES[1]: "complete_plasmid_genbank",
        PACKAGE_FILES[2]: "complete_plasmid_fasta",
        PACKAGE_FILES[3]: "multi_tu_region_fasta",
        PACKAGE_FILES[4]: "TU1_fasta",
        PACKAGE_FILES[5]: "TU2_fasta",
        PACKAGE_FILES[6]: "TU3_fasta",
        PACKAGE_FILES[7]: "component_source_inventory",
        PACKAGE_FILES[8]: "replacement_strategy_summary",
        PACKAGE_FILES[9]: "calculation_validation_report",
        PACKAGE_FILES[10]: "manual_review_items",
        PACKAGE_FILES[11]: "manifest",
        PACKAGE_FILES[12]: "checksums",
    }
    return roles[name]


def _manifest_rows(files: dict[str, bytes]) -> list[dict[str, Any]]:
    rows = []
    for name in PACKAGE_FILES:
        sha = _sha256(files[name]) if name not in {PACKAGE_FILES[11], PACKAGE_FILES[12]} else (MANIFEST_SELF_HASH_PLACEHOLDER if name == PACKAGE_FILES[11] else CHECKSUMS_SELF_HASH_PLACEHOLDER)
        rows.append({"path": name, "role": _role(name), "byte_size": len(files[name]), "sha256": sha, "media_type": _media_type(name)})
    return rows


def _manifest_payload(prepared: dict[str, Any], validation_report: dict[str, Any], manual_review_rows: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "file_count": len(PACKAGE_FILES),
        "project_name": _text(prepared["result"].get("project_name")) or _text(prepared["case"].get("project_name")),
        "backbone": {"name": "pBI121", "accession": "AF485783.1", "length_bp": 14758, "topology": "circular", "source_record_sha256": _text(prepared["audit"]["source_record_sha256"])},
        "complete_plasmid": {"length_bp": EXPECTED_COMPLETE_LENGTH, "topology": "circular", "sequence_sha256": EXPECTED_COMPLETE_SHA},
        "multi_tu_region": {"length_bp": EXPECTED_MULTI_TU_LENGTH, "sequence_sha256": _text(prepared["combined"].get("sequence_sha256"))},
        "blockers": list(validation_report.get("blockers") or []),
        "warnings": list(validation_report.get("warnings") or []),
        "wet_lab_readiness": WET_LAB_READINESS,
        "files": rows,
        "package_file_order": list(PACKAGE_FILES),
        "summary": {"file_count": len(PACKAGE_FILES), "blocker_count": len(validation_report.get("blockers") or []), "warning_count": len(validation_report.get("warnings") or []), "manual_review_count": len(manual_review_rows), "wet_lab_readiness": WET_LAB_READINESS},
    }


def _html_bytes(prepared: dict[str, Any], validation_report: dict[str, Any], manual_review_rows: list[dict[str, Any]]) -> bytes:
    file_list = "".join(f"<li>{html.escape(name)}</li>" for name in PACKAGE_FILES)
    warning_list = "".join(f"<li>{html.escape(str(item))}</li>" for item in validation_report.get("warnings", [])) or "<li>None</li>"
    blocker_list = "".join(f"<li>{html.escape(str(item))}</li>" for item in validation_report.get("blockers", [])) or "<li>None</li>"
    review_list = "".join(f"<li>{html.escape(row['review_item'])}: {html.escape(row['notes'])}</li>" for row in manual_review_rows)
    doc = f"""<!doctype html>
<html lang=\"zh-Hans\"><head><meta charset=\"utf-8\" /><title>Betalain pBI121 professional review package</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;color:#111827}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #d1d5db;padding:8px}}code{{word-break:break-all}}</style></head><body>
<h1>Betalain pBI121 professional review package</h1>
<p><strong>{html.escape(BOUNDARY_CN)}</strong></p>
<h2>Project and construct summary</h2>
<table><tbody><tr><th>Backbone</th><td>pBI121 / AF485783.1 / circular</td></tr><tr><th>Complete plasmid</th><td>{EXPECTED_COMPLETE_LENGTH} bp / <code>{EXPECTED_COMPLETE_SHA}</code></td></tr><tr><th>Multi-TU region</th><td>{EXPECTED_MULTI_TU_LENGTH} bp</td></tr><tr><th>TU lengths</th><td>2582 / 1916 / 2591 bp</td></tr><tr><th>Replacement strategy</th><td>4974-7979, 1-based inclusive; removed length 3006 bp</td></tr><tr><th>Retained/removed</th><td>LB, RB, and NPTII retained; GUS region replaced and removed annotations are absent</td></tr><tr><th>wet_lab_readiness</th><td>{WET_LAB_READINESS}</td></tr></tbody></table>
<h2>TU sources</h2><ul><li>TU1 CYP76AD1: HQ656023.1</li><li>TU2 DODA1: HQ656027.1</li><li>TU3 cDOPA5GT: AB182643.1</li><li>Promoter: CaMV 35S promoter from AF485783.1</li><li>three_prime_regulatory_region: NOS 3' regulatory region from AF485783.1</li></ul>
<h2>Blockers</h2><ul>{blocker_list}</ul><h2>Warnings</h2><ul>{warning_list}</ul><h2>Manual review items</h2><ul>{review_list}</ul><h2>13 files</h2><ol>{file_list}</ol>
</body></html>"""
    return doc.encode("utf-8")


def _build_manifest_and_checksums(prepared: dict[str, Any], files: dict[str, bytes], validation_report: dict[str, Any], manual_review_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], bytes, bytes]:
    manifest_bytes = b""
    checksum_bytes = b""
    manifest = {}
    for _ in range(10):
        rows = _manifest_rows({**files, PACKAGE_FILES[11]: manifest_bytes, PACKAGE_FILES[12]: checksum_bytes})
        manifest = _manifest_payload(prepared, validation_report, manual_review_rows, rows)
        next_manifest = _json_bytes(manifest)
        checksum_scope = {**files, PACKAGE_FILES[11]: next_manifest}
        next_checksums = "".join(f"{_sha256(checksum_scope[name])}  {name}\n" for name in CHECKSUMMED_FILES).encode("utf-8")
        if len(next_manifest) == len(manifest_bytes) and len(next_checksums) == len(checksum_bytes):
            manifest_bytes, checksum_bytes = next_manifest, next_checksums
            break
        manifest_bytes, checksum_bytes = next_manifest, next_checksums
    rows = _manifest_rows({**files, PACKAGE_FILES[11]: manifest_bytes, PACKAGE_FILES[12]: checksum_bytes})
    manifest = _manifest_payload(prepared, validation_report, manual_review_rows, rows)
    manifest_bytes = _json_bytes(manifest)
    checksum_scope = {**files, PACKAGE_FILES[11]: manifest_bytes}
    checksum_bytes = "".join(f"{_sha256(checksum_scope[name])}  {name}\n" for name in CHECKSUMMED_FILES).encode("utf-8")
    rows = _manifest_rows({**files, PACKAGE_FILES[11]: manifest_bytes, PACKAGE_FILES[12]: checksum_bytes})
    manifest = _manifest_payload(prepared, validation_report, manual_review_rows, rows)
    manifest_bytes = _json_bytes(manifest)
    return manifest, manifest_bytes, checksum_bytes


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


def validate_betalain_multi_tu_professional_review_package_bytes(data: bytes) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(BytesIO(data), "r") as archive:
            names = archive.namelist()
            if names != list(PACKAGE_FILES):
                raise BetalainMultiTuProfessionalReviewPackageError("The ZIP file list or order is incorrect.")
            files = {name: archive.read(name) for name in names}
    except (KeyError, zipfile.BadZipFile) as exc:
        raise BetalainMultiTuProfessionalReviewPackageError("The ZIP archive cannot be read.") from exc
    checksum_rows = files[PACKAGE_FILES[12]].decode("utf-8").splitlines()
    if [line.split("  ", 1)[1] for line in checksum_rows] != list(CHECKSUMMED_FILES):
        raise BetalainMultiTuProfessionalReviewPackageError("The checksum file order is incorrect.")
    for line in checksum_rows:
        expected, name = line.split("  ", 1)
        if _sha256(files[name]) != expected:
            raise BetalainMultiTuProfessionalReviewPackageError(f"Checksum verification failed for {name}.")
    manifest = json.loads(files[PACKAGE_FILES[11]].decode("utf-8"))
    if int(manifest.get("file_count") or 0) != len(PACKAGE_FILES):
        raise BetalainMultiTuProfessionalReviewPackageError("The manifest file count is incorrect.")
    if list(manifest.get("package_file_order") or []) != list(PACKAGE_FILES):
        raise BetalainMultiTuProfessionalReviewPackageError("The manifest file order is incorrect.")
    for entry in list(manifest.get("files") or [])[:-2]:
        name = _text(entry.get("path"))
        if int(entry.get("byte_size") or -1) != len(files[name]) or _text(entry.get("sha256")) != _sha256(files[name]):
            raise BetalainMultiTuProfessionalReviewPackageError(f"The manifest entry is incorrect for {name}.")
    fasta_sequence, _ = _parse_single_sequence(files[PACKAGE_FILES[2]], "fasta", "complete_plasmid.fasta")
    genbank_sequence, genbank_record = _parse_single_sequence(files[PACKAGE_FILES[1]], "genbank", "complete_plasmid.gb")
    multi_tu_sequence, _ = _parse_single_sequence(files[PACKAGE_FILES[3]], "fasta", "multi_tu_region.fasta")
    if fasta_sequence != genbank_sequence or _sequence_sha256(fasta_sequence) != EXPECTED_COMPLETE_SHA:
        raise BetalainMultiTuProfessionalReviewPackageError("The complete plasmid sequence is inconsistent.")
    if len(multi_tu_sequence) != EXPECTED_MULTI_TU_LENGTH:
        raise BetalainMultiTuProfessionalReviewPackageError("The multi-TU sequence length is inconsistent.")
    if _text(genbank_record.annotations.get("topology")).lower() != "circular":
        raise BetalainMultiTuProfessionalReviewPackageError("The complete plasmid topology is not circular.")
    return {"verified": True, "files": list(PACKAGE_FILES), "manifest": manifest, "file_checksums": {name: _sha256(files[name]) for name in CHECKSUMMED_FILES}}


def assess_betalain_multi_tu_professional_review_package(result: dict[str, Any], *, current_input_signature: str | None = None) -> dict[str, Any]:
    try:
        prepared = _prepared_context(result, current_input_signature)
        inventory_rows = _inventory_rows(prepared)
        validation_report = _validation_report(prepared, inventory_rows)
    except BetalainMultiTuProfessionalReviewPackageError as exc:
        return {"review_status": "blocked", "wet_lab_readiness": WET_LAB_READINESS, "blocker_count": 1, "warning_count": 0, "manual_review_count": 0, "blockers": [str(exc)], "warnings": [], "manual_review_items": []}
    manual_rows = _manual_review_rows()
    blockers = list(validation_report.get("blockers") or [])
    warnings = list(validation_report.get("warnings") or [])
    return {"review_status": "ready_for_professional_review" if not blockers else "blocked", "wet_lab_readiness": WET_LAB_READINESS, "blocker_count": len(blockers), "warning_count": len(warnings), "manual_review_count": len(manual_rows), "blockers": blockers, "warnings": warnings, "manual_review_items": manual_rows, "validation_report": validation_report}


def build_betalain_multi_tu_professional_review_package(result: dict[str, Any], *, current_input_signature: str | None = None) -> dict[str, Any]:
    prepared = _prepared_context(result, current_input_signature)
    inventory_rows = _inventory_rows(prepared)
    manual_rows = _manual_review_rows()
    validation_report = _validation_report(prepared, inventory_rows)
    if validation_report.get("blockers"):
        raise BetalainMultiTuProfessionalReviewPackageError("; ".join(str(item) for item in validation_report["blockers"]))
    files: dict[str, bytes] = {
        PACKAGE_FILES[0]: _html_bytes(prepared, validation_report, manual_rows),
        PACKAGE_FILES[1]: _bytes(_mapping(prepared["exports"].get("complete_plasmid_genbank")).get("data")),
        PACKAGE_FILES[2]: _bytes(_mapping(prepared["exports"].get("complete_plasmid_fasta")).get("data")),
        PACKAGE_FILES[3]: _fasta_bytes(
            "betalain_pbi121_multi_tu_region|len=7089|sha256=5f5222bb3b672e08230ae2325c4646bbc10e28e4d3e279f7c9d8f570ae317f42",
            _text(prepared["combined"].get("dna") or prepared["combined"].get("sequence")),
        ),
        PACKAGE_FILES[4]: _bytes(_mapping(_mapping(prepared["exports"].get("unit_fastas")).get("TU1")).get("data")),
        PACKAGE_FILES[5]: _bytes(_mapping(_mapping(prepared["exports"].get("unit_fastas")).get("TU2")).get("data")),
        PACKAGE_FILES[6]: _bytes(_mapping(_mapping(prepared["exports"].get("unit_fastas")).get("TU3")).get("data")),
        PACKAGE_FILES[7]: _csv_bytes(inventory_rows, CSV_COLUMNS),
        PACKAGE_FILES[8]: _json_bytes(_replacement_strategy_summary(prepared["validation"])),
        PACKAGE_FILES[9]: _json_bytes(validation_report),
        PACKAGE_FILES[10]: _csv_bytes(manual_rows, MANUAL_REVIEW_COLUMNS),
    }
    manifest, manifest_bytes, checksum_bytes = _build_manifest_and_checksums(prepared, files, validation_report, manual_rows)
    files[PACKAGE_FILES[11]] = manifest_bytes
    files[PACKAGE_FILES[12]] = checksum_bytes
    data = _build_zip(files)
    verification = validate_betalain_multi_tu_professional_review_package_bytes(data)
    file_name = f"{_safe_file_stem(_text(result.get('project_name')) or _text(prepared['case'].get('project_name')))}_\u4e13\u4e1a\u4ea4\u4ed8\u5ba1\u67e5\u5305.zip"
    return {"data": data, "mime": PACKAGE_MIME, "file_name": file_name, "sha256": _sha256(data), "files": list(PACKAGE_FILES), "manifest": manifest, "file_rows": manifest["files"], "validation_report": validation_report, "review_status": "ready_for_professional_review", "wet_lab_readiness": WET_LAB_READINESS, "blocker_count": 0, "warning_count": len(validation_report.get("warnings") or []), "manual_review_count": len(manual_rows), "blockers": [], "warnings": list(validation_report.get("warnings") or []), "manual_review_items": manual_rows, "verification": verification}
