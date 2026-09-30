"""Offline plant-vector contract loading and deterministic identity matching."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from functools import lru_cache
from io import StringIO
from pathlib import Path
from typing import Any, Mapping

from Bio import SeqIO


SCHEMA_VERSION = "vector-asset-contracts-v1"
CONTRACT_ROOT = Path(__file__).resolve().parents[1] / "data" / "vector_asset_contracts_v1"
CONTRACTS_PATH = CONTRACT_ROOT / "contracts.json"
ALLOWED_ASSET_KINDS = {
    "exact_insertion_source",
    "tDNA_replacement_source",
    "reference_vector",
    "hold_unverified_asset",
}
ALLOWED_OPERATION_KINDS = {"exact_insertion", "exact_replacement", "none"}
IDENTITY_STATUSES = {
    "EXACT_KNOWN_ASSET",
    "KNOWN_ACCESSION_SEQUENCE_MISMATCH",
    "KNOWN_SEQUENCE_METADATA_MISMATCH",
    "UNVERIFIED_UPLOADED_VECTOR",
    "NOT_A_VECTOR_ASSET",
}
REQUIRED_CONTRACT_FIELDS = {
    "schema_version",
    "contract_version",
    "asset_id",
    "display_name",
    "aliases",
    "accession_version",
    "record_id",
    "asset_kind",
    "operation_kind",
    "circular",
    "full_sequence_length",
    "full_sequence_sha256",
    "external_coordinate_contract",
    "internal_coordinate_contract",
    "operation_region_sha256",
    "supported_workflows",
    "blocked_workflows",
    "direct_design_allowed",
    "arbitrary_coordinate_allowed",
    "reference_view_allowed",
    "canonical_modification_allowed",
    "formal_selection_allowed",
    "retained_features",
    "protected_features",
    "warning_text",
    "source_evidence",
    "review_status",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class VectorAssetContractError(ValueError):
    """Raised when the packaged contract or a requested identity is invalid."""


def normalize_dna_sequence(value: Any) -> str:
    return "".join(str(value or "").split()).upper()


def sequence_sha256(value: Any) -> str:
    return hashlib.sha256(normalize_dna_sequence(value).encode("ascii")).hexdigest()


def _validate_coordinate_contract(contract: Mapping[str, Any]) -> None:
    operation_kind = str(contract["operation_kind"])
    external = contract["external_coordinate_contract"]
    internal = contract["internal_coordinate_contract"]
    if operation_kind == "exact_insertion":
        if not isinstance(external, dict) or external.get("cut_boundary") != "27|28":
            raise VectorAssetContractError("An exact-insertion contract requires the reviewed external cut boundary.")
        if not isinstance(internal, dict) or internal.get("cut_index") != 27:
            raise VectorAssetContractError("An exact-insertion contract requires the reviewed internal cut index.")
    elif operation_kind == "exact_replacement":
        if not isinstance(external, dict) or (external.get("start"), external.get("end")) != (4974, 7979):
            raise VectorAssetContractError("An exact-replacement contract requires the reviewed external region.")
        if not isinstance(internal, dict) or (internal.get("start"), internal.get("end")) != (4973, 7979):
            raise VectorAssetContractError("An exact-replacement contract requires the reviewed half-open region.")
        if not _SHA256_RE.fullmatch(str(contract.get("operation_region_sha256") or "")):
            raise VectorAssetContractError("An exact-replacement contract requires an operation-region SHA-256.")
    elif external is not None or internal is not None or contract.get("operation_region_sha256") is not None:
        raise VectorAssetContractError("A no-operation asset cannot define operation coordinates or a region hash.")


def _validate_contracts_payload(payload: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise VectorAssetContractError("The vector asset contract file has an unsupported schema version.")
    rows = payload.get("contracts")
    if not isinstance(rows, list) or not rows:
        raise VectorAssetContractError("The vector asset contract file must contain at least one contract.")
    asset_ids: set[str] = set()
    identity_tokens: dict[str, str] = {}
    validated: list[dict[str, Any]] = []
    for raw in rows:
        if not isinstance(raw, dict) or not REQUIRED_CONTRACT_FIELDS <= set(raw):
            missing = sorted(REQUIRED_CONTRACT_FIELDS - set(raw or {}))
            raise VectorAssetContractError("A vector asset contract is missing required fields: " + ", ".join(missing))
        contract = copy.deepcopy(raw)
        asset_id = str(contract.get("asset_id") or "")
        if not asset_id or asset_id in asset_ids:
            raise VectorAssetContractError(f"Duplicate or empty vector asset_id: {asset_id or '<empty>'}.")
        asset_ids.add(asset_id)
        aliases = contract.get("aliases")
        if not isinstance(aliases, list) or any(not str(value or "").strip() for value in aliases):
            raise VectorAssetContractError(f"Contract {asset_id} has invalid aliases.")
        for value in (contract.get("accession_version"), contract.get("record_id"), *aliases):
            token = str(value or "").strip().upper()
            if not token:
                continue
            owner = identity_tokens.get(token)
            if owner is not None and owner != asset_id:
                raise VectorAssetContractError(
                    f"Duplicate vector identity token {token} in contracts {owner} and {asset_id}."
                )
            identity_tokens[token] = asset_id
        if contract.get("schema_version") != SCHEMA_VERSION:
            raise VectorAssetContractError(f"Contract {asset_id} has an unsupported schema version.")
        if contract.get("asset_kind") not in ALLOWED_ASSET_KINDS:
            raise VectorAssetContractError(f"Contract {asset_id} has an unknown asset_kind.")
        if contract.get("operation_kind") not in ALLOWED_OPERATION_KINDS:
            raise VectorAssetContractError(f"Contract {asset_id} has an unknown operation_kind.")
        if not isinstance(contract.get("full_sequence_length"), int) or int(contract["full_sequence_length"]) <= 0:
            raise VectorAssetContractError(f"Contract {asset_id} has an invalid full_sequence_length.")
        if not _SHA256_RE.fullmatch(str(contract.get("full_sequence_sha256") or "")):
            raise VectorAssetContractError(f"Contract {asset_id} has an invalid full_sequence_sha256.")
        supported = set(contract.get("supported_workflows") or [])
        blocked = set(contract.get("blocked_workflows") or [])
        if supported & blocked:
            raise VectorAssetContractError(f"Contract {asset_id} supports and blocks the same workflow.")
        if contract.get("arbitrary_coordinate_allowed") is not False:
            raise VectorAssetContractError(f"Contract {asset_id} must block arbitrary coordinates.")
        if bool(contract.get("direct_design_allowed")) and contract.get("operation_kind") == "none":
            raise VectorAssetContractError(f"Direct-design contract {asset_id} requires an operation_kind.")
        if contract.get("asset_kind") in {"reference_vector", "hold_unverified_asset"}:
            if contract.get("operation_kind") != "none" or bool(contract.get("canonical_modification_allowed")):
                raise VectorAssetContractError(f"Reference/hold contract {asset_id} cannot allow canonical modification.")
        _validate_coordinate_contract(contract)
        validated.append(contract)
    return tuple(validated)


@lru_cache(maxsize=8)
def _load_contracts_cached(path_text: str, mtime_ns: int) -> tuple[dict[str, Any], ...]:
    del mtime_ns
    path = Path(path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VectorAssetContractError("The local vector asset contract file cannot be read.") from exc
    return _validate_contracts_payload(payload)


def load_vector_asset_contracts(path: Path | str | None = None) -> list[dict[str, Any]]:
    contract_path = Path(path or CONTRACTS_PATH).resolve()
    try:
        mtime_ns = contract_path.stat().st_mtime_ns
    except OSError as exc:
        raise VectorAssetContractError("The local vector asset contract file does not exist.") from exc
    return copy.deepcopy(list(_load_contracts_cached(str(contract_path), mtime_ns)))


def vector_asset_contract(asset_id: str) -> dict[str, Any]:
    match = next((row for row in load_vector_asset_contracts() if row["asset_id"] == asset_id), None)
    if match is None:
        raise VectorAssetContractError(f"Unknown vector asset_id: {asset_id}.")
    return match


def _identity_tokens(contract: Mapping[str, Any]) -> set[str]:
    values = [
        contract.get("accession_version"),
        contract.get("record_id"),
        *list(contract.get("aliases") or []),
    ]
    return {str(value).strip().upper() for value in values if str(value or "").strip()}


@lru_cache(maxsize=16)
def _contract_source_sequence(asset_id: str) -> str:
    contract = vector_asset_contract(asset_id)
    evidence = next(
        (row for row in contract["source_evidence"] if str(row.get("local_record_path") or "")),
        None,
    )
    if not evidence:
        raise VectorAssetContractError(f"Contract {asset_id} does not identify a local source record.")
    source_path = Path(__file__).resolve().parents[1] / str(evidence["local_record_path"])
    try:
        record = SeqIO.read(source_path, "genbank")
    except Exception as exc:
        raise VectorAssetContractError(f"The local source record for {asset_id} cannot be parsed.") from exc
    sequence = normalize_dna_sequence(record.seq)
    if len(sequence) != int(contract["full_sequence_length"]) or sequence_sha256(sequence) != contract["full_sequence_sha256"]:
        raise VectorAssetContractError(f"The local source record for {asset_id} differs from its reviewed contract.")
    return sequence


def _rotation_equivalent(candidate: str, canonical: str) -> bool:
    return bool(candidate and len(candidate) == len(canonical) and candidate in (canonical + canonical))


def _record_accession(record: Mapping[str, Any]) -> str:
    for key in ("source_accession_version", "accession_version", "original_record_identifier", "record_id"):
        value = str(record.get(key) or "").strip().upper()
        if value:
            return value
    asset = record.get("asset") if isinstance(record.get("asset"), Mapping) else {}
    return str(asset.get("original_record_identifier") or "").strip().upper()


def classify_vector_asset(record: Mapping[str, Any] | None) -> dict[str, Any]:
    """Classify from record content; display names and file names are never identity inputs."""
    source = record if isinstance(record, Mapping) else {}
    sequence = normalize_dna_sequence(
        source.get("normalized_sequence")
        or source.get("nucleotide_sequence")
        or (source.get("asset") or {}).get("nucleotide_sequence")
    )
    if not sequence:
        raw_text = str(source.get("original_text") or source.get("raw_text") or "")
        if raw_text.strip():
            try:
                parsed = SeqIO.read(StringIO(raw_text), "genbank")
            except Exception:
                parsed = None
            if parsed is not None:
                sequence = normalize_dna_sequence(parsed.seq)
                source = {
                    **dict(source),
                    "topology": source.get("topology") or parsed.annotations.get("topology"),
                    "original_record_identifier": source.get("original_record_identifier") or parsed.id,
                }
    if not sequence:
        return {
            "identity_status": "NOT_A_VECTOR_ASSET",
            "asset_id": None,
            "asset_kind": None,
            "operation_kind": "none",
            "read_only": True,
            "reason": "No complete vector sequence was available for identity matching.",
        }
    observed_accession = _record_accession(source)
    topology = str(source.get("topology") or (source.get("asset") or {}).get("topology") or "").lower()
    contracts = load_vector_asset_contracts()
    accession_match = next((row for row in contracts if observed_accession in _identity_tokens(row)), None)
    sequence_match: dict[str, Any] | None = None
    rotation_equivalent = False
    observed_hash = sequence_sha256(sequence)
    for contract in contracts:
        if len(sequence) != int(contract["full_sequence_length"]):
            continue
        if observed_hash == contract["full_sequence_sha256"]:
            sequence_match = contract
            break
        if bool(contract["circular"]) and _rotation_equivalent(sequence, _contract_source_sequence(contract["asset_id"])):
            sequence_match = contract
            rotation_equivalent = True
            break
    if sequence_match is not None:
        accession_conflict = accession_match is not None and accession_match["asset_id"] != sequence_match["asset_id"]
        topology_matches = topology == ("circular" if sequence_match["circular"] else "linear")
        if accession_conflict or not topology_matches:
            return {
                "identity_status": "KNOWN_SEQUENCE_METADATA_MISMATCH",
                "asset_id": None,
                "matched_asset_id": sequence_match["asset_id"],
                "asset_kind": "unverified_uploaded_vector",
                "operation_kind": "none",
                "read_only": True,
                "sequence_sha256": observed_hash,
                "rotation_equivalent": rotation_equivalent,
                "reason": "The sequence matches a known asset, but accession or topology metadata does not match its contract.",
            }
        return {
            "identity_status": "EXACT_KNOWN_ASSET",
            "asset_id": sequence_match["asset_id"],
            "asset_kind": sequence_match["asset_kind"],
            "operation_kind": sequence_match["operation_kind"],
            "read_only": not bool(sequence_match["direct_design_allowed"]),
            "sequence_sha256": observed_hash,
            "rotation_equivalent": rotation_equivalent,
            "contract": copy.deepcopy(sequence_match),
            "reason": "The complete sequence, length, and topology match the reviewed vector asset contract.",
        }
    if accession_match is not None:
        return {
            "identity_status": "KNOWN_ACCESSION_SEQUENCE_MISMATCH",
            "asset_id": None,
            "matched_asset_id": accession_match["asset_id"],
            "asset_kind": "unverified_uploaded_vector",
            "operation_kind": "none",
            "read_only": True,
            "sequence_sha256": observed_hash,
            "rotation_equivalent": False,
            "reason": "The accession identifies a known asset, but the complete sequence does not match its reviewed contract.",
        }
    return {
        "identity_status": "UNVERIFIED_UPLOADED_VECTOR",
        "asset_id": None,
        "asset_kind": "unverified_uploaded_vector",
        "operation_kind": "none",
        "read_only": True,
        "sequence_sha256": observed_hash,
        "rotation_equivalent": False,
        "reason": "The complete vector has no reviewed operation contract and is read-only.",
    }
