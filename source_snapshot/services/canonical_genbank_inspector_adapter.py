"""Read-only binding from canonical GenBank exports to the construct inspector."""
from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any, Literal, TypedDict

from services.genbank_construct_inspector import (
    GenBankConstructInspection,
    inspect_genbank_construct,
)


ADAPTER_SCHEMA_VERSION = "bds.canonical_genbank_inspection_adapter.v1"
AUTHORITATIVE_GENBANK_SOURCE = "canonical_export.genbank.data"
AUTHORITATIVE_IDENTITY_SOURCE = "canonical_runtime.active_construct_snapshot"

_CONSTRUCT_ID_PATTERN = re.compile(r"construct-[0-9a-f]{32}")
_REVISION_ID_PATTERN = re.compile(r"rev-[0-9a-f]{16}")

AdapterStatus = Literal["PASS", "PASS_WITH_WARNINGS", "FAIL"]


class CanonicalGenBankInspection(TypedDict):
    schema_version: str
    status: AdapterStatus
    inspection: GenBankConstructInspection | None
    identity_binding: dict[str, Any]
    errors: list[str]
    provenance: dict[str, Any]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _result(
    *,
    status: AdapterStatus,
    inspection: GenBankConstructInspection | None,
    identity_binding: dict[str, Any],
    errors: list[str],
    source_sha256: str = "",
    source_kind: str = "",
    file_name: str = "",
) -> CanonicalGenBankInspection:
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "status": status,
        "inspection": inspection,
        "identity_binding": identity_binding,
        "errors": errors,
        "provenance": {
            "authoritative_genbank_source": AUTHORITATIVE_GENBANK_SOURCE,
            "authoritative_identity_source": AUTHORITATIVE_IDENTITY_SOURCE,
            "inspector": "services.genbank_construct_inspector.inspect_genbank_construct",
            "source_sha256": source_sha256,
            "source_kind": source_kind,
            "file_name": file_name,
            "sequence_mutation": "none",
            "canonical_state_mutation": "none",
        },
    }


def _invalid_payload(message: str) -> CanonicalGenBankInspection:
    return _result(
        status="FAIL",
        inspection=None,
        identity_binding={"status": "FAIL", "checks": []},
        errors=[message],
    )


def _valid_construct_id(value: str) -> bool:
    return _CONSTRUCT_ID_PATTERN.fullmatch(value) is not None


def _valid_revision_id(value: str) -> bool:
    return _REVISION_ID_PATTERN.fullmatch(value) is not None


def inspect_canonical_genbank_export(
    canonical_export: Mapping[str, Any],
    *,
    expected_construct_id: str | None = None,
    expected_revision_id: str | None = None,
) -> CanonicalGenBankInspection:
    """Inspect canonical GenBank output against current runtime identity.

    The adapter never constructs, serializes, repairs, or normalizes GenBank. It
    passes the canonical export bytes directly to the existing read-only
    inspector. Callers must independently obtain the expected construct and
    revision identifiers from the current canonical runtime snapshot; GenBank
    bytes alone do not prove construct or revision identity.
    """
    if not isinstance(canonical_export, Mapping):
        return _invalid_payload("Canonical export payload must be a mapping.")

    authoritative_construct_id = _text(expected_construct_id)
    authoritative_revision_id = _text(expected_revision_id)
    authority_errors: list[str] = []
    if not authoritative_construct_id:
        authority_errors.append("Expected canonical construct identity is missing.")
    elif not _valid_construct_id(authoritative_construct_id):
        authority_errors.append("Expected canonical construct identity is malformed.")
    if not authoritative_revision_id:
        authority_errors.append("Expected canonical revision identity is missing.")
    elif not _valid_revision_id(authoritative_revision_id):
        authority_errors.append("Expected canonical revision identity is malformed.")
    if authority_errors:
        return _result(
            status="FAIL",
            inspection=None,
            identity_binding={
                "status": "FAIL",
                "authoritative_construct_id": authoritative_construct_id,
                "authoritative_revision_id": authoritative_revision_id,
                "checks": [],
            },
            errors=authority_errors,
        )

    genbank = _mapping(canonical_export.get("genbank"))
    metadata = _mapping(canonical_export.get("metadata"))
    if not genbank:
        return _invalid_payload("Canonical export payload is missing genbank output.")
    if not metadata:
        return _invalid_payload("Canonical export payload is missing canonical metadata.")

    data = genbank.get("data")
    if isinstance(data, bytes):
        raw_bytes = data
        source_kind = "bytes"
    elif isinstance(data, str):
        try:
            raw_bytes = data.encode("utf-8")
        except UnicodeEncodeError:
            return _invalid_payload("Canonical GenBank output must be UTF-8 encodable.")
        source_kind = "text"
    else:
        return _invalid_payload("Canonical GenBank output must be bytes or text.")
    if not raw_bytes:
        return _invalid_payload("Canonical GenBank output is empty.")

    expected_length = metadata.get("sequence_length")
    expected_checksum = _text(metadata.get("sequence_checksum")).lower()
    record_id = _text(metadata.get("record_id"))
    export_construct_id = _text(metadata.get("construct_id"))
    export_revision_id = _text(metadata.get("revision_id"))
    expected_topology = _text(metadata.get("topology")).lower()
    file_name = _text(genbank.get("file_name"))

    metadata_errors: list[str] = []
    if isinstance(expected_length, bool) or not isinstance(expected_length, int) or expected_length <= 0:
        metadata_errors.append("Canonical sequence length metadata is missing or invalid.")
    if not re.fullmatch(r"[0-9a-f]{64}", expected_checksum):
        metadata_errors.append("Canonical sequence checksum metadata is missing or invalid.")
    if not export_construct_id:
        metadata_errors.append("Canonical export construct identity metadata is missing.")
    elif not _valid_construct_id(export_construct_id):
        metadata_errors.append("Canonical export construct identity metadata is malformed.")
    if not export_revision_id:
        metadata_errors.append("Canonical export revision identity metadata is missing.")
    elif not _valid_revision_id(export_revision_id):
        metadata_errors.append("Canonical export revision identity metadata is malformed.")
    if expected_topology and expected_topology not in {"linear", "circular"}:
        metadata_errors.append("Canonical topology metadata is invalid.")
    if metadata_errors:
        return _result(
            status="FAIL",
            inspection=None,
            identity_binding={
                "status": "FAIL",
                "canonical_record_id": record_id,
                "authoritative_construct_id": authoritative_construct_id,
                "authoritative_revision_id": authoritative_revision_id,
                "export_construct_id": export_construct_id,
                "export_revision_id": export_revision_id,
                "checks": [],
            },
            errors=metadata_errors,
            source_sha256=hashlib.sha256(raw_bytes).hexdigest(),
            source_kind=source_kind,
            file_name=file_name,
        )

    inspection = inspect_genbank_construct(raw_bytes)
    source_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    checks = [
        {
            "check_id": "construct_id",
            "matches": export_construct_id == authoritative_construct_id,
            "authority": authoritative_construct_id,
            "export_metadata": export_construct_id,
        },
        {
            "check_id": "revision_id",
            "matches": export_revision_id == authoritative_revision_id,
            "authority": authoritative_revision_id,
            "export_metadata": export_revision_id,
        },
        {
            "check_id": "inspector_acceptance",
            "matches": inspection["status"] != "FAIL",
            "canonical": "parseable_and_structurally_consistent",
            "genbank": inspection["status"],
        },
        {
            "check_id": "source_byte_identity",
            "matches": inspection["provenance"].get("source_record_sha256") == source_sha256,
            "canonical": source_sha256,
            "genbank": inspection["provenance"].get("source_record_sha256", ""),
        },
        {
            "check_id": "sequence_length",
            "matches": inspection["sequence_length"] == expected_length,
            "canonical": expected_length,
            "genbank": inspection["sequence_length"],
        },
        {
            "check_id": "sequence_sha256",
            "matches": inspection["sequence_sha256"] == expected_checksum,
            "canonical": expected_checksum,
            "genbank": inspection["sequence_sha256"],
        },
        {
            "check_id": "supported_topology",
            "matches": inspection["topology"] in {"linear", "circular"},
            "canonical": expected_topology or "declared_by_genbank",
            "genbank": inspection["topology"],
        },
    ]
    if expected_topology:
        checks.append(
            {
                "check_id": "topology",
                "matches": inspection["topology"] == expected_topology,
                "canonical": expected_topology,
                "genbank": inspection["topology"],
            }
        )
    if record_id:
        checks.append(
            {
                "check_id": "record_identifier",
                "matches": inspection["record_identifier"] == record_id,
                "canonical": record_id,
                "genbank": inspection["record_identifier"],
            }
        )

    failed_checks = [check["check_id"] for check in checks if not check["matches"]]
    errors = list(inspection["errors"])
    if failed_checks:
        errors.append(
            "Canonical GenBank identity binding failed: " + ", ".join(failed_checks) + "."
        )
    status: AdapterStatus
    if errors:
        status = "FAIL"
    elif inspection["status"] == "PASS_WITH_WARNINGS":
        status = "PASS_WITH_WARNINGS"
    else:
        status = "PASS"

    return _result(
        status=status,
        inspection=inspection,
        identity_binding={
            "status": "FAIL" if failed_checks else "PASS",
            "canonical_record_id": record_id,
            "authoritative_construct_id": authoritative_construct_id,
            "authoritative_revision_id": authoritative_revision_id,
            "export_construct_id": export_construct_id,
            "export_revision_id": export_revision_id,
            "canonical_sequence_length": expected_length,
            "canonical_sequence_sha256": expected_checksum,
            "canonical_topology": expected_topology,
            "genbank_record_identifier": inspection["record_identifier"],
            "genbank_sequence_length": inspection["sequence_length"],
            "genbank_sequence_sha256": inspection["sequence_sha256"],
            "genbank_topology": inspection["topology"],
            "checks": checks,
        },
        errors=errors,
        source_sha256=source_sha256,
        source_kind=source_kind,
        file_name=file_name,
    )


__all__ = [
    "ADAPTER_SCHEMA_VERSION",
    "AUTHORITATIVE_GENBANK_SOURCE",
    "AUTHORITATIVE_IDENTITY_SOURCE",
    "CanonicalGenBankInspection",
    "inspect_canonical_genbank_export",
]
