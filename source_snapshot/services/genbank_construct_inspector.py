"""Deterministic file and structural inspection for one GenBank construct record."""
from __future__ import annotations

import hashlib
from io import StringIO
from pathlib import Path
from typing import Any, Literal, TypedDict

from Bio import SeqIO

from services.canonical_construct_runtime import (
    CanonicalConstructRuntimeError,
    create_sequence_asset,
)
from services.mvp_cds_input import analyze_cds_input
from services.real_genbank_asset_import import (
    RealGenBankAssetError,
    parse_genbank_bytes,
)


INSPECTION_SCHEMA_VERSION = "bds.genbank_construct_inspection.v1"
INSPECTION_SCOPE = "file_and_structural_consistency_only"

CheckStatus = Literal["PASS", "WARN", "FAIL", "NOT_APPLICABLE"]
InspectionStatus = Literal["PASS", "PASS_WITH_WARNINGS", "FAIL"]


class InspectionCheck(TypedDict):
    check_id: str
    status: CheckStatus
    message: str
    evidence: dict[str, Any]


class GenBankConstructInspection(TypedDict):
    schema_version: str
    status: InspectionStatus
    scope: str
    record_identifier: str
    sequence_length: int
    sequence_sha256: str
    topology: str
    feature_count: int
    checks: list[InspectionCheck]
    warnings: list[str]
    errors: list[str]
    provenance: dict[str, str]


class _InspectionInputError(ValueError):
    pass


def _check(
    check_id: str,
    status: CheckStatus,
    message: str,
    evidence: dict[str, Any] | None = None,
) -> InspectionCheck:
    return {
        "check_id": check_id,
        "status": status,
        "message": message,
        "evidence": dict(evidence or {}),
    }


def _read_source(source: bytes | str | Path) -> tuple[bytes, str]:
    if isinstance(source, Path):
        try:
            return source.read_bytes(), "path"
        except OSError as exc:
            raise _InspectionInputError("The GenBank input path could not be read.") from exc
    if isinstance(source, bytes):
        return source, "bytes"
    if isinstance(source, str):
        try:
            return source.encode("utf-8"), "text"
        except UnicodeEncodeError as exc:
            raise _InspectionInputError("GenBank text must be UTF-8 encodable.") from exc
    raise _InspectionInputError("GenBank input must be bytes, text, or pathlib.Path.")


def _not_applicable_checks() -> list[InspectionCheck]:
    return [
        _check(
            check_id,
            "NOT_APPLICABLE",
            "This check was not run because the input did not pass GenBank parsing.",
        )
        for check_id in (
            "sequence_integrity",
            "topology_metadata",
            "feature_coordinates",
            "strand_metadata",
            "compound_locations",
            "canonical_intake_consistency",
            "cds_deterministic_checks",
            "qualifier_structure",
        )
    ]


def _failed_parse_result(
    *,
    input_kind: str,
    source_sha256: str,
    message: str,
    reason_code: str,
) -> GenBankConstructInspection:
    checks = [
        _check("parseability", "FAIL", message, {"reason_code": reason_code}),
        *_not_applicable_checks(),
    ]
    return {
        "schema_version": INSPECTION_SCHEMA_VERSION,
        "status": "FAIL",
        "scope": INSPECTION_SCOPE,
        "record_identifier": "",
        "sequence_length": 0,
        "sequence_sha256": "",
        "topology": "",
        "feature_count": 0,
        "checks": checks,
        "warnings": [],
        "errors": [message],
        "provenance": {
            "input_kind": input_kind,
            "source_record_sha256": source_sha256,
            "authoritative_parser": "services.real_genbank_asset_import.parse_genbank_bytes",
            "canonical_intake": "services.canonical_construct_runtime.create_sequence_asset",
            "cds_validator": "services.mvp_cds_input.analyze_cds_input",
            "sequence_mutation": "none",
        },
    }


def _coordinate_check(features: list[dict[str, Any]], sequence_length: int) -> InspectionCheck:
    invalid: list[dict[str, Any]] = []
    zero_length: list[dict[str, int]] = []
    part_count = 0
    compound_count = 0
    for feature in features:
        ordinal = int(feature["ordinal"])
        parts = list(feature.get("location_parts") or [])
        part_count += len(parts)
        if not parts:
            invalid.append(
                {
                    "feature_ordinal": ordinal,
                    "issue": "missing_location_parts",
                }
            )
            continue
        if len(parts) > 1:
            compound_count += 1
        computed_length = 0
        for part_index, part in enumerate(parts, start=1):
            start = int(part["start_zero_based"])
            end = int(part["end_zero_based_exclusive"])
            computed_length += max(0, end - start)
            if start == end:
                zero_length.append(
                    {
                        "feature_ordinal": ordinal,
                        "part_index": part_index,
                        "position_zero_based": start,
                    }
                )
            if start < 0 or end < start or end > sequence_length:
                invalid.append(
                    {
                        "feature_ordinal": ordinal,
                        "part_index": part_index,
                        "start_zero_based": start,
                        "end_zero_based_exclusive": end,
                    }
                )
        if computed_length != int(feature.get("length", 0)):
            invalid.append(
                {
                    "feature_ordinal": ordinal,
                    "issue": "parsed_feature_length_mismatch",
                    "declared_length": int(feature.get("length", 0)),
                    "computed_part_length": computed_length,
                }
            )
    evidence = {
        "coordinate_system": "zero_based_half_open",
        "feature_count": len(features),
        "location_part_count": part_count,
        "compound_feature_count": compound_count,
        "zero_length_locations": zero_length,
        "invalid_locations": invalid,
    }
    if invalid:
        return _check(
            "feature_coordinates",
            "FAIL",
            "One or more feature locations fall outside the parsed sequence or have inconsistent lengths.",
            evidence,
        )
    return _check(
        "feature_coordinates",
        "PASS",
        "All parsed feature locations are within the sequence and have consistent lengths.",
        evidence,
    )


def _strand_check(features: list[dict[str, Any]]) -> InspectionCheck:
    missing: list[int] = []
    mixed: list[int] = []
    for feature in features:
        ordinal = int(feature["ordinal"])
        parts = list(feature.get("location_parts") or [])
        if feature.get("strand") not in {-1, 1} or any(part.get("strand") not in {-1, 1} for part in parts):
            missing.append(ordinal)
        if bool(feature.get("mixed_strand")):
            mixed.append(ordinal)
    evidence = {
        "allowed_strands": [-1, 1],
        "missing_or_ambiguous_feature_ordinals": missing,
        "mixed_strand_feature_ordinals": mixed,
    }
    if missing or mixed:
        return _check(
            "strand_metadata",
            "WARN",
            "Some features have missing, ambiguous, or mixed strand metadata; their locations are preserved for review.",
            evidence,
        )
    return _check(
        "strand_metadata",
        "PASS",
        "All feature locations declare a consistent forward or reverse strand.",
        evidence,
    )


def _compound_location_check(features: list[dict[str, Any]]) -> InspectionCheck:
    compound = [int(item["ordinal"]) for item in features if len(item.get("location_parts") or []) > 1]
    crosses_origin = [int(item["ordinal"]) for item in features if bool(item.get("crosses_origin"))]
    operators = [
        {
            "feature_ordinal": int(item["ordinal"]),
            "operator": str(item.get("location_operator") or "single"),
        }
        for item in features
        if len(item.get("location_parts") or []) > 1
    ]
    return _check(
        "compound_locations",
        "PASS",
        "Compound and origin-spanning locations were retained by the authoritative parser.",
        {
            "compound_feature_ordinals": compound,
            "cross_origin_feature_ordinals": crosses_origin,
            "operators": operators,
        },
    )


def _qualifier_check(features: list[dict[str, Any]]) -> InspectionCheck:
    issues: list[dict[str, Any]] = []
    for feature in features:
        ordinal = int(feature["ordinal"])
        qualifiers = feature.get("qualifiers")
        if qualifiers is None:
            continue
        if not isinstance(qualifiers, dict):
            issues.append(
                {
                    "feature_ordinal": ordinal,
                    "issue": "malformed_qualifier_mapping",
                }
            )
            continue
        for key, values in sorted(qualifiers.items(), key=lambda item: str(item[0])):
            if not isinstance(key, str) or not key.strip():
                issues.append(
                    {
                        "feature_ordinal": ordinal,
                        "qualifier": str(key),
                        "issue": "malformed_qualifier_key",
                    }
                )
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) for value in values
            ):
                issues.append(
                    {
                        "feature_ordinal": ordinal,
                        "qualifier": str(key),
                        "issue": "malformed_qualifier_values",
                    }
                )
    if issues:
        return _check(
            "qualifier_structure",
            "WARN",
            "Some qualifier entries are not represented as valid GenBank key/list structures.",
            {"issues": issues, "issue_count": len(issues)},
        )
    return _check(
        "qualifier_structure",
        "PASS",
        "Parsed qualifier keys and list-valued entries retain GenBank structural semantics.",
        {"issue_count": 0},
    )


def _canonical_intake_check(
    raw_text: str,
    audit: dict[str, Any],
) -> tuple[InspectionCheck, dict[str, Any] | None]:
    try:
        asset = create_sequence_asset(
            project_id="genbank-construct-inspection",
            display_name=str(audit.get("record_name") or "GenBank construct"),
            raw_text=raw_text,
            molecule_type="dna",
            source_type="inspection",
            source_format="genbank",
            source_name="external-genbank-record",
            source_file_checksum=str(audit["source_record_sha256"]),
            asset_role="backbone",
        )
    except (CanonicalConstructRuntimeError, ValueError):
        return (
            _check(
                "canonical_intake_consistency",
                "FAIL",
                "The parsed record does not pass the existing canonical sequence intake adapter.",
                {"reason_code": "canonical_intake_rejected"},
            ),
            None,
        )
    except Exception:
        return (
            _check(
                "canonical_intake_consistency",
                "FAIL",
                "The existing canonical sequence intake adapter failed while inspecting the parsed record.",
                {"reason_code": "canonical_intake_failed"},
            ),
            None,
        )

    mismatches: list[str] = []
    if str(asset.get("nucleotide_sequence") or "") != str(audit.get("sequence") or ""):
        mismatches.append("sequence")
    if int(asset.get("length", 0)) != int(audit.get("length", 0)):
        mismatches.append("sequence_length")
    topology = str(audit.get("topology") or "")
    if topology in {"linear", "circular"} and str(asset.get("topology") or "") != topology:
        mismatches.append("topology")
    if len(asset.get("imported_feature_records") or []) != len(audit.get("features") or []):
        mismatches.append("feature_count")

    warnings = [str(item) for item in asset.get("warnings") or []]
    evidence = {
        "mismatches": mismatches,
        "canonical_length": int(asset.get("length", 0)),
        "canonical_topology": str(asset.get("topology") or ""),
        "canonical_feature_count": len(asset.get("imported_feature_records") or []),
        "adapter_warning_count": len(warnings),
    }
    if mismatches:
        return (
            _check(
                "canonical_intake_consistency",
                "FAIL",
                "The authoritative GenBank audit differs from the existing canonical intake projection.",
                evidence,
            ),
            asset,
        )
    if warnings:
        return (
            _check(
                "canonical_intake_consistency",
                "WARN",
                "Sequence, topology, and feature count match canonical intake; some feature detail remains review metadata.",
                evidence,
            ),
            asset,
        )
    return (
        _check(
            "canonical_intake_consistency",
            "PASS",
            "Sequence, topology, and feature count match the existing canonical intake projection.",
            evidence,
        ),
        asset,
    )


def _cds_check(raw_text: str, audit: dict[str, Any]) -> InspectionCheck:
    audit_features = list(audit.get("features") or [])
    results: list[dict[str, Any]] = []
    hash_mismatches: list[int] = []

    def _failure(
        message: str,
        reason_code: str,
        *,
        feature_ordinal: int | None = None,
    ) -> InspectionCheck:
        evidence: dict[str, Any] = {
            "reason_code": reason_code,
            "cds_feature_count": len(results),
            "hash_mismatch_feature_ordinals": hash_mismatches,
            "features": results,
        }
        if feature_ordinal is not None:
            evidence["feature_ordinal"] = feature_ordinal
        return _check("cds_deterministic_checks", "FAIL", message, evidence)

    try:
        record = next(SeqIO.parse(StringIO(raw_text), "genbank"))
    except Exception:
        return _failure(
            "The GenBank record could not be reparsed for deterministic CDS inspection.",
            "cds_record_parse_failed",
        )

    for ordinal, feature in enumerate(record.features, start=1):
        if str(feature.type).upper() != "CDS":
            continue
        try:
            extracted = str(feature.extract(record.seq)).upper()
            extracted_sha256 = hashlib.sha256(extracted.encode("ascii")).hexdigest()
        except Exception:
            return _failure(
                "A CDS feature could not be extracted by the authoritative Biopython feature extractor.",
                "feature_extraction_failed",
                feature_ordinal=ordinal,
            )
        try:
            audited = audit_features[ordinal - 1]
            if not isinstance(audited, dict):
                raise TypeError("audit feature is not a mapping")
        except (IndexError, TypeError):
            return _failure(
                "The parsed CDS feature cannot be matched to its authoritative feature audit.",
                "cds_audit_projection_failed",
                feature_ordinal=ordinal,
            )
        if extracted_sha256 != str(audited.get("sequence_sha256") or ""):
            hash_mismatches.append(ordinal)
        try:
            analysis = analyze_cds_input(
                extracted,
                source_kind="genbank_feature",
                source_name=f"feature:{ordinal}",
            )
            if not isinstance(analysis, dict):
                raise TypeError("CDS analyzer result is not a mapping")
            findings = [
                {
                    "rule_id": str(item.get("rule_id") or ""),
                    "blocking": bool(item.get("blocking")),
                }
                for item in analysis.get("findings") or []
            ]
        except Exception:
            return _failure(
                "The existing deterministic CDS analyzer failed while inspecting a CDS feature.",
                "cds_analyzer_failed",
                feature_ordinal=ordinal,
            )
        results.append(
            {
                "feature_ordinal": ordinal,
                "location_expression": str(audited.get("location_expression") or ""),
                "strand": audited.get("strand"),
                "extracted_length": len(extracted),
                "extracted_sequence_sha256": extracted_sha256,
                "validator_schema_version": str(analysis.get("schema_version") or ""),
                "blocking": bool(analysis.get("blocking")),
                "finding_count": len(findings),
                "findings": findings,
            }
        )

    evidence = {
        "cds_feature_count": len(results),
        "hash_mismatch_feature_ordinals": hash_mismatches,
        "features": results,
    }
    if not results:
        return _check(
            "cds_deterministic_checks",
            "NOT_APPLICABLE",
            "No CDS features were present; no CDS-specific check was applied.",
            evidence,
        )
    if hash_mismatches or any(bool(item["blocking"]) for item in results):
        return _check(
            "cds_deterministic_checks",
            "FAIL",
            "One or more CDS features failed the existing deterministic CDS validator or extraction-hash consistency check.",
            evidence,
        )
    if any(int(item["finding_count"]) > 0 for item in results):
        return _check(
            "cds_deterministic_checks",
            "WARN",
            "The existing deterministic CDS validator reported non-blocking review findings.",
            evidence,
        )
    return _check(
        "cds_deterministic_checks",
        "PASS",
        "All CDS features passed the existing deterministic CDS validator.",
        evidence,
    )


def inspect_genbank_construct(source: bytes | str | Path) -> GenBankConstructInspection:
    """Inspect one external GenBank record without changing its source or sequence."""
    try:
        raw_bytes, input_kind = _read_source(source)
    except _InspectionInputError as exc:
        return _failed_parse_result(
            input_kind="invalid",
            source_sha256="",
            message=str(exc),
            reason_code="invalid_input",
        )

    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    try:
        audit = parse_genbank_bytes(raw_bytes)
    except RealGenBankAssetError as exc:
        return _failed_parse_result(
            input_kind=input_kind,
            source_sha256=source_sha256,
            message=str(exc),
            reason_code="genbank_parse_rejected",
        )
    except Exception:
        return _failed_parse_result(
            input_kind=input_kind,
            source_sha256=source_sha256,
            message="The authoritative GenBank parser could not inspect the record or one of its feature locations.",
            reason_code="genbank_parser_failed",
        )

    raw_text = raw_bytes.decode("utf-8-sig")
    features = list(audit.get("features") or [])
    sequence_length = int(audit.get("length", 0))
    topology = str(audit.get("topology") or "")
    checks: list[InspectionCheck] = [
        _check(
            "parseability",
            "PASS",
            "Exactly one GenBank record was parsed by the authoritative GenBank asset adapter.",
            {
                "record_identifier": str(audit.get("accession") or ""),
                "source_record_sha256": source_sha256,
            },
        )
    ]

    canonical_check, canonical_asset = _canonical_intake_check(raw_text, audit)
    if sequence_length <= 0:
        checks.append(
            _check(
                "sequence_integrity",
                "FAIL",
                "The parsed GenBank record does not contain a nucleotide sequence.",
                {"sequence_length": sequence_length},
            )
        )
    elif canonical_asset is None:
        checks.append(
            _check(
                "sequence_integrity",
                "FAIL",
                "The sequence does not pass the existing canonical nucleotide intake rules.",
                {"sequence_length": sequence_length},
            )
        )
    else:
        checks.append(
            _check(
                "sequence_integrity",
                "PASS",
                "The parsed sequence is non-empty and passes the existing canonical nucleotide intake rules.",
                {
                    "sequence_length": sequence_length,
                    "sequence_sha256": str(audit.get("sequence_sha256") or ""),
                },
            )
        )

    if topology in {"linear", "circular"}:
        checks.append(
            _check(
                "topology_metadata",
                "PASS",
                "The GenBank record declares a supported topology.",
                {"topology": topology},
            )
        )
    else:
        checks.append(
            _check(
                "topology_metadata",
                "WARN",
                "Topology is missing or is not recognized as linear or circular.",
                {"topology": topology},
            )
        )

    checks.extend(
        [
            _coordinate_check(features, sequence_length),
            _strand_check(features),
            _compound_location_check(features),
            canonical_check,
            _cds_check(raw_text, audit),
            _qualifier_check(features),
        ]
    )

    warnings = [item["message"] for item in checks if item["status"] == "WARN"]
    errors = [item["message"] for item in checks if item["status"] == "FAIL"]
    status: InspectionStatus = "FAIL" if errors else ("PASS_WITH_WARNINGS" if warnings else "PASS")
    return {
        "schema_version": INSPECTION_SCHEMA_VERSION,
        "status": status,
        "scope": INSPECTION_SCOPE,
        "record_identifier": str(audit.get("accession") or ""),
        "sequence_length": sequence_length,
        "sequence_sha256": str(audit.get("sequence_sha256") or ""),
        "topology": topology,
        "feature_count": len(features),
        "checks": checks,
        "warnings": warnings,
        "errors": errors,
        "provenance": {
            "input_kind": input_kind,
            "source_record_sha256": source_sha256,
            "authoritative_parser": "services.real_genbank_asset_import.parse_genbank_bytes",
            "canonical_intake": "services.canonical_construct_runtime.create_sequence_asset",
            "cds_validator": "services.mvp_cds_input.analyze_cds_input",
            "feature_extraction": "Bio.SeqFeature.extract",
            "sequence_mutation": "none",
        },
    }


__all__ = [
    "GenBankConstructInspection",
    "INSPECTION_SCHEMA_VERSION",
    "INSPECTION_SCOPE",
    "InspectionCheck",
    "inspect_genbank_construct",
]
